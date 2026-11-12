import { createHash, randomUUID } from 'node:crypto';
import type { HeaderPair, JsonObject, PreparedInput, RuntimePayload } from '../../shared/contracts';
import { BridgeError, isObject } from '../../shared/errors';
import { Redactor } from '../../control/redaction';
import type { NativeBindings, NativeMessage, NativeRecord } from './native';
import { isNativeModelCall, prepareCli } from './cli';
import { prepareNativeBody } from '../../shared/native-input';
import { applyCachePolicy, rewriteCacheTtl } from '../../shared/cache-policy';
import type { CachePolicy, CacheTtlRewrite } from '../../shared/runtime-policy';
import type { NativeErrorStage } from '../../shared/native-error-diagnostics';

function unsupported(message: string): never {
  throw new BridgeError('unsupported_parameter', message, 422);
}

function systemTexts(value: PreparedInput['input']['body']['system']): string[] | undefined {
  if (value === undefined) return undefined;
  const values = typeof value === 'string' ? [value] : value.map(block => {
    if (block.type !== 'text' || typeof block.text !== 'string' || Object.keys(block).some(key => !['type', 'text'].includes(key))) unsupported('首版 system 内容块只支持 type/text；显式缓存边界不能静默丢弃');
    return block.text as string;
  });
  if (values.some(text => /^\s*x-anthropic-billing-header:/.test(text))) unsupported('首版接收业务 system，不接收已经归因封口的 CC system 前缀');
  // OM 将空段落数组解释为未提供 system；显式空输入使用 CLI --system-prompt '' 的原生表示。
  return values.length ? values : [''];
}

function subsetMismatch(expected: unknown, actual: unknown, path: string): string | undefined {
  if (isObject(expected)) {
    if (!isObject(actual)) return path;
    for (const [key, value] of Object.entries(expected)) {
      const mismatch = subsetMismatch(value, actual[key], path + '.' + key);
      if (mismatch) return mismatch;
    }
  } else if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || expected.length !== actual.length) return path;
    for (const [index, value] of expected.entries()) {
      const mismatch = subsetMismatch(value, actual[index], path + '[' + index + ']');
      if (mismatch) return mismatch;
    }
  } else if (expected !== actual) return path;
  return undefined;
}

function ensureSubset(expected: unknown, actual: unknown, path: string): void {
  const mismatch = subsetMismatch(expected, actual, path);
  if (mismatch) unsupported('原生 293 改变了显式参数：' + mismatch);
}

function normalizeContent(value: unknown): unknown {
  if (typeof value === 'string') return [{ type: 'text', text: value }];
  if (!Array.isArray(value)) return value;
  return value.map(block => isObject(block) && block.type === 'tool_result' && block.content !== undefined ? { ...block, content: normalizeContent(block.content) } : block);
}

function contentBlocks(messages: unknown): { role: string; block: unknown }[] {
  if (!Array.isArray(messages)) unsupported('原生 293 没有提供可核验的消息数组');
  return messages.flatMap(message => {
    if (!isObject(message) || typeof message.role !== 'string') unsupported('原生 293 没有提供可核验的消息角色');
    const content = normalizeContent(message.content);
    if (!Array.isArray(content)) unsupported('原生 293 没有提供可核验的消息内容');
    return content.map(block => ({ role: message.role as string, block }));
  });
}

function ensureBusinessRecords(expected: NativeMessage[], actual: NativeRecord[]): void {
  const identifiers = new Set(expected.map(message => message.uuid));
  const business = actual.filter(message => message.uuid && identifiers.has(message.uuid));
  ensureSubset(expected.map(message => ({ uuid: message.uuid, message: message.message })), business.map(message => ({ uuid: message.uuid, message: message.message })), 'business');
}

/** 还原原生附加提醒后的工具结果投影，只接受原业务前缀及同次构造中已知的完整提醒。
 * @param expected 调用方原始工具结果。
 * @param actual 原生归一化后的工具结果。
 * @param metadata 同次原生附件投影。
 * @param start 尚未消费的附件位置。
 * @return 可核验的原业务块及新附件位置，不能无损关联时为空。
 */
function toolResultProjection(expected: unknown, actual: unknown, metadata: { role: string; block: unknown }[], start: number): { block: unknown; next: number } | null {
  if (!isObject(expected) || !isObject(actual) || expected.type !== 'tool_result' || actual.type !== 'tool_result' || !Array.isArray(expected.content) || !Array.isArray(actual.content)) return null;
  const copy = structuredClone(actual);
  const content = copy.content as unknown[];
  let next = start;
  const consume = (text: string, separator: string): boolean => {
    let remaining = text;
    while (remaining) {
      const item = metadata[next];
      if (item?.role !== 'user' || !isObject(item.block) || item.block.type !== 'text' || typeof item.block.text !== 'string') return false;
      const prefix = separator + item.block.text.replace(/\n$/, '');
      if (!prefix || !remaining.startsWith(prefix)) return false;
      remaining = remaining.slice(prefix.length); next++; separator = '\n\n';
    }
    return true;
  };
  for (const [index, block] of expected.content.entries()) {
    const emitted = content[index];
    if (isObject(block) && block.type === 'text' && typeof block.text === 'string' && isObject(emitted) && emitted.type === 'text' && typeof emitted.text === 'string' && emitted.text.startsWith(block.text)) {
      if (!consume(emitted.text.slice(block.text.length), '\n\n')) return null;
      emitted.text = block.text;
    }
  }
  for (const block of content.slice(expected.content.length)) {
    if (!isObject(block) || block.type !== 'text' || typeof block.text !== 'string' || !consume(block.text.replace(/\n$/, ''), '')) return null;
  }
  content.length = expected.content.length;
  return subsetMismatch(expected, copy, 'messages') ? null : { block: copy, next };
}

/** 验证原生发送消息只包含完整业务历史及同次原生提醒，允许工具结果的已知提醒合并表示。
 * @param expected 原始业务消息。
 * @param nativeMetadata 同次构造的官方附件投影。
 * @param actual SDK 最终构造的消息数组。
 * @return 验证成功时无返回值，无法关联时明确拒绝。
 */
export function ensureMessages(expected: PreparedInput['input']['body']['messages'], nativeMetadata: NativeMessage[], actual: unknown): void {
  const business = contentBlocks(expected);
  const metadata = contentBlocks(nativeMetadata.map(message => message.message));
  let nextBusiness = 0, nextMetadata = 0;
  for (const item of contentBlocks(actual)) {
    const input = business[nextBusiness];
    // 工具续轮会把附件提醒合入 tool_result.content，不能把该原生表示误判为业务历史被改写。
    const projected = input?.role === item.role ? toolResultProjection(input.block, item.block, metadata, nextMetadata) : null;
    if (projected) { nextBusiness++; nextMetadata = projected.next; continue; }
    if (input?.role === item.role && !subsetMismatch(input.block, item.block, 'messages')) {
      nextBusiness++;
      continue;
    }
    // 原生提醒在独立消息和相邻用户块中可能带不同的收尾换行；只规范化已知原生段，业务正文仍逐字段核对。
    const normalizeReminder = (block: unknown): unknown => isObject(block) && block.type === 'text' && typeof block.text === 'string' ? { ...block, text: block.text.replace(/\n$/, '') } : block;
    let generated = metadata[nextMetadata];
    // 无其他上下文的续轮会将同一 Environment 附件从提醒包装提升为 system；只允许已知完整正文的这一转换。
    if (generated?.role === 'user' && item.role === 'system' && isObject(generated.block) && typeof generated.block.text === 'string') {
      const environment = /^<system-reminder>\n(# Environment\n[\s\S]*)\n<\/system-reminder>\n?$/.exec(generated.block.text);
      if (environment) generated = { role: 'system', block: { ...generated.block, text: environment[1] } };
    }
    if (generated?.role !== item.role || subsetMismatch(normalizeReminder(generated.block), normalizeReminder(item.block), 'native_metadata')) unsupported('原生 293 生成了无法关联到业务或原生提醒的消息块');
    nextMetadata++;
  }
  if (nextBusiness !== business.length || nextMetadata !== metadata.length) unsupported('原生 293 未保留完整的业务消息或原生提醒');
}

/** 原生首发参数；业务用途核对字段，种子用途只取得发送上下文。 */
interface NativeRequest { body: JsonObject; headers: Headers; agent: JsonObject }

/** 调用官方 CLI 首发构造，按用途核验后交给受控发送；没有回调时仅构造。
 * @param prepared 已验证的业务输入及上下文。
 * @param bindings 固定版本的 CLI 装配与发送接口。
 * @param signal 本轮独立取消信号。
 * @param send 可选的唯一发送回调，必须等原始响应消费收口后才返回。
 * @param purpose 业务构造或仅取得原生发送上下文；后者的种子正文不会发送。
 * @return 原版 CLI 构造出的参数及原生请求头。
 */
export async function generateNativeRequest(prepared: PreparedInput, bindings: NativeBindings, signal: AbortSignal, send?: (target: RequestInfo | URL, init: RequestInit, request: NativeRequest, cancel: () => void) => Promise<void>, purpose: 'business' | 'transport_context' = 'business'): Promise<NativeRequest> {
  const { body } = prepared.input;
  const thinking = body.thinking;
  const output = body.output_config ?? {};
  if (Object.keys(output).some(key => !['effort', 'format'].includes(key))) unsupported('首版 output_config 只支持 effort 和 format');
  if (signal.aborted) throw new DOMException('请求已取消', 'AbortError');
  const stop = new AbortController();
  const cancel = (): void => stop.abort(signal.reason);
  signal.addEventListener('abort', cancel, { once: true });
  if (signal.aborted) cancel();
  let captured: NativeRequest | undefined;
  let constructionError: unknown;
  let calls = 0;
  try {
    const cli = await prepareCli(prepared, bindings, systemTexts(body.system), thinking ? {
        ...structuredClone(thinking),
        type: thinking.type === 'disabled' ? 'disabled' : 'enabled',
        ...(thinking.budget_tokens !== undefined ? { budgetTokens: thinking.budget_tokens } : {}),
      } : undefined, stop);
    for await (const ignored of bindings.cliQuery.OM({
      messages: cli.messages, systemPrompt: cli.systemPrompt, userContext: cli.userContext, systemContext: cli.systemContext,
      toolUseContext: cli.toolContext, querySource: cli.querySource, maxTurns: 1,
      canUseTool: async () => { throw new Error('构造阶段禁止执行本地工具'); },
      deps: {
        autocompact: bindings.core.Cer, now: () => new Date().toISOString(), uuid: randomUUID,
        callModel: async function* (value: unknown) {
          if (++calls !== 1 || !isNativeModelCall(value)) throw new Error('原生 CLI 构造调用边界不匹配');
          if (purpose === 'business') ensureBusinessRecords(cli.business, value.messages);
          const identifiers = new Set(cli.business.map(message => message.uuid));
          const metadata = purpose === 'business' ? bindings.core.Ck(value.messages.filter(message => !message.uuid || !identifiers.has(message.uuid)), cli.nativeTools, body.model, { preserveTrailingThinking: true }) : [];
          for await (const event of bindings.core.K_t({ ...value, options: {
            ...value.options, model: body.model, querySource: cli.querySource, requestClass: prepared.context.requestClass,
            agentContext: cli.agent, extraToolSchemas: structuredClone(body.tools ?? []), toolChoice: structuredClone(body.tool_choice),
            maxOutputTokensOverride: body.max_tokens, temperatureOverride: body.temperature,
            effortValue: output.effort ?? value.options.effortValue, outputFormat: structuredClone(output.format), resumeIncompleteThinking: true,
            fetchOverride: async (target: RequestInfo | URL, init: RequestInit) => {
              try {
                if (typeof init.body !== 'string') throw new Error('原生构造器没有提供 JSON 正文');
                const result: unknown = JSON.parse(init.body);
                if (!isObject(result)) throw new Error('原生正文不是 JSON 对象');
                // 原生入站只借用此处的发送上下文；种子历史随后被完整替换，不能据其提醒布局拦截业务。
                if (purpose === 'business') {
                  // CLI 以省略表示关闭，普通 API 的明确值必须保留；只适配已知完整形状，避免吞掉扩展或覆盖原生不同值。
                  if (body.thinking?.type === 'disabled' && Object.keys(body.thinking).length === 1 && result.thinking === undefined) {
                    result.thinking = structuredClone(body.thinking);
                    init.body = JSON.stringify(result);
                  }
                  ensureMessages(body.messages, metadata, result.messages);
                  for (const key of ['max_tokens', 'temperature', 'tool_choice', 'output_config'] as const) {
                    if (body[key] !== undefined) ensureSubset(body[key], result[key], key);
                  }
                  // 省略也表示无工具，不能让原生默认声明绕过保留检查。
                  ensureSubset(body.tools ?? [], result.tools, 'tools');
                  if (body.thinking !== undefined) ensureSubset(body.thinking, result.thinking, 'thinking');
                }
                if (signal.aborted) throw new DOMException('请求已取消', 'AbortError');
                captured = { body: result, headers: new Headers(init.headers), agent: cli.agent };
                try {
                  if (send) await send(target, init, captured, () => stop.abort());
                } finally {
                  // SDK 永远拿不到响应；发送完成或失败后立即取消，禁止解析响应、模型重试及工具循环。
                  stop.abort();
                }
                throw new DOMException('原生首发已收口', 'AbortError');
              } catch (error) {
                // 查询循环可能把构造异常转换为助手事件；先取消并保留原异常，防止调用方只等到总超时。
                if (!captured) { constructionError = error; stop.abort(error); }
                throw error;
              }
            },
          } })) {
            if (!captured && isObject(event) && (event.type === 'model_fallback_triggered' || (event.type === 'assistant' && event.isApiErrorMessage === true))) {
              const category = typeof event.error === 'string' && /^[a-z_]{1,64}$/.test(event.error) ? event.error : 'native_error';
              constructionError = new BridgeError('native_construction', event.type === 'model_fallback_triggered' ? '当前桥接不启动隐式模型回退' : '原生构造器未接受当前参数：' + category, 422);
              stop.abort(constructionError);
              throw constructionError;
            }
            // 装配器不接收模型事件；响应由受控发送回调交给桥接独占读取。
            void event;
            if (captured) break;
          }
        },
      },
    })) {
      void ignored;
      if (captured) break;
    }
  } catch (error) {
    if (!captured) throw constructionError ?? error;
  } finally {
    signal.removeEventListener('abort', cancel);
  }
  if (signal.aborted) throw new DOMException('请求已取消', 'AbortError');
  if (constructionError) throw constructionError;
  if (!captured) throw new Error('原生 293 未能完成请求构造');
  return captured;
}

/** 运行一次模型作业，只有最终原生 SDK 发送阶段访问上游。
 * @param prepared 已经完成入口验证的作业。
 * @param bindings 固定来源原生绑定。
 * @param signal 本轮取消信号。
 * @param redactor 本轮秘密处理器。
 * @param emit 本轮有背压的事件输出。
 * @param cachePolicy 本机启动时固定的缓存策略。
 * @param cacheTtlRewrite 前置服务按本次设置冻结的已有缓存TTL覆盖。
 * @param onStage 记录实际失败边界的本地观察器。
 * @return 作业和流已收口。
 */
export async function runNativeJob(prepared: PreparedInput, bindings: NativeBindings, signal: AbortSignal, redactor: Redactor, emit: (payload: RuntimePayload) => Promise<void>, cachePolicy: CachePolicy = 'preserve', cacheTtlRewrite: CacheTtlRewrite = 'off', onStage: (stage: NativeErrorStage) => void = () => {}): Promise<void> {
  onStage('construction');
  redactor.register(prepared.input);
  redactor.register({ api_key: process.env.ANTHROPIC_API_KEY, token: process.env.CLAUDE_CODE_OAUTH_TOKEN });
  const { api } = bindings;
  const native = prepared.input.inputFormat === 'claude_code';
  // 原生正文已经包含业务提示词和历史。种子仅取得同一账号的发送上下文，其正文不会进入上游。
  const construction: PreparedInput = native ? { ...prepared, input: { ...prepared.input, inputFormat: 'api', body: { model: prepared.input.body.model, messages: [{ role: 'user', content: '初始化本次原生发送上下文' }], stream: prepared.input.body.stream === true } } } : prepared;
  let resolveResponse!: (response: Response) => void;
  let rejectResponse!: (error: unknown) => void;
  const responseReady = new Promise<Response>((resolve, reject) => { resolveResponse = resolve; rejectResponse = reject; });
  let release!: () => void;
  const released = new Promise<void>(resolve => { release = resolve; });
  let calls = 0;
  const sending = generateNativeRequest(construction, bindings, signal, async (target, init, generated, cancelNative) => {
    try {
      if (++calls !== 1) throw new Error('首版禁止隐式模型重试');
      const headers = generated.headers;
      if (native) {
        generated.body = prepareNativeBody(prepared.input.body, generated.body.metadata, prepared.input.nativeIngressPolicy, generated.body.system);
        init.body = JSON.stringify(generated.body);
        const beta = prepared.headers.filter(([name]) => name.toLowerCase() === 'anthropic-beta').map(([, value]) => value).join(',');
        if (beta) headers.set('anthropic-beta', beta);
      }
      for (const name of ['content-length', 'host']) headers.delete(name);
      const forwarded = new Headers();
      for (const [name, value] of prepared.headers) {
        const lower = name.toLowerCase();
        if (lower === 'anthropic-beta') {
          if (native) continue;
          const nativeTokens = new Set((headers.get(name) ?? '').split(','));
          if (value.split(',').map(x => x.trim()).some(token => !nativeTokens.has(token))) unsupported('当前原生参数无法表达请求携带的 anthropic-beta');
          continue;
        }
        if (lower === 'anthropic-version') {
          if (value !== headers.get(name)) unsupported('anthropic-version 与原生版本不一致');
          continue;
        }
        forwarded.append(name, value);
      }
      // 先保留调用方完整的多值表示，再覆盖 SDK 默认值，避免把同名默认头重复拼入。
      for (const [name, value] of forwarded) headers.set(name, value);
      // 保留原 SDK 的发送上下文，仅映射明确的响应模式及扩展头，不再创建第二个客户端。
      const stream = prepared.input.body.stream === true;
      const sendingBody = !native && generated.body.stream !== stream ? { ...generated.body, stream } : generated.body;
      const cache = applyCachePolicy(prepared.input.body, sendingBody, cachePolicy);
      const finalBody = rewriteCacheTtl(cache.body, cacheTtlRewrite);
      if (finalBody !== generated.body) init.body = JSON.stringify(finalBody);
      if (typeof init.body !== 'string') throw new Error('原生 SDK 发送正文不是字符串');
      init.headers = headers;
      // 单次发送合同要求由调用方处理重定向；原生 fetch 的自动跟随会产生未归属的第二次请求。
      init.redirect = 'manual';
      // SDK 的首响应预算等待 fetchOverride 返回；桥接独占读取完整响应时该回调仍挂起。
      // 出站只绑定本轮调用方取消，防止 SDK 构造计时器取消已正常返回的长流。
      const dispatch = new AbortController();
      init.signal = AbortSignal.any([signal, dispatch.signal]);
      const outgoing = [...headers.entries()] as HeaderPair[];
      redactor.register(outgoing);
      // 正文和头仅走私有管道；控制层先注册秘密，再统一脱敏持久化，避免重复扫描完整正文。
      const snapshot: RuntimePayload = { type: 'cc_prepared', attempt: 1, body: init.body, headers: outgoing, body_bytes: Buffer.byteLength(init.body), body_sha256: createHash('sha256').update(init.body).digest('hex'), cache_policy: cache.decision };
      const fail = (error: unknown): never => { dispatch.abort(); cancelNative(); throw error; };
      // 快照在 Ree 前固定；等待两方收口后才交付响应事件，失败时取消并释放未交付的响应。
      onStage('dispatch');
      const [written, sent] = await Promise.allSettled([emit(snapshot).catch(fail), (async () => api.Ree(target, init))().catch(fail)]);
      if (written.status === 'rejected') {
        onStage('construction');
        if (sent.status === 'fulfilled') await sent.value.body?.cancel().catch(() => {});
        throw written.reason;
      }
      if (sent.status === 'rejected') throw sent.reason;
      const response = sent.value;
      resolveResponse(response);
      // 原始响应由桥接器独占读取，SDK 不能提前消费错误正文或启动解析与重试。
      await released;
    } catch (error) {
      rejectResponse(error);
      throw error;
    }
  }, native ? 'transport_context' : 'business').catch(error => { rejectResponse(error); });
  let status = 0;
  let finalState: 'success' | 'http_error' | 'canceled' = 'success';
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  let drained = false;
  try {
    const response = await responseReady;
    onStage('response_headers');
    status = response.status;
    const responseHeaders = [...response.headers.entries()] as HeaderPair[];
    await emit({ type: 'response_headers', attempt: 1, status, headers: responseHeaders });
    onStage('response_body');
    reader = response.body?.getReader();
    if (reader) {
      while (true) {
        const next = await reader.read();
        if (next.done) { drained = true; break; }
        await emit({ type: 'response_chunk', attempt: 1, data_b64: Buffer.from(next.value).toString('base64') });
      }
    }
    finalState = status >= 300 ? 'http_error' : signal.aborted ? 'canceled' : 'success';
  } finally {
    // 失败或取消时主动释放响应，空闲确认必须晚于流与 SDK 的收口。
    if (reader) {
      if (!drained) await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    release();
    await sending;
  }
  await emit({ type: 'completed', attempt: 1, state: finalState });
}

