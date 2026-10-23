"""通过有界 JSONL 管道托管真实 Pi SDK，账号控制权留在 Python 所有者。"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path


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

        def read_records():
            try:
                while True:
                    line = process.stdout.readline(2 * 1024 * 1024 + 1)
                    if not line:
                        break
                    if len(line) > 2 * 1024 * 1024 or not line.endswith(b'\n'):
                        raise ValueError('Pi 输出超过管道上限')
                    records.put(json.loads(line), timeout=5)
            except (OSError, ValueError, queue.Full):
                pass
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
        outcome, calls = 'error', 0
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
                    if record.get('type') in ('settled', 'error'):
                        outcome = record['type']
                        break
            else:
                outcome = 'timeout' if expired.is_set() or not stop.is_set() else 'stopped'
            return outcome
        finally:
            timer.cancel()
            try:
                process.stdin.write(b'{"type":"abort"}\n')
                process.stdin.flush()
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
