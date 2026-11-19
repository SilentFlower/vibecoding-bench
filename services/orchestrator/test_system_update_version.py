"""验证运行时版本读取、严格文件边界及原内部服务鉴权。"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI

import system_updates


class PlatformVersionTests(unittest.TestCase):
    """使用真实ASGI路由和独立文件，版本读取无需宿主或账号运行时。"""

    def setUp(self) -> None:
        """准备固定版本文件和真实管理路由。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.file = self.root / 'platform-version.json'
        replacement = patch.object(system_updates, '_PLATFORM_VERSION_FILE', self.file)
        replacement.start()
        self.addCleanup(replacement.stop)
        self.provider = Mock(side_effect=AssertionError('版本读取不调用账号运行时'))
        self.app = FastAPI()
        self.app.include_router(system_updates.system_updates_router(self.provider))

    def request(self, *, app=None, headers=None, method='GET') -> tuple:
        """沿实际ASGI协议读取版本。

        :param app: 可选带正式鉴权中间件的应用。
        :param headers: 合成请求头。
        :param method: 待验证HTTP方法。
        :return: 状态、响应头及JSON对象。
        """
        async def execute():
            """提供一次空请求正文并收集真实响应。:return: 响应数据。"""
            messages = []
            sent = False

            async def receive():
                """正文只提交一次，后续等待由响应生命周期取消。:return: 请求消息。"""
                nonlocal sent
                if not sent:
                    sent = True
                    return {'type': 'http.request', 'body': b'', 'more_body': False}
                await asyncio.Event().wait()

            async def send(message):
                """收集响应。:param message: ASGI消息。:return: None。"""
                messages.append(message)

            path = '/api/system-updates/version'
            scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
                'http_version': '1.1', 'scheme': 'http', 'method': method, 'path': path,
                'raw_path': path.encode(), 'query_string': b'', 'root_path': '',
                'server': ('synthetic.test', 80), 'client': ('test', 1),
                'headers': [(key.encode(), value.encode()) for key, value in (headers or {}).items()]}
            await (app or self.app)(scope, receive, send)
            response = next(message for message in messages if message['type'] == 'http.response.start')
            body = b''.join(message.get('body', b'') for message in messages if message['type'] == 'http.response.body')
            return response['status'], dict(response['headers']), json.loads(body)

        return asyncio.run(execute())

    def test_version_is_current_image_data_and_independent_of_updater(self) -> None:
        """当前文件改变即时反映，缺少宿主底座时仍读取版本并禁用响应缓存。:return: None。"""
        with patch.dict(os.environ, {}, clear=False), patch.object(system_updates, 'updater_request') as updater:
            for version in ('v0.0.0', 'v1.17.2', 'v1.17.3'):
                self.file.write_text(json.dumps({'version': version}))
                status, headers, body = self.request()
                self.assertEqual(status, 200)
                self.assertEqual(headers[b'cache-control'], b'no-store')
                self.assertEqual(body, {'version': version})
            updater.assert_not_called()
        self.provider.assert_not_called()

    def test_missing_and_malformed_metadata_return_only_unknown_version(self) -> None:
        """坏JSON、类型、重复或额外字段及越界内容不能伪装成当前版本。:return: None。"""
        self.assertEqual(self.request()[2], {'version': None})
        invalid = [b'[]', b'{', b'\xff', b' ' * 1025,
            b'{"version":"v1.2.3","version":"v9.9.9"}']
        invalid += [json.dumps(value).encode() for value in ({}, {'version': True}, {'version': 17},
            {'version': None}, {'version': '1.2.3'}, {'version': 'v01.2.3'}, {'version': 'v１.2.3'},
            {'version': 'v1.2.3\n'}, {'version': 'v1.2.3', 'private': 'synthetic-secret'})]
        for raw in invalid:
            with self.subTest(raw=raw[:40]):
                self.file.write_bytes(raw)
                status, headers, body = self.request()
                self.assertEqual(status, 200)
                self.assertEqual(headers[b'cache-control'], b'no-store')
                self.assertEqual(body, {'version': None})

    def test_non_regular_files_and_links_are_rejected_without_blocking(self) -> None:
        """固定文件路径拒绝链接、目录和FIFO，不读取其它文件内容。:return: None。"""
        other = self.root / 'other.json'
        other.write_text('{"version":"v9.9.9"}')
        self.file.symlink_to(other)
        self.assertEqual(self.request()[2], {'version': None})
        self.file.unlink()
        self.file.mkdir()
        self.assertEqual(self.request()[2], {'version': None})
        self.file.rmdir()
        os.mkfifo(self.file)
        self.assertEqual(self.request()[2], {'version': None})

    def test_original_internal_authentication_protects_version(self) -> None:
        """实际内部鉴权拒绝缺失或错误令牌，正确内部请求才读取版本。:return: None。"""
        import main

        self.file.write_text('{"version":"v1.17.2"}')
        app = FastAPI()
        app.include_router(system_updates.system_updates_router(self.provider))
        app.middleware('http')(main.session_auth_middleware)
        token = 'synthetic-internal-token-' * 2
        with patch.object(main, 'V3_ENABLED', True), patch.dict(os.environ, {'V3_INTERNAL_TOKEN': token}):
            for headers in ({}, {'authorization': 'Bearer wrong'}):
                self.assertEqual(self.request(app=app, headers=headers)[0], 401)
            self.assertEqual(self.request(app=app, headers={'authorization': 'Bearer ' + token})[2],
                {'version': 'v1.17.2'})
        self.assertEqual(self.request(method='POST')[0], 405)


if __name__ == '__main__':
    unittest.main()
