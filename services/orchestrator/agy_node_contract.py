"""AGY 节点控制的固定操作和冻结身份。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


AGY_NODE_SHORT = frozenset({
    'agy-preflight', 'agy-inspect', 'agy-fingerprint', 'agy-capacity-state', 'agy-capture-read',
    'agy-stage-import',
})
AGY_NODE_LONG = frozenset({'agy-export', 'agy-verify-import', 'agy-prepare-import'})
AGY_NODE_OPERATIONS = AGY_NODE_SHORT | AGY_NODE_LONG | {
    'agy-prepare', 'agy-capacity', 'agy-fence', 'agy-restore-source', 'agy-activate-import',
    'agy-revoke-import', 'agy-control', 'agy-ingress',
}


class AgyLocation(BaseModel):
    """当前节点实际环境的精确定位。@param account_id 网关账号。@param environment_id 固定环境。"""

    model_config = ConfigDict(extra='forbid')
    node_key: StrictStr = Field(pattern=r'^(local|[a-f0-9]{32})$')
    account_id: StrictInt = Field(ge=1)
    environment_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    assignment_revision: StrictInt = Field(ge=1)
    generation: StrictInt = Field(ge=0)


class AgyPreparation(AgyLocation):
    """中央冻结的 AGY 配置及容器预算。@param environment 逻辑环境。@param configuration 网关配置。"""

    environment: dict
    configuration: dict
    wake: StrictBool = True


class AgyCapacity(AgyLocation):
    """容量操作及网关对原操作的逐项证明。@param authorities 已读取的网关容量配置。"""

    authorities: dict[str, dict]
    operation_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    before: StrictInt = Field(ge=1, le=64)
    target: StrictInt = Field(ge=1, le=64)
    phase: Literal['prepare', 'settle', 'reconcile']


class AgyControl(AgyLocation):
    """节点 AGY 管理操作。@param action 固定操作。@param body 原管理入参。"""

    action: Literal['capture-read', 'capture-set', 'cpu-read', 'cpu-set',
        'kernel-read', 'kernel-set', 'stop', 'rebuild', 'reconcile', 'quiesce']
    body: dict


class AgyCapture(AgyLocation):
    """原诊断尝试在当前已迁移资料树中的定位。@param attempt_id 网关尝试。"""

    attempt_id: StrictStr = Field(pattern=r'^[a-f0-9-]{36}$')


class AgyIngress(AgyCapture):
    """原代次已脱敏的入口快照。@param ingress 网关预览。"""

    ingress: dict
