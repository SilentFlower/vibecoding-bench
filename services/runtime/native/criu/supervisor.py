"""可信PID1：收到持有确认后恢复单个实例，退出时由内核收口全部后代。"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from entropy import ProcessProof, reset_fork_guard
from shared_image import IMAGE_RESOURCE, verify_restored_image

ROOT = Path('/var/lib/ccrb-criu')


def main() -> None:
    """只接受固定加载器传入的实例及六个私有FD。@return 无。"""
    if os.getpid() != 1 or len(sys.argv) != 8:
        raise SystemExit(111)
    instance = ROOT / 'instances' / sys.argv[1]
    gate, report, incoming, outgoing, errors, image = [int(value) for value in sys.argv[2:]]
    # pidfd由sender持有后才允许恢复；ACK前此命名空间没有业务进程。
    if os.read(gate, 1) != b'S':
        raise SystemExit(111)
    os.close(gate)
    configuration = json.loads((instance / 'config.json').read_text())
    subprocess.run(['/bin/mount', '--make-rprivate', '/'], check=True)
    subprocess.run(['/bin/mount', '-t', 'proc', 'proc', '/proc'], check=True)
    subprocess.run(['/bin/mount', '-t', 'tmpfs', '-o', 'size=1m,mode=0755,nosuid,nodev',
                    'tmpfs', configuration['work_root']], check=True)
    logical = Path(configuration['source_root'])
    logical.mkdir(mode=0o700)
    subprocess.run(['/bin/mount', '--bind', str(instance / 'fs'), str(logical)], check=True)
    # 研究快照源PID大于监督子进程；显式跳过其PID，防止CRIU自身抢占待恢复PID。
    maximum = max(configuration['source_max_pid'] + 128, 1024)
    Path('/proc/sys/kernel/ns_last_pid').write_text(str(maximum))
    work = instance / 'work'
    work.mkdir(mode=0o700)
    arguments = ['/opt/ccrb-criu/criu', '--no-default-config', 'restore',
        '-D', configuration['images'], '-W', str(work), '--shell-job', '--restore-sibling',
        '--leave-stopped', '-d', '--pidfile', str(instance / 'worker.pid'),
        '-v2', '-o', str(instance / 'restore.log')]
    for descriptor, name in zip((incoming, outgoing, errors), ('0', '1', '2')):
        arguments += ['--inherit-fd', f'fd[{descriptor}]:' + configuration['pipes'][name]]
    arguments += ['--inherit-fd', f'fd[{image}]:' + IMAGE_RESOURCE]
    restore_started = time.monotonic()
    result = subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, pass_fds=(incoming, outgoing, errors, image), timeout=30)
    restore_ms = round((time.monotonic() - restore_started) * 1000, 3)
    for descriptor in (incoming, outgoing, errors):
        os.close(descriptor)
    if result.returncode:
        raise SystemExit(111)
    pid = int((instance / 'worker.pid').read_text())
    verify_restored_image(pid, image, configuration)
    os.close(image)
    started = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()[19]
    entropy_started = time.monotonic()
    receipt = reset_fork_guard(ProcessProof(pid, 1, started, configuration['image_sha256']))
    print(json.dumps({'layer': 'criu_supervisor', 'criu_restore_ms': restore_ms,
        'entropy_verify_ms': round((time.monotonic() - entropy_started) * 1000, 3)}), file=sys.stderr, flush=True)
    os.write(report, json.dumps({'inner_pid': pid, 'entropy': receipt}).encode() + b'\n')
    os.close(report)
    os.kill(pid, signal.SIGCONT)
    os.waitpid(pid, 0)


if __name__ == '__main__':
    main()
