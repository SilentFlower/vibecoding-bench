"""加权聚合观察器的空值合同修复、冻结保护及严格结果协议回归。"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from project_verifier import ProjectVerifier, _native_weighted_adapter


class WeightedAdapterTests(unittest.TestCase):
    """只适配已确认的旧版本，不能隐藏错误结果或修改旧资产。"""

    def setUp(self):
        """读取冻结旧观察器和未来使用的修正版。@return None。"""
        root = Path(__file__).resolve().parent
        self.original = (root / 'testdata/weighted-observer-legacy.txt').read_bytes()
        self.current = (root.parent / 'project_library/projects/agate/verification/AG-WEIGHTED-DEV-observe.py').read_bytes()
        self.spec = {'script': 'verification/AG-WEIGHTED-DEV-observe.py', 'args': [],
            'python_paths': ['library'], 'expected': {'candidate_import': True, 'business': True}}

    def test_exact_legacy_version_maps_to_current_and_unknown_protocol_is_unchanged(self):
        """源码摘要、脚本和布尔协议均须精确匹配，不能凭文件名推测修复。@return None。"""
        self.assertEqual('04e8a3a7fc1b09c9e6966697bbfe1908a0c5b66ebfc90209d16c7266c500bd5e',
            hashlib.sha256(self.original).hexdigest())
        self.assertEqual('e0e953f723d91ebf42032ad8afed8201ac244a55906d1b8ad43d035c80f4153e',
            hashlib.sha256(self.current).hexdigest())
        actual, facts = _native_weighted_adapter(self.original, self.spec)
        self.assertEqual(self.current, actual)
        self.assertEqual('weighted-null-pair-contract-v1', facts['name'])
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), facts['original_runner_sha256'])
        self.assertEqual(hashlib.sha256(self.current).hexdigest(), facts['effective_runner_sha256'])
        self.assertIs(True, facts['preserves_frozen_contract'])
        for source in (self.original + b'\n', self.current):
            self.assertEqual((source, None), _native_weighted_adapter(source, self.spec))
        for change in ({'script': 'verification/other.py'}, {'args': ['--different']},
                {'python_paths': ['other']}, {'expected': {'business': True}},
                {'expected': {'candidate_import': 1, 'business': True}},
                {'expected': {'candidate_import': True, 'business': 1}},
                {'expected': {'candidate_import': True, 'business': True, 'extra': True}}):
            with self.subTest(change=change):
                self.assertEqual((self.original, None),
                    _native_weighted_adapter(self.original, {**self.spec, **change}))

    def test_real_entry_stages_fixed_bytes_without_relaxing_two_field_json(self):
        """真实入口只执行临时可信副本，额外字段和数值冒充布尔均不通过。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / 'project'
            for relative in ('project/verification', 'project/seed', 'candidate', 'environment'):
                (root / relative).mkdir(parents=True)
            observer = project / self.spec['script']
            observer.write_bytes(self.original)
            child = Mock(status='running', id='weighted-test')
            child.wait.return_value = {'StatusCode': 0}
            client = Mock()
            staged = []

            def create(*args, **kwargs):
                directory = next(Path(path) for path, mount in kwargs['volumes'].items()
                    if mount['bind'] == '/request-data')
                payload = json.loads((directory / 'native.json').read_text())
                staged.append((payload['script'], (directory / payload['script']).read_bytes()))
                self.assertEqual('none', kwargs['network_mode'])
                self.assertEqual('ro', kwargs['volumes'][str(project / 'verification')]['mode'])
                self.assertEqual(self.original, observer.read_bytes())
                return child

            client.containers.create.side_effect = create
            verifier = ProjectVerifier(client, root, root, 'fixture-image')
            profile = {'requirements': ['fixture==1'],
                'business': {'memory_mb': 512, 'pids_limit': 64, 'timeout_sec': 60}}
            cases = [({'candidate_import': True, 'business': True}, 'passed'),
                ({'candidate_import': True, 'business': False}, 'failed'),
                ({'candidate_import': False, 'business': True}, 'failed'),
                ({'candidate_import': 1, 'business': True}, 'failed'),
                ({'candidate_import': True, 'business': 1}, 'failed'),
                ({'candidate_import': True, 'business': True, 'extra': True}, 'failed'),
                ({'candidate_import': True, 'business': True, 'feedback_codes': []}, 'failed'),
                ({'candidate_import': True}, 'failed')]
            for actual, expected in cases:
                with self.subTest(actual=actual):
                    child.logs.return_value = b'VIBEBENCH_NATIVE_READY_V1\n' + json.dumps(actual).encode()
                    result = verifier.verify_native(root / 'candidate', project, self.spec,
                        root / 'environment', profile)
                    self.assertEqual(expected, result['status'])
                    self.assertEqual(actual, result['actual'])
                    self.assertEqual('weighted-null-pair-contract-v1', result['runtime_adapter']['name'])
                    self.assertNotIn('feedback_codes', result)
                    self.assertEqual(('trusted-native-business.py', self.current), staged[-1])
            # 协议不符时仍按原脚本运行，不能偷偷应用已确认修复或取得适配器审计标记。
            mismatch = {**self.spec, 'args': ['--different']}
            actual = {'candidate_import': True, 'business': False}
            child.logs.return_value = b'VIBEBENCH_NATIVE_READY_V1\n' + json.dumps(actual).encode()
            result = verifier.verify_native(root / 'candidate', project, mismatch,
                root / 'environment', profile)
            self.assertEqual('failed', result['status'])
            self.assertNotIn('runtime_adapter', result)
            self.assertEqual((self.spec['script'], self.original), staged[-1])
            self.assertEqual(self.original, observer.read_bytes())


if __name__ == '__main__':
    unittest.main()
