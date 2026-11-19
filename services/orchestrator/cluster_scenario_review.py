"""原场景私有评审的按次文件提供器，独立于候选挂载根。"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from cluster_scenario_project import NodeScenarioProject
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class NodeReviewInputs:
    """核对本次完整冻结包，准备原私有session文件及真实节点计时。

    :param data: 原节点数据根。
    :param scope: 原已认领证明。
    :param run_id: 原Run。
    :param work: 原冻结项目及评审。
    :param grants: 原证明存储。
    """

    def __init__(self, data, scope, run_id, work, grants) -> None:
        """保存原节点和评审定位。参数见类说明。:return: None。"""
        if work.scenario is None or work.scenario.review is None or not scope.source.startswith('run:'+run_id+':'):
            raise ValueError('节点私有评审缺少本次冻结身份')
        self.data,self.scope,self.run_id,self.work,self.grants=data,scope,run_id,work,grants
        self.root=data/'environments'/scope.environment_id
        self.operation=data/'node-runs'/scope.environment_id/scope.operation_id/'review-inputs'
        self.package_path=self.operation/'package.json'
        self.private_root=data/'project-review-private'/work.scenario.session_id
        self.workspace=self.private_root/'home/review'
        self.owner=self.root/'runtime/scenario-review-sessions'/work.scenario.session_id

    def package(self) -> dict:
        """核对原包完整字节和候选实际模型，拒绝替代回答。:return: 原冻结评审包。"""
        review=self.work.scenario.review
        raw=safe_read(self.package_path,512*1024,private=True)
        if len(raw)!=review.bytes or hashlib.sha256(raw).hexdigest()!=review.sha256:
            raise ValueError('节点私有评审完整包摘要或大小不符')
        value=strict_json(raw,512*1024)
        if (value.get('job_id')!=review.job_id or value.get('task_id')!=self.work.scenario.files.inputs.task_id
                or value.get('turn_no')!=self.work.scenario.turn_no or value.get('resolved_model')!=review.resolved_model):
            raise ValueError('节点私有评审包与原回答身份或实际模型不一致')
        return value

    def prepare(self) -> dict:
        """一次准备评审私有目录，原意图后的未知结果留待定向恢复。:return: 真实文件和时钟回执。"""
        grant=self.grants.authorize(self.scope)
        if grant.lease is not None and (grant.lease.shared_cli or grant.lease.exclusive):
            raise ValueError('节点私有评审需要原非共享CLI证明')
        private_directory(self.operation)
        result=self.operation/'prepared.json'
        if result.exists() or result.is_symlink():
            return self.facts()
        self.package()
        intent=self.operation/'intent.json'
        if intent.exists() or intent.is_symlink():
            raise ValueError('节点私有评审文件准备结果未知，保留原意图')
        atomic_json(intent,{'scope':self.scope.model_dump(),'run_id':self.run_id,'project':self.work.model_dump()})
        identity={'account_id':self.scope.account_id,'environment_id':self.scope.environment_id,
            'session_id':self.work.scenario.session_id,'task_id':self.work.scenario.files.inputs.task_id,
            'job_id':self.work.scenario.review.job_id,'library_digest':self.work.library_digest}
        marker=self.private_root/'node-review-owner.json'
        if self.private_root.exists() or self.private_root.is_symlink():
            private_directory(self.private_root)
            if strict_json(safe_read(marker,16384,private=True),16384)!=identity:
                raise ValueError('原私有评审session归属冲突')
        else:
            private_directory(self.private_root)
            atomic_json(marker,identity)
        private_directory(self.owner)
        self.workspace.mkdir(parents=True,exist_ok=True,mode=0o700)
        value={'scope':self.scope.model_dump(),'run_id':self.run_id,'work':self.work.scenario.files.model_dump(),
            'review':self.work.scenario.review.model_dump(),'workspace_relative':str(self.workspace.relative_to(self.data)),
            'clock':{'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'start_mono':time.monotonic()}}
        atomic_json(result,value)
        return value

    def facts(self) -> dict:
        """只读本次私有文件回执。:return: 原Scope的完整准备事实。"""
        value=strict_json(safe_read(self.operation/'prepared.json',192*1024,private=True),192*1024)
        if (value['scope']!=self.scope.model_dump() or value['run_id']!=self.run_id
                or value['work']!=self.work.scenario.files.model_dump() or value['review']!=self.work.scenario.review.model_dump()
                or value['workspace_relative']!=str(self.workspace.relative_to(self.data))):
            raise ValueError('节点私有评审文件事实属于其他执行')
        return value


class NodeScenarioReview(NodeScenarioProject):
    """沿原场景配置与原生字节合同提供私有评审上下文。

    :param data: 原数据根。
    :param scope: 原非共享CLI证明。
    :param run_id: 原Run。
    :param work: 原冻结评审。
    :param grants: 原证明存储。
    """

    def __init__(self, data, scope, run_id, work, grants) -> None:
        """绑定原私有session与文件所有者。参数见类说明。:return: None。"""
        super().__init__(data,scope,run_id,work,grants)
        self.files=NodeReviewInputs(data,scope,run_id,work,grants)
        self.workspace=self.files.workspace
        self.owner=self.files.owner
        self.artifacts=self.root/'runtime/scenario-reviews'/run_id
        self.native=self.files.private_root/'home/.claude/projects/-home-node-review'

    def run_context(self, run_id: str) -> dict | None:
        """投影本次原评审身份。:param run_id: 原Run。:return: 原私有上下文。"""
        value=super().run_context(run_id)
        if value is not None:
            value.update(role='review',scenario_execution={'id':self.work.scenario.execution_id,
                'evaluation_job_id':self.work.scenario.review.job_id})
        return value

    def review_root(self, run_id: str) -> Path:
        """只向原ReviewRuntime交付本次私有根。:param run_id: 原Run。:return: 原私有session目录。"""
        if run_id!=self.run_id or not self.can_start(run_id):
            raise ValueError('原私有评审根与本次Run不一致')
        self.current_workspace()
        return self.files.private_root

    def _package_path(self, job_id: int) -> Path:
        if job_id!=self.work.scenario.review.job_id:
            raise ValueError('节点私有评审包属于其他原评测作业')
        self.files.package()
        return self.files.package_path

    def container_cwd(self) -> str:
        """沿原私有评审容器工作目录。:return: 原review根。"""
        return '/home/node/review'

    def control_root(self) -> Path:
        """解析原私有评审只读控制根。:return: 原私有controls。"""
        return self.files.private_root/'controls'

    def runtime_run_directory(self) -> Path:
        """定位原私有driver运行目录。:return: 原评审Run产物根。"""
        return self.files.private_root/'runtime/runs'/self.run_id
