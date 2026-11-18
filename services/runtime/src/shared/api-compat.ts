import type { ContextInput, JsonObject, MessageBody } from './contracts';
import { BridgeError, isObject } from './errors';
import { prepareNativeBody, readNativeInput } from './native-input';

/** 将普通API的消息级system原位交给上游，身份和billing取自同次SDK。
 * @param requested 已通过普通API结构校验的请求。
 * @param generated 同次SDK生成的发送上下文。
 * @param sourceVersion 当前固定源版本。
 * @return 保留消息顺序、轮次配置和缓存位置的发送正文。
 */
export function prepareApiSystemMessages(requested: MessageBody, generated: JsonObject, sourceVersion: '2.1.280' | '2.1.293' = '2.1.293'): JsonObject {
  const attribution = readNativeInput(generated, 'local_base_url', sourceVersion);
  if (!attribution || attribution.billingIndex < 0 || !Array.isArray(generated.system)) throw new BridgeError('native_identity', '无法取得同次SDK归因上下文', 503);
  const body = structuredClone(requested);
  // CLI的历史构造器只接受user/assistant；借用发送上下文后原位保留API的system，避免降级为user或提前生效。
  const system = body.system === undefined ? generated.system : [generated.system[attribution.billingIndex], ...(typeof body.system === 'string' ? [{ type: 'text', text: body.system }] : body.system)];
  const result: MessageBody = { ...(typeof generated.max_tokens === 'number' ? { max_tokens: generated.max_tokens } : {}), ...body, metadata: generated.metadata, system, tools: body.tools ?? [] };
  // 复用同次上下文的CCH占位处理，不能把种子正文的已计算值带到真实API正文。
  return prepareNativeBody(result, generated.metadata, 'local_base_url', generated.system, sourceVersion);
}

function keys(value: JsonObject, allowed: string[]): void {
  if (Object.keys(value).some(key => !allowed.includes(key))) throw new BridgeError('unsupported_parameter', 'context_management 包含当前版本未支持的字段', 422);
}

function count(value: unknown, type: string[], positive = false): boolean {
  return isObject(value) && Object.keys(value).length === 2 && typeof value.type === 'string' && type.includes(value.type) && typeof value.value === 'number' && Number.isSafeInteger(value.value) && value.value >= (positive ? 1 : 0);
}

/** 校验普通 API 明确支持的两类历史管理指令，保留原参数。
 * @param value 调用方的历史管理对象。
 * @return 无；未知策略或畸形参数在发送前拒绝。
 */
export function validateContextManagement(value: unknown): void {
  const invalid = (): never => { throw new BridgeError('invalid_context_management', 'context_management 参数结构不合法', 400); };
  if (!isObject(value)) invalid();
  const config = value as JsonObject;
  keys(config, ['edits']);
  if (config.edits === undefined) return;
  if (!Array.isArray(config.edits)) invalid();
  let thinking = false;
  for (const [index, raw] of (config.edits as unknown[]).entries()) {
    if (!isObject(raw)) invalid();
    const edit = raw as JsonObject;
    if (edit.type === 'clear_thinking_20251015') {
      keys(edit, ['type', 'keep']);
      if (thinking || index !== 0) invalid();
      thinking = true;
      if (edit.keep !== undefined && edit.keep !== 'all' && !count(edit.keep, ['thinking_turns'], true)) invalid();
    } else if (edit.type === 'clear_tool_uses_20250919') {
      keys(edit, ['type', 'trigger', 'keep', 'clear_at_least', 'exclude_tools', 'clear_tool_inputs']);
      if (edit.trigger !== undefined && !count(edit.trigger, ['input_tokens', 'tool_uses'])) invalid();
      if (edit.keep !== undefined && !count(edit.keep, ['tool_uses'])) invalid();
      if (edit.clear_at_least !== undefined && !count(edit.clear_at_least, ['input_tokens'])) invalid();
      if (edit.exclude_tools !== undefined && (!Array.isArray(edit.exclude_tools) || !edit.exclude_tools.every(item => typeof item === 'string' && item.length > 0))) invalid();
      if (edit.clear_tool_inputs !== undefined && typeof edit.clear_tool_inputs !== 'boolean') invalid();
    } else throw new BridgeError('unsupported_parameter', '当前版本未支持该 context_management 策略', 422);
  }
}

/** 普通 API 身份归运行时所有，先提取明确的会话关联再删除调用方 metadata。
 * @param body 已复制的普通 API 正文。
 * @param context 已复制的显式上下文。
 * @return 无；原调用方对象保持原样，冲突会话明确拒绝。
 */
export function normalizeApiMetadata(body: JsonObject, context: ContextInput): void {
  if (body.metadata === undefined) return;
  if (!isObject(body.metadata) || (body.metadata.user_id !== undefined && typeof body.metadata.user_id !== 'string')) throw new BridgeError('invalid_metadata', 'metadata 必须为对象且 user_id 必须为字符串', 400, 'native_metadata_invalid');
  const user = body.metadata.user_id;
  let session: unknown;
  if (typeof user === 'string') {
    try {
      const parsed: unknown = JSON.parse(user);
      if (isObject(parsed)) session = parsed.session_id;
    } catch { session = /^user_.*_session_(.+)$/.exec(user)?.[1]; }
  }
  if (session !== undefined) {
    if (typeof session !== 'string') throw new BridgeError('invalid_metadata', 'metadata 中的会话必须为字符串', 400);
    if (context.sessionId !== undefined && context.sessionId !== session) throw new BridgeError('context_conflict', 'metadata 会话与显式上下文冲突', 400);
    context.sessionId = session;
  }
  delete body.metadata;
}

/** 在同次官方 SDK 构造后保留已验证的显式历史管理指令。
 * @param requested 普通 API 的显式参数。
 * @param generated 官方 SDK 同次构造的正文。
 * @param headers 官方 SDK 同次构造的请求头。
 * @return 应用于同次发送的正文；能力不足时明确拒绝。
 */
export function applyContextManagement(requested: JsonObject, generated: JsonObject, headers: Headers): JsonObject {
  if (requested.context_management === undefined) return generated;
  const tokens = new Set((headers.get('anthropic-beta') ?? '').split(',').map(token => token.trim()));
  if (!tokens.has('context-management-2025-06-27')) throw new BridgeError('unsupported_parameter', '当前原生模型请求未提供 context_management 能力', 422);
  const config = requested.context_management as JsonObject;
  const clearsThinking = Array.isArray(config.edits) && config.edits.some(edit => isObject(edit) && edit.type === 'clear_thinking_20251015');
  if (clearsThinking && (!isObject(generated.thinking) || !['enabled', 'adaptive'].includes(String(generated.thinking.type)))) throw new BridgeError('unsupported_parameter', '清理 thinking 历史需要同次原生请求启用 thinking', 422);
  return { ...generated, context_management: structuredClone(config) };
}
