"""节点具体Pi终端操作及一次性启动、输入回执，沿用原工程执行器。"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Literal

from docker.errors import NotFound
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from cluster_execution_grants import ExecutionScope
from cluster_quota import quota_scope_path
from pi_terminal import KEYS
from project_library import ProjectLibrary
from projects_catalog import ProjectsCatalog
from projects_runtime import ProjectsTerminal
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class TerminalWork(BaseModel):
    """原中央工作中由Pi和工程准备实际消费的冻结字段。

    :param id: 原工作。
    :param account_id: 原中央账号。
    :param generation: 原控制代次。
    :param session_id: 原Claude会话。
    :param project_key: 冻结项目。
    :param objective_id: 冻结目标。
    :param library_digest: 冻结内容摘要，节点目录由服务端计算。
    :param settings_json: 原CLI设置。
    :param remaining_sec: 中央本轮剩余时限。
    :param cycle_no: 原累计工程周期。
    :param has_baseline: 中央是否已保存原工作区基线。
    :param resume_required: 原工作是否已有输入。
    :param created_at: 原工作创建时间。
    """

    model_config = ConfigDict(extra='forbid')
    id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    account_id: StrictInt = Field(ge=1)
    generation: StrictInt = Field(ge=1)
    session_id: StrictStr = Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
    project_key: StrictStr = Field(pattern=r'^[a-z][a-z0-9-]{0,79}$')
    objective_id: StrictStr = Field(min_length=1, max_length=160)
    library_digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    settings_json: StrictStr = Field(max_length=65536)
    remaining_sec: StrictInt = Field(ge=1, le=31536000)
    cycle_no: StrictInt = Field(default=1, ge=1)
    has_baseline: StrictBool = False
    resume_required: StrictBool = False
    created_at: float = Field(ge=0, strict=True, allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_settings(self):
        """核对实际Pi必需的冻结CLI版本与等级，避免启动后才发现坏配置。:return: 原工作。"""
        settings = strict_json(self.settings_json.encode(), 65536)
        if (not isinstance(settings.get('claude_code_version'), str)
                or not re.fullmatch(r'2\.1\.[0-9]{1,6}', settings['claude_code_version'])
                or not isinstance(settings.get('claude_effort_level'), str)
                or not settings['claude_effort_level'] or len(settings['claude_effort_level']) > 40):
            raise ValueError('节点终端缺少原冻结CLI版本或等级')
        return self


class TerminalStart(BaseModel):
    """原有限许可及终端所需冻结工作。:param scope: 原许可范围。:param work: 原工作投影。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    work: TerminalWork


class TerminalObserve(BaseModel):
    """有界观察定位。:param scope: 原许可范围。:param cursor: 原生会话字节游标。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    cursor: StrictInt = Field(default=0, ge=0)


class TerminalInputQuery(BaseModel):
    """原输入回执定位。:param scope: 原执行。:param operation_id: 原输入操作。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    operation_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')


class TerminalInput(TerminalInputQuery):
    """单次原样终端输入。:param text: 原文本。:param keys: 原按键。:param submit: 是否追加Enter。"""

    text: StrictStr = Field(default='', max_length=48000)
    keys: list[StrictStr] = Field(default_factory=list, max_length=16)
    submit: StrictBool = False


class TerminalResolution(TerminalInputQuery):
    """中央人工对账的原输入结论。:param resolution_id: 原决策记录。:param sent: 人工核对是否已发送。"""

    resolution_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    sent: StrictBool


class TerminalControl(BaseModel):
    """原作业的有限控制。:param scope: 原执行。:param operation: 原监督器支持的动作。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    operation: Literal['inspect', 'freeze', 'resume', 'stop']


class TerminalAssets(BaseModel):
    """注册原同批工程内容。:param node_key: 原节点。:param digest: 原内容摘要。"""

    model_config = ConfigDict(extra='forbid')
    node_key: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')


class TerminalCapture(BaseModel):
    """原工作受限抓包查询。:param scope: 原执行。:param relative: 白名单预览文件。:param running: 中央当前工作是否运行。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    relative: StrictStr | None = Field(default=None, max_length=4096)
    running: StrictBool = False


class TerminalMaintenance(TerminalStart):
    """固定工程维护操作。:param operation: 原工作启动恢复检查或已结束轮次清理。"""

    operation: Literal['recovery-ready', 'cleanup-cycle']


class TerminalPassiveAck(BaseModel):
    """中央已经保存的原生补证确认。:param scope: 原执行。:param evidence_key: 原事实摘要。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    evidence_key: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')


class NodeTerminals:
    """操作节点已有真实运行时，输入定位只从本节点原启动收据取得。

    :param executor: 原固定节点执行器。
    :param host: 本进程唯一运行时。
    :param grants: 本节点有限证明。
    :param terminal_factory: 原工程终端构造器，测试可提供离线执行替身。
    """

    def __init__(self, executor, host, grants, terminal_factory=ProjectsTerminal) -> None:
        """登记私有范围和原执行器，初始化保持原工作。

        :param executor: 原节点入口。
        :param host: 原持久运行时。
        :param grants: 原节点证明。
        :param terminal_factory: 原终端构造器。
        :return: None。
        """
        self.executor, self.host, self.grants = executor, host, grants
        self.terminal_factory, self.lock = terminal_factory, threading.RLock()
        self.catalogs = {}
        self.stop_dependents = None

    def quota_source(self, scope: ExecutionScope, stream: str) -> Path | None:
        """提供具体执行的独立额度文件，普通终端沿原流组路径。

        :param scope: 原执行。
        :param stream: 原CLI或recorder证据流。
        :return: 具体私有文件；默认None。
        """
        return None

    def register_assets(self, digest: str, source: Path) -> dict:
        """从控制组件的固定同批只读资产注册原摘要。

        :param digest: 中央原内容摘要。
        :param source: 服务端选定的镜像资产根。
        :return: 已注册摘要及协议归属。
        """
        if not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('节点工程内容摘要无效')
        with self.lock:
            root = self.executor.data / 'project-library/releases' / digest
            if root.is_symlink():
                raise ValueError('节点冻结内容目录不能为链接')
            library = ProjectLibrary(root if root.exists() else source)
            if library.digest != digest:
                raise ValueError('节点镜像工程内容与原工作不一致，请先交付原冻结资产')
            installed = library if root.exists() else library.install(self.executor.data)
            self.catalogs[digest] = ProjectsCatalog(source.parent / 'project-research', installed)
        return {'digest': digest, 'state': 'registered'}

    def dispatch(self, operation: str, raw: bytes, asset_source: Path) -> dict | list[dict]:
        """解析具体终端动作，路径和运行时定位由本节点计算。

        :param operation: 固定终端操作。
        :param raw: 原有界私有输入。
        :param asset_source: 服务端固定的镜像资产目录。
        :return: 原动作的有限结果。
        """
        value = strict_json(raw, 256 * 1024)
        if operation == 'terminal-assets':
            request = TerminalAssets.model_validate(value)
            if request.node_key != self.executor.node_key:
                raise ValueError('工程资产注册属于其他节点')
            return self.register_assets(request.digest, asset_source)
        operations = {'terminal-start': (TerminalStart, self.start), 'terminal-get': (ExecutionScope, self.get),
            'terminal-observe': (TerminalObserve, self.observe), 'terminal-send': (TerminalInput, self.send),
            'terminal-input': (TerminalInputQuery, self.input_receipt), 'terminal-control': (TerminalControl, self.control),
            'terminal-reconcile': (TerminalResolution, self.resolve_input), 'terminal-capture': (TerminalCapture, self.capture),
            'terminal-maintenance': (TerminalMaintenance, self.maintenance),
            'terminal-passive-ack': (TerminalPassiveAck, self.ack_passive)}
        if operation in ('terminal-conversation', 'terminal-usage', 'terminal-passive'):
            return self.read(ExecutionScope.model_validate(value), operation.removeprefix('terminal-'))
        if operation == 'terminal-recover':
            return self.recover_stop(ExecutionScope.model_validate(value))
        if operation not in operations:
            raise ValueError('节点终端操作无效')
        model, action = operations[operation]
        return action(model.model_validate(value))

    def _directory(self, scope: ExecutionScope, *, create: bool = False) -> Path:
        if scope.node_key != self.executor.node_key or scope.role not in ('projects', 'warmup'):
            raise ValueError('节点终端执行范围无效')
        parent = self.executor.data / 'node-terminals'
        environment = parent / scope.environment_id
        result = environment / scope.operation_id
        if create:
            for path in (parent, environment, result):
                private_directory(path)
        return result

    def _record(self, scope: ExecutionScope) -> dict:
        value = strict_json(safe_read(self._directory(scope) / 'execution.json', 256 * 1024, private=True), 256 * 1024)
        if (value.get('protocol') != 1 or value.get('scope') != scope.model_dump()
                or value.get('phase') not in ('starting', 'ready', 'reconcile', 'closed')):
            raise ValueError('节点终端原启动收据损坏或范围变化')
        return value

    def _terminal(self, scope: ExecutionScope, work: dict):
        runtime = self.host.runtime
        if runtime is None or self.host.closed:
            raise ValueError('节点原运行时尚未准备或正在关闭')
        with self.lock:
            catalog = self.catalogs.get(work['library_digest'])
        if catalog is None:
            root = self.executor.data / 'project-library/releases' / work['library_digest']
            library = ProjectLibrary(root)
            if library.digest != work['library_digest']:
                raise ValueError('节点原冻结工程资产需要核对')
            catalog = ProjectsCatalog(root.parent / 'project-research', library)
            with self.lock:
                self.catalogs[work['library_digest']] = catalog

        def quota_context(account, source, flows, controls):
            self.grants.authorize(scope)
            path = quota_scope_path(self.executor.data, scope)
            projection = strict_json(safe_read(path, 96 * 1024, private=True), 96 * 1024)
            if projection['scope'] != scope.model_dump():
                raise ValueError('节点额度上下文与原scope不一致')
            state = projection['state']
            context = state.get('remote_cli')
            if (state.get('identity') != self.host.gateway.quota_identity(account)
                    or not isinstance(context, dict) or context.get('source') != source
                    or type(context.get('sample_required')) is not bool):
                raise ValueError('节点原正式执行缺少中央本次额度采集上下文')
            return {'QUOTA_SOURCE': source, 'QUOTA_IDENTITY': state['identity'], 'QUOTA_WARMUP': '1',
                'QUOTA_SAMPLE_REQUIRED': '1' if context['sample_required'] else '0'}

        def quota_observation(account, source, facts):
            if account['id'] != scope.account_id or source != scope.source:
                raise ValueError('原生补证与节点执行账号或来源不一致')
            # 先持久发件箱，再让原会话读取器推进游标；响应丢失时仍可重读原事实。
            path = self._directory(scope) / 'passive-outbox.json'
            if path.exists() or path.is_symlink():
                previous = self._passive(scope)
                if previous['facts']['evidence_key'] == facts['evidence_key']:
                    return
                if previous.get('acknowledged') is not True:
                    raise ValueError('原生补证等待中央保存确认')
            atomic_json(path, {'scope': scope.model_dump(), 'facts': facts, 'acknowledged': False})

        return self.terminal_factory(runtime, catalog, None, quota_context, namespace=scope.role,
            quota_observation=quota_observation)

    def _passive(self, scope: ExecutionScope) -> dict:
        value = strict_json(safe_read(self._directory(scope) / 'passive-outbox.json', 8192, private=True), 8192)
        if (value.get('scope') != scope.model_dump() or not isinstance(value.get('facts'), dict)
                or not re.fullmatch('[a-f0-9]{64}', str(value['facts'].get('evidence_key', '')))
                or type(value.get('acknowledged')) is not bool):
            raise ValueError('原节点补证发件箱范围或内容异常')
        return value

    def _work(self, record: dict) -> dict:
        work = dict(record['work'])
        work['baseline_registered'] = work.pop('has_baseline')
        work['library_root'] = str(self.executor.data / 'project-library/releases' / work['library_digest'])
        if record.get('result'):
            work['runtime_json'] = json.dumps(record['result'], ensure_ascii=False)
        if record.get('node_started_at'):
            work['segment_started_at'] = record['node_started_at']
        return work

    def _receipt(self, record: dict) -> dict:
        return {key: record[key] for key in ('protocol', 'scope', 'phase', 'result', 'pending_input', 'error_type')
            if key in record}

    def _confirm_input(self, record: dict, receipt: dict) -> None:
        if receipt.get('status') in ('sent', 'not_sent') and record.get('pending_input') == receipt['operation_id']:
            record['pending_input'] = None
            scope = ExecutionScope.model_validate(record['scope'])
            atomic_json(self._directory(scope) / 'execution.json', record)

    def get(self, scope: ExecutionScope) -> dict:
        """读取原启动阶段与定位，查询保持原许可截止。

        :param scope: 原冻结范围。
        :return: 原节点启动收据。
        """
        # 原收据原子发布，查询不等待长版本安装持有的执行锁。
        cancelled = self._unsubmitted(scope)
        if cancelled is not None:
            return cancelled
        try:
            record = self._record(scope)
        except FileNotFoundError:
            self.grants.get(scope)
            return {'protocol': 1, 'scope': scope.model_dump(), 'phase': 'reconcile',
                'result': None, 'pending_input': None, 'error_type': 'NodeReceiptMissing'}
        if record['phase'] == 'ready' and self.host.runtime is None:
            return {**self._receipt(record), 'phase': 'reconcile', 'error_type': 'NodeRestart'}
        return self._receipt(record)

    def _unsubmitted(self, scope: ExecutionScope) -> dict | None:
        path = self._directory(scope) / 'unsubmitted.json'
        try:
            receipt = strict_json(safe_read(path, 8192, private=True), 8192)
        except FileNotFoundError:
            return None
        expected = {'protocol': 1, 'scope': scope.model_dump(), 'phase': 'closed', 'result': None, 'pending_input': None}
        proof = self.grants.get(scope)
        if receipt != expected or proof['phase'] != 'closed' or proof.get('closed_reason') != 'node_not_started':
            raise ValueError('原节点未启动撤销回执需要核对')
        return receipt

    def _cancel_prepared(self, scope: ExecutionScope) -> dict:
        proof = self.grants.get(scope)
        if proof['phase'] != 'prepared' and not (proof['phase'] == 'closed' and proof.get('closed_reason') == 'node_not_started'):
            raise ValueError('原启动已认领且缺少回执，请先核对原作业')
        self.grants.close(scope, 'node_not_started')
        receipt = {'protocol': 1, 'scope': scope.model_dump(), 'phase': 'closed', 'result': None, 'pending_input': None}
        atomic_json(self._directory(scope, create=True) / 'unsubmitted.json', receipt)
        return {'stopped': True}

    def start(self, request: TerminalStart) -> dict:
        """先落一次性启动意图，再调用原终端；重试仅返回原回执。

        :param request: 中央原工作和已准备有限证明。
        :return: ready或reconcile收据，未知启动保持原操作。
        """
        scope, work = request.scope, request.work.model_dump()
        if (scope.account_id != work['account_id']
                or scope.source != f"{scope.role}:{work['id']}:{work['generation']}"
                or len(request.work.model_dump_json().encode()) > 192 * 1024):
            raise ValueError('节点终端工作与原许可来源不一致')
        with self.executor._locked(environment_id=scope.environment_id):
            directory = self._directory(scope, create=True)
            path = directory / 'execution.json'
            if path.exists() or path.is_symlink():
                previous = self._record(scope)
                if previous['work'] != work:
                    raise ValueError('原节点终端操作冻结工作已变化')
                return self._receipt(previous)
            terminal = self._terminal(scope, work)
            connection = self.executor.database()
            try:
                row = connection.execute('SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL',
                    (scope.account_id,)).fetchone()
                if row is None or row['cc2api_account_id'] != scope.gateway_account_id:
                    raise ValueError('节点原终端账号已变化')
                account = dict(row)
            finally:
                connection.close()
            # 激活只接受一次；进程崩溃在写意图之前也会留下active证明阻止再次启动。
            self.grants.activate(scope)
            record = {'protocol': 1, 'scope': scope.model_dump(), 'work': work,
                'phase': 'starting', 'result': None, 'pending_input': None,
                'shared_cli': not bool(account.get(scope.role + '_capture_enabled', 0))}
            atomic_json(path, record)
            try:
                mirror = self.host.gateway.lease_mirror
                mirror.attach(scope)
                with mirror.preparing(scope):
                    record['result'] = terminal.start(account, self._work(record))
                record['phase'] = 'ready'
                record['node_started_at'] = time.time()
            except Exception as error:
                record.update(phase='reconcile', error_type=type(error).__name__)
            atomic_json(path, record)
            return self._receipt(record)

    def _ready(self, scope: ExecutionScope) -> tuple[dict, object]:
        record = self._record(scope)
        if record['phase'] != 'ready':
            raise ValueError('节点原终端尚未就绪或需要对账')
        return record, self._terminal(scope, self._work(record))

    def observe(self, request: TerminalObserve) -> dict:
        """只读原终端状态和原生增量，过期后保留观察入口。

        :param request: 原scope及游标。
        :return: 原终端观察结果。
        """
        with self.executor._locked(read_only=True, environment_id=request.scope.environment_id):
            record, terminal = self._ready(request.scope)
            return terminal.observe(self._work(record), request.cursor)

    def input_receipt(self, request: TerminalInputQuery) -> dict:
        """读取原输入收据，未知状态保持原值。

        :param request: 原执行及输入操作。
        :return: 持久输入状态。
        """
        self._record(request.scope)
        value = strict_json(safe_read(self._directory(request.scope) / (request.operation_id + '.json'),
            8192, private=True), 8192)
        if value.get('operation_id') != request.operation_id or value.get('scope') != request.scope.model_dump():
            raise ValueError('节点原输入收据范围不一致')
        return value

    def read(self, scope: ExecutionScope, kind: str) -> dict | list[dict]:
        """读取原生补证、会话或用量，定位始终取本节点启动收据。

        :param scope: 原执行范围。
        :param kind: passive、conversation或usage。
        :return: 原终端只读结果。
        """
        if kind not in ('passive', 'conversation', 'usage'):
            raise ValueError('节点终端只读操作无效')
        with self.executor._locked(read_only=kind != 'passive', environment_id=scope.environment_id):
            record = self._record(scope)
            if record['phase'] not in ('ready', 'closed') or not record.get('result'):
                raise ValueError('原终端尚未保存可读定位')
            terminal = self._terminal(scope, self._work(record))
            outbox = self._directory(scope) / 'passive-outbox.json'
            if kind == 'passive' and (outbox.exists() or outbox.is_symlink()):
                pending = self._passive(scope)
                if not pending['acknowledged']:
                    return pending['facts']
            action = {'passive': terminal.passive_status, 'conversation': terminal.conversation, 'usage': terminal.usage}[kind]
            return action(self._work(record))

    def ack_passive(self, request: TerminalPassiveAck) -> dict:
        """中央持久保存后确认补证，重复确认保持原结论。

        :param request: 原执行及已保存事实摘要。
        :return: 原事实已经确认的回执。
        """
        scope = request.scope
        with self.executor._locked(environment_id=scope.environment_id):
            self._record(scope)
            pending = self._passive(scope)
            if pending['facts']['evidence_key'] != request.evidence_key:
                raise ValueError('中央确认属于其他原生补证')
            pending['acknowledged'] = True
            atomic_json(self._directory(scope) / 'passive-outbox.json', pending)
            return {'acknowledged': True, 'evidence_key': request.evidence_key}

    def capture(self, request: TerminalCapture) -> dict:
        """按节点保存的原工作读取抓包，路径由原脱敏读取器计算。

        :param request: 原执行和受限预览。
        :return: 原脱敏抓包摘要或白名单文件。
        """
        with self.executor._locked(read_only=True, environment_id=request.scope.environment_id):
            record = self._record(request.scope)
            work = self._work(record)
            work['status'] = 'running' if request.running and record['phase'] == 'ready' else 'paused'
            return self._terminal(request.scope, work).capture(work, request.relative)

    def maintenance(self, request: TerminalMaintenance) -> dict:
        """在当前归属和原工作范围内执行工程维护，不启动模型。

        :param request: 当前实际环境、冻结工作和固定维护动作。
        :return: 启动恢复条件或原轮次清理回执。
        """
        scope = request.scope
        if scope.role not in ('projects', 'warmup') or scope.source != f'{scope.role}:{request.work.id}:{request.work.generation}':
            raise ValueError('工程维护与原工作来源不一致')
        with self.executor._locked(environment_id=scope.environment_id):
            self.grants.check_scope(scope)
            connection = self.executor.database()
            try:
                saved = connection.execute('SELECT * FROM accounts WHERE id=?', (scope.account_id,)).fetchone()
            finally:
                connection.close()
            if saved is None or request.work.account_id != scope.account_id:
                raise ValueError('工程维护的账号范围不一致')
            record = {'work': request.work.model_dump()}
            work = self._work(record)
            terminal = self._terminal(scope, work)
            if request.operation == 'recovery-ready':
                return {'ready': terminal.startup_recovery_ready(dict(saved), work)}
            previous = self._record(scope)
            if previous['phase'] != 'closed' or previous['work'] != request.work.model_dump():
                raise ValueError('工程轮次清理要求原执行已确认收口')
            terminal.cleanup_cycle(dict(saved), request.work.cycle_no)
            return {'cleaned': True, 'cycle_no': request.work.cycle_no}

    def resolve_input(self, request: TerminalResolution) -> dict:
        """保存中央人工入口的原输入核对结论，原操作始终只作查询。

        :param request: 原输入和中央决策记录。
        :return: sent或not_sent回执。
        """
        scope = request.scope
        with self.executor._locked(environment_id=scope.environment_id):
            record = self._record(scope)
            path = self._directory(scope) / (request.operation_id + '.json')
            receipt = strict_json(safe_read(path, 8192, private=True), 8192)
            if receipt.get('scope') != scope.model_dump() or receipt.get('operation_id') != request.operation_id:
                raise ValueError('人工结论与原输入范围不一致')
            resolution = {'id': request.resolution_id, 'sent': request.sent}
            if receipt.get('resolution') is not None:
                if receipt['resolution'] != resolution:
                    raise ValueError('原输入已经保存另一人工结论')
                self._confirm_input(record, receipt)
                return receipt
            if receipt.get('status') in ('sent', 'not_sent'):
                if (receipt['status'] == 'sent') != request.sent:
                    raise ValueError('人工结论与节点已确认的原输入事实冲突')
                self._confirm_input(record, receipt)
                return receipt
            if receipt.get('status') != 'unknown' or record.get('pending_input') != request.operation_id:
                raise ValueError('原输入尚未进入可核对状态')
            receipt.update(status='sent' if request.sent else 'not_sent', resolution=resolution)
            atomic_json(path, receipt)
            self._confirm_input(record, receipt)
            return receipt

    def send(self, request: TerminalInput) -> dict:
        """持久保存输入意图后投递一次，重复请求仅返回原收据。

        :param request: 原scope、独立输入操作及原样文本/按键。
        :return: sent或unknown收据。
        """
        if len(request.text.encode()) > 48000 or any(key not in KEYS for key in request.keys):
            raise ValueError('节点终端输入超过原限制')
        scope = request.scope
        digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        with self.executor._locked(environment_id=scope.environment_id):
            record, terminal = self._ready(scope)
            path = self._directory(scope) / (request.operation_id + '.json')
            if path.exists() or path.is_symlink():
                previous = strict_json(safe_read(path, 8192, private=True), 8192)
                if (previous.get('scope') != scope.model_dump() or previous.get('operation_id') != request.operation_id
                        or previous.get('digest') != digest):
                    raise ValueError('原节点输入操作的内容已变化')
                self._confirm_input(record, previous)
                return previous
            if record.get('pending_input') is not None:
                raise ValueError('原终端输入结果尚未核对，请读取原输入回执')
            self.grants.authorize(scope)
            receipt = {'protocol': 1, 'scope': scope.model_dump(), 'operation_id': request.operation_id,
                'digest': digest, 'status': 'unknown'}
            # 先在原执行收据登记未决输入；任何写入窗口崩溃都阻止下一条输入越过未知状态。
            record['pending_input'] = request.operation_id
            atomic_json(self._directory(scope) / 'execution.json', record)
            atomic_json(path, receipt)
            try:
                terminal.send(self._work(record), request.operation_id, request.text, request.keys, request.submit)
                receipt['status'] = 'sent'
            except Exception as error:
                receipt['error_type'] = type(error).__name__
            atomic_json(path, receipt)
            self._confirm_input(record, receipt)
            return receipt

    def recover_stop(self, scope: ExecutionScope) -> dict:
        """节点重启或启动未知时，仅恢复并收口原实际执行。

        :param scope: 原私有终端及证明范围。
        :return: 原执行已经实际停止的回执。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            if self._unsubmitted(scope) is not None:
                return {'stopped': True}
            try:
                record = self._record(scope)
            except FileNotFoundError:
                # prepared证明尚未被启动层认领；先关闭证明，迟到启动再也不能越过activate。
                return self._cancel_prepared(scope)
            if record['phase'] == 'closed':
                return {'stopped': True}
            if self.stop_dependents:
                self.stop_dependents(scope)
            connection = self.executor.database()
            try:
                saved = connection.execute('SELECT * FROM account_environments WHERE environment_id=? AND account_id=?',
                    (scope.environment_id, scope.account_id)).fetchone()
                account = connection.execute('SELECT * FROM accounts WHERE id=?', (scope.account_id,)).fetchone()
            finally:
                connection.close()
            if (saved is None or account is None or saved['generation'] != scope.generation
                    or account['cc2api_account_id'] != scope.gateway_account_id):
                raise ValueError('原终端恢复与本节点实际账号或代次不一致')
            row, account = dict(saved), dict(account)
            grant = self.grants.get(scope)['grant']
            lease = grant.get('lease')
            if lease is None and scope.gateway_account_id is not None:
                raise ValueError('原节点Pi恢复缺少中央租约证明')
            shared = lease['shared_cli'] if lease is not None else record.get('shared_cli')
            if type(shared) is not bool:
                raise ValueError('原独立节点Pi恢复缺少冻结执行模式')
            self.grants.close(scope, 'node_execution_recovering')
            runtime = self.host.recovery_runtime(scope)
            mirror = self.host.gateway.lease_mirror
            mirror.recover(scope)
            job = runtime.restore_execution(row, account, scope.source, lease, shared_cli=shared)
            if job is not None:
                if record.get('result') and record['result'].get('token') != job['token']:
                    raise ValueError('原终端恢复的实际token与启动回执不一致')
                runtime.cleanup(job['token'])
                if runtime._execution_path(job).exists() or any(value['source'] == scope.source
                        for value in runtime.environment_jobs(scope.environment_id)):
                    raise ValueError('原节点执行记录或实际作业仍未收口')
            else:
                try:
                    container = runtime._container(row)
                except NotFound:
                    container = None
                if container is not None:
                    container.reload()
                    if container.status == 'running':
                        observed = container.exec_run(['python3', '-I', '/usr/local/bin/v3-cli-control', 'status'])
                        if observed.exit_code != 1:
                            raise ValueError('原账号仍有实际CLI进程，缺少原定位时保持待核对')
                    elif container.status not in ('exited', 'dead', 'created'):
                        raise ValueError('原CLI角色实际停止状态尚未确认')
                if lease is not None:
                    mirror.request('POST', f'/admin/runtime/accounts/{scope.gateway_account_id}/lease',
                        {'operation': 'release', 'owner': lease['owner'], 'generation': lease['generation']})
            self.grants.close(scope, 'node_execution_closed')
            if scope.gateway_account_id is None:
                mirror.release_independent(scope)
            record['phase'] = 'closed'
            atomic_json(self._directory(scope) / 'execution.json', record)
            return {'stopped': True}

    def control(self, request: TerminalControl) -> dict:
        """定向控制原作业，停止成功后保存关闭收据。

        :param request: 原scope及固定监督操作。
        :return: 原监督结果。
        """
        scope = request.scope
        with self.executor._locked(environment_id=scope.environment_id):
            record = self._record(scope)
            if record['phase'] == 'closed' and request.operation == 'stop':
                return {'stopped': True}
            record, terminal = self._ready(scope)
            if request.operation == 'stop' and self.stop_dependents:
                self.stop_dependents(scope)
            if request.operation == 'resume':
                self.grants.authorize(scope)
            result = terminal.control(self._work(record), request.operation)
            if request.operation == 'stop':
                self.grants.close(scope, 'node_execution_closed')
                if scope.gateway_account_id is None:
                    self.host.gateway.lease_mirror.release_independent(scope)
                record['phase'] = 'closed'
                atomic_json(self._directory(scope) / 'execution.json', record)
            return result
