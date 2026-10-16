#!/usr/bin/env python3
"""普通用户容器的最小 PID1、进程收口及只读内核采样。"""
import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path


def processes() -> list[int]:
    """列出本命名空间账号进程，排除 PID1 和当前管理命令。

    :return: 可收口的非僵尸 PID。
    """
    result = []
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal() or int(path.name) in (1, os.getpid()):
            continue
        try:
            status = dict(line.split(':', 1) for line in (path / 'status').read_text().splitlines() if ':' in line)
            if int(status['Uid'].split()[0]) == os.getuid() and not status['State'].lstrip().startswith('Z'):
                result.append(int(path.name))
        except (OSError, KeyError, ValueError):
            continue
    return result


def main() -> None:
    """运行最小空闲进程或受控命令，不接受外部网络请求。

    :return: None；失败使用非零退出码。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('idle', 'stop', 'status', 'sample'))
    operation = parser.parse_args().operation
    if os.geteuid() != 1000:
        raise RuntimeError('CLI 容器必须由账号普通用户运行')
    if operation == 'sample':
        # 脚本与模块来自只读镜像；-I 模式下仅加入这个固定受信目录。
        sys.path.insert(0, '/usr/local/bin')
        from process_metrics import cli_processes, memory_limit
        print(json.dumps({'memory': memory_limit(), 'samples': cli_processes()}))
    elif operation == 'status':
        raise SystemExit(0 if processes() else 1)
    elif operation == 'stop':
        for signum, duration in ((signal.SIGTERM, 3), (signal.SIGKILL, 3)):
            for pid in processes():
                try:
                    os.kill(pid, signum)
                except ProcessLookupError:
                    pass
            deadline = time.monotonic() + duration
            while processes() and time.monotonic() < deadline:
                time.sleep(0.1)
        if processes():
            raise RuntimeError('账号子进程尚未完成收口')
    else:
        stopping = False

        def stop(signum, frame) -> None:
            """标记退出，由命名空间退出收口全部本账号进程。"""
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        while not stopping:
            # Python 直接作为 PID1，避免清理 UID1000 时误杀额外空闲子进程。
            try:
                while os.waitpid(-1, os.WNOHANG)[0]:
                    pass
            except ChildProcessError:
                pass
            time.sleep(0.2)


if __name__ == '__main__':
    main()
