"""部署级持久维护门禁与实际活动计数，独立于单账号租约。"""
from __future__ import annotations

import os
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

from system_update_contract import DEPLOYMENT_RE, safe_read, strict_json

ADMISSIONS = ContextVar('v3_update_admissions', default=())


def read_gate(directory: Path, deployment: str) -> dict:
    """读取双方共用的维护记录，损坏或缺失一律拒绝准入。

    :param directory: root 管理并只读挂载的目录。
    :param deployment: 固定部署标识。
    :return: 完整门禁。
    """
    value = strict_json(safe_read(directory / 'admission.json', 8192, private=True), 8192)
    if (set(value) != {'schema_version', 'deployment', 'operation_id', 'epoch', 'phase', 'target_release', 'revision', 'created_at'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['deployment'] != deployment or not DEPLOYMENT_RE.fullmatch(deployment)
            or value['phase'] not in ('idle', 'blocked')):
        raise ValueError('部署维护记录无效')
    for key in ('epoch', 'revision'):
        if not isinstance(value[key], str) or str(uuid.UUID(value[key])) != value[key]:
            raise ValueError('部署维护代次无效')
    if value['phase'] == 'blocked':
        if not isinstance(value['operation_id'], str) or str(uuid.UUID(value['operation_id'])) != value['operation_id']:
            raise ValueError('部署维护操作身份无效')
    elif value['operation_id'] is not None or value['target_release'] is not None:
        raise ValueError('空闲维护记录仍有操作归属')
    return value


class DeploymentGate:
    """在准入锁内登记控制活动，让外部写入门禁后的 ACK 有确定边界。"""

    def __init__(self, directory: Path | None = None, deployment: str | None = None) -> None:
        """构造私有计数器。

        :param directory: 测试可指定目录，默认使用部署环境。
        :param deployment: 测试可指定部署身份。
        :return: None。
        """
        self.directory, self.deployment = directory, deployment
        self.lock = threading.RLock()
        self.active = {}

    def state(self) -> dict:
        """在实际准入锁内取得维护状态及在途计数。

        :return: legacy 或持久门禁及进程活动。
        """
        with self.lock:
            path = self.directory or (Path(os.environ['V3_UPDATE_GATE_DIR']) if os.environ.get('V3_UPDATE_GATE_DIR') else None)
            if path is None:
                value = {'phase': 'idle', 'epoch': None, 'enabled': False}
            else:
                try:
                    value = {**read_gate(path, self.deployment or os.environ.get('V3_DEPLOYMENT_ID', '')), 'enabled': True}
                except (ValueError, OSError):
                    value = {'phase': 'reconcile', 'epoch': None, 'enabled': True}
            return {**value, 'active': len(self.active), 'activities': list(self.active.values())}

    @contextmanager
    def admission(self, source: str):
        """在同一锁内核验门禁并登记实际活动，结束时定向释放。

        :param source: 固定脱敏来源名称。
        :return: 上下文管理器；维护中抛出 RuntimeError。
        """
        identifier = uuid.uuid4().hex
        with self.lock:
            if self.state()['phase'] != 'idle':
                raise RuntimeError('平台正在维护，等待本次更新完成')
            self.active[identifier] = source
        token = ADMISSIONS.set((*ADMISSIONS.get(), identifier))
        try:
            yield
        finally:
            ADMISSIONS.reset(token)
            with self.lock:
                self.active.pop(identifier, None)

    def continuing(self) -> bool:
        """核对本调用链是否持有维护前已经登记的活动。

        :return: 原活动仍在本进程登记时为 True。
        """
        with self.lock:
            return any(identifier in self.active for identifier in ADMISSIONS.get())

    def proof(self) -> str | None:
        """读取当前有限调用链仍被登记的私有证明身份。

        :return: 私有活动 ID，或 None。
        """
        with self.lock:
            return next((identifier for identifier in reversed(ADMISSIONS.get()) if identifier in self.active), None)

    def reserve(self, source: str) -> str | None:
        """登记跨请求的真实作业，结束时由原作业定向释放。

        :param source: 不可复用的原执行来源。
        :return: 启用底座时的私有活动 ID。
        """
        with self.lock:
            state = self.state()
            if not state['enabled']:
                return None
            if state['phase'] != 'idle' and not self.continuing():
                raise RuntimeError('平台维护中，新的作业等待更新完成')
            identifier = uuid.uuid4().hex
            self.active[identifier] = 'job:' + source
            return identifier

    def release_reserved(self, identifier: str | None) -> None:
        """按真实作业身份定向释放登记。

        :param identifier: 原活动 ID。
        :return: None。
        """
        with self.lock:
            self.active.pop(identifier, None)

    @contextmanager
    def continue_reserved(self, identifier: str):
        """为原登录确认等后续请求派生有限证明，拒绝已撤销的原作业。

        :param identifier: 原作业活动 ID。
        :return: 有限续接上下文。
        """
        with self.lock:
            if identifier not in self.active:
                raise RuntimeError('原作业登记已经失效')
            child = uuid.uuid4().hex
            self.active[child] = 'continuation'
        token = ADMISSIONS.set((*ADMISSIONS.get(), child))
        try:
            yield
        finally:
            ADMISSIONS.reset(token)
            self.release_reserved(child)


UPDATE_GATE = DeploymentGate()


def update_open() -> bool:
    """查询当前业务是否允许新认领。

    :return: 已明确空闲时为 True。
    """
    return UPDATE_GATE.state()['phase'] == 'idle'


def background_activity(function):
    """包装后台有限活动，维护期间保留原计划等待下次扫描。

    :param function: 同步后台扫描入口。
    :return: 保持原签名的包装函数。
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            activity = UPDATE_GATE.admission('background:' + function.__qualname__)
            activity.__enter__()
        except RuntimeError:
            return None
        try:
            return function(*args, **kwargs)
        finally:
            activity.__exit__(None, None, None)
    return wrapped


def scheduled_activity(function):
    """让已持久排队的有限任务等待门禁开放，避免维护造成业务失败。

    :param function: Scheduler 的有限执行或单项投放事务；整批等待不持有活动。
    :return: 可随调度器停止事件退出的包装函数。
    """
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        while not self._window_stop.is_set():
            try:
                activity = UPDATE_GATE.admission('scheduler:' + function.__name__)
                activity.__enter__()
                break
            except RuntimeError:
                self._window_stop.wait(0.5)
        else:
            return None
        try:
            return function(self, *args, **kwargs)
        finally:
            activity.__exit__(None, None, None)
    return wrapped
