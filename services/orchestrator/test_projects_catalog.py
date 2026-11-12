"""公开研究隔离及任务跨内容发布恢复的真实文件回归。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_history_metadata_reuses_only_this_request_without_loading_full_library(self):
        """页面跨版本核对原合同但不扫描全库，下一请求仍重新读取元数据。:return: None。"""
        definition = self.library.projects['example'].manifest['scenarios'][0]['tasks'][0]
        work = {'library_digest': self.library.digest, 'library_root': str(self.library.root),
            'project_key': 'example', 'objective_id': definition['id']}
        document = read_document(self.source / 'catalog.json')
        document['version'] = 'next-metadata-release'
        write_document(self.source / 'catalog.json', document)
        current = ProjectsCatalog(self.research, ProjectLibrary(self.source).install(self.root / 'data'))
        snapshots = {}
        with patch('projects_catalog.ProjectLibrary', side_effect=AssertionError('页面不能完整加载历史库')), \
                patch('projects_catalog.read_document', wraps=read_document) as reader:
            seed, contract = current.proof_contract(work, snapshots)
            self.assertEqual(definition, contract)
            self.assertEqual(self.library.projects['example'].manifest['seed_digest'], seed)
            self.assertEqual(2, reader.call_count)
            self.assertEqual((seed, contract), current.proof_contract(work, snapshots))
            self.assertEqual(2, reader.call_count)
            current.proof_contract(work, {})
            self.assertEqual(4, reader.call_count)

    def test_history_metadata_rejects_escape_links_and_reloads_repaired_contract(self):
        """历史目录越界、符号链接和坏合同拒绝，失败仅在本次读取内复用。:return: None。"""
        definition = self.library.projects['example'].manifest['scenarios'][0]['tasks'][0]
        work = {'library_digest': self.library.digest, 'library_root': str(self.library.root),
            'project_key': 'example', 'objective_id': definition['id']}
        document = read_document(self.source / 'catalog.json')
        document['version'] = 'next-boundary-release'
        write_document(self.source / 'catalog.json', document)
        current = ProjectsCatalog(self.research, ProjectLibrary(self.source).install(self.root / 'data'))
        for changed in ({'library_root': str(self.source)}, {'project_key': '../example'}, {'project_key': 'missing'}):
            with self.subTest(changed=changed), self.assertRaises((ValueError, KeyError)):
                current.proof_contract({**work, **changed}, {})
        path = self.library.root / 'projects/example/project.json'
        original = read_document(path)
        path.unlink()
        path.symlink_to(self.source / 'projects/example/project.json')
        with self.assertRaises(OSError):
            current.proof_contract(work, {})
        path.unlink()
        write_document(path, {'schema': 3, 'scenarios': [{'tasks': [None]}]})
        snapshots = {}
        with patch('projects_catalog.read_document', wraps=read_document) as reader:
            with self.assertRaises(ValueError): current.proof_contract(work, snapshots)
            count = reader.call_count
            with self.assertRaises(ValueError): current.proof_contract(work, snapshots)
            self.assertEqual(count, reader.call_count)
        write_document(path, original)
        self.assertEqual(definition, current.proof_contract(work, {})[1])


if __name__ == '__main__':
    unittest.main()
