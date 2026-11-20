"""接管只有启动状态的 AGY 单次恢复租约。"""
import json
import os
import select
import signal
import socket
import struct
import subprocess
import time

CONTROL = '/run/ccrb-criu/agy.sock'
_IMAGE_FAILURES = ('execution_file_identity', 'execution_source_checksum', 'execution_mapping_reference',
    'execution_mapping_missing', 'execution_mapping_writable_shared', 'execution_mapping_ambiguous',
    'execution_site_0', 'execution_site_1', 'execution_site_2', 'execution_site_3')
_FAILURE_REASONS = {
    'worker_start': ('worker_start_failed',),
    'observer_start': ('observer_start_failed', *_IMAGE_FAILURES),
    'native_listener': ('listener_failed', 'native_listener_identity_timeout', 'native_listener_identity_conflict'),
    'controller_connect': ('controller_unavailable', 'AGY_CRIU_PEER', 'AGY_CRIU_OWNER', 'AGY_CRIU_IMAGE', 'AGY_CRIU_PIPES'),
    'checkpoint_stop': ('stop_failed', 'agy_criu_stop'),
    'checkpoint_dump': ('dump_failed', 'AGY_CRIU_DUMP', 'AGY_CRIU_STOP'),
    'checkpoint_restore': ('restore_failed', 'AGY_CRIU_RESTORE', 'AGY_CRIU_OWNER', 'AGY_CRIU_IMAGE', 'agy_criu_identity'),
    'observer_resume': ('observer_resume_failed', *_IMAGE_FAILURES),
    'restore_listener': ('listener_failed', 'agy_criu_listener'),
}


def failure_detail(stage: str, reason: object = None) -> dict[str, str]:
    """投影当前阶段的受控失败原因。@param stage 已核对阶段。@param reason 内部候选错误。@return 脱敏阶段和原因。"""
    allowed = _FAILURE_REASONS[stage]
    return {'stage': stage, 'reason': reason if isinstance(reason, str) and reason in allowed else allowed[0]}


def read_failure(value: object) -> dict[str, str] | None:
    """核对来自私有事件或状态的诊断。@param value 原投影。@return 白名单诊断或空。"""
    if not isinstance(value, dict) or set(value) != {'stage', 'reason'}:
        return None
    stage, reason = value['stage'], value['reason']
    if isinstance(stage, str) and isinstance(reason, str) and reason in _FAILURE_REASONS.get(stage, ()):
        return {'stage': stage, 'reason': reason}
    return None


class RestoredObserver:
    """恢复后的观察器由控制器收口，内核保留原事件管道。"""

    def __init__(self, pid, stdout, lease):
        """绑定实际PID与旧管道。@param pid 已核对观察器。@param stdout 原 stdout。@param lease 根控制器连接。@return 无。"""
        self.pid = pid
        self.stdout = stdout
        self.lease = lease
        self.descriptor = os.pidfd_open(pid)
        self.returncode = None

    def poll(self):
        """读取真实退出状态。@return 活动为空，已退出为0。"""
        if select.select([self.descriptor], [], [], 0)[0]:
            self.returncode = 0
        return self.returncode

    def wait(self, timeout=None):
        """等待实际退出。@param timeout 秒预算。@return 已退出为0。"""
        if not select.select([self.descriptor], [], [], timeout)[0]:
            raise subprocess.TimeoutExpired('AGY observer', timeout)
        self.returncode = 0
        return self.returncode

    def release(self):
        """撤销原生和观察器租约，等待控制器杀掉仍在运行的实例。@return 无。"""
        self.lease.close()

    def close(self):
        """关闭租约和本地描述符。@return 无。"""
        self.release()
        os.close(self.descriptor)


class Template:
    """封存原生进程和观察器的启动状态，只由同一个私有内核消费一次。"""

    def __init__(self, bridge):
        """绑定实际启动观察。@param bridge 本代原生桥。@return 无。"""
        self.bridge = bridge
        self.connection = socket.socket(socket.AF_UNIX)
        self.parked = False
        self.suspended = False
        self.stage = 'controller_connect'

    def read(self, kind, until):
        """核对控制器单帧答复。@param kind 期待状态。@param until 原单调截止。@return 受控回执。"""
        data = bytearray()
        while len(data) < 4096:
            remaining = until - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('agy_criu_deadline')
            self.connection.settimeout(remaining)
            part = self.connection.recv(1)
            if not part:
                break
            data.extend(part)
            if part == b'\n':
                value = json.loads(data)
                if isinstance(value, dict) and value.get('type') == kind:
                    return value
                if isinstance(value, dict) and value.get('type') == 'unavailable':
                    raise ValueError(failure_detail(self.stage, value.get('reason'))['reason'])
                break
        raise ValueError('agy_criu_receipt')

    def send(self, message, until):
        """发送私有阶段指令。@param message 固定控制对象。@param until 原单调截止。@return 无。"""
        remaining = until - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('agy_criu_deadline')
        self.connection.settimeout(remaining)
        self.connection.sendall(json.dumps(message).encode() + b'\n')

    def park(self, until):
        """真实观察器停止后生成快照并收回原进程。@param until 原单调截止。@return 保存耗时。"""
        bridge = self.bridge
        self.connection.settimeout(max(.001, until - time.monotonic()))
        self.connection.connect(CONTROL)
        peer = self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
        _, uid, _ = struct.unpack('3i', peer)
        if uid:
            raise ValueError('agy_criu_owner')
        self.send({'type': 'template', 'observer': bridge.proc.pid, 'native': bridge.native_pid}, until)
        self.read('accepted', until)
        self.stage = 'checkpoint_stop'
        self.suspended = True
        os.kill(bridge.proc.pid, signal.SIGUSR1)
        if not bridge.checkpoint_stopped.wait(max(0, until - time.monotonic())):
            raise TimeoutError('agy_criu_stop')
        self.stage = 'checkpoint_dump'
        self.send({'type': 'dump'}, until)
        receipt = self.read('template_ready', until)
        bridge.proc.wait(timeout=max(0, until - time.monotonic()))
        self.parked = True
        return receipt['dump_ms']

    def restore(self, until):
        """重新确认真实观察后返回。@param until 原单调截止。@return 恢复耗时。"""
        bridge = self.bridge
        self.stage = 'checkpoint_restore'
        self.send({'type': 'restore'}, until)
        receipt = self.read('restored', until)
        if receipt['observer'] != bridge.proc.pid or receipt['native'] != bridge.native_pid:
            raise ValueError('agy_criu_identity')
        self.stage = 'observer_resume'
        bridge.proc = RestoredObserver(receipt['observer'], bridge.proc.stdout, self.connection)
        signal.pidfd_send_signal(bridge.proc.descriptor, signal.SIGUSR2)
        signal.pidfd_send_signal(bridge.proc.descriptor, signal.SIGCONT)
        if not bridge.checkpoint_resumed.wait(max(0, until - time.monotonic())):
            raise TimeoutError('agy_criu_observer')
        self.parked = False
        self.suspended = False
        return receipt['restore_ms']

    def close(self):
        """放弃模板或撤销恢复租约。@return 无。"""
        self.connection.close()
