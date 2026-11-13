"""正式镜像与部署对象的命名，历史引用仅用于读取和回退。"""
import hashlib
import re


IMAGE_PREFIX = 'flower2api'
LEGACY_IMAGE_PREFIX = 'vibebench-v3'


def account_rebuild_required(before: dict, after: dict) -> bool:
    """判断账号内容或仓库族变化是否需要重建。

    :param before: 已验证的原账号组件。
    :param after: 已验证的目标账号组件。
    :return: 内容变化或仓库族变化时为真；同仓库仅标签变化可复用。
    """
    return (before['content_sha256'] != after['content_sha256']
        or before['reference'].rsplit(':', 1)[0] != after['reference'].rsplit(':', 1)[0])


def image_reference(role: str, release: str, *, namespace: str = '', legacy: bool = False) -> str:
    """生成精确角色和批次的镜像引用。

    :param role: control 或 account。
    :param release: 已冻结的构建批次。
    :param namespace: 空值表示本地镜像，正式仓库使用 ghcr.io/owner。
    :param legacy: 历史读取及回退使用原包名。
    :return: 带固定批次标签的完整镜像引用。
    """
    if role not in ('control', 'account') or not isinstance(release, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', release):
        raise ValueError('镜像角色或构建批次无效')
    if namespace and not re.fullmatch(r'ghcr.io/[a-z0-9][a-z0-9-]*', namespace):
        raise ValueError('镜像命名空间无效')
    prefix = LEGACY_IMAGE_PREFIX if legacy else IMAGE_PREFIX
    return (namespace + '/' if namespace else '') + f'{prefix}-{role}:v3-{release}'


def matches_image_reference(reference: str, role: str, release: str,
                            *, namespace: str = 'ghcr.io/silentflower') -> bool:
    """核对新旧精确镜像引用，保持角色与批次绑定。

    :param reference: 待核对的清单引用。
    :param role: 预期角色。
    :param release: 预期构建批次。
    :param namespace: 预期仓库命名空间。
    :return: 仅本角色、本批次的新旧正式名称为真。
    """
    return reference in (image_reference(role, release, namespace=namespace),
        image_reference(role, release, namespace=namespace, legacy=True))


def deployment_network_names(deployment: str) -> tuple[str, str]:
    """返回本部署的新网络名和历史网络名。

    :param deployment: 持久部署标识。
    :return: 按新名、旧名排序的精确网络名称。
    """
    if not isinstance(deployment, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,35}', deployment):
        raise ValueError('部署标识无效')
    return f'flower2api-{deployment}', f'vibebench-v3-{deployment}'


def account_container_prefix(deployment: str, *, legacy: bool = False) -> str:
    """生成账号角色共用的容器前缀。

    :param deployment: 持久部署标识。
    :param legacy: 仅用于核对历史容器的名称占用。
    :return: 后续拼接原环境 ID 的固定前缀。
    """
    deployment_network_names(deployment)
    digest = hashlib.sha256(deployment.encode()).hexdigest()[:12]
    # 新品牌较长；省略中间 account 段，使完整环境 ID 加 sender 后缀仍处于 63 字节内。
    return f'v3-{digest}-account-' if legacy else f'flower2api-{digest}-'
