"""真实 ASGI 响应生命周期与维护期原登录续接验证。"""
import asyncio
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from runtime_files import atomic_json
from system_update_gate import DeploymentGate
from system_updates import SystemUpdateAdmissionMiddleware, UpdateRequest


class UpdateRequestTests(unittest.TestCase):
    """验证新操作默认期限与显式期限的严格类型合同。"""

    def test_default_minute_preserves_explicit_and_rejects_non_integer(self) -> None:
        """缺省一分钟，显式期限保持，布尔和字符串继续拒绝。@return None。"""
        fields = {'operation_id': str(uuid.uuid4()), 'expected_revision': str(uuid.uuid4()),
            'target_release': 'system-ci-1-1', 'target_manifest_sha256': 'a' * 64}
        self.assertEqual(UpdateRequest(**fields).drain_timeout_seconds, 60)
        self.assertEqual(UpdateRequest(**fields, drain_timeout_seconds=1800).drain_timeout_seconds, 1800)
        for value in (True, '60', 60.5):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                UpdateRequest(**fields, drain_timeout_seconds=value)


class UpdateAdmissionTests(unittest.IsolatedAsyncioTestCase):
    """使用真实任务及正文发送验证准入释放边界。"""

    def setUp(self) -> None:
        """准备共享文件与真实作业登记。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gate = DeploymentGate(self.root, 'test')
        self.record = {'schema_version': 1, 'deployment': 'test', 'operation_id': None,
            'epoch': str(uuid.uuid4()), 'phase': 'idle', 'target_release': None,
            'revision': str(uuid.uuid4()), 'created_at': '2026-11-11T00:00:00Z'}
        atomic_json(self.root / 'admission.json', self.record)
        self.runtime = SimpleNamespace(lock=threading.RLock(), jobs={})
        environment = patch.dict('os.environ', {'V3_UPDATE_GATE_DIR': str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        replacement = patch('system_updates.UPDATE_GATE', self.gate)
        replacement.start()
        self.addCleanup(replacement.stop)

    def block(self) -> None:
        """模拟宿主发布维护门禁。@return None。"""
        self.record.update(phase='blocked', operation_id=str(uuid.uuid4()), target_release='system-ci-1-1')
        atomic_json(self.root / 'admission.json', self.record)

    async def test_stream_body_and_disconnect_release_actual_activity(self) -> None:
        """头部及首块正文完成后仍有活动，断连 finally 精确释放。@return None。"""
        started, finish = asyncio.Event(), asyncio.Event()
        messages = []
        async def send(message):
            messages.append(message)
        async def app(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'first', 'more_body': True})
            started.set()
            await finish.wait()
            self.assertIsNotNone(self.gate.proof())
            await send({'type': 'http.response.body', 'body': b'last'})
        middleware = SystemUpdateAdmissionMiddleware(app, lambda: self.runtime)
        task = asyncio.create_task(middleware({'type': 'http', 'method': 'POST', 'path': '/api/test'}, None, send))
        await asyncio.wait_for(started.wait(), 1)
        self.block()
        self.assertEqual(self.gate.state()['active'], 1)
        await middleware({'type': 'http', 'method': 'POST', 'path': '/api/new'}, None, send)
        self.assertEqual(messages[-2]['status'], 503)
        finish.set()
        await task
        self.assertEqual(self.gate.state()['active'], 0)
        self.assertEqual(messages[-1]['body'], b'last')
        self.record.update(phase='idle', operation_id=None, target_release=None)
        atomic_json(self.root / 'admission.json', self.record)
        started.clear()
        finish.clear()
        task = asyncio.create_task(middleware({'type': 'http', 'method': 'POST', 'path': '/api/test'}, None, send))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.gate.state()['active'], 0)

    async def test_original_login_can_finish_and_late_confirmation_is_rejected(self) -> None:
        """只允许真实原作业收口，完成后的旧登录路径被维护门禁拒绝。@return None。"""
        identifier = self.gate.reserve('login:abcdef123456')
        self.runtime.jobs['original'] = {'source': 'login:abcdef123456', 'update_activity_id': identifier}
        self.block()
        messages = []
        async def send(message):
            messages.append(message)
        async def app(scope, receive, send):
            self.assertTrue(self.gate.continuing())
            self.runtime.jobs.clear()
            self.gate.release_reserved(identifier)
            self.assertEqual(self.gate.state()['active'], 1)
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'committed'})
        middleware = SystemUpdateAdmissionMiddleware(app, lambda: self.runtime)
        scope = {'type': 'http', 'method': 'POST', 'path': '/api/accounts/login/abcdef123456/commit'}
        await middleware(scope, None, send)
        self.assertEqual(messages[0]['status'], 200)
        self.assertEqual(self.gate.state()['active'], 0)
        await middleware(scope, None, send)
        self.assertEqual(messages[-2]['status'], 503)


if __name__ == '__main__':
    unittest.main()
