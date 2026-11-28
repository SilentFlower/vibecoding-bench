"""SSH控制容器的长驻私有执行服务，账号运行时与实际jobs由同一进程持有。"""
from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import re
import socket
import threading
from traceback import extract_tb
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from secrets import compare_digest
from stat import S_ISREG, S_ISSOCK

from docker import DockerClient
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from pydantic import Field, StrictStr
from starlette.concurrency import run_in_threadpool
from uvicorn import Config, Server

from cluster_execution import NodeExecution, NodeLocation, execute_operation
from agy_node import AgyNode
from agy_node_contract import AGY_NODE_OPERATIONS, AGY_NODE_SHORT
from cluster_quiesce import NodeQuiesce, quiesce_node
from cluster_update_gate import NodeGateCommand, node_admission, node_gate
from cluster_execution_grants import ExecutionGrant, ExecutionGrants, ExecutionScope
from cluster_draft_login import NodeDraftLogins
from cluster_draft_login_contract import DraftLoginAccept, DraftLoginActivation, DraftLoginCode, DraftLoginCodeRead, DraftLoginGrant, DraftLoginGrantClose, DraftLoginInputQuery, DraftLoginPreparation, DraftLoginPreparationDelete, DraftLoginScope, DraftLoginStart
from cluster_draft_login_grants import DraftLoginGrants
from cluster_draft_login_operations import DRAFT_LOGIN_OPERATIONS, DRAFT_LOGIN_SHORT_OPERATIONS
from cluster_private import initialize_node_private
from cluster_quota import ApiQuotaRead, NodeTerminalQuota, TerminalQuotaRead, TerminalQuotaState, read_api_quota
from cluster_project_capture import ProjectHistoryCapture, read_project_history_capture
from cluster_runtime_host import NodeRuntimeHost
from cluster_runs import NodeRuns
from cluster_run_verification import NodeRunVerifications
from cluster_continue import NodeContinues
from cluster_credentials import NodeCredentials
from cluster_credentials_contract import CredentialRefreshStart, CredentialStatusRead, CredentialUsageStart
from cluster_owner_contract import OwnerPrepare, OwnerPublish
from cluster_owner_node import owner_receipt, prepare_owner, publish_owner
from cluster_login import NodeAccountLogins
from cluster_login_contract import AccountLoginAccept, AccountLoginCode, AccountLoginCodeRead, AccountLoginStart
from cluster_environment_operations import ENVIRONMENT_OPERATIONS, response_limit
from cluster_environment_management import (EnvironmentState, EnvironmentReference, EnvironmentCpu, EnvironmentChoice,
    EnvironmentCapture, EnvironmentMaintenance, environment_management)
from cluster_bound_identity import BoundIdentityRead, read_bound_identity, read_bound_process
from cluster_bound_login import NodeBoundAccountLogins
from cluster_bound_login_contract import BoundLoginAbort, BoundLoginPublish, BoundLoginStart
from cluster_terminal import NodeTerminals, TerminalInputQuery
from cluster_workspace import NodeWorkspaceSnapshots, WorkspaceSnapshotReference, WorkspaceSnapshotRequest
from cluster_verification import NodeVerifications, RunVerificationStart, VerificationReference, VerificationStart
from runtime_files import directory_fd, private_directory
from system_update_contract import strict_json
from cluster_restart import PreservedRestart, restart_preserved
from cluster_preparation_files import PreparationFiles, prepare_from_files, stage_preparation_files
from cluster_migration_errors import migration_failure


class _GrantClosure(ExecutionScope):
    """关闭原有限证明所需的精确范围及固定原因。"""

    reason: StrictStr = Field(pattern=r'^[a-z][a-z0-9_]{0,79}$')


def create_node_app(executor: NodeExecution, host: NodeRuntimeHost, token: str, release: str) -> FastAPI:
    """建立仅由私有UDS承载的固定操作服务。

    :param executor: 已核对安装归属的执行入口。
    :param host: 本进程持有的唯一节点运行时。
    :param token: 本节点独立服务认证。
    :param release: 当前精确发布身份。
    :return: 私有应用；生命周期结束时收口本进程实际作业。
    """
    if host.executor is not executor or not re.fullmatch('[a-f0-9]{64}', token) or not release:
        raise ValueError('节点私有服务安装范围或认证无效')
    grants = ExecutionGrants(executor.data, executor.node_key, executor.deployment, executor.database)
    host.attach_grants(grants)
    # AGY 请求本身由发送器持有；节点配置按单次操作注入，避免写入工程账号的长驻快照。
    agy = AgyNode(NodeExecution(executor.data, executor.host_data, executor.node_key, executor.deployment,
        executor.client, runtime_factory=host.runtime_factory))
    terminals = NodeTerminals(executor, host, grants)
    snapshots = NodeWorkspaceSnapshots(terminals)
    quotas = NodeTerminalQuota(terminals)
    runs = NodeRuns(executor, host, grants)
    credentials = NodeCredentials(executor, host, grants, runs)
    logins = NodeAccountLogins(executor, host, grants, credentials)
    bound_logins = NodeBoundAccountLogins(executor,host,grants)
    bound_logins.slots=logins.slots
    draft_grants=DraftLoginGrants(executor.data,executor.node_key,executor.deployment,executor.database)
    draft_logins=NodeDraftLogins(executor,host,draft_grants)
    draft_logins.slots=logins.slots
    run_quotas = NodeTerminalQuota(runs)
    run_snapshots = NodeWorkspaceSnapshots(runs, source=runs.snapshot_workspace)
    continues = NodeContinues(executor, host, grants)
    continue_quotas = NodeTerminalQuota(continues)
    pty_slots = threading.BoundedSemaphore(4)
    verifications = NodeVerifications(terminals, snapshots)
    run_verifications = NodeRunVerifications(runs, run_snapshots)
    run_verifications.slots = verifications.slots
    terminals.stop_dependents = verifications.stop_scope
    slots = threading.BoundedSemaphore(8)
    control_slots = threading.BoundedSemaphore(4)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            try:
                await run_in_threadpool(continues.close)
                await run_in_threadpool(logins.close)
                await run_in_threadpool(bound_logins.close)
                await run_in_threadpool(draft_logins.close)
                await run_in_threadpool(credentials.close)
                await run_in_threadpool(verifications.close)
                await run_in_threadpool(run_verifications.close)
            finally:
                await run_in_threadpool(host.close)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def dispatch(operation: str, raw: bytes) -> dict:
        try:
            if operation == 'health':
                if strict_json(raw, 8192) != {}:
                    raise ValueError('节点健康检查输入无效')
                value = {'protocol': 1, 'node_key': executor.node_key, 'deployment': executor.deployment,
                    'release': release, 'state': 'ready'}
            elif operation == 'platform-gate':
                value = node_gate(executor, NodeGateCommand.model_validate(strict_json(raw, 4096)))
            elif operation in AGY_NODE_OPERATIONS:
                value = agy.call(operation, strict_json(raw, 2 * 1024 * 1024))
            elif operation in ('stage-preparation-files', 'prepare-files'):
                request = PreparationFiles.model_validate(strict_json(raw, 2 * 1024 * 1024))
                value = (stage_preparation_files if operation == 'stage-preparation-files' else prepare_from_files)(executor, request)
            elif operation == 'restart-preserved':
                value = restart_preserved(executor, PreservedRestart.model_validate(strict_json(raw, 16384)))
            elif operation in ('grant-create', 'grant-renew', 'grant-get', 'grant-close'):
                model = ExecutionGrant if operation in ('grant-create', 'grant-renew') else (
                    _GrantClosure if operation == 'grant-close' else ExecutionScope)
                request = model.model_validate(strict_json(raw, 16384))
                # 续接与撤销只改私有证明，独立于长安装的环境文件锁；实际输入仍逐次核对。
                if operation == 'grant-close':
                    scope = ExecutionScope.model_validate(request.model_dump(exclude={'reason'}))
                    record = grants.close(scope, request.reason)
                else:
                    action = {'grant-create': grants.create, 'grant-renew': grants.renew, 'grant-get': grants.get}[operation]
                    record = action(request)
                value = {'protocol': 1, 'node_key': executor.node_key, 'record': record}
            elif operation in ('terminal-verification-start', 'terminal-verification-get', 'terminal-verification-cancel'):
                model = VerificationStart if operation == 'terminal-verification-start' else VerificationReference
                request = model.model_validate(strict_json(raw, 2 * 1024 * 1024))
                action = {'terminal-verification-start': verifications.start,
                    'terminal-verification-get': verifications.get, 'terminal-verification-cancel': verifications.cancel}[operation]
                value = {'protocol': 1, 'node_key': executor.node_key, 'terminal': action(request)}
            elif operation == 'api-quota-read':
                request = ApiQuotaRead.model_validate(strict_json(raw, 16384))
                value = {'protocol': 1, 'node_key': executor.node_key, 'quota': read_api_quota(executor, request)}
            elif operation == 'project-history-capture':
                request = ProjectHistoryCapture.model_validate(strict_json(raw, 16384))
                value = {'protocol': 1, 'node_key': executor.node_key, 'history': read_project_history_capture(executor, request)}
            elif operation in ('credential-status','credential-material','credential-identity','credential-identity-import'):
                request=CredentialStatusRead.model_validate(strict_json(raw,16384))
                action={'credential-status':credentials.status,'credential-material':credentials.material,
                    'credential-identity':credentials.identity,'credential-identity-import':credentials.identity_import}[operation]
                value={'protocol':1,'node_key':executor.node_key,'credentials':action(request)}
            elif operation=='account-quiesce':
                request=NodeQuiesce.model_validate(strict_json(raw,16384))
                value=quiesce_node(executor,request)
            elif operation in ENVIRONMENT_OPERATIONS:
                model={'environment-state':EnvironmentState,'environment-cpu-set':EnvironmentCpu,
                    'environment-capture-read':EnvironmentCapture,'environment-capture-set':EnvironmentChoice,
                    'environment-criu-set':EnvironmentChoice,'environment-maintenance':EnvironmentMaintenance}.get(operation,EnvironmentReference)
                request=model.model_validate(strict_json(raw,2*1024*1024))
                value=environment_management(executor,request,operation)
            elif operation in ('credential-owner-get','credential-owner-prepare','credential-owner-publish'):
                model={'credential-owner-get':NodeLocation,'credential-owner-prepare':OwnerPrepare,
                    'credential-owner-publish':OwnerPublish}[operation]
                request=model.model_validate(strict_json(raw,65536))
                action={'credential-owner-get':owner_receipt,'credential-owner-prepare':prepare_owner,
                    'credential-owner-publish':publish_owner}[operation]
                value={'protocol':1,'node_key':executor.node_key,'ownership':action(executor,request)}
            elif operation in ('account-bound-identity','account-bound-process'):
                request=BoundIdentityRead.model_validate(strict_json(raw,16384))
                value={'protocol':1,'node_key':executor.node_key,'identity':(read_bound_process if operation=='account-bound-process' else read_bound_identity)(executor,request)}
            elif operation in DRAFT_LOGIN_OPERATIONS:
                action=operation.removeprefix('draft-login-')
                model={'prepare':DraftLoginPreparation,'recover-preparation':DraftLoginPreparation,'delete-preparation':DraftLoginPreparationDelete,'start':DraftLoginStart,'code':DraftLoginCode,
                    'code-receipt':DraftLoginCodeRead,'accept':DraftLoginAccept,'input':DraftLoginInputQuery,'activate':DraftLoginActivation,
                    'grant-create':DraftLoginGrant,'grant-renew':DraftLoginGrant,'grant-close':DraftLoginGrantClose}.get(action,DraftLoginScope)
                request=model.model_validate(strict_json(raw,2*1024*1024 if action in ('prepare','recover-preparation') else 65536))
                if action=='grant-close':
                    scope=DraftLoginScope.model_validate(request.model_dump(exclude={'reason'}))
                    value={'protocol':1,'node_key':executor.node_key,'record':draft_grants.close(scope,request.reason)}
                elif action in ('grant-create','grant-renew','grant-get'):
                    handler={'grant-create':draft_grants.create,'grant-renew':draft_grants.renew,'grant-get':draft_grants.get}[action]
                    value={'protocol':1,'node_key':executor.node_key,'record':handler(request)}
                else:
                    handler={'prepare':draft_logins.prepare,'recover-preparation':draft_logins.recover_preparation,'start':draft_logins.start,'get':draft_logins.get,
                        'stop':draft_logins.stop,'observe':draft_logins.observe,'code':draft_logins.code,
                        'code-receipt':draft_logins.code_receipt,'commit':draft_logins.commit,'snapshot':draft_logins.snapshot,
                        'accept':draft_logins.accept,'discard':draft_logins.discard,'input':draft_logins.input_receipt,
                        'files':draft_logins.files,'activate':draft_logins.activate,'summary':draft_logins.summary,'delete':draft_logins.delete,
                        'delete-preparation':draft_logins.delete_preparation}[action]
                    value={'protocol':1,'node_key':executor.node_key,'login':handler(request)}
            elif operation in ('account-bound-login-start','account-bound-login-get','account-bound-login-stop',
                    'account-bound-login-observe','account-bound-login-code','account-bound-login-code-receipt',
                    'account-bound-login-commit','account-bound-login-snapshot','account-bound-login-accept',
                    'account-bound-login-discard','account-bound-login-input','account-bound-login-publish','account-bound-login-abort'):
                action=operation.removeprefix('account-bound-login-')
                model={'start':BoundLoginStart,'code':AccountLoginCode,'code-receipt':AccountLoginCodeRead,
                    'accept':AccountLoginAccept,'input':TerminalInputQuery,'publish':BoundLoginPublish,'abort':BoundLoginAbort}.get(action,ExecutionScope)
                request=model.model_validate(strict_json(raw,65536))
                handler={'start':bound_logins.start,'get':bound_logins.get,'stop':bound_logins.stop,
                    'observe':bound_logins.observe,'code':bound_logins.code,'code-receipt':bound_logins.code_receipt,
                    'commit':bound_logins.commit,'snapshot':bound_logins.snapshot,'accept':bound_logins.accept,
                    'discard':bound_logins.discard,'input':bound_logins.input_receipt,'publish':bound_logins.publish,'abort':bound_logins.abort}[action]
                value={'protocol':1,'node_key':executor.node_key,'login':handler(request)}
            elif operation in ('account-login-start','account-login-get','account-login-stop','account-login-observe',
                    'account-login-code','account-login-code-receipt','account-login-commit','account-login-snapshot','account-login-accept','account-login-discard','account-login-input'):
                model=AccountLoginStart if operation=='account-login-start' else AccountLoginCode if operation=='account-login-code' else (
                    AccountLoginCodeRead if operation=='account-login-code-receipt' else AccountLoginAccept if operation=='account-login-accept'
                    else TerminalInputQuery if operation=='account-login-input' else ExecutionScope)
                request=model.model_validate(strict_json(raw,65536))
                action={'account-login-start':logins.start,'account-login-get':logins.get,'account-login-stop':logins.stop,
                    'account-login-observe':logins.observe,'account-login-code':logins.code,
                    'account-login-code-receipt':logins.code_receipt,'account-login-commit':logins.commit,
                    'account-login-snapshot':logins.snapshot,'account-login-accept':logins.accept,'account-login-discard':logins.discard,
                    'account-login-input':logins.input_receipt}[operation]
                value={'protocol':1,'node_key':executor.node_key,'login':action(request)}
            elif operation in ('credential-refresh-start','credential-refresh-get','credential-refresh-stop'):
                model=CredentialRefreshStart if operation=='credential-refresh-start' else ExecutionScope
                request=model.model_validate(strict_json(raw,32768))
                scope=request.scope if operation=='credential-refresh-start' else request
                if scope.source!='oauth-refresh:'+scope.operation_id:
                    raise ValueError('原刷新操作来源不一致')
                action={'credential-refresh-start':credentials.start,'credential-refresh-get':credentials.get,
                    'credential-refresh-stop':credentials.stop}[operation]
                value={'protocol':1,'node_key':executor.node_key,'credentials':action(request)}
            elif operation in ('credential-usage-start','credential-usage-get','credential-usage-stop'):
                model=CredentialUsageStart if operation=='credential-usage-start' else ExecutionScope
                request=model.model_validate(strict_json(raw,32768))
                scope=request.scope if operation=='credential-usage-start' else request
                if scope.source!='quota:'+scope.operation_id:
                    raise ValueError('原usage操作来源不一致')
                action={'credential-usage-start':credentials.start,'credential-usage-get':credentials.get,
                    'credential-usage-stop':credentials.stop}[operation]
                value={'protocol':1,'node_key':executor.node_key,'credentials':action(request)}
            elif operation in ('run-verification-start','run-verification-get','run-verification-cancel'):
                model=VerificationReference if operation=='run-verification-get' else RunVerificationStart
                request=model.model_validate(strict_json(raw,2*1024*1024))
                action={'run-verification-start':run_verifications.start,'run-verification-get':run_verifications.get,
                    'run-verification-cancel':run_verifications.cancel}[operation]
                value={'protocol':1,'node_key':executor.node_key,'run':action(request)}
            elif operation in ('terminal-quota-state', 'terminal-quota-read'):
                model = TerminalQuotaState if operation == 'terminal-quota-state' else TerminalQuotaRead
                request = model.model_validate(strict_json(raw, 96 * 1024))
                action = quotas.publish if operation == 'terminal-quota-state' else quotas.read
                value = {'protocol': 1, 'node_key': executor.node_key, 'terminal': action(request)}
            elif operation in ('run-quota-state', 'run-quota-read'):
                model = TerminalQuotaState if operation == 'run-quota-state' else TerminalQuotaRead
                request = model.model_validate(strict_json(raw, 96 * 1024))
                action = run_quotas.publish if operation == 'run-quota-state' else run_quotas.read
                value = {'protocol': 1, 'node_key': executor.node_key, 'run': action(request)}
            elif operation in ('run-snapshot', 'run-snapshot-get'):
                model = WorkspaceSnapshotRequest if operation == 'run-snapshot' else WorkspaceSnapshotReference
                request = model.model_validate(strict_json(raw,16384))
                action = run_snapshots.create if operation == 'run-snapshot' else run_snapshots.get
                value = {'protocol':1,'node_key':executor.node_key,'run':action(request)}
            elif operation.startswith('run-'):
                value = {'protocol': 1, 'node_key': executor.node_key, 'run': runs.dispatch(operation, raw)}
            elif operation in ('continue-quota-state', 'continue-quota-read'):
                model = TerminalQuotaState if operation == 'continue-quota-state' else TerminalQuotaRead
                request = model.model_validate(strict_json(raw, 96 * 1024))
                action = continue_quotas.publish if operation == 'continue-quota-state' else continue_quotas.read
                value = {'protocol': 1, 'node_key': executor.node_key, 'continue': action(request)}
            elif operation.startswith('continue-'):
                value = {'protocol': 1, 'node_key': executor.node_key, 'continue': continues.dispatch(operation, raw)}
            elif operation in ('terminal-snapshot', 'terminal-snapshot-get'):
                model = WorkspaceSnapshotRequest if operation == 'terminal-snapshot' else WorkspaceSnapshotReference
                request = model.model_validate(strict_json(raw, 16384))
                action = snapshots.create if operation == 'terminal-snapshot' else snapshots.get
                value = {'protocol': 1, 'node_key': executor.node_key, 'terminal': action(request)}
            elif operation.startswith('terminal-'):
                value = {'protocol': 1, 'node_key': executor.node_key, 'terminal': terminals.dispatch(operation, raw,
                    Path(os.environ.get('PROJECT_LIBRARY_DIR', '/repo/project_library')))}
            else:
                value = execute_operation(executor, operation, raw)
            result = {'ok': True, 'result': value}
            if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode()) > response_limit(operation):
                raise ValueError('节点执行回执过大，请核对原操作')
            return result
        except Exception as error:
            # 错误对象可能包含私有profile或Docker配置，仅返回原边界允许的类型。
            frames = ','.join(f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}'
                for frame in extract_tb(error.__traceback__)[-8:])
            logging.getLogger(__name__).error('节点执行失败 operation=%s error_type=%s frames=%s',
                operation if re.fullmatch('[a-z-]{1,80}', operation) else 'invalid', type(error).__name__, frames)
            result = {'ok': False, 'reason': 'node_preparation_failed', 'error_type': type(error).__name__}
            if operation in ('fence', 'export', 'verify-import', 'prepare-import', 'revoke-import', 'restore-source', 'stage-import'):
                result['failure'] = migration_failure(error, operation)
            elif operation in AGY_NODE_OPERATIONS and operation.removeprefix('agy-') in (
                    'preflight', 'fence', 'export', 'verify-import', 'prepare-import', 'activate-import', 'revoke-import', 'restore-source'):
                result['failure'] = migration_failure(error, operation.removeprefix('agy-'))
            return result

    @app.post('/operations/{operation}')
    async def operation_request(operation: str, request: Request):
        """认证后读取有界输入并将固定动作交给共享执行器。

        :param operation: 固定私有操作。
        :param request: 原UDS请求。
        :return: 脱敏失败或有限私有结果。
        """
        supplied = request.headers.get('x-v3-node-token', '')
        if not re.fullmatch('[a-f0-9]{64}', supplied) or not compare_digest(token, supplied):
            return JSONResponse({'ok': False, 'reason': 'node_authentication_failed'}, status_code=401)
        control = operation in AGY_NODE_SHORT or operation in DRAFT_LOGIN_SHORT_OPERATIONS or operation in ('health', 'grant-renew', 'grant-close', 'grant-get', 'terminal-get', 'terminal-input',
            'terminal-quota-state', 'terminal-verification-get', 'run-get', 'run-poll', 'run-quota-state', 'run-refresh-get',
            'continue-get', 'continue-input', 'continue-quota-state', 'credential-refresh-get', 'credential-status',
            'credential-material','credential-identity','credential-usage-get','credential-owner-get',
            'account-login-get','account-login-observe','account-login-code-receipt','account-login-snapshot','account-login-input','account-bound-identity',
            'account-bound-login-get','account-bound-login-observe','account-bound-login-code-receipt','account-bound-login-snapshot','account-bound-login-input')
        control = control or operation == 'platform-gate'
        selected = control_slots if control else slots
        if not selected.acquire(blocking=False):
            return JSONResponse({'ok': False, 'reason': 'node_busy'}, status_code=503)
        try:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                limit = 96 * 1024 if operation in ('terminal-quota-state', 'run-quota-state', 'continue-quota-state') else 16384 if control else 2 * 1024 * 1024
                if len(raw) > limit:
                    return JSONResponse({'ok': False, 'reason': 'node_request_too_large'}, status_code=413)
            operation_id = request.headers.get('x-v3-node-update-operation')
            epoch = request.headers.get('x-v3-node-update-epoch')
            continuation = (operation_id, epoch) if operation_id or epoch else None
            def admitted():
                with node_admission(operation, continuation):
                    return dispatch(operation, bytes(raw))
            try:
                result = await run_in_threadpool(admitted)
            except (RuntimeError, ValueError):
                return JSONResponse({'ok': False, 'reason': 'node_maintenance'}, status_code=503)
            return JSONResponse(result)
        finally:
            selected.release()

    @app.websocket('/continue-pty')
    @app.websocket('/account-login-pty')
    @app.websocket('/account-bound-login-pty')
    @app.websocket('/draft-login-pty')
    async def continue_pty(websocket: WebSocket):
        """独立认证后连接冻结续聊PTY，浏览器身份仍由中央持有。

        :param websocket: SSH转发的私有UDS连接。
        :return: None；错误只返回固定关闭原因。
        """
        supplied = websocket.headers.get('x-v3-node-token', '')
        if not re.fullmatch('[a-f0-9]{64}', supplied) or not compare_digest(token, supplied):
            await websocket.close(code=4401)
            return
        if not pty_slots.acquire(blocking=False):
            await websocket.close(code=1013)
            return
        try:
            with node_admission('node-pty', None):
                await websocket.accept()
                first = await asyncio.wait_for(websocket.receive_text(), timeout=10)
                model=DraftLoginScope if websocket.url.path=='/draft-login-pty' else ExecutionScope
                scope = model.model_validate(strict_json(first.encode(), 16384))
                actor={'/account-login-pty':logins,'/account-bound-login-pty':bound_logins,'/continue-pty':continues,
                    '/draft-login-pty':draft_logins}[websocket.url.path]
                await actor.serve(websocket, scope)
        except Exception as error:
            logging.getLogger(__name__).error('节点续聊PTY关闭 error_type=%s', type(error).__name__)
        finally:
            pty_slots.release()
            try:
                await websocket.close(code=1000)
            except Exception:
                # 连接可能先由中央或实际PTY关闭；持久执行仍由原停止协议收口。
                pass

    return app


@contextmanager
def _node_socket(data: Path):
    parent = data / 'node-agent'
    private_directory(parent)
    directory = directory_fd(parent)
    lock = None
    listener = None
    identity = None
    try:
        lock = os.open('service.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        metadata = os.fstat(lock)
        if not S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077 or metadata.st_nlink != 1:
            raise ValueError('节点服务生命周期锁无效')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            previous = os.stat('control.sock', dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            previous = None
        if previous is not None:
            if not S_ISSOCK(previous.st_mode) or previous.st_uid != os.geteuid() or previous.st_nlink != 1:
                raise ValueError('节点服务socket存在未知归属')
            # 已持有唯一生命周期锁，旧socket只可能属于原已退出进程。
            os.unlink('control.sock', dir_fd=directory)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(parent / 'control.sock'))
        os.chmod('control.sock', 0o600, dir_fd=directory, follow_symlinks=False)
        identity = os.stat('control.sock', dir_fd=directory, follow_symlinks=False)
        listener.listen(16)
        listener.setblocking(False)
        yield listener
    finally:
        if listener is not None:
            listener.close()
        if identity is not None:
            try:
                current = os.stat('control.sock', dir_fd=directory, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                    os.unlink('control.sock', dir_fd=directory)
            except FileNotFoundError:
                pass
        if lock is not None:
            os.close(lock)
        os.close(directory)


def main() -> None:
    """核验私有安装后启动唯一UDS服务，生命周期结束时收口实际作业。:return: None。"""
    client, host = None, None
    os.umask(0o077)
    try:
        data, node_key, deployment = Path(os.environ['BENCH_DATA']), os.environ['V3_NODE_KEY'], os.environ['V3_DEPLOYMENT_ID']
        initialize_node_private(data, node_key, deployment)
        with _node_socket(data) as listener:
            client = DockerClient.from_env()
            executor = NodeExecution(data, Path(os.environ['HOST_BENCH_DATA']), node_key, deployment, client)
            host = NodeRuntimeHost(executor)
            app = create_node_app(executor, host, os.environ['V3_INTERNAL_TOKEN'], os.environ['V3_RELEASE'])
            server = Server(Config(app, access_log=False, log_level='warning', limit_concurrency=16,
                ws_max_size=32768, ws_max_queue=4, ws_ping_interval=10, ws_ping_timeout=10,
                timeout_graceful_shutdown=125))
            server.run(sockets=[listener])
    except Exception as error:
        logging.getLogger(__name__).error('节点控制服务启动失败 error_type=%s', type(error).__name__)
        raise SystemExit(1) from None
    finally:
        if host is not None:
            host.close()
        if client is not None:
            client.close()


if __name__ == '__main__':
    main()
