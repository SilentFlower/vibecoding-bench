"""只保存固定执行身份和异常栈位置，避免启动诊断收集凭据或业务正文。"""
from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path
from uuid import uuid4

from runtime_files import atomic_json, directory_fd


NETWORK_FAILURE_PREFIX = 'VIBEBENCH_NETWORK_ERROR_V1 '
MAX_DIAGNOSTIC_BYTES = 64 * 1024
_IDENTIFIER = re.compile(r'[A-Za-z0-9_.<>-]{1,160}\Z')
_SOURCE = re.compile(r'(?:projects|warmup|run|continue|login):[A-Za-z0-9_.:-]{1,240}\Z')


def _bounded_record(value: dict, network: bool = True) -> dict:
    context = {}
    supplied = value.get('context') if isinstance(value.get('context'), dict) else {}
    for key in ('account_id', 'generation', 'exit_code'):
        item = supplied.get(key)
        if type(item) is int:
            context[key] = item
    for key in ('work_id', 'handle'):
        item = supplied.get(key)
        if isinstance(item, str) and re.fullmatch(r'[a-f0-9]{1,64}', item):
            context[key] = item
    if supplied.get('namespace') in ('projects', 'warmup'):
        context['namespace'] = supplied['namespace']
    if supplied.get('mode') in ('passthrough', 'quota', 'capture'):
        context['mode'] = supplied['mode']
    source = supplied.get('source')
    if isinstance(source, str) and _SOURCE.fullmatch(source):
        context['source'] = source
    phase = value.get('phase')
    observed = value.get('at')
    result = {'schema': 1, 'phase': phase if isinstance(phase, str) and re.fullmatch(r'[a-z_]{1,64}', phase) else 'unknown',
        'at': observed if type(observed) in (int, float) and math.isfinite(observed) else time.time(),
        'context': context, 'exceptions': []}
    errors = value.get('exceptions') if isinstance(value.get('exceptions'), list) else []
    for error in errors[:4]:
        if not isinstance(error, dict) or not isinstance(error.get('type'), str) or not _IDENTIFIER.fullmatch(error['type']):
            continue
        entry = {'type': error['type'], 'frames': []}
        if type(error.get('errno')) is int:
            entry['errno'] = error['errno']
        frames = error.get('frames') if isinstance(error.get('frames'), list) else []
        for frame in frames[-32:]:
            if (isinstance(frame, dict) and all(isinstance(frame.get(key), str) and _IDENTIFIER.fullmatch(frame[key])
                    for key in ('file', 'function')) and type(frame.get('line')) is int and frame['line'] > 0):
                entry['frames'].append({key: frame[key] for key in ('file', 'function', 'line')})
        result['exceptions'].append(entry)
    if network and isinstance(value.get('network'), dict):
        result['network'] = _bounded_record(value['network'], network=False)
    return result


class NetworkContextError(ValueError):
    """携带网络角色返回的安全诊断，错误正文不透传到公开故障。

    :param diagnostic: 网络角色输出的固定字段记录，可为空。
    """

    def __init__(self, diagnostic: dict | None = None) -> None:
        """保留可私有留存的网络错误事实。:param diagnostic: 有界记录。:return: None。"""
        super().__init__('网络上下文切换失败，执行未启动')
        self.diagnostic = _bounded_record(diagnostic, network=False) if diagnostic else None


def runtime_failure(error: BaseException, phase: str, context: dict | None = None) -> dict:
    """提取异常类型、错误码和栈位置，不访问异常正文、源码行或局部变量。

    :param error: 当前失败及其有限因果链。
    :param phase: 控制端固定的失败步骤。
    :param context: 服务端生成的执行身份。
    :return: 可安全存入私有诊断的有限记录。
    """
    value = {'schema': 1, 'at': time.time(), 'phase': phase, 'context': context or {}, 'exceptions': []}
    seen = set()
    while error is not None and id(error) not in seen and len(value['exceptions']) < 4:
        seen.add(id(error))
        frames, trace = [], error.__traceback__
        while trace is not None:
            frames.append({'file': Path(trace.tb_frame.f_code.co_filename).name,
                'function': trace.tb_frame.f_code.co_name, 'line': trace.tb_lineno})
            frames = frames[-32:]
            trace = trace.tb_next
        entry = {'type': type(error).__name__, 'frames': frames}
        if isinstance(error, OSError):
            entry['errno'] = error.errno
        value['exceptions'].append(entry)
        if isinstance(error, NetworkContextError) and error.diagnostic:
            value['network'] = error.diagnostic
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    return _bounded_record(value)


def write_runtime_failure(directory: Path, record: dict) -> Path | None:
    """尽力原子保存私有记录，诊断故障不得覆盖正在处理的原异常。

    :param directory: 管理端或网络角色专属的目录。
    :param record: 固定字段错误记录。
    :return: 已保存的路径；无法安全保存时为 None。
    """
    try:
        descriptor = directory_fd(directory, create=True)
        try:
            metadata = os.fstat(descriptor)
            if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
                return None
            os.fchmod(descriptor, 0o700)
        finally:
            os.close(descriptor)
        value = _bounded_record(record)
        if len(json.dumps(value, ensure_ascii=False).encode()) > MAX_DIAGNOSTIC_BYTES:
            return None
        target = directory / (uuid4().hex + '.json')
        atomic_json(target, value)
        return target
    except Exception:
        # 原错误和收口状态比诊断写入更重要，不能因磁盘故障改写启动结果。
        return None


def network_failure(output: bytes | str, source: str) -> dict | None:
    """只接收当前网络调用的固定错误协议，拒绝旧来源和任意标准错误正文。

    :param output: 网络入口的受控输出。
    :param source: 本次期望执行来源，空串表示透传。
    :return: 当前来源的安全记录，缺少有效协议时为空。
    """
    text = output.decode('utf-8', errors='replace') if isinstance(output, bytes) else output
    for line in text[-MAX_DIAGNOSTIC_BYTES:].splitlines():
        if not line.startswith(NETWORK_FAILURE_PREFIX):
            continue
        try:
            value = json.loads(line[len(NETWORK_FAILURE_PREFIX):])
            if not isinstance(value, dict) or value.get('schema') != 1:
                continue
            value = _bounded_record(value, network=False)
            if value['context'].get('source', '') == source:
                return value
        except (ValueError, TypeError, RecursionError, OverflowError):
            continue
    return None
