"""退役内核入口保持鉴权且无下载、切换与租约副作用。"""
import unittest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
import main


class RetiredKernelApiTests(unittest.TestCase):
    """通过实际鉴权中间件验证旧调用的明确结果。"""

    def test_authenticated_get_and_operations_return_gone(self):
        """旧合法请求已鉴权410，匿名沿原会话门禁拒绝。@return None。"""
        runtime = Mock()
        with patch.multiple(main, account_runtime=runtime, V3_ENABLED=False, _AUTH_ENABLED=True,
                WEBUI_USER='fixture', WEBUI_PASS='fixture'), patch.dict('os.environ', {'V3_UPDATE_GATE_DIR': ''}), \
                patch('urllib.request.urlopen', side_effect=AssertionError('禁止下载')):
            client = TestClient(main.app)
            path = '/api/environments/' + 'a' * 32 + '/native-kernel'
            body = {'operation': 'prepare', 'operation_id': 'synthetic', 'expected_revision': '3:initial'}
            self.assertEqual(client.get(path + '/releases').status_code, 401)
            self.assertEqual(client.post(path, json=body).status_code, 401)
            client.cookies.set(main._SESSION_COOKIE, main._make_session_token('fixture'))
            self.assertEqual(client.get(path + '/releases?refresh=true').status_code, 410)
            for version in ('2.1.280','2.1.293'):
                for operation in ('prepare','activate','rollback','recover'):
                    response = client.post(path, json={**body, 'source_version': version, 'operation': operation})
                    self.assertEqual(response.status_code, 410, response.text)
                    self.assertIn('平台版本统一管理', response.text)
            self.assertEqual(client.get(path + '/releases?source_version=obsolete').status_code, 410)
            self.assertEqual(client.post(path, json={'obsolete_payload': True}).status_code, 410)
            self.assertEqual(runtime.mock_calls, [])
