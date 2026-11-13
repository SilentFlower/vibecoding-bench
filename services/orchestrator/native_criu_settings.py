"""CRIU目标选择、容器入口及同代恢复观测的安全投影。"""
import hashlib
import json
import time

from account_isolation import role_container
from native_criu_policy import restore_policy
from native_kernel_upgrade import pending_upgrade
from native_settings_operation import apply_settings
from system_update_contract import safe_read, strict_json

ENTRY = ['/usr/local/bin/python3', '-E', '-s', '/opt/ccrb-criu/entry.py']
REASONS = {'legacy_backend', 'platform_disabled', 'account_disabled', 'image_unsupported',
    'memory_budget', 'controller_preflight_failed', 'controller_unavailable', 'kernel_unsupported',
    'template_failed', 'template_preparing', 'identity_changed'}


def read_settings(runtime, row: dict, observation: dict | None = None) -> dict:
    """只读核对目标与实际入口。@param runtime 账号运行时。@param row 当前环境。@param observation 同代巡检。@return 不含秘密的版本化恢复摘要。"""
    fingerprint = json.loads(row['fingerprint_json'])
    try:
        raw = safe_read(runtime._sender_config(row), 1024 * 1024)
        configuration = strict_json(raw, 1024 * 1024)
    except FileNotFoundError:
        raw, configuration = b'', {}
    if not isinstance(configuration, dict):
        raise ValueError('发送器配置需要对账')
    sender = role_container(runtime, row, 'sender')
    sender.reload()
    details = sender.attrs['Config']
    installed = (details.get('Labels') or {}).get('vibebench.native-criu') == '1'
    actual = details.get('Entrypoint') == ENTRY
    native = configuration.get('native')
    supported = isinstance(native, dict)
    policy = restore_policy(native, fingerprint, installed)
    binding = configuration.get('binding') if isinstance(configuration.get('binding'), dict) else {}
    owned = (binding.get('account_id') == row.get('gateway_account_id')
        and binding.get('environment_id') == row['environment_id'] and binding.get('generation') == row['generation'])
    applied = supported and owned and actual == policy['eligible'] and configuration.get('native_criu_enabled', False) is policy['eligible']
    revision = hashlib.sha256(json.dumps({'environment_id': row['environment_id'], 'generation': row['generation'],
        'state': row['state'], 'fingerprint': fingerprint, 'policy': policy,
        'sender_sha256': hashlib.sha256(raw).hexdigest(), 'entrypoint': details.get('Entrypoint'),
        'container_id': sender.id, 'installed': installed}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    result = {**policy, 'schema_version': 1, 'environment_id': row['environment_id'], 'generation': row['generation'],
        'revision': revision, 'supported': supported, 'installed': installed, 'applied': applied,
        'state': 'unknown', 'template_ready': False, 'checked_at_ms': None, 'last_start_source': None}
    if policy['reason']:
        result['state'] = 'disabled' if policy['reason'] in ('platform_disabled', 'account_disabled') else 'not_installed' if policy['reason'] == 'image_unsupported' else 'unavailable'
    elif not owned:
        result['reason'] = 'binding_unverified'
    elif not applied:
        result.update(state='requires_rebuild', reason='container_rebuild_required')
    elif row['state'] == 'stopped':
        result['reason'] = 'environment_stopped'
    elif not observation:
        result['reason'] = 'telemetry_missing'
    else:
        checked = observation.get('checked_at_ms')
        if (observation.get('environment_id') != row['environment_id'] or observation.get('generation') != row['generation']
                or observation.get('kernel_generation') != native.get('kernel_generation')
                or type(checked) is not int or not 0 <= time.time() * 1000 - checked <= 45000):
            result['reason'] = 'telemetry_stale'
        else:
            value = observation.get('restore')
            # 仅白名单枚举及精确布尔值进入页面，旧/畸形遥测不能伪装成模板就绪。
            if (isinstance(value, dict) and type(value.get('schema_version')) is int and value['schema_version'] == 1
                    and value.get('state') in ('ready', 'preparing', 'unavailable', 'unknown')
                    and type(value.get('template_ready')) is bool
                    and (value.get('reason') is None or isinstance(value['reason'], str) and value['reason'] in REASONS)
                    and (value['state'] == 'ready') == value['template_ready']):
                result.update(state=value['state'], reason=value.get('reason'), template_ready=value['template_ready'], checked_at_ms=checked)
                if value.get('last_start_source') in ('exec', 'criu_restore'):
                    result['last_start_source'] = value['last_start_source']
            else:
                result['reason'] = 'telemetry_missing'
    return result


def set_settings(runtime, row: dict, account: dict, enabled: bool, expected_generation: int, expected_revision: str) -> dict:
    """在原维护门禁内应用账号选择。@param runtime 锁内运行时。@param row 当前环境。@param account 唯一账号。@param enabled 目标选择。@param expected_generation 页面代次。@param expected_revision 页面摘要。@return 经重建核对的实际配置。"""
    before = read_settings(runtime, row)
    if (type(enabled) is not bool or account.get('cc2api_account_id') != row.get('gateway_account_id')
            or expected_generation != before['generation'] or expected_revision != before['revision']):
        raise ValueError('环境或CRIU配置已变化，请刷新后重新操作')
    if not before['supported'] or before['reason'] == 'binding_unverified' or row['state'] not in ('ready', 'stopped'):
        raise ValueError('原生发送器尚未就绪或绑定需要对账')
    if pending_upgrade(runtime._root(row), include_preparing=True):
        raise ValueError('请求内核正在维护，请完成后再切换CRIU')
    if enabled and not before['installed']:
        raise ValueError('当前镜像需要先通过系统更新安装CRIU能力')
    if enabled and not before['platform_enabled']:
        raise ValueError('平台已关闭CRIU，请先恢复平台开关')
    if before['enabled'] == enabled and before['applied']:
        return before
    return apply_settings(runtime, row, account, enabled, before, read_settings,
        field='native_criu_enabled', label='CRIU', prefix='criu', audit_name='criu-operation.json')
