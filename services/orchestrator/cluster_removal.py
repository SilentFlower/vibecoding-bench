"""回收经过原 SSH 身份、安装标记及 Docker 归属核对的远程节点。"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import PurePosixPath

from docker.errors import NotFound
from docker.types import Mount

from cluster_deployment import node_container_name, node_network_name
from cluster_node_ops import NODE_COMPONENT_ORDER
from cluster_ssh import REMOVAL_FILES_SCRIPT
from project_library import digest_json


class NodeRemovalError(ValueError):
    """节点移除可公开的固定错误。"""


class NodeRemoval:
    """推进原节点的持久移除操作。:param node: 原 SSH 连接。:param docker: 同一宿主 Docker 客户端。:param deployment: 部署身份。:param removal: 持久移除记录。"""

    def __init__(self, node, docker, deployment: str, removal: dict) -> None:
        """冻结本次清理路径与归属。:return: 无。"""
        self.node, self.docker = node, docker
        self.root = PurePosixPath(node.config.data_root)
        self.owner = {'protocol': 1, 'deployment_id': deployment, 'node_key': node.node_key}
        self.labels = {'vibebench.product': 'v3', 'vibebench.deployment': deployment,
            'vibebench.cluster-node': node.node_key}
        self.network_name = node_network_name(deployment, node.node_key)
        self.control_name = node_container_name(deployment, node.node_key)
        self.helper_name = self.control_name + '-remove'
        self.helper_labels = {**self.labels, 'vibebench.role': 'node-removal',
            'vibebench.operation': removal['operation_id']}

    def _inventory(self, image: str | None) -> tuple[list, object | None, object | None]:
        roles, helper = [], None
        sources = set()
        for container in self.docker.containers.list(all=True):
            labels = container.labels
            mounts = container.attrs.get('Mounts', [])
            own = labels.get('vibebench.cluster-node') == self.node.node_key
            verifier = labels.get('vibebench.project-verifier') == 'native' and labels.get('vibebench.node-key') == self.node.node_key
            if container.name == self.helper_name:
                host = container.attrs.get('HostConfig') or {}
                if (image is None or any(labels.get(key) != value for key, value in self.helper_labels.items())
                        or container.attrs.get('Image') != image or host.get('NetworkMode') != 'none'
                        or host.get('ReadonlyRootfs') is not True or not self._mounted_at(mounts, '/node-data') or len(mounts) != 1):
                    raise NodeRemovalError('数据清理辅助组件的实际归属需要核对')
                helper = container
            elif verifier and labels.get('vibebench.verifier-root') == digest_json(str(self.root)):
                roles.append(('project-review', container))
            elif own and all(labels.get(key) == value for key, value in self.labels.items()):
                role = labels.get('vibebench.role')
                if role not in NODE_COMPONENT_ORDER or (role == 'node-control'
                        and (container.name != self.control_name or not self._mounted_at(mounts, '/data'))):
                    raise NodeRemovalError('节点的组件角色或数据挂载需要核对')
                roles.append((role, container))
            else:
                if own or verifier or container.name == self.control_name:
                    raise NodeRemovalError('节点容器的实际归属需要核对')
                for mount in mounts:
                    source = PurePosixPath(mount.get('Source') or '.')
                    if self.root == source or self.root in source.parents or source in self.root.parents:
                        raise NodeRemovalError('其他容器仍在使用节点数据目录，请先核对挂载')
                    if mount.get('Type') == 'bind' and source.is_absolute():
                        sources.add(str(source))
        if sources:
            verified = self.node.verify_removal_mounts(sorted(sources))
            if verified != {'ok': True}:
                raise NodeRemovalError(verified.get('error', '其他容器的实际挂载需要核对'))
        if sum(role == 'node-control' for role, _ in roles) > 1:
            raise NodeRemovalError('发现多个节点控制组件，请先核对归属')
        try:
            network = self.docker.networks.get(self.network_name)
        except NotFound:
            network = None
        if network is not None:
            labels = network.attrs.get('Labels') or {}
            if any(labels.get(key) != value for key, value in self.labels.items()):
                raise NodeRemovalError('节点网络归属需要核对')
            if set(network.attrs.get('Containers') or {}) - {container.id for _, container in roles}:
                raise NodeRemovalError('节点网络仍有其他容器连接，请先核对归属')
        return roles, network, helper

    def _mounted_at(self, mounts: list, destination: str) -> bool:
        bound = [mount for mount in mounts if mount.get('Destination') == destination]
        return (len(bound) == 1 and bound[0].get('Type') == 'bind'
            and bound[0].get('Source') == str(self.root) and bound[0].get('RW') is True)

    def _files(self, action: str, identity: dict | None = None) -> dict:
        result = self.node.removal_files(action, self.owner, identity)
        if 'error' in result:
            raise NodeRemovalError(result['error'])
        observed = result.get('identity')
        if (result.get('state') not in ('owned', 'absent', 'empty')
                or result['state'] == 'absent' and observed is not None
                or result['state'] != 'absent' and (not isinstance(observed, dict)
                    or set(observed) != {'device', 'inode'} or any(type(value) is not int or value < 0 for value in observed.values()))):
            raise NodeRemovalError('节点数据目录回执需要核对')
        return result

    def _helper_image(self, roles: list) -> str | None:
        control = next((container for role, container in roles if role == 'node-control'), None)
        reference = control.attrs['Image'] if control else os.environ.get('V3_CONTROL_IMAGE')
        if not reference:
            return None
        try:
            image = self.docker.images.get(reference)
        except NotFound:
            if control is None:
                return None
            raise NodeRemovalError('原节点控制镜像需要核对') from None
        labels = image.attrs.get('Config', {}).get('Labels') or {}
        if (not re.fullmatch('sha256:[a-f0-9]{64}', image.id) or labels.get('vibebench.product') != 'v3'
                or labels.get('vibebench.role') != 'control'):
            raise NodeRemovalError('原节点控制镜像的角色需要核对')
        return image.id

    @staticmethod
    def _stop(container) -> None:
        container.reload()
        if container.attrs['State'].get('Running') or container.attrs['State'].get('Restarting'):
            container.stop(timeout=5)
            container.reload()
        state = container.attrs['State']
        if state.get('Running') is not False or state.get('Restarting') or state.get('Pid') != 0:
            raise NodeRemovalError('节点组件尚未确认停止，请重试原移除')

    def _erase_with_helper(self, image: str, identity: dict, helper) -> None:
        if helper is None:
            payload = json.dumps({'action': 'erase', 'root': '/node-data', 'owner': self.owner,
                'proof': identity})
            helper = self.docker.containers.create(image, name=self.helper_name, labels=self.helper_labels,
                entrypoint='python3', command=['-c', REMOVAL_FILES_SCRIPT, payload], network_mode='none',
                user='0:0', read_only=True, mounts=[Mount('/node-data', str(self.root), 'bind', propagation='rprivate')],
                cap_drop=['ALL'], cap_add=['DAC_OVERRIDE'], security_opt=['no-new-privileges'])
        if helper.status == 'created':
            helper.start()
        while True:
            helper.reload()
            if helper.status not in ('running', 'created'):
                break
            time.sleep(0.5)
        exit_code = helper.attrs['State']['ExitCode']
        helper.remove()
        if exit_code != 0:
            raise NodeRemovalError('节点数据擦除中断，请核对目录和挂载后重试')

    def run(self, record: dict, installed: bool, checkpoint) -> None:
        """推进经过确认的会话，离线后使用原证明继续同一操作。:param record: 原操作。:param installed: 中央曾观察到组件安装。:param checkpoint: 同一操作的持久进度写入。:return: 远端清理已经核对。"""
        proof = record.get('proof')
        roles, network, helper = self._inventory(proof['image'] if proof else None)
        if proof is None:
            files = self._files('probe')
            if files['state'] != 'owned' and (installed or roles or network is not None):
                raise NodeRemovalError('原节点已安装或仍有组件，缺少原数据目录归属证明')
            proof = {'files': files, 'root': str(self.root), 'owner': self.owner,
                'image': self._helper_image(roles) if files['state'] == 'owned' else None}
            checkpoint(phase='retiring_components', proof=proof)
        elif proof['root'] != str(self.root) or proof['owner'] != self.owner:
            raise NodeRemovalError('原移除操作的节点或数据目录归属已变化')

        files = self._files('probe', proof['files']['identity'])
        if record['phase'] == 'retiring_components':
            if files != proof['files']:
                raise NodeRemovalError('组件停止前节点数据归属已变化')
            # 控制进程先退出，防止删除最后一个组件期间重建账号容器。
            for role, container in roles:
                if role == 'node-control':
                    self._stop(container)
            roles, network, _ = self._inventory(proof['image'])
            for _, container in sorted(roles, key=lambda item: NODE_COMPONENT_ORDER[item[0]]):
                self._stop(container)
                container.remove()
            if network is not None:
                network.remove()
            checkpoint(phase='clearing_data')

        roles, network, helper = self._inventory(proof['image'])
        if roles or network is not None:
            raise NodeRemovalError('原节点还有运行组件或网络，请核对后重试')
        if proof['files']['state'] == 'owned':
            if files['state'] == 'absent':
                raise NodeRemovalError('核对时原节点数据目录缺失，请恢复原目录定位')
            if helper is not None or files['state'] == 'owned':
                if proof['image']:
                    self._erase_with_helper(proof['image'], proof['files']['identity'], helper)
                else:
                    self._files('erase', proof['files']['identity'])
            expected = {'state': 'empty', 'identity': proof['files']['identity']}
        else:
            expected = proof['files']
        if self._files('probe', expected['identity']) != expected:
            raise NodeRemovalError('未确认原节点数据已清理，请重试原移除')
