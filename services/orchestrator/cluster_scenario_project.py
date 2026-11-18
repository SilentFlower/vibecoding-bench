"""场景候选的按次文件提供器，原中央管理器保存业务事务和预算。"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from cluster_execution_grants import ExecutionScope
from cluster_legacy_projects import NodeLegacyProject
from cluster_project_plan import ProjectPlanDecision
from cluster_scenario_files import NodeScenarioFiles, ScenarioConfiguration
from project_library import ProjectLibrary
from runtime_files import atomic_json


class ScenarioPlanPublish(BaseModel):
    """原场景配置的固定发布。:param scope: 原执行。:param configuration: 原中央场景配置。"""

    model_config=ConfigDict(extra='forbid')
    scope: ExecutionScope
    configuration: ScenarioConfiguration


class NodeScenarioProject(NodeLegacyProject):
    """复用原Run原生证据和控制文件，场景输入由专用文件执行器准备。

    :param data: 原节点数据根。
    :param scope: 原有限证明。
    :param run_id: 原Run。
    :param work: 原冻结场景候选。
    :param grants: 原节点证明存储。
    """

    configuration_type=ScenarioConfiguration
    configuration_cleanup=('project-plan-request.json','project-work.json')

    def __init__(self, data, scope, run_id, work, grants) -> None:
        """绑定本次场景文件及原生证据所有者。参数见类说明。:return: None。"""
        if work.scenario is None:
            raise ValueError('场景文件提供器缺少冻结场景定位')
        super().__init__(data,scope,run_id,work,grants)
        self.files=NodeScenarioFiles(data,scope,run_id,work.scenario.files,grants)
        self.owner=self.files.store
        self.artifacts=self.root/'runtime/scenario-projects'/run_id
        self.scenarios=self
        self._library=None

    def run_context(self, run_id: str) -> dict | None:
        """只向原AccountRuntime投影本次场景候选。:param run_id: 原Run。:return: 本次上下文。"""
        if run_id!=self.run_id:
            return None
        scenario=self.work.scenario
        return {'id':self.work.instance_id,'workspace_relative':str(self.workspace.relative_to(self.data)),
            'scenario_instance_id':scenario.files.inputs.scenario_id,'scenario_task_id':scenario.files.inputs.task_id,
            'role':'candidate','scenario_execution':{'id':scenario.execution_id},'session_id':scenario.session_id,
            'catalog_release_id':scenario.catalog_release_id,'project_key':self.work.project_key}

    def context(self, run_id: str) -> dict | None:
        """提供原离线Python环境所需的同次场景定位。:param run_id: 原Run。:return: 原上下文。"""
        return self.run_context(run_id)

    def _release(self, release_id: int) -> ProjectLibrary:
        if release_id!=self.work.scenario.catalog_release_id:
            raise ValueError('节点场景离线环境属于其他内容登记')
        if self._library is None:
            library=ProjectLibrary(self.data/'project-library/releases'/self.work.library_digest)
            if library.digest!=self.work.library_digest:
                raise ValueError('节点场景离线内容摘要不一致')
            self._library=library
        return self._library

    def prepare_workspace(self, row: dict, run_id: str, environment_root: Path) -> tuple[str,Path]:
        """在原有限证明内准备场景材料并登记实际目录所有者。

        :param row: 原账号环境。
        :param run_id: 原Run。
        :param environment_root: 原节点环境根。
        :return: 原场景别名与实际目录。
        """
        if (row['account_id']!=self.scope.account_id or row['environment_id']!=self.scope.environment_id
                or row['generation']!=self.scope.generation or environment_root!=self.root or not self.can_start(run_id)):
            raise ValueError('节点场景工作区与原账号环境不一致')
        self.files.prepare()
        atomic_json(self.owner/'execution.json',{'scope':self.scope.model_dump(),'run_id':run_id})
        return self.workspace.name,self.workspace

    def _configuration(self, value: ScenarioConfiguration) -> dict:
        document=super()._configuration(value)
        if (value.work_file!=f'/run/v3/runs/{self.run_id}/project-work.json'
                or value.segment_boot_id!=self.files.facts()['clock']['boot_id']):
            raise ValueError('节点场景预算计时身份或路径与实际准备不符')
        return document

    def decision(self, value: ProjectPlanDecision) -> dict:
        """发布原场景本轮完成决定，沿原Run退出后再推进后续任务。

        :param value: 原中央已封存的单轮决定。
        :return: 原阶段及内容摘要。
        """
        if value.action=='send':
            raise ValueError('场景后续轮次必须经中央原任务重新准入')
        return super().decision(value)
