"""抓包索引脱敏、分代聚合和受限预览，读取不会修改原始证据。"""
from __future__ import annotations

import json
import os
import re
from hashlib import md5
from math import isfinite
from pathlib import Path
from stat import S_ISREG


_SENSITIVE_HEADER_RE = re.compile(
    r"(authorization|cookie|set-cookie|x-api-key|token|secret|credential|key)",
    re.IGNORECASE,
)
TLS_PREVIEW_MAX_BYTES = 4 * 1024 * 1024
TLS_PREVIEW_MAX_LINES = 256
TLS_PREVIEW_MAX_RECORDS = 64
TLS_PREVIEW_MAX_LINE_BYTES = 512 * 1024
_TLS_VECTOR_LIMIT = 4096
_TLS_IDENTIFIER_RE = re.compile(r'[A-Za-z0-9_-]{1,128}')
_TLS_SOURCE_RE = re.compile(r'(?:run|continue|projects|warmup):[A-Za-z0-9_-]{1,128}:[0-9]{1,20}')
_TLS_VERSION_RE = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?')
_TLS_JA3_RE = re.compile(r'[0-9]+,' + ','.join([r'(?:[0-9]+(?:-[0-9]+)*)?'] * 4))


def _tls_integer(value: object, maximum: int = 65535) -> bool:
    """只接受协议整数，防止布尔或任意嵌套值混入公开向量。"""
    return type(value) is int and 0 <= value <= maximum


def _tls_vector(value: object, maximum: int = 65535) -> tuple[list[int] | None, bool]:
    """限制公开向量大小，并单独报告丢弃的非法或超额字段。"""
    if value is None:
        return None, False
    if not isinstance(value, list):
        return None, True
    result = [item for item in value[:_TLS_VECTOR_LIMIT] if _tls_integer(item, maximum)]
    return result, len(result) != len(value)


def _tls_public_context(value: object) -> dict:
    """逐字段重建执行快照，不能把新出现的私有字段随原对象公开。"""
    if not isinstance(value, dict) or type(value.get('schema')) is not int or value['schema'] != 1:
        return {}
    out = {'schema': 1}
    for name, pattern, limit in (('source', _TLS_SOURCE_RE, 256),
            ('claude_code_version', _TLS_VERSION_RE, 80), ('run_id', _TLS_IDENTIFIER_RE, 128),
            ('work_id', _TLS_IDENTIFIER_RE, 128)):
        item = value.get(name)
        if isinstance(item, str) and len(item) <= limit and pattern.fullmatch(item):
            out[name] = item
    if value.get('namespace') in ('projects', 'warmup'):
        out['namespace'] = value['namespace']
    source = value.get('claude_code_version_source')
    if source in ('explicit', 'account', 'global', 'legacy-explicit', 'legacy-account', 'legacy-global', 'legacy-execution'):
        out['claude_code_version_source'] = source
    return out


def _tls_public_record(value: object) -> dict | None:
    """按 schema 1 重建握手预览，原始正文及未知嵌套内容绝不透传。"""
    if not isinstance(value, dict) or type(value.get('schema')) is not int or value['schema'] != 1:
        return None
    if value.get('event') != 'tls_clienthello' or value.get('direction') != 'client_to_recorder':
        return None
    status = value.get('parse_status')
    if status not in ('ok', 'error', 'unsupported', 'oversize'):
        return None
    out = {'schema': 1, 'event': 'tls_clienthello', 'direction': 'client_to_recorder',
        'parse_status': status, 'capture_context': _tls_public_context(value.get('capture_context'))}
    timestamp = value.get('ts')
    if type(timestamp) in (int, float) and isfinite(timestamp):
        out['ts'] = timestamp
    connection = value.get('client_connection_id')
    if isinstance(connection, str) and _TLS_IDENTIFIER_RE.fullmatch(connection):
        out['client_connection_id'] = connection
    for name, choices in (('transport', ('tcp',)), ('target_status', ('target', 'non_target', 'unclassified')),
            ('capture_scope', ('all', 'anthropic')), ('capture_context_status', ('ok', 'missing', 'invalid', 'source_mismatch'))):
        if value.get(name) in choices:
            out[name] = value[name]
    limited = status == 'ok' and (not _tls_integer(value.get('legacy_version'))
        or not isinstance(value.get('cipher_suites'), list) or not isinstance(value.get('extensions'), list))
    if _tls_integer(value.get('legacy_version')):
        out['legacy_version'] = value['legacy_version']
    for name in ('cipher_suites', 'signature_algorithms', 'supported_groups', 'supported_versions', 'ec_point_formats'):
        out[name], incomplete = _tls_vector(value.get(name), 255 if name == 'ec_point_formats' else 65535)
        limited = limited or incomplete
    for name, fields in (('extensions', ('type', 'length')), ('key_share', ('group', 'key_exchange_length'))):
        items = value.get(name)
        if items is None:
            out[name] = None
            continue
        if not isinstance(items, list):
            out[name], limited = None, True
            continue
        # 仅公开类型和长度；未知扩展原文、PSK 与 key exchange 字节必须留在私有文件。
        out[name] = [{key: item[key] for key in fields} for item in items[:_TLS_VECTOR_LIMIT]
            if isinstance(item, dict) and all(_tls_integer(item.get(key)) for key in fields)]
        limited = limited or len(out[name]) != len(items)
    sni = value.get('sni')
    if sni is None or isinstance(sni, str) and re.fullmatch(r'[A-Za-z0-9._-]{1,253}', sni):
        out['sni'] = sni
    else:
        limited = True
    protocols = value.get('alpn_protocols')
    if protocols is None:
        out['alpn_protocols'] = None
    elif isinstance(protocols, list):
        out['alpn_protocols'] = []
        for item in protocols[:_TLS_VECTOR_LIMIT]:
            limited = limited or not isinstance(item, dict)
            text = item.get('text') if isinstance(item, dict) else None
            if isinstance(text, str) and re.fullmatch(r'[\x21-\x7e]{1,255}', text):
                out['alpn_protocols'].append({'text': text})
            else:
                out['alpn_protocols'].append({'text': None})
        limited = limited or len(protocols) > _TLS_VECTOR_LIMIT
    else:
        out['alpn_protocols'], limited = None, True
    fingerprint = value.get('ja3')
    out['ja3'] = None
    limited = limited or status == 'ok' and fingerprint is None
    if fingerprint is not None:
        string = fingerprint.get('string') if isinstance(fingerprint, dict) else None
        digest = fingerprint.get('md5') if isinstance(fingerprint, dict) else None
        if isinstance(string, str) and len(string) <= 65536 and _TLS_JA3_RE.fullmatch(string) and \
                isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{32}', digest) and \
                md5(string.encode('ascii')).hexdigest() == digest:
            out['ja3'] = {'string': string, 'md5': digest}
        else:
            limited = True
    out['fields_incomplete'] = limited
    return out


def _tls_preview(paths: list[Path]) -> dict:
    """在全组共享预算内读取 JSONL；半行或坏数据只返回固定状态。"""
    entries, issues = [], set()
    bytes_read, lines_read, truncated = 0, 0, False
    for number, path in enumerate(paths):
        if bytes_read >= TLS_PREVIEW_MAX_BYTES or lines_read >= TLS_PREVIEW_MAX_LINES or len(entries) >= TLS_PREVIEW_MAX_RECORDS:
            truncated = True
            break
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as stream:
                observed = os.fstat(stream.fileno())
                if not S_ISREG(observed.st_mode):
                    raise OSError('unsupported capture file')
                # 一次请求读取一个文件快照，追加中的后半行不能误报成完整 JSON。
                while stream.tell() < observed.st_size:
                    remaining = TLS_PREVIEW_MAX_BYTES - bytes_read
                    if remaining <= 0 or lines_read >= TLS_PREVIEW_MAX_LINES or len(entries) >= TLS_PREVIEW_MAX_RECORDS:
                        truncated = True
                        break
                    line = stream.readline(min(TLS_PREVIEW_MAX_LINE_BYTES + 1, remaining, observed.st_size - stream.tell()))
                    if not line:
                        issues.add('incomplete_line')
                        break
                    bytes_read += len(line)
                    lines_read += 1
                    if len(line) > TLS_PREVIEW_MAX_LINE_BYTES:
                        issues.add('line_limit')
                        truncated = True
                        break
                    if not line.endswith(b'\n'):
                        if stream.tell() < observed.st_size:
                            truncated = True
                        issues.add('incomplete_line')
                        break
                    try:
                        value = _tls_public_record(json.loads(line))
                    except (ValueError, UnicodeError, RecursionError, OverflowError):
                        value = None
                    if value is None:
                        issues.add('invalid_record')
                    else:
                        entries.append(value)
                        if value['fields_incomplete'] or value['parse_status'] != 'ok':
                            issues.add('partial_record')
        except OSError:
            issues.add('unreadable_file')
        if truncated and number + 1 < len(paths):
            break
    if not paths:
        status, message = 'unavailable', '该抓包尚未保存 ClientHello 记录'
    elif truncated or issues:
        status, message = 'partial', '仅展示有界扫描内的有效握手；存在未读、未完成或异常记录'
    elif entries:
        status, message = 'complete', '已保存客户端到 Recorder 的握手；版本为执行快照，连接 ID 可关联 HTTP'
    else:
        status, message = 'empty', '尚未保存完整 ClientHello 行'
    exact = not truncated and not issues
    return {'available': bool(paths), 'status': status, 'message': message, 'entries': entries,
        'scanned_records': len(entries), 'scanned_lines': lines_read, 'bytes_read': bytes_read,
        'total_records': len(entries) if exact else None, 'count_exact': exact,
        'truncated': truncated, 'issues': sorted(issues)}


def capture_context_json(source: str, version: str, *, run_id: str | None = None,
                         namespace: str | None = None, work_id: str | None = None,
                         version_source: str | None = None) -> str:
    """序列化实际启动快照，避免各捕获入口遗漏执行身份。

    :param source: 本次网络监听的完整执行来源。
    :param version: 实际装载的冻结 CLI 版本。
    :param run_id: 普通或续聊对应的真实 run ID。
    :param namespace: 双迭代的服务端固定空间。
    :param work_id: 双迭代对应的真实 work ID。
    :param version_source: 已存在的冻结版本来源；缺失时不推测。
    :return: 仅供 Recorder 进程环境使用的紧凑 JSON。
    """
    value = {'schema': 1, 'source': source, 'claude_code_version': version}
    for key, item in (('run_id', run_id), ('namespace', namespace), ('work_id', work_id),
            ('claude_code_version_source', version_source)):
        if item is not None:
            value[key] = item
    return json.dumps(value, separators=(',', ':'))


def _redact_capture_value(name: str, value: object) -> object:
    """
    对抓包索引预览里的敏感 header 值做脱敏。

    :param name: header 或字段名
    :param value: 原始值
    :return: 可安全展示的值
    """
    if _SENSITIVE_HEADER_RE.search(name):
        return "[redacted]"
    return value


def _redact_capture_headers(headers: object) -> dict[str, object]:
    """
    脱敏 header 对象，供 WebUI / API 预览使用。

    :param headers: header dict
    :return: 脱敏后的 header dict
    """
    if not isinstance(headers, dict):
        return {}
    return {
        str(k): _redact_capture_value(str(k), v)
        for k, v in headers.items()
    }


def _redact_capture_record(record: object) -> object:
    """
    对 capture_index.json 里的单条索引记录做浅层脱敏。

    :param record: 索引记录
    :return: 脱敏后的记录
    """
    if not isinstance(record, dict):
        return record
    out = dict(record)
    for section in ("request", "response"):
        value = out.get(section)
        if not isinstance(value, dict):
            continue
        copied = dict(value)
        copied["headers"] = _redact_capture_headers(copied.get("headers"))
        out[section] = copied
    analysis = out.get("analysis")
    if isinstance(analysis, dict):
        copied = dict(analysis)
        if "cch_headers" in copied:
            copied["cch_headers"] = _redact_capture_headers(copied.get("cch_headers"))
        out["analysis"] = copied
    return out


def _read_capture_index(path: Path) -> dict[str, object]:
    """
    读取并脱敏抓包索引。

    :param path: capture_index.json 路径
    :return: 索引内容；不存在或解析失败时返回可展示状态
    """
    if not path.exists():
        return {
            "available": False,
            "error": "capture_index.json not found",
            "entries": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "error": f"failed to read capture index: {exc}",
            "entries": [],
        }
    if not isinstance(data, dict):
        return {
            "available": False,
            "error": "capture index is not an object",
            "entries": [],
        }
    entries = data.get("entries")
    if isinstance(entries, list):
        data["entries"] = [_redact_capture_record(item) for item in entries]
    data["available"] = True
    return data


def _capture_roots(base: Path) -> list[Path]:
    """兼容原续聊组链接，仅接受同账号 flows 下的受管分组。"""
    roots = [base]
    for directory in sorted(base.glob('continue-*')):
        if directory.is_dir() and (not directory.is_symlink() or (
                directory.resolve().parent == base.resolve().parent and directory.resolve().name.startswith('group-'))):
            roots.append(directory)
    return roots


def _capture_path_allowed(root: Path, path: Path) -> bool:
    """拒绝分组内部的链接，保留已验证的分组根兼容链接。"""
    if path.is_symlink():
        return False
    for parent in path.parents:
        if parent == root:
            return True
        if parent.is_symlink():
            return False
    return False


def _capture_files(base: Path) -> list[dict[str, object]]:
    """
    返回抓包目录下的文件列表。

    :param base: run flows 目录
    :return: 文件元信息列表
    """
    if not base.exists():
        return []
    files: list[dict[str, object]] = []
    paths = {path for root in _capture_roots(base) for path in root.rglob('*')
        if path.is_file() and _capture_path_allowed(root, path)}
    for path in sorted(paths):
        rel = path.relative_to(base)
        if 'cli' in rel.parts or rel.name == 'passive-quota.jsonl':
            continue
        files.append({
            "path": str(rel),
            "size": path.stat().st_size,
        })
    return files


def capture_summary(base: Path, *, running: bool = False) -> dict:
    """聚合旧平铺及各执行代次，索引缺失时仍返回已落盘文件。

    :param base: 调用方已核对账号及执行归属的证据根目录。
    :param running: 业务侧是否仍有活动执行。
    :return: 脱敏索引、文件清单、采样数量及真实完整性状态。
    """
    files = _capture_files(base)
    tls = _tls_preview([base / item['path'] for item in files if Path(item['path']).name == 'tls_clienthello.jsonl'])
    paths = [(root, path) for root in _capture_roots(base)
        for path in [root / 'capture_index.json', *sorted(root.glob('executions/*/capture_index.json'))]]
    indexes, entries, finalizations = [], {}, []
    for root, path in paths:
        if not _capture_path_allowed(root, path):
            continue
        index = _read_capture_index(path)
        if index.get('available'):
            indexes.append(index)
            for item in index.get('entries', []):
                if isinstance(item, dict):
                    entries[(str(path.parent), str(item.get('flow_id')))] = item
    for item in files:
        if Path(item['path']).name != 'capture-status.json':
            continue
        try:
            value = json.loads((base / item['path']).read_text())
            if isinstance(value, dict):
                finalizations.append({key: value.get(key) for key in ('state', 'recorder_graceful', 'message', 'updated_at')})
        except (OSError, ValueError):
            finalizations.append({'state': 'error', 'message': '抓包收尾记录不可读取'})
    values = list(entries.values())
    partial = any(item.get('capture_state') in ('pending', 'interrupted') for item in values)
    partial = partial or any(item.get('state') in ('partial', 'stopping') for item in finalizations)
    partial = partial or tls['status'] == 'partial'
    if any(item.get('state') == 'error' for item in finalizations):
        status, message = 'error', 'Recorder 收尾尚未确认，已保留采集数据'
    elif running:
        status, message = 'collecting', '正在采集；仅展示已落盘内容'
    elif partial or any(item['size'] and Path(item['path']).name not in ('capture-status.json', 'capture_index.json') for item in files) and not values:
        status, message = 'partial', '已有部分数据，响应或索引可能未完成'
    elif values:
        status, message = 'complete', '已保存采集记录'
    else:
        status, message = 'empty', '尚未采到目标流量'
    index = {'available': bool(indexes), 'entries': values, 'total_flows': len(values),
        'cc_versions': sorted({version for item in indexes for version in item.get('cc_versions', [])}),
        'updated_at': max((float(item.get('updated_at') or 0) for item in indexes), default=0)}
    return {'available': bool(files or indexes), 'index_available': bool(indexes), 'index': index,
        'files': files, 'status': status, 'message': message, 'sample_count': len(values), 'finalizations': finalizations,
        'tls_clienthello': tls}


def capture_file_preview(base: Path, relative: str) -> dict:
    """预览脱敏索引、收尾记录或 TLS 白名单，不公开原始正文与恢复材料。

    :param base: 已核对的证据根目录。
    :param relative: 来自本组文件清单的相对路径。
    :return: 受限 JSON 预览。
    """
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or path.name not in ('capture_index.json', 'capture-status.json', 'tls_clienthello.jsonl'):
        raise ValueError('该文件不支持公开预览，请查看脱敏索引和文件清单')
    allowed = {item['path'] for item in _capture_files(base)}
    if relative not in allowed:
        raise ValueError('文件不属于当前抓包')
    if path.name == 'capture_index.json':
        return _read_capture_index(base / path)
    if path.name == 'tls_clienthello.jsonl':
        return _tls_preview([base / path])
    value = json.loads((base / path).read_text())
    return {key: value.get(key) for key in ('state', 'recorder_graceful', 'message', 'updated_at')}


