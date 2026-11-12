"""按逐来源原生边界累计分类用量，缺失证据保持未知。"""
from __future__ import annotations

import json
import re
from pathlib import Path


TOKEN_FIELDS = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')


def observed_model(directory: Path, response: dict, session_id: str) -> str:
    """从已核对主消息的精确字节位置读取实际模型，不探测可用模型。

    :param directory: 该角色自己的固定原生日志目录。
    :param response: 父链观察器返回的主assistant摘要。
    :param session_id: 固定会话身份。
    :return: 已实际使用的模型ID；缺失或身份冲突明确拒绝。
    """
    name=session_id+'.jsonl'
    prefix=name+':'
    if not response['key'].startswith(prefix):
        raise ValueError('实际模型消息不属于固定主会话')
    offset=int(response['key'][len(prefix):])
    path=directory/name
    if offset<0 or path.is_symlink():
        raise ValueError('实际模型证据位置不合法')
    with path.open('rb') as stream:
        stream.seek(offset)
        raw=stream.readline(8*1024*1024+1)
    if not raw.endswith(b'\n') or len(raw)>8*1024*1024:
        raise ValueError('实际模型证据缺失或超限')
    record=json.loads(raw)
    if not isinstance(record,dict) or not isinstance(record.get('message'),dict):
        raise ValueError('原生实际模型消息结构不合法')
    message=record.get('message',{})
    model=message.get('model')
    if (record.get('uuid')!=response['id'] or record.get('isSidechain') or record.get('isMeta')
            or record.get('isApiErrorMessage') or message.get('role')!='assistant'
            or not isinstance(model,str) or len(model)>128 or not re.fullmatch(r'[A-Za-z0-9._\-\[\]]+',model)):
        raise ValueError('原生主会话缺少可确认的实际模型')
    return model


def _merge_response(previous: dict, current: dict) -> dict:
    return {field:max(value for value in (previous[field],current[field]) if value is not None)
        if previous[field] is not None or current[field] is not None else None for field in TOKEN_FIELDS}


def source_usage(directory: Path, start: dict | None, end: dict | None, session_id: str) -> dict:
    """有界读取固定主会话字节区间，不回退扫描整份历史。

    :param directory: 该角色自己的持久日志根。
    :param start: 精确来源起点。
    :param end: 精确来源终点，未封存则未知。
    :param session_id: 固定主会话身份。
    :return: 去重原生响应与区间覆盖情况。
    """
    if not isinstance(start, dict) or not isinstance(end, dict):
        return {'responses': {}, 'complete': False}
    name = session_id + '.jsonl'
    offset, limit = start.get(name, 0), end.get(name, 0)
    responses = {}
    try:
        path = directory / name
        if (type(offset) is not int or type(limit) is not int or not 0 <= offset <= limit
                or path.is_symlink() or not path.is_file() or path.stat().st_size < limit or limit - offset > 64 * 1024 * 1024):
            return {'responses': {}, 'complete': False}
        with path.open('rb') as stream:
            stream.seek(offset)
            while stream.tell() < limit:
                position = stream.tell()
                line = stream.readline(min(8 * 1024 * 1024, limit - position) + 1)
                if stream.tell() > limit or not line.endswith(b'\n'):
                    return {'responses': {}, 'complete': False}
                record = json.loads(line)
                message = record.get('message')
                if (record.get('type') != 'assistant' or record.get('isSidechain') or record.get('isMeta')
                        or record.get('isApiErrorMessage') or not isinstance(message, dict)
                        or message.get('role') != 'assistant' or message.get('model') == '<synthetic>'):
                    continue
                key = message.get('id') or record.get('requestId')
                if not isinstance(key, str) or not key:
                    return {'responses': {}, 'complete': False}
                usage = message.get('usage')
                value = {field: usage.get(field) if isinstance(usage, dict) and type(usage.get(field)) is int
                    and usage[field] >= 0 else None for field in TOKEN_FIELDS}
                identity = session_id + ':' + key
                responses[identity] = _merge_response(responses[identity],value) if identity in responses else value
        return {'responses': responses, 'complete': bool(responses) or limit==offset}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {'responses': {}, 'complete': False}


def aggregate_usage(sources: list[dict]) -> dict:
    """对多个Run及quota来源去重，按字段报告部分已知小计。

    :param sources: source_usage 的结果列表。
    :return: 输入、输出、缓存、请求与覆盖信息；未知不补零。
    """
    responses = {}
    for source in sources:
        for key, value in source['responses'].items():
            responses[key] = _merge_response(responses[key],value) if key in responses else value
    result = {}
    known_fields = {}
    for field in TOKEN_FIELDS:
        values = [value[field] for value in responses.values() if value[field] is not None]
        result[field] = sum(values) if values else None
        known_fields[field] = len(values)
    result.update(requests=len(responses) if responses else None, sources=len(sources),
        known_sources=sum(source['complete'] for source in sources), known_fields=known_fields,
        complete=bool(sources) and all(source['complete'] for source in sources)
            and bool(responses) and all(count == len(responses) for count in known_fields.values()))
    return result
