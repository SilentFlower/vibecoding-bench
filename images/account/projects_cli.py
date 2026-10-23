#!/usr/bin/env python3
"""仅监督原生 Claude Code 终端，全部业务输入由 Pi 的工具操作提供。"""
import argparse
import json
import os
import shlex
import subprocess
import time
from pathlib import Path


def run(configuration: Path) -> int:
    """创建独立 tmux 并等待 CLI 退出，不注入问题或识别业务阶段。

    :param configuration: 控制端生成的本执行配置。
    :return: CLI 退出码，或监督超时的 124。
    """
    value = json.loads(configuration.read_text())
    command = ['tmux', '-S', value['socket'], '-f', '/dev/null']
    cli = ['claude', '--permission-mode', 'bypassPermissions', '--settings', value['settings']]
    cli.extend(['--resume' if value['resume'] else '--session-id', value['session_id']])
    if value.get('model'):
        cli.extend(['--model', value['model']])
    # 只将受控的 argv 转义为 tmux 启动命令；业务文本通过独立 stdin 缓冲投递。
    script = 'set +m; ' + shlex.join(cli) + '; code=$?; printf "%s" "$code" > ' + shlex.quote(value['exit_file']) + '; sleep 3600'
    started = subprocess.run([*command, 'new-session', '-d', '-s', value['session'],
        '-x', '180', '-y', '50', script], capture_output=True)
    if started.returncode:
        return 1
    try:
        deadline = time.monotonic() + value['timeout_sec']
        while time.monotonic() < deadline:
            if Path(value['exit_file']).is_file():
                return int(Path(value['exit_file']).read_text())
            if subprocess.run([*command, 'has-session', '-t', value['session']],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                return 1
            signal = Path(value['quota_signal']) if value.get('quota_signal') else None
            if signal and signal.is_file():
                return 43
            time.sleep(0.5)
        return 124
    finally:
        subprocess.run([*command, 'kill-server'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='监督 Pi 所控制的 Claude Code 终端')
    parser.add_argument('--config', required=True, type=Path)
    raise SystemExit(run(parser.parse_args().config))
