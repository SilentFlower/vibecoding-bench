"""中央远程终端协调：真实网关租约、有限节点证明及持久原操作收口。"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from pathlib import Path

from account_runtime import AccountRuntime, RuntimeBusy
from cluster_deployment import node_container_name
from cluster_execution_grants import ExecutionGrant, ExecutionLeaseProof, ExecutionScope
from cluster_terminal import TerminalStart
from cluster_runs import RunStart, RunWork
from cluster_continue_contract import ContinueStart, ContinueWork
from cluster_transfer import NodeArchiveTransfer
from cluster_workspace import WorkspaceSnapshotArchive, WorkspaceSnapshotRequest, read_workspace_bundle
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json
from system_update_gate import UPDATE_GATE


class TerminalSessions:
    """协调已经准备的节点和冻结工程资产，额度仍由原中央所有者决定。

    :param ledger: 原NodeExecutions账本。
    :param service: 原中央ClusterService。
    :param runtime: 原中央运行时发布身份。
    :param gateway: 原真实网关受信客户端。
    :param quota_admit: 中央真实额度认领回调，返回本次身份。
    :param quota_release: 确认停止后归还原额度许可的回调。
    """

    def __init__(self, ledger, service, runtime, gateway, quota_admit, quota_release, *, activity_gate=UPDATE_GATE,
                 quota_refresh=None, quota_finalize=None, run_quota_admit=None, admission=None) -> None:
        """登记中央依赖，初始化保留已有远程作业。

        :param ledger: 原中央私有账本。
        :param service: 节点通道。
        :param runtime: 原发布与部署。
        :param gateway: 原真实网关。
        :param quota_admit: 真实额度认领函数。
        :param quota_release: 原额度释放函数。
        :param activity_gate: 与原中央运行时共用的维护活动登记。
        :param quota_refresh: 首次证明和续接后同步中央门禁及原被动证据。
        :param quota_finalize: 实际停止后消费原节点最终额度证据。
        :param run_quota_admit: 原Runner已持有owner锁时使用的额度认领回调。
        :param admission: 记录新Scope之前的共同CLI优先级门禁。
        :return: None。
        """
        self.ledger, self.service, self.runtime, self.gateway = ledger, service, runtime, gateway
        self.quota_admit, self.quota_release = quota_admit, quota_release
        self.quota_refresh = quota_refresh
        self.quota_finalize = quota_finalize
        self.run_quota_admit = run_quota_admit
        self.admission=admission
        self.run_prepare = None
        self.lock, self.operations, self.workers, self.stopping = threading.RLock(), {}, {}, {}
        self.closing = False
        self.activity_gate, self.activities = activity_gate, {}

    def recover(self) -> dict:
        """恢复旧占用并关闭新输入，旧执行由原业务收口或人工对账。

        :return: 原操作恢复计数及需隔离的坏记录标识。
        """
        invalid = []
        for operation_id in self.ledger.pending():
            with self._operation_lock(operation_id):
                with self.lock:
                    if operation_id not in self.activities:
                        self.activities[operation_id] = self.activity_gate.restore_reserved('remote-cli:' + operation_id)
                try:
                    self._isolate(operation_id, 'central_restart')
                except ValueError:
                    # 坏记录仍保留旧活动，单个账号等待修复；其他账号继续初始化管理入口。
                    invalid.append(operation_id)
        return {'recovered': len(self.activities), 'invalid': invalid}

    def _operation_lock(self, operation_id: str):
        with self.lock:
            return self.operations.setdefault(operation_id, threading.RLock())

    def _scope(self, row: dict) -> ExecutionScope:
        return ExecutionScope.model_validate(row['record']['scope'])

    def _account(self, scope: ExecutionScope, *, available: bool = True) -> dict:
        connection = self.service.store.database()
        try:
            row = connection.execute('SELECT * FROM accounts WHERE id=?', (scope.account_id,)).fetchone()
            if row is None or row['cc2api_account_id'] != scope.gateway_account_id:
                raise ValueError('原远程执行账号或网关绑定已变化')
            if available and (not row['enabled'] or row['deleted_at'] is not None):
                raise ValueError('原远程执行账号已停用或删除')
            return dict(row)
        finally:
            connection.close()

    def _path(self, scope: ExecutionScope) -> str:
        if scope.gateway_account_id is None:
            raise ValueError('独立账号没有网关租约路径')
        return f'/admin/runtime/accounts/{scope.gateway_account_id}/lease'

    def _lease(self, snapshot: dict, scope: ExecutionScope, *, claimed: bool = False, exclusive: bool = False) -> ExecutionLeaseProof:
        value = AccountRuntime._owned_lease(snapshot, scope.source)
        if value is None or claimed and value.get('phase') != 'claimed':
            raise ValueError('中央网关缺少本次原租约确认')
        lease = ExecutionLeaseProof.model_validate({key: value[key] for key in
            ('owner', 'generation', 'expires_at', 'exclusive', 'shared_cli')})
        if (lease.exclusive is not exclusive or not time.time() < lease.expires_at <= time.time() + 35
                or exclusive and (not scope.bound_account_login or lease.shared_cli)):
            raise ValueError('中央普通终端租约模式或截止无效')
        return lease

    def _call(self, row: dict, operation: str, payload: dict):
        scope = self._scope(row)
        if scope.role == 'cli' and operation.startswith('terminal-'):
            if operation not in ('terminal-start', 'terminal-get', 'terminal-control', 'terminal-recover', 'terminal-snapshot', 'terminal-snapshot-get',
                    'terminal-quota-state', 'terminal-quota-read'):
                raise ValueError('原Run操作超出具体任务协议')
            operation = ('continue-' if scope.source.startswith('continue:') else 'run-') + operation.removeprefix('terminal-')
        node = self.service.store.get(row['node_id'])
        if (node['node_key'] != scope.node_key or node['kind'] != 'ssh'
                or hashlib.sha256(node['config_json'].encode()).hexdigest() != row['record']['node_config_sha256']):
            raise ValueError('原节点执行的SSH配置已变化，请先核对原服务器')
        result = self.service.connection(node['id']).execution_environment(
            node_container_name(self.runtime.deployment, scope.node_key), payload, operation)
        if result.get('protocol') != 1 or result.get('node_key') != scope.node_key:
            raise ValueError('节点执行回执属于其他安装')
        return result['login'] if operation.startswith(('account-login-','account-bound-login-')) else result['credentials'] if operation.startswith(('credential-refresh-','credential-usage-')) else result['continue'] if operation.startswith('continue-') else result['run'] if operation.startswith('run-') else result['terminal'] if operation.startswith('terminal-') else result['record']

    def snapshot(self, operation_id: str, snapshot_id: str, objects: Path | None = None) -> dict:
        """下载原节点有界快照包，返回原snapshot_tree清单及可选内容对象。

        :param operation_id: 原终端执行。
        :param snapshot_id: 本次固定基线或提交尝试。
        :param objects: 候选内容对象目录，基线为None。
        :return: 原完整源码快照清单。
        """
        request = WorkspaceSnapshotRequest(scope=self._scope(self.ledger.get(operation_id)), snapshot_id=snapshot_id,
            purpose='candidate' if objects is not None else 'baseline')
        with self._operation_lock('snapshot:' + operation_id + ':' + snapshot_id):
            return self._snapshot(request, objects)

    def _snapshot(self, request: WorkspaceSnapshotRequest, objects: Path | None) -> dict:
        scope, snapshot_id = request.scope, request.snapshot_id
        operation_id = scope.operation_id
        row = self.ledger.get(operation_id)
        root = self.service.data / 'cluster-workspace-snapshots'
        parent, directory = root / operation_id, root / operation_id / snapshot_id
        for target in (root, parent, directory):
            private_directory(target)
        metadata = directory / 'archive.json'
        if metadata.exists() or metadata.is_symlink():
            receipt = WorkspaceSnapshotArchive.model_validate(strict_json(safe_read(metadata, 16384, private=True), 16384))
        else:
            receipt = WorkspaceSnapshotArchive.model_validate(self._call(row, 'terminal-snapshot', request.model_dump()))
        if receipt.scope != scope or receipt.snapshot_id != snapshot_id or receipt.purpose != request.purpose:
            raise ValueError('节点源码快照回执与原中央操作范围不一致')
        if not metadata.exists():
            atomic_json(metadata, receipt.model_dump())
        bundle = directory / 'snapshot.tar'
        if not bundle.exists() and not bundle.is_symlink():
            transfer = self._archive_transfer(row)
            transfer.download_snapshot(scope.environment_id, operation_id, snapshot_id, bundle, receipt.sha256, receipt.bytes, run=scope.role == 'cli')
        return read_workspace_bundle(bundle, receipt, objects)

    def _archive_transfer(self, row: dict) -> NodeArchiveTransfer:
        scope=self._scope(row)
        node=self.service.store.get(row['node_id'])
        if (node['node_key']!=scope.node_key
                or hashlib.sha256(node['config_json'].encode()).hexdigest()!=row['record']['node_config_sha256']):
            raise ValueError('源码传输前原SSH配置已变化')
        connection=self.service.connection(node['id'])
        docker=self.service.docker(node['id'])
        return NodeArchiveTransfer(connection.docker_socket(),docker.api._version,
            node_container_name(self.runtime.deployment,scope.node_key))

    def _save(self, operation_id: str, phase: str | None = None, **changes) -> dict:
        with self._operation_lock(operation_id):
            row = self.ledger.get(operation_id)
            return self.ledger.checkpoint(operation_id, row['revision'], phase or row['phase'], **changes)

    def _isolate(self, operation_id: str, reason: str) -> None:
        with self._operation_lock(operation_id):
            row = self.ledger.get(operation_id)
            if row['phase'] != 'closed':
                self._save(operation_id, 'reconcile', failure=reason)
        with self.lock:
            event = self.stopping.get(operation_id)
            if event is not None:
                event.set()

    def _release_activity(self, operation_id: str) -> None:
        with self.lock:
            activity = self.activities.pop(operation_id, None)
        self.activity_gate.release_reserved(activity)

    def start(self, request: TerminalStart | RunStart | ContinueStart) -> dict:
        """认领真实中央许可后启动一次节点终端，重复只读取原账本。

        :param request: 原已准备环境的scope和冻结工作。
        :return: running或已存在的原阶段；未知提交保留reconcile。
        """
        scope = request.scope
        recorded = False
        account = None
        try:
            with self._operation_lock(scope.operation_id):
                with self.lock:
                    if self.closing:
                        raise RuntimeBusy('远程执行服务正在关闭')
                existing = self.ledger.find(scope.operation_id)
                if existing is not None:
                    if existing['record']['scope'] != scope.model_dump() or existing['record']['work'] != request.work.model_dump():
                        raise ValueError('原远程启动操作的范围已变化')
                    return existing
                account = self._account(scope)
                if self.admission is not None:
                    self.admission(account,scope)
                independent = scope.gateway_account_id is None
                shared = request.work.shared_cli if isinstance(request.work, (RunWork, ContinueWork)) else not bool(account.get(scope.role + '_capture_enabled', 0))
                low_priority = not isinstance(request.work, (RunWork, ContinueWork)) or request.work.task.warmup
                if independent:
                    active = self.ledger.active(scope.account_id)
                    if (self.runtime.environment_jobs(scope.environment_id) or active and (low_priority or not shared
                            or len(active) >= self.runtime.cli_limit or any(item['phase'] != 'running'
                                or item['record']['grant'].get('not_after', 0) <= time.time()
                                or item['record']['scope']['role'] != 'cli'
                                or not item['source'].startswith('run:')
                                or not RunWork.model_validate(item['record']['work']).shared_cli for item in active))):
                        raise RuntimeBusy('独立账号已有执行，低优先级终端等待原作业')
                else:
                    snapshot = self.gateway._request('GET', self._path(scope))
                    if not isinstance(snapshot.get('holders'), list) or snapshot.get('importing') != 0:
                        raise ValueError('中央真实CLI占用需要先核对')
                    if snapshot['holders'] and (low_priority or not shared):
                        raise RuntimeBusy('账号已有正式CLI执行，低优先级终端等待原作业')
                row = self.ledger.begin(scope, request.work, require_new=True)
                recorded = True
                activity = self.activity_gate.reserve('remote-cli:' + scope.source)
                with self.lock:
                    self.activities[scope.operation_id] = activity
                admit = self.run_quota_admit if isinstance(request, (RunStart, ContinueStart)) and self.run_quota_admit is not None else self.quota_admit
                quota_identity = admit(account, scope.source)
                if not isinstance(quota_identity, str) or not 1 <= len(quota_identity) <= 4096:
                    raise ValueError('中央额度所有者未返回有效原身份')
                if independent:
                    grant = ExecutionGrant(**scope.model_dump(), not_after=int(time.time()) + 30)
                    row = self._save(scope.operation_id, 'claimed', quota_identity=quota_identity,
                        local_admission_intent=True, grant=grant.model_dump())
                else:
                    row = self._save(scope.operation_id, quota_identity=quota_identity, gateway_prepare_intent=True)
                    snapshot = self.gateway._request('POST', self._path(scope),
                        {'operation': 'prepare-cli-shared' if shared else 'prepare-cli', 'owner': scope.source})
                    lease = self._lease(snapshot, scope)
                    if lease.shared_cli != shared:
                        raise ValueError('中央网关未返回本次真实CLI模式')
                    self._save(scope.operation_id, lease=lease.model_dump())
                    proof = {'owner': lease.owner, 'generation': lease.generation}
                    lease = self._lease(self.gateway._request('POST', self._path(scope), {'operation': 'claim', **proof}),
                        scope, claimed=True)
                    grant = ExecutionGrant(**scope.model_dump(), not_after=lease.expires_at, sequence=1, lease=lease)
                    row = self._save(scope.operation_id, 'claimed', lease=lease.model_dump(), grant=grant.model_dump())
                prepared = self._call(row, 'grant-create', grant.model_dump())
                if prepared.get('phase') != 'prepared' or prepared.get('grant') != grant.model_dump():
                    raise ValueError('节点未确认本次原有限证明')
                if self.quota_refresh:
                    self.quota_refresh(row)
                row = self._save(scope.operation_id, 'starting')
                self._start_heartbeat(scope.operation_id)
            # 长安装期间环境锁在节点持有，中央原租约和证明由独立线程续接。
            if isinstance(request,RunStart) and request.work.project is not None and request.work.project.execution_plan() is not None:
                if self.run_prepare is None:
                    raise ValueError('原同会话计划的中央准备所有者尚未就绪')
                self.run_prepare(row)
            receipt = self._call(row, 'terminal-start', request.model_dump())
            with self._operation_lock(scope.operation_id):
                self.ledger.admit(scope.operation_id)
                if receipt.get('phase') != 'ready' or receipt.get('scope') != scope.model_dump():
                    raise ValueError('节点原终端启动需要核对')
                return self._save(scope.operation_id, 'running', node_receipt=receipt)
        except Exception:
            if recorded:
                row = self.ledger.get(scope.operation_id)
                if not row['record']['gateway_prepare_intent'] and not row['record']['local_admission_intent']:
                    # 本处理者已独占登记原source；真实网关意图之前失败能确认节点尚未收到启动。
                    self.cancel_unsubmitted(scope.operation_id)
                else:
                    self._isolate(scope.operation_id, 'remote_start_unconfirmed')
            raise

    def _start_heartbeat(self, operation_id: str) -> None:
        with self.lock:
            if self.closing or operation_id in self.workers:
                raise RuntimeBusy('原执行续约已启动或服务正在关闭')
            event = threading.Event()
            thread = threading.Thread(target=self._heartbeat, args=(operation_id, event),
                name='cluster-terminal-lease', daemon=True)
            self.stopping[operation_id], self.workers[operation_id] = event, thread
            thread.start()

    def renew(self, operation_id: str) -> dict:
        """续接同一中央真实租约，并向节点提交下一有限序号。

        :param operation_id: 原执行。
        :return: 最新中央记录，节点确认前任何异常保留原占用。
        """
        try:
            return self._renew(operation_id)
        except Exception:
            self._isolate(operation_id, 'remote_renew_unconfirmed')
            raise

    def _renew(self, operation_id: str) -> dict:
        with self._operation_lock(operation_id):
            with self.lock:
                event = self.stopping.get(operation_id)
                if self.closing or event is not None and event.is_set():
                    raise RuntimeBusy('原远程执行正在停止续接')
            row = self.ledger.admit(operation_id)
            scope = self._scope(row)
            old = ExecutionGrant.model_validate(row['record']['grant'])
            lease = None
            if scope.gateway_account_id is None and old.not_after <= time.time():
                raise RuntimeBusy('独立执行许可已过期，请先核对原节点作业')
            if scope.gateway_account_id is not None:
                proof = {'owner': old.lease.owner, 'generation': old.lease.generation}
                lease = self._lease(self.gateway._request('POST', self._path(scope), {'operation': 'heartbeat', **proof}),
                    scope, claimed=True)
                if lease.model_dump(exclude={'expires_at'}) != old.lease.model_dump(exclude={'expires_at'}):
                    raise ValueError('中央原租约代次或模式已变化')
            with self.lock:
                if self.closing or event is not None and event.is_set():
                    raise RuntimeBusy('远程服务已关闭新证明提交')
            grant = old.model_copy(update={'sequence': old.sequence + 1,
                'not_after': lease.expires_at if lease else int(time.time()) + 30, 'lease': lease})
            row = self._save(operation_id, lease=lease.model_dump() if lease else None, grant=grant.model_dump())
            receipt = self._call(row, 'grant-renew', grant.model_dump())
            if receipt.get('grant') != grant.model_dump() or receipt.get('phase') not in ('prepared', 'active'):
                raise ValueError('节点原证明续接结果需要核对')
            if self.quota_refresh:
                self.quota_refresh(row)
            return row

    def _heartbeat(self, operation_id: str, event: threading.Event) -> None:
        while not event.wait(5):
            try:
                self.renew(operation_id)
            except Exception:
                return

    def node_state(self, operation_id: str) -> dict:
        """只读原节点启动回执，故障和超期后保留核对入口。

        :param operation_id: 原执行。
        :return: 原节点收据。
        """
        row = self.ledger.get(operation_id)
        receipt = self._call(row, 'terminal-get', self._scope(row).model_dump())
        if receipt.get('scope') != row['record']['scope']:
            raise ValueError('原节点启动回执范围不一致')
        return receipt

    def read(self, operation_id: str, operation: str, **parameters):
        """执行固定只读终端查询，路径和token始终由节点原回执确定。

        :param operation_id: 原执行。
        :param operation: observe、input、conversation、usage、passive或capture。
        :param parameters: 有界cursor或原输入input_id。
        :return: 原节点只读结果。
        """
        if operation not in ('observe', 'input', 'conversation', 'usage', 'passive', 'capture'):
            raise ValueError('远程终端只读操作无效')
        allowed = ({'cursor'} if operation == 'observe' else {'input_id'} if operation == 'input'
            else {'relative', 'running'} if operation == 'capture' else set())
        if set(parameters) - allowed:
            raise ValueError('远程终端只读参数超出原操作范围')
        row = self.ledger.get(operation_id)
        scope = self._scope(row).model_dump()
        if operation == 'input':
            if 'input_id' not in parameters:
                raise ValueError('原输入回执查询缺少input_id')
            payload = {'scope': scope, 'operation_id': parameters['input_id']}
        else:
            payload = {'scope': scope, **parameters} if operation in ('observe', 'capture') else scope
        return self._call(row, 'terminal-' + operation, payload)

    def ack_passive(self, operation_id: str, evidence_key: str) -> dict:
        """中央已持久合并原生补证后确认原发件箱。

        :param operation_id: 原终端执行。
        :param evidence_key: 原已合并事实摘要。
        :return: 节点持久确认回执。
        """
        row = self.ledger.get(operation_id)
        result = self._call(row, 'terminal-passive-ack', {'scope': self._scope(row).model_dump(), 'evidence_key': evidence_key})
        if result != {'acknowledged': True, 'evidence_key': evidence_key}:
            raise ValueError('原节点补证保存确认尚未匹配')
        return result

    def send(self, operation_id: str, input_id: str, text: str, keys: list[str], submit: bool) -> dict:
        """由已认领原会话投递一个输入，未知结果继续保留节点意图。

        :param operation_id: 原执行。
        :param input_id: 中央预先持久登记的输入操作。
        :param text: 原文本。
        :param keys: 原按键。
        :param submit: 是否追加Enter。
        :return: 原输入sent或unknown回执。
        """
        with self.lock:
            if self.closing:
                raise RuntimeBusy('远程执行服务正在关闭新输入')
        row = self.ledger.admit(operation_id)
        if row['phase'] != 'running' or row['record']['grant']['not_after'] <= time.time():
            raise ValueError('原远程终端尚未就绪或有限证明已过期')
        return self._call(row, 'terminal-send', {'scope': self._scope(row).model_dump(),
            'operation_id': input_id, 'text': text, 'keys': keys, 'submit': submit})

    def _stop_heartbeat(self, operation_id: str) -> None:
        with self.lock:
            event, thread = self.stopping.get(operation_id), self.workers.get(operation_id)
            if event is not None:
                event.set()
        if thread is not None:
            thread.join(15)
            if thread.is_alive():
                raise ValueError('原远程租约续接仍在收口，请等待并查询原操作')

    def control(self, operation_id: str, operation: str) -> dict:
        """定向控制原节点终端，恢复操作继续核对新输入许可。

        :param operation_id: 原执行。
        :param operation: 原inspect、freeze、resume或stop。
        :return: 原监督结果，stop完成时返回stopped。
        """
        if operation == 'stop':
            self.stop(operation_id)
            return {'stopped': True}
        if operation not in ('inspect', 'freeze', 'resume'):
            raise ValueError('远程终端控制操作无效')
        row = self.ledger.admit(operation_id) if operation == 'resume' else self.ledger.get(operation_id)
        if operation == 'resume' and row['record']['grant']['not_after'] <= time.time():
            raise ValueError('原远程证明已过期，请先对账再恢复输入')
        return self._call(row, 'terminal-control', {'scope': self._scope(row).model_dump(), 'operation': operation})

    def resolve_input(self, operation_id: str, input_id: str, resolution_id: str, sent: bool) -> dict:
        """转交中央人工入口的原输入结论，核对结果自身不会续约。

        :param operation_id: 原执行。
        :param input_id: 原未知输入。
        :param resolution_id: 中央原人工决策。
        :param sent: 人工核对是否已发送。
        :return: 节点原输入结论。
        """
        row = self.ledger.get(operation_id)
        result = self._call(row, 'terminal-reconcile', {'scope': self._scope(row).model_dump(),
            'operation_id': input_id, 'resolution_id': resolution_id, 'sent': sent})
        receipt = self.node_state(operation_id)
        if row['phase'] != 'closed':
            self._save(operation_id, node_receipt=receipt)
        return result

    def stop(self, operation_id: str) -> dict:
        """取得原节点停止回执后释放中央真实租约及额度许可。

        :param operation_id: 原执行。
        :return: closed记录；任何未知步骤继续保留原占用。
        """
        self._stop_heartbeat(operation_id)
        with self._operation_lock(operation_id):
            row = self.ledger.get(operation_id)
            if row['phase'] == 'closed':
                self._release_activity(operation_id)
                return row
            if not row['record']['gateway_prepare_intent'] and not row['record']['local_admission_intent']:
                return self.cancel_unsubmitted(operation_id)
            scope = self._scope(row)
            try:
                if (scope.gateway_account_id is not None and row['record']['grant'] is None
                        and row['record']['node_receipt'] is None):
                    return self._cancel_before_node_grant(row)
                row = self._save(operation_id, 'stopping')
                if row['record']['node_receipt'] is None or row['record']['node_receipt']['phase'] != 'closed':
                    try:
                        self._call(row, 'terminal-control', {'scope': scope.model_dump(), 'operation': 'stop'})
                    except Exception:
                        # 停止提交未知时只查询原回执，避免把HTTP失败当作仍在运行。
                        pass
                    receipt = self.node_state(operation_id)
                    if receipt.get('phase') != 'closed':
                        self._call(row, 'terminal-recover', scope.model_dump())
                        receipt = self.node_state(operation_id)
                        if receipt.get('phase') != 'closed':
                            raise ValueError('原节点实际停止尚未确认')
                    row = self._save(operation_id, node_receipt=receipt)
                if scope.gateway_account_id is not None and row['record']['lease_released'] is None:
                    lease = ExecutionLeaseProof.model_validate(row['record']['lease'])
                    proof = {'owner': lease.owner, 'generation': lease.generation}
                    try:
                        snapshot = self.gateway._request('POST', self._path(scope), {'operation': 'release', **proof})
                    except Exception:
                        snapshot = self.gateway._request('GET', self._path(scope))
                    if AccountRuntime._owned_lease(snapshot, scope.source) is not None:
                        raise ValueError('原中央租约释放尚未确认')
                    row = self._save(operation_id, lease_released={**proof, 'released': True})
                if self.quota_finalize:
                    self.quota_finalize(row)
                self.quota_release(self._account(scope, available=False), scope.source, False)
                row = self._save(operation_id, 'closed', local_admission_released=scope.gateway_account_id is None)
                self._release_activity(operation_id)
                with self.lock:
                    self.workers.pop(operation_id, None)
                    self.stopping.pop(operation_id, None)
                return row
            except Exception:
                self._isolate(operation_id, 'remote_stop_unconfirmed')
                raise

    def _cancel_before_node_grant(self, row: dict) -> dict:
        scope, operation_id = self._scope(row), row['operation_id']
        snapshot = self.gateway._request('GET', self._path(scope))
        if not isinstance(snapshot.get('holders'), list):
            raise ValueError('原中央认领结果需要完整租约快照核对')
        current = AccountRuntime._owned_lease(snapshot, scope.source)
        old = row['record']['lease']
        if current is not None:
            lease = self._lease(snapshot, scope)
            if old is not None and any(old[field] != getattr(lease, field) for field in ('owner', 'generation', 'exclusive', 'shared_cli')):
                raise ValueError('原中央未提交执行的租约代次发生变化')
            row = self._save(operation_id, lease=lease.model_dump())
        if row['record']['lease'] is not None:
            lease = row['record']['lease']
            proof = {'owner': lease['owner'], 'generation': lease['generation']}
            try:
                snapshot = self.gateway._request('POST', self._path(scope), {'operation': 'release', **proof})
            except Exception:
                snapshot = self.gateway._request('GET', self._path(scope))
            if not isinstance(snapshot.get('holders'), list) or AccountRuntime._owned_lease(snapshot, scope.source) is not None:
                raise ValueError('原中央未提交执行的租约撤销尚未确认')
            row = self._save(operation_id, lease_released={**proof, 'released': True})
        # 原grant检查点先于任何节点调用；缺少该证据可确定节点尚未收到本次工作。
        self.quota_release(self._account(scope, available=False), scope.source, True)
        row = self._save(operation_id, 'closed', node_start_cancelled=True, failure='central_node_not_submitted')
        self._release_activity(operation_id)
        return row

    def cancel_unsubmitted(self, operation_id: str) -> dict:
        """仅收口本处理者尚未提交真实网关认领意图的准备。

        :param operation_id: 原私有执行登记。
        :return: central_not_started关闭记录；已有真实意图必须沿原停止流程核对。
        """
        with self._operation_lock(operation_id):
            row = self.ledger.get(operation_id)
            record = row['record']
            if row['phase'] == 'closed':
                self._release_activity(operation_id)
                return row
            if (record['gateway_prepare_intent'] or record['local_admission_intent'] or record['lease'] is not None or record['grant'] is not None
                    or record['node_receipt'] is not None or record['lease_released'] is not None):
                raise ValueError('原执行已有真实认领意图，需核对原节点及中央租约')
            scope = self._scope(row)
            self.quota_release(self._account(scope, available=False), scope.source, True)
            row = self._save(operation_id, 'closed', failure='central_not_started')
            self._release_activity(operation_id)
            return row

    def close(self) -> None:
        """关闭本进程续接，原执行与未知收据由中央账本保留供重启核对。:return: None。"""
        with self.lock:
            self.closing = True
            threads = list(self.workers.values())
            for event in self.stopping.values():
                event.set()
        deadline = time.monotonic() + 10
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
