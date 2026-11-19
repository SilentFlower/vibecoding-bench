"""节点独立凭据维护的冻结工作，实际RT继续由原HOME持有。"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt,StrictStr,model_validator

from cluster_execution_grants import ExecutionScope
from cluster_execution import NodeInspection


class CredentialStatusRead(NodeInspection):
    """只读当前HOME所需的完整归属与稳定身份。

    :param generation: 原中央实际环境代次。
    :param account_identity: 原稳定账号身份。
    """

    generation:StrictInt=Field(ge=1)
    account_identity:StrictStr=Field(min_length=1,max_length=4096)


class CredentialMaterial(BaseModel):
    """仅供原受信所有权流程使用的当前HOME完整材料。

    :param access_token: 当前所有者AT。
    :param refresh_token: 当前所有者RT。
    :param expires_at: UTC毫秒到期值。
    """

    model_config=ConfigDict(extra='forbid')
    access_token:StrictStr=Field(min_length=1,max_length=16384,pattern=r'^[\x21-\x7e]+$')
    refresh_token:StrictStr=Field(min_length=1,max_length=16384,pattern=r'^[\x21-\x7e]+$')
    expires_at:StrictInt=Field(ge=1,lt=2**53)


class CredentialIdentityImport(BaseModel):
    """原Gateway创建所需的Node实际设备和环境载荷。

    :param device_id: 原Node设备。
    :param environment_id: 原环境。
    :param source: 原CLI身份来源。
    :param canonical_env: 实际基础环境。
    :param canonical_process: 原实际进程指标。
    :param canonical_prompt: 原环境提示字段。
    """

    model_config=ConfigDict(extra='forbid')
    device_id:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    environment_id:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    source:StrictStr=Field(min_length=1,max_length=256)
    canonical_env:dict
    canonical_process:dict
    canonical_prompt:dict


class CredentialRefreshWork(BaseModel):
    """原所有者授权的一次无模型刷新工作。

    :param kind: 固定凭据刷新用途。
    :param id: 原维护操作ID。
    :param account_id: 原中央账号。
    :param account_identity: 原稳定账号身份，AT/RT轮换保持同一身份。
    :param version: 本次冻结的CLI版本。
    :param force_refresh: 原401恢复是否强制刷新。
    :param refresh_buffer_sec: 原探针有效期缓冲。
    :param review_scope: 可选的原已释放私有评审来源。
    :param review_request_id: 原Node所有者待办ID，与评审来源成对。
    """

    model_config=ConfigDict(extra='forbid')
    kind:Literal['credential-refresh']='credential-refresh'
    id:StrictStr=Field(pattern='^[a-f0-9]{32}$')
    account_id:StrictInt=Field(ge=1)
    account_identity:StrictStr=Field(min_length=1,max_length=4096)
    version:StrictStr=Field(pattern=r'^2\.1\.[0-9]{1,6}$')
    force_refresh:StrictBool=False
    refresh_buffer_sec:StrictInt=Field(default=600,ge=0,le=86400)
    review_scope:ExecutionScope | None=None
    review_request_id:StrictStr | None=Field(default=None,pattern='^[a-f0-9]{64}$')

    @property
    def source(self) -> str:
        """生成本次唯一原所有者维护来源。:return: 不含凭据的来源。"""
        return 'oauth-refresh:'+self.id

    @property
    def shared_cli(self) -> bool:
        """凭据维护需要原账号独占执行能力。:return: False。"""
        return False

    @model_validator(mode='after')
    def validate_review(self):
        """评审待办必须来自同账号独立Scope。:return: 原冻结工作。"""
        if (self.review_scope is None)!=(self.review_request_id is None):
            raise ValueError('评审刷新需要完整原来源及待办ID')
        if self.review_scope is not None and (not self.force_refresh or self.review_scope.account_id!=self.account_id
                or self.review_scope.gateway_account_id is not None or self.review_scope.role!='cli'
                or not re.fullmatch(r'run:[a-f0-9]{12}:[0-9]+',self.review_scope.source)):
            raise ValueError('评审刷新来源与原独立账号不一致')
        return self


class CredentialRefreshStart(BaseModel):
    """凭据操作族的独立维护Scope，拒绝模型与网关租约替代。

    :param scope: 原中央新建的login凭据维护Scope。
    :param work: 本次实际刷新工作。
    """

    model_config=ConfigDict(extra='forbid')
    scope:ExecutionScope
    work:CredentialRefreshWork

    @model_validator(mode='after')
    def validate_scope(self):
        """冻结来源、实际环境与原评审定位保持一致。:return: 原启动请求。"""
        scope,work=self.scope,self.work
        if (scope.role!='login' or scope.gateway_account_id is not None or scope.operation_id!=work.id
                or scope.source!=work.source or scope.account_id!=work.account_id):
            raise ValueError('独立凭据维护与原Scope不一致')
        if work.review_scope is not None and any(getattr(scope,key)!=getattr(work.review_scope,key)
                for key in ('node_key','account_id','environment_id','assignment_revision','generation')):
            raise ValueError('评审刷新不能跨原节点、环境或代次')
        return self


class CredentialUsageWork(BaseModel):
    """原账号当前HOME的一次具体只读usage工作。

    :param id: 本次唯一查询标识。
    :param account_id: 原中央账号。
    :param account_identity: 原稳定身份。
    :param version: 原请求使用的CLI版本头；查询保持原生TLS。
    """

    model_config=ConfigDict(extra='forbid')
    kind:Literal['credential-usage']='credential-usage'
    id:StrictStr=Field(pattern='^[a-f0-9]{32}$')
    account_id:StrictInt=Field(ge=1)
    account_identity:StrictStr=Field(min_length=1,max_length=4096)
    version:StrictStr=Field(pattern=r'^2\.1\.[0-9]{1,6}$')

    @property
    def source(self) -> str:
        """固定本次原查询来源。:return: 不含凭据的唯一来源。"""
        return 'quota:'+self.id

    @property
    def shared_cli(self) -> bool:
        """沿原手动额度查询的CLI模式。:return: False；API仍可并行。"""
        return False


class CredentialUsageStart(BaseModel):
    """具体usage工作与原独立账号有限许可。

    :param scope: 原login操作族的有限许可。
    :param work: 无模型、无RT修改的只读查询。
    """

    model_config=ConfigDict(extra='forbid')
    scope:ExecutionScope
    work:CredentialUsageWork

    @model_validator(mode='after')
    def validate_scope(self):
        """限制当前独立账号及原具体来源。:return: 原请求。"""
        if (self.scope.role!='login' or self.scope.gateway_account_id is not None
                or self.scope.operation_id!=self.work.id or self.scope.source!=self.work.source
                or self.scope.account_id!=self.work.account_id):
            raise ValueError('独立usage查询与原Scope不一致')
        return self


def credential_start(value: dict) -> CredentialRefreshStart | CredentialUsageStart:
    """按明确工作类型解析原节点维护记录。

    :param value: 已落盘或接收的原Scope与具体工作。
    :return: 严格验证的刷新或usage请求。
    """
    work=value.get('work')
    model=CredentialUsageStart if isinstance(work,dict) and work.get('kind')=='credential-usage' else CredentialRefreshStart
    return model.model_validate(value)
