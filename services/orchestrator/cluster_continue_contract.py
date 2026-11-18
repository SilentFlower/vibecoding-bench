"""原ContinueManager续聊的具体冻结合同，保留原Run及Claude会话。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from cluster_execution_grants import ExecutionScope


class ContinueTask(BaseModel):
    """续聊实际使用的原任务字段。:param id: 原任务。:param warmup: 续聊沿原普通额度规则。"""

    model_config = ConfigDict(extra='forbid')
    id: StrictInt = Field(ge=1)
    warmup: StrictBool = False

    @model_validator(mode='after')
    def validate_workload(self):
        """续聊保持原普通交互额度模式。:return: 原任务定位。"""
        if self.warmup:
            raise ValueError('续聊不能使用养号额度模式')
        return self


class ContinueWork(BaseModel):
    """原sid/代次与原会话的有限工作投影。

    :param id: 原Run。
    :param account_id: 原账号。
    :param task: 原任务定位。
    :param sid: 原中央续聊会话。
    :param generation: 原续聊控制代次。
    :param session_id: 原真实Claude会话。
    :param version: 原解析版本。
    :param version_source: 原版本来源。
    :param permission_mode: 原权限模式。
    :param model: 原冻结模型，空串保留原CLI默认。
    :param capture_full_http: 原完整抓包模式。
    """

    model_config = ConfigDict(extra='forbid')
    id: StrictStr = Field(pattern=r'^[a-f0-9]{12}$')
    account_id: StrictInt = Field(ge=1)
    task: ContinueTask
    sid: StrictStr = Field(pattern=r'^[a-f0-9]{12}$')
    generation: StrictInt = Field(ge=0)
    session_id: StrictStr = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    version: StrictStr = Field(pattern=r'^2\.1\.[0-9]{1,6}$')
    version_source: StrictStr | None = Field(default=None, max_length=128)
    permission_mode: StrictStr = Field(pattern=r'^(manual|acceptEdits|bypassPermissions|plan|auto|dontAsk)$')
    model: StrictStr = Field(default='', max_length=128, pattern=r'^[A-Za-z0-9._\-\[\]]*$')
    capture_full_http: StrictBool = False

    @property
    def source(self) -> str:
        """保留原续聊sid和控制代次。:return: 原continue source。"""
        return f'continue:{self.sid}:{self.generation}'

    @property
    def shared_cli(self) -> bool:
        """续聊沿原非共享CLI模式。:return: False。"""
        return False

    def run(self) -> dict:
        """投影原begin_continue实际消费字段。:return: 原Run冻结字段。"""
        return {'id': self.id, 'task_id': self.task.id, 'account_id': self.account_id,
            'claude_code_version': self.version, 'claude_code_version_source': self.version_source,
            'capture_full_http': self.capture_full_http}


class ContinueStart(BaseModel):
    """原scope和具体续聊工作。:param scope: 原许可范围。:param work: 原冻结续聊。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    work: ContinueWork

    @model_validator(mode='after')
    def validate_scope(self):
        """拒绝其他账号、来源和执行类型。:return: 原请求。"""
        if self.scope.role != 'cli' or self.scope.account_id != self.work.account_id or self.scope.source != self.work.source:
            raise ValueError('节点续聊与原执行scope不一致')
        return self
