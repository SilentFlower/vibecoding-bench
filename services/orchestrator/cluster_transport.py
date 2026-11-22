"""将统一网关的受限发送器协议流式转接至 SSH Unix 隧道。"""
from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from httpx import AsyncClient, AsyncHTTPTransport, RequestError, Timeout
from starlette.responses import StreamingResponse

from cluster_store import ClusterStore
from system_update_gate import UPDATE_GATE


_METHODS = {'internal/send': 'POST', 'internal/native/status': 'GET', 'internal/native/prepare': 'POST',
    'internal/native/readiness': 'POST', 'internal/native/idle-policy': 'POST',
    'internal/native/prepare-switch': 'POST', 'internal/native/prepare/cancel': 'POST',
    'internal/native/messages': 'POST', 'internal/status': 'GET'}
_AGY_METHODS = {'internal/agy/prepare': 'POST', 'internal/agy/generate': 'POST',
    'internal/agy/tools': 'POST', 'internal/agy/cancel': 'POST', 'internal/agy/warm': 'POST', 'internal/status': 'GET'}
_HOP_HEADERS = {b'connection', b'keep-alive', b'proxy-authenticate', b'proxy-authorization',
    b'te', b'trailer', b'transfer-encoding', b'upgrade', b'host', b'x-v3-relay-token'}


class _NodeResponse(StreamingResponse):
    """将响应发送失败和流迭代结束统一收口到原资源释放函数。"""

    def __init__(self, content, cleanup, **kwargs) -> None:
        super().__init__(content, **kwargs)
        self.cleanup = cleanup

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.cleanup()


@dataclass(frozen=True)
class NodeTransport:
    """一条中央已核对的账号节点发送通道。

    :param node_id: 中央节点 ID。
    :param node_key: 节点稳定身份。
    :param account_id: 编排账号 ID。
    :param environment_id: 原固定环境身份。
    :param assignment_revision: 人工分配版本。
    :param generation: 实际 sender 代次。
    :param socket_path: 受保护 SSH 隧道 socket。
    :param secret: 仅供网关与 sender 使用的私有认证。
    """

    node_id: int
    node_key: str
    account_id: int
    environment_id: str
    assignment_revision: int
    generation: int
    socket_path: Path
    secret: str = field(repr=False)
    agy: bool = False


class NodeTransports:
    """登记和核对私有传输，活动计数覆盖实际响应流。

    :param store: 中央节点与账号归属存储。
    """

    def __init__(self, store: ClusterStore) -> None:
        """初始化仅含私有元数据的登记。:param store: 中央存储。:return: None。"""
        self.store, self.lock = store, threading.RLock()
        self.entries: dict[tuple[str, str, int], NodeTransport] = {}
        self.active: dict[int, int] = {}
        self.account_active: dict[tuple[bool, int], int] = {}

    def register(self, entry: NodeTransport) -> None:
        """登记本次已核对通道，拒绝较旧 sender 覆盖。

        :param entry: 内部验证后的发送通道。
        :return: None。
        """
        key = entry.node_key, entry.environment_id, entry.assignment_revision
        if len(entry.secret) < 32:
            raise ValueError('节点发送器认证无效')
        with self.lock:
            existing = self.entries.get(key)
            if existing and existing.generation > entry.generation:
                raise ValueError('节点发送器回执已过期')
            self.entries[key] = entry

    def authorize(self, node_key: str, environment_id: str, revision: int, authorization: str) -> NodeTransport:
        """按当前权威归属与私有认证核对通道。

        :param node_key: URL 中的节点身份。
        :param environment_id: URL 中的环境身份。
        :param revision: 分配版本。
        :param authorization: 原 sender 认证头。
        :return: 可用于本次转发的冻结通道。
        """
        with self.lock:
            entry = self.entries.get((node_key, environment_id, revision))
        if entry is None or not secrets.compare_digest(authorization, 'Bearer ' + entry.secret):
            raise ValueError('节点传输认证或运行绑定无效')
        assignment = self.store.agy_assignment(entry.account_id) if entry.agy else self.store.assignment(entry.account_id)
        draining = entry.agy and assignment['phase'] != 'ready' and self.store.agy_draining(entry.account_id, revision)
        if (assignment['node_id'] != entry.node_id or assignment['node_key'] != node_key
                or assignment['revision'] != revision
                or not draining and (assignment['phase'] != 'ready' or not assignment['enabled'])):
            raise ValueError('账号节点归属已变化或正在维护')
        connection = self.store.database()
        try:
            if entry.agy:
                row = connection.execute('SELECT p.gateway_account_id AS account_id,e.generation FROM account_environments e '
                    'JOIN platform_api_environments p ON p.environment_id=e.environment_id '
                    'WHERE e.environment_id=? AND e.account_id IS NULL', (environment_id,)).fetchone()
            else:
                row = connection.execute('SELECT account_id,generation FROM account_environments WHERE environment_id=?',
                    (environment_id,)).fetchone()
            if row is None or row['account_id'] != entry.account_id or row['generation'] != entry.generation:
                raise ValueError('账号环境代次已变化')
        finally:
            connection.close()
        return entry

    def acquire(self, node_key: str, environment_id: str, revision: int, authorization: str) -> NodeTransport:
        """与迁移关闭准入共用短锁，原子核对绑定并计入实际流。

        :param node_key: 冻结节点。
        :param environment_id: 固定环境。
        :param revision: 分配版本。
        :param authorization: 原发送器认证。
        :return: 已登记活动的冻结通道，调用方必须用end释放。
        """
        with self.store.lock:
            entry = self.authorize(node_key, environment_id, revision, authorization)
            with self.lock:
                self.active[entry.node_id] = self.active.get(entry.node_id, 0) + 1
                key = entry.agy, entry.account_id
                self.account_active[key] = self.account_active.get(key, 0) + 1
        return entry

    def end(self, entry: NodeTransport) -> None:
        """释放一个实际流及账号排空计数。:param entry: 原已取得通道。:return: None。"""
        with self.lock:
            for counts, key in ((self.active, entry.node_id), (self.account_active, (entry.agy, entry.account_id))):
                remaining = counts.get(key, 0) - 1
                if remaining > 0:
                    counts[key] = remaining
                else:
                    counts.pop(key, None)

    def account_streams(self, account_id: int, *, agy: bool = False) -> int:
        """读取账号仍在传输的实际流数。@param account_id 中央账号。@param agy 网关账号域。@return 实际活动计数。"""
        with self.lock:
            return self.account_active.get((agy, account_id), 0)


def _forward_headers(headers: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    excluded = set(_HOP_HEADERS)
    for name, value in headers:
        if name.lower() == b'connection':
            excluded.update(token.strip().lower() for token in value.split(b','))
    return [(name, value) for name, value in headers if name.lower() not in excluded]


def node_transport_router(registry) -> APIRouter:
    """提供仅接受网关内部认证的流式账号转接。

    :param registry: 当前节点传输登记的回调。
    :return: 受限内部路由。
    """
    router = APIRouter()

    @router.api_route('/cluster-transports/v2/{deployment_key}/{node_key}/{environment_id}/{revision}/{path:path}', methods=['GET', 'POST'])
    async def forward(deployment_key: str, node_key: str, environment_id: str, revision: int, path: str, request: Request):
        """核对当前绑定后原样传递发送器请求与响应字节。

        :param deployment_key: 当前部署的固定摘要。
        :param node_key: 节点身份。
        :param environment_id: 环境身份。
        :param revision: 人工分配版本。
        :param path: 精确 sender 路由。
        :param request: 网关内部请求。
        :return: 保留响应状态和原始压缩内容的流式响应。
        """
        deployment = os.environ.get('V3_DEPLOYMENT_ID', '')
        if (not deployment or deployment_key != hashlib.sha256(deployment.encode()).hexdigest()[:12]
                or request.method not in (_METHODS.get(path), _AGY_METHODS.get(path)) or request.url.query):
            raise HTTPException(404, '节点转发路径无效', headers={'x-v3-transport-error': 'before-send'})
        transports = registry()
        if transports is None:
            raise HTTPException(503, '节点传输尚未就绪', headers={'x-v3-transport-error': 'before-send'})
        activity = None
        acquisition = None
        try:
            activity = UPDATE_GATE.reserve('node-stream:' + environment_id)
            acquisition = asyncio.create_task(asyncio.to_thread(transports.acquire, node_key, environment_id,
                revision, request.headers.get('authorization', '')))
            entry = await asyncio.shield(acquisition)
        except asyncio.CancelledError:
            # 线程内的短事务不会随协程取消；等待其结果后收口，防止留下永久活动计数。
            if acquisition is not None:
                try:
                    acquired = await acquisition
                except Exception:
                    pass
                else:
                    transports.end(acquired)
            if activity is not None:
                UPDATE_GATE.release_reserved(activity)
            raise
        except Exception:
            if activity is not None:
                UPDATE_GATE.release_reserved(activity)
            raise HTTPException(503, '节点传输绑定已失效或正在维护', headers={'x-v3-transport-error': 'before-send'}) from None
        if (_AGY_METHODS if entry.agy else _METHODS).get(path) != request.method:
            transports.end(entry)
            UPDATE_GATE.release_reserved(activity)
            raise HTTPException(404, '节点转发路径无效', headers={'x-v3-transport-error': 'before-send'})
        client = None
        upstream = None
        cleanup_task = None
        uploaded = asyncio.Event()

        async def cleanup_resources() -> None:
            try:
                if upstream is not None:
                    await upstream.aclose()
            finally:
                try:
                    if client is not None:
                        await client.aclose()
                finally:
                    transports.end(entry)
                    UPDATE_GATE.release_reserved(activity)

        async def cleanup() -> None:
            nonlocal cleanup_task
            if cleanup_task is None:
                cleanup_task = asyncio.create_task(cleanup_resources())
            await asyncio.shield(cleanup_task)

        async def body():
            length = 0
            try:
                async for chunk in request.stream():
                    length += len(chunk)
                    if length > 128 * 1024 * 1024:
                        raise HTTPException(413, '节点转发输入超出发送器上限')
                    yield chunk
            finally:
                uploaded.set()

        async def disconnected() -> None:
            # 请求体由唯一读取者消费完之后，才可以监听断连，避免竞争 ASGI receive 丢失正文。
            await uploaded.wait()
            while True:
                message = await request.receive()
                if message['type'] == 'http.disconnect':
                    return

        sending = watcher = None
        try:
            client = AsyncClient(transport=AsyncHTTPTransport(uds=str(entry.socket_path), retries=0),
                trust_env=False, follow_redirects=False, timeout=Timeout(connect=8, read=None, write=30, pool=8))
            operation = client.build_request(request.method, 'http://node-sender/' + path,
                headers=_forward_headers(request.scope['headers']), content=body())
            sending = asyncio.create_task(client.send(operation, stream=True))
            watcher = asyncio.create_task(disconnected())
            completed, _ = await asyncio.wait((sending, watcher), return_when=asyncio.FIRST_COMPLETED)
            if sending not in completed:
                sending.cancel()
                await asyncio.gather(sending, return_exceptions=True)
                raise HTTPException(499, '调用方已断开')
            upstream = sending.result()
        except RequestError:
            await cleanup()
            raise HTTPException(502, '节点传输中断，提交结果需要核对',
                headers={'x-v3-transport-error': 'submitted'}) from None
        except BaseException:
            if sending is not None:
                sending.cancel()
                await asyncio.gather(sending, return_exceptions=True)
            await cleanup()
            raise
        finally:
            if watcher is not None:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)

        async def response_body():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await cleanup()

        response = _NodeResponse(response_body(), cleanup, status_code=upstream.status_code)
        response.raw_headers = _forward_headers(upstream.headers.raw)
        return response

    return router
