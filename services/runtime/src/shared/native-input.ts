import type { ContextInput, JsonObject, MessageBody, NativeIngressPolicy } from './contracts';
import { BridgeError, isObject } from './errors';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const BILLING = /^\s*x-anthropic-billing-header:/;
const CONTROL_FIELDS = new Set(['settings', 'claude_settings', 'env', 'extra_headers', 'extra_body', 'headers', 'proxy_url', 'api_key', 'oauth_token', 'claude_binary', 'claude_home', 'claude_config_dir', 'workdir']);

/** 固定 293 原生正文中可证明的归因证据，不能授权本机配置或执行。
 * @property billingIndex 独立 billing 文本块的位置。
 * @property fields 原始 billing 字段，保留扩展字段与轮次信息。
 * @property user 原生 metadata.user_id 的结构。
 * @property context 可与显式信封及请求头合并的关联信息。
 */
export interface NativeInput {
  billingIndex: number;
  fields: Record<string, string>;
  user: JsonObject;
  context: ContextInput;
}

/** 识别并校验完整的固定 293 原生请求；普通 API 返回空值。
 * @param body 尚未裁剪或重新组装的请求正文。
 * @param policy 启动侧入站策略，默认要求完整 CLI billing。
 * @return 原生归因证据；缺少原生 billing 时为空，疑似原生但损坏时明确失败。
 */
export function readNativeInput(body: JsonObject, policy: NativeIngressPolicy = 'strict'): NativeInput | null {
  if (!['strict', 'local_base_url'].includes(policy)) throw new BridgeError('invalid_native_policy', '原生入站策略不合法');
  const system = body.system;
  const blocks = Array.isArray(system) ? system : typeof system === 'string' ? [{ type: 'text', text: system }] : [];
  const candidates = blocks.map((block, index) => ({ block, index })).filter(({ block }) => isObject(block) && typeof block.text === 'string' && BILLING.test(block.text));
  if (!candidates.length) return null;
  const invalid = (message: string): never => { throw new BridgeError('invalid_native_request', message, 422); };
  if (!Array.isArray(system) || candidates.length !== 1 || candidates[0]!.index !== 0) invalid('原生 system 必须包含唯一且位于首段的 billing 文本块');
  const { block, index } = candidates[0]!;
  if (!isObject(block) || block.type !== 'text' || typeof block.text !== 'string' || block.cache_control !== undefined) invalid('原生 billing 必须为不带缓存边界的独立文本块');
  const fields: Record<string, string> = Object.create(null);
  const cchCount = ((block.text as string).match(/\bcch=/g) ?? []).length;
  if (cchCount > 1 || (policy === 'strict' && cchCount !== 1)) invalid('原生 billing 的 CCH 位置存在歧义');
  for (const part of (block.text as string).replace(BILLING, '').split(';').map(value => value.trim()).filter(Boolean)) {
    const pair = /^([a-z_][a-z0-9_]*)=([^\r\n;]+)$/.exec(part);
    if (!pair || Object.hasOwn(fields, pair[1]!)) invalid('原生 billing 字段损坏或重复');
    fields[pair![1]!] = pair![2]!;
  }
  if (cchCount !== (fields.cch === undefined ? 0 : 1)) invalid('原生 billing 的 CCH 位置存在歧义');
  if (!/^2\.1\.293\.[0-9a-f]{3}$/.test(fields.cc_version ?? '') || !(policy === 'local_base_url' ? ['cli', 'sdk-cli'] : ['cli']).includes(fields.cc_entrypoint ?? '')) invalid('当前只接纳固定 2.1.293 CLI 原生请求');
  if ((policy === 'strict' || fields.cch !== undefined) && !/^[0-9a-f]{5}$/.test(fields.cch ?? '')) invalid('原生 billing 缺少有效 CCH');
  if (fields.cc_is_subagent !== undefined && !['true', 'false'].includes(fields.cc_is_subagent)) invalid('原生子代理标识不合法');
  if (fields.cc_prompt_id !== undefined && !UUID.test(fields.cc_prompt_id)) invalid('原生 prompt ID 必须为 UUID');
  for (const key of ['cc_prompt_index', 'cc_turn_index']) if (fields[key] !== undefined && !/^\d+$/.test(fields[key]!)) invalid('原生轮次必须为非负整数');
  if (!isObject(body.metadata) || typeof body.metadata.user_id !== 'string') invalid('原生请求缺少 metadata.user_id');
  let user: unknown;
  try { user = JSON.parse((body.metadata as JsonObject).user_id as string); } catch { invalid('原生 metadata.user_id 不是 JSON 字符串'); }
  if (!isObject(user) || typeof user.device_id !== 'string' || !/^[0-9a-f]{64}$/i.test(user.device_id) || typeof user.account_uuid !== 'string' || (user.account_uuid !== '' && !UUID.test(user.account_uuid)) || typeof user.session_id !== 'string' || !UUID.test(user.session_id)) invalid('原生 metadata.user_id 的设备、账号或会话结构不合法');
  for (const key of Object.keys(body)) if (CONTROL_FIELDS.has(key)) invalid('原生正文不能携带本机控制字段：' + key);
  const parsed = user as JsonObject;
  return { billingIndex: index, fields, user: parsed, context: { sessionId: parsed.session_id as string, ...(fields.cc_prompt_id ? { promptId: fields.cc_prompt_id } : {}), agentKind: fields.cc_is_subagent === 'true' ? 'subagent' : 'main' } };
}

/** 将调用方关联与原生证据合并，任何显式冲突均在发送前拒绝。
 * @param context 调用方显式上下文。
 * @param native 原生正文解析出的关联证据。
 * @return 合并后的上下文。
 */
export function mergeNativeContext(context: ContextInput, native: NativeInput): ContextInput {
  for (const [key, value] of Object.entries(native.context)) if (context[key as keyof ContextInput] !== undefined && context[key as keyof ContextInput] !== value) throw new BridgeError('context_conflict', '原生正文与上下文冲突：' + key);
  return { ...context, ...native.context };
}

/** 从原生正文准备唯一发送，账号与 CCH 存在性以同次原生上下文为准。
 * @param body 原生业务正文。
 * @param generatedMetadata 同一 SDK 按专用账号生成的身份。
 * @param policy 启动侧入站策略。
 * @param generatedSystem 同次 SDK 实际生成的 CLI system，用来取得发送入口及原生 CCH 分支。
 * @return 业务字段和缓存位置保持不变的请求正文。
 */
export function prepareNativeBody(body: MessageBody, generatedMetadata: unknown, policy: NativeIngressPolicy = 'strict', generatedSystem?: unknown): JsonObject {
  const native = readNativeInput(body, policy);
  if (!native || !isObject(generatedMetadata) || typeof generatedMetadata.user_id !== 'string') throw new BridgeError('native_identity', '无法取得当前账号的原生身份', 503);
  const account: unknown = JSON.parse(generatedMetadata.user_id);
  if (!isObject(account) || typeof account.device_id !== 'string' || typeof account.account_uuid !== 'string') throw new BridgeError('native_identity', '当前账号原生身份结构不匹配', 503);
  const result = structuredClone(body);
  result.metadata = { ...(body.metadata as JsonObject), user_id: JSON.stringify({ ...native.user, device_id: account.device_id, account_uuid: account.account_uuid }) };
  const blocks = result.system as JsonObject[];
  let billing = blocks[native.billingIndex]!.text as string;
  let generatedCch: boolean | undefined;
  if (generatedSystem !== undefined || policy === 'local_base_url') {
    // 入站是否缺 CCH 与内部目标是否生成 CCH 是两件事，必须以同次真实 CC 上下文判断。
    let generated: NativeInput | null;
    try { generated = readNativeInput({ system: generatedSystem, metadata: generatedMetadata }, 'local_base_url'); }
    catch { throw new BridgeError('native_identity', '同次 CLI billing 上下文校验失败', 503); }
    if (!generated || generated.fields.cc_entrypoint !== 'cli') throw new BridgeError('native_identity', '无法取得同次 CLI billing 上下文', 503);
    generatedCch = generated.fields.cch !== undefined;
    if (policy === 'local_base_url') billing = billing.replace(/((?:x-anthropic-billing-header:|;)\s*cc_entrypoint=)[^;\r\n]+/, '$1' + generated.fields.cc_entrypoint);
  }
  if (generatedCch === false) {
    billing = billing.replace(/((?:x-anthropic-billing-header:|;)\s*)cch=[0-9a-f]{5}\s*;?/, '$1');
  } else {
    if (native.fields.cch === undefined) billing = billing.trimEnd() + (billing.trimEnd().endsWith(';') ? ' ' : '; ') + 'cch=00000;';
    billing = billing.replace(/(x-anthropic-billing-header:\s*|;\s*)cch=[0-9a-f]{5}(?=\s*(?:;|$))/, '$1cch=00000');
  }
  blocks[native.billingIndex]!.text = billing;
  return result;
}
