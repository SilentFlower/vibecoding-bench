"""验证公开合同容错、真实错误反例、冻结来源和具体反馈。"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from project_verifier import ProjectVerifier, _native_contract_observer_adapter
from projects_verification import ProjectsVerification


class ContractObserverTests(unittest.TestCase):
    """合理实现必须通过，真实功能错误和伪造协议必须拒绝。"""

    @classmethod
    def setUpClass(cls):
        """从真实固定种子与参考补丁准备两个独立实现。:return: None。"""
        cls.directory = Path(__file__).resolve().parent
        cls.repository = cls.directory.parent
        cls.temporary = tempfile.TemporaryDirectory(prefix='contract-observers-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.references = Path(cls.temporary.name)
        cls.cases = {
            'chardet': ('CHARDET-O04-DEV', 'project_chardet_batch_observer.py',
                'chardet-batch-observer-legacy.txt', ['library', 'app'], 'batch_results'),
            'babel': ('BA-PREFERENCES-DEV', 'project_locale_preferences_observer.py',
                'babel-preferences-observer-legacy.txt', ['library'], 'locale_preferences_quality'),
            'bibtexparser': ('BIBTEXPARSER-O03-DEV', 'project_pages_observer.py',
                'bibtexparser-pages-observer-legacy.txt', ['library', 'app'], 'pages_ranges'),
        }
        for project, (objective, _, _, _, _) in cls.cases.items():
            source = cls.repository / 'project_library/projects' / project
            target = cls.references / project
            shutil.copytree(source / 'seed', target)
            applied = subprocess.run(['git', 'apply', str(source / 'verification' / ('development-' + objective + '.patch'))],
                cwd=target, capture_output=True, text=True)
            if applied.returncode:
                raise AssertionError(applied.stderr)

    def specification(self, project):
        """构造现有产品执行协议。:param project: 项目名。:return: 冻结业务协议。"""
        objective, _, _, paths, _ = self.cases[project]
        return {'script': 'verification/' + objective + '-observe.py', 'args': [],
            'python_paths': paths, 'expected': {'candidate_import': True, 'business': True}}

    def observe(self, project, prelude='', public=False):
        """在独立进程执行真实参考或错误变体。:param project: 项目名。:param prelude: 错误注入代码。
        :param public: 是否执行未来公开用例。:return: 观察器输出或公开执行数量。
        """
        objective, filename, _, _, _ = self.cases[project]
        root = self.references / project
        paths = [str(root / 'library')]
        if project == 'bibtexparser':
            paths.append(str(self.repository / 'project_library/environments/bibtexparser-py312/artifacts'
                / 'pylatexenc-2.11-py2.py3-none-any.whl'))
        command = 'import json,runpy,sys\nsys.path[:0]=' + repr(paths) + '\n' + prelude + '\n'
        if public:
            path = self.repository / 'project_library/projects' / project / 'materials' / (objective + '-tests.py')
            command += ('namespace=runpy.run_path(' + repr(str(path)) + ')\n'
                'tests=[value for name,value in namespace.items() if name.startswith("test_")]\n'
                'for test in tests:test()\nprint(json.dumps({"executed":len(tests)}))\n')
        else:
            command += 'runpy.run_path(' + repr(str(self.directory / filename)) + ',run_name="__main__")\n'
        process = subprocess.run([sys.executable, '-I', '-B', '-c', command], capture_output=True, text=True,
            timeout=20, env={**os.environ, 'PROJECT_CANDIDATE_ROOT': str(root), 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(0, process.returncode, process.stderr)
        return json.loads(process.stdout)

    def test_known_sources_and_future_copies_are_exact(self):
        """既有冻结版本和未来副本均使用精确受信代码，未知字节拒绝。:return: None。"""
        for project, (objective, filename, legacy, _, _) in self.cases.items():
            with self.subTest(project=project):
                current = (self.directory / filename).read_bytes()
                future = self.repository / 'project_library/projects' / project / 'verification' / (objective + '-observe.py')
                self.assertEqual(current, future.read_bytes())
                original = (self.directory / 'testdata' / legacy).read_bytes()
                for source in (original, current):
                    actual, adapter = _native_contract_observer_adapter(source, self.specification(project))
                    self.assertEqual(current, actual)
                    self.assertEqual(hashlib.sha256(source).hexdigest(), adapter['original_runner_sha256'])
                    self.assertEqual(hashlib.sha256(current).hexdigest(), adapter['effective_runner_sha256'])
                with self.assertRaisesRegex(ValueError, '版本未知'):
                    _native_contract_observer_adapter(original + b'\n', self.specification(project))
                with patch.object(Path, 'read_bytes', return_value=b'unknown trusted code'):
                    with self.assertRaisesRegex(ValueError, '受信观察器'):
                        _native_contract_observer_adapter(original, self.specification(project))
                for changed in ({'script': 'verification/other.py'}, {'args': ['different']},
                        {'python_paths': ['unknown']}, {'expected': {'candidate_import': 1, 'business': True}},
                        {'expected': {'candidate_import': True, 'business': 1}}, {'expected': {'business': True}}):
                    self.assertEqual((original, None),
                        _native_contract_observer_adapter(original, {**self.specification(project), **changed}))

    def test_real_entry_keeps_frozen_bytes_and_strict_diagnostics(self):
        """产品入口只读旧资产，额外字段、假布尔和伪造类别均不能通过。:return: None。"""
        for project, (_, filename, legacy, _, failure_code) in self.cases.items():
            with self.subTest(project=project), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for name in ('project/verification', 'project/seed', 'candidate', 'environment'):
                    (root / name).mkdir(parents=True)
                spec = self.specification(project)
                original = (self.directory / 'testdata' / legacy).read_bytes()
                observer = root / 'project' / spec['script']
                observer.write_bytes(original)
                child = Mock(status='running', id='contract-observer')
                child.wait.return_value = {'StatusCode': 0}
                client = Mock()

                def create(*args, **kwargs):
                    """检查真实挂载和临时执行入口。:param args: 创建参数。:param kwargs: 容器参数。:return: 测试容器。"""
                    staged = next(Path(path) for path, mount in kwargs['volumes'].items() if mount['bind'] == '/request-data')
                    payload = json.loads((staged / 'native.json').read_text())
                    self.assertEqual('trusted-native-business.py', payload['script'])
                    self.assertEqual((self.directory / filename).read_bytes(), (staged / payload['script']).read_bytes())
                    self.assertEqual(original, observer.read_bytes())
                    self.assertEqual('none', kwargs['network_mode'])
                    self.assertEqual('ro', kwargs['volumes'][str(root / 'project/verification')]['mode'])
                    return child

                client.containers.create.side_effect = create
                verifier = ProjectVerifier(client, root, root, 'fixture-image')
                profile = {'requirements': ['fixture==1'], 'business': {'memory_mb': 256, 'pids_limit': 64, 'timeout_sec': 30}}
                valid = {'candidate_import': True, 'business': True, 'feedback_codes': []}
                cases = [(valid, 'passed'), ({**valid, 'candidate_import': False}, 'failed'),
                    ({**valid, 'business': False, 'feedback_codes': [failure_code]}, 'failed'),
                    ({**valid, 'candidate_import': 1}, 'failed'), ({**valid, 'business': 1}, 'failed'),
                    ({**valid, 'business': False}, 'failed'), ({**valid, 'feedback_codes': [failure_code]}, 'failed'),
                    ({**valid, 'extra': 'PRIVATE_DIAGNOSTIC'}, 'failed'),
                    ({**valid, 'feedback_codes': ['PRIVATE_DIAGNOSTIC']}, 'failed'),
                    ({**valid, 'feedback_codes': [failure_code] * 2, 'business': False}, 'failed')]
                for actual, expected in cases:
                    with self.subTest(actual=actual):
                        child.logs.return_value = b'VIBEBENCH_NATIVE_READY_V1\n' + json.dumps(actual).encode()
                        result = verifier.verify_native(root / 'candidate', root / 'project', spec, root / 'environment', profile)
                        self.assertEqual(expected, result['status'])
                        self.assertNotIn('PRIVATE_DIAGNOSTIC', json.dumps(ProjectsVerification._public_facts(result)))
                observer.write_bytes(original + b'\n')
                self.assertEqual('error', verifier.verify_native(root / 'candidate', root / 'project', spec,
                    root / 'environment', profile)['status'])

    def test_reference_and_reasonable_variants_pass_public_and_business_checks(self):
        """旧参考与合理兼容变体均通过独立矩阵及未来公开用例。:return: None。"""
        alternate_locale = '''import babel.core as module
original = module.negotiate_locale_preferences
def alternate(header, available, **kwargs):
    """显式正偏好允许优先。:param header: 头部。:param available: 可用区域。:param kwargs: 参数。:return: 选择结果。"""
    if '*' not in header:
        header = ','.join(part for part in header.split(',') if part.strip().split(';')[-1].strip() != 'q=0')
    return original(header, available, **kwargs)
module.negotiate_locale_preferences = alternate
'''
        spaced_pages = '''import bibtexparser.pages as module
class Spaced(module.NormalizePages):
    """保持原首尾空白的合法实现。"""
    def transform_entry(self, entry, library):
        """保留空白而不改变规范化语义。:param entry: 文献。:param library: 文献库。:return: 变换文献。"""
        original = entry['pages']
        result = super().transform_entry(entry, library)
        leading = original[:len(original) - len(original.lstrip())]
        trailing = original[len(original.rstrip()):]
        result.get('pages').value = leading + result['pages'].strip() + trailing
        return result
module.NormalizePages = Spaced
'''
        for project, alternate, expected_count in (('babel', alternate_locale, 4), ('bibtexparser', spaced_pages, 3)):
            for prelude in ('', alternate):
                with self.subTest(project=project, alternate=bool(prelude)):
                    report = self.observe(project, prelude)
                    self.assertTrue(report['candidate_import'])
                    self.assertTrue(report['business'])
                    self.assertEqual([], report['feedback_codes'])
                    self.assertEqual(expected_count, self.observe(project, prelude, public=True)['executed'])

    def test_wrong_locale_behaviors_remain_failures_with_specific_feedback(self):
        """质量、顺序、排除、输入边界及一次性消费错误仍分别拒绝。:return: None。"""
        variants = {
            'locale_preferences_quality': "return list(available)[0] if available else None",
            'locale_preferences_order': "return original(','.join(reversed(header.split(','))), available, **kwargs)",
            'locale_preferences_matching': "result=original(header, available, **kwargs)\n    return result.lower() if result else result",
            'locale_preferences_exclusions': "header=','.join(part for part in header.split(',') if part.strip().split(';')[-1].strip()!='q=0')\n    return original(header, available, **kwargs)",
            'locale_preferences_headers': "return None if len(header)>8192 else original(header, available, **kwargs)",
            'locale_preferences_once': "list(available)\n    return original(header, available, **kwargs)",
        }
        for code, body in variants.items():
            prelude = ('import babel.core as module\noriginal=module.negotiate_locale_preferences\n'
                'def broken(header, available, **kwargs):\n'
                '    """模拟真实错误。:param header: 头部。:param available: 可用区域。:param kwargs: 参数。:return: 错误结果。"""\n'
                '    ' + body + '\nmodule.negotiate_locale_preferences=broken\n')
            with self.subTest(code=code):
                report = self.observe('babel', prelude)
                self.assertFalse(report['business'])
                self.assertIn(code, report['feedback_codes'])
        for prelude, code in (('import babel.core as module\nmodule.negotiate_locale_preferences=None', 'locale_preferences_api'),
                ('import babel.core as module\nmodule.negotiate_locale=lambda *args,**kwargs:None', 'locale_preferences_legacy')):
            self.assertIn(code, self.observe('babel', prelude)['feedback_codes'])

    def test_chardet_reasonable_indexes_and_error_representations_pass(self):
        """两种连续编号及三种明确错误表示均保持相同业务语义。:return: None。"""
        for offset in (0, 1):
            for error_form in ('string', 'mapping', 'exception'):
                prelude = ('import chardet.batch as module\noriginal=module.detect_many\n'
                    'def alternate(records, **kwargs):\n'
                    '    """只转换公开合同未限定的表示。:param records: 记录。:param kwargs: 策略。:return: 结果迭代器。"""\n'
                    '    for row in original(records, **kwargs):\n'
                    '        row=dict(row)\n        row["index"] += ' + str(offset - 1) + '\n'
                    '        if row["error"] is not None:\n'
                    '            if ' + repr(error_form) + ' == "mapping":row["error"]={"reason":row["error"]}\n'
                    '            if ' + repr(error_form) + ' == "exception":row["error"]=ValueError("局部记录失败")\n'
                    '        yield row\nmodule.detect_many=alternate\n')
                with self.subTest(offset=offset, error_form=error_form):
                    report = self.observe('chardet', prelude)
                    self.assertTrue(report['business'], report)
                    self.assertEqual([], report['feedback_codes'])
                    self.assertEqual(3, self.observe('chardet', prelude, public=True)['executed'])

    def test_chardet_real_behavior_errors_still_fail(self):
        """结果、顺序、惰性、局部隔离、策略、上游与真实检测错误仍拒绝。:return: None。"""
        variants = {
            'batch_results': 'row["result"]={"encoding":"fake"} if row["error"] is None else None',
            'batch_order': 'row["index"]=0',
            'batch_errors': 'row["result"]={"encoding":"fake"} if row["error"] is not None else row["result"]',
        }
        for code, body in variants.items():
            prelude = ('import chardet.batch as module\noriginal=module.detect_many\n'
                'def broken(records, **kwargs):\n'
                '    """注入可观察的业务错误。:param records: 记录。:param kwargs: 策略。:return: 错误记录。"""\n'
                '    for row in original(records, **kwargs):\n        row=dict(row)\n        ' + body
                + '\n        yield row\nmodule.detect_many=broken\n')
            with self.subTest(code=code):
                self.assertIn(code, self.observe('chardet', prelude)['feedback_codes'])
        prelude = ('import chardet.batch as module\noriginal=module.detect_many\n'
            'module.detect_many=lambda records,**kwargs:iter(list(original(records,**kwargs)))')
        self.assertIn('batch_laziness', self.observe('chardet', prelude)['feedback_codes'])
        prelude = ('import chardet.batch as module\noriginal=module.detect_many\n'
            'module.detect_many=lambda records,**kwargs:original(records)')
        self.assertIn('batch_policies', self.observe('chardet', prelude)['feedback_codes'])
        prelude = '''import chardet.batch as module
original=module.detect_many
def swallowed(records, **kwargs):
    """错误地吞掉上游异常。:param records: 输入记录。:param kwargs: 策略。:return: 部分结果。"""
    try:
        yield from original(records, **kwargs)
    except LookupError:
        return
module.detect_many=swallowed
'''
        self.assertIn('batch_upstream', self.observe('chardet', prelude)['feedback_codes'])
        prelude = '''import chardet.batch as module
original_detect=module.detect
cache={}
def cached(data, should_rename_legacy=False):
    """错误地复用旧检测结果。:param data: 字节。:param should_rename_legacy: 选项。:return: 缓存结果。"""
    key=(bytes(data),should_rename_legacy)
    if key not in cache:cache[key]=original_detect(data,should_rename_legacy=should_rename_legacy)
    return dict(cache[key])
module.detect=cached
'''
        self.assertIn('batch_detection', self.observe('chardet', prelude)['feedback_codes'])
        self.assertIn('batch_api', self.observe('chardet',
            'import chardet.batch as module\nmodule.detect_many=None')['feedback_codes'])

    def test_wrong_pages_behaviors_remain_failures_with_specific_feedback(self):
        """归一、未知格式、原值、非原地修改和其它字段错误均拒绝。:return: None。"""
        variants = {
            'pages_ranges': "result.get('pages').value=result['pages'].replace('--','-')",
            'pages_unknown': "result.get('pages').value=result['pages'].replace('-','--')",
            'pages_original': "result.parser_metadata.pop('original_pages', None)",
            'pages_fields': "result.get('year').value='1999'",
            'pages_idempotent': "result.parser_metadata['original_pages']=result['pages']",
        }
        for code, body in variants.items():
            prelude = ('import bibtexparser.pages as module\nclass Broken(module.NormalizePages):\n'
                '    """模拟错误页码中间件。"""\n'
                '    def transform_entry(self, entry, library):\n'
                '        """注入实际错误。:param entry: 文献。:param library: 文献库。:return: 错误结果。"""\n'
                '        result=super().transform_entry(entry, library)\n        ' + body
                + '\n        return result\nmodule.NormalizePages=Broken\n')
            with self.subTest(code=code):
                report = self.observe('bibtexparser', prelude)
                self.assertFalse(report['business'])
                self.assertIn(code, report['feedback_codes'])
        inplace = '''import bibtexparser.pages as module
class Inplace(module.NormalizePages):
    """错误地直接修改输入库。"""
    def transform(self, library):
        """执行原地错误。:param library: 文献库。:return: 原文献库。"""
        for entry in library.entries:
            self.transform_entry(entry, library)
        return library
module.NormalizePages=Inplace
'''
        self.assertIn('pages_immutable', self.observe('bibtexparser', inplace)['feedback_codes'])
        default_stack = ('import bibtexparser\nfrom bibtexparser.pages import NormalizePages\n'
            'original=bibtexparser.parse_string\nbibtexparser.parse_string=lambda *args,**kwargs:'
            'NormalizePages().transform(original(*args,**kwargs))')
        self.assertIn('pages_default_stack', self.observe('bibtexparser', default_stack)['feedback_codes'])
        self.assertIn('pages_api', self.observe('bibtexparser',
            'import bibtexparser.pages as module\nmodule.NormalizePages=object')['feedback_codes'])

    def test_feedback_stays_bounded_specific_and_private(self):
        """新诊断可进入历史反馈，重复或私有诊断不能污染公开说明。:return: None。"""
        report = {'previous_objectives': [{'report': {'feedback_codes': ['locale_preferences_exclusions', 'pages_original'],
            'stdout': 'PRIVATE_OUTPUT'}}], 'feedback_codes': ['PRIVATE_OUTPUT']}
        feedback = ProjectsVerification._business_feedback(report)
        self.assertEqual(2, len(feedback))
        self.assertIn('排除', feedback[0])
        self.assertIn('原值', feedback[1])
        self.assertNotIn('PRIVATE_OUTPUT', json.dumps(feedback))
        self.assertEqual(feedback, ProjectsVerification._business_feedback(
            {'feedback_codes': ['locale_preferences_exclusions', 'pages_original'] * 100}))
        batch_feedback = ProjectsVerification._business_feedback({'business': {'feedback_codes': ['batch_errors']},
            'previous_objectives': [{'report': {'feedback_codes': ['batch_order', 'PRIVATE_OUTPUT']}}]})
        self.assertEqual(2, len(batch_feedback))
        self.assertIn('局部失败', batch_feedback[0])
        self.assertIn('编号可以从零或一开始', batch_feedback[1])
        self.assertNotIn('PRIVATE_OUTPUT', json.dumps(batch_feedback))


if __name__ == '__main__':
    unittest.main()
