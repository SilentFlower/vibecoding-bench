"""中央普通Runner的具体节点路由，保持原source、调度和真实停止合同。"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
from uuid import uuid4

from account_runtime import RuntimeBusy
from cluster_deployment import node_container_name
from cluster_execution_grants import ExecutionScope
from cluster_runs import RunFile, RunFileEntry, RunStart, RunTask, RunUsage, RunWork
from cluster_quota import QuotaFileChunk
from run_usage import usage_input_tokens
from run_artifacts import MAX_WORKSPACE_ENTRIES, MAX_WORKSPACE_LIST_BYTES, PREVIEW_BYTES
from system_update_contract import strict_json


class ClusterRunner:
    """按原账号归属启动一次实际Run，返回只由中央解析的原操作定位。

    :param sessions: 共用原中央许可/续约/停止协调器。
    :param identity: 原中央额度身份函数。
    """

    def __init__(self, sessions, identity) -> None:
        """登记原所有者依赖。:param sessions: 中央协调器。:param identity: 原身份。:return: None。"""
        self.sessions, self.identity = sessions, identity
        self.project_io = None
        self.credentials = None
        self.owners = None
        self.logins = None
        self.bound_logins = None
        self.draft_logins = None
        self.recovery_stop, self.recovery_thread = threading.Event(), None
        self.recovery_sources = None
        self.recovery_lock = threading.RLock()

    def routes(self, account: dict) -> bool:
        """从中央人工归属选择执行位置。

        :param account: 原账号。
        :return: 是否由所属SSH节点承接。
        """
        return self.sessions.service.store.assignment(account['id'])['kind'] == 'ssh'

    def handles(self, token: str | None) -> bool:
        """识别中央原Run操作定位。:param token: 原worker或sidecar字段。:return: 是否为节点Run。"""
        return isinstance(token, str) and re.fullmatch(r'remote-run:[a-f0-9]{32}', token) is not None

    def _row(self, token: str) -> dict:
        if not self.handles(token):
            raise ValueError('原远程Run定位无效')
        row = self.sessions.ledger.get(token.removeprefix('remote-run:'))
        if row['role'] != 'cli':
            raise ValueError('原远程Run定位属于其他执行类型')
        RunWork.model_validate(row['record']['work'])
        return row

    def for_run(self, run_id: str) -> dict | None:
        """按原中央Run尝试查实际节点，历史读取保留冻结位置。

        :param run_id: 原Run。
        :return: 该次尝试原执行或None。
        """
        connection = self.sessions.service.store.database()
        try:
            run = connection.execute('SELECT account_id,quota_attempt,execution_source FROM runs WHERE id=?', (run_id,)).fetchone()
        finally:
            connection.close()
        if run is None:
            return None
        row = self.sessions.ledger.by_source(run['account_id'], f"run:{run_id}:{run['quota_attempt']}", active_only=False)
        if row is None and isinstance(run['execution_source'], str):
            previous = re.fullmatch(r'run:([a-f0-9]{12}):([0-9]+)', run['execution_source'])
            if previous and previous[1] == run_id and int(previous[2]) < run['quota_attempt']:
                row = self.sessions.ledger.by_source(run['account_id'], run['execution_source'], active_only=False)
        return row

    def start(self, run_id: str, account: dict, task: dict, environment: dict) -> tuple[str, str]:
        """启动原Run，失败后登记原操作的后台实际收口。

        :param run_id: 原Run。
        :param account: 原账号。
        :param task: 原冻结任务。
        :param environment: 原worker环境。
        :return: 原操作定位。
        """
        try:
            return self._start(run_id, account, task, environment)
        except Exception:
            try:
                source = f"run:{run_id}:{int(task.get('quota_attempt') or 0)}"
                row = self.sessions.ledger.by_source(account['id'], source, active_only=True)
                if row is not None:
                    try:
                        self.sessions._isolate(row['operation_id'], 'remote_start_unconfirmed')
                    finally:
                        self._queue_recovery(row)
            except Exception:
                # 原持久占用继续拒绝新作业，中央重启仍按账本恢复该原来源。
                pass
            raise

    def _start(self, run_id: str, account: dict, task: dict, environment: dict) -> tuple[str, str]:
        """在任何中央工作目录创建前选择并启动原节点任务。

        :param run_id: 原Run。
        :param account: 原账号。
        :param task: 原冻结任务模式。
        :param environment: 原Runner已解析的worker环境。
        :return: 相同的中央节点执行定位，保持原DTO兼容。
        """
        source = f"run:{run_id}:{int(task.get('quota_attempt') or 0)}"
        previous_project = self.sessions.ledger.by_source(account['id'],source,active_only=False)
        project = (previous_project['record']['work'].get('project') if previous_project is not None
            else self.project_io.binding(run_id) if self.project_io else None)
        work = RunWork(id=run_id, account_id=account['id'], task=RunTask(id=task['id'],
            quota_attempt=int(task.get('quota_attempt') or 0), warmup=bool(task.get('warmup')),
            capture_full_http=bool(task.get('capture_full_http')),
            claude_code_version_source=task.get('claude_code_version_source')), worker_env=environment, project=project)
        with self.sessions._operation_lock('source:' + str(account['id']) + ':' + work.source):
            previous = self.sessions.ledger.by_source(account['id'], work.source, active_only=False)
            if previous is not None:
                if previous['record']['work'] != work.model_dump():
                    raise ValueError('原远程Run冻结任务已变化，请核对原尝试')
                row = previous
            else:
                if any(item['phase'] in ('reconcile', 'stopping') for item in self.sessions.ledger.active(account['id'])):
                    raise RuntimeBusy('账号原节点执行等待核对')
                service, runtime = self.sessions.service, self.sessions.runtime
                service.prepare_remote_cli(account, runtime, self.sessions.gateway, self.identity(account))
                assignment = service.store.assignment(account['id'])
                if assignment['kind'] != 'ssh' or assignment['phase'] != 'ready':
                    raise ValueError('Run准备期间账号节点归属发生变化')
                if work.project is not None:
                    node=service.store.get(assignment['node_id'])
                    asset=service.connection(node['id']).execution_environment(node_container_name(runtime.deployment,node['node_key']),
                        {'node_key':node['node_key'],'digest':work.project.library_digest},'terminal-assets')
                    if (asset.get('protocol')!=1 or asset.get('node_key')!=node['node_key']
                            or asset.get('terminal')!={'digest':work.project.library_digest,'state':'registered'}):
                        raise ValueError('节点原经典项目资产注册回执无效')
                actual = runtime._row(account['name'], account['id'])
                scope = ExecutionScope(operation_id=uuid4().hex, node_key=assignment['node_key'], account_id=account['id'],
                    gateway_account_id=account.get('cc2api_account_id'), environment_id=actual['environment_id'],
                    assignment_revision=assignment['revision'], generation=actual['generation'], source=work.source, role='cli')
                row = self.sessions.start(RunStart(scope=scope, work=work))
            if row['phase'] == 'closed':
                raise ValueError('原远程Run尝试已经收口，后续工作须使用新的原尝试标识')
            if row['phase'] != 'running' or row['record']['node_receipt']['phase'] != 'ready':
                raise RuntimeBusy('原远程Run启动结果等待核对，请查询原操作')
            scope = ExecutionScope.model_validate(row['record']['scope'])
            with self.sessions.service.store.lock:
                connection = self.sessions.service.store.database()
                try:
                    with connection:
                        cursor = connection.execute('UPDATE runs SET environment_id=?,environment_generation=?,execution_source=?,runtime_release=? '
                            'WHERE id=? AND account_id=? AND quota_attempt=?', (scope.environment_id, scope.generation, scope.source,
                                row['record']['runtime_release'], run_id, account['id'], work.task.quota_attempt))
                        if cursor.rowcount != 1:
                            raise ValueError('原中央Run尝试在实际启动后发生变化，请核对原节点执行')
                finally:
                    connection.close()
            if work.project is not None:
                if self.project_io is None:
                    raise ValueError('原中央经典项目文件所有者尚未就绪')
                self.project_io.permit(row)
            token = 'remote-run:' + row['operation_id']
            return token, token

    def poll(self, token: str) -> dict:
        """取得原节点实际exec与有界worker状态。:param token: 原定位。:return: 原轮询回执。"""
        row = self._row(token)
        result = self._read(row, 'run-poll', row['record']['scope'])
        if (result.get('scope') != row['record']['scope'] or type(result.get('running')) is not bool
                or not isinstance(result.get('worker_status'), dict)
                or not result['running'] and type(result.get('exit_code')) is not int):
            raise ValueError('原节点Run实际状态回执无效')
        return result

    def _read(self, row: dict, operation: str, payload: dict) -> dict:
        deadline = time.monotonic() + 10
        while True:
            result = self.sessions._call(row, operation, payload)
            if (result.get('scope') != row['record']['scope'] or result.get('busy') is not True
                    or set(result) != {'scope', 'busy'}):
                return result
            if time.monotonic() >= deadline:
                raise RuntimeBusy('原节点Run正在投递或收口，请稍后查询实际状态')
            # 只重复已确认无副作用的状态查询，原业务输入继续沿持久回执处理。
            time.sleep(0.1)

    def wait_worker(self, token: str) -> int:
        """短轮询等待原exec，失联或未知输入保留原操作。

        :param token: 原中央Run定位。
        :return: 实际driver退出码。
        """
        while True:
            result = self.poll(token)
            if result.get('pending_input') is not None:
                self.sessions._isolate(token.removeprefix('remote-run:'), 'remote_input_unconfirmed')
                raise RuntimeError('节点Run输入结果待核对，已保留原作业与回执')
            if not result['running']:
                return result['exit_code']
            time.sleep(0.5)

    def status(self, run_id: str) -> dict:
        """读取原实际worker轻量状态。:param run_id: 原Run。:return: 原worker状态。"""
        raw = self.artifact(run_id, 'status.json')
        return strict_json(raw, 65536) if raw is not None else {}

    def artifact_chunk(self, row: dict, name: str, offset: int = 0) -> QuotaFileChunk:
        """读取固定原产物的有界片段，范围与响应均严格核对。

        :param row: 原冻结执行。
        :param name: 固定产物名。
        :param offset: 原字节位置。
        :return: 原文件身份及最多128KiB片段。
        """
        result = self._read(row, 'run-artifact', {'scope': row['record']['scope'], 'name': name, 'offset': offset})
        if result.get('scope') != row['record']['scope'] or result.get('name') != name:
            raise ValueError('原节点Run产物属于其他执行')
        chunk = QuotaFileChunk.model_validate({key: value for key, value in result.items() if key not in ('scope', 'name')})
        content = base64.b64decode(chunk.content, validate=True)
        if (len(content) > 128 * 1024 or chunk.offset + len(content) > chunk.size
                or chunk.file_identity is None and (chunk.size or chunk.offset or content)):
            raise ValueError('原节点Run产物片段大小无效')
        return chunk

    def artifact(self, run_id: str, name: str, *, limit: int = 65536) -> bytes | None:
        """读取有界轻量产物，缺失与损坏继续区分。

        :param run_id: 原Run。
        :param name: 固定产物名。
        :param limit: 当前消费者的固定字节上限。
        :return: 完整原字节；原文件缺失为None。
        """
        row = self.for_run(run_id)
        if row is None:
            raise ValueError('原Run缺少节点执行定位')
        chunk = self.artifact_chunk(row, name)
        if chunk.file_identity is None:
            return None
        if chunk.size > limit:
            raise ValueError('原Run产物超过该入口读取上限')
        return b''.join(self.iter_artifact(row, name, first=chunk))

    def iter_artifact(self, row: dict, name: str, *, first: QuotaFileChunk | None = None, offset: int = 0):
        """有界流式读取本次已观察大小，轮转保持显式失败。

        :param row: 原执行。
        :param name: 固定产物名。
        :param first: 已核对的首段元数据。
        :param offset: 本次读取的起点。
        :return: 最多128KiB的原字节迭代器。
        """
        first = first or self.artifact_chunk(row, name)
        if first.file_identity is None:
            return
        identity, size = first.file_identity, first.size
        position = offset
        chunk = self.artifact_chunk(row, name, offset) if offset else first
        while True:
            if chunk.file_identity != identity or chunk.offset != position or chunk.size < size:
                raise ValueError('原Run产物在读取期间发生轮转')
            piece = base64.b64decode(chunk.content, validate=True)
            if not piece and position < size:
                raise ValueError('原Run产物片段未推进')
            piece = piece[:size - position]
            yield piece
            position += len(piece)
            if position >= size:
                return
            chunk = self.artifact_chunk(row, name, position)

    def latest_session(self, run_id: str) -> str | None:
        """读取原节点本次实际会话，用于原额度尝试的恢复。

        :param run_id: 原Run。
        :return: 原主会话标识或None。
        """
        row = self.for_run(run_id)
        if row is None:
            raise ValueError('原Run缺少节点执行定位')
        result = self._read(row, 'run-session', row['record']['scope'])
        session = result.get('session_id')
        if (result.get('scope') != row['record']['scope'] or set(result) != {'scope', 'session_id'}
                or session is not None and (not isinstance(session, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', session))):
            raise ValueError('原节点Run主会话定位无效')
        return session

    def files(self, run_id: str) -> list[dict]:
        """聚合原节点的有界公开文件分页。

        :param run_id: 原Run。
        :return: 原文件树；响应错误、超限或失联保持显式失败。
        """
        row = self.for_run(run_id)
        if row is None:
            raise ValueError('原Run缺少节点执行定位')
        entries, after, size = [], '', 0
        while True:
            result = self._read(row, 'run-files', {'scope': row['record']['scope'], 'after': after})
            if (set(result) != {'scope', 'available', 'files', 'next'} or result['scope'] != row['record']['scope']
                    or type(result['available']) is not bool or not isinstance(result['files'], list)
                    or len(result['files']) > 128):
                raise ValueError('原节点Run文件清单回执无效')
            if not result['available']:
                if result['files'] or result['next'] is not None:
                    raise ValueError('原节点Run缺失清单回执无效')
                raise FileNotFoundError('原Run产物目录尚未提供')
            for raw in result['files']:
                entry = RunFileEntry.model_validate(raw).model_dump(exclude_none=True)
                if entry['path'] <= after:
                    raise ValueError('原节点Run文件游标未推进')
                after = entry['path']
                size += len(json.dumps(entry, ensure_ascii=False).encode())
                entries.append(entry)
                if len(entries) > MAX_WORKSPACE_ENTRIES or size > MAX_WORKSPACE_LIST_BYTES:
                    raise ValueError('原节点Run文件清单超过读取上限')
            if result['next'] is None:
                return entries
            if not result['files'] or result['next'] != after:
                raise ValueError('原节点Run文件下一页游标无效')

    def file(self, run_id: str, path: str) -> dict:
        """读取原Node的64KiB公开预览，保持原文本与二进制语义。

        :param run_id: 原Run。
        :param path: 公开相对路径。
        :return: 原预览字段。
        """
        row = self.for_run(run_id)
        if row is None:
            raise ValueError('原Run缺少节点执行定位')
        request = RunFile(scope=row['record']['scope'], path=path)
        result = self._read(row, 'run-file', request.model_dump())
        if result == {'scope': row['record']['scope'], 'available': False}:
            raise FileNotFoundError('原Run产物文件尚未提供')
        if (set(result) != {'scope', 'available', 'path', 'size', 'truncated', 'binary', 'text_base64'}
                or result['scope'] != row['record']['scope'] or result['available'] is not True
                or result['path'] != path or type(result['size']) is not int or result['size'] < 0
                or type(result['truncated']) is not bool or type(result['binary']) is not bool
                or not isinstance(result['text_base64'], str)):
            raise ValueError('原节点Run文件预览回执无效')
        raw = base64.b64decode(result['text_base64'], validate=True)
        if len(raw) > PREVIEW_BYTES or result['binary'] and raw:
            raise ValueError('原节点Run文件预览超过读取上限')
        return {'path': path, 'size': result['size'], 'truncated': result['truncated'], 'binary': result['binary'],
            'text': raw.decode('utf-8')}

    def stats(self, run_id: str) -> dict:
        """读取原scope的共享聚合结果。:param run_id: 原Run。:return: 原公开stats。"""
        row = self.for_run(run_id)
        if row is None:
            raise ValueError('原Run缺少节点执行定位')
        result = self._read(row, 'run-stats', row['record']['scope'])
        if set(result) != {'scope', 'stats'} or result['scope'] != row['record']['scope']:
            raise ValueError('原节点Run统计属于其他执行')
        stats = RunUsage.model_validate(result['stats']).model_dump()
        if row['record']['work'].get('project') and not stats['usage_available']:
            if self.project_io is None:
                raise ValueError('原经典项目用量文件所有者尚未就绪')
            usage=self.project_io.manager.native_usage(run_id,self.project_io.manager.data/'missing-native',usage_input_tokens)
            if usage['usage_available']:
                stats.update(tokens_in=usage['tokens_in'],tokens_out=usage['tokens_out'],requests=usage['requests'],
                    available=True,usage_available=True,source='claude_session')
        return stats

    def capture(self, run_id: str, *, running: bool, relative: str | None = None) -> dict:
        """读取原执行节点的脱敏抓包投影。:param run_id: 原Run。:param running: 原活动状态。:param relative: 原白名单预览。:return: 原公开抓包。"""
        row = self.for_run(run_id)
        if row is None:
            raise ValueError('原Run缺少节点执行定位')
        result = self._read(row, 'run-capture', {'scope': row['record']['scope'], 'running': running, 'relative': relative})
        if (set(result) != {'scope', 'capture'} or result['scope'] != row['record']['scope']
                or not isinstance(result['capture'], dict)):
            raise ValueError('原节点Run抓包属于其他执行')
        return result['capture']

    def cleanup(self, token: str) -> None:
        """按原scope取得实际停止回执后释放中央许可。

        :param token: 原中央Run定位。
        :return: None；未知继续保留原活动占用。
        """
        row = self._row(token)
        try:
            self.sessions.stop(row['operation_id'])
        except Exception:
            try:
                self.sessions._isolate(row['operation_id'], 'remote_stop_unconfirmed')
            except Exception:
                # 数据库暂不可写时，原所有者明确登记的内存收口集合继续保留。
                pass
            self._queue_recovery(row)
            raise

    def _queue_recovery(self, row: dict) -> None:
        with self.recovery_lock:
            if self.recovery_sources is None:
                self.recovery_sources = set()
            self.recovery_sources.add((row['account_id'], row['source']))

    def watch_managed_oauth_refresh(self, token: str, account: dict, stop_event, refresh, owner_lock) -> None:
        """读取原worker请求，由中央原所有者刷新一次并在节点发布固定结果。

        :param token: 原Run定位。
        :param account: 原绑定账号。
        :param stop_event: 原worker收口信号。
        :param refresh: 已在原owner锁内执行的唯一刷新回调。
        :param owner_lock: 原账号中央OAuth所有权锁。
        :return: None；提交未知只查原发布回执。
        """
        row = self._row(token)
        scope = row['record']['scope']
        if scope['account_id'] != account['id'] or scope['gateway_account_id'] != account.get('cc2api_account_id'):
            raise ValueError('原Run刷新账号绑定不一致')
        independent=scope['gateway_account_id'] is None
        if independent:
            work=RunWork.model_validate(row['record']['work'])
            if work.project is None or work.project.scenario is None or work.project.scenario.review is None:
                return
            if self.credentials is None:
                raise ValueError('原Node独立凭据维护所有者尚未就绪')
        while not stop_event.wait(1):
            row = self.sessions.ledger.get(row['operation_id'])
            if row['phase'] != 'running':
                return
            try:
                chunk = self.artifact_chunk(row, 'oauth-refresh-request.json')
                if chunk.file_identity is None:
                    continue
                raw = base64.b64decode(chunk.content, validate=True)
                if chunk.offset or chunk.size != len(raw) or len(raw) > 8192:
                    raise ValueError('原worker刷新请求超限')
                strict_json(raw, 8192)
                request = {'scope': scope, 'request_sha256': hashlib.sha256(raw).hexdigest(), 'ok': False}
                if independent:
                    if stop_event.is_set():
                        return
                    self.credentials.defer_review(row,request['request_sha256'])
                    self._queue_recovery(row)
                    return
                with owner_lock:
                    self.sessions.ledger.admit(row['operation_id'])
                    if stop_event.is_set():
                        return
                    try:
                        refresh()
                        self.sessions.service.prepare_remote_cli(account, self.sessions.runtime, self.sessions.gateway, self.identity(account))
                        request['ok'] = True
                    except Exception:
                        # 原刷新所有者保留自己的不确定提交；节点只接收固定失败结果。
                        pass
                    if stop_event.is_set():
                        return
                    try:
                        result = self.sessions._call(row, 'run-refresh', request)
                    except Exception:
                        result = self.sessions._call(row, 'run-refresh-get', request)
                    if result != {'request': request, 'phase': 'ready'}:
                        self.sessions._isolate(row['operation_id'], 'remote_refresh_unconfirmed')
                return
            except Exception:
                self.sessions._isolate(row['operation_id'], 'remote_refresh_unconfirmed')
                if independent:
                    self._queue_recovery(row)
                return

    def cleanup_run(self, run_id: str) -> None:
        """恢复时只收口该原Run实际尝试。:param run_id: 原Run。:return: None。"""
        row = self.for_run(run_id)
        if row is not None:
            self.cleanup('remote-run:' + row['operation_id'])
            if row['record']['work'].get('project') is not None:
                if self.project_io is None:
                    raise ValueError('原经典项目证据所有者尚未就绪')
                self.project_io.native_directory(run_id)

    def start_recovery(self, completed) -> None:
        """后台恢复旧节点任务，失联保留原占用并继续允许其他账号工作。

        :param completed: 实际收口后通知原Scheduler及额度所有者的回调。
        :return: None；恢复线程持续按原操作核对。
        """
        if self.recovery_thread is not None or self.recovery_stop.is_set():
            raise ValueError('节点Run恢复已经启动或关闭')
        self.recovery_sources = self._recovery_sources()
        self.recovery_thread = threading.Thread(target=self._recover_loop, args=(completed,), name='cluster-run-recovery', daemon=True)
        self.recovery_thread.start()

    def _recover_loop(self, completed) -> None:
        while not self.recovery_stop.is_set():
            for coordinator in (self.logins,self.bound_logins,self.draft_logins):
                try:
                    if coordinator is not None:
                        coordinator.recover_pending()
                except Exception:
                    # 各具体登录持久记录保留，其他账号继续核对原工作。
                    pass
            try:
                if self.credentials is not None:
                    self.credentials.recover_pending()
            except Exception:
                # 凭据操作的未知状态保持原维护，其他账号继续核对各自Run。
                pass
            try:
                if self.project_io is not None and self.project_io.programs is not None:
                    self.project_io.programs.recover_pending()
            except Exception:
                # 程序账本异常保留其占用，普通Run继续核对各自原来源。
                pass
            try:
                self.recover_once(completed)
            except Exception:
                # 原账本和维护占用继续保留；单次后台读取故障等待下轮核对。
                pass
            self.recovery_stop.wait(5)

    def _recovery_sources(self) -> set[tuple[int, str]]:
        connection = self.sessions.service.store.database()
        try:
            return {(row['account_id'], row['source']) for row in connection.execute(
                "SELECT e.account_id,e.source FROM node_executions e JOIN runs r ON r.account_id=e.account_id "
                "AND e.source LIKE 'run:'||r.id||':%' WHERE e.role='cli' AND (e.phase<>'closed' OR "
                "(r.status IN ('queued','running','stopping','quota_wait') AND e.source='run:'||r.id||':'||r.quota_attempt))")}
        finally:
            connection.close()

    def recover_once(self, completed) -> None:
        """收口旧来源及本进程明确失败的原操作，保留后来新作业。

        :param completed: 实际停止后通知原Scheduler的回调。
        :return: None；单个账号故障继续保留原占用。
        """
        with self.recovery_lock:
            if self.recovery_sources is None:
                self.recovery_sources = self._recovery_sources()
            sources = set(self.recovery_sources)
        for account_id, source in sources:
            if self.recovery_stop.is_set():
                return
            run = None
            try:
                row = self.sessions.ledger.by_source(account_id, source, active_only=False)
                if row is None:
                    continue
                work = RunWork.model_validate(row['record']['work'])
                # 集合只含启动前旧来源或原所有者明确登记的失败；续约线程尚未退出时仍可重试原停止。
                connection = self.sessions.service.store.database()
                try:
                    current = connection.execute('SELECT * FROM runs WHERE account_id=? AND id=?', (account_id, work.id)).fetchone()
                    run = dict(current) if current is not None and current['quota_attempt'] == work.task.quota_attempt else None
                finally:
                    connection.close()
                self.sessions.stop(row['operation_id'])
                if run is not None:
                    account = self.sessions._account(ExecutionScope.model_validate(row['record']['scope']), available=False)
                    completed(work.id, work.task.quota_attempt, account)
                with self.recovery_lock:
                    self.recovery_sources.discard((account_id, source))
            except Exception:
                if run is not None:
                    self._recovery_pending(run)

    def _recovery_pending(self, run: dict) -> None:
        with self.sessions.service.store.lock:
            connection = self.sessions.service.store.database()
            try:
                with connection:
                    connection.execute("UPDATE runs SET error='服务重启后原节点执行正在对账' "
                        "WHERE id=? AND quota_attempt=? AND status IN ('queued','running','stopping','quota_wait') AND stop_requested_at IS NULL",
                        (run['id'], run['quota_attempt']))
            finally:
                connection.close()

    def close(self) -> None:
        """关闭后台恢复入口，原未决作业与维护占用继续由账本保存。:return: None。"""
        self.recovery_stop.set()
        if self.logins is not None:
            self.logins.close()
        if self.bound_logins is not None:
            self.bound_logins.close()
        if self.draft_logins is not None:
            self.draft_logins.close()
        if self.credentials is not None:
            self.credentials.close()
        if self.recovery_thread is not None:
            self.recovery_thread.join(timeout=2)
