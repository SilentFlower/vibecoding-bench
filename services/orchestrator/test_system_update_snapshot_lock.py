"""更新页的只读查询与维护快照并行时，仍需取得一致生命周期证明。"""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
