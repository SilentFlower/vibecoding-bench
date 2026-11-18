"""原Node交接持久意图的共用准入读取。"""
from pathlib import Path

from system_update_contract import safe_read, strict_json


def pending_owner_transition(root: Path) -> bool:
    """读取原环境交接阶段，缺失记录表示尚无交接。

    :param root: 已核对归属的环境根。
    :return: 原交接尚未发布完成时为True，损坏记录抛出异常。
    """
    try:
        value=strict_json(safe_read(root/'runtime/owner-transition.json',16384,private=True),16384)
    except FileNotFoundError:
        return False
    if not isinstance(value,dict) or value.get('phase') not in ('preparing','published'):
        raise ValueError('原节点交接记录需要核对')
    return value['phase']!='published'


def validate_owner_preparation(root: Path, request) -> None:
    """普通环境投影先核对原Owner结果，防止迟到准备写回旧绑定。

    :param root: 原已验证环境目录。
    :param request: 具体NodePreparation，账号及归属由原入口先核对。
    :return: None；未决交接或旧绑定拒绝投影。
    """
    # 运行时再加载严格模型，保持AccountRuntime与NodeExecution的模块初始化边界。
    from cluster_owner_contract import OwnerReceipt
    try:
        value=strict_json(safe_read(root/'runtime/owner-transition.json',16384,private=True),16384)
    except FileNotFoundError:
        return
    record=OwnerReceipt.model_validate(value)
    scope=record.scope
    if (record.phase!='published' or scope.target_binding!=request.account.get('cc2api_account_id')
            or scope.node_key!=request.node_key or scope.account_id!=request.account['id']
            or scope.environment_id!=request.environment['environment_id']
            or scope.assignment_revision!=request.assignment_revision):
        raise ValueError('原Node凭据交接或准备绑定已变化，请重新读取当前归属')
