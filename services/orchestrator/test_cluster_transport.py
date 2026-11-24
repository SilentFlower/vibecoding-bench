"""以真实 HTTP 和 Unix socket 验证节点转接的流、取消及权限边界。"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import tempfile
import threading
import unittest
import uuid
import time
from base64 import b64encode
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, Request
from httpx import AsyncClient, ConnectError
from starlette.responses import Response, StreamingResponse
from uvicorn import Config, Server

from cluster_store import ClusterStore
from cluster_transport import NodeTransport, NodeTransports, node_transport_router
from database_migrations import apply_migrations
from system_update_gate import DeploymentGate
from runtime_files import atomic_json
import test_cluster_ssh as ssh_fixture


async def _chunked(payload: bytes):
    yield payload


class ClusterTransportTests(unittest.IsolatedAsyncioTestCase):
    """使用独立数据库和真实流式服务器核对转发结果。"""

    async def asyncSetUp(self) -> None:
        """建立账号、绑定及两端回环服务。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database_path = self.root / 'bench.sqlite'
        connection = self.database()
        try:
            apply_migrations(connection)
            with connection:
                connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(1,'synthetic','profiles/synthetic')")
                connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json,generation) VALUES(?, 'synthetic',1,'{}',2)", ('e' * 32,))
                self.node_id = connection.execute("INSERT INTO cluster_nodes(node_key,name,kind,config_json,created_at) VALUES(?,'节点','ssh','{}',0)", ('a' * 32,)).lastrowid
                connection.execute('UPDATE account_node_assignments SET node_id=? WHERE account_id=1', (self.node_id,))
        finally:
            connection.close()
        self.store = ClusterStore(self.database, threading.Lock())
        self.registry = NodeTransports(self.store)
        self.socket_path = self.root / 'sender.sock'
        self.secret = 'synthetic-sender-token-' * 3
        self.entry = NodeTransport(self.node_id, 'a' * 32, 1, 'e' * 32, 1, 2, self.socket_path, self.secret)
        self.registry.register(self.entry)
        self.gate = DeploymentGate()
        self.gate_patch = patch('cluster_transport.UPDATE_GATE', self.gate)
        self.gate_patch.start()
        self.addCleanup(self.gate_patch.stop)
        self.environment_patch = patch.dict(os.environ, {'V3_DEPLOYMENT_ID': 'synthetic'})
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)
        self.requests = []
        self.stream_closed = asyncio.Event()
        self.compressed = gzip.compress('节点原始响应'.encode())
        sender = FastAPI()

        @sender.api_route('/internal/{path:path}', methods=['GET', 'POST'])
        async def receive(path: str, request: Request):
            self.requests.append((path, dict(request.headers), await request.body()))
            if request.headers.get('x-synthetic-mode') == 'stream':
                async def events():
                    try:
                        while True:
                            yield b'data: synthetic\n\n'
                            await asyncio.sleep(0.05)
                    finally:
                        self.stream_closed.set()
                return StreamingResponse(events(), media_type='text/event-stream')
            return Response(self.compressed, status_code=201, headers={'content-encoding': 'gzip',
                'content-type': 'application/json', 'connection': 'close, x-node-private', 'x-node-private': 'hidden'})

        app = FastAPI()
        app.include_router(node_transport_router(lambda: self.registry))
        self.servers = []
        unix = socket.socket(socket.AF_UNIX)
        unix.bind(str(self.socket_path))
        self.addCleanup(unix.close)
        await self.start_server(sender, unix)
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        self.addCleanup(listener.close)
        self.base = f'http://127.0.0.1:{listener.getsockname()[1]}'
        await self.start_server(app, listener)
        key = hashlib.sha256(b'synthetic').hexdigest()[:12]
        self.path = f'/cluster-transports/v2/{key}/{"a" * 32}/{"e" * 32}/1/internal/send'
        self.client = AsyncClient(base_url=self.base, trust_env=False, timeout=5)

    def database(self):
        """打开隔离 SQLite。:return: 待关闭的连接。"""
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    async def start_server(self, app, listener) -> None:
        """启动真实 ASGI HTTP 服务。:param app: 应用。:param listener: 监听套接字。:return: None。"""
        server = Server(Config(app, log_level='error', lifespan='off', ws='none'))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        self.servers.append((server, task))
        for _ in range(200):
            if server.started:
                return
            if task.done():
                await task
                self.fail('回环服务提前结束')
            await asyncio.sleep(0.01)
        self.fail('回环服务启动超时')

    async def asyncTearDown(self) -> None:
        """释放客户端及服务器，检查流式计数归零。:return: None。"""
        await self.client.aclose()
        for server, task in reversed(self.servers):
            server.should_exit = True
            await asyncio.wait_for(task, timeout=5)
        self.assertEqual({}, self.registry.active)
        self.assertEqual({}, self.gate.active)

    def headers(self) -> dict:
        """生成仅在测试中使用的合成私有认证。:return: 请求头。"""
        return {'authorization': 'Bearer ' + self.secret, 'x-v3-relay-token': 'central-private-token',
            'connection': 'keep-alive, x-private-hop', 'x-private-hop': 'hidden'}

    async def test_raw_compressed_response_and_input_survive_relay(self) -> None:
        """压缩响应、请求原字节和sender认证保持一致，中央秘密在转接处移除。:return: None。"""
        body = b'{"synthetic":"\x00\xff"}'
        async with self.client.stream('POST', self.path, content=body, headers=self.headers()) as response:
            actual = b''.join([chunk async for chunk in response.aiter_raw()])
            self.assertEqual(201, response.status_code)
            self.assertEqual(self.compressed, actual)
            self.assertEqual('gzip', response.headers['content-encoding'])
            self.assertNotIn('x-node-private', response.headers)
        path, headers, received = self.requests[0]
        self.assertEqual('send', path)
        self.assertEqual(body, received)
        self.assertEqual('Bearer ' + self.secret, headers['authorization'])
        self.assertNotIn('x-v3-relay-token', headers)
        self.assertNotIn('x-private-hop', headers)

    async def test_tui_control_frames_are_reencoded_by_relay(self) -> None:
        """真实中继重建分块边界并保留数据。:return: None。"""
        for action in ('prepare', 'send', 'cancel'):
            path = f'internal/tui-v2/{action}'
            route = self.path.replace('internal/send', path)
            for payload in (b'', b'x'):
                response = await self.client.post(route, headers=self.headers(), content=_chunked(payload))
                self.assertEqual(201, response.status_code)
                received_path, headers, received = self.requests[-1]
                self.assertEqual(f'tui-v2/{action}', received_path)
                self.assertEqual('chunked', headers.get('transfer-encoding'))
                self.assertEqual(payload, received)
                self.assertEqual('Bearer ' + self.secret, headers['authorization'])
                self.assertNotIn('x-v3-relay-token', headers)
            other_method = await self.client.get(route, headers=self.headers())
            self.assertEqual(404, other_method.status_code)
        self.assertEqual(6, len(self.requests))

    async def test_original_tui_relay_closes_when_source_is_fenced(self) -> None:
        """排空只保留同账号的 V2 路由；隔离源后不再转发。:return: None。"""
        operation = 'a' * 32
        with closing(self.database()) as connection, connection:
            connection.execute("UPDATE account_node_assignments SET phase='maintenance' WHERE account_id=1")
            target = connection.execute("SELECT id FROM cluster_nodes WHERE node_key='local'").fetchone()['id']
            connection.execute("INSERT INTO node_migrations VALUES(?,1,?,?,'requested',?,0,0)",
                (operation, self.node_id, target, json.dumps({'last_confirmed_phase': 'requested', 'source_revision': 1})))
        for action in ('prepare', 'send', 'cancel'):
            route = self.path.replace('internal/send', f'internal/tui-v2/{action}')
            self.assertEqual(503, (await self.client.post(route, headers={'authorization': 'Bearer wrong'})).status_code)
            self.assertEqual(201, (await self.client.post(route, headers=self.headers())).status_code)
        status = self.path.replace('internal/send', 'internal/status')
        self.assertEqual(201, (await self.client.get(status, headers=self.headers())).status_code)
        self.assertEqual(503, (await self.client.post(self.path, headers=self.headers())).status_code)
        with closing(self.database()) as connection, connection:
            connection.execute("UPDATE node_migrations SET phase='source_fenced' WHERE operation_id=?", (operation,))
        self.assertEqual(503, (await self.client.get(status, headers=self.headers())).status_code)
        for action in ('prepare', 'send', 'cancel'):
            route = self.path.replace('internal/send', f'internal/tui-v2/{action}')
            self.assertEqual(503, (await self.client.post(route, headers=self.headers())).status_code)
        self.assertEqual(4, len(self.requests))

    @unittest.skipUnless(os.environ.get('FLOWER_TUI_RELAY_TEST_SENDER') and shutil.which('socat'),
                         '需要通过 FLOWER_TUI_RELAY_TEST_SENDER 指定已构建的 sender，并安装 socat')
    async def test_tui_control_frames_reach_real_sender_through_relay(self) -> None:
        """经仓库中继和 Unix 套接字验证真实 sender 的空体边界。:return: None。"""
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            address = f'127.0.0.1:{listener.getsockname()[1]}'
        config = self.root / 'tui-sender.json'
        atomic_json(config, {'binding': {'account_id': 1, 'environment_id': 'e' * 32,
            'generation': 2, 'endpoint': f'http://{address}', 'secret': self.secret,
            'release_id': 'synthetic'}, 'proxy_url': '', 'allowed_origin': 'http://127.0.0.1'})

        async def stop(process):
            if process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)

        sender = await asyncio.create_subprocess_exec(os.environ['FLOWER_TUI_RELAY_TEST_SENDER'],
            env={'V3_SENDER_CONFIG': str(config), 'V3_SENDER_LISTEN': address, 'RUST_LOG': 'warn'})
        self.addAsyncCleanup(stop, sender)
        async with AsyncClient(trust_env=False, timeout=1) as client:
            for _ in range(100):
                if sender.returncode is not None:
                    self.fail(f'sender 启动退出 {sender.returncode}')
                try:
                    response = await client.get(f'http://{address}/internal/status', headers=self.headers())
                    self.assertEqual(200, response.status_code)
                    break
                except ConnectError:
                    await asyncio.sleep(0.02)
            else:
                self.fail('sender 启动超时')
        endpoint = self.root / 'tui-real-sender.sock'
        bridge = await asyncio.create_subprocess_exec('socat', f'UNIX-LISTEN:{endpoint},fork', f'TCP:{address}')
        self.addAsyncCleanup(stop, bridge)
        for _ in range(100):
            if endpoint.is_socket():
                break
            await asyncio.sleep(0.02)
        else:
            self.fail('Unix 转接套接字启动超时')
        self.registry.register(replace(self.entry, socket_path=endpoint))
        for action, bad_body in (('send', 'V2 发送只接收原预留信封'),
                                 ('cancel', 'V2 取消只接收原预留信封')):
            path = f'internal/tui-v2/{action}'
            route = self.path.replace('internal/send', path)
            for payload, expected in ((b'', 'V2 预留身份或正文不匹配'), (b'x', bad_body)):
                response = await self.client.post(route, headers=self.headers(), content=_chunked(payload))
                self.assertEqual(400, response.status_code)
                # 预留信封特意省略。错误类别区分已进入身份校验与正文入口拒绝。
                self.assertIn(expected, response.json()['error'])
        # 过期信封可幂等取消，整个用例无需挂载账号持久卷。
        expired = b64encode(json.dumps({'account_id': 1, 'environment_id': 'e' * 32, 'generation': 2,
            'principal_id': 1, 'session_id': 'synthetic', 'reservation_id': str(uuid.uuid4()),
            'deadline_unix_ms': 1, 'continuation_only': False}).encode()).decode()
        cancel = 'internal/tui-v2/cancel'
        response = await self.client.post(self.path.replace('internal/send', cancel),
            headers={**self.headers(), 'x-v3-tui-reservation': expired},
            content=_chunked(b''))
        self.assertEqual(204, response.status_code)

    async def test_stream_cancel_closes_sender_and_releases_activity(self) -> None:
        """客户端取消真实 SSE 后关闭上游，活动覆盖流生命周期。:return: None。"""
        headers = {**self.headers(), 'x-synthetic-mode': 'stream'}
        async with self.client.stream('POST', self.path, content=b'{}', headers=headers) as response:
            chunk = await anext(response.aiter_raw())
            self.assertIn(b'data: synthetic', chunk)
            self.assertEqual({self.node_id: 1}, self.registry.active)
        await asyncio.wait_for(self.stream_closed.wait(), timeout=3)
        for _ in range(100):
            if not self.registry.active:
                break
            await asyncio.sleep(0.01)
        self.assertEqual({}, self.registry.active)

    async def test_changed_assignment_and_authentication_stop_before_sender(self) -> None:
        """认证错误和人工归属版本变化在发送前拒绝。:return: None。"""
        response = await self.client.post(self.path, content=b'{}', headers={'authorization': 'Bearer wrong'})
        self.assertEqual(503, response.status_code)
        self.assertEqual('before-send', response.headers['x-v3-transport-error'])
        connection = self.database()
        try:
            with connection:
                connection.execute('UPDATE account_node_assignments SET revision=revision+1 WHERE account_id=1')
        finally:
            connection.close()
        response = await self.client.post(self.path, content=b'{}', headers=self.headers())
        self.assertEqual(503, response.status_code)
        self.assertEqual([], self.requests)

    async def test_database_admission_failure_releases_enabled_update_gate(self) -> None:
        """准入查询异常也释放实际平台活动，数据库故障保持发送前拒绝。:return: None。"""
        directory = self.root / 'update-gate'
        atomic_json(directory / 'admission.json', {'schema_version': 1, 'deployment': 'synthetic',
            'operation_id': None, 'epoch': str(uuid.uuid4()), 'phase': 'idle', 'target_release': None,
            'revision': str(uuid.uuid4()), 'created_at': time.time()})
        gate = DeploymentGate(directory, 'synthetic')
        with patch('cluster_transport.UPDATE_GATE', gate), patch.object(self.registry, 'acquire',
                side_effect=sqlite3.OperationalError('合成数据库占用')):
            response = await self.client.post(self.path, content=b'{}', headers=self.headers())
        self.assertEqual(503, response.status_code)
        self.assertEqual('before-send', response.headers['x-v3-transport-error'])
        self.assertEqual({}, gate.active)
        self.assertEqual([], self.requests)

    async def test_path_whitelist_blocks_other_deployment_and_operations(self) -> None:
        """错误部署、查询参数和非白名单操作不会到达sender。:return: None。"""
        for path in (self.path.replace('/v2/', '/v2/other-'), self.path + '?unexpected=1',
                self.path.replace('/internal/send', '/admin/shell')):
            response = await self.client.post(path, content=b'{}', headers=self.headers())
            self.assertEqual(404, response.status_code)
        self.assertEqual([], self.requests)

    async def test_unavailable_socket_is_conservative_and_never_retried(self) -> None:
        """通道中断返回需核对的提交状态，保持一次发送边界。:return: None。"""
        self.socket_path.unlink()
        response = await self.client.post(self.path, content=b'{}', headers=self.headers())
        self.assertEqual(502, response.status_code)
        self.assertEqual('submitted', response.headers['x-v3-transport-error'])
        self.assertEqual([], self.requests)

    @unittest.skipUnless(os.geteuid() == 0 and shutil.which('sshd'), 'SSH回环需要sshd和root')
    async def test_stream_bytes_cross_real_ssh_business_tunnel(self) -> None:
        """节点转发HTTP经独立真实SSH业务连接到达指定发送器。:return: None。"""
        fixture = ssh_fixture.ClusterSshTests(methodName='runTest')
        await asyncio.to_thread(fixture.setUp)
        self.addCleanup(fixture.doCleanups)
        path = await asyncio.to_thread(fixture.node._forward, 'e' * 32, str(self.socket_path))
        self.registry.register(NodeTransport(self.node_id, 'a' * 32, 1, 'e' * 32, 1, 2, path, self.secret))
        self.assertEqual({'e' * 32}, set(fixture.node.processes))
        response = await self.client.post(self.path, content=b'cross-ssh', headers=self.headers())
        self.assertEqual(201, response.status_code)
        self.assertEqual('节点原始响应', response.text)
        self.assertEqual(b'cross-ssh', self.requests[0][2])
