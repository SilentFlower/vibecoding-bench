"""由 SSH 纳管控制容器调用的私有账号环境准备入口。"""
from __future__ import annotations

import fcntl
import ipaddress
import json
import os
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from stat import S_ISREG
from typing import Callable, Literal

from docker import DockerClient
from docker.errors import DockerException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from account_runtime import AccountRuntime, _read_json, derive_v3_fingerprint, read_cli_identity_at
from account_isolation import ROLE_COLUMNS, ROLE_LABELS, role_container
from database_migrations import apply_migrations
from cluster_environment import EnvironmentFence, fence_environment, restore_fenced_source
from cluster_deployment import node_network_name
from cluster_owner_state import validate_owner_preparation
from cluster_archive import AgyArchiveIdentity, ArchiveIdentity
from cluster_migration_profiles import PROFILE_NAMES, ProfileReference, read_profile
from cluster_migration_files import ArchiveExport, ImportStage, MigrationCliIdentity, MigrationFiles
from cluster_verification import pending_run_programs
from account_update_identity import role_release
from content_capture_settings import read_settings as read_capture_settings
from native_criu_settings import read_settings as read_criu_settings
from native_kernel_upgrade import status as native_kernel_status
from physical_features import physical_features_summary
from runtime_files import atomic_json, directory_fd
from system_update_contract import strict_json


class NodePreparation(BaseModel):
    """中央冻结的单账号环境准备输入。

    :param protocol: 固定私有协议。
    :param node_key: 目标节点身份。
    :param assignment_revision: 人工分配版本。
    :param account: 中央账号行投影。
    :param environment: 中央分配的环境行。
    :param gateway_config: 当前账号的网关运行配置。
    :param quota_identity: 中央冻结的额度身份。
    :param profile_files: 受限的 UTF-8 profile 文件。
    :param cli_only: 独立账号仅准备原CLI布局，保持完整本地凭据。
    :param login_sid: 已有账号明确登录的原SID，只允许准备CLI布局。
    """

    model_config = ConfigDict(extra='forbid')
    protocol: Literal[1] = 1
    node_key: StrictStr = Field(pattern=r'^(local|[a-f0-9]{32})$')
    assignment_revision: StrictInt = Field(ge=1)
    account: dict
    environment: dict
    gateway_config: dict
    quota_identity: StrictStr = Field(max_length=4096)
    profile_files: dict[str, StrictStr] = Field(default_factory=dict)
    cli_only: StrictBool = False
    login_sid: StrictStr | None = Field(default=None,pattern=r'^[a-f0-9]{12}$')


class _GatewaySnapshot:
    def __init__(self, account_id: int, configuration: dict, *, bench_account_id: int | None = None) -> None:
        self.account_id, self.configuration = account_id, configuration
        self.bench_account_id = bench_account_id
        self.notifications: set[int] = set()

    def _request(self, method: str, path: str, payload=None, **kwargs):
        if method == 'GET' and path == f'/admin/runtime/accounts/{self.account_id}/config':
            return self.configuration
        if method == 'GET' and path == '/admin/native-preparations':
            return []
        if method == 'POST' and path == f'/admin/accounts/{self.account_id}/native-preparation':
            self.notifications.add(self.account_id)
            return {'ok': True}
        raise ValueError('节点准备操作超出当前账号的只读网关配置范围')


class NodeLocation(BaseModel):
    """固定指定节点环境的私有定位。

    :param node_key: 安装时冻结的节点。
    :param account_id: 中央账号身份。
    :param environment_id: 环境身份。
    :param assignment_revision: 当前人工分配版本。
    """

    model_config = ConfigDict(extra='forbid')
    node_key: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    account_id: StrictInt = Field(ge=1)
    environment_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    assignment_revision: StrictInt = Field(ge=1)


class NodeInspection(NodeLocation):
    """只读核对指定环境及选定CLI版本。

    :param version: 当前选定CLI版本。
    :param observation: 原Gateway同账号的只读准备观察，由原读取器核对代次及时效。
    """

    version: StrictStr = Field(pattern=r'^2\.1\.[0-9]{1,6}$')
    observation: dict | None = None


class NodeTransportInspection(NodeInspection):
    """复核已运行的 V2 发送器绑定。

    :param transport_gateway_account: 该环境绑定的网关账号。
    :param verify_stopped: 回切时核验原环境和角色实际停止。
    """

    transport_gateway_account: StrictInt = Field(ge=1)
    verify_stopped: StrictBool | None = None


class ImportPreparation(BaseModel):
    """目标已核验私有树与当前中央账号投影。

    :param stage: 原上传与核验范围。
    :param preparation: 中央冻结的目标节点准备输入。
    :param profile_references: 原操作私有文件中的大profile引用。
    """

    model_config = ConfigDict(extra='forbid')
    stage: ImportStage
    preparation: NodePreparation
    profile_references: dict[str, ProfileReference] = Field(default_factory=dict)


class NodeReviewAdmission(NodeInspection):
    """原节点私有评审的只读准入输入。

    :param quota_identity: 中央当前冻结的原账号额度身份。
    :param include_refresh: 是否返回同身份的有界原所有者待办。
    """

    quota_identity: StrictStr=Field(min_length=1,max_length=4096)
    include_refresh: StrictBool=False


class ImportActivation(BaseModel):
    """中央已提交新归属后的精确激活范围。

    :param node_key: 目标节点。
    :param operation_id: 原迁移操作。
    :param transfer_id: 已发布的暂存尝试。
    :param account_id: 原固定账号。
    :param environment_id: 原固定环境。
    :param revision: 已提交的新分配版本。
    :param generation: 目标已核对实际代次。
    """

    model_config = ConfigDict(extra='forbid')
    node_key: StrictStr = Field(pattern=r'^(local|[a-f0-9]{32})$')
    operation_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    transfer_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    account_id: StrictInt = Field(ge=1)
    environment_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    revision: StrictInt = Field(ge=2)
    generation: StrictInt = Field(ge=1)


class ImportRevocation(BaseModel):
    """目标在包尚未生成时也可持久撤销原迁移操作。

    :param node_key: 目标节点。
    :param target_revision: 原冻结目标分配版本。
    :param identity: 中央冻结的迁移及源身份。
    """

    model_config = ConfigDict(extra='forbid')
    node_key: StrictStr = Field(pattern=r'^(local|[a-f0-9]{32})$')
    target_revision: StrictInt = Field(ge=2)
    identity: AgyArchiveIdentity | ArchiveIdentity


class NodeExecution:
    """在节点本地准备中央指定的账号环境，保留中央刷新权。

    :param data: 控制容器内的节点独立数据根。
    :param host_data: 对应的节点宿主数据根。
    :param node_key: 安装时冻结的节点身份。
    :param deployment: 安装时冻结的部署身份。
    :param client: 本节点 Docker 客户端。
    :param runtime_factory: 原运行时构造器；测试可提供执行替身。
    :param local_runtime: 默认节点作为迁移目标时的中央运行时，仅共享本机锁和实际作业。
    :param runtime_release: 持久节点进程的借用释放回调，普通命令默认关闭临时线程池。
    :param shared_runtime: 是否由当前持久进程持有实际jobs。
    """

    def __init__(self, data: Path, host_data: Path, node_key: str, deployment: str,
                 client: DockerClient, runtime_factory: Callable = AccountRuntime,
                 local_runtime: AccountRuntime | None = None, runtime_release: Callable | None = None,
                 shared_runtime: bool = False) -> None:
        """读取受保护的节点归属，初始化不准备任何账号。

        :param data: 容器内节点目录。
        :param host_data: 节点宿主目录。
        :param node_key: 节点身份。
        :param deployment: 部署身份。
        :param client: 本节点 Docker 客户端。
        :param runtime_factory: 运行时构造器。
        :param local_runtime: 默认本机目标使用的已有运行时。
        :param runtime_release: 原借用释放回调。
        :param shared_runtime: 当前进程持有真实jobs时允许核对已登记执行。
        :return: None。
        """
        if not re.fullmatch('(local|[a-f0-9]{32})', node_key):
            raise ValueError('节点身份无效')
        if node_key == 'local':
            if (local_runtime is None or local_runtime.node_key is not None or local_runtime.deployment != deployment
                    or local_runtime.data != data or local_runtime.host_data != host_data
                    or (data / 'cluster-node.json').exists() or (data / 'cluster-node.json').is_symlink()):
                raise ValueError('本机迁移目标与中央运行时归属不一致')
        else:
            owner = _read_json(data / 'cluster-node.json')
            if local_runtime is not None or owner != {'protocol': 1, 'node_key': node_key, 'deployment_id': deployment}:
                raise ValueError('节点数据目录与安装归属不一致')
        self.data, self.host_data, self.node_key, self.deployment = data, host_data, node_key, deployment
        self.client, self.runtime_factory = client, runtime_factory
        if shared_runtime and runtime_release is None:
            raise ValueError('持久节点运行时需要明确的借用释放边界')
        self.runtime_release, self.shared_runtime = runtime_release, shared_runtime
        self.local_runtime = local_runtime
        # 本机目标准备使用独立投影；中央权威环境行仅由迁移CAS切换。
        self.database_path = data / ('node-execution-local.sqlite' if node_key == 'local' else 'node-execution.sqlite')

    def database(self) -> sqlite3.Connection:
        """打开节点自己的执行投影库。:return: 由调用方关闭的连接。"""
        if self.database_path.is_symlink():
            raise ValueError('节点执行数据库不能为链接')
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _runtime(self, gateway, quota_identity=None):
        runtime = self.runtime_factory(self.client, self.data, self.host_data, self.database,
            derive_v3_fingerprint, gateway, quota_identity)
        expected_node = None if self.node_key == 'local' else self.node_key
        expected_network = self.local_runtime.network if self.local_runtime else node_network_name(self.deployment, self.node_key)
        if (getattr(runtime, 'node_key', None) != expected_node or getattr(runtime, 'deployment', None) != self.deployment
                or runtime.network != expected_network):
            self._release_runtime(runtime)
            raise ValueError('节点执行组件的部署、节点或网络配置不一致')
        if self.local_runtime:
            runtime.capacity_lock = self.local_runtime.capacity_lock
            runtime.lock = self.local_runtime.lock
            runtime.jobs = self.local_runtime.jobs
            runtime.environment_locks = self.local_runtime.environment_locks
        return runtime

    def _release_runtime(self, runtime) -> None:
        if self.runtime_release is not None:
            self.runtime_release(runtime)
        else:
            runtime.heartbeat_pool.shutdown(wait=True)

    def _check_execution_records(self, runtime, row: dict) -> None:
        root = runtime._root(row)
        paths = runtime._execution_records(row) if self.shared_runtime else list((root / 'runtime/executions').glob('*.json'))
        single = root / 'runtime/execution.json'
        if single.exists() or single.is_symlink():
            paths.append(single)
        if not paths:
            return
        if not self.shared_runtime:
            raise ValueError('节点环境存在需要先核对的执行记录')
        known = {runtime._execution_path(job): job for job in runtime.environment_jobs(row['environment_id'])}
        for path in paths:
            job = known.get(path)
            value = _read_json(path)
            if (job is None or not isinstance(value, dict) or value.get('source') != job['source']
                    or value.get('generation') != row['generation'] or job['row']['generation'] != row['generation']
                    or value.get('account_id') != job['account'].get('cc2api_account_id')
                    or value.get('container_id') != row.get('container_id')):
                raise ValueError('节点环境存在未登记或代次不匹配的执行记录')

    @contextmanager
    def _locked(self, *, read_only: bool = False, environment_id: str | None = None):
        if environment_id is not None and not re.fullmatch('[a-f0-9]{32}', environment_id):
            raise ValueError('节点环境操作锁身份无效')
        parent = self.data if environment_id is None else self.data / 'node-locks'
        name = '.node-preparation.lock' if environment_id is None else environment_id + '.lock'
        descriptor = directory_fd(parent, create=True)
        try:
            lock = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=descriptor)
        finally:
            os.close(descriptor)
        try:
            metadata = os.fstat(lock)
            if not S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077 or metadata.st_nlink != 1:
                raise ValueError('节点操作锁权限或类型无效')
            # 观察只尝试共享锁，环境列表不会等待安装或迁移；跨进程准备继续串行核对容量。
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB if read_only else fcntl.LOCK_EX)
            yield
        finally:
            os.close(lock)

    def prepare(self, request: NodePreparation) -> dict:
        """校验归属与投影后准备账号，返回仅供中央使用的传输绑定。

        :param request: 中央通过私有 SSH 通道发送的输入。
        :return: 实际环境、发送器地址及原生准备通知。
        """
        account_id, name, environment_id, remote_id = self._validate_preparation(request)
        with self._locked(environment_id=environment_id), self._locked():
            return self._prepare_locked(request, account_id, name, environment_id, remote_id)


    def _validate_preparation(self, request: NodePreparation, *, migration: bool = False) -> tuple[int, str, str, int | None]:
        account, environment = request.account, request.environment
        name, account_id = account.get('name'), account.get('id')
        environment_id = environment.get('environment_id')
        remote_id = account.get('cc2api_account_id')
        if (request.node_key != self.node_key or type(account_id) is not int or account_id <= 0
                or not isinstance(name, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,128}', name)
                or account.get('profile_path') != 'profiles/' + name
                or not (remote_id is None and request.cli_only or type(remote_id) is int and remote_id > 0)
                or remote_id is None and bool(request.gateway_config)
                or request.login_sid is not None and not request.cli_only
                or not isinstance(environment_id, str) or not re.fullmatch('[a-f0-9]{32}', environment_id)
                or environment.get('account_id') != account_id or environment.get('name') != name):
            raise ValueError('节点准备账号、环境或归属不一致')
        if set(request.profile_files) - {'.credentials.json', '.claude.json', 'settings.json'}:
            raise ValueError('节点 profile 文件超出允许范围')
        return account_id, name, environment_id, remote_id


    def inspect(self, request: NodeInspection) -> dict:
        """读取节点真实状态与私有资料的公开摘要，保持已有执行状态。

        :param request: 冻结的账号、环境和分配版本。
        :return: 无凭据的角色、身份、内核及观察投影。
        """
        with self._locked(read_only=True, environment_id=request.environment_id):
            if isinstance(request, NodeTransportInspection):
                return self._existing_transport(request)
            return self._inspect_locked(request)

    def _inspection_row(self, request: NodeLocation) -> dict:
        if request.node_key != self.node_key:
            raise ValueError('节点检查身份不一致')
        root = self.data / 'environments' / request.environment_id
        expected = {'protocol': 1, 'node_key': self.node_key, 'account_id': request.account_id,
            'environment_id': request.environment_id, 'revision': request.assignment_revision, 'phase': 'ready'}
        if _read_json(root / 'runtime/node-assignment.json') != expected:
            raise ValueError('节点环境归属与检查版本不一致')
        connection = self.database()
        try:
            stored = connection.execute('SELECT * FROM account_environments WHERE environment_id=? AND account_id=?',
                (request.environment_id, request.account_id)).fetchone()
            if stored is None:
                raise ValueError('节点环境尚未登记')
            return dict(stored)
        finally:
            connection.close()

    def _existing_transport(self, request: NodeTransportInspection) -> dict:
        """复核已运行绑定，维持原工作。@param request 内部固定范围。@return 私有发送器证明或空绑定。"""
        row = self._inspection_row(request)
        connection = self.database()
        try:
            account = connection.execute('SELECT cc2api_account_id FROM accounts WHERE id=? AND deleted_at IS NULL',
                (request.account_id,)).fetchone()
        finally:
            connection.close()
        gateway_id = request.transport_gateway_account
        if account is None or account['cc2api_account_id'] != gateway_id:
            raise ValueError('节点已有发送器与网关账号不一致')
        runtime = self._runtime(_GatewaySnapshot(gateway_id, {}, bench_account_id=request.account_id))
        scope = {'protocol': 1, 'node_key': self.node_key, 'assignment_revision': request.assignment_revision}
        try:
            runtime._check_node_fence(row)
            if request.verify_stopped and row['state'] == 'stopped':
                from cluster_owner_node import _idle, _stopped

                # 中央的停止标记可能滞后，回切需要在原节点锁内确认实际角色和执行记录。
                _idle(self, runtime, row)
                _stopped(runtime, row)
                return {**scope, 'binding': None, 'stopped': {
                    'account_id': gateway_id, 'environment_id': row['environment_id'],
                    'generation': row['generation'], 'release_id': role_release(runtime, row)}}
            if row['state'] not in ('ready', 'cli_reconcile'):
                return {**scope, 'binding': None}
            for role in ('network', 'sender'):
                container = role_container(runtime, row, role, allow_old_release=True)
                container.reload()
                if container.status != 'running':
                    return {**scope, 'binding': None}
            binding = _read_json(runtime._sender_config(row))['binding']
            if (binding.get('account_id') != gateway_id or binding.get('environment_id') != request.environment_id
                    or binding.get('generation') != row['generation'] or binding.get('release_id') != role_release(runtime, row)):
                raise ValueError('节点已有发送器归属或代次不一致')
            network = role_container(runtime, row, 'network', allow_old_release=True)
            address = str(ipaddress.ip_address(network.attrs['NetworkSettings']['Networks'][runtime.network]['IPAddress']))
            return {**scope, 'binding': binding, 'sender_address': address}
        finally:
            self._release_runtime(runtime)

    def _inspect_locked(self, request: NodeInspection) -> dict:
        row=self._inspection_row(request)
        root=self.data/'environments'/request.environment_id
        runtime = self._runtime(_GatewaySnapshot(0, {}))
        try:
            # 执行记录来自节点落盘；跨进程内存中的空 jobs 不代表环境空闲。
            busy = (root / 'runtime/execution.json').exists() or any((root / 'runtime/executions').glob('*.json'))
            try:
                identity = runtime.read_cli_identity(row, request.version)
                identity_status = '已确认 CLI 本地设备身份' if ':config.userID' in identity['source'] else '已观测 CLI 设备身份'
            except ValueError:
                identity_status = '节点 CLI 身份待核对'
            try:
                kernel = native_kernel_status(runtime, row)
            except (OSError, ValueError, TypeError):
                kernel = None
            connection = self.database()
            try:
                account = connection.execute('SELECT cc2api_account_id FROM accounts WHERE id=?', (row['account_id'],)).fetchone()
            finally:
                connection.close()
            binding = account['cc2api_account_id'] if account else None
            settings = {'content_capture': None, 'criu': None}
            if binding is not None:
                current = {**row, 'gateway_account_id': binding}
                for key, reader in (('content_capture', read_capture_settings), ('criu', read_criu_settings)):
                    try:
                        settings[key] = reader(runtime, current, request.observation)
                    except (OSError, ValueError, TypeError, DockerException):
                        # 缺失或损坏的配置保持未知，环境其余实际观察仍可读取。
                        pass
            return {'protocol': 1, 'node_key': self.node_key, 'assignment_revision': request.assignment_revision,
                'environment_id': row['environment_id'], 'account_id': row['account_id'], 'generation': row['generation'],
                'role_status': runtime.role_status(row), 'state': row['state'], 'busy': bool(busy),
                'identity_status': identity_status, 'native_kernels': {'2.1.293': kernel}, 'native_kernel': kernel,
                'physical_features': physical_features_summary(row, root / 'runtime/physical-features.json', time.time()),
                'runtime_release': role_release(runtime, row), 'gateway_account_id': binding, **settings,
                'cli_versions': sorted(path.parent.name for path in (root / 'cli').glob('*/.ready'))}
        finally:
            self._release_runtime(runtime)

    def review_admission(self, request: NodeReviewAdmission) -> dict:
        """在原节点核对私有评审资源、孤儿和原所有者刷新待办。

        :param request: 原账号环境、分配及本次额度身份。
        :return: 无私有材料的实际准入结果及来源身份。
        """
        with self._locked(read_only=True,environment_id=request.environment_id):
            row=self._inspection_row(request)
            connection=self.database()
            try:
                account=connection.execute('SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL',
                    (request.account_id,)).fetchone()
                if account is None:
                    raise ValueError('节点私有评审账号已变化')
                account=dict(account)
            finally:
                connection.close()
            runtime=self._runtime(_GatewaySnapshot(0,{}))
            try:
                admission=runtime.reviews.admission(account,identity=request.quota_identity)
                result={'protocol':1,'node_key':self.node_key,'account_id':request.account_id,
                    'environment_id':request.environment_id,'assignment_revision':request.assignment_revision,
                    'generation':row['generation'],'admission':admission}
                if request.include_refresh:
                    state=runtime.reviews.owner_refresh_state(account,identity=request.quota_identity)
                    keys=('account_id','environment_id','environment_generation','identity','request_id','run_id',
                        'source','status','attempts','not_before')
                    result['owner_refresh']={key:state[key] for key in keys} if state is not None else None
                return result
            finally:
                self._release_runtime(runtime)

    def fence(self, request: EnvironmentFence) -> dict:
        """按中央已排空范围隔离源环境，拒绝未收口工作。

        :param request: 原账号、节点、环境、分配版本和代次。
        :return: 真实Docker停止及持久隔离收据。
        """
        if request.node_key != self.node_key:
            raise ValueError('源隔离节点身份不一致')
        with self._locked(environment_id=request.environment_id):
            if pending_run_programs(self.data,request.environment_id):
                raise ValueError('节点环境仍有未收口独立程序，等待原验收停止')
            connection = self.database()
            try:
                stored = connection.execute('SELECT * FROM account_environments WHERE environment_id=? AND account_id=?',
                    (request.environment_id, request.account_id)).fetchone()
                if stored is None:
                    raise ValueError('源隔离环境尚未登记')
                row = dict(stored)
            finally:
                connection.close()
            runtime = self._runtime(_GatewaySnapshot(0, {}))
            try:
                return fence_environment(runtime, row, request)
            finally:
                self._release_runtime(runtime)

    def export(self, request: ArchiveExport) -> dict:
        """在原环境私有锁内核对已停止源并生成持久归档。

        :param request: 原源身份与独立导出尝试。
        :return: 节点及冻结包描述，归档内容保留在源节点私有目录。
        """
        if request.node_key != self.node_key:
            raise ValueError('归档源节点身份不一致')
        with self._locked(environment_id=request.environment_id):
            if pending_run_programs(self.data,request.environment_id):
                raise ValueError('节点环境仍有未收口独立程序，等待原验收停止')
            connection = self.database()
            try:
                stored = connection.execute('SELECT * FROM account_environments WHERE environment_id=? AND account_id=?',
                    (request.environment_id, request.account_id)).fetchone()
                if stored is None:
                    raise ValueError('导出源环境尚未登记')
                row = dict(stored)
            finally:
                connection.close()
            runtime = self._runtime(_GatewaySnapshot(0, {}))
            try:
                fence_environment(runtime, row, EnvironmentFence.model_validate(request.model_dump(exclude={'attempt_id', 'version'})))
                cli_identity = runtime.read_cli_identity(row, request.version)
                identity = ArchiveIdentity(operation_id=request.operation_id, deployment_id=self.deployment,
                    source_node_key=self.node_key, account_id=request.account_id, environment_id=request.environment_id,
                    assignment_revision=request.assignment_revision)
                archive = MigrationFiles(self.data, self.node_key, self.deployment).export(runtime._root(row), identity,
                    request.attempt_id, cli_version=request.version, cli_identity=cli_identity, environment_generation=row['generation'])
                return {'protocol': 1, 'node_key': self.node_key, 'archive': archive.model_dump()}
            finally:
                self._release_runtime(runtime)

    def restore_source(self, request: EnvironmentFence) -> dict:
        """撤销原源隔离，中央在目标撤销和源收据齐全后恢复准入。

        :param request: 原操作的精确源范围。
        :return: 原代次源恢复收据。
        """
        if request.node_key != self.node_key:
            raise ValueError('源恢复节点身份不一致')
        with self._locked(environment_id=request.environment_id):
            connection = self.database()
            try:
                stored = connection.execute('SELECT * FROM account_environments WHERE account_id=? AND environment_id=?',
                    (request.account_id, request.environment_id)).fetchone()
                if stored is None:
                    raise ValueError('源恢复环境尚未登记')
                row = dict(stored)
            finally:
                connection.close()
            runtime = self._runtime(_GatewaySnapshot(0, {}))
            try:
                return restore_fenced_source(runtime, row, request)
            finally:
                self._release_runtime(runtime)

    def revoke_import(self, request: ImportRevocation) -> dict:
        """持久撤销该操作的目标副本并核对已发布角色停止。

        :param request: 原目标暂存范围，即使上传尚未开始也按同一操作保留墓碑。
        :return: 目标停止和迟到命令撤销收据。
        """
        if request.node_key != self.node_key or request.target_revision != request.identity.assignment_revision + 1:
            raise ValueError('目标撤销节点或分配版本不一致')
        identity = request.identity
        if isinstance(identity, AgyArchiveIdentity):
            raise ValueError('AGY 撤销必须使用平台专用操作')
        with self._locked(environment_id=identity.environment_id):
            files = MigrationFiles(self.data, self.node_key, self.deployment)
            operation = files._operation(identity, 'import')
            tombstone = operation / 'revoked.json'
            receipt = {'protocol': 1, 'operation_id': identity.operation_id, 'node_key': self.node_key,
                'account_id': identity.account_id, 'environment_id': identity.environment_id,
                'revision': request.target_revision, 'phase': 'revoked'}
            if tombstone.exists() or tombstone.is_symlink():
                if _read_json(tombstone) != receipt:
                    raise ValueError('目标撤销收据范围不一致')
            root = self.data / 'environments' / identity.environment_id
            if root.exists() or root.is_symlink():
                marker_path = root / 'runtime/node-migration-target.json'
                try:
                    marker = _read_json(marker_path)
                except FileNotFoundError:
                    marker = None
                expected = {'operation_id': identity.operation_id, 'node_key': self.node_key,
                    'account_id': identity.account_id, 'environment_id': identity.environment_id,
                    'revision': request.target_revision}
                if (not isinstance(marker, dict) or any(marker.get(key) != value for key, value in expected.items())
                        or marker.get('phase') not in ('published', 'prepared', 'revoked')):
                    # 原停止副本可在本次尚未发布时取消，只核对旧fence及实际角色，保留原资料。
                    self._previous_copy(root, expected)
                    atomic_json(tombstone, receipt)
                    return receipt
                connection = self.database()
                try:
                    stored = connection.execute('SELECT * FROM account_environments WHERE environment_id=? AND account_id=?',
                        (identity.environment_id, identity.account_id)).fetchone()
                finally:
                    connection.close()
                if stored is None:
                    if self._scoped_containers(identity.environment_id):
                        raise ValueError('目标存在缺少实际代次记录的角色，请先对账')
                else:
                    row = dict(stored)
                    runtime = self._runtime(_GatewaySnapshot(0, {}))
                    try:
                        fence_environment(runtime, row, EnvironmentFence(operation_id=identity.operation_id,
                            node_key=self.node_key, account_id=identity.account_id, environment_id=identity.environment_id,
                            assignment_revision=request.target_revision, generation=row['generation']))
                    finally:
                        self._release_runtime(runtime)
                atomic_json(marker_path, {**marker, 'phase': 'revoked'})
            elif self._scoped_containers(identity.environment_id):
                raise ValueError('目标存在缺少运行目录的实际角色，请先对账')
            atomic_json(tombstone, receipt)
            return receipt

    def stage_import(self, request: ImportStage) -> dict:
        """建立目标节点单环境的私有上传暂存区。

        :param request: 目标分配与源包描述。
        :return: 固定操作和上传尝试的接纳回执。
        """
        with self._locked(environment_id=request.archive.identity.environment_id):
            return MigrationFiles(self.data, self.node_key, self.deployment).stage(request)

    def verify_import(self, request: ImportStage) -> dict:
        """在目标私有树核验包，保持当前业务环境尚未发布。

        :param request: 原已接纳的上传尝试。
        :return: 逐文件身份、权限与摘要核验回执。
        """
        with self._locked(environment_id=request.archive.identity.environment_id):
            return MigrationFiles(self.data, self.node_key, self.deployment).restore(request)

    def prepare_import(self, request: ImportPreparation) -> dict:
        """将已核对私有树发布为目标环境并准备角色，中央继续保持维护。

        :param request: 原暂存范围与当前中央有限投影。
        :return: 私有目标环境和发送器绑定，归属切换由中央CAS提交。
        """
        stage, preparation = request.stage, request.preparation
        if isinstance(stage.archive.identity, AgyArchiveIdentity):
            raise ValueError('AGY 归档必须使用平台专用准备操作')
        if request.profile_references:
            if preparation.profile_files or set(request.profile_references) - set(PROFILE_NAMES):
                raise ValueError('迁移profile引用范围无效')
            path = self.data / 'node-migrations' / stage.archive.identity.operation_id / 'imports' / stage.transfer_id
            profiles = {name: read_profile(path / ('profile-' + ref.sha256 + '.json'), ref)
                for name, ref in request.profile_references.items()}
            preparation = preparation.model_copy(update={'profile_files': profiles})
        account_id, name, environment_id, remote_id = self._validate_preparation(preparation, migration=True)
        archive = stage.archive
        if (stage.node_key != self.node_key or preparation.node_key != self.node_key
                or preparation.assignment_revision != stage.target_revision
                or account_id != archive.identity.account_id or environment_id != archive.identity.environment_id
                or archive.cli_identity is None or archive.cli_version is None or archive.environment_generation is None
                or preparation.environment.get('generation') != archive.environment_generation
                or preparation.environment.get('state') not in ('ready', 'stopped')):
            raise ValueError('目标发布与源账号、分配、身份或代次不一致')
        with self._locked(environment_id=environment_id):
            files = MigrationFiles(self.data, self.node_key, self.deployment)
            if not files.stage(stage)['uploaded']:
                raise ValueError('目标发布前迁移包尚未上传完成')
            path = self.data / 'node-migrations' / archive.identity.operation_id / 'imports' / stage.transfer_id
            verified = _read_json(path / 'verified.json')
            if (verified.get('phase') != 'verified' or verified.get('sha256') != archive.sha256
                    or verified.get('operation_id') != archive.identity.operation_id
                    or verified.get('transfer_id') != stage.transfer_id or verified.get('node_key') != self.node_key):
                raise ValueError('目标发布缺少原暂存资料的核验回执')
            intent = {'protocol': 1, 'operation_id': archive.identity.operation_id, 'transfer_id': stage.transfer_id,
                'node_key': self.node_key, 'account_id': account_id, 'environment_id': environment_id,
                'revision': stage.target_revision, 'archive_sha256': archive.sha256,
                'source_generation': archive.environment_generation, 'source_state': preparation.environment['state'],
                'cli_version': archive.cli_version, 'cli_identity': archive.cli_identity.model_dump()}
            intent_path = path / 'publish-intent.json'
            if intent_path.exists() or intent_path.is_symlink():
                if _read_json(intent_path) != intent:
                    raise ValueError('目标发布意图的冻结范围已变化')
            root = self.data / 'environments' / environment_id
            marker = root / 'runtime/node-migration-target.json'
            exists = root.exists() or root.is_symlink()
            published = False
            if exists:
                try:
                    value = _read_json(marker)
                except FileNotFoundError:
                    value = None
                published = (isinstance(value, dict) and all(value.get(key) == item for key, item in intent.items())
                    and value.get('phase') in ('published', 'prepared'))
            if not published:
                # 源身份在私有树中先按同一版本合同复核，发布前不接触账号运行目录。
                profile = path / 'profile'
                descriptor = directory_fd(profile, create=True)
                os.close(descriptor)
                if '.claude.json' not in preparation.profile_files:
                    raise ValueError('目标发布缺少当前账号profile身份')
                atomic_json(profile / '.claude.json', json.loads(preparation.profile_files['.claude.json']))
                actual_identity = MigrationCliIdentity.model_validate(read_cli_identity_at(path / 'environment', profile, archive.cli_version))
                if actual_identity != archive.cli_identity:
                    raise ValueError('目标暂存的CLI设备或登录账号与源收据不一致')
                atomic_json(intent_path, intent)
                if exists:
                    self._retire_previous(root, path, intent)
                atomic_json(path / 'environment/runtime/node-migration-target.json', {**intent, 'phase': 'published'})
                atomic_json(path / 'environment/runtime/node-assignment.json', {'protocol': 1, 'node_key': self.node_key,
                    'account_id': account_id, 'environment_id': environment_id, 'revision': stage.target_revision, 'phase': 'ready'})
                source_parent = directory_fd(path)
                target_parent = directory_fd(root.parent, create=True)
                try:
                    os.rename('environment', environment_id, src_dir_fd=source_parent, dst_dir_fd=target_parent)
                    os.fsync(source_parent)
                    os.fsync(target_parent)
                finally:
                    os.close(source_parent)
                    os.close(target_parent)
            environment = {**preparation.environment, 'state': 'stopped', 'container_id': None,
                'network_container_id': None, 'sender_container_id': None, 'isolation_version': 2}
            prepared = preparation.model_copy(update={'environment': environment})
            self._prepare_import_projection(prepared, path, intent)
            with self._locked():
                peer = self._prepare_locked(prepared, account_id, name, environment_id, remote_id, import_intent=intent)
            row = peer['environment']
            actual_identity = MigrationCliIdentity.model_validate(read_cli_identity_at(root, self.data / 'profiles' / name, archive.cli_version))
            if actual_identity != archive.cli_identity:
                raise ValueError('目标准备后的CLI身份与源回执不一致')
            public = {**intent, 'phase': 'prepared', 'generation': row['generation']}
            atomic_json(marker, public)
            # sender秘密只保留在原运行目录，迁移回执只登记实际环境和版本。
            atomic_json(path / 'published.json', {**public, 'environment': row})
            return {**peer, 'operation_id': archive.identity.operation_id, 'transfer_id': stage.transfer_id, 'phase': 'prepared'}

    def _previous_copy(self, root: Path, intent: dict) -> tuple[dict, list]:
        try:
            fence = _read_json(root / 'runtime/node-fence.json')
        except FileNotFoundError:
            raise ValueError('目标环境包含其他操作资料，请先核对原隔离回执') from None
        if (not isinstance(fence, dict) or fence.get('protocol') != 1 or fence.get('phase') != 'fenced'
                or fence.get('node_key') != self.node_key or fence.get('environment_id') != intent['environment_id']
                or fence.get('account_id') != intent['account_id'] or fence.get('operation_id') == intent['operation_id']
                or not isinstance(fence.get('operation_id'), str) or not re.fullmatch('[a-f0-9]{32}', fence['operation_id'])
                or type(fence.get('assignment_revision')) is not int
                or not 1 <= fence['assignment_revision'] <= intent['revision']
                or type(fence.get('generation')) is not int or fence['generation'] < 0
                or not isinstance(fence.get('stopped_containers'), list)
                or any(not isinstance(value, str) for value in fence['stopped_containers'])):
            raise ValueError('目标已有副本缺少原已停止隔离证明')
        if fence['assignment_revision'] == intent['revision']:
            # 中央提交前撤销保留原分配版本。同版本目标须证明旧操作已经撤销。
            tombstone = self.data / 'node-migrations' / fence['operation_id'] / 'revoked.json'
            expected = {key: intent[key] for key in ('node_key', 'account_id', 'environment_id', 'revision')}
            try:
                revoked = _read_json(tombstone)
            except FileNotFoundError:
                revoked = None
            if revoked != {'protocol': 1, **expected, 'operation_id': fence['operation_id'], 'phase': 'revoked'}:
                raise ValueError('目标同版本副本缺少匹配的原撤销收据')
        if self.node_key != 'local':
            ownership = _read_json(root / 'runtime/node-assignment.json')
            if ownership != {'protocol': 1, 'node_key': self.node_key, 'account_id': intent['account_id'],
                    'environment_id': intent['environment_id'], 'revision': fence['assignment_revision'],
                    'phase': 'fenced', 'operation_id': fence['operation_id']}:
                raise ValueError('目标旧副本的分配与原隔离操作不一致')
        labels = {'vibebench.product': 'v3', 'vibebench.deployment': self.deployment,
            'vibebench.environment': intent['environment_id']}
        containers = self._scoped_containers(intent['environment_id'])
        actual = {item.id for item in containers}
        saved = set(fence['stopped_containers'])
        if (len(saved) != len(fence['stopped_containers']) or not actual <= saved):
            raise ValueError('目标旧副本的实际角色与原隔离回执不一致')
        for container in containers:
            container.reload()
            state = container.attrs.get('State', {})
            if (any(container.labels.get(key) != value for key, value in labels.items())
                    or container.labels.get('vibebench.role') not in ('account', 'account-sender', 'account-network')
                    or container.status not in ('exited', 'dead', 'created') or state.get('Running') is not False or state.get('Pid') != 0):
                raise ValueError('目标旧副本仍有未核对角色，请先收口')
        return fence, containers

    def _scoped_containers(self, environment_id: str) -> list:
        labels = {'vibebench.product': 'v3', 'vibebench.deployment': self.deployment,
            'vibebench.environment': environment_id}
        containers = self.client.containers.list(all=True, filters={'label': [key + '=' + value for key, value in labels.items()]})
        node = None if self.node_key == 'local' else self.node_key
        return [item for item in containers if item.labels.get('vibebench.cluster-node') == node]

    def _retire_previous(self, root: Path, path: Path, intent: dict) -> None:
        fence, containers = self._previous_copy(root, intent)
        retirement = {'protocol': 1, 'operation_id': intent['operation_id'], 'node_key': self.node_key,
            'environment_id': intent['environment_id'], 'previous_fence': fence}
        marker = path / 'retirement.json'
        retry = marker.exists() or marker.is_symlink()
        if retry and _read_json(marker) != retirement:
            raise ValueError('旧副本保留操作的冻结范围已变化')
        if not retry and {item.id for item in containers} != set(fence['stopped_containers']):
            raise ValueError('目标旧副本的实际角色与原隔离回执不一致')
        previous = path / 'previous-environment'
        if previous.exists() or previous.is_symlink():
            raise ValueError('本次操作已有旧副本保留资料，请核对目录移动结果')
        # 先保留停止收据和意图；部分角色移除后仍可按原精确集合继续，旧HOME始终保留。
        atomic_json(marker, retirement)
        for container in containers:
            container.remove()
        original_parent = directory_fd(root.parent)
        private_parent = directory_fd(path)
        try:
            os.rename(root.name, 'previous-environment', src_dir_fd=original_parent, dst_dir_fd=private_parent)
            os.fsync(original_parent)
            os.fsync(private_parent)
        finally:
            os.close(original_parent)
            os.close(private_parent)

    def _prepare_import_projection(self, request: NodePreparation, path: Path, intent: dict) -> None:
        marker = path / 'projection.json'
        expected = {'protocol': 1, 'operation_id': intent['operation_id'], 'node_key': self.node_key,
            'environment_id': intent['environment_id'], 'source_generation': intent['source_generation']}
        if marker.exists() or marker.is_symlink():
            if _read_json(marker) != expected:
                raise ValueError('目标执行投影的冻结范围已变化')
            return
        connection = self.database()
        try:
            apply_migrations(connection)
            with connection:
                old = connection.execute('SELECT * FROM account_environments WHERE environment_id=?',
                    (intent['environment_id'],)).fetchone()
                retirement = _read_json(path / 'retirement.json') if (path / 'retirement.json').exists() else None
                previous_generation = retirement['previous_fence']['generation'] if retirement else 0
                if old and (old['account_id'] != intent['account_id'] or old['name'] != request.account['name']
                        or retirement and old['generation'] != previous_generation
                        or not retirement and any(old[column] for column in ('container_id', 'network_container_id', 'sender_container_id'))):
                    raise ValueError('目标原执行投影身份或代次与新导入不一致')
                if old and not retirement and old['generation'] > intent['source_generation']:
                    raise ValueError('目标存在缺少原隔离证明的较新执行投影')
                # 取消后的目标可能已有更高代次；以两端已停止证明的较大值继续，避免重用旧代次。
                generation = max(intent['source_generation'], previous_generation, old['generation'] if old else 0)
                self._project_row(connection, 'accounts', request.account, update=True)
                self._project_row(connection, 'account_environments', {**request.environment, 'generation': generation}, update=True)
        finally:
            connection.close()
        # 角色准备只发生在投影收据之后；重试已准备操作时不能回写源代次。
        atomic_json(marker, expected)

    def activate_import(self, request: ImportActivation) -> dict:
        """按中央已提交范围核对目标实际角色，保存可开放准入的激活回执。

        :param request: 中央CAS后冻结的节点、分配和目标代次。
        :return: 无发送器秘密的激活证明，原停止环境继续保持停止。
        """
        if request.node_key != self.node_key:
            raise ValueError('目标激活节点身份不一致')
        with self._locked(environment_id=request.environment_id):
            path = self.data / 'node-migrations' / request.operation_id / 'imports' / request.transfer_id
            if (path.parent.parent / 'revoked.json').exists() or (path.parent.parent / 'revoked.json').is_symlink():
                raise ValueError('目标操作已撤销，拒绝迟到激活')
            published = _read_json(path / 'published.json')
            expected = {key: getattr(request, key) for key in ('operation_id', 'transfer_id', 'node_key', 'account_id',
                'environment_id', 'revision', 'generation')}
            if not isinstance(published, dict) or any(published.get(key) != value for key, value in expected.items()):
                raise ValueError('目标激活与原发布范围不一致')
            root = self.data / 'environments' / request.environment_id
            marker = _read_json(root / 'runtime/node-migration-target.json')
            if (not isinstance(marker, dict) or marker.get('phase') not in ('prepared', 'activated')
                    or any(marker.get(key) != value for key, value in expected.items())):
                raise ValueError('目标激活与运行目录身份不一致')
            connection = self.database()
            try:
                stored = connection.execute('SELECT * FROM account_environments WHERE environment_id=? AND account_id=?',
                    (request.environment_id, request.account_id)).fetchone()
                if stored is None or stored['generation'] != request.generation:
                    raise ValueError('目标实际环境代次已变化')
                row = dict(stored)
            finally:
                connection.close()
            runtime = self._runtime(_GatewaySnapshot(0, {}))
            try:
                identity = MigrationCliIdentity.model_validate(runtime.read_cli_identity(row, published['cli_version']))
                if identity.model_dump() != published['cli_identity']:
                    raise ValueError('目标实际CLI身份与发布记录不一致')
                if runtime.environment_jobs(row['environment_id']) or runtime._execution_records(row):
                    raise ValueError('目标激活前存在未核对执行记录')
                if row['state'] not in ('ready', 'stopped'):
                    raise ValueError('目标运行状态仍需核对')
                if published['source_state'] == 'stopped':
                    if runtime._running_sender_active(row):
                        raise ValueError('目标仍有发送活动，停止结果需要核对')
                    runtime._stop_environment(row)
                    runtime._update(row, state='stopped')
                    roles = runtime.role_status(row)
                    if any(roles.get(role) not in ('exited', 'dead', 'created') for role in ('cli', 'sender', 'network')):
                        raise ValueError('目标原停止状态尚未恢复')
                    for role in ('cli', 'sender', 'network'):
                        container = role_container(runtime, row, role)
                        container.reload()
                        if container.attrs.get('State', {}).get('Pid') != 0 or container.attrs.get('State', {}).get('Running') is not False:
                            raise ValueError('目标实际角色停止证据不一致')
                else:
                    roles = runtime.role_status(row)
                    if any(roles.get(role) != 'running' for role in ('cli', 'sender', 'network')):
                        raise ValueError('目标实际运行角色尚未就绪')
                receipt = {'protocol': 1, **expected, 'phase': 'activated'}
                atomic_json(root / 'runtime/node-migration-target.json', {**marker, 'phase': 'activated'})
                atomic_json(path / 'activated.json', receipt)
                return receipt
            finally:
                self._release_runtime(runtime)

    def _prepare_locked(self, request: NodePreparation, account_id: int, name: str,
                        environment_id: str, remote_id: int | None, *, import_intent: dict | None = None) -> dict:
        root = self.data / 'environments' / environment_id
        validate_owner_preparation(root,request)
        ownership_path = root / 'runtime/node-assignment.json'
        ownership = {'protocol': 1, 'node_key': self.node_key, 'account_id': account_id,
            'environment_id': environment_id, 'revision': request.assignment_revision, 'phase': 'ready'}
        fence = root / 'runtime/node-fence.json'
        if fence.exists() or fence.is_symlink():
            value = _read_json(fence)
            if not isinstance(value, dict) or value.get('phase') != 'cancelled':
                raise ValueError('源环境正在隔离，请核对原迁移操作')
        if ownership_path.exists() or ownership_path.is_symlink():
            if _read_json(ownership_path) != ownership:
                raise ValueError('节点环境分配版本或维护阶段不一致')
        elif root.exists() and any(root.iterdir()):
            raise ValueError('节点存在未核对归属的环境资料')
        atomic_json(ownership_path, ownership)
        connection = self.database()
        try:
            apply_migrations(connection)
            with connection:
                self._project_row(connection, 'accounts', request.account, update=True)
                existing = connection.execute('SELECT account_id,name FROM account_environments WHERE environment_id=?',
                    (environment_id,)).fetchone()
                if existing and (existing['account_id'], existing['name']) != (account_id, name):
                    raise ValueError('节点执行投影存在冲突身份')
                if not existing:
                    self._project_row(connection, 'account_environments', request.environment, update=False)
        finally:
            connection.close()
        for filename, content in request.profile_files.items():
            value = json.loads(content)
            if not isinstance(value, dict):
                raise ValueError('节点 profile 必须是 JSON 对象')
            if self.local_runtime:
                # 管理profile保留唯一刷新权；本机准备只消费同账号已有文件。
                current = _read_json(self.data / 'profiles' / name / filename)
                if not isinstance(current, dict):
                    raise ValueError('本机目标管理profile格式无效')
                if filename == '.credentials.json':
                    oauth = current.get('claudeAiOauth')
                    if isinstance(oauth, dict):
                        oauth.pop('refreshToken', None)
                if current != value:
                    raise ValueError('本机目标准备期间管理profile已变化')
                continue
            if filename == '.credentials.json' and remote_id is not None:
                value = json.loads(json.dumps(value))
                oauth = value.get('claudeAiOauth')
                if isinstance(oauth, dict):
                    oauth.pop('refreshToken', None)
            atomic_json(self.data / 'profiles' / name / filename, value)
        gateway = _GatewaySnapshot(remote_id or 0, request.gateway_config, bench_account_id=account_id)
        runtime = self._runtime(gateway, lambda account: request.quota_identity)
        try:
            # 活动 CLI 需要持久协调；准备入口不能把跨进程丢失的 jobs 当作空闲。
            row = runtime._row(name, account_id)
            self._check_execution_records(runtime, row)
            if import_intent is not None and row['state'] == 'reconcile':
                marker = _read_json(root / 'runtime/node-migration-target.json')
                if marker.get('phase') != 'published' or any(marker.get(key) != value for key, value in import_intent.items()):
                    raise ValueError('目标恢复缺少原迁移发布证明')
                roles = {row[column]: role for role, column in ROLE_COLUMNS.items() if row.get(column)}
                for container in self._scoped_containers(environment_id):
                    container.reload()
                    state = container.attrs.get('State', {})
                    role = roles.get(container.id)
                    if (role is None or container.labels.get('vibebench.role') != ROLE_LABELS[role]
                            or state.get('Running') is not False or state.get('Pid') != 0):
                        raise ValueError('目标原准备仍有实际角色或未知归属，请先核对')
                if runtime.environment_jobs(environment_id):
                    raise ValueError('目标原准备仍有实际作业，请先核对')
                # 仅收口本次尚未提交的已停止失败角色，保留HOME、身份及原迁移游标。
                runtime._stop_environment(row, remove=True)
                runtime._update(row, state='stopped')
            if request.cli_only:
                if request.login_sid is not None:
                    runtime.ensure(request.account,prepare_sender=False,allow_inactive_login=True,
                        ownership_source='login:'+request.login_sid)
                else:
                    runtime.ensure(request.account, prepare_sender=False)
                binding = None
            else:
                options = {'prepare_tui': True} if request.gateway_config.get('_prepare_tui') is True else {}
                binding = runtime.transport(request.account, '', **options)
            connection = self.database()
            try:
                row = dict(connection.execute('SELECT * FROM account_environments WHERE environment_id=?',
                    (environment_id,)).fetchone())
            finally:
                connection.close()
            if remote_id is None and request.cli_only and request.login_sid is None:
                # 普通独立CLI首次准备即沿原发布器建立HOME；已有完整HOME仍由其当前RT作主。
                runtime.sync_credentials(row,request.account)
            network = self.client.containers.get(row['network_container_id'])
            network.reload()
            address = network.attrs['NetworkSettings']['Networks'][runtime.network]['IPAddress']
            ipaddress.ip_address(address)
            return {'protocol': 1, 'node_key': self.node_key, 'assignment_revision': request.assignment_revision,
                'environment': row, 'binding': binding, 'sender_address': address,
                'native_notifications': sorted(gateway.notifications)}
        finally:
            self._release_runtime(runtime)

    def _project_row(self, connection: sqlite3.Connection, table: str, values: dict, *, update: bool) -> None:
        if table not in ('accounts', 'account_environments'):
            raise ValueError('节点投影表无效')
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(' + table + ')')}
        if not values or set(values) - columns:
            raise ValueError('节点投影字段与执行镜像版本不一致')
        names = list(values)
        identity = 'id' if table == 'accounts' else 'environment_id'
        suffix = (' ON CONFLICT(' + identity + ') DO UPDATE SET '
            + ','.join(name + '=excluded.' + name for name in names if name != identity)) if update else ''
        connection.execute('INSERT INTO ' + table + '(' + ','.join(names) + ') VALUES('
            + ','.join('?' for _ in names) + ')' + suffix, tuple(values[name] for name in names))


def execute_operation(executor: NodeExecution, operation: str, raw: bytes) -> dict:
    """由临时入口和持久服务共用固定环境操作分派。

    :param executor: 原安装归属的执行器。
    :param operation: 精确私有操作名称。
    :param raw: 有界JSON输入。
    :return: 原操作的私有结果。
    """
    operations = {'prepare': (NodePreparation, executor.prepare), 'inspect': (NodeInspection, executor.inspect),
        'review-admission': (NodeReviewAdmission,executor.review_admission),
        'fence': (EnvironmentFence, executor.fence), 'export': (ArchiveExport, executor.export),
        'stage-import': (ImportStage, executor.stage_import), 'verify-import': (ImportStage, executor.verify_import),
        'prepare-import': (ImportPreparation, executor.prepare_import),
        'activate-import': (ImportActivation, executor.activate_import),
        'restore-source': (EnvironmentFence, executor.restore_source),
        'revoke-import': (ImportRevocation, executor.revoke_import)}
    if operation not in operations:
        raise ValueError('节点执行操作无效')
    request_type, action = operations[operation]
    payload = strict_json(raw, 2 * 1024 * 1024)
    if operation == 'inspect' and isinstance(payload, dict) and 'transport_gateway_account' in payload:
        # 回执校验按原模型字段全集比对，V2 查询使用独立输入以保留原凭据协议。
        request_type = NodeTransportInspection
    return action(request_type.model_validate(payload))


def main() -> None:
    """从 docker exec 标准输入读取一次私有准备请求。:return: None。"""
    client = None
    try:
        raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('节点准备请求过大')
        operation = sys.argv[1] if len(sys.argv) == 2 else 'prepare' if len(sys.argv) == 1 else ''
        if os.environ.get('V3_ROLE') == 'node-control':
            # SSH每次exec只接入原长驻进程；服务失联不能另建丢失jobs的临时运行时。
            from cluster_agent_client import node_agent_request
            result = node_agent_request(Path(os.environ['BENCH_DATA']), os.environ['V3_INTERNAL_TOKEN'], operation, raw)
        else:
            data = Path(os.environ['BENCH_DATA'])
            client = DockerClient.from_env()
            executor = NodeExecution(data, Path(os.environ['HOST_BENCH_DATA']), os.environ['V3_NODE_KEY'],
                os.environ['V3_DEPLOYMENT_ID'], client)
            result = {'ok': True, 'result': execute_operation(executor, operation, raw)}
    except Exception as error:
        # 进程边界不打印 profile、代理、令牌、私钥或异常原文。
        result = {'ok': False, 'reason': 'node_preparation_failed', 'error_type': type(error).__name__}
    finally:
        if client is not None:
            client.close()
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
