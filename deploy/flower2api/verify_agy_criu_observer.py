"""在仅有回环网络的 Linux 虚拟机里验证真实 AGY 及观察器的停态交接。"""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import tempfile
import time

from agy_runtime.capture_bridge import ResearchBridge
from agy_runtime.credentials import publish_access_document
from agy_runtime.process_memory import memory


def receive(stream, timeout=25):
    """有界读取夹具进程的回执。@param stream 控制管道。@param timeout 秒预算。@return JSON回执。"""
    if not select.select([stream], [], [], timeout)[0]:
        raise TimeoutError('等待交接回执超时')
    line = stream.readline()
    if not line:
        raise EOFError('交接进程提前退出')
    return json.loads(line)


def emit(stream, value):
    """发送一次无需业务数据的阶段回执。@param stream 控制管道。@param value 回执。@return 无。"""
    stream.write(json.dumps(value) + '\n')
    stream.flush()


def run_business(root, binary):
    """以业务 UID 启动真实观察器并接回原管道。@param root 测试目录。@param binary 固定原版。@return 无。"""
    bridge = ResearchBridge(root / 'bridge', 'candidate', False, None)
    bridge.binary = binary
    bridge.native_home = root / 'home'
    bridge.native_home.mkdir(mode=0o700)
    publish_access_document(bridge.native_home, {'account_id': 17, 'credential_generation': 1,
        'email': 'synthetic@example.test', 'access_token': 'synthetic-offline-criu-only', 'expires_at': 4070908800000})
    bridge.checkpoint_enabled = True
    bridge.startup_timeout = 25
    bridge._start()
    observer = bridge.proc.pid
    native = bridge.native_pid
    first = len(bridge.native_events)
    logs = bridge.native_home / '.gemini/antigravity-cli/log'
    ports = {int(port) for path in logs.glob('*.log') for port in
        re.findall(r'Language server listening on random port at (\d+) for HTTP\b', path.read_text())}
    if len(ports) != 1:
        raise ValueError('原生控制端口不唯一')
    port = ports.pop()

    def wait_event(kind):
        until = time.monotonic() + 8
        while time.monotonic() < until:
            bridge._pump()
            for event in bridge.native_events[first:]:
                if event['event'] == 'observer_error':
                    raise ValueError(event['error'])
                if event['event'] == kind and event.get('native_pid') == native:
                    return event['threads']
        raise TimeoutError(kind)

    def capabilities():
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=4)
        try:
            connection.request('POST', '/exa.language_server_pb.LanguageServerService/GetCapabilities',
                b'{}', {'Content-Type': 'application/json', 'x-codeium-csrf-token': bridge.csrf})
            response = connection.getresponse()
            if response.status != 200 or not isinstance(json.loads(response.read()), dict):
                raise ValueError('原生能力接口响应无效')
            return response.status
        finally:
            connection.close()

    before = capabilities()
    os.kill(observer, signal.SIGUSR1)
    threads = wait_event('observer_checkpoint_stopped')
    emit(sys.stdout, {'observer': observer, 'native': native, 'threads': threads, 'baseline_rpc': before})
    if receive(sys.stdin)['stage'] != 'reap':
        raise ValueError('缺少快照收口指令')
    bridge.proc.wait(timeout=5)
    emit(sys.stdout, {'reaped': True})
    if receive(sys.stdin)['stage'] != 'resume':
        raise ValueError('缺少恢复后的观察器接管指令')
    os.kill(observer, signal.SIGUSR2)
    os.kill(observer, signal.SIGCONT)
    restored_threads = wait_event('observer_checkpoint_resumed')
    emit(sys.stdout, {'after_restore_rpc': capabilities(), 'restored_threads': restored_threads})


def verify(root, binary, criu):
    """核对快照确实释放旧进程，保留原有两条观察管道。@param root 私有测试根。@param binary 原版。@param criu 固定工具。@return 测量和回执。"""
    working = root / 'business'
    working.mkdir(mode=0o700)
    os.chown(working, 1001, 1001)
    snapshot = root / 'snapshot'
    snapshot.mkdir(mode=0o700)
    child = subprocess.Popen([sys.executable, __file__, '--inside', '--work-root', str(working),
        '--binary', str(binary)], user=1001, group=1001, extra_groups=[], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, text=True)
    inherited = {}
    restored_descriptor = None
    try:
        stopped = receive(child.stdout, timeout=40)
        observer, native = stopped['observer'], stopped['native']
        before = memory(native)
        descriptors = Path(f'/proc/{observer}/fd')
        for path in descriptors.iterdir():
            target = os.readlink(path)
            if target.startswith('pipe:') and target not in inherited:
                inherited[target] = os.open(path, os.O_WRONLY | os.O_CLOEXEC)
        # 原业务读端由下层进程持有。保留写端保证老读端在快照前后使用同一条管道。
        options = ['--images-dir', str(snapshot), '--shell-job', '--file-locks']

        def run(stage, arguments, descriptors=()):
            log = root / (stage + '.log')
            started = time.monotonic()
            result = subprocess.run([str(criu), '--no-default-config', stage, *options,
                *arguments, '-v4', '--log-file', str(log)], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, pass_fds=descriptors, timeout=20)
            if result.returncode:
                lines = log.read_text().splitlines()
                raise RuntimeError('\n'.join(line for line in lines if 'Error' in line)[-2400:])
            return round((time.monotonic() - started) * 1000)

        dump_ms = run('dump', ['--tree', str(observer)])
        emit(child.stdin, {'stage': 'reap'})
        if receive(child.stdout) != {'reaped': True} or Path(f'/proc/{observer}').exists():
            raise ValueError('旧观察器进程未完成回收')
        if Path(f'/proc/{native}').exists():
            raise ValueError('旧原生进程未完成回收')
        pidfile = root / 'restored.pid'
        arguments = ['--leave-stopped', '--restore-detached', '--restore-sibling', '--pidfile', str(pidfile)]
        for target, descriptor in inherited.items():
            arguments.extend(['--inherit-fd', f'fd[{descriptor}]:{target}'])
        restore_ms = run('restore', arguments, tuple(inherited.values()))
        restored = int(pidfile.read_text())
        restored_descriptor = os.pidfd_open(restored)
        if restored != observer:
            raise ValueError('恢复的观察器身份变化')
        emit(child.stdin, {'stage': 'resume'})
        receipt = receive(child.stdout)
        if child.wait(timeout=6) or receipt['restored_threads'] != stopped['threads']:
            raise ValueError('恢复的原生线程集合变化')
        return {**stopped, **receipt, 'dump_ms': dump_ms, 'restore_ms': restore_ms,
            'snapshot_bytes': sum(path.stat().st_size for path in snapshot.iterdir() if path.is_file()),
            'before_dump': before}
    finally:
        if restored_descriptor is not None:
            try:
                signal.pidfd_send_signal(restored_descriptor, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.close(restored_descriptor)
        for descriptor in inherited.values():
            os.close(descriptor)
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=6)


def main():
    """运行隔离验证。@return 无。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=Path('/usr/local/bin/agy-1.5.9'))
    parser.add_argument('--criu', type=Path, default=Path('/opt/ccrb-criu/criu'))
    parser.add_argument('--inside', action='store_true')
    parser.add_argument('--work-root', type=Path)
    args = parser.parse_args()
    if args.inside:
        run_business(args.work_root, args.binary)
        return
    if os.geteuid() or set(os.listdir('/sys/class/net')) != {'lo'}:
        parser.error('需要仅有回环接口的独立虚拟机及其 CRIU 测试权限')
    with tempfile.TemporaryDirectory(prefix='agy-criu-probe-') as temporary:
        root = Path(temporary)
        # 凭据文件助手会逐层打开目录，实际业务材料和原生快照分别存放于私有子目录。
        root.chmod(0o755)
        print(json.dumps(verify(root, args.binary, args.criu), ensure_ascii=False))


if __name__ == '__main__':
    main()
