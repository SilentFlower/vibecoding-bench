"""节点有限执行证明，只镜像中央许可，执行停止由原进程监督合同核对。"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from runtime_files import directory_fd, atomic_json, private_directory
from system_update_contract import safe_read, strict_json
from cluster_owner_state import pending_owner_transition


class ExecutionLeaseProof(BaseModel):
    """中央已认领租约的有限镜像。

    :param owner: 原执行source。
    :param generation: 原真实网关租约代次。
    :param expires_at: 中央租约的UTC秒截止。
    :param exclusive: 是否排他维护。
    :param shared_cli: 是否原共享CLI槽位。
    """

    model_config = ConfigDict(extra='forbid')
    owner: StrictStr = Field(min_length=1, max_length=160)
    generation: StrictStr = Field(min_length=1, max_length=128)
    expires_at: StrictInt = Field(ge=0)
    exclusive: StrictBool
    shared_cli: StrictBool = False


class ExecutionScope(BaseModel):
    """中央冻结的单次节点执行范围。

    :param operation_id: 本次执行认领的独立操作。
    :param node_key: 固定执行节点。
    :param account_id: 中央账号。
    :param gateway_account_id: 原网关绑定，独立账号为None。
    :param environment_id: 固定环境。
    :param assignment_revision: 当前人工分配版本。
    :param generation: 本机实际环境代次。
    :param source: 原执行来源。
    :param role: 固定执行类型。
    """

    model_config = ConfigDict(extra='forbid')
    operation_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    node_key: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    account_id: StrictInt = Field(ge=1)
    gateway_account_id: StrictInt | None = Field(default=None, ge=1)
    environment_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    assignment_revision: StrictInt = Field(ge=1)
    generation: StrictInt = Field(ge=0)
    source: StrictStr = Field(min_length=1, max_length=160)
    role: Literal['cli', 'projects', 'warmup', 'login', 'review']

    @property
    def account_login(self) -> bool:
        """识别已有账号的明确登录来源，保持普通作业的停用门禁。

        :return: 是否为login角色及精确SID来源。
        """
        return self.role=='login' and re.fullmatch('login:[a-f0-9]{12}',self.source) is not None

    @property
    def bound_account_login(self) -> bool:
        """识别具有原Gateway绑定的明确登录。:return: 是否需要真实排他网关租约。"""
        return self.gateway_account_id is not None and self.account_login


class ExecutionGrant(ExecutionScope):
    """有限证明的初次输入与单调续接输入。

    :param not_after: 本次节点准入的UTC秒截止。
    :param sequence: 原操作内从1递增的续接序号。
    :param lease: 原中央网关租约镜像，独立账号使用中央作业许可。
    """

    not_after: StrictInt = Field(ge=0)
    sequence: StrictInt = Field(default=1, ge=1)
    lease: ExecutionLeaseProof | None = None

    @model_validator(mode='after')
    def validate_owner(self):
        """核对网关绑定与原source，节点截止始终受原真实租约约束。:return: 本次已核对证明。"""
        if (self.gateway_account_id is None) != (self.lease is None):
            raise ValueError('执行证明与网关绑定不一致')
        if self.lease is not None and (self.lease.owner != self.source or self.not_after > self.lease.expires_at
                or self.lease.exclusive and self.lease.shared_cli):
            raise ValueError('执行证明超出原租约范围')
        return self

    def scope(self) -> ExecutionScope:
        """读取单次不可变执行范围。:return: 原冻结scope。"""
        return ExecutionScope.model_validate(self.model_dump(exclude={'not_after', 'sequence', 'lease'}))


class _GrantRecord(BaseModel):
    """节点私有证明记录，closed仅表示新输入已关闭。"""

    model_config = ConfigDict(extra='forbid')
    protocol: Literal[1] = 1
    grant: ExecutionGrant
    phase: Literal['prepared', 'active', 'closed']
    closed_reason: StrictStr | None = None

    @model_validator(mode='after')
    def validate_phase(self):
        """关闭原因与原阶段一起核对，坏记录保持拒绝。:return: 私有记录。"""
        if ((self.phase == 'closed') != (self.closed_reason is not None)
                or self.closed_reason is not None and not re.fullmatch('[a-z][a-z0-9_]{0,79}', self.closed_reason)):
            raise ValueError('节点执行证明的关闭阶段无效')
        return self


class ExecutionGrants:
    """持久核对节点证明和环境归属，实际动作由调用方持有环境文件锁。

    :param data: 节点私有数据根。
    :param node_key: 安装归属。
    :param deployment: 安装部署。
    :param database: 本节点执行投影连接工厂。
    :param clock: 本机UTC秒时钟，测试可注入。
    """

    _record_model=_GrantRecord

    def __init__(self, data: Path, node_key: str, deployment: str, database: Callable,
                 clock: Callable = time.time) -> None:
        """保存原安装与节点库边界，初始化保持已有作业。

        :param data: 节点数据根。
        :param node_key: 安装节点。
        :param deployment: 原部署。
        :param database: 节点库连接工厂。
        :param clock: 节点时钟。
        :return: None。
        """
        if not re.fullmatch('[a-f0-9]{32}', node_key) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,35}', deployment):
            raise ValueError('节点执行证明安装范围无效')
        self.data, self.node_key, self.deployment, self.database, self.clock = data, node_key, deployment, database, clock
        self.directory, self.lock = data / 'node-execution-grants', threading.RLock()
        self._installation()

    def _installation(self) -> None:
        # 安装标记可能由非root的SSH管理用户创建；这里只核对原公开归属和无链接读取。
        if strict_json(safe_read(self.data / 'cluster-node.json', 8192), 8192) != {
                'protocol': 1, 'node_key': self.node_key, 'deployment_id': self.deployment}:
            raise ValueError('执行证明节点安装归属不一致')

    def _path(self, scope: ExecutionScope, *, create: bool = False) -> Path:
        if scope.node_key != self.node_key:
            raise ValueError('执行证明属于其他节点')
        parent = self.directory / scope.environment_id
        if create:
            private_directory(self.directory)
            private_directory(parent)
        return parent / (scope.operation_id + '.json')

    def open_for_stopped_observation(self, environment_id: str) -> set[str]:
        """只读核对冻结环境的持久证明。@param environment_id 不可变原环境。@return 尚未关闭的操作身份。"""
        if not re.fullmatch('[a-f0-9]{32}', environment_id):
            raise ValueError('执行许可的环境无效')
        with self.lock:
            parent = self.directory / environment_id
            try:
                fd = directory_fd(parent)
            except FileNotFoundError:
                return set()
            try:
                names = os.listdir(fd)
                active = set()
                for name in names:
                    if not re.fullmatch(r'[a-f0-9]{32}\.json', name):
                        raise ValueError('节点许可目录存在未核对的文件')
                    record = self._record_model.model_validate(
                        strict_json(safe_read(parent / name, 16384, private=True), 16384)
                    )
                    if (
                        record.grant.environment_id != environment_id
                        or record.grant.node_key != self.node_key
                        or name != record.grant.operation_id + '.json'
                    ):
                        raise ValueError('持久许可归属有变化')
                    # 过期的许可也可能持有已接受的工作，只将正式关闭记录视为收口。
                    if record.phase != 'closed':
                        active.add(record.grant.operation_id)
                return active
            finally:
                os.close(fd)

    def _load(self, scope: ExecutionScope) -> _GrantRecord:
        value = self._record_model.model_validate(strict_json(safe_read(self._path(scope), 16384, private=True), 16384))
        if value.grant.scope() != scope:
            raise ValueError('执行证明与原账号、环境或来源范围不一致')
        return value

    def _check_environment(self, scope: ExecutionScope) -> None:
        self._installation()
        root = self.data / 'environments' / scope.environment_id
        expected = {'protocol': 1, 'node_key': self.node_key, 'account_id': scope.account_id,
            'environment_id': scope.environment_id, 'revision': scope.assignment_revision, 'phase': 'ready'}
        if strict_json(safe_read(root / 'runtime/node-assignment.json', 8192, private=True), 8192) != expected:
            raise ValueError('节点执行归属或分配版本已变化')
        fence = root / 'runtime/node-fence.json'
        if fence.exists() or fence.is_symlink():
            if strict_json(safe_read(fence, 8192, private=True), 8192).get('phase') != 'cancelled':
                raise ValueError('节点环境已被迁移隔离')
        connection = self.database()
        try:
            row = connection.execute('SELECT e.account_id,e.generation,a.cc2api_account_id FROM account_environments e '
                'JOIN accounts a ON a.id=e.account_id WHERE e.environment_id=? AND (a.enabled=1 OR ?=1) AND a.deleted_at IS NULL',
                (scope.environment_id,int(scope.account_login))).fetchone()
            if (row is None or row['account_id'] != scope.account_id or row['generation'] != scope.generation
                    or row['cc2api_account_id'] != scope.gateway_account_id):
                raise ValueError('节点执行实际账号、网关绑定或代次已变化')
        finally:
            connection.close()

    def check_scope(self, scope: ExecutionScope) -> None:
        """核对固定维护操作的当前节点、归属及实际代次。

        :param scope: 中央确定的原实际环境范围。
        :return: None；此检查只核对归属，不授予启动或输入许可。
        """
        if scope.node_key != self.node_key:
            raise ValueError('维护操作属于其他节点')
        self._check_environment(scope)

    def _deadline(self, grant: ExecutionGrant) -> None:
        if pending_owner_transition(self.data/'environments'/grant.environment_id):
            raise ValueError('原节点凭据交接尚未完成，新执行和输入继续等待')
        remaining = grant.not_after - self.clock()
        if not 0 < remaining <= 35:
            raise ValueError('节点执行证明已过期或节点时钟需要核对')

    def create(self, grant: ExecutionGrant) -> dict:
        """保存中央初次有限证明，重复只接受原精确输入。

        :param grant: 中央冻结且有截止的证明。
        :return: 私有证明记录，实际作业尚未启动。
        """
        grant=self._record_model(grant=grant,phase='prepared').grant
        with self.lock:
            scope = grant.scope()
            self._check_environment(scope)
            self._deadline(grant)
            if grant.sequence != 1:
                raise ValueError('节点初次证明的续接序号应为1')
            path = self._path(scope, create=True)
            if path.exists() or path.is_symlink():
                record = self._load(scope)
                if record.phase == 'closed' or record.grant != grant:
                    raise ValueError('原节点执行证明已关闭或冻结范围已变化')
            else:
                record = self._record_model(grant=grant, phase='prepared')
                atomic_json(path, record.model_dump())
            return record.model_dump()

    def renew(self, grant: ExecutionGrant) -> dict:
        """按原证明和单调序号镜像中央续约，保持原owner及租约代次。

        :param grant: 同一冻结范围的新截止与下一序号。
        :return: 已持久续接记录。
        """
        grant=self._record_model(grant=grant,phase='prepared').grant
        with self.lock:
            scope = grant.scope()
            self._check_environment(scope)
            self._deadline(grant)
            record = self._load(scope)
            old = record.grant
            if record.phase == 'closed':
                raise ValueError('原节点执行证明已关闭')
            if record.phase == 'active' and old.not_after <= self.clock():
                raise ValueError('原节点执行证明已过期，请先核对实际作业')
            if grant == old:
                return record.model_dump()
            if (grant.sequence != old.sequence + 1 or grant.not_after < old.not_after
                    or not self._lease_renewal(old,grant)):
                raise ValueError('节点续接序号、原租约代次或截止不一致')
            record.grant = grant
            atomic_json(self._path(scope), record.model_dump())
            return record.model_dump()

    def _lease_renewal(self, old: ExecutionGrant, grant: ExecutionGrant) -> bool:
        """正式账号续接继续核对原Gateway租约身份和单调截止。"""
        before=old.lease.model_dump(exclude={'expires_at'}) if old.lease else None
        after=grant.lease.model_dump(exclude={'expires_at'}) if grant.lease else None
        return before==after and (old.lease is None or grant.lease is not None and grant.lease.expires_at>=old.lease.expires_at)

    def activate(self, scope: ExecutionScope) -> dict:
        """认领本次启动意图，重复认领必须查询原启动结果。

        :param scope: 原不可变执行范围。
        :return: active证明，实际进程及输入收据由执行层继续保存。
        """
        with self.lock:
            self._check_environment(scope)
            record = self._load(scope)
            self._deadline(record.grant)
            if record.phase != 'prepared':
                raise ValueError('原节点执行已认领或关闭，请核对原启动收据')
            record.phase = 'active'
            atomic_json(self._path(scope), record.model_dump())
            return record.model_dump()

    def authorize(self, scope: ExecutionScope) -> ExecutionGrant:
        """在已持有环境文件锁时核对当前新输入许可。

        :param scope: 当前原执行范围。
        :return: 截止内且归属有效的原证明。
        """
        with self.lock:
            self._check_environment(scope)
            record = self._load(scope)
            self._deadline(record.grant)
            if record.phase != 'active':
                raise ValueError('节点执行尚未认领或已关闭新输入')
            return record.grant

    def get(self, scope: ExecutionScope) -> dict:
        """只读原证明，过期和归属变化后的收据仍保留供核对。

        :param scope: 原执行范围。
        :return: 私有记录，读取不会续期或认领执行。
        """
        with self.lock:
            return self._load(scope).model_dump()

    def close(self, scope: ExecutionScope, reason: str) -> dict:
        """持久关闭新输入，保留原证明并继续要求实际进程对账。

        :param scope: 原执行范围。
        :param reason: 固定脱敏原因代码。
        :return: closed记录，此记录只表示输入许可关闭。
        """
        if not re.fullmatch('[a-z][a-z0-9_]{0,79}', reason):
            raise ValueError('节点执行关闭原因无效')
        with self.lock:
            record = self._load(scope)
            if record.phase != 'closed':
                record.phase, record.closed_reason = 'closed', reason
                atomic_json(self._path(scope), record.model_dump())
            return record.model_dump()
