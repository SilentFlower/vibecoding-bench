"""原Runner冻结工作与节点实际driver操作，中央调度和数据库继续保持权威。"""
from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import time
from pathlib import Path
from stat import S_ISREG
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from cluster_execution_grants import ExecutionGrant, ExecutionScope
from cluster_legacy_projects import LegacyProjectWork, NodeLegacyProject, ProjectNativeRead
from cluster_project_plan import ProjectPlanPublish, ProjectPlanDecisionPublish
from cluster_scenario_project import NodeScenarioProject, ScenarioPlanPublish
from cluster_scenario_review import NodeScenarioReview
from cluster_workspace import WorkspaceSnapshotArchive
from cluster_terminal import NodeTerminals, TerminalCapture, TerminalControl
from cluster_quota import _read_quota_file, quota_scope_path
from project_library import safe_relative
from run_artifacts import PRIVATE_ROOTS, list_workspace_files, ordinary_run_alias, read_workspace_file
from run_capture import run_capture
from run_usage import native_session_usage, run_usage
from runtime_files import atomic_json, directory_fd, private_directory
from system_update_contract import safe_read, strict_json


WORKER_ENVIRONMENT = frozenset({
    'TASK_PROMPT', 'TASK_FOLLOWUP_TIMING_JSON', 'TASK_FOLLOWUPS_JSON', 'RUN_ID', 'TIMEOUT_SEC', 'ACC_NAME',
    'CLAUDE_CODE_VERSION', 'CLAUDE_CODE_EFFORT_LEVEL', 'CLAUDE_PERMISSION_MODE', 'PROFILE_CLAUDE_CODE_EFFORT_LEVEL',
    'CLEAN_WORKSPACE_DEPS', 'TIMEOUT_WRAPUP_SEC', 'OAUTH_CREDENTIAL_SYNC_INTERVAL_SEC', 'OAUTH_401_PROFILE_WAIT_SEC',
    'CLAUDE_API_STALL_WATCHDOG_SEC', 'CLAUDE_API_STALL_MAX_RECOVERIES', 'CLAUDE_BUSY_INTERRUPT_GRACE_SEC',
    'CLAUDE_API_STALL_RECOVERY_PROMPT', 'OAUTH_REFRESH_BUFFER_SEC', 'TZ', 'LANG', 'LC_ALL',
    'QUOTA_SOURCE', 'QUOTA_WARMUP', 'RESUME_SESSION_ID', 'CC2API_MANAGED_OAUTH', 'CLAUDE_MODEL_OVERRIDE',
    'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', 'DISABLE_TELEMETRY', 'DISABLE_ERROR_REPORTING',
})
RunArtifactName = Literal['status.json', 'transcript.log', 'session-baseline.json', 'followups.json', 'oauth-refresh-request.json', 'quota-control.json', 'project-plan-request.json', 'project-plan-state.json', 'project-work.json']


class RunTask(BaseModel):
    """原driver实际读取的任务字段。:param id: 原任务。:param quota_attempt: 原额度尝试。:param warmup: 原低优先级模式。:param capture_full_http: 原捕获模式。"""

    model_config = ConfigDict(extra='forbid')
    id: StrictInt = Field(ge=1)
    quota_attempt: StrictInt = Field(default=0, ge=0)
    warmup: StrictBool = False
    capture_full_http: StrictBool = False
    claude_code_version_source: StrictStr | None = Field(default=None, max_length=128)


class RunWork(BaseModel):
    """原中央Run与有限worker环境，拒绝任意宿主路径和环境变量。

    :param id: 原12位Run标识。
    :param account_id: 原中央账号。
    :param task: 原实际任务模式。
    :param worker_env: 原driver已经解析的冻结输入、版本、时限与模型。
    :param project: 可选原经典实例上下文。
    """

    model_config = ConfigDict(extra='forbid')
    id: StrictStr = Field(pattern=r'^[a-f0-9]{12}$')
    account_id: StrictInt = Field(ge=1)
    task: RunTask
    worker_env: dict[StrictStr, StrictStr]
    project: LegacyProjectWork | None = None

    @model_validator(mode='after')
    def validate_execution(self):
        """核对实际启动所需字段与原Run来源，禁止worker覆盖root端点。:return: 原冻结工作。"""
        environment = self.worker_env
        required = {'RUN_ID', 'TASK_PROMPT', 'CLAUDE_CODE_VERSION', 'CLAUDE_CODE_EFFORT_LEVEL',
            'CLAUDE_PERMISSION_MODE', 'QUOTA_SOURCE', 'ACC_NAME', 'TIMEOUT_SEC'}
        if (not required.issubset(environment) or set(environment) - WORKER_ENVIRONMENT
                or environment['RUN_ID'] != self.id
                or environment['QUOTA_SOURCE'] != self.source
                or not re.fullmatch(r'2\.1\.[0-9]{1,6}', environment['CLAUDE_CODE_VERSION'])
                or environment['CLAUDE_PERMISSION_MODE'] not in ('manual', 'acceptEdits', 'bypassPermissions', 'plan', 'auto', 'dontAsk')
                or not environment['CLAUDE_CODE_EFFORT_LEVEL'] or len(environment['CLAUDE_CODE_EFFORT_LEVEL']) > 40
                or len(self.model_dump_json().encode()) > 192 * 1024):
            raise ValueError('节点Run缺少原冻结版本、模式、来源或工作超限')
        if self.project is not None:
            review=self.project.scenario is not None and self.project.scenario.review is not None
            if not self.shared_cli and not review or review and (self.task.capture_full_http or self.task.warmup):
                raise ValueError('原项目或评审的CLI模式不一致')
        model = environment.get('CLAUDE_MODEL_OVERRIDE')
        if model is not None and not re.fullmatch(r'[A-Za-z0-9._\-\[\]]{1,128}', model):
            raise ValueError('节点Run模型覆盖无效')
        return self

    @property
    def source(self) -> str:
        """取得原Run及额度尝试的唯一来源。:return: 原run source。"""
        return f'run:{self.id}:{self.task.quota_attempt}'

    @property
    def shared_cli(self) -> bool:
        """取得原普通任务的CLI槽位模式。:return: 原共享模式。"""
        if self.project is not None and self.project.scenario is not None and self.project.scenario.review is not None:
            return False
        return not self.task.capture_full_http and not self.task.warmup


class RunStart(BaseModel):
    """原准备环境与冻结Run。:param scope: 原有限范围。:param work: 原任务投影。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    work: RunWork

    @model_validator(mode='after')
    def validate_scope(self):
        """核对Run和原账号/source属于同一操作。:return: 原请求。"""
        if (self.scope.role != 'cli' or self.scope.account_id != self.work.account_id
                or self.scope.source != self.work.source):
            raise ValueError('节点Run与原执行scope不一致')
        return self


class RunArtifact(BaseModel):
    """原Run固定轻量产物的分段读取。:param scope: 原执行。:param name: 固定产物名。:param offset: 已读字节数。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    name: RunArtifactName
    offset: StrictInt = Field(default=0, ge=0)


class RunScenarioInput(RunStart):
    """原场景基线的具体暂存意图。:param archive: 原Scope和固定代码基线的完整包回执。"""

    archive: WorkspaceSnapshotArchive

    @model_validator(mode='after')
    def validate_base(self):
        """基线包必须属于同一场景输入和同一Scope。:return: 原请求。"""
        project=self.work.project
        if (project is None or project.scenario is None or self.archive.scope!=self.scope
                or project.scenario.review is not None
                or self.archive.purpose!='candidate'
                or self.archive.tree_digest!=project.scenario.files.inputs.code.base_checkpoint_digest):
            raise ValueError('原场景基线包与冻结Run不一致')
        return self


class RunScenarioStage(BaseModel):
    """读取原场景已登记的输入阶段包。:param scope: 原执行。:param stage: 实际回执中的阶段键。"""

    model_config=ConfigDict(extra='forbid')
    scope: ExecutionScope
    stage: StrictStr=Field(min_length=1,max_length=96)


class RunRefresh(BaseModel):
    """中央唯一所有者完成原刷新请求的结果。:param scope: 原执行。:param request_sha256: 原worker请求摘要。:param ok: 原所有者的固定结果。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    request_sha256: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    ok: StrictBool


class RunOwnerRefresh(BaseModel):
    """独立私有评审的原所有者刷新待办。

    :param scope: 原实际私有评审Scope。
    :param request_sha256: 原worker单次刷新请求的完整摘要。
    """

    model_config=ConfigDict(extra='forbid')
    scope:ExecutionScope
    request_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')


class RunFiles(BaseModel):
    """原Run公开文件清单分页。:param scope: 原执行。:param after: 原相对路径游标。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    after: StrictStr = Field(default='', max_length=4096)


class RunFile(BaseModel):
    """原Run公开产物预览。:param scope: 原执行。:param path: 受限相对路径。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    path: StrictStr = Field(min_length=1, max_length=4096)

    @model_validator(mode='after')
    def validate_path(self):
        """在节点目录读取前核对相对路径。:return: 原请求。"""
        safe_relative(self.path)
        if self.path.startswith('.bench-') or self.path.split('/')[0] in PRIVATE_ROOTS:
            raise ValueError('该路径不是公开运行产物')
        return self


class RunFileEntry(BaseModel):
    """公开文件树条目。:param path: 相对路径。:param type: 普通文件或目录。:param size: 文件字节数。"""

    model_config = ConfigDict(extra='forbid')
    path: StrictStr = Field(min_length=1, max_length=4096)
    type: Literal['file', 'dir']
    size: StrictInt | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def validate_entry(self):
        """拒绝跨目录路径和缺少大小的普通文件。:return: 原条目。"""
        safe_relative(self.path)
        if self.type == 'file' and self.size is None or self.type == 'dir' and self.size is not None:
            raise ValueError('节点公开文件条目无效')
        return self


class RunUsage(BaseModel):
    """原公开统计结构。:param tokens_in: 输入。:param tokens_out: 输出。:param requests: 请求数。:param errors: 错误数。"""

    model_config = ConfigDict(extra='forbid')
    tokens_in: StrictInt = Field(ge=0)
    tokens_out: StrictInt = Field(ge=0)
    requests: StrictInt = Field(ge=0)
    errors: StrictInt = Field(ge=0)
    available: StrictBool
    usage_available: StrictBool
    source: Literal['sidecar', 'claude_session', 'none']


class NodeRuns(NodeTerminals):
    """复用原节点启动回执和实际停止恢复，启动原AccountRuntime任务driver。

    :param executor: 原节点执行器。
    :param host: 原单例运行时。
    :param grants: 原有限证明。
    """

    def _directory(self, scope: ExecutionScope, *, create: bool = False) -> Path:
        if scope.node_key != self.executor.node_key or scope.role != 'cli':
            raise ValueError('节点Run执行范围无效')
        parent = self.executor.data / 'node-runs'
        environment = parent / scope.environment_id
        result = environment / scope.operation_id
        if create:
            for path in (parent, environment, result):
                private_directory(path)
        return result

    def _record(self, scope: ExecutionScope) -> dict:
        value = super()._record(scope)
        work = RunWork.model_validate(value['work'])
        if work.source != scope.source or work.account_id != scope.account_id:
            raise ValueError('节点Run回执与原冻结工作不一致')
        value['work'] = work.model_dump()
        return value

    def dispatch(self, operation: str, raw: bytes) -> dict:
        """只接受具体Run启动、短轮询和原监督器停止。

        :param operation: 固定Run动作。
        :param raw: 原有界JSON。
        :return: 有限原作业回执。
        """
        value = strict_json(raw, 256 * 1024)
        if operation=='run-review-input-stage':
            return self.stage_review_input(RunStart.model_validate(value))
        if operation=='run-review-input-commit':
            return self.commit_review_input(ExecutionScope.model_validate(value))
        if operation=='run-review-input-facts':
            scope=ExecutionScope.model_validate(value)
            return self._read(scope,lambda item:self._project(item).files.facts(),scope)
        if operation=='run-scenario-input-stage':
            return self.stage_scenario_input(RunScenarioInput.model_validate(value))
        if operation=='run-scenario-input-commit':
            return self.commit_scenario_input(ExecutionScope.model_validate(value))
        if operation=='run-scenario-input-facts':
            scope=ExecutionScope.model_validate(value)
            return self._read(scope,lambda item:self._project(item).files.facts(),scope)
        if operation=='run-scenario-input-archive':
            request=RunScenarioStage.model_validate(value)
            with self.executor._locked(environment_id=request.scope.environment_id):
                return self._project(request.scope).files.archive(request.stage)
        if operation == 'run-project-prepare':
            return self.prepare_project(RunStart.model_validate(value))
        if operation in ('run-project-configure','run-project-decision'):
            model=ProjectPlanPublish if operation=='run-project-configure' else ProjectPlanDecisionPublish
            if operation=='run-project-configure' and value.get('configuration',{}).get('workflow_schema')==3:
                model=ScenarioPlanPublish
            request=model.model_validate(value)
            with self.executor._locked(environment_id=request.scope.environment_id):
                record=self._record(request.scope)
                if operation=='run-project-configure':
                    if not record.get('project_prepared') or record.get('start_intent') or record['phase']!='starting':
                        raise ValueError('原计划配置发布阶段已关闭')
                    return self._project(request.scope).configure(request.configuration)
                if record['phase']!='ready':
                    raise ValueError('原计划执行尚未准备或已经停止')
                return self._project(request.scope).decision(request.decision)
        if operation == 'run-project-facts':
            scope = ExecutionScope.model_validate(value)
            return self._read(scope,lambda item:({'scope':item.model_dump(),'unsubmitted':True}
                if self._unsubmitted(item) is not None else self._project(item).facts()),scope)
        if operation == 'run-project-native':
            request = ProjectNativeRead.model_validate(value)
            return self._read(request.scope, lambda item:self._project(item.scope).read(item), request)
        if operation == 'run-project-permit':
            return self.permit_project(ExecutionScope.model_validate(value))
        if operation == 'run-start':
            return self.start(RunStart.model_validate(value))
        if operation == 'run-get':
            return self.get(ExecutionScope.model_validate(value))
        if operation == 'run-poll':
            return self.poll(ExecutionScope.model_validate(value))
        if operation == 'run-recover':
            return self.recover_stop(ExecutionScope.model_validate(value))
        if operation == 'run-control':
            return self.control(TerminalControl.model_validate(value))
        if operation == 'run-artifact':
            return self.artifact(RunArtifact.model_validate(value))
        if operation == 'run-session':
            return self.latest_session(ExecutionScope.model_validate(value))
        if operation == 'run-files':
            request = RunFiles.model_validate(value)
            return self._read(request.scope, self.files, request)
        if operation == 'run-file':
            request = RunFile.model_validate(value)
            return self._read(request.scope, self.file, request)
        if operation == 'run-stats':
            scope = ExecutionScope.model_validate(value)
            return self._read(scope, self.stats, scope)
        if operation == 'run-capture':
            request = TerminalCapture.model_validate(value)
            return self._read(request.scope, self.capture, request)
        if operation in ('run-refresh', 'run-refresh-get'):
            return self.refresh(RunRefresh.model_validate(value), query=operation == 'run-refresh-get')
        if operation=='run-owner-refresh-defer':
            return self.defer_owner_refresh(RunOwnerRefresh.model_validate(value))
        raise ValueError('节点Run动作无效')

    def files(self, request: RunFiles) -> dict:
        """只列出原work物理目录的有界公开文件树。

        :param request: 原scope和路径游标。
        :return: 最多128条及96KiB的一页，缺失目录有独立状态。
        """
        self._reader(request.scope)
        path = self._workspace(request.scope)
        try:
            entries = list_workspace_files(path)
        except FileNotFoundError:
            return {'scope': request.scope.model_dump(), 'available': False, 'files': [], 'next': None}
        page, size, cursor = [], 0, None
        for entry in entries:
            if entry['path'] <= request.after:
                continue
            length = len(json.dumps(entry, ensure_ascii=False).encode())
            if len(page) >= 128 or size + length > 96 * 1024:
                cursor = page[-1]['path']
                break
            size += length
            page.append(entry)
        return {'scope': request.scope.model_dump(), 'available': True, 'files': page, 'next': cursor}

    def file(self, request: RunFile) -> dict:
        """沿原64KiB预览合同读取文件，正文经base64限制私有回执大小。

        :param request: 原执行和相对路径。
        :return: UTF-8预览与元信息，缺失文件有独立状态。
        """
        self._reader(request.scope)
        path = self._workspace(request.scope)
        try:
            value = read_workspace_file(path.parent, path.name, request.path)
        except OSError:
            return {'scope': request.scope.model_dump(), 'available': False}
        text = value.pop('text')
        return {'scope': request.scope.model_dump(), 'available': True, **value,
            'text_base64': base64.b64encode(text.encode()).decode()}

    def stats(self, scope: ExecutionScope) -> dict:
        """按原task/run固定流组聚合各尝试与本次会话。

        :param scope: 原执行。
        :return: 与原公开stats一致的共享聚合结果。
        """
        self._reader(scope)
        group = self._flow_group(scope)
        paths = []
        try:
            descriptor = directory_fd(group)
        except FileNotFoundError:
            descriptor = None
        if descriptor is not None:
            try:
                for relative in ('stats.jsonl',):
                    try:
                        info = os.stat(relative, dir_fd=descriptor, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if not S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise ValueError('原Run统计文件类型无效')
                    paths.append(group / relative)
            finally:
                os.close(descriptor)
            try:
                executions = directory_fd(group / 'executions')
            except FileNotFoundError:
                executions = None
            if executions is not None:
                try:
                    with os.scandir(executions) as children:
                        for count, child in enumerate(children, 1):
                            if count > 10000:
                                raise ValueError('原Run统计尝试数量超过读取上限')
                            if not re.fullmatch('[a-f0-9]{20}', child.name) or not child.is_dir(follow_symlinks=False):
                                continue
                            path = group / 'executions' / child.name / 'stats.jsonl'
                            try:
                                path.lstat()
                            except FileNotFoundError:
                                continue
                            paths.append(path)
                finally:
                    os.close(executions)
        session = self.executor.data / 'environments' / scope.environment_id / 'home/.claude/projects' / (
            '/home/node/projects/' + self._workspace(scope).name).replace('/', '-')
        native = (lambda:{'tokens_in':0,'tokens_out':0,'requests':0,'usage_available':False}) if self._record(scope)['work'].get('project') else lambda:native_session_usage(session)
        return {'scope': scope.model_dump(), 'stats': run_usage(sorted(paths),native)}

    def _workspace(self, scope: ExecutionScope) -> Path:
        # 历史读取依赖冻结scope；可变runs行会在下一次额度尝试时更新。
        work = RunWork.model_validate(self._record(scope)['work'])
        run_id = work.id
        if work.project is not None:
            return self._project(scope).workspace
        return self.executor.data / 'environments' / scope.environment_id / 'projects' / ordinary_run_alias(scope.environment_id, run_id)

    def _flow_group(self, scope: ExecutionScope) -> Path:
        work = RunWork.model_validate(self._record(scope)['work'])
        if work.project is not None and work.project.scenario is not None and work.project.scenario.review is not None:
            return self._project(scope).files.private_root/'flows'
        return self.executor.data / 'environments' / scope.environment_id / 'flows' / (
            'group-' + hashlib.sha256(f'{work.task.id}/{work.id}'.encode()).hexdigest()[:20])

    def quota_source(self, scope: ExecutionScope, stream: str) -> Path | None:
        """读取原私有评审的固定额度文件。

        :param scope: 原Run。
        :param stream: 原CLI或recorder证据流。
        :return: 原私有文件；候选和普通任务为None。
        """
        work=RunWork.model_validate(self._record(scope)['work'])
        if work.project is not None and work.project.scenario is not None and work.project.scenario.review is not None:
            return self._project(scope).files.private_root/'flows'/('cli/cli-quota.jsonl' if stream=='cli' else 'passive-quota.jsonl')
        return None

    def capture(self, request: TerminalCapture) -> dict:
        """复用原公开抓包白名单，原始证据留在原环境。

        :param request: 原执行、活动事实和公开元数据路径。
        :return: 有界脱敏投影。
        """
        self._reader(request.scope)
        record = self._record(request.scope)
        if not record['work']['task']['capture_full_http']:
            raise ValueError('该原Run不是完整抓包执行')
        value = run_capture(self._flow_group(request.scope),
            running=request.running and record['phase'] == 'ready', relative=request.relative)
        return {'scope': request.scope.model_dump(), 'capture': value}

    def defer_owner_refresh(self, request: RunOwnerRefresh) -> dict:
        """核对具体401请求后持久保存原Node所有者待办。

        :param request: 原私有评审Scope与worker请求摘要。
        :return: 原待办的有界确认；重复调用保持同一原请求。
        """
        scope=request.scope
        with self.executor._locked(environment_id=scope.environment_id):
            record=self._record(scope)
            work=RunWork.model_validate(record['work'])
            if (scope.gateway_account_id is not None or work.project is None or work.project.scenario is None
                    or work.project.scenario.review is None):
                raise ValueError('原Node所有者待办仅用于独立私有评审')
            path=self._directory(scope)/'owner-refresh-defer.json'
            expected={'protocol':1,'scope':scope.model_dump(),'request_sha256':request.request_sha256,
                'phase':'deferred','request_id':hashlib.sha256(scope.source.encode()).hexdigest()}
            if path.exists() or path.is_symlink():
                if strict_json(safe_read(path,16384,private=True),16384)!=expected:
                    raise ValueError('原评审刷新待办请求已变化')
                return expected
            if record['phase']!='ready' or self.host.runtime is None:
                raise ValueError('原私有评审实际定位需要先核对')
            self.grants.authorize(scope)
            runtime=self.host.runtime
            job=runtime.job_for_container(record['result']['token'])
            if job.get('source')!=scope.source or job.get('execution_role')!='project-review':
                raise ValueError('原401请求与实际私有评审不一致')
            source=self._source_artifact(scope,record,runtime,'oauth-refresh-request.json')
            raw=safe_read(source,8192)
            strict_json(raw,8192)
            if hashlib.sha256(raw).hexdigest()!=request.request_sha256:
                raise ValueError('原worker刷新请求已变化')
            runtime.reviews.defer_owner_refresh(job)
            runtime.reviews.wait_owner_refresh_exit(job)
            atomic_json(path,expected)
            return expected

    def refresh(self, request: RunRefresh, *, query: bool = False) -> dict:
        """只发布中央所有者的原结果和已投影AT，节点保持原RT所有权边界。

        :param request: 原请求摘要与中央固定结论。
        :param query: 是否只查询原结果意图。
        :return: 原发布阶段；重复结果保持同一结论。
        """
        scope = request.scope
        with self.executor._locked(environment_id=scope.environment_id):
            record = self._record(scope)
            if scope.gateway_account_id is None:
                raise ValueError('独立账号刷新沿原本地所有者流程处理')
            path = self._directory(scope) / 'refresh.json'
            expected = request.model_dump()
            if path.exists() or path.is_symlink():
                receipt = strict_json(safe_read(path, 16384, private=True), 16384)
                if receipt.get('request') != expected or receipt.get('phase') not in ('pending', 'ready'):
                    raise ValueError('原Run刷新发布结论已变化')
                if receipt['phase'] == 'ready' or query:
                    return receipt
            elif query:
                raise ValueError('原Run刷新发布尚未登记')
            if record['phase'] != 'ready' or self.host.runtime is None:
                raise ValueError('原Run已经停止或需要核对')
            runtime = self.host.runtime
            with runtime.environment_lock(scope.environment_id):
                self.grants.authorize(scope)
                job = runtime.job_for_container(record['result']['token'])
                source = self._source_artifact(scope,record,runtime,'oauth-refresh-request.json')
                if hashlib.sha256(safe_read(source, 8192)).hexdigest() != request.request_sha256:
                    raise ValueError('原worker刷新请求已变化')
                receipt = {'request': expected, 'phase': 'pending'}
                atomic_json(path, receipt)
                if request.ok:
                    # NodePreparation只投影AT；实际HOME/访问文件仍由原运行时发布。
                    runtime.sync_credentials(job['row'], job['account'])
                    if job.get('execution_role')=='project-review':
                        runtime.reviews.sync_credentials(job)
                self.grants.authorize(scope)
                destination = self._source_artifact(scope,record,runtime,'oauth-refresh-result.json')
                result = {'ok': request.ok}
                if not request.ok:
                    result['error'] = '中央OAuth所有者刷新失败，请核对原账号状态'
                atomic_json(destination, result, mode=0o640)
                os.chown(destination, 0, 1000, follow_symlinks=False)
                receipt['phase'] = 'ready'
                atomic_json(path, receipt)
                return receipt

    def get(self, scope: ExecutionScope) -> dict:
        """读取原启动回执及实际worker未决输入，重启后仍保留定位。

        :param scope: 原执行。
        :return: 原回执；运行时重启沿原NodeRestart合同投影。
        """
        result = super().get(scope)
        if result['phase'] == 'closed' and self._unsubmitted(scope) is None and self._archive_index(scope) is None:
            result.update(phase='reconcile', error_type='ArchivePending')
        path = self.executor.data / 'node-inputs' / scope.environment_id / scope.operation_id / 'state.json'
        if path.exists() or path.is_symlink():
            state = strict_json(safe_read(path, 8192, private=True), 8192)
            pending = state.get('pending_input')
            if (state.get('scope') != scope.model_dump()
                    or pending is not None and not re.fullmatch('[a-f0-9]{32}', str(pending))):
                raise ValueError('原Run输入指针与启动范围不一致')
            result['pending_input'] = pending
        return result

    def _archive_root(self, scope: ExecutionScope) -> Path:
        return self.executor.data / 'environments' / scope.environment_id / 'runtime/node-run-archives' / scope.operation_id

    def _archive_index(self, scope: ExecutionScope) -> dict | None:
        try:
            value = strict_json(safe_read(self._archive_root(scope) / 'index.json', 16384, private=True), 16384)
        except FileNotFoundError:
            return None
        if value.get('scope') != scope.model_dump() or not isinstance(value.get('files'), dict):
            raise ValueError('原Run冻结产物归属无效')
        for name, metadata in value['files'].items():
            RunArtifact(scope=scope, name=name)
            if (not isinstance(metadata, dict) or type(metadata.get('bytes')) is not int or metadata['bytes'] < 0
                    or not re.fullmatch('[a-f0-9]{64}', str(metadata.get('sha256')))):
                raise ValueError('原Run冻结产物清单无效')
            actual = (self._archive_root(scope) / name).lstat()
            if (not S_ISREG(actual.st_mode) or actual.st_nlink != 1 or actual.st_uid != os.geteuid()
                    or actual.st_mode & 0o077 or actual.st_size != metadata['bytes']):
                raise ValueError('原Run冻结产物文件与清单不一致')
        return value

    def recover_stop(self, scope: ExecutionScope) -> dict:
        """先沿原监督器实际停止，再冻结本次产物供额度恢复和历史读取。

        :param scope: 原执行。
        :return: 已确认停止与原产物冻结完成回执。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            path=self._directory(scope)/'execution.json'
            if path.exists() or path.is_symlink():
                record=self._record(scope)
                work=RunWork.model_validate(record['work'])
                if work.project is not None and work.project.execution_plan() is not None and record.get('start_intent') is False:
                    if record.get('project_prepared'):
                        self._project(scope).finish()
                    self.grants.close(scope,'node_not_started')
                    record['phase']='closed'
                    atomic_json(path,record)
                    receipt={'protocol':1,'scope':scope.model_dump(),'phase':'closed','result':None,'pending_input':None}
                    atomic_json(self._directory(scope)/'unsubmitted.json',receipt)
                    return {'stopped':True}
        result = super().recover_stop(scope)
        if self._unsubmitted(scope) is not None:
            return result
        with self.executor._locked(environment_id=scope.environment_id):
            if self._archive_index(scope) is None:
                if RunWork.model_validate(self._record(scope)['work']).project is not None:
                    self._project(scope).finish()
                self._archive(scope)
        return result

    def _archive(self, scope: ExecutionScope) -> None:
        record, runtime = self._record(scope), self._reader(scope)
        if record['phase'] != 'closed':
            raise ValueError('原Run实际停止后才能冻结产物')
        root = self._archive_root(scope)
        private_directory(root.parent)
        private_directory(root)
        files = {}
        for name in ('status.json', 'transcript.log', 'session-baseline.json', 'followups.json', 'oauth-refresh-request.json', 'quota-control.json', 'project-plan-request.json', 'project-plan-state.json', 'project-work.json'):
            source = self._source_artifact(scope, record, runtime, name)
            try:
                parent = directory_fd(source.parent)
            except FileNotFoundError:
                continue
            try:
                try:
                    descriptor = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                except FileNotFoundError:
                    continue
            finally:
                os.close(parent)
            temporary = root / ('.' + name + '.' + uuid4().hex + '.tmp')
            try:
                with os.fdopen(descriptor, 'rb') as original:
                    metadata = os.fstat(original.fileno())
                    if (not S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                            or name == 'followups.json' and metadata.st_mode & 0o077):
                        raise ValueError('原Run冻结产物必须是普通单链接文件')
                    if metadata.st_mtime < record.get('node_intent_at', 0):
                        continue
                    digest, remaining = hashlib.sha256(), metadata.st_size
                    with temporary.open('xb') as target:
                        temporary.chmod(0o600)
                        while remaining:
                            content = original.read(min(128 * 1024, remaining))
                            if not content:
                                raise ValueError('原Run停止后产物大小发生变化')
                            target.write(content)
                            digest.update(content)
                            remaining -= len(content)
                        target.flush()
                        os.fsync(target.fileno())
                    temporary.replace(root / name)
                    files[name] = {'bytes': metadata.st_size, 'sha256': digest.hexdigest()}
            finally:
                temporary.unlink(missing_ok=True)
        atomic_json(root / 'index.json', {'scope': scope.model_dump(), 'files': files})

    def _source_artifact(self, scope: ExecutionScope, record: dict, runtime, name: str) -> Path:
        work=RunWork.model_validate(record['work'])
        review=work.project is not None and work.project.scenario is not None and work.project.scenario.review is not None
        if name == 'quota-control.json':
            handle = hashlib.sha256(scope.source.encode()).hexdigest()[:20]
            controls=self._project(scope).control_root() if review else self.executor.data/'environments'/scope.environment_id/'controls'
            path = controls/handle/'pause.json'
            if path.exists() or path.is_symlink():
                metadata = path.lstat()
                if not S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
                    raise ValueError('原Run额度补证必须来自root只读控制目录')
            return path
        if review:
            return self._project(scope).runtime_run_directory()/name
        return runtime.run_artifact_path(record['work']['id'], name)

    def _reader(self, scope: ExecutionScope):
        self._record(scope)
        self.grants.get(scope)
        return self.host.runtime or self.host.recovery_runtime(scope)

    def artifact(self, request: RunArtifact) -> dict:
        """按原Run归属读取固定产物，保持半行和原始字节。

        :param request: 原scope、产物名与游标。
        :return: 最多128KiB文件片段。
        """
        return self._read(request.scope, self._artifact, request)

    def _artifact(self, request: RunArtifact) -> dict:
        runtime = self._reader(request.scope)
        record = self._record(request.scope)
        if record['phase'] == 'closed':
            if self._archive_index(request.scope) is None:
                raise ValueError('原Run冻结产物等待核对')
            path = self._archive_root(request.scope) / request.name
        else:
            path = self._source_artifact(request.scope, record, runtime, request.name)
        return {'scope': request.scope.model_dump(), 'name': request.name,
            **_read_quota_file(path, request.offset, private=request.name == 'followups.json')}

    def latest_session(self, scope: ExecutionScope) -> dict:
        """沿原本次目录和基线选择实际主会话，供中央原额度恢复使用。

        :param scope: 原执行。
        :return: 该次实际有新字节的最近会话标识或None。
        """
        return self._read(scope, self._latest_session, scope)

    def _latest_session(self, scope: ExecutionScope) -> dict:
        runtime, record = self._reader(scope), self._record(scope)
        run_id = record['work']['id']
        base = (self._project(scope).native if record['work'].get('project') else runtime.run_session_path(run_id))
        baseline_path = (self._archive_root(scope) / 'session-baseline.json' if record['phase'] == 'closed'
            else runtime.run_artifact_path(run_id, 'session-baseline.json'))
        baseline = strict_json(safe_read(baseline_path, 512 * 1024), 512 * 1024) if baseline_path.exists() else {}
        latest, newest, count = None, -1, 0
        for path in base.glob('*.jsonl'):
            count += 1
            if count > 10000:
                raise ValueError('原Run会话文件数量超过受限读取范围')
            metadata = path.lstat()
            if (not S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_size <= int(baseline.get(path.name, 0))
                    or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', path.stem)):
                continue
            if metadata.st_mtime_ns > newest:
                latest, newest = path.stem, metadata.st_mtime_ns
        return {'scope': scope.model_dump(), 'session_id': latest}

    def _project(self, scope: ExecutionScope) -> NodeLegacyProject:
        work = RunWork.model_validate(self._record(scope)['work'])
        if work.project is None:
            raise ValueError('原Run没有经典项目上下文')
        if work.project.scenario is None:
            provider=NodeLegacyProject
        else:
            provider=NodeScenarioReview if work.project.scenario.review is not None else NodeScenarioProject
        return provider(self.executor.data,scope,work.id,work.project,self.grants)

    def permit_project(self, scope: ExecutionScope) -> dict:
        """中央保存原物化事实并复核批次后，放行原监督进程一次。

        :param scope: 原已准备的节点执行。
        :return: 原放行事实，重复命令核对同一监督器。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            record = self._record(scope)
            if record['phase']!='ready' or self.host.runtime is None:
                raise ValueError('原经典项目监督进程尚未准备')
            project=self._project(scope)
            project.current_workspace()
            runtime = self.host.runtime
            job = runtime.job_for_container(record['result']['token'])
            if (job['source']!=scope.source or job['run_id']!=record['work']['id']
                    or job['account']['id']!=scope.account_id or job['row']['environment_id']!=scope.environment_id
                    or job['row']['generation']!=scope.generation
                    or bool(job.get('shared_cli'))!=RunWork.model_validate(record['work']).shared_cli
                    or (isinstance(project,NodeScenarioReview) and job.get('execution_role')!='project-review')):
                raise ValueError('原经典项目放行与实际监督器不一致')
            self.grants.authorize(scope)
            runtime.authorize_input(job)
            path = project.control_root()/job['handle']/'start.json'
            expected = job['process']
            if path.exists() or path.is_symlink():
                if strict_json(safe_read(path,16384),16384)!=expected:
                    raise ValueError('原经典项目监督放行事实已变化')
            else:
                atomic_json(path,expected,0o640)
                os.chown(path,0,1000,follow_symlinks=False)
            return {'scope':scope.model_dump(),'permitted':True}

    def snapshot_workspace(self, request) -> Path:
        """核对原冻结候选或实际停止后的目录所有者。

        :param request: 原快照请求。
        :return: 原实际项目目录。
        """
        if request.purpose!='candidate':
            raise ValueError('经典项目seed由原内容摘要提供')
        scope = request.scope
        record = self._record(scope)
        project = self._project(scope)
        workspace = project.current_workspace()
        if record['phase']=='ready':
            runtime = self.host.runtime
            if runtime is None:
                raise ValueError('原经典项目需要先核对节点恢复')
            job=runtime.job_for_container(record['result']['token'])
            if (job['source']!=scope.source or job['run_id']!=record['work']['id']
                    or job['account']['id']!=scope.account_id or job['row']['environment_id']!=scope.environment_id
                    or job['row']['generation']!=scope.generation):
                raise ValueError('原经典项目候选与实际作业身份不一致')
            proof = runtime.control_execution(record['result']['token'],'freeze')
            if proof.get('source')!=scope.source or proof.get('frozen') is not True:
                raise ValueError('原经典项目进程树尚未实际冻结')
        elif record['phase']!='closed':
            raise ValueError('原经典项目尚未确认实际停止')
        return workspace

    def stage_scenario_input(self, request: RunScenarioInput) -> dict:
        """认领原场景文件准备意图，并创建本次源码包的固定暂存目录。

        :param request: 原Run、Scope及冻结基线包。
        :return: 原暂存回执；后续仍需完整导入核验。
        """
        scope,work=request.scope,request.work
        with self.executor._locked(environment_id=scope.environment_id):
            path=self._directory(scope,create=True)/'execution.json'
            archive=request.archive.model_dump()
            if path.exists() or path.is_symlink():
                record=self._record(scope)
                if record['work']!=work.model_dump() or record.get('scenario_input_archive')!=archive:
                    raise ValueError('原场景输入暂存意图已经冻结')
                self.grants.authorize(scope)
            else:
                record={'protocol':1,'scope':scope.model_dump(),'work':work.model_dump(),'phase':'starting',
                    'result':None,'pending_input':None,'shared_cli':work.shared_cli,'node_intent_at':time.time(),
                    'project_prepared':False,'start_intent':False,'scenario_input_archive':archive,
                    'scenario_input_ready':False,'project_prepare_intent':False}
                atomic_json(path,record)
                self.grants.activate(scope)
            operation=self._project(scope).files.operation
            private_directory(operation)
            directory=operation/'imports'/request.archive.snapshot_id
            private_directory(directory)
            return {'scope':scope.model_dump(),'archive':archive,'staged':True}

    def commit_scenario_input(self, scope: ExecutionScope) -> dict:
        """从本次固定暂存文件核对完整源码包，再登记输入基线就绪。

        :param scope: 原场景执行。
        :return: 原输入基线摘要及就绪事实。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            record=self._record(scope)
            receipt=WorkspaceSnapshotArchive.model_validate(record['scenario_input_archive'])
            self.grants.authorize(scope)
            if not record.get('scenario_input_ready'):
                if record['phase']!='starting' or record.get('project_prepare_intent') or record.get('start_intent'):
                    raise ValueError('原场景基线导入阶段已经关闭')
                files=self._project(scope).files
                files.import_base(files.operation/'imports'/receipt.snapshot_id/'snapshot.tar',receipt)
                record['scenario_input_ready']=True
                atomic_json(self._directory(scope)/'execution.json',record)
            return {'scope':scope.model_dump(),'tree_digest':receipt.tree_digest,'ready':True}

    def stage_review_input(self, request: RunStart) -> dict:
        """认领原私有评审包暂存意图，禁止包内容进入候选挂载根。

        :param request: 原非共享Run及冻结包身份。
        :return: 原Scope及包暂存事实。
        """
        scope,work=request.scope,request.work
        if work.project is None or work.project.scenario is None or work.project.scenario.review is None:
            raise ValueError('原Run缺少冻结私有评审包')
        with self.executor._locked(environment_id=scope.environment_id):
            path=self._directory(scope,create=True)/'execution.json'
            review=work.project.scenario.review.model_dump()
            if path.exists() or path.is_symlink():
                record=self._record(scope)
                if record['work']!=work.model_dump() or record.get('review_input')!=review:
                    raise ValueError('原私有评审包暂存意图已经冻结')
                grant=self.grants.authorize(scope)
            else:
                record={'protocol':1,'scope':scope.model_dump(),'work':work.model_dump(),'phase':'starting',
                    'result':None,'pending_input':None,'shared_cli':False,'node_intent_at':time.time(),
                    'project_prepared':False,'start_intent':False,'review_input':review,
                    'review_input_ready':False,'project_prepare_intent':False}
                atomic_json(path,record)
                grant=ExecutionGrant.model_validate(self.grants.activate(scope)['grant'])
            if grant.lease is not None and (grant.lease.shared_cli or grant.lease.exclusive):
                raise ValueError('原私有评审需要非共享CLI证明')
            private_directory(self._project(scope).files.operation)
            return {'scope':scope.model_dump(),'review':review,'staged':True}

    def commit_review_input(self, scope: ExecutionScope) -> dict:
        """核对完整原评审包后登记就绪，重复核对不执行CLI。

        :param scope: 原非共享Run。
        :return: 原包摘要及实际就绪事实。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            record=self._record(scope)
            self.grants.authorize(scope)
            if not record.get('review_input_ready'):
                if record['phase']!='starting' or record.get('project_prepare_intent') or record.get('start_intent'):
                    raise ValueError('原私有评审包导入阶段已经关闭')
                self._project(scope).files.package()
                record['review_input_ready']=True
                atomic_json(self._directory(scope)/'execution.json',record)
            return {'scope':scope.model_dump(),'sha256':record['review_input']['sha256'],'ready':True}

    def prepare_project(self, request: RunStart) -> dict:
        """在实际exec意图之前准备原计划工作区和原生起点。

        :param request: 原冻结计划Run及有限证明。
        :return: 原文件准备事实；重复准备始终读取原记录。
        """
        scope,work=request.scope,request.work
        if work.project is None or work.project.execution_plan() is None:
            raise ValueError('原Run没有需要预准备的同会话计划')
        with self.executor._locked(environment_id=scope.environment_id):
            path=self._directory(scope,create=True)/'execution.json'
            staged=False
            if path.exists() or path.is_symlink():
                record=self._record(scope)
                if record['work']!=work.model_dump():
                    raise ValueError('原计划文件准备结果需要核对')
                if record.get('project_prepared'):
                    return {'scope':scope.model_dump(),'prepared':True}
                ready='review_input_ready' if work.project.scenario is not None and work.project.scenario.review is not None else 'scenario_input_ready'
                if (work.project.scenario is None or not record.get(ready)
                        or record.get('project_prepare_intent') or record.get('start_intent') or record['phase']!='starting'):
                    raise ValueError('原场景文件准备需要核对已导入基线和原意图')
                staged=True
                record['project_prepare_intent']=True
            else:
                if work.project.scenario is not None:
                    raise ValueError('原场景需要先核对中央已接受基线包')
                record={'protocol':1,'scope':scope.model_dump(),'work':work.model_dump(),'phase':'starting',
                    'result':None,'pending_input':None,'shared_cli':work.shared_cli,'node_intent_at':time.time(),
                    'project_prepared':False,'start_intent':False}
            # 文件意图先于证明认领；中断后只允许按原记录停止，避免未知准备被重做。
            atomic_json(path,record)
            if staged:
                self.grants.authorize(scope)
            else:
                self.grants.activate(scope)
            try:
                connection=self.executor.database()
                try:
                    row=connection.execute('SELECT * FROM account_environments WHERE environment_id=? AND account_id=?',
                        (scope.environment_id,scope.account_id)).fetchone()
                finally:
                    connection.close()
                if row is None:
                    raise ValueError('原计划账号环境缺失')
                project=self._project(scope)
                project.prepare_workspace(dict(row),work.id,project.root)
                project.record_native_start(work.id,project.native)
                record['project_prepared']=True
            except Exception as error:
                record.update(phase='reconcile',error_type=type(error).__name__)
                atomic_json(path,record)
                raise
            atomic_json(path,record)
            return {'scope':scope.model_dump(),'prepared':True}

    def start(self, request: RunStart) -> dict:
        """一次认领并启动原driver，重复请求只读取原意图。

        :param request: 原冻结工作和中央许可。
        :return: ready或reconcile启动回执。
        """
        scope, work = request.scope, request.work
        with self.executor._locked(environment_id=scope.environment_id):
            directory = self._directory(scope, create=True)
            path = directory / 'execution.json'
            prepared=None
            if path.exists() or path.is_symlink():
                previous = self._record(scope)
                if previous['work'] != work.model_dump():
                    raise ValueError('原节点Run启动工作已变化')
                if (work.project is None or work.project.execution_plan() is None or not previous.get('project_prepared')
                        or previous.get('start_intent') or previous['phase']!='starting'):
                    return self._receipt(previous)
                self.grants.authorize(scope)
                prepared=previous
            elif work.project is not None and work.project.execution_plan() is not None:
                raise ValueError('原同会话计划需要先完成中央配置与文件准备')
            runtime = self.host.runtime
            if runtime is None or self.host.closed or runtime.project_iterations is not None:
                raise ValueError('节点Run运行时尚未准备或上下文需要核对')
            connection = self.executor.database()
            try:
                saved = connection.execute('SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL',
                    (scope.account_id,)).fetchone()
                if saved is None or saved['cc2api_account_id'] != scope.gateway_account_id or saved['name'] != work.worker_env['ACC_NAME']:
                    raise ValueError('节点Run账号或绑定已变化')
                account = dict(saved)
                # 只投影本次Run用于原运行时更新定位；任务定义与全局调度继续归中央。
                with connection:
                    previous = connection.execute('SELECT account_id,task_id,quota_attempt FROM runs WHERE id=?', (work.id,)).fetchone()
                    if previous is not None and (previous['account_id'] != scope.account_id or previous['task_id'] != work.task.id
                            or previous['quota_attempt'] > work.task.quota_attempt):
                        raise ValueError('节点Run投影存在旧账号或更新尝试')
                    connection.execute('INSERT INTO runs(id,account_id,task_id,quota_attempt) VALUES(?,?,?,?) '
                        'ON CONFLICT(id) DO UPDATE SET quota_attempt=excluded.quota_attempt',
                        (work.id, scope.account_id, work.task.id, work.task.quota_attempt))
            finally:
                connection.close()
            if prepared is None:
                self.grants.activate(scope)
            record = {'protocol': 1, 'scope': scope.model_dump(), 'work': work.model_dump(), 'phase': 'starting',
                'result': None, 'pending_input': None, 'shared_cli': work.shared_cli, 'node_intent_at': time.time()}
            if prepared is not None:
                record=prepared
                record['start_intent']=True
            atomic_json(path, record)
            try:
                mirror = self.host.gateway.lease_mirror
                mirror.attach(scope)
                quota = quota_scope_path(self.executor.data, scope)
                state = strict_json(safe_read(quota, 96 * 1024, private=True), 96 * 1024)
                context = state['state']['remote_cli']
                identity = self.host.gateway.quota_identity(account)
                if (state['scope'] != scope.model_dump() or context['source'] != scope.source
                        or state['state']['identity'] != identity):
                    raise ValueError('节点Run缺少原中央额度许可')
                kind=('project_review' if work.project is not None and work.project.scenario is not None
                    and work.project.scenario.review is not None else 'project_iteration' if work.project is not None
                    else 'warmup' if work.task.warmup else 'capture' if work.task.capture_full_http else 'normal')
                connection=self.executor.database()
                try:
                    with connection:
                        cursor=connection.execute('UPDATE runs SET quota_identity=?,run_kind=? WHERE id=? AND account_id=? AND quota_attempt=?',
                            (identity,kind,work.id,scope.account_id,work.task.quota_attempt))
                        if cursor.rowcount!=1:
                            raise ValueError('节点Run角色或额度身份投影已变化')
                finally:
                    connection.close()
                quota_env = {'QUOTA_SOURCE': scope.source, 'QUOTA_IDENTITY': identity,
                    'QUOTA_STATE_FILE': '/quota-account/state.json', 'QUOTA_SIGNAL_FILE': '/quota-control/pause.json',
                    'QUOTA_OBSERVATIONS_FILE': '/flows/passive-quota.jsonl',
                    'QUOTA_WARMUP': '1' if work.task.warmup else '0',
                    'QUOTA_SAMPLE_REQUIRED': '1' if context['sample_required'] else '0'}
                with mirror.preparing(scope):
                    options = {'project_manager': self._project(scope),
                        'defer_permission': True} if work.project is not None else {}
                    _, token = runtime.start_run(account, work.task.model_dump(), work.id, dict(work.worker_env), quota_env, **options)
                record.update(phase='ready', result={'token': token, 'source': scope.source}, node_started_at=time.time())
            except Exception as error:
                record.update(phase='reconcile', error_type=type(error).__name__)
            atomic_json(path, record)
            return self._receipt(record)

    def poll(self, scope: ExecutionScope) -> dict:
        """短轮询原exec，实际退出与未知输入分开返回。

        :param scope: 原冻结执行。
        :return: 实际进程状态与原worker状态。
        """
        return self._read(scope, self._poll, scope)

    def _read(self, scope: ExecutionScope, reader, request) -> dict:
        try:
            with self.executor._locked(read_only=True, environment_id=scope.environment_id):
                return reader(request)
        except BlockingIOError:
            return {'scope': scope.model_dump(), 'busy': True}

    def _poll(self, scope: ExecutionScope) -> dict:
        record = self._record(scope)
        if not record.get('result') or self.host.runtime is None:
            raise ValueError('原节点Run尚未取得实际执行定位')
        runtime = self.host.runtime
        job = runtime.job_for_container(record['result']['token'])
        inspected = runtime.client.api.exec_inspect(job['exec'])
        if inspected.get('Running') and job.get('shared_cli'):
            result = runtime._process_result(job)
            if result is not None and not result.get('cleaned'):
                raise ValueError('原节点Run子进程尚未完成收口')
        pending = self.host.inputs.brokers.get(job['token'])
        pending_id = pending.state()['pending_input'] if pending is not None else None
        status_path = self._source_artifact(scope,record,runtime,'status.json')
        status = strict_json(safe_read(status_path, 65536), 65536) if status_path.exists() else {}
        return {'scope': scope.model_dump(), 'running': bool(inspected.get('Running')),
            'exit_code': inspected.get('ExitCode') if not inspected.get('Running') else None,
            'worker_status': status, 'pending_input': pending_id}

    def control(self, request: TerminalControl) -> dict:
        """沿原实际token停止或控制监督器。

        :param request: 原作业与固定动作。
        :return: 原监督器回执；停止由恢复合同核对真实收口。
        """
        if request.operation == 'stop':
            return self.recover_stop(request.scope)
        with self.executor._locked(environment_id=request.scope.environment_id):
            record = self._record(request.scope)
            if record['phase'] != 'ready' or self.host.runtime is None:
                raise ValueError('原节点Run尚未就绪')
            if request.operation == 'resume':
                self.grants.authorize(request.scope)
            return self.host.runtime.control_execution(record['result']['token'], request.operation)
