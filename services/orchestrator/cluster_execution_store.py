"""中央远程终端执行账本，冻结原归属、source及真实租约并按版本推进。"""
from __future__ import annotations

import hashlib
import json
import re
import time

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator

from cluster_login_contract import AccountLoginStart, AccountLoginWork
from cluster_bound_login_contract import BoundLoginStart, BoundLoginWork
from cluster_execution_grants import ExecutionGrant, ExecutionLeaseProof, ExecutionScope
from cluster_terminal import TerminalWork
from cluster_runs import RunWork
from cluster_continue_contract import ContinueWork
from cluster_credentials_contract import CredentialRefreshWork, CredentialUsageWork, credential_start
from system_update_contract import strict_json


class LeaseReleaseReceipt(BaseModel):
    """中央原真实租约释放回执。:param owner: 原source。:param generation: 原租约代次。:param released: 原释放已确认。"""

    model_config = ConfigDict(extra='forbid')
    owner: StrictStr = Field(min_length=1, max_length=160)
    generation: StrictStr = Field(min_length=1, max_length=128)
    released: StrictBool


class CentralExecutionRecord(BaseModel):
    """中央私有执行范围与当前证据，旧截止保留用于恢复。

    :param scope: 原不可变执行范围。
    :param work: 原冻结终端工作。
    :param node_config_sha256: 原SSH配置摘要。
    :param runtime_release: 原控制组件发布。
    :param gateway_prepare_intent: 是否已登记真实网关认领意图。
    :param lease: 原真实租约及当前已确认截止。
    :param grant: 当前节点证明及单调序号。
    :param node_receipt: 原节点启动或关闭回执。
    :param lease_released: 原中央真实租约释放回执。
    :param failure: 固定脱敏原因。
    :param quota_identity: 模型工作的原额度身份，无模型凭据维护保持None。
    :param local_admission_intent: 独立账号已登记原中央执行许可意图。
    :param local_admission_released: 原节点停止及独立许可释放已确认；模型工作同时归还原额度。
    :param node_start_cancelled: 节点证明提交前失败，中央确认原网关许可与额度已撤销。
    """

    model_config = ConfigDict(extra='forbid')
    protocol: int = Field(default=1, strict=True, ge=1, le=1)
    scope: ExecutionScope
    work: TerminalWork | RunWork | ContinueWork | CredentialRefreshWork | CredentialUsageWork | AccountLoginWork | BoundLoginWork
    node_config_sha256: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    runtime_release: StrictStr = Field(min_length=1, max_length=128)
    gateway_prepare_intent: StrictBool = False
    lease: ExecutionLeaseProof | None = None
    grant: ExecutionGrant | None = None
    node_receipt: dict | None = None
    lease_released: LeaseReleaseReceipt | None = None
    failure: StrictStr | None = Field(default=None, pattern=r'^[a-z][a-z0-9_]{0,79}$')
    quota_identity: StrictStr | None = Field(default=None, min_length=1, max_length=4096)
    local_admission_intent: StrictBool = False
    local_admission_released: StrictBool = False
    node_start_cancelled: StrictBool = False

    @model_validator(mode='after')
    def validate_evidence(self):
        """核对原工作、租约、证明和节点回执均属于同一scope。:return: 原私有记录。"""
        scope = self.scope
        if isinstance(self.work,BoundLoginWork):
            BoundLoginStart(scope=scope,work=self.work)
            valid=self.quota_identity is None
            if self.lease is not None and (self.lease.exclusive is not True or self.lease.shared_cli is not False):
                raise ValueError('绑定重授权必须保留原真实排他登录租约')
        elif isinstance(self.work,AccountLoginWork):
            AccountLoginStart(scope=scope,work=self.work)
            valid=self.quota_identity is None
        elif isinstance(self.work,(CredentialRefreshWork,CredentialUsageWork)):
            credential_start({'scope':scope.model_dump(),'work':self.work.model_dump()})
            valid=self.quota_identity is None
        elif isinstance(self.work, (RunWork, ContinueWork)):
            valid = scope.role == 'cli' and scope.source == self.work.source
        else:
            valid = scope.role in ('projects', 'warmup') and scope.source == f'{scope.role}:{self.work.id}:{self.work.generation}'
        if (not valid or self.work.account_id != scope.account_id
                or len(self.work.model_dump_json().encode()) > 192 * 1024):
            raise ValueError('中央远程工作与原执行范围不一致')
        independent = scope.gateway_account_id is None
        if independent and (self.gateway_prepare_intent or self.lease is not None or self.lease_released is not None):
            raise ValueError('独立账号不能登记网关租约')
        if (not independent and (self.local_admission_intent or self.local_admission_released)
                or self.local_admission_released and not self.local_admission_intent):
            raise ValueError('独立执行许可与原账号绑定不一致')
        if self.lease is not None and (not self.gateway_prepare_intent or self.lease.owner != scope.source):
            raise ValueError('中央租约缺少原认领意图或source不一致')
        if self.grant is not None:
            if self.grant.scope() != scope:
                raise ValueError('节点证明与原执行范围不一致')
            if independent:
                if (self.grant.lease is not None or not self.local_admission_intent
                        or self.quota_identity is None and not isinstance(self.work,(CredentialRefreshWork,CredentialUsageWork,AccountLoginWork))):
                    raise ValueError('独立节点证明缺少原中央许可')
            elif (self.grant.lease is None or self.lease is None
                    or self.grant.lease.model_dump(exclude={'expires_at'}) != self.lease.model_dump(exclude={'expires_at'})
                    or self.grant.not_after > self.lease.expires_at):
                raise ValueError('节点证明超出中央原租约范围')
        if self.lease_released is not None and (self.lease is None or not self.lease_released.released
                or self.lease_released.owner != self.lease.owner or self.lease_released.generation != self.lease.generation):
            raise ValueError('中央租约释放回执与原代次不一致')
        if self.node_receipt is not None:
            receipt = self.node_receipt
            if (type(receipt.get('protocol')) is not int or receipt['protocol'] != 1
                    or receipt.get('scope') != scope.model_dump()
                    or receipt.get('phase') not in ('starting', 'ready', 'reconcile', 'closed')
                    or len(json.dumps(receipt, ensure_ascii=False, allow_nan=False).encode()) > 64 * 1024):
                raise ValueError('中央保存的节点回执与原操作不一致')
            result = receipt.get('result')
            if receipt['phase'] == 'ready' and not isinstance(result, dict):
                raise ValueError('原节点启动确认缺少实际执行定位')
            if result is not None and (not isinstance(result, dict) or result.get('source') != scope.source
                    or not isinstance(result.get('token'), str) or not 1 <= len(result['token']) <= 512):
                raise ValueError('原节点执行定位与实际source不一致')
        if self.local_admission_released and (self.node_receipt is None or self.node_receipt['phase'] != 'closed'):
            raise ValueError('独立许可释放前必须确认原节点停止')
        if self.node_start_cancelled and (independent or not self.gateway_prepare_intent or self.grant is not None
                or self.node_receipt is not None or self.failure != 'central_node_not_submitted'
                or self.lease is not None and self.lease_released is None):
            raise ValueError('原节点未提交撤销与中央许可证据不一致')
        return self


class NodeExecutions:
    """中央执行会话与恢复游标，所有写入复用原数据库写锁。

    :param store: 原中央节点与分配存储。
    :param release: 原同批控制发布。
    """

    def __init__(self, store, release: str) -> None:
        """登记中央存储，初始化保持已有执行和租约。

        :param store: 原ClusterStore。
        :param release: 当前控制发布。
        :return: None。
        """
        if not isinstance(release, str) or not 1 <= len(release) <= 128:
            raise ValueError('中央执行登记缺少原控制发布')
        self.store, self.release = store, release

    def _decode(self, row) -> dict:
        if row is None:
            raise ValueError('原节点执行记录不存在')
        value = dict(row)
        record = CentralExecutionRecord.model_validate(strict_json(value.pop('record_json').encode(), 512 * 1024))
        scope = record.scope
        expected = {'operation_id': scope.operation_id, 'account_id': scope.account_id,
            'environment_id': scope.environment_id, 'assignment_revision': scope.assignment_revision,
            'environment_generation': scope.generation, 'source': scope.source, 'role': scope.role}
        if any(value.get(key) != item for key, item in expected.items()):
            raise ValueError('中央执行行与冻结私有记录不一致')
        self._validate_phase(value['phase'], record)
        return {**value, 'record': record.model_dump()}

    def _validate_phase(self, phase: str, record: CentralExecutionRecord) -> None:
        if record.node_start_cancelled:
            if phase != 'closed':
                raise ValueError('原节点未提交撤销只允许在中央收口后记录')
            return
        if (phase == 'closed' and record.failure == 'central_not_started' and not record.gateway_prepare_intent
                and record.lease is None and record.grant is None and record.node_receipt is None
                and record.lease_released is None and not record.local_admission_intent and not record.local_admission_released):
            return
        independent = record.scope.gateway_account_id is None
        if independent and phase in ('claimed', 'starting', 'running', 'stopping', 'closed') and not record.local_admission_intent:
            raise ValueError('中央独立执行阶段缺少原许可意图')
        if not independent and phase in ('claimed', 'starting', 'running', 'stopping', 'closed') and record.lease is None:
            raise ValueError('中央执行阶段缺少原真实租约证据')
        if phase in ('starting', 'running') and record.grant is None:
            raise ValueError('节点执行启动缺少原有限证明')
        if phase == 'running' and (record.node_receipt is None or record.node_receipt['phase'] != 'ready'):
            raise ValueError('运行阶段缺少原节点启动确认')
        if phase == 'closed' and (record.node_receipt is None or record.node_receipt['phase'] != 'closed'
                or (not record.local_admission_released if independent else record.lease_released is None)):
            raise ValueError('关闭执行前必须确认节点停止与中央原租约释放')

    def get(self, operation_id: str) -> dict:
        """读取原操作，归属变化后保留原历史。

        :param operation_id: 原独立操作。
        :return: 中央私有记录，公开页面须另作字段投影。
        """
        if not re.fullmatch('[a-f0-9]{32}', operation_id):
            raise ValueError('节点执行操作身份无效')
        connection = self.store.database()
        try:
            return self._decode(connection.execute('SELECT * FROM node_executions WHERE operation_id=?', (operation_id,)).fetchone())
        finally:
            connection.close()

    def find(self, operation_id: str) -> dict | None:
        """只读定位可选原操作，数据库或坏记录错误保持明确失败。

        :param operation_id: 原独立操作。
        :return: 原私有记录，确实缺失时为None。
        """
        if not re.fullmatch('[a-f0-9]{32}', operation_id):
            raise ValueError('节点执行操作身份无效')
        connection = self.store.database()
        try:
            row = connection.execute('SELECT * FROM node_executions WHERE operation_id=?', (operation_id,)).fetchone()
            return self._decode(row) if row is not None else None
        finally:
            connection.close()

    def by_source(self, account_id: int, source: str, *, active_only: bool = True) -> dict | None:
        """按原中央工作来源恢复操作映射，未知提交继续引用原行。

        :param account_id: 原中央账号。
        :param source: 原工作及控制代次的source。
        :param active_only: 是否只读未收口操作。
        :return: 最新原操作，明确缺失时为None。
        """
        if type(account_id) is not int or account_id <= 0 or not isinstance(source, str) or not 1 <= len(source) <= 160:
            raise ValueError('节点执行来源定位无效')
        connection = self.store.database()
        try:
            condition = " AND phase<>'closed'" if active_only else ''
            row = connection.execute('SELECT * FROM node_executions WHERE account_id=? AND source=?' + condition
                + ' ORDER BY created_at DESC,rowid DESC LIMIT 1', (account_id, source)).fetchone()
            return self._decode(row) if row is not None else None
        finally:
            connection.close()

    def latest_cycle(self, account_id: int, role: str, cycle_no: int) -> dict | None:
        """定位指定空间和轮次最后一条实际执行，供轮次清理核对。

        :param account_id: 中央账号。
        :param role: projects或warmup。
        :param cycle_no: 已确认结束的正整数轮次。
        :return: 原冻结执行或None。
        """
        if type(account_id) is not int or account_id < 1 or role not in ('projects', 'warmup') or type(cycle_no) is not int or cycle_no < 1:
            raise ValueError('工程轮次执行定位无效')
        connection = self.store.database()
        try:
            row = connection.execute('SELECT * FROM node_executions WHERE account_id=? AND role=? '
                "AND json_extract(record_json,'$.work.cycle_no')=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
                (account_id, role, cycle_no)).fetchone()
            return self._decode(row) if row else None
        finally:
            connection.close()

    def pending(self) -> list[str]:
        """列出未收口执行的原操作，以便逐账号隔离坏记录。

        :return: 中央持久操作标识；完整范围仍须逐条get核对。
        """
        connection = self.store.database()
        try:
            return [row['operation_id'] for row in connection.execute("SELECT operation_id FROM node_executions "
                "WHERE phase<>'closed' ORDER BY created_at,rowid")]
        finally:
            connection.close()

    def active(self, account_id: int) -> list[dict]:
        """读取一个账号的持久未收口执行，重启准入不依赖内存jobs。

        :param account_id: 原中央账号。
        :return: 按登记时间排列的原私有记录。
        """
        if type(account_id) is not int or account_id <= 0:
            raise ValueError('节点执行账号身份无效')
        connection = self.store.database()
        try:
            return [self._decode(row) for row in connection.execute("SELECT * FROM node_executions WHERE account_id=? "
                "AND phase<>'closed' ORDER BY created_at,rowid", (account_id,))]
        finally:
            connection.close()

    def begin(self, scope: ExecutionScope, work: TerminalWork | RunWork | ContinueWork | CredentialRefreshWork | CredentialUsageWork | AccountLoginWork | BoundLoginWork, *, require_new: bool = False) -> dict:
        """同一事务冻结当前归属和工作，同source的未知启动只沿原操作恢复。

        :param scope: 中央依据实际环境形成的冻结范围。
        :param work: 原工作实际消费字段。
        :param require_new: 协调器认领新处理者时拒绝另一进程已建立的同操作。
        :return: preparing记录，尚未认领中央真实租约。
        """
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    previous = connection.execute('SELECT * FROM node_executions WHERE operation_id=?', (scope.operation_id,)).fetchone()
                    if previous is not None:
                        if require_new:
                            raise ValueError('原节点执行已由其他处理者登记，请查询原操作')
                        value = self._decode(previous)
                        if value['record']['scope'] != scope.model_dump() or value['record']['work'] != work.model_dump():
                            raise ValueError('原节点执行操作的冻结范围已变化')
                        return value
                    if connection.execute("SELECT 1 FROM node_executions WHERE account_id=? AND source=? AND phase<>'closed'",
                            (scope.account_id, scope.source)).fetchone():
                        raise ValueError('原source已有节点执行记录，请查询原操作')
                    closed = connection.execute('SELECT * FROM node_executions WHERE account_id=? AND source=? '
                        'ORDER BY created_at DESC LIMIT 1', (scope.account_id, scope.source)).fetchone()
                    if closed is not None:
                        if isinstance(work,(CredentialRefreshWork,CredentialUsageWork,AccountLoginWork)):
                            raise ValueError('原凭据刷新尝试已收口，禁止重放旧操作')
                        if isinstance(work, (RunWork, ContinueWork)):
                            raise ValueError('原Run尝试已实际收口，后续执行需要新的原尝试标识')
                        original = self._decode(closed)['record']['work']
                        stable = ('id', 'account_id', 'generation', 'session_id', 'project_key', 'objective_id',
                            'library_digest', 'settings_json', 'cycle_no', 'created_at')
                        candidate = work.model_dump()
                        if (any(original[key] != candidate[key] for key in stable)
                                or candidate['remaining_sec'] > original['remaining_sec']
                                or original['has_baseline'] and not candidate['has_baseline']
                                or original['resume_required'] and not candidate['resume_required']):
                            raise ValueError('已停止原source的新握手必须保留原工作及剩余预算')
                    current = connection.execute('SELECT n.*,b.revision AS assignment_revision,b.phase AS assignment_phase,'
                        'e.environment_id,e.generation,e.state AS environment_state,a.cc2api_account_id FROM account_node_assignments b '
                        'JOIN cluster_nodes n ON n.id=b.node_id JOIN accounts a ON a.id=b.account_id '
                        'JOIN account_environments e ON e.account_id=a.id WHERE a.id=? AND (a.enabled=1 OR ?=1) AND a.deleted_at IS NULL '
                        "AND NOT EXISTS (SELECT 1 FROM node_login_drafts d WHERE d.saved_account_id=a.id AND d.phase<>'closed') "
                        "AND n.enabled=1 AND n.deleted_at IS NULL AND n.kind='ssh'",
                        (scope.account_id,int(scope.account_login and isinstance(work,AccountLoginWork)))).fetchone()
                    if (current is None or current['node_key'] != scope.node_key or current['assignment_phase'] != 'ready'
                            or current['assignment_revision'] != scope.assignment_revision
                            or current['environment_id'] != scope.environment_id or current['generation'] != scope.generation
                            or current['cc2api_account_id'] != scope.gateway_account_id
                            or current['environment_state'] not in ('ready', 'stopped')):
                        raise ValueError('中央账号、节点、分配或实际环境代次已变化')
                    preparation = strict_json((current['preparation_json'] or '{}').encode(), 65536)
                    if preparation.get('state') != 'prepared' or preparation.get('release') != self.release:
                        raise ValueError('原节点需要先准备同批控制组件')
                    record = CentralExecutionRecord(scope=scope, work=work, runtime_release=self.release,
                        node_config_sha256=hashlib.sha256(current['config_json'].encode()).hexdigest())
                    now = time.time()
                    connection.execute('INSERT INTO node_executions(operation_id,account_id,node_id,environment_id,'
                        'assignment_revision,environment_generation,source,role,phase,record_json,created_at,updated_at) '
                        "VALUES(?,?,?,?,?,?,?,?,'preparing',?,?,?)", (scope.operation_id, scope.account_id, current['id'],
                        scope.environment_id, scope.assignment_revision, scope.generation, scope.source, scope.role,
                        record.model_dump_json(), now, now))
            finally:
                connection.close()
        return self.get(scope.operation_id)

    def admit(self, operation_id: str) -> dict:
        """新操作前核对当前中央归属，历史读取继续使用get。

        :param operation_id: 原执行。
        :return: 当前归属仍匹配的原私有记录，租约和节点输入许可由协调器继续核验。
        """
        value = self.get(operation_id)
        scope = ExecutionScope.model_validate(value['record']['scope'])
        if value['phase'] in ('stopping', 'reconcile', 'closed'):
            raise ValueError('原节点执行正在收口或需要先对账')
        self._check_assignment(value, scope)
        return value

    def maintenance(self, operation_id: str) -> dict:
        """核对已收口原执行的当前归属，供固定轮次清理使用。

        :param operation_id: 已确认双端收口的原执行。
        :return: 当前归属仍匹配的关闭记录。
        """
        value = self.get(operation_id)
        if value['phase'] != 'closed':
            raise ValueError('工程维护要求原节点执行已确认收口')
        self._check_assignment(value, ExecutionScope.model_validate(value['record']['scope']))
        return value

    def _check_assignment(self, value: dict, scope: ExecutionScope) -> None:
        connection = self.store.database()
        try:
            current = connection.execute('SELECT n.*,b.revision AS assignment_revision,b.phase AS assignment_phase,'
                'e.environment_id,e.generation,e.state AS environment_state,a.cc2api_account_id FROM account_node_assignments b '
                'JOIN cluster_nodes n ON n.id=b.node_id JOIN accounts a ON a.id=b.account_id '
                'JOIN account_environments e ON e.account_id=a.id WHERE a.id=? AND (a.enabled=1 OR ?=1) AND a.deleted_at IS NULL '
                "AND NOT EXISTS (SELECT 1 FROM node_login_drafts d WHERE d.saved_account_id=a.id AND d.phase<>'closed') "
                "AND n.enabled=1 AND n.deleted_at IS NULL AND n.kind='ssh'",
                (scope.account_id,int(scope.account_login and value['record']['work'].get('kind') in ('account-login','account-bound-login')))).fetchone()
            if (current is None or current['id'] != value['node_id'] or current['node_key'] != scope.node_key
                    or current['assignment_revision'] != scope.assignment_revision or current['assignment_phase'] != 'ready'
                    or current['environment_id'] != scope.environment_id or current['generation'] != scope.generation
                    or current['cc2api_account_id'] != scope.gateway_account_id
                    or current['environment_state'] not in ('ready', 'stopped')
                    or hashlib.sha256(current['config_json'].encode()).hexdigest() != value['record']['node_config_sha256']):
                raise ValueError('原节点执行的中央归属、配置或实际代次已变化')
            preparation = strict_json((current['preparation_json'] or '{}').encode(), 65536)
            if preparation.get('state') != 'prepared' or preparation.get('release') != value['record']['runtime_release']:
                raise ValueError('原节点执行的控制发布需要先核对')
        finally:
            connection.close()

    def checkpoint(self, operation_id: str, revision: int, phase: str, **changes) -> dict:
        """按原CAS版本保存许可或节点回执，关闭前要求节点与中央双重收口。

        :param operation_id: 原操作。
        :param revision: 本次读取的账本版本。
        :param phase: 本次确定的阶段。
        :param changes: 受限证据字段，冻结身份保持原值。
        :return: 新版本私有记录。
        """
        allowed = {'gateway_prepare_intent', 'lease', 'grant', 'node_receipt', 'lease_released', 'failure', 'quota_identity',
            'local_admission_intent', 'local_admission_released', 'node_start_cancelled'}
        if set(changes) - allowed:
            raise ValueError('节点执行检查点超出可更新证据范围')
        transitions = {'preparing': {'preparing', 'claimed', 'reconcile', 'closed'},
            'claimed': {'claimed', 'starting', 'stopping', 'reconcile'},
            'starting': {'starting', 'running', 'stopping', 'reconcile'},
            'running': {'running', 'stopping', 'reconcile'}, 'stopping': {'stopping', 'closed', 'reconcile'},
            'reconcile': {'reconcile', 'claimed', 'starting', 'running', 'stopping', 'closed'}, 'closed': {'closed'}}
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    previous = self._decode(connection.execute('SELECT * FROM node_executions WHERE operation_id=?', (operation_id,)).fetchone())
                    if type(revision) is not int or previous['revision'] != revision:
                        raise ValueError('节点执行版本已变化，请先读取原记录')
                    if phase not in transitions.get(previous['phase'], set()):
                        raise ValueError('节点执行阶段不能跳过原恢复边界')
                    old = CentralExecutionRecord.model_validate(previous['record'])
                    record = CentralExecutionRecord.model_validate({**previous['record'], **changes})
                    if previous['phase'] == 'closed' and record != old:
                        raise ValueError('原关闭执行历史已经固定，请使用明确的新握手操作')
                    if old.lease is not None and (record.lease is None
                            or old.lease.model_dump(exclude={'expires_at'}) != record.lease.model_dump(exclude={'expires_at'})
                            or record.lease.expires_at < old.lease.expires_at):
                        raise ValueError('中央原租约身份、模式或截止不能被覆盖')
                    if old.gateway_prepare_intent and not record.gateway_prepare_intent:
                        raise ValueError('中央原认领意图必须继续保留')
                    if (old.local_admission_intent and not record.local_admission_intent
                            or old.local_admission_released and not record.local_admission_released):
                        raise ValueError('原独立许可意图和释放事实必须继续保留')
                    if old.quota_identity is not None and record.quota_identity != old.quota_identity:
                        raise ValueError('原执行的中央额度身份必须继续保留')
                    if old.grant is not None and record.grant != old.grant:
                        if (record.grant is None or record.grant.sequence != old.grant.sequence + 1
                                or record.grant.not_after < old.grant.not_after):
                            raise ValueError('节点证明续接序号或截止不能回退')
                    if old.lease_released is not None and record.lease_released != old.lease_released:
                        raise ValueError('原租约释放事实必须继续保留')
                    if old.node_receipt is not None and old.node_receipt['phase'] == 'closed' and (
                            record.node_receipt is None or record.node_receipt['phase'] != 'closed'):
                        raise ValueError('原节点停止收据不能回退为可执行')
                    if old.node_receipt is not None and old.node_receipt.get('result') is not None and (
                            record.node_receipt is None or record.node_receipt.get('result') != old.node_receipt['result']):
                        raise ValueError('原节点实际执行定位不能被其他进程覆盖')
                    self._validate_phase(phase, record)
                    serialized = record.model_dump_json()
                    if len(serialized.encode()) > 512 * 1024:
                        raise ValueError('中央节点执行记录超过保存上限')
                    result = connection.execute('UPDATE node_executions SET phase=?,record_json=?,revision=revision+1,updated_at=? '
                        'WHERE operation_id=? AND revision=?', (phase, serialized, time.time(), operation_id, revision))
                    if result.rowcount != 1:
                        raise ValueError('节点执行版本已变化')
            finally:
                connection.close()
        return self.get(operation_id)
