"""原账号已删除时，只为同一平台维护代次核对历史停止环境。"""
from __future__ import annotations

import json
import os
import re
import secrets
from contextlib import closing
from pathlib import Path
from typing import Literal

from docker.errors import NotFound
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from account_isolation import ISOLATION_VERSION, ROLE_COLUMNS, ROLE_LABELS
from native_kernel_upgrade import pending_upgrade
from runtime_files import directory_fd
from system_update_contract import BUILD_RE, RELEASE_RE, SHA_RE, safe_read, strict_json


HOST_READ_PATH = '/maintenance/stopped-environment'


class _NodeObservation(BaseModel):
    """宿主在原维护门禁内取得的节点只读结果。"""

    model_config = ConfigDict(extra='forbid')
    engine_id: StrictStr = Field(min_length=1)
    operation_id: StrictStr
    epoch: StrictStr
    phase: Literal['blocked']
    directories: list[Literal['home', 'runtime', 'profile']]
    binding: tuple[StrictStr, StrictInt] | None
    jobs: StrictInt
    executions: StrictInt
    leases: StrictInt
    pending_receipts: StrictInt


class _ImageSelection(BaseModel):
    """宿主按信任根验签后选定的历史账号镜像。"""

    model_config = ConfigDict(extra='forbid')
    system_release: StrictStr = Field(pattern=f'^{RELEASE_RE.pattern}$')
    manifest_sha256: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    account_release: StrictStr = Field(pattern=f'^{BUILD_RE.pattern}$')
    registry_digest: StrictStr = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    config_digest: StrictStr = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    engine_digest: Literal['registry_digest', 'config_digest']

    def image_id(self) -> str:
        """取宿主预先核准的 Docker 摘要类型。@return 当前选择对应的完整镜像摘要。"""
        return self.registry_digest if self.engine_digest == 'registry_digest' else self.config_digest


class _HostEvidence(BaseModel):
    """仅经已有宿主认证 socket 接受的一次性读回。"""

    model_config = ConfigDict(extra='forbid')
    scope: dict
    nodes: dict[str, _NodeObservation]
    image: _ImageSelection | None


def _registration(runtime, row: dict) -> tuple[dict | None, list[dict]]:
    """读取同一 SQLite 快照中的原归属及竞争登记。"""
    environment, account = row['environment_id'], row['account_id']
    with closing(runtime.database()) as connection:
        connection.execute('BEGIN')
        stored = connection.execute('SELECT * FROM account_environments WHERE environment_id=?', (environment,)).fetchone()
        conflicts = (
            ('SELECT 1 FROM accounts WHERE id=? OR name=? COLLATE NOCASE OR profile_path=?',
                (account, row['name'], 'profiles/' + row['name'])),
            ('SELECT 1 FROM account_node_assignments WHERE account_id=?', (account,)),
            ('SELECT 1 FROM account_environments WHERE environment_id<>? AND name=? COLLATE NOCASE', (environment, row['name'])),
            ('SELECT 1 FROM node_executions WHERE account_id=? OR environment_id=?', (account, environment)),
            ('SELECT 1 FROM node_migrations WHERE account_id=?', (account,)),
            ('SELECT 1 FROM platform_api_environments WHERE environment_id=?', (environment,)),
        )
        if stored is None or dict(stored) != row or any(connection.execute(sql, args).fetchone() for sql, args in conflicts):
            raise ValueError('原登记或历史名称已变化')
        draft = connection.execute(
            'SELECT node_id,operation_id,phase,revision,saved_account_id FROM node_login_drafts WHERE environment_id=?',
            (environment,)).fetchone()
        nodes = [dict(node) for node in connection.execute('SELECT id,node_key,kind,revision FROM cluster_nodes '
            'WHERE deleted_at IS NULL ORDER BY id')]
        if [(node['node_key'], node['kind']) for node in nodes if node['kind'] == 'local'] != [('local', 'local')]:
            raise ValueError('中央节点登记待核对')
        if draft is not None and (draft['phase'] != 'closed' or type(draft['revision']) is not int or draft['revision'] <= 0
                or draft['saved_account_id'] not in (None, account)
                or not any(node['id'] == draft['node_id'] and node['kind'] == 'ssh' for node in nodes)):
            raise ValueError('原 SSH 草稿或所属节点待核对')
        return dict(draft) if draft is not None else None, nodes


def _is_directory(path: Path) -> bool:
    try:
        os.close(directory_fd(path))
    except FileNotFoundError:
        return False
    return True


def _local_files(runtime, row: dict, expected: set[str]) -> None:
    # 旧环境由 ID 定位。与之关联的 profile 仍使用冻结在账号环境行里的历史名。
    root = runtime.data / 'environments' / row['environment_id']
    directory = root / 'runtime'
    paths = {'profile': runtime.data / 'profiles' / row['name'], 'home': root / 'home', 'runtime': directory}
    present = {kind for kind, path in paths.items() if _is_directory(path)}
    if present != expected or _is_directory(root) != ('runtime' in expected):
        raise ValueError('中央原环境或历史 profile 待核对')
    if 'runtime' not in present:
        return
    markers = [directory / name for name in ('node-assignment.json', 'node-fence.json', 'node-migration-target.json',
        'execution.json', 'login-commit.json', 'credential-handoff.json')]
    markers.append(runtime.data / 'login-drafts' / (row['environment_id'] + '.json'))
    if any(path.exists() or path.is_symlink() for path in markers) or pending_upgrade(root):
        raise ValueError('中央历史环境仍有持久操作')
    executions = directory / 'executions'
    if _is_directory(executions):
        descriptor = directory_fd(executions)
        try:
            if os.listdir(descriptor):
                raise ValueError('中央历史环境仍有持久执行')
        finally:
            os.close(descriptor)
    binding = strict_json(safe_read(directory / 'sender' / 'sender.json')).get('binding')
    if (not isinstance(binding, dict) or binding.get('environment_id') != row['environment_id']
            or type(binding.get('generation')) is not int or binding['generation'] != row['generation']):
        raise ValueError('中央原 sender 绑定待核对')


def _roles(engine, deployment: str, environment: str, identifiers: dict, image: _ImageSelection | None) -> dict:
    actual = {item.id for item in engine.containers.list(all=True, filters={'label': [f'vibebench.environment={environment}']})}
    if actual != (set(identifiers.values()) if image is not None else set()):
        raise ValueError('存在额外或缺少的原角色')
    roles = {}
    for role, identifier in identifiers.items():
        try:
            container = engine.containers.get(identifier)
        except NotFound:
            if image is not None:
                raise
            continue
        if image is None:
            raise ValueError('无角色节点仍保留原容器')
        labels = {'vibebench.product': 'v3', 'vibebench.deployment': deployment,
            'vibebench.environment': environment, 'vibebench.role': ROLE_LABELS[role],
            'vibebench.isolation-version': str(ISOLATION_VERSION), 'vibebench.release': image.account_release}
        state = container.attrs['State']
        if (container.id != identifier or container.attrs['Image'] != image.image_id()
                or any(container.labels.get(key) != value for key, value in labels.items())
                or 'vibebench.cluster-node' in container.labels
                or state.get('Status') != 'exited' or state.get('Running') is not False
                or state.get('Restarting') is not False or type(state.get('Pid')) is not int or state['Pid'] != 0):
            raise ValueError('原角色身份、签发来源或实际退出状态待核对')
        roles[role] = {'id': container.id, 'state': state['Status'], 'image_id': container.attrs['Image']}
    return roles


def _admission(runtime, gate: dict, read_gate) -> None:
    keys = ('phase', 'operation_id', 'epoch')
    current = read_gate()
    gateway = runtime.gateway._request('GET', '/admin/runtime/system-update/status')
    if (any(value.get(key) != gate[key] for value in (current, gateway) for key in keys)
            or current.get('deployment') != runtime.deployment
            or any(type(value.get('active')) is not int or value['active'] != 0 for value in (current, gateway))
            or gateway.get('tui_tool_pending') is not False):
        raise ValueError('双端门禁、实际活动或工具回执待核对')


def stopped_environment(runtime, row: dict, gate: dict, read_gate, read_host) -> dict:
    """为维护快照核对已删除账号的停止环境。

    :param runtime: 中央账号运行时。
    :param row: 当前快照中的原环境行。
    :param gate: 实际已封闭门禁。
    :param read_gate: 同进程门禁重读。
    :param read_host: 已鉴权的宿主实时读回，按挑战返回冻结节点证据与已验签的原镜像选择。
    :return: 现有快照所需的角色与节点投影，未知事实由调用方保留原阻塞。
    """
    environment, name, generation, account = (row[key] for key in ('environment_id', 'name', 'generation', 'account_id'))
    identifiers = {role: row.get(column) for role, column in ROLE_COLUMNS.items()}
    if (gate['phase'] != 'blocked' or gate.get('deployment') != runtime.deployment or not gate.get('operation_id')
            or not gate.get('epoch') or row['state'] != 'stopped'
            or not isinstance(environment, str) or not re.fullmatch('[a-f0-9]{32}', environment)
            or not isinstance(name, str) or name in ('', '.', '..') or '/' in name or '\x00' in name
            or type(generation) is not int or generation <= 0 or type(account) is not int or account <= 0
            or any(not isinstance(value, str) or not SHA_RE.fullmatch(value) for value in identifiers.values())
            or len(set(identifiers.values())) != len(ROLE_COLUMNS)):
        raise ValueError('原停止环境范围待核对')
    guard = runtime.environment_lock(environment)
    if not guard.acquire(timeout=1):
        raise ValueError('原环境正在维护')
    try:
        _admission(runtime, gate, read_gate)
        if runtime.environment_jobs(environment):
            raise ValueError('原环境仍有作业')
        draft, nodes = frozen = _registration(runtime, row)
        owner = next(node['node_key'] for node in nodes if node['id'] == draft['node_id']) if draft else 'local'
        scope = {'deployment': runtime.deployment, 'operation_id': gate['operation_id'], 'epoch': gate['epoch'],
            'challenge': secrets.token_hex(16), 'environment_id': environment, 'account_id': account,
            'generation': generation, 'profile_name': name, 'role_ids': identifiers, 'draft': draft, 'nodes': nodes}
        evidence = _HostEvidence.model_validate(read_host(scope))
        if (json.dumps(evidence.scope, sort_keys=True) != json.dumps(scope, sort_keys=True)
                or set(evidence.nodes) != {node['node_key'] for node in nodes}
                or len({item.engine_id for item in evidence.nodes.values()}) != len(nodes)
                or (evidence.image is None) != bool(draft)):
            raise ValueError('宿主历史停止回执范围待核对')
        local_roles = {}
        for node in nodes:
            key = node['node_key']
            observed = evidence.nodes[key]
            directories = {'home', 'runtime', 'profile'} if key == owner else {'profile'} if key == 'local' else set()
            if (set(observed.directories) != directories or len(observed.directories) != len(directories)
                    or observed.binding != ((environment, generation) if key == owner else None)
                    or observed.operation_id != gate['operation_id'] or observed.epoch != gate['epoch']
                    or any(count != 0 for count in (observed.jobs, observed.executions, observed.leases, observed.pending_receipts))):
                raise ValueError('原节点资料、运行代次或在途活动待核对')
            engine = runtime.client if key == 'local' else runtime.cluster_service.docker(node['id'])
            if engine.info().get('ID') != observed.engine_id:
                raise ValueError('节点 Docker 实际身份待核对')
            roles = _roles(engine, runtime.deployment, environment, identifiers, evidence.image if key == 'local' else None)
            if key == 'local':
                _local_files(runtime, row, directories)
                local_roles = roles
        if _registration(runtime, row) != frozen or runtime.environment_jobs(environment):
            raise ValueError('读取期间原归属或环境作业变化')
        _admission(runtime, gate, read_gate)
        return {'node_kind': 'local' if draft is None else 'ssh', 'origin': None, 'roles': local_roles, 'blockers': []}
    finally:
        guard.release()
