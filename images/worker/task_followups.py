#!/usr/bin/env python3
"""用主会话证据推进有限业务补充，不进行网络调用或凭据操作。"""
import argparse
import hashlib
import json
import math
import os
import re
import secrets
import stat
import sys
import time
from datetime import datetime
from heapq import heapify, heappop, heappush
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


def _text(content: object, role: str) -> str | None:
    if isinstance(content, str):
        return content
    if role == 'assistant' and isinstance(content, list):
        # 思考块不属于交付正文；工具和 synthetic 判断仍由消息类型独立保护。
        parts = [item['text'] for item in content if isinstance(item, dict)
            and item.get('type') == 'text' and isinstance(item.get('text'), str)]
        return '\n'.join(parts) if parts else None
    if isinstance(content, list) and content and all(
            isinstance(item, dict) and item.get('type') == 'text' and isinstance(item.get('text'), str)
            for item in content):
        return '\n'.join(item['text'] for item in content)
    return None


def _matches_input(actual: str, expected: str) -> bool:
    # CLI可能只包装首段并把末行留在标签外；移除的仅是有同ID的传输包装，正文仍须逐字核对。
    actual = actual.strip()
    if actual == expected.strip():
        return True
    pasted = re.fullmatch(
        r'<pasted_content id="(?P<id>[A-Za-z0-9_-]{1,128})">\r?\n'
        r'(?P<text>[\s\S]*?)</pasted_content id="(?P=id)">(?P<tail>[\s\S]*)', actual)
    if pasted is None or re.search(r'</?pasted_content\b', pasted['text'] + pasted['tail']):
        return False
    body, tail = pasted['text'], pasted['tail']
    bodies = [body]
    if body.endswith('\r\n'):
        bodies.append(body[:-2])
    elif body.endswith('\n'):
        bodies.append(body[:-1])
    tails = [tail]
    # 实测关闭标签会额外带最多两个换行；不移除空格、正文或任意数量的原始空行。
    for _ in range(2):
        if tails[-1].startswith('\r\n'):
            tails.append(tails[-1][2:])
        elif tails[-1].startswith('\n'):
            tails.append(tails[-1][1:])
        else:
            break
    return any((prefix + suffix).strip() == expected.strip() for prefix in bodies for suffix in tails)


def _ordered(items: list[dict], parents: dict[str, str | None]) -> list[dict]:
    indices = {}
    for index, item in enumerate(items):
        if item['id']:
            if item['id'] in indices:
                raise ValueError('主会话消息标识重复，无法确认归属')
            indices[item['id']] = index
    children = [[] for _ in items]
    indegrees = [0] * len(items)
    cache = {}
    for index, item in enumerate(items):
        parent, trace, seen = item['parent'], [], set()
        while parent and parent not in indices and parent not in cache:
            if parent in seen:
                raise ValueError('主会话父链存在循环')
            seen.add(parent)
            trace.append(parent)
            parent = parents.get(parent)
        ancestor = indices.get(parent, cache.get(parent))
        for identity in trace:
            cache[identity] = ancestor
        item['parent_key'] = items[ancestor]['key'] if ancestor is not None else None
        if ancestor is not None:
            children[ancestor].append(index)
            indegrees[index] += 1
    # 父子关系优先于落盘和时钟顺序；旧无时间记录继续使用稳定的原文件顺序。
    timed = all(item['epoch'] is not None for item in items)
    priority = [item['epoch'] if timed else index for index, item in enumerate(items)]
    ready = [(priority[index], index) for index, count in enumerate(indegrees) if count == 0]
    heapify(ready)
    result = []
    while ready:
        _, index = heappop(ready)
        result.append(items[index])
        for child in children[index]:
            indegrees[child] -= 1
            if indegrees[child] == 0:
                heappush(ready, (priority[child], child))
    if len(result) != len(items):
        raise ValueError('主会话父链存在循环')
    return result


def read_dialogue(path: Path, offset: int = 0, include_queue: bool = False) -> list[dict]:
    """有界读取主消息，保留字节证据并恢复实际对话顺序。

    :param path: 已由调用方核对的主 JSONL 文件。
    :param offset: 本次执行或阶段已保存的字节游标。
    :param include_queue: 定时模式额外读取原生入队证据，通用完成检测始终排除。
    :return: 按父链及时间排序的消息摘要，不保留工具大正文。
    """
    if path.stat().st_size < offset:
        raise ValueError('主会话已截断，阶段游标不能自动回退')
    items, parents = [], {}
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
            if not isinstance(entry, dict) or entry.get('isSidechain'):
                continue
            identity = entry.get('uuid')
            identity = identity if isinstance(identity, str) and identity else None
            parent = entry.get('parentUuid')
            parent = parent if isinstance(parent, str) and parent else None
            if identity:
                if identity in parents and parents[identity] != parent:
                    raise ValueError('主会话消息父链冲突')
                parents[identity] = parent
            if entry.get('isMeta'):
                continue
            message = entry.get('message')
            if not isinstance(message, dict):
                message = entry
            role = message.get('role')
            attachment = entry.get('attachment')
            native_input = entry.get('type') == 'attachment'
            if native_input:
                origin = attachment.get('origin') if isinstance(attachment, dict) else None
                if not isinstance(attachment, dict) or attachment.get('type') != 'queued_command' \
                        or entry.get('sessionId') != path.stem or not identity or not parent \
                        or attachment.get('commandMode') != 'prompt' or attachment.get('humanTurn') is not True \
                        or not isinstance(origin, dict) or origin.get('kind') != 'human' \
                        or not isinstance(attachment.get('prompt'), str):
                    continue
                # 忙碌时的用户补充以原生附件进入当前回合，rendered包装和队列移除均不能证明消费。
                # 复用原附件字节键与父链，让阶段机和通用完成检测同时看见这条真实输入。
                role = 'user'
            queued = include_queue and entry.get('type') == 'queue-operation' \
                and entry.get('operation') == 'enqueue' and entry.get('sessionId') == path.stem
            if queued:
                role = 'queue'
            if role not in ('user', 'assistant') and not queued:
                continue
            content = message.get('content')
            text = _text(attachment['prompt'] if native_input else content, role)
            synthetic = entry.get('isApiErrorMessage') is True or message.get('model') == '<synthetic>'
            tool = message.get('stop_reason') == 'tool_use' or (
                isinstance(content, list) and any(isinstance(item, dict) and item.get('type') in ('tool_use', 'tool_result') for item in content))
            epoch = None
            try:
                timestamp = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                if timestamp.tzinfo is not None:
                    epoch = timestamp.timestamp()
            except (KeyError, ValueError, TypeError, AttributeError, OverflowError, OSError):
                pass
            items.append({'role': role, 'text': text, 'normal': not synthetic and not tool and not queued,
                'synthetic': synthetic, 'tool': tool, 'error': str(entry.get('error') or ''),
                'id': identity, 'parent': parent, 'epoch': epoch,
                'key': path.name + ':' + str(start), 'end': stream.tell()})
    return _ordered(items, parents)


def latest_dialogue(project: Path, idle_seconds: float, baseline_path: Path) -> dict | None:
    """为通用完成检测返回本次执行的最新主消息，与阶段机共用解析。

    :param project: 主会话目录。
    :param idle_seconds: 文件须满足的稳定窗口。
    :param baseline_path: 本次尝试开始时保存的文件字节基线。
    :return: 最新主消息摘要；未稳定或尚无新消息时返回 None。
    """
    files = _files(project)
    if not files:
        return None
    path = max(files, key=lambda item: item.stat().st_mtime)
    if time.time() - path.stat().st_mtime < idle_seconds:
        return None
    offset = 0
    try:
        baseline = json.loads(baseline_path.read_text())
        value = baseline.get(str(path), 0)
        if type(value) is int and value >= 0:
            offset = value
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    items = read_dialogue(path, offset)
    return items[-1] if items else None


def _evidence(state: dict, project: Path, expected: str) -> tuple[dict | None, dict | None, Path | None]:
    accepted = latest = selected = None
    for path in _files(project):
        if state['session'] and path.name != state['session']:
            continue
        offset = state['cursor'].get(path.name, 0)
        local_input = local_latest = None
        descendants = set()
        for item in read_dialogue(path, offset):
            if local_input is None:
                if item['role'] == 'user' and item['normal'] and item['text'] is not None \
                        and _matches_input(item['text'], expected):
                    local_input = item
                    descendants.add(item['key'])
            else:
                linked = local_input['id'] is None or item['id'] is None or item['parent_key'] in descendants
                if linked:
                    descendants.add(item['key'])
                local_latest = dict(item, linked=linked)
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
            idle_seconds: float = 10, allow_next: bool = True, timing: dict | None = None) -> dict:
    """依据输入与回复证据推进一个阶段，pending 状态禁止再次发送。

    :param action: init/observe/advance，定时模式另提供 start/tick。
    :param state_path: 本运行持久阶段文件。
    :param project: 固定主会话目录。
    :param run_id: 固定运行标识。
    :param initial: 原始初始题面，恢复控制提示不能覆盖它。
    :param followups: 本次已固化的零至两条业务补充。
    :param resume: 是否从原运行恢复。
    :param idle_seconds: 最终回复所需稳定窗口。
    :param allow_next: 收尾窗口禁止启动下一业务补充。
    :param timing: 新运行冻结时间快照；None 保留旧阶段规则。
    :return: wait、send、complete 或 incomplete 动作及阶段摘要。
    """
    if action not in ('init', 'observe', 'advance', 'start', 'tick') or not re.fullmatch(r'[a-f0-9]{12}', run_id):
        raise ValueError('阶段动作或运行标识无效')
    if not isinstance(initial, str) or not initial.strip() or not isinstance(followups, list) or len(followups) > 2 \
            or any(not isinstance(x, str) or not x.strip() or len(x) > 8000
                or re.search(r'[\x00-\x08\x0b-\x1f\x7f]', x) for x in followups):
        raise ValueError('阶段消息计划无效')
    digest = plan_digest(run_id, followups)
    total = 1 + len(followups)
    directory = _parent(state_path)
    os.close(directory)
    if timing is not None:
        return _process_timed(action, state_path, project, run_id, initial, followups,
            resume, idle_seconds, allow_next, timing)
    if action in ('start', 'tick'):
        raise ValueError('旧阶段模式不能使用定时动作')
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
        if accepted is None or latest is None or latest['role'] != 'assistant' or not latest['normal'] or not latest['linked'] \
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
    if action in ('init', 'observe'):
        return dict(result, phase=state['phase'])
    if accepted is None or latest is None:
        # driver 已确认收尾回复/退出且禁止追加时，缺证据必须显式未完成，不能继续空等到硬超时。
        return dict(result, action='wait' if allow_next else 'incomplete', phase=state['phase'])
    if latest['role'] != 'assistant' or not latest['normal'] or not latest['linked'] or not latest['text'] or not latest['text'].strip():
        return dict(result, action='wait' if allow_next else 'incomplete', phase=state['phase'])
    if time.time() - path.stat().st_mtime < idle_seconds:
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


def _process_timed(action: str, state_path: Path, project: Path, run_id: str,
        initial: str, followups: list[str], resume: bool, idle_seconds: float,
        allow_next: bool, timing: dict) -> dict:
    if not isinstance(timing, dict):
        raise ValueError('补充时间快照须为对象')
    offsets = timing.get('offsets_sec')
    timeout, wrapup = timing.get('timeout_sec'), timing.get('wrapup_sec')
    if type(timing.get('schema')) is not int or timing['schema'] not in (1, 2) \
            or type(timeout) is not int or timeout < 1 or type(wrapup) is not int or wrapup < 0 \
            or not isinstance(offsets, list) or len(offsets) != len(followups):
        raise ValueError('补充时间快照无效')
    # 账号镜像须和管理端按相同版本校验，历史计划及其摘要不随新策略改变。
    lower, upper = ((timeout + 9) // 10, timeout * 6 // 10) if timing['schema'] == 1 else (
        (timeout + 19) // 20, timeout * 3 // 10)
    if any(type(x) is not int or not lower <= x <= upper
            or x >= timeout - wrapup for x in offsets) or offsets != sorted(set(offsets)):
        raise ValueError('补充时间快照无效')
    timing_digest = hashlib.sha256(json.dumps(timing, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    digest = plan_digest(run_id, followups)
    if state_path.exists() or state_path.is_symlink():
        state = _read(state_path, MAX_STATE_BYTES)
    elif action == 'init' and not resume:
        state = {'schema': 2, 'run_id': run_id, 'plan_digest': digest, 'timing_digest': timing_digest,
            'initial_digest': hashlib.sha256(initial.encode()).hexdigest(),
            'completed_stages': 0, 'phase': 'awaiting', 'session': '', 'started_at': None,
            'cursor': {p.name: p.stat().st_size for p in _files(project)},
            'items': [{'status': 'scheduled', 'cursor': {}, 'queue_entry': None,
                'input_entry': None, 'reply_entry': None} for _ in followups]}
        _write(state_path, state)
    else:
        raise ValueError('缺少原定时状态，恢复不能重抽或初始化')
    original = json.dumps(state, sort_keys=True)
    # 复用旧模式的运行身份、游标及会话校验，计数另按消息证据验证。
    _validate(dict(state, schema=1, completed_stages=0, phase='awaiting'), run_id, digest,
        1 + len(followups), initial)
    items = state.get('items')
    started = state.get('started_at')
    if type(state.get('schema')) is not int or state['schema'] != 2 \
            or state.get('timing_digest') != timing_digest \
            or not isinstance(items, list) or len(items) != len(followups) \
            or state.get('phase') not in ('awaiting', 'pending', 'complete') \
            or type(state.get('completed_stages')) is not int or not 0 <= state['completed_stages'] <= 1 + len(followups) \
            or (started is not None and (type(started) not in (int, float) or not math.isfinite(started) or started <= 0)):
        raise ValueError('定时状态与原计划不匹配')
    seen_scheduled = False
    for item in items:
        if not isinstance(item, dict) or item.get('status') not in ('scheduled', 'pending', 'queued', 'consumed', 'completed'):
            raise ValueError('定时消息状态无效')
        _validate(dict(state, schema=1, completed_stages=0, phase='awaiting', cursor=item.get('cursor')),
            run_id, digest, 1 + len(followups), initial)
        if seen_scheduled and item['status'] != 'scheduled':
            raise ValueError('定时消息不能跳过前序投递')
        seen_scheduled = seen_scheduled or item['status'] in ('scheduled', 'pending')
        for key, required in (('queue_entry', item['status'] == 'queued'),
                ('input_entry', item['status'] in ('consumed', 'completed')),
                ('reply_entry', item['status'] == 'completed')):
            if (item.get(key) is not None and not isinstance(item[key], str)) or (required and not item.get(key)):
                raise ValueError('定时消息证据键无效')
    if state['phase'] == 'complete' and (state['completed_stages'] != 1 + len(followups)
            or any(item['status'] != 'completed' for item in items)):
        raise ValueError('定时完成状态不一致')
    accepted, _, path = _evidence(state, project, initial)
    if state['session'] and accepted is None:
        # 已确认过的初始输入不应再次消失；拒绝覆盖原进度，避免损坏日志被当作尚未开始。
        raise ValueError('原主会话输入证据缺失，已保留原阶段状态')
    latest = None
    records, ancestry = [], {}
    if accepted:
        state['session'] = path.name
        records = read_dialogue(path, state['cursor'].get(path.name, 0), include_queue=True)
        tracked = {accepted['key']}
        for text in followups:
            inputs = [r for r in records if r['role'] == 'user' and r['normal']
                and r['text'] is not None and _matches_input(r['text'], text)]
            if len(inputs) > 1:
                raise ValueError('定时业务输入重复，归属不确定')
            tracked.update(r['key'] for r in inputs)
        # 入队记录无 UUID，只确认传输；真正消费和完成仍依赖普通消息父链。
        # 仅跟踪最多三条业务输入的祖先标记，避免长任务保存整条祖先链造成平方内存增长。
        for record in records:
            if record['role'] == 'queue':
                continue
            ancestors = ancestry.get(record['parent_key'], set())
            ancestry[record['key']] = ancestors | ({record['key']} if record['key'] in tracked else set())
        dialogue = [r for r in records if r['role'] != 'queue']
        latest = dialogue[-1] if dialogue else None
        for index, item in enumerate(items):
            boundary = item['cursor'].get(path.name, 0)
            matches = [r for r in records if r['text'] is not None and _matches_input(r['text'], followups[index])
                and int(r['key'].rsplit(':', 1)[1]) >= boundary
                and (r['role'] == 'queue' or r['role'] == 'user' and r['normal']
                    and (accepted['id'] is None or r['id'] is None or accepted['key'] in ancestry[r['key']]))]
            users = [r for r in matches if r['role'] == 'user']
            queues = [r for r in matches if r['role'] == 'queue']
            if len(users) > 1 or len(queues) > 1 or matches and item['status'] == 'scheduled':
                raise ValueError('定时输入重复或未经投递，归属不确定')
            if item.get('input_entry') and not any(r['key'] == item['input_entry'] for r in users) \
                    or item.get('queue_entry') and not any(r['key'] == item['queue_entry'] for r in queues):
                raise ValueError('原定时投递证据缺失')
            if queues:
                item['queue_entry'] = queues[0]['key']
                if item['status'] == 'pending':
                    item['status'] = 'queued'
            if users:
                item['input_entry'] = users[0]['key']
                if item['status'] != 'completed':
                    item['status'] = 'consumed'
            if item.get('reply_entry'):
                replies = [r for r in dialogue if r['key'] == item['reply_entry'] and r['role'] == 'assistant'
                    and r['normal'] and r['text'] and (users[0]['id'] is None or r['id'] is None
                        or item['input_entry'] in ancestry[r['key']])]
                if not replies:
                    raise ValueError('原定时完成证据缺失')
    if resume and any(item['status'] in ('pending', 'queued') for item in items):
        # 原生队列只在旧 CLI 内存中，重启后不能把历史 enqueue 当作消息仍会执行。
        raise ValueError('补充消息投递结果不确定，原队列未消费，禁止盲目重发')
    if action == 'start' and started is None:
        state['started_at'] = time.time()
    elif resume and started is None:
        raise ValueError('原运行缺少投递时钟，不能猜测恢复时间')
    stable_reply = latest is not None and latest['role'] == 'assistant' and latest['normal'] \
        and latest['text'] and latest['text'].strip() and time.time() - path.stat().st_mtime >= idle_seconds
    if stable_reply:
        for item in items:
            if item['status'] in ('consumed', 'completed') and (latest['id'] is None
                    or item['input_entry'] in ancestry[latest['key']]
                    or any(r['key'] == item['input_entry'] and r['id'] is None for r in records)):
                item.update(status='completed', reply_entry=latest['key'])
    initial_done = bool(stable_reply and (accepted['id'] is None or latest['id'] is None
        or accepted['key'] in ancestry[latest['key']]))
    state['completed_stages'] = int(initial_done) + sum(x['status'] == 'completed' for x in items)
    complete = initial_done and all(x['status'] == 'completed' for x in items)
    state['phase'] = 'complete' if complete else 'pending' if any(x['status'] == 'pending' for x in items) else 'awaiting'
    result = {'action': 'complete' if complete else 'wait', 'phase': state['phase']}
    if not complete and action == 'advance' and not allow_next:
        result['action'] = 'incomplete'
    elif action == 'tick' and allow_next and accepted and state['started_at'] is not None:
        for index, item in enumerate(items):
            if item['status'] == 'pending':
                break
            if item['status'] == 'scheduled':
                if time.time() >= state['started_at'] + offsets[index]:
                    item.update(status='pending', cursor={p.name: p.stat().st_size for p in _files(project)})
                    state['phase'] = 'pending'
                    result = {'action': 'send', 'index': index + 1, 'text': followups[index], 'phase': 'pending'}
                break
    if json.dumps(state, sort_keys=True) != original:
        _write(state_path, state)
    return result


def main() -> None:
    """提供 driver 使用的无网络命令行入口。

    :return: None；错误仅输出固定诊断，不输出题面和会话正文。
    """
    parser = argparse.ArgumentParser(description='有限业务补充阶段控制')
    parser.add_argument('action', choices=('init', 'observe', 'advance', 'start', 'tick'))
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--idle', type=float, default=10)
    parser.add_argument('--no-next', action='store_true')
    args = parser.parse_args()
    try:
        followups = json.loads(os.environ.get('TASK_FOLLOWUPS_JSON', '[]'))
        timing_raw = os.environ.get('TASK_FOLLOWUP_TIMING_JSON')
        timing = json.loads(timing_raw) if timing_raw else None
        if timing_raw and (not isinstance(timing, dict)
                or 'TIMEOUT_SEC' in os.environ and timing.get('timeout_sec') != int(os.environ['TIMEOUT_SEC'])
                or 'TIMEOUT_WRAPUP_SEC' in os.environ and timing.get('wrapup_sec') != int(os.environ['TIMEOUT_WRAPUP_SEC'])):
            raise ValueError('投递时间快照与执行预算不一致')
        value = process(args.action, args.state, args.project, os.environ.get('RUN_ID', ''),
            os.environ.get('TASK_INITIAL_PROMPT', ''), followups, args.resume, args.idle, not args.no_next,
            timing)
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({'action': 'error', 'message': '自动补充阶段证据无效或投递结果不确定，需核对原运行'}))
        sys.exit(1)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
