#!/usr/bin/env python3
"""用主会话证据推进有限业务补充，不进行网络调用或凭据操作。"""
import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import time
from pathlib import Path

MAX_STATE_BYTES = 65536
MAX_LINE_BYTES = 4 * 1024 * 1024
MAX_SCAN_BYTES = 64 * 1024 * 1024


def plan_digest(run_id: str, messages: list[str]) -> str:
    """绑定运行与补充正文，防止恢复时换题或重抽。

    :param run_id: 固定运行标识。
    :param messages: 已选定的补充正文。
    :return: 规范计划 SHA256。
    """
    raw = json.dumps({'run_id': run_id, 'followups': messages}, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, maximum: int) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum \
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('阶段状态文件类型、链接或大小无效')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            value = json.loads(stream.read(maximum + 1))
        if not isinstance(value, dict):
            raise ValueError('阶段状态必须为对象')
        return value
    finally:
        os.close(descriptor)


def _parent(path: Path) -> int:
    if not path.is_absolute() or path.name in ('', '.', '..'):
        raise ValueError('阶段文件须使用固定绝对路径')
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError('阶段目录不能经过符号链接')
    return os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _write(path: Path, value: dict) -> None:
    directory = _parent(path)
    temporary = '.followups-' + secrets.token_hex(8)
    descriptor = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory)
        with os.fdopen(descriptor, 'w', closefd=False) as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(descriptor)
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


def _files(project: Path) -> list[Path]:
    if not project.is_absolute() or project.is_symlink():
        raise ValueError('主会话目录无效')
    if not project.exists():
        return []
    if not project.is_dir():
        raise ValueError('主会话目录无效')
    result = []
    for path in project.glob('*.jsonl'):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('主会话不能是链接或特殊文件')
        result.append(path)
    return sorted(result)


def _text(content: object) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and all(
            isinstance(item, dict) and item.get('type') == 'text' and isinstance(item.get('text'), str)
            for item in content):
        return '\n'.join(item['text'] for item in content)
    return None


def _dialogue(path: Path, offset: int):
    if path.stat().st_size < offset:
        raise ValueError('主会话已截断，阶段游标不能自动回退')
    with path.open('rb') as stream:
        stream.seek(offset)
        scanned = 0
        while True:
            start = stream.tell()
            raw = stream.readline(MAX_LINE_BYTES + 1)
            if not raw:
                break
            scanned += len(raw)
            if scanned > MAX_SCAN_BYTES:
                raise ValueError('本阶段会话证据过大，需要明确对账')
            if len(raw) > MAX_LINE_BYTES and not raw.endswith(b'\n'):
                # 工具大输出不是业务输入确认；限长读取，避免让观察器占满容器内存。
                while raw and not raw.endswith(b'\n'):
                    raw = stream.readline(MAX_LINE_BYTES + 1)
                    scanned += len(raw)
                    if scanned > MAX_SCAN_BYTES:
                        raise ValueError('本阶段会话证据过大，需要明确对账')
                continue
            if not raw.endswith(b'\n'):
                break
            try:
                entry = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(entry, dict) or entry.get('isSidechain') or entry.get('isMeta'):
                continue
            message = entry.get('message')
            if not isinstance(message, dict):
                message = entry
            role = message.get('role')
            if role not in ('user', 'assistant'):
                continue
            content = message.get('content')
            text = _text(content)
            synthetic = entry.get('isApiErrorMessage') is True or message.get('model') == '<synthetic>'
            tool = message.get('stop_reason') == 'tool_use' or (
                isinstance(content, list) and any(isinstance(item, dict) and item.get('type') in ('tool_use', 'tool_result') for item in content))
            yield {'role': role, 'text': text, 'normal': not synthetic and not tool,
                'key': path.name + ':' + str(start), 'end': stream.tell()}


def _evidence(state: dict, project: Path, expected: str) -> tuple[dict | None, dict | None, Path | None]:
    accepted = latest = selected = None
    for path in _files(project):
        if state['session'] and path.name != state['session']:
            continue
        offset = state['cursor'].get(path.name, 0)
        local_input = local_latest = None
        for item in _dialogue(path, offset):
            if local_input is None:
                if item['role'] == 'user' and item['normal'] and item['text'] is not None \
                        and item['text'].strip() == expected.strip():
                    local_input = item
            else:
                local_latest = item
        if local_input:
            if accepted:
                raise ValueError('多个主会话出现相同阶段输入，归属不确定')
            accepted, latest, selected = local_input, local_latest, path
    return accepted, latest, selected


def _validate(state: dict, run_id: str, digest: str, total: int, initial: str) -> None:
    count = state.get('completed_stages')
    cursor = state.get('cursor')
    phase = state.get('phase')
    if type(state.get('schema')) is not int or state.get('schema') != 1 or state.get('run_id') != run_id or state.get('plan_digest') != digest \
            or state.get('initial_digest') != hashlib.sha256(initial.encode()).hexdigest():
        raise ValueError('阶段状态与原运行计划不匹配')
    if type(count) is not int or not 0 <= count <= total or phase not in ('awaiting', 'pending', 'complete'):
        raise ValueError('阶段序号或状态无效')
    if (phase == 'complete') != (count == total) or (phase == 'pending' and count == 0):
        raise ValueError('阶段完成状态不一致')
    if not isinstance(cursor, dict) or any(not isinstance(k, str) or Path(k).name != k
            or not k.endswith('.jsonl') or type(v) is not int or v < 0 for k, v in cursor.items()):
        raise ValueError('阶段游标无效')
    session = state.get('session')
    if not isinstance(session, str) or (session and (Path(session).name != session or not session.endswith('.jsonl'))):
        raise ValueError('阶段主会话归属无效')


def process(action: str, state_path: Path, project: Path, run_id: str,
            initial: str, followups: list[str], resume: bool = False,
            idle_seconds: float = 10, allow_next: bool = True) -> dict:
    """依据输入与回复证据推进一个阶段，pending 状态禁止再次发送。

    :param action: init、observe 或 advance。
    :param state_path: 本运行持久阶段文件。
    :param project: 固定主会话目录。
    :param run_id: 固定运行标识。
    :param initial: 原始初始题面，恢复控制提示不能覆盖它。
    :param followups: 本次已固化的零至两条业务补充。
    :param resume: 是否从原运行恢复。
    :param idle_seconds: 最终回复所需稳定窗口。
    :param allow_next: 收尾窗口禁止启动下一业务补充。
    :return: wait、send、complete 或 incomplete 动作及阶段摘要。
    """
    if action not in ('init', 'observe', 'advance') or not re.fullmatch(r'[a-f0-9]{12}', run_id):
        raise ValueError('阶段动作或运行标识无效')
    if not isinstance(initial, str) or not initial.strip() or not isinstance(followups, list) or len(followups) > 2 \
            or any(not isinstance(x, str) or not x.strip() or len(x) > 8000
                or re.search(r'[\x00-\x08\x0b-\x1f\x7f]', x) for x in followups):
        raise ValueError('阶段消息计划无效')
    digest = plan_digest(run_id, followups)
    total = 1 + len(followups)
    directory = _parent(state_path)
    os.close(directory)
    if state_path.exists() or state_path.is_symlink():
        state = _read(state_path, MAX_STATE_BYTES)
    elif action == 'init' and not resume:
        state = {'schema': 1, 'run_id': run_id, 'plan_digest': digest,
            'initial_digest': hashlib.sha256(initial.encode()).hexdigest(),
            'completed_stages': 0, 'phase': 'awaiting', 'session': '',
            'cursor': {p.name: p.stat().st_size for p in _files(project)},
            'input_entry': None, 'reply_entry': None}
        _write(state_path, state)
    else:
        raise ValueError('缺少原阶段状态，恢复不能重新初始化或抽签')
    _validate(state, run_id, digest, total, initial)
    result = {'action': 'wait', 'completed_stages': state['completed_stages'], 'phase': state['phase']}
    if state['phase'] == 'complete':
        accepted, latest, path = _evidence(state, project, ([initial] + followups)[-1])
        if accepted is None or latest is None or latest['role'] != 'assistant' or not latest['normal'] \
                or accepted['key'] != state['input_entry'] or latest['key'] != state['reply_entry']:
            raise ValueError('已完成阶段缺少匹配的主会话证据')
        return dict(result, action='complete')
    expected = ([initial] + followups)[state['completed_stages']]
    accepted, latest, path = _evidence(state, project, expected)
    if accepted:
        changed = state['input_entry'] != accepted['key'] or state['phase'] == 'pending'
        state.update(input_entry=accepted['key'], session=path.name, phase='awaiting')
        if changed:
            _write(state_path, state)
    elif resume and state['phase'] == 'pending':
        raise ValueError('补充消息投递结果不确定，已保留现场，禁止盲目重发')
    if action in ('init', 'observe') or accepted is None or latest is None:
        return dict(result, phase=state['phase'])
    if latest['role'] != 'assistant' or not latest['normal'] or not latest['text'] or not latest['text'].strip() \
            or time.time() - path.stat().st_mtime < idle_seconds:
        return dict(result, phase=state['phase'])
    state.update(completed_stages=state['completed_stages'] + 1, reply_entry=latest['key'])
    if state['completed_stages'] == total:
        state['phase'] = 'complete'
        _write(state_path, state)
        return {'action': 'complete', 'completed_stages': total, 'phase': 'complete'}
    if not allow_next:
        # 保留当前阶段的游标，终态由 driver 明确标为未完成，不能用收尾总结跳过补充。
        state['completed_stages'] -= 1
        _write(state_path, state)
        return dict(result, action='incomplete')
    state.update(phase='pending', input_entry=None,
        cursor={p.name: p.stat().st_size for p in _files(project)})
    _write(state_path, state)
    return {'action': 'send', 'index': state['completed_stages'],
        'text': followups[state['completed_stages'] - 1],
        'completed_stages': state['completed_stages'], 'phase': 'pending'}


def main() -> None:
    """提供 driver 使用的无网络命令行入口。

    :return: None；错误仅输出固定诊断，不输出题面和会话正文。
    """
    parser = argparse.ArgumentParser(description='有限业务补充阶段控制')
    parser.add_argument('action', choices=('init', 'observe', 'advance'))
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--idle', type=float, default=10)
    parser.add_argument('--no-next', action='store_true')
    args = parser.parse_args()
    try:
        followups = json.loads(os.environ.get('TASK_FOLLOWUPS_JSON', '[]'))
        value = process(args.action, args.state, args.project, os.environ.get('RUN_ID', ''),
            os.environ.get('TASK_INITIAL_PROMPT', ''), followups, args.resume, args.idle, not args.no_next)
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({'action': 'error', 'message': '自动补充阶段证据无效或投递结果不确定，需核对原运行'}))
        sys.exit(1)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
