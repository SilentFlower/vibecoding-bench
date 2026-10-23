"""公开研究隔离及任务跨内容发布恢复的真实文件回归。"""
import tempfile
import unittest
from pathlib import Path

from project_library import ProjectLibrary, read_document, write_document
from projects_catalog import ProjectsCatalog
from test_project_development import development_fixture


class ProjectsCatalogTests(unittest.TestCase):
    """检查研究不泄露验证材料，原工作始终使用原冻结合同。"""

    def setUp(self):
        """准备真实可校验的工程资产和研究文本。:return: None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = development_fixture(self.root / 'source')
        self.library = ProjectLibrary(self.source).install(self.root / 'data')
        self.research = self.root / 'research'; self.research.mkdir()
        (self.research / 'example.md').write_text('已核对的项目研究')
        (self.research / 'only-research-roadmap-20.md').write_text('尚未建立工程验收')
        self.catalog = ProjectsCatalog(self.research, self.library)

    def test_public_research_does_not_expose_private_contracts(self):
        """研究和公开材料可读，私有验证、参考答案和路径不进入模型输入。:return: None。"""
        public = self.catalog.project('example')
        self.assertTrue(public['ready'])
        self.assertNotIn('PRIVATE_VERIFICATION_SENTINEL', str(public))
        self.assertNotIn('private-secret', str(public))
        self.assertFalse(self.catalog.project('only-research')['ready'])
        with self.assertRaises(ValueError):
            self.catalog.objective('only-research', 'anything')
        with self.assertRaises(ValueError):
            self.catalog.project('../example')

    def test_original_work_keeps_original_contract_after_new_release(self):
        """内容更新后恢复工作时仍读取旧目录、目标和程序合同。:return: None。"""
        original = self.catalog.project('example')['objectives'][0]
        document = read_document(self.source / 'catalog.json')
        document['version'] = 'new-release'
        write_document(self.source / 'catalog.json', document)
        project = read_document(self.source / 'projects/example/project.json')
        project['scenarios'][0]['tasks'][0]['goal'] = '新版本工程目标'
        write_document(self.source / 'projects/example/project.json', project)
        newer = ProjectLibrary(self.source).install(self.root / 'data')
        current = ProjectsCatalog(self.research, newer)
        restored = current.for_work({'library_digest': self.library.digest, 'library_root': str(self.library.root)})
        self.assertEqual(original, restored.project('example')['objectives'][0])
        self.assertNotEqual(original['goal'], current.project('example')['objectives'][0]['goal'])
        with self.assertRaises(ValueError):
            current.for_work({'library_digest': 'outside', 'library_root': str(self.source)})


if __name__ == '__main__':
    unittest.main()
