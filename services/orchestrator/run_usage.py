"""普通Run共享的有界统计读取，保持原sidecar与Claude会话的聚合语义。"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from run_artifacts import list_workspace_files
from runtime_files import directory_fd

MAX_USAGE_BYTES = 64 * 1024 * 1024
MAX_USAGE_LINE_BYTES = 8 * 1024 * 1024


def usage_input_tokens(usage: dict) -> int:
    """沿原规则计算普通输入与缓存token。:param usage: 原usage。:return: 输入总量。"""
    return sum(int(usage.get(key) or 0) for key in
        ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))


def _records(paths):
    remaining, count = MAX_USAGE_BYTES, 0
    for path in paths:
        count += 1
        if count > 10000:
            raise ValueError('运行用量文件数量超过读取上限')
        parent = directory_fd(path.parent)
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        finally:
            os.close(parent)
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('运行用量必须读取普通单链接文件')
            if info.st_size > remaining:
                raise ValueError('运行用量总字节超过读取上限')
            remaining -= info.st_size
            unread = info.st_size
            while unread:
                line = source.readline(min(unread, MAX_USAGE_LINE_BYTES + 1))
                if len(line) > MAX_USAGE_LINE_BYTES:
                    raise ValueError('运行用量单行超过读取上限')
                if not line:
                    raise ValueError('运行用量文件在读取期间发生截断')
                unread -= len(line)
                try:
                    value = json.loads(line.decode('utf-8', errors='ignore'))
                except (ValueError, UnicodeError):
                    continue
                if isinstance(value, dict):
                    yield value


def native_session_usage(base: Path) -> dict:
    """保持普通Run的requestId和原usage回退去重规则。

    :param base: 该Run实际Claude session物理目录。
    :return: 原输入、输出、请求数与采集可用性。
    """
    result = {'tokens_in': 0, 'tokens_out': 0, 'requests': 0, 'usage_available': False}
    try:
        entries = list_workspace_files(base)
    except FileNotFoundError:
        return result
    paths = [base / item['path'] for item in entries if item['type'] == 'file' and item['path'].endswith('.jsonl')]
    paths.sort(key=lambda path: path.lstat().st_mtime_ns)
    seen = set()
    for record in _records(paths):
        message = record.get('message')
        if (not isinstance(message, dict) or message.get('role') != 'assistant'
                or record.get('type') not in (None, 'assistant') or not isinstance(message.get('usage'), dict)):
            continue
        usage = message['usage']
        key = record.get('requestId')
        if not isinstance(key, str) or not key:
            key = json.dumps(usage, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        result['tokens_in'] += usage_input_tokens(usage)
        result['tokens_out'] += int(usage.get('output_tokens') or 0)
        result['requests'] += 1
    result['usage_available'] = result['requests'] > 0
    return result


def run_usage(paths: list[Path], native) -> dict:
    """共享原sidecar阶段、错误、flow去重及原生回退语义。

    :param paths: 已定位该Run各尝试的stats文件。
    :param native: 读取原生会话聚合的回调。
    :return: 原公开stats字段。
    """
    if not paths:
        session = native()
        return {**session, 'errors': 0, 'available': bool(session['usage_available']),
            'source': 'claude_session' if session['usage_available'] else 'none'}
    tokens_in = tokens_out = errors = fallback_requests = 0
    request_ids, response_ids, usage_available = set(), set(), False
    for record in _records(paths):
        if 'error' in record:
            errors += 1
            continue
        if record.get('phase') == 'request':
            flow = record.get('flow_id')
            if flow:
                request_ids.add(str(flow))
            else:
                fallback_requests += 1
            continue
        if record.get('phase') and record['phase'] != 'response':
            continue
        flow = record.get('flow_id')
        if flow:
            response_ids.add(str(flow))
        else:
            fallback_requests += 1
        usage = record.get('usage') or {}
        if not isinstance(usage, dict):
            usage = {}
        usage_available = usage_available or 'input_tokens' in usage or 'output_tokens' in usage
        tokens_in += usage_input_tokens(usage)
        tokens_out += int(usage.get('output_tokens') or 0)
    requests, source = len(request_ids | response_ids) + fallback_requests, 'sidecar'
    if not usage_available:
        session = native()
        if session['usage_available']:
            tokens_in, tokens_out, usage_available, source = session['tokens_in'], session['tokens_out'], True, 'claude_session'
    return {'tokens_in': tokens_in, 'tokens_out': tokens_out, 'requests': requests, 'errors': errors,
        'available': requests > 0 or usage_available, 'usage_available': usage_available, 'source': source}
