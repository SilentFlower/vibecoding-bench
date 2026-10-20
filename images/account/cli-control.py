#!/usr/bin/env python3
"""普通用户容器的 PID1、逐作业监督及受控进程树操作。"""
import argparse
import ctypes
import json
import os
import signal
import subprocess
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


def _table() -> dict[int, dict]:
    result = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            fields = (path / 'stat').read_text().rpartition(')')[2].split()
            status = (path / 'status').read_text().splitlines()
            uid = int(next(line for line in status if line.startswith('Uid:')).split()[1])
            if uid == os.getuid():
                result[int(path.name)] = {'state': fields[0], 'parent': int(fields[1]),
                    'started': int(fields[19]), 'uid': uid}
        except (OSError, IndexError, ValueError, StopIteration):
            continue
    return result


def _descendants(pid: int, table: dict[int, dict]) -> dict[int, dict]:
    selected = {pid} if pid in table else set()
    while True:
        expanded = selected | {child for child, row in table.items() if row['parent'] in selected}
        if expanded == selected:
            return {child: table[child] for child in selected}
        selected = expanded


def _signal(pid: int, started: int, signum: int) -> None:
    row = _table().get(pid)
    # PID 可复用；每次发信号都重新核对启动时刻，绝不只凭持久文件中的整数。
    if row and row['started'] == started:
        try:
            os.kill(pid, signum)
        except ProcessLookupError:
            pass


def _verify(pid: int, started: int, source: str) -> dict | None:
    if pid <= 1 or started <= 0 or not source or len(source) > 160:
        raise ValueError('作业进程证明不合法')
    row = _table().get(pid)
    if row is None:
        return None
    if row['started'] != started or row['parent'] != 0:
        raise ValueError('作业进程代次或 Docker exec 归属不匹配')
    try:
        command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
        arguments = [item.decode() for item in command if item]
        marker = arguments.index('supervise')
        own_file = str(Path(__file__).resolve())
        if own_file not in arguments[:marker] or arguments[marker+1:marker+3] != ['--source', source]:
            raise ValueError('作业监督进程来源不匹配')
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError('无法核对作业监督进程') from error
    return row


def _publish(path: Path, value: dict) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('作业状态路径不能为链接')
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    with temporary.open('x') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, separators=(',', ':'))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _freeze(pid: int, started: int, source: str) -> dict:
    if _verify(pid, started, source) is None:
        return {'exists': False, 'source': source}
    deadline = time.monotonic() + 5
    previous, stable = None, 0
    while time.monotonic() < deadline:
        _verify(pid, started, source)
        tree = _descendants(pid, _table())
        # 先暂停监督器及祖先进程，再反复收敛后代，覆盖扫描期间的 fork 与孤儿收养。
        _signal(pid, started, signal.SIGSTOP)
        for child, row in tree.items():
            _signal(child, row['started'], signal.SIGSTOP)
        current = _descendants(pid, _table())
        keys = {(child, row['started']) for child, row in current.items()}
        frozen = bool(current) and all(row['state'] in ('T', 't', 'Z') for row in current.values())
        stable = stable + 1 if frozen and keys == previous else 0
        if stable >= 2:
            return {'exists': True, 'source': source, 'pid': pid, 'started': started,
                'frozen': True, 'processes': [{'pid': child, **row} for child, row in sorted(current.items())]}
        previous = keys
        time.sleep(0.03)
    raise RuntimeError('无法证明本作业全部写入进程已暂停')


def control(operation: str, pid: int, started: int, source: str) -> dict:
    """核对来源后操作一个作业，不按账号 UID 清理。

    :param operation: inspect、freeze、resume 或 stop-job。
    :param pid: 已在控制端登记的监督器 PID。
    :param started: 内核进程启动时刻。
    :param source: 本执行不可复用的来源。
    :return: 来源、进程树及实际操作结果；证明不符时拒绝。
    """
    root = _verify(pid, started, source)
    if root is None:
        return {'exists': False, 'source': source}
    if operation == 'freeze':
        return _freeze(pid, started, source)
    tree = _descendants(pid, _table())
    if operation == 'inspect':
        return {'exists': True, 'source': source, 'pid': pid, **root,
            'processes': [{'pid': child, **row} for child, row in sorted(tree.items())]}
    if operation == 'resume':
        for child, row in tree.items():
            _signal(child, row['started'], signal.SIGCONT)
        return {'exists': True, 'source': source, 'resumed': True}
    if operation != 'stop-job':
        raise ValueError('不支持的作业控制操作')
    for child, row in tree.items():
        _signal(child, row['started'], signal.SIGCONT)
    _signal(pid, started, signal.SIGTERM)
    deadline = time.monotonic() + 7
    while time.monotonic() < deadline:
        current = _table().get(pid)
        if current is None or current['started'] != started or current['state'] == 'Z':
            return {'exists': False, 'source': source, 'cleaned': True}
        time.sleep(0.05)
    proof = _freeze(pid, started, source)
    if not proof['exists']:
        return {'exists': False, 'source': source, 'cleaned': True}
    for process in proof['processes']:
        if process['pid'] != pid:
            _signal(process['pid'], process['started'], signal.SIGKILL)
    _signal(pid, started, signal.SIGCONT)
    time.sleep(0.1)
    remaining = _descendants(pid, _table())
    if any(child != pid and row['state'] != 'Z' for child, row in remaining.items()):
        raise RuntimeError('本作业仍有未收口子进程')
    _signal(pid, started, signal.SIGKILL)
    return {'exists': False, 'source': source, 'cleaned': True, 'forced': True}


def _reap(driver_pid: int) -> int | None:
    result = None
    try:
        while True:
            pid, status = os.waitpid(-1, os.WNOHANG)
            if not pid:
                break
            if pid == driver_pid:
                result = os.waitstatus_to_exitcode(status)
    except ChildProcessError:
        pass
    return result


def supervise(source: str, proof: Path, ready: Path, result: Path, command: list[str]) -> int:
    """为本次 Docker exec 收养后台后代，并在发布启动证明后等待控制端放行。

    :param source: 受信任调度器生成的执行来源。
    :param proof: 启动证明输出路径，仅在启动 CLI 前由控制端读取登记。
    :param ready: 控制端只读挂载的启动许可。
    :param result: 本次退出与定向清理结果。
    :param command: driver 参数数组，不使用 shell 拼接。
    :return: 原 driver 退出码；清理不确定时保持监督器，等待明确收口。
    """
    if not source or len(source) > 160 or not command:
        raise ValueError('执行来源或 driver 命令为空')
    library = ctypes.CDLL(None, use_errno=True)
    if library.prctl(36, 1, 0, 0, 0):
        raise OSError(ctypes.get_errno(), '无法建立作业子进程归属')
    stopping = False

    def stop(signum, frame) -> None:
        """只标记本监督器，清理循环负责回收本作业全部后代。"""
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    pid = os.getpid()
    row = _table()[pid]
    identity = {'schema': 1, 'pid': pid, 'started': row['started'], 'source': source,
        'parent': row['parent'], 'uid': os.getuid()}
    _publish(proof, identity)
    deadline = time.monotonic() + 20
    while not stopping:
        try:
            permit = json.loads(ready.read_text())
            if all(permit.get(key) == identity[key] for key in ('pid', 'started', 'source')):
                break
        except (OSError, ValueError, AttributeError):
            pass
        if time.monotonic() >= deadline:
            _publish(result, {**identity, 'cleaned': True, 'exit_code': 125})
            return 125
        time.sleep(0.05)
    if stopping:
        _publish(result, {**identity, 'cleaned': True, 'exit_code': 143})
        return 143
    # CLI 不继承监督器的输出通道，项目输出不能冒充启动握手；正文仍由原 transcript 采集。
    driver = subprocess.Popen(command, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    exit_code = None
    while exit_code is None and not stopping:
        exit_code = _reap(driver.pid)
        time.sleep(0.03)
    if exit_code is None:
        exit_code = 143
    for signum, duration in ((signal.SIGTERM, 3), (signal.SIGKILL, 3)):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            tree = _descendants(pid, _table())
            children = {child: entry for child, entry in tree.items() if child != pid and entry['state'] != 'Z'}
            if not children:
                _reap(driver.pid)
                driver.returncode = exit_code
                _publish(result, {**identity, 'cleaned': True, 'exit_code': exit_code})
                return exit_code
            for child, entry in children.items():
                _signal(child, entry['started'], signal.SIGCONT)
                _signal(child, entry['started'], signum)
            _reap(driver.pid)
            time.sleep(0.05)
    _publish(result, {**identity, 'cleaned': False, 'exit_code': exit_code})
    # 不确定时保留祖先归属，避免先退出而把未知后台进程丢给整个账号 PID1。
    while True:
        _reap(driver.pid)
        time.sleep(0.2)


def main() -> None:
    """运行最小空闲进程或受控命令，不接受外部网络请求。

    :return: None；失败使用非零退出码。
    """
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='operation', required=True)
    for operation in ('idle', 'stop', 'status', 'sample', 'orphans'):
        commands.add_parser(operation)
    execution = commands.add_parser('supervise')
    execution.add_argument('--source', required=True)
    execution.add_argument('--proof', type=Path, required=True)
    execution.add_argument('--ready', type=Path, required=True)
    execution.add_argument('--result', type=Path, required=True)
    execution.add_argument('command', nargs=argparse.REMAINDER)
    for operation in ('inspect', 'freeze', 'resume', 'stop-job'):
        operation_parser = commands.add_parser(operation)
        operation_parser.add_argument('--source', required=True)
        operation_parser.add_argument('--pid', type=int, required=True)
        operation_parser.add_argument('--started', type=int, required=True)
    args = parser.parse_args()
    operation = args.operation
    if os.geteuid() != 1000:
        raise RuntimeError('CLI 容器必须由账号普通用户运行')
    if operation == 'supervise':
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        raise SystemExit(supervise(args.source, args.proof, args.ready, args.result, command))
    elif operation in ('inspect', 'freeze', 'resume', 'stop-job'):
        print(json.dumps(control(operation, args.pid, args.started, args.source)))
    elif operation == 'orphans':
        print(json.dumps({'orphans': [{'pid': pid, **row} for pid, row in _table().items()
            if pid != os.getpid() and row['parent'] == 1 and row['state'] != 'Z']}))
    elif operation == 'sample':
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
