"""用实际 Scheduler、SQLite 和线程验证维护期间的批次与原项目续接。"""
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import main
import system_update_gate
import test_quota
from runtime_files import atomic_json
from system_update_gate import DeploymentGate


class UpdateSchedulingTests(unittest.TestCase):
    """有限执行参与排空，批次等待保持持久排队。"""

    def setUp(self) -> None:
        """复用正式数据库和离线运行器夹具，建立实际共享门禁。@return None。"""
        test_quota.QuotaGuardTests.setUp(self)
        self.gate_root = self.base / 'gate'
        self.gate_root.mkdir()
        self.gate = DeploymentGate(self.gate_root, 'test')
        self.value = {'schema_version': 1, 'deployment': 'test', 'phase': 'idle', 'operation_id': None,
            'epoch': str(uuid.uuid4()), 'revision': str(uuid.uuid4()), 'target_release': None,
            'created_at': '2026-11-11T00:00:00Z'}
        self.write_gate('idle')
        for module, name, value in ((main, 'UPDATE_GATE', self.gate),
                (system_update_gate, 'UPDATE_GATE', self.gate), (main, 'quota_guard', None)):
            replacement = patch.object(module, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        with main.get_db() as connection:
            connection.execute("INSERT INTO task_batches(id,account_id,name,status,concurrency,timeout_sec) VALUES(1,1,'合成批次','active',1,1800)")
            for _ in range(2):
                connection.execute("INSERT INTO task_batch_items(batch_id,topic_id,prompt,status) VALUES(1,1,'合成原任务','pending')")

    def write_gate(self, phase: str) -> None:
        """模拟宿主持久接管或开放。:param phase: 门禁阶段。@return None。"""
        self.value.update(phase=phase, operation_id=str(uuid.uuid4()) if phase == 'blocked' else None,
            target_release='system-ci-1-1' if phase == 'blocked' else None)
        atomic_json(self.gate_root / 'admission.json', self.value)

    def wait_for(self, predicate, message: str) -> None:
        """有界等候实际状态。:param predicate: 只读断言。:param message: 超时说明。@return None。"""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail(message)

    def test_batch_wait_does_not_hold_drain_after_original_run_finishes(self) -> None:
        """原执行收口后计数归零，第二项保留 pending 并在恢复后运行。@return None。"""
        first_started, first_finish, second_dispatch = threading.Event(), threading.Event(), threading.Event()
        original_create = self.scheduler._create_batch_task_and_run
        calls = []
        def create(*arguments):
            calls.append(arguments)
            if len(calls) == 2:
                second_dispatch.set()
            return original_create(*arguments)
        def wait_worker(_worker):
            if not first_started.is_set():
                first_started.set()
                first_finish.wait(5)
            return 0
        self.runner.wait_worker.side_effect = wait_worker
        thread = threading.Thread(target=self.scheduler._execute_batch, args=(1,))
        with patch.object(self.scheduler, '_create_batch_task_and_run', side_effect=create):
            thread.start()
            try:
                self.assertTrue(first_started.wait(3))
                self.write_gate('blocked')
                first_finish.set()
                self.assertTrue(second_dispatch.wait(4))
                self.wait_for(lambda: self.gate.state()['active'] == 0, '批次等待仍持有维护活动')
                self.assertEqual(self.runner.start_run.call_count, 1)
                with main.get_db() as connection:
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM task_batch_items WHERE status='pending'").fetchone()[0], 1)
                self.write_gate('idle')
                # 保留真实的两秒轮询，覆盖串行两项及并行构建时的调度延迟。
                thread.join(12)
                self.assertFalse(thread.is_alive())
                self.assertEqual(self.runner.start_run.call_count, 2)
                with main.get_db() as connection:
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs WHERE status='success'").fetchone()[0], 2)
            finally:
                first_finish.set()
                self.write_gate('idle')
                self.scheduler.stop_window_waits()
                thread.join(6)

    def test_gate_before_dispatch_keeps_original_items_without_activity(self) -> None:
        """批次启动后的准入竞争保留原项，维护期计数为零。@return None。"""
        before_dispatch = threading.Event()
        original_create = self.scheduler._create_batch_task_and_run
        def create(*arguments):
            if not before_dispatch.is_set():
                self.write_gate('blocked')
                before_dispatch.set()
            return original_create(*arguments)
        thread = threading.Thread(target=self.scheduler._execute_batch, args=(1,))
        with patch.object(self.scheduler, '_create_batch_task_and_run', side_effect=create):
            thread.start()
            try:
                self.assertTrue(before_dispatch.wait(3))
                self.assertEqual(self.gate.state()['active'], 0)
                self.runner.start_run.assert_not_called()
                with main.get_db() as connection:
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
                self.write_gate('idle')
                thread.join(12)
                self.assertFalse(thread.is_alive())
                self.assertEqual(self.runner.start_run.call_count, 2)
            finally:
                self.write_gate('idle')
                self.scheduler.stop_window_waits()
                thread.join(6)

    def test_original_project_can_finish_preparation_with_all_other_guards(self) -> None:
        """原有限调用链续接有效，时间窗仍能拒绝，迟到调用保持维护状态。@return None。"""
        with patch.object(main, '_account_run_window', return_value={'allowed': True}) as window:
            with self.gate.admission('scheduler:original-project'):
                self.write_gate('blocked')
                self.assertTrue(main._project_admission(self.account, 'original'))
                window.return_value = {'allowed': False}
                self.assertFalse(main._project_admission(self.account, 'original'))
            window.return_value = {'allowed': True}
            self.assertFalse(main._project_admission(self.account, 'original'))

    def test_control_restart_preserves_batch_items_waiting_at_maintenance(self) -> None:
        """旧调度器停止后保留 pending，新调度器按原批次继续。@return None。"""
        waiting = threading.Event()
        original_create = self.scheduler._create_batch_task_and_run
        def create(*arguments):
            waiting.set()
            return original_create(*arguments)
        self.write_gate('blocked')
        thread = threading.Thread(target=self.scheduler._execute_batch, args=(1,))
        with patch.object(self.scheduler, '_create_batch_task_and_run', side_effect=create):
            thread.start()
            try:
                self.assertTrue(waiting.wait(3))
                self.assertEqual(self.gate.state()['active'], 0)
                self.scheduler.stop_window_waits()
                thread.join(3)
                self.assertFalse(thread.is_alive())
                self.runner.start_run.assert_not_called()
                with main.get_db() as connection:
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM task_batch_items WHERE status='pending'").fetchone()[0], 2)
                self.write_gate('idle')
                replacement = main.Scheduler(self.runner)
                replacement._execute_batch(1)
                self.assertEqual(self.runner.start_run.call_count, 2)
            finally:
                self.scheduler.stop_window_waits()
                self.write_gate('idle')
                thread.join(3)

    def test_original_project_continuation_preserves_passive_quota_rejection(self) -> None:
        """原有限活动仍按实际额度拒绝，续接证明只解决部署维护准入。@return None。"""
        test_quota.QuotaGuardTests._run(self)
        with patch.object(main, 'quota_guard', self.guard), patch.object(main, '_account_run_window', return_value={'allowed': True}):
            with self.gate.admission('scheduler:original-project'):
                self.write_gate('blocked')
                self.assertTrue(main._project_admission(self.account, 'original'))
                test_quota.QuotaGuardTests._state(self, test_quota.quota_headers(time.time(), five=600, rejected=True))
                self.assertFalse(main._project_admission(self.account, 'original'))
                self.runner.start_run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
