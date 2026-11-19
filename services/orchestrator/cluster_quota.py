"""远程工程的中央额度门禁投影及受限JSONL镜像，沿用原被动消费协议。"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from stat import S_ISREG
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from cluster_execution_grants import ExecutionScope
from cluster_deployment import node_container_name
from account_runtime import _read_json
from runtime_files import atomic_json, directory_fd, private_directory
from system_update_contract import safe_read, strict_json


class TerminalQuotaState(BaseModel):
    """中央门禁的有限投影。:param scope: 原执行。:param sequence: 当前证明序号。:param sampled_at: 中央采样时刻。:param state: 原额度门禁。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    sequence: StrictInt = Field(ge=1)
    sampled_at: float = Field(strict=True, gt=0, allow_inf_nan=False)
    state: dict

    @model_validator(mode='after')
    def bounded_state(self):
        """限制节点只读门禁投影的身份及体积。:return: 原请求。"""
        if (not isinstance(self.state.get('identity'), str) or not 1 <= len(self.state['identity']) <= 4096
                or len(json.dumps(self.state, ensure_ascii=False, allow_nan=False).encode()) > 64 * 1024):
            raise ValueError('节点额度投影身份或大小无效')
        return self


class TerminalQuotaRead(BaseModel):
    """节点原额度文件的有界只读请求。:param scope: 原执行。:param stream: CLI或Recorder。:param offset: 已镜像字节位置。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    stream: Literal['cli', 'recorder']
    offset: StrictInt = Field(default=0, ge=0)


class QuotaFileChunk(BaseModel):
    """原节点额度文件片段。:param file_identity: 原文件身份。:param offset: 实际读取起点。:param size: 实际大小。:param content: 有界原始字节。"""

    model_config = ConfigDict(extra='forbid')
    file_identity: StrictStr | None = Field(default=None, pattern=r'^[0-9]+:[0-9]+$')
    offset: StrictInt = Field(ge=0)
    size: StrictInt = Field(ge=0)
    content: StrictStr = Field(max_length=174764)


class TerminalQuotaChunk(QuotaFileChunk):
    """原终端额度片段及冻结范围。:param scope: 原执行。:param stream: 固定源。"""

    scope: ExecutionScope
    stream: Literal['cli', 'recorder']


class _QuotaMirrorCursor(BaseModel):
    """镜像私有游标，损坏记录保留供核对。"""

    model_config = ConfigDict(extra='forbid')
    scope: dict
    file_identity: StrictStr | None = Field(default=None, pattern=r'^[0-9]+:[0-9]+$')
    offset: StrictInt = Field(ge=0)

    @model_validator(mode='after')
    def validate_position(self):
        """有已复制字节时必须知道原文件身份。:return: 原游标。"""
        if self.file_identity is None and self.offset:
            raise ValueError('额度镜像缺少原文件身份')
        return self


class ApiQuotaScope(BaseModel):
    """固定发送器额度读取范围。:param node_key: 原节点。:param account_id: 原账号。:param environment_id: 原环境。:param assignment_revision: 原分配版本。:param generation: 实际代次。"""

    model_config = ConfigDict(extra='forbid')
    node_key: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    account_id: StrictInt = Field(ge=1)
    environment_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    assignment_revision: StrictInt = Field(ge=1)
    generation: StrictInt = Field(ge=0)


class ApiQuotaRead(BaseModel):
    """固定发送器证据的有界读取。:param scope: 原环境范围。:param offset: 字节游标。"""

    model_config = ConfigDict(extra='forbid')
    scope: ApiQuotaScope
    offset: StrictInt = Field(default=0, ge=0)


class ApiQuotaChunk(QuotaFileChunk):
    """带原环境范围的API额度证据。:param scope: 已核对范围。"""

    scope: ApiQuotaScope


def read_api_quota(executor, request: ApiQuotaRead) -> dict:
    """核对原归属后只读发送器固定证据。:param executor: 当前安装节点。:param request: 有界查询。:return: 原范围与片段。"""
    scope = request.scope
    if scope.node_key != executor.node_key:
        raise ValueError('API额度证据属于其他节点')
    with executor._locked(read_only=True, environment_id=scope.environment_id):
        root = executor.data / 'environments' / scope.environment_id
        expected = {'protocol': 1, 'node_key': scope.node_key, 'account_id': scope.account_id,
            'environment_id': scope.environment_id, 'revision': scope.assignment_revision, 'phase': 'ready'}
        if _read_json(root / 'runtime/node-assignment.json') != expected:
            raise ValueError('API额度证据的分配版本已变化')
        connection = executor.database()
        try:
            row = connection.execute('SELECT generation FROM account_environments WHERE environment_id=? AND account_id=?',
                (scope.environment_id, scope.account_id)).fetchone()
        finally:
            connection.close()
        if row is None or row['generation'] != scope.generation:
            raise ValueError('API额度证据的实际环境代次已变化')
        return {'scope': scope.model_dump(), **_read_quota_file(root / 'flows/api/observations.jsonl', request.offset)}


def register_api_quota_cursor(connection, data: Path, account_id: int, identity: str,
                              environment_id: str, *, remote: bool) -> None:
    """在调用方已核对归属的短事务内交接固定 API 来源。

    :param connection: 持有共享写锁的数据库连接。
    :param data: 中央数据根。
    :param account_id: 已核对账号。
    :param identity: 原额度身份。
    :param environment_id: 原环境。
    :param remote: 当前归属是否使用中央远程镜像。
    :return: None；未知身份或路径保留原记录并报错。
    """
    source = f'api:{environment_id}:{identity}'
    local = data / 'environments' / environment_id / 'flows/api/observations.jsonl'
    mirror = data / 'cluster-quota' / hashlib.sha256(f'{account_id}:{source}'.encode()).hexdigest() / 'api.jsonl'
    path = str(mirror if remote else local)
    connection.execute('INSERT OR IGNORE INTO quota_observation_cursors(source,account_id,identity,path,byte_offset) '
        'VALUES(?,?,?,?,0)', (source, account_id, identity, path))
    existing = connection.execute('SELECT account_id,identity,path FROM quota_observation_cursors WHERE source=?',
        (source,)).fetchone()
    if (existing['account_id'] != account_id or existing['identity'] != identity
            or existing['path'] not in (str(local), str(mirror))):
        raise ValueError('API额度来源已登记另一身份或未知路径')
    if existing['path'] != path:
        # 逻辑来源跨迁移保持；文件字节位置只属于原物理文件，额度与许可继续由原表持有。
        connection.execute('UPDATE quota_observation_cursors SET path=?,file_identity=NULL,byte_offset=0 WHERE source=?',
            (path, source))


class RemoteApiQuota:
    """所属节点API证据镜像，原消费器继续持有额度权威。:param service: 中央归属。:param runtime: 中央环境登记。:param identity: 原额度身份函数。"""

    def __init__(self, service, runtime, identity) -> None:
        """保存依赖与账号级镜像锁。:param service: 归属。:param runtime: 环境。:param identity: 原身份。:return: None。"""
        self.service, self.runtime, self.identity = service, runtime, identity
        self.lock, self.account_locks = threading.Lock(), {}

    def pull(self, account: dict) -> None:
        """读取当前已准备环境的API证据，失败关闭本次新准入。:param account: 当前账号。:return: None。"""
        if account.get('cc2api_account_id') is None:
            return
        with self.lock:
            lock = self.account_locks.setdefault(account['id'], threading.Lock())
        with lock:
            self._pull(account)

    def _pull(self, account: dict) -> None:
        assignment = self.service.store.assignment(account['id'])
        if assignment['kind'] != 'ssh':
            return
        if not assignment['enabled'] or assignment['phase'] != 'ready':
            raise ValueError('所属节点正在维护，API额度证据等待核对')
        connection = self.service.store.database()
        try:
            row = connection.execute('SELECT environment_id,generation FROM account_environments WHERE account_id=?',
                (account['id'],)).fetchone()
        finally:
            connection.close()
        if row is None or row['generation'] == 0:
            return
        scope = ApiQuotaScope(node_key=assignment['node_key'], account_id=account['id'],
            environment_id=row['environment_id'], assignment_revision=assignment['revision'], generation=row['generation'])
        identity = self.identity(account)
        source = f'api:{scope.environment_id}:{identity}'
        root = self.service.data / 'cluster-quota'
        private_directory(root)
        parent = root / hashlib.sha256(f'{account["id"]}:{source}'.encode()).hexdigest()
        private_directory(parent)
        metadata = parent / 'api.json'
        saved = strict_json(safe_read(metadata, 8192, private=True), 8192) if metadata.exists() or metadata.is_symlink() else {
            'scope': scope.model_dump(), 'file_identity': None, 'offset': 0}
        saved = _QuotaMirrorCursor.model_validate(saved).model_dump()
        previous = ApiQuotaScope.model_validate(saved.get('scope'))
        if previous.account_id != scope.account_id or previous.environment_id != scope.environment_id:
            raise ValueError('API额度镜像的原环境或游标无效')
        if previous != scope:
            saved = {**saved, 'file_identity': None, 'offset': 0}

        def read(offset):
            response = self.service.connection(assignment['node_id']).execution_environment(
                node_container_name(self.runtime.deployment, scope.node_key),
                ApiQuotaRead(scope=scope, offset=offset).model_dump(), 'api-quota-read')
            if response.get('node_key') != scope.node_key:
                raise ValueError('API额度片段属于其他节点')
            chunk = ApiQuotaChunk.model_validate(response.get('quota'))
            if chunk.scope != scope:
                raise ValueError('API额度片段属于其他环境')
            return chunk.model_dump(exclude={'scope'})

        chunk = _mirror_quota_file(parent, 'api', saved, read, read(saved['offset']))
        if chunk is None:
            return
        # 网络读取期间人工迁移可能进入排空，迟到证据仍须重新核对原归属。
        current = self.service.store.assignment(account['id'])
        if any(current[key] != assignment[key] for key in ('node_id', 'revision', 'phase')):
            raise ValueError('API额度读取期间节点归属已变化')
        atomic_json(metadata, {'scope': scope.model_dump(), 'file_identity': chunk.file_identity,
            'offset': chunk.offset + len(base64.b64decode(chunk.content, validate=True))})
        with self.service.store.lock:
            connection = self.service.store.database()
            try:
                with connection:
                    current = connection.execute('SELECT b.node_id,b.revision,b.phase,n.enabled,e.environment_id,e.generation '
                        'FROM account_node_assignments b JOIN cluster_nodes n ON n.id=b.node_id '
                        'JOIN account_environments e ON e.account_id=b.account_id WHERE b.account_id=?', (account['id'],)).fetchone()
                    if current is None or tuple(current) != (assignment['node_id'], assignment['revision'], 'ready', 1,
                            scope.environment_id, scope.generation):
                        raise ValueError('API额度登记期间节点归属或实际代次已变化')
                    register_api_quota_cursor(connection, self.service.data, account['id'], identity,
                        scope.environment_id, remote=True)
            finally:
                connection.close()


class NodeTerminalQuota:
    """复用节点原挂载和额度记录，所有路径由原scope推导。

    :param terminals: 原节点终端。
    """

    def __init__(self, terminals) -> None:
        """绑定本节点执行和短发布锁。:param terminals: 原终端。:return: None。"""
        self.terminals, self.lock = terminals, threading.RLock()

    def publish(self, request: TerminalQuotaState) -> dict:
        """发布中央当前门禁，迟到或超期证明拒绝覆盖。

        :param request: 原当前证明序号及有限额度快照。
        :return: 本次已确认序号和采样时刻。
        """
        scope = request.scope
        with self.lock:
            self.terminals.grants.check_scope(scope)
            grant = self.terminals.grants.get(scope)
            current = grant['grant']
            if (grant['phase'] == 'closed' or current['sequence'] != request.sequence
                    or not time.time() < current['not_after'] <= time.time() + 35
                    or not -5 <= time.time() - request.sampled_at <= 35
                    or request.state['identity'] != self.terminals.host.gateway.quota_identity({'id': scope.account_id})):
                raise ValueError('原节点额度投影的证明、身份或采样已失效')
            data = self.terminals.executor.data
            private_directory(data / 'node-quota')
            metadata = data / 'node-quota' / (str(scope.account_id) + '.json')
            parent = data / 'node-quota-scopes'
            private_directory(parent)
            private_directory(parent / scope.environment_id)
            scoped = quota_scope_path(data, scope)
            if scoped.exists() or scoped.is_symlink():
                own = TerminalQuotaState.model_validate(strict_json(safe_read(scoped, 96 * 1024, private=True), 96 * 1024))
                if (own.scope != scope or request.sampled_at < own.sampled_at
                        or request.sampled_at == own.sampled_at and request != own):
                    raise ValueError('迟到节点额度投影拒绝覆盖新采样')
            previous = None
            if metadata.exists() or metadata.is_symlink():
                previous = TerminalQuotaState.model_validate(strict_json(safe_read(metadata, 96 * 1024, private=True), 96 * 1024))
                if previous.scope == scope and (request.sampled_at < previous.sampled_at
                        or request.sampled_at == previous.sampled_at and request != previous):
                    raise ValueError('迟到节点额度投影拒绝覆盖新采样')
            # 先保存原采样身份；重复发布可修复门禁文件原子替换前的进程中断。
            atomic_json(scoped, request.model_dump())
            # 两个共享作业各有自己的启动上下文；迟到的另一个scope只保留自身上下文，账号窗口保持最新。
            if previous is None or request.sampled_at > previous.sampled_at or previous == request:
                atomic_json(metadata, request.model_dump())
                atomic_json(data / 'quota' / str(scope.account_id) / 'state.json', request.state, mode=0o644)
            return {'sequence': request.sequence, 'sampled_at': request.sampled_at}

    def read(self, request: TerminalQuotaRead) -> dict:
        """读取原终端固定额度文件，拒绝链接并保持半行原字节。

        :param request: 原执行、固定额度源及字节游标。
        :return: 最多128KiB原始字节的base64片段。
        """
        scope = request.scope
        record = self.terminals._record(scope)
        group = (str(record['work']['task']['id']) + '/' + record['work']['id'] if scope.role == 'cli'
            else scope.role + '/' + record['work']['id'])
        if scope.role == 'cli' and scope.source.startswith('continue:'):
            group += '/continue-' + record['work']['sid']
        base = (self.terminals.executor.data / 'environments' / scope.environment_id / 'flows'
            / ('group-' + hashlib.sha256(group.encode()).hexdigest()[:20]) / 'executions'
            / hashlib.sha256(scope.source.encode()).hexdigest()[:20])
        path = base / ('cli/cli-quota.jsonl' if request.stream == 'cli' else 'passive-quota.jsonl')
        private=self.terminals.quota_source(scope,request.stream)
        if private is not None:
            path=private
        return {'scope': scope.model_dump(), 'stream': request.stream, **_read_quota_file(path, request.offset)}


def quota_scope_path(data: Path, scope: ExecutionScope) -> Path:
    """解析该次执行的独立额度上下文，账号公共窗口继续单独投影。

    :param data: 原节点数据根。
    :param scope: 原冻结执行。
    :return: 固定私有上下文路径。
    """
    return data / 'node-quota-scopes' / scope.environment_id / (scope.operation_id + '.json')


class RemoteTerminalQuota:
    """把节点额度证据镜像到中央，消费仍由原QuotaGuard处理。

    :param sessions: 原中央会话协调器。
    :param guard: 原QuotaGuard。
    :param identity: 原账号额度身份。
    """

    def __init__(self, sessions, guard, identity) -> None:
        """保存原权威依赖。:param sessions: 原会话。:param guard: 原额度门禁。:param identity: 原身份。:return: None。"""
        self.sessions, self.guard, self.identity = sessions, guard, identity

    def refresh(self, row: dict) -> None:
        """原证明续接后同步有界观察和最新中央门禁。

        :param row: 当前已持久保存的原证明。
        :return: None；失败由原会话协调器保留待核对。
        """
        scope = ExecutionScope.model_validate(row['record']['scope'])
        account = self.sessions._account(scope)
        if row['record']['quota_identity'] != self.identity(account):
            raise ValueError('远程执行的中央额度身份已变化')
        if row['record']['node_receipt'] is not None:
            self.pull(row)
        self.guard.consume(account)
        with self.guard._lock:
            snapshot = self.guard._publish(account)
            state = strict_json(safe_read(self.sessions.service.data / 'quota' / str(scope.account_id) / 'state.json', 65536), 65536)
            low_priority = scope.role != 'cli' or row['record']['work']['task']['warmup']
            policy = self.guard.warmup_snapshot(account, scope.source, quota_state=snapshot) if low_priority else {}
            state['remote_cli'] = {'source': scope.source, 'sample_required': bool(policy.get('sample_required'))}
            sampled_at = time.time()
        request = TerminalQuotaState(scope=scope, sequence=row['record']['grant']['sequence'], sampled_at=sampled_at, state=state)
        response = self.sessions._call(row, 'terminal-quota-state', request.model_dump())
        if response != {'sequence': request.sequence, 'sampled_at': request.sampled_at}:
            raise ValueError('原节点额度门禁采样尚未确认')

    def pull(self, row: dict) -> None:
        """镜像原执行的两个固定额度流，断连与崩溃沿原字节位置恢复。

        :param row: 原中央执行记录，已停止历史也可读。
        :return: None；原消费器负责逐行身份核对和事务游标。
        """
        with self.sessions._operation_lock('quota:' + row['operation_id']):
            for stream in ('cli', 'recorder'):
                self._pull(row, stream)

    def finalize(self, row: dict) -> None:
        """实际停止后消费最后证据，原额度许可在确认后释放。

        :param row: 节点已经closed的原中央执行。
        :return: None；读取失败保留原中央占用供重试。
        """
        self.pull(row)
        self.guard.consume(self.sessions._account(ExecutionScope.model_validate(row['record']['scope']), available=False))

    def _pull(self, row: dict, stream: str) -> None:
        scope = ExecutionScope.model_validate(row['record']['scope'])
        root = self.sessions.service.data / 'cluster-quota'
        private_directory(root)
        # 同工作同代次可有多次已确认收口后的恢复，原额度source及事务游标继续沿用。
        parent = root / hashlib.sha256(f'{scope.account_id}:{scope.source}'.encode()).hexdigest()
        private_directory(parent)
        path, metadata = parent / (stream + '.jsonl'), parent / (stream + '.json')
        saved = strict_json(safe_read(metadata, 8192, private=True), 8192) if metadata.exists() or metadata.is_symlink() else {
            'scope': scope.model_dump(), 'file_identity': None, 'offset': 0}
        saved = _QuotaMirrorCursor.model_validate(saved).model_dump()
        previous_scope = ExecutionScope.model_validate(saved.get('scope'))
        if any(getattr(previous_scope, key) != getattr(scope, key) for key in ('account_id', 'source', 'role')):
            raise ValueError('中央额度镜像的原执行或游标无效')
        if previous_scope.model_dump(exclude={'operation_id'}) != scope.model_dump(exclude={'operation_id'}):
            saved = {**saved, 'file_identity': None, 'offset': 0}
        def read(offset):
            value = TerminalQuotaChunk.model_validate(self.sessions._call(row, 'terminal-quota-read',
                {'scope': scope.model_dump(), 'stream': stream, 'offset': offset}))
            if value.scope != scope or value.stream != stream:
                raise ValueError('原节点额度片段属于其他执行')
            return value.model_dump(exclude={'scope', 'stream'})

        chunk = _mirror_quota_file(parent, stream, saved, read, read(saved['offset']))
        if chunk is None:
            return
        atomic_json(metadata, {'scope': scope.model_dump(), 'file_identity': chunk.file_identity,
            'offset': chunk.offset + len(base64.b64decode(chunk.content, validate=True))})
        observation_source = ('cli:' if stream == 'cli' else '') + scope.source
        with self.sessions.service.store.lock:
            connection = self.sessions.service.store.database()
            try:
                with connection:
                    connection.execute('INSERT OR IGNORE INTO quota_observation_cursors(source,account_id,identity,path,byte_offset) '
                        'VALUES(?,?,?,?,0)', (observation_source, scope.account_id, row['record']['quota_identity'], str(path)))
                    existing = connection.execute('SELECT account_id,identity,path FROM quota_observation_cursors WHERE source=?',
                        (observation_source,)).fetchone()
                    if tuple(existing) != (scope.account_id, row['record']['quota_identity'], str(path)):
                        raise ValueError('额度来源已登记另一身份或执行镜像')
            finally:
                connection.close()


def _read_quota_file(path: Path, offset_requested: int, *, private: bool = False, maximum: int = 128 * 1024) -> dict:
    """从固定证据文件读取至本次fstat大小，保留半行。:param path: 服务端派生路径。:param offset_requested: 原游标。:param private: 是否保留原阶段文件的私有权限要求。:param maximum: 本次读取字节上限，最多128KiB。:return: 有界原始片段。"""
    if type(maximum) is not int or not 1<=maximum<=128*1024:
        raise ValueError('节点证据片段读取上限无效')
    empty = {'file_identity': None, 'offset': 0, 'size': 0, 'content': ''}
    try:
        parent = directory_fd(path.parent)
    except FileNotFoundError:
        return empty
    try:
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            return empty
        with os.fdopen(descriptor, 'rb') as source:
            metadata = os.fstat(source.fileno())
            if not S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or private and metadata.st_mode & 0o077:
                raise ValueError('节点额度证据必须是原普通文件')
            offset = offset_requested if offset_requested <= metadata.st_size else 0
            source.seek(offset)
            # 只读本次fstat已观察的字节，正式采集并发追加不能超过回执中的实际大小。
            content = source.read(min(maximum, metadata.st_size - offset))
            return {**empty, 'file_identity': f'{metadata.st_dev}:{metadata.st_ino}', 'offset': offset,
                'size': metadata.st_size, 'content': base64.b64encode(content).decode()}
    finally:
        os.close(parent)

def _mirror_quota_file(parent: Path, stream: str, saved: dict, read, initial: dict) -> QuotaFileChunk | None:
    """共享轮转、大小和落盘边界，游标发布失败允许重读。:param parent: 私有镜像目录。:param stream: 固定文件名。:param saved: 原字节位置。:param read: 有界原文件读取。:param initial: 已核对首片段。:return: 实际已镜像的原片段或缺失。"""
    path = parent / (stream + '.jsonl')
    chunk = QuotaFileChunk.model_validate(initial)
    content = base64.b64decode(chunk.content, validate=True)
    if len(content) > 128 * 1024 or chunk.offset + len(content) > chunk.size:
        raise ValueError('节点额度片段大小不一致')
    if chunk.file_identity is None:
        if content or chunk.size or chunk.offset:
            raise ValueError('缺失节点额度文件带有未知内容')
        return
    if chunk.file_identity != saved['file_identity'] and saved['offset']:
        # 新文件先从零读取；原文件镜像保留至新身份的首片段到达。
        response = read(0)
        chunk = QuotaFileChunk.model_validate(response)
        if chunk.offset != 0 or chunk.file_identity is None:
            raise ValueError('节点轮转额度文件仍待核对')
        content = base64.b64decode(chunk.content, validate=True)
        if len(content) > 128 * 1024 or len(content) > chunk.size:
            raise ValueError('节点轮转额度片段大小不一致')
    reset = chunk.file_identity != saved['file_identity'] or chunk.offset < saved['offset']
    if not reset and chunk.offset != saved['offset']:
        raise ValueError('节点额度片段跳过原字节游标')
    if reset and chunk.offset != 0:
        raise ValueError('新节点额度文件必须从零镜像')
    if reset:
        temporary = parent / (stream + '.reset')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    else:
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'r+b') as target:
            observed = os.fstat(target.fileno())
            if not S_ISREG(observed.st_mode) or observed.st_uid != os.geteuid() or observed.st_mode & 0o077 or observed.st_nlink != 1:
                raise ValueError('中央额度镜像不是原私有普通文件')
            if observed.st_size < chunk.offset:
                raise ValueError('中央额度镜像在原游标前缺失')
            target.seek(chunk.offset)
            target.write(content)
            target.truncate()
            target.flush()
            os.fsync(target.fileno())
    return chunk
