"""账号命名空间中的完整 Pi 养号现场与控制接口，复用现有管理鉴权。"""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr
from sse_starlette.sse import EventSourceResponse


class WarmupPiConfigIn(BaseModel):
    """独立保存追加指南和本轮预算，原间隔与额度由既有账号 API 维护。

    :param instructions: 用户追加指南原文。
    :param budget_sec: 本轮累计执行预算。
    """
    instructions: StrictStr = Field(default='', max_length=12000)
    budget_sec: StrictInt = Field(default=1800, ge=60, le=86400)
    model_config = ConfigDict(extra='forbid')


class WarmupPiReconcileIn(BaseModel):
    """记录原生输入的人工核对事实。:param operation_id: 原操作ID。:param sent: 是否已发送。"""
    operation_id: StrictStr = Field(min_length=1, max_length=128)
    sent: StrictBool
    model_config = ConfigDict(extra='forbid')


def warmup_pi_router(service) -> APIRouter:
    """创建桥已放行的 accounts 下属养号路由。:param service: 当前服务引用。:return: FastAPI路由。"""
    router = APIRouter(prefix='/api/accounts/warmup/pi')

    def owner():
        """读取已就绪服务，不用旧 worker 伪装新轮次。:return: 实际服务。"""
        value = service()
        if value is None:
            raise HTTPException(503, 'Pi 养号需要已就绪的 v3 固定账号运行环境')
        return value

    @router.get('')
    def overview() -> dict:
        """读取养号账号现场。:return: 公开账号摘要。"""
        return owner().view()

    @router.put('/agents/{account_id}')
    def configure(account_id: int, body: WarmupPiConfigIn) -> dict:
        """保存指南和预算，不启用原账号开关。:param account_id: 账号。:param body: 独立Pi配置。:return: 公开状态。"""
        try:
            return owner().configure(account_id, body.instructions, body.budget_sec)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.get('/agents/{account_id}/snapshot')
    def snapshot(account_id: int) -> dict:
        """读取当前轮最新屏幕和事件高水位。:param account_id: 账号。:return: 一致现场快照。"""
        return owner().snapshot(account_id)

    @router.get('/agents/{account_id}/events/page')
    def events(account_id: int, before: int | None = Query(None, ge=1, le=9223372036854775807),
               limit: int = Query(20, ge=1, le=100)) -> dict:
        """倒序分页读取交互。:param account_id: 账号。:param before: 独占事件上界。:param limit: 页大小。:return: 交互页。"""
        return owner().event_page(account_id, before, limit)

    @router.get('/agents/{account_id}/rounds/page')
    def rounds(account_id: int, before: str | None = Query(None, min_length=1, max_length=128),
               limit: int = Query(10, ge=1, le=100)) -> dict:
        """倒序分页读取真实轮次。:param account_id: 账号。:param before: 上一页末轮。:param limit: 页大小。:return: 轮次页。"""
        try:
            return owner().round_page(account_id, before, limit)
        except ValueError:
            raise HTTPException(404, '养号分页游标不存在') from None

    @router.get('/rounds/{round_id}')
    def detail(round_id: str) -> dict:
        """读取冻结题目与原生完成证据。:param round_id: 轮次。:return: 公开详情。"""
        try:
            return owner().round_detail(round_id)
        except ValueError as error:
            raise HTTPException(404, str(error)) from None

    @router.get('/agents/{account_id}/actions')
    def actions(account_id: int) -> list[dict]:
        """读取输入对账事项。:param account_id: 账号。:return: 未确认输入。"""
        return owner().actions(account_id)

    @router.post('/agents/{account_id}/reconcile')
    def reconcile(account_id: int, body: WarmupPiReconcileIn) -> dict:
        """保存人工核对结论。:param account_id: 账号。:param body: 原操作及结论。:return: 公开状态。"""
        try:
            return owner().reconcile(account_id, body.operation_id, body.sent)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.post('/agents/{account_id}/{action}')
    def transition(account_id: int, action: Literal['start', 'pause', 'stop']) -> dict:
        """控制Pi原轮次，不改写旧runs。:param account_id: 账号。:param action: 启动、暂停或停止。:return: 公开状态。"""
        try:
            return owner().start(account_id) if action == 'start' else owner().pause(account_id, stop_round=action == 'stop')
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.get('/stream')
    async def stream(request: Request, account_id: int = Query(..., ge=1), after: int = Query(0, ge=0)):
        """推送高水位后的真实增量，支持断线续接。:param request: 请求。:param account_id: 账号。:param after: 事件起点。:return: SSE响应。"""
        current = owner()
        previous_id = request.headers.get('last-event-id', '')
        if previous_id.isdecimal() and len(previous_id) < 20:
            after = max(after, int(previous_id))

        async def generate():
            cursor, previous = after, None
            while not await request.is_disconnected():
                records = current.events(account_id, cursor)
                if records:
                    cursor = records[-1]['id']
                state = current.view(account_id)
                encoded = json.dumps(state, ensure_ascii=False)
                if records or previous != encoded:
                    yield {'event': 'update', 'id': str(cursor), 'data': json.dumps({'state': state, 'events': records}, ensure_ascii=False)}
                    previous = encoded
                await asyncio.sleep(1)

        return EventSourceResponse(generate(), ping=15)

    return router
