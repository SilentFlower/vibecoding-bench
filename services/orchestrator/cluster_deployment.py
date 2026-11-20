"""通过已认证 SSH Docker 通道安装同批节点私有执行组件。"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import tarfile
import time
from collections.abc import Iterator
from contextlib import closing

from docker import DockerClient
from docker.constants import DEFAULT_DATA_CHUNK_SIZE
from docker.errors import DockerException, NotFound
from docker.models.images import Image
from docker.utils import version_gte
from requests.exceptions import RequestException

from cluster_nodes import NodeConfiguration
from runtime_files import atomic_text
from system_update_contract import safe_read


class NodeImagePreparationError(ValueError):
    """携带可以公开的节点镜像准备失败阶段。"""


def _inspect_image(client: DockerClient, reference: str) -> Image:
    """读取镜像以及可用的平台清单。:param client: 当前Docker宿主。:param reference: 固定镜像引用。:return: 实际镜像记录。"""
    api = client.api
    if not version_gte(api.api_version, '1.48'):
        return client.images.get(reference)
    # SDK尚未暴露清单参数，沿其状态校验和镜像模型读取原Docker响应。
    with api._get(api._url('/images/{0}/json', reference), params={'manifests': 'true'}) as response:
        return client.images.prepare_model(api._result(response, True))


def _image_platform(attrs: dict) -> dict:
    """提取OCI平台。:param attrs: Docker镜像检查结果。:return: 系统、架构及实际变体。"""
    platform = {'os': attrs.get('Os'), 'architecture': attrs.get('Architecture')}
    if attrs.get('Variant'):
        platform['variant'] = attrs['Variant']
    return platform


def _has_image_content(attrs: dict) -> bool:
    """判断选中平台的实际内容是否到达。:param attrs: Docker镜像检查结果。:return: 配置与平台内容是否完整。"""
    platform = _image_platform(attrs)
    if not all(platform.values()) or (attrs.get('RootFS') or {}).get('Type') != 'layers':
        return False
    manifests = attrs.get('Manifests')
    if manifests is None:
        # 经典镜像存储没有独立索引，检查返回的配置与层登记来自实际镜像。
        return True
    return any(manifest.get('Available') is True
               and (manifest.get('ImageData') or {}).get('Platform') == platform
               for manifest in manifests)


def _export_image(client: DockerClient, reference: str, platform: dict | None) -> Iterator[bytes]:
    """逐块导出指定平台。:param client: 中央镜像宿主。:param reference: 固定镜像引用。:param platform: 可选OCI平台。:return: 归档字节迭代器。"""
    api = client.api
    if platform is None or not version_gte(api.api_version, '1.48'):
        with closing(api.get_image(reference)) as source:
            yield from source
        return
    # 仅导出实际选中的平台，避免镜像索引中的其他制品影响节点导入。
    with api._get(api._url('/images/{0}/get', reference), stream=True,
                  params={'platform': json.dumps(platform)}) as response:
        yield from api._stream_raw_result(response, DEFAULT_DATA_CHUNK_SIZE, False)


def _load_image(client: DockerClient, source: Iterator[bytes], platform: dict) -> Iterator[dict]:
    """逐块导入指定平台。:param client: 节点Docker宿主。:param source: 中央归档流。:param platform: 已核对OCI平台。:return: 导入进度迭代器。"""
    api = client.api
    if not version_gte(api.api_version, '1.48'):
        yield from api.load_image(source, quiet=True)
        return
    with api._post(api._url('/images/load'), data=source, stream=True,
                   params={'quiet': True, 'platform': json.dumps(platform)}) as response:
        api._raise_for_status(response)
        yield from api._stream_helper(response, decode=True)


class _ArchiveReader(io.RawIOBase):
    """把 Docker SDK 字节迭代器接入流式 tar 读取，避免缓存完整镜像。"""

    def __init__(self, source) -> None:
        """保存来源。:param source: 字节迭代器。:return: None。"""
        super().__init__()
        self.source, self.iterator, self.pending = source, iter(source), memoryview(b'')

    def readable(self) -> bool:
        """声明只读流。:return: True。"""
        return True

    def readinto(self, buffer) -> int:
        """按目标缓冲区大小逐块读取。:param buffer: 目标缓冲区。:return: 实际字节数。"""
        while not self.pending:
            chunk = next(self.iterator, None)
            if chunk is None:
                return 0
            self.pending = memoryview(chunk)
        length = min(len(buffer), len(self.pending))
        buffer[:length] = self.pending[:length]
        self.pending = self.pending[length:]
        return length

    def close(self) -> None:
        """释放原镜像响应及读取器。:return: None。"""
        if not self.closed:
            self.source.close()
        super().close()


def image_config_digest(client, reference: str, platform: dict | None = None) -> str:
    """从镜像归档原始配置计算跨 Docker daemon 稳定的身份。

    :param client: 对应宿主 Docker SDK 客户端。
    :param reference: 固定批次标签或精确镜像 ID。
    :param platform: 可选实际运行平台。
    :return: 绑定 rootfs 和运行配置的 SHA256。
    """
    configurations, manifests = {}, []
    source = _ArchiveReader(_export_image(client, reference, platform))
    try:
        with tarfile.open(fileobj=source, mode='r|') as archive:
            for member in archive:
                if not member.isfile() or member.size > 4 * 1024 * 1024:
                    continue
                if member.name == 'manifest.json':
                    manifests = json.load(archive.extractfile(member))
                elif member.name.endswith('.json') or member.name.startswith('blobs/sha256/'):
                    raw = archive.extractfile(member).read()
                    try:
                        value = json.loads(raw)
                    except (ValueError, UnicodeError):
                        continue
                    if isinstance(value, dict) and isinstance(value.get('rootfs'), dict) and 'architecture' in value:
                        configurations[member.name] = 'sha256:' + hashlib.sha256(raw).hexdigest()
        entries = [entry for entry in manifests if reference in (entry.get('RepoTags') or [])]
        if not entries and reference.startswith('sha256:') and len(manifests) == 1:
            entries = manifests
        if len(entries) != 1 or entries[0].get('Config') not in configurations:
            raise ValueError('节点镜像无法核对唯一的原始配置')
        return configurations[entries[0]['Config']]
    finally:
        source.close()


def node_container_name(deployment: str, node_key: str) -> str:
    """生成精确归属的私有控制容器名称。

    :param deployment: 部署身份。
    :param node_key: 节点身份。
    :return: 稳定名称。
    """
    return 'flower2api-node-' + hashlib.sha256((deployment + ':' + node_key).encode()).hexdigest()[:24]


def node_network_name(deployment: str, node_key: str) -> str:
    """生成固定节点的独立Docker网络名称。

    :param deployment: 已登记部署。
    :param node_key: 稳定节点身份。
    :return: 由组件安装和执行共同核对的网络名。
    """
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,35}', deployment) or not re.fullmatch('[a-f0-9]{32}', node_key):
        raise ValueError('节点网络归属无效')
    return 'flower2api-' + deployment + '-node-' + node_key[:12]


class NodeInstallationConfigurationError(ValueError):
    """节点安装所需的中央配置缺失，公开消息仅包含配置名。

    :param missing: 服务内部判定缺失的配置项名称。
    """

    def __init__(self, missing: list[str]) -> None:
        """构造可供管理员修复的固定提示。:param missing: 缺失配置名。:return: None。"""
        super().__init__('管理中心缺少节点安装配置：' + '、'.join(missing) + '；请按维护流程更新宿主部署模板并重建控制端')


class NodeDeployment:
    """同批镜像的节点安装器，不持有或分发中央管理员口令。

    :param service: 当前中央 ClusterService。
    :param deployment: 已验证部署身份。
    :param release: 控制镜像批次。
    :param control_image: 本机固定控制镜像引用。
    :param account_image: 本机固定账号镜像引用。
    """

    def __init__(self, service, deployment: str, release: str, control_image: str, account_image: str, *, account_release: str | None = None) -> None:
        """保存当前平台的固定交付引用。

        :param service: 节点服务。
        :param deployment: 部署身份。
        :param release: 批次。
        :param control_image: 控制镜像。
        :param account_image: 账号镜像。
        :return: None。
        """
        missing = [name for name, value in (('V3_DEPLOYMENT_ID', deployment), ('V3_RELEASE', release),
            ('V3_CONTROL_IMAGE', control_image), ('V3_ACCOUNT_IMAGE', account_image)) if not value]
        if missing:
            raise NodeInstallationConfigurationError(missing)
        if not re.fullmatch('[a-z0-9][a-z0-9-]{0,35}', deployment):
            raise ValueError('节点安装需要完整的当前平台镜像配置')
        self.service, self.deployment, self.release = service, deployment, release
        self.control_image, self.account_image = control_image, account_image
        self.account_release = account_release

    def prefetch_images(self, node) -> tuple[str, Image]:
        """核对并预取同批镜像。:param node: 已由节点作业核对的连接。:return: 账号批次和实际控制镜像。"""
        account_release = self.account_release or os.environ.get('V3_ACCOUNT_RELEASE') or self.release
        # 导入解包可能超过日常控制请求期限，使用独立客户端。
        transfer = DockerClient(base_url='unix://' + str(node.docker_socket()), version='auto', timeout=600)
        try:
            control = self._ensure_image(transfer, self.control_image, 'control', self.release)
            self._ensure_image(transfer, self.account_image, 'account', account_release)
            return account_release, control
        finally:
            transfer.close()

    def prepare(self, node_id: int, revision: int, *, prefetched: tuple[str, Image] | None = None) -> dict:
        """检查平台后流式交付镜像并创建私有控制容器。

        :param node_id: 管理员指定的节点。
        :param revision: 请求发起时节点版本。
        :param prefetched: 同一节点作业之前核验的镜像。
        :return: 本次安装回执。
        """
        row = self.service.store.get(node_id)
        if row['kind'] != 'ssh' or row['revision'] != revision:
            raise ValueError('节点配置已变化或当前不接受安装')
        node = self.service.connection(node_id)
        config = NodeConfiguration.model_validate(json.loads(row['config_json']))
        node.observe()
        node.bootstrap(self.deployment)
        account_release, control = prefetched or self.prefetch_images(node)
        # 首次创建容器可能超过日常查询期限；安装使用独立客户端，不延长共享控制请求。
        remote = DockerClient(base_url='unix://' + str(node.docker_socket()), version='auto', timeout=120)
        try:
            return self._prepare_control(remote, node, row, config, account_release, control)
        finally:
            remote.close()

    def _prepare_control(self, remote, node, row: dict, config: NodeConfiguration, account_release: str, control) -> dict:
        labels = {'vibebench.product': 'v3', 'vibebench.deployment': self.deployment,
            'vibebench.cluster-node': row['node_key']}
        network_name = node_network_name(self.deployment, row['node_key'])
        try:
            network = remote.networks.get(network_name)
            if any(network.attrs.get('Labels', {}).get(key) != value for key, value in labels.items()):
                raise ValueError('节点 Docker 网络已存在其他归属')
        except NotFound:
            network = remote.networks.create(network_name, driver='bridge', labels=labels, check_duplicate=True)
        name = node_container_name(self.deployment, row['node_key'])
        expected = {**labels, 'vibebench.role': 'node-control', 'vibebench.release': self.release}
        try:
            container = remote.containers.get(name)
        except NotFound:
            container = None
        if container is not None and container.labels.get('vibebench.release') != self.release:
            container.reload()
            if any(container.labels.get(key) != value for key,value in {**labels,'vibebench.role':'node-control'}.items()):
                raise ValueError('原节点控制容器归属不一致')
            mounts=[item for item in container.attrs.get('Mounts',[]) if item.get('Destination')=='/data']
            if len(mounts)!=1 or mounts[0].get('Source')!=config.data_root or mounts[0].get('RW') is not True:
                raise ValueError('原节点控制容器数据挂载不一致')
            running=remote.containers.list(filters={'label':[key+'='+value for key,value in labels.items()]})
            programs=remote.containers.list(filters={'label':['vibebench.project-verifier=native',
                'vibebench.node-key='+row['node_key']]})
            if container.status=='running' or running or programs:
                raise ValueError('节点升级需要先排空并停止本Node全部角色，请按集群升级操作单执行')
            # 管理员明确准备新批次时只替换已停止的控制实例；HOME及账号角色由原生命周期核验和重建。
            container.remove()
            container=None
        if container is None:
            token_path = node.private / 'execution-token'
            if not token_path.exists():
                atomic_text(token_path, secrets.token_hex(32))
            token = safe_read(token_path, 128, private=True).decode()
            if not re.fullmatch('[a-f0-9]{64}', token):
                raise ValueError('节点执行身份文件格式无效')
            environment = {key: os.environ[key] for key in (
                'V3_MAX_ACTIVE_ACCOUNTS', 'V3_ACCOUNT_CPUS', 'V3_ACCOUNT_CLI_CPUS', 'V3_ACCOUNT_SENDER_CPUS',
                'V3_ACCOUNT_NETWORK_CPUS', 'V3_ACCOUNT_MEMORY', 'V3_ACCOUNT_SWAP', 'V3_NATIVE_SENDER_MEMORY',
                'V3_NATIVE_CRIU', 'PER_ACCOUNT_CONCURRENCY') if key in os.environ}
            environment.update(V3_ROLE='node-control', V3_NODE_KEY=row['node_key'], V3_DEPLOYMENT_ID=self.deployment,
                V3_RELEASE=self.release, V3_ACCOUNT_RELEASE=account_release, V3_ACCOUNT_IMAGE=self.account_image,
                V3_NETWORK=network_name, V3_INTERNAL_TOKEN=token, BENCH_DATA='/data',
                HOST_BENCH_DATA=config.data_root, V3_UPDATE_GATE_DIR='/data/system-update-gate')
            container = remote.containers.run(self.control_image, name=name, detach=True, environment=environment,
                labels=expected, network=network.name, restart_policy={'Name': 'unless-stopped'},
                volumes={config.data_root: {'bind': '/data', 'mode': 'rw'},
                    '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'rw'}})
        container.reload()
        if any(container.labels.get(key) != value for key, value in expected.items()):
            raise ValueError('节点控制容器归属或发布身份不一致')
        if container.attrs.get('Image') != control.attrs['Id']:
            actual = remote.images.get(container.attrs['Image'])
            if image_config_digest(remote, actual.id) != image_config_digest(remote, self.control_image):
                raise ValueError('节点控制容器使用了不同的镜像内容')
        mounts = container.attrs.get('Mounts') or []
        data_mounts = [mount for mount in mounts if mount.get('Destination') == '/data']
        if len(data_mounts) != 1 or data_mounts[0].get('Source') != config.data_root or data_mounts[0].get('RW') is not True:
            raise ValueError('节点控制容器数据挂载不一致')
        if container.status != 'running':
            container.start()
            container.reload()
        if container.status != 'running':
            raise ValueError('节点控制容器未就绪')
        deadline = time.monotonic() + 10
        while True:
            try:
                health = node.agent_health(name)
                break
            except ValueError:
                if time.monotonic() >= deadline:
                    raise ValueError('节点控制进程未就绪，请核对安装目录与维护记录') from None
                time.sleep(0.2)
        if health != {'protocol': 1, 'node_key': row['node_key'], 'deployment': self.deployment,
                'release': self.release, 'state': 'ready'}:
            raise ValueError('节点控制进程的部署、发布或协议不一致')
        return {'node_id': row['id'], 'node_key': row['node_key'], 'revision': row['revision'],
            'container_name': name, 'container_id': container.id, 'protocol': 1, 'release': self.release,
            'state': 'prepared', 'account_reference': self.account_image, 'account_release': account_release,
            'account_image_id': remote.images.get(self.account_image).attrs['Id']}

    def _ensure_image(self, remote: DockerClient, reference: str, role: str, release: str) -> Image:
        """补齐并核验节点目标镜像。:param remote: 节点Docker宿主。:param reference: 固定镜像。:param role: 预期角色。:param release: 预期批次。:return: 可用于安装的远端镜像。"""
        local = self.service.local_client
        component = '控制' if role == 'control' else '账号'
        try:
            original = _inspect_image(local, reference)
        except (DockerException, RequestException) as error:
            raise NodeImagePreparationError(f'读取中央{component}镜像失败') from error
        expected = {'vibebench.product': 'v3', 'vibebench.role': role, 'vibebench.release': release}
        labels = (original.attrs.get('Config') or {}).get('Labels') or {}
        if not _has_image_content(original.attrs) or any(labels.get(key) != value for key, value in expected.items()):
            raise NodeImagePreparationError(f'中央{component}镜像内容或发布身份无效')
        platform = _image_platform(original.attrs)
        try:
            image = _inspect_image(remote, reference)
        except NotFound:
            image = None
        except (DockerException, RequestException) as error:
            raise NodeImagePreparationError(f'读取节点{component}镜像失败') from error

        if image is None or not _has_image_content(image.attrs):
            # 索引可以与中央同ID但缺失真实配置或层；归属不明的同名引用仍需核对。
            if image is not None and image.id != original.id:
                raise NodeImagePreparationError(f'节点{component}镜像的同名引用归属待核对')
            try:
                with closing(_export_image(local, reference, platform)) as source:
                    for progress in _load_image(remote, source, platform):
                        if progress.get('error') or progress.get('errorDetail'):
                            raise NodeImagePreparationError(f'节点{component}镜像导入失败')
            except (DockerException, RequestException) as error:
                raise NodeImagePreparationError(f'节点{component}镜像传输或导入失败') from error
            try:
                image = _inspect_image(remote, reference)
            except (DockerException, RequestException) as error:
                raise NodeImagePreparationError(f'节点{component}镜像导入后无法复核') from error
            if not _has_image_content(image.attrs):
                raise NodeImagePreparationError(f'节点{component}镜像导入后内容仍不完整')

        labels = (image.attrs.get('Config') or {}).get('Labels') or {}
        if (_image_platform(image.attrs) != platform or image.attrs.get('RootFS') != original.attrs.get('RootFS')
                or any(labels.get(key) != value for key, value in expected.items())):
            raise NodeImagePreparationError(f'节点存在不同内容的同名{component}镜像，请核对节点制品')
        if original.id != image.id:
            try:
                same_configuration = image_config_digest(local, reference, platform) == image_config_digest(remote, reference, platform)
            except (DockerException, RequestException, ValueError, tarfile.TarError) as error:
                raise NodeImagePreparationError(f'节点{component}镜像无法核对原始配置') from error
            if not same_configuration:
                raise NodeImagePreparationError(f'节点存在不同内容的同名{component}镜像，请核对节点制品')
        return image
