"""维护门禁跨重启、准入计数和未知状态的真实文件验证。"""
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from runtime_files import atomic_json
from system_update_gate import DeploymentGate, NodeImageFetchPaused


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

    def test_restored_persistent_job_counts_during_maintenance_without_new_admission(self) -> None:
        """恢复旧占用只增加排空事实，新作业与调用链继续遵守原维护门禁。:return: None。"""
        self.value.update(phase='blocked', operation_id=str(uuid.uuid4()), target_release='system-ci-1-1')
        atomic_json(self.root / 'admission.json', self.value)
        identifier = self.gate.restore_reserved('remote-cli:original-operation')
        self.assertEqual(1, self.gate.state()['active'])
        self.assertFalse(self.gate.continuing())
        with self.assertRaises(RuntimeError):
            self.gate.reserve('remote-cli:new-operation')
        with self.assertRaises(RuntimeError):
            with self.gate.admission('new-request'):
                self.fail('恢复旧作业不能开放维护期准入')
        self.gate.release_reserved(identifier)
        self.assertEqual(0, self.gate.state()['active'])

    def test_node_image_fetch_does_not_hold_central_cutover(self) -> None:
        """镜像传输独立执行，中央切换后作业不会开始换版写入。@return 无。"""
        identifier = self.gate.reserve('cluster-node-install:2')
        try:
            with self.gate.continue_reserved(identifier):
                self.assertEqual(self.gate.state()['central_active'], 2)
                with self.assertRaises(NodeImageFetchPaused):
                    with self.gate.node_image_fetch(identifier):
                        report = self.gate.state()
                        self.assertEqual(report['active'], 2)
                        self.assertEqual(report['central_active'], 0)
                        self.value.update(phase='blocked', operation_id=str(uuid.uuid4()), target_release='system-ci-1-1')
                        atomic_json(self.root / 'admission.json', self.value)
                self.assertEqual(self.gate.state()['central_active'], 2)
        finally:
            self.gate.release_reserved(identifier)
        self.assertEqual(self.gate.state()['central_active'], 0)

    def test_control_cutover_distinguishes_node_stream_from_central_work(self) -> None:
        """节点流只读取中央归属，中央实际写入仍由门禁收口。@return 无。"""
        stream = self.gate.reserve('node-stream:synthetic')
        with self.gate.admission('job:local-system-rollout'):
            status = self.gate.state()
            self.assertEqual(2, status['central_active'])
            self.assertEqual(1, status['control_active'])
        self.assertEqual(0, self.gate.state()['control_active'])
        self.gate.release_reserved(stream)

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

    def test_node_maintenance_is_bound_to_exact_original_operation_and_epoch(self) -> None:
        """内部节点工作仅沿原维护授权，普通准入仍遵守原门禁。:return: None。"""
        operation = str(uuid.uuid4())
        self.value.update(phase='blocked', operation_id=operation, target_release='system-ci-1-1')
        atomic_json(self.root / 'admission.json', self.value)
        with self.assertRaises(RuntimeError):
            self.gate.reserve_maintenance('cluster-node', str(uuid.uuid4()), self.value['epoch'])
        with self.assertRaises(RuntimeError):
            self.gate.reserve_maintenance('cluster-node', operation, str(uuid.uuid4()))
        proof = self.gate.reserve_maintenance('cluster-node', operation, self.value['epoch'])
        self.assertEqual(1, self.gate.state()['active'])
        with self.assertRaises(RuntimeError):
            self.gate.reserve('ordinary-request')
        with self.gate.continue_reserved(proof):
            self.assertTrue(self.gate.continuing())
        self.gate.release_reserved(proof)
        self.assertEqual(0, self.gate.state()['active'])


if __name__ == '__main__':
    unittest.main()
