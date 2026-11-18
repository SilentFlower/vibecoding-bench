"""绑定SSH账号原登录、网关导入与AT-only发布的具体合同。"""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from cluster_execution_grants import ExecutionScope
from cluster_login_contract import AccountLoginWork


class BoundLoginIdentity(BaseModel):
    """原Gateway身份白名单，本次重授权保持同一账号。

    :param email: 原邮箱。
    :param account_uuid: 原账号UUID。
    :param organization_uuid: 原组织；未登记时保留可选语义。
    """

    model_config=ConfigDict(extra='forbid')
    email:StrictStr=Field(min_length=1,max_length=320)
    account_uuid:StrictStr=Field(min_length=1,max_length=256)
    organization_uuid:StrictStr | None=Field(default=None,max_length=256)


class BoundLoginCommit(BaseModel):
    """绑定Node冻结与发布的无令牌阶段回执。

    :param stage: 冻结、AT已保存或已接受。
    :param authorization_sha256: 原冻结授权摘要。
    :param refresh_sha256: 新授权RT摘要。
    :param files: 原冻结文件白名单。
    :param cleanup_pending: 本次RT暂存仍需清理。
    :param identity: 本次已核对的CLI身份。
    :param auth_method: 原CLI认证方式。
    :param aborted: 原导入明确未提交后取消。
    :param published_access_sha256: 已发布Gateway当前AT摘要。
    """

    model_config=ConfigDict(extra='forbid')
    stage:Literal['frozen','saved','accepted']
    authorization_sha256:StrictStr=Field(pattern='^[a-f0-9]{64}$')
    refresh_sha256:StrictStr=Field(pattern='^[a-f0-9]{64}$')
    files:list[Literal['.claude.json','.claude/.credentials.json','.claude/settings.json']]=Field(min_length=2,max_length=3)
    cleanup_pending:StrictBool
    identity:BoundLoginIdentity
    auth_method:StrictStr | None=Field(default=None,max_length=80)
    aborted:StrictBool=False
    published_access_sha256:StrictStr | None=Field(default=None,pattern='^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def validate_stage(self):
        """完整冻结白名单与明确取消阶段必须保持一致。:return: 原回执。"""
        if (not {'.claude.json','.claude/.credentials.json'}<=set(self.files) or len(set(self.files))!=len(self.files)
                or self.aborted and self.stage!='frozen'):
            raise ValueError('原绑定登录冻结文件或取消阶段需要核对')
        return self


class BoundLoginWork(AccountLoginWork):
    """绑定账号的原设备、网关身份与登录来源冻结工作。

    :param gateway_account_id: 原网关账号ID。
    :param device_id: 已核对的当前Node设备。
    :param expected_identity: 原Gateway身份，提交前核对本次真实CLI产物。
    :param refresh_scope: 独立RT父来源在本合同固定为空。
    """

    kind:Literal['account-bound-login']='account-bound-login'
    gateway_account_id:StrictInt=Field(ge=1)
    device_id:StrictStr=Field(pattern='^[a-f0-9]{64}$')
    expected_identity:BoundLoginIdentity
    refresh_scope:None=None

    @model_validator(mode='after')
    def validate_binding(self):
        """冻结具体Gateway身份，拒绝跨独立RT来源借用。:return: 原绑定工作。"""
        identity={'account_id':self.account_id,'binding':self.gateway_account_id,
            'uuid':self.expected_identity.account_uuid,'org':self.expected_identity.organization_uuid}
        if self.account_identity!=json.dumps(identity,sort_keys=True):
            raise ValueError('绑定登录工作与原Gateway身份不一致')
        return self


class BoundLoginStart(BaseModel):
    """同一绑定账号的原排他登录范围。

    :param scope: 原中央真实login租约范围。
    :param work: 本次冻结工作。
    """

    model_config=ConfigDict(extra='forbid')
    scope:ExecutionScope
    work:BoundLoginWork

    @model_validator(mode='after')
    def validate_scope(self):
        """核对绑定、原SID、实际代次及具体操作。:return: 原请求。"""
        if (self.scope.role!='login' or self.scope.gateway_account_id!=self.work.gateway_account_id
                or self.scope.account_id!=self.work.account_id or self.scope.source!=self.work.source
                or self.scope.operation_id!=self.work.id or self.scope.generation<1):
            raise ValueError('绑定登录与原真实账号范围不一致')
        return self


class BoundLoginPublish(BaseModel):
    """仅发布Gateway回执当前AT，RT留在原唯一所有者。

    :param scope: 原登录Scope。
    :param authorization_sha256: 原Node冻结授权摘要。
    :param access_token: Gateway当前权威AT，仅用于私有发布。
    :param expires_at: 当前毫秒有效期。
    """

    model_config=ConfigDict(extra='forbid')
    scope:ExecutionScope
    authorization_sha256:StrictStr=Field(pattern='^[a-f0-9]{64}$')
    access_token:StrictStr=Field(min_length=1,max_length=16384,pattern=r'^[\x21-\x7e]+$')
    expires_at:StrictInt=Field(ge=1,lt=2**53)

    @model_validator(mode='after')
    def validate_scope(self):
        """发布只属于原绑定login来源。:return: 原私有发布请求。"""
        if (self.scope.gateway_account_id is None or self.scope.role!='login'
                or re.fullmatch('login:[a-f0-9]{12}',self.scope.source) is None):
            raise ValueError('AT-only发布需要原绑定登录范围')
        return self


class BoundLoginAbort(BaseModel):
    """中央fence及原回执明确未导入后收口本次冻结副本。

    :param scope: 原绑定登录范围。
    :param authorization_sha256: 本次冻结摘要。
    :param lease_generation: 已fence的原真实排他租约代次。
    :param import_not_submitted: 中央已查询原导入回执的明确结论。
    """

    model_config=ConfigDict(extra='forbid')
    scope:ExecutionScope
    authorization_sha256:StrictStr=Field(pattern='^[a-f0-9]{64}$')
    lease_generation:StrictStr=Field(min_length=1,max_length=128)
    import_not_submitted:StrictBool

    @model_validator(mode='after')
    def validate_scope(self):
        """未知导入或其它来源不能声明取消。:return: 原取消请求。"""
        if (self.import_not_submitted is not True or self.scope.gateway_account_id is None
                or self.scope.role!='login' or re.fullmatch('login:[a-f0-9]{12}',self.scope.source) is None):
            raise ValueError('冻结授权取消需要原绑定及明确未导入结论')
        return self
