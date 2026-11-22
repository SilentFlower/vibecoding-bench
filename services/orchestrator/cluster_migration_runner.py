"""中央人工迁移协调器，按持久阶段执行停机、发布、切换与恢复。"""
from __future__ import annotations

import ipaddress
import hashlib
import json
import uuid
import threading

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from account_update_identity import configured_release
from cluster_archive import AgyArchiveIdentity, ArchiveIdentity
from cluster_environment import EnvironmentFence
from cluster_execution import ImportActivation, ImportPreparation, ImportRevocation, NodeInspection
from cluster_deployment import node_container_name
from cluster_migration_files import ArchiveDescriptor, ArchiveExport, ImportStage
from cluster_migration_io import MigrationIO, MigrationUploadIncomplete
from cluster_migration_lease import IndependentMigrationPermit, MigrationLease
from cluster_migrations import NodeMigrations
from cluster_migration_errors import migration_failure
from cluster_migration_profiles import MigrationProfiles
from system_profile import validate_computer_profile, validate_system_profile


class MigrationStart(BaseModel):
    """管理员冻结的迁移目标与原分配版本。

    :param operation_id: 可幂等重试的独立迁移操作。
    :param node_id: 人工选择的目标。
    :param revision: 原分配版本。
    :param version: 原已选择CLI版本，迁移期间保持。
    """

    model_config = ConfigDict(extra='forbid')
    operation_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    node_id: StrictInt = Field(ge=1)
    revision: StrictInt = Field(ge=1)
    version: StrictStr = Field(pattern=r'^(2\.1\.[0-9]{1,6}|1\.5\.9)$')


class MigrationCoordinator:
    """跨节点IO使用原账号锁与排他租约，未知结果保持维护。

    :param service: 中央节点服务。
    :param runtime: 中央原运行时。
    :param gateway: 原受信网关。
    :param quota_identity: 原额度身份读取函数。
    :param guard: 按账号取得owner/profile锁并产出当前账号和环境的上下文。
    """

    def __init__(self, service, runtime, gateway, quota_identity, guard) -> None:
        """保存中央权威与执行边界。

        :param service: 节点服务。
        :param runtime: 原运行时。
        :param gateway: 原网关。
        :param quota_identity: 额度身份回调。
        :param guard: 原账号owner/profile互斥与空闲核对上下文，排空期间不持有环境锁。
        :return: None。
        """
        self.service, self.runtime, self.gateway = service, runtime, gateway
        self.quota_identity, self.guard = quota_identity, guard
        self.ledger, self.io = NodeMigrations(service.store), MigrationIO(service, runtime)
        self.stopping = threading.Event()

    def begin(self, account_id: int, request: MigrationStart) -> dict:
        """核对空闲和节点能力后持久关闭账号准入，尚未执行节点IO。

        :param account_id: 当前中央账号。
        :param request: 人工选择与冻结版本。
        :return: requested阶段或同操作原记录。
        """
        if self.stopping.is_set():
            raise ValueError('迁移服务正在关闭，请稍后继续原操作')
        if not request.version.startswith('2.1.'):
            raise ValueError('当前账号的 CLI 迁移版本无效')
        try:
            existing = self.ledger.get(request.operation_id)
        except ValueError:
            existing = None
        if existing is not None:
            record = existing['record']
            if ((existing['account_id'], existing['target_node_id'], record['source_revision'])
                    != (account_id, request.node_id, request.revision)
                    or record.get('checkpoints', {}).get('execution', {}).get('version') != request.version):
                raise ValueError('原迁移操作的冻结范围不一致')
            return existing
        with self.guard(account_id) as (account, row):
            with self.runtime.environment_lock(row['environment_id']):
                row = self._fresh_row(account['id'], row['environment_id'])
                if row['state'] not in ('ready', 'stopped'):
                    raise ValueError('账号环境需要先完成执行对账，再开始迁移')
                fingerprint = json.loads(row['fingerprint_json'])
                if 'system_profile' in fingerprint:
                    validate_system_profile(fingerprint['system_profile'])
                    if 'computer_profile' in fingerprint:
                        validate_computer_profile(fingerprint['computer_profile'], fingerprint['system_profile'])
                original = self.service.store.assignment(account_id)
                source = self.service.store.get(original['node_id'])
                target = self.service.store.get(request.node_id)
                if not target['enabled'] or target['kind'] not in ('local', 'ssh'):
                    raise ValueError('迁移目标节点不可接单，请核对节点状态')
                if row['generation'] == 0 and not any(row.get(key) for key in ('container_id', 'network_container_id', 'sender_container_id')):
                    if source['kind'] == 'local':
                        root = self.runtime._root(row)
                        if root.is_symlink():
                            raise ValueError('账号环境目录需要先核对')
                        if not root.exists() or not any(root.iterdir()):
                            raise ValueError('账号尚未执行，请先设置首次执行节点')
                    else:
                        inspection = NodeInspection(node_key=source['node_key'], account_id=account_id,
                            environment_id=row['environment_id'], assignment_revision=original['revision'], version=request.version)
                        observed = self.service.connection(source['id']).prepare_environment(
                            node_container_name(self.runtime.deployment, source['node_key']), inspection.model_dump(), inspect=True)
                        self._receipt(observed, {'protocol': 1, 'node_key': source['node_key'], 'account_id': account_id,
                            'environment_id': row['environment_id'], 'assignment_revision': original['revision'], 'generation': 0})
                execution = self._execution(account, request.version, source, target)
                return self.ledger.begin(request.operation_id, account_id, request.node_id, request.revision, execution=execution)

    def _execution(self, account, version, source, target):
        return {'account_name': account['name'], 'profile_path': account['profile_path'],
            'gateway_account_id': account['cc2api_account_id'], 'version': version,
            'attempt_id': uuid.uuid4().hex, 'transfer_id': uuid.uuid4().hex,
            'source_node_key': source['node_key'], 'source_node_revision': source['revision'],
            'source_node_config_sha256': hashlib.sha256(source['config_json'].encode()).hexdigest(),
            'source_node_location': self._node_location(source),
            'target_node_key': target['node_key'], 'target_node_revision': target['revision'],
            'target_node_config_sha256': hashlib.sha256(target['config_json'].encode()).hexdigest(),
            'target_node_location': self._node_location(target)}

    def _fresh_row(self, account_id: int, environment_id: str) -> dict:
        connection = self.service.store.database()
        try:
            row = connection.execute('SELECT * FROM account_environments WHERE account_id=? AND environment_id=?',
                (account_id, environment_id)).fetchone()
            if row is None:
                raise ValueError('迁移原环境已变化')
            return dict(row)
        finally:
            connection.close()

    def _node_location(self, node: dict) -> dict:
        config = json.loads(node['config_json'])
        return {key: config.get(key) for key in ('host', 'port', 'host_key', 'data_root')}

    def _ready(self, node: dict, *, synchronize: bool = False) -> None:
        if not node['enabled']:
            raise ValueError('迁移目标节点已暂停接单')
        if node['kind'] == 'ssh':
            preparation = json.loads(node['preparation_json']) if node['preparation_json'] else {}
            if synchronize and preparation.get('state') == 'prepared' and preparation.get('release') == self.runtime.release_id:
                health = self.service.connection(node['id']).agent_health(node_container_name(self.runtime.deployment, node['node_key']))
                if health.get('release') != self.runtime.release_id or health.get('deployment') != self.runtime.deployment:
                    raise ValueError('迁移目标需要先准备同批执行组件')
            if preparation.get('state') != 'prepared' or preparation.get('release') != self.runtime.release_id:
                automatic = getattr(self.service, 'synchronization', None) is not None
                if not synchronize or not automatic and node['id'] not in getattr(self.service, 'install_workers', {}):
                    raise ValueError('迁移目标需要先准备同批执行组件')
                if automatic:
                    self.service.prepare_node(node['id'], node['revision'], automatic=True)
                while not self.stopping.wait(.5):
                    node = self.service.store.get(node['id'])
                    preparation = json.loads(node['preparation_json']) if node['preparation_json'] else {}
                    if preparation.get('state') == 'prepared' and preparation.get('release') == self.runtime.release_id:
                        return self._ready(node, synchronize=True)
                    if preparation.get('state') in ('failed', 'needs_check'):
                        raise ValueError('迁移目标需要先准备同批执行组件')
                    if not automatic and node['id'] not in self.service.install_workers:
                        raise ValueError('迁移目标需要先准备同批执行组件')
                raise ValueError('迁移服务正在关闭，请稍后继续原操作')
        elif node['kind'] != 'local':
            raise ValueError('迁移目标节点类型无效')

    def _context(self, operation_id: str, account: dict) -> tuple[dict, dict, ArchiveIdentity, EnvironmentFence]:
        migration = self.ledger.get(operation_id)
        record = migration['record']
        execution = record.get('checkpoints', {}).get('execution')
        if (not isinstance(execution, dict) or migration['account_id'] != account['id']
                or account['name'] != execution['account_name'] or account['profile_path'] != execution['profile_path']
                or account['cc2api_account_id'] != execution['gateway_account_id']):
            raise ValueError('迁移原账号或网关绑定已变化')
        for side in ('source', 'target'):
            node = self.service.store.get(migration[side + '_node_id'])
            # 暂停接单会推进页面revision；恢复核对固定连接配置，避免暂停本身阻断原迁移恢复。
            same_location = (self._node_location(node) == execution[side + '_node_location']
                if side + '_node_location' in execution else
                hashlib.sha256(node['config_json'].encode()).hexdigest() == execution[side + '_node_config_sha256'])
            if node['node_key'] != execution[side + '_node_key'] or not same_location:
                raise ValueError('迁移原节点配置版本已变化，请核对原操作')
        identity_type = AgyArchiveIdentity if self.ledger.agy else ArchiveIdentity
        identity = identity_type(operation_id=operation_id, deployment_id=self.runtime.deployment,
            source_node_key=execution['source_node_key'], account_id=account['id'],
            environment_id=record['environment_id'], assignment_revision=record['source_revision'],
            **({'platform': 'antigravity', 'kernel': execution.get('kernel')} if self.ledger.agy else {}))
        fence = EnvironmentFence(operation_id=operation_id, node_key=execution['source_node_key'], account_id=account['id'],
            environment_id=record['environment_id'], assignment_revision=record['source_revision'], generation=record['source_generation'])
        return migration, execution, identity, fence

    def _lease(self, operation_id: str, execution: dict, account_id: int) -> MigrationLease | IndependentMigrationPermit:
        if execution['gateway_account_id'] is None:
            return IndependentMigrationPermit(self.ledger,operation_id,self.service.transports,account_id,abort=self.stopping)
        return MigrationLease(self.gateway, self.ledger, operation_id, execution['gateway_account_id'],
            self.service.transports, account_id, abort=self.stopping)

    def run(self, operation_id: str) -> dict:
        """推进同操作，提交后恢复只继续新目标激活。

        :param operation_id: 原持久操作。
        :return: completed记录；异常保持reconcile与实际现场。
        """
        migration = self.ledger.get(operation_id)
        if migration['phase'] in ('completed', 'cancelled'):
            return migration
        step = 'context'
        try:
            # 同步在两端操作锁之外等待；后台安装器使用同一把节点锁。
            if migration['record']['last_confirmed_phase'] != 'committed' and not self.ledger.agy:
                step = 'preflight'
                self.ledger.progress(operation_id, step)
                self._ready(self.service.store.get(migration['target_node_id']), synchronize=True)
            with self.service.migration_nodes(migration), self.guard(migration['account_id']) as (account, row):
                migration, execution, identity, fence = self._context(operation_id, account)
                if migration['phase'] in ('completed', 'cancelled'):
                    return migration
                early_cancel = self.ledger.agy and self._early_cancel(operation_id)
                if early_cancel:
                    return self.cancel(operation_id)
                if 'cancellation' in migration['record'].get('checkpoints', {}) and not early_cancel:
                    raise ValueError('迁移已经开始取消，请继续原取消操作')
                with self._lease(operation_id, execution, account['id']) as lease:
                    step = 'draining'
                    self.ledger.progress(operation_id, step)
                    if self.ledger.agy:
                        if not lease.drain(cancelled=lambda: self._early_cancel(operation_id)):
                            lease.release()
                            return self.ledger.finish_drain_cancel(operation_id)
                    else:
                        lease.drain()
                    # 先排空，再取环境锁，允许排空中的既有transport完成原准备。
                    with self.runtime.environment_lock(fence.environment_id):
                        row = self._fresh_row(account['id'], fence.environment_id)
                        if migration['phase'] == 'reconcile':
                            migration = self.ledger.resume(operation_id)
                        target_id, source_id = migration['target_node_id'], migration['source_node_id']
                        if migration['phase'] in ('requested', 'draining', 'source_fenced', 'exporting', 'importing', 'verified'):
                            self._ready(self.service.store.get(target_id))
                        if migration['phase'] == 'requested':
                            migration = self.ledger.advance(operation_id, 'draining', {'active': 0, 'node_streams': 0})
                            if self.ledger.agy:
                                if migration['phase'] == 'requested':
                                    lease.release()
                                    return self.ledger.finish_drain_cancel(operation_id)
                                fence = fence.model_copy(update={'generation': migration['record']['source_generation']})
                        if migration['phase'] == 'draining':
                            lease.check()
                            step = 'fence'
                            self.ledger.progress(operation_id, step)
                            if self.ledger.agy:
                                lease.drain()
                                self._before_fence(migration, account, row, execution)
                            receipt = self.io.command(source_id, 'fence', fence.model_dump())
                            self._receipt(receipt, {'protocol': 1, **fence.model_dump(), 'phase': 'fenced'})
                            migration = self.ledger.advance(operation_id, 'source_fenced', receipt)
                        if migration['phase'] == 'source_fenced':
                            lease.check()
                            step = 'export'
                            self.ledger.progress(operation_id, step)
                            request = {**fence.model_dump(), 'attempt_id': execution['attempt_id']}
                            if self.ledger.agy:
                                request['kernel'] = execution['kernel']
                            else:
                                request = ArchiveExport(**request, version=execution['version']).model_dump()
                            archive = ArchiveDescriptor.model_validate(self.io.command(source_id, 'export', request)['archive'])
                            if (archive.identity != identity or archive.environment_generation != fence.generation
                                    or not self.ledger.agy and (archive.cli_version != execution['version'] or archive.cli_identity is None)):
                                raise ValueError('迁移包与原源身份或代次不一致')
                            self.ledger.checkpoint(operation_id, 'archive', archive.model_dump())
                            migration = self.ledger.advance(operation_id, 'exporting', {'sha256': archive.sha256, 'bytes': archive.bytes})
                        if migration['phase'] in ('exporting', 'importing', 'verified'):
                            archive = ArchiveDescriptor.model_validate(migration['record']['checkpoints']['archive'])
                            transfer_id = migration['record']['checkpoints'].get('transfer', {}).get('transfer_id', execution['transfer_id'])
                            stage = ImportStage(node_key=execution['target_node_key'], transfer_id=transfer_id,
                                target_revision=fence.assignment_revision + 1, archive=archive)
                            if migration['phase'] == 'exporting':
                                lease.check()
                                step = 'transfer'
                                self.ledger.progress(operation_id, step)
                                bundle = self.io.download(source_id, archive)
                                try:
                                    self.io.upload(target_id, stage, bundle)
                                except MigrationUploadIncomplete:
                                    # 原未知上传保留供核查；新尝试先落盘，重启后才能沿同一位置继续。
                                    migration = self.ledger.renew_transfer(operation_id, stage.transfer_id, uuid.uuid4().hex)
                                    stage = stage.model_copy(update={'transfer_id': migration['record']['checkpoints']['transfer']['transfer_id']})
                                    lease.check()
                                    self.io.upload(target_id, stage, bundle)
                                migration = self.ledger.advance(operation_id, 'importing', {'transfer_id': stage.transfer_id})
                            if migration['phase'] == 'importing':
                                lease.check()
                                checkpoints = migration['record'].get('checkpoints', {})
                                if 'target' not in checkpoints:
                                    step = 'verify-import'
                                    self.ledger.progress(operation_id, step)
                                    verified = self.io.command(target_id, 'verify-import', stage.model_dump())
                                    self._receipt(verified, {'protocol': 1, 'node_key': stage.node_key, 'operation_id': operation_id,
                                        'transfer_id': stage.transfer_id, 'phase': 'verified', 'sha256': archive.sha256})
                                frozen = {**row, 'generation': fence.generation, 'state': migration['record']['source_state']}
                                step = 'prepare-import'
                                self.ledger.progress(operation_id, step)
                                peer = self._prepare_import(target_id, stage, account, frozen)
                                self.ledger.checkpoint(operation_id, 'target', {'environment': peer['environment']})
                                migration = self.ledger.advance(operation_id, 'verified', {'transfer_id': stage.transfer_id,
                                    'generation': peer['environment']['generation']})
                            if migration['phase'] == 'verified':
                                lease.check()
                                self._ready(self.service.store.get(target_id))
                                migration = self.ledger.commit(operation_id, migration['record']['checkpoints']['target']['environment'])
                        if migration['phase'] == 'committed':
                            lease.check()
                            record = migration['record']
                            # 提交后重建协调器也须激活已发布的新尝试，execution仅保留最初身份。
                            transfer_id = record['checkpoints'].get('transfer', {}).get('transfer_id', execution['transfer_id'])
                            request = ImportActivation(node_key=execution['target_node_key'], operation_id=operation_id,
                                transfer_id=transfer_id, account_id=account['id'], environment_id=record['environment_id'],
                                revision=record['target_revision'], generation=record['target_generation'])
                            step = 'activate-import'
                            self.ledger.progress(operation_id, step)
                            activated = self.io.command(target_id, 'activate-import', request.model_dump())
                            self._receipt(activated, {'protocol': 1, **request.model_dump(), 'phase': 'activated'})
                            lease.release()
                            return self.ledger.finish(operation_id, self._central_receipt(activated, target_id, 'activated'))
                        raise ValueError('迁移当前阶段需要核对')
        except Exception as error:
            if self.ledger.get(operation_id)['phase'] not in ('completed', 'cancelled'):
                self.ledger.isolate(operation_id, 'migration_step_unconfirmed', failure=migration_failure(error, step))
            raise

    def _early_cancel(self, operation_id):
        checkpoints = self.ledger.get(operation_id)['record'].get('checkpoints', {})
        return checkpoints.get('cancellation', {}).get('before_fence') is True

    def _prepare_import(self, target_id, stage, account, frozen):
        profiles = MigrationProfiles(self.service.data, stage.archive.identity.operation_id)
        preparation = self.service.build_preparation(account, frozen, stage.node_key, stage.target_revision,
            self.runtime, self.gateway, self.quota_identity(account), profile_sink=profiles.save,
            **({'cli_only': True} if account['cc2api_account_id'] is None else {}))
        if profiles.references:
            self.io.upload_profiles(target_id, stage, profiles)
        peer = self.io.command(target_id, 'prepare-import', ImportPreparation(stage=stage, preparation=preparation,
            profile_references=profiles.references).model_dump())
        self._prepared(peer, account, stage)
        return peer

    def cancel(self, operation_id: str) -> dict:
        """提交前撤销目标，再恢复源；原操作的迟到节点命令持续被拒绝。

        :param operation_id: 原未提交操作。
        :return: cancelled记录；提交后保留新归属并拒绝回退。
        """
        migration = self.ledger.get(operation_id)
        if migration['phase'] == 'cancelled':
            return migration
        if migration['phase'] == 'completed' or migration['record']['last_confirmed_phase'] == 'committed':
            raise ValueError('迁移归属已提交，请继续目标激活')
        step = 'context'
        try:
            with self.service.migration_nodes(migration), self.guard(migration['account_id']) as (account, row):
                migration, execution, identity, fence = self._context(operation_id, account)
                if migration['phase'] == 'cancelled':
                    return migration
                if migration['phase'] == 'completed' or migration['record']['last_confirmed_phase'] == 'committed':
                    raise ValueError('迁移归属已提交，请继续目标激活')
                self.ledger.checkpoint(operation_id, 'cancellation', {'requested': True})
                with self._lease(operation_id, execution, account['id']) as lease:
                    step = 'draining'
                    self.ledger.progress(operation_id, step)
                    lease.drain()
                    if migration['phase'] == 'reconcile':
                        migration = self.ledger.resume(operation_id)
                    with self.runtime.environment_lock(fence.environment_id):
                        revoke = ImportRevocation(node_key=execution['target_node_key'], target_revision=fence.assignment_revision + 1,
                            identity=identity)
                        step = 'revoke-import'
                        self.ledger.progress(operation_id, step)
                        target = self.io.command(migration['target_node_id'], 'revoke-import', revoke.model_dump())
                        self._receipt(target, {'protocol': 1, 'node_key': revoke.node_key, 'operation_id': operation_id,
                            'account_id': account['id'], 'environment_id': identity.environment_id, 'revision': revoke.target_revision, 'phase': 'revoked'})
                        self.ledger.checkpoint(operation_id, 'target_revoked', target)
                        lease.check()
                        step = 'restore-source'
                        self.ledger.progress(operation_id, step)
                        source = self.io.command(migration['source_node_id'], 'restore-source', fence.model_dump())
                        self._receipt(source, {'protocol': 1, **fence.model_dump(), 'phase': 'restored'})
                        self.ledger.checkpoint(operation_id, 'source_restored', source)
                        lease.release()
                        return self.ledger.cancel(operation_id, self._central_receipt(source, migration['source_node_id'], 'restored'),
                            self._central_receipt(target, migration['target_node_id'], 'revoked'))
        except Exception as error:
            if self.ledger.get(operation_id)['phase'] not in ('completed', 'cancelled'):
                self.ledger.isolate(operation_id, 'migration_cancellation_unconfirmed', failure=migration_failure(error, step))
            raise

    def _prepared(self, peer: dict, account: dict, stage: ImportStage) -> None:
        self._receipt(peer, {'protocol': 1, 'node_key': stage.node_key, 'assignment_revision': stage.target_revision,
            'operation_id': stage.archive.identity.operation_id, 'transfer_id': stage.transfer_id, 'phase': 'prepared'})
        actual, binding = peer.get('environment'), peer.get('binding')
        if not isinstance(actual,dict) or actual.get('account_id')!=account['id'] or actual.get('environment_id')!=stage.archive.identity.environment_id:
            raise ValueError('迁移目标准备回执与原正式环境不一致')
        if account['cc2api_account_id'] is None:
            if binding is not None:
                raise ValueError('独立迁移目标不能发布Gateway绑定')
            return
        # 控制组件可独立换批；目标新建角色按受信配置的账号镜像发布来源核对。
        if (not isinstance(binding, dict) or actual.get('account_id') != account['id']
                or actual.get('environment_id') != stage.archive.identity.environment_id or actual.get('name') != account['name']
                or binding.get('account_id') != account['cc2api_account_id'] or binding.get('environment_id') != actual['environment_id']
                or binding.get('generation') != actual.get('generation') or binding.get('release_id') != configured_release(self.runtime)
                or not isinstance(binding.get('secret'), str) or not 32 <= len(binding['secret']) <= 256):
            raise ValueError('迁移目标准备回执与原环境或发送器身份不一致')
        ipaddress.ip_address(peer.get('sender_address', ''))

    def _receipt(self, receipt: dict, expected: dict) -> None:
        if not isinstance(receipt, dict) or any(receipt.get(key) != value for key, value in expected.items()):
            raise ValueError('迁移节点收据与原冻结范围不一致')

    def _central_receipt(self, receipt: dict, node_id: int, phase: str) -> dict:
        keys = ('operation_id', 'account_id', 'environment_id', 'revision')
        if phase != 'revoked':
            keys += ('generation',)
        source = {**receipt, 'revision': receipt['assignment_revision']} if phase == 'restored' else receipt
        return {**{key: source[key] for key in keys}, 'node_id': node_id, 'phase': phase}
