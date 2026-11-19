"""工程终端按人工归属执行，已登记工作始终沿原节点操作读取和控制。"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from uuid import uuid4

from cluster_deployment import node_container_name
from cluster_execution_grants import ExecutionScope
from cluster_program_verification import RemoteProgramVerification
from cluster_project_capture import ProjectHistoryCapture
from cluster_terminal import TerminalStart, TerminalWork
from project_runtime_policy import ProjectRuntimeError


class ClusterProjectsTerminal:
    """复用原本机终端与中央远程会话协调器。

    :param local: 原ProjectsTerminal。
    :param sessions: 原TerminalSessions。
    :param identity: 中央权威额度身份回调。
    """

    def __init__(self, local, sessions, identity) -> None:
        """绑定固定工程空间。:param local: 本机终端。:param sessions: 远程协调器。:param identity: 原账号身份。:return: None。"""
        self.local, self.sessions, self.identity = local, sessions, identity
        self.runtime, self.namespace, self.settings = local.runtime, local.namespace, local.settings
        self.program = RemoteProgramVerification(sessions, local.catalog)

    def _source(self, work: dict) -> str:
        return f"{self.namespace}:{work['id']}:{work['generation']}"

    def _record(self, work: dict) -> dict | None:
        info = json.loads(work['runtime_json']) if work.get('runtime_json') else {}
        operation = info.get('remote_execution')
        if operation is not None:
            row = self.sessions.ledger.get(operation)
            scope = row['record']['scope']
            receipt = row['record']['node_receipt']
            if (scope['source'] != self._source(work) or scope['account_id'] != work['account_id']
                    or scope['role'] != self.namespace or info.get('source') != scope['source']
                    or info.get('node_key') != scope['node_key'] or not receipt or not receipt.get('result')
                    or info.get('token') != receipt['result']['token']):
                raise ValueError('工程定位与原节点执行不一致')
            return row
        row = self.sessions.ledger.by_source(work['account_id'], self._source(work), active_only=bool(info))
        if row is not None:
            if info:
                raise ValueError('工程同时存在本机定位和未收口节点执行，请先核对')
            return row
        assignment = self.sessions.service.store.assignment(work['account_id'])
        if assignment['kind'] == 'ssh':
            raise ValueError('远程工程缺少原执行定位，请先核对启动结果')
        return None

    def _projection(self, work: dict) -> TerminalWork:
        names = ('id', 'account_id', 'generation', 'session_id', 'project_key', 'objective_id',
            'library_digest', 'settings_json', 'created_at')
        return TerminalWork(**{name: work[name] for name in names}, remaining_sec=work.get('remaining_sec', 1), cycle_no=work.get('cycle_no', 1),
            has_baseline=bool(work.get('baseline_json')), resume_required=bool(work.get('resume_required')))

    def _prepare(self, account: dict, work: dict) -> TerminalStart:
        if self.local.credentials:
            self.local.credentials(account)
        service = self.sessions.service
        service.prepare_remote_cli(account, self.runtime, self.sessions.gateway, self.identity(account))
        assignment = service.store.assignment(account['id'])
        if assignment['kind'] != 'ssh' or assignment['phase'] != 'ready':
            raise ValueError('工程准备期间账号节点归属发生变化')
        node = service.store.get(assignment['node_id'])
        registered = service.connection(node['id']).execution_environment(
            node_container_name(self.runtime.deployment, node['node_key']),
            {'node_key': node['node_key'], 'digest': work['library_digest']}, 'terminal-assets')
        if (registered.get('protocol') != 1 or registered.get('node_key') != node['node_key']
                or registered.get('terminal') != {'digest': work['library_digest'], 'state': 'registered'}):
            raise ValueError('所属节点尚未确认原工程冻结资产')
        environment = self.runtime._row(account['name'], account['id'])
        scope = ExecutionScope(operation_id=uuid4().hex, node_key=node['node_key'], account_id=account['id'],
            gateway_account_id=account.get('cc2api_account_id'), environment_id=environment['environment_id'],
            assignment_revision=assignment['revision'], generation=environment['generation'],
            source=self._source(work), role=self.namespace)
        return TerminalStart(scope=scope, work=self._projection(work))

    def _location(self, row: dict) -> dict:
        record = row['record']
        if row['phase'] != 'running' or not record['node_receipt'] or record['node_receipt']['phase'] != 'ready':
            raise ProjectRuntimeError('startup_unknown', '原节点启动结果需要核对，请保留原会话和输入记录')
        scope, result = record['scope'], record['node_receipt']['result']
        return {'remote_execution': row['operation_id'], 'source': scope['source'], 'token': result['token'],
            'node_key': scope['node_key'], 'environment_id': scope['environment_id'],
            'assignment_revision': scope['assignment_revision'], 'environment_generation': scope['generation']}

    def start(self, account: dict, work: dict) -> dict:
        """按归属启动一次原工作。:param account: 当前账号。:param work: 冻结工作。:return: 原实际执行定位。"""
        if type(work.get('remaining_sec')) is not int or work['remaining_sec'] < 1:
            raise ValueError('原工程启动缺少本轮实际剩余预算')
        with self.sessions._operation_lock('source:' + str(account['id']) + ':' + self._source(work)):
            row = self.sessions.ledger.by_source(account['id'], self._source(work))
            if row is not None:
                return self._location(row)
            if self.sessions.service.store.assignment(account['id'])['kind'] == 'local':
                return self.local.start(account, work)
            return self._location(self.sessions.start(self._prepare(account, work)))

    def observe(self, work: dict, cursor: int = 0) -> dict:
        """读取原执行画面。:param work: 原工作。:param cursor: 原生游标。:return: 观察结果。"""
        row = self._record(work)
        return self.sessions.read(row['operation_id'], 'observe', cursor=cursor) if row else self.local.observe(work, cursor)

    def send(self, work: dict, operation_id: str, text: str, keys: list[str], submit: bool) -> None:
        """沿原操作发送一次输入。:param work: 原工作。:param operation_id: 原输入。:param text: 文本。:param keys: 按键。:param submit: 追加Enter。:return: None。"""
        row = self._record(work)
        if row is None:
            return self.local.send(work, operation_id, text, keys, submit)
        receipt = self.sessions.send(row['operation_id'], operation_id, text, keys, submit)
        if receipt.get('status') != 'sent':
            raise ValueError('原节点输入结果未知，请沿原操作核对')

    def control(self, work: dict, operation: str) -> dict:
        """控制原实际进程。:param work: 原工作。:param operation: 监督动作。:return: 真实控制结果。"""
        row = self._record(work)
        return self.sessions.control(row['operation_id'], operation) if row else self.local.control(work, operation)

    def snapshot(self, work: dict, objects: Path | None = None, *, snapshot_id: str | None = None) -> dict:
        """读取原节点基线或候选。:param work: 原工作。:param objects: 候选对象目录。:param snapshot_id: 固定提交。:return: 完整源码清单。"""
        row = self._record(work)
        if row is None:
            return self.local.snapshot(work, objects, snapshot_id=snapshot_id)
        if objects is not None and snapshot_id is None:
            raise ValueError('远程候选快照必须绑定原提交操作')
        return self.sessions.snapshot(row['operation_id'], snapshot_id or row['operation_id'], objects)

    def conversation(self, work: dict) -> list[dict]:
        """读取完整原生交流。:param work: 原工作。:return: 原用户与助手消息。"""
        row = self._record(work)
        return self.sessions.read(row['operation_id'], 'conversation') if row else self.local.conversation(work)

    def usage(self, work: dict) -> dict:
        """读取原会话真实用量。:param work: 原工作。:return: 原去重汇总。"""
        row = self._record(work)
        return self.sessions.read(row['operation_id'], 'usage') if row else self.local.usage(work)

    def passive_status(self, work: dict) -> dict:
        """消费原节点结构化额度事实。:param work: 原工作。:return: 原生补证。"""
        row = self._record(work)
        if row is None:
            return self.local.passive_status(work)
        facts = self.sessions.read(row['operation_id'], 'passive')
        if facts.get('evidence_key') and self.local.quota_observation:
            account = self.sessions._account(ExecutionScope.model_validate(row['record']['scope']), available=False)
            self.local.quota_observation(account, row['source'], facts)
            self.sessions.ack_passive(row['operation_id'], facts['evidence_key'])
        return facts

    def capture(self, work: dict, relative: str | None = None) -> dict:
        """读取所属节点脱敏抓包。:param work: 原工作。:param relative: 白名单文件。:return: 原摘要或预览。"""
        if work['status'] in ('passed', 'stopped', 'deferred') and not work.get('runtime_json'):
            return self._history_capture(work, relative)
        row = self._record(work)
        return (self.sessions.read(row['operation_id'], 'capture', relative=relative, running=work['status'] == 'running')
            if row else self.local.capture(work, relative))

    def _history_capture(self, work: dict, relative: str | None) -> dict:
        service = self.sessions.service
        assignment = service.store.assignment(work['account_id'])
        if assignment['phase'] != 'ready':
            raise ValueError('历史工程资料正在迁移，请在原操作完成后读取')
        if assignment['kind'] == 'local':
            capture = self.local.capture(work, relative)
            current = service.store.assignment(work['account_id'])
            if any(current[key] != assignment[key] for key in ('node_id', 'revision', 'phase')):
                raise ValueError('历史工程抓包读取期间节点归属已变化')
            return capture
        connection = service.store.database()
        try:
            environment = connection.execute('SELECT environment_id,generation FROM account_environments WHERE account_id=?',
                (work['account_id'],)).fetchone()
        finally:
            connection.close()
        if environment is None:
            raise ValueError('历史工程所属环境不存在')
        original = self.sessions.ledger.by_source(work['account_id'], self._source(work), active_only=False)
        if original and original['environment_id'] != environment['environment_id']:
            raise ValueError('历史工程与当前资料环境不一致')
        request = ProjectHistoryCapture(node_key=assignment['node_key'], account_id=work['account_id'],
            environment_id=environment['environment_id'], assignment_revision=assignment['revision'],
            generation=environment['generation'], namespace=self.namespace, work_id=work['id'], relative=relative)
        value = service.connection(assignment['node_id']).execution_environment(
            node_container_name(self.runtime.deployment, assignment['node_key']), request.model_dump(), 'project-history-capture')
        current = service.store.assignment(work['account_id'])
        connection = service.store.database()
        try:
            latest = connection.execute('SELECT environment_id,generation FROM account_environments WHERE account_id=?',
                (work['account_id'],)).fetchone()
        finally:
            connection.close()
        if (any(current[key] != assignment[key] for key in ('node_id', 'revision', 'phase'))
                or latest is None or tuple(latest) != tuple(environment)):
            raise ValueError('历史工程抓包读取期间归属或环境代次已变化')
        history = value.get('history') if isinstance(value, dict) else None
        if (not isinstance(value, dict) or value.get('protocol') != 1 or value.get('node_key') != request.node_key
                or not isinstance(history, dict) or history.get('reference') != request.model_dump()
                or not isinstance(history.get('capture'), dict)):
            raise ValueError('历史工程抓包回执与原查询不一致')
        capture = history['capture']
        return capture if relative is not None else {**capture, 'work_id': work['id'], 'namespace': self.namespace,
            'mode': 'full_http', **json.loads(work['settings_json'])}

    def verify_program(self, work: dict, snapshot: dict, directory: Path, target: dict, *, answer: str = '',
                       regression: bool = False, cancel: threading.Event | None = None) -> dict | None:
        """路由原候选的独立程序验收。

        :param work: 当前原工作。
        :param snapshot: 原冻结候选。
        :param directory: 中央提交目录。
        :param target: 当前或历史已通过目标。
        :param answer: 原生实际回答。
        :param regression: 原完整回归模式。
        :param cancel: 原控制者取消信号。
        :return: 节点完整报告；本机返回None以沿用原验证器。
        """
        row = self._record(work)
        return (self.program.verify(row, work, snapshot, directory, target, answer=answer, regression=regression, cancel=cancel)
            if row else None)

    def resolve_input(self, work: dict, operation_id: str, sent: bool) -> None:
        """先保存原节点人工结论。:param work: 原工作。:param operation_id: 原输入。:param sent: 人工事实。:return: None。"""
        row = self._record(work)
        if row:
            self.sessions.resolve_input(row['operation_id'], operation_id, operation_id, sent)

    def recover_work(self, work: dict) -> None:
        """重启后先收口原节点作业，再由工程服务清理旧定位。

        :param work: 原代次持久工作。
        :return: None；原停止未知时保留工作现场并继续阻塞。
        """
        row = self.sessions.ledger.by_source(work['account_id'], self._source(work))
        if row:
            self.sessions.stop(row['operation_id'])
        else:
            self.local.recover_work(work)

    def prepare_startup_recovery(self, account: dict, work: dict) -> None:
        """人工恢复前准备原环境。:param account: 当前账号。:param work: 原工作。:return: None。"""
        if self.sessions.service.store.assignment(account['id'])['kind'] == 'local':
            return self.local.prepare_startup_recovery(account, work)
        self.recover_work(work)
        self._prepare(account, work)

    def startup_recovery_ready(self, account: dict, work: dict) -> bool:
        """核对原环境启动恢复条件。:param account: 当前账号。:param work: 原工作。:return: 全部条件明确为True。"""
        if self.sessions.service.store.assignment(account['id'])['kind'] == 'local':
            return self.local.startup_recovery_ready(account, work)
        if self.sessions.ledger.active(account['id']):
            return False
        request = self._prepare(account, work)
        node = self.sessions.service.store.assignment(account['id'])
        response = self.sessions.service.connection(node['node_id']).execution_environment(
            node_container_name(self.runtime.deployment, request.scope.node_key),
            {**request.model_dump(), 'operation': 'recovery-ready'}, 'terminal-maintenance')
        return (response.get('protocol') == 1 and response.get('node_key') == request.scope.node_key
            and response.get('terminal') == {'ready': True})

    def cleanup_cycle(self, account: dict, cycle_no: int) -> None:
        """清理原账号已完成轮次。:param account: 原账号。:param cycle_no: 已结束轮次。:return: None。"""
        row = self.sessions.ledger.latest_cycle(account['id'], self.namespace, cycle_no)
        if row is None:
            if self.sessions.service.store.assignment(account['id'])['kind'] != 'local':
                raise ValueError('远程工程轮次缺少原执行记录，请先核对')
            return self.local.cleanup_cycle(account, cycle_no)
        if row['phase'] != 'closed' or self.sessions.ledger.active(account['id']):
            raise ValueError('工程轮次尚有未收口节点执行')
        self.sessions.ledger.maintenance(row['operation_id'])
        result = self.sessions._call(row, 'terminal-maintenance', {'scope': row['record']['scope'],
            'work': row['record']['work'], 'operation': 'cleanup-cycle'})
        if result != {'cleaned': True, 'cycle_no': cycle_no}:
            raise ValueError('原节点工程轮次清理尚未确认')
