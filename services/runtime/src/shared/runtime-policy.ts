import { BridgeError, isObject } from './errors';

/** 由本机启动配置选择的消息缓存策略。 */
export type CachePolicy = 'preserve' | 'sub2api';

/** 受信任前置服务按本次设置冻结的已有缓存TTL覆盖。 */
export type CacheTtlRewrite = 'off' | '5m' | '1h';

/** 校验私有指令中的TTL模式，省略时保留原值。
 * @param value 前置服务冻结的策略。
 * @return 有效模式；非法模式按私有协议错误拒绝。
 */
export function readCacheTtlRewrite(value: unknown): CacheTtlRewrite {
  if (value === undefined) return 'off';
  if (value === 'off' || value === '5m' || value === '1h') return value;
  throw new BridgeError('runtime_protocol', '私有缓存TTL策略无效', 502);
}

/** 本机第一方遥测开关，开启仍服从官方策略。 */
export type TelemetryPolicy = 'off' | 'on';

/** 实际初始化状态，不表示服务端已成功接收。 */
export type TelemetryState = 'off' | 'pending' | 'initialized' | 'suppressed' | 'unavailable';

/** worker 握手中可证明的原生遥测状态。 */
export type TelemetryHandshake = { policy: 'off'; state: 'off' } | { policy: 'on'; state: 'initialized' | 'suppressed' };

/** 校验本机遥测开关，省略时关闭。
 * @param value 配置入口的原始值。
 * @return 已校验开关，非法值抛出配置错误。
 */
export function readTelemetryPolicy(value: unknown): TelemetryPolicy {
  if (value === undefined) return 'off';
  if (value === 'off' || value === 'on') return value;
  throw new BridgeError('native_configuration', 'CCRB_TELEMETRY 必须为 off 或 on', 503);
}

/** 校验 worker 报告的遥测状态与配置关系。
 * @param value 私有握手中的未知对象。
 * @return 仅允许已完成初始化或被策略抑制的明确状态。
 */
export function isTelemetryHandshake(value: unknown): value is TelemetryHandshake {
  return isObject(value) && ((value.policy === 'off' && value.state === 'off') || (value.policy === 'on' && (value.state === 'initialized' || value.state === 'suppressed')));
}

const CACHE_REASONS = {
  policy_preserve: '保留原始缓存布局',
  caller_message_breakpoints: '调用方已有消息缓存断点',
  root_cache_control_present: '保留根级缓存机制',
  unsupported_cache_control: '缓存结构无法安全优化',
  no_available_slots: '缓存断点预算已用完',
  no_cacheable_blocks: '没有可用的消息缓存边界',
  sub2api_tail: '已应用 sub2api 尾部选点',
} as const;

/** 缓存处理结果，只含位置与控制枚举，不保存业务内容。 */
export interface CachePolicyDecision {
  mode: CachePolicy;
  action: 'preserved' | 'skipped' | 'applied';
  reason: keyof typeof CACHE_REASONS;
  selected: { message: number; block: number }[];
  breakpoints: number | null;
  ttl: '5m' | '1h' | null;
}

/** 校验本机缓存配置，省略时采用保真策略。
 * @param value 配置入口提供的原始值。
 * @return 已校验的缓存策略，非法值抛出受控配置错误。
 */
export function readCachePolicy(value: unknown): CachePolicy {
  if (value === undefined) return 'preserve';
  if (value === 'preserve' || value === 'sub2api') return value;
  throw new BridgeError('native_configuration', 'CCRB_CACHE_POLICY 必须为 preserve 或 sub2api', 503);
}

/** 校验私有事件中的缓存诊断，避免各消费者猜测其形状。
 * @param value 未知诊断对象。
 * @return 结构及模式关系合法时为真。
 */
export function isCachePolicyDecision(value: unknown): value is CachePolicyDecision {
  if (!isObject(value) || (value.mode !== 'preserve' && value.mode !== 'sub2api') || typeof value.reason !== 'string' || !Object.hasOwn(CACHE_REASONS, value.reason)) return false;
  if (!Array.isArray(value.selected) || value.selected.length > 2 || value.selected.some(position => !isObject(position) || !Number.isSafeInteger(position.message) || Number(position.message) < 0 || !Number.isSafeInteger(position.block) || Number(position.block) < 0)) return false;
  if (value.breakpoints !== null && (!Number.isSafeInteger(value.breakpoints) || Number(value.breakpoints) < 0)) return false;
  if (value.action === 'applied') return value.mode === 'sub2api' && value.reason === 'sub2api_tail' && value.selected.length > 0 && typeof value.breakpoints === 'number' && value.breakpoints <= 4 && (value.ttl === '5m' || value.ttl === '1h');
  if (value.selected.length || value.ttl !== null) return false;
  if (value.action === 'preserved') return value.mode === 'preserve' && value.reason === 'policy_preserve';
  return value.action === 'skipped' && value.mode === 'sub2api' && !['policy_preserve', 'sub2api_tail'].includes(value.reason);
}

/** 将已校验诊断转为日志说明，不据此宣称上游命中缓存。
 * @param decision 本次发送的策略结果。
 * @return 可持久保存的中文说明。
 */
export function describeCachePolicy(decision: CachePolicyDecision): string {
  const positions = decision.selected.map(position => `messages[${position.message}].content[${position.block}]`).join('、');
  return `缓存策略 ${decision.mode}：${CACHE_REASONS[decision.reason]}${positions ? '；位置 ' + positions + '；新 TTL=' + decision.ttl : ''}`;
}
