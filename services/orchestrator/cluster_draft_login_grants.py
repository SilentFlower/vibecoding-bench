"""NULL草稿专用有限证明，复用原截止、一次认领和持久关闭规则。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from cluster_draft_login_contract import DraftLoginGrant, DraftLoginScope
from cluster_execution_grants import ExecutionGrants
from system_update_contract import safe_read, strict_json


class _DraftGrantRecord(BaseModel):
    """草稿证明独立解码，正式账号与Gateway租约字段保持拒绝。"""

    model_config=ConfigDict(extra='forbid')
    protocol:StrictInt=Field(default=1,ge=1,le=1)
    grant:DraftLoginGrant
    phase:Literal['prepared','active','closed']
    closed_reason:StrictStr | None=Field(default=None,pattern=r'^[a-z][a-z0-9_]{0,79}$')

    @model_validator(mode='after')
    def validate_phase(self):
        """关闭事实与原固定原因同时保存。:return: 已核对记录。"""
        if (self.phase=='closed')!=(self.closed_reason is not None):
            raise ValueError('原草稿证明的关闭阶段无效')
        return self


class DraftLoginGrants(ExecutionGrants):
    """独立草稿身份与文件空间，原正式账号证明继续保持正ID合同。

    :param data: 原Node私有根。
    :param node_key: 原受信节点。
    :param deployment: 原部署。
    :param database: 原Node投影库。
    :param clock: 原UTC秒时钟。
    """

    _record_model=_DraftGrantRecord

    def __init__(self, data: Path, node_key: str, deployment: str, database: Callable,
            clock: Callable=time.time) -> None:
        """复用原有限证明状态机并隔离草稿文件。

        :param data: 原私有根。
        :param node_key: 原节点。
        :param deployment: 原部署。
        :param database: 原投影连接工厂。
        :param clock: 节点时钟。
        :return: None。
        """
        super().__init__(data,node_key,deployment,database,clock)
        self.directory=data/'node-draft-login-grants'

    def _check_environment(self, scope: DraftLoginScope, *, stopping: bool=False) -> None:
        scope=DraftLoginScope.model_validate(scope.model_dump())
        self._installation()
        deletion=self.data/'node-draft-deletions'/scope.environment_id
        if deletion.is_symlink() or any(deletion.glob('*.json')):
            raise ValueError('原草稿已进入完整清理，新的输入许可已关闭')
        root=self.data/'environments'/scope.environment_id
        marker=strict_json(safe_read(root/'runtime/node-draft-login.json',8192,private=True),8192)
        if (marker!={'protocol':1,'scope':scope.model_dump(),'phase':'ready'} or type(marker.get('protocol')) is not int
                or DraftLoginScope.model_validate(marker.get('scope'))!=scope):
            raise ValueError('草稿专属Node范围、逻辑代次或准备状态已经变化')
        if any(path.exists() or path.is_symlink() for path in (root/'runtime/node-assignment.json',root/'runtime/node-fence.json')):
            raise ValueError('原草稿已经存在正式归属或迁移隔离记录')
        connection=self.database()
        try:
            row=connection.execute('SELECT * FROM account_environments WHERE environment_id=?',(scope.environment_id,)).fetchone()
            if (row is None or row['name']!=scope.name or row['account_id'] is not None or row['generation']!=scope.generation
                    or not stopping and row['state'] not in ('ready','stopped')):
                raise ValueError('原草稿NULL账号或实际环境代次已经变化')
            if connection.execute('SELECT 1 FROM accounts WHERE name=? OR profile_path=? LIMIT 1',
                    (scope.name,'profiles/'+scope.name)).fetchone():
                raise ValueError('正式或软删除账号仍引用原Node草稿')
        finally:
            connection.close()

    def check_stopping_scope(self, scope: DraftLoginScope) -> None:
        """原Node重启隔离后只恢复停止能力，NULL身份和实际代次仍须匹配。

        :param scope: 原已冻结草稿范围。
        :return: None；不续接许可，不授予新输入。
        """
        self._check_environment(scope,stopping=True)

    def _lease_renewal(self, old: DraftLoginGrant, grant: DraftLoginGrant) -> bool:
        """草稿无Gateway租约，续接沿父类核对同范围、单调序号与截止。"""
        return True
