"""用真实pytest重复doctest核可信适配、旧身份保护与公开失败事实。"""
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from project_library import digest_json
from project_verifier import ProjectVerifier, _NativeRegressionControlError, _native_regression_adapter
from projects_verification import ProjectsVerification


class DuplicateAdapterTests(unittest.TestCase):
    """新API示例不污染旧合同，旧节点、次数或结果变化仍拒绝。"""

    @classmethod
    def setUpClass(cls):
        """读取原可信控制器并提取真实收集函数。@return None。"""
        cls.runner = Path(__file__).resolve().parents[1] / 'project_library/projects/babel/verification/native_regression.py'
        cls.original = cls.runner.read_bytes()

    def setUp(self):
        """为真实pytest子进程建立独立可信样例目录。@return None。"""
        temporary = tempfile.TemporaryDirectory(prefix='duplicate-adapter-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.example = self.root / 'sample.py'
        self.base = 'def stable():\n    """\n    >>> stable()\n    1\n    """\n    return 1\n'
        self.example.write_text(self.base)

    def collect(self, source, required, copies=2):
        """实际收集并运行重复doctest，控制函数取自产品实际执行字节。

        :param source: 原控制器或产品生成的适配字节。
        :param required: 冻结节点列表。
        :param copies: 同一模块真实收集次数。
        :return: pytest退出码、完整结构化收集事实。
        """
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name == 'pytest_collection_modifyitems')
        collector = ast.unparse(function)
        output = self.root / 'collection.json'
        plugin = '''import json
from collections import Counter
from pathlib import Path
state={'control':{'project':str(Path.cwd()),'required_nodes':REQUIRED,'duplicate_ids':True},'errors':[]}
namespace={'Counter':Counter,'Path':Path,'_state':lambda:state}
exec(COLLECTOR,namespace)
def pytest_collection_modifyitems(session,config,items):namespace['pytest_collection_modifyitems'](session,config,items)
def pytest_runtest_logreport(report):
    if report.when=='call':state.setdefault('outcomes',[]).append({'id':report.nodeid,'outcome':report.outcome})
def pytest_sessionfinish(session,exitstatus):Path(OUTPUT).write_text(json.dumps(state))
'''.replace('REQUIRED', repr(required)).replace('COLLECTOR', repr(collector)).replace('OUTPUT', repr(str(output)))
        (self.root / 'control_plugin.py').write_text(plugin)
        environment = {**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONPATH': str(self.root)}
        result = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-p', 'control_plugin',
            '--doctest-modules', '--keep-duplicates', *(['sample.py'] * copies), '-q', '-p', 'no:cacheprovider'],
            cwd=self.root, env=environment, capture_output=True, text=True, timeout=30)
        self.assertTrue(output.exists(), result.stdout + result.stderr)
        return result.returncode, json.loads(output.read_text())

    def frozen(self):
        """用真实原doctest建立本测试的重复身份合同。@return 合同。"""
        code, state = self.collect(self.original, [])
        self.assertEqual(0, code)
        self.assertEqual(2, len(state['duplicate_identities']))
        return {'project': 'babel', 'nodes': [{**item, 'outcome': 'passed'} for item in state['collection']],
            'duplicate_identities': state['duplicate_identities']}

    def test_new_api_doctest_is_filtered_after_real_duplicate_collection(self):
        """原算法误报4对2，适配后原两节点真实执行且身份完全相等。@return None。"""
        contract = self.frozen()
        required = [item['id'] for item in contract['nodes']]
        self.example.write_text(self.base + '\ndef added_api():\n    """\n    >>> added_api()\n    2\n    """\n    return 999\n')
        code, old = self.collect(self.original, required)
        self.assertEqual(0, code)
        self.assertEqual(4, len(old['duplicate_identities']))
        actual, facts = _native_regression_adapter(self.original, contract)
        code, current = self.collect(actual, required)
        self.assertEqual(0, code)
        self.assertEqual(contract['duplicate_identities'], current['duplicate_identities'])
        self.assertEqual([], current['errors'])
        self.assertEqual(required, [item['id'] for item in current['collection']])
        self.assertEqual(['passed', 'passed'], [item['outcome'] for item in current['outcomes']])
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), facts['original_runner_sha256'])
        self.assertEqual(hashlib.sha256(actual).hexdigest(), facts['effective_runner_sha256'])

    def test_original_node_removal_rename_failure_and_extra_occurrence_are_rejected(self):
        """原节点少、身份改、结果坏或重复次数增都不能被新范围规则隐藏。@return None。"""
        contract = self.frozen()
        required = [item['id'] for item in contract['nodes']]
        adapted, _ = _native_regression_adapter(self.original, contract)
        cases = [('def replacement():\n    return 1\n', 2, 'missing_frozen_nodes'),
            (self.base.replace('stable', 'renamed'), 2, 'missing_frozen_nodes'),
            (self.base.replace('return 1', 'return 9'), 2, 'failed'),
            (self.base, 3, 'extra_frozen_duplicate_occurrences')]
        for content, copies, expected in cases:
            with self.subTest(expected=expected):
                self.example.write_text(content)
                code, state = self.collect(adapted, required, copies)
                if expected == 'failed':
                    self.assertNotEqual(0, code)
                    self.assertTrue(any(item['outcome'] == 'failed' for item in state['outcomes']))
                else:
                    self.assertTrue(any(expected in error for error in state['errors']), state)

    def test_unknown_runner_and_nonunique_known_fragment_are_rejected(self):
        """未知源码不凭片段猜测，已知版本也要求唯一精确片段。@return None。"""
        contract = self.frozen()
        with self.assertRaises(_NativeRegressionControlError):
            _native_regression_adapter(self.original + b'\n', contract)
        from project_verifier import _DUPLICATE_COLLECTOR
        source = self.original + _DUPLICATE_COLLECTOR.encode()
        with patch('project_verifier._DUPLICATE_RUNNER_SHA256', {hashlib.sha256(source).hexdigest()}):
            with self.assertRaises(_NativeRegressionControlError):
                _native_regression_adapter(source, contract)
        self.assertEqual((b'unknown', None), _native_regression_adapter(b'unknown', {'nodes': []}))

    def test_product_stages_actual_runner_outside_readonly_verification_mount(self):
        """真实产品入口执行input根可信副本，并继续主机核完整重复身份。@return None。"""
        contract = self.frozen()
        project = self.root / 'project'
        (project / 'verification').mkdir(parents=True)
        (project / 'seed').mkdir()
        (project / 'verification/native.py').write_bytes(self.original)
        (project / 'verification/contract.json').write_text(json.dumps(contract))
        (self.root / 'candidate').mkdir()
        (self.root / 'environment').mkdir()
        client = Mock()
        child = Mock(status='running', id='test-container')
        actual = {'status': 'passed', 'collection_matches_contract': True, 'collected': 2,
            'collection_digest': digest_json([{'id': item['id'], 'kind': item['kind']} for item in contract['nodes']]),
            'duplicate_identities': contract['duplicate_identities']}
        child.logs.return_value = b'VIBEBENCH_NATIVE_READY_V1\n' + json.dumps(actual).encode()
        child.wait.return_value = {'StatusCode': 0}
        captured = []

        def create(*args, **kwargs):
            directory = next(Path(path) for path, mount in kwargs['volumes'].items() if mount['bind'] == '/request-data')
            self.assertTrue((directory / 'verification').is_dir())
            payload = json.loads((directory / 'native.json').read_text())
            self.assertEqual('trusted-native-regression.py', payload['script'])
            staged = (directory / payload['script']).read_bytes()
            self.assertNotEqual(self.original, staged)
            captured.append(hashlib.sha256(staged).hexdigest())
            return child

        client.containers.create.side_effect = create
        verifier = ProjectVerifier(client, self.root, self.root, 'test-image')
        specification = {'regression': {'runner': 'verification/native.py', 'contract': 'verification/contract.json'}}
        profile = {'requirements': ['pytest==9.1.1'], 'regression': {'memory_mb': 512, 'pids_limit': 64, 'timeout_sec': 60}}
        result = verifier.verify_native(self.root / 'candidate', project, specification, self.root / 'environment', profile, regression=True)
        self.assertEqual('passed', result['status'])
        self.assertEqual(captured[0], result['runtime_adapter']['effective_runner_sha256'])
        self.assertEqual(self.original, (project / 'verification/native.py').read_bytes())
        actual['duplicate_identities'] = actual['duplicate_identities'][:-1]
        child.logs.return_value = b'VIBEBENCH_NATIVE_READY_V1\n' + json.dumps(actual).encode()
        self.assertEqual('failed', verifier.verify_native(self.root / 'candidate', project, specification,
            self.root / 'environment', profile, regression=True)['status'])

    def test_public_failure_facts_keep_counts_and_reasons_with_bounded_structure(self):
        """先保留失败计数，再裁剪大业务值，绝不透传原数组或日志。@return None。"""
        report = {'status': 'failed', 'business': {'status': 'passed', 'actual': {str(index): '\x00' * 10000 for index in range(32)}},
            'regression': {'status': 'failed', 'reason': 'collection_identity_mismatch', 'regression': {
                'status': 'failed', 'counts': {'passed': 7989, 'skipped': 7, 'xfailed': 2, 'failed': 0, 'private': 99},
                'collected': 7998, 'collection_matches_contract': True,
                'duplicate_execution_count': 320, 'collection_errors': ['extra_frozen_duplicate_occurrences:1'],
                'duplicate_identities': ['private'] * 10000, 'stdout_tail': 'private log', 'stderr': 'private stderr'}}}
        facts = ProjectsVerification._public_facts(report)
        self.assertEqual('collection_identity_mismatch', facts['regression']['reason'])
        self.assertEqual(7989, facts['regression']['regression']['counts']['passed'])
        self.assertEqual(320, facts['regression']['regression']['duplicate_execution_count'])
        text = json.dumps(facts, ensure_ascii=False)
        self.assertNotIn('private log', text)
        self.assertNotIn('duplicate_identities', text)
        self.assertNotIn('"private"', text)
        self.assertLess(len(text.encode()), 13 * 1024)
        self.assertTrue(facts['facts_truncated'])


if __name__ == '__main__':
    unittest.main()
