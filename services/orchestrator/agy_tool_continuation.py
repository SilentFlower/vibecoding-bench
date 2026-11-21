"""保存按逻辑环境生效的反重力续轮策略。"""
import json
import re
from pathlib import Path

from runtime_files import atomic_json

MODES = {'claim', 'history', 'claim_with_history'}


def _policy_path(data: Path, environment_id: str) -> Path:
    if not re.fullmatch(r'[0-9a-f]{32}', environment_id):
        raise ValueError('反重力环境标识无效')
    return data / 'agy-tool-continuation' / f'{environment_id}.json'


def read_policy(data: Path, environment_id: str) -> dict:
    """读取逻辑环境的策略和版本。@param data 管理面状态目录。@param environment_id 已核对环境。@return 策略视图。"""
    path = _policy_path(data, environment_id)
    try:
        record = json.loads(path.read_text())
    except FileNotFoundError:
        return {'mode': 'claim', 'revision': 0}
    if (not isinstance(record, dict) or set(record) != {'mode', 'revision'}
            or type(record['mode']) is not str or record['mode'] not in MODES
            or type(record['revision']) is not int or record['revision'] < 1):
        raise ValueError('工具续轮策略需要核对')
    return record


def save_policy(data: Path, environment_id: str, expected_revision: int, mode: str, *, supported: bool) -> dict:
    """在环境锁内核对版本后保存。@param data 管理面状态目录。@param environment_id 环境。@param expected_revision 原策略版本。@param mode 新策略。@param supported 当前链路支持历史续轮。@return 实际保存的策略。"""
    current = read_policy(data, environment_id)
    if current['revision'] != expected_revision:
        raise ValueError('工具续轮模式已变化，请刷新后重试')
    if mode not in MODES or mode != 'claim' and not supported:
        raise ValueError('当前请求内核暂不支持所选工具续轮模式')
    if current['mode'] == mode:
        return current
    record = {'mode': mode, 'revision': expected_revision + 1}
    path = _policy_path(data, environment_id)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    atomic_json(path, record)
    return record


def configured_binding(data: Path, binding: dict | None) -> dict | None:
    """在已核对发送绑定上附加权威策略。@param data 管理面状态目录。@param binding 已核对绑定。@return 带策略的绑定或休眠标记。"""
    if binding is None:
        return None
    mode = read_policy(data, binding['environment_id'])['mode']
    return {**binding, 'agy_tool_continuation_mode': mode} if mode != 'claim' else binding
