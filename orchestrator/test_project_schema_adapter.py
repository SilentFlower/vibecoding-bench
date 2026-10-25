"""冻结 Schema 误判修复的精确版本、真实入口和失败诊断回归。"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from project_verifier import ProjectVerifier, _native_schema_adapter
from projects_verification import ProjectsVerification


class SchemaAdapterTests(unittest.TestCase):
    """旧资产不可改写，修复不能放过失败候选或未知协议。"""

    def setUp(self):
        """读取已冻结旧观察器及当前修正版。@return None。"""
        root = Path(__file__).resolve().parent
        self.original = (root / 'testdata/schema-observer-legacy.txt').read_bytes()
        self.current = (root.parent / 'project_library/projects/agate/verification/AG-SCHEMA-DEV-observe.py').read_bytes()
        self.spec = {'script': 'verification/AG-SCHEMA-DEV-observe.py', 'args': [],
            'python_paths': ['library'], 'expected': {'candidate_import': True, 'business': True}}

    def test_exact_legacy_version_maps_to_current_and_unknown_source_is_unchanged(self):
        """仅精确字节及协议可适配，未知版本不能被文件名误替换。@return None。"""
        for source in (self.original, self.current):
            actual, facts = _native_schema_adapter(source, self.spec)
            self.assertEqual(self.current, actual)
            self.assertEqual(hashlib.sha256(source).hexdigest(), facts['original_runner_sha256'])
            self.assertEqual(hashlib.sha256(self.current).hexdigest(), facts['effective_runner_sha256'])
            self.assertTrue(facts['preserves_frozen_contract'])
        unknown = self.original + b'\n'
        self.assertEqual((unknown, None), _native_schema_adapter(unknown, self.spec))
        for change in ({'script': 'verification/other.py'}, {'args': ['--different']},
                {'expected': {'business': True}}, {'expected': {'candidate_import': 1, 'business': True}},
                {'python_paths': ['other']}):
            self.assertEqual((self.original, None), _native_schema_adapter(self.original, {**self.spec, **change}))

    def test_real_entry_stages_fixed_bytes_and_keeps_strict_business_results(self):
        """实际验证入口执行可信副本，诊断信息不能改变业务结果或隐藏额外字段。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / 'project'
            for relative in ('project/verification', 'project/seed', 'candidate', 'environment'):
                (root / relative).mkdir(parents=True)
            observer = project / self.spec['script']
            observer.write_bytes(self.original)
            child = Mock(status='running', id='schema-test')
            child.wait.return_value = {'StatusCode': 0}
            client = Mock()

            def create(*args, **kwargs):
                directory = next(Path(path) for path, mount in kwargs['volumes'].items() if mount['bind'] == '/request-data')
                payload = json.loads((directory / 'native.json').read_text())
                self.assertEqual('trusted-native-business.py', payload['script'])
                self.assertEqual(self.current, (directory / payload['script']).read_bytes())
                self.assertEqual('none', kwargs['network_mode'])
                return child

            client.containers.create.side_effect = create
            verifier = ProjectVerifier(client, root, root, 'fixture-image')
            profile = {'requirements': ['fixture==1'], 'business': {'memory_mb': 512, 'pids_limit': 64, 'timeout_sec': 60}}
            cases = [({'candidate_import': True, 'business': True, 'feedback_codes': []}, 'passed'),
                ({'candidate_import': True, 'business': False, 'feedback_codes': ['schema_invalid_rules']}, 'failed'),
                ({'candidate_import': False, 'business': True, 'feedback_codes': []}, 'failed'),
                ({'candidate_import': True, 'business': True, 'feedback_codes': ['schema_invalid_rules']}, 'failed'),
                ({'candidate_import': True, 'business': True, 'feedback_codes': [], 'extra': True}, 'failed'),
                ({'candidate_import': True, 'business': True, 'feedback_codes': ['private arbitrary text']}, 'failed'),
                ({'candidate_import': True, 'business': True}, 'failed')]
            for actual, expected in cases:
                with self.subTest(actual=actual):
                    child.logs.return_value = b'VIBEBENCH_NATIVE_READY_V1\n' + json.dumps(actual).encode()
                    result = verifier.verify_native(root / 'candidate', project, self.spec, root / 'environment', profile)
                    self.assertEqual(expected, result['status'])
                    facts = ProjectsVerification._public_facts(result)
                    self.assertTrue(facts['runtime_adapter']['preserves_frozen_contract'])
                    if actual.get('business') is False:
                        self.assertEqual(['schema_invalid_rules'], facts['feedback_codes'])
            self.assertEqual(self.original, observer.read_bytes())
