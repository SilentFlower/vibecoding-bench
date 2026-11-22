"""AGY 节点实际环境、归档发布与隔离后的激活。"""
from contextlib import contextmanager
import ipaddress
import json
import os
from pathlib import Path

from pydantic import Field, StrictStr

from account_isolation import ISOLATION_VERSION, ROLE_COLUMNS, role_container
from account_runtime import RuntimeCapacityUnavailable, _read_json, active_account_environments
from account_update_identity import configured_release
from agy_capacity import CapacityError, _receipt as capacity_receipt, change_capacity
from agy_environment import account_input, capture, lookup, sender_config, stop_environment, summary, transport
from agy_kernel import activate, catalog, selection, verify_candidate
from agy_node_contract import AgyCapacity, AgyCapture, AgyControl, AgyIngress, AgyLocation, AgyPreparation
from agy_runtime.capture import read_snapshot, save_ingress
from cluster_archive import AgyArchiveIdentity
from cluster_deployment import node_network_name
from cluster_environment import EnvironmentFence, fence_environment, restore_fenced_source
from cluster_execution import ImportActivation, ImportRevocation
from cluster_migration_files import ImportStage, MigrationFiles
from database_migrations import apply_migrations
from cpu_resources import read_resources as read_cpu_resources, set_resources as set_cpu_resources
from native_capture_policy import capture_enabled
from runtime_files import atomic_json, directory_fd
from system_profile import validate_computer_profile, validate_system_profile


class AgyExport(EnvironmentFence):
    """已隔离 AGY 原环境的归档尝试。@param attempt_id 固定导出身份。"""

    attempt_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    kernel: StrictStr | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


class AgyImport(AgyPreparation):
    """核验之后的目标发布请求。@param stage 固定归档与上传尝试。"""

    stage: ImportStage


class _GatewayConfiguration:
    """将中央已核验配置限制在本操作和原网关账号。"""

    def __init__(self, account_id, configuration, authorities=None):
        self.path = f'/admin/runtime/accounts/{account_id}/config'
        self.configuration = configuration
        self.authorities = authorities or {}

    def _request(self, method, path, **kwargs):
        if method == 'GET':
            if path == self.path:
                return self.configuration
            for operation_id, configuration in self.authorities.items():
                if path == self.path + '?capacity_operation=' + operation_id:
                    return configuration
        raise ValueError('AGY 节点操作超出原配置证明范围')


def _optional(path):
    try:
        return _read_json(path)
    except FileNotFoundError:
        return None


class AgyNode:
    """在可信节点进程中执行固定 AGY 操作。@param executor 原节点执行器。"""

    def __init__(self, executor):
        """绑定执行器、安装节点和私有归档目录。@param executor 已验证执行器。@return 无。"""
        self.executor = executor
        self.key = executor.node_key
        self.files = MigrationFiles(executor.data, self.key, executor.deployment)

    @contextmanager
    def _runtime(self, request, *, source=False):
        if source and self.executor.local_runtime is not None:
            yield self.executor.local_runtime
            return
        if not self.executor.database_path.is_file():
            raise ValueError('AGY 节点执行投影尚未登记')
        gateway = _GatewayConfiguration(request.account_id, getattr(request, 'configuration', {}),
            getattr(request, 'authorities', None))
        runtime = self.executor._runtime(gateway)
        try:
            yield runtime
        finally:
            self.executor._release_runtime(runtime)

    def call(self, operation: str, payload: dict) -> dict:
        """验证模型并分派到安装节点。@param operation 专用节点动作。@param payload 私有请求。@return 冻结范围回执。"""
        model, action = {
            'agy-preflight': (AgyPreparation, self._preflight),
            'agy-prepare': (AgyPreparation, self._prepare),
            'agy-inspect': (AgyLocation, self._inspect),
            'agy-fingerprint': (AgyLocation, self._fingerprint),
            'agy-capacity-state': (AgyLocation, self._capacity_state),
            'agy-capacity': (AgyCapacity, self._capacity),
            'agy-control': (AgyControl, self._control),
            'agy-capture-read': (AgyCapture, self._capture_read),
            'agy-ingress': (AgyIngress, self._ingress),
            'agy-fence': (EnvironmentFence, self._fence),
            'agy-restore-source': (EnvironmentFence, self._restore),
            'agy-export': (AgyExport, self._export),
            'agy-stage-import': (ImportStage, self._stage),
            'agy-verify-import': (ImportStage, self._verify),
            'agy-prepare-import': (AgyImport, self._import),
            'agy-activate-import': (ImportActivation, self._activate),
            'agy-revoke-import': (ImportRevocation, self._revoke),
        }[operation]
        request = model.model_validate(payload)
        if request.node_key != self.key:
            raise ValueError('AGY 实际节点身份不一致')
        return action(request)

    def _row(self, runtime, request, *, ready=False, recover_preparation=False):
        row = lookup(runtime, request.account_id)
        if (row is None or row['environment_id'] != request.environment_id
                or row['generation'] != request.generation
                and not (recover_preparation and row['generation'] > request.generation)):
            raise ValueError('AGY 节点网关环境或代次已变化')
        if ready:
            root = runtime._root(row) / 'runtime'
            expected = self._owner(request.account_id, request.environment_id, request.assignment_revision)
            published = _optional(root / 'node-migration-target.json')
            if (_optional(root / 'node-assignment.json') != expected
                    or not isinstance(published, dict) or published.get('phase') != 'activated'
                    or published.get('revision') != request.assignment_revision):
                raise ValueError('AGY 节点分配尚未激活')
        return row

    def _owner(self, account_id, environment_id, revision):
        return {'protocol': 1, 'node_key': self.key, 'account_id': account_id, 'environment_id': environment_id,
            'revision': revision, 'phase': 'ready'}

    def _identity(self, request, kernel):
        return AgyArchiveIdentity(platform='antigravity', operation_id=request.operation_id,
            deployment_id=self.executor.deployment, source_node_key=self.key, account_id=request.account_id,
            environment_id=request.environment_id, assignment_revision=request.assignment_revision, kernel=kernel)

    def _preflight(self, request):
        configuration, row = request.configuration, request.environment
        if (configuration.get('account_id') != request.account_id or configuration.get('platform') != 'antigravity'
                or configuration.get('auth_type') != 'oauth' or configuration.get('status') not in ('active', 'disabled', 'error')
                or configuration.get('credential_state', {}).get('phase') != 'ready'
                or row['environment_id'] != request.environment_id or row.get('account_id') is not None
                or row['generation'] != request.generation or row['name'] != f'agy:{request.account_id}'):
            raise ValueError('AGY 目标预检范围不一致')
        account_input(configuration, row)
        client = self.executor.client
        local = self.executor.local_runtime
        if local is not None:
            reference, release, network = local.image, configured_release(local), local.network
            with local.capacity_lock:
                local._make_room(row, allow_eviction=False)
        else:
            # 预检不实例化 AccountRuntime。空节点须由正式导入迁移初始化完整投影库。
            reference = os.environ['V3_ACCOUNT_IMAGE']
            release = os.environ.get('V3_ACCOUNT_RELEASE') or os.environ['V3_RELEASE']
            network = node_network_name(self.executor.deployment, self.key)
            active = active_account_environments(client, self.executor.deployment, self.key)
            if request.environment_id not in active and len(active) >= int(os.environ.get('V3_MAX_ACTIVE_ACCOUNTS', '1')):
                raise ValueError('AGY 迁移目标无空余环境容量')
        image = client.images.get(reference)
        labels = image.attrs['Config'].get('Labels') or {}
        if any(labels.get(key) != value for key, value in {'vibebench.product': 'v3',
                'vibebench.role': 'account', 'vibebench.release': release,
                'vibebench.isolation-version': str(ISOLATION_VERSION)}.items()):
            raise ValueError('AGY 迁移目标镜像批次或能力不一致')
        fingerprint = json.loads(row['fingerprint_json'])
        sender_config(configuration, fingerprint, labels)
        if 'system_profile' in fingerprint:
            profile = validate_system_profile(fingerprint['system_profile'], Path('/proc/cpuinfo').read_text())
            if 'computer_profile' in fingerprint:
                validate_computer_profile(fingerprint['computer_profile'], profile)
        client.networks.get(network)
        return {'protocol': 1, **request.model_dump(include=set(AgyLocation.model_fields)),
            'release': release, 'phase': 'compatible'}

    def _prepare(self, request):
        with self.executor._locked(environment_id=request.environment_id), self.executor._locked(), self._runtime(request) as runtime:
            self._row(runtime, request, ready=True, recover_preparation=True)
            try:
                binding = transport(runtime, request.account_id, wake=request.wake, allow_eviction=False)
            except RuntimeCapacityUnavailable:
                return {**self._prepared(runtime, request, None), 'preparation_reason': 'waiting_capacity'}
            return self._prepared(runtime, request, binding)

    def _prepared(self, runtime, request, binding):
        row = lookup(runtime, request.account_id)
        address = None
        if binding is not None:
            network = role_container(runtime, row, 'network')
            network.reload()
            address = str(ipaddress.ip_address(network.attrs['NetworkSettings']['Networks'][runtime.network]['IPAddress']))
        return {'protocol': 1, 'node_key': self.key, 'assignment_revision': request.assignment_revision,
            'environment': row, 'binding': binding, 'sender_address': address}

    def _inspect(self, request):
        with self.executor._locked(read_only=True, environment_id=request.environment_id), self._runtime(request) as runtime:
            row = self._row(runtime, request, ready=True)
            return {'protocol': 1, **request.model_dump(), 'environment': summary(runtime, row)}

    def _fingerprint(self, request):
        with self.executor._locked(read_only=True, environment_id=request.environment_id), self._runtime(request, source=True) as runtime:
            row = self._row(runtime, request, ready=self.key != 'local')
            kernel = selection(runtime, row)
            if kernel is not None:
                verify_candidate(runtime._root(row), kernel)
            return {'protocol': 1, **request.model_dump(), 'fingerprint_json': row['fingerprint_json'], 'kernel': kernel}

    def _capacity_state(self, request):
        with self.executor._locked(read_only=True, environment_id=request.environment_id), self._runtime(request) as runtime:
            receipt = capacity_receipt(runtime, self._row(runtime, request, ready=True))
            return {'protocol': 1, **request.model_dump(), 'receipt': receipt}

    def _capacity(self, request):
        with self.executor._locked(environment_id=request.environment_id), self._runtime(request) as runtime:
            scope = request.model_dump(include=set(AgyLocation.model_fields))
            self._row(runtime, request, ready=True)
            try:
                change_capacity(runtime, request.account_id, request.operation_id, request.before, request.target, request.phase)
            except CapacityError as error:
                return {'protocol': 1, **scope, 'error': str(error)}
            return {'protocol': 1, **scope, 'operation_id': request.operation_id}

    def _control(self, request):
        with self.executor._locked(environment_id=request.environment_id), self._runtime(request) as runtime:
            row = self._row(runtime, request, ready=True)
            action, body = request.action, request.body
            result = None
            if action == 'capture-read':
                result = capture(runtime, row)
            elif action == 'capture-set':
                result = capture(runtime, row, body)
            elif action == 'cpu-read':
                result = read_cpu_resources(runtime, row)
            elif action == 'cpu-set':
                result = set_cpu_resources(runtime, row, body['expected_generation'], body['expected_revision'], body['cpus'])
            elif action == 'kernel-read':
                result = catalog(runtime, row)
            elif action == 'kernel-set':
                sender = role_container(runtime, row, 'sender') if row.get('sender_container_id') else None
                if sender is not None:
                    sender.reload()
                result = activate(runtime, row, body, sender if sender is not None and sender.status == 'running' else None)
            else:
                if runtime._running_sender_active(row) and (action != 'reconcile'
                        or summary(runtime, row).get('reconcile_allowed') is not True):
                    raise ValueError('AGY 原发送器仍有活动')
                stop_environment(runtime, row, remove=action != 'stop', retire_initial=action != 'quiesce')
                result = {'ok': True}
            return {'protocol': 1, **request.model_dump(include=set(AgyLocation.model_fields)),
                'value': result, 'environment': row}

    def _capture_read(self, request):
        with self.executor._locked(read_only=True, environment_id=request.environment_id), self._runtime(request) as runtime:
            row = self._row(runtime, request, ready=True)
            try:
                snapshot = read_snapshot(runtime._root(row), request.account_id, request.attempt_id)
            except FileNotFoundError:
                result = {'state': 'missing'}
            except TimeoutError:
                result = {'state': 'expired'}
            else:
                result = {'state': 'available', 'snapshot': snapshot}
            return {'protocol': 1, **request.model_dump(), **result}

    def _ingress(self, request):
        with self.executor._locked(environment_id=request.environment_id), self._runtime(request) as runtime:
            row = self._row(runtime, request, ready=True)
            if not capture_enabled(json.loads(row['fingerprint_json'])):
                raise ValueError('AGY 内容采集已关闭')
            save_ingress(runtime._root(row) / 'flows/api/agy-prepared', request.account_id,
                request.attempt_id, request.ingress)
            return {'protocol': 1, **request.model_dump(exclude={'ingress'}), 'state': 'saved'}

    def _fence(self, request):
        with self.executor._locked(environment_id=request.environment_id), self._runtime(request, source=True) as runtime:
            row = self._row(runtime, request)
            if capacity_receipt(runtime, row) is not None:
                raise ValueError('原 AGY 容量操作仍需收口')
            return fence_environment(runtime, row, request, agy=True)

    def _restore(self, request):
        with self.executor._locked(environment_id=request.environment_id), self._runtime(request, source=True) as runtime:
            return restore_fenced_source(runtime, self._row(runtime, request), request, agy=True)

    def _export(self, request):
        scope = EnvironmentFence.model_validate(request.model_dump(exclude={'attempt_id', 'kernel'}))
        with self.executor._locked(environment_id=request.environment_id), self._runtime(request, source=True) as runtime:
            row = self._row(runtime, scope)
            fence_environment(runtime, row, scope, agy=True)
            if request.kernel != selection(runtime, row):
                raise ValueError('AGY 源运行内核已变化')
            if request.kernel is not None:
                verify_candidate(runtime._root(row), request.kernel)
            archive = self.files.export(runtime._root(row), self._identity(scope, request.kernel), request.attempt_id,
                environment_generation=row['generation'])
            return {'protocol': 1, 'node_key': self.key, 'archive': archive.model_dump()}

    def _validate_stage(self, stage):
        if (not isinstance(stage.archive.identity, AgyArchiveIdentity) or stage.node_key != self.key
                or stage.archive.environment_generation is None or stage.archive.cli_identity is not None
                or stage.archive.cli_version is not None):
            raise ValueError('迁移包不属于 AGY 源')

    def _stage(self, stage):
        self._validate_stage(stage)
        with self.executor._locked(environment_id=stage.archive.identity.environment_id):
            return self.files.stage(stage)

    def _verify(self, stage):
        self._validate_stage(stage)
        with self.executor._locked(environment_id=stage.archive.identity.environment_id):
            return self.files.restore(stage)

    def _import(self, request):
        stage = request.stage
        self._validate_stage(stage)
        archive, row = stage.archive, request.environment
        identity = archive.identity
        if ((request.account_id, request.environment_id, request.assignment_revision, request.generation)
                != (identity.account_id, identity.environment_id, stage.target_revision, archive.environment_generation)
                or row['state'] not in ('ready', 'stopped')):
            raise ValueError('AGY 目标准备与源归档范围不一致')
        scope = request.model_dump(exclude={'stage'})
        with self.executor._locked(environment_id=request.environment_id), self.executor._locked():
            self._preflight(AgyPreparation.model_validate(scope))
            if not self.files.stage(stage)['uploaded']:
                raise ValueError('AGY 目标归档上传未核对')
            path = self.executor.data / 'node-migrations' / identity.operation_id / 'imports' / stage.transfer_id
            verified = _read_json(path / 'verified.json')
            if any(verified.get(key) != value for key, value in {'phase': 'verified', 'node_key': self.key,
                    'operation_id': identity.operation_id, 'transfer_id': stage.transfer_id,
                    'sha256': archive.sha256, 'revision': stage.target_revision}.items()):
                raise ValueError('AGY 目标缺少原归档核验回执')
            intent = {'protocol': 1, 'operation_id': identity.operation_id, 'transfer_id': stage.transfer_id,
                'node_key': self.key, 'account_id': request.account_id, 'environment_id': request.environment_id,
                'revision': stage.target_revision, 'archive_sha256': archive.sha256,
                'source_generation': request.generation, 'source_state': row['state'], 'cli_version': None,
                'cli_identity': None, 'platform': 'antigravity'}
            root = self.executor.data / 'environments' / request.environment_id
            self._publish(request, path, root, intent)
            with self._runtime(request) as runtime:
                current = lookup(runtime, request.account_id)
                if current['state'] in ('starting', 'reconcile'):
                    # 本操作尚未开放目标发送绑定，已核对的半创建角色可以按原环境重建。
                    if runtime._running_sender_active(current):
                        raise ValueError('AGY 未提交目标存在活动发送，需要原操作核对')
                    stop_environment(runtime, current, remove=True)
                binding = transport(runtime, request.account_id, allow_eviction=False, selected_kernel=identity.kernel,
                    import_preparation=True)
                peer = self._prepared(runtime, request, binding)
            prepared = {**intent, 'phase': 'prepared', 'generation': peer['environment']['generation']}
            atomic_json(path / 'published.json', prepared)
            atomic_json(root / 'runtime/node-migration-target.json', prepared)
            return {**peer, 'operation_id': identity.operation_id, 'transfer_id': stage.transfer_id, 'phase': 'prepared'}

    def _publish(self, request, path, root, intent):
        saved = _optional(path / 'publish-intent.json')
        if saved is not None and saved != intent:
            raise ValueError('AGY 原目标发布范围已变化')
        marker = _optional(root / 'runtime/node-migration-target.json')
        publish = not isinstance(marker, dict) or marker.get('operation_id') != intent['operation_id']
        if publish:
            atomic_json(path / 'publish-intent.json', intent)
            if root.exists() or root.is_symlink():
                self.executor._retire_previous(root, path, intent)
            target = path / 'environment'
            os.close(directory_fd(target))
            if request.stage.archive.identity.kernel is not None:
                verify_candidate(target, request.stage.archive.identity.kernel)
            atomic_json(target / 'runtime/node-migration-target.json', {**intent, 'phase': 'published'})
            atomic_json(target / 'runtime/node-assignment.json',
                self._owner(request.account_id, request.environment_id, request.assignment_revision))
            source_parent = directory_fd(path)
            target_parent = directory_fd(root.parent, create=True)
            try:
                os.rename('environment', root.name, src_dir_fd=source_parent, dst_dir_fd=target_parent)
                os.fsync(source_parent)
                os.fsync(target_parent)
            finally:
                os.close(source_parent)
                os.close(target_parent)
        elif (not all(marker.get(key) == value for key, value in intent.items())
                or marker.get('phase') not in ('published', 'prepared')):
            raise ValueError('AGY 运行目录原发布身份已变化')
        self._projection(request, path, intent)

    def _projection(self, request, path, intent):
        marker = path / 'agy-projection.json'
        saved = _optional(marker)
        if saved is not None:
            if saved != intent:
                raise ValueError('AGY 目标投影冻结范围已变化')
            return
        connection = self.executor.database()
        try:
            apply_migrations(connection)
            with connection:
                old = connection.execute('SELECT e.*,p.environment_id AS binding FROM account_environments e '
                    'LEFT JOIN platform_api_environments p ON p.gateway_account_id=? WHERE e.environment_id=?',
                    (request.account_id, request.environment_id)).fetchone()
                previous = (_optional(path / 'retirement.json') or {}).get('previous_fence')
                if old and (old['account_id'] is not None or old['name'] != request.environment['name']
                        or old['binding'] != request.environment_id
                        or previous and old['generation'] > max(request.generation, previous['generation'])
                        or not previous and (old['generation'] > request.generation
                            or any(old[column] for column in ROLE_COLUMNS.values()))):
                    raise ValueError('AGY 原目标投影缺少相符的停止证据')
                row = {'environment_id': request.environment_id, 'account_id': None,
                    'name': request.environment['name'], 'fingerprint_json': request.environment['fingerprint_json'],
                    'generation': max(request.generation, old['generation'] if old else 0,
                        previous['generation'] if previous else 0),
                    'state': 'stopped', 'isolation_version': ISOLATION_VERSION,
                    **{column: None for column in ROLE_COLUMNS.values()}}
                self.executor._project_row(connection, 'account_environments', row, update=True)
                connection.execute('INSERT INTO platform_api_environments(gateway_account_id,environment_id,platform) '
                    "VALUES(?,?,'antigravity') ON CONFLICT(gateway_account_id) DO NOTHING",
                    (request.account_id, request.environment_id))
                linked = connection.execute('SELECT environment_id FROM platform_api_environments WHERE gateway_account_id=?',
                    (request.account_id,)).fetchone()
                if linked[0] != request.environment_id:
                    raise ValueError('AGY 网关账号在目标已绑定另一环境')
        finally:
            connection.close()
        atomic_json(marker, intent)

    def _activate(self, request):
        with self.executor._locked(environment_id=request.environment_id), self._runtime(request) as runtime:
            path = self.executor.data / 'node-migrations' / request.operation_id / 'imports' / request.transfer_id
            if _optional(path.parent.parent / 'revoked.json') is not None:
                raise ValueError('AGY 目标操作已撤销')
            published = _read_json(path / 'published.json')
            expected = request.model_dump()
            row = self._row(runtime, request)
            marker_path = runtime._root(row) / 'runtime/node-migration-target.json'
            marker = _read_json(marker_path)
            if (published.get('platform') != 'antigravity'
                    or any(published.get(key) != value or marker.get(key) != value for key, value in expected.items())
                    or marker.get('phase') not in ('prepared', 'activated')
                    or row['state'] not in ('stopped', 'ready')):
                raise ValueError('AGY 激活范围与已发布身份不一致')
            if published['source_state'] == 'stopped':
                if runtime._running_sender_active(row):
                    raise ValueError('AGY 目标仍有发送活动')
                stop_environment(runtime, row, remove=False)
                for role in ROLE_COLUMNS:
                    container = role_container(runtime, row, role)
                    container.reload()
                    state = container.attrs.get('State', {})
                    if state.get('Running') is not False or state.get('Pid') != 0:
                        raise ValueError('AGY 目标实际停止状态需要核对')
            elif any(status != 'running' for status in runtime.role_status(row).values()):
                raise ValueError('AGY 目标实际角色尚未就绪')
            else:
                runtime._sender_active(row)
            atomic_json(marker_path, {**marker, 'phase': 'activated'})
            return {'protocol': 1, **expected, 'phase': 'activated'}

    def _revoke(self, request):
        identity = request.identity
        if not isinstance(identity, AgyArchiveIdentity) or request.target_revision != identity.assignment_revision + 1:
            raise ValueError('AGY 撤销与原归档范围不一致')
        with self.executor._locked(environment_id=identity.environment_id):
            path = self.files._operation(identity, 'import') / 'revoked.json'
            receipt = {'protocol': 1, 'node_key': self.key, 'operation_id': identity.operation_id,
                'account_id': identity.account_id, 'environment_id': identity.environment_id,
                'revision': request.target_revision, 'phase': 'revoked'}
            saved = _optional(path)
            if saved is not None:
                if saved != receipt:
                    raise ValueError('AGY 原撤销范围已变化')
                return receipt
            root = self.executor.data / 'environments' / identity.environment_id
            marker = _optional(root / 'runtime/node-migration-target.json')
            if marker is not None and marker.get('operation_id') == identity.operation_id:
                if (marker.get('platform') != 'antigravity' or any(marker.get(key) != value
                        for key, value in receipt.items() if key != 'phase')
                        or marker.get('phase') not in ('published', 'prepared', 'revoked')):
                    raise ValueError('AGY 目标已激活，请继续原提交')
                scope = EnvironmentFence(node_key=self.key, operation_id=identity.operation_id,
                    account_id=identity.account_id, environment_id=identity.environment_id,
                    assignment_revision=request.target_revision, generation=marker.get('generation', 0))
                row = lookup(self.executor, identity.account_id) if self.executor.database_path.is_file() else None
                if row and row['environment_id'] == identity.environment_id:
                    with self._runtime(scope) as runtime:
                        scope = scope.model_copy(update={'generation': row['generation']})
                        fence_environment(runtime, row, scope, agy=True)
                elif self.executor._scoped_containers(identity.environment_id):
                    raise ValueError('AGY 撤销存在未登记的实际角色')
                else:
                    # 发布目录之后、登记投影之前中断时也保留已确认的空副本隔离。
                    atomic_json(root / 'runtime/node-fence.json', {'protocol': 1, **scope.model_dump(),
                        'phase': 'fenced', 'stopped_containers': []})
                    atomic_json(root / 'runtime/node-assignment.json', {
                        **self._owner(identity.account_id, identity.environment_id, request.target_revision),
                        'phase': 'fenced', 'operation_id': identity.operation_id})
                atomic_json(root / 'runtime/node-migration-target.json', {**marker, 'phase': 'revoked'})
            elif root.exists() or root.is_symlink():
                self.executor._previous_copy(root, receipt)
            elif self.executor._scoped_containers(identity.environment_id):
                raise ValueError('AGY 目标存在缺少目录的实际角色')
            atomic_json(path, receipt)
            return receipt
