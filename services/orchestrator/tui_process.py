"""账号内交互进程的启动、续轮和退出回收。"""

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from subprocess import Popen, TimeoutExpired
from threading import Event, Lock, Thread, TIMEOUT_MAX
from uuid import uuid4

from tui_capacity import TuiCapacity, TuiCapacityError, TuiProcessSlot


class TuiProcessError(RuntimeError):
    """会话占用或进程归属错误。@param code 可供发送器映射的固定原因。"""

    def __init__(self, code: str) -> None:
        """保存原因。@param code 固定错误码。@return 无。"""
        super().__init__(code)
        self.code = code


@dataclass(eq=False, slots=True)
class TuiProcessHandle:
    """仅供受信调用方持有的会话代次，生命周期结束后只保留退出码。

    @param _owner 执行器私有身份。
    @param _session_id 已授权会话的标识。
    """

    _owner: object
    _session_id: str
    _generation: str = field(default_factory=lambda: str(uuid4()), init=False)
    _returncode: int | None = field(default=None, init=False)

    @property
    def generation(self) -> str:
        """标识这一次进程启动。@return 本代固定的 UUID 字符串。"""
        return self._generation


@dataclass(slots=True)
class _Running:
    """账号执行器在子进程生存期间持有的资源。"""

    handle: TuiProcessHandle
    process: Popen
    slot: TuiProcessSlot
    cancel_event: Event | None
    close_lock: Lock = field(default_factory=Lock)
    closing: bool = False


class TuiProcessExecutor:
    """管理单个账号的交互进程，一个活动会话最多拥有一个子进程。

    @param capacity 本账号的共享容量。
    @param spawn 受信工厂，按服务端会话标识选取固定启动参数、显式环境及私有通信端点。
        工厂成功时交付直属 Popen，抛错前须自行收回它已创建的资源。PTY 主端及私有管道
        由调用方管理。工厂负责让子树跟随直属进程退出，例如以该进程监督独立 PID 命名空间。
    @param terminate_grace 在强制结束直属进程前允许的退出秒数。
    """

    def __init__(self, capacity: TuiCapacity, spawn: Callable[[str], Popen], *, terminate_grace: float = 1.0) -> None:
        """绑定账号及启动工厂。

        @param capacity 账号容量。
        @param spawn 以会话标识区分私有环境的受信进程工厂。
        @param terminate_grace 正常终止后的宽限秒数。
        @return 无。
        """
        if type(terminate_grace) not in (int, float) or not 0 <= terminate_grace <= TIMEOUT_MAX:
            raise ValueError('terminate_grace 超出允许的等待范围')
        self._capacity = capacity
        self._spawn = spawn
        self._terminate_grace = terminate_grace
        self._owner = object()
        self._lock = Lock()
        self._sessions: dict[str, _Running | None] = {}

    def start(self, session_id: str, *, timeout: float, cancel_event: Event | None = None) -> TuiProcessHandle:
        """在取得名额后启动该会话的交互进程。

        @param session_id 来自已授权调用方的会话标识，仅作为匹配键。
        @param timeout 排队超时秒数，零表示立即尝试。
        @param cancel_event 整个进程生命周期的取消信号，含排队及运行期间。
        @return 本次启动的句柄。
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError('会话标识必须是非空字符串')
        with self._lock:
            if session_id in self._sessions:
                raise TuiProcessError('tui_session_in_use')
            # 先占会话名，防止相同会话同时排入名额队列，并在前一轮结束后意外重启。
            self._sessions[session_id] = None

        slot = None
        started: Future[TuiProcessHandle] = Future()
        try:
            slot = self._capacity.acquire(timeout=timeout, cancel_event=cancel_event)
            handle = TuiProcessHandle(self._owner, session_id)
            if cancel_event is not None and cancel_event.is_set():
                raise TuiCapacityError('capacity_cancelled')
            # Linux 的父线程退出信号跟随执行 spawn 的线程。交由原本负责回收的线程启动，
            # 使首轮 HTTP 返回后，原生 TUI 仍能等候同一会话的工具结果。
            Thread(target=self._launch_and_watch, args=(handle, slot, cancel_event, started),
                   name='tui-process-owner', daemon=True).start()
        except BaseException:
            self._release_pending(session_id, slot)
            raise

        try:
            started.result()
            if cancel_event is not None and cancel_event.is_set():
                raise TuiCapacityError('capacity_cancelled')
        except BaseException:
            # 等待者提前退出时，被取消的交接由启动线程收口；已交接的进程仍由 close 等待退出。
            if not started.cancel() and started.exception() is None:
                self.close(handle)
            raise
        return handle

    def _release_pending(self, session_id: str, slot: TuiProcessSlot | None) -> None:
        with self._lock:
            del self._sessions[session_id]
            if slot is not None:
                slot.release_after_close()

    def _launch_and_watch(self, handle: TuiProcessHandle, slot: TuiProcessSlot,
                          cancel_event: Event | None, started: Future[TuiProcessHandle]) -> None:
        try:
            if started.cancelled() or (cancel_event is not None and cancel_event.is_set()):
                raise TuiCapacityError('capacity_cancelled')
            process = self._spawn(handle._session_id)
        except BaseException as error:
            self._release_pending(handle._session_id, slot)
            if started.set_running_or_notify_cancel():
                started.set_exception(error)
            return
        running = _Running(handle, process, slot, cancel_event)
        with self._lock:
            self._sessions[handle._session_id] = running
        if started.set_running_or_notify_cancel():
            started.set_result(handle)
        else:
            try:
                self.close(handle)
            except OSError:
                # 关闭信号失败时仍须等到进程退出才释放名额。
                pass
        self._watch(running)

    def resume(self, session_id: str, handle: TuiProcessHandle) -> Popen:
        """校验会话、活跃代次及名额，交还原进程供调用方继续通信。

        @param session_id 本次请求已获准续传的会话。
        @param handle 首轮取得的进程句柄。
        @return 同一个直属子进程，退出与取消可在返回后发生。
        """
        with self._lock:
            running = self._sessions.get(session_id)
            if running is None or running.handle is not handle or running.closing:
                raise TuiProcessError('tui_process_inactive')
            cancelled = running.cancel_event is not None and running.cancel_event.is_set()
            if cancelled or running.process.poll() is not None:
                raise TuiProcessError('tui_process_inactive')
            self._capacity.reuse(running.slot)
            return running.process

    def close(self, handle: TuiProcessHandle) -> int:
        """终止句柄对应的进程并等候回收；并发或重复调用返回同一退出码。

        @param handle 此执行器签发的进程句柄。
        @return 原进程的退出码，信号导致的退出以负数表示。
        """
        with self._lock:
            if not isinstance(handle, TuiProcessHandle) or handle._owner is not self._owner:
                raise TuiProcessError('tui_process_inactive')
            if handle._returncode is not None:
                return handle._returncode
            running = self._sessions.get(handle._session_id)
            if running is None or running.handle is not handle:
                raise TuiProcessError('tui_process_inactive')
            running.closing = True

        # 每个进程独立执行终止和升级信号，避免慢退回收阻塞其它会话的续轮。
        with running.close_lock:
            process = running.process
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=self._terminate_grace)
                except TimeoutExpired:
                    process.kill()
            return self._retire(running, process.wait())

    def _watch(self, running: _Running) -> None:
        if running.cancel_event is not None:
            # 外部 Event 无法直接唤醒 waitpid，按短间隔观察自然退出且可立即响应取消。
            while running.process.poll() is None:
                if running.cancel_event.wait(0.05):
                    try:
                        self.close(running.handle)
                    except OSError:
                        # 信号发送失败时名额仍属于活进程，保留 wait 以回收其后自然退出或显式重试。
                        break
                    return
        self._retire(running, running.process.wait())

    def _retire(self, running: _Running, code: int) -> int:
        with self._lock:
            handle = running.handle
            if handle._returncode is None:
                # 监护线程和 close 可能同时得到退出码；先清会话，再唤醒等待该名额的请求。
                handle._returncode = code
                del self._sessions[handle._session_id]
                running.slot.release_after_close()
        return code
