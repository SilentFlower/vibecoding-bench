"""节点worker的逐作业输入代理，实际投递复用原终端与有限证明。"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import struct
import threading

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator

from cluster_update_gate import NodeJobThread
from cluster_execution_grants import ExecutionScope
from runtime_files import atomic_json, private_directory
from runtime_terminal_input import KEYS, send_terminal_input
from system_update_contract import safe_read, strict_json


INPUT_LIMIT = 256 * 1024
WIRE_LIMIT = 6 * INPUT_LIMIT + 4096


class WorkerInput(BaseModel):
    """受限输入请求，实际账号、容器和会话由原作业决定。

    :param operation_id: 单次投递的稳定标识。
    :param text: 原样正文，按UTF-8字节限制。
    :param keys: 原白名单按键。
    :param submit: 是否追加Enter。
    """

    model_config = ConfigDict(extra='forbid')
    operation_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    text: StrictStr = Field(default='', max_length=INPUT_LIMIT)
    keys: list[StrictStr] = Field(default_factory=list, max_length=16)
    submit: StrictBool = False

    @model_validator(mode='after')
    def validate_payload(self):
        """在持久意图前检查正文与按键上限。:return: 原请求。"""
        if len(self.text.encode()) > INPUT_LIMIT or any(key not in KEYS for key in self.keys):
            raise ValueError('节点worker输入超限或按键无效')
        return self


class NodeInputBroker:
    """一个原scope和实际token对应一个串行私有socket及持久输入账本。

    :param executor: 原节点环境文件锁与数据根。
    :param runtime: 原真实运行时。
    :param scope: 原有限证明范围。
    :param token: 原实际作业。
    :param controls: root拥有、账号只读挂载的原控制目录。
    """

    def __init__(self, executor, runtime, scope: ExecutionScope, token: str, controls: Path) -> None:
        """创建root侧端点，实际启动在调用start后进行。

        :param executor: 原节点入口。
        :param runtime: 原运行时。
        :param scope: 原不可变范围。
        :param token: 原作业token。
        :param controls: 原root控制目录。
        :return: None。
        """
        self.executor, self.runtime, self.scope, self.token = executor, runtime, scope, token
        self.job = runtime.job_for_container(token)
        self.controls, self.socket_path = controls, controls / ('input-' + scope.operation_id + '.sock')
        self.directory = executor.data / 'node-inputs' / scope.environment_id / scope.operation_id
        for directory in (executor.data / 'node-inputs', self.directory.parent, self.directory):
            private_directory(directory)
        self.lock, self.stopping = threading.RLock(), threading.Event()
        self.listener, self.thread = None, None

    def start(self) -> None:
        """绑定原只读控制目录，短proc路径避免UNIX地址长度截断。:return: None。"""
        with self.lock:
            if self.listener is not None or self.stopping.is_set():
                raise ValueError('节点输入代理已启动或关闭')
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            descriptor = os.open(self.controls, flags)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                metadata = os.fstat(descriptor)
                if metadata.st_uid != 0 or metadata.st_gid != 1000 or metadata.st_mode & 0o027:
                    raise ValueError('节点输入控制目录归属或权限无效')
                try:
                    existing = self.socket_path.lstat()
                except FileNotFoundError:
                    existing = None
                if existing is not None:
                    # 单例节点与原作业门禁已完成对账；只清理root拥有的旧socket。
                    if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid != 0:
                        raise ValueError('节点输入端点已有未知对象')
                    self.socket_path.unlink()
                listener.bind(f'/proc/self/fd/{descriptor}/' + self.socket_path.name)
                os.chown(self.socket_path, 0, 1000, follow_symlinks=False)
                self.socket_path.chmod(0o660)
                listener.listen(2)
                listener.settimeout(0.25)
                self.listener = listener
                self.thread = NodeJobThread(target=self._serve, name='node-input-' + self.scope.operation_id[:8], daemon=True)
                self.thread.start()
            except BaseException:
                listener.close()
                raise
            finally:
                os.close(descriptor)

    def _receipt(self, operation_id: str) -> dict:
        value = strict_json(safe_read(self.directory / (operation_id + '.json'), 8192, private=True), 8192)
        if (value.get('scope') != self.scope.model_dump() or value.get('operation_id') != operation_id
                or value.get('status') not in ('sent', 'not_sent', 'unknown')
                or not isinstance(value.get('payload_sha256'), str) or len(value['payload_sha256']) != 64):
            raise ValueError('节点worker原输入回执范围或状态无效')
        return value

    def receipt(self, operation_id: str) -> dict:
        """只读原输入回执，过期之后仍可查询。

        :param operation_id: 原输入标识。
        :return: 原持久回执。
        """
        request = WorkerInput(operation_id=operation_id)
        with self.lock:
            return self._receipt(request.operation_id)

    def state(self) -> dict:
        """读取未决输入定位，重启后保持同一scope。:return: 原未决标识或None。"""
        path = self.directory / 'state.json'
        if not path.exists() and not path.is_symlink():
            return {'scope': self.scope.model_dump(), 'pending_input': None}
        value = strict_json(safe_read(path, 8192, private=True), 8192)
        pending = value.get('pending_input')
        if value.get('scope') != self.scope.model_dump():
            raise ValueError('节点worker输入账本范围无效')
        if pending is not None:
            WorkerInput(operation_id=pending)
        return value

    def send(self, request: WorkerInput) -> dict:
        """意图先持久化，重复操作只返回原回执，未知阻止后续投递。

        :param request: 原受限输入。
        :return: sent、not_sent或unknown原回执。
        """
        payload = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        path = self.directory / (request.operation_id + '.json')
        with self.lock:
            if path.exists() or path.is_symlink():
                previous = self._receipt(request.operation_id)
                if previous['payload_sha256'] != payload:
                    raise ValueError('节点worker原输入正文已变化')
                return previous
            state = self.state()
            if state['pending_input'] is not None:
                pending_path = self.directory / (state['pending_input'] + '.json')
                if not pending_path.exists() or self._receipt(state['pending_input'])['status'] == 'unknown':
                    raise ValueError('节点worker原输入等待核对')
            receipt = {'scope': self.scope.model_dump(), 'operation_id': request.operation_id,
                'payload_sha256': payload, 'status': 'not_sent'}
            if self.stopping.is_set():
                atomic_json(path, receipt)
                return receipt
            with self.executor._locked(environment_id=self.scope.environment_id), self.runtime.environment_lock(self.scope.environment_id):
                try:
                    if self.stopping.is_set():
                        raise ValueError('节点worker输入端点已经关闭')
                    job = self.runtime.job_for_container(self.token)
                    if job is not self.job or job['source'] != self.scope.source or job['row']['environment_id'] != self.scope.environment_id:
                        raise ValueError('节点worker输入目标与原scope不一致')
                    self.runtime.authorize_input(job)
                except Exception:
                    atomic_json(path, receipt)
                    return receipt
                # 意图先于Docker发送；崩溃在任意落盘间隙都只能继续查询原操作。
                state['pending_input'] = request.operation_id
                atomic_json(self.directory / 'state.json', state)
                receipt['status'] = 'unknown'
                atomic_json(path, receipt)
                try:
                    send_terminal_input(self.runtime, self.token, request.operation_id,
                        request.text, request.keys, request.submit, max_bytes=INPUT_LIMIT)
                except Exception:
                    return receipt
                receipt['status'] = 'sent'
                atomic_json(path, receipt)
                state['pending_input'] = None
                atomic_json(self.directory / 'state.json', state)
                return receipt

    def _serve(self) -> None:
        while not self.stopping.is_set():
            try:
                stream, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with stream:
                try:
                    stream.settimeout(5)
                    _, uid, _ = struct.unpack('3i', stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    if uid not in (0, 1000):
                        raise ValueError('节点worker输入连接身份无效')
                    raw, deadline = bytearray(), time.monotonic() + 5
                    while True:
                        chunk = stream.recv(min(65536, WIRE_LIMIT + 1 - len(raw)))
                        if not chunk:
                            break
                        raw.extend(chunk)
                        if len(raw) > WIRE_LIMIT or time.monotonic() >= deadline:
                            raise ValueError('节点worker输入帧超限或读取超时')
                    value = strict_json(bytes(raw), WIRE_LIMIT)
                    action = value.pop('action', None)
                    if action == 'query' and set(value) == {'operation_id'}:
                        response = self.receipt(value['operation_id'])
                    elif action == 'send':
                        response = self.send(WorkerInput.model_validate(value))
                    else:
                        raise ValueError('节点worker输入动作无效')
                except Exception:
                    response = {'status': 'rejected', 'reason': '节点worker输入等待核对原回执'}
                try:
                    stream.sendall(json.dumps(response, ensure_ascii=False, separators=(',', ':')).encode())
                except OSError:
                    # 回执已经持久保存；丢失响应只允许查询同一operation。
                    pass

    def close(self) -> None:
        """关闭新输入且保持持久回执，调用者在环境锁外等待线程。:return: None。"""
        self.stopping.set()
        listener = self.listener
        if listener is not None:
            listener.close()

    def join(self, timeout: float = 6) -> None:
        """在释放环境锁之后等待端点退出，保留未知作业记录。

        :param timeout: 有界等待秒数。
        :return: None。
        """
        if self.thread is not None:
            self.thread.join(timeout)


class NodeInputs:
    """按原job创建输入代理，生命周期与实际节点运行时一致。

    :param executor: 原节点执行器。
    :param mirror: 原有限证明镜像。
    """

    def __init__(self, executor, mirror) -> None:
        """登记单例依赖。:param executor: 原节点。:param mirror: 原许可镜像。:return: None。"""
        self.executor, self.mirror = executor, mirror
        self.lock, self.brokers, self.closed = threading.RLock(), {}, False

    def prepare(self, runtime, job: dict, controls: Path) -> dict:
        """在worker实际启动前登记原作业端点。

        :param runtime: 原AccountRuntime。
        :param job: 原真实作业。
        :param controls: 原root控制目录。
        :return: 仅该次worker使用的固定socket环境变量。
        """
        scope = self.mirror.scope_for_job(job)
        with self.lock:
            if self.closed or job['token'] in self.brokers:
                raise ValueError('节点worker输入代理已存在或正在关闭')
            broker = NodeInputBroker(self.executor, runtime, scope, job['token'], controls)
            broker.start()
            self.brokers[job['token']] = broker
        return {'V3_NODE_INPUT_SOCKET': '/controls/' + job['handle'] + '/' + broker.socket_path.name}

    def release(self, job: dict) -> None:
        """实际作业收口时关闭新输入，原回执继续保留。

        :param job: 原已确认停止的实际作业。
        :return: None；环境锁内保持非阻塞。
        """
        with self.lock:
            broker = self.brokers.pop(job['token'], None)
        if broker is not None:
            broker.close()

    def close(self) -> None:
        """节点关闭时先关闭全部新输入，再有界等待后台线程。:return: None。"""
        with self.lock:
            self.closed = True
            brokers = list(self.brokers.values())
        for broker in brokers:
            broker.close()
        deadline = time.monotonic() + 6
        for broker in brokers:
            broker.join(max(0, deadline - time.monotonic()))
