"""节点组件自动换批、持久恢复与原账号停机保护。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import threading
import time
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path

from docker import DockerClient
from docker.errors import NotFound

from account_runtime import RuntimeBusy
from cluster_deployment import image_config_digest, node_container_name
from cluster_execution import NodeInspection
from account_isolation import ROLE_COLUMNS, ROLE_LABELS
from cluster_environment import EnvironmentFence
from cluster_image_cleanup import cleanup_node_images
from cluster_migration_errors import MigrationFailure
from cluster_migrations import pristine_target_migration
from cluster_migration_maintenance import paused_migration_lease, paused_migration_record
from cluster_node_recovery import RESTORE_NODE_DATA
from cluster_profile_reader import profile_reader_source
from cluster_execution_store import NodeExecutions
from runtime_files import atomic_json, private_directory
from system_update_gate import UPDATE_GATE


class NodeSynchronizationWait(RuntimeBusy):
    """节点同步等待实际活动收口，保留原任务供后台重试。"""


class NodeSynchronization:
    """在原节点归属下协调组件换批。:param service: 中央节点服务。:param runtime: 原运行时。:param gateway: 网关。:param quota: 原额度身份读取器。"""

    def __init__(self, service, runtime, gateway, quota, version=None) -> None:
        """保存原运行依赖。:param service: 节点服务。:param runtime: 原运行时。:param gateway: 原网关。:param quota: 身份读取。:param version: CLI版本读取。:return: None。"""
        self.service, self.runtime, self.gateway, self.quota = service, runtime, gateway, quota
        self.version = version
        self.boot_id = uuid.uuid4().hex
        self.image_proofs = {}
        self.cancelled_platforms = set()
        self.stopping = threading.Event()
        self.slots = threading.BoundedSemaphore(2)
        self.thread = threading.Thread(target=self._watch, name='cluster-node-sync', daemon=True)

    def start(self) -> None:
        """启动已托管节点的目标批次核对。:return: None。"""
        self.thread.start()

    def close(self) -> None:
        """停止新同步，保留原私有日志。:return: None。"""
        self.stopping.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def _watch(self) -> None:
        while not self.stopping.is_set():
            try:
                self.service.resume_removals()
                self.synchronize()
                self._cleanup_ready_nodes()
            except Exception:
                # 单个不可用节点的实际原因由各自安装作业持久化，扫描不会影响其他节点。
                pass
            self.stopping.wait(15)

    def _cleanup_ready_nodes(self) -> None:
        if UPDATE_GATE.state()['phase'] != 'idle':
            return
        for row in self.service.store.list():
            saved = row.get('preparation') or {}
            if self.stopping.is_set():
                return
            if row['kind'] != 'ssh' or row.get('removal') or saved.get('state') != 'prepared' or saved.get('release') != self.runtime.release_id:
                continue
            with self.service.lock:
                lock = self.service.operation_locks.setdefault(row['id'], threading.Lock())
            if not lock.acquire(blocking=False):
                continue
            try:
                current = self.service.store.get(row['id'])
                if current['revision'] != row['revision']:
                    continue
                with UPDATE_GATE.admission('cluster-node-image-cleanup'):
                    cleanup_node_images(self.service, row['id'], self.runtime.deployment, self.runtime.release_id)
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                # 原维护目录暂不可读或平台正在切换时，保留原证据供下次扫描。
                continue
            finally:
                lock.release()

    def synchronize(self, *, explicit: bool = False) -> list[dict]:
        """提交当前目标的节点后台同步。

        :param explicit: 管理员显式统一同步，包含首次节点。
        :return: 当前公开节点状态。
        """
        gate = UPDATE_GATE.state()
        for row in self.service.store.list():
            saved = row.get('preparation') or {}
            if row['kind'] != 'ssh' or row.get('removal') or self.stopping.is_set():
                continue
            managed = bool(saved.get('release') or saved.get('target_release') or row.get('account_count'))
            due = saved.get('retry_at', 0) <= time.time()
            needed = saved.get('release') != self.runtime.release_id or saved.get('state') != 'prepared'
            if not explicit and (not managed or not due or not needed):
                continue
            try:
                maintenance = None
                if gate.get('phase') == 'blocked':
                    path = self.service.connection(row['id']).private / 'maintenance/current.json'
                    if not path.exists():
                        continue
                    job = json.loads(path.read_text())
                    if (job.get('phase') in ('rolled_back', 'platform_restored')
                            or job.get('target_release') != self.runtime.release_id
                            or job.get('resume_boot_id') != self.boot_id):
                        continue
                    if (job.get('platform_operation') != gate.get('operation_id')
                            or job.get('platform_epoch') != gate.get('epoch')):
                        continue
                    maintenance = {'operation_id': gate['operation_id'], 'epoch': gate['epoch']}
                if maintenance is None:
                    self.service.prepare_node(row['id'], row['revision'], automatic=True)
                else:
                    self.service.prepare_node(row['id'], row['revision'], automatic=True, maintenance=maintenance)
            except (ValueError, RuntimeError, OSError):
                continue
        return self.service.store.list()

    def status(self, node_id: int, revision: int, phase: str, *, reason: str | None = None,
               current_release: str | None = None) -> None:
        """持久保存公开阶段，原接单偏好独立保留。

        :param node_id: 原节点。
        :param revision: 原配置版本。
        :param phase: 当前步骤。
        :param reason: 固定说明。
        :param current_release: 已核对原批次。
        :return: None。
        """
        previous = self.service.store.get(node_id)
        previous = json.loads(previous['preparation_json']) if previous['preparation_json'] else {}
        state = {'state': 'preparing', 'phase': phase, 'target_release': previous.get('target_release') or self.runtime.release_id,
            'original_preparation': previous.get('original_preparation') or previous,
            'current_release': current_release}
        if reason:
            state['reason'] = reason
        if not self.service.store.save_preparation(node_id, revision, state):
            raise ValueError('节点同步期间配置已变化')

    def _historical_environment(self, node, control: str, node_id: int, environment_id: str) -> bool:
        """核对终态迁移留下的停止副本。:param node: SSH连接。:param control: 原控制容器。:param node_id: 当前节点。:param environment_id: 历史环境。:return: 收据及实际停止证明是否一致。"""
        if not isinstance(environment_id, str) or not re.fullmatch('[a-f0-9]{32}', environment_id):
            return False
        connection = self.service.store.database()
        try:
            pending = [dict(value) for value in connection.execute("SELECT * FROM node_migrations "
                "WHERE (source_node_id=? OR target_node_id=?) AND phase='reconcile'", (node_id, node_id))]
        finally:
            connection.close()
        for migration in pending:
            record = paused_migration_record(migration)
            if record and record.get('environment_id') == environment_id:
                if self._paused_environment(migration, node_id):
                    return True
        script = ('import json,sys;from pathlib import Path;from account_runtime import _read_json;'
            'v=json.load(sys.stdin);print(json.dumps(_read_json(Path(v["root"])/"environments"/v["environment_id"]/"runtime/node-fence.json")))')
        try:
            fence = json.loads(node._command(shlex.join(['docker', 'exec', '-i', control, 'python3', '-c', script]),
                data=json.dumps({'root': '/data', 'environment_id': environment_id}).encode(), timeout=15, maximum_output=16384))
            connection = self.service.store.database()
            try:
                stored = connection.execute("SELECT * FROM node_migrations WHERE operation_id=? AND "
                    "((source_node_id=? AND phase='completed') OR (target_node_id=? AND phase='cancelled'))",
                    (fence.get('operation_id'), node_id, node_id)).fetchone()
            finally:
                connection.close()
            if stored is None:
                return False
            record = json.loads(stored['record_json'])
            if not (fence.get('phase') == 'fenced' and fence.get('environment_id') == environment_id
                and fence.get('account_id') == stored['account_id'] and record.get('environment_id') == environment_id
                and fence.get('node_key') == node.node_key):
                return False
            if stored['phase'] == 'completed':
                return (fence.get('generation') == record.get('source_generation')
                    and fence.get('assignment_revision') == record.get('source_revision'))
            # 取消会保留已停止的目标及资料，中央零归属不表示这些副本缺少所有者。
            revision = record['source_revision'] + 1
            receipt = {'operation_id': stored['operation_id'], 'account_id': stored['account_id'],
                'environment_id': environment_id, 'revision': revision, 'phase': 'revoked'}
            if (record.get('last_confirmed_phase') != 'cancelled'
                    or record.get('receipts', {}).get('target_revoked') != {**receipt, 'node_id': node_id}
                    or fence.get('assignment_revision') != revision):
                return False
            script = ('import json,sys;from pathlib import Path;from account_runtime import _read_json;'
                'v=json.load(sys.stdin);p=Path(v["root"]);print(json.dumps({'
                '"target":_read_json(p/"environments"/v["environment_id"]/"runtime/node-migration-target.json"),'
                '"revoked":_read_json(p/"node-migrations"/v["operation_id"]/"revoked.json")}))')
            proof = json.loads(node._command(shlex.join(['docker', 'exec', '-i', control, 'python3', '-c', script]),
                data=json.dumps({'root': '/data', 'environment_id': environment_id, 'operation_id': stored['operation_id']}).encode(),
                timeout=15, maximum_output=16384))
            expected = {**receipt, 'protocol': 1, 'node_key': node.node_key}
            if (not isinstance(proof, dict) or not isinstance(proof.get('target'), dict)
                    or proof.get('revoked') != expected
                    or any(proof['target'].get(key) != value for key, value in {
                        **expected, 'source_generation': record['source_generation']}.items())):
                return False
            labels = ['vibebench.product=v3', 'vibebench.deployment=' + self.runtime.deployment,
                'vibebench.cluster-node=' + node.node_key, 'vibebench.environment=' + environment_id]
            stopped = fence.get('stopped_containers')
            if not isinstance(stopped, list) or not all(isinstance(value, str) for value in stopped):
                return False
            for container in self.service.docker(node_id).containers.list(all=True, filters={'label': labels}):
                container.reload()
                state = container.attrs.get('State', {})
                if (container.id not in stopped or container.labels.get('vibebench.role') not in ROLE_LABELS.values()
                        or state.get('Running') is not False or state.get('Pid') != 0):
                    return False
            return True
        except (ValueError, OSError, RuntimeError):
            return False

    def _paused_environment(self, migration: dict, node_id: int) -> bool:
        record = paused_migration_record(migration)
        if record is None:
            return False
        node = self.service.store.get(node_id)
        environment_id = record.get('environment_id')
        if not isinstance(environment_id, str) or not re.fullmatch('[a-f0-9]{32}', environment_id):
            return False
        connection = self.service.store.database()
        try:
            environment = connection.execute('SELECT * FROM account_environments WHERE account_id=?',
                (migration['account_id'],)).fetchone()
            account = connection.execute('SELECT cc2api_account_id FROM accounts WHERE id=?',
                (migration['account_id'],)).fetchone()
        finally:
            connection.close()
        if (environment is None or account is None or self.service.transports.account_streams(migration['account_id'])
                or NodeExecutions(self.service.store, self.runtime.release_id).active(migration['account_id'])):
            return False
        owner = getattr(self.runtime, 'credential_ownership', None)
        if owner:
            state = owner.state(migration['account_id'])
            if state and (state.get('phase') != 'ready' or state.get('refresh_pending') or state.get('gateway_refresh_pending')):
                return False
        lease = (self.gateway._request('GET', f'/admin/runtime/accounts/{account["cc2api_account_id"]}/lease')
            if account['cc2api_account_id'] is not None else {'active': 0, 'waiting': 0, 'importing': 0, 'holders': []})
        if paused_migration_lease(self.service.store.database, dict(environment), lease) is None:
            return False
        source = migration['source_node_id'] == node_id
        config = json.loads(node['config_json'])
        expected = {'operation_id': migration['operation_id'], 'environment_id': environment_id,
            'account_id': migration['account_id'], 'node_key': node['node_key']}
        if source:
            expected.update(phase='fenced', generation=record['source_generation'], assignment_revision=record['source_revision'])
        else:
            expected.update(revision=record['source_revision'] + 1, source_generation=record['source_generation'])
        script = '''import json,os,sys
from pathlib import Path
value=json.load(sys.stdin)
root=Path(value['root'])/'environments'/value['expected']['environment_id']
valid=not value['source'] and not root.exists() and not root.is_symlink()
if root.is_dir() and not root.is_symlink():
    path=root/'runtime'/('node-fence.json' if value['source'] else 'node-migration-target.json')
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
        marker=json.loads(stream.read(16385))
    valid=all(marker.get(key)==item for key,item in value['expected'].items())
    if not value['source']:
        valid=valid and marker.get('phase') in ('published','prepared')
print(json.dumps({'paused':valid,'environment':root.exists()}))
'''
        proof = json.loads(self.service.connection(node_id)._command('python3 -c ' + shlex.quote(script),
            data=json.dumps({'root': config['data_root'], 'source': source, 'expected': expected}).encode(),
            timeout=15, maximum_output=1024))
        if proof.get('paused') is not True:
            return False
        labels = ['vibebench.product=v3', 'vibebench.deployment=' + self.runtime.deployment,
            'vibebench.cluster-node=' + node['node_key'], 'vibebench.environment=' + environment_id]
        containers = self.service.docker(node_id).containers.list(all=True, filters={'label': labels})
        if containers and proof.get('environment') is not True:
            return False
        if source and {container.id for container in containers} != {
                environment[column] for column in ROLE_COLUMNS.values() if environment[column]}:
            return False
        for container in containers:
            container.reload()
            state = container.attrs.get('State', {})
            if (container.labels.get('vibebench.role') not in ROLE_LABELS.values()
                    or state.get('Running') is not False or state.get('Pid') != 0):
                return False
        return True

    def _rows(self, node_id: int) -> list[dict]:
        connection = self.service.store.database()
        try:
            migrations = [dict(value) for value in connection.execute("SELECT * FROM node_migrations WHERE (source_node_id=? OR target_node_id=?) "
                "AND phase NOT IN ('completed','cancelled')", (node_id, node_id))]
            paused = [value for value in migrations if paused_migration_record(value) is not None
                and self._paused_environment(value, node_id)]
            migrations = [value for value in migrations if value not in paused]
            if any(not pristine_target_migration(value, node_id) for value in migrations):
                raise NodeSynchronizationWait('节点仍有源或目标迁移，请先完成原迁移')
            if migrations:
                node = self.service.connection(node_id)
                name = node_container_name(self.runtime.deployment, self.service.store.get(node_id)['node_key'])
                script = ('import json,sys;from pathlib import Path;v=json.load(sys.stdin);'
                    'print(json.dumps({"pristine":all(not (Path("/data/node-migrations")/op).exists() '
                    'and not (Path("/data/node-migrations")/op).is_symlink() for op in v["operations"])}))')
                observed = json.loads(node._command(shlex.join(['docker', 'exec', '-i', name, 'python3', '-c', script]),
                    data=json.dumps({'operations': [value['operation_id'] for value in migrations]}).encode(),
                    timeout=15, maximum_output=1024))
                if observed != {'pristine': True}:
                    raise NodeSynchronizationWait('原迁移目标已有暂存资料，请完成原操作后同步')
            if connection.execute("SELECT 1 FROM node_login_drafts WHERE node_id=? AND phase<>'closed' LIMIT 1",
                    (node_id,)).fetchone():
                raise NodeSynchronizationWait('节点仍有登录草稿或未确认授权，请先收口原操作')
            accounts = [dict(row) for row in connection.execute('SELECT a.*,b.revision AS assignment_revision,b.phase AS assignment_phase '
                'FROM accounts a JOIN account_node_assignments b ON b.account_id=a.id WHERE b.node_id=?', (node_id,))]
            result = []
            for account in accounts:
                if any(value['account_id'] == account['id'] for value in paused):
                    # 已暂停的源保持原隔离和租约；只换组件并原地保留资料，不重建或激活该账号。
                    continue
                environment = connection.execute('SELECT * FROM account_environments WHERE account_id=?', (account['id'],)).fetchone()
                if environment is not None:
                    result.append({'account': account, 'environment': dict(environment)})
        finally:
            connection.close()
        for item in result:
            account = item['account']
            if (account['assignment_phase'] != 'ready' or self.service.transports.account_streams(account['id'])
                    or NodeExecutions(self.service.store, self.runtime.release_id).active(account['id'])):
                raise NodeSynchronizationWait('节点仍有已登记工作或连接，正在等待原工作完成')
            owner = getattr(self.runtime, 'credential_ownership', None)
            if owner and account.get('deleted_at') is None:
                state = owner.state(account['id'])
                if state and (state.get('phase') != 'ready' or state.get('refresh_pending') or state.get('gateway_refresh_pending')):
                    raise NodeSynchronizationWait('节点账号仍有凭据交接或刷新待确认')
        return result

    def _check_platform(self, job: dict) -> None:
        gate = UPDATE_GATE.state()
        peer = self.gateway._request('GET', '/admin/runtime/system-update/status')
        if (self.stopping.is_set() or gate.get('phase') != 'blocked' or peer.get('phase') != 'blocked' or peer.get('active') != 0
                or gate.get('operation_id') != job['platform_operation'] or peer.get('operation_id') != job['platform_operation']
                or gate.get('epoch') != job['platform_epoch'] or peer.get('epoch') != job['platform_epoch']):
            raise NodeSynchronizationWait('节点平台维护的原门禁或代次已变化')

    @contextmanager
    def _lease(self, account: dict, job: dict):
        if job.get('platform_operation'):
            self._check_platform(job)
            yield lambda: self._check_platform(job)
            return
        remote_id = account.get('cc2api_account_id')
        if remote_id is None:
            yield lambda: None
            return
        path = f'/admin/runtime/accounts/{remote_id}/lease'
        owner = 'node-sync:' + job['job_id'] + ':' + str(account['id'])
        proof = job.setdefault('leases', {}).get(str(account['id']))
        snapshot = self.gateway._request('GET', path)
        holders = snapshot.get('holders')
        if holders:
            if (proof is None or len(holders) != 1 or any(holders[0].get(key) != proof[key] for key in ('owner', 'generation'))
                    or snapshot.get('active') != 0):
                raise NodeSynchronizationWait('节点账号仍有API或原租约，等待原工作收口')
            self.gateway._request('POST', path, {'operation': 'release', **proof})
        snapshot = self.gateway._request('POST', path, {'operation': 'prepare', 'owner': owner})
        holders = snapshot.get('holders')
        if not isinstance(holders, list) or len(holders) != 1 or holders[0].get('owner') != owner:
            raise NodeSynchronizationWait('节点API排空尚未确认，继续等待')
        proof = {key: holders[0][key] for key in ('owner', 'generation')}
        job['leases'][str(account['id'])] = proof
        self._save(job)
        if snapshot.get('active') != 0 or snapshot.get('importing') != 0:
            raise NodeSynchronizationWait('节点API排空尚未确认，继续等待')
        self.gateway._request('POST', path, {'operation': 'claim', **proof})
        stopped, failed = threading.Event(), threading.Event()

        def heartbeat():
            while not stopped.wait(5):
                try:
                    current = self.gateway._request('POST', path, {'operation': 'heartbeat', **proof})
                    if not any(all(item.get(key) == value for key, value in proof.items()) for item in current.get('holders', [])):
                        failed.set()
                        return
                except Exception:
                    failed.set()
                    return

        def check():
            if failed.is_set() or self.stopping.is_set():
                raise NodeSynchronizationWait('节点维护租约已中断，原资料保留待核对')

        thread = threading.Thread(target=heartbeat, name='cluster-node-sync-lease', daemon=True)
        thread.start()
        try:
            yield check
        finally:
            stopped.set()
            thread.join(timeout=10)
            # 未确认停止的故障保留原租约；下次按原代次核对后收口。
            if not failed.is_set() and not thread.is_alive():
                self.gateway._request('POST', path, {'operation': 'release', **proof})

    def _save(self, job: dict) -> None:
        atomic_json(Path(job['journal']), job)

    def install(self, installer, node_id: int, revision: int, *, maintenance: dict | None = None, stage_only: bool = False, late_restore: bool = False) -> dict:
        """自动识别同批、首次与需要换批的节点并执行原恢复流程。

        :param installer: 同批安装器。
        :param node_id: 原节点。
        :param revision: 冻结配置版本。
        :return: 健康安装回执。
        """
        with self.slots:
            if (stage_only and maintenance is not None
                    and (maintenance['operation_id'], maintenance['epoch']) in self.cancelled_platforms):
                raise NodeSynchronizationWait('平台取消已登记，原节点状态保持')
            previous = self.service.store.get(node_id)
            saved = json.loads(previous['preparation_json']) if previous['preparation_json'] else {}
            self.status(node_id, revision, 'checking', current_release=saved.get('release') or saved.get('current_release'))
            row = self.service.store.get(node_id)
            node = self.service.connection(node_id)
            remote = self.service.docker(node_id)
            name = node_container_name(self.runtime.deployment, row['node_key'])
            try:
                control = remote.containers.get(name)
            except NotFound:
                control = None
            directory = node.private / 'maintenance'
            private_directory(directory)
            journal = directory / 'current.json'
            job = json.loads(journal.read_text()) if journal.exists() else None
            if job and job.get('phase') in ('completed', 'rolled_back'):
                job = None
            if job and job.get('phase') == 'rolling_back_control':
                self._rollback_control(remote, node, name, job)
                raise NodeSynchronizationWait('原组件已恢复，正在等待重试本次同步')
            if control is None or control.labels.get('vibebench.release') == installer.release:
                if job is None and not stage_only:
                    return installer.prepare(node_id, revision)
            if job is None:
                if journal.exists():
                    previous_job = json.loads(journal.read_text())
                    atomic_json(directory / (previous_job['job_id'] + '.json'), previous_job)
                control.reload()
                expected = {'vibebench.product': 'v3', 'vibebench.deployment': self.runtime.deployment,
                    'vibebench.cluster-node': row['node_key'], 'vibebench.role': 'node-control'}
                mounts = [value for value in control.attrs.get('Mounts', []) if value.get('Destination') == '/data']
                config = json.loads(row['config_json'])
                if (any(control.labels.get(key) != value for key, value in expected.items()) or len(mounts) != 1
                        or mounts[0].get('Source') != config['data_root'] or mounts[0].get('RW') is not True):
                    raise ValueError('原节点控制组件归属或数据挂载需要核对')
                job = {'job_id': uuid.uuid4().hex, 'node_id': node_id, 'node_key': row['node_key'],
                    'config_sha256': hashlib.sha256(row['config_json'].encode()).hexdigest(), 'revision': revision,
                    'target_release': installer.release, 'old_release': control.labels['vibebench.release'],
                    'old_container': control.id, 'old_image': control.attrs['Image'], 'old_running': control.status == 'running',
                    'phase': 'draining', 'journal': str(journal), 'fences': {}, 'accounts': [], 'late_restore': late_restore,
                    'data_policy': 'in_place',
                    'preparation_before': saved.get('original_preparation') or saved}
                if maintenance is not None:
                    job.update(platform_operation=maintenance['operation_id'], platform_epoch=maintenance['epoch'])
                job['backup_epoch'] = uuid.UUID(job['platform_epoch']).hex if job.get('platform_epoch') else job['job_id']
                atomic_json(directory / (job['job_id'] + '-container.json'), control.attrs)
                self._save(job)
            if (job['node_key'] != row['node_key'] or job['target_release'] != installer.release
                    or job['config_sha256'] != hashlib.sha256(row['config_json'].encode()).hexdigest()):
                raise ValueError('原节点维护目标或配置已变化，请核对原任务')
            if job.get('platform_operation'):
                self._check_platform(job)
            with ExitStack() as leases:
                checks = []
                if job['phase'] == 'draining':
                    self.status(node_id, revision, 'draining', current_release=job['old_release'])
                    accounts = self._rows(node_id)
                    job['accounts'] = accounts
                    self._save(job)
                    for item in accounts:
                        checks.append(leases.enter_context(self._lease(item['account'], job)))
                    for item in accounts:
                        account, environment = item['account'], item['environment']
                        if environment['generation'] == 0 or environment['state'] == 'retired' or account.get('deleted_at') is not None:
                            continue
                        if str(account['id']) not in job.get('cli_identities', {}):
                            if self.version is None:
                                raise ValueError('节点维护缺少原CLI身份核验配置')
                            version = self.version(account)
                            identity = self._cli_identity(node, name, environment, version)
                            job.setdefault('cli_identities', {})[str(account['id'])] = {'version': version, 'identity': identity}
                            self._save(job)
                        scope = EnvironmentFence(operation_id=job['job_id'], node_key=row['node_key'], account_id=account['id'],
                            environment_id=environment['environment_id'], assignment_revision=account['assignment_revision'],
                            generation=environment['generation'])
                        for check in checks:
                            check()
                        try:
                            receipt = node.fence_environment(name, scope.model_dump())
                        except MigrationFailure as error:
                            if error.code == 'busy':
                                raise NodeSynchronizationWait('节点仍有实际工作或凭据维护，等待原操作完成') from None
                            raise
                        if receipt.get('phase') != 'fenced' or receipt.get('operation_id') != job['job_id']:
                            raise NodeSynchronizationWait('节点原角色实际停止回执需要核对')
                        job['fences'][str(account['id'])] = scope.model_dump()
                        self._save(job)
                    job['phase'] = 'fenced'
                    self._save(job)
                if not checks:
                    for item in job['accounts']:
                        checks.append(leases.enter_context(self._lease(item['account'], job)))
                for check in checks:
                    check()
                self.status(node_id, revision, 'stopping', current_release=job['old_release'])
                if job['phase'] == 'fenced':
                    labels = {'vibebench.product': 'v3', 'vibebench.deployment': self.runtime.deployment,
                        'vibebench.cluster-node': row['node_key']}
                    containers = remote.containers.list(all=True, filters={'label': [key + '=' + value for key, value in labels.items()]})
                    programs = remote.containers.list(filters={'label': ['vibebench.project-verifier=native', 'vibebench.node-key=' + row['node_key']]})
                    if programs:
                        raise NodeSynchronizationWait('节点仍有独立验收容器，等待原验收完成')
                    known = {item['environment']['environment_id'] for item in job['accounts']}
                    fenced = {item['environment']['environment_id'] for item in job['accounts']
                        if str(item['account']['id']) in job['fences']}
                    for container in containers:
                        if container.id != job['old_container'] and container.labels.get('vibebench.environment') not in known:
                            container.reload()
                            environment_id = container.labels.get('vibebench.environment')
                            if (container.attrs.get('State', {}).get('Running') is not False
                                    or container.attrs.get('State', {}).get('Pid') != 0
                                    or not self._historical_environment(node, name, node_id, environment_id)):
                                raise NodeSynchronizationWait('节点存在未核对归属的运行角色，请先对账')
                            known.add(environment_id)
                            job.setdefault('historical_environments', []).append(environment_id)
                            self._save(job)
                        if container.id != job['old_container'] and container.labels.get('vibebench.environment') not in fenced:
                            container.reload()
                            if container.attrs.get('State', {}).get('Running') is not False or container.attrs.get('State', {}).get('Pid') != 0:
                                raise NodeSynchronizationWait('历史环境仍有实际角色，等待原退休操作完成')
                    for container in sorted(containers, key=lambda item: item.id == job['old_container']):
                        container.stop(timeout=5)
                        container.reload()
                        if container.attrs.get('State', {}).get('Running') is not False or container.attrs.get('State', {}).get('Pid') != 0:
                            raise NodeSynchronizationWait('节点角色停止尚未确认')
                    # 旧版本中断时可能留下独立复制进程，先按原作业停止，避免继续占盘。
                    try:
                        helper = remote.containers.get('flower-node-backup-' + job['job_id'][:24])
                    except NotFound:
                        helper = None
                    if helper is not None:
                        helper.reload()
                        if (helper.labels.get('flower.maintenance.job') != job['job_id']
                                or helper.attrs['Image'] != job['old_image']):
                            raise ValueError('节点原备份进程归属不一致')
                        helper.stop(timeout=5)
                        helper.reload()
                        if helper.attrs.get('State', {}).get('Running') is not False or helper.attrs.get('State', {}).get('Pid') != 0:
                            raise NodeSynchronizationWait('节点原备份进程尚未确认停止')
                        helper.remove()
                    job['data_policy'] = 'in_place'
                    # backed_up沿用已安装宿主的排空完成回执；原地模式只保留小型作业日志。
                    job['phase'] = 'backed_up'
                    self._save(job)
                for check in checks:
                    check()
                if self.stopping.is_set():
                    raise NodeSynchronizationWait('节点服务正在关闭，原同步资料已保留')
                if stage_only:
                    if job['phase'] != 'backed_up':
                        raise ValueError('节点平台停止阶段尚未完成')
                    return {'state': 'preparing', 'phase': 'waiting_for_platform',
                        'current_release': job['old_release'], 'target_release': installer.release}
                if job['phase'] == 'backed_up':
                    original = remote.containers.get(job['old_container'])
                    original.rename(name + '-previous-' + job['job_id'][:8])
                    job['phase'] = 'switching'
                    self._save(job)
                self.status(node_id, revision, 'switching', current_release=job['old_release'])
                try:
                    result = installer.prepare(node_id, revision)
                except Exception:
                    self._rollback_control(remote, node, name, job)
                    raise
                self.status(node_id, revision, 'restoring', current_release=installer.release)
                job['phase'] = 'restoring'
                self._save(job)
                self._restore_accounts(node, name, job)
                try:
                    remote.containers.get(job['old_container']).remove()
                except NotFound:
                    pass
                job['phase'] = 'completed'
                self._save(job)
                return {**result, 'phase': 'ready', 'current_release': installer.release, 'target_release': installer.release}

    def _cli_identity(self, node, name: str, environment: dict, version: str) -> dict:
        script = profile_reader_source() + ('import json,sys;from pathlib import Path;from account_runtime import read_cli_identity_at;'
            'v=json.load(sys.stdin);print(json.dumps(read_cli_identity_at(Path("/data/environments")/v["environment_id"],'
            'Path("/data/profiles")/v["name"],v["version"])))')
        command = shlex.join(['docker', 'exec', '-i', name, 'python3', '-c', script])
        value = json.loads(node._command(command, data=json.dumps({'environment_id': environment['environment_id'],
            'name': environment['name'], 'version': version}).encode(), timeout=20, maximum_output=8192))
        if not isinstance(value, dict) or set(value) != {'device_id', 'account_uuid', 'source'}:
            raise ValueError('节点CLI身份回执格式无效')
        return value

    def _restore_accounts(self, node, name: str, job: dict, *, preserve: bool = True) -> None:
        for item in job['accounts']:
            account, environment = item['account'], item['environment']
            scope = job['fences'].get(str(account['id']))
            if scope and str(account['id']) not in job.get('source_restored', []):
                node.migration_environment(name, scope, 'restore-source')
                job.setdefault('source_restored', []).append(str(account['id']))
                self._save(job)
            frozen_identity = job.get('cli_identities', {}).get(str(account['id']))
            if frozen_identity and self._cli_identity(node, name, environment, frozen_identity['version']) != frozen_identity['identity']:
                raise ValueError('节点恢复后的原CLI设备或账号身份不一致')
            if environment['state'] != 'ready' or account.get('deleted_at') is not None:
                continue
            control = self.service.docker(job['node_id']).containers.get(name)
            values = dict(value.split('=', 1) for value in control.attrs['Config'].get('Env', []) if '=' in value)
            selected_release = values.get('V3_ACCOUNT_RELEASE') or values.get('V3_RELEASE')
            if not selected_release:
                raise ValueError('节点恢复缺少实际账号镜像来源')
            if preserve and scope and self.service.preparation_capabilities(job['node_id'], name)['restart']:
                selected = self.service.docker(job['node_id']).images.get(values['V3_ACCOUNT_IMAGE'])
                node.migration_environment(name, {**scope, 'expected_image_id': selected.id}, 'restart-preserved')
            projected = {key: value for key, value in account.items() if key not in ('assignment_revision', 'assignment_phase')}
            request = self.service.build_preparation(projected, environment, job['node_key'], account['assignment_revision'],
                self.runtime, self.gateway, self.quota(account), cli_only=account.get('cc2api_account_id') is None)
            peer = self.service.deliver_preparation(job['node_id'], name, request, operation_id=job['job_id'])
            if frozen_identity and self._cli_identity(node, name, environment, frozen_identity['version']) != frozen_identity['identity']:
                raise ValueError('节点准备后原CLI设备或账号身份不一致')
            assignment = self.service.store.assignment(account['id'])
            if assignment['node_id'] != job['node_id'] or assignment['revision'] != account['assignment_revision']:
                raise ValueError('节点恢复期间原账号归属已变化')
            self.service._adopt_remote(account, environment, assignment, self.service.store.get(job['node_id']), peer,
                self.runtime, self.gateway, cli_only=account.get('cc2api_account_id') is None, maintenance=True,
                expected_release=selected_release)

    def _rollback_control(self, remote, node, name: str, job: dict) -> None:
        try:
            helper = remote.containers.get('flower-node-backup-' + job['job_id'][:24])
        except NotFound:
            helper = None
        if helper is not None:
            helper.reload()
            if helper.labels.get('flower.maintenance.job') != job['job_id'] or helper.attrs['Image'] != job['old_image']:
                raise ValueError('原节点备份进程身份需要核对')
            if helper.attrs.get('State', {}).get('Running') is True:
                raise NodeSynchronizationWait('原节点备份仍在收口，完成后恢复原组件')
        job['phase'] = 'rolling_back_control'
        self._save(job)
        original = remote.containers.get(job['old_container'])
        try:
            candidate = remote.containers.get(name)
        except NotFound:
            candidate = None
        if candidate is not None and candidate.id != original.id:
            if (candidate.labels.get('vibebench.cluster-node') != job['node_key']
                    or candidate.labels.get('vibebench.release') != job['target_release']):
                raise ValueError('节点回退发现不同归属的候选组件')
            candidate.stop(timeout=5)
            candidate.reload()
            if candidate.attrs.get('State', {}).get('Running') is not False:
                raise ValueError('候选控制组件尚未确认停止')
            candidate.remove()
        original.reload()
        if original.name != name:
            original.rename(name)
        if job['old_running'] or job['accounts']:
            original.start()
            deadline = time.monotonic() + 20
            while True:
                try:
                    health = node.agent_health(name)
                    if health.get('release') != job['old_release'] or health.get('node_key') != job['node_key']:
                        raise ValueError('原节点控制组件身份不一致')
                    break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.2)
            self._restore_accounts(node, name, job, preserve=False)
        job['phase'] = 'rolled_back'
        self._save(job)

    def recover_original(self, node_id: int) -> None:
        """在账号恢复前的失败中恢复原控制和角色。

        :param node_id: 原节点。
        :return: None；已开始恢复新账号的操作保留新现场继续核对。
        """
        row = self.service.store.get(node_id)
        node = self.service.connection(node_id)
        path = node.private / 'maintenance/current.json'
        if not path.exists():
            return
        job = json.loads(path.read_text())
        if job['phase'] not in ('draining', 'fenced', 'backed_up', 'switching', 'rolling_back_control'):
            return
        if (job['node_key'] != row['node_key']
                or job['config_sha256'] != hashlib.sha256(row['config_json'].encode()).hexdigest()):
            raise ValueError('原节点回退连接归属已变化')
        self._rollback_control(self.service.docker(node_id), node,
            node_container_name(self.runtime.deployment, row['node_key']), job)

    def environment_snapshot(self, row: dict, account: dict, *, quiescent: bool = True) -> dict:
        """核对远程实际角色和执行占用，供原宿主排空与健康验收。

        :param row: 中央当前环境。
        :param account: 中央原账号。
        :param quiescent: 冻结维护快照时另核对工作与租约排空。
        :return: 原快照格式的远程事实，秘密保持在节点内部。
        """
        if account.get('deleted_at') is not None and row['state'] == 'retired' and not any(row.get(column) for column in ROLE_COLUMNS.values()):
            return {**{key: row.get(key) for key in ('environment_id', 'generation', 'state', 'name', 'account_id')},
                'node_kind': 'ssh', 'roles': {}, 'origin': None, 'blockers': []}
        assignment = self.service.store.assignment(account['id'])
        node_row = self.service.store.get(assignment['node_id'])
        connection = self.service.store.database()
        try:
            pending = connection.execute("SELECT * FROM node_migrations WHERE account_id=? AND phase='reconcile'",
                (account['id'],)).fetchone()
        finally:
            connection.close()
        paused = pending is not None and self._paused_environment(dict(pending), node_row['id'])
        saved = json.loads(node_row['preparation_json']) if node_row['preparation_json'] else {}
        staged = False
        if saved.get('state') != 'prepared':
            path = self.service.connection(node_row['id']).private / 'maintenance/current.json'
            job = json.loads(path.read_text()) if path.exists() else {}
            gate = UPDATE_GATE.state()
            staged = (quiescent and job.get('phase') == 'backed_up' and gate.get('phase') == 'blocked'
                and job.get('platform_operation') == gate.get('operation_id') and job.get('platform_epoch') == gate.get('epoch')
                and job.get('node_key') == node_row['node_key']
                and job.get('config_sha256') == hashlib.sha256(node_row['config_json'].encode()).hexdigest())
            if not staged:
                raise NodeSynchronizationWait('节点组件正在同步或等待原任务核对')
            control = self.service.docker(node_row['id']).containers.get(job['old_container'])
            control.reload()
            if control.attrs.get('State', {}).get('Running') is not False or control.attrs.get('State', {}).get('Pid') != 0:
                raise NodeSynchronizationWait('已备份原节点的控制组件重新出现活动')
            self._check_platform(job)
            self._rows(node_row['id'])
        peer = None
        if quiescent and not staged and not paused:
            self._rows(node_row['id'])
            if self.version is None:
                raise ValueError('节点快照缺少原CLI版本选择器')
            node = self.service.connection(node_row['id'])
            request = NodeInspection(node_key=node_row['node_key'], account_id=account['id'], environment_id=row['environment_id'],
                assignment_revision=assignment['revision'], version=self.version(account))
            peer = node.prepare_environment(node_container_name(self.runtime.deployment, node_row['node_key']), request.model_dump(), inspect=True)
            if (peer.get('environment_id') != row['environment_id'] or peer.get('account_id') != account['id']
                    or peer.get('generation') != row['generation'] or peer.get('busy') is not False):
                raise NodeSynchronizationWait('节点实际代次或持久执行登记仍需收口')
            if account.get('cc2api_account_id') is not None:
                lease = self.gateway._request('GET', f'/admin/runtime/accounts/{account["cc2api_account_id"]}/lease')
                if lease.get('active') or lease.get('waiting') or lease.get('holders') or lease.get('importing'):
                    raise NodeSynchronizationWait('节点账号API或租约仍在使用')
        remote = self.service.docker(node_row['id'])
        roles, releases, images = {}, set(), set()
        for role, column in ROLE_COLUMNS.items():
            if not row.get(column):
                continue
            container = remote.containers.get(row[column])
            container.reload()
            expected = {'vibebench.product': 'v3', 'vibebench.deployment': self.runtime.deployment,
                'vibebench.environment': row['environment_id'], 'vibebench.cluster-node': node_row['node_key'],
                'vibebench.role': ROLE_LABELS[role]}
            if any(container.labels.get(key) != value for key, value in expected.items()):
                raise ValueError('远程角色实际归属与中央环境不一致')
            if (staged or paused) and (container.attrs.get('State', {}).get('Running') is not False or container.attrs.get('State', {}).get('Pid') != 0):
                raise NodeSynchronizationWait('已备份节点的账号角色重新出现活动')
            if peer is not None and peer.get('role_status', {}).get(role) != container.status:
                raise ValueError('节点运行时角色来源与实际容器不一致')
            roles[role] = {'id': container.id, 'state': container.status, 'image_id': container.attrs['Image']}
            releases.add(container.labels.get('vibebench.release'))
            images.add(container.attrs['Image'])
            if quiescent and role == 'cli' and container.status == 'running':
                observed = container.exec_run(['python3', '-I', '/usr/local/bin/v3-cli-control', 'orphans'])
                if observed.exit_code or not isinstance(observed.output, bytes) or len(observed.output) > 65536:
                    raise NodeSynchronizationWait('节点CLI实际进程证据尚未确认')
                if json.loads(observed.output).get('orphans') != []:
                    raise NodeSynchronizationWait('节点CLI仍有原实际工作，继续等待')
        if roles and (len(roles) != 3 or len(releases) != 1 or len(images) != 1):
            raise ValueError('远程三角色来源尚未完整核对')
        release = next(iter(releases)) if releases else None
        origin = None
        if images:
            reference = os.environ['V3_ACCOUNT_IMAGE']
            actual = next(iter(images))
            if paused:
                # 源角色已按原冻结ID核验并停止，升级保留其原镜像，原迁移恢复时再创建目标角色。
                reference = container.attrs['Config']['Image']
                verified = True
            elif saved.get('account_reference') == reference and saved.get('account_image_id') == actual:
                verified = True
            else:
                original = self.service.local_client.images.get(reference)
                key = (node_row['node_key'], reference, actual, original.attrs['Id'])
                if key not in self.image_proofs:
                    self.image_proofs[key] = (actual == original.attrs['Id'] or
                        image_config_digest(remote, actual) == image_config_digest(self.service.local_client, reference))
                verified = self.image_proofs[key]
            if not verified:
                raise ValueError('远程账号镜像内容与受信来源不一致')
            origin = {'release': release, 'image_id': actual, 'reference': reference, 'verified': True}
        return {**{key: row.get(key) for key in ('environment_id', 'generation', 'state', 'name', 'account_id')},
            'node_kind': 'ssh', 'node_id': node_row['id'], 'roles': roles, 'origin': origin, 'blockers': []}

    def platform_status(self, operation_id: str, epoch: str) -> dict:
        """读取同一平台操作的节点备份与同步阶段。:param operation_id: 宿主操作。:param epoch: 原代次。:return: 脱敏进度。"""
        result = []
        for row in self.service.store.list():
            saved = row.get('preparation') or {}
            if row['kind'] != 'ssh' or row.get('removal') or not saved:
                continue
            with self.service.lock:
                running = row['id'] in self.service.install_workers
            entry = {'node_id': row['id'], 'node_key': row['node_key'], 'name': row['name'], 'phase': 'registering',
                'running': running, 'preparation': saved}
            path = self.service.connection(row['id']).private / 'maintenance/current.json'
            if path.exists():
                job = json.loads(path.read_text())
                if job.get('platform_operation') == operation_id and job.get('platform_epoch') == epoch:
                    entry.update(phase=job['phase'], target_release=job['target_release'], job_id=job['job_id'],
                        backup_epoch=job.get('backup_epoch'))
            result.append(entry)
        return {'nodes': result}

    def restore_platform_snapshot(self, node_id: int) -> dict:
        """在原全局门禁下恢复旧组件，原地作业保留当前资料。

        :param node_id: 原节点。
        :return: 原组件健康状态；历史快照作业沿原独立恢复路径。
        """
        row = self.service.store.get(node_id)
        node = self.service.connection(node_id)
        journal = node.private / 'maintenance/current.json'
        job = json.loads(journal.read_text())
        if (job['node_key'] != row['node_key']
                or job['config_sha256'] != hashlib.sha256(row['config_json'].encode()).hexdigest()):
            raise ValueError('节点完整恢复连接归属已变化')
        if job['phase'] == 'platform_restored':
            return {'state': 'prepared', 'release': job['old_release'], 'phase': 'ready'}
        self._check_platform(job)
        node.observe()
        job.pop('resume_boot_id', None)
        job['phase'] = 'platform_restoring'
        self._save(job)
        remote = self.service.docker(node_id)
        labels = {'vibebench.product':'v3','vibebench.deployment':self.runtime.deployment,
            'vibebench.cluster-node':row['node_key']}
        containers = remote.containers.list(all=True,filters={'label':[key+'='+value for key,value in labels.items()]})
        programs = remote.containers.list(filters={'label':['vibebench.project-verifier=native','vibebench.node-key='+row['node_key']]})
        if programs:
            raise ValueError('节点完整恢复仍有独立验收实例')
        known = {item['environment']['environment_id'] for item in job['accounts']}
        known.update(job.get('historical_environments', []))
        for container in containers:
            if (container.labels.get('vibebench.role') == 'node-control' and container.id != job['old_container']
                    and container.name != node_container_name(self.runtime.deployment, row['node_key'])):
                raise ValueError('节点完整恢复存在未知控制组件')
            if container.labels.get('vibebench.role') != 'node-control' and container.labels.get('vibebench.environment') not in known:
                raise ValueError('节点完整恢复存在未知环境角色')
            container.stop(timeout=5)
            container.reload()
            if container.attrs.get('State',{}).get('Running') is not False or container.attrs.get('State',{}).get('Pid') != 0:
                raise ValueError('节点完整恢复尚未确认角色停止')
        # 新维护只切回程序并保留当前资料；历史带完整快照的作业继续沿原恢复合同。
        if job.get('data_policy') != 'in_place':
            config = json.loads(row['config_json'])
            root = Path(config['data_root'])
            client = DockerClient(base_url='unix://'+str(node.docker_socket()),version='auto',timeout=None)
            try:
                payload = {'name':root.name,'job_id':job['job_id'],'epoch':job.get('backup_epoch',job['job_id']),
                    'node_key':row['node_key'],'deployment':self.runtime.deployment}
                if not job.get('snapshot_restored'):
                    helper_name = 'flower-node-restore-' + job['job_id'][:24]
                    try:
                        helper = client.containers.get(helper_name)
                        helper.reload()
                        if (helper.labels.get('flower.maintenance.job') != job['job_id']
                                or helper.attrs['Image'] != job['old_image']):
                            raise ValueError('节点原恢复进程归属不一致')
                    except NotFound:
                        helper = client.containers.run(job['old_image'],['-c',RESTORE_NODE_DATA,json.dumps(payload)],entrypoint='python3',
                            name=helper_name,detach=True,network_mode='none',labels={'flower.maintenance.job':job['job_id'], 'vibebench.product':'v3',
                                'vibebench.deployment':self.runtime.deployment, 'vibebench.role':'node-restore'},
                            volumes={str(root.parent):{'bind':'/node-parent','mode':'rw'},job['backup']:{'bind':'/backup','mode':'rw'}})
                    if helper.wait().get('StatusCode') != 0:
                        raise ValueError('节点原恢复进程未通过核验')
                    helper.remove()
                    job['snapshot_restored'] = True
                    job['source_restored'] = []
                    self._save(job)
            finally:
                client.close()
        name = node_container_name(self.runtime.deployment,row['node_key'])
        try:
            current = remote.containers.get(name)
        except NotFound:
            current = None
        if current is not None and current.attrs['Image'] != job['old_image']:
            current.remove()
            current = None
        try:
            original = remote.containers.get(job['old_container'])
        except NotFound:
            original = current
        if original is None:
            frozen = json.loads((node.private/'maintenance'/(job['job_id']+'-container.json')).read_text())
            original = remote.containers.create(job['old_image'],name=name,command=frozen['Config'].get('Cmd'),
                entrypoint=frozen['Config'].get('Entrypoint'),environment=frozen['Config'].get('Env'),
                user=frozen['Config'].get('User'),hostname=frozen['Config'].get('Hostname'),
                labels=frozen['Config']['Labels'],network=frozen['HostConfig']['NetworkMode'],
                restart_policy=frozen['HostConfig'].get('RestartPolicy'),
                volumes={item['Source']:{'bind':item['Destination'],'mode':'rw' if item.get('RW') else 'ro'}
                    for item in frozen['Mounts'] if item['Type']=='bind'})
        original.reload()
        if original.name != name:
            original.rename(name)
        original.start()
        deadline=time.monotonic()+20
        while True:
            try:
                health=node.agent_health(name)
                if health.get('release')!=job['old_release'] or health.get('node_key')!=job['node_key']:
                    raise ValueError('节点恢复组件身份不一致')
                break
            except Exception:
                if time.monotonic()>=deadline:
                    raise
                time.sleep(.2)
        for scope in job['fences'].values():
            if str(scope['account_id']) not in job.get('source_restored', []):
                node.migration_environment(name, scope, 'restore-source')
                job.setdefault('source_restored', []).append(str(scope['account_id']))
                self._save(job)
        # 相同账号镜像仍在原容器时先恢复实际角色，原生命周期可保持原代次。
        for item in job['accounts']:
            environment=item['environment']
            if environment['state']!='ready':
                continue
            try:
                roles={role:remote.containers.get(environment[column]) for role,column in ROLE_COLUMNS.items()}
            except NotFound:
                continue
            for role in ('network','cli','sender'):
                roles[role].start()
        self._restore_accounts(node,name,job,preserve=False)
        if not job['old_running']:
            original.stop(timeout=5)
        job['phase']='platform_restored'
        self._save(job)
        return {'state':'prepared','release':job['old_release'],'phase':'ready'}
