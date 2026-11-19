"""节点具体续聊准备与私有PTY，输入和实际停止保持原有限证明。"""
from __future__ import annotations

import base64
import hashlib
import time
from pathlib import Path
from stat import S_ISREG

from starlette.websockets import WebSocket

from cluster_continue_contract import ContinueStart, ContinueWork
from cluster_pty import PtyInput, PtyResize, serve_node_pty
from cluster_execution_grants import ExecutionScope
from cluster_quota import _read_quota_file, quota_scope_path
from run_artifacts import ordinary_run_alias
from cluster_terminal import NodeTerminals, TerminalControl, TerminalInputQuery
from continue_pty import open_continue_pty
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class NodeContinues(NodeTerminals):
    """准备原交互作业，通过私有WS转发原PTY。

    :param executor: 原节点安装。
    :param host: 唯一运行时。
    :param grants: 原有限证明。
    """

    def __init__(self, executor, host, grants) -> None:
        """登记原依赖及实际PTY。:param executor: 原节点。:param host: 原运行时。:param grants: 原证明。:return: None。"""
        super().__init__(executor, host, grants)
        self.ptys = {}
        self.stop_dependents = self._prepare_stop

    def _directory(self, scope: ExecutionScope, *, create: bool = False) -> Path:
        if scope.node_key != self.executor.node_key or scope.role != 'cli' or not scope.source.startswith('continue:'):
            raise ValueError('原节点续聊范围无效')
        parent = self.executor.data / 'node-continues'
        environment, result = parent / scope.environment_id, parent / scope.environment_id / scope.operation_id
        if create:
            for path in (parent, environment, result):
                private_directory(path)
        return result

    def _record(self, scope: ExecutionScope) -> dict:
        value = super()._record(scope)
        work = ContinueWork.model_validate(value['work'])
        if work.source != scope.source or work.account_id != scope.account_id:
            raise ValueError('原续聊回执与工作范围不一致')
        return value

    def dispatch(self, operation: str, raw: bytes) -> dict:
        """仅接受具体续聊准备、回执、原作业收口与凭据同步。

        :param operation: 固定动作。
        :param raw: 原有界JSON。
        :return: 原Scope回执。
        """
        value = strict_json(raw, 16384)
        if operation == 'continue-start':
            return self.start(ContinueStart.model_validate(value))
        if operation == 'continue-input':
            request = TerminalInputQuery.model_validate(value)
            return self.input_receipt(request)
        if operation == 'continue-control':
            request = TerminalControl.model_validate(value)
            if request.operation != 'stop':
                raise ValueError('续聊控制仅接受原作业停止')
            return self.recover_stop(request.scope)
        scope = ExecutionScope.model_validate(value)
        if operation == 'continue-get':
            return self.get(scope)
        if operation == 'continue-recover':
            return self.recover_stop(scope)
        if operation == 'continue-credentials':
            return self.credentials(scope)
        if operation == 'continue-quota-control':
            self._record(scope)
            path = self.executor.data / 'environments' / scope.environment_id / 'controls' / hashlib.sha256(scope.source.encode()).hexdigest()[:20] / 'pause.json'
            if path.exists() or path.is_symlink():
                metadata = path.lstat()
                if not S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
                    raise ValueError('原续聊额度补证必须来自root只读控制目录')
            return {'scope': scope.model_dump(), **_read_quota_file(path, 0)}
        raise ValueError('节点续聊动作无效')

    def start(self, request: ContinueStart) -> dict:
        """只准备原begin_continue，实际PTY在一次性WS连接时启动。

        :param request: 原具体续聊与许可。
        :return: 原实际token或待核对回执。
        """
        scope, work = request.scope, request.work
        with self.executor._locked(environment_id=scope.environment_id):
            path = self._directory(scope, create=True) / 'execution.json'
            if path.exists() or path.is_symlink():
                old = self._record(scope)
                if old['work'] != work.model_dump():
                    raise ValueError('原节点续聊冻结工作已变化')
                return self.get(scope)
            runtime = self.host.runtime
            if runtime is None or self.host.closed or runtime.project_iterations is not None:
                raise ValueError('节点续聊原运行时需要准备')
            connection = self.executor.database()
            try:
                saved = connection.execute('SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL', (scope.account_id,)).fetchone()
                original = connection.execute('SELECT account_id,task_id,environment_id FROM runs WHERE id=?', (work.id,)).fetchone()
                if original is None:
                    with connection:
                        connection.execute('INSERT INTO runs(id,account_id,task_id,environment_id) VALUES(?,?,?,?)',
                            (work.id, scope.account_id, work.task.id, scope.environment_id))
                    original = connection.execute('SELECT account_id,task_id,environment_id FROM runs WHERE id=?', (work.id,)).fetchone()
            finally:
                connection.close()
            if (saved is None or saved['cc2api_account_id'] != scope.gateway_account_id
                    or original is None or original['account_id'] != scope.account_id or original['task_id'] != work.task.id
                    or original['environment_id'] != scope.environment_id):
                raise ValueError('节点续聊原Run、账号或环境不一致')
            account = dict(saved)
            self.grants.activate(scope)
            record = {'protocol': 1, 'scope': scope.model_dump(), 'work': work.model_dump(), 'phase': 'starting',
                'result': None, 'pending_input': None, 'shared_cli': False, 'node_started_at': time.time()}
            atomic_json(path, record)
            try:
                projection = strict_json(safe_read(quota_scope_path(self.executor.data, scope), 96 * 1024, private=True), 96 * 1024)
                context = projection['state']['remote_cli']
                identity = self.host.gateway.quota_identity(account)
                if projection['scope'] != scope.model_dump() or projection['state']['identity'] != identity or context['source'] != scope.source:
                    raise ValueError('原续聊缺少中央额度认领')
                session = self.executor.data / 'environments' / scope.environment_id / 'home/.claude/projects' / (
                    '/home/node/projects/' + ordinary_run_alias(scope.environment_id, work.id)).replace('/', '-') / (work.session_id + '.jsonl')
                if not _read_quota_file(session, 0)['size']:
                    raise ValueError('原续聊Claude会话尚未提供')
                quota = {'QUOTA_SOURCE': scope.source, 'QUOTA_IDENTITY': identity, 'QUOTA_WARMUP': '0',
                    'QUOTA_SAMPLE_REQUIRED': '1' if context['sample_required'] else '0'}
                mirror = self.host.gateway.lease_mirror
                mirror.attach(scope)
                flows = self.executor.data / 'flows' / account['name'] / str(work.task.id) / work.id / ('continue-' + work.sid)
                with mirror.preparing(scope):
                    _, token = runtime.begin_continue(account, work.run(), work.sid, quota, flows)
                record.update(phase='ready', result={'token': token, 'source': scope.source})
            except Exception as error:
                record.update(phase='reconcile', error_type=type(error).__name__)
            atomic_json(path, record)
            return self._receipt(record)

    def get(self, scope: ExecutionScope) -> dict:
        """观察原准备与PTY未决输入，重启和断连保留隔离。

        :param scope: 原执行。
        :return: 原回执或待核对阶段。
        """
        result = super().get(scope)
        if result['phase'] == 'ready':
            path = self._directory(scope) / 'pty.json'
            if path.exists() or path.is_symlink():
                pty = strict_json(safe_read(path, 16384, private=True), 16384)
                if pty.get('scope') != scope.model_dump():
                    raise ValueError('节点原PTY回执范围错误')
                state = self._input_state(scope)
                pending = state['pending_input']
                if pending is not None:
                    try:
                        if self.input_receipt(TerminalInputQuery(scope=scope, operation_id=pending))['status'] != 'unknown':
                            pending = None
                    except FileNotFoundError:
                        pass
                if pty.get('phase') != 'ready' or scope.operation_id not in self.ptys or pending is not None:
                    result.update(phase='reconcile', error_type='NodePtyUnconfirmed', pending_input=pending)
        return result

    def open_pty(self, scope: ExecutionScope):
        """先保存一次性意图，再登记并启动原PTY。

        :param scope: 原许可范围。
        :return: 原实际PTY；重复连接保持拒绝。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            record = self._record(scope)
            if record['phase'] != 'ready' or self.host.runtime is None:
                raise ValueError('原续聊准备尚未完成')
            runtime, work = self.host.runtime, ContinueWork.model_validate(record['work'])
            with runtime.environment_lock(scope.environment_id), self.lock:
                path = self._directory(scope) / 'pty.json'
                if path.exists() or path.is_symlink() or scope.operation_id in self.ptys:
                    raise ValueError('原PTY启动已经登记，请核对原执行')
                job = runtime.job_for_container(record['result']['token'])
                runtime.authorize_input(job)
                atomic_json(path, {'scope': scope.model_dump(), 'phase': 'opening'})
                exec_id, raw = open_continue_pty(runtime, job['token'], work.session_id, work.permission_mode, work.model)
                self.ptys[scope.operation_id] = {'raw': raw, 'exec': exec_id, 'job': job, 'scope': scope}
                atomic_json(path, {'scope': scope.model_dump(), 'phase': 'ready', 'exec': exec_id})
                return raw

    def _input_state(self, scope: ExecutionScope) -> dict:
        path = self._directory(scope) / 'input-state.json'
        if not path.exists() and not path.is_symlink():
            return {'scope': scope.model_dump(), 'pending_input': None}
        value = strict_json(safe_read(path, 8192, private=True), 8192)
        if value.get('scope') != scope.model_dump():
            raise ValueError('原PTY输入意图范围错误')
        if value.get('pending_input') is not None:
            TerminalInputQuery(scope=scope, operation_id=value['pending_input'])
        return value

    def send_input(self, scope: ExecutionScope, request: PtyInput) -> dict:
        """持久记录原输入意图，只向同一原作业写入一次。

        :param scope: 本连接冻结范围。
        :param request: 原输入及标识。
        :return: sent、not_sent或unknown；部分写入保持未知。
        """
        data = base64.b64decode(request.data, validate=True)
        if not 1 <= len(data) <= 16384:
            raise ValueError('原PTY输入字节数无效')
        digest = hashlib.sha256(data).hexdigest()
        path = self._directory(scope) / (request.operation_id + '.json')
        runtime = self.host.runtime
        if runtime is None:
            raise ValueError('原PTY运行时需要核对')
        with self.executor._locked(environment_id=scope.environment_id), runtime.environment_lock(scope.environment_id), self.lock:
            if path.exists() or path.is_symlink():
                old = self.input_receipt(TerminalInputQuery(scope=scope, operation_id=request.operation_id))
                if old['payload_sha256'] != digest:
                    raise ValueError('原PTY输入字节已变化')
                return old
            state = self._input_state(scope)
            if state['pending_input'] is not None:
                pending = self.input_receipt(TerminalInputQuery(scope=scope, operation_id=state['pending_input']))
                if pending['status'] == 'unknown':
                    raise ValueError('原PTY输入等待核对')
                state['pending_input'] = None
            receipt = {'scope': scope.model_dump(), 'operation_id': request.operation_id, 'payload_sha256': digest, 'status': 'not_sent'}
            pty, runtime = self.ptys.get(scope.operation_id), self.host.runtime
            if pty is None or runtime is None:
                atomic_json(path, receipt)
                return receipt

            with runtime.environment_lock(scope.environment_id):
                try:
                    record = self._record(scope)
                    job = runtime.job_for_container(record['result']['token'])
                    if job is not pty['job'] or record['phase'] != 'ready':
                        raise ValueError('原PTY作业句柄已变化')
                    runtime.authorize_input(job)
                except Exception:
                    atomic_json(path, receipt)
                    return receipt
                atomic_json(self._directory(scope) / 'input-state.json', {**state, 'pending_input': request.operation_id})
                receipt['status'] = 'unknown'
                atomic_json(path, receipt)
                try:
                    runtime.authorize_input(job)
                    if pty['raw'].send(data) != len(data):
                        return receipt
                except Exception:
                    return receipt
                receipt['status'] = 'sent'
                atomic_json(path, receipt)
                atomic_json(self._directory(scope) / 'input-state.json', state)
                return receipt

    def input_receipt(self, request: TerminalInputQuery) -> dict:
        """严格读取原PTY收据，过期及重启后保持只读。:param request: 原scope和输入标识。:return: 原有限回执。"""
        value = super().input_receipt(request)
        digest = value.get('payload_sha256')
        if (value.get('status') not in ('sent', 'not_sent', 'unknown') or not isinstance(digest, str)
                or len(digest) != 64 or any(character not in '0123456789abcdef' for character in digest)):
            raise ValueError('原PTY输入收据损坏')
        return value

    def _prepare_stop(self, scope: ExecutionScope) -> None:
        record = self._record(scope)
        path = self.executor.data / 'environments' / scope.environment_id / 'runtime/execution.json'
        if path.exists() or path.is_symlink():
            execution = strict_json(safe_read(path, 256 * 1024, private=True), 256 * 1024)
            if execution.get('source') != scope.source or execution.get('run_id') != record['work']['id']:
                raise ValueError('原续聊实际停止定位与冻结Run不一致')
        self.close_pty(scope)

    def resize(self, scope: ExecutionScope, request: PtyResize) -> None:
        """只调整原PTY窗口，实际账号和许可仍逐次核对。:param scope: 原执行。:param request: 有限尺寸。:return: None。"""
        runtime = self.host.runtime
        if runtime is None:
            raise ValueError('原PTY运行时需要核对')
        with self.executor._locked(environment_id=scope.environment_id), runtime.environment_lock(scope.environment_id), self.lock:
            pty = self.ptys[scope.operation_id]
            try:
                self.host.runtime.authorize_input(pty['job'])
            except ValueError:
                # 尺寸变化不提交业务输入；证明失效后保留原输出和原窗口。
                return
            self.host.runtime.client.api.exec_resize(pty['exec'], height=request.rows, width=request.cols)

    def credentials(self, scope: ExecutionScope) -> dict:
        """仅发布中央所有者已投影的绑定AT。:param scope: 原续聊。:return: 原范围确认。"""
        with self.executor._locked(environment_id=scope.environment_id):
            if scope.gateway_account_id is None or self.host.runtime is None:
                raise ValueError('绑定续聊凭据发布范围无效')
            record = self._record(scope)
            runtime = self.host.runtime
            job = runtime.job_for_container(record['result']['token'])
            runtime.authorize_input(job)
            runtime.sync_credentials(job['row'], job['account'])
            return {'scope': scope.model_dump(), 'synced': True}

    def close_pty(self, scope: ExecutionScope) -> None:
        """关闭原输入端点，实际作业停止仍由原恢复合同确认。:param scope: 原执行。:return: None。"""
        with self.lock:
            pty = self.ptys.pop(scope.operation_id, None)
            if pty is not None:
                try:
                    pty['raw'].close()
                finally:
                    atomic_json(self._directory(scope) / 'pty.json', {'scope': scope.model_dump(), 'phase': 'closed', 'exec': pty['exec']})

    def close(self) -> None:
        """收口本进程PTY连接，实际作业继续沿原host停止合同。:return: None。"""
        with self.lock:
            scopes = [value['scope'] for value in self.ptys.values()]
        for scope in scopes:
            self.close_pty(scope)

    async def serve(self, websocket: WebSocket, scope: ExecutionScope) -> None:
        """在私有连接中转发原PTY，单连接结束后关闭其新输入能力。

        :param websocket: 已核对节点认证的私有连接。
        :param scope: 首帧冻结执行。
        :return: None；启动或输入未知保持原持久记录。
        """
        await serve_node_pty(self,websocket,scope)
