#!/usr/bin/env python3
"""对已准入的直属原生工作进程作只读 TLS 采集，以 JSONL 私有管道收口。"""
import argparse
import ctypes as c
import hashlib
import json
import os
import select
from pathlib import Path
import struct
import sys

from http_capture import HttpCapture, unavailable

IMAGE_SHA256 = 'af4cea9e21aa959c5e39c389173ba30ebb19b354b67acfe99164946450e9776d'
WRITE_OFFSET = 0x232D5B3
WRITE_BYTES = bytes.fromhex('4883c4185b415c415d415e415f5dc3')
SAMPLE = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_void_p, c.c_size_t)


class CaptureError(Exception):
    """只携带固定诊断码，禁止异常原文流入日志。"""


def _checked(value, reason):
    if not value or isinstance(value, int) and value < 0:
        raise CaptureError(reason)
    return value


class Observer:
    """拥有单个目标 PID 的 BPF 对象、探针和有界 HTTP 状态。"""

    def __init__(self, pid: int, image: str, owner: int | None = None, started: str | None = None) -> None:
        """核验固定执行体并装载探针。

        @param pid 本账号sender直属worker的实际PID。
        @param image 已准入的完整执行体SHA。
        @param owner 可信broker指定的sender PID；省略时使用观察器的实际父进程。
        @param started broker冻结的进程启动时刻；省略时沿用独立运行模式。
        @return None；归属、映像或加载校验失败抛出固定诊断码。
        """
        self.lib = None
        self.obj = self.link = self.ring = None
        self.pid = pid
        self.connections = {}
        self.writes = self.accepted = 0
        self.reason = None
        if image != IMAGE_SHA256:
            raise CaptureError('IMAGE_NOT_ADMITTED')
        try:
            status = Path(f'/proc/{pid}/status').read_text()
            if f'PPid:\t{owner if owner is not None else os.getppid()}\n' not in status:
                raise CaptureError('WORKER_OWNERSHIP')
            if started is not None and Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19] != started:
                raise CaptureError('WORKER_OWNERSHIP')
            with open(f'/proc/{pid}/exe', 'rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
                source.seek(WRITE_OFFSET)
                if digest != image or source.read(len(WRITE_BYTES)) != WRITE_BYTES:
                    raise CaptureError('IMAGE_MISMATCH')
        except OSError:
            raise CaptureError('WORKER_UNAVAILABLE') from None
        self.lib = c.CDLL('libbpf.so.1', use_errno=True)
        for name, args, result in (
            ('bpf_object__open_file', [c.c_char_p, c.c_void_p], c.c_void_p),
            ('bpf_object__load', [c.c_void_p], c.c_int),
            ('bpf_object__find_program_by_name', [c.c_void_p, c.c_char_p], c.c_void_p),
            ('bpf_object__find_map_fd_by_name', [c.c_void_p, c.c_char_p], c.c_int),
            ('bpf_program__attach_uprobe', [c.c_void_p, c.c_bool, c.c_int, c.c_char_p, c.c_size_t], c.c_void_p),
            ('ring_buffer__new', [c.c_int, SAMPLE, c.c_void_p, c.c_void_p], c.c_void_p),
            ('ring_buffer__poll', [c.c_void_p, c.c_int], c.c_int),
            ('ring_buffer__consume', [c.c_void_p], c.c_int),
            ('ring_buffer__free', [c.c_void_p], None),
            ('bpf_link__destroy', [c.c_void_p], c.c_int),
            ('bpf_object__close', [c.c_void_p], None),
            ('bpf_map_lookup_elem', [c.c_int, c.c_void_p, c.c_void_p], c.c_int),
            ('bpf_map_update_elem', [c.c_int, c.c_void_p, c.c_void_p, c.c_ulonglong], c.c_int),
        ):
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        try:
            path = str(Path(__file__).resolve().with_name('capture.bpf.o')).encode()
            self.obj = _checked(self.lib.bpf_object__open_file(path, None), 'PROBE_ARTIFACT')
            if self.lib.bpf_object__load(self.obj):
                raise CaptureError('BPF_LOAD_FAILED')
            namespace = Path('/proc/self/ns/pid').stat()
            config = c.create_string_buffer(struct.pack('<QQII', namespace.st_dev, namespace.st_ino, pid, 0))
            key = c.c_uint(0)
            fd = self.lib.bpf_object__find_map_fd_by_name(self.obj, b'config')
            if fd < 0 or self.lib.bpf_map_update_elem(fd, c.byref(key), config, 0):
                raise CaptureError('WORKER_OWNERSHIP')
            program = _checked(self.lib.bpf_object__find_program_by_name(self.obj, b'capture'), 'PROBE_ARTIFACT')
            self.callback = SAMPLE(self._sample)
            fd = self.lib.bpf_object__find_map_fd_by_name(self.obj, b'events')
            if fd < 0:
                raise CaptureError('PROBE_ARTIFACT')
            self.ring = _checked(self.lib.ring_buffer__new(fd, self.callback, None, None), 'RING_UNAVAILABLE')
            self.link = _checked(self.lib.bpf_program__attach_uprobe(program, False, pid,
                                  f'/proc/{pid}/exe'.encode(), WRITE_OFFSET), 'PROBE_ATTACH_FAILED')
        except Exception:
            self.close()
            raise

    def _sample(self, context, pointer, size):
        try:
            if size not in (16416, 65568, 262176, 1048608, 4194336, 8388640):
                raise CaptureError('EVENT_INVALID')
            raw = c.string_at(pointer, 32)
            pid_tid, ssl, sequence, accepted, requested = struct.unpack_from('<QQQII', raw)
            if pid_tid >> 32 != self.pid or not 0 < accepted <= min(requested, size - 32):
                raise CaptureError('EVENT_OWNERSHIP')
            if sequence != self.writes + 1:
                self.reason = 'EVENT_SEQUENCE'
            self.writes += 1
            self.accepted += accepted
            # 事件序号覆盖整个采集代次；一处缺口后停止所有连接的解析，计数仍用于最终对账。
            if self.reason:
                return 0
            if ssl not in self.connections:
                if len(self.connections) >= 8:
                    raise CaptureError('CONNECTION_LIMIT')
                self.connections[ssl] = HttpCapture()
            # 大事件只复制真实接受范围，避免Python再复制容量档位的空闲尾部。
            self.connections[ssl].feed(c.string_at(c.cast(pointer, c.c_void_p).value + 32, accepted))
        except CaptureError as error:
            self.reason = str(error)
        except Exception:
            self.reason = 'EVENT_INVALID'
        return 0

    def poll(self) -> None:
        """有界消费可用副本。@return None；内核通道失败抛固定码。"""
        if self.lib.ring_buffer__poll(self.ring, 10) < 0:
            raise CaptureError('RING_FAILED')

    def finish(self, client_id: str) -> dict:
        """卸载后对账并选择同次HTTP。@param client_id 组装头的请求ID。@return 原生接受证据。"""
        if self.link:
            if self.lib.bpf_link__destroy(self.link):
                self.reason = 'PROBE_DETACH_FAILED'
            self.link = None
        if self.lib.ring_buffer__consume(self.ring) < 0:
            self.reason = 'RING_FAILED'
        key, counts = c.c_uint(0), (c.c_ulonglong * 5)()
        fd = self.lib.bpf_object__find_map_fd_by_name(self.obj, b'stats')
        if fd < 0 or self.lib.bpf_map_lookup_elem(fd, c.byref(key), counts):
            self.reason = 'COUNTS_UNAVAILABLE'
        elif list(counts) != [self.writes, self.accepted, 0, 0, 0]:
            self.reason = 'EVENT_LOSS'
        matches = [(ssl, state) for ssl, state in self.connections.items() if state.client_id() == client_id]
        if len(matches) == 1:
            ssl, state = matches[0]
            result = state.evidence(self.reason)
            result['connection_id'] = hex(ssl)
        else:
            result = unavailable(self.reason or ('REQUEST_AMBIGUOUS' if matches else 'REQUEST_NOT_OBSERVED'))
        result.update(worker_pid=self.pid, accepted_write_count=self.writes,
                      write_counts=dict(zip(('writes', 'bytes', 'dropped', 'read_errors', 'oversized'), counts)))
        return result

    def close(self) -> None:
        """释放全部内核对象，适用于半初始化及正常退出。@return None。"""
        if self.link:
            self.lib.bpf_link__destroy(self.link)
            self.link = None
        if self.ring:
            self.lib.ring_buffer__free(self.ring)
            self.ring = None
        if self.obj:
            self.lib.bpf_object__close(self.obj)
            self.obj = None


def _write(value):
    value = {'schema_version': 1, **value}
    sys.stdout.write(json.dumps(value, separators=(',', ':'), ensure_ascii=False) + '\n')
    sys.stdout.flush()


def main() -> None:
    """执行单次作业私有协议；EOF立即释放。@return None。"""
    parser = argparse.ArgumentParser(description='原生 TLS 接受边界旁路采集')
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--worker', required=True)
    parser.add_argument('--capture', required=True)
    parser.add_argument('--owner', type=int)
    parser.add_argument('--started')
    args = parser.parse_args()
    observer = None
    try:
        observer = Observer(args.pid, args.image, args.owner, args.started)
        # 加载阶段结束后清零权限；后续只持有已归属的探针和映射FD。
        header = (c.c_uint * 2)(0x20080522, 0)
        capabilities = (c.c_uint * 6)()
        libc = c.CDLL(None, use_errno=True)
        if (libc.prctl(47, 4, 0, 0, 0) or libc.capset(c.byref(header), c.byref(capabilities))
                or libc.prctl(38, 1, 0, 0, 0)):
            raise CaptureError('OBSERVER_CONFIGURATION')
        _write({'ready': True, 'capture_id': args.capture, 'worker_id': args.worker})
        while True:
            observer.poll()
            if select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.buffer.readline(4097)
                if not line:
                    return
                if len(line) > 4096 or not line.endswith(b'\n'):
                    raise CaptureError('COMMAND_INVALID')
                command = json.loads(line)
                client = command.get('client_request_id')
                if (command.get('capture_id') != args.capture or not isinstance(client, str)
                        or not 1 <= len(client) <= 128 or any(ord(char) < 33 or ord(char) > 126 for char in client)):
                    raise CaptureError('COMMAND_INVALID')
                result = observer.finish(client)
                result.update(capture_id=args.capture, worker_id=args.worker)
                _write(result)
                return
            if not Path(f'/proc/{args.pid}').exists():
                raise CaptureError('WORKER_UNAVAILABLE')
    except BrokenPipeError:
        pass
    except Exception as error:
        reason = str(error) if isinstance(error, CaptureError) else 'OBSERVER_FAILED'
        result = unavailable(reason)
        result.update(capture_id=args.capture, worker_id=args.worker, worker_pid=args.pid)
        _write(result)
    finally:
        if observer:
            observer.close()


if __name__ == '__main__':
    main()
