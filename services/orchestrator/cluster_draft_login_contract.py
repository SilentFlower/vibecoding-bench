"""NULL登录草稿的独立范围与有限证明，正式账号身份在提交后产生。"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from cluster_login_contract import AccountLoginAccept, AccountLoginCode, AccountLoginCodeRead, AccountLoginSnapshot
from cluster_terminal import TerminalInputQuery
from system_update_contract import strict_json


class DraftLoginSettings(BaseModel):
    """仅在私有准备通道传递的草稿配置，记录保存其摘要。

    :param name: 原专属账号名。
    :param timezone: 首次固化的明确时区。
    :param upstream_proxy_scheme: 原代理协议。
    :param upstream_socks5_host: 原代理主机。
    :param upstream_socks5_port: 原代理端口。
    :param upstream_socks5_user: 原私有代理用户名。
    :param upstream_socks5_pass: 原私有代理密码。
    """

    model_config=ConfigDict(extra='forbid')
    name:StrictStr=Field(pattern=r'^[a-zA-Z0-9_-]{1,128}$')
    timezone:StrictStr=Field(min_length=1,max_length=128)
    upstream_proxy_scheme:Literal['http','socks5','socks5h']='socks5'
    upstream_socks5_host:StrictStr=Field(default='',max_length=1024)
    upstream_socks5_port:StrictInt=Field(default=1080,ge=1,le=65535)
    upstream_socks5_user:StrictStr=Field(default='',max_length=4096)
    upstream_socks5_pass:StrictStr=Field(default='',max_length=4096)


def draft_preparation_sha256(settings: DraftLoginSettings, fingerprint_json: str, profile_files: dict[str,str]) -> str:
    """冻结私有准备内容，重复操作不能替换原代理、画像或设置。

    :param settings: 已校验的原私有配置。
    :param fingerprint_json: 原中央选择的画像JSON。
    :param profile_files: 仅允许初始配置文件，不传递旧授权材料。
    :return: 规范内容SHA256；结构或边界异常保持拒绝。
    """
    fingerprint=strict_json(fingerprint_json.encode(),65536)
    if not isinstance(fingerprint,dict) or fingerprint.get('tz')!=settings.timezone:
        raise ValueError('原草稿画像与固化时区不一致')
    if set(profile_files)-{'.claude.json','settings.json'} or sum(len(value.encode()) for value in profile_files.values())>1024*1024:
        raise ValueError('草稿初始配置文件超出允许范围')
    documents={name:strict_json(value.encode(),1024*1024) for name,value in profile_files.items()}
    if any(not isinstance(value,dict) for value in documents.values()):
        raise ValueError('草稿初始配置文件必须为对象')
    raw=json.dumps({'settings':settings.model_dump(),'fingerprint':fingerprint,'profile_files':documents},
        ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


class DraftLoginWork(BaseModel):
    """草稿的明确授权或已有产物恢复，保持原逻辑身份和CLI版本。

    :param id: 本次中央操作。
    :param sid: 原管理会话及实际login来源。
    :param environment_id: 尚未绑定正式账号的原环境。
    :param name: 专属账号名。
    :param draft_generation: 原字符串逻辑代次。
    :param version: 本次冻结CLI版本。
    :param mode: authorize启动授权；recover只检查原保留产物。
    :param home: 本次原容器HOME，恢复可沿原SID暂存。
    :param preparation_sha256: 私有准备内容的摘要。
    :param expires_at: 本次授权UTC秒上限。
    """

    model_config=ConfigDict(extra='forbid')
    kind:Literal['draft-login']='draft-login'
    id:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    sid:StrictStr=Field(pattern=r'^[a-f0-9]{12}$')
    environment_id:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    name:StrictStr=Field(pattern=r'^[a-zA-Z0-9_-]{1,128}$')
    draft_generation:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    version:StrictStr=Field(pattern=r'^2\.1\.[0-9]{1,6}$')
    mode:Literal['authorize','recover']='authorize'
    home:StrictStr=Field(pattern=r'^/home/node(?:/\.v3-login/[a-f0-9]{12})?$')
    preparation_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    expires_at:StrictInt=Field(ge=1)

    @property
    def source(self) -> str:
        """保持原实际登录来源。:return: login:SID。"""
        return 'login:'+self.sid

    @model_validator(mode='after')
    def validate_home(self):
        """新授权使用本次私有暂存；恢复沿冻结的原HOME。:return: 已校验工作。"""
        if self.mode=='authorize' and self.home!='/home/node/.v3-login/'+self.sid:
            raise ValueError('草稿新授权只能使用本次SID的私有暂存HOME')
        return self


class DraftLoginScope(BaseModel):
    """资源准备后冻结的NULL草稿范围，字段不包含正式账号或网关ID。

    :param operation_id: 原操作。
    :param node_key: 原受信节点。
    :param environment_id: 原NULL账号环境。
    :param name: 原专属名称。
    :param draft_generation: 原逻辑草稿代次。
    :param generation: Node已观察到的实际环境代次。
    :param source: 原login:SID来源。
    :param role: 固定草稿用途。
    """

    model_config=ConfigDict(extra='forbid')
    operation_id:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    node_key:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    environment_id:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    name:StrictStr=Field(pattern=r'^[a-zA-Z0-9_-]{1,128}$')
    draft_generation:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    generation:StrictInt=Field(ge=1)
    source:StrictStr=Field(pattern=r'^login:[a-f0-9]{12}$')
    role:Literal['login-draft']='login-draft'


class DraftLoginGrant(DraftLoginScope):
    """草稿专用有限证明，省略Gateway租约和正式账号身份。

    :param not_after: 本次UTC秒截止。
    :param sequence: 同一操作内从1递增的证明序号。
    """

    not_after:StrictInt=Field(ge=1)
    sequence:StrictInt=Field(default=1,ge=1)

    def scope(self) -> DraftLoginScope:
        """读取原不可变草稿范围。:return: 原Scope。"""
        return DraftLoginScope.model_validate(self.model_dump(exclude={'not_after','sequence'}))


class DraftLoginGrantClose(DraftLoginScope):
    """关闭草稿输入许可的固定原因。:param reason: 原受控关闭原因。"""

    reason:StrictStr=Field(pattern=r'^[a-z][a-z0-9_]{0,79}$')


class DraftLoginStart(BaseModel):
    """原NULL草稿工作与实际冻结范围的对应关系。

    :param scope: 原草稿独立Scope。
    :param work: 本次冻结授权/恢复。
    """

    model_config=ConfigDict(extra='forbid')
    scope:DraftLoginScope
    work:DraftLoginWork

    @model_validator(mode='after')
    def validate_scope(self):
        """拒绝跨环境、名称、SID或逻辑代次使用原工作。:return: 已核对请求。"""
        if (self.scope.operation_id!=self.work.id or self.scope.source!=self.work.source
                or any(getattr(self.scope,key)!=getattr(self.work,key) for key in ('environment_id','name','draft_generation'))):
            raise ValueError('草稿工作与本次Node范围不一致')
        return self


class DraftLoginPreparation(BaseModel):
    """有限登录证明之前的原NULL环境资源准备。

    :param node_key: 本次节点。
    :param work: 原冻结工作，实际代次在准备完成后产生。
    :param settings: 原私有代理与明确时区。
    :param fingerprint_json: 原中央画像。
    :param profile_files: 原初始配置，不包含credentials。
    :param previous: 显式恢复/重登的原已停止Scope。
    """

    model_config=ConfigDict(extra='forbid')
    node_key:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    work:DraftLoginWork
    settings:DraftLoginSettings
    fingerprint_json:StrictStr=Field(min_length=2,max_length=65536)
    profile_files:dict[StrictStr,StrictStr]=Field(default_factory=dict)
    previous:DraftLoginScope | None=None

    @model_validator(mode='after')
    def validate_preparation(self):
        """只允许原私有配置与同一NULL环境的前代来源。:return: 已核对准备。"""
        if (self.settings.name!=self.work.name or draft_preparation_sha256(self.settings,self.fingerprint_json,
                self.profile_files)!=self.work.preparation_sha256):
            raise ValueError('原草稿配置或准备摘要已经变化')
        if self.work.mode=='recover' and self.previous is None:
            raise ValueError('草稿恢复必须指向原已停止的来源')
        previous=self.previous
        if previous is not None and (previous.node_key!=self.node_key or previous.operation_id==self.work.id
                or previous.source==self.work.source
                or previous.environment_id!=self.work.environment_id or previous.name!=self.work.name
                or previous.draft_generation==self.work.draft_generation):
            raise ValueError('草稿新会话必须沿原节点/环境并使用新的操作和逻辑代次')
        return self


class DraftLoginResult(BaseModel):
    """实际Node登录作业的无凭据定位。

    :param token: 原运行时执行句柄。
    :param source: 原login来源。
    """

    model_config=ConfigDict(extra='forbid')
    token:StrictStr=Field(min_length=1,max_length=512)
    source:StrictStr=Field(pattern=r'^login:[a-f0-9]{12}$')


class DraftLoginCommit(BaseModel):
    """草稿原冻结授权及实际清理的无令牌事实。

    :param stage: 原授权文件保存/清理阶段。
    :param authorization_sha256: 原文件集合摘要。
    :param refresh_sha256: 原RT摘要。
    :param files: 固定配置文件集合。
    :param cleanup_pending: 原暂存及终端是否仍需清理。
    :param auth_method: 原CLI受控认证方式。
    """

    model_config=ConfigDict(extra='forbid')
    stage:Literal['frozen','home_saved','saved','accepted']
    authorization_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    refresh_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    files:list[Literal['.claude.json','.claude/.credentials.json','.claude/settings.json']]=Field(min_length=2,max_length=3)
    cleanup_pending:StrictBool
    auth_method:StrictStr | None=Field(default=None,max_length=80)

    @model_validator(mode='after')
    def validate_files(self):
        """原冻结清单必须完整，重复文件保持拒绝。:return: 已核对回执。"""
        if len(set(self.files))!=len(self.files) or not {'.claude.json','.claude/.credentials.json'}<=set(self.files):
            raise ValueError('原草稿授权文件清单不完整或重复')
        return self


class DraftLoginReceipt(BaseModel):
    """Root持久记录只接收原范围与无令牌执行事实。

    :param protocol: 固定私有协议。
    :param scope: 原完整草稿范围。
    :param phase: 原Node实际阶段。
    :param result: 原实际作业定位。
    :param error_type: 受控错误类型。
    :param commit: 可选的原授权摘要与清理事实。
    :param discarded: 原完整清理的可选事实。
    """

    model_config=ConfigDict(extra='forbid')
    protocol:StrictInt=Field(default=1,ge=1,le=1)
    scope:DraftLoginScope
    phase:Literal['starting','ready','reconcile','closed']
    result:DraftLoginResult | None=None
    error_type:StrictStr | None=Field(default=None,pattern=r'^[A-Za-z][A-Za-z0-9_]{0,79}$')
    commit:DraftLoginCommit | None=None
    discarded:StrictBool | None=None

    @model_validator(mode='after')
    def validate_result(self):
        """实际作业继续绑定原SID来源。:return: 已核对回执。"""
        if self.phase=='ready' and self.result is None:
            raise ValueError('原草稿启动确认缺少实际执行定位')
        if self.result is not None and self.result.source!=self.scope.source:
            raise ValueError('原草稿Node执行来源已经变化')
        if self.commit is not None and self.commit.stage=='accepted' and self.phase!='closed':
            raise ValueError('草稿接受回执必须确认原实际停止')
        return self


class DraftLoginCodeRead(AccountLoginCodeRead):
    """原单次授权码回执使用独立草稿范围。:param scope: 原NULL草稿Scope。"""

    scope:DraftLoginScope


class DraftLoginCode(AccountLoginCode):
    """复用原授权码规则，输入仅进入原草稿CLI。:param scope: 原NULL草稿Scope。"""

    scope:DraftLoginScope


class DraftLoginInputQuery(TerminalInputQuery):
    """原PTY输入回执的草稿定位。:param scope: 原NULL草稿Scope。"""

    scope:DraftLoginScope


class DraftLoginAccept(AccountLoginAccept):
    """中央确认同一冻结授权，仍沿原NULL草稿收口。:param scope: 原草稿Scope。"""

    scope:DraftLoginScope


class DraftLoginSnapshot(AccountLoginSnapshot):
    """原受信材料/身份快照沿草稿范围返回。:param scope: 原NULL草稿Scope。"""

    scope:DraftLoginScope


class DraftLoginFile(BaseModel):
    """原授权文件的私有传输定位，仅返回摘要和有界大小。

    :param sha256: 原私有文件完整字节摘要。
    :param bytes: 单个文件字节数。
    """

    model_config=ConfigDict(extra='forbid')
    sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    bytes:StrictInt=Field(ge=2,le=1024*1024)


class DraftLoginFiles(BaseModel):
    """固定Node授权文件索引，完整文件经独立SSH Docker归档读取。

    :param protocol: 固定协议。
    :param scope: 原草稿范围。
    :param authorization_sha256: 原规范文件集合摘要。
    :param files: 固定枚举文件及其摘要/大小。
    """

    model_config=ConfigDict(extra='forbid')
    protocol:StrictInt=Field(default=1,ge=1,le=1)
    scope:DraftLoginScope
    authorization_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    files:dict[Literal['.claude.json','.claude/.credentials.json','.claude/settings.json'],DraftLoginFile]

    @model_validator(mode='after')
    def validate_files(self):
        """最小授权文件完整才可供中央镜像。:return: 已核对索引。"""
        if not {'.claude.json','.claude/.credentials.json'}<=set(self.files):
            raise ValueError('原草稿授权文件索引不完整')
        return self


class DraftLoginActivation(DraftLoginAccept):
    """中央已首次落库后的真实账号投影。

    :param account_id: 同一操作产生的真实正账号ID。
    :param assignment_revision: 首次远程归属固定为1。
    """

    account_id:StrictInt=Field(ge=1)
    assignment_revision:StrictInt=Field(default=1,ge=1,le=1)


class DraftLoginActivated(BaseModel):
    """原草稿角色已移除，真实账号身份与首次归属已发布的回执。

    :param protocol: 固定协议。
    :param request: 原完整激活请求。
    :param refresh_sha256: 原已接受授权的RT摘要。
    :param phase: 原角色移除及真实ID发布完成。
    """

    model_config=ConfigDict(extra='forbid')
    protocol:StrictInt=Field(default=1,ge=1,le=1)
    request:DraftLoginActivation
    refresh_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    phase:Literal['activated']='activated'


class DraftLoginPreparationDelete(BaseModel):
    """只按冻结操作清理尚未启动的准备，清理无需重传代理或重新配置资源。

    :param node_key: 原节点。
    :param work: 中央原冻结工作及准备摘要。
    :param previous: 明确重登时的原已停止来源。
    """

    model_config=ConfigDict(extra='forbid')
    node_key:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    work:DraftLoginWork
    previous:DraftLoginScope | None=None

    @model_validator(mode='after')
    def validate_previous(self):
        """清理身份继续绑定同一节点、环境和不同前代。:return: 已核对请求。"""
        previous=self.previous
        if self.work.mode=='recover' and previous is None:
            raise ValueError('原恢复准备的前代需要核对')
        if previous is not None and (previous.node_key!=self.node_key or previous.operation_id==self.work.id
                or previous.source==self.work.source or previous.environment_id!=self.work.environment_id
                or previous.name!=self.work.name or previous.draft_generation==self.work.draft_generation):
            raise ValueError('原准备清理的前代已经变化')
        return self


class DraftLoginPreparationScope(BaseModel):
    """尚未授予输入许可的准备清理身份，与可执行Scope独立。

    :param operation_id: 原冻结准备操作。
    :param node_key: 原节点。
    :param environment_id: 原NULL环境。
    :param name: 原名称。
    :param draft_generation: 原逻辑代次。
    :param generation: 节点观察到的实际资源代次，未创建资源时可为0。
    :param source: 原login来源。
    :param preparation_sha256: 原完整私有准备摘要。
    :param role: 固定只清理用途，执行证明拒绝此身份。
    """

    model_config=ConfigDict(extra='forbid')
    operation_id:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    node_key:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    environment_id:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    name:StrictStr=Field(pattern=r'^[a-zA-Z0-9_-]{1,128}$')
    draft_generation:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    generation:StrictInt=Field(ge=0)
    source:StrictStr=Field(pattern=r'^login:[a-f0-9]{12}$')
    preparation_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    role:Literal['login-draft-preparation']='login-draft-preparation'


class DraftLoginDeleted(BaseModel):
    """环境外保存的原草稿完整清理回执。

    :param protocol: 固定协议。
    :param scope: 原NULL草稿的完整范围。
    :param phase: 原专属资源及资料已清理。
    """

    model_config=ConfigDict(extra='forbid')
    protocol:StrictInt=Field(default=1,ge=1,le=1)
    scope:DraftLoginScope | DraftLoginPreparationScope=Field(discriminator='role')
    phase:Literal['deleted']='deleted'


class DraftLoginSummary(BaseModel):
    """只读草稿产物存在及实际角色状态，文件存在不代表认证成功。

    :param protocol: 固定协议。
    :param scope: 原草稿范围。
    :param credentials_present: 原冻结HOME中凭据文件是否存在。
    :param container_status: 已核验的实际CLI状态。
    :param state: 原Node环境状态。
    """

    model_config=ConfigDict(extra='forbid')
    protocol:StrictInt=Field(default=1,ge=1,le=1)
    scope:DraftLoginScope
    credentials_present:StrictBool
    container_status:Literal['running','exited','dead','created','restarting','paused','missing','unknown']
    state:StrictStr=Field(pattern=r'^[a-z_]{1,80}$')
