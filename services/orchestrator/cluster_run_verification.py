"""已释放场景候选的独立程序验收，原CLI证明只用于定位历史候选。"""
from __future__ import annotations

import time
from cluster_execution import NodeInspection
from cluster_runs import RunWork
from cluster_verification import NodeVerifications, RunVerificationStart
from project_library import ProjectLibrary, digest_json
from runtime_files import atomic_json


class NodeRunVerifications(NodeVerifications):
    """复用原隔离验证器、冻结候选和报告协议，独立于已关闭CLI许可。

    :param terminals: 原NodeRuns，仅用于读取同一历史Scope。
    :param snapshots: 原Run冻结候选包。
    :param verifier_factory: 原隔离验证器构造器。
    """

    request_type=RunVerificationStart

    def _authorize(self, request: RunVerificationStart) -> None:
        scope=request.scope
        record=self.terminals._record(scope)
        work=RunWork.model_validate(record['work'])
        project=work.project
        if (record['phase']!='closed' or self.terminals.grants.get(scope)['phase']!='closed'
                or project is None or project.scenario is None or project.scenario.review is not None):
            raise ValueError('独立场景验收需要原候选CLI已实际释放')
        if not time.time()<request.not_after<=time.time()+35:
            raise ValueError('独立程序启动许可已过期或超出本次期限')
        row=self.terminals.executor._inspection_row(NodeInspection(node_key=scope.node_key,account_id=scope.account_id,
            environment_id=scope.environment_id,assignment_revision=scope.assignment_revision,
            version=work.worker_env['CLAUDE_CODE_VERSION']))
        if row['generation']!=scope.generation:
            raise ValueError('独立程序所属节点环境代次已变化')

    def _contract(self, request: RunVerificationStart):
        work=RunWork.model_validate(self.terminals._record(request.scope)['work'])
        files=work.project.scenario.files
        if (request.library_digest!=files.library_digest or request.project_key!=files.project_key
                or request.objective_id!=files.task_key):
            raise ValueError('独立程序合同与原候选场景不一致')
        library=ProjectLibrary(self.terminals.executor.data/'project-library/releases'/files.library_digest)
        if library.schema not in (2,3):
            raise ValueError('独立程序场景内容版本不符')
        project=library.projects[files.project_key]
        scenario=next(item for item in project.manifest['scenarios'] if item['id']==files.scenario_key)
        definition=next(item for item in scenario['tasks'] if item['id']==files.task_key)
        return project,definition,library

    def _runtime(self, request: RunVerificationStart):
        return self.terminals._reader(request.scope)

    def cancel(self,request:RunVerificationStart) -> dict:
        """取消原尝试，未提交时先保存墓碑拒绝迟到的原启动。

        :param request: 中央原完整冻结程序许可，取消时保留原截止。
        :return: 已完成或实际取消的原程序回执。
        """
        with self.terminals.executor._locked(environment_id=request.scope.environment_id),self.lock:
            self.terminals._record(request.scope)
            directory=self._directory(request)
            intent=directory/'intent.json'
            if not intent.exists() and not intent.is_symlink():
                self._directory(request,create=True)
                atomic_json(intent,request.model_dump())
                state={'scope':request.scope.model_dump(),'attempt_id':request.attempt_id,'phase':'cancelled',
                    'request_digest':digest_json(request.model_dump()),'cancel_requested':True,'report':None}
                atomic_json(directory/'state.json',state)
                return self._state(request)
        return super().cancel(request)
