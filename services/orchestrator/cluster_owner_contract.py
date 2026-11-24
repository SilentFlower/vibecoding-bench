"""原凭据交接在所属节点的有限停止、发布与持久范围。"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from cluster_execution import NodeLocation, NodePreparation
from cluster_execution_grants import ExecutionLeaseProof


class OwnerScope(NodeLocation):
    """冻结原交接身份，长期所有权继续由中央原账本管理。

    :param operation_id: 原交接操作。
    :param generation: 当前实际环境代次。
    :param previous_binding: 原网关绑定。
    :param target_binding: 目标网关绑定，独立所有者为None。
    :param handoff_credentials: 是否发布原权威凭据。
    :param retire: 是否退休，保持新普通执行关闭。
    """

    operation_id:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    generation:StrictInt=Field(ge=0)
    previous_binding:StrictInt | None=Field(default=None,ge=1)
    target_binding:StrictInt | None=Field(default=None,ge=1)
    handoff_credentials:StrictBool=True
    retire:StrictBool=False

    @model_validator(mode='after')
    def validate_retirement(self):
        """退休只关闭原绑定和执行能力。:return: 原冻结范围。"""
        if self.retire and (self.handoff_credentials or self.target_binding is not None):
            raise ValueError('退休交接不能发布凭据或关联另一账号')
        return self


class OwnerLease(BaseModel):
    """中央已认领的单个真实绑定排他门禁。

    :param account_id: 网关账号。
    :param lease: 原binding来源的真实短期门禁。
    """

    model_config=ConfigDict(extra='forbid')
    account_id:StrictInt=Field(ge=1)
    lease:ExecutionLeaseProof

    @model_validator(mode='after')
    def validate_binding(self):
        """只接受原排他绑定事务。:return: 原门禁。"""
        if not self.lease.exclusive or self.lease.shared_cli or re.fullmatch(r'binding:[a-f0-9]{32}',self.lease.owner) is None:
            raise ValueError('凭据交接需要原binding排他门禁')
        return self


class OwnerPrepare(BaseModel):
    """中央原门禁截止内的具体节点停止请求。

    :param scope: 原不可变交接范围。
    :param leases: 原绑定及目标的真实门禁。
    :param not_after: 本次UTC秒截止。
    """

    model_config=ConfigDict(extra='forbid')
    scope:OwnerScope
    initial_projection:NodePreparation | None=None
    leases:list[OwnerLease]=Field(default_factory=list,max_length=2)
    missing_bindings:list[StrictInt]=Field(default_factory=list,max_length=1)
    not_after:StrictInt=Field(ge=1)

    @model_validator(mode='after')
    def validate_leases(self):
        """所有原绑定目标都必须有唯一门禁。:return: 完整准备请求。"""
        if self.initial_projection is not None:
            initial=self.initial_projection
            if (not self.scope.retire or self.scope.handoff_credentials or self.scope.generation!=0
                    or self.scope.previous_binding is not None or self.scope.target_binding is not None
                    or not initial.cli_only or initial.login_sid is not None or initial.profile_files or initial.gateway_config
                    or initial.node_key!=self.scope.node_key or initial.assignment_revision!=self.scope.assignment_revision
                    or initial.account.get('id')!=self.scope.account_id or initial.account.get('cc2api_account_id') is not None
                    or initial.environment.get('environment_id')!=self.scope.environment_id
                    or initial.environment.get('generation')!=0
                    or any(initial.environment.get(key) for key in ('container_id','network_container_id','sender_container_id'))):
                raise ValueError('首次退休投影仅用于原零代未准备独立账号')
        expected={value for value in (self.scope.previous_binding,self.scope.target_binding) if value is not None}
        missing=set(self.missing_bindings)
        if (missing and (self.scope.target_binding is not None or missing!={self.scope.previous_binding})
                or len(self.leases)+len(missing)!=len(expected) or {item.account_id for item in self.leases}|missing!=expected
                or any(self.not_after>item.lease.expires_at for item in self.leases)):
            raise ValueError('凭据交接门禁与原绑定范围不一致')
        return self


class OwnerMaterial(BaseModel):
    """仅用于受信文件发布的原所有者快照。

    :param access_token: 当前AT。
    :param refresh_token: 仅交给独立所有者的RT。
    :param expires_at: UTC毫秒到期。
    :param device_id: 原设备身份。
    :param account_uuid: 原账号UUID。
    :param organization_uuid: 原组织UUID。
    """

    model_config=ConfigDict(extra='forbid')
    access_token:StrictStr=Field(min_length=1,max_length=16384)
    refresh_token:StrictStr | None=Field(default=None,min_length=1,max_length=16384)
    expires_at:StrictInt=Field(ge=1,lt=2**53)
    device_id:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    account_uuid:StrictStr=Field(min_length=1,max_length=256)
    organization_uuid:StrictStr | None=Field(default=None,max_length=256)


class OwnerPublish(OwnerPrepare):
    """中央原事务提交后发布到同一Node的权威快照。

    :param material: 原快照；退休为None，网关所有者只接受AT。
    """

    material:OwnerMaterial | None=None

    @model_validator(mode='after')
    def validate_material(self):
        """按目标刷新所有者限制RT发布。:return: 原发布请求。"""
        if self.scope.handoff_credentials:
            if self.material is None or ((self.material.refresh_token is None)!=(self.scope.target_binding is not None)):
                raise ValueError('凭据发布与目标刷新所有者不一致')
        elif self.material is not None:
            raise ValueError('停止交接不接收凭据')
        return self


class OwnerReceipt(BaseModel):
    """节点当前交接阶段，私有凭据保存在原文件。

    :param scope: 原冻结范围。
    :param phase: 停止确认或发布完成。
    :param stopped: 原角色停止是否已核验。
    """

    model_config=ConfigDict(extra='forbid')
    protocol:Literal[1]=1
    scope:OwnerScope
    phase:Literal['preparing','published']='preparing'
    stopped:StrictBool=False
    environment_removed:StrictBool=False

    def wire(self) -> dict:
        """仅在实际完成退休时扩展回执，使普通交接兼容旧中央。@return 节点公开回执。"""
        return self.model_dump(exclude=set() if self.environment_removed else {'environment_removed'})
