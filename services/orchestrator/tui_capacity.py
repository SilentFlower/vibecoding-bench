"""单账号的交互式 TUI 进程准入与生命周期名额。"""

from collections import deque
from dataclasses import dataclass
from threading import Condition, Event, TIMEOUT_MAX
from time import monotonic


_CANCEL_POLL_SECONDS = 0.05


class TuiCapacityError(RuntimeError):
    """携带执行器可映射的准入错误码。

    @param code 稳定的失败原因。
    """

    def __init__(self, code: str) -> None:
        """保存错误码。@param code 稳定的失败原因。@return 无。"""
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TuiCapacitySnapshot:
    """同一时点的名额上限、进程占用和排队数。"""

    limit: int
    in_use: int
    waiting: int


@dataclass(frozen=True, eq=False, slots=True)
class TuiProcessSlot:
    """执行器持有的单进程名额，使用对象身份匹配所属容量。"""

    _capacity: "TuiCapacity"

    def release_after_close(self) -> None:
        """进程确认关闭或确认启动未发生后归还名额。@return 无；重复归还无副作用。"""
        self._capacity._release(self)


class TuiCapacity:
    """在同一账号的发送器内共享，按进程而非按 HTTP 请求管理名额。

    @param configured_concurrency 账号配置的进程并发数，可为零。
    @param budget_bytes 显式分给本组件的 RAM 总预算（字节，含固定保留）。
    @param fixed_reserve_bytes 共享开销的固定保留（字节）。
    @param per_process_reserve_bytes 每个进程的规划预留（正整数字节）。
    @param max_waiters 满额时的等待队列上限，零表示立即拒绝。
    单进程预留是规划值。实际 RAM 上限由执行环境负责。
    """

    def __init__(
        self,
        configured_concurrency: int,
        *,
        budget_bytes: int,
        fixed_reserve_bytes: int,
        per_process_reserve_bytes: int,
        max_waiters: int,
    ) -> None:
        """冻结显式预算，初始化队列和占用状态。

        @param configured_concurrency 配置并发。
        @param budget_bytes 可分配预算（字节）。
        @param fixed_reserve_bytes 固定保留（字节）。
        @param per_process_reserve_bytes 单进程预留（字节）。
        @param max_waiters 等待队列上限。
        @return 无。
        """
        for name, value, minimum in (
            ("configured_concurrency", configured_concurrency, 0),
            ("budget_bytes", budget_bytes, 0),
            ("fixed_reserve_bytes", fixed_reserve_bytes, 0),
            ("per_process_reserve_bytes", per_process_reserve_bytes, 1),
            ("max_waiters", max_waiters, 0),
        ):
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} 必须是大于等于 {minimum} 的整数")

        # 已占用进程由名额计算；这里以总预算减固定保留，避免再次扣除运行中进程的实测内存。
        usable = max(0, budget_bytes - fixed_reserve_bytes)
        self._limit = min(configured_concurrency, usable // per_process_reserve_bytes)
        self._max_waiters = max_waiters
        self._condition = Condition()
        self._active: set[TuiProcessSlot] = set()
        self._waiters: deque[object] = deque()

    def acquire(self, *, timeout: float, cancel_event: Event | None = None) -> TuiProcessSlot:
        """为即将启动的进程保留一个名额，满额时按入队顺序等候。

        @param timeout 等候秒数，零表示仅尝试立即取得。
        @param cancel_event 请求取消信号；取消时移出等待队列。
        @return 独立的进程名额，由执行器保存到进程关闭。
        """
        if type(timeout) not in (int, float) or not 0 <= timeout <= TIMEOUT_MAX:
            raise ValueError(f"timeout 必须是 0 到 {TIMEOUT_MAX} 之间的秒数")
        deadline = monotonic() + timeout
        with self._condition:
            self._check_cancelled(cancel_event)
            if self._limit == 0:
                raise TuiCapacityError("capacity_unavailable")
            if timeout and monotonic() >= deadline:
                raise TuiCapacityError("capacity_timeout")
            if not self._waiters and len(self._active) < self._limit:
                return self._reserve()
            if timeout == 0 or len(self._waiters) >= self._max_waiters:
                raise TuiCapacityError("capacity_busy")

            waiter = object()
            self._waiters.append(waiter)
            try:
                while True:
                    self._check_cancelled(cancel_event)
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TuiCapacityError("capacity_timeout")
                    # 只由队首领取名额，避免新进入的请求绕过已有等待者。
                    if self._waiters[0] is waiter and len(self._active) < self._limit:
                        return self._reserve()
                    # 外部 Event 无法唤醒此 Condition，分段等候可及时兑现取消。
                    delay = min(remaining, _CANCEL_POLL_SECONDS) if cancel_event is not None else remaining
                    self._condition.wait(delay)
            finally:
                self._waiters.remove(waiter)
                self._condition.notify_all()

    def reuse(self, slot: TuiProcessSlot) -> TuiProcessSlot:
        """验证并返回原进程名额。进程或会话归属及关闭互斥由执行器管理。

        @param slot 原进程持有的名额。
        @return 同一名额；已释放或属于另一账号实例时拒绝。
        """
        with self._condition:
            if slot not in self._active:
                raise TuiCapacityError("capacity_slot_inactive")
            return slot

    def snapshot(self) -> TuiCapacitySnapshot:
        """读取线程安全的占用快照。@return 上限、占用及排队数。"""
        with self._condition:
            return TuiCapacitySnapshot(self._limit, len(self._active), len(self._waiters))

    @staticmethod
    def _check_cancelled(cancel_event: Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise TuiCapacityError("capacity_cancelled")

    def _reserve(self) -> TuiProcessSlot:
        slot = TuiProcessSlot(self)
        self._active.add(slot)
        return slot

    def _release(self, slot: TuiProcessSlot) -> None:
        with self._condition:
            if slot in self._active:
                self._active.remove(slot)
                self._condition.notify_all()
