"""节点登记、版本竞争、默认归属和私钥公开边界的真实存储测试。"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from cluster_api import cluster_router
from cluster_migration_api import MigrationOperations
from cluster_migrations import NodeMigrations
from cluster_nodes import NodeAddress, NodeConfiguration, NodeCreate, host_key_identity
from cluster_service import ClusterService
from cluster_ssh import NodeSshError
from cluster_store import ClusterStore, NodeRemoved
from account_runtime import AccountRuntime, RuntimeBusy, derive_v3_fingerprint
from database_migrations import apply_migrations, migration_plan


class ClusterNodeTests(unittest.TestCase):
    """使用临时 SQLite 和真实 OpenSSH 密钥验证登记合同。"""

    def setUp(self) -> None:
        """创建独立数据库与密钥。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'db.sqlite'
        connection = self.database()
        try:
            apply_migrations(connection)
        finally:
            connection.close()
        self.store = ClusterStore(self.database, threading.Lock())
        self.service = ClusterService(self.store, self.root, Mock(), self.root / 'transport')
        self.addCleanup(self.service.close)
        self.key = self.root / 'test-key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(self.key)], check=True, capture_output=True)
        self.host_key = ' '.join(self.key.with_suffix('.pub').read_text().split()[:2])
        self.config = {'name': '节点一', 'host': '127.0.0.1', 'port': 2222, 'username': 'root',
            'host_key': self.host_key, 'data_root': '/srv/test-node'}

    def database(self):
        """返回测试连接。:return: 由调用方关闭的连接。"""
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def test_old_accounts_backfill_and_new_accounts_receive_local_assignment(self) -> None:
        """旧库回填与新账号触发器保持唯一默认归属。:return: None。"""
        connection = sqlite3.connect(':memory:')
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        apply_migrations(connection, target=1)
        with connection:
            connection.execute("INSERT INTO accounts(name,profile_path) VALUES('old','profiles/old')")
        apply_migrations(connection)
        with connection:
            connection.execute("INSERT INTO accounts(name,profile_path) VALUES('new','profiles/new')")
        apply_migrations(connection)
        rows = connection.execute('SELECT a.name,n.node_key FROM accounts a JOIN account_node_assignments b '
            'ON b.account_id=a.id JOIN cluster_nodes n ON n.id=b.node_id ORDER BY a.id').fetchall()
        self.assertEqual([('old', 'local'), ('new', 'local')], [tuple(row) for row in rows])
        self.assertEqual(1, connection.execute('SELECT COUNT(*) FROM cluster_nodes').fetchone()[0])

    def test_account_count_excludes_deleted_and_keeps_disabled_and_historical_assignments(self) -> None:
        """公开计数排除软删除，停用账号继续计入，历史归属保留并支持恢复。:return: None。"""
        node = self.service.register(NodeCreate(**self.config, private_key=self.key.read_text()))
        connection = self.database()
        self.addCleanup(connection.close)
        with connection:
            connection.execute("INSERT INTO accounts(name,profile_path) VALUES('active','profiles/active')")
            connection.execute("INSERT INTO accounts(name,profile_path,enabled) VALUES('disabled','profiles/disabled',0)")
            deleted = connection.execute("INSERT INTO accounts(name,profile_path,deleted_at) "
                "VALUES('deleted','profiles/deleted',1)").lastrowid
        assignments = [tuple(row) for row in connection.execute('SELECT * FROM account_node_assignments ORDER BY account_id')]
        counts = {row['node_key']: row['account_count'] for row in self.store.list()}
        self.assertEqual({'local': 2, node['node_key']: 0}, counts)
        self.assertEqual(assignments, [tuple(row) for row in connection.execute('SELECT * FROM account_node_assignments ORDER BY account_id')])
        with connection:
            connection.execute('UPDATE accounts SET deleted_at=NULL WHERE id=?', (deleted,))
        self.assertEqual(3, next(row['account_count'] for row in self.store.list() if row['node_key'] == 'local'))

    def test_remote_summary_exposes_only_the_observed_293_kernel(self) -> None:
        """新中央读取旧节点时只展示 293；280 的信息不能充当 293 状态。@return 无。"""
        node = self.store.create('a' * 32, NodeConfiguration(**self.config))
        connection = self.database()
        self.addCleanup(connection.close)
        with connection:
            account = connection.execute("INSERT INTO accounts(name,profile_path,cc2api_account_id) VALUES('fake','profiles/fake',7)").lastrowid
            connection.execute('UPDATE account_node_assignments SET node_id=?,revision=3 WHERE account_id=?', (node['id'], account))
        row = {'account_id': account, 'environment_id': 'e' * 32, 'generation': 3}
        old = {'source_version': '2.1.280', 'state': 'builtin'}
        current = {'source_version': '2.1.293', 'state': 'builtin'}
        observed = {**row, 'assignment_revision': 3, 'gateway_account_id': 7, 'busy': False, 'state': 'ready',
            'role_status': {}, 'identity_status': '已确认', 'physical_features': None, 'cli_versions': ['2.1.280'],
            'runtime_release': 'fixture', 'content_capture': None, 'criu': None, 'native_kernel': old,
            'native_kernels': {'2.1.280': old, '2.1.293': current}}
        runtime = SimpleNamespace(release_id='fixture', deployment='test')
        with patch.object(self.service, 'connection') as remote:
            remote.return_value.prepare_environment.return_value = observed
            summary = self.service.remote_summary(row, runtime, '2.1.280')
            self.assertEqual((summary['native_kernel'], summary['native_kernels']), (current, {'2.1.293': current}))
            self.assertEqual(summary['cli_versions'], ['2.1.280'])
            del observed['native_kernels']['2.1.293']
            summary = self.service.remote_summary(row, runtime, '2.1.280')
            self.assertEqual((summary['native_kernel'], summary['native_kernels']), (None, {'2.1.293': None}))

    def test_missing_registered_cluster_structure_is_rejected(self) -> None:
        """已登记库损坏时拒绝伪装成功。:return: None。"""
        connection = self.database()
        self.addCleanup(connection.close)
        connection.execute('DROP TRIGGER cluster_assign_new_account')
        with self.assertRaisesRegex(ValueError, '节点迁移'):
            migration_plan(connection)

    def test_account_node_summaries_are_read_only_safe_and_preserve_unreachable_assignment(self) -> None:
        """停用账号和失联节点保留真实归属，列表摘要排除内部配置。:return: None。"""
        remote = self.store.create('a' * 32, NodeConfiguration(**self.config))
        connection = self.database()
        try:
            with connection:
                connection.execute("INSERT INTO accounts(name,profile_path) VALUES('local-account','profiles/local')")
                connection.execute("INSERT INTO accounts(name,profile_path,enabled) VALUES('remote-account','profiles/remote',0)")
                connection.execute("INSERT INTO accounts(name,profile_path,deleted_at) VALUES('deleted-account','profiles/deleted',1)")
                connection.execute("UPDATE account_node_assignments SET node_id=?,revision=3 WHERE account_id=2", (remote['id'],))
                connection.execute("UPDATE cluster_nodes SET observation_json=? WHERE id=?",
                    (json.dumps({'state': 'unreachable', 'observed_at': time.time(), 'reason': 'synthetic-private'}), remote['id']))
            traced = []
            connection.set_trace_callback(traced.append)
            with patch.object(self.store, 'database', return_value=connection):
                result = self.store.assignment_summaries()
            self.assertTrue(all(statement.startswith('SELECT ') for statement in traced))
        finally:
            connection.close()
        self.assertEqual(result[1]['node']['node_key'], 'local')
        self.assertIsNone(result[1]['node_observation'])
        self.assertNotIn(3, result)
        self.assertEqual(result[2]['node']['node_key'], 'a' * 32)
        self.assertEqual(result[2]['node']['revision'], 3)
        self.assertEqual(result[2]['node_observation']['state'], 'unreachable')
        self.assertFalse(result[2]['node_observation']['stale'])
        self.assertEqual(set(result[2]['node']), {'node_id', 'node_key', 'node_name', 'kind', 'enabled', 'revision', 'phase'})
        self.assertNotIn('synthetic-private', json.dumps(result))

    def test_registration_keeps_private_key_out_of_database_and_responses(self) -> None:
        """只写密钥进入0700/0600私有文件，公开及数据库保持脱敏。:return: None。"""
        request = NodeCreate(**self.config, private_key=self.key.read_text())
        result = self.service.register(request)
        serialized = json.dumps(result) + json.dumps(self.store.list())
        self.assertNotIn('PRIVATE KEY', serialized)
        self.assertNotIn('private_key', result)
        self.assertEqual('private_key', result['auth_method'])
        connection = self.database()
        self.addCleanup(connection.close)
        self.assertNotIn('PRIVATE KEY', json.dumps([tuple(row) for row in connection.execute('SELECT * FROM cluster_nodes')]))
        private = self.root / 'cluster-private' / result['node_key']
        self.assertEqual(0o700, private.stat().st_mode & 0o777)
        self.assertEqual(0o600, (private / 'identity').stat().st_mode & 0o777)
        self.assertEqual(0o600, (private / 'known_hosts').stat().st_mode & 0o777)
        with self.assertRaisesRegex(ValueError, '已登记'):
            self.service.register(request)
        self.assertEqual(1, len(list((self.root / 'cluster-private').iterdir())))

    def test_stale_observation_cannot_overwrite_new_node_configuration(self) -> None:
        """失效配置的迟到观测保持丢弃。:return: None。"""
        node = self.service.register(NodeCreate(**self.config, private_key=self.key.read_text()))
        updated = self.store.set_enabled(node['id'], node['revision'], False)
        self.assertEqual(node['revision'] + 1, updated['revision'])
        self.assertFalse(self.store.save_observation(node['id'], node['revision'], {'state': 'reachable', 'observed_at': 0}))
        self.assertIsNone(updated['observation'])
        with self.assertRaisesRegex(ValueError, '已变化'):
            self.store.set_enabled(node['id'], node['revision'], True)

    def test_referenced_node_and_local_node_cannot_be_removed(self) -> None:
        """实际账号引用和本机默认节点受到保护。:return: None。"""
        node = self.service.register(NodeCreate(**self.config, private_key=self.key.read_text()))
        connection = self.database()
        self.addCleanup(connection.close)
        with connection:
            account = connection.execute("INSERT INTO accounts(name,profile_path,enabled) VALUES('linked','profiles/linked',0)").lastrowid
            connection.execute('UPDATE account_node_assignments SET node_id=? WHERE account_id=?', (node['id'], account))
        self.assertEqual(node['id'], self.store.assignment(account)['node_id'])
        with self.assertRaisesRegex(ValueError, '关联账号'):
            self.service.remove(node['id'], node['revision'])
        local = self.store.list()[0]
        with self.assertRaisesRegex(ValueError, '本机'):
            self.service.remove(local['id'], local['revision'])

    def test_rename_paused_node_preserves_raw_ssh_identity_and_account_assignment(self) -> None:
        """改名沿原身份更新显示列，并拒绝旧版本或无效名称。:return: 无。"""
        node = self.service.register(NodeCreate(**self.config, private_key=self.key.read_text()))
        paused = self.store.set_enabled(node['id'], node['revision'], False)
        original = self.store.get(node['id'])['config_json']
        connection = self.database()
        self.addCleanup(connection.close)
        with connection:
            account = connection.execute("INSERT INTO accounts(name,profile_path) VALUES('linked','profiles/linked')").lastrowid
            connection.execute('UPDATE account_node_assignments SET node_id=? WHERE account_id=?', (node['id'], account))
        app = FastAPI()
        app.include_router(cluster_router(lambda: self.service))
        with TestClient(app) as client, patch.object(self.service, 'connection', side_effect=AssertionError('改名无需连接宿主')):
            path = f"/api/nodes/{node['id']}/name"
            body = {'revision': paused['revision'], 'name': ' 日本执行节点 '}
            self.assertEqual(422, client.put(path, json={**body, 'name': '一\n二'}).status_code)
            response = client.put(path, json=body)
            self.assertEqual(200, response.status_code)
            self.assertEqual(409, client.put(path, json=body).status_code)
        self.assertEqual('日本执行节点', response.json()['name'])
        self.assertEqual((False, node['node_key']), (response.json()['enabled'], response.json()['node_key']))
        self.assertEqual(original, self.store.get(node['id'])['config_json'])
        self.assertEqual(('日本执行节点', 1), (self.store.assignment(account)['node_name'], self.store.assignment(account)['revision']))

    def test_removal_retries_original_operation_and_releases_endpoint_after_completion(self) -> None:
        """遗留已取消迁移可归档，断线重试继续原操作，原地址可重新登记。:return: 无。"""
        request = NodeCreate(**self.config, private_key=self.key.read_text())
        node = self.service.register(request)
        local = self.store.list()[0]
        connection = self.database()
        self.addCleanup(connection.close)
        with connection:
            account = connection.execute("INSERT INTO accounts(name,profile_path) VALUES('history','profiles/history')").lastrowid
            connection.execute("INSERT INTO accounts(name,profile_path,deleted_at) VALUES('old','profiles/old',1)")
            connection.execute("UPDATE account_node_assignments SET node_id=? WHERE account_id=(SELECT id FROM accounts WHERE name='old')", (node['id'],))
            connection.execute("INSERT INTO node_migrations VALUES(?,?,?,?,'requested',?,0,0)",
                ('a' * 32, account, local['id'], node['id'], json.dumps({'source_revision': 1, 'last_confirmed_phase': 'requested'})))
        with self.assertRaisesRegex(ValueError, '未结束迁移'):
            self.service.remove(node['id'], node['revision'])
        with connection:
            connection.execute("UPDATE node_migrations SET phase='cancelled'")
        app = FastAPI()
        app.include_router(cluster_router(lambda: self.service))
        release = threading.Event()
        self.addCleanup(release.set)

        def interrupt(record, installed, checkpoint):
            checkpoint(phase='clearing_data', proof={'original': True})
            release.wait(timeout=5)
            raise NodeSshError('connection_failed')

        def finish(record, installed, checkpoint):
            self.assertEqual('clearing_data', record['phase'])
            self.assertEqual({'original': True}, record['proof'])

        with TestClient(app) as client, patch('cluster_service.NodeRemoval') as cleanup, patch.object(self.service, 'docker'):
            cleanup.return_value.run.side_effect = interrupt
            path = f"/api/nodes/{node['id']}"
            body = {'revision': node['revision']}
            accepted = client.request('DELETE', path, json=body)
            self.assertEqual(202, accepted.status_code)
            operation = accepted.json()['operation_id']
            self.assertEqual(operation, client.request('DELETE', path, json=body).json()['operation_id'])
            self.assertFalse(self.store.get(node['id'])['enabled'])
            with self.assertRaisesRegex(ValueError, '原账号的节点'):
                self.store.require_account_restore(connection, 'old')
            with self.assertRaisesRegex(ValueError, '暂停接单'):
                self.store.assign_unstarted(account, node['id'], 1)
            with self.assertRaisesRegex(ValueError, '进入移除'):
                self.store.set_enabled(node['id'], node['revision'] + 1, True)
            with self.assertRaisesRegex(ValueError, '已登记'):
                self.service.register(request)
            with self.service.lock:
                worker = self.service.removal_workers[node['id']]
            release.set()
            worker.join(timeout=5)
            failed = self.store.list()[1]['removal']
            self.assertEqual((operation, 'needs_check', 'clearing_data'), (failed['operation_id'], failed['state'], failed['phase']))
            cleanup.return_value.run.side_effect = finish
            self.assertEqual(202, client.request('DELETE', path, json={'revision': node['revision'] + 1}).status_code)
            with self.service.operation_locks[node['id']]:
                self.assertEqual([local['id']], [item['id'] for item in self.store.list()])
            replay = client.request('DELETE', path, json=body)
            self.assertEqual((operation, 'completed'), (replay.json()['operation_id'], replay.json()['state']))
        self.assertEqual(('cancelled', node['id']), tuple(connection.execute('SELECT phase,target_node_id FROM node_migrations').fetchone()))
        history = MigrationOperations(SimpleNamespace(service=self.service, ledger=NodeMigrations(self.store))).list(account)
        self.assertEqual(('cancelled', {'id': node['id'], 'name': node['name']}), (history['items'][0]['phase'], history['items'][0]['target']))
        with self.assertRaisesRegex(ValueError, '远程文件已清理'):
            self.service.connection(node['id'])
        self.assertNotEqual(node['node_key'], self.service.register(request)['node_key'])

    def test_execution_history_keeps_original_node_and_account_references(self) -> None:
        """账号已迁出后仍保留节点执行历史，未收口执行阻止凭据切换。:return: None。"""
        import main
        node = self.service.register(NodeCreate(**self.config, private_key=self.key.read_text()))
        connection = self.database()
        self.addCleanup(connection.close)
        with connection:
            account_id = connection.execute("INSERT INTO accounts(name,profile_path) VALUES('historic','profiles/historic')").lastrowid
            connection.execute("INSERT INTO account_environments(environment_id,account_id,name,fingerprint_json) "
                "VALUES(?,?,?,'{}')", ('e' * 32, account_id, 'historic'))
            connection.execute("INSERT INTO node_executions(operation_id,account_id,node_id,environment_id,"
                "assignment_revision,environment_generation,source,role,phase,record_json,created_at,updated_at) "
                "VALUES(?,?,?,?,1,1,'projects:historic:1','projects','reconcile','{}',0,0)",
                ('f' * 32, account_id, node['id'], 'e' * 32))
        account = dict(connection.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone())
        with patch.object(main, 'get_db', self.database), patch.object(main, 'pi_owners', None), \
                patch.object(main, 'continue_manager', None), patch.object(main, 'login_manager', None):
            self.assertIn('节点执行', main._oauth_owner_transition_blocker(account))
            self.assertEqual(1, main._account_reference_counts(connection, account_id)['node_executions'])
            with connection:
                connection.execute("UPDATE node_executions SET phase='closed'")
            self.assertIsNone(main._oauth_owner_transition_blocker(account))
        _, removal = self.store.begin_removal(node['id'], node['revision'])
        removal.update(phase='clearing_data', proof={'synthetic': True})
        self.store.save_removal(node['id'], removal)
        self.store.save_removal(node['id'], {**removal, 'state': 'completed', 'phase': 'completed'})
        self.assertEqual(('closed', node['id']), tuple(connection.execute('SELECT phase,node_id FROM node_executions').fetchone()))
        runner = Mock()
        runner.sessions.service = self.service
        runner.for_run.return_value = {'node_id': node['id'], 'record': {'scope': {'node_key': node['node_key'],
            'environment_id': 'e' * 32, 'assignment_revision': 1, 'generation': 1}}}
        runner.artifact_chunk.side_effect = NodeRemoved('原节点已移除，远程文件已清理')
        with patch.object(main, 'cluster_runner', runner), patch.object(main, '_require_visible_run'):
            self.assertEqual(node['name'], main._public_run_node('historic-run')['name'])
            with self.assertRaises(HTTPException) as raised:
                main.get_transcript('historic-run')
            self.assertEqual((410, '原节点已移除，远程文件已清理'), (raised.exception.status_code, raised.exception.detail))

    def test_invalid_inputs_do_not_reach_shell_or_echo_private_material(self) -> None:
        """非法地址、路径及私钥错误经过公开接口时保持固定错误。:return: None。"""
        for host in ('-oProxyCommand=bad', 'localhost\nother', '127.0.0.1;id', 'http://node', '[::1]'):
            with self.subTest(host=host), self.assertRaises(ValidationError):
                NodeAddress(host=host)
        self.assertEqual('::1', NodeAddress(host='::1').host)
        for data_root in ('/', '/srv', '/srv/../other', '/srv/test\nnode'):
            with self.subTest(data_root=data_root), self.assertRaises(ValidationError):
                NodeConfiguration(**{**self.config, 'data_root': data_root})
        app = FastAPI()
        app.include_router(cluster_router(lambda: self.service))
        with TestClient(app) as client:
            response = client.post('/api/nodes', json={**self.config, 'private_key': '秘密不应回显'})
            self.assertEqual(422, response.status_code)
            self.assertNotIn('秘密不应回显', response.text)

    def test_host_key_fingerprint_matches_openssh(self) -> None:
        """主机指纹与实际OpenSSH解析一致。:return: None。"""
        output = subprocess.run(['ssh-keygen', '-l', '-E', 'sha256', '-f', str(self.key.with_suffix('.pub'))],
            check=True, capture_output=True, text=True).stdout
        self.assertIn(host_key_identity(self.host_key)['sha256'], output)

    def test_corrupt_node_configuration_does_not_hide_other_nodes(self) -> None:
        """单个节点记录损坏时本机与其他节点仍能正常展示。:return: None。"""
        node = self.service.register(NodeCreate(**self.config, private_key=self.key.read_text()))
        connection = self.database()
        self.addCleanup(connection.close)
        with connection:
            connection.execute("UPDATE cluster_nodes SET config_json='broken' WHERE id=?", (node['id'],))
        rows = self.store.list()
        self.assertEqual('local', rows[0]['kind'])
        self.assertEqual('unreachable', rows[1]['observation']['state'])
        self.assertIn('损坏', rows[1]['observation']['reason'])

    def test_pausing_node_blocks_new_local_admission(self) -> None:
        """暂停本机节点后正式账号与新登录草稿都不能新准入。:return: None。"""
        connection = self.database()
        self.addCleanup(connection.close)
        with connection:
            account = connection.execute("INSERT INTO accounts(name,profile_path) VALUES('paused','profiles/paused')").lastrowid
        self.service.admit_local({'id': account})
        local = self.store.list()[0]
        self.store.set_enabled(local['id'], local['revision'], False)
        for payload in ({'id': account}, {'name': 'new-login'}):
            with self.subTest(account=payload), self.assertRaises(RuntimeBusy):
                self.service.admit_local(payload)

    def test_initial_assignment_persists_and_existing_environment_requires_migration(self) -> None:
        """首次选择未准备节点仍落库，已有资料沿原迁移和CAS边界。:return: None。"""
        node = self.service.register(NodeCreate(**self.config, private_key=self.key.read_text()))
        connection = self.database()
        self.addCleanup(connection.close)
        with connection:
            aid = connection.execute("INSERT INTO accounts(name,profile_path) VALUES('fresh','profiles/fresh')").lastrowid
            other = connection.execute("INSERT INTO accounts(name,profile_path) VALUES('existing','profiles/existing')").lastrowid
        with patch.dict('os.environ', {'V3_RELEASE': 'synthetic', 'V3_DEPLOYMENT_ID': 'synthetic',
                'V3_ACCOUNT_IMAGE': 'synthetic-account', 'V3_NETWORK': 'synthetic-network', 'V3_ACCOUNT_MEMORY': '4g'}):
            runtime = AccountRuntime(Mock(), self.root, self.root, self.database, derive_v3_fingerprint, Mock())
        self.addCleanup(runtime.heartbeat_pool.shutdown)
        account = {'id': aid, 'name': 'fresh'}
        result = self.service.assign_initial(account, runtime, node['id'], 1)
        self.assertEqual((node['id'], 2), (result['node_id'], result['revision']))
        self.assertEqual(result, ClusterStore(self.database, threading.Lock()).assignment(aid))
        with self.assertRaisesRegex(ValueError, '已变化'):
            self.service.assign_initial(account, runtime, node['id'], 1)
        row = runtime._row('existing', other)
        runtime._update(row, generation=1)
        with self.assertRaisesRegex(ValueError, '迁移'):
            self.service.assign_initial({'id': other, 'name': 'existing'}, runtime, node['id'], 1)
        self.assertEqual('local', self.store.assignment(other)['kind'])

    def test_pause_during_installation_requires_capability_recheck(self) -> None:
        """暂停不被迟到安装回执覆盖，安装中状态收口为待核对。:return: None。"""
        node = self.service.register(NodeCreate(**self.config, private_key=self.key.read_text()))
        self.store.save_preparation(node['id'], node['revision'], {'state': 'preparing'})
        updated = self.store.set_enabled(node['id'], node['revision'], False)
        self.assertEqual('needs_check', updated['preparation']['state'])
        self.assertFalse(self.store.save_preparation(node['id'], node['revision'], {'state': 'prepared'}))


if __name__ == '__main__':
    unittest.main()
