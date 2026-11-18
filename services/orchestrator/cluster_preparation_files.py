"""大profile通过固定私有文件准备账号，沿用原节点准备身份与生命周期。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from account_runtime import _read_json
from cluster_execution import NodeLocation, NodePreparation
from cluster_migration_profiles import PROFILE_NAMES, ProfileReference, read_profile
from runtime_files import atomic_json, private_directory


class PreparationFileScope(NodeLocation):
    """原账号准备操作的文件范围。:param operation_id: 本次准备。:param generation: 中央观察代次。"""

    operation_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    generation: StrictInt = Field(ge=0)


class PreparationFiles(BaseModel):
    """不含大profile正文的原节点准备输入。:param scope: 固定范围。:param preparation: 原投影。:param profiles: 精确文件引用。"""

    model_config = ConfigDict(extra='forbid')
    scope: PreparationFileScope
    preparation: NodePreparation
    profiles: dict[str, ProfileReference]


def _directory(executor, request: PreparationFiles):
    scope, preparation = request.scope, request.preparation
    if (scope.node_key != executor.node_key or preparation.node_key != scope.node_key
            or preparation.assignment_revision != scope.assignment_revision
            or preparation.account.get('id') != scope.account_id
            or preparation.environment.get('environment_id') != scope.environment_id
            or preparation.environment.get('generation') != scope.generation
            or preparation.profile_files or set(request.profiles) - set(PROFILE_NAMES)):
        raise ValueError('节点准备文件范围与原账号不一致')
    # 小控制投影沿原验证器核对；大文件按实际摘要读取，规模不再作为账号拒绝条件。
    executor._validate_preparation(preparation)
    directory = executor.data / 'node-preparations' / scope.operation_id / str(scope.account_id)
    private_directory(directory)
    marker = directory / 'scope.json'
    expected = {'protocol': 1, 'scope': scope.model_dump()}
    if marker.exists() or marker.is_symlink():
        if _read_json(marker) != expected:
            raise ValueError('节点准备文件属于其他操作')
    elif any(directory.iterdir()):
        raise ValueError('节点准备目录存在未知资料')
    else:
        atomic_json(marker, expected)
    return directory


def stage_preparation_files(executor, request: PreparationFiles) -> dict:
    """建立固定操作私有文件目录。:param executor: 原节点。:param request: 原准备范围。:return: 目录受理回执。"""
    with executor._locked(environment_id=request.scope.environment_id):
        _directory(executor, request)
    return {'protocol': 1, 'node_key': executor.node_key, 'staged': True}


def prepare_from_files(executor, request: PreparationFiles) -> dict:
    """读取完整profile后执行同一原准备器。:param executor: 原节点。:param request: 原文件引用。:return: 原准备回执。"""
    with executor._locked(environment_id=request.scope.environment_id):
        directory = _directory(executor, request)
        files = {name: read_profile(directory / ('profile-' + reference.sha256 + '.json'), reference)
            for name, reference in request.profiles.items()}
        preparation = request.preparation.model_copy(update={'profile_files': files})
        account_id, name, environment_id, remote_id = executor._validate_preparation(request.preparation)
        with executor._locked():
            return executor._prepare_locked(preparation, account_id, name, environment_id, remote_id)
