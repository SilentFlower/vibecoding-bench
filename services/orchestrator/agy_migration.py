"""将 AGY 网关环境接入现有持久迁移生命周期。"""
from contextlib import contextmanager
import hashlib
import json

from account_update_identity import configured_release
from agy_environment import lookup
from agy_node_contract import AgyPreparation
from cluster_migration_io import MigrationIO
from cluster_migration_runner import MigrationCoordinator, MigrationStart
from cluster_migrations import NodeMigrations


class AgyMigrationCoordinator(MigrationCoordinator):
    """使用 AGY 网关账号和固定环境身份执行迁移。@param placement 中央 AGY 归属服务。"""

    def __init__(self, placement):
        """接入共享迁移阶段与私有文件通道。@param placement 中央 AGY 归属服务。@return 无。"""
        self.placement = placement
        runtime = placement.runtime
        super().__init__(placement.service, runtime, runtime.gateway, None, self._guard)
        self.ledger = NodeMigrations(placement.store, agy=True)
        self.io = MigrationIO(placement.service, runtime, agy=placement)

    @contextmanager
    def _guard(self, account_id):
        row = lookup(self.runtime, account_id)
        if row is None:
            raise ValueError('AGY 网关账号尚未登记运行环境')
        yield {'id': account_id, 'name': row['name'], 'profile_path': None, 'cc2api_account_id': account_id}, row

    def _fresh_row(self, account_id, environment_id):
        row = lookup(self.runtime, account_id)
        if row is None or row['environment_id'] != environment_id:
            raise ValueError('原 AGY 网关环境已变化')
        return row

    def _configuration_identity(self, configuration):
        return hashlib.sha256(json.dumps([configuration.get(key) for key in
            ('account_id', 'platform', 'auth_type', 'email', 'proxy_url')], ensure_ascii=False).encode()).hexdigest()

    def begin(self, account_id: int, request: MigrationStart) -> dict:
        """预检原身份、目标制品与资源，再登记迁移。@param account_id 网关账号。@param request 目标及分配。@return 原持久迁移。"""
        if self.stopping.is_set() or request.version != '1.5.9':
            raise ValueError('AGY 迁移服务或运行版本尚未就绪')
        try:
            existing = self.ledger.get(request.operation_id)
        except ValueError:
            existing = None
        if existing is not None:
            return self.ledger.begin(request.operation_id, account_id, request.node_id, request.revision)
        original = self.ledger.assignment(account_id)
        if original['revision'] != request.revision or original['phase'] != 'ready' or original['node_id'] == request.node_id:
            raise ValueError('AGY 账号归属已变化或迁移目标与当前节点相同')
        nodes = {'source_node_id': original['node_id'], 'target_node_id': request.node_id}
        with self.service.migration_nodes(nodes), self.placement.current(account_id) as (row, assignment):
            if (assignment != original or row['generation'] < 1 or row['state'] not in ('ready', 'stopped')):
                raise ValueError('AGY 当前运行环境需要确认后才能迁移')
            source, target = (self.service.store.get(nodes[key]) for key in ('source_node_id', 'target_node_id'))
            self._ready(target, synchronize=False)
            configuration = self.placement.configuration(account_id)
            self._preflight(target, row, request.revision + 1, configuration)
            with self._guard(account_id) as (account, _):
                execution = self._execution(account, request.version, source, target)
            observed = self.placement.exact(row, assignment, 'agy-fingerprint')
            if observed['fingerprint_json'] != row['fingerprint_json']:
                raise ValueError('AGY 源环境配置正在同步，请重读后迁移')
            execution['kernel'] = observed['kernel']
            execution['configuration_identity'] = self._configuration_identity(configuration)
            return self.ledger.begin(request.operation_id, account_id, request.node_id, request.revision, execution=execution)

    def _prepare_import(self, target_id, stage, account, frozen):
        migration = self.ledger.get(stage.archive.identity.operation_id)
        configuration = self.placement.configuration(account['id'])
        if self._configuration_identity(configuration) != migration['record']['checkpoints']['execution']['configuration_identity']:
            raise ValueError('AGY 源账号身份或代理已变化，请核对原迁移')
        scope = {'node_key': stage.node_key, 'assignment_revision': stage.target_revision,
            'environment_id': frozen['environment_id'], 'generation': frozen['generation'], 'account_id': account['id']}
        peer = self.io.command(target_id, 'prepare-import', {**scope, 'environment': frozen,
            'configuration': configuration, 'stage': stage.model_dump()})
        self._receipt(peer, {'operation_id': stage.archive.identity.operation_id,
            'transfer_id': stage.transfer_id, 'phase': 'prepared'})
        self.placement.prepared(peer, scope, wake=True)
        return peer

    def _before_fence(self, migration, account, row, execution):
        configuration = self.placement.configuration(account['id'])
        if self._configuration_identity(configuration) != execution['configuration_identity']:
            raise ValueError('AGY 源账号身份或代理已变化，请核对原迁移')
        assignment = self.ledger.assignment(account['id'])
        self.placement.settle_capacity(row, assignment)
        target = self.service.store.get(migration['target_node_id'])
        self._preflight(target, row, assignment['revision'] + 1, configuration)

    def _preflight(self, target, row, revision, configuration):
        scope = {'node_key': target['node_key'], 'assignment_revision': revision, 'environment_id': row['environment_id'],
            'generation': row['generation'], 'account_id': row['gateway_account_id']}
        actual = self.io.command(target['id'], 'preflight', AgyPreparation(**scope, environment=row,
            configuration=configuration).model_dump())
        self._receipt(actual, {'protocol': 1, **scope, 'phase': 'compatible',
            'release': configured_release(self.runtime)})

    def cancel(self, operation_id: str) -> dict:
        """排空时解除原门禁，已隔离时按双端核验恢复。@param operation_id 原迁移。@return 已取消记录。"""
        record = self.ledger.get(operation_id)
        if record['record']['last_confirmed_phase'] != 'requested':
            return super().cancel(operation_id)
        record = self.ledger.request_drain_cancel(operation_id)
        path = f"/admin/runtime/accounts/{record['account_id']}/lease"
        snapshot = self.gateway._request('GET', path)
        holders = snapshot.get('holders')
        if not isinstance(holders, list) or snapshot.get('importing') != 0:
            raise ValueError('原 AGY 网关门禁需要核对')
        if holders:
            owner = 'node-migration:' + operation_id
            owned = [value for value in holders if value.get('owner') == owner]
            if owned:
                lease, = owned
                proof = {key: lease[key] for key in ('owner', 'generation')}
                previous = record['record']['checkpoints'].get('gateway_lease')
                if (len(holders) != 1 or lease.get('exclusive') is not True
                        or previous is not None and proof != previous):
                    raise ValueError('原 AGY 网关门禁已变化')
                after = self.gateway._request('POST', path, {'operation': 'release', **proof})
                if after.get('holders') != [] or after.get('importing') != 0:
                    raise ValueError('AGY 网关门禁释放需要核对')
        return self.ledger.finish_drain_cancel(operation_id)
