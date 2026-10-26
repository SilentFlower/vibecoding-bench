#!/usr/bin/env python3
"""仅监督原生 Claude Code 终端，全部业务输入由 Pi 的工具操作提供。"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path


def _publish(path: Path, value: dict) -> None:
    """原子发布本作业的小型通知，不跟随已有目标链接。

    :param path: 固定作业目录中的目标。
    :param value: 已裁剪的通知或设置。
    :return: None。
    """
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def notify(configuration: Path) -> int:
    """把 CLI 钩子转为本地唤醒提示，绝不返回授权或业务判断。

    :param configuration: 原监督进程的固定作业配置。
    :return: 钩子退出码，通知失败也不干扰原生交互。
    """
    try:
        value = json.loads(configuration.read_text())
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            return 0
        event = json.loads(raw)
        if not isinstance(event, dict) or event.get('session_id') != value['session_id']:
            return 0
        kind, tool = event.get('hook_event_name'), event.get('tool_name')
        if kind not in ('PermissionRequest', 'PreToolUse', 'Stop'):
            return 0
        if kind == 'PreToolUse' and tool not in ('AskUserQuestion', 'ExitPlanMode'):
            return 0
        if tool is not None and (not isinstance(tool, str) or len(tool) > 200):
            return 0
        _publish(Path(value['interaction_signal']), {'schema': 1, 'source': value['source'],
            'session_id': value['session_id'], 'id': uuid.uuid4().hex, 'event': kind,
            'tool': tool, 'observed_at': time.time()})
    except (OSError, ValueError, KeyError, TypeError):
        # 通知只是提示；失败由原生事件与画面变化兜底，不能阻塞或自动放行工具。
        pass
    return 0


def _install_notifications(configuration: Path, value: dict) -> None:
    """仅在本作业覆盖设置追加通知，保留用户原有钩子。

    :param configuration: 本次监督配置。
    :param value: 已读取的配置。
    :return: None；旧配置没有通知路径时保持兼容。
    """
    if not value.get('interaction_signal') or not value.get('source'):
        return
    settings = Path(value['settings'])
    document = json.loads(settings.read_text())
    hooks = document.setdefault('hooks', {})
    command = shlex.join(['python3', '-I', str(Path(__file__).resolve()),
        '--config', str(configuration.resolve()), '--notify'])
    for event, matcher in (('PermissionRequest', ''), ('PreToolUse', 'AskUserQuestion|ExitPlanMode'), ('Stop', '')):
        entries = hooks.setdefault(event, [])
        if not any(item.get('command') == command for entry in entries for item in entry.get('hooks', [])):
            entries.append({'matcher': matcher, 'hooks': [{'type': 'command', 'command': command, 'timeout': 3}]})
    _publish(settings, document)


def run(configuration: Path) -> int:
    """创建独立 tmux 并等待 CLI 退出，不注入问题或识别业务阶段。

    :param configuration: 控制端生成的本执行配置。
    :return: CLI 退出码，或监督超时的 124。
    """
    value = json.loads(configuration.read_text())
    _install_notifications(configuration, value)
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
    parser.add_argument('--notify', action='store_true')
    arguments = parser.parse_args()
    raise SystemExit(notify(arguments.config) if arguments.notify else run(arguments.config))
