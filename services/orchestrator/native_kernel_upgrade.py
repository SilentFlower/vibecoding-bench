"""平台内置内核的只读信息和历史独立选择迁移。"""
from __future__ import annotations

import json
from pathlib import Path

from native_sender import SHA256, SHA256_280, VERSION, VERSION_280, builtin_config, installed_versions
from runtime_files import atomic_json

PENDING = {'draining', 'switching', 'restoring', 'finishing', 'reconcile'}
TERMINAL = {'idle', 'active', 'restored', 'failed'}
VERSIONS = ('2.1.280', '2.1.293')


def _record(root: Path, source_version: str = '2.1.293') -> Path:
    if source_version not in VERSIONS:
        raise ValueError('未知官方原生运行时版本')
    return root / ('runtime/native-kernel-upgrade-280.json' if source_version == '2.1.280' else 'runtime/native-kernel-upgrade.json')


def _read(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError('历史内核记录不能是符号链接')
    try:
        if path.stat().st_size > 65536:
            raise ValueError('历史内核记录超过大小预算')
        value = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError('历史内核记录格式无效')
    return value


def _load(root: Path, source_version: str = '2.1.293') -> dict:
    return _read(_record(root, source_version))


def _migration(root: Path) -> Path:
    return root / 'runtime/native-kernel-platform-migration.json'


def migration_context(root: Path, row: dict, account_id: int) -> bool:
    """校验受控重建的持久上下文。@param root 私有目录。@param row 当前环境。@param account_id 唯一账号。@return 是否属于本次迁移。"""
    value = _read(_migration(root))
    return (value.get('account_id') == account_id and value.get('environment_id') == row['environment_id']
        and type(value.get('generation')) is int and row['generation'] in (value['generation'], value['generation'] + 1))


def pending_upgrade(root: Path, *, include_preparing: bool = False) -> bool:
    """保护历史未完成维护。@param root 环境私有根。@param include_preparing 兼容历史调用，退役候选退出门禁。@return 是否需要对账。"""
    migration = _migration(root)
    if migration.exists() or migration.is_symlink():
        _read(migration)
        return True
    records = [_load(root, version) for version in VERSIONS]
    return any(record and record.get('state', 'idle') not in TERMINAL for record in records)


def validate_records(root: Path, account_id: int | None, *, reconciled: bool = False) -> list[tuple[str, dict]]:
    """在环境副作用之前核对全部历史记录。

    :param root: 持有生命周期锁的环境私有目录。
    :param account_id: 当前绑定网关账号；未绑定环境只允许空记录。
    :param reconciled: 调用者已在原租约中完成中断对账。
    :return: 全部通过归属和维护状态核验的记录。
    """
    records = [(version, _load(root, version)) for version in VERSIONS]
    for _, record in records:
        if not record:
            continue
        if account_id is None or record.get('account_id') != account_id:
            raise ValueError('历史内核选择与当前账号归属不符')
        if record.get('state', 'idle') not in TERMINAL and not reconciled:
            raise ValueError('历史内核维护待环境对账')
    return records


def migrate_records(root: Path, account_id: int, *, reconciled: bool = False) -> None:
    """在受控重建边界将历史选择写为旧平台可读的内置状态。

    :param root: 已持有生命周期锁的环境目录。
    :param account_id: 当前唯一绑定的网关账号。
    :param reconciled: 调用者已经核对活动、代次和旧租约。
    :return: None；全部记录通过归属检查后才开始原子写入。
    """
    records = validate_records(root, account_id, reconciled=reconciled)
    for version, record in records:
        if not record:
            continue
        if (record.get('management') == 'platform' and record.get('state') == 'restored'
                and all(record.get(key) is None for key in ('current','kernel_generation','previous','prepared','preparing_release'))
                and not record.get('previous_available')):
            continue
        # 保留一份有界摘要。旧平台读取current为空，回退时自然采用目标镜像内置版本。
        atomic_json(_record(root, version), {'account_id': account_id, 'state': 'restored',
            'management': 'platform', 'current': None, 'kernel_generation': None,
            'previous': None, 'previous_available': False, 'prepared': None, 'preparing_release': None,
            'migrated_from': {key: record[key] for key in
                ('state', 'current', 'operation_id', 'binding_generation') if key in record}})


def archive_binding_records(root: Path, account_id: int | None) -> None:
    """在原绑定门禁内归档终态记录，使下一绑定采用平台内置选择。

    :param root: 已持有环境锁且旧发送器已停止的私有目录。
    :param account_id: 交接前的网关绑定；首次绑定为None。
    :return: None；未知归属和未完成迁移保持拒绝。
    """
    if pending_upgrade(root):
        raise ValueError('历史内核维护待环境对账')
    records = validate_records(root, account_id)
    for version, record in records:
        if not record:
            continue
        path = _record(root, version)
        # 先持久化审计再移除活动记录；中断重试可覆盖同一账号的归档，DB提交前后均采用内置选择。
        atomic_json(path.with_name(f'{path.stem}.account-{account_id}.json'), record)
        path.unlink()


def status(runtime, row: dict, source_version: str = '2.1.293') -> dict | None:
    """投影目标内置身份；实际进程状态沿原生准备观察单独显示。

    :param runtime: 环境协调器。
    :param row: 环境身份和代次。
    :param source_version: 官方源版本。
    :return: 已安装版本的只读信息，基础后端或缺失安装返回None。
    """
    _record(runtime._root(row), source_version)
    try:
        config = json.loads(runtime._sender_config(row).read_text())
        native = config.get('native')
        if not isinstance(native, dict):
            return None
        selected = native.get('runtimes', {}).get(source_version)
        if selected is None and source_version == '2.1.293':
            selected = native
        if not isinstance(selected, dict):
            return None
        try:
            validate_records(runtime._root(row), config['binding']['account_id'])
            pending = pending_upgrade(runtime._root(row))
        except ValueError:
            # 归属或日志异常只投影维护提示，避免把旧记录误当作当前运行身份。
            pending = True
        legacy = bool(selected.get('release') or selected.get('kernel_generation'))
        builtin = {'release': VERSION_280, 'launcher_sha256': SHA256_280} if source_version == '2.1.280' else {
            'release': VERSION, 'launcher_sha256': SHA256}
        return {'management': 'platform', 'source_version': source_version,
            'state': 'reconcile' if pending else 'migration_required' if legacy else 'builtin',
            'revision': str(row['generation']), 'current': selected.get('release') if legacy else builtin,
            'builtin': builtin, 'platform_release': config['binding'].get('release_id'),
            'error': '历史内核维护需要环境对账' if pending else None}
    except FileNotFoundError:
        return None


def recover_interrupted(root: Path) -> bool:
    """将历史中断显式标为环境对账。@param root 环境根目录。@return 是否仍需对账。"""
    for version in VERSIONS:
        record = _load(root, version)
        if record.get('preparing_release'):
            # 下载入口已退役；保留中断审计，避免陈旧候选占用采集和CRIU设置的维护门禁。
            record = {**record, 'preparing_release': None, 'cancelled_preparing_release': record['preparing_release']}
            atomic_json(_record(root, version), record)
        if record and record.get('state', 'idle') not in TERMINAL and record.get('state') != 'reconcile':
            atomic_json(_record(root, version), {**record, 'state': 'reconcile',
                'reconcile_from': record.get('state'), 'error': '历史内核维护中断，请执行环境对账'})
    return pending_upgrade(root)


def reconcile_legacy(runtime, row: dict, account: dict) -> None:
    """在环境对账入口核对原租约，重建内置布局后收口历史维护。

    :param runtime: 已持有环境锁的协调器。
    :param row: 当前环境行。
    :param account: 数据库当前账号。
    :return: None；异常保留维护门禁和对账状态。
    """
    root = runtime._root(row)
    journal_path = _migration(root)
    journal = _read(journal_path)
    if journal_path.exists() and not journal:
        raise ValueError('内置内核迁移日志缺少归属信息，请核对原记录')
    account_id = account.get('cc2api_account_id')
    if journal and not migration_context(root, row, account_id):
        raise ValueError('内置内核迁移归属或代次待核对')
    records = journal.get('records') if journal else {version: _load(root, version) for version in VERSIONS}
    if not isinstance(records, dict) or set(records) != set(VERSIONS) or any(not isinstance(value, dict) for value in records.values()):
        raise ValueError('历史内核迁移记录格式无效')
    pending = [record for record in records.values() if record and record.get('state', 'idle') not in TERMINAL]
    if len(pending) != 1 or not account_id:
        raise ValueError('历史内核维护缺少唯一操作和账号归属')
    if runtime.environment_jobs(row['environment_id']) or runtime._execution_records(row):
        raise ValueError('环境仍有活动作业，历史内核维护待对账')
    with runtime.database() as connection:
        count = connection.execute('SELECT COUNT(*) FROM accounts WHERE cc2api_account_id=? AND deleted_at IS NULL', (account_id,)).fetchone()[0]
    if count != 1 or any(record and record.get('account_id') != account_id for record in records.values()):
        raise ValueError('历史内核维护缺少唯一账号绑定')
    record = pending[0]
    phase = record.get('reconcile_from', record.get('state'))
    if phase not in PENDING - {'reconcile'} or not record.get('operation_id'):
        raise ValueError('历史内核维护阶段或操作身份未知，请核对原始记录')
    if not journal and record.get('binding_generation') != row['generation']:
        raise ValueError('历史内核维护代次待核对')
    config = json.loads(runtime._sender_config(row).read_text())
    binding = config['binding']
    if binding.get('account_id') != account_id or binding.get('environment_id') != row['environment_id']:
        raise ValueError('历史发送器绑定与环境不一致')
    if binding.get('generation') != row['generation'] and not (
            journal and not row.get('sender_container_id') and binding.get('generation') == journal['generation']):
        raise ValueError('历史发送器绑定代次与环境不一致')
    labels = runtime.client.images.get(runtime.image).attrs['Config'].get('Labels') or {}
    versions = installed_versions(labels)
    config['native'] = builtin_config(config.get('native'), versions)
    if config['native'] is None:
        raise ValueError('历史内核维护缺少原生发送器配置')
    path = f'/admin/runtime/accounts/{account_id}/lease'
    snapshot = runtime.gateway._request('GET', path)
    lease = snapshot.get('lease')
    if snapshot.get('active') != 0 or snapshot.get('waiting', 0) != 0 or snapshot.get('holders') or runtime._running_sender_active(row):
        raise ValueError('账号仍有活动请求，历史内核维护待对账')
    owner = 'kernel:' + record['operation_id']
    if lease:
        if lease.get('owner') != owner or not record.get('lease_generation') or lease.get('generation') != record['lease_generation']:
            raise ValueError('维护租约属于其他操作或代次')
        if lease.get('phase') not in ('draining', 'claimed', 'reconcile') or lease.get('exclusive') is not True:
            raise ValueError('历史内核维护租约阶段未知')
    elif phase != 'draining' and journal.get('phase') != 'finishing':
        raise ValueError('历史内核切换缺少原维护租约，请核对归属')
    stopped = journal.get('stopped', row['state'] == 'stopped')
    journal = {'account_id': account_id, 'environment_id': row['environment_id'], 'generation': row['generation'],
        'phase': 'rebuilding', 'stopped': stopped, 'records': records}
    # 日志先于副作用持久化。即使旧选择已经归一或新容器只创建了一部分，也能恢复原操作租约。
    atomic_json(journal_path, journal)
    if not lease:
        prepared = runtime.gateway._request('POST', path, {'operation': 'prepare', 'owner': owner})
        lease = prepared.get('lease')
        if (not lease or lease.get('owner') != owner or not lease.get('generation')
                or lease.get('phase') not in ('draining', 'claimed', 'reconcile') or lease.get('exclusive') is not True):
            raise ValueError('未取得历史内核维护门禁')
        record['lease_generation'] = lease['generation']
        atomic_json(journal_path, journal)
        if prepared.get('active') != 0 or prepared.get('waiting', 0) != 0 or prepared.get('holders') or runtime._running_sender_active(row):
            raise ValueError('重建门禁已关闭，等待原请求结束后再次对账')
    if lease.get('phase') == 'draining':
        claimed = runtime.gateway._request('POST', path, {'operation': 'claim', 'owner': owner, 'generation': lease['generation']})
        current = claimed.get('lease')
        if not current or current.get('owner') != owner or current.get('generation') != lease['generation'] or current.get('phase') != 'claimed':
            raise ValueError('历史内核维护门禁领取结果待核对')
        lease = current
    try:
        runtime._stop_environment(row, remove=True)
        runtime._write_sender_config(row, config)
        migrate_records(root, account_id, reconciled=True)
        runtime._update(row, state='stopped')
        if not stopped:
            ready, _ = runtime.ensure(account, prepare_sender=False, native_migration=True)
            row.update(ready)
        journal.update(generation=row['generation'], phase='finishing')
        atomic_json(journal_path, journal)
        released = runtime.gateway._request('POST', path, {'operation': 'release', 'owner': owner, 'generation': lease['generation']})
        if released.get('lease') is not None:
            raise ValueError('历史内核维护门禁释放结果待核对')
        journal_path.unlink()
    except Exception:
        runtime._update(row, state='reconcile')
        raise
