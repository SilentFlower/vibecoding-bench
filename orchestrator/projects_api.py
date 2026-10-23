"""新 Projects 的账号控制、研究、事件和人工对账接口。"""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr
from sse_starlette.sse import EventSourceResponse


class ProjectsAgentIn(BaseModel):
    """配置账号的项目池、业务指南和工作预算。

    :param project_keys: 允许 Pi 使用的项目列表。
    :param instructions: 用户提供的业务指南。
    :param budget_sec: 单次指挥与工作累计预算。
    """
    project_keys: list[StrictStr]
    instructions: StrictStr = ''
    budget_sec: StrictInt = 3600
    model_config = ConfigDict(extra='forbid')


class ProjectsReconcileIn(BaseModel):
    """保存管理员对未知输入的核对结论。

    :param operation_id: 需要核对的操作 ID。
    :param sent: 是否确认已发送。
    """
    operation_id: StrictStr
    sent: StrictBool
    model_config = ConfigDict(extra='forbid')


def projects_router(service) -> APIRouter:
    """创建路由，运行时读取服务引用，不绕过既有管理鉴权。

    :param service: 返回当前 ProjectsService 的回调。
    :return: 可挂载的 FastAPI 路由。
    """
    router = APIRouter(prefix='/api/projects')

    def owner():
        """取得当前已就绪的账号控制服务。

        :return: Projects 服务；未就绪时返回明确的 503。
        """
        value = service()
        if value is None:
            raise HTTPException(503, 'Pi Projects 需要 v3 固定账号运行环境')
        return value

    @router.get('')
    def overview() -> dict:
        """读取全部账号控制状态。:return: 公开控制摘要。"""
        return owner().state()

    @router.get('/catalog')
    def catalog() -> dict:
        """读取保留的项目研究目录。:return: 研究项目及工程准入状态。"""
        return owner().catalog.listing()

    @router.get('/catalog/{key}')
    def project(key: str) -> dict:
        """读取公开研究。:param key: 项目标识。:return: 项目研究及业务材料。"""
        try:
            return owner().catalog.project(key)
        except ValueError as error:
            raise HTTPException(404, str(error)) from None

    @router.put('/agents/{account_id}')
    def configure(account_id: int, body: ProjectsAgentIn) -> dict:
        """保存 Pi 配置。:param account_id: 账号。:param body: 项目池与指南。:return: 账号控制状态。"""
        try:
            return owner().configure(account_id, body.project_keys, body.instructions, body.budget_sec)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.get('/agents/{account_id}/events')
    def events(account_id: int, after: int = Query(0, ge=0)) -> list[dict]:
        """分页读取事件。:param account_id: 账号。:param after: 事件游标。:return: 事件列表。"""
        return owner().events(account_id, after)

    @router.get('/agents/{account_id}/work')
    def history(account_id: int) -> list[dict]:
        """读取账号工作历史。:param account_id: 账号。:return: 最近工作的公开摘要。"""
        return owner().history(account_id)

    @router.get('/agents/{account_id}/actions')
    def actions(account_id: int) -> list[dict]:
        """读取待核对输入。:param account_id: 账号。:return: 原操作及未知状态。"""
        return owner().actions(account_id)

    @router.get('/work/{work_id}')
    def work_detail(work_id: str) -> dict:
        """读取新工程交付记录。:param work_id: 工作 ID。:return: 工作及冻结交付列表。"""
        try:
            return owner().work_detail(work_id)
        except ValueError as error:
            raise HTTPException(404, str(error)) from None

    @router.get('/submissions/{submission_id}')
    def submission(submission_id: str, path: str | None = None) -> dict:
        """读取冻结成果。:param submission_id: 交付 ID。:param path: 候选相对路径。:return: 修改清单或文本预览。"""
        try:
            return owner().submission(submission_id, path)
        except (ValueError, OSError) as error:
            raise HTTPException(404, '冻结成果不存在、损坏或路径不属于候选清单') from None

    @router.post('/agents/{account_id}/reconcile')
    def reconcile(account_id: int, body: ProjectsReconcileIn) -> dict:
        """提交人工核对。:param account_id: 账号。:param body: 操作与结论。:return: 核对后状态。"""
        try:
            return owner().reconcile(account_id, body.operation_id, body.sent)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.post('/agents/{account_id}/{action}')
    def transition(account_id: int, action: Literal['start', 'pause', 'stop'], body: dict | None = None) -> dict:
        """控制账号 Pi。:param account_id: 账号。:param action: 启动、暂停或停止目标。:param body: 保留空请求兼容。:return: 当前状态。"""
        try:
            return owner().start(account_id) if action == 'start' else owner().pause(account_id, stop_work=action == 'stop')
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.get('/stream')
    async def stream(request: Request, account_id: int = Query(..., ge=1), after: int = Query(0, ge=0)):
        """推送账号状态及增量事件。:param request: 当前连接。:param account_id: 账号。:param after: 事件游标。:return: 可断线续接的 SSE。"""
        current = owner()
        last_event = request.headers.get('last-event-id', '')
        if last_event.isdecimal() and len(last_event) < 20:
            after = max(after, int(last_event))

        async def generate():
            cursor, previous = after, None
            while not await request.is_disconnected():
                records = current.events(account_id, cursor)
                if records:
                    cursor = records[-1]['id']
                state = current.state(account_id)
                encoded = json.dumps(state, ensure_ascii=False)
                if records or encoded != previous:
                    yield {'event': 'update', 'id': str(cursor),
                        'data': json.dumps({'state': state, 'events': records}, ensure_ascii=False)}
                    previous = encoded
                await asyncio.sleep(1)

        return EventSourceResponse(generate(), ping=15)

    return router
