"""节点登记、版本竞争、默认归属和私钥公开边界的真实存储测试。"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from cluster_api import cluster_router
from cluster_nodes import NodeAddress, NodeConfiguration, NodeCreate, host_key_identity
from cluster_service import ClusterService
from cluster_store import ClusterStore
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

    def test_missing_registered_cluster_structure_is_rejected(self) -> None:
        """已登记库损坏时拒绝伪装成功。:return: None。"""
        connection = self.database()
        self.addCleanup(connection.close)
        connection.execute('DROP TRIGGER cluster_assign_new_account')
        with self.assertRaisesRegex(ValueError, '节点迁移'):
            migration_plan(connection)

    def test_registration_keeps_private_key_out_of_database_and_responses(self) -> None:
        """只写密钥进入0700/0600私有文件，公开及数据库保持脱敏。:return: None。"""
        request = NodeCreate(**self.config, private_key=self.key.read_text())
        result = self.service.register(request)
        serialized = json.dumps(result) + json.dumps(self.store.list())
        self.assertNotIn('PRIVATE KEY', serialized)
        self.assertNotIn('private_key', serialized)
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
            account = connection.execute("INSERT INTO accounts(name,profile_path) VALUES('linked','profiles/linked')").lastrowid
            connection.execute('UPDATE account_node_assignments SET node_id=? WHERE account_id=?', (node['id'], account))
        self.assertEqual(node['id'], self.store.assignment(account)['node_id'])
        with self.assertRaisesRegex(ValueError, '关联账号'):
            self.service.remove(node['id'], node['revision'])
        local = self.store.list()[0]
        with self.assertRaisesRegex(ValueError, '本机'):
            self.service.remove(local['id'], local['revision'])

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
        with self.assertRaisesRegex(ValueError, '执行记录'):
            self.service.remove(node['id'], node['revision'])

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
        """首次分配落库并校验CAS，已有代次拒绝直接换节点。:return: None。"""
        node = self.service.register(NodeCreate(**self.config, private_key=self.key.read_text()))
        self.store.save_preparation(node['id'], node['revision'], {'state': 'prepared', 'release': 'synthetic', 'protocol': 1})
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
