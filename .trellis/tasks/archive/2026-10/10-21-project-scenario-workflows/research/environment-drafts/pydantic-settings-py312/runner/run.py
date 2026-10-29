"""在指定离线容器中验证固定上游与研究参考补丁，所有结果保存到独立证据目录。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _memory() -> dict:
    result = {'child_max_rss_kib': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss}
    for name in ('memory.peak', 'memory.current', 'memory.max', 'pids.peak', 'pids.max'):
        path = Path('/sys/fs/cgroup') / name
        try:
            value = path.read_text().strip()
            result[name] = int(value) if value.isdigit() else value
        except OSError:
            result[name] = None
    return result


def _execute(name: str, command: list[str], cwd: Path, environment: dict, limit: int) -> dict:
    started = time.monotonic()
    with (Path('/evidence') / (name + '.log')).open('wb') as stream:
        try:
            completed = subprocess.run(command, cwd=cwd, env=environment, stdout=stream,
                stderr=subprocess.STDOUT, timeout=limit)
            code, timed_out = completed.returncode, False
        except subprocess.TimeoutExpired:
            code, timed_out = 124, True
    result = {'command': command, 'cwd': str(cwd), 'exit_code': code, 'timed_out': timed_out,
        'elapsed_sec': round(time.monotonic() - started, 6), 'resources_after': _memory()}
    _write(Path('/evidence') / (name + '-result.json'), result)
    return result


def _reference_patch(root: Path) -> dict:
    patch = Path('/control/reference-union.patch').read_text(encoding='utf-8')
    target = root / 'library/pydantic_settings/sources/providers/env.py'
    original = target.read_text(encoding='utf-8')
    rows = patch.splitlines(keepends=True)
    hunks = [(index, re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n?', row))
        for index, row in enumerate(rows) if row.startswith('@@ ')]
    if len(hunks) != 1 or hunks[0][1] is None:
        raise ValueError('本研究只接受已冻结的单段参考补丁')
    index, match = hunks[0]
    start, count = int(match[1]) - 1, int(match[2] or 1)
    old = [row[1:] for row in rows[index + 1:] if row[:1] in (' ', '-')]
    new = [row[1:] for row in rows[index + 1:] if row[:1] in (' ', '+')]
    content = original.splitlines(keepends=True)
    if content[start:start + count] != old:
        raise ValueError('参考补丁与固定原版上下文不一致')
    target.write_text(''.join([*content[:start], *new, *content[start + count:]]), encoding='utf-8')
    return {'file': str(target.relative_to(root)), 'before_sha256': hashlib.sha256(original.encode()).hexdigest(),
        'after_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'patch_sha256': hashlib.sha256(patch.encode()).hexdigest()}


def main() -> None:
    """离线安装并运行本次原版或补丁验证。

    :return: 无；所有必要执行和业务对照成功时退出零。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('baseline', 'reference'))
    arguments = parser.parse_args()
    started = time.monotonic()
    root = Path('/work/project')
    shutil.copytree('/source', root)
    Path('/tmp/home').mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, 'HOME': '/tmp/home', 'PYTHONDONTWRITEBYTECODE': '1',
        'PIP_CONFIG_FILE': '/dev/null', 'PIP_NO_CACHE_DIR': '1', 'PYTHONPATH': '/work/project/library:/work/dependencies',
        'PATH': '/work/dependencies/bin:' + os.environ['PATH'], 'TERM': 'dumb'}
    for key in list(environment):
        if key.startswith('APP_') or key == 'PYDANTIC_SETTINGS_DEBUG':
            environment.pop(key)
    metadata = {'mode': arguments.mode, 'python': sys.version, 'platform': platform.platform(),
        'uid': os.getuid(), 'gid': os.getgid(), 'cgroup': Path('/proc/self/cgroup').read_text(),
        'network_mode': 'none', 'initial_resources': _memory()}
    _write(Path('/evidence/runtime.json'), metadata)
    installation = _execute('offline-install', [sys.executable, '-m', 'pip', 'install',
        '--disable-pip-version-check', '--no-index', '--no-deps', '--target', '/work/dependencies',
        '--find-links', '/offline/artifacts', '-r', '/offline/profile/requirements.txt'], root, environment, 240)
    if installation['exit_code']:
        raise SystemExit(80)
    if arguments.mode == 'reference':
        _write(Path('/evidence/reference-patch.json'), _reference_patch(root))
    native = _execute('native', [sys.executable, '-m', 'pytest', 'tests', '-q', '-ra',
        '--junitxml=/evidence/native-tests.xml'], root / 'library', environment, 300)
    suite = 'union-original' if arguments.mode == 'baseline' else 'union-fixed'
    business = _execute('business', [sys.executable, '-B', '/control/check_settings.py', suite,
        '--candidate-root', str(root)], root, environment, 60)
    actual = None
    try:
        actual = json.loads(Path('/evidence/business.log').read_text(encoding='utf-8'))
    except (ValueError, OSError):
        pass
    expected = json.loads(Path('/control/native', suite + '.json').read_text(encoding='utf-8'))['expected']
    matched = actual == expected
    result = {'mode': arguments.mode, 'installation': installation, 'native': native, 'business': business,
        'business_actual': actual, 'business_expected': expected, 'business_matches': matched,
        'elapsed_sec': round(time.monotonic() - started, 6), 'resources_final': _memory()}
    _write(Path('/evidence/result.json'), result)
    print(json.dumps({'mode': arguments.mode, 'native_exit': native['exit_code'],
        'business_exit': business['exit_code'], 'business_matches': matched,
        'elapsed_sec': result['elapsed_sec']}, ensure_ascii=False))
    raise SystemExit(0 if native['exit_code'] == business['exit_code'] == 0 and matched else 1)


if __name__ == '__main__':
    main()
