"""使用独立 SQLite 验证账号版本继承、增量配置和旧执行兼容。"""
import sqlite3
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import main
import test_main
from test_tls_capture_artifacts import clienthello_record


class AccountCliSettingsTests(unittest.TestCase):
    """从设置 API 到运行创建及真实启动参数核对版本，不使用真实账号。"""

    def setUp(self) -> None:
        """复用独立目录夹具并关闭外部运行依赖。:return: None。"""
        self.fixture = test_main.ClaudeCodeVersionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        for name, value in {'account_runtime': None, 'quota_guard': None, 'warmup_pi_service': None,
                'scheduler': Mock(), '_AUTH_ENABLED': False}.items():
            context = patch.object(main, name, value)
            context.start()
            self.addCleanup(context.stop)
        self.client = TestClient(main.app)
        self.sql("INSERT INTO accounts(id,name,profile_path,warmup_enabled) VALUES(1,'main',?,1)",
            (str(main.PROFILES_DIR / 'main'),))
        self.sql("INSERT INTO topics(id,no,title,description) VALUES(1,1,'Synthetic','A local fixture')")
        self.sql("INSERT INTO tasks(id,topic_no,title,prompt,account_id) VALUES(1,1,'Synthetic','Implement a fixture',1)")
        main.update_claude_code_version(main.ClaudeCodeVersionIn(claude_code_version='2.1.293'))

    def sql(self, statement: str, parameters=()) -> list[dict]:
        """执行测试专属 SQL。:param statement: SQL。:param parameters: 参数。:return: 行列表。"""
        with main._db_lock:
            connection = main.get_db()
            try:
                with connection:
                    return [dict(row) for row in connection.execute(statement, parameters)]
            finally:
                connection.close()

    def test_settings_default_off_partial_updates_and_validation(self) -> None:
        """两个空间独立更新，清空版本继承全局，错误不落库。:return: None。"""
        value = self.client.get('/api/accounts/1/cli-settings').json()
        self.assertFalse(value['projects_capture_enabled'])
        self.assertFalse(value['warmup_capture_enabled'])
        self.assertEqual(('2.1.293', 'global'), (value['effective_claude_code_version'], value['claude_code_version_source']))
        value = self.client.put('/api/accounts/1/cli-settings', json={
            'claude_code_version': ' 2.1.303 ', 'projects_capture_enabled': True}).json()
        self.assertEqual(('2.1.303', 'account'), (value['effective_claude_code_version'], value['claude_code_version_source']))
        self.assertTrue(value['projects_capture_enabled'])
        value = self.client.put('/api/accounts/1/cli-settings', json={'warmup_capture_enabled': True}).json()
        self.assertTrue(value['projects_capture_enabled'])
        self.assertTrue(value['warmup_capture_enabled'])
        self.assertEqual('2.1.303', value['claude_code_version'])
        for payload, status in [({'claude_code_version': 'latest'}, 400),
                ({'projects_capture_enabled': 1}, 422), ({'unrelated': True}, 422)]:
            with self.subTest(payload=payload):
                self.assertEqual(status, self.client.put('/api/accounts/1/cli-settings', json=payload).status_code)
        value = self.client.put('/api/accounts/1/cli-settings', json={'claude_code_version': None}).json()
        self.assertEqual('2.1.293', value['effective_claude_code_version'])
        self.assertTrue(value['warmup_capture_enabled'])
        main.scheduler.submit.assert_not_called()
        self.assertEqual([], self.sql('SELECT id FROM runs'))
        self.sql('UPDATE accounts SET deleted_at=1 WHERE id=1')
        self.assertEqual(404, self.client.get('/api/accounts/1/cli-settings').status_code)
        self.assertEqual(404, self.client.put('/api/accounts/1/cli-settings', json={}).status_code)

    def test_all_run_creators_freeze_account_version_and_single_override(self) -> None:
        """普通、批次、旧养号与抓包同规则，单次值不回写账号和全局。:return: None。"""
        self.sql("UPDATE accounts SET claude_code_version='2.1.303' WHERE id=1")
        normal = main.run_task(1)['run_ids'][0]
        capture = main.start_capture_run(main.CaptureRunIn(account_id=1, topic_id=1,
            claude_code_version='2.1.293'))
        self.sql("INSERT INTO task_batches(id,account_id,name) VALUES(1,1,'Synthetic')")
        self.sql("INSERT INTO task_batch_items(id,batch_id,topic_id,prompt) VALUES(1,1,1,'Synthetic')")
        account = self.sql('SELECT * FROM accounts WHERE id=1')[0]
        batch = self.sql('SELECT * FROM task_batches WHERE id=1')[0]
        item = {**self.sql('SELECT * FROM task_batch_items WHERE id=1')[0], 'topic_no': 1, 'title': 'Synthetic'}
        created = main.Scheduler(Mock())._create_batch_task_and_run(batch, account, item, 'batch-fixture')
        self.assertEqual('2.1.303', created[1])
        topic = self.sql('SELECT * FROM topics WHERE id=1')[0]
        warmup = main.WarmupScheduler(Mock())._create_task_and_run(account, topic, 'Synthetic warmup')
        self.assertEqual('2.1.303', warmup[2])
        versions = {row['id']: (row['claude_code_version'], row['claude_code_version_source'])
            for row in self.sql('SELECT * FROM runs')}
        self.assertEqual(('2.1.303', 'account'), versions[normal])
        self.assertEqual(('2.1.293', 'explicit'), versions[capture['run_id']])
        self.assertEqual(('2.1.303', 'account'), versions['batch-fixture'])
        self.assertEqual(('2.1.303', 'account'), versions[warmup[0]])
        self.assertEqual('2.1.303', main._project_execution_settings(account)['claude_code_version'])
        self.assertEqual('2.1.293', main.effective_claude_code_version())
        self.sql('UPDATE accounts SET claude_code_version=NULL WHERE id=1')
        main.update_claude_code_version(main.ClaudeCodeVersionIn(claude_code_version='2.1.280'))
        self.assertEqual('2.1.303', self.sql('SELECT * FROM runs WHERE id=?', (normal,))[0]['claude_code_version'])
        self.assertEqual('2.1.280', main._resolve_account_cli_version(self.sql('SELECT * FROM accounts WHERE id=1')[0])[0])

    def test_old_empty_snapshot_is_filled_once_with_source(self) -> None:
        """兼容回填先持久化，之后即使默认改变或启动失败也不漂移。:return: None。"""
        self.sql("UPDATE accounts SET claude_code_version='2.1.303' WHERE id=1")
        self.sql("INSERT INTO runs(id,task_id,account_id,claude_code_version) VALUES('legacy',1,1,'')")
        value = self.sql("SELECT * FROM runs WHERE id='legacy'")[0]
        self.assertEqual('2.1.303', main._ensure_run_claude_code_version(value))
        self.assertEqual('legacy-account', value['claude_code_version_source'])
        self.sql("UPDATE accounts SET claude_code_version='2.1.293' WHERE id=1")
        value = self.sql("SELECT * FROM runs WHERE id='legacy'")[0]
        self.assertEqual('2.1.303', main._ensure_run_claude_code_version(value))

    def test_capture_run_existing_summary_exposes_safe_tls_and_keeps_route_visibility(self) -> None:
        """普通抓包沿原鉴权摘要展示握手，不扩大原始文件下载或已删除运行权限。:return: None。"""
        capture = main.start_capture_run(main.CaptureRunIn(account_id=1, topic_id=1, claude_code_version='2.1.293'))
        directory = main.FLOWS_DIR / 'main' / str(capture['task_id']) / capture['run_id']
        directory.mkdir(parents=True)
        self.sql('UPDATE runs SET flows_dir=? WHERE id=?', (str(directory), capture['run_id']))
        record = clienthello_record('real-client-connection')
        record['capture_context'] = {'schema': 1, 'source': f'run:{capture["run_id"]}:0',
            'run_id': capture['run_id'], 'claude_code_version': '2.1.293'}
        (directory / 'tls_clienthello.jsonl').write_text(json.dumps(record) + '\n')
        (directory / 'capture_index.json').write_text(json.dumps({'entries': [{'flow_id': 'http-flow',
            'client_connection_id': 'real-client-connection', 'capture_state': 'complete'}]}))
        response = self.client.get(f'/api/runs/{capture["run_id"]}/capture')
        self.assertEqual(200, response.status_code)
        value = response.json()
        self.assertEqual('real-client-connection', value['tls_clienthello']['entries'][0]['client_connection_id'])
        self.assertEqual(value['index']['entries'][0]['client_connection_id'],
            value['tls_clienthello']['entries'][0]['client_connection_id'])
        self.assertEqual('2.1.293', value['tls_clienthello']['entries'][0]['capture_context']['claude_code_version'])
        self.assertNotIn('PRIVATE_TLS_CANARY', response.text)
        self.assertEqual(404, self.client.get(f'/api/runs/{capture["run_id"]}/capture/file?path=tls_clienthello.jsonl').status_code)
        self.sql('UPDATE runs SET deleted_at=1 WHERE id=?', (capture['run_id'],))
        self.assertEqual(404, self.client.get(f'/api/runs/{capture["run_id"]}/capture').status_code)

    def test_batch_and_warmup_use_current_account_at_creation(self) -> None:
        """长期调度持有旧账号对象时，新执行仍采用创建事务中的当前配置。:return: None。"""
        self.sql("UPDATE accounts SET claude_code_version='2.1.303' WHERE id=1")
        stale = self.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.sql("UPDATE accounts SET claude_code_version='2.1.293' WHERE id=1")
        self.sql("INSERT INTO task_batches(id,account_id,name) VALUES(1,1,'Synthetic')")
        self.sql("INSERT INTO task_batch_items(id,batch_id,topic_id,prompt) VALUES(1,1,1,'Synthetic')")
        item = {**self.sql('SELECT * FROM task_batch_items WHERE id=1')[0], 'topic_no': 1, 'title': 'Synthetic'}
        batch = self.sql('SELECT * FROM task_batches WHERE id=1')[0]
        created = main.Scheduler(Mock())._create_batch_task_and_run(batch, stale, item, 'fresh-account')
        self.assertEqual('2.1.293', created[1])
        warmup = main.WarmupScheduler(Mock())._create_task_and_run(stale,
            self.sql('SELECT * FROM topics WHERE id=1')[0], 'Synthetic')
        self.assertEqual('2.1.293', warmup[2])

    def test_existing_login_uses_account_version_and_keeps_it_for_auth_status(self) -> None:
        """账号版本控制登录实际容器与后续子命令，旧会话不读取新配置。:return: None。"""
        self.sql("UPDATE accounts SET claude_code_version='2.1.303' WHERE id=1")
        client, calls = self.fixture._docker_client()
        manager = main.LoginManager(client)
        session = manager.start('main', {})
        self.assertEqual('2.1.303', session.version)
        self.assertEqual('2.1.303', calls[-1][1]['environment']['CLAUDE_CODE_VERSION'])
        self.sql("UPDATE accounts SET claude_code_version='2.1.293' WHERE id=1")
        client.api.exec_start.return_value = b'{"loggedIn":true}'
        client.api.exec_create.return_value = {'Id': 'auth-fixture'}
        self.assertTrue(manager.auth_status(session.sid)['loggedIn'])
        self.assertEqual('2.1.303', client.api.exec_create.call_args.kwargs['environment']['CLAUDE_CODE_VERSION'])

    def test_legacy_snapshot_prefers_matching_execution_evidence(self) -> None:
        """旧空快照优先恢复来源和容器代次均匹配的版本证明。:return: None。"""
        self.sql("UPDATE accounts SET claude_code_version='2.1.303' WHERE id=1")
        self.sql('CREATE TABLE IF NOT EXISTS account_environments(environment_id TEXT,account_id INTEGER,container_id TEXT,generation INTEGER)')
        self.sql("INSERT INTO account_environments(environment_id,account_id,container_id,generation) VALUES('fixture-env',1,'fixture-container',4)")
        columns = {row['name'] for row in self.sql('PRAGMA table_info(runs)')}
        for name, declaration in [('environment_id', 'TEXT'), ('environment_generation', 'INTEGER'), ('execution_source', 'TEXT')]:
            if name not in columns:
                self.sql(f'ALTER TABLE runs ADD COLUMN {name} {declaration}')
        self.sql("INSERT INTO runs(id,task_id,account_id,environment_id,environment_generation,execution_source) VALUES('proof',1,1,'fixture-env',4,'run:proof:0')")
        root = self.fixture.base / 'account-fixture'
        (root / 'runtime').mkdir(parents=True)
        (root / 'runtime/execution.json').write_text(json.dumps({'source': 'run:proof:0', 'generation': 4,
            'container_id': 'fixture-container', 'version': '2.1.293'}))
        value = self.sql("SELECT * FROM runs WHERE id='proof'")[0]
        with patch.object(main, 'account_runtime', SimpleNamespace(_root=lambda row: root)):
            self.assertEqual('2.1.293', main._ensure_run_claude_code_version(value))
        self.assertEqual('legacy-execution', value['claude_code_version_source'])

    def test_old_schema_upgrade_keeps_data_and_defaults(self) -> None:
        """真实旧 schema 连续升级保持旧配置及运行数据。:return: None。"""
        path = self.fixture.base / 'legacy.sqlite'
        schema = main._SCHEMA
        for line in ['  claude_code_version TEXT,\n', '  projects_capture_enabled INTEGER NOT NULL DEFAULT 0,\n',
                '  warmup_capture_enabled INTEGER NOT NULL DEFAULT 0,\n', '  claude_code_version_source TEXT,\n']:
            schema = schema.replace(line, '')
        with sqlite3.connect(path) as connection:
            connection.executescript(schema)
            connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(1,'legacy','legacy')")
            connection.execute("INSERT INTO runs(id,task_id,account_id) VALUES('old',1,1)")
        with patch.object(main, 'DB_PATH', path):
            main.init_db(); main.init_db()
            account = self.sql('SELECT * FROM accounts')[0]
            self.assertEqual((None, 0, 0), (account['claude_code_version'], account['projects_capture_enabled'], account['warmup_capture_enabled']))
            self.assertEqual('old', self.sql('SELECT * FROM runs')[0]['id'])


if __name__ == '__main__':
    unittest.main()
