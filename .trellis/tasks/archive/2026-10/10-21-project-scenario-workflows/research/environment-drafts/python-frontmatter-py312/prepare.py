"""下载已经核实的固定 wheel，并生成不伪造运行就绪状态的环境档案。"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ['PyYAML==6.0.3', 'pytest==9.1.1', 'toml==0.10.2', 'pyaml==26.7.0',
    'iniconfig==2.3.1', 'packaging==26.3', 'pluggy==1.7.0', 'Pygments==2.21.0']


def main() -> None:
    """准备固定制品和实际下载证据。@return None。"""
    artifacts = ROOT / 'artifacts'
    evidence = ROOT / 'evidence'
    for directory in [artifacts, evidence, ROOT / 'download-cache', ROOT / 'download-temp', ROOT / 'profile']:
        directory.mkdir(parents=True, exist_ok=True)
    requirements = ROOT / 'requirements-frozen.txt'
    requirements.write_text('\n'.join(REQUIREMENTS) + '\n', encoding='utf-8')
    command = [sys.executable, '-m', 'pip', 'download', '--disable-pip-version-check', '--only-binary=:all:',
        '--no-deps', '--dest', str(artifacts), '--requirement', str(requirements)]
    environment = dict(os.environ, PIP_CACHE_DIR=str(ROOT / 'download-cache'), TMPDIR=str(ROOT / 'download-temp'))
    started = time.monotonic()
    with (evidence / 'download.log').open('wb') as log:
        result = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False)
    record = {'command': command, 'exit_code': result.returncode, 'elapsed_sec': time.monotonic() - started,
        'scope': '仅下载既有固定版本，不查询或选择最新版'}
    (evidence / 'download-result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    if result.returncode:
        print(json.dumps(record, ensure_ascii=False))
        raise SystemExit(result.returncode)
    wheels = []
    for path in sorted(artifacts.iterdir()):
        if not path.is_file() or path.suffix != '.whl' or path.is_symlink():
            raise ValueError('离线目录出现非 wheel 或链接')
        wheels.append({'path': 'artifacts/' + path.name, 'digest': hashlib.sha256(path.read_bytes()).hexdigest(),
            'size': path.stat().st_size})
    if len(wheels) != len(REQUIREMENTS):
        raise ValueError('固定八项 wheel 未齐备或出现额外制品')
    profile = {'schema': 1, 'id': 'python-frontmatter-py312', 'adapter': 'python-native', 'python': '3.12',
        'platform': 'linux-amd64', 'requirements': REQUIREMENTS, 'artifacts': wheels,
        'business': {'timeout_sec': 180, 'memory_mb': 512, 'pids_limit': 64},
        'regression': {'timeout_sec': 180, 'memory_mb': 512, 'pids_limit': 64},
        'verification_status': 'prepared_not_verified',
        'source_commit': 'd2977d71638cb451bc06f2af3bb48e09e0dbe8c6',
        'notes': '依赖为既有完整测试环境；资源为本次受控验证上限，尚不代表已经通过或最优配置。'}
    (ROOT / 'profile/profile.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'download_exit_code': result.returncode, 'wheel_count': len(wheels),
        'wheel_bytes': sum(item['size'] for item in wheels), 'verification_status': 'prepared_not_verified'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
