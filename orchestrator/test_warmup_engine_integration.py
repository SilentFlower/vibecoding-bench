"""用真实 SQLite 与同类双工程服务验证养号空间，禁止真实模型和容器调用。"""
import json
import os
import threading
import time
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import main
import test_quota
from account_runtime import AccountRuntime
from pi_owners import AccountPiOwners
from projects import ProjectsService
from projects_api import projects_router
from projects_warmup import migrate_warmup_configuration, warmup_migration_blocker
from test_projects_agent import CatalogFixture, PiFixture, TerminalFixture
from warmup_pi_api import warmup_pi_router


# 保留已部署旧四表的真实契约，仅用于验证配置保留和旧执行硬门禁。
LEGACY_WARMUP_SCHEMA = '''
CREATE TABLE IF NOT EXISTS warmup_pi_agents (
 account_id INTEGER PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 0,
 managed INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'off',
 instructions TEXT NOT NULL DEFAULT '', budget_sec INTEGER NOT NULL DEFAULT 1800,
 current_round_id TEXT, session_file TEXT, message TEXT, last_reason TEXT,
 recovery_count INTEGER NOT NULL DEFAULT 0, recovery_phase TEXT, retry_at REAL,
 updated_at REAL NOT NULL, FOREIGN KEY(account_id) REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS warmup_pi_rounds (
 id TEXT PRIMARY KEY, account_id INTEGER NOT NULL, generation INTEGER NOT NULL,
 topic_id INTEGER NOT NULL, topic_no INTEGER NOT NULL, title TEXT NOT NULL,
 topic_json TEXT NOT NULL, settings_json TEXT NOT NULL, account_identity TEXT NOT NULL,
 status TEXT NOT NULL, session_id TEXT NOT NULL, runtime_json TEXT,
 observation_json TEXT, observation_id TEXT, evidence_json TEXT, claude_usage_json TEXT,
 work_sec REAL NOT NULL DEFAULT 0, created_at REAL NOT NULL, started_at REAL,
 segment_started_at REAL, ended_at REAL, message TEXT,
 FOREIGN KEY(account_id) REFERENCES warmup_pi_agents(account_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS warmup_pi_one_active_round ON warmup_pi_rounds(account_id)
 WHERE status NOT IN ('completed','stopped');
CREATE TABLE IF NOT EXISTS warmup_pi_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL, round_id TEXT,
 kind TEXT NOT NULL, payload_json TEXT NOT NULL, event_key TEXT UNIQUE, created_at REAL NOT NULL,
 FOREIGN KEY(account_id) REFERENCES warmup_pi_agents(account_id)
);
CREATE INDEX IF NOT EXISTS warmup_pi_event_page ON warmup_pi_events(account_id,id);
CREATE TABLE IF NOT EXISTS warmup_pi_actions (
 id TEXT PRIMARY KEY, round_id TEXT NOT NULL, generation INTEGER NOT NULL,
 tool_call_id TEXT NOT NULL, request_json TEXT NOT NULL, status TEXT NOT NULL,
 error TEXT, created_at REAL NOT NULL, ended_at REAL,
 FOREIGN KEY(round_id) REFERENCES warmup_pi_rounds(id)
);
'''


class WarmupEngineIntegrationTests(unittest.TestCase):
    """核对独立工程池、配置迁移、旧入口和账号互斥。"""

    def setUp(self):
        """建立完整账号表与两个仅操作临时文件的工程服务。:return: None。"""
        test_quota.QuotaGuardTests.setUp(self)
        self.owners = AccountPiOwners()
        self.catalog = CatalogFixture(self.base)
        self.pi, self.warmup_pi = PiFixture(), PiFixture()
        self.terminal = TerminalFixture(self.base / 'original-work')
        self.warmup_terminal = TerminalFixture(self.base / 'warmup-work')
        environment = patch.dict(os.environ, {'V3_DEPLOYMENT_ID': 'warmup-engine-tests',
            'V3_ACCOUNT_IMAGE': 'synthetic-image', 'V3_NETWORK': 'synthetic-network'})
        environment.start();self.addCleanup(environment.stop)
        runtime = AccountRuntime(Mock(), self.base, self.base, main.get_db, Mock(), Mock())
        self.addCleanup(runtime.heartbeat_pool.shutdown, wait=True)
        for name, value in (('account_runtime', runtime), ('pi_owners', self.owners), ('V3_ENABLED', True)):
            patcher = patch.object(main, name, value);patcher.start();self.addCleanup(patcher.stop)
        self.projects = ProjectsService(self.base, main.get_db, main._db_lock, self.catalog, self.terminal,
            main._projects_account, main._projects_admission, lambda: {'model': 'synthetic'}, Mock(),
            self.pi, main._quota_identity, owners=self.owners)
        self.warmup = ProjectsService(self.base, main.get_db, main._db_lock, self.catalog, self.warmup_terminal,
            main._projects_account, main._warmup_projects_admission, lambda: {'model': 'synthetic'}, Mock(),
            self.warmup_pi, main._quota_identity, owners=self.owners, namespace='warmup', auto_cycle=True)
        for name, value in (('projects_service', self.projects), ('warmup_pi_service', self.warmup),
                ('warmup_scheduler', main.WarmupScheduler(self.scheduler))):
            patcher = patch.object(main, name, value);patcher.start();self.addCleanup(patcher.stop)
        self.addCleanup(self.projects.close);self.addCleanup(self.warmup.close)
        self.projects.configure(1, ['example'], '原项目指南', 1800)
        self.projects.configure_schedule(1, True, 30)
        self.connection = main.get_db()
        self.connection.executescript(LEGACY_WARMUP_SCHEMA)
        self.connection.execute('INSERT INTO warmup_pi_agents(account_id,instructions,budget_sec,updated_at) VALUES(1,?,?,?)',
            ('  养号追加原文\n请用英文与Claude交流。  ', 1800, time.time()))
        self.connection.commit();self.addCleanup(self.connection.close)

    def original(self):
        """取得原项目配置全部列，迁移不能改动它。:return: 原配置。"""
        return dict(self.connection.execute('SELECT * FROM projects_agents WHERE account_id=1').fetchone())

    def join(self, service):
        """等假控制者退出。:param service: 对应工程空间。:return: None。"""
        controller = service.controllers.get(1)
        if controller:
            controller[0].join(3)
            self.assertFalse(controller[0].is_alive())

    def test_migration_preserves_raw_guide_authorization_and_every_original_schedule_column(self):
        """原文指南只进入新养号空间，原项目计划和所有字段逐列不变。:return: None。"""
        before = self.original()
        account = main._projects_account(1)
        result = migrate_warmup_configuration(main.get_db, main._db_lock)
        self.assertEqual((1, 1), (result['created_agents'], result['imported_guides']))
        self.assertEqual(before, self.original())
        self.assertEqual(account, main._projects_account(1))
        value = self.warmup.state(1)['agents'][0]
        self.assertEqual('  养号追加原文\n请用英文与Claude交流。  ', value['instructions'])
        self.assertEqual(['example'], value['project_keys'])
        self.assertEqual((False, 180, 300, None), tuple(value['schedule'][key] for key in
            ('enabled', 'interval_minutes', 'interval_max_minutes', 'next_run_at')))
        self.assertEqual(0, migrate_warmup_configuration(main.get_db, main._db_lock)['imported_guides'])
        self.assertEqual(1, self.connection.execute('SELECT count(*) FROM warmup_projects_events').fetchone()[0])
        self.assertEqual(0, self.connection.execute('SELECT count(*) FROM warmup_projects_work').fetchone()[0])
        self.assertFalse(self.pi.entered.is_set());self.assertFalse(self.warmup_pi.entered.is_set())

    def test_existing_warmup_config_keeps_pool_budget_plan_and_appends_raw_guide_once(self):
        """已有新空间配置仅追加旧原文，不能覆盖它的独立选择或提前下一次运行。:return: None。"""
        self.warmup.configure(1, ['other'], '新空间现有指南', 2400)
        self.warmup.configure_schedule(1, True, 90, 120)
        before = dict(self.connection.execute('SELECT * FROM warmup_projects_agents WHERE account_id=1').fetchone())
        migrate_warmup_configuration(main.get_db, main._db_lock)
        after = dict(self.connection.execute('SELECT * FROM warmup_projects_agents WHERE account_id=1').fetchone())
        for key in before:
            if key not in ('instructions', 'updated_at'):
                self.assertEqual(before[key], after[key], key)
        self.assertEqual('新空间现有指南\n\n账号养号追加指南（原文）：\n  养号追加原文\n请用英文与Claude交流。  ', after['instructions'])
        migrate_warmup_configuration(main.get_db, main._db_lock)
        self.assertEqual(after['instructions'], self.connection.execute('SELECT instructions FROM warmup_projects_agents').fetchone()[0])

    def test_missing_original_authorization_creates_off_empty_pool(self):
        """没有原项目授权时保存指南不自动全选，也不启用新养号。:return: None。"""
        self.connection.execute('DELETE FROM projects_agents WHERE account_id=1');self.connection.commit()
        migrate_warmup_configuration(main.get_db, main._db_lock)
        value = self.warmup.state(1)['agents'][0]
        self.assertEqual([], value['project_keys'])
        self.assertFalse(value['schedule']['enabled'])
        with self.assertRaises(ValueError):
            self.warmup.start(1)

    def test_real_legacy_round_blocks_takeover_without_relabeling_it_as_engineering(self):
        """真实题库轮次保留原记录并阻止新养号，不能转换成工程成功。:return: None。"""
        self.connection.execute('UPDATE warmup_pi_agents SET managed=1,session_file=? WHERE account_id=1', ('private-session',))
        self.connection.commit()
        self.assertIsNotNone(warmup_migration_blocker(main.get_db, 1))
        result = migrate_warmup_configuration(main.get_db, main._db_lock)
        self.assertEqual([1], result['blocked_accounts'])
        self.assertEqual(0, self.connection.execute('SELECT count(*) FROM warmup_projects_agents').fetchone()[0])
        self.assertEqual('legacy_warmup', main._warmup_projects_admission(main._projects_account(1), None)['reason'])
        self.assertEqual(0, self.connection.execute('SELECT count(*) FROM warmup_projects_work').fetchone()[0])

    def test_old_run_starts_only_the_independent_engine_without_enabling_any_plan(self):
        """旧立即运行入口可启动关闭计划下的工程养号，原项目和旧开关不变。:return: None。"""
        migrate_warmup_configuration(main.get_db, main._db_lock)
        before = self.original();account = main._projects_account(1)
        result = main.run_account_warmup_now(1)
        self.assertEqual(('projects', True), (result['engine'], result['started']))
        self.assertTrue(self.warmup_pi.entered.wait(1))
        self.assertEqual(before, self.original())
        self.assertEqual(account, main._projects_account(1))
        self.assertFalse(self.warmup.state(1)['agents'][0]['schedule']['enabled'])
        self.assertFalse(self.pi.entered.is_set())
        self.assertEqual('warmup', self.owners.owner(1)['kind'])
        self.scheduler.submit = Mock(side_effect=AssertionError('不允许旧题库执行'))
        main.warmup_scheduler.start();main.warmup_scheduler._tick()
        self.assertIsNone(main.warmup_scheduler._thread)
        self.scheduler.submit.assert_not_called()

    def test_shared_account_owner_defers_other_space_without_new_model(self):
        """两个进度空间独立，但同账号模型思考期即互斥。:return: None。"""
        migrate_warmup_configuration(main.get_db, main._db_lock)
        self.projects.start(1);self.assertTrue(self.pi.entered.wait(1))
        value = self.warmup.start(1)['agents'][0]
        self.assertFalse(value['controller_active'])
        self.assertFalse(self.warmup_pi.entered.is_set())
        self.assertEqual('projects', self.owners.owner(1)['kind'])

    def test_scheduler_keeps_own_claim_during_slow_terminal_resume_in_both_spaces(self):
        """真实调度扫描穿过慢终端准备时，自己的认领不能撤销代次或丢失原目标与会话。:return: None。"""
        migrate_warmup_configuration(main.get_db, main._db_lock)
        for namespace, service, terminal, pi in (('projects', self.projects, self.terminal, self.pi),
                ('warmup', self.warmup, self.warmup_terminal, self.warmup_pi)):
            with self.subTest(namespace=namespace):
                original_start = terminal.start

                def native_start(account, work):
                    """使用与真实终端一致的服务端来源。:param account: 账号。:param work: 工作。:return: 原生定位。"""
                    return {**original_start(account, work), 'source': f"{namespace}:{work['id']}:{work['generation']}"}

                with patch.object(terminal, 'start', side_effect=native_start):
                    service.start(1)
                    self.assertTrue(pi.entered.wait(1))
                    first_generation = service.state(1)['agents'][0]['generation']
                    first = service.tool(1, first_generation, 'claude_start', {'project_key': 'example', 'objective_id': 'feature'}, 'seed')
                self.assertEqual('running', first['status'])
                original = service.state(1)['agents'][0]['work']
                service.pause(1)
                self.join(service)
                service._write('UPDATE projects_work SET work_sec=? WHERE id=?', (1804.6653017997742, original['id']))
                service.start(1)
                generation = service.state(1)['agents'][0]['generation']
                registered, proceed = threading.Event(), threading.Event()
                jobs, results = [], []

                def slow_start(account, work):
                    """先登记真实运行器作业，再等待测试允许终端准备返回。:param account: 账号。:param work: 工作。:return: 原生定位。"""
                    job = {'row': {'account_id': account['id'], 'environment_id': 'slow-claim-fixture'},
                        'source': f"{namespace}:{work['id']}:{work['generation']}", 'shared_cli': True, 'claimed': True}
                    with main.account_runtime.lock:
                        main.account_runtime._register_job(job)
                    jobs.append(job)
                    registered.set()
                    if not proceed.wait(3):
                        raise AssertionError('隔离终端准备未按预期释放')
                    return native_start(account, work)

                def resume():
                    """从真实工具边界恢复原工程。:return: None。"""
                    results.append(service.tool(1, generation, 'claude_start', {'project_key': 'example', 'objective_id': 'feature'}, 'resume'))

                thread = threading.Thread(target=resume)
                try:
                    with patch.object(terminal, 'start', side_effect=slow_start):
                        thread.start()
                        self.assertTrue(registered.wait(1))
                        saved = service._one('SELECT * FROM projects_work WHERE id=?', (original['id'],))
                        self.assertIsNone(saved['runtime_json'])
                        self.assertNotEqual(generation, saved['generation'])
                        service.tick()
                        service.tick()
                        current = service.state(1)['agents'][0]
                        self.assertEqual(generation, current['generation'])
                        self.assertTrue(current['controller_active'])
                        self.assertEqual('running', current['status'])
                        proceed.set()
                        thread.join(2)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual('running', results[0]['status'])
                    current = service.state(1)['agents'][0]
                    self.assertEqual((original['id'], original['session_id'], 1804.6653017997742),
                        tuple(current['work'][key] for key in ('id', 'session_id', 'work_sec')))
                    self.assertFalse(any(item['kind'] == 'gate_wait' and item['payload'].get('reason') == 'busy'
                        for item in service.event_page(1, limit=100)['items']))
                    self.assertEqual(2, len(terminal.started))
                    self.assertEqual([], terminal.sent)
                finally:
                    proceed.set()
                    thread.join(3)
                    with main.account_runtime.lock:
                        for job in jobs:
                            main.account_runtime._remove_job(job)
                    service.pause(1)
                    self.join(service)

    def test_quota_save_changes_no_schedule_and_legacy_plan_fields_are_explicitly_rejected(self):
        """保存额度只改额度，旧小时计划不能静默覆盖任一工程空间。:return: None。"""
        migrate_warmup_configuration(main.get_db, main._db_lock)
        original = self.original()
        warmup = dict(self.connection.execute('SELECT * FROM warmup_projects_agents').fetchone())
        main.update_account_warmup(1, main.WarmupConfigIn(warmup_quota_5h_limit_percent=45))
        self.assertEqual(45, main._projects_account(1)['warmup_quota_5h_limit_percent'])
        self.assertEqual(original, self.original())
        self.assertEqual(warmup, dict(self.connection.execute('SELECT * FROM warmup_projects_agents').fetchone()))
        with self.assertRaises(HTTPException) as rejected:
            main.update_account_warmup(1, main.WarmupConfigIn(enabled=False, interval_min_hours=3, interval_max_hours=5))
        self.assertEqual(409, rejected.exception.status_code)
        self.assertEqual(original, self.original())

    def test_old_resume_requires_the_original_unfinished_work_and_does_not_enable_schedule(self):
        """恢复入口不能创造新目标，已有目标恢复保留UUID、累计与关闭计划。:return: None。"""
        migrate_warmup_configuration(main.get_db, main._db_lock)
        with self.assertRaises(HTTPException) as rejected:
            main.resume_account_warmup(1)
        self.assertEqual(409, rejected.exception.status_code)
        self.warmup.start(1);self.assertTrue(self.warmup_pi.entered.wait(1))
        generation = self.warmup.state(1)['agents'][0]['generation']
        result = self.warmup.tool(1, generation, 'claude_start', {'project_key': 'example', 'objective_id': 'feature'}, 'start')
        self.assertNotEqual('rejected', result.get('status'))
        first = self.warmup.state(1)['agents'][0]['work']
        self.warmup.pause(1);self.join(self.warmup)
        resumed = main.resume_account_warmup(1)
        current = resumed['state']['agents'][0]
        self.assertEqual(first['id'], current['work']['id'])
        self.assertEqual(first['session_id'], current['work']['session_id'])
        self.assertFalse(current['schedule']['enabled'])
        self.assertFalse(main._projects_account(1)['warmup_enabled'])

    def test_apis_share_engine_protocol_and_keep_namespace_specific_state(self):
        """两入口完整复用工程API，严格类型及随机计划保持各自空间。:return: None。"""
        migrate_warmup_configuration(main.get_db, main._db_lock)
        application = FastAPI()
        application.include_router(projects_router(lambda: self.projects))
        application.include_router(warmup_pi_router(lambda: self.warmup))
        with TestClient(application) as client:
            base = '/api/accounts/warmup/pi'
            self.assertEqual('warmup', client.get(base).json()['namespace'])
            self.assertEqual('projects', client.get('/api/projects').json()['namespace'])
            self.assertEqual(200, client.get(base + '/catalog').status_code)
            self.assertEqual([], client.get(base + '/agents/1/work/page').json()['items'])
            self.assertEqual(200, client.put(base + '/agents/1/schedule', json={'enabled': False,
                'interval_minutes': 180, 'interval_max_minutes': 300}).status_code)
            self.assertEqual(422, client.put(base + '/agents/1/schedule', json={'enabled': False,
                'interval_minutes': 180, 'interval_max_minutes': True}).status_code)
            self.assertEqual(422, client.put(base + '/agents/1', json={'project_keys': ['example'],
                'instructions': '', 'budget_sec': True}).status_code)
        self.assertEqual(30, self.projects.state(1)['agents'][0]['schedule']['interval_minutes'])

    def test_account_summary_reads_warmup_space_and_never_exposes_its_guide(self):
        """账号卡片只呈现独立养号现场，不能误把原项目30分钟计划挂进来。:return: None。"""
        migrate_warmup_configuration(main.get_db, main._db_lock)
        account = main.list_accounts()[0]
        self.assertEqual('projects', account['warmup_engine'])
        self.assertFalse(account['project_pi']['schedule']['enabled'])
        self.assertEqual(180, account['project_pi']['schedule']['interval_minutes'])
        self.assertEqual(300, account['project_pi']['schedule']['interval_max_minutes'])
        self.assertNotIn('instructions', account['project_pi'])
        self.assertNotIn('养号追加原文', json.dumps(account['project_pi'], ensure_ascii=False))
        self.assertTrue(self.projects.state(1)['agents'][0]['schedule']['enabled'])

    def test_legacy_round_without_managed_flag_still_blocks_new_engine(self):
        """即使接管标志未写入，已有真实题库记录也不能被当作空配置迁移。:return: None。"""
        self.connection.execute('INSERT INTO warmup_pi_rounds(id,account_id,generation,topic_id,topic_no,title,topic_json,'
            'settings_json,account_identity,status,session_id,created_at) VALUES(?,1,1,1,1,?,?,?,?,?,?,?)',
            ('a' * 32, '旧题', '{}', '{}', 'old-identity', 'completed', 'old-session', time.time()))
        self.connection.commit()
        self.assertIsNotNone(warmup_migration_blocker(main.get_db, 1))
        self.assertEqual([1], migrate_warmup_configuration(main.get_db, main._db_lock)['blocked_accounts'])
        self.assertEqual(1, self.connection.execute('SELECT count(*) FROM warmup_pi_rounds').fetchone()[0])
        self.assertEqual(0, self.connection.execute('SELECT count(*) FROM warmup_projects_work').fetchone()[0])

    def test_native_quota_proof_cannot_cross_engine_namespaces(self):
        """养号原生额度只接受同空间工作和代次，原项目入口不能借用它的证明。:return: None。"""
        migrate_warmup_configuration(main.get_db, main._db_lock)
        self.warmup.start(1);self.assertTrue(self.warmup_pi.entered.wait(1))
        generation = self.warmup.state(1)['agents'][0]['generation']
        self.warmup.tool(1, generation, 'claude_start', {'project_key': 'example', 'objective_id': 'feature'}, 'start-quota')
        work = self.warmup.state(1)['agents'][0]['work']
        source = f"warmup:{work['id']}:{generation}"
        self.connection.execute('UPDATE warmup_projects_work SET runtime_json=? WHERE id=?',
            (json.dumps({'source': source, 'token': 'fixture'}), work['id']))
        self.connection.commit()
        account = main._projects_account(1)
        facts = {'quota_limited': True, 'window': 'five_hour', 'observed_at': time.time(), 'retry_at': time.time() + 300}
        main._projects_native_quota(account, source, facts)
        self.assertFalse(self.guard.snapshot(account)['blocked'])
        main._warmup_projects_native_quota(account, source, facts)
        self.assertTrue(self.guard.snapshot(account)['blocked'])


if __name__ == '__main__':
    unittest.main()
