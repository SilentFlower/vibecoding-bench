"""在实际ASGI路由验证AGY内部鉴权、准入与脱敏响应，原生调用使用替身。"""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import main


class AgyAuthApiTests(unittest.TestCase):
    """保持既有服务鉴权与错误反馈合同。"""

    def test_cleanup_loop_runs_before_wait_and_cancels_cleanly(self):
        """重启首轮立即核对原操作，关闭沿原异步生命周期取消。@return 无。"""
        manager=Mock()
        with patch.object(main,'_agy_auth_manager',manager), patch('main.asyncio.sleep',AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError): asyncio.run(main._agy_auth_cleanup_loop())
        manager.cleanup.assert_called_once()

    def test_service_auth_and_fixed_errors_do_not_echo_private_input(self):
        """错误只返回固定文本，正确服务证明才进入驱动。@return 无。"""
        secret='synthetic-agy-service-token-'*2
        manager=Mock()
        manager.handle.return_value={'phase':'ready'}

        async def run():
            """执行实际中间件及内部路由。@return 无。"""
            transport=httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport,base_url='http://synthetic.test') as client:
                path='/internal/v3/agy-auth/exchange'
                response=await client.post(path,json={'code':'synthetic-private-code'})
                self.assertEqual(response.status_code,401)
                manager.handle.assert_not_called()
                headers={'Authorization':'Bearer '+secret}
                response=await client.post(path,headers=headers,json={'session_id':'a'*32,'code':'synthetic-private-code'})
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json(),{'phase':'ready'})
                manager.handle.side_effect=ValueError('synthetic-private-code')
                response=await client.post(path,headers=headers,json={'session_id':'a'*32,'code':'synthetic-private-code'})
                self.assertEqual(response.status_code,503)
                self.assertNotIn('synthetic-private-code',response.text)
                response=await client.post(path,headers=headers,content=b'{"code":"synthetic-private-code"')
                self.assertEqual(response.status_code,503)
                self.assertNotIn('synthetic-private-code',response.text)

        with patch.dict(os.environ,{'V3_INTERNAL_TOKEN':secret}), patch.multiple(main,V3_ENABLED=True,
                account_runtime=SimpleNamespace(),_agy_auth_manager=manager):
            asyncio.run(run())


if __name__=='__main__':
    unittest.main()
