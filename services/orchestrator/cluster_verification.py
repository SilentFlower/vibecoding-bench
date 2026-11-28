"""节点冻结候选的独立程序验收作业，启动意图、取消和完整报告持久保存。"""
from __future__ import annotations

import hashlib
import re
import shutil
import threading

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from cluster_update_gate import NodeJobThread
from cluster_execution_grants import ExecutionScope
from cluster_workspace import WorkspaceSnapshotArchive, WorkspaceSnapshotReference, read_workspace_bundle
from project_library import canonical_json, digest_json, materialize_snapshot, read_document, safe_relative, snapshot_tree
from project_verifier import ProjectVerifier
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class VerificationReference(BaseModel):
    """原节点独立验收定位。:param scope: 原执行。:param attempt_id: 本次验收尝试。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    attempt_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')


class VerificationStart(VerificationReference):
    """固定候选与原冻结程序合同。:param snapshot_id: 原候选快照。:param candidate_digest: 原候选摘要。:param library_digest: 验收资产摘要。:param project_key: 原项目。:param objective_id: 原目标。:param definition_digest: 原定义摘要。:param answer: 原实际回答。:param regression: 原完整回归模式。"""

    snapshot_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    candidate_digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    library_digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    project_key: StrictStr = Field(pattern=r'^[a-z][a-z0-9-]{0,79}$')
    objective_id: StrictStr = Field(min_length=1, max_length=160)
    definition_digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    answer: StrictStr = Field(default='', max_length=256 * 1024)
    regression: StrictBool = False


class VerificationReport(BaseModel):
    """完整报告的固定文件身份。:param sha256: 原始字节摘要。:param bytes: 完整字节数。:param status: 原程序结论。"""

    model_config = ConfigDict(extra='forbid')
    sha256: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    bytes: StrictInt = Field(ge=1, le=32 * 1024 * 1024)
    status: Literal['passed', 'failed', 'error', 'cancelled']


class RunVerificationStart(VerificationStart):
    """只允许已释放候选的原隔离验证器启动。

    :param not_after: 中央发布的启动截止，最大未来35秒，不赋予CLI或刷新权限。
    """

    not_after: StrictInt = Field(ge=0)


class VerificationState(VerificationReference):
    """原后台验收的有界回执。:param phase: 当前阶段。:param request_digest: 原冻结输入。:param report: 完整报告身份。:param cancel_requested: 原取消意图。:param failure_type: 脱敏故障类型。"""

    phase: Literal['starting', 'running', 'complete', 'cancelled', 'reconcile']
    request_digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    report: VerificationReport | None = None
    cancel_requested: StrictBool
    failure_type: StrictStr | None = Field(default=None, pattern=r'^[A-Za-z0-9_]{1,120}$')


def pending_run_programs(data: Path, environment_id: str) -> list[dict]:
    """读取原环境的持久程序占用，缺失或冲突记录保留核对门禁。

    :param data: 原Node私有数据根。
    :param environment_id: 原环境身份。
    :return: 尚未完成或确认取消的原尝试。
    """
    if not re.fullmatch('[a-f0-9]{32}',environment_id):
        raise ValueError('节点独立程序环境身份无效')
    pending=[]
    for path in (data/'node-runs'/environment_id).glob('*/verifications/*/intent.json'):
        request=RunVerificationStart.model_validate(strict_json(safe_read(path,2*1024*1024,private=True),2*1024*1024))
        state=VerificationState.model_validate(strict_json(safe_read(path.with_name('state.json'),16384,private=True),16384))
        if (request.scope.environment_id!=environment_id or request.scope.operation_id!=path.parents[2].name
                or request.attempt_id!=path.parent.name or state.scope!=request.scope
                or state.attempt_id!=request.attempt_id or state.request_digest!=digest_json(request.model_dump())):
            raise ValueError('节点独立程序占用与原环境或尝试不一致')
        if state.phase not in ('complete','cancelled'):
            pending.append(state.model_dump())
    return pending


class NodeVerifications:
    """每节点两个原隔离程序验收槽位，未知作业保留原记录。

    :param terminals: 原持久终端。
    :param snapshots: 原节点冻结快照。
    :param verifier_factory: 原独立ProjectVerifier构造器。
    """

    request_type = VerificationStart

    def __init__(self, terminals, snapshots, verifier_factory=ProjectVerifier) -> None:
        """建立固定节点作业作用域。:param terminals: 原终端。:param snapshots: 原快照。:param verifier_factory: 原验证器。:return: None。"""
        self.terminals, self.snapshots, self.verifier_factory = terminals, snapshots, verifier_factory
        self.lock, self.slots, self.workers = threading.RLock(), threading.BoundedSemaphore(2), {}
        self.closing = False

    def _directory(self, reference: VerificationReference, *, create: bool = False) -> Path:
        parent = self.terminals._directory(reference.scope) / 'verifications'
        directory = parent / reference.attempt_id
        if create:
            private_directory(parent)
            private_directory(directory)
        return directory

    def _state(self, reference: VerificationReference) -> dict:
        state = VerificationState.model_validate(strict_json(safe_read(self._directory(reference) / 'state.json',
            16384, private=True), 16384)).model_dump()
        # 独立账号的scope.gateway_account_id=null属于冻结身份，不能递归删去。
        state = {key: value for key, value in state.items() if value is not None}
        if (state.get('scope') != reference.scope.model_dump() or state.get('attempt_id') != reference.attempt_id
                or state.get('phase') not in ('starting', 'running', 'complete', 'cancelled', 'reconcile')):
            raise ValueError('原节点验收作业范围或阶段无效')
        return state

    def get(self, reference: VerificationReference) -> dict:
        """读取原尝试，节点重启后的未决作业明确进入待核对。

        :param reference: 原执行和尝试。
        :return: 小型原作业回执。
        """
        with self.lock:
            self.terminals._record(reference.scope)
            state = self._state(reference)
            if state['phase'] in ('starting', 'running') and reference.attempt_id not in self.workers:
                state.update(phase='reconcile', failure_type='NodeRestart')
                atomic_json(self._directory(reference) / 'state.json', state)
            return state

    def _labels(self, reference: VerificationReference) -> dict:
        return {'vibebench.node-key': reference.scope.node_key, 'vibebench.environment-id': reference.scope.environment_id,
            'vibebench.execution-id': reference.scope.operation_id, 'vibebench.verification-id': reference.attempt_id}

    def _authorize(self, request: VerificationStart) -> None:
        self.terminals.grants.authorize(request.scope)
        self.terminals._ready(request.scope)

    def _contract(self, request: VerificationStart):
        record = self.terminals._record(request.scope)
        work = {**self.terminals._work(record), 'library_digest': request.library_digest}
        terminal = self.terminals._terminal(request.scope, work)
        project, definition = terminal.catalog.objective(request.project_key, request.objective_id)
        return project, definition, terminal.catalog.library

    def _runtime(self, request: VerificationStart):
        return self.terminals.host.runtime

    def start(self, request: VerificationStart) -> dict:
        """持久认领一次原验收；重复请求只返回原作业。

        :param request: 原候选和冻结合同。
        :return: 原尝试启动或已保存阶段。
        """
        scope = request.scope
        if len(request.answer.encode()) > 256 * 1024:
            raise ValueError('原验收回答超过完整输入上限')
        with self.terminals.executor._locked(environment_id=scope.environment_id), self.lock:
            directory = self._directory(request)
            if (directory / 'intent.json').exists() or (directory / 'intent.json').is_symlink():
                previous = self.request_type.model_validate(strict_json(safe_read(directory / 'intent.json', 2 * 1024 * 1024,
                    private=True), 2 * 1024 * 1024))
                if previous != request:
                    raise ValueError('原节点验收尝试的冻结输入已变化')
                return self.get(request)
            if self.closing:
                raise ValueError('节点验收服务正在关闭')
            self._authorize(request)
            parent = directory.parent
            for previous in parent.glob('*/intent.json'):
                value = strict_json(safe_read(previous.with_name('state.json'), 16384, private=True), 16384)
                if value.get('phase') not in ('complete', 'cancelled'):
                    raise ValueError('原执行尚有未收口验收作业，请先核对')
            if not self.slots.acquire(blocking=False):
                raise ValueError('所属节点的独立程序验收槽位已满')
            try:
                self._directory(request, create=True)
                atomic_json(directory / 'intent.json', request.model_dump())
                state = {'scope': scope.model_dump(), 'attempt_id': request.attempt_id, 'phase': 'starting',
                    'request_digest': digest_json(request.model_dump()), 'report': None, 'cancel_requested': False}
                atomic_json(directory / 'state.json', state)
                cancel = threading.Event()
                worker = NodeJobThread(target=self._run, args=(request, cancel), daemon=True)
                self.workers[request.attempt_id] = (worker, cancel)
                worker.start()
                return state
            except Exception:
                self.workers.pop(request.attempt_id, None)
                self.slots.release()
                raise

    def _run(self, request: VerificationStart, cancel: threading.Event) -> None:
        directory = self._directory(request)
        try:
            with self.lock:
                state = self._state(request)
                state['phase'] = 'running'
                atomic_json(directory / 'state.json', state)
            project, definition, library = self._contract(request)
            if library.digest != request.library_digest or digest_json(definition) != request.definition_digest:
                raise ValueError('节点独立程序验收的冻结合同不一致')
            receipt = WorkspaceSnapshotArchive.model_validate(self.snapshots.get(WorkspaceSnapshotReference(
                scope=request.scope, snapshot_id=request.snapshot_id)))
            if receipt.purpose != 'candidate' or receipt.tree_digest != request.candidate_digest:
                raise ValueError('节点验收引用的冻结候选不一致')
            environment_name = project.manifest['environment']
            profile = library.environments[environment_name]
            artifacts = profile['artifacts']
            contract_snapshot=snapshot_tree(project.root)
            # 场景内容制品只承诺路径与摘要；容量读取实际冻结文件，兼容带size的旧工程档案。
            artifact_sizes={item['path']:(library.root/'environments'/environment_name/safe_relative(item['path'])).stat().st_size
                for item in artifacts}
            if shutil.disk_usage(directory).free < receipt.tree_bytes * 3 + contract_snapshot['bytes'] * 3 + sum(artifact_sizes.values()) + 33 * 1024 * 1024:
                raise ValueError('所属节点空间不足以保存候选副本和完整验收报告')
            objects = directory / 'objects'
            bundle = self.snapshots._parent(request.scope) / (request.snapshot_id + '.tar')
            snapshot = read_workspace_bundle(bundle, receipt, objects)
            candidate = directory / 'candidate'
            materialize_snapshot(snapshot, objects, candidate)
            # 冻结资产可保持0700/0600；仅本次挂载副本恢复0755/0644，覆盖脚本目录与完整基线。
            contract_objects=directory/'contract-objects'
            frozen=snapshot_tree(project.root,contract_objects)
            if frozen['digest']!=contract_snapshot['digest']:
                raise ValueError('节点冻结程序合同在复制期间发生变化')
            contract=directory/'contract'
            materialize_snapshot(frozen,contract_objects,contract)
            specification = read_document(contract / safe_relative(definition['evaluation']['native']))
            offline = directory / 'offline'
            offline.mkdir(mode=0o755)
            offline.chmod(0o755)
            # 节点采用077私有umask；只给本次只读离线副本设置UID1000读取权限，保留冻结原件权限。
            for artifact in artifacts:
                relative = safe_relative(artifact['path'])
                target = offline / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                current = target.parent
                while current != offline:
                    current.chmod(0o755)
                    current = current.parent
                shutil.copyfile(library.root / 'environments' / environment_name / relative, target, follow_symlinks=False)
                with target.open('rb') as source:
                    if (target.stat().st_size != artifact.get('size',artifact_sizes[artifact['path']])
                            or hashlib.file_digest(source, 'sha256').hexdigest() != artifact['digest']):
                        raise ValueError('本次节点离线验收制品与原冻结摘要不一致')
                target.chmod(0o644)
            runtime = self._runtime(request)
            verifier = self.verifier_factory(self.terminals.executor.client, self.terminals.executor.data,
                self.terminals.executor.host_data, runtime.image, execution_labels=self._labels(request))
            self._authorize(request)
            report = verifier.verify_native(candidate, contract, specification,
                offline, profile,
                answer=request.answer, regression=request.regression, cancel=cancel)
            # 原验证器清理失败可能保留实际容器；完成回执必须等精确尝试的进程确认退出。
            self._stop_containers(request)
            raw = canonical_json(report)
            if len(raw) > 32 * 1024 * 1024 or report.get('status') not in ('passed', 'failed', 'error', 'cancelled'):
                raise ValueError('原节点验收报告大小或结论异常')
            # 完整报告通过固定Docker归档读取，控制回执保持有界。
            atomic_json(directory / 'report.json', report)
            published = safe_read(directory / 'report.json', 32 * 1024 * 1024, private=True)
            with self.lock:
                state = self._state(request)
                state.update(phase='complete', report={'sha256': hashlib.sha256(published).hexdigest(), 'bytes': len(published),
                    'status': report['status']})
                atomic_json(directory / 'state.json', state)
        except Exception as error:
            with self.lock:
                state = self._state(request)
                state.update(phase='reconcile', failure_type=type(error).__name__)
                atomic_json(directory / 'state.json', state)
        finally:
            with self.lock:
                self.workers.pop(request.attempt_id, None)
            self.slots.release()

    def cancel(self, reference: VerificationReference) -> dict:
        """持久取消并核对原验收容器，完成报告继续保留。

        :param reference: 原执行和验收尝试。
        :return: 已完成或已确认取消的原作业。
        """
        with self.lock:
            state = self._state(reference)
            running = None
            if state['phase'] not in ('complete','cancelled'):
                state['cancel_requested'] = True
                atomic_json(self._directory(reference) / 'state.json', state)
                running = self.workers.get(reference.attempt_id)
            if running:
                running[1].set()
        if running:
            running[0].join(timeout=10)
            if running[0].is_alive():
                raise ValueError('原节点验收仍在执行取消收尾')
        self._stop_containers(reference)
        with self.lock:
            state = self._state(reference)
            if state['phase'] != 'complete':
                state['phase'] = 'cancelled'
                atomic_json(self._directory(reference) / 'state.json', state)
            return state

    def _stop_containers(self,reference:VerificationReference) -> None:
        # 节点重启后按全部固定标签核对遗留容器，不把线程消失当作已停止。
        labels = {**self._labels(reference), 'vibebench.project-verifier': 'native',
            'vibebench.verifier-root': digest_json(str(self.terminals.executor.host_data))}
        filters = {'label': [key + '=' + value for key, value in labels.items()]}
        for container in self.terminals.executor.client.containers.list(all=True, filters=filters):
            if any(container.labels.get(key) != value for key, value in labels.items()):
                raise ValueError('节点遗留验收容器范围不一致')
            container.remove(force=True)
        if self.terminals.executor.client.containers.list(all=True, filters=filters):
            raise ValueError('原节点验收容器停止尚未确认')

    def stop_scope(self, scope: ExecutionScope) -> None:
        """原终端释放前先收口所有依赖程序验收。

        :param scope: 原终端执行。
        :return: None；未知验收继续阻止原终端释放。
        """
        parent = self.terminals._directory(scope) / 'verifications'
        for path in parent.glob('*/state.json'):
            reference = VerificationReference(scope=scope, attempt_id=path.parent.name)
            self.cancel(reference)

    def close(self) -> None:
        """关闭新验收并取消本进程所有原作业。:return: None。"""
        with self.lock:
            self.closing = True
            workers = list(self.workers.values())
        for worker, cancel in workers:
            cancel.set()
        for worker, cancel in workers:
            worker.join(timeout=10)
            if worker.is_alive():
                raise ValueError('节点独立验收关闭仍待实际收口')
