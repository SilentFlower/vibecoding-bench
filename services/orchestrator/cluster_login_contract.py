"""已有独立节点账号明确重授权的具体冻结工作。"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from cluster_execution_grants import ExecutionScope
from cluster_credentials_contract import CredentialMaterial


def login_authorization_sha256(documents: dict) -> str:
    """统一冻结授权文件集合的规范摘要，保留完整未知字段。

    :param documents: 已严格解析的固定JSON文件集合。
    :return: 原内容的规范SHA256。
    """
    return hashlib.sha256(json.dumps(documents,ensure_ascii=False,sort_keys=True,separators=(',',':'),
        allow_nan=False).encode()).hexdigest()


class AccountLoginWork(BaseModel):
    """本次明确重授权的原账号、SID及冻结版本。

    :param id: 原中央唯一操作ID。
    :param sid: 原登录SID；与操作ID分别冻结。
    :param account_id: 已存在的中央独立账号。
    :param account_identity: 原稳定账号身份，启动前由Node核对。
    :param version: 本次实际选择的CLI版本。
    :param force_reauth: 明确的新授权，始终保护旧HOME凭据。
    :param expires_at: 本次授权TTL的UTC秒，续接执行证明保持此上限。
    :param refresh_scope: 可选的原未知RT维护；新授权完成前保持原隔离。
    """

    model_config=ConfigDict(extra='forbid')
    kind:Literal['account-login']='account-login'
    id:StrictStr=Field(pattern='^[a-f0-9]{32}$')
    sid:StrictStr=Field(pattern='^[a-f0-9]{12}$')
    account_id:StrictInt=Field(ge=1)
    account_identity:StrictStr=Field(min_length=1,max_length=4096)
    version:StrictStr=Field(pattern=r'^2\.1\.[0-9]{1,6}$')
    force_reauth:StrictBool=True
    expires_at:StrictInt=Field(ge=1)
    refresh_scope:ExecutionScope | None=None

    @property
    def source(self) -> str:
        """沿原登录来源定位实际tmux。:return: login:SID。"""
        return 'login:'+self.sid

    @property
    def shared_cli(self) -> bool:
        """明确重授权沿原独占CLI资源规则。:return: False。"""
        return False

    @model_validator(mode='after')
    def validate_force(self):
        """此具体工作只接受明确重授权。:return: 原冻结工作。"""
        if self.force_reauth is not True:
            raise ValueError('远程已有账号登录需要明确重授权')
        parent=self.refresh_scope
        if parent is not None and (parent.role!='login' or parent.gateway_account_id is not None
                or parent.account_id!=self.account_id or parent.source!='oauth-refresh:'+parent.operation_id):
            raise ValueError('明确重授权只能关联原独立RT维护来源')
        return self


class AccountLoginStart(BaseModel):
    """原独立账号登录维护的完整冻结范围。

    :param scope: 原中央独立login许可。
    :param work: 本次具体重授权工作。
    """

    model_config=ConfigDict(extra='forbid')
    scope:ExecutionScope
    work:AccountLoginWork

    @model_validator(mode='after')
    def validate_scope(self):
        """拒绝绑定账号、其它角色与旧SID替代本次来源。:return: 原启动请求。"""
        if (self.scope.role!='login' or self.scope.gateway_account_id is not None
                or self.scope.operation_id!=self.work.id or self.scope.source!=self.work.source
                or self.scope.account_id!=self.work.account_id):
            raise ValueError('独立账号重授权与原Scope不一致')
        parent=self.work.refresh_scope
        if parent is not None and (any(getattr(self.scope,key)!=getattr(parent,key) for key in
                ('node_key','account_id','environment_id','assignment_revision')) or self.scope.generation<parent.generation):
            raise ValueError('重授权不能跨原RT所有者节点、环境或回退代次')
        return self


class AccountLoginCodeRead(BaseModel):
    """原授权码输入的只读回执定位。

    :param scope: 原登录范围。
    :param request_id: 原单次输入标识。
    """

    model_config=ConfigDict(extra='forbid')
    scope:ExecutionScope
    request_id:StrictStr=Field(pattern='^[a-f0-9]{32}$')


class AccountLoginAccept(BaseModel):
    """中央保存同一新授权之后的明确收口。

    :param scope: 原登录范围。
    :param authorization_sha256: 原Node冻结授权摘要。
    """

    model_config=ConfigDict(extra='forbid')
    scope:ExecutionScope
    authorization_sha256:StrictStr=Field(pattern='^[a-f0-9]{64}$')


class AccountLoginCode(AccountLoginCodeRead):
    """向原登录投递一次授权码，原文仅用于stdin。

    :param scope: 原完整登录范围。
    :param request_id: 原单次输入标识。
    :param code: 原完整授权码，禁止控制字符。
    """

    code:StrictStr=Field(min_length=1,max_length=8192)

    @model_validator(mode='after')
    def validate_code(self):
        """固定校验原码；错误由私有调度器脱敏。:return: 原输入。"""
        if not self.code.strip() or any(ord(value)<32 or ord(value)==127 for value in self.code):
            raise ValueError('原登录授权码格式无效')
        return self


class AccountLoginIdentity(BaseModel):
    """原Node新授权的身份白名单，设备来源证明另走原核验。

    :param user_id: 当前HOME的原设备字段；允许历史独立账号缺失。
    :param email: 本次CLI写出的邮箱。
    :param account_uuid: 本次CLI写出的账号身份。
    :param organization_uuid: 可选组织身份。
    """

    model_config=ConfigDict(extra='forbid')
    user_id:StrictStr | None=Field(default=None,max_length=4096)
    email:StrictStr=Field(min_length=1,max_length=320)
    account_uuid:StrictStr=Field(min_length=1,max_length=256)
    organization_uuid:StrictStr | None=Field(default=None,max_length=256)


class AccountLoginMaterial(CredentialMaterial):
    """本次授权凭据及原CLI可选套餐字段。

    :param subscription_type: 原订阅类型。
    :param rate_limit_tier: 原限额层级。
    """

    subscription_type:StrictStr | None=Field(default=None,max_length=256)
    rate_limit_tier:StrictStr | None=Field(default=None,max_length=256)


class AccountLoginSnapshot(BaseModel):
    """仅供中央受信提交回调消费的原授权快照。

    :param protocol: 固定协议。
    :param scope: 原登录完整范围。
    :param authorization_sha256: 原冻结文件摘要。
    :param material: 当前Node完整凭据，仅供本次镜像。
    :param identity: 原身份白名单。
    :param cli_identity: 可选原设备来源观察。
    :param version: 本次实际CLI版本。
    :param auth_method: 原CLI认证方式。
    """

    model_config=ConfigDict(extra='forbid')
    protocol:StrictInt=Field(default=1,ge=1,le=1)
    scope:ExecutionScope
    authorization_sha256:StrictStr=Field(pattern='^[a-f0-9]{64}$')
    material:AccountLoginMaterial
    identity:AccountLoginIdentity
    cli_identity:dict[str,StrictStr] | None=None
    version:StrictStr=Field(pattern=r'^2\.1\.[0-9]{1,6}$')
    auth_method:StrictStr | None=Field(default=None,max_length=80)
