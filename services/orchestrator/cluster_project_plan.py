"""原同会话项目计划的具体冻结配置，路径由节点再核对。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from cluster_execution_grants import ExecutionScope


class LegacyProjectPlan(BaseModel):
    """本次原计划执行的初始阶段。

    :param id: 原计划。
    :param execution_id: 原计划执行。
    :param phase_seq: 首次阶段序号。
    :param step_id: 原当前业务步骤。
    :param session_id: 原固定Claude会话。
    """

    model_config = ConfigDict(extra='forbid')
    id: StrictInt = Field(ge=1)
    execution_id: StrictInt = Field(ge=1)
    phase_seq: StrictInt = Field(ge=0)
    step_id: StrictStr = Field(min_length=1,max_length=160)
    session_id: StrictStr = Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')


class ProjectPlanConfiguration(BaseModel):
    """原ProjectPlans.execution_configuration的受限返回结构。

    :param schema_version: 原driver schema，JSON使用schema。
    :param plan_id: 原计划。
    :param run_id: 原运行。
    :param source: 原额度尝试。
    :param generation: 原批次代次。
    :param phase_seq: 本次起始阶段。
    :param step_id: 原步骤。
    :param session_id: 原会话。
    :param prompt: 原业务输入。
    :param cwd: 原容器工作目录。
    :param resume: 原接续决定。
    :param native_directory: 原容器会话目录。
    :param request_file: 原driver通知文件。
    :param state_file: 原driver输入状态文件。
    :param decision_file: 原只读决定文件。
    """

    model_config = ConfigDict(extra='forbid',populate_by_name=True)
    schema_version: StrictInt = Field(default=1,alias='schema',ge=1,le=1)
    plan_id: StrictInt = Field(ge=1)
    run_id: StrictStr = Field(pattern=r'^[a-f0-9]{12}$')
    source: StrictStr = Field(min_length=1,max_length=160)
    generation: StrictInt = Field(ge=1)
    phase_seq: StrictInt = Field(ge=0)
    step_id: StrictStr = Field(min_length=1,max_length=160)
    session_id: StrictStr = Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
    prompt: StrictStr = Field(max_length=65536)
    cwd: StrictStr = Field(max_length=256)
    resume: StrictBool
    native_directory: StrictStr = Field(max_length=512)
    request_file: StrictStr = Field(max_length=512)
    state_file: StrictStr = Field(max_length=512)
    decision_file: StrictStr = Field(max_length=512)

    @model_validator(mode='after')
    def validate_size(self):
        """保持原计划64KiB输入上限。:return: 原配置。"""
        if len(self.model_dump_json(by_alias=True).encode())>65536:
            raise ValueError('原计划配置超过受限输入大小')
        return self


class ProjectPlanPublish(BaseModel):
    """中央原事务的具体配置发布。:param scope: 原执行。:param configuration: 原配置。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    configuration: ProjectPlanConfiguration


class ProjectPlanDecision(BaseModel):
    """原逐步验收决定，保留原driver需要的字段。

    :param schema_version: 原schema。
    :param plan_id: 原计划。
    :param run_id: 原运行。
    :param source: 原执行。
    :param generation: 原批次代次。
    :param phase_seq: 原决定阶段。
    :param step_id: 原业务步骤。
    :param session_id: 原会话。
    :param response_key: 已验收的原生回复。
    :param action: 原complete/failed/send。
    :param next_phase_seq: 后续阶段。
    :param next_step_id: 后续步骤。
    :param prompt: 后续输入。
    """

    model_config = ConfigDict(extra='forbid',populate_by_name=True)
    schema_version: StrictInt = Field(default=1,alias='schema',ge=1,le=1)
    plan_id: StrictInt = Field(ge=1)
    run_id: StrictStr = Field(pattern=r'^[a-f0-9]{12}$')
    source: StrictStr = Field(min_length=1,max_length=160)
    generation: StrictInt = Field(ge=1)
    phase_seq: StrictInt = Field(ge=0)
    step_id: StrictStr = Field(min_length=1,max_length=160)
    session_id: StrictStr = Field(min_length=1,max_length=128)
    response_key: StrictStr = Field(min_length=1,max_length=256)
    action: Literal['complete','failed','send']
    next_phase_seq: StrictInt | None = Field(default=None,ge=1)
    next_step_id: StrictStr | None = Field(default=None,min_length=1,max_length=160)
    prompt: StrictStr | None = Field(default=None,max_length=65536)

    @model_validator(mode='after')
    def validate_phase(self):
        """后续发送必须精确推进一阶段。:return: 原决定。"""
        if self.action=='send':
            if self.next_phase_seq!=self.phase_seq+1 or self.next_step_id is None or self.prompt is None:
                raise ValueError('原计划下一阶段决定不完整')
        elif any(value is not None for value in (self.next_phase_seq,self.next_step_id,self.prompt)):
            raise ValueError('原计划终态决定包含后续输入')
        if len(self.model_dump_json(by_alias=True,exclude_none=True).encode())>65536:
            raise ValueError('原计划决定超过受限大小')
        return self


class ProjectPlanDecisionPublish(BaseModel):
    """发布原阶段决定。:param scope: 原执行。:param decision: 原中央结论。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    decision: ProjectPlanDecision
