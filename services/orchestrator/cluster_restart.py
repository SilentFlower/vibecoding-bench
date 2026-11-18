"""控制组件换批后恢复未变化的账号镜像，保留原角色和环境代次。"""
from __future__ import annotations

import os

from pydantic import Field, StrictStr

from account_isolation import ROLE_COLUMNS, role_container
from account_runtime import _read_json
from cli_scratchpad import restore_cli_scratchpad
from cluster_environment import EnvironmentFence
from cluster_execution import _GatewaySnapshot


class PreservedRestart(EnvironmentFence):
    """同一已撤销隔离下的原角色恢复。:param expected_image_id: 当前选定账号镜像的实际ID。"""

    expected_image_id: StrictStr = Field(pattern=r'^sha256:[a-f0-9]{64}$')


def restart_preserved(executor, request: PreservedRestart) -> dict:
    """核对原停止证明后恢复相同账号镜像。

    :param executor: 当前已核验节点执行器。
    :param request: 原操作、环境代次及所选实际镜像。
    :return: 是否复用及原环境；镜像变化交由原生命周期重建。
    """
    if request.node_key != executor.node_key:
        raise ValueError('原角色恢复节点不一致')
    selected = executor.client.images.get(os.environ['V3_ACCOUNT_IMAGE'])
    if selected.id != request.expected_image_id:
        raise ValueError('账号镜像选择已变化')
    with executor._locked(environment_id=request.environment_id):
        connection = executor.database()
        try:
            stored = connection.execute('SELECT * FROM account_environments WHERE account_id=? AND environment_id=?',
                (request.account_id, request.environment_id)).fetchone()
        finally:
            connection.close()
        if stored is None or stored['generation'] != request.generation:
            raise ValueError('原角色恢复代次已变化')
        row = dict(stored)
        runtime = executor._runtime(_GatewaySnapshot(0, {}))
        try:
            root = runtime._root(row)
            marker = _read_json(root / 'runtime/node-fence.json')
            scope = request.model_dump(exclude={'expected_image_id'})
            if marker != {'protocol': 1, **scope, 'phase': 'cancelled'}:
                raise ValueError('原角色恢复缺少同一操作停止及撤销证明')
            containers = {role: role_container(runtime, row, role) for role in ROLE_COLUMNS}
            if any(container.attrs['Image'] != selected.id for container in containers.values()):
                return {'protocol': 1, 'node_key': executor.node_key, 'reused': False}
            if runtime.environment_jobs(row['environment_id']) or runtime._execution_records(row):
                raise ValueError('原角色恢复仍有未知执行记录')
            try:
                for role in ('network', 'cli', 'sender'):
                    container = containers[role]
                    container.reload()
                    if container.status != 'running':
                        container.start()
                    if role == 'network':
                        runtime._wait_network(row)
                    elif role == 'cli':
                        restore_cli_scratchpad(runtime, row, container)
                    container.reload()
                    if container.status != 'running':
                        raise ValueError('原账号角色尚未恢复运行')
                runtime._update(row, state='ready')
            except Exception:
                runtime._stop_environment(row)
                runtime._update(row, state='stopped')
                raise
            return {'protocol': 1, 'node_key': executor.node_key, 'reused': True,
                'environment': {**row, 'state': 'ready'}}
        finally:
            executor._release_runtime(runtime)
