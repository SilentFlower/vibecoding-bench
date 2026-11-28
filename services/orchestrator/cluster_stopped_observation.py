"""原 SSH 节点在本操作实际冻结时，读取历史环境资料、作业、租约及 Docker 身份。"""

from __future__ import annotations

import os
import re
from uuid import UUID

from docker.errors import NotFound
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from native_kernel_upgrade import pending_upgrade
from runtime_files import directory_fd
from system_update_contract import safe_read, strict_json
from system_update_gate import UPDATE_GATE


OPERATION = 'stopped-environment-observe'


class StoppedNodeRead(BaseModel):
    """只接受一个原环境和节点登记；请求中没有宿主路径、命令或临时地址。"""

    model_config = ConfigDict(extra='forbid')
    deployment: StrictStr = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,35}$')
    operation_id: StrictStr
    epoch: StrictStr
    challenge: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    node_key: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    node_id: StrictInt = Field(gt=0)
    node_revision: StrictInt = Field(gt=0)
    environment_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    generation: StrictInt = Field(gt=0)
    profile_name: StrictStr = Field(min_length=1, max_length=128)
    role_ids: dict[StrictStr, StrictStr]

    @field_validator('operation_id', 'epoch')
    @classmethod
    def uuid_text(cls, value: str) -> str:
        """核对原门禁 UUID。@param value 原字符串。@return 已校验的规范值。"""
        if str(UUID(value)) != value:
            raise ValueError('维护身份无效')
        return value

    @field_validator('profile_name')
    @classmethod
    def original_name(cls, value: str) -> str:
        """仅允许原 profile 的单个文件名。@param value 冻结名称。@return 原值。"""
        if value in ('.', '..') or '/' in value or '\\' in value or not value.isprintable():
            raise ValueError('历史 profile 名称无效')
        return value

    @field_validator('role_ids')
    @classmethod
    def original_roles(cls, values: dict) -> dict:
        """限制为原三角色的完整身份。@param values 三个角色映射。@return 原映射。"""
        if (
            set(values) != {'cli', 'network', 'sender'}
            or len(set(values.values())) != 3
            or any(not re.fullmatch('[a-f0-9]{64}', value) for value in values.values())
        ):
            raise ValueError('原三角色身份无效')
        return values


def require_node_gate(read: StoppedNodeRead) -> dict:
    """从当前进程的真实门禁确认维护代次。@param read 原请求。@return 本次实际门禁。"""
    state = UPDATE_GATE.state()
    if (
        state.get('deployment') != read.deployment
        or state.get('phase') != 'blocked'
        or state.get('epoch') != read.epoch
        or state.get('operation_id') != read.operation_id
        or type(state.get('active')) is not int
        or state['active'] != 0
    ):
        raise ValueError('节点未确认同代冻结或仍有活动')
    return state


def _directory(path):
    try:
        fd = directory_fd(path)
    except FileNotFoundError:
        return False
    os.close(fd)
    return True


def _files(data, read):
    root = data / 'environments' / read.environment_id
    directory = root / 'runtime'
    paths = {'home': root / 'home', 'runtime': directory, 'profile': data / 'profiles' / read.profile_name}
    present = [name for name, path in paths.items() if _directory(path)]
    if _directory(root) != ('runtime' in present) or ('runtime' in present) != ('home' in present):
        raise ValueError('节点原环境目录不完整')
    if 'runtime' not in present:
        return present, None, 0
    binding = strict_json(safe_read(directory / 'sender' / 'sender.json')).get('binding')
    if (
        not isinstance(binding, dict)
        or binding.get('environment_id') != read.environment_id
        or type(binding.get('generation')) is not int
        or binding['generation'] != read.generation
    ):
        raise ValueError('节点 sender 原环境或代次不符')
    # 只计执行文件，既有角色和目录始终保留。未知过渡标记不能作为停止证明。
    if pending_upgrade(root) or any(
        os.path.lexists(directory / name)
        for name in (
            'node-fence.json',
            'node-migration-target.json',
            'login-commit.json',
            'credential-handoff.json',
        )
    ):
        raise ValueError('节点环境仍有维护或交接')
    executions = int(os.path.lexists(directory / 'execution.json'))
    try:
        fd = directory_fd(directory / 'executions')
    except FileNotFoundError:
        pass
    else:
        try:
            executions += len(os.listdir(fd))
        finally:
            os.close(fd)
    return present, (read.environment_id, read.generation), executions


def _no_roles(engine, read):
    if engine.containers.list(all=True, filters={'label': 'vibebench.environment=' + read.environment_id}):
        raise ValueError('节点仍有该环境的角色')
    for identifier in read.role_ids.values():
        try:
            engine.containers.get(identifier)
        except NotFound:
            continue
        raise ValueError('节点仍有原角色引用对应的容器')


def node_observation(executor, host, grants, draft_grants, read: StoppedNodeRead) -> dict:
    """在原长驻节点内读取固定范围。@param executor 安装身份与 Docker。@param host 原运行时。@param grants 执行许可。@param draft_grants 草稿许可。@param read 冻结范围。@return 受限读回。"""
    if read.node_key != executor.node_key or read.deployment != executor.deployment:
        raise ValueError('原节点或部署身份不符')
    gate = require_node_gate(read)
    _no_roles(executor.client, read)
    engine = executor.client.info().get('ID')
    if not isinstance(engine, str) or not engine:
        raise ValueError('原 Docker 引擎缺少身份')
    directories, binding, executions = _files(executor.data, read)
    with host.lock:
        if host.closed or host.gateway.lease_mirror is None:
            raise ValueError('原节点作业登记尚未就绪')
        jobs = len(host.runtime.environment_jobs(read.environment_id)) if host.runtime is not None else 0
        mirror = host.gateway.lease_mirror
    with mirror.lock:
        held = {
            scope.operation_id
            for scope in mirror.scopes.values()
            if scope.environment_id == read.environment_id
        }
        held.update(grants.open_for_stopped_observation(read.environment_id))
    leases = len(held) + len(draft_grants.open_for_stopped_observation(read.environment_id))
    after = require_node_gate(read)
    if after.get('revision') != gate.get('revision'):
        raise ValueError('取证期间节点门禁有变化')
    return {
        'protocol': 1,
        'node_key': executor.node_key,
        'challenge': read.challenge,
        'environment_id': read.environment_id,
        'profile_name': read.profile_name,
        'generation': read.generation,
        'engine_id': engine,
        'directories': directories,
        'binding': binding,
        'jobs': jobs,
        'executions': executions,
        'leases': leases,
        **{k: after[k] for k in ('operation_id', 'epoch', 'phase')},
    }
