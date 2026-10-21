"""等待真实模拟完成后运行只读页面核验，不伪造完成标记或业务状态。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from argparse import ArgumentParser
from pathlib import Path


def main() -> None:
    """核真实ready和连接资料后执行既有浏览器检查。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--run', default='run-001')
    parser.add_argument('--timeout-sec', default=7200, type=int)
    options = parser.parse_args()
    bundle = options.bundle.resolve(strict=True)
    connection = bundle / options.run / 'connection.json'
    deadline = time.monotonic() + options.timeout_sec
    while time.monotonic() < deadline:
        if connection.is_file():
            configuration = json.loads(connection.read_text())
            ids = configuration.get('batch_ids', [])
            if (ids and len(ids) == len(configuration['expected_selected_task_counts'])
                    and Path(configuration['browser_ready_file']).is_file()):
                break
            cleanup = connection.parent / 'cleanup.json'
            if cleanup.is_file():
                raise RuntimeError('运行器已清理且没有可验证的完整ready状态')
        time.sleep(2)
    else:
        raise TimeoutError('等待本批真实浏览器ready超时')
    script = Path(__file__).with_name('mock-harness') / 'verify-browser.py'
    completed = subprocess.run([sys.executable, str(script), '--connection-file', str(connection),
        '--output-dir', str(bundle / 'browser' / options.run)],
        env=dict(os.environ, HUNDRED_MOCK_BUNDLE=str(bundle)), timeout=1200)
    raise SystemExit(completed.returncode)


if __name__ == '__main__':
    main()
