"""账号内容采集策略；在原空闲维护门禁内重建并核对实际配置。"""
import hashlib
import json
import time

from native_capture_policy import capture_enabled
from native_kernel_upgrade import pending_upgrade
from native_settings_operation import apply_settings
from system_update_contract import safe_read, strict_json


def read_settings(runtime, row: dict, observation: dict | None = None) -> dict:
    """只读取得采集配置与并发版本。

    :param runtime: 权威账号运行时。
    :param row: 锁内当前环境记录。
    :param observation: 既有批量巡检取得的同代次状态。
    :return: 不含凭据的策略、实际配置及版本摘要。
    """
    fingerprint = json.loads(row['fingerprint_json'])
    try:
        # sender 配置按原隔离合同为 root:1001 的 0640，供独立发送器只读。
        raw = safe_read(runtime._sender_config(row), 1024 * 1024)
        configuration = strict_json(raw, 1024 * 1024)
    except FileNotFoundError:
        raw, configuration = b'', {}
    enabled = capture_enabled(fingerprint)
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
    protocol = configuration.get('native_tls_observer_protocol')
    installed = type(protocol) is int and protocol == 1
    tls = {'state': 'preparing', 'reason': 'CAPTURE_PREPARING', 'checked_at_ms': None,
        'protocol_version': 1 if installed else None, 'image_admitted': None}
    if not enabled:
        tls.update(state='disabled', reason=None)
    elif not installed:
        tls.update(state='not_installed', reason='OBSERVER_NOT_CONFIGURED')
    elif row['state'] == 'stopped':
        tls.update(state='stopped', reason=None)
    elif observation and owned:
        tls.update(state='unavailable', reason='OBSERVER_STATUS_UNAVAILABLE')
        native = configuration.get('native') or {}
        checked = observation.get('checked_at_ms')
        if (observation.get('environment_id') == row['environment_id']
                and observation.get('generation') == row['generation']
                and observation.get('kernel_generation') == native.get('kernel_generation')
                and type(checked) is int and 0 <= time.time() * 1000 - checked <= 45000):
            candidate = observation.get('tls_observer')
            if (isinstance(candidate, dict) and type(candidate.get('protocol_version')) is int
                    and candidate.get('protocol_version') == 1
                    and candidate.get('state') in ('preparing', 'ready', 'unavailable')
                    and (candidate.get('state') != 'ready' or candidate.get('image_admitted') is True)):
                reason = candidate.get('reason')
                # 仅固定诊断码进入页面，避免私有管道的异常原文被投影。
                if reason is None or (isinstance(reason, str) and 1 <= len(reason) <= 64
                        and all(char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for char in reason)):
                    tls.update(state=candidate['state'], reason=reason, checked_at_ms=checked,
                        image_admitted=candidate.get('image_admitted') if type(candidate.get('image_admitted')) is bool else None)
        else:
            tls.update(state='unavailable', reason='OBSERVER_STATUS_STALE')
    else:
        tls.update(state='unavailable', reason='OBSERVER_STATUS_UNAVAILABLE')
    return {'environment_id': row['environment_id'], 'account_id': row['account_id'],
        'generation': row['generation'], 'revision': revision, 'enabled': enabled,
        'applied': supported and owned and actual == enabled, 'supported': supported, 'tls_observer': tls}


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
    if enabled and before['tls_observer']['protocol_version'] != 1:
        raise ValueError('当前镜像需要先通过系统更新安装原生TLS采集能力')
    return apply_settings(runtime, row, account, enabled, before, read_settings,
        field='native_capture_enabled', label='采集', prefix='capture', audit_name='content-capture-operation.json')
