"""平台更新管理桥和受证环境维护，宿主执行器拥有切换生命周期。"""
from __future__ import annotations

from system_update_connection import UnixUpdateConnection

import json
import os
import re
import secrets
from contextlib import ExitStack
from http.client import HTTPConnection
from pathlib import Path
from socket import AF_UNIX, SOCK_STREAM, socket

from fastapi import APIRouter, HTTPException, Request
from docker.errors import NotFound
from starlette.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr

from account_isolation import ROLE_COLUMNS, ROLE_LABELS, role_container
from account_update_identity import image_origin
from native_kernel_upgrade import pending_upgrade
from system_update_contract import MANIFEST_LIMIT, safe_read, strict_json, validate_operation
from system_update_gate import UPDATE_GATE


class SystemUpdateAdmissionMiddleware:
    """在实际 ASGI 生命周期持有准入，流式正文和断连清理均参与排空。"""

    def __init__(self, app, runtime_provider) -> None:
        """绑定原应用和实际运行时。:param app: ASGI 应用。:param runtime_provider: 延迟读取。@return None。"""
        self.app = app
        self.runtime_provider = runtime_provider

    async def __call__(self, scope, receive, send) -> None:
        """直到响应结束才撤销活动。:param scope: 请求。:param receive: 输入。:param send: 输出。@return None。"""
        path = scope.get('path', '')
        if (scope['type'] != 'http' or not os.environ.get('V3_UPDATE_GATE_DIR')
                or scope['method'] in ('GET', 'HEAD', 'OPTIONS') or not path.startswith('/api/')
                or path.startswith('/api/system-updates/')):
            await self.app(scope, receive, send)
            return
        activity = UPDATE_GATE.admission('http:management')
        try:
            activity.__enter__()
        except RuntimeError:
            original = re.fullmatch(r'/api/accounts/login/([a-f0-9]{12})(?:/(?:code|commit))?', path)
            runtime = self.runtime_provider()
            identifier = None
            if original and runtime:
                with runtime.lock:
                    identifier = next((job.get('update_activity_id') for job in runtime.jobs.values()
                        if job.get('source') == 'login:' + original.group(1)), None)
            if not identifier:
                await JSONResponse(status_code=503, content={'detail': '平台正在维护，请稍后重试'},
                    headers={'Retry-After': '5'})(scope, receive, send)
                return
            activity = UPDATE_GATE.continue_reserved(identifier)
            try:
                activity.__enter__()
            except RuntimeError:
                await JSONResponse(status_code=409, content={'detail': '原登录活动已经结束，请刷新状态'})(scope, receive, send)
                return
        try:
            await self.app(scope, receive, send)
        finally:
            # 同一 ASGI 任务撤销 ContextVar，避免响应迭代器跨任务归还令牌。
            activity.__exit__(None, None, None)


class UpdateRequest(BaseModel):
    """冻结安装请求；额外字段及 bool 伪装整数均拒绝。

    :param operation_id: 本次唯一 UUID。
    :param expected_revision: 管理端展示的现场版本。
    :param target_release: 精确目标。
    :param target_manifest_sha256: 精确清单摘要。
    :param drain_timeout_seconds: 等待期限。
    """
    model_config = ConfigDict(extra='forbid')
    operation_id: StrictStr
    expected_revision: StrictStr
    target_release: StrictStr
    target_manifest_sha256: StrictStr
    drain_timeout_seconds: StrictInt = 60


class UpdateControl(BaseModel):
    """取消／恢复时再次冻结现场版本。

    :param expected_revision: 当前现场版本。
    """
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictStr


class EnvironmentUpdate(BaseModel):
    """独立更新服务对一个环境的受证动作。

    :param operation_id: 持久维护操作。
    :param epoch: 维护代次。
    :param environment_id: 精确环境身份。
    :param generation: 预期当前环境代次。
    :param action: inspect、rebuild、stop、restore 或 retire。
    :param allowed_image_ids: 原操作重建意图固化的镜像集合，用于部分恢复及回退收口。
    """
    model_config = ConfigDict(extra='forbid')
    operation_id: StrictStr
    epoch: StrictStr
    environment_id: StrictStr
    generation: StrictInt
    action: StrictStr
    allowed_image_ids: list[StrictStr] = []




def update_token() -> str:
    """读取独立更新凭据，保持浏览器不可见。

    :return: 固定 64 字符私有令牌。
    """
    path = os.environ.get('V3_UPDATE_SOCKET_DIR')
    if not path:
        raise RuntimeError('需要首次接入系统更新底座')
    value = safe_read(Path(path) / 'token', 128, private=True).decode().strip()
    if not re.fullmatch(r'[a-f0-9]{64}', value):
        raise ValueError('独立更新凭据无效')
    return value


def updater_request(method: str, path: str, body: dict | None = None) -> dict:
    """代理固定内部更新协议，限定响应大小和请求期限。

    :param method: 固定方法。
    :param path: 本模块生成的固定路径。
    :param body: 已验证 DTO。
    :return: 脱敏状态；冲突沿原状态码传递。
    """
    try:
        token = update_token()
        connection = UnixUpdateConnection(Path(os.environ['V3_UPDATE_SOCKET_DIR']) / 'updater.sock')
        try:
            connection.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            value = strict_json(response.read(MANIFEST_LIMIT + 1))
            if response.status >= 400:
                raise HTTPException(response.status, value.get('detail', '系统更新请求失败'))
            return value
        finally:
            connection.close()
    except (OSError, ValueError, RuntimeError) as error:
        raise HTTPException(503, '系统更新服务暂不可用，请核对首次接入状态') from error


def runtime_snapshot(runtime) -> dict:
    """收集环境、实际进程及全部已有租约的只读排空证据。

    :param runtime: 已初始化 AccountRuntime。
    :return: 门禁及有限脱敏阻塞项。
    """
    gate = UPDATE_GATE.state()
    if runtime is None:
        return {**gate, 'ready': False, 'environments': [], 'blockers': ['账号运行时未初始化']}
    connection = runtime.database()
    try:
        rows = [dict(row) for row in connection.execute('SELECT * FROM account_environments ORDER BY environment_id')]
        accounts = {row['id']: dict(row) for row in connection.execute('SELECT * FROM accounts')}
    finally:
        connection.close()
    blockers = ['管理端仍有在途活动'] if gate['active'] else []
    environments = []
    for row in rows:
        reasons = []
        item = {key: row.get(key) for key in ('environment_id', 'generation', 'state', 'name', 'account_id')}
        try:
            with ExitStack() as locks:
                guard = runtime.environment_lock(row['environment_id'])
                # 更新页只读轮询也使用此锁；有界等待其收口，持续生命周期占锁继续阻断维护。
                if not guard.acquire(timeout=1):
                    raise RuntimeError('环境生命周期仍在维护')
                locks.callback(guard.release)
                if runtime.environment_jobs(row['environment_id']):
                    reasons.append('CLI 或评审作业仍在运行')
                root = runtime._root(row)
                if runtime._execution_records(row) or (root / 'runtime/execution.json').exists():
                    reasons.append('持久执行登记尚未收口')
                if pending_upgrade(root):
                    reasons.append('请求内核维护尚未完成')
                account = accounts.get(row.get('account_id'))
                ownership = getattr(runtime, 'credential_ownership', None)
                if ownership and account:
                    record = ownership.state(account['id'])
                    if record and (record.get('phase') != 'ready' or record.get('refresh_pending') or record.get('gateway_refresh_pending')):
                        reasons.append('凭据交接或刷新结果尚未确认')
                if account and account.get('cc2api_account_id'):
                    lease = runtime.gateway._request('GET', f'/admin/runtime/accounts/{int(account["cc2api_account_id"])}/lease')
                    if lease.get('active') or lease.get('waiting') or lease.get('lease') or lease.get('holders'):
                        reasons.append('账号 API 或运行租约尚未收口')
                roles, image_ids = {}, set()
                for role, column in ROLE_COLUMNS.items():
                    if not row.get(column):
                        continue
                    container = role_container(runtime, row, role)
                    container.reload()
                    roles[role] = {'id': container.id, 'state': container.status, 'image_id': container.attrs['Image']}
                    image_ids.add(container.attrs['Image'])
                    if role == 'cli' and container.status == 'running' and not reasons:
                        result = container.exec_run(['python3', '-I', '/usr/local/bin/v3-cli-control', 'orphans'])
                        if result.exit_code or len(result.output) > 65536 or strict_json(result.output, 65536).get('orphans') != []:
                            reasons.append('实际 CLI 进程仍有活动或采集失败')
                if row.get('sender_container_id') and runtime._running_sender_active(row):
                    reasons.append('发送器仍有活动连接')
                if len(image_ids) > 1:
                    reasons.append('账号三角色镜像来源不一致')
                if len(roles) not in (0, 3):
                    reasons.append('账号三角色登记不完整')
                if row['state'] not in ('ready', 'cli_reconcile', 'stopped', 'retired'):
                    reasons.append('环境生命周期仍需对账')
                if not roles and row['state'] not in ('stopped', 'retired'):
                    reasons.append('环境缺少已确认的停止状态')
                item.update(roles=roles, origin=image_origin(runtime, row) if roles else None)
        except Exception:
            # 公开响应保留未知事实，不转发包含私有路径或凭据的底层异常。
            reasons.append('环境排空证据尚未完整核验')
        item['blockers'] = reasons
        blockers.extend(f'{row["name"]}: {reason}' for reason in reasons)
        environments.append(item)
    return {**gate, 'ready': gate['phase'] == 'blocked' and not blockers,
        'environments': environments, 'blockers': blockers[:256]}


def environment_sources(runtime) -> list[dict]:
    """只读核对实际账号角色及镜像来源，用于更新页的环境分布。

    :param runtime: 当前账号运行时。
    :return: 环境名称、实际来源、运行状态和核验结果。
    """
    if runtime is None:
        return []
    connection = runtime.database()
    try:
        rows = [dict(row) for row in connection.execute('SELECT * FROM account_environments ORDER BY name')]
    finally:
        connection.close()
    result = []
    for row in rows:
        item = {'environment_id': row['environment_id'], 'name': row['name'], 'release': None,
            'running': False, 'verified': True}
        guard = runtime.environment_lock(row['environment_id'])
        if not guard.acquire(blocking=False):
            item['verified'] = False
            result.append(item)
            continue
        try:
            roles = []
            for role, column in ROLE_COLUMNS.items():
                if row.get(column):
                    container = role_container(runtime, row, role)
                    container.reload()
                    roles.append(container.status)
            if roles:
                item['running'] = 'running' in roles
                if len(roles) != 3:
                    raise ValueError('账号角色登记不完整')
                item['release'] = image_origin(runtime, row)['release']
        except Exception:
            item['verified'] = False
        finally:
            guard.release()
        result.append(item)
    return result


def partial_restore_ready(runtime, row: dict, account: dict | None, allowed_image_ids: list[str]) -> None:
    """核验本操作造成的部分角色可安全收口，外来镜像和未知活动保持阻断。

    :param runtime: 原版运行时。
    :param row: 当前精确环境和代次。
    :param account: 原账号归属。
    :param allowed_image_ids: 宿主持久意图固定的原／候选真实镜像 ID。
    :return: None；证据异常拒绝恢复。
    """
    if (not 1 <= len(allowed_image_ids) <= 2 or any(not re.fullmatch(r'sha256:[a-f0-9]{64}', value) for value in allowed_image_ids)
            or UPDATE_GATE.state()['active'] or runtime.environment_jobs(row['environment_id'])):
        raise ValueError('部分恢复的来源或在途证明无效')
    root = runtime._root(row)
    if runtime._execution_records(row) or (root / 'runtime/execution.json').exists() or pending_upgrade(root):
        raise ValueError('部分恢复仍有持久执行或内核维护')
    if account and account.get('cc2api_account_id'):
        lease = runtime.gateway._request('GET', f'/admin/runtime/accounts/{int(account["cc2api_account_id"])}/lease')
        if lease.get('active') or lease.get('waiting') or lease.get('lease') or lease.get('holders'):
            raise ValueError('部分恢复仍有账号租约或 API 活动')
    registered = {row[column] for column in ROLE_COLUMNS.values() if row.get(column)}
    instances = runtime.client.containers.list(all=True, filters={'label': [
        'vibebench.product=v3', 'vibebench.deployment=' + runtime.deployment,
        'vibebench.environment=' + row['environment_id']]})
    if any(container.id not in registered or container.labels.get('vibebench.role') not in ROLE_LABELS.values() for container in instances):
        raise ValueError('部分恢复发现未登记角色，需要对账')
    for role, column in ROLE_COLUMNS.items():
        if not row.get(column):
            continue
        try:
            container = role_container(runtime, row, role, allow_old_release=True)
        except NotFound:
            continue
        container.reload()
        if container.attrs['Image'] not in allowed_image_ids:
            raise ValueError('部分恢复发现本操作以外的镜像')
        if role == 'cli' and container.status == 'running':
            result = container.exec_run(['python3', '-I', '/usr/local/bin/v3-cli-control', 'orphans'])
            if result.exit_code or len(result.output) > 65536 or strict_json(result.output, 65536).get('orphans') != []:
                raise ValueError('部分恢复存在实际 CLI 活动')
    if runtime._running_sender_active(row):
        raise ValueError('部分恢复存在发送器活动')


def system_updates_router(runtime_provider) -> APIRouter:
    """建立已鉴权管理桥的精确更新接口。

    :param runtime_provider: 当前 AccountRuntime 的延迟读取函数。
    :return: FastAPI 路由。
    """
    router = APIRouter()

    @router.post('/internal/v3/system-updates/admitted-control')
    async def admitted_control(body: dict):
        """核对原有限控制请求的实际登记，响应不包含活动内容。

        :param body: 私有 admission_id。
        :return: 原活动仍被持有时为 True。
        """
        if set(body) != {'admission_id'} or not isinstance(body['admission_id'], str) or not re.fullmatch(r'[a-f0-9]{32}', body['admission_id']):
            raise HTTPException(400, '原控制活动证明无效')
        with UPDATE_GATE.lock:
            return {'admitted': body['admission_id'] in UPDATE_GATE.active}

    @router.post('/internal/v3/system-updates/admitted')
    async def admitted(body: dict):
        """为原 CLI 作业提供实际登记证明，沿主中间件内部鉴权。

        :param body: account_id 和不可复用 owner。
        :return: 原作业仍在等待认领或执行时为 True。
        """
        if (set(body) != {'account_id', 'owner'} or type(body['account_id']) is not int
                or not isinstance(body['owner'], str) or not 1 <= len(body['owner']) <= 160):
            raise HTTPException(400, '原任务证明格式无效')
        runtime = runtime_provider()
        if runtime is None:
            return {'admitted': False}
        with runtime.lock:
            return {'admitted': any(job.get('source') == body['owner']
                and job.get('account', {}).get('cc2api_account_id') == body['account_id']
                and job.get('system_update_admitted') is True for job in runtime.jobs.values())}

    @router.get('/api/system-updates/status')
    def status():
        """读取更新能力及持久状态。@return 状态对象。"""
        if not os.environ.get('V3_UPDATE_SOCKET_DIR'):
            return {'installed': False, 'message': '需要首次接入系统更新底座'}
        return {**updater_request('GET', '/status'), 'environments': environment_sources(runtime_provider())}

    @router.get('/api/system-updates/releases')
    def releases():
        """读取已验证版本缓存。@return 版本目录。"""
        return updater_request('GET', '/releases')

    @router.post('/api/system-updates/check', status_code=202)
    def check():
        """异步检查受信版本。@return 检查身份。"""
        return updater_request('POST', '/check', {})

    for action in ('prepare', 'install', 'rollback'):
        def register(action_name):
            @router.post('/api/system-updates/' + action_name, status_code=202)
            def operate(body: UpdateRequest):
                """提交冻结版本操作。:param body: 严格请求。@return 操作状态。"""
                try:
                    value = validate_operation(body.model_dump())
                except ValueError as error:
                    raise HTTPException(400, str(error)) from error
                return updater_request('POST', '/' + action_name, value)
        register(action)

    @router.get('/api/system-updates/operations/{operation_id}')
    def operation(operation_id: str):
        """读取固定操作。:param operation_id: UUID。@return 操作状态。"""
        if not re.fullmatch(r'[a-f0-9-]{36}', operation_id):
            raise HTTPException(400, '操作身份无效')
        return updater_request('GET', '/operations/' + operation_id)

    for action in ('cancel', 'recover'):
        def register_control(action_name):
            @router.post('/api/system-updates/operations/{operation_id}/' + action_name, status_code=202)
            def control(operation_id: str, body: UpdateControl):
                """受控取消或恢复。:param operation_id: 原操作。:param body: 现场版本。@return 状态。"""
                if not re.fullmatch(r'[a-f0-9-]{36}', operation_id):
                    raise HTTPException(400, '操作身份无效')
                return updater_request('POST', '/operations/' + operation_id + '/' + action_name, body.model_dump())
        register_control(action)

    def internal_proof(request: Request) -> dict:
        expected = update_token()
        if not secrets.compare_digest(request.headers.get('x-v3-update-token', ''), expected):
            raise HTTPException(403, '更新服务证明无效')
        return UPDATE_GATE.state()

    @router.post('/internal/v3/system-updates/snapshot')
    def snapshot(request: Request):
        """读取真实排空快照。:param request: 内部证明。@return 快照。"""
        internal_proof(request)
        return runtime_snapshot(runtime_provider())

    @router.post('/internal/v3/system-updates/environment')
    def environment(request: Request, body: EnvironmentUpdate):
        """只在同一维护操作下收口或重建环境。

        :param request: 独立更新服务证明。
        :param body: 具体身份、代次及动作。
        :return: 本环境的实际状态。
        """
        gate = internal_proof(request)
        if gate.get('phase') != 'blocked' or gate.get('operation_id') != body.operation_id or gate.get('epoch') != body.epoch:
            raise HTTPException(409, '维护操作或代次已经变化')
        runtime = runtime_provider()
        evidence = runtime_snapshot(runtime)
        if body.action not in ('restore', 'retire') and not evidence['ready']:
            raise HTTPException(409, '平台在途工作尚未排空')
        if body.action not in ('inspect', 'rebuild', 'stop', 'restore', 'retire'):
            raise HTTPException(400, '环境维护动作无效')
        connection = runtime.database()
        try:
            stored = connection.execute('SELECT * FROM account_environments WHERE environment_id=?', (body.environment_id,)).fetchone()
            account = connection.execute('SELECT * FROM accounts WHERE id=?', (stored['account_id'],)).fetchone() if stored else None
        finally:
            connection.close()
        if not stored or stored['generation'] != body.generation:
            raise HTTPException(409, '环境身份或代次已经变化')
        row = dict(stored)
        with runtime.environment_lock(row['environment_id']):
            if body.action in ('restore', 'retire'):
                if evidence['active'] or (body.action == 'restore' and any(item['blockers']
                        for item in evidence['environments'] if item['environment_id'] != row['environment_id'])):
                    raise HTTPException(409, '其他环境仍有在途工作或未知证据')
                try:
                    partial_restore_ready(runtime, row, dict(account) if account else None, body.allowed_image_ids)
                except (OSError, ValueError) as error:
                    raise HTTPException(409, '部分角色恢复证据尚未完整核验') from error
            if body.action != 'inspect':
                # 历史回退先由新解析器收口角色；retire 保留账号行及 HOME，随后由旧生命周期重建。
                runtime._stop_environment(row, remove=body.action in ('rebuild', 'restore', 'retire'))
                runtime._update(row, state='stopped')
                if body.action in ('rebuild', 'restore'):
                    if not account:
                        raise HTTPException(409, '环境缺少原始账号归属')
                    row, _ = runtime.ensure(dict(account))
        return {'environment_id': row['environment_id'], 'generation': row['generation'],
            'state': row['state'], 'origin': None if body.action == 'retire' else image_origin(runtime, row)}

    return router
