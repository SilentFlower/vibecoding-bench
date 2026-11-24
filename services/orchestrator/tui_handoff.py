"""将已授权的客户端工具交还给原先等待的账号进程。"""

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from subprocess import Popen
from threading import Event

from tui_process import TuiProcessExecutor, TuiProcessHandle
from tui_tool_receipts import ToolReceiptStore, ToolTurn


@dataclass(frozen=True, slots=True)
class TuiToolHandoff:
    """一次已绑定运行进程的工具交接。作用域由已认证的调用方传入。"""

    turn: ToolTurn
    receipts: ToolReceiptStore
    executor: TuiProcessExecutor
    handle: TuiProcessHandle
    _session_key: str

    @classmethod
    def start(cls, turn: ToolTurn, receipts: ToolReceiptStore, executor: TuiProcessExecutor,
              *, timeout: float, cancel_event: Event | None = None) -> "TuiToolHandoff":
        """为一次新轮取得账号进程。

        @param turn 经过授权的账号、主体、会话和逻辑轮次。
        @param receipts 账号私有回执存储。
        @param executor 此账号的进程执行器。
        @param timeout 新轮等待进程名额的剩余时间，单位秒。
        @param cancel_event 进程生命周期的取消事件。
        @return 与这次进程启动代次绑定的交接对象。
        """
        # 客户端之间可能复用会话名。轮次不参与会话键，以便并行的新轮不能占用同一终端。
        identity = dumps([turn.account_id, turn.principal_id, turn.session_id], separators=(',', ':'))
        key = sha256(identity.encode()).hexdigest()
        handle = executor.start(key, timeout=timeout, cancel_event=cancel_event)
        return cls(turn, receipts, executor, handle, key)

    def offer(self, tool_use_id: str, *, internal_id: str, name: str, arguments: dict | None) -> dict | None:
        """先记账再向客户端交付工具调用，同一调用最多产生一次新的交付。

        @param tool_use_id 首次分配并在重试中保持的外部调用 ID。
        @param internal_id 进程中对应的工具调用 ID。
        @param name 客户端注册的原工具名。
        @param arguments 完整参数；流式块开头尚未取得参数时传 None。
        @return 要发给客户端的工具块或流式块头；已认领过的交付返回 None。
        """
        self.executor.resume(self._session_key, self.handle)
        self.receipts.register(self.turn, tool_use_id, internal_id=internal_id, name=name,
                               arguments=arguments, backend='tui', generation=self.handle.generation)
        if self.receipts.claim_delivery(self.turn, tool_use_id):
            return {'type': 'tool_use', 'id': tool_use_id, 'name': name,
                    'input': {} if arguments is None else arguments}
        return None

    def seal_arguments(self, tool_use_id: str, *, internal_id: str, name: str, arguments: dict) -> None:
        """流式工具参数收齐后、向客户端交付块结束事件前，核对映射及参数摘要。

        @param tool_use_id 流式工具块头登记的外部调用 ID。
        @param internal_id 原进程调用 ID。
        @param name 客户端工具名。
        @param arguments 依次组装并解码后的完整参数。
        @return 无。
        """
        self.executor.resume(self._session_key, self.handle)
        self.receipts.read(self.turn, tool_use_id)
        self.receipts.register(self.turn, tool_use_id, internal_id=internal_id, name=name,
                               arguments=arguments, backend='tui', generation=self.handle.generation)

    def deliver(self, tool_use_id: str, *, internal_id: str,
                send_and_ack: Callable[[Popen, dict], str]) -> bool:
        """将已保存的客户端结果投递到原进程。调用方负责在其私有通道上读取实际接收回执。

        @param tool_use_id 外部调用 ID。
        @param internal_id 原进程发出的工具调用 ID。
        @param send_and_ack 向指定进程发送完整结果并返回该进程确认的内部调用 ID。
        @return 本次收到正确回执时为 True；没有可认领结果时为 False。
        """
        # 复用仍在等待的进程；即使新轮排满队列，此操作也不申请新名额。
        process = self.executor.resume(self._session_key, self.handle)
        binding = dict(internal_id=internal_id, backend='tui', generation=self.handle.generation)
        result = self.receipts.take_result(self.turn, tool_use_id, **binding)
        if result is None:
            return False
        # 持久状态先进入投递待核对。断线或错误回执都不能触发第二次自动投递。
        if send_and_ack(process, {**result, 'tool_use_id': internal_id}) != internal_id:
            raise ValueError('原进程返回的工具调用回执不匹配')
        self.receipts.confirm_result(self.turn, tool_use_id, **binding)
        return True
