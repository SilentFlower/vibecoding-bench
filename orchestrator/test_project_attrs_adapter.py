"""验证 attrs 冻结适配、真实业务反例及具体反馈，不调用外部模型。"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from project_verifier import ProjectVerifier, _native_attrs_adapter
from projects_verification import ProjectsVerification


class AttrsAdapterTests(unittest.TestCase):
    """精确修复误判，同时拒绝真实错误、未知来源和伪造诊断。"""

    def setUp(self):
        """读取控制端、未来内容与旧冻结脚本。:return: None。"""
        self.directory = Path(__file__).resolve().parent
        self.project = self.directory.parent / 'project_library/projects/attrs'
        self.original = (self.directory / 'testdata/attrs-validation-observer-legacy.txt').read_bytes()
        self.current = (self.directory / 'project_attrs_observer.py').read_bytes()
        self.spec = {'script': 'verification/AT-VALIDATION-REPORT-DEV-observe.py', 'args': [],
            'python_paths': ['library/src'], 'expected': {'candidate_import': True, 'business': True}}

    def test_exact_sources_match_and_unknown_source_is_environment_error(self):
        """仅已核实来源可适配，未来内容副本必须与控制端一致。:return: None。"""
        self.assertEqual(self.current, (self.project / self.spec['script']).read_bytes())
        for source in (self.original, self.current):
            actual, facts = _native_attrs_adapter(source, self.spec)
            self.assertEqual(self.current, actual)
            self.assertEqual(hashlib.sha256(source).hexdigest(), facts['original_runner_sha256'])
            self.assertEqual(hashlib.sha256(actual).hexdigest(), facts['effective_runner_sha256'])
            self.assertTrue(facts['preserves_frozen_contract'])
        with self.assertRaisesRegex(ValueError, '版本未知'):
            _native_attrs_adapter(self.original + b'\n', self.spec)
        for change in ({'args': ['different']}, {'python_paths': ['library']}, {'expected': {'business': True}},
                {'expected': {'candidate_import': 1, 'business': True}}, {'script': 'verification/other.py'}):
            self.assertEqual((self.original, None), _native_attrs_adapter(self.original, {**self.spec, **change}))

    def test_real_entry_stages_fixed_source_and_rejects_invalid_protocol(self):
        """真实产品入口不改冻结文件，未知字段不能流入公开事实。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('project/verification', 'project/seed', 'candidate', 'environment'):
                (root / name).mkdir(parents=True)
            observer = root / 'project' / self.spec['script']
            observer.write_bytes(self.original)
            child = Mock(status='running', id='attrs-test')
            child.wait.return_value = {'StatusCode': 0}
            client = Mock()

            def create(*args, **kwargs):
                """核对受信入口和只读挂载。:param args: 创建参数。:param kwargs: 容器配置。:return: 合成容器。"""
                staged = next(Path(path) for path, mount in kwargs['volumes'].items() if mount['bind'] == '/request-data')
                payload = json.loads((staged / 'native.json').read_text())
                self.assertEqual('trusted-native-business.py', payload['script'])
                self.assertEqual(self.current, (staged / payload['script']).read_bytes())
                self.assertEqual(self.original, observer.read_bytes())
                self.assertEqual('none', kwargs['network_mode'])
                return child

            client.containers.create.side_effect = create
            verifier = ProjectVerifier(client, root, root, 'fixture-image')
            profile = {'requirements': ['fixture==1'], 'business': {'memory_mb': 512, 'pids_limit': 64, 'timeout_sec': 60}}
            valid = {'candidate_import': True, 'business': True, 'feedback_codes': []}
            cases = [(valid, 'passed'), ({**valid, 'candidate_import': False}, 'failed'),
                ({**valid, 'business': False, 'feedback_codes': ['attrs_report_order']}, 'failed'),
                ({**valid, 'business': 1}, 'failed'), ({**valid, 'candidate_import': 1}, 'failed'),
                ({**valid, 'business': False}, 'failed'), ({**valid, 'extra': 'PRIVATE_DIAGNOSTIC'}, 'failed'),
                ({**valid, 'feedback_codes': ['PRIVATE_DIAGNOSTIC']}, 'failed'),
                ({**valid, 'business': False, 'feedback_codes': ['attrs_report_order'] * 2}, 'failed')]
            for value, expected in cases:
                with self.subTest(value=value):
                    child.logs.return_value = b'VIBEBENCH_NATIVE_READY_V1\n' + json.dumps(value).encode()
                    report = verifier.verify_native(root / 'candidate', root / 'project', self.spec, root / 'environment', profile)
                    self.assertEqual(expected, report['status'])
                    self.assertNotIn('PRIVATE_DIAGNOSTIC', json.dumps(ProjectsVerification._public_facts(report)))
            observer.write_bytes(self.original + b'\n')
            self.assertEqual('error', verifier.verify_native(root / 'candidate', root / 'project',
                self.spec, root / 'environment', profile)['status'])

    def test_public_reference_and_contract_violations_are_independently_checked(self):
        """真实参考实现及八类错误实现分别执行完整业务矩阵。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(self.project / 'seed', root, dirs_exist_ok=True)
            applied = subprocess.run(['git', 'apply', str(self.project / 'verification/development-AT-VALIDATION-REPORT-DEV.patch')],
                cwd=root, capture_output=True, text=True)
            self.assertEqual(0, applied.returncode, applied.stderr)
            module = root / 'library/src/attr/validation.py'
            original = module.read_text()
            command = ('import sys;sys.path.insert(0,' + repr(str(root / 'library/src'))
                + ');import runpy;runpy.run_path(' + repr(str(self.directory / 'project_attrs_observer.py')) + ',run_name="__main__")')
            variants = [('', original), ('', original.replace("    if type(raise_errors) is not bool:\n        raise TypeError('报告抛错模式必须是布尔值')\n", '')),
                ('attrs_report_order', original.replace('return tuple(issues)', 'return tuple(reversed(issues))')),
                ('attrs_report_identity', original.replace('ValidationIssue(attribute.name, attribute, error)',
                    'ValidationIssue(attribute.name, attribute, ValueError(str(error)))')),
                ('attrs_report_once', original.replace('for attribute in attributes:', 'for attribute in (*attributes, *attributes):')),
                ('attrs_report_values', original.replace('attributes = fields(type(instance))',
                    'attributes = fields(type(instance))\n    object.__setattr__(instance, attributes[0].name, 99)')),
                ('attrs_report_aggregate', original.replace('if issues and raise_errors:', 'if False:')),
                ('attrs_report_disabled', original.replace('if not get_run_validators():', 'if False:')),
                ('attrs_report_composites', original.replace('        try:\n',
                    "        if hasattr(getattr(instance, attribute.name), '__next__'):\n            tuple(getattr(instance, attribute.name))\n        try:\n")),
                ('attrs_report_base_exception', original.replace('except Exception as error:', 'except BaseException as error:'))]
            for code, source in variants:
                with self.subTest(code=code):
                    module.write_text(source)
                    result = subprocess.run([sys.executable, '-I', '-B', '-c', command],
                        env={'PATH': os.defpath, 'PROJECT_CANDIDATE_ROOT': str(root)}, capture_output=True, text=True, timeout=15)
                    self.assertEqual(0, result.returncode, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertTrue(report['candidate_import'])
                    self.assertEqual(not code, report['business'])
                    if code:
                        self.assertIn(code, report['feedback_codes'])

    def test_feedback_is_specific_bounded_and_includes_previous_objective(self):
        """嵌套旧目标仍有具体行为反馈，任意私有诊断不透传。:return: None。"""
        codes = ['attrs_report_order', 'attrs_report_disabled']
        report = {'status': 'failed', 'previous_objectives': [{'report': {'feedback_codes': codes,
            'stdout_tail': 'PRIVATE_CODE'}}]}
        feedback = ProjectsVerification._business_feedback(report)
        self.assertEqual(2, len(feedback))
        self.assertIn('声明顺序', feedback[0])
        self.assertIn('禁用', feedback[1])
        self.assertNotIn('PRIVATE_CODE', json.dumps(feedback))
        self.assertEqual([], ProjectsVerification._business_feedback({'feedback_codes': ['PRIVATE_CODE']}))
        all_codes = ['attrs_report_order', 'attrs_report_identity', 'attrs_report_once', 'attrs_report_values',
            'attrs_report_aggregate', 'attrs_report_disabled', 'attrs_report_composites', 'attrs_report_base_exception']
        self.assertEqual(8, len(ProjectsVerification._business_feedback({'feedback_codes': all_codes * 100})))
