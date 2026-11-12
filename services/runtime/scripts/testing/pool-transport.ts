import { AsyncLocalStorage } from 'node:async_hooks';
import { channel } from 'node:diagnostics_channel';
import { isObject } from '../../src/shared/errors';
import { POOL_TRANSPORT_PHASES, decodePoolTransportDiagnostics, type PoolTransportDiagnostics } from './pool-common';

/** 只观察当前模型 POST，不改变 fetch、连接策略或错误传播。 */
export class PoolTransportObserver {
  private readonly scope = new AsyncLocalStorage<boolean>();
  private requests = new WeakSet<object>();
  private readonly subscriptions: { source: ReturnType<typeof channel>; listener: (message: unknown) => void }[] = [];
  private phase: PoolTransportDiagnostics['phase'] = 'unknown';
  private bodySentObserved: boolean | null = null;
  private socket: Record<string, unknown> | null = null;
  private unavailable = false;
  private closed = false;

  /** 建立本次请求的临时订阅，观测不可用时仍允许原转发执行。 */
  constructor() {
    try {
      for (const [name, event] of [['undici:request:create', 'create'], ['undici:client:sendHeaders', 'sending'], ['undici:request:bodySent', 'awaiting_headers'], ['undici:request:headers', 'response_body']] as const) {
        const source = channel(name), listener = (message: unknown): void => this.observe(event, message);
        this.subscriptions.push({ source, listener }); source.subscribe(listener);
      }
    } catch { this.unavailable = true; this.close(); }
  }

  private observe(event: 'create' | 'sending' | 'awaiting_headers' | 'response_body', message: unknown): void {
    if (this.closed || this.unavailable) return;
    try {
      if (!isObject(message) || !isObject(message.request)) return;
      const request = message.request;
      if (event === 'create') {
        // CONNECT 可能共享异步作用域，但它不能提供模型正文的发送证据。
        if (this.scope.getStore() !== true || request.method !== 'POST') return;
        this.requests.add(request); this.phase = 'before_send'; this.bodySentObserved = false;
        return;
      }
      if (!this.requests.has(request)) return;
      if (event === 'sending' && isObject(message.socket)) this.socket = message.socket;
      if (event === 'awaiting_headers') this.bodySentObserved = true;
      if (event === 'response_body' && (!isObject(message.response) || typeof message.response.statusCode !== 'number' || message.response.statusCode < 200)) return;
      // sendHeaders 发布早于写入，只标记进入发送流程，不能称为对端实收。
      if (POOL_TRANSPORT_PHASES.indexOf(event) > POOL_TRANSPORT_PHASES.indexOf(this.phase)) this.phase = event;
    } catch { this.unavailable = true; }
  }

  /** 在本请求作用域执行原有操作。
   * @param operation 原有的单次 fetch 调用。
   * @return 原调用结果或原异常。
   */
  run<T>(operation: () => Promise<T>): Promise<T> { return this.closed ? operation() : this.scope.run(true, operation); }

  /** 仅提取白名单计数，不保存 socket、URL、请求或异常文本。
   * @return 明确区分未知与零值的观测快照。
   */
  snapshot(): PoolTransportDiagnostics {
    if (this.unavailable) return decodePoolTransportDiagnostics(null);
    try {
      // 只使用模型 POST 的 sendHeaders 事件关联的 socket，不采纳可能属于 CONNECT 的异常计数。
      const socket = this.socket;
      return decodePoolTransportDiagnostics({ phase: this.phase, bodySentObserved: this.bodySentObserved, connectionBytesWritten: socket?.bytesWritten, connectionBytesRead: socket?.bytesRead });
    } catch { return decodePoolTransportDiagnostics(null); }
  }

  /** 释放本次订阅和连接引用，避免后续请求污染当前观测。
   * @return 订阅与异步作用域均已释放。
   */
  close(): void {
    if (this.closed) return;
    this.closed = true;
    for (const { source, listener } of this.subscriptions) { try { source.unsubscribe(listener); } catch {} }
    this.requests = new WeakSet(); this.socket = null; this.scope.disable();
  }
}
