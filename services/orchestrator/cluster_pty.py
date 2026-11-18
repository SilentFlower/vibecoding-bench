"""具体Node操作共用的有限PTY帧与私有连接收口。"""
from __future__ import annotations

import asyncio

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocket, WebSocketDisconnect

from cluster_execution_grants import ExecutionScope
from system_update_contract import strict_json


class PtyInput(BaseModel):
    """原PTY的有限二进制输入。:param operation_id: 单次输入。:param data: 最多16KiB原字节的base64。"""

    model_config=ConfigDict(extra='forbid')
    operation_id:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    data:StrictStr=Field(min_length=1,max_length=21848)


class PtyResize(BaseModel):
    """原PTY的有限窗口尺寸。:param rows: 行。:param cols: 列。"""

    model_config=ConfigDict(extra='forbid')
    rows:StrictInt=Field(ge=1,le=1000)
    cols:StrictInt=Field(ge=1,le=1000)


async def serve_node_pty(owner, websocket: WebSocket, scope: ExecutionScope) -> None:
    """转发已鉴权的具体作业PTY，保持单片输入回执与连接关闭。

    :param owner: 实现原open/send/receipt/resize/close方法的具体Actor。
    :param websocket: 原私有UDS连接。
    :param scope: 首帧冻结范围。
    :return: None；连接结束只关闭attach，实际作业按原停止协议收口。
    """
    tasks,raw=[],None

    async def output():
        loop=asyncio.get_running_loop()
        while True:
            content=await loop.sock_recv(raw,4096)
            if not content:
                return
            await websocket.send_bytes(content)

    async def incoming():
        while True:
            text=await websocket.receive_text()
            if len(text.encode())>32768:
                raise ValueError('PTY输入帧超过读取上限')
            value=strict_json(text.encode(),32768)
            action=value.pop('type',None)
            if action=='input':
                receipt=await run_in_threadpool(owner.send_input,scope,PtyInput.model_validate(value))
                await websocket.send_json({'type':'input_ack','receipt':receipt})
            elif action=='resize':
                await run_in_threadpool(owner.resize,scope,PtyResize.model_validate(value))
            else:
                raise ValueError('原PTY输入动作无效')

    try:
        raw=await run_in_threadpool(owner.open_pty,scope)
        await websocket.send_json({'type':'ready','scope':scope.model_dump()})
        tasks=[asyncio.create_task(output()),asyncio.create_task(incoming())]
        done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        if raw is not None:
            await run_in_threadpool(owner.close_pty,scope)
