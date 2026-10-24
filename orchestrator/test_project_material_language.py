"""验证工程材料语言规范化的语义边界和重复执行行为。"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location('normalize_project_language',
    Path(__file__).resolve().parents[1] / 'scripts/normalize-project-language.py')
LANGUAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LANGUAGE)


class ProjectMaterialLanguageTests(unittest.TestCase):
    """使用最小内容库证明说明翻译不会修改业务代码或固定字面。"""

    def setUp(self):
        """创建独立规范化输入及禁止变更的固定源码。:return: None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / 'projects/example'
        for directory in ('materials', 'disclosure', 'verification', 'seed/library'):
            (self.project / directory).mkdir(parents=True)
        catalog = {'schema':3, 'version':'old', 'projects':['example'], 'project_manifest':'development.json'}
        self.write_json(self.root / 'catalog.json', catalog)
        self.write_json(self.root / 'catalog-development.json', catalog)
        self.task = {'id':'EXAMPLE-DEV', 'development_cycle':'feature', 'goal':'中文页面标题',
            'prompt':'Implement select_columns with lazy rows and preserve exact UTF-8 values.\n\nDeliver Chinese compatibility documentation at library/docs/change.md.',
            'materials':['materials/EXAMPLE-DEV-contract.md','materials/EXAMPLE-DEV-tests.py'],
            'owner_materials':['disclosure/EXAMPLE-DEV-business.md'],
            'allowed_paths':['library/example.py','library/tests/test_example.py','library/docs/change.md'],
            'evaluation':{'rubric':'verification/EXAMPLE-DEV.rubric.json','version':2}}
        self.manifest = {'scenarios':[{'tasks':[self.task]}]}
        self.write_json(self.project / 'development.json', self.manifest)
        self.write_json(self.project / 'verification/EXAMPLE-DEV.rubric.json', {
            'version':2, 'criteria':[{'id':'business','requirement':'Preserve the value "已遮蔽".'},
                {'id':'delivery','requirement':'必须交付授权源码、能在原版失败的公开回归和中文兼容说明；所有冻结原生回归通过。'}],
            'comparison':'依据真实程序行为接受等价实现，不按参考文本或篇幅评分。'})
        (self.project / 'materials/EXAMPLE-DEV-contract.md').write_text('# 中文合同\n')
        (self.project / 'disclosure/EXAMPLE-DEV-business.md').write_text('# 业务确认\n')
        self.source = '"""公开业务回归。"""\n\ndef test_preserves_business_value():\n    """真实业务字面不能翻译。"""\n    assert "已遮蔽" == "已遮蔽"\n'
        (self.project / 'materials/EXAMPLE-DEV-tests.py').write_text(self.source)
        (self.project / 'seed/library/example.py').write_text('VALUE = "固定源码"\n')

    def write_json(self, path: Path, value: object) -> None:
        """保存真实 JSON 测试输入。:param path: 文件。:param value: 数据。:return: None。"""
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

    def test_full_contract_and_public_tests_are_normalized_without_business_changes(self):
        """完整英文合同、授权路径与业务原值同时保留，重复运行无改动。:return: None。"""
        fixed = (self.project / 'seed/library/example.py').read_bytes()
        result = LANGUAGE.normalize(self.root, apply=True)
        self.assertEqual(1, result['generated_objectives'])
        self.assertEqual(2, result['docstrings_updated'])
        current = json.loads((self.project / 'development.json').read_text())['scenarios'][0]['tasks'][0]
        self.assertEqual(self.task['goal'], current['goal'])
        self.assertIn('English compatibility documentation', current['prompt'])
        contract = (self.project / self.task['materials'][0]).read_text()
        self.assertIn(current['prompt'], contract)
        for path in self.task['allowed_paths']:
            self.assertIn(path, contract)
        revised = (self.project / self.task['materials'][1]).read_text()
        self.assertEqual(LANGUAGE.python_evidence(self.source), LANGUAGE.python_evidence(revised))
        self.assertIn('"已遮蔽" == "已遮蔽"', revised)
        self.assertEqual(fixed, (self.project / 'seed/library/example.py').read_bytes())
        rubric = json.loads((self.project / 'verification/EXAMPLE-DEV.rubric.json').read_text())
        self.assertEqual(3, rubric['version'])
        self.assertEqual(3, current['evaluation']['version'])
        self.assertEqual('Preserve the value "已遮蔽".', rubric['criteria'][0]['requirement'])
        self.assertEqual([], LANGUAGE.normalize(self.root)['changed_files'])

    def test_reintroduced_generated_chinese_explanation_is_detected(self):
        """重新生成中文说明后，检查模式必须发现待修内容。:return: None。"""
        LANGUAGE.normalize(self.root, apply=True)
        path = self.project / 'materials/EXAMPLE-DEV-contract.md'
        path.write_text('# 重生的中文合同\n')
        pending = LANGUAGE.normalize(self.root)
        self.assertEqual('changes_pending', pending['status'])
        self.assertEqual(['projects/example/materials/EXAMPLE-DEV-contract.md'],
            [item['path'] for item in pending['changed_files']])
        self.assertEqual('# 重生的中文合同\n', path.read_text())

    def test_exact_legacy_mapping_cannot_translate_executable_business_literals(self):
        """旧材料映射若改变断言业务值，应在任何文件写入前失败。:return: None。"""
        self.task['materials'] = ['materials/legacy-tests.py']
        self.task['owner_materials'] = []
        self.write_json(self.project / 'development.json', self.manifest)
        path = self.project / 'materials/legacy-tests.py'
        path.write_text(self.source)
        mapping = self.root / 'translations.json'
        self.write_json(mapping, {'schema':1, 'files':{
            'project_library/projects/example/materials/legacy-tests.py':{'"已遮蔽"':'"redacted"'},
        }})
        previous_manifest = (self.project / 'development.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '业务字面'):
            LANGUAGE.normalize(self.root, apply=True, translations=mapping)
        self.assertEqual(self.source, path.read_text())
        self.assertEqual(previous_manifest, (self.project / 'development.json').read_bytes())

    def test_installed_historical_release_cannot_be_rewritten(self):
        """已安装摘要目录必须保持冻结，不能借语言规范化覆盖历史合同。:return: None。"""
        release = self.root / 'releases' / ('a' * 64)
        release.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, '历史内容版本不可'):
            LANGUAGE.normalize(release, apply=True)


if __name__ == '__main__':
    unittest.main()
