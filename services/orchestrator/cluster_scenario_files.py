"""场景输入的节点文件提供器，代码来源及披露选择由中央冻结。"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from cluster_execution_grants import ExecutionScope
from cluster_project_plan import ProjectPlanConfiguration
from cluster_workspace import WorkspaceSnapshotArchive, WorkspaceSnapshotRequest, read_workspace_bundle, write_workspace_bundle
from project_input_files import prepare_scenario_input_files
from project_library import ProjectLibrary, canonical_json, digest_json, read_checkpoint, read_document, write_document
from project_workspace import publish_project_workspace
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


ContentKey=Annotated[StrictStr,Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,79}$')]
TreeDigest=Annotated[StrictStr,Field(pattern=r'^[a-f0-9]{64}$')]
JobKey=Annotated[StrictStr,Field(pattern=r'^[1-9][0-9]*$')]


class ScenarioCodeInput(BaseModel):
    """中央已接受代码输入。:param task_id: 原任务。:param dependencies: 接受作业及摘要。:param base_checkpoint_digest: 原基线。:param base_checkpoint_job_id: 原接受来源。"""

    model_config=ConfigDict(extra='forbid')
    task_id: StrictInt=Field(ge=1)
    dependencies: dict[JobKey,TreeDigest]
    base_checkpoint_digest: TreeDigest
    base_checkpoint_job_id: StrictInt | None=Field(default=None,ge=1)


class ScenarioInputSelection(BaseModel):
    """中央场景输入选择。:param scenario_id: 原场景。:param task_id: 原任务。:param entry_key: 冻结入口。:param code: 已接受代码来源。:param disclosures: 原有序披露键。"""

    model_config=ConfigDict(extra='forbid')
    scenario_id: StrictInt=Field(ge=1)
    task_id: StrictInt=Field(ge=1)
    entry_key: ContentKey
    code: ScenarioCodeInput
    disclosures: list[ContentKey]

    @model_validator(mode='after')
    def validate_identity(self):
        """核对任务身份和披露唯一性。:return: 原输入选择。"""
        if self.code.task_id!=self.task_id or len(self.disclosures)!=len(set(self.disclosures)):
            raise ValueError('场景输入选择的任务身份或披露键冲突')
        return self


class ScenarioFileWork(BaseModel):
    """节点场景文件的冻结定位，输入路径从原内容推导。

    :param library_digest: 同批完整内容版本。
    :param project_key: 原项目键。
    :param scenario_key: 原冻结场景键。
    :param task_key: 原冻结任务键。
    :param seed_digest: 原源码seed。
    :param started: 中央已记录场景物化。
    :param inputs: 中央已核对的输入选择。
    """

    model_config=ConfigDict(extra='forbid')
    library_digest: TreeDigest
    project_key: StrictStr=Field(pattern=r'^[a-z][a-z0-9-]{0,79}$')
    scenario_key: ContentKey
    task_key: ContentKey
    seed_digest: TreeDigest
    started: StrictBool
    inputs: ScenarioInputSelection

    def alias(self, environment_id: str) -> str:
        """沿原场景算法生成固定别名。:param environment_id: 原环境。:return: 原场景别名。"""
        return 'scenario-'+digest_json([environment_id,self.inputs.scenario_id])[:12]


class ScenarioReviewWork(BaseModel):
    """原冻结回答的私有评审包定位。

    :param job_id: 原中央评测作业。
    :param review_attempt: 原同回答逻辑评审尝试。
    :param sha256: 完整包原字节摘要。
    :param bytes: 完整包字节数。
    :param resolved_model: 原候选实际使用的模型。
    """

    model_config=ConfigDict(extra='forbid')
    job_id: StrictInt=Field(ge=1)
    review_attempt: StrictInt=Field(ge=1,le=2)
    sha256: TreeDigest
    bytes: StrictInt=Field(ge=1,le=512*1024)
    resolved_model: StrictStr=Field(pattern=r'^[A-Za-z0-9._\-\[\]]{1,128}$')


class ScenarioProjectWork(BaseModel):
    """本次原场景候选的冻结执行身份。

    :param files: 实际场景文件定位。
    :param catalog_release_id: 原中央内容登记行。
    :param execution_id: 原任务执行。
    :param turn_no: 原任务轮次。
    :param session_id: 原场景固定会话。
    :param review: 原私有评审包；候选为None。
    """

    model_config=ConfigDict(extra='forbid')
    files: ScenarioFileWork
    catalog_release_id: StrictInt=Field(ge=1)
    execution_id: StrictInt=Field(ge=1)
    turn_no: StrictInt=Field(ge=1)
    session_id: StrictStr=Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
    review: ScenarioReviewWork | None = None


class ScenarioConfiguration(ProjectPlanConfiguration):
    """原场景driver配置，保留中央预留与节点真实启动时钟。

    :param workflow_schema: 原场景工作流版本。
    :param work_file: 原driver工作计时文件。
    :param segment_id: 中央实际预算片段。
    :param segment_boot_id: 原执行节点启动身份。
    :param work_limit_sec: 原片段预留秒数。
    """

    workflow_schema: StrictInt=Field(ge=3,le=3)
    work_file: StrictStr=Field(max_length=512)
    segment_id: StrictInt=Field(ge=1)
    segment_boot_id: StrictStr=Field(min_length=1,max_length=128)
    work_limit_sec: StrictFloat | StrictInt=Field(ge=0,le=86400,allow_inf_nan=False)


class NodeScenarioFiles:
    """执行本次场景文件准备，状态、对象及旧现场随环境保留。

    :param data: 原节点数据根。
    :param scope: 已由原Run所有者认领的有限范围。
    :param run_id: 原Run。
    :param work: 原冻结文件定位。
    :param grants: 原节点证明存储。
    """

    def __init__(self, data: Path, scope: ExecutionScope, run_id: str, work: ScenarioFileWork, grants) -> None:
        """保存原执行定位。参数见类说明。:return: None。"""
        if not scope.source.startswith('run:'+run_id+':'):
            raise ValueError('场景文件准备来源属于其他Run')
        self.data,self.scope,self.run_id,self.work,self.grants=data,scope,run_id,work,grants
        self.root=data/'environments'/scope.environment_id
        self.workspace=self.root/'projects'/work.alias(scope.environment_id)
        self.store=self.root/'runtime/scenario-inputs'/str(work.inputs.scenario_id)
        self.objects,self.manifests=self.store/'objects',self.store/'manifests'
        self.operation=data/'node-runs'/scope.environment_id/scope.operation_id/'scenario-inputs'

    def import_base(self, path: Path, receipt: WorkspaceSnapshotArchive) -> dict:
        """核对本Scope完整基线包后导入内容对象，禁止任意树替代中央选择。

        :param path: 本次原操作私有目录中已上传的包。
        :param receipt: 中央冻结的原源码包回执。
        :return: 已核对完整对象的原基线清单。
        """
        self.grants.authorize(self.scope)
        if (receipt.scope!=self.scope or receipt.purpose!='candidate'
                or receipt.tree_digest!=self.work.inputs.code.base_checkpoint_digest):
            raise ValueError('节点场景基线包与原Scope或已接受输入不一致')
        for directory in (self.store,self.objects,self.manifests):
            private_directory(directory)
        snapshot=read_workspace_bundle(path,receipt,self.objects)
        write_document(self.manifests/(snapshot['digest']+'.json'),snapshot)
        return snapshot

    def prepare(self) -> dict:
        """一次准备实际场景输入，未知写入保留原意图供停止恢复。

        :return: 原Scope、文件选择、物化路径和逐阶段真实回执。
        """
        self.grants.authorize(self.scope)
        private_directory(self.operation)
        identity={'scope':self.scope.model_dump(),'run_id':self.run_id,'work':self.work.model_dump()}
        result=self.operation/'prepared.json'
        if result.exists() or result.is_symlink():
            saved=self.facts()
            if any(saved.get(key)!=value for key,value in identity.items()):
                raise ValueError('节点场景文件准备身份已变化')
            return saved
        intent=self.operation/'intent.json'
        if intent.exists() or intent.is_symlink():
            raise ValueError('节点场景输入准备结果未知，保留原意图等待对账')
        library=ProjectLibrary(self.data/'project-library/releases'/self.work.library_digest)
        if library.digest!=self.work.library_digest or library.schema not in (2,3):
            raise ValueError('节点场景冻结内容版本不一致')
        project=library.projects[self.work.project_key]
        if project.manifest['seed_digest']!=self.work.seed_digest:
            raise ValueError('节点场景seed与原冻结内容不一致')
        scenario=next(item for item in project.manifest['scenarios'] if item['id']==self.work.scenario_key)
        task=next(item for item in scenario['tasks'] if item['id']==self.work.task_key)
        if (self.work.inputs.entry_key not in {item['id'] for item in scenario['entries']}
                or any(key not in {item['id'] for item in task.get('branches',[])} for key in self.work.inputs.disclosures)):
            raise ValueError('场景披露选择或入口与冻结内容不一致')
        # 先核对完整基线，意图后的任何中断均保留现场，原Run所有者负责严格收口。
        read_checkpoint(self.objects,self.manifests,self.work.inputs.code.base_checkpoint_digest)
        atomic_json(intent,identity)
        private_directory(self.store)
        publish_project_workspace(self.data,self.workspace,self.store/'materialized.json',self.work.inputs.scenario_id,
            self.work.seed_digest,lambda:project.root/'seed',self.work.started,
            lambda:bool(self.grants.authorize(self.scope)),identity_key='scenario_id',staging_root=self.store/'staging')
        inputs=prepare_scenario_input_files(self.data,self.workspace,project.root,scenario,task,
            self.work.inputs.model_dump(),self.objects,self.manifests,
            lambda checksum:read_checkpoint(self.objects,self.manifests,checksum),marker_root=self.store,
            staging_root=self.store/'staging',before_write=lambda:self.grants.authorize(self.scope))
        value={**identity,'workspace_relative':str(self.workspace.relative_to(self.data)),'inputs':inputs,
            'clock':{'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'start_mono':time.monotonic()}}
        if len(canonical_json(value))>192*1024:
            raise ValueError('节点场景输入回执超过私有协议大小上限')
        atomic_json(result,value)
        return value

    def facts(self) -> dict:
        """只读本次已完成文件准备回执，保留历史事实。:return: 原私有回执。"""
        value=strict_json(safe_read(self.operation/'prepared.json',192*1024,private=True),192*1024)
        if (value['scope']!=self.scope.model_dump() or value['work']!=self.work.model_dump()
                or value['run_id']!=self.run_id):
            raise ValueError('节点场景文件回执属于其他执行')
        return value

    def archive(self, stage: str) -> dict:
        """封存已登记输入阶段的完整对象，中央据此保存原检查点事实。

        :param stage: 本次真实回执中的entry/task/branch键。
        :return: 原阶段不可变源码包回执。
        """
        facts=self.facts()
        checksum=facts['inputs']['stages'][stage]['input_checkpoint_digest']
        snapshot=read_checkpoint(self.objects,self.manifests,checksum)
        snapshot_id=hashlib.sha256(('scenario-input:'+stage+':'+checksum).encode()).hexdigest()[:32]
        directory=self.operation/'exports'
        private_directory(directory)
        path=directory/(snapshot_id+'.json')
        if path.exists() or path.is_symlink():
            receipt=WorkspaceSnapshotArchive.model_validate(strict_json(safe_read(path,16384,private=True),16384))
            if receipt.scope!=self.scope or receipt.snapshot_id!=snapshot_id or receipt.tree_digest!=checksum:
                raise ValueError('节点场景阶段源码包身份冲突')
            return receipt.model_dump()
        request=WorkspaceSnapshotRequest(scope=self.scope,snapshot_id=snapshot_id,purpose='candidate')
        receipt=write_workspace_bundle(directory/(snapshot_id+'.tar'),request,snapshot,self.objects)
        atomic_json(path,receipt.model_dump())
        return receipt.model_dump()
