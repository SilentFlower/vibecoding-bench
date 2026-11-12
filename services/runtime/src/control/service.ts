import type { HeaderPair, PreparedInput, RuntimeEvent, NativeIngressPolicy } from '../shared/contracts';
import { BridgeError, errorText } from '../shared/errors';
import { parseInput } from '../shared/input';
import { prepareInput } from './header-policy';
import type { Engine } from './engine';
import { LogStore } from './log-store';
import { RequestTrace, type FinalCaptureSample } from './trace';
import { selectUpstreamModel } from '../shared/upstream';

/** 串行服务的请求预算和日志设置。 */
interface ServiceOptions {
  mode: 'off' | 'summary' | 'debug';
  maxBodyBytes: number;
  timeoutMs: number;
  secrets?: Record<string, unknown>;
  nativeIngressPolicy?: NativeIngressPolicy;
  modelOverride?: string;
  finalCapture?: (requestId: string) => FinalCaptureSample | null;
}

const HOP_HEADERS = new Set(['connection', 'keep-alive', 'proxy-connection', 'transfer-encoding', 'te', 'trailer', 'upgrade', 'content-length', 'content-encoding', 'set-cookie']);

function responseChannel(cancel: (reason: unknown) => void): {
  readable: ReadableStream<Uint8Array>;
  write(chunk: Uint8Array): Promise<void>;
  close(): void;
  abort(reason: unknown): void;
} {
  let control!: ReadableStreamDefaultController<Uint8Array>;
  let demand = false;
  let ended = false;
  let pending: { chunk: Uint8Array; resolve(): void; reject(reason: unknown): void } | null = null;
  const deliver = (): void => {
    if (!demand || !pending || ended) return;
    const item = pending; pending = null; demand = false;
    control.enqueue(item.chunk); item.resolve();
  };
  const finish = (reason?: unknown): void => {
    if (ended) return;
    ended = true;
    pending?.reject(reason ?? new DOMException('响应已结束', 'AbortError')); pending = null;
    // 取消后直接结束逻辑字节流，不额外拼接 SSE。未确认终态由日志和调用方分别判断。
    control.close();
  };
  const readable = new ReadableStream<Uint8Array>({
    start(value) { control = value; },
    pull() { demand = true; deliver(); },
    cancel(reason) {
      if (ended) return;
      ended = true;
      pending?.reject(reason); pending = null;
      cancel(reason);
    },
  }, { highWaterMark: 0 });
  return {
    readable,
    write(chunk) {
      if (ended) return Promise.reject(new DOMException('响应已取消', 'AbortError'));
      if (pending) return Promise.reject(new BridgeError('runtime_protocol', '运行时未等待上一段响应完成', 502));
      return new Promise<void>((resolve, reject) => { pending = { chunk, resolve, reject }; deliver(); });
    },
    close: () => finish(),
    abort: reason => finish(reason),
  };
}

/** 保留响应逻辑字节所对应的端到端头。
 * @param incoming 运行时返回的响应头。
 * @return 可在当前 HTTP 连接发送的头。
 */
export function responseHeaders(incoming: HeaderPair[]): Headers {
  const blocked = new Set(HOP_HEADERS);
  for (const [name, value] of incoming) if (name.toLowerCase() === 'connection') for (const token of value.split(',')) blocked.add(token.trim().toLowerCase());
  const result = new Headers();
  for (const [name, value] of incoming) if (!blocked.has(name.toLowerCase())) result.append(name, value);
  return result;
}

/** 单账号串行控制器，日志与响应共享一个请求归属。 */
export class BridgeService {
  private queue: Promise<void> = Promise.resolve();
  private readonly controllers = new Set<AbortController>();
  private readonly recentIds = new Set<string>();
  private closing = false;

  /** 绑定引擎与异步日志存储。
   * @param engine 实际执行引擎。
   * @param store 日志存储。
   * @param options 模式、采集限制及超时。
   */
  constructor(private readonly engine: Engine, private readonly store: LogStore, private readonly options: ServiceOptions) {}

  /** 提交一个 API 请求，响应正文按原始逻辑字节流式返回。
   * @param raw JSON 业务正文或信封。
   * @param headers 入站头。
   * @param external 调用方取消信号。
   * @param ingressText HTTP 入口原始 UTF-8 正文，保留空白与转义表示。
   * @return 带关联 ID 的 HTTP 响应。
   */
  async submit(raw: unknown, headers: HeaderPair[] = [], external = new AbortController().signal, ingressText?: string): Promise<Response> {
    let prepared: PreparedInput;
    try {
      if (this.closing) throw new BridgeError('service_closing', '服务正在关闭，不再接收作业', 503);
      prepared = selectUpstreamModel(prepareInput(parseInput(raw, headers, this.options.nativeIngressPolicy)), this.options.modelOverride);
      if (this.recentIds.has(prepared.input.request_id) || this.store.exists(prepared.input.request_id)) throw new BridgeError('duplicate_request', 'request_id 已使用，不能覆盖已有日志', 409);
    } catch (error) {
      const trace = new RequestTrace(null, raw, headers, this.store, { ...this.options, ingressText, engine: this.engine.name, binarySha256: this.engine.binarySha256 });
      trace.finish('error', errorText(error));
      return this.errorResponse(error, trace);
    }
    this.recentIds.add(prepared.input.request_id);
    if (this.recentIds.size > 10000) this.recentIds.delete(this.recentIds.values().next().value!);
    const trace = new RequestTrace(prepared, raw, headers, this.store, { ...this.options, ingressText, engine: this.engine.name, binarySha256: this.engine.binarySha256 });
    const controller = new AbortController();
    this.controllers.add(controller);
    const cancel = (): void => controller.abort(external.reason);
    external.addEventListener('abort', cancel, { once: true });
    if (external.aborted) cancel();
    const deadline = this.options.timeoutMs > 0 ? setTimeout(() => controller.abort(new BridgeError('request_timeout', '请求超过运行预算', 504)), this.options.timeoutMs) : undefined;
    const channel = responseChannel(reason => controller.abort(reason));
    let resolveHeaders!: (value: { status: number; headers: Headers }) => void;
    let rejectHeaders!: (error: unknown) => void;
    const receivedHeaders = new Promise<{ status: number; headers: Headers }>((resolve, reject) => { resolveHeaders = resolve; rejectHeaders = reject; });
    let gotHeaders = false;
    let terminal = false;
    const stopResponse = (): void => {
      const reason = controller.signal.reason ?? new DOMException('请求已取消', 'AbortError');
      rejectHeaders(reason);
      channel.abort(reason);
    };
    controller.signal.addEventListener('abort', stopResponse, { once: true });
    if (controller.signal.aborted) stopResponse();
    this.queue = this.queue.catch(() => {}).then(async () => {
      try {
        if (controller.signal.aborted) throw controller.signal.reason ?? new DOMException('请求已取消', 'AbortError');
        trace.start();
        await this.engine.run(prepared, controller.signal, async (event: RuntimeEvent) => {
          // TLS 实收先于池响应；提前保存可避免响应的敏感标志值影响此前请求的预览。
          if (event.type === 'response_headers' && this.options.finalCapture) trace.finalCapture(() => this.options.finalCapture!(trace.row.id));
          trace.event(event);
          if (event.type === 'final_capture_ready') {
            if (this.options.finalCapture) trace.finalCapture(() => this.options.finalCapture!(trace.row.id));
          } else if (event.type === 'response_headers') {
            if (gotHeaders) throw new BridgeError('runtime_protocol', '运行时重复返回响应头', 502);
            gotHeaders = true;
            const outgoing = responseHeaders(event.headers);
            outgoing.set('x-ccrb-request-id', trace.row.id);
            outgoing.set('x-ccrb-engine', this.engine.name);
            resolveHeaders({ status: event.status, headers: outgoing });
          } else if (event.type === 'response_chunk') {
            if (!gotHeaders) throw new BridgeError('runtime_protocol', '运行时在响应头前返回正文', 502);
            if ([204, 205, 304].includes(trace.row.httpStatus!)) throw new BridgeError('runtime_protocol', '无正文 HTTP 状态不能附带响应片段', 502);
            await channel.write(Buffer.from(event.data_b64, 'base64'));
          } else if (event.type === 'error') {
            throw new BridgeError(event.code ?? 'native_error', event.error, event.status ?? 502);
          } else if (event.type === 'completed') {
            terminal = true;
            if (this.options.finalCapture) trace.finalCapture(() => this.options.finalCapture!(trace.row.id));
            const timedOut = controller.signal.reason instanceof BridgeError;
            trace.finish(timedOut ? 'error' : event.state, timedOut ? errorText(controller.signal.reason) : event.error);
          }
        });
        if (!terminal || !gotHeaders) throw new BridgeError('runtime_protocol', '运行时缺少响应或完整终态', 502);
        channel.close();
      } catch (error) {
        const canceled = controller.signal.aborted && !(controller.signal.reason instanceof BridgeError);
        if (this.options.finalCapture) trace.finalCapture(() => this.options.finalCapture!(trace.row.id));
        trace.finish(canceled ? 'canceled' : 'error', errorText(controller.signal.reason ?? error));
        rejectHeaders(error);
        controller.abort();
        channel.abort(error);
      } finally {
        clearTimeout(deadline);
        external.removeEventListener('abort', cancel);
        controller.signal.removeEventListener('abort', stopResponse);
        this.controllers.delete(controller);
      }
    });
    try {
      const result = await receivedHeaders;
      return new Response([204, 205, 304].includes(result.status) ? null : channel.readable, { status: result.status, headers: result.headers });
    } catch (error) {
      return this.errorResponse(error, trace);
    }
  }

  private errorResponse(error: unknown, trace: RequestTrace): Response {
    const code = error instanceof BridgeError ? error.code : 'bridge_error';
    return Response.json({ type: 'error', error: { type: code, message: trace.redactor.text(errorText(error)) }, request_id: trace.row.id }, { status: error instanceof BridgeError ? error.status : 502, headers: { 'x-ccrb-request-id': trace.row.id, 'cache-control': 'no-store' } });
  }

  /** 停止接收中的作业并等待取消收口。
   * @return 当前串行队列结束。
   */
  async close(): Promise<void> {
    this.closing = true;
    for (const controller of this.controllers) controller.abort();
    await this.queue;
    await this.engine.close();
  }
}
