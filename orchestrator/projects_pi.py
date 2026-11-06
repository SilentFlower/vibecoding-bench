"""通过有界 JSONL 管道托管真实 Pi SDK，账号控制权留在 Python 所有者。"""
from __future__ import annotations

import json
import math
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from stat import S_ISREG


PI_FAILURE_MESSAGES = {
    'stream_incomplete': 'Pi 模型响应中断，未收到正常结束标记',
    'model_response_error': 'Pi 模型返回了无法完成的响应',
    'controller_interrupted': 'Pi 指挥进程意外退出',
    'model_authentication': 'Pi 模型认证失败，请检查模型 API 密钥后重新启动',
    'model_permission': 'Pi 模型权限不足，请核对模型权限后重新启动',
    'provider_retry_forbidden': 'Pi 上游明确禁止自动重试，请核对模型服务后重新启动',
    'provider_retry_invalid': 'Pi 上游重试等待时间无效，请检查模型服务后重新启动',
    'model_request_invalid': 'Pi 模型请求被拒绝或响应不兼容，请核对模型及工具调用配置后重新启动',
    'pi_protocol_error': 'Pi 通信协议异常，请检查运行时版本后重新启动',
    'pi_initialization': 'Pi 尚未就绪便退出，请检查运行时及模型配置后重新启动',
    'execution_unconfirmed': 'CLI 执行收口未确认，原环境和租约已保留，请完成环境对账后恢复',
}


def diagnose_stream_failure(directory: Path, session_file: str, error_at: float) -> str | None:
    """只读核对旧错误对应的原 Pi 会话，不扫描完整历史或发布执行。

    :param directory: 服务端派生的本账号、本空间会话目录。
    :param session_file: 原控制者已登记的会话文件。
    :param error_at: 待诊断原错误的 UTC 秒。
    :return: 已证实的断流故障码；证据缺失、不匹配或读取失败时为 None。
    """
    try:
        path = Path(session_file)
        if (directory.is_symlink() or path.parent != directory or path.is_symlink()
                or type(error_at) not in (int, float) or not math.isfinite(error_at)):
            return None
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not S_ISREG(before.st_mode) or before.st_nlink != 1:
                return None
            header_line = stream.readline(8193)
            if not header_line.endswith(b'\n') or len(header_line) > 8192:
                return None
            header = json.loads(header_line)
            if (not isinstance(header, dict) or header.get('type') != 'session'
                    or header.get('cwd') != str(directory)):
                return None
            limit = 512 * 1024
            offset = max(len(header_line), before.st_size - limit)
            stream.seek(offset)
            if offset > len(header_line):
                # 尾部可能落在大条目中间，只接受其后的完整 JSONL 记录。
                stream.readline(limit)
            tail = stream.read(limit)
            after = os.fstat(stream.fileno())
        if (not tail.endswith(b'\n') or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)):
            return None
        for line in reversed(tail.splitlines()):
            entry = json.loads(line)
            if not isinstance(entry, dict):
                return None
            if entry.get('type') != 'message':
                continue
            message = entry.get('message')
            if (not isinstance(message, dict) or message.get('role') != 'assistant'
                    or message.get('provider') != 'projects' or message.get('stopReason') != 'error'
                    or message.get('errorMessage') != 'Stream ended without finish_reason'):
                return None
            if not isinstance(entry.get('timestamp'), str):
                return None
            timestamp = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
            if timestamp.tzinfo is None or abs(timestamp.timestamp() - error_at) > 5:
                return None
            return 'stream_incomplete'
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None
    return None


class ProjectsPi:
    """为一个账号运行一个 Pi 子进程，不向模型提供宿主 shell。

    :param host: 安装了依赖的 Pi SDK 入口脚本。
    """

    def __init__(self, host: Path | None = None) -> None:
        """定位已锁定依赖的入口，不自动下载或安装软件。

        :param host: 测试或部署可指定的入口。
        :return: None。
        """
        local = Path(__file__).resolve().parents[1] / 'images/pi-agent/host.mjs'
        self.host = host or Path(os.environ.get('PROJECTS_PI_HOST', str(local if local.exists() else '/opt/pi-agent/host.mjs')))

    def available(self) -> bool:
        """确认当前运行环境具备实际 Pi SDK。

        :return: Node、脚本与安装依赖是否均存在。
        """
        return bool(shutil.which('node') and self.host.is_file()
            and (self.host.parent / 'node_modules/@earendil-works/pi-coding-agent/package.json').is_file())

    def run(self, configuration: dict, tools, event, stop: threading.Event, timeout_sec: int) -> str:
        """持续处理 Pi 的真实工具调用、回复与用量，停止时中止子进程。

        :param configuration: 含内存凭据的私有配置，不写日志。
        :param tools: 校验并执行工具的回调。
        :param event: 持久化公开事件的回调。
        :param stop: 当前账号的取消信号。
        :param timeout_sec: 本次指挥的总时限。
        :return: settled、stopped、timeout 或 error。
        """
        if not self.available():
            raise ValueError('Pi SDK 尚未安装，请使用包含 Pi 运行时的新管理镜像')
        environment = {key: value for key, value in os.environ.items()
            if key in ('PATH', 'LANG', 'LC_ALL', 'TZ', 'NODE_EXTRA_CA_CERTS')}
        environment.update(HOME=configuration['session_dir'], PI_SKIP_VERSION_CHECK='1', PI_TELEMETRY='0')
        process = subprocess.Popen(['node', str(self.host)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=environment)
        records = queue.Queue(maxsize=128)
        protocol_failed = threading.Event()

        def read_records():
            try:
                while True:
                    line = process.stdout.readline(2 * 1024 * 1024 + 1)
                    if not line:
                        break
                    if len(line) > 2 * 1024 * 1024 or not line.endswith(b'\n'):
                        raise ValueError('Pi 输出超过管道上限')
                    value = json.loads(line)
                    if not isinstance(value, dict) or value.get('type') not in (
                            'ready', 'tool', 'assistant', 'context', 'recovery', 'settled', 'error'):
                        raise ValueError('Pi 输出协议无效')
                    records.put(value, timeout=5)
            except (OSError, ValueError, queue.Full):
                protocol_failed.set()
            finally:
                try:
                    records.put(None, timeout=5)
                except queue.Full:
                    pass

        reader = threading.Thread(target=read_records, daemon=True)
        reader.start()
        expired = threading.Event()

        def expire():
            expired.set()
            stop.set()

        timer = threading.Timer(timeout_sec, expire)
        timer.daemon = True
        timer.start()
        outcome, calls, ready = 'error', 0, False

        def interrupted() -> str:
            """投影已确认的管道退出；取消和未知协议不能自动恢复。:return: 本轮结果。"""
            if stop.is_set():
                return 'timeout' if expired.is_set() else 'stopped'
            code = 'pi_protocol_error' if protocol_failed.is_set() else 'controller_interrupted' if ready else 'pi_initialization'
            event({'type': 'error', 'reason': 'model_unavailable' if code == 'controller_interrupted' else 'provider_request_error',
                'code': code, 'message': PI_FAILURE_MESSAGES[code]})
            return 'error'

        try:
            process.stdin.write((json.dumps({'type': 'configure', **configuration}, ensure_ascii=False) + '\n').encode())
            process.stdin.flush()
            deadline = time.monotonic() + timeout_sec
            while not stop.is_set() and time.monotonic() < deadline:
                try:
                    record = records.get(timeout=0.5)
                except queue.Empty:
                    continue
                if record is None:
                    outcome = interrupted()
                    break
                if record.get('type') == 'tool':
                    calls += 1
                    if calls > 1000:
                        event({'type': 'error', 'message': '本次 Pi 工具调用达到上限，已保留现场'})
                        break
                    result = tools(record['name'], record.get('args', {}), record['tool_call_id'])
                    if stop.is_set():
                        outcome = 'timeout' if expired.is_set() else 'stopped'
                        break
                    process.stdin.write((json.dumps({'type': 'tool_result', 'id': record['id'],
                        'result': result}, ensure_ascii=False) + '\n').encode())
                    process.stdin.flush()
                else:
                    event(record)
                    if record.get('type') == 'ready':
                        ready = True
                    if record.get('type') in ('settled', 'error'):
                        outcome = record['type']
                        break
            else:
                outcome = 'timeout' if expired.is_set() or not stop.is_set() else 'stopped'
            return outcome
        except BrokenPipeError:
            # 工具回执已确认后子进程退出，只重建指挥者，不重复执行该工具。
            return interrupted()
        finally:
            timer.cancel()
            try:
                process.stdin.write(b'{"type":"abort"}\n')
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            process.stdout.close()
            reader.join(timeout=1)
