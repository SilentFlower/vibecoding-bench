"""中央固定工程验收的节点作业协调，完整报告按原尝试下载并核对。"""
from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from uuid import uuid4

from cluster_deployment import node_container_name
from cluster_execution_grants import ExecutionScope
from cluster_transfer import NodeArchiveTransfer
from cluster_verification import VerificationReference, VerificationStart, VerificationState
from project_library import digest_json
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class RemoteProgramVerification:
    """协调所属节点的原ProjectVerifier，中央仍拥有最终验收结论。

    :param sessions: 原中央终端协调器。
    :param catalog: 原冻结工程目录。
    """

    def __init__(self, sessions, catalog) -> None:
        """保存原依赖。:param sessions: 原会话。:param catalog: 原资产。:return: None。"""
        self.sessions, self.catalog = sessions, catalog

    def _receipt(self, request: VerificationStart, value: dict) -> VerificationState:
        state = VerificationState.model_validate(value)
        if (state.scope != request.scope or state.attempt_id != request.attempt_id
                or state.request_digest != digest_json(request.model_dump())):
            raise ValueError('节点独立验收回执与原冻结输入不一致')
        if state.phase == 'complete' and state.report is None:
            raise ValueError('原节点程序验收完成回执缺少完整报告')
        return state

    def verify(self, row: dict, work: dict, snapshot: dict, directory: Path, target: dict, *, answer: str = '',
               regression: bool = False, cancel: threading.Event | None = None) -> dict:
        """提交一次原候选验收，未知启动只查询同一尝试。

        :param row: 原中央终端记录。
        :param work: 本次当前工作。
        :param snapshot: 原已冻结候选清单。
        :param directory: 中央原提交目录。
        :param target: 当前或历史已通过目标的冻结工作。
        :param answer: 原生实际回答。
        :param regression: 是否验证原完整回归。
        :param cancel: 原控制者取消信号。
        :return: 原节点完整程序报告。
        """
        scope = ExecutionScope.model_validate(row['record']['scope'])
        if (work['account_id'] != scope.account_id or target['account_id'] != scope.account_id
                or work['project_key'] != target['project_key'] or scope.source != f"{scope.role}:{work['id']}:{work['generation']}"):
            raise ValueError('独立验收目标与原账号、项目或执行不一致')
        assets = self.catalog.for_work(target)
        project, definition = assets.objective(target['project_key'], target['objective_id'])
        library = assets.library
        if digest_json(definition) != digest_json(strict_json(target['definition_json'].encode(), 4 * 1024 * 1024)):
            raise ValueError('原节点验收目标合同与中央冻结版本不一致')
        request = VerificationStart(scope=scope, attempt_id=uuid4().hex, snapshot_id=directory.name,
            candidate_digest=snapshot['digest'], library_digest=library.digest, project_key=target['project_key'],
            objective_id=target['objective_id'], definition_digest=digest_json(definition), answer=answer, regression=regression)
        resource = library.environments[project.manifest['environment']]['regression' if regression else 'business']
        timeout = resource['timeout_sec'] + 120
        root = self.sessions.service.data / 'cluster-verifications'
        for path in (root, root / scope.operation_id, root / scope.operation_id / request.attempt_id):
            private_directory(path)
        private = root / scope.operation_id / request.attempt_id
        registered = self.sessions._call(row, 'terminal-assets', {'node_key': scope.node_key, 'digest': library.digest})
        if registered != {'digest': library.digest, 'state': 'registered'}:
            raise ValueError('所属节点缺少原独立验收资产')
        with self.sessions._operation_lock(scope.operation_id):
            current = self.sessions.ledger.admit(scope.operation_id)
            if current['phase'] != 'running' or current['record']['grant']['not_after'] <= time.time():
                raise ValueError('原远程执行尚未就绪或证明已过期')
            atomic_json(private / 'intent.json', request.model_dump())
            try:
                try:
                    value = self.sessions._call(current, 'terminal-verification-start', request.model_dump())
                except Exception:
                    # 启动响应丢失只查询同一尝试，不能创建另一程序作业替代未知提交。
                    value = self.sessions._call(current, 'terminal-verification-get',
                        VerificationReference(scope=scope, attempt_id=request.attempt_id).model_dump())
                state = self._receipt(request, value)
            except Exception:
                self.sessions._isolate(scope.operation_id, 'remote_verification_start_unconfirmed')
                raise
        deadline = time.monotonic() + timeout
        reference = VerificationReference(scope=scope, attempt_id=request.attempt_id).model_dump()
        while state.phase in ('starting', 'running'):
            if cancel and cancel.is_set() or time.monotonic() >= deadline:
                atomic_json(private / 'cancel.json', reference)
                try:
                    state = self._receipt(request, self.sessions._call(current, 'terminal-verification-cancel', reference))
                    if state.phase not in ('complete', 'cancelled'):
                        raise ValueError('原节点验收取消仍待实际收口')
                except Exception:
                    self.sessions._isolate(scope.operation_id, 'remote_verification_cancel_unconfirmed')
                    raise
                return {'status': 'cancelled', 'message': '当前节点独立验收已取消'}
            if cancel:
                cancel.wait(0.25)
            else:
                time.sleep(0.25)
            try:
                state = self._receipt(request, self.sessions._call(current, 'terminal-verification-get', reference))
            except Exception:
                self.sessions._isolate(scope.operation_id, 'remote_verification_observation_unconfirmed')
                raise
        atomic_json(private / 'state.json', state.model_dump())
        if state.phase == 'cancelled':
            return {'status': 'cancelled', 'message': '原节点独立验收已确认取消'}
        if state.phase != 'complete':
            self.sessions._isolate(scope.operation_id, 'remote_verification_reconcile')
            raise ValueError('原节点程序验收需要核对，请保留原尝试')
        return self._download_report(row,request,state,private)

    def _download_report(self, row: dict, request: VerificationStart, state: VerificationState, private: Path, *, run: bool = False) -> dict:
        scope=request.scope
        destination=private/'report.json'
        if destination.exists() or destination.is_symlink():
            raw=safe_read(destination,32*1024*1024,private=True)
            if len(raw)!=state.report.bytes or hashlib.sha256(raw).hexdigest()!=state.report.sha256:
                raise ValueError('原完整程序报告缓存与节点回执不一致')
            report=strict_json(raw,32*1024*1024)
            if report.get('status')!=state.report.status:
                raise ValueError('原完整程序报告缓存与原结论不一致')
            return report
        node = self.sessions.service.store.get(row['node_id'])
        if hashlib.sha256(node['config_json'].encode()).hexdigest() != row['record']['node_config_sha256']:
            raise ValueError('原节点验收报告下载前SSH配置已变化')
        connection = self.sessions.service.connection(row['node_id'])
        docker = self.sessions.service.docker(row['node_id'])
        transfer = NodeArchiveTransfer(connection.docker_socket(), docker.api._version,
            node_container_name(self.sessions.runtime.deployment, scope.node_key))
        transfer.download_verification(scope.environment_id, scope.operation_id, request.attempt_id, destination,
            state.report.sha256, state.report.bytes,**({'run':True} if run else {}))
        raw = safe_read(destination, 32 * 1024 * 1024, private=True)
        if len(raw) != state.report.bytes or hashlib.sha256(raw).hexdigest() != state.report.sha256:
            raise ValueError('节点完整程序验收报告字节摘要不符')
        report = strict_json(raw, 32 * 1024 * 1024)
        if report.get('status') != state.report.status:
            raise ValueError('节点完整程序报告与原结论回执不一致')
        return report
