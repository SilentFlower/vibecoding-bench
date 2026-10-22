"""冻结场景内容、隐藏投影、发布摘要与旧历史读取的回归。"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from project_iteration import ProjectIterationManager
from project_library import ProjectLibrary, materialize_snapshot, snapshot_tree, write_document
from test_project_iterations import ProjectIterationFixture


def scenario_fixture(root: Path) -> Path:
    """构建只用于回归的最小混合任务内容，不发布为真实项目。

    :param root: 临时内容目录。
    :return: 写入后的内容根目录。
    """
    project = root / 'projects' / 'example'
    seed = project / 'seed'
    seed.mkdir(parents=True)
    (seed / 'LICENSE').write_text('测试夹具许可', encoding='utf-8')
    (seed / 'example.py').write_text('VALUE = 1\n', encoding='utf-8')
    write_document(project / 'verification/rubric.json', {'criteria': [
        {'id': 'fact', 'requirement': '解释真实公开行为', 'evidence': ['example.py:1']}]})
    (project / 'disclosure').mkdir()
    (project / 'disclosure/details.txt').write_text('隐藏材料', encoding='utf-8')
    tasks = [{'id': key, 'kind': kind, 'goal': '真实业务目标', 'prompt': '说明这个项目如何使用',
        'requires': [], 'materials': [], 'allowed_paths': [], 'outcomes': ['resolved'],
        'evaluation': {'version': 1, 'rubric': 'verification/rubric.json'}}
        for key, kind in [('Q1', 'understand'), ('Q2', 'consult'), ('Q3', 'plan')]]
    tasks[2]['requires'] = [{'task_id': 'Q1', 'artifact': 'answer'}]
    manifest = {'schema': 2, 'project_key': 'example', 'title': '临时场景夹具', 'category': 'test',
        'description': '仅测试内容契约', 'seed_digest': snapshot_tree(seed)['digest'], 'environment': 'python-test',
        'source': {'repository': 'https://github.com/example/example', 'commit': 'a' * 40,
            'license_files': ['seed/LICENSE'], 'private_note': '不公开'},
        'scenarios': [{'id': 'SC1', 'title': '业务场景', 'goal': '理解与决策', 'default_entry': 'normal',
            'entries': [{'id': 'normal', 'task_ids': ['Q1', 'Q2', 'Q3']}], 'tasks': tasks}]}
    write_document(project / 'project.json', manifest)
    environment = root / 'environments/python-test'
    artifact = environment / 'artifacts/test.whl'
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b'\x00test-only-offline-artifact')
    resources = {'timeout_sec': 300, 'memory_mb': 512, 'pids_limit': 64}
    write_document(environment / 'profile/profile.json', {'schema': 1, 'id': 'python-test',
        'adapter': 'python-native', 'python': '3.12', 'business': resources, 'regression': resources,
        'artifacts': [{'path': 'artifacts/test.whl', 'digest': hashlib.sha256(artifact.read_bytes()).hexdigest()}]})
    write_document(root / 'catalog.json', {'schema': 2, 'version': 'test-only', 'projects': ['example']})
    return root


class ScenarioContentTests(unittest.TestCase):
    """验证数量可变、真实依赖和内容隔离边界。"""

    def setUp(self) -> None:
        """准备独立内容。@return None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = scenario_fixture(Path(self.temporary.name) / 'library')
        self.path = self.root / 'projects/example/project.json'
        self.manifest = json.loads(self.path.read_text())

    def load_changed(self) -> ProjectLibrary:
        """保存当前修改并加载。@return 内容库。"""
        write_document(self.path, self.manifest)
        return ProjectLibrary(self.root)

    def test_variable_tasks_and_nonadjacent_dependency(self) -> None:
        """三个任务与非相邻回答依赖均合法。@return None。"""
        library = ProjectLibrary(self.root)
        summary = library.projects['example'].summary(include_steps=True)
        self.assertEqual(3, summary['task_count'])
        self.assertEqual(1, summary['scenario_count'])
        self.assertNotIn('rubric', json.dumps(summary))
        self.assertNotIn('private_note', summary['source'])
        self.assertNotIn('prompt', summary['scenarios'][0]['tasks'][0])

    def test_cycle_missing_and_answer_as_code_rejected(self) -> None:
        """引用不存在、依赖成环及问答冒充代码均被拒绝。@return None。"""
        tasks = self.manifest['scenarios'][0]['tasks']
        for dependency in ({'task_id': 'missing', 'artifact': 'answer'},
                {'task_id': 'Q3', 'artifact': 'answer'}, {'task_id': 'Q1', 'artifact': 'code'}):
            with self.subTest(dependency=dependency):
                tasks[0]['requires'] = [dependency]
                with self.assertRaises(ValueError):
                    self.load_changed()

    def test_branch_materials_hidden_and_reachability_checked(self) -> None:
        """只有可达分支能激活任务，隐藏文件不能声明为初始材料。@return None。"""
        scenario = self.manifest['scenarios'][0]
        scenario['entries'][0]['task_ids'] = ['Q1']
        scenario['tasks'][0]['branches'] = [{'id': 'details', 'when': '合理请求必要材料',
            'materials': ['disclosure/details.txt'], 'activate_tasks': ['Q2', 'Q3']}]
        self.load_changed()
        scenario['tasks'][0]['materials'] = ['disclosure/details.txt']
        with self.assertRaises(ValueError):
            self.load_changed()
        scenario['tasks'][0]['materials'] = []
        scenario['tasks'][0]['branches'] = []
        with self.assertRaises(ValueError):
            self.load_changed()

    def test_install_and_reopen_preserve_digest(self) -> None:
        """分项目发布和离线制品复制后仍校验同一摘要。@return None。"""
        library = ProjectLibrary(self.root)
        installed = library.install(Path(self.temporary.name) / 'data')
        self.assertEqual(library.digest, installed.digest)
        self.assertEqual(installed.digest, installed.install(Path(self.temporary.name) / 'data').digest)
        self.assertEqual(2, installed.schema)
        (installed.root / 'projects/example/disclosure/details.txt').write_text('已篡改')
        self.assertNotEqual(library.digest, ProjectLibrary(installed.root).digest)

    def test_artifact_tampering_and_symlink_rejected(self) -> None:
        """依赖摘要和逐级目录链接不可绕过校验。@return None。"""
        artifact = self.root / 'environments/python-test/artifacts/test.whl'
        artifact.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            ProjectLibrary(self.root)
        artifact.unlink()
        artifact.symlink_to(self.path)
        with self.assertRaises(ValueError):
            ProjectLibrary(self.root)

    def test_install_deduplicates_dependencies_but_workspace_stays_independent(self) -> None:
        """重复离线依赖可复用 inode，候选改动不能回写冻结源码。@return None。"""
        artifact = self.root / 'environments/python-test/artifacts/test.whl'
        artifact.write_bytes(b'test-only-offline-dependency' * 512)
        duplicate = artifact.with_name('copy.whl')
        duplicate.write_bytes(artifact.read_bytes())
        profile_path = self.root / 'environments/python-test/profile/profile.json'
        profile = json.loads(profile_path.read_text())
        checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
        profile['artifacts'] = [{'path': 'artifacts/' + name, 'digest': checksum}
            for name in ('test.whl', 'copy.whl')]
        write_document(profile_path, profile)
        source = ProjectLibrary(self.root)
        data = Path(self.temporary.name) / 'dedup-data'
        installed = source.install(data)
        directory = installed.root / 'environments/python-test/artifacts'
        self.assertEqual(source.digest, installed.digest)
        self.assertEqual((directory / 'test.whl').stat().st_ino, (directory / 'copy.whl').stat().st_ino)
        seed = installed.projects['example'].root / 'seed'
        snapshot = snapshot_tree(seed, data / 'project-artifacts/objects')
        workspace = data / 'candidate'
        materialize_snapshot(snapshot, data / 'project-artifacts/objects', workspace)
        original = (seed / 'example.py').read_bytes()
        (workspace / 'example.py').write_text('VALUE = 2\n')
        self.assertEqual(original, (seed / 'example.py').read_bytes())
        self.assertEqual(source.digest, ProjectLibrary(installed.root).digest)

    def test_duplicate_identity_and_invalid_rounds_rejected(self) -> None:
        """身份不重复，bool 不冒充整数上限。@return None。"""
        tasks = self.manifest['scenarios'][0]['tasks']
        tasks[0]['max_turns'] = True
        with self.assertRaises(ValueError):
            self.load_changed()
        tasks[0].pop('max_turns')
        tasks[1]['id'] = 'Q1'
        with self.assertRaises(ValueError):
            self.load_changed()


class HistoricalCatalogTests(ProjectIterationFixture):
    """当前库不可用时，保留既有实例与发布的版本语义。"""

    def test_history_survives_unavailable_current_catalog(self) -> None:
        """历史 API 可读，新内容入口明确 503。@return None。"""
        batch = self.manager.create_batch(1, '历史', ['project-001'])
        historical = ProjectIterationManager(self.data, None, main.get_db, main._db_lock,
            self.manager.submit, self.manager.settings, self.manager.identity, self.stop_fixture,
            self.manager.verifier, self.manager.is_executing)
        self.addCleanup(historical.stop)
        with patch.multiple(main, project_iterations=historical, project_iteration_error='当前库不可用', _AUTH_ENABLED=False):
            client = TestClient(main.app)
            try:
                self.assertEqual(200, client.get('/api/project-iteration-batches').status_code)
                self.assertEqual(200, client.get(f"/api/project-instances/{batch['instances'][0]['id']}").status_code)
                self.assertEqual(503, client.get('/api/project-catalog').status_code)
                self.assertEqual(503, client.post('/api/project-iteration-batches', json={'account_id': 1}).status_code)
            finally:
                client.close()
        self.assertEqual(self.library.digest, historical._release(1).digest)

    def test_api_preserves_schema_defaults_explicit_values_and_rejects_null(self) -> None:
        """真实API省略字段选600或1800，显式值不被DTO默认覆盖。@return None。"""
        library=ProjectLibrary(scenario_fixture(self.data/'scenario-api-library'))
        manager=ProjectIterationManager(self.data,library,main.get_db,main._db_lock,
            self.manager.submit,self.manager.settings,self.manager.identity,self.stop_fixture,
            self.manager.verifier,self.manager.is_executing)
        self.addCleanup(manager.stop)
        with patch.multiple(main,project_iterations=manager,_AUTH_ENABLED=False,V3_ENABLED=False):
            client=TestClient(main.app)
            self.addCleanup(client.close)
            result=client.post('/api/project-iteration-batches',json={'account_id':1,'concurrency':None})
            self.assertEqual(200,result.status_code)
            self.assertEqual(600,result.json()['policy']['timeout_sec'])
            explicit=client.post('/api/project-iteration-batches',json={'account_id':1,'timeout_sec':61,'task_budget_sec':181})
            self.assertEqual((61,181),(explicit.json()['policy']['timeout_sec'],explicit.json()['policy']['task_budget_sec']))
            for value in (None,True,'600',600.5):
                with self.subTest(value=value):
                    self.assertEqual(422,client.post('/api/project-iteration-batches',json={'account_id':1,'review_timeout_sec':value}).status_code)
            with patch.object(main,'project_iterations',self.manager):
                old=client.post('/api/project-iteration-batches',json={'account_id':1,'project_keys':['project-001']})
                self.assertEqual(1800,old.json()['policy']['timeout_sec'])
                self.assertEqual(400,client.post('/api/project-iteration-batches',json={'account_id':1,'review_budget_sec':720}).status_code)
