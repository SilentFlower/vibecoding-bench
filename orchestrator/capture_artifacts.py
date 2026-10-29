"""抓包索引脱敏、分代聚合和受限预览，读取不会修改原始证据。"""
from __future__ import annotations

import json
import re
from pathlib import Path


_SENSITIVE_HEADER_RE = re.compile(
    r"(authorization|cookie|set-cookie|x-api-key|token|secret|credential|key)",
    re.IGNORECASE,
)


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
        'files': files, 'status': status, 'message': message, 'sample_count': len(values), 'finalizations': finalizations}


def capture_file_preview(base: Path, relative: str) -> dict:
    """预览脱敏索引或收尾记录，不公开原始 HTTP 正文与凭据。

    :param base: 已核对的证据根目录。
    :param relative: 来自本组文件清单的相对路径。
    :return: 受限 JSON 预览。
    """
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or path.name not in ('capture_index.json', 'capture-status.json'):
        raise ValueError('该文件不支持公开预览，请查看脱敏索引和文件清单')
    allowed = {item['path'] for item in _capture_files(base)}
    if relative not in allowed:
        raise ValueError('文件不属于当前抓包')
    if path.name == 'capture_index.json':
        return _read_capture_index(base / path)
    value = json.loads((base / path).read_text())
    return {key: value.get(key) for key in ('state', 'recorder_graceful', 'message', 'updated_at')}


