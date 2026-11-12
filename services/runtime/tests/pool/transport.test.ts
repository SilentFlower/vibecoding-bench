import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { mkdtemp, readFile, readlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { createServer as createHttpsServer } from 'node:https';
import { connect } from 'node:net';
import type { Duplex } from 'node:stream';
import { PrivateProcess } from '../../scripts/testing/pool-process';
import { startPoolFixture, type PoolFixture } from '../../scripts/testing/pool-fixture';
import { POOL_MODEL, REQUEST_LIMIT, decodeForwarderFrame, poolProxyEnvironment, type ForwarderFrame } from '../../scripts/testing/pool-common';
import { isObject } from '../../src/shared/errors';

let root: string, socketPath: string, collector: PrivateProcess<ForwarderFrame>, fixture: PoolFixture;
const key = 'isolated-transport-pool-canary-1792';

beforeAll(async () => {
  if (Bun.spawnSync(['ip','link','set','lo','up']).exitCode !== 0 || await readlink('/proc/self/ns/net') === await readlink('/proc/1/ns/net')) throw new Error('TLS 矩阵需要独立无外网空间');
  const interfaces = (await readFile('/proc/net/dev', 'utf8')).split('\n').slice(2).filter(x => x.includes(':')).map(x => x.split(':')[0]!.trim());
  if (interfaces.join(',') !== 'lo') throw new Error('离线空间存在外网接口');
  root = await mkdtemp(join(tmpdir(), 'ccrb-pool-transport-')); socketPath = join(root, 'tls.sock');
  const keyFile = join(root, 'key.pem'), certFile = join(root, 'cert.pem');
  if (Bun.spawnSync(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',keyFile,'-out',certFile,'-days','1','-subj','/CN=api.anthropic.com','-addext','subjectAltName=DNS:api.anthropic.com,IP:127.0.0.1'], { stdout: 'ignore', stderr: 'ignore' }).exitCode !== 0) throw new Error('测试证书生成失败');
  fixture = startPoolFixture(key);
  const built = await Bun.build({ entrypoints: [resolve('scripts/testing/pool-forwarder.ts')], target: 'node', format: 'esm', outdir: root, naming: 'forwarder.mjs' });
  if (!built.success) throw new Error('采集器构建失败');
  if (!(await Bun.build({ entrypoints: [resolve('tests/pool/tls-client.ts')], target: 'node', format: 'esm', outdir: root, naming: 'client.mjs' })).success) throw new Error('TLS 客户端构建失败');
  collector = new PrivateProcess([Bun.which('node')!, join(root, 'forwarder.mjs')], { HOME: root, LANG: 'C.UTF-8', PATH: process.env.PATH ?? '/usr/bin:/bin' }, decodeForwarderFrame);
  await collector.send({ type: 'init', socketPath, keyFile, certFile, config: { baseUrl: fixture.baseUrl, apiKey: key, live: false, maxRequests: 30, timeoutMs: 500 } });
  const ready = await collector.next(); expect(ready.type).toBe('ready'); if (ready.type === 'ready') expect(ready.rawHeadersMatched).toBe(true);
});

afterAll(async () => { await collector?.close(); await fixture?.close(); if (root) await rm(root, { recursive: true, force: true }); });

/** 直接 TLS 客户端用于传输单元，不伪造原生 CCH 证明。 */
async function call(raw: Uint8Array | string, path = '/v1/messages?beta=true', cancel = false, slow = false, destination = socketPath): Promise<{ status: number; body: Buffer; closed: boolean }> {
  const child = Bun.spawn([Bun.which('node')!, join(root, 'client.mjs')], { env: { HOME: root, PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8' }, stdin: 'pipe', stdout: 'pipe', stderr: 'ignore' });
  child.stdin.write(JSON.stringify({ socketPath: destination, certFile: join(root, 'cert.pem'), path, cancel, slow, body: Buffer.from(raw).toString('base64') }) + '\n'); await child.stdin.flush(); child.stdin.end();
  const text = await new Response(child.stdout).text(), code = await child.exited;
  const value: unknown = code === 0 && text ? JSON.parse(text) : null;
  if (!isObject(value) || typeof value.status !== 'number' || typeof value.body !== 'string' || typeof value.closed !== 'boolean') throw new Error('本机 TLS 客户端失败');
  return { status: value.status, body: Buffer.from(value.body, 'base64'), closed: value.closed };
}

async function forward(body: Record<string, unknown>, choice: string, allowed = true, cancel = false, slow = false): Promise<{ response: Awaited<ReturnType<typeof call>>; end: Extract<ForwarderFrame, { type: 'finished' }> }> {
  fixture.select(choice);
  const response = call(JSON.stringify(body), '/v1/messages?beta=true', cancel, slow);
  const frame = await Promise.race([collector.next(5000), response.then(() => { throw new Error('尚未采集就收到响应'); })]); if (frame.type !== 'captured') throw new Error('缺少实体采集');
  expect(JSON.parse(frame.body)).toEqual(body); expect(frame.path).toBe('/v1/messages?beta=true');
  await collector.send({ type: allowed ? 'forward' : 'reject', id: frame.id });
  const end = await collector.next(); if (end.type !== 'finished') throw new Error('缺少唯一终态');
  expect(end.id).toBe(frame.id);
  return { response: await response, end };
}

describe('Node TLS 单次发送及故障收口', () => {
  test('FBK-001：不支持的 Key 在 Node 初始化时拒绝，零池请求且不回显秘密', async () => {
    const before = fixture.calls.length;
    for (const apiKey of ['quote"back\\slash-canary', 'pool-中文-key']) {
      const rejected = new PrivateProcess([Bun.which('node')!, join(root, 'forwarder.mjs')], { HOME: root, PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8' }, decodeForwarderFrame);
      try {
        await rejected.send({ type: 'init', socketPath: join(root, 'invalid-key.sock'), keyFile: join(root, 'key.pem'), certFile: join(root, 'cert.pem'), config: { baseUrl: fixture.baseUrl, apiKey, live: false, maxRequests: 1, timeoutMs: 500 } });
        const frame = await rejected.next(); expect(frame.type).toBe('fatal'); expect(JSON.stringify(frame)).not.toContain(apiKey);
        expect(await rejected.child.exited).toBe(1);
      } finally { await rejected.close(); }
    }
    expect(fixture.calls.length).toBe(before);
  });

  test('核验拒绝、非法路径、损坏 UTF-8 和超限均不访问池', async () => {
    const before = fixture.calls.length;
    const rejected = await forward({ model: 'claude', max_tokens: 128 }, 'json', false);
    expect(rejected.response.status).toBe(400); expect(rejected.end.attempted).toBe(false);
    expect(rejected.end.upstreamStatus).toBeNull(); expect(rejected.end.failureCode).toBe('REQUEST_REJECTED');
    expect((await call('{}', '/v1/models')).status).toBe(400);
    expect((await call(Buffer.from([0xc3,0x28]))).status).toBe(400);
    await expect(call(Buffer.alloc(REQUEST_LIMIT + 1, 120))).rejects.toThrow();
    expect(fixture.calls.length).toBe(before);
  });

  test('JSON 与扩展字段原样保留，鉴权仅第二段替换', async () => {
    const before = fixture.calls.length, body = { model: 'claude-sonnet-4-6', max_tokens: 128, stream: false, future: { signature: 'opaque' } };
    const { response, end } = await forward(body, 'json');
    expect(response.status).toBe(200); expect(end.upstreamStatus).toBe(200); expect(end.outcome).toBe('success'); expect(fixture.calls.length).toBe(before + 1);
    expect(fixture.calls.at(-1)).toEqual({ path: '/v1/messages?beta=true', body: { ...body, model: POOL_MODEL }, authenticated: true, extension: 'preserved' });
    expect(end.response.sha256).toBe(createHash('sha256').update(response.body).digest('hex'));
    expect(end.transportDiagnostics).toMatchObject({ phase: 'response_body', bodySentObserved: true });
    expect(end.transportDiagnostics!.connectionBytesWritten).toBeGreaterThan(0);
    expect(JSON.stringify(end)).not.toContain(key); expect(JSON.stringify(end)).not.toContain('original-cc-canary');
  });

  test('上一响应的敏感名称标志头不污染下一轮的 stream=true 预览', async () => {
    const { end } = await forward({ model: 'claude', max_tokens: 128, stream: true }, 'sse');
    expect(end.outcome).toBe('success'); expect(end.prepared).toBeDefined();
    expect(JSON.parse(end.prepared!.body.text).stream).toBe(true);
  });

  test('HTTP 错误和重定向均只发送一次，不跟随、不回退', async () => {
    for (const choice of ['401','429','500','redirect']) {
      const before = fixture.calls.length, { response, end } = await forward({ model: 'claude', max_tokens: 128 }, choice);
      expect(response.status).toBe(choice === 'redirect' ? 302 : Number(choice)); expect(fixture.calls.length).toBe(before + 1);
      expect(end.outcome).toBe(choice === 'redirect' ? 'redirect_blocked' : 'http_error'); expect(fixture.redirected).toBe(0); expect(JSON.stringify(end)).not.toContain(key);
      if (choice !== 'redirect') expect(response.body.toString()).toContain(key);
    }
  });

  test('流式背压和超长预览仍保留完整逻辑字节哈希', async () => {
    const { response, end } = await forward({ model: 'claude', max_tokens: 128, stream: true }, 'large', true, false, true);
    expect(end.outcome).toBe('success'); expect(response.body.length).toBeGreaterThan(1024 * 1024); expect(end.response.status).toBe('truncated');
    expect(end.response.sha256).toBe(createHash('sha256').update(response.body).digest('hex'));
    expect(response.body.toString()).toContain('event: message_stop');
  });

  test('调用方取消与池超时有不同收口，无额外池请求', async () => {
    const before = fixture.calls.length, canceledBefore = fixture.canceled;
    const canceled = await forward({ model: 'claude', max_tokens: 128, stream: true }, 'cancel', true, true);
    expect(canceled.end.outcome).toBe('canceled'); expect(canceled.end.response.status).toBe('incomplete'); expect(fixture.canceled).toBeGreaterThan(canceledBefore);
    const timeout = await forward({ model: 'claude', max_tokens: 128 }, 'timeout');
    expect(timeout.end.outcome).toBe('timeout'); expect(timeout.end.upstreamStatus).toBeNull(); expect(timeout.end.failureCode).toBe('POOL_TIMEOUT'); expect(timeout.response.status).toBe(502); expect(fixture.calls.length).toBe(before + 2);
  });

  test('Node 标准代理只用于池第二段，TLS 原始头探针不经过代理', async () => {
    const target = new URL(fixture.baseUrl), sockets = new Set<Duplex>(); let proxyCalls = 0;
    const proxy = createServer((incoming, response) => {
      proxyCalls++;
      void (async () => {
        const url = new URL(incoming.url!); if (url.origin !== target.origin || url.pathname !== '/v1/messages') { response.writeHead(403); response.end(); return; }
        const chunks: Buffer[] = []; for await (const chunk of incoming) chunks.push(Buffer.from(chunk));
        const headers = Object.fromEntries(Object.entries(incoming.headers).filter(([,v]) => v !== undefined).map(([k,v]) => [k, Array.isArray(v) ? v.join(', ') : v!]));
        const upstream = await fetch(url, { method: 'POST', headers, body: Buffer.concat(chunks) });
        response.writeHead(upstream.status, { 'content-type': 'application/json', connection: 'close' }); response.end(Buffer.from(await upstream.arrayBuffer()));
      })().catch(() => response.destroy());
    });
    proxy.on('connect', (incoming, socket, head) => {
      proxyCalls++;
      if (incoming.url !== target.host) { socket.end('HTTP/1.1 403 Forbidden\r\n\r\n'); return; }
      const upstream = connect(Number(target.port), '127.0.0.1', () => { socket.write('HTTP/1.1 200 Connection Established\r\n\r\n'); if (head.length) upstream.write(head); socket.pipe(upstream); upstream.pipe(socket); });
      sockets.add(socket); sockets.add(upstream);
      socket.on('close', () => { sockets.delete(socket); upstream.destroy(); }); upstream.on('close', () => { sockets.delete(upstream); socket.destroy(); });
      socket.on('error', () => upstream.destroy()); upstream.on('error', () => socket.destroy());
    });
    await new Promise<void>(resolve => proxy.listen(0, '127.0.0.1', resolve));
    const address = proxy.address(); if (!address || typeof address === 'string') throw new Error('代理端口不可用');
    const proxyUrl = 'http://127.0.0.1:' + address.port, destination = join(root, 'proxy-tls.sock');
    const via = new PrivateProcess([Bun.which('node')!, '--use-env-proxy', join(root, 'forwarder.mjs')], { HOME: root, LANG: 'C.UTF-8', PATH: process.env.PATH ?? '/usr/bin:/bin', ...poolProxyEnvironment({ HTTP_PROXY: proxyUrl, HTTPS_PROXY: proxyUrl }, true) }, decodeForwarderFrame);
    try {
      await via.send({ type: 'init', socketPath: destination, keyFile: join(root, 'key.pem'), certFile: join(root, 'cert.pem'), config: { baseUrl: fixture.baseUrl, apiKey: key, live: false, maxRequests: 1, timeoutMs: 2000 } });
      const ready = await via.next(); expect(ready.type).toBe('ready'); expect(proxyCalls).toBe(0);
      fixture.select('json'); const before = fixture.calls.length;
      const response = call('{"model":"claude","max_tokens":128}', '/v1/messages', false, false, destination);
      const captured = await via.next(); if (captured.type !== 'captured') throw new Error('代理场景缺少 TLS 实体');
      await via.send({ type: 'forward', id: captured.id });
      const end = await via.next(); if (end.type !== 'finished') throw new Error('代理场景缺少转发终态');
      expect(end.upstreamStatus).toBe(200); expect(end.outcome).toBe('success'); expect((await response).status).toBe(200);
      expect(proxyCalls).toBe(1); expect(fixture.calls.length).toBe(before + 1); expect(fixture.calls.at(-1)!.authenticated).toBe(true);
    } finally { await via.close(); for (const socket of sockets) socket.destroy(); await new Promise<void>(resolve => proxy.close(() => resolve())); }
  });

  test('连接失败的本地 502 不称为池响应，错误码有界且无凭据', async () => {
    await fixture.close();
    const { response, end } = await forward({ model: 'claude', max_tokens: 128 }, 'json');
    expect(response.status).toBe(502); expect(end.attempted).toBe(true); expect(end.upstreamStatus).toBeNull(); expect(end.outcome).toBe('error');
    expect(['ECONNREFUSED','ECONNRESET','UND_ERR_SOCKET']).toContain(end.failureCode!); expect(end.response.bytes).toBe(0); expect(JSON.stringify(end)).not.toContain(key);
  });

  test('直连与 HTTPS 代理的断连阶段、单次发送及下一请求恢复均可核对', async () => {
    let phase: 'normal' | 'before_headers' | 'response_body' | 'connect' = 'normal', received = 0, proxyCalls = 0;
    const sockets = new Set<Duplex>();
    const body = JSON.stringify({ type: 'message', content: [{ type: 'text', text: '离线连接恢复' }] });
    const upstream = createHttpsServer({ key: await readFile(join(root, 'key.pem')), cert: await readFile(join(root, 'cert.pem')) }, (request, response) => {
      const chunks: Buffer[] = [];
      request.on('data', chunk => chunks.push(Buffer.from(chunk)));
      request.on('end', () => {
        received++;
        expect(JSON.parse(Buffer.concat(chunks).toString()).model).toBe(POOL_MODEL);
        if (phase === 'before_headers') { request.socket.destroy(); return; }
        response.writeHead(200, { 'content-type': 'application/json', 'content-length': String(Buffer.byteLength(body)), connection: 'close' });
        if (phase === 'response_body') { response.write(body.slice(0, 20)); setTimeout(() => response.destroy(), 30); }
        else response.end(body);
      });
    });
    await new Promise<void>(resolve => upstream.listen(0, '127.0.0.1', resolve));
    const address = upstream.address(); if (!address || typeof address === 'string') throw new Error('故障夹具没有端口');
    const target = '127.0.0.1:' + address.port;
    const proxy = createServer();
    proxy.on('connect', (request, socket, head) => {
      proxyCalls++;
      if (request.url !== target || phase === 'connect') { socket.end('HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'); return; }
      const remote = connect(address.port, '127.0.0.1', () => { socket.write('HTTP/1.1 200 Connection Established\r\n\r\n'); if (head.length) remote.write(head); socket.pipe(remote); remote.pipe(socket); });
      sockets.add(socket); sockets.add(remote);
      socket.on('close', () => { sockets.delete(socket); remote.destroy(); }); remote.on('close', () => { sockets.delete(remote); socket.destroy(); });
      socket.on('error', () => remote.destroy()); remote.on('error', () => socket.destroy());
    });
    await new Promise<void>(resolve => proxy.listen(0, '127.0.0.1', resolve));
    const proxyAddress = proxy.address(); if (!proxyAddress || typeof proxyAddress === 'string') throw new Error('故障代理没有端口');
    const proxyUrl = 'http://127.0.0.1:' + proxyAddress.port;
    try {
      for (const routed of [false, true]) {
        const destination = join(root, routed ? 'diagnostic-proxy.sock' : 'diagnostic-direct.sock');
        const transport = new PrivateProcess([Bun.which('node')!, ...(routed ? ['--use-env-proxy'] : []), join(root, 'forwarder.mjs')], { HOME: root, LANG: 'C.UTF-8', PATH: process.env.PATH ?? '/usr/bin:/bin', NODE_EXTRA_CA_CERTS: join(root, 'cert.pem'), ...(routed ? poolProxyEnvironment({ HTTP_PROXY: proxyUrl, HTTPS_PROXY: proxyUrl }, true) : {}) }, decodeForwarderFrame);
        try {
          await transport.send({ type: 'init', socketPath: destination, keyFile: join(root, 'key.pem'), certFile: join(root, 'cert.pem'), config: { baseUrl: 'https://' + target, apiKey: key, live: false, maxRequests: 10, timeoutMs: 1500 } });
          expect((await transport.next()).type).toBe('ready');
          const choices = ['normal', 'before_headers', 'normal', 'response_body', 'normal', ...(routed ? ['connect', 'normal'] as const : [])] as const;
          for (const choice of choices) {
            phase = choice;
            const before = received, connectsBefore = proxyCalls;
            const result = call('{"model":"claude","max_tokens":128}', '/v1/messages', false, false, destination);
            const captured = await transport.next(); if (captured.type !== 'captured') throw new Error('断连场景缺少实收请求');
            await transport.send({ type: 'forward', id: captured.id });
            const end = await transport.next(); if (end.type !== 'finished') throw new Error('断连场景缺少终态');
            const response = await result;
            expect(received - before).toBe(choice === 'connect' ? 0 : 1);
            expect(proxyCalls - connectsBefore).toBe(routed ? 1 : 0);
            expect(end.attempted).toBe(true); expect(JSON.stringify(end)).not.toContain(key);
            if (choice === 'normal') {
              expect(response.status).toBe(200); expect(end.outcome).toBe('success'); expect(response.body.toString()).toBe(body);
              expect(end.transportDiagnostics).toMatchObject({ phase: 'response_body', bodySentObserved: true });
            } else if (choice === 'before_headers') {
              expect(response.status).toBe(502); expect(end.upstreamStatus).toBeNull(); expect(end.failureCode).toBe('UND_ERR_SOCKET');
              expect(end.transportDiagnostics).toMatchObject({ phase: 'awaiting_headers', bodySentObserved: true, connectionBytesRead: 0 });
              expect(end.transportDiagnostics!.connectionBytesWritten).toBeGreaterThan(0);
            } else if (choice === 'response_body') {
              expect(response.status).toBe(200); expect(response.closed).toBe(true); expect(end.upstreamStatus).toBe(200); expect(end.outcome).toBe('error');
              expect(end.response.status).toBe('incomplete'); expect(end.transportDiagnostics!.phase).toBe('response_body');
            } else {
              expect(response.status).toBe(502); expect(end.upstreamStatus).toBeNull();
              expect(end.transportDiagnostics).toEqual({ phase: 'before_send', bodySentObserved: false, connectionBytesWritten: null, connectionBytesRead: null });
            }
          }
        } finally { await transport.close(); }
      }
    } finally {
      for (const socket of sockets) socket.destroy();
      upstream.closeAllConnections();
      await Promise.all([new Promise<void>(resolve => proxy.close(() => resolve())), new Promise<void>(resolve => upstream.close(() => resolve()))]);
    }
  }, 15000);
});
