"""完整工程目标的项目内 DAG、真实通过门禁及旧内容兼容回归。"""
import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_projects_agent as agent_fixtures
from project_library import ProjectLibrary, read_document, write_document
from projects_catalog import ProjectsCatalog
from test_project_development import development_fixture
from test_project_scenario_content import scenario_fixture


class DependencyCatalog:
    """只替换冻结资产加载，保留服务的实际 SQLite、交付和锁。

    :param root: 测试资产根。
    :param digest: 内容版本。
    :param seed: 项目源码身份。
    """

    def __init__(self, root, digest='original-content', seed='fixed-seed'):
        """构造三个完整目标及其传递前置。@param root 根。@param digest 版本。@param seed 源码。@return None。"""
        self.library = SimpleNamespace(root=root, digest=digest)
        self.seed, self.releases = seed, {digest: self}
        template = {'development_cycle': 'feature', 'allowed_paths': ['library/app.py'],
            'evaluation': {'native': 'private.json'}}
        self.definitions = {key: {**copy.deepcopy(template), 'id': key, 'goal': key + ' 完整工程交付',
            'requires': [] if previous is None else [{'task_id': previous, 'artifact': 'code'}]}
            for key, previous in (('feature', None), ('extension', 'feature'), ('delivery', 'extension'))}

    def project(self, key, detail=True):
        """返回仅含真实公开依赖的目录。@param key 项目。@param detail 详细标记。@return 公开目标。"""
        if key not in ('example', 'other'):
            raise ValueError('测试项目不存在')
        return {'project_key': key, 'ready': True, 'objectives': [
            {field: task[field] for field in ('id', 'goal', 'development_cycle', 'requires')}
            for task in self.definitions.values()]}

    def objective(self, key, objective_id):
        """取得项目归属及冻结目标。@param key 项目。@param objective_id 目标。@return 项目与合同。"""
        self.project(key)
        return SimpleNamespace(root=self.library.root, manifest={'seed_digest': self.seed}), self.definitions[objective_id]

    def for_work(self, work):
        """恢复原内容版本，不用新目标定义替换旧证明。@param work 工作。@return 原资产。"""
        if work['library_digest'] not in self.releases:
            raise ValueError('冻结版本不可读')
        return self.releases[work['library_digest']]


class ProjectsDependencyTests(unittest.TestCase):
    """通过真实服务入口证明依赖不能被 Pi、旧身份或失效记录绕过。"""

    def setUp(self):
        """复用独立数据库夹具而不重复收集它的测试。@return None。"""
        self.fixture = agent_fixtures.ProjectsAgentTests('test_pause_rejects_old_generation_before_any_terminal_write')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = self.fixture.service
        self.catalog = DependencyCatalog(self.fixture.root)
        self.service.catalog = self.catalog
        self.identity = 'current-account-identity'
        self.service.identity = lambda account: self.identity + ':' + str(account['id'])
        self.fixture.verification = {'status': 'passed', 'feedback': []}
        self.fixture.activate()

    def start_work(self, objective='feature', account_id=1, project='example'):
        """通过实际工具边界申请目标。@param objective 目标。@param account_id 账号。@param project 项目。@return 工具结果。"""
        generation = self.service._one('SELECT generation FROM projects_agents WHERE account_id=?', (account_id,))['generation']
        return self.fixture.tool('claude_start', {'project_key': project, 'objective_id': objective},
            account_id=account_id, generation=generation)

    def complete(self, objective='feature', account_id=1, project='example'):
        """让实际提交事务产生独立通过记录。@param objective 目标。@param account_id 账号。@param project 项目。@return 工作ID。"""
        started = self.start_work(objective, account_id, project)
        self.assertEqual('running', started['status'])
        generation = self.service._one('SELECT generation FROM projects_agents WHERE account_id=?', (account_id,))['generation']
        result = self.fixture.tool('project_submit', {'summary': '合成工程验收通过'},
            account_id=account_id, generation=generation)
        self.assertEqual('passed', result['status'])
        return started['work_id']

    def test_all_unfinished_ready_and_waiting_are_separate(self):
        """锁定后继仍计入总进度，不能因当前不可选而缩水。@return None。"""
        agent = self.service.view(1)['agents'][0]
        self.assertEqual(['feature'], [item['objective_id'] for item in agent['available_objectives']])
        self.assertEqual(3, len(agent['remaining_objectives']))
        self.assertEqual(['extension', 'feature'], agent['waiting_objectives'][1]['missing_prerequisites'])
        self.assertEqual((0, 3, 3, 1, 2), tuple(agent['progress'][key]
            for key in ('completed', 'remaining', 'total', 'ready', 'waiting')))

    def test_pi_cannot_create_or_launch_a_locked_successor(self):
        """启动工具不能绕过目录的前置门禁，也不能留下孤儿工作。@return None。"""
        result = self.start_work('extension')
        self.assertEqual('rejected', result['status'])
        self.assertIn('前置', result['message'])
        self.assertEqual([], self.fixture.terminal.started)
        self.assertEqual([], self.service._rows('SELECT id FROM projects_work'))

    def test_real_passed_submissions_unlock_the_dag_and_complete_only_at_end(self):
        """每一步只解锁满足前置的后继，三个完整交付后才完成。@return None。"""
        self.complete()
        agent = self.service.view(1)['agents'][0]
        self.assertEqual(['extension'], [item['objective_id'] for item in agent['available_objectives']])
        self.assertEqual((1, 2, 3), tuple(agent['progress'][key] for key in ('completed', 'remaining', 'total')))
        self.complete('extension'); self.complete('delivery')
        agent = self.service.state(1)['agents'][0]
        saved = self.service._one('SELECT * FROM projects_agents WHERE account_id=1')
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (saved['current_work_id'],))
        self.assertEqual([], agent['remaining_objectives'])
        self.assertEqual('completed', self.service._eligibility(saved, work)[0])

    def test_failed_stopped_or_unconfirmed_work_never_unlocks(self):
        """失败、停止和未知执行状态都不是前置通过事实。@return None。"""
        work = self.complete()
        for status in ('failed', 'stopped', 'blocked', 'unknown'):
            with self.subTest(status=status):
                self.service._write('UPDATE projects_work SET status=? WHERE id=?', (status, work))
                self.assertEqual('rejected', self.start_work('extension')['status'])
        self.service._write("UPDATE projects_work SET status='passed' WHERE id=?", (work,))

    def test_passed_without_submission_or_with_unknown_input_does_not_unlock(self):
        """状态字样不能替代独立交付，未知输入同样使证明失效。@return None。"""
        work = self.complete()
        self.service._write("INSERT INTO projects_actions(id,work_id,generation,request_json,status,created_at) "
            "VALUES('uncertain',?,1,'{}','unknown',?)", (work, time.time()))
        self.assertEqual('rejected', self.start_work('extension')['status'])
        self.service._write("DELETE FROM projects_actions WHERE id='uncertain'")
        self.service._write('DELETE FROM projects_submissions WHERE work_id=?', (work,))
        self.assertEqual('rejected', self.start_work('extension')['status'])

    def test_other_account_project_or_original_identity_cannot_unlock(self):
        """不能借另一账号、另一项目或身份变化前的通过证明。@return None。"""
        self.fixture.activate(2)
        self.complete(account_id=2)
        self.assertEqual('rejected', self.start_work('extension')['status'])
        self.service.configure(1, ['example', 'other'])
        self.complete(project='other')
        self.assertEqual('rejected', self.start_work('extension')['status'])
        self.complete()
        self.identity = 'replacement-account-identity'
        self.assertEqual('rejected', self.start_work('extension')['status'])
        agent = self.service.view(1)['agents'][0]
        self.assertIn('extension', [item['objective_id'] for item in agent['waiting_objectives']])

    def test_transitive_missing_proof_is_blocked_instead_of_completed(self):
        """直接前置通过也不能掩盖传递前置的身份失效。@return None。"""
        first = self.complete(); self.complete('extension')
        self.service._write('UPDATE projects_work SET account_identity=NULL WHERE id=?', (first,))
        agent = self.service.view(1)['agents'][0]
        self.assertEqual((1, 0, 1, 3), tuple(agent['progress'][key] for key in ('remaining', 'ready', 'waiting', 'total')))
        saved = self.service._one('SELECT * FROM projects_agents WHERE account_id=1')
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (saved['current_work_id'],))
        self.assertEqual('blocked', self.service._eligibility(saved, work)[0])
        self.assertEqual('rejected', self.start_work('delivery')['status'])

    def test_new_library_can_reuse_same_seed_and_unchanged_old_contract(self):
        """添加其他内容后的全库摘要变化不废弃同合同的真实通过。@return None。"""
        self.complete()
        newer = DependencyCatalog(self.fixture.root, digest='expanded-content')
        newer.releases.update(self.catalog.releases)
        self.service.catalog = newer
        self.assertEqual('running', self.start_work('extension')['status'])

    def test_changed_seed_or_prerequisite_definition_does_not_unlock(self):
        """同名目标不能借旧源码或不同合同的成绩通过。@return None。"""
        self.complete()
        newer = DependencyCatalog(self.fixture.root, digest='changed-content', seed='different-seed')
        newer.releases.update(self.catalog.releases)
        self.service.catalog = newer
        self.assertEqual('rejected', self.start_work('extension')['status'])
        newer.seed = self.catalog.seed
        newer.definitions['feature']['goal'] = '同名但不同业务合同'
        self.assertEqual('rejected', self.start_work('extension')['status'])

    def test_creation_rechecks_proofs_under_both_service_and_database_locks(self):
        """外层读到就绪后，事务内证明失效仍不得发布新目标。@return None。"""
        self.complete()
        checked = []

        def changed(*args, **kwargs):
            """记录真实持锁状态并在提交前撤销证明。@param args 原参数。@param kwargs 原参数。@return 缺少的前置。"""
            checked.append((self.service.lock._is_owned(), self.service.write_lock.locked()))
            return [] if len(checked) == 1 else ['feature']

        with patch.object(self.service, '_missing_prerequisites', side_effect=changed):
            self.assertEqual('rejected', self.start_work('extension')['status'])
        self.assertEqual([(True, False), (True, True)], checked)
        self.assertEqual(1, len(self.service._rows('SELECT id FROM projects_work')))
        self.assertEqual(1, len(self.fixture.terminal.started))

    def test_proof_revoked_during_terminal_setup_closes_the_new_terminal(self):
        """锁外环境准备不能绕过最终前置复核。@return None。"""
        first = self.complete()
        original = self.fixture.terminal.start

        def changed(account, work):
            """在合成 I/O 后撤销原证明。@param account 账号。@param work 工作。@return 定位。"""
            result = original(account, work)
            self.service._write("UPDATE projects_work SET status='stopped' WHERE id=?", (first,))
            return result

        with patch.object(self.fixture.terminal, 'start', side_effect=changed):
            result = self.start_work('extension')
        self.assertEqual('rejected', result['status'])
        self.assertIn('环境准备期间', result['message'])
        child = self.service._one("SELECT * FROM projects_work WHERE objective_id='extension'")
        self.assertIsNone(child['baseline_json'])
        self.assertIn((child['id'], 'stop'), self.fixture.terminal.controls)

    def test_accepted_work_uses_database_ownership_and_excludes_current(self):
        """模型式伪造归属不能改变重放名单，当前目标永不当自己的历史。@return None。"""
        first = self.complete()
        second = self.complete('extension')
        current = self.start_work('delivery')
        rows = self.service.accepted_work({'id': current['work_id'], 'account_id': 2, 'project_key': 'other'})
        self.assertEqual([first, second], [row['id'] for row in rows])
        self.service._write("UPDATE projects_work SET status='passed' WHERE id=?", (current['work_id'],))
        self.assertEqual([first, second], [row['id'] for row in self.service.accepted_work({'id': current['work_id']})])

    def test_accepted_work_filters_unknown_proof_and_rejects_current_identity_change(self):
        """失效旧输入不能作成果证明，当前身份变化也不能跳过历史保护。@return None。"""
        first = self.complete()
        current = self.start_work('extension')
        self.service._write("INSERT INTO projects_actions(id,work_id,generation,request_json,status,created_at) "
            "VALUES('unknown-prior',?,1,'{}','unknown',?)", (first, time.time()))
        self.assertEqual([], self.service.accepted_work({'id': current['work_id']}))
        self.identity = 'different-identity'
        with self.assertRaisesRegex(ValueError, '身份'):
            self.service.accepted_work({'id': current['work_id']})

    def test_accepted_work_keeps_old_release_but_cannot_ignore_corrupt_contract(self):
        """新内容版本继续重放旧成果，损坏原合同必须失败关闭。@return None。"""
        first = self.complete()
        newer = DependencyCatalog(self.fixture.root, digest='new-library')
        newer.releases.update(self.catalog.releases)
        self.service.catalog = newer
        current = self.start_work('extension')
        self.assertEqual([first], [row['id'] for row in self.service.accepted_work({'id': current['work_id']})])
        self.service._write('UPDATE projects_work SET definition_json=? WHERE id=?', ('{}', first))
        with self.assertRaisesRegex(ValueError, '冻结验收合同'):
            self.service.accepted_work({'id': current['work_id']})


class DevelopmentDependencyContentTests(unittest.TestCase):
    """真实 schema 3 内容加载支持项目 DAG，旧 schema 2 不改变约束。"""

    def setUp(self):
        """构造真实内容库与三个独立单任务场景。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = development_fixture(Path(temporary.name) / 'library')
        self.path = self.root / 'projects/example/project.json'
        self.manifest = read_document(self.path)
        original = self.manifest['scenarios'][0]
        scenes = []
        for index, task_id in enumerate(('Q1', 'Q2', 'Q3')):
            scene = copy.deepcopy(original); scene['id'] = 'SCENE-' + task_id
            task = scene['tasks'][0]; task['id'] = task_id
            task['requires'] = [] if index == 0 else [{'task_id': 'Q' + str(index), 'artifact': 'code'}]
            for entry in scene['entries']:
                entry['task_ids'] = [task_id]
            scenes.append(scene)
        self.manifest['scenarios'] = scenes

    def load(self):
        """写入夹具后运行真实全库校验。@return 已验证库。"""
        write_document(self.path, self.manifest)
        return ProjectLibrary(self.root)

    def test_cross_scene_project_dag_and_public_metadata(self):
        """三个完整工程目标可跨场景依赖，公开视图只披露依赖元数据。@return None。"""
        library = self.load()
        catalog = ProjectsCatalog(self.root / 'research', library)
        objectives = catalog.project('example')['objectives']
        self.assertEqual(3, len(objectives))
        self.assertEqual([{'task_id': 'Q1', 'artifact': 'code'}], objectives[1]['requires'])
        self.assertNotIn('PRIVATE_VERIFICATION_SENTINEL', str(objectives))
        self.assertNotIn('evaluation', str(objectives))

    def test_project_cycle_or_missing_dependency_is_rejected(self):
        """跨场景不代表允许环、自依赖或不存在的目标。@return None。"""
        first = self.manifest['scenarios'][0]['tasks'][0]
        for dependency in ('Q3', 'Q1', 'missing'):
            first['requires'] = [{'task_id': dependency, 'artifact': 'code'}]
            with self.subTest(dependency=dependency), self.assertRaises(ValueError):
                self.load()

    def test_scene_still_has_one_complete_delivery_and_public_spec_is_checked(self):
        """不能把问答或多个细碎任务塞进完整场景，公开 native 引用也必须真实。@return None。"""
        task = self.manifest['scenarios'][0]['tasks'][0]
        task['evaluation']['public_native'] = 'verification/native.json'
        self.load()
        task['evaluation']['public_native'] = 'verification/missing.native.json'
        with self.assertRaises(ValueError): self.load()
        task['evaluation'].pop('public_native')
        task['kind'] = 'consult'
        with self.assertRaises(ValueError): self.load()
        task['kind'] = 'modify'
        self.manifest['scenarios'][0]['tasks'].append(copy.deepcopy(task))
        with self.assertRaises(ValueError): self.load()

    def test_legacy_schema_keeps_cross_scene_dependency_rejection(self):
        """原短场景内容不因完整开发 DAG 扩展而改变依赖边界。@return None。"""
        legacy = scenario_fixture(self.root.parent / 'legacy')
        path = legacy / 'projects/example/project.json'
        manifest = read_document(path); original = manifest['scenarios'][0]
        scenes = []
        for task in original['tasks']:
            scene = copy.deepcopy(original); scene['id'] = 'SCENE-' + task['id']; scene['tasks'] = [task]
            scene['entries'] = [{'id': 'only', 'task_ids': [task['id']]}]; scene['default_entry'] = 'only'
            scenes.append(scene)
        manifest['scenarios'] = scenes
        write_document(path, manifest)
        with self.assertRaises(ValueError): ProjectLibrary(legacy)


if __name__ == '__main__':
    unittest.main()
