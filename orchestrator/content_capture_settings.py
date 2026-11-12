"""账号内容采集策略；在原空闲维护门禁内重建并核对实际配置。"""
import hashlib
import json
import uuid

from native_kernel_upgrade import pending_upgrade
from runtime_files import atomic_json
from system_update_contract import safe_read, strict_json


def read_settings(runtime, row: dict) -> dict:
    """只读取得采集配置与并发版本。

    :param runtime: 权威账号运行时。
    :param row: 锁内当前环境记录。
    :return: 不含凭据的策略、实际配置及版本摘要。
    """
    fingerprint = json.loads(row['fingerprint_json'])
    try:
        # sender 配置按原隔离合同为 root:1001 的 0640，供独立发送器只读。
        raw = safe_read(runtime._sender_config(row), 1024 * 1024)
        configuration = strict_json(raw, 1024 * 1024)
    except FileNotFoundError:
        raw, configuration = b'', {}
    enabled = fingerprint.get('native_capture_enabled') is True
    actual = configuration.get('native_capture_dir') == '/flows/api/cc-prepared'
    supported = isinstance(configuration.get('native'), dict)
    binding = configuration.get('binding') if isinstance(configuration.get('binding'), dict) else {}
    owned = (binding.get('account_id') == row.get('gateway_account_id')
        and binding.get('environment_id') == row['environment_id']
        and binding.get('generation') == row['generation'])
    revision = hashlib.sha256(json.dumps({'environment_id': row['environment_id'],
        'account_id': row['account_id'], 'gateway_account_id': row.get('gateway_account_id'),
        'generation': row['generation'], 'state': row['state'],
        'fingerprint': fingerprint, 'sender_sha256': hashlib.sha256(raw).hexdigest()},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'environment_id': row['environment_id'], 'account_id': row['account_id'],
        'generation': row['generation'], 'revision': revision, 'enabled': enabled,
        'applied': supported and owned and actual == enabled, 'supported': supported}


def set_settings(runtime, row: dict, account: dict, enabled: bool,
                 expected_generation: int, expected_revision: str) -> dict:
    """按冻结版本切换后续请求采集；失败恢复原策略。

    :param runtime: 已进入更新准入及账号锁的运行时。
    :param row: 锁内当前环境记录。
    :param account: 唯一绑定的当前账号。
    :param enabled: 管理员选择的目标状态。
    :param expected_generation: 页面冻结代次。
    :param expected_revision: 页面冻结配置摘要。
    :return: 实际生效状态；恢复失败保留待对账状态。
    """
    before = read_settings(runtime, row)
    if account.get('cc2api_account_id') != row.get('gateway_account_id'):
        raise ValueError('账号发送器绑定已变化，请重新读取')
    if expected_generation != before['generation'] or expected_revision != before['revision']:
        raise ValueError('环境或采集配置已变化，请刷新后重新操作')
    if not before['supported'] or not before['applied'] or row['state'] not in ('ready', 'stopped'):
        raise ValueError('原生发送器尚未就绪或配置需要对账')
    if pending_upgrade(runtime._root(row), include_preparing=True):
        raise ValueError('请求内核正在维护，请完成后再切换采集')
    if before['enabled'] == enabled:
        return before
    original = json.loads(row['fingerprint_json'])
    was_stopped = row['state'] == 'stopped'
    owner = f'capture:{uuid.uuid4().hex}'
    if runtime.credential_ownership:
        runtime.credential_ownership.guard(account, owner)
    if runtime.environment_jobs(row['environment_id']) or runtime.reviews.serial_state(row):
        raise ValueError('账号正在工作或评审交接，请空闲后切换采集')
    lease_path = f'/admin/runtime/accounts/{account["cc2api_account_id"]}/lease'
    snapshot = runtime.gateway._request('GET', lease_path)
    if snapshot.get('lease') or snapshot.get('holders') or snapshot.get('active') != 0 or snapshot.get('waiting', 0):
        raise ValueError('账号正在工作，请空闲后切换采集')
    if runtime._running_sender_active(row):
        raise ValueError('账号仍有发送连接，请空闲后切换采集')
    audit_path = runtime._root(row) / 'runtime/content-capture-operation.json'
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
        runtime._update(row, fingerprint_json=json.dumps({**original, 'native_capture_enabled': enabled}), state='stopped')
        current, _ = runtime.ensure(account, preserve_proxy=True)
        row.update(current)
        if was_stopped:
            runtime._stop_environment(row)
            runtime._update(row, state='stopped')
        result = read_settings(runtime, row)
        if result['enabled'] != enabled or not result['applied']:
            raise ValueError('发送器实际采集配置与目标不一致')
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
                recovered = read_settings(runtime, row)
                restored = recovered['enabled'] == before['enabled'] and recovered['applied']
            except Exception:
                runtime._update(row, state='reconcile')
            if not restored:
                runtime._update(row, state='reconcile')
            atomic_json(audit_path, {**audit, 'state': 'restored' if restored else 'reconcile'})
            raise RuntimeError('采集切换失败，原策略已恢复' if restored else '采集配置需要对账，请查看环境维护状态') from None
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
            raise RuntimeError('采集维护门禁尚未释放，请通过环境维护对账') from None
