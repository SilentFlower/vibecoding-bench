"""统一解释CRIU目标选择和独立恢复预算，供创建、重建和状态读取共用。"""
from native_sender import POOL_MIB, RESTORE_IMAGE_MIB, WORKER_MIB, criu_enabled


def account_enabled(fingerprint: dict) -> bool:
    """读取账号持久选择。@param fingerprint 已保存环境指纹。@return 缺省开启；非法类型拒绝。"""
    value = fingerprint.get('native_criu_enabled', True)
    if type(value) is not bool:
        raise ValueError('CRIU加速选择无效，请对账账号配置')
    return value


def restore_policy(native: dict | None, fingerprint: dict, installed: bool) -> dict:
    """决定是否选择恢复入口。@param native 冻结原生资源或None。@param fingerprint 账号选择。@param installed 镜像是否支持恢复器。@return 安全策略、恢复预算与固定原因。"""
    if native is not None and (not isinstance(native, dict)
            or type(native.get('max_workers')) is not int or native['max_workers'] <= 0
            or type(native.get('memory_mib')) is not int or native['memory_mib'] < 0):
        raise ValueError('原生恢复资源配置需要对账')
    enabled, platform = account_enabled(fingerprint), criu_enabled()
    required = POOL_MIB + native['max_workers'] * (WORKER_MIB + RESTORE_IMAGE_MIB) if native else None
    memory = native['memory_mib'] if native else None
    reason = ('legacy_backend' if not native else 'platform_disabled' if not platform else
        'account_disabled' if not enabled else 'image_unsupported' if not installed else
        'memory_budget' if memory != 0 and memory < required else None)
    return {'enabled': enabled, 'platform_enabled': platform, 'eligible': reason is None,
        'reason': reason, 'memory_mib': memory, 'required_memory_mib': required}
