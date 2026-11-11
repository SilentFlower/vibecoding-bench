"""维护门禁跨重启、准入计数和未知状态的真实文件验证。"""
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from runtime_files import atomic_json
from system_update_gate import DeploymentGate


class UpdateGateTests(unittest.TestCase):
    """使用临时私有目录和真实线程验证准入边界。"""

    def setUp(self) -> None:
        """建立两份读取同一持久门禁的进程级对象。

        :return: None。
        """
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gate = DeploymentGate(self.root, 'test')
        self.value = {'schema_version': 1, 'deployment': 'test', 'operation_id': None,
            'epoch': str(uuid.uuid4()), 'phase': 'idle', 'target_release': None,
            'revision': str(uuid.uuid4()), 'created_at': '2026-11-11T00:00:00Z'}
        atomic_json(self.root / 'admission.json', self.value)

    def test_streaming_activity_survives_external_fence_and_rejects_new(self) -> None:
        """关闭准入后原活动仍计数，ACK 观察到确定的在途事实。

        :return: None。
        """
        entered, finish = threading.Event(), threading.Event()
        def work():
            with self.gate.admission('synthetic-stream'):
                entered.set()
                finish.wait(3)
        thread = threading.Thread(target=work)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.value.update(phase='blocked', operation_id=str(uuid.uuid4()), target_release='system-ci-1-1')
            atomic_json(self.root / 'admission.json', self.value)
            snapshot = self.gate.state()
            self.assertEqual(snapshot['active'], 1)
            self.assertEqual(snapshot['epoch'], self.value['epoch'])
            with self.assertRaises(RuntimeError):
                with self.gate.admission('late-request'):
                    self.fail('维护中不应执行新任务')
        finally:
            finish.set()
            thread.join(2)
        self.assertEqual(self.gate.state()['active'], 0)
        restored = DeploymentGate(self.root, 'test')
        with self.assertRaises(RuntimeError):
            with restored.admission('after-restart'):
                self.fail('重启不能放开维护门禁')

    def test_missing_corrupt_or_wrong_deployment_is_not_idle(self) -> None:
        """缺失、损坏和跨部署事实均进入对账。

        :return: None。
        """
        (self.root / 'admission.json').unlink()
        self.assertEqual(self.gate.state()['phase'], 'reconcile')
        (self.root / 'admission.json').write_text('{}')
        self.assertEqual(self.gate.state()['phase'], 'reconcile')
        self.value['deployment'] = 'other'
        atomic_json(self.root / 'admission.json', self.value)
        self.assertEqual(self.gate.state()['phase'], 'reconcile')

    def test_existing_job_continuation_is_revoked_after_release(self) -> None:
        """原作业后续请求可收口，撤销后迟到证明失效。@return None。"""
        identifier = self.gate.reserve('login:synthetic')
        self.value.update(phase='blocked', operation_id=str(uuid.uuid4()), target_release='system-ci-1-1')
        atomic_json(self.root / 'admission.json', self.value)
        with self.assertRaises(RuntimeError):
            self.gate.reserve('login:new')
        with self.gate.continue_reserved(identifier):
            proof = self.gate.proof()
            self.assertIsNotNone(proof)
            self.assertNotEqual(proof, identifier)
            self.gate.release_reserved(identifier)
            self.assertTrue(self.gate.continuing())
            self.assertEqual(self.gate.state()['active'], 1)
        self.assertEqual(self.gate.state()['active'], 0)
        with self.assertRaises(RuntimeError):
            with self.gate.continue_reserved(identifier):
                self.fail('迟到请求不应重开原作业')


if __name__ == '__main__':
    unittest.main()
