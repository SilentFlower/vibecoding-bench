"""按远程节点的换版证据回收无引用的旧发布镜像。"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

from docker.errors import NotFound

from cluster_deployment import node_container_name
from runtime_files import atomic_json
from runtime_names import matches_image_reference
from system_update_contract import safe_read
from system_update_gate import UPDATE_GATE


_IMAGE_ID = re.compile(r'sha256:[a-f0-9]{64}')
_JOB_FILE = re.compile(r'[a-f0-9]{32}\.json')


@dataclass(frozen=True)
class _Image:
    """原节点已使用的镜像身份。历史账号回执缺少 ID 时只用于保护。"""

    role: str
    reference: str
    release: str
    image_id: str | None


def _read(path: Path) -> dict:
    value = json.loads(safe_read(path, path.lstat().st_size, private=True))
    if not isinstance(value, dict):
        raise ValueError('节点维护记录格式无效')
    return value


def _image(role: str, reference: str, release: str, image_id: str | None) -> _Image:
    if not matches_image_reference(reference, role, release) or (
            image_id is not None and not _IMAGE_ID.fullmatch(image_id)):
        raise ValueError('节点发布镜像身份无效')
    return _Image(role, reference, release, image_id)


def _selection(container: dict, preparation: dict, release: str, expected_labels: dict) -> tuple[_Image, _Image]:
    config = container['Config']
    labels = config.get('Labels') or {}
    if (any(labels.get(key) != value for key, value in expected_labels.items())
            or labels.get('vibebench.release') != release):
        raise ValueError('节点原控制容器归属已变化')
    control = _image('control', config['Image'], release, container['Image'])
    environment = dict(item.split('=', 1) for item in (config.get('Env') or ()) if '=' in item)
    account_reference = environment['V3_ACCOUNT_IMAGE']
    account_release = environment.get('V3_ACCOUNT_RELEASE') or release
    account_id = None
    if preparation.get('account_reference') == account_reference and preparation.get('account_release') == account_release:
        account_id = preparation.get('account_image_id')
    return control, _image('account', account_reference, account_release, account_id)


def _history(directory: Path, job: dict, row: dict, labels: dict) -> list[tuple[_Image, _Image]]:
    config_sha = hashlib.sha256(row['config_json'].encode()).hexdigest()
    archives = sorted((path for path in directory.iterdir() if _JOB_FILE.fullmatch(path.name)),
                      key=lambda path: path.lstat().st_mtime_ns, reverse=True)
    selections = []
    for record in chain((job,), map(_read, archives)):
        if (record['phase'] != 'completed' or record['node_id'] != row['id']
                or record['node_key'] != row['node_key'] or record['config_sha256'] != config_sha):
            continue
        job_id = record['job_id']
        if not _JOB_FILE.fullmatch(job_id + '.json'):
            raise ValueError('节点维护作业身份无效')
        frozen = _read(directory / (job_id + '-container.json'))
        if frozen['Id'] != record['old_container'] or frozen['Image'] != record['old_image']:
            raise ValueError('节点换版前的容器身份不符')
        selections.append(_selection(frozen, record.get('preparation_before') or {}, record['old_release'], labels))
    return selections


def _candidate_references(remote, image: _Image) -> list[str] | None:
    try:
        actual = remote.images.get(image.image_id).attrs
    except NotFound:
        return []
    if not _matches_image(actual, image):
        return None
    tags = actual.get('RepoTags') or []
    digests = actual.get('RepoDigests') or []
    repository = image.reference.rsplit(':', 1)[0]
    if (any(tag != image.reference for tag in tags) or len(digests) > 1
            or any(repo != repository or not _IMAGE_ID.fullmatch(digest)
                   for repo, _, digest in (ref.partition('@') for ref in digests))):
        return None
    return tags + digests or None


def _matches_image(actual: dict, image: _Image) -> bool:
    labels = actual['Config'].get('Labels') or {}
    return ((image.image_id is None or actual['Id'] == image.image_id)
            and labels.get('vibebench.product') == 'v3' and labels.get('vibebench.role') == image.role
            and labels.get('vibebench.release') == image.release)


def _available(remote, image: _Image) -> bool:
    try:
        return _matches_image(remote.images.get(image.reference).attrs, image)
    except NotFound:
        return False


def _protected_images(remote, current: tuple[_Image, _Image], history: list[tuple[_Image, _Image]]) -> set[_Image]:
    protected = set(current)
    seen = {tuple(image.reference for image in current)}
    complete = 0
    for pair in history:
        key = tuple(image.reference for image in pair)
        if key in seen:
            continue
        seen.add(key)
        protected.update(pair)
        # 历史镜像可能已被手工删掉一半，仍要保留足够的完整回退组合。
        if all(_available(remote, image) for image in pair):
            complete += 1
            if complete == 2:
                break
    return protected


def _in_use(remote, image: _Image) -> bool:
    for container in remote.containers.list(all=True):
        attrs = container.attrs
        config = attrs['Config']
        if attrs['Image'] == image.image_id or config.get('Image') == image.reference:
            return True
        # 没有账号角色的控制端也可能已选定候选账号镜像。
        labels = config.get('Labels') or {}
        if labels.get('vibebench.product') == 'v3' and any(
                value in ('V3_ACCOUNT_IMAGE=' + image.reference, 'V3_CONTROL_IMAGE=' + image.reference)
                for value in (config.get('Env') or ())):
            return True
    return False


def _remove(remote, image: _Image, check_current) -> str:
    references = _candidate_references(remote, image)
    if references is None:
        return 'identity_or_alias_changed'
    if not references:
        return 'absent'
    for reference in references:
        if _in_use(remote, image):
            return 'referenced'
        current = _candidate_references(remote, image)
        if current is None or not set(current) <= set(references):
            return 'identity_or_alias_changed'
        if reference not in current:
            continue
        check_current()
        if remote.images.get(reference).id != image.image_id:
            return 'identity_or_alias_changed'
        remote.api.remove_image(reference, force=False, noprune=True)
    try:
        remote.images.get(image.image_id)
    except NotFound:
        return 'removed'
    raise RuntimeError('节点旧镜像回收尚未确认')


def _free_bytes(node) -> int | None:
    try:
        return node.observe()['disk_available_bytes']
    except (ValueError, OSError):
        return None


def cleanup_node_images(service, node_id: int, deployment: str, release: str) -> None:
    """核对已成功换版的节点并回收超出保留范围的旧镜像。

    :param service: 当前中央节点服务，调用方持有单节点操作锁和平台准入。
    :param node_id: 原已登记远程节点。
    :param deployment: 当前平台部署身份。
    :param release: 当前中央已部署控制批次。
    :return: 无；回执保存在节点私有维护目录。
    """
    row = service.store.get(node_id)
    preparation = json.loads(row['preparation_json'] or '{}')
    if preparation.get('state') != 'prepared' or preparation.get('release') != release:
        return
    node = service.connection(node_id)
    directory = node.private / 'maintenance'
    try:
        job = _read(directory / 'current.json')
    except FileNotFoundError:
        return
    if (job.get('phase') != 'completed' or job.get('target_release') != release or job.get('node_id') != node_id
            or job.get('node_key') != row['node_key']
            or job.get('config_sha256') != hashlib.sha256(row['config_json'].encode()).hexdigest()):
        return
    path = directory / 'image-cleanup.json'
    scope = {'job_id': job['job_id'], 'revision': row['revision'], 'container_id': preparation['container_id'], 'release': release}
    try:
        result = _read(path)
    except FileNotFoundError:
        result = {}
    if result.get('scope') != scope:
        result = {'scope': scope, 'outcomes': {}, 'state': 'pending'}
    if result['state'] == 'completed':
        return

    labels = {'vibebench.product': 'v3', 'vibebench.deployment': deployment,
              'vibebench.cluster-node': row['node_key'], 'vibebench.role': 'node-control'}
    name = node_container_name(deployment, row['node_key'])
    try:
        remote = service.docker(node_id)

        def check_current():
            fresh = service.store.get(node_id)
            if (UPDATE_GATE.state()['phase'] != 'idle' or service.closing
                    or any(fresh[key] != row[key] for key in ('node_key', 'revision', 'config_json', 'preparation_json'))):
                raise RuntimeError('节点或平台状态已变化')
            control = remote.containers.get(name)
            if control.id != preparation['container_id'] or control.status != 'running':
                raise RuntimeError('节点当前控制容器尚未就绪')
            return _selection(control.attrs, preparation, release, labels)

        current = check_current()
        if current[1].image_id is None or not _available(remote, current[1]):
            raise RuntimeError('节点当前账号镜像尚未核对')
        if node.agent_health(name) != {'protocol': 1, 'node_key': row['node_key'], 'deployment': deployment,
                                      'release': release, 'state': 'ready'}:
            raise RuntimeError('节点健康回执已变化')
        history = _history(directory, job, row, labels)
        protected = _protected_images(remote, current, history)
        protected_ids = {image.image_id for image in protected}
        protected_refs = {image.reference for image in protected}
        # 同一个账号镜像可以被多次换版复用。逐批保留时不能回收共享的原引用。
        candidates = {image.reference: image for pair in history for image in pair
                      if image.image_id and image.image_id not in protected_ids and image.reference not in protected_refs}
        present = set(remote.api.images(all=True, quiet=True)) if candidates else set()
        if candidates and 'before_free_bytes' not in result:
            result['before_free_bytes'] = _free_bytes(node)
        for reference, image in candidates.items():
            if result['outcomes'].get(reference) != 'removed':
                result['outcomes'][reference] = _remove(remote, image, check_current) if image.image_id in present else 'absent'
        if candidates:
            result['after_free_bytes'] = _free_bytes(node)
        result.update(state='completed', error_type=None)
    except Exception as error:
        # 镜像回收的错误不会进入原换版回退流程。下轮沿实际镜像状态重新核对。
        result.update(state='pending', error_type=type(error).__name__)
    result['updated_at'] = time.time()
    atomic_json(path, result)
