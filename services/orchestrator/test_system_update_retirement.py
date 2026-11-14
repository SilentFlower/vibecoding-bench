"""历史回退前由当前所有者受证收口角色的真实 HTTP 合同。"""
import asyncio
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI

from system_updates import system_updates_router
import test_account_runtime


class RetirementTests(unittest.TestCase):
    """核对门禁、代次和排空后才允许移除，身份及重建由原生命周期负责。"""

    def test_environment_actions_require_proof_and_preserve_applied_layout(self) -> None:
        """退役保留身份，重建和恢复沿实际布局；错误证明、代次及在途均拒绝。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'bench.sqlite'
            with sqlite3.connect(database) as connection:
                connection.executescript('CREATE TABLE account_environments(environment_id TEXT,account_id INTEGER,generation INTEGER,state TEXT);'
                    "INSERT INTO account_environments VALUES('synthetic',1,7,'ready');"
                    'CREATE TABLE accounts(id INTEGER);INSERT INTO accounts VALUES(1);')

            def connect():
                """打开独立真实 SQLite 连接。@return 带列名的连接。"""
                connection = sqlite3.connect(database)
                connection.row_factory = sqlite3.Row
                return connection

            runtime = SimpleNamespace(database=connect, environment_lock=lambda identifier: threading.RLock(),
                _stop_environment=Mock(), _update=lambda row, **fields: row.update(fields), ensure=Mock())
            evidence = {'ready': True, 'active': 0, 'environments': []}
            gate = {'phase': 'blocked', 'operation_id': 'synthetic-operation', 'epoch': 'synthetic-epoch'}
            with patch('system_updates.UPDATE_GATE', SimpleNamespace(state=lambda: gate)), \
                    patch('system_updates.update_token', return_value='synthetic-token'), \
                    patch('system_updates.runtime_snapshot', return_value=evidence), \
                    patch('system_updates.partial_restore_ready') as partial, \
                    patch('system_updates.image_origin', return_value={'release': 'ci-2-1'}):
                app = FastAPI()
                app.include_router(system_updates_router(lambda: runtime))
                def post(body, headers=None):
                    """沿真实 ASGI 协议调用路由，保持正式 CI 的依赖集合。:param body: 请求体。:param headers: 内部证明。:return: 状态及解码正文。"""
                    async def request():
                        """发送完整请求并收集真实响应。@return 状态及正文。"""
                        messages = []

                        async def receive():
                            """提供本次 JSON 请求体。@return ASGI 请求消息。"""
                            return {'type': 'http.request', 'body': json.dumps(body).encode(), 'more_body': False}

                        async def send(message):
                            """保存完整 ASGI 响应。:param message: 响应消息。:return: None。"""
                            messages.append(message)

                        path = '/internal/v3/system-updates/environment'
                        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                            'method': 'POST', 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                            'query_string': b'', 'root_path': '', 'server': ('test', 80), 'client': ('test', 1),
                            'headers': [(b'content-type', b'application/json'),
                                *[(key.encode(), value.encode()) for key, value in (headers or {}).items()]]}
                        await app(scope, receive, send)
                        status = next(item['status'] for item in messages if item['type'] == 'http.response.start')
                        data = json.loads(b''.join(item.get('body', b'') for item in messages if item['type'] == 'http.response.body'))
                        return SimpleNamespace(status_code=status, json=lambda: data)

                    return asyncio.run(request())

                body = {'operation_id': gate['operation_id'], 'epoch': gate['epoch'],
                    'environment_id': 'synthetic', 'generation': 7, 'action': 'retire',
                    'allowed_image_ids': ['sha256:' + 'a' * 64]}
                headers = {'x-v3-update-token': 'synthetic-token'}
                self.assertEqual(post(body).status_code, 403)
                for changes in ({'epoch': 'foreign'}, {'generation': 8}):
                    self.assertEqual(post({**body, **changes}, headers).status_code, 409)
                evidence.update(ready=False, active=1)
                self.assertEqual(post(body, headers).status_code, 409)
                runtime._stop_environment.assert_not_called()
                evidence.update(ready=True, active=0)
                partial.side_effect = ValueError('合成角色来源冲突')
                self.assertEqual(post(body, headers).status_code, 409)
                runtime._stop_environment.assert_not_called()
                partial.side_effect = None
                evidence.update(ready=False, environments=[{'environment_id': 'sibling', 'blockers': ['合成待恢复角色']}])
                response = post(body, headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['generation'], 7)
                self.assertEqual(response.json()['state'], 'stopped')
                self.assertIsNone(response.json()['origin'])
                self.assertTrue(runtime._stop_environment.call_args.kwargs['remove'])
                self.assertEqual(partial.call_args.args[-1], body['allowed_image_ids'])
                runtime.ensure.assert_not_called()

                # 更新恢复承接实际基础布局，不能因目标原生预算为空而再次阻断CLI。
                fixture = test_account_runtime.AccountRuntimeTests()
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                fixture._isolated_docker()
                runtime = fixture.runtime
                with fixture.database() as connection:
                    for name, definition in (('upstream_proxy_scheme', "TEXT DEFAULT 'socks5'"),
                            ('upstream_socks5_host', "TEXT DEFAULT '192.0.2.2'"),
                            ('upstream_socks5_port', 'INTEGER DEFAULT 1080'),
                            ('upstream_socks5_user', "TEXT DEFAULT ''"), ('upstream_socks5_pass', "TEXT DEFAULT ''")):
                        connection.execute('ALTER TABLE accounts ADD COLUMN ' + name + ' ' + definition)
                    account = dict(connection.execute('SELECT * FROM accounts WHERE id=1').fetchone())
                row = runtime._row('synthetic', 1)
                runtime._update(row, fingerprint_json=json.dumps({**json.loads(row['fingerprint_json']), 'mem': '1536m'}))
                fixture.gateway._request.return_value = {'auth_type': 'oauth', 'status': 'active',
                    'proxy_url': runtime._proxy(account), 'request_backend': 'native293', 'concurrency': 4}
                with patch.object(runtime, '_make_room'), patch.object(runtime, '_sender_active', return_value=0), \
                        patch.dict('os.environ', {'V3_NATIVE_SENDER_MEMORY': ''}):
                    row, _ = runtime.ensure(account, prepare_sender=False)
                    fingerprint = row['fingerprint_json']
                    for action in ('rebuild', 'restore'):
                        evidence.update(ready=True, active=0, environments=[])
                        response = post({**body, 'action': action, 'environment_id': row['environment_id'],
                            'generation': row['generation']}, headers)
                        self.assertEqual(200, response.status_code)
                        self.assertEqual('ready', response.json()['state'])
                        current = runtime._row('synthetic', 1)
                        self.assertEqual(row['generation'] + 1, current['generation'])
                        self.assertEqual(fingerprint, current['fingerprint_json'])
                        self.assertIsNone(json.loads(runtime._sender_config(current).read_text())['native'])
                        row = current

                    fixture.client.images.get.return_value.attrs['Config']['Labels']['vibebench.native-runtime'] = '293-raw-1'
                    runtime._update(row, fingerprint_json=json.dumps({**json.loads(row['fingerprint_json']), 'mem': '4g'}))
                    fixture.gateway._request.return_value['concurrency'] = 3
                    with patch.dict('os.environ', {'V3_NATIVE_SENDER_MEMORY': '1536m'}):
                        row, _ = runtime.ensure(account)
                    fingerprint = row['fingerprint_json']
                    native = json.loads(runtime._sender_config(row).read_text())['native']
                    for action in ('rebuild', 'restore'):
                        response = post({**body, 'action': action, 'environment_id': row['environment_id'],
                            'generation': row['generation']}, headers)
                        self.assertEqual(200, response.status_code)
                        current = runtime._row('synthetic', 1)
                        self.assertEqual(fingerprint, current['fingerprint_json'])
                        self.assertEqual(native, json.loads(runtime._sender_config(current).read_text())['native'])
                        row = current
