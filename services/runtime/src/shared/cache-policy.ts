import type { JsonObject } from './contracts';
import { isObject } from './errors';
import type { CachePolicy, CachePolicyDecision, CacheTtlRewrite } from './runtime-policy';

/** 在协议范围内覆盖已有缓存TTL，保持工具业务嵌套对象及断点位置。
 * @param body 已完成原生构造与缓存选点的正文。
 * @param mode 本次受信任策略。
 * @return 关闭时返回原对象；覆盖时返回独立正文。
 */
export function rewriteCacheTtl(body: JsonObject, mode: CacheTtlRewrite): JsonObject {
  if (mode === 'off') return body;
  const result = structuredClone(body);
  const rewrite = (block: unknown): void => {
    if (isObject(block) && isObject(block.cache_control) && block.cache_control.type === 'ephemeral') block.cache_control.ttl = mode;
  };
  rewrite(result);
  for (const field of ['system', 'tools'] as const) {
    if (Array.isArray(result[field])) for (const block of result[field]) rewrite(block);
  }
  if (Array.isArray(result.messages)) {
    for (const message of result.messages) {
      if (isObject(message) && Array.isArray(message.content)) for (const block of message.content) rewrite(block);
    }
  }
  return result;
}

/** 缓存策略返回值，跳过时直接保留原对象。 */
export interface CachePolicyResult {
  body: JsonObject;
  decision: CachePolicyDecision;
}

function messageMarkers(body: JsonObject): { top: number; nested: boolean } {
  let top = 0, nested = false;
  if (!Array.isArray(body.messages)) return { top, nested };
  for (const message of body.messages) {
    if (!isObject(message) || !Array.isArray(message.content)) continue;
    const pending: { blocks: unknown[]; depth: number }[] = [{ blocks: message.content, depth: 0 }];
    while (pending.length) {
      const { blocks, depth } = pending.pop()!;
      for (const block of blocks) {
        if (!isObject(block)) continue;
        if (Object.hasOwn(block, 'cache_control')) { if (depth) nested = true; else top++; }
        // 只沿协议内容块遍历，工具输入与 schema 中的同名业务字段不属于缓存指令。
        if (typeof block.type === 'string' && Array.isArray(block.content)) pending.push({ blocks: block.content, depth: depth + 1 });
      }
    }
  }
  return { top, nested };
}

function prefixBudget(body: JsonObject): { count: number; ttl: '5m' | '1h' } | null {
  let count = 0;
  let short = false;
  // 上游前缀按 tools → system → messages 形成；TTL 检查不能使用 JSON 键的排列顺序。
  for (const name of ['tools', 'system'] as const) {
    const value = body[name];
    if (value === undefined || (name === 'system' && typeof value === 'string')) continue;
    if (!Array.isArray(value)) return null;
    for (const block of value) {
      if (!isObject(block)) return null;
      if (!Object.hasOwn(block, 'cache_control')) continue;
      const cache = block.cache_control;
      if (!isObject(cache) || cache.type !== 'ephemeral' || Object.keys(cache).some(key => !['type', 'ttl', 'scope'].includes(key)) || (cache.scope !== undefined && typeof cache.scope !== 'string')) return null;
      if (cache.ttl !== undefined && cache.ttl !== '5m' && cache.ttl !== '1h') return null;
      if (short && cache.ttl === '1h') return null;
      if (cache.ttl !== '1h') short = true;
      count++;
    }
  }
  return { count, ttl: short ? '5m' : '1h' };
}

function candidate(message: JsonObject): number | null {
  if (message.role !== 'user' && message.role !== 'assistant') return null;
  if (typeof message.content === 'string') return message.content.length ? 0 : null;
  if (!Array.isArray(message.content)) return null;
  for (let block = message.content.length - 1; block >= 0; block--) {
    const value = message.content[block];
    if (!isObject(value)) continue;
    if (value.type === 'text' && typeof value.text === 'string' && value.text.length) return block;
    if (message.role === 'user' && value.type === 'tool_result') return block;
  }
  return null;
}

/** 在原生封口前应用保守缓存选点，调用方持有的消息断点优先。
 * @param original 调用方业务正文，用于判断断点所有权。
 * @param outgoing 已完成原生构造与业务字段校验的待发送正文。
 * @param mode 本机固定的缓存策略。
 * @return 未修改输入的正文及可审计诊断。
 */
export function applyCachePolicy(original: JsonObject, outgoing: JsonObject, mode: CachePolicy): CachePolicyResult {
  const decision: CachePolicyDecision = { mode, action: mode === 'preserve' ? 'preserved' : 'skipped', reason: 'policy_preserve', selected: [], breakpoints: null, ttl: null };
  const skip = (reason: CachePolicyDecision['reason'], count: number | null = null): CachePolicyResult => ({ body: outgoing, decision: { ...decision, reason, breakpoints: count } });
  if (mode === 'preserve') return { body: outgoing, decision };
  const owned = messageMarkers(original);
  if (owned.top || owned.nested) return skip('caller_message_breakpoints');
  if (Object.hasOwn(original, 'cache_control') || Object.hasOwn(outgoing, 'cache_control')) return skip('root_cache_control_present');
  const markers = messageMarkers(outgoing);
  const prefix = prefixBudget(outgoing);
  const messages = outgoing.messages;
  if (!prefix || markers.nested || !Array.isArray(messages) || messages.some(message => !isObject(message) || (typeof message.content !== 'string' && (!Array.isArray(message.content) || message.content.some(block => !isObject(block)))))) return skip('unsupported_cache_control');
  const count = prefix.count + markers.top;
  if (prefix.count >= 4) return skip('no_available_slots', count);
  const selected: CachePolicyDecision['selected'] = [];
  const indexes = messages.length ? [messages.length - 1] : [];
  if (messages.length >= 4) {
    let users = 0;
    for (let message = messages.length - 1; message >= 0; message--) {
      if (messages[message].role === 'user' && ++users === 2) { indexes.push(message); break; }
    }
  }
  for (const message of indexes) {
    const block = candidate(messages[message]);
    if (block !== null && selected.length < 4 - prefix.count && !selected.some(position => position.message === message && position.block === block)) selected.push({ message, block });
  }
  if (!selected.length) return skip('no_cacheable_blocks', count);
  selected.sort((a, b) => a.message - b.message || a.block - b.block);
  const rewritten = messages.map((message: JsonObject, index: number) => {
    const position = selected.find(item => item.message === index);
    if (typeof message.content === 'string') return position ? { ...message, content: [{ type: 'text', text: message.content, cache_control: { type: 'ephemeral', ttl: prefix.ttl } }] } : message;
    const content = message.content as JsonObject[];
    return { ...message, content: content.map((block, blockIndex) => {
      // 走到此处已证明调用方没有消息标记，待删除的仅为本轮 SDK 自动生成的断点。
      const { cache_control: unused, ...plain } = block;
      return position?.block === blockIndex ? { ...plain, cache_control: { type: 'ephemeral', ttl: prefix.ttl } } : plain;
    }) };
  });
  return { body: { ...outgoing, messages: rewritten }, decision: { ...decision, action: 'applied', reason: 'sub2api_tail', selected, breakpoints: prefix.count + selected.length, ttl: prefix.ttl } };
}
