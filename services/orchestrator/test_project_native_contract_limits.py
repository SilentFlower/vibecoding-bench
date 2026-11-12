"""完整原生回归合同独立读取上限与普通JSON隔离的回归。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from project_library import MAX_JSON_BYTES, canonical_json, digest_json, read_document
from project_scenario_content import MAX_NATIVE_CONTRACT_BYTES, _native_specification, read_native_contract
from project_verifier import ProjectVerifier


class NativeContractLimitTests(unittest.TestCase):
    """保留全部原生节点，只扩大合同文件且检查真实字节边界。"""

    def setUp(self) -> None:
        """建立临时私有验证目录。@return None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.verification = self.root / 'verification'
        self.verification.mkdir()
        self.contract = self.verification / 'contract.json'

    def test_large_contract_preserves_every_node_but_generic_json_stays_limited(self) -> None:
        """数万真实结构节点超过4MiB仍全量读取，普通JSON读法继续拒绝。@return None。"""
        value = {'schema': 1, 'nodes': [
            {'id': f'tests/case_{index:05d}/' + 'boundary_' * 15, 'kind': 'Function', 'outcome': 'passed'}
            for index in range(26000)]}
        content = canonical_json(value)
        self.assertGreater(len(content), MAX_JSON_BYTES)
        self.assertLess(len(content), MAX_NATIVE_CONTRACT_BYTES)
        self.contract.write_bytes(content)
        self.assertEqual(value, read_native_contract(self.contract))
        with self.assertRaisesRegex(ValueError, 'JSON'):
            read_document(self.contract)
        for name in ('observe.py', 'native_regression.py'):
            (self.verification / name).write_text('')
        specification = {'script': 'verification/observe.py', 'args': [], 'python_paths': ['library'],
            'expected': {'business': True}, 'regression': {'runner': 'verification/native_regression.py',
            'contract': 'verification/contract.json'}}
        spec_path = self.verification / 'native.json'
        spec_path.write_bytes(canonical_json(specification))
        _native_specification(self.root, 'verification/native.json')
        specification['padding'] = 'x' * (MAX_JSON_BYTES + 1)
        spec_path.write_bytes(canonical_json(specification))
        with self.assertRaisesRegex(ValueError, 'JSON'):
            _native_specification(self.root, 'verification/native.json')

    def test_exact_sixteen_mib_is_accepted_and_one_extra_byte_is_rejected(self) -> None:
        """以实际UTF8字节计量，不用节点计数或格式压缩掩盖边界。@return None。"""
        prefix = b'{"schema":1,"nodes":[]}'
        self.contract.write_bytes(prefix + b' ' * (MAX_NATIVE_CONTRACT_BYTES - len(prefix)))
        self.assertEqual({'schema': 1, 'nodes': []}, read_native_contract(self.contract))
        with self.contract.open('ab') as target:
            target.write(b' ')
        with self.assertRaisesRegex(ValueError, '大小'):
            read_native_contract(self.contract)

    def test_regression_adapter_reads_large_contract_without_losing_frozen_nodes(self) -> None:
        """真实适配器读取同一大合同并核全量集合摘要，Docker仅用替身。@return None。"""
        nodes = [{'id': f'tests/case_{index:05d}/' + 'boundary_' * 15,
            'kind': 'Function', 'outcome': 'passed'} for index in range(70000)]
        contract = {'schema': 1, 'project': 'large-fixture', 'nodes': nodes}
        self.contract.write_bytes(canonical_json(contract))
        self.assertGreater(self.contract.stat().st_size, 8 * 1024 * 1024)
        (self.verification / 'native_regression.py').write_text('')
        for name in ('seed', 'candidate', 'environment'):
            (self.root / name).mkdir()
        actual = {'status': 'passed', 'collection_matches_contract': True, 'collected': len(nodes),
            'collection_digest': digest_json([{'id': node['id'], 'kind': node['kind']} for node in nodes])}
        container = Mock(status='running', id='isolated-fixture')
        container.logs.return_value = b'VIBEBENCH_NATIVE_READY_V1\n' + canonical_json(actual)
        container.wait.return_value = {'StatusCode': 0}
        client = Mock()
        client.containers.create.return_value = container
        verifier = ProjectVerifier(client, self.root, self.root, 'fixture-image')
        result = verifier.verify_native(self.root / 'candidate', self.root, {'regression': {
            'runner': 'verification/native_regression.py', 'contract': 'verification/contract.json'}},
            self.root / 'environment', {'requirements': ['fixture==1.0'],
            'regression': {'memory_mb': 512, 'pids_limit': 64, 'timeout_sec': 60}}, regression=True)
        self.assertEqual('passed', result['status'])
        self.assertEqual(digest_json(contract), result['contract_digest'])
        self.assertEqual(70000, result['regression']['collected'])
        self.assertEqual('none', client.containers.create.call_args.kwargs['network_mode'])
        container.remove.assert_called_once_with(force=True)

    def test_read_bound_still_rejects_growth_after_metadata(self) -> None:
        """元信息检查后文件增长也不能越过有界read。@return None。"""
        self.contract.write_bytes(b' ' * (MAX_NATIVE_CONTRACT_BYTES + 1))
        mode = self.contract.stat().st_mode
        with patch('project_scenario_content.os.fstat', return_value=SimpleNamespace(st_mode=mode, st_size=0)):
            with self.assertRaisesRegex(ValueError, '超出大小'):
                read_native_contract(self.contract)

    def test_symlink_directory_and_fifo_are_rejected_without_blocking(self) -> None:
        """类型限制保持，FIFO通过非阻塞打开后直接拒绝。@return None。"""
        self.contract.write_text('{}')
        link = self.verification / 'link.json'
        link.symlink_to(self.contract)
        with self.assertRaises(OSError):
            read_native_contract(link)
        with self.assertRaisesRegex(ValueError, '类型'):
            read_native_contract(self.verification)
        fifo = self.verification / 'pipe.json'
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, '类型'):
            read_native_contract(fifo)

    def test_invalid_json_and_invalid_node_shape_remain_rejected(self) -> None:
        """容量例外不能绕过JSON或冻结节点内容校验。@return None。"""
        self.contract.write_text('{invalid')
        with self.assertRaises(json.JSONDecodeError):
            read_native_contract(self.contract)
        self.contract.write_text('{"schema":1,"nodes":[{"id":"missing-fields"}]}')
        for name in ('observe.py', 'native_regression.py'):
            (self.verification / name).write_text('')
        (self.verification / 'native.json').write_bytes(canonical_json({
            'script': 'verification/observe.py', 'args': [], 'python_paths': ['library'], 'expected': {},
            'regression': {'runner': 'verification/native_regression.py', 'contract': 'verification/contract.json'}}))
        with self.assertRaisesRegex(ValueError, '冻结节点合同'):
            _native_specification(self.root, 'verification/native.json')


if __name__ == '__main__':
    unittest.main()
