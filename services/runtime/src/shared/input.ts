import { randomUUID } from 'node:crypto';
import type { ApiMessage, BridgeInput, ContextInput, HeaderPair, MessageBody, NativeIngressPolicy } from './contracts';
import { BridgeError, isObject } from './errors';
import { readNativeInput, mergeNativeContext } from './native-input';

const BODY_KEYS = new Set(['model', 'messages', 'system', 'tools', 'tool_choice', 'max_tokens', 'thinking', 'temperature', 'output_config', 'stream']);
const CLIENT_SETTINGS_KEYS = ['settings', 'claude_settings', 'env'] as const;
const CONTEXT_KEYS = new Set(['requestClass', 'sessionId', 'promptId', 'agentId', 'parentAgentId', 'agentType', 'agentKind', 'workflowRunId']);
export const REQUEST_CLASSES = ['main', 'subagent', 'workflow', 'compaction', 'auxiliary', 'side_reply'] as const;

function validateKeys(value: Record<string, unknown>, allowed: Set<string>, owner: string): void {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new BridgeError('unsupported_parameter', owner + ' 暂不支持字段：' + key, 422);
  }
}

/** 从未知 JSON 建立唯一的请求合同。
 * @param raw API 正文或包含 body 的内部信封。
 * @param incomingHeaders HTTP 入口携带的头。
 * @param nativeIngressPolicy 启动侧选择的原生入站策略，默认严格。
 * @return 已验证、尚未应用头部策略的输入。
 */
export function parseInput(raw: unknown, incomingHeaders: HeaderPair[] = [], nativeIngressPolicy: NativeIngressPolicy = 'strict'): BridgeInput {
  if (!isObject(raw)) throw new BridgeError('invalid_request', '请求必须是 JSON 对象');
  const envelope = 'body' in raw && !('model' in raw || 'messages' in raw) ? raw : { body: raw };
  validateKeys(envelope, new Set(['schema_version', 'request_id', 'body', 'headers', 'context']), '信封');
  if (envelope.schema_version !== undefined && envelope.schema_version !== 1) throw new BridgeError('schema_version', '不支持的内部协议版本');
  if (!isObject(envelope.body)) throw new BridgeError('invalid_body', 'body 必须是对象');
  const body = { ...envelope.body };
  // 本机设置由账号运行时管理；只清理正文根字段，保留原始入站及嵌套业务数据。
  for (const key of CLIENT_SETTINGS_KEYS) delete body[key];
  const native = readNativeInput(body, nativeIngressPolicy);
  if (!native) validateKeys(body, BODY_KEYS, '正文');
  if (typeof body.model !== 'string' || !body.model.trim()) throw new BridgeError('invalid_model', 'model 必须是非空字符串');
  if (!Array.isArray(body.messages) || body.messages.length === 0) throw new BridgeError('invalid_messages', 'messages 必须是非空数组');
  const messages: ApiMessage[] = body.messages.map((message: unknown) => {
    if (!isObject(message) || !(native ? ['user', 'assistant', 'system'] : ['user', 'assistant']).includes(String(message.role))) throw new BridgeError('invalid_message', '消息 role 不属于当前接入类型支持的角色');
    if (!native) validateKeys(message, new Set(['role', 'content']), '消息');
    if (typeof message.content !== 'string' && (!Array.isArray(message.content) || !message.content.every(isObject))) throw new BridgeError('invalid_content', '消息 content 必须是文本或内容块数组');
    return { ...message, role: message.role as ApiMessage['role'], content: message.content as ApiMessage['content'] };
  });
  if (body.system !== undefined && typeof body.system !== 'string' && (!Array.isArray(body.system) || !body.system.every(isObject))) throw new BridgeError('invalid_system', 'system 必须是文本或文本块数组');
  if (body.tools !== undefined && (!Array.isArray(body.tools) || !body.tools.every(isObject))) throw new BridgeError('invalid_tools', 'tools 必须是对象数组');
  for (const key of ['thinking', 'tool_choice', 'output_config']) {
    if (body[key] !== undefined && !isObject(body[key])) throw new BridgeError('invalid_parameter', key + ' 必须是对象');
  }
  if (body.max_tokens !== undefined && (typeof body.max_tokens !== 'number' || !Number.isFinite(body.max_tokens))) throw new BridgeError('invalid_max_tokens', 'max_tokens 必须是有限数值');
  if (body.temperature !== undefined && (typeof body.temperature !== 'number' || !Number.isFinite(body.temperature))) throw new BridgeError('invalid_temperature', 'temperature 必须是有限数值');
  if (body.stream !== undefined && typeof body.stream !== 'boolean') throw new BridgeError('invalid_stream', 'stream 必须为布尔值');
  const context = envelope.context ?? {};
  if (!isObject(context)) throw new BridgeError('invalid_context', 'context 必须是对象');
  validateKeys(context, CONTEXT_KEYS, '上下文');
  for (const [key, value] of Object.entries(context)) {
    if (typeof value !== 'string' || !value.trim() || value.length > 512 || /[\0-\x1f\x7f]/.test(value) || [...value].some(char => char.charCodeAt(0) > 255)) throw new BridgeError('invalid_context', '上下文字段不合法：' + key);
  }
  if (context.requestClass !== undefined && !REQUEST_CLASSES.includes(context.requestClass as typeof REQUEST_CLASSES[number])) throw new BridgeError('unsupported_context', '当前版本不支持该请求类别', 422);
  if (context.agentKind !== undefined && !['main', 'subagent', 'teammate'].includes(String(context.agentKind))) throw new BridgeError('invalid_context', '不支持的 agentKind');
  const rawHeaders = envelope.headers ?? incomingHeaders;
  if (!Array.isArray(rawHeaders) || !rawHeaders.every(pair => Array.isArray(pair) && pair.length === 2 && pair.every(x => typeof x === 'string'))) throw new BridgeError('invalid_headers', 'headers 必须是二元字符串数组');
  const id = envelope.request_id ?? randomUUID();
  if (typeof id !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(id)) throw new BridgeError('invalid_request_id', 'request_id 格式不合法');
  return {
    schema_version: 1,
    request_id: id,
    body: { ...body, messages } as unknown as MessageBody,
    headers: rawHeaders.map(pair => [pair[0], pair[1]]) as HeaderPair[],
    context: native ? mergeNativeContext(context as ContextInput, native) : context as ContextInput,
    inputFormat: native ? 'claude_code' : 'api',
    ...(native && nativeIngressPolicy !== 'strict' ? { nativeIngressPolicy } : {}),
  };
}
