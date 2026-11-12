import { createServer } from 'node:https';
import { connect } from 'node:tls';
import { readFile, readlink, chmod } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import { once } from 'node:events';
import type { ServerResponse, IncomingMessage } from 'node:http';
import type { HeaderPair } from '../../src/shared/contracts';
import { BridgeError, isObject } from '../../src/shared/errors';
import { Redactor } from '../../src/control/redaction';
import { BodyCapture, POOL_MODEL, POOL_FAILURE_CODES, REQUEST_LIMIT, preparePoolRequest, sample, validatePoolConfig, type ForwarderFrame, type PoolConfig, type PoolPrepared } from './pool-common';
import { PoolTransportObserver } from './pool-transport';
import { LocalPoolStartupError, type LocalPoolStartupStage } from './local-pool-startup';

/** 独立 Node 接收端的启动合同，不经命令行传递池 Key。 */
interface Setup { type: 'init'; socketPath: string; keyFile: string; certFile: string; config: PoolConfig }
/** 一次收到完整实体、等待宿主核验 CCH 的请求。 */
interface Pending { id: number; request: IncomingMessage; response: ServerResponse; raw: string; headers: HeaderPair[]; abort: AbortController; timer: ReturnType<typeof setTimeout> | undefined; started: boolean }

const send = async (frame: ForwarderFrame): Promise<void> => { if (!process.stdout.write(JSON.stringify(frame) + '\n')) await once(process.stdout, 'drain'); };
let startupStage: LocalPoolStartupStage | null = 'forwarder_start';

/** 运行有限验收或显式手工联调的 Node TLS 转发器。 @return 父管道关闭后资源已收口。 */
async function main(): Promise<void> {
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const iterator = input[Symbol.asyncIterator]();
  const first = await iterator.next();
  const value: unknown = JSON.parse(first.value ?? 'null');
  if (!isObject(value) || value.type !== 'init' || !['socketPath','keyFile','certFile'].every(k => typeof value[k] === 'string') || !isObject(value.config)) throw new LocalPoolStartupError('forwarder_start', 'INIT_FRAME_INVALID');
  const setup = value as unknown as Setup;
  validatePoolConfig(setup.config);
  startupStage = 'certificate';
  const cert = await readFile(setup.certFile), key = await readFile(setup.keyFile);
  const pending = new Map<number, Pending>();
  const active = new Set<Promise<void>>();
  let sequence = 0, attempts = 0, closing = false;
  const expected = ['Host','api.anthropic.com','X-Dup','one','x-dUP','two','Content-Length','2','Connection','close'];
  let probeMatched = false;
  startupStage = 'tls_listen';
  const server = createServer({ key, cert, ALPNProtocols: ['http/1.1'] }, (request, response) => {
    const chunks: Buffer[] = []; let bytes = 0;
    request.on('data', (chunk: Buffer) => { bytes += chunk.length; if (setup.config.mode === 'manual' || bytes <= REQUEST_LIMIT) chunks.push(chunk); else request.destroy(); });
    request.on('error', () => { response.destroy(); });
    request.on('end', () => {
      if (request.url === '/__raw_headers_probe') {
        probeMatched = JSON.stringify(request.rawHeaders) === JSON.stringify(expected);
        response.writeHead(200, { Connection: 'close' }); response.end('{}'); return;
      }
      if (closing || request.method !== 'POST' || new URL(request.url ?? '/', 'https://api.anthropic.com').pathname !== '/v1/messages' || (request.headers['content-encoding'] && request.headers['content-encoding'] !== 'identity')) { response.writeHead(400); response.end('{"error":"采集路径或编码不支持"}'); return; }
      const rawBytes = Buffer.concat(chunks);
      let raw: string;
      try { raw = new TextDecoder('utf-8', { fatal: true }).decode(rawBytes); } catch { response.writeHead(400); response.end('{"error":"正文不是完整UTF-8"}'); return; }
      const headers: HeaderPair[] = [];
      for (let i = 0; i < request.rawHeaders.length; i += 2) headers.push([request.rawHeaders[i]!, request.rawHeaders[i + 1]!]);
      const id = ++sequence, abort = new AbortController();
      const item: Pending = { id, request, response, raw, headers, abort, started: false, timer: setup.config.mode === 'manual' ? undefined : setTimeout(() => { abort.abort('verification_timeout'); if (!item.started && !response.destroyed) { response.writeHead(504); response.end('{"error":"CCH核验未收口"}'); } }, 5000) };
      pending.set(id, item);
      response.on('close', () => { if (!response.writableFinished) abort.abort('caller_cancel'); });
      void send({ type: 'captured', id, method: request.method!, path: request.url!, httpVersion: request.httpVersion, headers, body: raw }).catch(() => response.destroy());
    });
  });
  server.requestTimeout = setup.config.mode === 'manual' ? 0 : 30000;
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(setup.socketPath, () => { server.off('error', reject); resolve(); });
  }); await chmod(setup.socketPath, 0o600);
  startupStage = 'tls_probe';
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => { socket.destroy(); reject(new LocalPoolStartupError('tls_probe', 'CHANNEL_TIMEOUT')); }, 5000);
    const socket = connect({ path: setup.socketPath, servername: 'api.anthropic.com', ca: cert }, () => socket.write('POST /__raw_headers_probe HTTP/1.1\r\nHost: api.anthropic.com\r\nX-Dup: one\r\nx-dUP: two\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}'));
    socket.on('data', () => {}); socket.on('error', error => { clearTimeout(timer); reject(error); });
    socket.on('end', () => { clearTimeout(timer); if (probeMatched) resolve(); else reject(new LocalPoolStartupError('tls_probe', 'RAW_HEADERS_MISMATCH')); });
  });
  startupStage = 'forwarder_verify';
  await send({ type: 'ready', namespace: await readlink('/proc/self/ns/net'), rawHeadersMatched: probeMatched });
  startupStage = null;

  const forward = async (item: Pending, allowed: boolean, reason?: string): Promise<void> => {
    // 响应标志头也可能被通用规则识别为秘密，不能污染下一请求的正文预览。
    const redactor = new Redactor(); redactor.register({ api_key: setup.config.apiKey });
    item.started = true; clearTimeout(item.timer);
    item.timer = setup.config.timeoutMs > 0 ? setTimeout(() => item.abort.abort('pool_timeout'), setup.config.timeoutMs) : undefined;
    const capture = new BodyCapture(); let complete = false, statusCode = 502, upstreamStatus: number | null = null, outcome = 'error', error: string | undefined, failureCode: string | undefined, prepared: PoolPrepared | undefined, responseHeaders: HeaderPair[] = [], attempted = false;
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    let transport: PoolTransportObserver | undefined;
    try {
      if (!allowed) throw new BridgeError(reason === 'budget_exhausted' ? 'pool_budget_exhausted' : 'request_rejected', reason === 'budget_exhausted' ? '本次池联调额度已用尽' : reason === 'invalid_request' ? '请求无法转换为池 Messages 请求' : '原生最终请求未通过独立核验', reason === 'budget_exhausted' ? 429 : 400);
      if (setup.config.maxRequests !== null && attempts >= setup.config.maxRequests) throw new BridgeError('pool_budget_exhausted', '本次池请求次数达到上限', 429);
      const outgoing = preparePoolRequest(item.raw, item.headers, item.request.url!, setup.config);
      outgoing.headers.push(['connection', 'close']); outgoing.changes.push({ name: 'connection', reason: '测试池每次独立连接，避免复用陈旧连接' });
      prepared = { url: outgoing.url, model: POOL_MODEL, headers: redactor.headers(outgoing.headers), body: sample(outgoing.body, redactor), changes: outgoing.changes };
      if (item.abort.signal.aborted) throw new Error('调用方已取消');
      attempts++; attempted = true;
      transport = new PoolTransportObserver();
      const upstream = await transport.run(() => fetch(outgoing.url, { method: 'POST', headers: outgoing.headers, body: outgoing.body, redirect: 'manual', signal: item.abort.signal }));
      statusCode = upstream.status; upstreamStatus = upstream.status;
      // fetch 已返回解压后的逻辑字节，长度和编码不能照搬到本地响应。
      const blocked = new Set(['content-length','content-encoding','connection','keep-alive','transfer-encoding','proxy-connection','te','trailer','upgrade','set-cookie','location']);
      for (const token of (upstream.headers.get('connection') ?? '').split(',')) blocked.add(token.trim().toLowerCase());
      responseHeaders = [...upstream.headers.entries()].filter(([name]) => !blocked.has(name.toLowerCase())) as HeaderPair[];
      item.response.writeHead(statusCode, Object.fromEntries(responseHeaders));
      reader = upstream.body?.getReader();
      if (reader) while (true) {
        const next = await reader.read(); if (next.done) break;
        capture.push(next.value);
        if (item.response.destroyed) { item.abort.abort('caller_cancel'); throw new Error('调用方已取消'); }
        if (!item.response.write(next.value)) await once(item.response, 'drain', { signal: item.abort.signal });
      }
      complete = true; item.response.end();
      outcome = statusCode >= 300 && statusCode < 400 ? 'redirect_blocked' : statusCode >= 400 ? 'http_error' : 'success';
    } catch (cause) {
      outcome = item.abort.signal.aborted ? item.abort.signal.reason === 'caller_cancel' ? 'canceled' : 'timeout' : 'error'; error = item.abort.signal.aborted ? '池转发已取消或超时' : cause instanceof BridgeError ? cause.message : '池转发未完成，请检查状态与配置';
      // 不保存任意异常 message；部分客户端会在异常内附带 URL、请求头或凭据。
      const fault = isObject(cause) && isObject(cause.cause) ? cause.cause : cause;
      failureCode = item.abort.signal.aborted ? outcome === 'canceled' ? 'CALLER_CANCELED' : 'POOL_TIMEOUT' : cause instanceof BridgeError ? cause.code.toUpperCase() : isObject(fault) && typeof fault.code === 'string' && POOL_FAILURE_CODES.has(fault.code) ? fault.code : attempted ? 'POOL_FETCH_ERROR' : 'REQUEST_REJECTED';
      if (!item.response.headersSent) { statusCode = cause instanceof BridgeError ? cause.status : allowed ? 502 : 400; item.response.writeHead(statusCode, { 'content-type': 'application/json', 'x-should-retry': 'false' }); item.response.end(JSON.stringify({ type: 'error', error: { type: failureCode, message: error } })); }
      else item.response.destroy();
    } finally {
      clearTimeout(item.timer); pending.delete(item.id);
      if (!complete) { item.abort.abort(); await reader?.cancel().catch(() => {}); }
      const transportDiagnostics = transport?.snapshot(); transport?.close();
      await send({ type: 'finished', id: item.id, attempted, outcome, ...(prepared ? { prepared } : {}), statusCode, upstreamStatus, headers: redactor.headers(responseHeaders), response: capture.finish(redactor, complete), ...(error ? { error } : {}), ...(failureCode ? { failureCode } : {}), ...(transportDiagnostics ? { transportDiagnostics } : {}) });
    }
  };
  try {
    while (true) {
      const next = await iterator.next(); if (next.done) break;
      const command: unknown = JSON.parse(next.value);
      if (!isObject(command)) throw new Error('采集控制帧不合法');
      if (command.type === 'shutdown') break;
      if ((command.type !== 'forward' && command.type !== 'reject') || !Number.isSafeInteger(command.id)) throw new Error('采集控制帧不合法');
      if (command.reason !== undefined && !['budget_exhausted','invalid_request','invalid_capture'].includes(String(command.reason))) throw new Error('采集拒绝原因不合法');
      const item = pending.get(Number(command.id));
      if (!item || item.started) throw new Error('采集请求归属不匹配');
      const task = forward(item, command.type === 'forward', command.reason as string | undefined); active.add(task); void task.finally(() => active.delete(task)).catch(() => {});
    }
  } finally {
    closing = true; input.close();
    for (const item of pending.values()) { clearTimeout(item.timer); item.abort.abort(); if (!item.started) item.response.destroy(); }
    await Promise.race([Promise.allSettled([...active]), new Promise(resolve => setTimeout(resolve, 1000))]);
    server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve()));
  }
}

void main().then(() => process.exit(0)).catch(async error => { await send({ type: 'fatal', message: 'TLS 采集转发器已失败', ...(startupStage === null ? {} : { startup: new LocalPoolStartupError(startupStage, error).startup }) }).catch(() => {}); process.exit(1); });
