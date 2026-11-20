"""更新页的只读查询与维护快照并行时，仍需取得一致生命周期证明。"""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from system_updates import runtime_snapshot


class SnapshotLockTests(unittest.TestCase):
    """区分短暂只读占锁和持续生命周期占锁，避免更新页轮询触发错误恢复。"""

    def setUp(self) -> None:
        """建立真实数据库与生命周期锁。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        database = self.root / 'bench.sqlite'
        with sqlite3.connect(database) as connection:
            connection.executescript('CREATE TABLE accounts(id INTEGER,cc2api_account_id INTEGER);'
                'CREATE TABLE account_environments(environment_id TEXT,generation INTEGER,state TEXT,name TEXT,account_id INTEGER,'
                'container_id TEXT,sender_container_id TEXT,network_container_id TEXT);'
                "INSERT INTO account_environments VALUES('synthetic',7,'stopped','synthetic',NULL,NULL,NULL,NULL);")

        def connect():
            """返回独立只读连接。@return SQLite 连接。"""
            connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
            connection.row_factory = sqlite3.Row
            return connection

        self.guard = threading.RLock()
        self.release = threading.Event()
        self.started = threading.Event()
        self.runtime = SimpleNamespace(database=connect, environment_lock=lambda identifier: self.guard,
            environment_jobs=lambda identifier: [], _execution_records=lambda row: [], _root=lambda row: self.root)
        gate = patch('system_updates.UPDATE_GATE', SimpleNamespace(state=lambda: {'phase': 'blocked', 'active': 0}))
        pending = patch('system_updates.pending_upgrade', return_value=None)
        gate.start(); pending.start()
        self.addCleanup(gate.stop); self.addCleanup(pending.stop)

    def hold(self) -> threading.Thread:
        """在独立线程持有生命周期锁。@return 已取得锁的线程。"""
        def owner():
            """保留一次真实占锁，等待测试收口。@return None。"""
            with self.guard:
                self.started.set()
                self.release.wait(3)
        thread = threading.Thread(target=owner)
        thread.start()
        self.assertTrue(self.started.wait(1))
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.release.set)
        return thread

    def test_unconnected_remote_environment_keeps_explicit_blocker_without_local_docker_access(self) -> None:
        """节点维护尚未接入时保留明确阻塞，避免检查本机同名容器。:return: None。"""
        self.runtime.locality=lambda row:False
        self.runtime._root=lambda row:self.fail('远程环境不能读取中央HOME')
        snapshot=runtime_snapshot(self.runtime)
        self.assertFalse(snapshot['ready'])
        self.assertIn('节点工作、连接或同步状态仍需核对',snapshot['blockers'][0])
        self.assertEqual('ssh',snapshot['environments'][0]['node_kind'])

    def test_short_read_only_lock_releases_before_snapshot_verification(self) -> None:
        """更新页短暂占锁结束后核验快照，保持排空成功。@return None。"""
        self.hold()
        timer = threading.Timer(0.05, self.release.set)
        timer.start()
        self.addCleanup(timer.join, 1)
        self.assertTrue(runtime_snapshot(self.runtime)['ready'])

    def test_persistent_lifecycle_lock_keeps_maintenance_blocked(self) -> None:
        """持续占锁仍返回阻塞，保留原维护安全边界。@return None。"""
        self.hold()
        snapshot = runtime_snapshot(self.runtime)
        self.assertFalse(snapshot['ready'])
        self.assertTrue(snapshot['blockers'])

    def test_connected_remote_snapshot_uses_node_evidence(self) -> None:
        """已接入节点维护后，原平台快照消费远程真实事实。:return: None。"""
        self.runtime.locality = lambda row: False
        self.runtime._root = lambda row: self.fail('远程环境保持在原节点')
        connection = sqlite3.connect(self.root / 'bench.sqlite')
        try:
            with connection:
                connection.execute('INSERT INTO accounts VALUES(1,NULL)')
                connection.execute('UPDATE account_environments SET account_id=1')
        finally:
            connection.close()
        synchronization = Mock()
        synchronization.environment_snapshot.return_value = {'environment_id': 'synthetic', 'node_kind': 'ssh',
            'generation': 7, 'roles': {}, 'blockers': []}
        store = Mock()
        store.list.return_value = [{'kind': 'ssh', 'id': 2, 'preparation': {'release': 'synthetic'}}]
        store.removed_draft_environments.return_value = set()
        self.runtime.cluster_service = SimpleNamespace(synchronization=synchronization, store=store)
        snapshot = runtime_snapshot(self.runtime)
        self.assertTrue(snapshot['ready'])
        self.assertEqual(7, snapshot['environments'][0]['generation'])
        self.assertEqual(2, snapshot['nodes'][0]['id'])
        synchronization.environment_snapshot.assert_called_once()

    def test_central_snapshot_uses_persisted_remote_ownership_without_connecting(self) -> None:
        """失联节点只能凭已知归属从中央切换范围移出。@return 无。"""
        self.runtime.locality = lambda row: False
        self.runtime._root = lambda row: self.fail('中央不能对远程环境执行本机维护')
        store = Mock()
        store.list.return_value = [{'kind': 'ssh', 'id': 2, 'name': 'main', 'preparation': {'release': 'old'}}]
        store.removed_draft_environments.return_value = set()
        synchronization = Mock()
        service = self.runtime.cluster_service = SimpleNamespace(synchronization=synchronization, store=store,
            draft_node=Mock(return_value={'kind': 'ssh', 'node_id': 2}))
        snapshot = runtime_snapshot(self.runtime, central_only=True)
        self.assertTrue(snapshot['ready'])
        self.assertEqual(snapshot['scope'], 'central')
        self.assertEqual(snapshot['environments'], [])
        self.assertEqual(snapshot['nodes'][0]['id'], 2)
        synchronization.environment_snapshot.assert_not_called()

        service.draft_node.side_effect = ValueError('冻结归属损坏')
        snapshot = runtime_snapshot(self.runtime, central_only=True)
        self.assertFalse(snapshot['ready'])
        self.assertIn('环境归属待核对', snapshot['blockers'][0])

    def test_pending_removal_blocks_upgrade_and_rollback_before_node_capture(self) -> None:
        """旧版切换用同一排空门禁，未收口移除不会进入待备份节点集合。:return: 无。"""
        store = Mock()
        store.removed_draft_environments.return_value = set()
        node = {'kind': 'ssh', 'id': 2, 'name': '隔离节点', 'preparation': {'release': 'synthetic'}}
        self.runtime.cluster_service = SimpleNamespace(store=store)
        for state, action in [('removing', '等待原操作完成'), ('needs_check', '重试移除')]:
            store.list.return_value = [{**node, 'removal': {'state': state}}]
            snapshot = runtime_snapshot(self.runtime)
            self.assertFalse(snapshot['ready'])
            self.assertEqual([], snapshot['nodes'])
            self.assertIn(action, snapshot['blockers'][0])
            self.assertEqual([{'name': node['name'], 'state': state}], snapshot['node_removals'])
        store.list.return_value = []
        self.assertTrue(runtime_snapshot(self.runtime)['ready'])

    def test_archived_closed_draft_keeps_history_without_node_probe(self) -> None:
        """归档回执已确认原草稿清理，平台沿中央历史完成快照。:return: 无。"""
        self.runtime.locality = Mock(side_effect=AssertionError('归档后的草稿无需执行归属检查'))
        store = Mock()
        store.removed_draft_environments.return_value = {'synthetic'}
        store.list.return_value = []
        self.runtime.cluster_service = SimpleNamespace(store=store)
        snapshot = runtime_snapshot(self.runtime)
        self.assertTrue(snapshot['ready'])
        self.assertEqual(('synthetic', 'ssh', {}), tuple(snapshot['environments'][0][key] for key in ('environment_id', 'node_kind', 'roles')))
