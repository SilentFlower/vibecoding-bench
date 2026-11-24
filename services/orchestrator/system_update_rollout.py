"""读取宿主签定的本机账号滚动更新记录。"""
from pathlib import Path

from system_update_contract import BUILD_RE, safe_read, strict_json


def rollout_path(directory: Path, control_release: str) -> Path:
    """定位目标控制批次的账号记录。@param directory 宿主只读门禁目录。@param control_release 运行的控制来源。@return 受限记录路径。"""
    if not BUILD_RE.fullmatch(control_release):
        raise ValueError('账号后台更新的控制来源无效')
    return directory / f'account-rollout-{control_release}.json'


def read_rollout(directory: Path, deployment: str, control_release: str, account_release: str) -> dict | None:
    """读取当前部署与镜像组合的范围。@param directory 门禁目录。@param deployment 部署。@param control_release 控制批次。@param account_release 目标账号批次。@return 账号范围或空。"""
    path = rollout_path(directory, control_release)
    try:
        raw = safe_read(path, 8 * 1024 * 1024, private=True)
    except FileNotFoundError:
        return None
    value = strict_json(raw, 8 * 1024 * 1024)
    if (value.get('schema_version') != 1 or value.get('deployment') != deployment
            or value.get('control_release') != control_release or value.get('account_release') != account_release
            or not isinstance(value.get('environments'), dict)
            or not isinstance(value.get('stopped_environments', {}), dict)
            or not isinstance(value.get('rebuilt_environments', {}), dict)):
        raise ValueError('账号后台更新归属无效')
    return value
