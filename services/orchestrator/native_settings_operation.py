"""原生账号配置切换共用的维护排空、重建与失败恢复。"""
import json
import uuid

from runtime_files import atomic_json


def apply_settings(runtime, row: dict, account: dict, enabled: bool, before: dict, reader,
                   *, field: str, label: str, prefix: str, audit_name: str) -> dict:
    """在已核对CAS和功能准入后应用单个布尔选择。

    :param runtime: 已持有更新及账号环境锁的运行时。
    :param row: 当前环境。
    :param account: 已验证的唯一账号绑定。
    :param enabled: 目标布尔值。
    :param before: 已验证的原配置摘要。
    :param reader: 功能所有者的只读实际配置函数。
    :param field: 内部固定指纹字段。
    :param label: 内部固定功能中文名。
    :param prefix: 内部固定租约所有者前缀。
    :param audit_name: 内部固定操作记录文件名。
    :return: 经重建核验的结果；失败恢复原指纹和角色或进入对账。
    """
    if type(enabled) is not bool:
        raise ValueError('配置选择必须为布尔值')
    original = json.loads(row['fingerprint_json'])
    was_stopped = row['state'] == 'stopped'
    owner = f'{prefix}:{uuid.uuid4().hex}'
    if runtime.credential_ownership:
        runtime.credential_ownership.guard(account, owner)
    if runtime.environment_jobs(row['environment_id']) or runtime.reviews.serial_state(row):
        raise ValueError(f'账号正在工作或评审交接，请空闲后切换{label}')
    lease_path = f'/admin/runtime/accounts/{account["cc2api_account_id"]}/lease'
    snapshot = runtime.gateway._request('GET', lease_path)
    if snapshot.get('lease') or snapshot.get('holders') or snapshot.get('active') != 0 or snapshot.get('waiting', 0):
        raise ValueError(f'账号正在工作，请空闲后切换{label}')
    if runtime._running_sender_active(row):
        raise ValueError(f'账号仍有发送连接，请空闲后切换{label}')
    audit_path = runtime._root(row) / 'runtime' / audit_name
    audit = {'schema_version': 1, 'environment_id': row['environment_id'],
        'account_id': account['cc2api_account_id'], 'operation_id': owner,
        'original_enabled': before['enabled'], 'target_enabled': enabled, 'state': 'applying'}
    changed = False
    try:
        # 维护租约持续关闭 API 入场；CLI 作业登记会阻止画像复用与重建，不能用于这条路径。
        prepared = runtime.gateway._request('POST', lease_path, {'operation': 'prepare', 'owner': owner})
        lease = runtime._owned_lease(prepared, owner)
        if not lease or prepared.get('active') != 0 or runtime._running_sender_active(row):
            raise ValueError('账号已开始工作，请空闲后重新操作')
        runtime.gateway._request('POST', lease_path,
            {'operation': 'claim', 'owner': owner, 'generation': lease['generation']})
        atomic_json(audit_path, {**audit, 'lease_generation': lease['generation']})
        changed = True
        runtime._stop_environment(row, remove=True)
        runtime._update(row, fingerprint_json=json.dumps({**original, field: enabled}), state='stopped')
        current, _ = runtime.ensure(account, preserve_proxy=True)
        row.update(current)
        if was_stopped:
            runtime._stop_environment(row)
            runtime._update(row, state='stopped')
        result = reader(runtime, row)
        if result['enabled'] != enabled or not result['applied']:
            raise ValueError(f'发送器实际{label}配置与目标不一致')
        atomic_json(audit_path, {**audit, 'state': 'applied'})
        return result
    except Exception:
        if changed:
            restored = False
            try:
                runtime._stop_environment(row, remove=True)
                runtime._update(row, fingerprint_json=json.dumps(original), state='stopped')
                current, _ = runtime.ensure(account, preserve_proxy=True)
                row.update(current)
                if was_stopped:
                    runtime._stop_environment(row)
                    runtime._update(row, state='stopped')
                recovered = reader(runtime, row)
                restored = recovered['enabled'] == before['enabled'] and recovered['applied']
            except Exception:
                runtime._update(row, state='reconcile')
            if not restored:
                runtime._update(row, state='reconcile')
            atomic_json(audit_path, {**audit, 'state': 'restored' if restored else 'reconcile'})
            raise RuntimeError(f'{label}切换失败，原策略已恢复' if restored else f'{label}配置需要对账，请查看环境维护状态') from None
        raise
    finally:
        try:
            # prepare 的响应也可能丢失，按唯一 owner 重读后只释放本次租约。
            snapshot = runtime.gateway._request('GET', lease_path)
            lease = runtime._owned_lease(snapshot, owner)
            if lease:
                # 门禁到期仍保持关闭，原 owner 可释放；重建期间无业务提交许可依赖续租。
                runtime.gateway._request('POST', lease_path,
                    {'operation': 'release', 'owner': owner, 'generation': lease['generation']})
        except Exception:
            runtime._update(row, state='reconcile')
            raise RuntimeError(f'{label}维护门禁尚未释放，请通过环境维护对账') from None
