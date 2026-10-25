"""Arrow 冻结验收的精确修复、失败归属和公开事实边界。"""
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from project_library import digest_json
from project_verifier import ProjectVerifier, _NativeRegressionControlError, _native_arrow_adapter, _native_failure_facts
from projects_verification import ProjectsVerification


class ArrowAdapterTests(unittest.TestCase):
    """合法的异常选择不误判，错误实现不能靠兼容适配获得通过。"""

    def setUp(self):
        """读取实际产品源码与冻结旧版本。:return: None。"""
        self.root = Path(__file__).resolve().parent
        self.project = self.root.parent / 'project_library/projects/arrow'
        self.runner = (self.project / 'verification/expansion_regression.py').read_bytes()
        self.legacy = (self.root / 'testdata/arrow-expansion-coverage-legacy.txt').read_bytes()
        self.current = (self.project / 'verification/expansion_coverage.py').read_bytes()

    def test_legacy_and_current_helpers_use_identical_precise_fix(self):
        """只修空列表的异常子类选择，非空错误类型的严格检查继续保留。:return: None。"""
        for helper in (self.legacy, self.current):
            _, fixed, receipt = _native_arrow_adapter(self.runner, helper, {'project': 'arrow'})
            self.assertEqual(self.current, fixed)
            self.assertTrue(receipt['preserves_frozen_contract'])
            self.assertEqual(hashlib.sha256(helper).hexdigest(), receipt['original_helper_sha256'])
        for source, helper, contract in [(self.runner + b'\n', self.legacy, {'project': 'arrow'}),
                (self.runner, self.legacy + b'\n', {'project': 'arrow'}), (self.runner, self.legacy, {'project': 'other'})]:
            with self.assertRaises(_NativeRegressionControlError):
                _native_arrow_adapter(source, helper, contract)

    def test_empty_list_error_variants_are_accepted_but_accepting_invalid_input_fails(self):
        """真实辅助函数接受合同允许的两种拒绝，错误类型或未拒绝都失败。:return: None。"""
        namespace = {'__file__': str(self.project / 'verification/expansion_coverage.py')}
        exec(compile(self.current, namespace['__file__'], 'exec'), namespace)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = SimpleNamespace(__file__=str(root / 'arrow.py'), Arrow=SimpleNamespace())
            for variant in (TypeError, ValueError, None, RuntimeError):
                class Reader:
                    """只实现当前辅助验收会用到的严格解析边界。"""

                    def parse(self, *args):
                        """保持非目标星期功能关闭。:param args: 原参数。:return: 非ISO星期结果。"""
                        return SimpleNamespace(isoweekday=lambda: 1)

                    def parse_strict(self, text, formats, *args, **kwargs):
                        """模拟候选的边界行为。:param text: 输入。:param formats: 格式。:return: 日期观察。"""
                        if formats == []:
                            if variant:
                                raise variant('候选公开参数拒绝')
                            return None
                        if formats in ([3], None) or kwargs.get('exact_width') == 1:
                            raise TypeError('错误参数')
                        if text in ('2025-W53-1', '123'):
                            raise ParserError('日历边界')
                        return SimpleNamespace(month=12, year=2027)

                class ParserError(ValueError):
                    """表示候选预期的日期解析拒绝。"""

                parser = SimpleNamespace(DateTimeParser=Reader, ParserError=ParserError)
                public = {f'test_{index}': lambda: None for index in range(6)}
                with patch.dict(sys.modules, {'arrow': module, 'arrow.parser': parser}), patch.object(
                        namespace['runpy'], 'run_path', side_effect=lambda path: public if 'coverage-public' in str(path) else {'business': True}):
                    if variant in (TypeError, ValueError):
                        namespace['cover_features'](root, root)
                    else:
                        with self.assertRaises((AssertionError, RuntimeError)):
                            namespace['cover_features'](root, root)

    def test_feature_probe_failure_does_not_corrupt_original_pytest_node(self):
        """真实pytest仍通过原节点，新增边界失败单列且不暴露断言原文。:return: None。"""
        runner, _, _ = _native_arrow_adapter(self.runner, self.legacy, {'project': 'arrow'})
        tree = ast.parse(runner)
        hook = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'hook' for target in node.targets)))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_original.py').write_text('def test_original():\n    assert 2 + 2 == 4\n')
            (root / 'control.json').write_text(json.dumps({'project': str(root), 'evidence': str(root)}))
            prefix = '''import pytest,json,os
from pathlib import Path
from types import SimpleNamespace
def fail(*args):raise ValueError('PRIVATE_ASSERTION_AND_SECRET')
runpy=SimpleNamespace(run_path=lambda path:{'cover_features':fail})
'''
            (root / 'control_plugin.py').write_text(prefix + hook)
            environment = {**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONPATH': str(root),
                           'BENCH_NATIVE_CONTROL': str(root / 'control.json')}
            result = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'control_plugin', 'test_original.py', '-q',
                '-p', 'no:cacheprovider'], cwd=root, env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            probe = json.loads((root / 'expansion-coverage.json').read_text())
            self.assertEqual('failed', probe['status'])
            self.assertEqual('ValueError', probe['exception_type'])
            facts = _native_failure_facts({'expansion_coverage': probe})
            self.assertEqual('feature_coverage', facts[0]['phase'])
            self.assertNotIn('PRIVATE_ASSERTION', json.dumps(facts))

    def test_public_diagnostics_have_node_and_exception_but_no_private_log(self):
        """模型可定位公开节点，原日志、私有堆栈、异常正文不会透传。:return: None。"""
        report = {'status': 'failed', 'stdout_tail': 'PRIVATE_CODE\nERROR tests/test_api.py::TestModule::test_get - ValueError: sk-private-secret\n'}
        report['failure_facts'] = _native_failure_facts(report)
        public = ProjectsVerification._public_facts(report)
        self.assertEqual('tests/test_api.py::TestModule::test_get', public['failure_facts'][0]['test_id'])
        self.assertEqual('ValueError', public['failure_facts'][0]['exception_type'])
        self.assertNotIn('sk-private-secret', json.dumps(public))
        self.assertNotIn('PRIVATE_CODE', json.dumps(public))

    def test_product_entry_overlays_helper_without_writing_frozen_assets(self):
        """真实入口同时使用可信wrapper和只读辅助挂载，旧合同及文件保持原字节。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / 'project'
            for relative in ('project/verification', 'project/seed', 'candidate', 'environment'):
                (root / relative).mkdir(parents=True)
            (project / 'verification/expansion_regression.py').write_bytes(self.runner)
            (project / 'verification/expansion_coverage.py').write_bytes(self.legacy)
            contract = {'project': 'arrow', 'nodes': [{'id': 'tests/test_original.py::test_original', 'kind': 'Function', 'outcome': 'passed'}]}
            actual = {'status': 'passed', 'collection_matches_contract': True, 'collected': 1,
                      'collection_digest': digest_json([{'id': contract['nodes'][0]['id'], 'kind': 'Function'}])}
            child = Mock(status='running', id='arrow-test')
            child.wait.return_value = {'StatusCode': 0}
            child.logs.return_value = b'VIBEBENCH_NATIVE_READY_V1\n' + json.dumps(actual).encode()
            client = Mock()

            def create(*args, **kwargs):
                """核对真实Docker入参和暂存文件。:param args: 镜像。:param kwargs: 创建参数。:return: 容器替身。"""
                staged = next(Path(path) for path, mount in kwargs['volumes'].items()
                    if mount['bind'] == '/request-data/verification/expansion_coverage.py')
                self.assertEqual(self.current, staged.read_bytes())
                self.assertEqual(self.legacy, (project / 'verification/expansion_coverage.py').read_bytes())
                self.assertEqual('none', kwargs['network_mode'])
                return child

            client.containers.create.side_effect = create
            verifier = ProjectVerifier(client, root, root, 'fixture-image')
            profile = {'requirements': ['fixture==1'], 'regression': {'memory_mb': 512, 'pids_limit': 64, 'timeout_sec': 60}}
            specification = {'regression': {'runner': 'verification/expansion_regression.py', 'contract': 'verification/contract.json'}}
            with patch('project_verifier.read_native_contract', return_value=contract):
                result = verifier.verify_native(root / 'candidate', project, specification, root / 'environment', profile, regression=True)
            self.assertEqual('passed', result['status'])
            self.assertEqual('arrow-feature-boundaries-v1', result['runtime_adapter']['name'])

    def test_coverage_gate_is_reported_as_actual_numbers_without_guessing(self):
        """覆盖率失败给出原门槛和真实值，不伪造某项原测试报错。:return: None。"""
        report = {'stdout_tail': 'FAIL Required test coverage of 99% not reached. Total coverage: 98.88%'}
        facts = _native_failure_facts(report)
        self.assertEqual('coverage', facts[0]['phase'])
        self.assertEqual(99, facts[0]['required_percent'])
        self.assertEqual(98.88, facts[0]['actual_percent'])
        self.assertNotIn('test_id', facts[0])
