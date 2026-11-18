"""历史账号环境的维护归属与新工作准入保持独立核验。"""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cluster_service import ClusterService
from cluster_store import ClusterStore
from database_migrations import apply_migrations
from runtime_files import atomic_json
from system_updates import runtime_snapshot


class HistoricalLocalityTests(unittest.TestCase):
    """使用真实迁移、存储和维护快照复现历史环境升级。"""

    def setUp(self) -> None:
        """建立完整集群库和独立维护环境。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'bench.sqlite'
        connection = self.database()
        try:
            apply_migrations(connection)
        finally:
            connection.close()
        self.store = ClusterStore(self.database, threading.Lock())
        self.service = ClusterService(self.store, self.root, Mock(), self.root / 'transport')
        self.addCleanup(self.service.close)
        self.runtime = SimpleNamespace(database=self.database, locality=self.service.owns_local,
            environment_lock=lambda identifier: threading.RLock(), environment_jobs=lambda identifier: [],
            _execution_records=lambda row: [], _root=lambda row: self.root / 'environments' / row['environment_id'])
        gate = patch('system_updates.UPDATE_GATE.state', return_value={'phase': 'blocked', 'active': 0})
        gate.start()
        self.addCleanup(gate.stop)

    def database(self):
        """提供独立 SQLite Row 连接。:return: 调用方负责关闭的连接。"""
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def environment(self, *, deleted: bool = False, orphan: bool = False) -> dict:
        """创建一条合成历史环境。

        :param deleted: 保留软删除账号及其真实默认分配。
        :param orphan: 模拟集群之前账号已物理删除的空环境。
        :return: 已提交的环境行。
        """
        connection = self.database()
        try:
            with connection:
                if not orphan:
                    connection.execute("INSERT INTO accounts(id,name,profile_path,deleted_at) VALUES(9,'synthetic','profiles/synthetic',?)",
                        (1 if deleted else None,))
                connection.execute("INSERT INTO account_environments(environment_id,account_id,name,fingerprint_json,state) "
                    "VALUES(?,9,'synthetic','{}','stopped')", ('e' * 32,))
            return dict(connection.execute('SELECT * FROM account_environments').fetchone())
        finally:
            connection.close()

    def test_deleted_local_environment_is_verified_without_admitting_new_work(self) -> None:
        """软删除环境仍按真实本机分配核验，业务准入继续拒绝已删除账号。:return: None。"""
        row = self.environment(deleted=True)
        self.assertTrue(self.service.owns_local(row))
        self.assertTrue(runtime_snapshot(self.runtime)['ready'])
        with self.assertRaisesRegex(ValueError, '账号节点归属缺失'):
            self.service.admit_local({'id': 9})

    def test_legacy_orphan_without_roles_or_node_history_keeps_stopped_state(self) -> None:
        """集群前的孤立空环境完成只读维护核验，历史登记保持原状态。:return: None。"""
        row = self.environment(orphan=True)
        self.assertTrue(self.service.owns_local(row))
        snapshot = runtime_snapshot(self.runtime)
        self.assertTrue(snapshot['ready'])
        self.assertEqual('stopped', snapshot['environments'][0]['state'])
        connection = self.database()
        try:
            self.assertEqual(0, connection.execute('SELECT COUNT(*) FROM accounts').fetchone()[0])
            self.assertEqual(0, connection.execute('SELECT COUNT(*) FROM account_node_assignments').fetchone()[0])
        finally:
            connection.close()

    def test_deleted_local_environment_with_stopped_roles_keeps_role_verification(self) -> None:
        """软删除环境遗留的三角色继续逐项核验，保持原停止状态。:return: None。"""
        row = self.environment(deleted=True)
        connection = self.database()
        try:
            with connection:
                connection.execute("UPDATE account_environments SET container_id='cli',sender_container_id='sender',network_container_id='network'")
        finally:
            connection.close()
        containers = {role: SimpleNamespace(id=role, status='exited', attrs={'Image': 'synthetic-image'}, reload=Mock())
            for role in ('cli', 'sender', 'network')}
        self.runtime._running_sender_active = Mock(return_value=False)
        with patch('system_updates.role_container', side_effect=lambda runtime, row, role: containers[role]) as lookup, \
                patch('system_updates.image_origin', return_value={'release': 'ci-synthetic-1'}):
            snapshot = runtime_snapshot(self.runtime)
        self.assertTrue(snapshot['ready'])
        self.assertEqual(3, lookup.call_count)
        self.assertEqual({'exited'}, {role['state'] for role in snapshot['environments'][0]['roles'].values()})
        self.runtime._running_sender_active.assert_called_once()

    def test_existing_account_with_missing_assignment_remains_blocked(self) -> None:
        """有效账号丢失分配时保持阻断，停止状态不能代替归属证明。:return: None。"""
        row = self.environment()
        connection = self.database()
        try:
            with connection:
                connection.execute('DELETE FROM account_node_assignments WHERE account_id=9')
        finally:
            connection.close()
        self.assertFalse(self.service.owns_local(row))

    def test_deleted_remote_assignment_and_deleted_node_remain_blocked(self) -> None:
        """软删除远程账号及损坏的节点登记继续阻断本机维护。:return: None。"""
        row = self.environment(deleted=True)
        connection = self.database()
        try:
            with connection:
                connection.execute("INSERT INTO cluster_nodes(node_key,name,kind,config_json,created_at) VALUES(?,'synthetic-node','ssh','{}',0)",
                    ('b' * 32,))
                connection.execute('UPDATE account_node_assignments SET node_id=2 WHERE account_id=9')
            self.assertFalse(self.service.owns_local(row))
            with connection:
                connection.execute('UPDATE account_node_assignments SET node_id=1 WHERE account_id=9')
                connection.execute("UPDATE cluster_nodes SET deleted_at=1 WHERE node_key='local'")
            self.assertFalse(self.service.owns_local(row))
        finally:
            connection.close()

    def test_orphan_with_live_state_or_registered_role_remains_blocked(self) -> None:
        """孤立环境仍有角色或未停止时拒绝本机兼容路径。:return: None。"""
        row = self.environment(orphan=True)
        connection = self.database()
        try:
            for state in ('ready', 'reconcile'):
                with connection:
                    connection.execute('UPDATE account_environments SET state=?', (state,))
                with self.subTest(state=state):
                    self.assertFalse(self.service.owns_local(row))
            with connection:
                connection.execute("UPDATE account_environments SET state='stopped',container_id='unknown-role'")
            self.assertFalse(self.service.owns_local(row))
        finally:
            connection.close()

    def test_orphan_with_cluster_marker_or_link_remains_blocked(self) -> None:
        """原节点标记及断开的链接保留归属未知事实。:return: None。"""
        row = self.environment(orphan=True)
        runtime = self.root / 'environments' / row['environment_id'] / 'runtime'
        runtime.mkdir(parents=True)
        for name in ('node-assignment.json', 'node-fence.json', 'node-migration-target.json'):
            marker = runtime / name
            marker.symlink_to('missing-synthetic-marker')
            with self.subTest(name=name):
                self.assertFalse(self.service.owns_local(row))
            marker.unlink()

    def test_orphan_with_node_history_remains_blocked(self) -> None:
        """节点执行、迁移或登录历史均阻挡孤立环境的本机兼容路径。:return: None。"""
        row = self.environment(orphan=True)
        statements = {
            'node_executions': ("INSERT INTO node_executions(operation_id,account_id,node_id,environment_id,assignment_revision,"
                "environment_generation,source,role,phase,record_json,created_at,updated_at) VALUES(?,9,1,?,1,0,'synthetic','cli','closed','{}',0,0)",
                ('a' * 32, row['environment_id'])),
            'node_migrations': ("INSERT INTO node_migrations VALUES(?,9,1,1,'completed','{}',0,0)", ('a' * 32,)),
            'node_login_drafts': ("INSERT INTO node_login_drafts(environment_id,node_id,operation_id,sid,generation,phase,record_json,created_at,updated_at) "
                "VALUES(?,1,?,?,?,?, '{}',0,0)", (row['environment_id'], 'a' * 32, 'c' * 12, 'd' * 32, 'closed')),
        }
        connection = self.database()
        try:
            for table, (statement, values) in statements.items():
                with connection:
                    connection.execute(statement, values)
                with self.subTest(table=table):
                    self.assertFalse(self.service.owns_local(row))
                with connection:
                    connection.execute('DELETE FROM ' + table)
        finally:
            connection.close()

    def test_deleted_local_environment_keeps_execution_blocker(self) -> None:
        """历史本机环境仍核验持久活动，归属修复继续保留排空保护。:return: None。"""
        row = self.environment(deleted=True)
        atomic_json(self.root / 'environments' / row['environment_id'] / 'runtime/execution.json', {'synthetic': True})
        snapshot = runtime_snapshot(self.runtime)
        self.assertFalse(snapshot['ready'])
        self.assertIn('持久执行登记尚未收口', snapshot['blockers'][0])
