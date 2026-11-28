"""平台更新管理桥和受证环境维护，宿主执行器拥有切换生命周期。"""
from __future__ import annotations

from system_update_connection import UnixUpdateConnection

import json
import os
import re
import secrets
from sqlite3 import Error as DatabaseError
from contextlib import ExitStack, contextmanager
from threading import Event, Thread
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from docker.errors import DockerException, NotFound
from starlette.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr
from typing import Literal

from account_isolation import ROLE_COLUMNS, ROLE_LABELS, role_container
from account_update_identity import configured_release, image_origin
from cpu_resources import read_resources, set_resources
from native_kernel_upgrade import migrate_records, pending_upgrade, validate_records
from native_sender import builtin_config
from runtime_files import atomic_json
from system_update_contract import MANIFEST_LIMIT, safe_read, strict_json, validate_operation
from system_update_gate import UPDATE_GATE
from system_update_rollout import read_rollout
from system_update_stopped import HOST_READ_PATH, stopped_environment
from cluster_migration_maintenance import paused_migration_lease
from cluster_store import ClusterStore


_PLATFORM_VERSION_FILE = Path(__file__).with_name('platform-version.json')


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
    prepared_operation_id: StrictStr | None = None


class UpdateControl(BaseModel):
    """取消／恢复时再次冻结现场版本。

    :param expected_revision: 当前现场版本。
    """
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictStr


class AccountUpdateRetry(UpdateControl):
    """重试当前已生效版本下的本机账号。@param environment_id 账号环境身份。"""

    environment_id: StrictStr


class ClusterUpdate(BaseModel):
    """已认证宿主的固定节点维护输入。:param operation_id: 原操作。:param epoch: 原代次。:param action: 固定动作。"""

    model_config = ConfigDict(extra='forbid')
    operation_id: StrictStr
    epoch: StrictStr
    action: Literal['prepare', 'status', 'rollback', 'resume', 'restore', 'cancel-preparation']
    target_release: StrictStr | None = None
    control_release: StrictStr | None = None
    control_image: StrictStr | None = None
    account_image: StrictStr | None = None
    account_release: StrictStr | None = None
    preserve_data: StrictBool = False


class EnvironmentUpdate(BaseModel):
    """独立更新服务对一个环境的受证动作。

    :param operation_id: 持久维护操作。
    :param epoch: 维护代次。
    :param environment_id: 精确环境身份。
    :param generation: 预期当前环境代次。
    :param action: inspect、rebuild、stop、restore、retire 或 rollout。
    :param allowed_image_ids: 原操作重建意图固化的镜像集合，用于部分恢复及回退收口。
    :param central_only: 沿已核对的中央快速换版范围执行。
    """
    model_config = ConfigDict(extra='forbid')
    operation_id: StrictStr
    epoch: StrictStr
    environment_id: StrictStr
    generation: StrictInt
    action: StrictStr
    allowed_image_ids: list[StrictStr] = []
    central_only: StrictBool = False


class RuntimeSnapshotInput(BaseModel):
    """受信更新器的环境快照范围。:param central_only: 中央本机范围。"""

    model_config = ConfigDict(extra='forbid')
    central_only: StrictBool = False
    control_only: StrictBool = False




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


def _rollout_environment(runtime, row: dict, account: dict | None) -> dict:
    """冻结控制切换所需的角色身份，工作活动交给账号更新。@param runtime 运行时。@param row 环境。@param account 本机账号。@return 可隔离的环境清单项。"""
    from agy_environment import lookup_environment

    item = {key: row.get(key) for key in ('environment_id', 'generation', 'state', 'name', 'account_id')}
    item.update(roles={}, origin=None, blockers=[])
    try:
        agy = lookup_environment(runtime, row['environment_id'])
        item['gateway_account_id'] = agy['gateway_account_id'] if agy else (account or {}).get('cc2api_account_id')
        if agy:
            item['platform'] = 'antigravity'
        if (guard := runtime.environment_lock(row['environment_id'])).acquire(blocking=False):
            try:
                for role, column in ROLE_COLUMNS.items():
                    if row.get(column):
                        container = role_container(runtime, row, role)
                        container.reload()
                        item['roles'][role] = {'id': container.id, 'image_id': container.attrs['Image'], 'state': container.status}
                if item['roles']:
                    item['origin'] = image_origin(runtime, row)
                elif row['state'] == 'stopped' and not agy and item['gateway_account_id'] is not None and row['generation'] > 0:
                    # 休眠账号不需要后台启动，原镜像证明仍可供首个获准请求核对。
                    try:
                        item['origin'] = image_origin(runtime, row)
                    except FileNotFoundError:
                        pass
            finally:
                guard.release()
        else:
            item['blockers'].append('环境正在维护，镜像归属待核对')
    except (OSError, ValueError, RuntimeError, DockerException):
        item['blockers'].append('账号角色或镜像归属待核对')
    return item


def runtime_snapshot(runtime, central_only: bool = False, control_only: bool = False) -> dict:
    """收集环境、实际进程及全部已有租约的只读排空证据。

    :param runtime: 已初始化 AccountRuntime。
    :param central_only: 只采集中央，本次快照仍检查中央所有活动。
    :param control_only: 快切仅冻结本机身份，活动账号随后独立处理。
    :return: 门禁及有限脱敏阻塞项。
    """
    gate = UPDATE_GATE.state()
    if control_only:
        # 节点转发只读中央归属。原网关关闭推理后，节点连接的收尾可留给原进程。
        gate = {**gate, 'active': gate.get('control_active', gate['active'])}
    elif central_only:
        gate = {**gate, 'active': gate.get('central_active', gate['active'])}
    if runtime is None:
        return {**gate, 'ready': False, 'environments': [], 'blockers': ['账号运行时未初始化']}
    connection = runtime.database()
    agy_assignments = {}
    agy_update_blockers = []
    try:
        rows = [dict(row) for row in connection.execute('SELECT * FROM account_environments ORDER BY environment_id')]
        accounts = {row['id']: dict(row) for row in connection.execute('SELECT * FROM accounts')}
        if ClusterStore.has_agy_nodes(connection):
            agy_assignments = {row['environment_id']: row for row in connection.execute(
                'SELECT p.environment_id,b.phase,b.account_id,n.kind FROM agy_node_assignments b '
                'JOIN platform_api_environments p ON p.gateway_account_id=b.account_id '
                "JOIN cluster_nodes n ON n.id=b.node_id WHERE n.kind='ssh' OR b.phase='retired'")}
            if connection.execute("SELECT 1 FROM agy_node_migrations WHERE phase NOT IN ('completed','cancelled')").fetchone():
                agy_update_blockers.append('请先完成或取消原 AGY 节点迁移，再更新平台')
    finally:
        connection.close()
    blockers = ['管理端仍有在途活动'] if gate['active'] else []
    environments = []
    locality = getattr(runtime, 'locality', None)
    service = getattr(runtime, 'cluster_service', None)
    node_rows = service.store.list() if service else []
    removed_drafts = service.store.removed_draft_environments() if service else set()
    node_removals = [{'name': row['name'], 'state': row['removal']['state']} for row in node_rows if row.get('removal')]
    for removal in node_removals if not control_only else ():
        action = '请在节点管理重试移除' if removal['state'] == 'needs_check' else '正在移除，请等待原操作完成'
        blockers.append(f"{removal['name']}：{action}")
    for row in rows:
        reasons = []
        item = {key: row.get(key) for key in ('environment_id', 'generation', 'state', 'name', 'account_id')}
        if row['state'] == 'retired' and row['account_id'] is None:
            # 已归档的工程环境仅保留历史身份，不应当作未保存的登录草稿处理。
            continue
        if assigned := agy_assignments.get(row['environment_id']):
            archived = (assigned['phase'] == 'retired' and row['state'] == 'stopped'
                and not any(row[column] for column in ROLE_COLUMNS.values()))
            if archived and assigned['kind'] == 'local':
                continue
            if not archived:
                # 快速控制切换也会改变归属读取和节点版本门禁，必须保留正在使用的原组件。
                reason = ('仍归属远程节点，请迁回本机后更新或回退平台' if assigned['kind'] == 'ssh'
                    else '已归档的本机环境仍有运行角色，请核对原删除操作')
                reasons = [f"AGY 账号 #{assigned['account_id']} {reason}"]
                agy_update_blockers.extend(reasons)
            environments.append({**item, 'platform': 'antigravity', 'gateway_account_id': assigned['account_id'],
                'node_kind': assigned['kind'], 'roles': {}, 'origin': None, 'blockers': reasons})
            continue
        if row['account_id'] is None and row['environment_id'] in removed_drafts:
            # 节点清理回执已证明原草稿的远端资料与组件收口，中央行继续保存历史引用。
            environments.append({**item, 'node_kind': 'ssh', 'roles': {}, 'origin': None, 'blockers': []})
            continue
        if locality is not None and not locality(row):
            if central_only:
                try:
                    # 只从本地分配表核对归属。新控制的版本门禁会隔离尚未换版的节点。
                    assignment = (service.store.assignment(row['account_id']) if row.get('account_id') is not None
                        else service.draft_node(environment_id=row['environment_id']))
                    if assignment and assignment.get('kind') == 'ssh':
                        continue
                except (ValueError, RuntimeError, AttributeError):
                    pass
            historical_blocker = None
            if (not control_only and gate.get('phase') == 'blocked' and gate.get('operation_id')
                    and gate['active'] == 0 and row['state'] == 'stopped'
                    and row['account_id'] is not None and row['account_id'] not in accounts
                    and any(row[column] for column in ROLE_COLUMNS.values())):
                try:
                    stopped = stopped_environment(runtime, row, gate, UPDATE_GATE.state,
                        lambda scope: updater_request('POST', HOST_READ_PATH, scope))
                except HTTPException as error:
                    historical_blocker = ('宿主尚未提供历史停止证据读取' if error.status_code == 404
                        else '宿主历史停止证据暂不可用')
                except (DatabaseError, DockerException, KeyError, OSError, ValueError):
                    historical_blocker = '历史停止环境的原归属、角色或在途证据待核对'
                else:
                    if not central_only or stopped['node_kind'] == 'local':
                        environments.append({**item, **stopped, 'gateway_account_id': None})
                    continue
            if central_only:
                if not control_only:
                    blockers.append(row['name'] + ': ' + (historical_blocker or '环境归属待核对'))
                continue
            if historical_blocker:
                environments.append({**item, 'roles': {}, 'origin': None, 'blockers': [historical_blocker]})
                blockers.append(row['name'] + ': ' + historical_blocker)
                continue
            try:
                if service is None or service.synchronization is None or accounts.get(row['account_id']) is None:
                    raise ValueError('远程维护尚未接入')
                item = service.synchronization.environment_snapshot(row, accounts[row['account_id']])
            except Exception:
                item.update(roles={}, origin=None, node_kind='ssh', blockers=['节点工作、连接或同步状态仍需核对'])
                blockers.append(row['name'] + ': 节点工作、连接或同步状态仍需核对')
            environments.append(item)
            continue
        if control_only:
            environments.append(_rollout_environment(runtime, row, accounts.get(row.get('account_id'))))
            continue
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
                from agy_environment import lookup_environment
                agy=lookup_environment(runtime,row['environment_id'])
                if agy:
                    item.update(platform='antigravity',gateway_account_id=agy['gateway_account_id'])
                    lease=runtime.gateway._request('GET',f"/admin/runtime/accounts/{agy['gateway_account_id']}/lease")
                    configuration=runtime.gateway._request('GET',f"/admin/runtime/accounts/{agy['gateway_account_id']}/config")
                    if lease.get('active') or lease.get('waiting') or lease.get('lease') or configuration.get('credential_state',{}).get('phase')!='ready':
                        reasons.append('AGY账号许可或凭据操作尚未收口')
                ownership = getattr(runtime, 'credential_ownership', None)
                if ownership and account:
                    record = ownership.state(account['id'])
                    if record and (record.get('phase') != 'ready' or record.get('refresh_pending') or record.get('gateway_refresh_pending')):
                        reasons.append('凭据交接或刷新结果尚未确认')
                if account and account.get('cc2api_account_id'):
                    item['gateway_account_id'] = account['cc2api_account_id']
                    lease = runtime.gateway._request('GET', f'/admin/runtime/accounts/{int(account["cc2api_account_id"])}/lease')
                    paused = paused_migration_lease(runtime.database, row, lease)
                    if paused is not None:
                        fence = strict_json((root / 'runtime/node-fence.json').read_bytes())
                        record = paused['record']
                        if any(fence.get(key) != value for key, value in {
                                'phase': 'fenced', 'operation_id': paused['operation_id'], 'node_key': 'local',
                                'environment_id': row['environment_id'], 'account_id': row['account_id'],
                                'generation': row['generation'], 'assignment_revision': record['source_revision']}.items()):
                            paused = None
                    if (lease.get('active') or lease.get('waiting') or lease.get('lease') or lease.get('holders')
                            or lease.get('importing') or lease.get('tui_pending') is True) and paused is None:
                        reasons.append('账号 API 或运行租约尚未收口')
                roles, image_ids = {}, set()
                for role, column in ROLE_COLUMNS.items():
                    if not row.get(column):
                        continue
                    container = role_container(runtime, row, role)
                    container.reload()
                    roles[role] = {'id': container.id, 'state': container.status, 'image_id': container.attrs['Image']}
                    if account and account.get('cc2api_account_id') and paused is not None:
                        state = container.attrs.get('State', {})
                        if state.get('Running') is not False or state.get('Pid') != 0:
                            reasons.append('原迁移源角色尚未确认停止')
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
                if not roles and row['state'] == 'stopped' and not agy and item.get('gateway_account_id') and row['generation'] > 0:
                    try:
                        item['origin'] = image_origin(runtime, row)
                    except FileNotFoundError:
                        pass
        except Exception:
            # 公开响应保留未知事实，不转发包含私有路径或凭据的底层异常。
            reasons.append('环境排空证据尚未完整核验')
        item['blockers'] = reasons
        blockers.extend(f'{row["name"]}: {reason}' for reason in reasons)
        environments.append(item)
    nodes = [row for row in node_rows if row['kind'] == 'ssh' and not row.get('removal')
        and ((row.get('preparation') or {}).get('release') or (row.get('preparation') or {}).get('current_release'))]
    scope = 'control' if control_only else 'central' if central_only else 'full'
    blockers = agy_update_blockers + blockers
    return {**gate, 'scope': scope, 'ready': gate['phase'] == 'blocked' and not blockers,
        'environments': environments, 'nodes': nodes, 'node_removals': node_removals, 'blockers': blockers[:256],
        'agy_update_blockers': agy_update_blockers[:3]}


def environment_sources(runtime, *, observe_remote: bool = True) -> list[dict]:
    """只读核对实际账号角色及镜像来源，用于更新页的环境分布。

    :param runtime: 当前账号运行时。
    :param observe_remote: 兼容入口可直接查看远程环境，分步更新使用节点自己的进度。
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
        locality = getattr(runtime, 'locality', None)
        if locality is not None and not locality(row):
            item.update(verified=False, node_kind='ssh', maintenance='节点自动同步')
            service = getattr(runtime, 'cluster_service', None)
            if observe_remote and service is not None and service.synchronization is not None:
                connection = runtime.database()
                try:
                    account = connection.execute('SELECT * FROM accounts WHERE id=?', (row['account_id'],)).fetchone()
                finally:
                    connection.close()
                try:
                    actual = service.synchronization.environment_snapshot(row, dict(account), quiescent=False)
                    item.update(verified=True, release=(actual.get('origin') or {}).get('release'),
                        running=any(role['state'] == 'running' for role in actual['roles'].values()), maintenance=None)
                except Exception:
                    item['maintenance'] = '节点同步状态需要核对'
            result.append(item)
            continue
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


def partial_restore_ready(runtime, row: dict, account: dict | None, allowed_image_ids: list[str], *,
                          lease_proof: dict | None = None, rolling: bool = False) -> None:
    """核验本操作造成的部分角色可安全收口，外来镜像和未知活动保持阻断。

    :param runtime: 原版运行时。
    :param row: 当前精确环境和代次。
    :param account: 原账号归属。
    :param allowed_image_ids: 宿主持久意图固定的原／候选真实镜像 ID。
    :param lease_proof: 本账号滚动持有的排他许可。
    :param rolling: 账号滚动在平台开放期间使用自己的活动登记。
    :return: None；证据异常拒绝恢复。
    """
    if (not 1 <= len(allowed_image_ids) <= 2 or any(not re.fullmatch(r'sha256:[a-f0-9]{64}', value) for value in allowed_image_ids)
            or (not rolling and UPDATE_GATE.state()['active']) or runtime.environment_jobs(row['environment_id'])):
        raise ValueError('部分恢复的来源或在途证明无效')
    root = runtime._root(row)
    if runtime._execution_records(row) or (root / 'runtime/execution.json').exists() or pending_upgrade(root):
        raise ValueError('部分恢复仍有持久执行或内核维护')
    if account and account.get('cc2api_account_id'):
        lease = runtime.gateway._request('GET', f'/admin/runtime/accounts/{int(account["cc2api_account_id"])}/lease')
        current = lease.get('lease')
        owned = lease_proof and current and all(current.get(key) == lease_proof[key] for key in ('owner', 'generation'))
        foreign = any(not owned or any(holder.get(key) != lease_proof[key] for key in ('owner', 'generation'))
            for holder in lease.get('holders', []))
        if lease.get('active') or foreign or lease.get('importing') or (current and not owned) or (lease.get('waiting') and not owned):
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


class AccountRolloutWaiting(ValueError):
    """账号当前有工作，保留原环境和准入。"""


class AccountRolloutWaitingForReceipt(AccountRolloutWaiting):
    """保留原工具轮，恢复后自动续办本账号。"""


@contextmanager
def _rollout_lease(runtime, gateway_id: int | None, owner: str):
    if gateway_id is None:
        yield None
        return
    path = f'/admin/runtime/accounts/{gateway_id}/lease'
    gateway = runtime.gateway
    snapshot = gateway._request('GET', path)
    previous = snapshot.get('lease')
    foreign = any(not previous or holder.get('owner') != owner or holder.get('generation') != previous['generation']
        for holder in snapshot.get('holders', []))
    if snapshot.get('active') or snapshot.get('importing') or foreign or (previous and previous['owner'] != owner):
        # 原回执仍在时登记专属续办。其他活动先结束也不会丢失本账号的自动重试。
        if snapshot.get('tui_pending') is True:
            raise AccountRolloutWaitingForReceipt()
        raise AccountRolloutWaiting()
    # 环境锁保证只有本次尝试能收回同一维护所有者。进程重启后租约会进入对账。
    if previous:
        gateway._request('POST', path, {'operation': 'release', 'owner': owner, 'generation': previous['generation']})
    if snapshot.get('tui_pending') is True:
        raise AccountRolloutWaitingForReceipt()
    if snapshot.get('waiting'):
        raise AccountRolloutWaiting()
    proof = gateway._request('POST', path, {'operation': 'prepare', 'owner': owner}).get('lease')
    if not proof or proof['owner'] != owner or not proof['exclusive']:
        raise AccountRolloutWaiting()
    identity = {'owner': owner, 'generation': proof['generation']}
    done, lost = Event(), Event()

    def renew() -> None:
        while not done.wait(10):
            try:
                gateway._request('POST', path, {'operation': 'heartbeat', **identity})
            except Exception:
                # 已过期的排他许可仍封住账号，重试将按同一所有者对账。
                lost.set()
                return

    heartbeat = Thread(target=renew, daemon=True, name='v3-update-account-lease')
    try:
        claimed = gateway._request('POST', path, {'operation': 'claim', **identity}).get('lease')
        if not claimed or claimed.get('phase') != 'claimed' or any(claimed.get(key) != value for key, value in identity.items()):
            raise AccountRolloutWaiting()
        heartbeat.start()
        yield identity
        if lost.is_set():
            raise ValueError('账号维护许可续期结果待核对')
    finally:
        done.set()
        if heartbeat.ident is not None:
            heartbeat.join()
        gateway._request('POST', path, {'operation': 'release', **identity})


def rollout_account(runtime, body: EnvironmentUpdate, record: dict) -> str:
    """以原身份与账号排他许可重建一个本机环境。@param runtime 当前运行时。@param body 冻结的环境范围。@param record 宿主授权。@return 单账号状态。"""
    from agy_environment import lookup_environment, stop_environment as stop_agy_environment, transport as agy_transport

    entry = record['environments'].get(body.environment_id)
    if not entry or entry['generation'] != body.generation:
        return 'needs_check'
    guard = runtime.environment_lock(body.environment_id)
    if not guard.acquire(blocking=False):
        return 'waiting'
    try:
        connection = runtime.database()
        try:
            stored = connection.execute('SELECT * FROM account_environments WHERE environment_id=?', (body.environment_id,)).fetchone()
            account = connection.execute('SELECT * FROM accounts WHERE id=?', (stored['account_id'],)).fetchone() if stored else None
        finally:
            connection.close()
        if not stored:
            return 'stopped'
        row, account = dict(stored), dict(account) if account else None
        if not runtime.owns_environment(row) or row['account_id'] != entry['account_id'] or (row['account_id'] is not None and not account):
            return 'needs_check'
        agy = lookup_environment(runtime, row['environment_id'])
        gateway_id = agy['gateway_account_id'] if agy else (account or {}).get('cc2api_account_id')
        if gateway_id != entry['gateway_account_id']:
            return 'needs_check'
        runtime._check_node_fence(row)
        if account and runtime.credential_ownership:
            runtime.credential_ownership.guard(account)

        checkpoint = runtime._root(row) / 'runtime/account-rollout.json'
        identity = {'operation_id': body.operation_id, 'environment_id': body.environment_id, 'original_generation': body.generation}
        try:
            attempt = strict_json(safe_read(checkpoint, private=True))
        except FileNotFoundError:
            attempt = None
        if attempt and any(attempt.get(key) != value for key, value in identity.items()):
            attempt = None
        previous_ids = entry['roles']
        target_image = record['target_image_id']
        if not attempt:
            if row['generation'] != body.generation:
                return 'needs_check'
            if row['state'] == 'stopped' or (account and not account['enabled']):
                return 'stopped'
            if (image_origin(runtime, row) != entry['origin']
                    or {role: row[column] for role, column in ROLE_COLUMNS.items()} != previous_ids):
                return 'needs_check'
            if row['state'] not in ('ready', 'cli_reconcile'):
                return 'needs_check'
        elif row['generation'] not in (attempt['generation'], attempt['next_generation']):
            return 'needs_check'
        if runtime.environment_jobs(body.environment_id):
            return 'waiting'

        owner = f'maintenance:system-update:{body.operation_id}:{body.environment_id}'
        with _rollout_lease(runtime, gateway_id, owner) as proof:
            binding = {'cc2api_account_id': gateway_id} if gateway_id is not None else None
            if gateway_id is not None:
                control = runtime.gateway._request('GET', f'/admin/accounts/{gateway_id}/work-control')
                configuration = runtime.gateway._request('GET', f'/admin/runtime/accounts/{gateway_id}/config')
                if not control['work_enabled'] or configuration['status'] != 'active':
                    return 'stopped'
                if agy and configuration.get('credential_state', {}).get('phase') != 'ready':
                    return 'waiting'
            if attempt and attempt.get('completed') and row['state'] == 'stopped':
                return 'stopped'
            if runtime._running_sender_active(row):
                return 'waiting'
            current_image = image_origin(runtime, row) if any(row.get(column) for column in ROLE_COLUMNS.values()) else None
            finished = bool(attempt and row['generation'] == attempt['next_generation'] and row['state'] == 'ready'
                and current_image and current_image['image_id'] == target_image)
            if not finished:
                partial_restore_ready(runtime, row, binding, [entry['origin']['image_id'], target_image], lease_proof=proof, rolling=True)
                if gateway_id is not None and not agy:
                    validate_records(runtime._root(row), gateway_id)
                resources = None if attempt else read_resources(runtime, row)
                cpus = attempt['cpus'] if attempt else resources['cpus']
                if resources and resources['persisted_cpus'] and any(value < 0.01 for value in cpus.values()):
                    raise ValueError('原环境实际 CPU 额度与已保存策略不符')
                with runtime.rollout_capacity(row):
                    attempt = {**identity, 'cpus': cpus, 'generation': row['generation'], 'next_generation': row['generation'] + 1}
                    atomic_json(checkpoint, attempt)
                    try:
                        if agy:
                            stop_agy_environment(runtime, row, remove=True)
                            agy_transport(runtime, gateway_id, system_maintenance=True, capacity_reserved=True)
                            row = lookup_environment(runtime, row['environment_id'])
                        else:
                            runtime._stop_environment(row, remove=True)
                            runtime._update(row, state='stopped')
                            if gateway_id is not None:
                                migrate_records(runtime._root(row), gateway_id)
                            row, _ = runtime.ensure(account, prepare_sender=gateway_id is not None, capacity_reserved=True)
                    except Exception:
                        runtime._update(row, state='reconcile')
                        raise
            if (row['state'] != 'ready' or row['generation'] != attempt['next_generation']
                    or image_origin(runtime, row)['image_id'] != target_image
                    or any(state != 'running' for state in runtime.role_status(row).values())):
                raise ValueError('新环境代次或实际组件未通过验收')
            cpus = attempt['cpus']
            if all(value >= 0.01 for value in cpus.values()):
                resources = read_resources(runtime, row)
                if resources['cpus'] != cpus:
                    set_resources(runtime, row, row['generation'], resources['revision'], cpus)
            atomic_json(checkpoint, {**attempt, 'completed': True})
        # 许可归还后保留无敏感字段的完成意图，重复回执可核对同一代次。
        return 'updated'
    finally:
        guard.release()


def system_updates_router(runtime_provider) -> APIRouter:
    """建立已鉴权管理桥的精确更新接口。

    :param runtime_provider: 当前 AccountRuntime 的延迟读取函数。
    :return: FastAPI 路由。
    """
    router = APIRouter()

    @router.get('/api/system-updates/version')
    def version(response: Response) -> dict:
        """读取当前控制镜像中的独立版本文件。

        :param response: 管理响应，禁止跨控制镜像缓存版本。
        :return: 规范平台版本或未知值。
        """
        response.headers['Cache-Control'] = 'no-store'
        try:
            value = strict_json(safe_read(_PLATFORM_VERSION_FILE, 1024), 1024)
        except (OSError, ValueError):
            # 独立启动和旧控制端可能缺少版本文件，保持未知值以兼容原管理入口。
            return {'version': None}
        current = value.get('version')
        valid = (set(value) == {'version'} and isinstance(current, str)
            and re.fullmatch(r'v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', current))
        return {'version': current if valid else None}

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
        current = updater_request('GET', '/status')
        return {**current, 'environments': environment_sources(runtime_provider(), observe_remote=not current.get('staged_updates'))}

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
                    value = validate_operation(body.model_dump(exclude_none=True))
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

    @router.post('/api/system-updates/operations/{operation_id}/retry-account', status_code=202)
    def retry_account(operation_id: str, body: AccountUpdateRetry):
        """重试单个账号的后台更新。@param operation_id 原操作。@param body 现场修订和环境 ID。@return 当前后台状态。"""
        if not re.fullmatch(r'[a-f0-9-]{36}', operation_id):
            raise HTTPException(400, '操作身份无效')
        return updater_request('POST', '/operations/' + operation_id + '/retry-account', body.model_dump())

    def internal_proof(request: Request) -> dict:
        expected = update_token()
        if not secrets.compare_digest(request.headers.get('x-v3-update-token', ''), expected):
            raise HTTPException(403, '更新服务证明无效')
        return UPDATE_GATE.state()

    @router.post('/internal/v3/system-updates/snapshot')
    def snapshot(request: Request, body: RuntimeSnapshotInput | None = None):
        """读取真实排空快照。:param request: 内部证明。:param body: 快照范围。@return 快照。"""
        internal_proof(request)
        if body and body.control_only:
            return runtime_snapshot(runtime_provider(), True, True)
        return runtime_snapshot(runtime_provider(), body.central_only if body else False)

    @router.post('/internal/v3/system-updates/nodes')
    def nodes(request: Request, body: ClusterUpdate) -> dict:
        """沿原内部认证协调同代节点备份与恢复。:param request: 原宿主证明。:param body: 固定范围。:return: 节点进度。"""
        gate = internal_proof(request)
        if gate.get('operation_id') != body.operation_id or gate.get('epoch') != body.epoch or gate.get('phase') != 'blocked':
            raise HTTPException(409, '节点平台维护操作或代次已变化')
        runtime = runtime_provider()
        service = getattr(runtime, 'cluster_service', None)
        if service is None:
            return {'nodes': []}
        try:
            return service.platform_nodes(body.model_dump())
        except (ValueError, RuntimeError):
            raise HTTPException(409, '节点平台维护仍需核对原任务') from None

    @router.post('/internal/v3/system-updates/environment')
    def environment(request: Request, body: EnvironmentUpdate):
        """只在同一维护操作下收口或重建环境。

        :param request: 独立更新服务证明。
        :param body: 具体身份、代次及动作。
        :return: 本环境的实际状态。
        """
        gate = internal_proof(request)
        if body.action == 'rollout':
            runtime = runtime_provider()
            if runtime is None or gate['phase'] != 'idle':
                raise HTTPException(409, '平台当前正在切换')
            try:
                with UPDATE_GATE.admission('job:local-system-rollout'):
                    record = read_rollout(Path(os.environ['V3_UPDATE_GATE_DIR']), runtime.deployment,
                        runtime.release_id, configured_release(runtime))
                    if not record or any(record.get(key) != getattr(body, key) for key in ('operation_id', 'epoch')):
                        raise HTTPException(409, '账号滚动更新归属已经变化')
                    state = rollout_account(runtime, body, record)
            except AccountRolloutWaitingForReceipt:
                return {'environment_id': body.environment_id, 'state': 'waiting', 'wait_reason': 'tui_receipt'}
            except AccountRolloutWaiting:
                state = 'waiting'
            except (OSError, ValueError, RuntimeError, DockerException):
                state = 'needs_check'
            return {'environment_id': body.environment_id, 'state': state}
        if gate.get('phase') != 'blocked' or gate.get('operation_id') != body.operation_id or gate.get('epoch') != body.epoch:
            raise HTTPException(409, '维护操作或代次已经变化')
        runtime = runtime_provider()
        evidence = runtime_snapshot(runtime, body.central_only)
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
        locality = getattr(runtime, 'locality', None)
        if locality is not None and (body.central_only or (account is None and row['account_id'] is not None)) and not locality(row):
            if body.central_only:
                raise HTTPException(409, '中央快速换版仅操作本机环境')
            raise HTTPException(409, '历史停止环境仅提供维护读取')
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
                from agy_environment import lookup_environment, stop_environment as stop_agy_environment, transport as agy_transport
                agy=lookup_environment(runtime,row['environment_id'])
                if account and dict(account).get('cc2api_account_id'):
                    validate_records(runtime._root(row), account['cc2api_account_id'])
                # 历史回退先由新解析器收口角色；retire 保留账号行及 HOME，随后由旧生命周期重建。
                remove=body.action in ('rebuild', 'restore', 'retire')
                if agy:
                    stop_agy_environment(runtime,row,remove=remove)
                else:
                    runtime._stop_environment(row, remove=remove)
                    runtime._update(row, state='stopped')
                if account and dict(account).get('cc2api_account_id'):
                    migrate_records(runtime._root(row), account['cc2api_account_id'])
                    if body.action == 'retire':
                        # 历史解析器只认识293根配置；目标生命周期随后按镜像能力补齐安装表。
                        path = runtime._sender_config(row)
                        if path.is_file():
                            config = json.loads(path.read_text())
                            config['native'] = builtin_config(config.get('native'), ('2.1.293',))
                            runtime._write_sender_config(row, config)
                if body.action in ('rebuild', 'restore'):
                    if agy:
                        agy_transport(runtime,agy['gateway_account_id'],system_maintenance=True)
                        row=lookup_environment(runtime,row['environment_id'])
                        return {'environment_id':row['environment_id'],'generation':row['generation'],'state':row['state'],'origin':image_origin(runtime,row)}
                    if not account:
                        raise HTTPException(409, '环境缺少原始账号归属')
                    row, _ = runtime.ensure(dict(account), prepare_sender=False)
        return {'environment_id': row['environment_id'], 'generation': row['generation'],
            'state': row['state'], 'origin': None if body.action == 'retire' else image_origin(runtime, row)}

    return router
