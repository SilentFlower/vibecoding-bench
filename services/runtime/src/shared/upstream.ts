import type { ModelSelection, NativeIngressPolicy, PreparedInput } from './contracts';
import { BridgeError, isObject } from './errors';

/** 本机启动选择的最终出站验证模式，不由业务请求授权。 */
export type TlsCaptureMode = 'off' | 'verify';

/** 校验显式上游地址，不改写原生 SDK 的路径语义。
 * @param value 可选启动值。
 * @return 原值；未配置时为空。
 */
export function readNativeBaseUrl(value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  try {
    const url = new URL(value);
    if (value !== value.trim() || !['http:', 'https:'].includes(url.protocol) || url.username || url.password || value.includes('?') || value.includes('#') || /[\x00-\x20\x7f]/.test(value)) throw new Error();
  } catch { throw new BridgeError('native_configuration', 'CCRB_NATIVE_BASE_URL 必须为不含凭据、查询串或片段的 HTTP(S) 地址', 503); }
  return value;
}

/** 校验可选根模型覆盖，不对模型能力作推断。
 * @param value 启动侧模型标识。
 * @return 原值；未配置时为空。
 */
export function readModelOverride(value: string | undefined): string | undefined {
  if (value !== undefined && (!value.trim() || value !== value.trim() || /[\x00-\x1f\x7f]/.test(value))) throw new BridgeError('native_configuration', 'CCRB_MODEL_OVERRIDE 必须为不含控制字符的非空模型标识', 503);
  return value;
}

/** 读取内置验证开关。
 * @param value 启动值。
 * @return 已验证模式，默认关闭。
 */
export function readTlsCaptureMode(value: string | undefined): TlsCaptureMode {
  if (value !== undefined && value !== 'off' && value !== 'verify') throw new BridgeError('native_configuration', 'CCRB_TLS_CAPTURE 必须为 off 或 verify', 503);
  return value ?? 'off';
}

/** 读取独立的原生入站兼容策略。
 * @param value 本机启动值。
 * @return 已验证策略，默认严格。
 */
export function readNativeIngressPolicy(value: string | undefined): NativeIngressPolicy {
  if (value !== undefined && value !== 'strict' && value !== 'local_base_url') throw new BridgeError('native_configuration', 'CCRB_NATIVE_INGRESS_POLICY 必须为 strict 或 local_base_url', 503);
  return value ?? 'strict';
}

/** 在已有入站归因完成后应用根模型选择，保留业务原文和分类证据。
 * @param prepared 已经解析的业务与上下文。
 * @param override 本机可选覆盖。
 * @return 新的有效请求；原对象不变。
 */
export function selectUpstreamModel(prepared: PreparedInput, override?: string): PreparedInput {
  const selected = readModelOverride(override);
  const selection: ModelSelection = { requested: prepared.input.body.model, effective: selected ?? prepared.input.body.model, source: selected === undefined ? 'request' : 'startup_override' };
  return { ...prepared, input: { ...prepared.input, body: { ...prepared.input.body, model: selection.effective } }, context: { ...prepared.context, modelSelection: selection } };
}

/** 校验持久记录及私有作业中的模型选择证据。
 * @param value 未知边界值。
 * @return 是否符合唯一模型选择合同。
 */
export function isModelSelection(value: unknown): value is ModelSelection {
  if (!isObject(value) || typeof value.requested !== 'string' || !value.requested || typeof value.effective !== 'string' || !value.effective) return false;
  return value.source === 'startup_override' || (value.source === 'request' && value.requested === value.effective);
}
