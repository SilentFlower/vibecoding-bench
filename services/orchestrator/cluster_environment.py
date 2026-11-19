"""本机和SSH节点共用的源环境持久隔离与真实停止回执。"""
from __future__ import annotations

import time
import json
import os

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
from docker.errors import NotFound

from account_runtime import RuntimeBusy, _read_json
from native_kernel_upgrade import pending_upgrade
from cluster_owner_state import pending_owner_transition
from runtime_files import atomic_json, directory_fd


class EnvironmentFence(BaseModel):
    """中央冻结的源环境停止范围。

    :param operation_id: 迁移操作。
    :param node_key: 原人工归属节点。
    :param account_id: 原账号。
    :param environment_id: 固定环境。
    :param assignment_revision: 原分配版本。
    :param generation: 原环境代次。
    """

    model_config = ConfigDict(extra='forbid')
    operation_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    node_key: StrictStr = Field(pattern=r'^(local|[a-f0-9]{32})$')
    account_id: StrictInt = Field(ge=1)
    environment_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    assignment_revision: StrictInt = Field(ge=1)
    generation: StrictInt = Field(ge=0)


def fence_environment(runtime, row: dict, request: EnvironmentFence) -> dict:
    """在中央排空门禁及环境锁内停止原角色，持久拒绝旧源唤醒。

    :param runtime: 原节点的实际AccountRuntime。
    :param row: 原节点实际环境行。
    :param request: 中央按原分配冻结的身份。
    :return: 包含真实停止容器的隔离回执，未知或活动状态抛错保留现场。
    """
    if (request.node_key != (getattr(runtime, 'node_key', None) or 'local')
            or row['environment_id'] != request.environment_id or row['account_id'] != request.account_id
            or row['generation'] != request.generation):
        raise ValueError('源隔离环境身份或代次不一致')
    root = runtime._root(row)
    descriptor = directory_fd(root)
    os.close(descriptor)
    path = root / 'runtime/node-fence.json'
    identity = {'protocol': 1, **request.model_dump()}
    if path.exists() or path.is_symlink():
        previous = _read_json(path)
        cancelled = isinstance(previous, dict) and previous.get('phase') == 'cancelled'
        if cancelled and previous.get('operation_id') == request.operation_id:
            raise ValueError('原迁移操作已取消，拒绝迟到隔离请求')
        if (not isinstance(previous, dict) or not cancelled and (
                any(previous.get(key) != value for key, value in identity.items())
                or previous.get('phase') not in ('fencing', 'fenced'))):
            raise ValueError('源环境存在其他隔离操作，请核对原收据')
    ownership = None
    if request.node_key != 'local':
        ownership = _read_json(root / 'runtime/node-assignment.json')
        expected = {'protocol': 1, 'node_key': request.node_key, 'account_id': request.account_id,
            'environment_id': request.environment_id, 'revision': request.assignment_revision}
        if (not isinstance(ownership, dict) or any(ownership.get(key) != value for key, value in expected.items())
                or ownership.get('phase') not in ('ready', 'fencing', 'fenced')
                or ownership.get('phase') != 'ready' and ownership.get('operation_id') != request.operation_id):
            raise ValueError('源节点分配版本或隔离操作不一致')
    pending = [root / 'runtime' / name for name in ('execution.json', 'login-commit.json', 'credential-handoff.json')]
    pending.append(runtime.data / 'login-drafts' / (row['environment_id'] + '.json'))
    if (pending_owner_transition(root) or runtime.environment_jobs(row['environment_id']) or any(item.exists() or item.is_symlink() for item in pending)
            or runtime._execution_records(row) or runtime.reviews.serial_state(row) or pending_upgrade(root)):
        raise RuntimeBusy('源节点仍有执行、登录、凭据交接或内核维护记录，请先收口')
    runtime.reviews.check_orphans(row)
    if row.get('container_id'):
        try:
            cli = runtime._container(row)
        except NotFound:
            cli = None
        if cli is not None:
            cli.reload()
            if cli.status == 'running':
                observed = cli.exec_run(['python3', '-I', '/usr/local/bin/v3-cli-control', 'orphans'])
                if observed.exit_code or not isinstance(observed.output, bytes) or len(observed.output) > 65536:
                    raise ValueError('源CLI实际进程核对失败，请先对账')
                value = json.loads(observed.output)
                if not isinstance(value, dict) or value.get('orphans') != []:
                    raise RuntimeBusy('源CLI仍有未登记的实际进程，请先收口')
    if runtime._running_sender_active(row):
        raise RuntimeBusy('源发送器仍有活动请求，请等待原请求完成')
    # 隔离意图先于Docker停止持久化，崩溃后普通准备也会因该记录拒绝旧源唤醒。
    atomic_json(path, {**identity, 'phase': 'fencing'})
    if ownership is not None:
        atomic_json(root / 'runtime/node-assignment.json', {**ownership, 'phase': 'fencing', 'operation_id': request.operation_id})
    runtime._stop_environment(row)
    expected = runtime._labels(row)
    expected.pop('vibebench.role')
    stopped = []
    for container in runtime.client.containers.list(all=True, filters={'label': [key + '=' + value for key, value in expected.items()]}):
        if container.labels.get('vibebench.cluster-node') != getattr(runtime, 'node_key', None):
            continue
        container.reload()
        state = container.attrs.get('State', {})
        if (any(container.labels.get(key) != value for key, value in expected.items())
                or container.status not in ('exited', 'dead', 'created') or state.get('Running') is not False
                or state.get('Pid') != 0):
            raise ValueError('源角色停止结果尚未确认，请按原迁移操作核对')
        stopped.append(container.id)
    runtime._update(row, state='stopped')
    if ownership is not None:
        atomic_json(root / 'runtime/node-assignment.json', {**ownership, 'phase': 'fenced', 'operation_id': request.operation_id})
    result = {**identity, 'phase': 'fenced', 'stopped_containers': sorted(stopped), 'observed_at': time.time()}
    atomic_json(path, result)
    return result


def restore_fenced_source(runtime, row: dict, request: EnvironmentFence) -> dict:
    """按原隔离收据撤销提交前迁移，旧操作保留取消墓碑。

    :param runtime: 原节点运行时，中央已持有排他维护许可。
    :param row: 原实际环境，恢复阶段保持停止。
    :param request: 原迁移冻结范围。
    :return: 无执行唤醒的源恢复收据。
    """
    if (request.node_key != (getattr(runtime, 'node_key', None) or 'local')
            or row['account_id'] != request.account_id or row['environment_id'] != request.environment_id
            or row['generation'] != request.generation):
        raise ValueError('源恢复身份或代次不一致')
    root = runtime._root(row)
    path = root / 'runtime/node-fence.json'
    try:
        previous = _read_json(path)
    except FileNotFoundError:
        previous = None
    identity = {'protocol': 1, **request.model_dump()}
    if previous is None or isinstance(previous, dict) and previous.get('phase') == 'fencing':
        previous = fence_environment(runtime, row, request)
    if (not isinstance(previous, dict) or any(previous.get(key) != value for key, value in identity.items())
            or previous.get('phase') not in ('fenced', 'cancelled')):
        raise ValueError('源恢复缺少原操作的已停止隔离收据')
    if previous['phase'] == 'fenced':
        # 重复核对真实停止，取消不能把过期租约或旧磁盘收据当作当前进程已停止。
        fence_environment(runtime, row, request)
    if request.node_key != 'local':
        ownership_path = root / 'runtime/node-assignment.json'
        ownership = _read_json(ownership_path)
        expected = {'protocol': 1, 'node_key': request.node_key, 'account_id': request.account_id,
            'environment_id': request.environment_id, 'revision': request.assignment_revision}
        valid = (ownership == {**expected, 'phase': 'ready'} or
            ownership == {**expected, 'phase': 'fenced', 'operation_id': request.operation_id})
        if not valid:
            raise ValueError('源恢复分配版本或隔离阶段已变化')
        atomic_json(ownership_path, {**expected, 'phase': 'ready'})
    # 准入仍由中央maintenance关闭；先发布本机ready，再写墓碑，使中断重试仍可核对原fence。
    atomic_json(path, {**identity, 'phase': 'cancelled'})
    return {**identity, 'phase': 'restored'}
