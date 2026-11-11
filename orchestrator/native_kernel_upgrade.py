"""固定 293 请求内核的签名分发及单环境在线切换。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from native_sender import ASSET, SHA256, VERSION
from runtime_files import atomic_json

TAG = re.compile(r'v0\.1\.0-beta\.[1-9][0-9]{0,8}')
DIGEST = re.compile(r'[a-f0-9]{64}')
PUBLIC_KEY = re.compile(r'[a-f0-9]{64}')
SOURCE = '8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978'
REPOSITORY = 'https://github.com/SilentFlower/cc-runtime-bridge/releases/download'
DOWNLOAD_HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
PENDING = {'draining', 'switching', 'restoring', 'finishing', 'reconcile'}


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    """只跟随固定发布源的 HTTPS 附件跳转。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """核对下一跳地址并保留 urllib 的跳转次数限制。"""
        target = urlsplit(newurl)
        if target.scheme != 'https' or target.netloc not in DOWNLOAD_HOSTS:
            raise ValueError('内核下载跳转不在发布来源白名单')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url: str, path: Path, limit: int) -> None:
    deadline = time.monotonic() + 90
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), ReleaseRedirect())
    with opener.open(url, timeout=10) as response, path.open('xb') as output:
        total = 0
        while chunk := response.read1(65536):
            total += len(chunk)
            if total > limit or time.monotonic() >= deadline:
                raise ValueError('内核下载超过大小或时间限制')
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())


def _verify_manifest(folder: Path, release: str, key: str) -> dict:
    manifest = folder / 'runtime-release.json'
    signature = folder / 'runtime-release.sig'
    if manifest.stat().st_size > 4096 or signature.stat().st_size != 64:
        raise ValueError('内核发布清单或签名大小不符')
    with tempfile.TemporaryDirectory(prefix='v3-kernel-key-') as directory:
        public = Path(directory) / 'ed25519.der'
        # 原始 32 字节公钥转为 OpenSSL 所需的 Ed25519 SPKI。
        public.write_bytes(bytes.fromhex('302a300506032b6570032100' + key))
        checked = subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER',
            '-inkey', str(public), '-rawin', '-in', str(manifest), '-sigfile', str(signature)],
            capture_output=True, timeout=5)
    if checked.returncode:
        raise ValueError('内核发布签名无效')
    def unique_fields(items):
        result = dict(items)
        if len(result) != len(items):
            raise ValueError('内核发布清单存在重复字段')
        return result
    value = json.loads(manifest.read_bytes(), object_pairs_hook=unique_fields)
    exact = {'schema_version': 1, 'release': release, 'platform': 'linux-x64', 'asset': ASSET,
        'source_version': '2.1.293', 'source_sha256': SOURCE, 'worker_schema': 2,
        'raw_input_protocol': 1, 'resource_contract': 1}
    fields = set(exact) | {'launcher_sha256', 'launcher_bytes', 'image_sha256', 'image_bytes'}
    if not isinstance(value, dict) or set(value) != fields or any(
            type(value[k]) is not type(v) or value[k] != v for k, v in exact.items()):
        raise ValueError('内核发布平台、来源或协议不兼容')
    for name, limit in (('launcher', 27_933_052), ('image', 134_217_728)):
        sha, size = value[f'{name}_sha256'], value[f'{name}_bytes']
        if not isinstance(sha, str) or not DIGEST.fullmatch(sha) or type(size) is not int or not 0 < size <= limit:
            raise ValueError('内核制品身份字段无效')
    return value


def _verify_binary(path: Path, manifest: dict) -> None:
    with path.open('rb') as artifact:
        if os.fstat(artifact.fileno()).st_size != manifest['launcher_bytes'] or (
                hashlib.file_digest(artifact, 'sha256').hexdigest() != manifest['launcher_sha256']):
            raise ValueError('内核分发文件摘要或大小不符')


def stage_release(store: Path, release: str, key: str) -> dict:
    """下载并验证固定标签的制品，原子发布到 sender 只读目录。

    :param store: 部署私有制品目录。
    :param release: 精确 beta 标签。
    :param key: 部署固定 Ed25519 公钥。
    :return: 已验证的精确制品引用。
    """
    if not isinstance(release, str) or not TAG.fullmatch(release) or not PUBLIC_KEY.fullmatch(key):
        raise ValueError('内核版本或发布公钥无效')
    store.mkdir(mode=0o755, parents=True, exist_ok=True)
    # 已准备的标签也可离线核验；同标签出现多个摘要时保留现状。
    release_dir = store / release
    if release_dir.is_dir():
        candidates = [path for path in release_dir.iterdir() if DIGEST.fullmatch(path.name)]
        if len(candidates) > 1:
            raise ValueError('内核发布标签有多个摘要，需对账')
        if candidates:
            cached = candidates[0]
            manifest = _verify_manifest(cached, release, key)
            if manifest['launcher_sha256'] != cached.name or cached.name == SHA256:
                raise ValueError('已准备内核的精确身份不一致')
            _verify_binary(cached / ASSET, manifest)
            return {'release': release, 'launcher_sha256': cached.name}
    if shutil.disk_usage(store).free < 64 * 1024 * 1024:
        raise ValueError('准备内核需要至少 64 MiB 可用空间')
    with tempfile.TemporaryDirectory(dir=store, prefix='.download-') as temporary:
        folder = Path(temporary) / 'files'
        folder.mkdir(mode=0o700)
        for name, limit in (('runtime-release.json', 4096), ('runtime-release.sig', 64)):
            _download(f'{REPOSITORY}/{release}/{name}', folder / name, limit)
        manifest = _verify_manifest(folder, release, key)
        sha = manifest['launcher_sha256']
        reference = {'release': release, 'launcher_sha256': sha}
        if sha == SHA256:
            raise ValueError('候选与镜像内置内核字节相同')
        target = store / release / sha
        target.parent.mkdir(mode=0o755, exist_ok=True)
        if not target.exists():
            _download(f'{REPOSITORY}/{release}/{ASSET}', folder / ASSET, manifest['launcher_bytes'])
            _verify_binary(folder / ASSET, manifest)
            (folder / ASSET).chmod(0o555)
            for name in ('runtime-release.json', 'runtime-release.sig'):
                (folder / name).chmod(0o444)
            folder.chmod(0o755)
            try:
                folder.rename(target)
            except OSError:
                if not target.is_dir():
                    raise
            directory = os.open(target.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        if _verify_manifest(target, release, key) != manifest:
            raise ValueError('已发布目录与候选清单不一致')
        _verify_binary(target / ASSET, manifest)
        return reference


def _record(root: Path) -> Path:
    return root / 'runtime/native-kernel-upgrade.json'


def _load(root: Path) -> dict:
    path = _record(root)
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def pending_upgrade(root: Path) -> bool:
    """查询固定环境有无待处理的内核操作。"""
    return _load(root).get('state') in PENDING


def applied_kernel(root: Path, account_id: int) -> dict:
    """读取已提交的版本选择，供同账号 sender 重建时恢复。"""
    record = _load(root)
    if not record or record.get('account_id') != account_id:
        return {}
    if record.get('state') in PENDING:
        raise ValueError('请求内核升级尚待对账')
    return {key: record[key] for key in ('current', 'kernel_generation') if key in record}


def pilot_key(environment_id: str) -> str:
    """返回只对已配置灰度环境生效的部署信任根。"""
    value = os.environ.get('V3_NATIVE_RELEASE_PUBLIC_KEY', '')
    return value if PUBLIC_KEY.fullmatch(value) and environment_id == os.environ.get(
        'V3_NATIVE_RELEASE_PILOT_ENVIRONMENT') else ''


def _shown(reference: dict | None) -> dict:
    return reference if reference is not None else {'release': VERSION, 'launcher_sha256': SHA256}


def _revision(record: dict, row: dict) -> str:
    return f"{row['generation']}:{record.get('revision', 'initial')}"


def status(runtime, row: dict) -> dict | None:
    """显示本灰度环境的操作状态，不公开服务地址或凭据。"""
    if not pilot_key(row['environment_id']) or not row.get('sender_container_id'):
        return None
    value = _load(runtime._root(row))
    try:
        config = json.loads(runtime._sender_config(row).read_text())
        if not config.get('native') or (value and value.get('account_id') != config['binding']['account_id']):
            return None
    except (OSError, KeyError, ValueError):
        return None
    same_generation = value.get('binding_generation') == row['generation']
    return {'state': 'preparing' if value.get('preparing_release') else value.get('state', 'idle'),
        'preparing_release': value.get('preparing_release'), 'operation_id': value.get('operation_id'),
        'revision': _revision(value, row),
        'current': _shown(value.get('current')),
        'previous': _shown(value.get('previous')) if value.get('previous_available') else None,
        'prepared': value.get('prepared'), 'pid': value.get('pid') if same_generation else None,
        'image_sha256': value.get('image_sha256') if same_generation else None, 'error': value.get('prepare_error') or value.get('error'),
        'binding_generation': value.get('binding_generation')}


def _context(runtime, row: dict, account_id: int) -> dict:
    from account_isolation import role_container
    if row.get('state') not in ('ready', 'cli_reconcile'):
        raise ValueError('原生账号环境尚未就绪')
    sender = role_container(runtime, row, 'sender')
    sender.reload()
    if sender.status != 'running' or not any(m.get('Destination') == '/runtime-releases'
            and not m.get('RW') for m in sender.attrs.get('Mounts', [])):
        raise ValueError('发送器尚未启用只读内核版本目录')
    config = json.loads(runtime._sender_config(row).read_text())
    binding = config['binding']
    if (binding['account_id'] != account_id or binding['environment_id'] != row['environment_id']
            or binding['generation'] != row['generation'] or not config.get('native')):
        raise ValueError('原生发送器归属或配置已变化')
    return config


def run_upgrade(runtime, row: dict, account_id: int, operation: str,
                operation_id: str, release: str | None, expected_sha256: str | None, expected_revision: str) -> dict:
    """为固定账号执行准备、切换、回滚或中断对账。

    :param runtime: 当前 V3 运行时协调器。
    :param row: 环境与角色身份快照。
    :param account_id: 该环境唯一绑定的网关账号。
    :param operation: prepare、activate、rollback、recover。
    :param operation_id: 幂等请求 UUID。
    :param release: 准备或激活的精确标签。
    :param expected_sha256: 激活或回滚时，管理员确认的目标分发摘要。
    :param expected_revision: 管理端读取并确认的不可复用操作版本。
    :return: 操作完成后可显示的受限状态。
    """
    environment_id = row['environment_id']
    key = pilot_key(environment_id)
    if not key or not isinstance(operation_id, str) or str(uuid.UUID(operation_id)) != operation_id:
        raise ValueError('账号未启用灰度升级或操作标识无效')
    root = runtime._root(row)
    record_path = _record(root)
    lock = runtime.environment_lock(environment_id)
    lease_path = f'/admin/runtime/accounts/{account_id}/lease'
    request = runtime.gateway._request

    def save(**changes):
        record.update(changes)
        atomic_json(record_path, record)

    def owned(snapshot):
        lease = snapshot.get('lease')
        if not lease or lease.get('owner') != 'kernel:' + record['operation_id']:
            return None
        generation = record.get('lease_generation')
        if generation and lease.get('generation') != generation:
            return None
        return lease

    def check_revision():
        if expected_revision != _revision(record, row):
            raise ValueError('内核操作状态已变化，请刷新后确认')

    def lease_action(action):
        return request('POST', lease_path, {'operation': action, 'owner': 'kernel:' + record['operation_id'],
            'generation': record.get('lease_generation')})

    def probe(config, target, generation):
        config['native']['release'] = target
        config['native']['kernel_generation'] = generation
        runtime._write_sender_config(row, config)
        result = request('POST', f'/admin/runtime/accounts/{account_id}/native-kernel-probe',
            {'owner': 'kernel:' + record['operation_id'], 'lease_generation': record['lease_generation'],
             'binding': config['binding'], 'target': {'release': target, 'kernel_generation': generation}},
            timeout=115)
        if (result.get('state') != 'ready' or not result.get('pid') or result.get('release') != target
                or result.get('kernel_generation') != generation or result.get('account_id') != account_id
                or result.get('environment_id') != environment_id or result.get('generation') != row['generation']):
            raise ValueError('内核预热回执身份不一致')
        if not DIGEST.fullmatch(result.get('image_sha256') or ''):
            raise ValueError('缺少实际执行体核验回执')
        return {'pid': result['pid'], 'image_sha256': result['image_sha256']}

    if operation == 'prepare':
        if not isinstance(release, str) or not TAG.fullmatch(release):
            raise ValueError('内核版本标签无效')
        with lock:
            _context(runtime, row, account_id)
            record = _load(root)
            if record.get('prepare_operation_id') == operation_id:
                if record.get('prepare_requested') != release or record.get('prepare_revision') != expected_revision:
                    raise ValueError('重复准备标识与原请求不一致')
                return status(runtime, row)
            check_revision()
            if record.get('preparing_release') or record.get('state') in PENDING or record.get('account_id', account_id) != account_id:
                raise ValueError('已有内核操作待处理')
            save(account_id=account_id, prepare_operation_id=operation_id, preparing_release=release,
                prepare_requested=release, prepare_revision=expected_revision, revision=str(uuid.uuid4()), prepare_error=None)
        try:
            reference = stage_release(runtime.data / 'native-releases', release, key)
            with lock:
                _context(runtime, row, account_id)
                record = _load(root)
                if record.get('prepare_operation_id') != operation_id or record.get('preparing_release') != release:
                    raise ValueError('准备操作已改变，请刷新后重试')
                save(prepared=reference, preparing_release=None)
        except Exception:
            with lock:
                record = _load(root)
                if record.get('prepare_operation_id') == operation_id:
                    save(preparing_release=None, prepare_error='候选下载、校验或归属检查失败')
            raise
        return status(runtime, row)

    with lock:
        config = _context(runtime, row, account_id)
        record = _load(root)
        if record.get('account_id', account_id) != account_id:
            raise ValueError('内核操作绑定已变化')
        if operation == 'recover':
            check_revision()
            if record.get('state') not in PENDING:
                return status(runtime, row)
            if record.get('binding_generation') != row['generation']:
                raise ValueError('待对账操作与当前发送器代次不一致')
            if record.get('state') != 'reconcile':
                raise ValueError('操作正在执行或需重启对账')
            snapshot = request('GET', lease_path)
            lease = owned(snapshot)
            if snapshot.get('lease') and not lease:
                raise ValueError('门禁已由其他操作持有')
            if not lease and record.get('reconcile_from') == 'finishing':
                if (config['native'].get('release') != record.get('current')
                        or config['native'].get('kernel_generation') != record.get('kernel_generation')):
                    raise ValueError('提交记录和实际发送器选择不一致')
                save(state=record['finish_state'], revision=str(uuid.uuid4()))
                return status(runtime, row)
            if record.get('reconcile_from') == 'draining':
                if config['native'].get('release') != record.get('original'):
                    raise ValueError('排空阶段的内核选择已变化')
                # 排空阶段还没有写入候选，原租约即使过期也可按所有权直接释放。
                if lease:
                    save(lease_generation=lease['generation'])
                    lease_action('release')
                save(state='failed', revision=str(uuid.uuid4()), error='切换在排空阶段结束')
                return status(runtime, row)
            if not lease or snapshot.get('active') != 0 or runtime._sender_active(row) != 0:
                raise ValueError('账号门禁或请求状态待核对')
            save(state='restoring', revision=str(uuid.uuid4()), lease_generation=lease['generation'])
        else:
            if record.get('operation_id') == operation_id:
                if (record.get('operation') != operation or record.get('operation_revision') != expected_revision
                        or record.get('operation_release') != release
                        or _shown(record.get('target'))['launcher_sha256'] != expected_sha256):
                    raise ValueError('重复操作标识与原请求不一致')
                return status(runtime, row)
            check_revision()
            if record.get('preparing_release') or record.get('state') in PENDING:
                raise ValueError('已有内核操作待处理')
            if operation == 'activate':
                target = record.get('prepared')
                if not target or target['release'] != release:
                    raise ValueError('已准备的内核候选变化，请刷新后确认')
            elif operation == 'rollback' and record.get('previous_available'):
                target = record.get('previous')
            else:
                raise ValueError('内核操作不可用')
            if _shown(target)['launcher_sha256'] != expected_sha256:
                raise ValueError('目标内核摘要已变化，请刷新后确认')
            current = config['native'].get('release')
            if target == current or current != record.get('current'):
                raise ValueError('候选已生效或当前内核状态漂移')
            if target is not None:
                folder = runtime.data / 'native-releases' / target['release'] / target['launcher_sha256']
                manifest = _verify_manifest(folder, target['release'], key)
                if manifest['launcher_sha256'] != target['launcher_sha256']:
                    raise ValueError('内核候选已变化')
                _verify_binary(folder / ASSET, manifest)
            save(state='draining', operation_id=operation_id, operation=operation, account_id=account_id,
                operation_release=release, operation_revision=expected_revision, revision=str(uuid.uuid4()),
                binding_generation=row['generation'], original=current, target=target,
                prior_previous=record.get('previous'), prior_previous_available=record.get('previous_available', False),
                lease_generation=None, error=None)
            try:
                lease = owned(lease_action('prepare'))
                if not lease:
                    raise ValueError('未取得账号维护门禁')
                save(lease_generation=lease['generation'])
            except Exception:
                save(state='reconcile', reconcile_from='draining', error='维护门禁结果待核对')
                raise

    if operation != 'recover':
        try:
            deadline = time.monotonic() + 120
            while True:
                snapshot = request('GET', lease_path)
                if not owned(snapshot):
                    raise ValueError('账号维护门禁已变化')
                if snapshot.get('active') == 0 and runtime._sender_active(row) == 0:
                    lease_action('claim')
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('账号长流排空超时')
                if owned(snapshot)['expires_at'] < time.time() + 10:
                    lease_action('heartbeat')
                time.sleep(0.5)
        except Exception:
            with lock:
                try:
                    snapshot = request('GET', lease_path)
                    if owned(snapshot):
                        lease_action('release')
                    save(state='failed', error='排空失败，保留原内核')
                except Exception:
                    save(state='reconcile', reconcile_from='draining', error='排空门禁待核对')
            return status(runtime, row)

    with lock:
        original, target = record['original'], record['target']
        try:
            config = _context(runtime, row, account_id)
            if not owned(request('GET', lease_path)):
                raise ValueError('账号维护门禁已变化')
            if operation == 'recover':
                current_lease = owned(request('GET', lease_path))
                if not current_lease:
                    raise ValueError('账号维护门禁已变化')
                if current_lease.get('phase') == 'draining':
                    lease_action('claim')
                if record.get('reconcile_from') != 'finishing':
                    raise ValueError('执行中断，恢复原内核')
                # 先前已实际预热并提交选择，只补核执行体并完成释放。
                generation = record['kernel_generation']
                evidence = probe(config, record['current'], generation)
                finish = {'state': record['finish_state'], **evidence}
            else:
                save(state='switching')
                generation = record['operation_id']
                evidence = probe(config, target, generation)
                finish = {'state': 'active', 'current': target, 'previous': original,
                    'previous_available': True, 'kernel_generation': generation, 'error': None, **evidence}
        except Exception:
            try:
                if not owned(request('GET', lease_path)):
                    raise ValueError('账号维护门禁已变化')
                save(state='restoring')
                config = _context(runtime, row, account_id)
                generation = str(uuid.uuid4())
                evidence = probe(config, original, generation)
                finish = {'state': 'restored', 'current': original, 'kernel_generation': generation,
                    'previous': record.get('prior_previous'), 'previous_available': record.get('prior_previous_available', False),
                    'error': '候选未生效，已恢复原内核', **evidence}
            except Exception:
                save(state='reconcile', reconcile_from='restoring', error='恢复结果待核对，账号仍在维护')
                return status(runtime, row)
        # 先记下实测回执，再开放入场。中断后按门禁和回执决定收尾。
        final_state = finish.pop('state')
        save(**finish, state='finishing', finish_state=final_state)
        try:
            lease_action('release')
            save(state=final_state)
        except Exception:
            save(state='reconcile', reconcile_from='finishing', error='内核已就绪，门禁释放结果待核对')
        return status(runtime, row)


def recover_interrupted(root: Path) -> bool:
    """启动时识别未完成的操作，保留原门禁供明确对账。"""
    record = _load(root)
    phase = record.get('state')
    if record.get('preparing_release'):
        record.update(preparing_release=None, prepare_error='下载中断，可重新准备候选')
        atomic_json(_record(root), record)
    if phase in PENDING and phase != 'reconcile':
        atomic_json(_record(root), {**record, 'state': 'reconcile', 'reconcile_from': phase,
            'error': '内核升级中断，等待对账'})
    return phase in PENDING
