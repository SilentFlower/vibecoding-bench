"""记录单个真实子进程命令的时间、退出码和子进程峰值 RSS。"""
import argparse
import json
import os
import resource
import subprocess
import time
from pathlib import Path


def main() -> None:
    """有界执行一次命令，日志与证据只写本次挂载。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--cwd', required=True)
    parser.add_argument('--timeout', type=int, default=150)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    options = parser.parse_args()
    command = options.command[1:] if options.command[:1] == ['--'] else options.command
    root = Path('/evidence')
    started = time.monotonic()
    timed_out = False
    with (root / (options.name + '.log')).open('wb') as log:
        try:
            result = subprocess.run(command, cwd=options.cwd, stdout=log, stderr=subprocess.STDOUT,
                timeout=options.timeout, check=False)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code, timed_out = 124, True
    report = {'command': command, 'cwd': options.cwd, 'exit_code': code, 'timed_out': timed_out,
        'elapsed_sec': time.monotonic() - started,
        'max_rss_kib': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        'rss_scope': '本次新测量进程已退出子进程的 rusage 最大 RSS，不是容器总峰值',
        'environment': {key: os.environ.get(key) for key in ['HOME', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE',
            'PIP_CONFIG_FILE', 'PIP_NO_INDEX', 'PROJECT_CANDIDATE_ROOT', 'PROJECT_ANSWER_FILE']}}
    (root / (options.name + '-process.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'step': options.name, 'exit_code': code, 'elapsed_sec': report['elapsed_sec']}, ensure_ascii=False), flush=True)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
