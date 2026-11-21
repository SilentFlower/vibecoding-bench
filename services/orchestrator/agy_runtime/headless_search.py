"""执行固定原版的独立搜索，从本次工具轨迹提取结构化来源。"""
import json
import os
import select
import signal
import sqlite3
import subprocess
import tempfile
import time
import uuid

from .contract import InputError
from .credentials import publish_access_document
from .storage import private_dir


FRAME_LIMIT = 64 * 1024 * 1024
AGENT_NAME = 'flower-web-search'
PERMISSIONS = {'permissions': {'deny': [
    'command(*)', 'read_file(*)', 'write_file(*)', 'read_url(*)', 'execute_url(*)', 'mcp(*)']}}
AGENT = '''---
name: flower-web-search
description: 执行一次网页搜索
mainAgent: true
subagent: false
tools: [search_web]
commandExecutionPolicy: "off"
inheritMcp: false
inheritCustomizations: false
---

只使用 search_web 执行查询。query 参数使用调用方给出的原始字符串。
工具执行后结束当前回合。
'''


def _varint(raw, start):
    value = 0
    for shift in range(0, 70, 7):
        if start + shift // 7 >= len(raw):
            break
        byte = raw[start + shift // 7]
        value |= (byte & 127) << shift
        if byte < 128 and value < 1 << 64:
            return value, start + shift // 7 + 1
    raise InputError('invalid_search_trajectory')


def _fields(raw):
    fields = {}
    cursor = 0
    while cursor < len(raw):
        tag, cursor = _varint(raw, cursor)
        number, wire = divmod(tag, 8)
        if not number or wire not in (0, 1, 2, 5):
            raise InputError('invalid_search_trajectory')
        if wire == 0:
            value, cursor = _varint(raw, cursor)
        else:
            if wire == 2:
                size, cursor = _varint(raw, cursor)
            else:
                size = 8 if wire == 1 else 4
            if cursor + size > len(raw):
                raise InputError('invalid_search_trajectory')
            value = raw[cursor:cursor + size]
            cursor += size
        fields.setdefault(number, []).append(value)
    return fields


def _only(fields, number):
    values = fields.get(number, ())
    if len(values) != 1 or not isinstance(values[0], bytes):
        raise InputError('invalid_search_trajectory')
    return values[0]


def _sources(home, conversation, index, query):
    # 1.5.9 的 stream-json 回执仅含搜索状态。读取对应 SQLite 步骤里的 SearchWeb Any，避免从模型总结提取链接。
    if not isinstance(conversation, str) or str(uuid.UUID(conversation)) != conversation:
        raise InputError('invalid_search_conversation')
    path = home / '.gemini/antigravity-cli/conversations' / (conversation + '.db')
    if path.is_symlink() or not path.is_file():
        raise InputError('missing_search_trajectory')
    database = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        row = database.execute('''SELECT step_payload FROM steps
            WHERE idx=? AND step_type=132 AND status=3 AND step_format=0 AND length(step_payload)<=?
            AND EXISTS (SELECT 1 FROM trajectory_meta WHERE cascade_id=?)''',
            (index, FRAME_LIMIT, conversation)).fetchone()
    finally:
        database.close()
    if row is None or not isinstance(row[0], bytes):
        raise InputError('missing_search_trajectory')
    generic = _fields(_only(_fields(row[0]), 140))
    result = _fields(_only(generic, 2))
    native = _fields(_only(result, 6))
    if _only(native, 1) != b'type.googleapis.com/exa.cortex.core.tools.SearchWeb':
        raise InputError('invalid_search_trajectory')
    search = _fields(_only(native, 2))
    if _only(search, 1).decode() != query:
        raise InputError('search_query_mismatch')
    sources = []
    seen = set()
    for raw in search.get(3, ()):
        if not isinstance(raw, bytes):
            raise InputError('invalid_search_trajectory')
        document = _fields(raw)
        url = _only(document, 1).decode()
        title = _only(document, 4).decode() if 4 in document else ''
        if url not in seen:
            sources.append({'url': url, 'title': title})
            seen.add(url)
    return sources


def _events(process, until, cancelled):
    buffer = bytearray()
    while True:
        if cancelled.is_set():
            raise InputError('request_cancelled')
        remaining = until - time.monotonic()
        if remaining <= 0:
            raise InputError('request_deadline_exceeded')
        ready, _, _ = select.select([process.stdout], [], [], min(remaining, .2))
        if not ready:
            continue
        block = os.read(process.stdout.fileno(), 65536)
        if not block:
            if buffer:
                raise InputError('incomplete_search_event')
            return
        buffer.extend(block)
        while (newline := buffer.find(b'\n')) >= 0:
            event = json.loads(buffer[:newline])
            del buffer[:newline + 1]
            if not isinstance(event, dict):
                raise InputError('invalid_search_event')
            yield event
        if len(buffer) > FRAME_LIMIT:
            raise InputError('search_event_limit')


def run_search(image, folder, model, snapshot, proxy, query, until, cancelled, *, ca_file=None):
    """运行一次原版搜索并核验来源。@param image 封存执行体的 FD。@param folder 请求私有目录。
    @param model 已选公开模型。@param snapshot 本账号 AT 快照。@param proxy 账号代理。
    @param query 原始查询。@param until 单调截止。@param cancelled 取消信号。
    @param ca_file 隔离回环的证书。@return 结构化来源及真实用量。"""
    home = private_dir(folder / 'home')
    work = private_dir(folder / 'work')
    agents = private_dir(work / '.agents' / 'agents')
    (agents / (AGENT_NAME + '.md')).write_text(AGENT, encoding='utf-8')
    publish_access_document(home, snapshot)
    env = {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TERM': 'dumb',
        'USER': 'agy-search', 'TMPDIR': str(folder), 'NO_PROXY': '127.0.0.1,localhost',
        'AGY_CLI_DISABLE_AUTO_UPDATE': 'true'}
    if proxy:
        env.update(HTTP_PROXY=proxy, HTTPS_PROXY=proxy, ALL_PROXY=proxy)
    if ca_file:
        env['SSL_CERT_FILE'] = str(ca_file)
    prompt = '执行一次 search_web，query 参数逐字使用这个 JSON 字符串。随后结束回合。\n' + json.dumps(query, ensure_ascii=False)
    remaining = until - time.monotonic()
    if cancelled.is_set() or remaining <= 0:
        raise InputError('request_deadline_exceeded')
    # 查询走 stdin，进程参数只保留固定选项和已核对的模型名。
    with tempfile.TemporaryFile(dir=folder) as stdin:
        stdin.write((json.dumps({'event': 'user', 'message': {'content': prompt}}, ensure_ascii=False) + '\n').encode())
        stdin.seek(0)
        command = [f'/proc/self/fd/{image}', '--agent', AGENT_NAME, '--model', model,
            '--settings', json.dumps(PERMISSIONS),
            '--disable-slash-commands', '--output-format', 'stream-json', '-p', '',
            '--input-format', 'stream-json', '--print-timeout', str(max(1, int(remaining))) + 's']
        process = subprocess.Popen(command, cwd=work, env=env, stdin=stdin, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, pass_fds=(image,), start_new_session=True)
        try:
            return _receipt(process, home, query, until, cancelled)
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            process.stdout.close()


def _receipt(process, home, query, until, cancelled):
    result = None
    search = None
    for event in _events(process, until, cancelled):
        if event.get('event') == 'result':
            if result is not None:
                raise InputError('invalid_search_terminal')
            result = event['result']
        if event.get('event') != 'step_update':
            continue
        step = event['step_update']
        if step.get('step_type') != 'tool':
            continue
        if step.get('tool_name') not in ('search_web', 'manage_task'):
            raise InputError('unexpected_search_tool')
        if step.get('tool_name') == 'search_web' and step.get('state') != 'ACTIVE':
            info = step.get('tool_info', {})
            if search is not None or step.get('state') != 'DONE' or info.get('error') \
                    or info.get('parameters', {}).get('query') != query:
                raise InputError('search_tool_failed')
            search = step
    remaining = until - time.monotonic()
    if remaining <= 0 or process.wait(timeout=remaining) or not isinstance(result, dict) \
            or result.get('status') != 'SUCCESS' or not search \
            or result.get('conversation_id') != search.get('conversation_id') \
            or type(search.get('step_index')) is not int:
        raise InputError('search_result_unavailable')
    sources = _sources(home, search['conversation_id'], search['step_index'], query)
    raw = result.get('usage', {})
    counts = {key: raw.get(key, 0) for key in ('input_tokens', 'output_tokens', 'thinking_tokens', 'cache_read_tokens')}
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise InputError('invalid_search_usage')
    return {'sources': sources, 'usage': {
        'input_tokens': max(0, counts['input_tokens'] - counts['cache_read_tokens']),
        'cache_read_input_tokens': counts['cache_read_tokens'],
        'output_tokens': counts['output_tokens'] + counts['thinking_tokens']}}
