"""经典单步项目的冻结文件上下文与具体原生证据。"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from stat import S_ISREG

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from cluster_execution_grants import ExecutionScope
from cluster_quota import _read_quota_file
from cluster_project_plan import LegacyProjectPlan, ProjectPlanConfiguration, ProjectPlanDecision
from cluster_scenario_files import ScenarioProjectWork
from project_library import ProjectLibrary
from project_workspace import publish_project_workspace
from runtime_files import atomic_json, directory_fd, private_directory
from system_update_contract import safe_read, strict_json


class LegacyProjectWork(BaseModel):
    """中央冻结的原实例定位，路径全部由执行方计算。

    :param instance_id: 原项目实例。
    :param attempt_id: 原业务步骤尝试。
    :param batch_generation: 原批次代次。
    :param library_digest: 原内容版本。
    :param project_key: 原项目键。
    :param seed_digest: 原源码seed摘要。
    :param started: 中央已登记实际物化事实。
    :param plan: 原同会话计划的初始定位。
    :param scenario: 原场景候选的初始定位。
    """

    model_config = ConfigDict(extra='forbid')
    instance_id: StrictInt = Field(ge=1)
    attempt_id: StrictInt | None = Field(ge=1)
    batch_generation: StrictInt = Field(ge=1)
    library_digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    project_key: StrictStr = Field(pattern=r'^[a-z][a-z0-9-]{0,79}$')
    seed_digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    started: StrictBool
    plan: LegacyProjectPlan | None = None
    scenario: ScenarioProjectWork | None = None

    @model_validator(mode='after')
    def validate_workflow(self):
        """核对原工作流及共用冻结字段，拒绝混合定位。:return: 原冻结工作。"""
        if self.scenario is None:
            if self.attempt_id is None:
                raise ValueError('原经典项目缺少业务尝试')
        elif (self.plan is not None or self.library_digest!=self.scenario.files.library_digest
                or self.project_key!=self.scenario.files.project_key or self.seed_digest!=self.scenario.files.seed_digest
                or self.started!=self.scenario.files.started):
            raise ValueError('原场景定位与共用冻结字段冲突')
        return self

    def execution_plan(self) -> LegacyProjectPlan | None:
        """提供本次原driver的具体身份。:return: 原计划或场景轮次，普通单步为None。"""
        if self.scenario is not None:
            return LegacyProjectPlan(id=self.scenario.files.inputs.scenario_id,execution_id=self.scenario.execution_id,
                phase_seq=self.scenario.turn_no,step_id=self.scenario.files.task_key,session_id=self.scenario.session_id)
        return self.plan

    def alias(self, environment_id: str) -> str:
        """沿原实例别名算法解析目录。:param environment_id: 原环境。:return: 原稳定别名。"""
        if self.scenario is not None:
            return self.scenario.files.alias(environment_id)
        return 'project-'+hashlib.sha256(f'{environment_id}:instance:{self.instance_id}'.encode()).hexdigest()[:12]

    def workspace_relative(self, environment_id: str) -> str:
        """解析原执行可见的固定工作目录。:param environment_id: 原环境。:return: 节点数据根内相对路径。"""
        if self.scenario is not None and self.scenario.review is not None:
            return 'project-review-private/'+self.scenario.session_id+'/home/review'
        return 'environments/'+environment_id+'/projects/'+self.alias(environment_id)


class ProjectNativeRead(BaseModel):
    """原项目会话的有界字节读取。:param scope: 原操作。:param name: 原JSONL文件名。:param offset: 原字节位置。:param limit: 本次范围内的字节上限。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    name: StrictStr = Field(pattern=r'^[A-Za-z0-9_-]{1,128}\.jsonl$')
    offset: StrictInt = Field(default=0, ge=0)
    limit: StrictInt = Field(default=128*1024,ge=1,le=128*1024)


class NodeLegacyProject:
    """供本次AccountRuntime调用使用的文件提供器，保持中央调度权威。

    :param data: 原节点数据根。
    :param scope: 原有限执行范围。
    :param run_id: 原Run。
    :param work: 原冻结实例。
    :param grants: 原证明存储。
    """

    configuration_type=ProjectPlanConfiguration
    configuration_cleanup=('project-plan-request.json',)

    def __init__(self, data: Path, scope: ExecutionScope, run_id: str, work: LegacyProjectWork, grants) -> None:
        """登记本次原执行。参数见类说明。:return: None。"""
        self.data,self.scope,self.run_id,self.work,self.grants = data,scope,run_id,work,grants
        self.root = data/'environments'/scope.environment_id
        self.workspace = self.root/'projects'/work.alias(scope.environment_id)
        self.native = self.root/'home/.claude/projects'/('/home/node/projects/'+self.workspace.name).replace('/','-')
        self.artifacts = self.root/'runtime/legacy-projects'/run_id
        self.owner = self.root/'runtime/legacy-project-instances'/str(work.instance_id)
        self.operation=data/'node-runs'/scope.environment_id/scope.operation_id
        self.plans=self

    def run_context(self, run_id: str) -> dict | None:
        """只解析本次冻结实例。:param run_id: 原运行。:return: 原实例定位。"""
        if run_id!=self.run_id:
            return None
        result={'id':self.work.instance_id,'workspace_relative':str(self.workspace.relative_to(self.data))}
        if self.work.plan is not None:
            result.update(plan_id=self.work.plan.id,session_id=self.work.plan.session_id)
        return result

    def can_start(self, run_id: str) -> bool:
        """实际文件发布和exec前核对原有限证明。:param run_id: 原运行。:return: 原Scope仍允许准备。"""
        if run_id!=self.run_id:
            return False
        self.grants.authorize(self.scope)
        return True

    def prepare_workspace(self, row: dict, run_id: str, environment_root: Path) -> tuple[str,Path]:
        """沿原seed和物化标记发布工作区，拒绝未知现场。

        :param row: 原账号环境。
        :param run_id: 原运行。
        :param environment_root: 原账号根。
        :return: 原稳定别名和实际目录。
        """
        if (row['account_id']!=self.scope.account_id or row['environment_id']!=self.scope.environment_id
                or row['generation']!=self.scope.generation or environment_root!=self.root or not self.can_start(run_id)):
            raise ValueError('节点经典项目的实际环境与原Scope不一致')
        library = ProjectLibrary(self.data/'project-library/releases'/self.work.library_digest)
        if library.digest!=self.work.library_digest or library.schema!=1:
            raise ValueError('节点原经典内容版本需要核对')
        project = library.projects[self.work.project_key]
        if project.manifest['seed_digest']!=self.work.seed_digest:
            raise ValueError('节点原经典seed摘要不一致')
        private_directory(self.owner)
        publish_project_workspace(self.data,self.workspace,self.owner/'materialized.json',self.work.instance_id,
            self.work.seed_digest,lambda:project.root/'seed',self.work.started,lambda:self.can_start(run_id))
        atomic_json(self.owner/'execution.json',{'scope':self.scope.model_dump(),'run_id':run_id})
        return self.workspace.name,self.workspace

    def _sizes(self) -> dict:
        try:
            descriptor = directory_fd(self.native)
        except FileNotFoundError:
            return {}
        result = {}
        try:
            with os.scandir(descriptor) as files:
                for entry in files:
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}\.jsonl',entry.name):
                        continue
                    item = entry.stat(follow_symlinks=False)
                    if not S_ISREG(item.st_mode) or item.st_nlink!=1:
                        raise ValueError('原经典项目会话类型无效')
                    result[entry.name]=item.st_size
                    if len(result)>512 or item.st_size>64*1024*1024*1024:
                        raise ValueError('原经典项目会话超出有界证据范围')
        finally:
            os.close(descriptor)
        return result

    def record_native_start(self, run_id: str, directory: Path) -> None:
        """保留该Run首次原生字节起点，额度恢复复用原起点。

        :param run_id: 原运行。
        :param directory: 原物理原生目录。
        :return: None。
        """
        if run_id!=self.run_id or directory!=self.native:
            raise ValueError('原经典项目会话目录归属不符')
        private_directory(self.artifacts)
        path = self.artifacts/'native-start.json'
        if not path.exists() and not path.is_symlink():
            atomic_json(path,self._sizes())

    def finish(self) -> None:
        """实际停止后保存本次原生终点。:return: None。"""
        if not self.artifacts.exists():
            return
        path=self.artifacts/'native-end.json'
        if path.exists() or path.is_symlink():
            previous=strict_json(safe_read(path,96*1024,private=True),96*1024)
            if previous['scope']==self.scope.model_dump():
                return
        # 后来的步骤取得同一目录后，旧停止命令保持旧产物边界。
        self.current_workspace()
        atomic_json(self.artifacts/'native-end.json',{'scope':self.scope.model_dump(),'sizes':self._sizes()})

    def current_workspace(self) -> Path:
        """确认原实例尚未被后续执行接管。:return: 原物理工作区。"""
        value = strict_json(safe_read(self.owner/'execution.json',16384,private=True),16384)
        if value!={'scope':self.scope.model_dump(),'run_id':self.run_id}:
            raise ValueError('原经典项目目录已由后续执行取得，请读取原冻结候选')
        return self.workspace

    def facts(self) -> dict:
        """返回原物化事实和原生字节边界。:return: 有界原事实。"""
        start = strict_json(safe_read(self.artifacts/'native-start.json',96*1024,private=True),96*1024)
        end_path = self.artifacts/'native-end.json'
        end = None
        if end_path.exists() or end_path.is_symlink():
            saved = strict_json(safe_read(end_path,96*1024,private=True),96*1024)
            if saved['scope']==self.scope.model_dump():
                end=saved['sizes']
        sizes=self._sizes()
        return {'scope':self.scope.model_dump(),'project':self.work.model_dump(),
            'workspace_relative':str(self.workspace.relative_to(self.data)),'start':start,'end':end,'files':sizes}

    def read(self, request: ProjectNativeRead) -> dict:
        """只读原物理会话中的固定JSONL文件。

        :param request: 原Scope、受限文件名和游标。
        :return: 原字节片段与文件身份。
        """
        if request.scope!=self.scope:
            raise ValueError('原经典项目原生证据Scope不一致')
        return {'scope':self.scope.model_dump(),'name':request.name,
            **_read_quota_file(self.native/request.name,request.offset,maximum=request.limit)}

    def _configuration(self, value: ProjectPlanConfiguration) -> dict:
        plan=self.work.execution_plan()
        cwd=self.container_cwd()
        handle=hashlib.sha256(self.scope.source.encode()).hexdigest()[:20]
        if (plan is None or value.plan_id!=plan.id or value.run_id!=self.run_id or value.source!=self.scope.source
                or value.generation!=self.work.batch_generation or value.phase_seq!=plan.phase_seq
                or value.step_id!=plan.step_id or value.session_id!=plan.session_id or value.cwd!=cwd
                or value.native_directory!='/home/node/.claude/projects/'+cwd.replace('/','-')
                or value.request_file!=f'/run/v3/runs/{self.run_id}/project-plan-request.json'
                or value.state_file!=f'/run/v3/runs/{self.run_id}/project-plan-state.json'
                or value.decision_file!=f'/controls/{handle}/project-plan-decision.json'):
            raise ValueError('原同会话计划配置与冻结工作或服务端路径不一致')
        return value.model_dump(by_alias=True)

    def container_cwd(self) -> str:
        """解析本执行的固定容器工作目录。:return: 原项目挂载别名。"""
        return '/home/node/projects/'+self.workspace.name

    def control_root(self) -> Path:
        """定位本执行的实际root只读控制挂载根。:return: 节点账号控制目录。"""
        return self.root/'controls'

    def runtime_run_directory(self) -> Path:
        """定位本次driver实际产物目录。:return: 原节点Run运行目录。"""
        return self.root/'runtime/runs'/self.run_id

    def configure(self, value: ProjectPlanConfiguration) -> dict:
        """只保存原中央事务的固定计划配置。

        :param value: 原中央配置。
        :return: 原配置发布事实。
        """
        self.grants.authorize(self.scope)
        self.current_workspace()
        expected={'scope':self.scope.model_dump(),'configuration':self._configuration(value)}
        path=self.operation/'project-plan.json'
        if path.exists() or path.is_symlink():
            if strict_json(safe_read(path,96*1024,private=True),96*1024)!=expected:
                raise ValueError('原同会话计划配置已经冻结')
        else:
            # 原execution_configuration清除旧候选通知，输入状态仍保留供原driver核对接续。
            try:
                directory=directory_fd(self.runtime_run_directory())
            except FileNotFoundError:
                directory=None
            if directory is not None:
                try:
                    for name in self.configuration_cleanup:
                        try:
                            os.unlink(name,dir_fd=directory)
                        except FileNotFoundError:
                            pass
                    os.fsync(directory)
                finally:
                    os.close(directory)
            atomic_json(path,expected)
        return {'scope':self.scope.model_dump(),'configured':True}

    def execution_configuration(self, run_id: str, source: str, quota_attempt: int, native_directory: Path,
                                request_path: Path, decision_path: Path, cwd: str) -> dict:
        """向原AccountRuntime返回中央已持久化的配置。

        :param run_id: 原运行。
        :param source: 原执行来源。
        :param quota_attempt: 原额度代次。
        :param native_directory: 原物理会话目录。
        :param request_path: 原driver通知路径。
        :param decision_path: 原root决定路径。
        :param cwd: 原容器工作目录。
        :return: 原冻结driver配置。
        """
        saved=strict_json(safe_read(self.operation/'project-plan.json',96*1024,private=True),96*1024)
        value=self.configuration_type.model_validate(saved['configuration'])
        handle=hashlib.sha256(self.scope.source.encode()).hexdigest()[:20]
        if (saved['scope']!=self.scope.model_dump() or run_id!=self.run_id or source!=self.scope.source
                or type(quota_attempt) is not int or source!=f'run:{run_id}:{quota_attempt}' or native_directory!=self.native
                or request_path!=self.runtime_run_directory()/'project-plan-request.json'
                or decision_path!=self.control_root()/handle/'project-plan-decision.json' or cwd!=value.cwd):
            raise ValueError('原同会话计划与实际启动路径或来源不一致')
        self.grants.authorize(self.scope)
        return self._configuration(value)

    def decision(self, value: ProjectPlanDecision) -> dict:
        """将原中央阶段结论发布到该作业只读控制文件。

        :param value: 原已持久化业务决定。
        :return: 原阶段与内容摘要。
        """
        plan=self.work.execution_plan()
        if (plan is None or value.plan_id!=plan.id or value.run_id!=self.run_id or value.source!=self.scope.source
                or value.generation!=self.work.batch_generation or value.session_id!=plan.session_id):
            raise ValueError('原计划验收决定与当前执行不一致')
        self.current_workspace()
        self.grants.authorize(self.scope)
        document=value.model_dump(by_alias=True,exclude_none=True)
        handle=hashlib.sha256(self.scope.source.encode()).hexdigest()[:20]
        path=self.control_root()/handle/'project-plan-decision.json'
        unchanged=False
        if path.exists() or path.is_symlink():
            previous=ProjectPlanDecision.model_validate(strict_json(safe_read(path,65536),65536))
            unchanged=previous==value
            if not unchanged and (previous.action!='send' or value.phase_seq!=previous.next_phase_seq
                    or value.step_id!=previous.next_step_id):
                raise ValueError('原计划决定发生回退、跳跃或同阶段变更')
        elif value.phase_seq!=plan.phase_seq or value.step_id!=plan.step_id:
            raise ValueError('原计划首个决定阶段不一致')
        if not unchanged:
            atomic_json(path,document,0o640)
            os.chown(path,0,1000,follow_symlinks=False)
        return {'scope':self.scope.model_dump(),'phase_seq':value.phase_seq,
            'sha256':hashlib.sha256(value.model_dump_json(by_alias=True,exclude_none=True).encode()).hexdigest()}
