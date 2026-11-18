"""SSH Node 本机停机操作入口，安装与换批由中央节点准备负责。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from docker import DockerClient

from cluster_backup_index import cluster_backup_scope
from cluster_deployment import node_container_name
from project_library import digest_json


def node_action(data: Path, host_data: Path, action: str, *, release: str | None = None, client=None) -> dict:
    """核对安装与实际容器后执行一个明确的本机动作。

    :param data: 本进程可访问的 Node 数据根。
    :param host_data: 已登记的宿主数据根，容器挂载必须与其一致。
    :param action: check、status、stop 或 up。
    :param release: up 必须明确的控制批次。
    :param client: 可选的本机 Docker 客户端。
    :return: 仅含公开安装与容器定位的实际状态。
    """
    if action not in ('check', 'status', 'stop', 'up') or (action == 'up' and not release):
        raise ValueError('节点动作或目标批次无效')
    if not data.is_absolute() or data.resolve() != data or not host_data.is_absolute():
        raise ValueError('节点操作需要原规范绝对数据根')
    scope = cluster_backup_scope(data)
    if scope is None or scope['kind'] != 'node':
        raise ValueError('数据根缺少原 Node 安装归属')
    owns_client = client is None
    if client is None:
        client = DockerClient.from_env()
    labels = {'vibebench.product': 'v3', 'vibebench.deployment': scope['deployment_id'],
        'vibebench.cluster-node': scope['node_key']}
    order = {'project-review': 0, 'account': 1, 'account-sender': 2, 'account-network': 3, 'node-control': 4}
    try:
        containers = client.containers.list(all=True, filters={'label': [key + '=' + value for key, value in labels.items()]})
        programs = client.containers.list(all=True, filters={'label': ['vibebench.project-verifier=native',
            'vibebench.node-key=' + scope['node_key']]})
        controls, roles = [], {}
        for container in programs:
            container.reload()
            if (container.labels.get('vibebench.project-verifier') != 'native'
                    or container.labels.get('vibebench.node-key') != scope['node_key']
                    or container.labels.get('vibebench.verifier-root') != digest_json(str(host_data))):
                raise ValueError('独立验收容器的节点或数据归属需要核对')
            roles[container.id] = 'project-review'
        for container in containers:
            container.reload()
            if (any(container.labels.get(key) != value for key, value in labels.items())
                    or container.labels.get('vibebench.role') not in order):
                raise ValueError('节点容器存在未知归属或角色')
            roles[container.id] = container.labels['vibebench.role']
            if container.labels['vibebench.role'] == 'node-control':
                mounts = [item for item in container.attrs.get('Mounts', []) if item.get('Destination') == '/data']
                if (container.name != node_container_name(scope['deployment_id'], scope['node_key'])
                        or len(mounts) != 1 or mounts[0].get('Source') != str(host_data) or mounts[0].get('RW') is not True):
                    raise ValueError('节点控制实例名称或数据挂载需要核对')
                controls.append(container)
        containers = programs + containers
        if len(controls) > 1 or (action in ('check', 'up') and len(controls) != 1):
            raise ValueError('请先从中央节点页面准备唯一控制组件')
        if action == 'stop':
            # 先关账号执行与网络，再停控制进程；持久未决操作由原重启对账继续收口。
            for container in sorted(containers, key=lambda item: order[roles[item.id]]):
                container.stop(timeout=5)
                container.reload()
                state = container.attrs.get('State', {})
                if state.get('Running') is not False or state.get('Pid') != 0:
                    raise ValueError('节点角色实际停止仍需核对')
        if action == 'up':
            control = controls[0]
            if control.labels.get('vibebench.release') != release:
                raise ValueError('目标批次变化，请从中央节点页面准备同批组件')
            control.start()
            control.reload()
            if control.status != 'running':
                raise ValueError('节点控制实例尚未运行')
        return {**scope, 'containers': [{'id': item.id, 'role': roles[item.id],
            'state': item.status, 'release': item.labels.get('vibebench.release')} for item in containers]}
    finally:
        if owns_client:
            client.close()


def main() -> None:
    """读取明确 Node 动作及数据根并输出公开状态。:return: None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'status', 'stop', 'up'))
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--host-data-root', type=Path)
    parser.add_argument('--release')
    args = parser.parse_args()
    result = node_action(args.data_root, args.host_data_root or args.data_root, args.action, release=args.release)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
