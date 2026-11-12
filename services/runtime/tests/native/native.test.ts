import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';
import { createServer } from 'node:http';
import { connect } from 'node:net';
import type { Duplex } from 'node:stream';
import { readConfig, startServer, type RunningServer } from '../../src/control/server';
import type { HeaderPair, RuntimePayload } from '../../src/shared/contracts';
import { decodeWorkerFrame } from '../../src/shared/protocol';
import { verifyRuntime } from '../../src/runtime/profile';
import { PrivateProcess } from '../../scripts/testing/pool-process';
import { createEngine, type Engine } from '../../src/control/engine';
import { prepareInput } from '../../src/control/header-policy';
import { parseInput } from '../../src/shared/input';

const isolated = process.env.CCRB_NATIVE_ISOLATED === '1';
const native = isolated ? describe : describe.skip;

native('官方 293 的无外网回环链路', () => {
  let root: string;
  let app: RunningServer;
  let upstream: Bun.Server<undefined>;
  let proxy: ReturnType<typeof createServer>;
  let base: string;
  let mode: 'normal' | 'tool' | 'local_tool' | 'http_error' | 'network_error' | 'sse_error' | 'incomplete' | 'slow' = 'normal';
  const requests: { raw: string; body: Record<string, unknown>; headers: HeaderPair[] }[] = [];
  const telemetryRequests: { raw: string; body: { events: { event_type: string; event_data: Record<string, unknown> }[] }; headers: HeaderPair[] }[] = [];
  const telemetryCases: Record<string, unknown>[] = [];
  const proxyTargets: string[] = [];
  const proxyHttpRequests: { method: string | undefined; url: string | undefined }[] = [];
  const auxiliaryRequests: { method: string; path: string }[] = [];
  let telemetryMode: 'normal' | 'error' | 'slow' = 'normal';
  const sockets = new Set<Duplex>();
  const upstreamSecret = 'ccrb-upstream-secret-canary';
  let expectedResponse = '';
  let nativeEngine: Engine;
  let config: ReturnType<typeof readConfig>;
  const policyCases: Record<string, unknown>[] = [];
  let setupMs = 0;
  const timings: { previousPid: number | null; pid: number | null; completeMs: number }[] = [];
  const cases: { index: number; body: Record<string, unknown>; context: Record<string, unknown>; id: string }[] = [];

  beforeAll(async () => {
    if (Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode !== 0) throw new Error('无法在独立网络空间启用回环接口');
    root = await mkdtemp(join(tmpdir(), 'ccrb-native-test-'));
    await mkdir(join(root, 'home')); await mkdir(join(root, 'config'));
    const certificate = Bun.spawnSync(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', join(root, 'key.pem'), '-out', join(root, 'cert.pem'), '-days', '1', '-subj', '/CN=api.anthropic.com', '-addext', 'subjectAltName=DNS:api.anthropic.com'], { stdout: 'pipe', stderr: 'pipe' });
    if (certificate.exitCode !== 0) throw new Error('回环证书生成失败');
    // 固定的合成设备身份仅用于离线夹具，不复制真实账号配置。
    await writeFile(join(root, 'config', '.claude.json'), JSON.stringify({ userID: 'a'.repeat(64) }));
    upstream = Bun.serve({
      hostname: '127.0.0.1', port: 0,
      tls: { key: Bun.file(join(root, 'key.pem')), cert: Bun.file(join(root, 'cert.pem')) },
      async fetch(request) {
        const url = new URL(request.url);
        if (url.pathname === '/api/event_logging/v2/batch') {
          const raw = await request.text();
          telemetryRequests.push({ raw, body: JSON.parse(raw), headers: [...request.headers.entries()] as HeaderPair[] });
          if (telemetryMode === 'error') return Response.json({ error: 'synthetic telemetry failure' }, { status: 500 });
          if (telemetryMode === 'slow') {
            let timer: ReturnType<typeof setTimeout>;
            return new Response(new ReadableStream({ start(controller) { timer = setTimeout(() => { try { controller.close(); } catch {} }, 5000); timer.unref(); }, cancel() { clearTimeout(timer); } }), { headers: { 'content-type': 'application/json' } });
          }
          return Response.json({});
        }
        if (url.pathname !== '/v1/messages') { auxiliaryRequests.push({ method: request.method, path: url.pathname }); return Response.json({}); }
        const raw = await request.text();
        const body = JSON.parse(raw);
        requests.push({ raw, body, headers: [...request.headers.entries()] as HeaderPair[] });
        const message = { id: 'msg_native_fixture', type: 'message', role: 'assistant', model: body.model, content: [{ type: 'text', text: '真实原生发送的离线响应' }], stop_reason: 'end_turn', usage: { input_tokens: 10, output_tokens: 4 } };
        if (mode === 'slow') {
          let timer: ReturnType<typeof setInterval>;
          const stream = new ReadableStream<Uint8Array>({
            start(control) {
              control.enqueue(Buffer.from('event: message_start\ndata: {"type":"message_start"}\n\n'));
              timer = setInterval(() => control.enqueue(Buffer.from(': keepalive\n\n')), 20);
              timer.unref();
              request.signal.addEventListener('abort', () => clearInterval(timer), { once: true });
            },
            cancel() { clearInterval(timer); },
          });
          return new Response(stream, { headers: { 'content-type': 'text/event-stream' } });
        }
        if (mode === 'http_error') {
          expectedResponse = JSON.stringify({ type: 'error', error: { type: 'rate_limit_error', message: upstreamSecret } });
          return new Response(expectedResponse, { status: 429, headers: { 'content-type': 'application/json', 'x-upstream-extension': 'preserved' } });
        }
        if (body.stream !== true) {
          expectedResponse = JSON.stringify(message);
          return new Response(expectedResponse, { headers: { 'content-type': 'application/json', 'request-id': 'req_native_fixture', 'x-upstream-extension': 'preserved' } });
        }
        const tool = mode === 'tool' || mode === 'local_tool';
        const events: Record<string, unknown>[] = [
          { type: 'message_start', message: { ...message, content: [], stop_reason: null } },
          { type: 'content_block_start', index: 0, content_block: tool ? { type: 'tool_use', id: 'toolu_returned', name: mode === 'local_tool' ? 'Bash' : 'lookup_status', input: {} } : { type: 'text', text: '' } },
          { type: 'content_block_delta', index: 0, delta: tool ? { type: 'input_json_delta', partial_json: mode === 'local_tool' ? JSON.stringify({ command: 'touch ' + join(root, 'must-not-execute') }) : '{"project":"beta"}' } : { type: 'text_delta', text: '真实原生发送的离线响应' } },
          { type: 'content_block_stop', index: 0 },
        ];
        if (mode === 'sse_error') events.push({ type: 'error', error: { type: 'overloaded_error', message: 'fixture error' } });
        else if (mode !== 'incomplete') events.push({ type: 'message_delta', delta: { stop_reason: tool ? 'tool_use' : 'end_turn' }, usage: message.usage }, { type: 'message_stop' });
        expectedResponse = events.map(event => 'event: ' + event.type + '\ndata: ' + JSON.stringify(event) + '\n\n').join('');
        return new Response(expectedResponse, { headers: { 'content-type': 'text/event-stream', 'request-id': 'req_native_fixture', 'x-upstream-extension': 'preserved' } });
      },
    });
    proxy = createServer();
    proxy.on('request', (request, response) => {
      proxyHttpRequests.push({ method: request.method, url: request.url });
      request.resume(); response.writeHead(501); response.end('CONNECT required');
    });
    proxy.on('connect', (request, socket, head) => {
      proxyTargets.push(request.url ?? '');
      if (request.url !== 'api.anthropic.com:443') { socket.end('HTTP/1.1 403 Forbidden\r\n\r\n'); return; }
      if (mode === 'network_error') { socket.end('HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n'); return; }
      sockets.add(socket); socket.on('close', () => sockets.delete(socket));
      const target = connect(upstream.port!, '127.0.0.1', () => {
        socket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
        if (head.length) target.write(head);
        socket.pipe(target); target.pipe(socket);
      });
      sockets.add(target); target.on('close', () => sockets.delete(target));
      target.on('error', () => socket.destroy()); socket.on('error', () => target.destroy());
    });
    await new Promise<void>(resolve => proxy.listen(0, '127.0.0.1', resolve));
    const address = proxy.address();
    if (!address || typeof address === 'string') throw new Error('代理没有有效端口');
    config = readConfig({
      CCRB_PORT: '0', CCRB_DATA_DIR: join(root, 'data'),
      CCRB_CLAUDE_BINARY: process.env.CCRB_TEST_CLAUDE_BINARY ?? '/root/.nvm/versions/node/v22.23.4/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe',
      CCRB_CLAUDE_HOME: join(root, 'home'), CCRB_CLAUDE_CONFIG_DIR: join(root, 'config'),
      CCRB_NATIVE_API_KEY: upstreamSecret, CCRB_CA_FILE: join(root, 'cert.pem'), CCRB_PROXY_URL: 'http://127.0.0.1:' + address.port,
      CCRB_TIMEOUT_MS: '15000',
    });
    // 模拟凭据仅由原生端持有的配置路径，控制层不能依赖预先知道密钥来脱敏。
    const setupStarted = performance.now();
    nativeEngine = await createEngine(config.engine);
    app = await startServer({ ...config, engine: { ...config.engine, apiKey: undefined } }, nativeEngine);
    base = 'http://127.0.0.1:' + app.server.port;
    setupMs = performance.now() - setupStarted;
    expect(nativeEngine.workerPid).toBeNull();
  }, 30000);

  afterAll(async () => {
    // 只在显式指定的证据目录留存真实 TLS 观测；测试 HOME 仍会清理，完整原生提示词不进入 Git。
    const captures = process.env.CCRB_NATIVE_CAPTURE_DIR;
    if (captures && app) {
      await app.store.flush();
      const details = await Promise.all(cases.map(value => app.store.detail(value.id)));
      await mkdir(captures, { recursive: true });
      await writeFile(join(captures, 'requests.json'), JSON.stringify({ source: 'isolated_local_tls', real_upstream_requests: 0, binary_sha256: nativeEngine.binarySha256, cases,
        requests: requests.map(request => ({ ...request, headers: request.headers.map(([name, value]) => [name, /authorization|api[-_]?key|cookie|token/i.test(name) ? '[REDACTED]' : value]) })),
        details, policy_cases: policyCases, telemetry_cases: telemetryCases,
        telemetry_requests: telemetryRequests.map(request => ({ ...request, headers: request.headers.map(([name, value]) => [name, /authorization|api[-_]?key|cookie|token/i.test(name) ? '[REDACTED]' : value]) })),
        proxy_http_requests: proxyHttpRequests,
        auxiliary_requests: auxiliaryRequests,
      }, null, 2));
    }
    if (app) await app.close();
    for (const socket of sockets) socket.destroy();
    if (proxy) await new Promise<void>(resolve => proxy.close(() => resolve()));
    if (upstream) await upstream.stop(true);
    if (root) await rm(root, { recursive: true, force: true });
    const report = process.env.CCRB_NATIVE_REPORT;
    if (report) {
      await mkdir(dirname(report), { recursive: true });
      await writeFile(report, JSON.stringify({ setupMs, binarySha256: nativeEngine.binarySha256, conditions: 'HTTP 控制面及日志启用、TLS CONNECT 合成上游；与裸协议基准不同，不直接相减计算开销', timings }, null, 2));
    }
  });

  async function send(body: Record<string, unknown>, context: Record<string, unknown> = {}, headers: HeaderPair[] = []): Promise<{ response: Response; raw: string; id: string }> {
    const started = performance.now(), previousPid = nativeEngine.workerPid, index = requests.length;
    const response = await fetch(base + '/api/requests', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ body, context, headers }) });
    const raw = await response.text();
    cases.push({ index, body, context, id: response.headers.get('x-ccrb-request-id')! });
    timings.push({ previousPid, pid: nativeEngine.workerPid, completeMs: performance.now() - started });
    // 矩阵逐项核验持久日志，轮间先排空有界异步写盘队列；响应耗时已在上方单独记录。
    await app.store.flush();
    expect(app.store.error).toBeNull();
    return { response, raw, id: response.headers.get('x-ccrb-request-id')! };
  }

  function assertCch(raw: string): void {
    const decoded = JSON.parse(raw);
    expect(JSON.stringify(decoded)).toBe(raw);
    const billing = (decoded.system as { text: string }[]).find(block => block.text?.startsWith('x-anthropic-billing-header:'));
    expect(billing).toBeDefined();
    expect(billing!.text).toContain('cc_entrypoint=cli;');
    const cch = /cch=([0-9a-f]{5})/.exec(billing!.text)?.[1];
    expect(cch).not.toBe('00000');
    billing!.text = billing!.text.replace(/cch=[0-9a-f]{5}/, 'cch=00000');
    delete decoded.max_tokens;
    const neutralize = (value: unknown): unknown => {
      if (Array.isArray(value)) return value.map(neutralize);
      if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, key === 'model' && typeof child === 'string' ? '' : neutralize(child)]));
      return value;
    };
    const expected = (Bun.hash.xxHash64(JSON.stringify(neutralize(decoded)), 0x4D659218E32A3268n) & 0xfffffn).toString(16).padStart(5, '0');
    expect(cch).toBe(expected);
  }

  test('原始输入由同一进程校验和过滤，错误输入零发送后仍可复用', async () => {
    mode = 'normal';
    const workerId = randomUUID();
    const verified = await verifyRuntime(config.engine.binaryPath!);
    const env: Record<string, string> = {
      HOME: config.engine.home!, CLAUDE_CONFIG_DIR: config.engine.configDir!, PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8',
      CCRB_WORKER_ID: workerId, CCRB_TELEMETRY: 'off', CLAUDE_CODE_ENTRYPOINT: 'cli', DISABLE_AUTO_COMPACT: '1',
      CLAUDE_CODE_GATEWAY_HINT_HEADERS: '1', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', DISABLE_AUTOUPDATER: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1',
      ANTHROPIC_API_KEY: upstreamSecret, HTTPS_PROXY: config.engine.proxyUrl!, HTTP_PROXY: config.engine.proxyUrl!, NODE_EXTRA_CA_CERTS: config.engine.caFile!,
    };
    if (verified.identity.kind === 'original') env.BUN_OPTIONS = '--preload ' + config.engine.preloadPath;
    const worker = new PrivateProcess(['/proc/' + process.pid + '/fd/' + verified.handle.fd, '--version'], env, line => decodeWorkerFrame(line, workerId), config.engine.cwd);
    const collect = async (id: string): Promise<RuntimePayload[]> => {
      const events: RuntimePayload[] = [];
      while (true) {
        const frame = await worker.next();
        if (frame.type === 'request_event' || frame.type === 'worker_idle') expect(frame.request_id).toBe(id);
        if (frame.type === 'worker_idle') return events;
        if (frame.type !== 'request_event') throw new Error('原始输入返回了非请求事件');
        events.push(frame.payload);
      }
    };
    try {
      const ready = await worker.next();
      expect(ready.type).toBe('worker_ready');
      if (ready.type !== 'worker_ready') throw new Error('缺少工作进程握手');
      expect(ready.raw_input_protocol).toBe(1);
      expect(ready.cache_ttl_rewrite_protocol).toBe(1);
      expect(ready.pid).toBe(worker.child.pid);
      const count = requests.length;
      const body = { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '原始输入回环' }], stream: false };
      await worker.send({ type: 'request_input', schema_version: 2, worker_id: workerId, request_id: 'raw-invalid', input: { schema_version: 1, request_id: 'raw-invalid', body, headers: [['x-unknown', 'bad\r\nheader']] } });
      expect(await collect('raw-invalid')).toContainEqual(expect.objectContaining({ type: 'error', code: 'invalid_header' }));
      expect(requests.length).toBe(count);
      for (const id of ['raw-first', 'raw-second']) {
        await worker.send({ type: 'request_input', schema_version: 2, worker_id: workerId, request_id: id, input: { schema_version: 1, request_id: id, body, headers: [['accept-language', 'zh-CN'], ['new-api-user', 'synthetic']] } });
        const events = await collect(id);
        expect(events[0]).toEqual(expect.objectContaining({ type: 'header_policy', decisions: expect.arrayContaining([{ name: 'new-api-user', action: 'drop', reason: '调用方请求头未登记到协议白名单' }]) }));
        expect(events.at(-1)).toEqual(expect.objectContaining({ type: 'completed', state: 'success' }));
        expect(new Headers(requests.at(-1)!.headers).has('new-api-user')).toBe(false);
        assertCch(requests.at(-1)!.raw);
      }
      expect(requests.length - count).toBe(2);
      for (const cache_ttl_rewrite of ['1h', '5m', 'off'] as const) {
        const id = 'raw-ttl-' + cache_ttl_rewrite;
        await worker.send({ type: 'request_input', schema_version: 2, worker_id: workerId, request_id: id,
          cache_ttl_rewrite, input: { schema_version: 1, request_id: id, body } });
        const events = await collect(id);
        expect(events.at(-1)).toEqual(expect.objectContaining({ type: 'completed', state: 'success' }));
        const prepared = events.find(event => event.type === 'cc_prepared');
        if (prepared?.type !== 'cc_prepared') throw new Error('缺少TTL改写后的组装快照');
        const actual = requests.at(-1)!;
        // 组装阶段的CCH占位由最终传输补齐；两阶段仅规范该已知字段后比较。
        const normalizeCch = (raw: string): unknown => JSON.parse(raw.replace(/cch=[0-9a-f]{5}/g, 'cch=00000'));
        expect(normalizeCch(prepared.body)).toEqual(normalizeCch(actual.raw));
        const markers: Record<string, unknown>[] = [];
        const pending: unknown[] = [actual.body];
        while (pending.length) {
          const node = pending.pop();
          if (node && typeof node === 'object' && !Array.isArray(node)) {
            const object = node as Record<string, unknown>;
            if (object.cache_control && typeof object.cache_control === 'object') markers.push(object.cache_control as Record<string, unknown>);
            pending.push(...Object.values(object));
          } else if (Array.isArray(node)) pending.push(...node);
        }
        expect(markers.length).toBeGreaterThan(0);
        if (cache_ttl_rewrite !== 'off') expect(markers.every(marker => marker.ttl === cache_ttl_rewrite)).toBe(true);
        assertCch(actual.raw);
      }
      expect(requests.length - count).toBe(5);
      await worker.send({ type: 'worker_shutdown', schema_version: 2, worker_id: workerId });
      expect(await worker.child.exited).toBe(0);
    } finally { await verified.handle.close(); await worker.close(); }
  }, 30000);

  test('显式密钥已被专用 CLI 配置拒绝时保留 503 说明，重复请求不发送或改写决定', async () => {
    const dedicated = join(root, 'rejected-key');
    await mkdir(join(dedicated, 'home'), { recursive: true });
    await mkdir(join(dedicated, 'config'));
    const key = 'ccrb-rejected-key-canary';
    const marker = key.trim().slice(-20);
    const configuration = { userID: 'b'.repeat(64), customApiKeyResponses: { approved: [], rejected: [marker] } };
    const path = join(dedicated, 'config', '.claude.json');
    await writeFile(path, JSON.stringify(configuration));
    const config = readConfig({ CCRB_PORT: '0', CCRB_DATA_DIR: join(dedicated, 'data'), CCRB_CLAUDE_BINARY: process.env.CCRB_TEST_CLAUDE_BINARY ?? '/root/.nvm/versions/node/v22.23.4/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe', CCRB_CLAUDE_HOME: join(dedicated, 'home'), CCRB_CLAUDE_CONFIG_DIR: join(dedicated, 'config'), CCRB_NATIVE_API_KEY: key, CCRB_PROXY_URL: 'http://127.0.0.1:1', CCRB_TIMEOUT_MS: '15000' });
    const engine = await createEngine(config.engine);
    const rejected = await startServer(config, engine);
    const count = requests.length;
    try {
      for (const id of ['rejected-first', 'rejected-next']) {
        const response = await fetch('http://127.0.0.1:' + rejected.server.port + '/api/requests', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ request_id: id, body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '不应发送' }], stream: false } }) });
        expect(response.status).toBe(503);
        expect(await response.json()).toEqual({ type: 'error', request_id: id, error: { type: 'native_configuration', message: '专用 CLI 配置已拒绝当前显式密钥' } });
        expect(engine.workerPid).toBeNull();
        await rejected.store.flush();
        const detail = await rejected.store.detail(id);
        expect(detail?.request.state).toBe('error');
        expect(detail?.captures.find(item => item.stage === 'cc_prepared')?.status).toBe('unavailable');
        expect(JSON.stringify(detail)).not.toContain(key);
      }
      const saved = JSON.parse(await readFile(path, 'utf8'));
      expect(saved.customApiKeyResponses).toEqual(configuration.customApiKeyResponses);
      expect(requests.length).toBe(count);
    } finally { await rejected.close(); }
  }, 30000);

  test('主请求由真实 293 构造并发送，扩展头、关联和 CCH 均一致', async () => {
    mode = 'normal'; const count = requests.length;
    const prompt = '11111111-1111-4111-8111-111111111111';
    const session = '22222222-2222-4222-8222-222222222222';
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '原生主请求' }], system: '业务系统提示词', max_tokens: 64, stream: true }, { sessionId: session, promptId: prompt }, [['x-future-feature', 'preserved'], ['Authorization', 'Bearer caller-secret-canary'], ['x-client-request-id', 'forged-client-id']]);
    expect(result.response.status).toBe(200);
    expect(result.raw).toBe(expectedResponse);
    expect(requests.length - count).toBe(1);
    const request = requests.at(-1)!; const headers = new Headers(request.headers);
    expect(headers.has('x-future-feature')).toBe(false);
    expect(headers.get('x-api-key')).toBe(upstreamSecret);
    expect(headers.get('x-client-request-id')).not.toContain('forged');
    expect(headers.get('x-client-request-id')).not.toContain(',');
    expect(headers.get('x-claude-code-request-class')).toBe('main');
    expect(headers.get('x-claude-code-session-id')).toBe(session);
    expect(headers.get('x-claude-code-prompt-id')).toBe(prompt);
    expect(JSON.stringify(request.body.metadata)).toContain(session);
    expect(request.raw).toContain('cc_prompt_id=' + prompt + ';');
    expect(headers.get('user-agent')).toContain('2.1.293');
    expect(headers.get('user-agent')).toBe('claude-cli/2.1.293 (external, cli)');
    expect(JSON.stringify(request.body.messages)).toContain('原生主请求');
    assertCch(request.raw);
    await app.store.flush();
    const detail = await fetch(base + '/api/logs/' + result.id).then(r => r.json());
    expect(detail.request.state).toBe('success');
    expect(detail.request.binarySha256).toHaveLength(64);
    expect(JSON.stringify(detail)).not.toContain(upstreamSecret);
    expect(JSON.stringify(detail)).not.toContain('caller-secret-canary');
    const prepared = detail.captures.find((capture: { stage: string }) => capture.stage === 'cc_prepared').text;
    expect(prepared).toContain('cch=00000');
    expect(prepared.replace(/cch=00000/, /cch=([0-9a-f]{5})/.exec(request.raw)![0])).toBe(request.raw);
    expect(detail.captures.find((capture: { stage: string }) => capture.stage === 'wire_final').status).toBe('unavailable');
  });

  test('省略工具时不注入内置声明，CLI 提示词、human 来源及模型默认参数仍走原生装配', async () => {
    mode = 'normal'; const count = requests.length;
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '请检查这条离线样本的出站参数。' }], stream: true });
    expect(result.response.status).toBe(200); expect(requests.length - count).toBe(1);
    const request = requests.at(-1)!;
    const system = (request.body.system as { text: string }[]).map(block => block.text);
    expect(system).toContain("You are Claude Code, Anthropic's official CLI for Claude.");
    expect(system.join('\n')).not.toContain('You are a Claude agent, built on');
    expect(system.join('\n')).toContain('cc_turn_origin=human;');
    expect(system.join('\n')).toContain('cc_prompt_index=1; cc_turn_index=1;');
    const tools = request.body.tools as { name: string }[];
    expect(tools).toEqual([]);
    expect(request.body).toMatchObject({ max_tokens: 32000, thinking: { type: 'adaptive', display: 'updates' }, output_config: { effort: 'high' }, context_management: { edits: [{ type: 'clear_thinking_20251015', keep: 'all' }] } });
    const messages = JSON.stringify(request.body.messages);
    expect(messages).not.toContain('schemas are NOT loaded'); expect(messages).toContain('Sonnet 4.6');
    assertCch(request.raw);
  });

  test('同一进程交替省略、空工具与自定义列表，每轮只声明实际工具', async () => {
    mode = 'normal'; let pid = nativeEngine.workerPid;
    const custom = [{ name: 'lookup_status', description: '只查询合成状态', input_schema: { type: 'object', properties: { project: { type: 'string' } }, required: ['project'], additionalProperties: false } }];
    for (const tools of [[], custom, undefined] as const) {
      const count = requests.length;
      const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '请检查这条离线样本的出站参数。' }], ...(tools !== undefined ? { tools } : {}), stream: true });
      expect(result.response.status).toBe(200); expect(requests.length - count).toBe(1);
      pid ??= nativeEngine.workerPid; expect(nativeEngine.workerPid).toBe(pid);
      const request = requests.at(-1)!;
      expect(request.body.tools).toEqual(tools ?? []);
      expect(JSON.stringify(request.body.messages)).not.toContain('schemas are NOT loaded');
      assertCch(request.raw);
    }
  });

  test.each([{ system: '你是业务助手，请保留业务系统提示词。' }, { system: '' }, { system: [] }])('显式 system 完整替换 CLI 默认正文 %#', async ({ system }) => {
    mode = 'normal'; const count = requests.length;
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '请检查这条离线样本的出站参数。' }], system, stream: true });
    expect(result.response.status).toBe(200); expect(requests.length - count).toBe(1);
    const request = requests.at(-1)!;
    const texts = (request.body.system as { text: string }[]).map(block => block.text);
    expect(texts).toContain("You are Claude Code, Anthropic's official CLI for Claude.");
    if (typeof system === 'string' && system) expect(texts.slice(2)).toEqual([system]);
    else expect(texts).toHaveLength(2);
    expect(request.body.tools).toEqual([]);
    assertCch(request.raw);
  });

  test('子代理保留父子头、prompt、billing 与工具历史，返回工具不在本地执行', async () => {
    mode = 'tool'; const count = requests.length;
    const result = await send({
      model: 'claude-sonnet-4-6', stream: true, max_tokens: 64,
      messages: [
        { role: 'user', content: '查询项目状态' },
        { role: 'assistant', content: [{ type: 'thinking', thinking: '准备调用工具', signature: 'synthetic-history-signature' }, { type: 'tool_use', id: 'toolu_history', name: 'lookup_status', input: { project: 'alpha' } }] },
        { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_history', content: 'ready' }] },
      ],
      tools: [{ name: 'lookup_status', description: '查询状态', input_schema: { type: 'object', properties: { project: { type: 'string' } } } }],
    }, {}, [
      ['x-claude-code-request-class', 'subagent'], ['x-claude-code-agent-id', 'child-fixture'],
      ['x-claude-code-parent-agent-id', 'parent-fixture'], ['x-claude-code-agent-type', 'Explore'],
      ['x-claude-code-session-id', '33333333-3333-4333-8333-333333333333'],
      ['x-claude-code-prompt-id', '44444444-4444-4444-8444-444444444444'],
    ]);
    expect(result.raw).not.toContain('unsupported_parameter');
    expect(result.response.status).toBe(200);
    expect(result.raw).toBe(expectedResponse);
    expect(result.raw).toContain('toolu_returned');
    expect(requests.length - count).toBe(1);
    const request = requests.at(-1)!; const headers = new Headers(request.headers);
    expect(headers.get('x-claude-code-request-class')).toBe('subagent');
    expect(headers.get('x-claude-code-agent-id')).toBe('child-fixture');
    expect(headers.get('x-claude-code-parent-agent-id')).toBe('parent-fixture');
    expect(headers.get('x-claude-code-agent-type')).toBe('Explore');
    expect(request.raw).toContain('cc_is_subagent=true');
    expect(JSON.stringify(request.body.metadata)).toContain('33333333-3333-4333-8333-333333333333');
    expect(request.raw).toContain('cc_prompt_id=44444444-4444-4444-8444-444444444444;');
    expect(request.raw).toContain('toolu_history');
    expect(request.raw).toContain('synthetic-history-signature');
    assertCch(request.raw);
  });

  test('非流式请求仍使用原生 SDK，JSON 响应不经 SSE 重组', async () => {
    mode = 'normal'; const count = requests.length;
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '非流式验证' }], max_tokens: 64, stream: false });
    expect(result.response.status).toBe(200);
    expect(result.raw).toBe(expectedResponse);
    expect(result.response.headers.get('content-type')).toContain('application/json');
    expect(requests.length - count).toBe(1);
    expect(requests.at(-1)!.body.stream).toBe(false);
    assertCch(requests.at(-1)!.raw);
  });

  test.each([false, true])('有无显式 Bash 声明均只返回工具事件，不在本机执行或继续推理 %#', async explicit => {
    mode = 'local_tool'; const count = requests.length;
    const tools = [{ name: 'Bash', description: '仅返回给调用方的离线工具声明', input_schema: { type: 'object', properties: { command: { type: 'string' } }, required: ['command'] } }];
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '仅观察工具事件的离线样本' }], ...(explicit ? { tools } : {}), max_tokens: 64, stream: true });
    expect(result.response.status).toBe(200); expect(result.raw).toBe(expectedResponse);
    expect(result.raw).toContain('Bash'); expect(result.raw).toContain('must-not-execute');
    expect(requests.length - count).toBe(1);
    expect(requests.at(-1)!.body.tools).toEqual(explicit ? tools : []);
    expect(await Bun.file(join(root, 'must-not-execute')).exists()).toBe(false);
    assertCch(requests.at(-1)!.raw);
  });

  test.each([
    ['compaction', {}],
    ['compaction', { agentId: 'compact-child', parentAgentId: 'compact-parent', agentType: 'Explore' }],
    ['auxiliary', {}],
    ['side_reply', {}],
    ['workflow', { agentId: 'workflow-child', parentAgentId: 'workflow-parent', workflowRunId: 'run-fixture' }],
  ] as const)('原生 %s 上下文保持分类与 billing 一致 %#', async (requestClass, extra) => {
    mode = 'normal'; const count = requests.length;
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '分类验证' }], stream: false }, { requestClass, ...extra });
    expect(result.response.status).toBe(200); expect(result.raw).toBe(expectedResponse);
    expect(requests.length - count).toBe(1);
    const request = requests.at(-1)!; const headers = new Headers(request.headers);
    expect(headers.get('x-claude-code-request-class')).toBe(requestClass);
    expect(request.raw.includes('cc_is_subagent=true')).toBe('agentId' in extra);
    if ('agentId' in extra) expect(headers.get('x-claude-code-agent-id')).toBe(extra.agentId);
    assertCch(request.raw);
  });

  test('显式 adaptive thinking、工具选择和 effort 由原生能力生成', async () => {
    mode = 'normal';
    const result = await send({
      model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '参数保留验证' }], stream: false, max_tokens: 2048,
      thinking: { type: 'adaptive' }, output_config: { effort: 'high' }, tool_choice: { type: 'auto' },
      tools: [{ name: 'lookup_status', input_schema: { type: 'object', properties: {} } }],
    });
    expect(result.response.status).toBe(200);
    expect(requests.at(-1)!.body).toMatchObject({ thinking: { type: 'adaptive' }, output_config: { effort: 'high' }, tool_choice: { type: 'auto' }, max_tokens: 2048 });
  });

  test('原生无法保留的显式 system 缓存参数在发送前拒绝', async () => {
    const count = requests.length;
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '不支持参数验证' }], system: [{ type: 'text', text: 'cache', cache_control: { type: 'ephemeral' } }] });
    expect(result.response.status).toBe(422);
    expect(result.raw).toContain('unsupported_parameter');
    expect(requests.length).toBe(count);
  });

  test('上游 429 状态和正文返回，原生 SDK 不额外重试', async () => {
    mode = 'http_error'; const count = requests.length;
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: 'HTTP 错误验证' }], stream: true });
    expect(result.response.status).toBe(429);
    expect(result.raw).toBe(expectedResponse);
    expect(result.response.headers.get('x-upstream-extension')).toBe('preserved');
    expect(requests.length - count).toBe(1);
    await app.store.flush();
    const detail = await fetch(base + '/api/logs/' + result.id).then(r => r.json());
    expect(detail.request.state).toBe('http_error');
    expect(JSON.stringify(detail)).not.toContain(upstreamSecret);
  });

  test('原生传输失败立即收口，下一请求重建且不重放失败作业', async () => {
    const pid = nativeEngine.workerPid, count = requests.length;
    // 先关闭空闲连接，确保这次经过拒绝 CONNECT 的本机夹具。
    for (const socket of sockets) socket.destroy();
    mode = 'network_error';
    const started = performance.now();
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '合成传输失败' }], stream: false });
    expect(result.response.status).toBe(502); expect(performance.now() - started).toBeLessThan(5000);
    expect(requests.length).toBe(count);
    await app.store.flush();
    expect((await app.store.detail(result.id))?.request.state).toBe('error');
    mode = 'normal';
    const next = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '传输失败后的下一轮' }], stream: false });
    expect(next.response.status).toBe(200); expect(requests.length - count).toBe(1);
    expect(nativeEngine.workerPid).not.toBe(pid); assertCch(requests.at(-1)!.raw);
  });

  test('采集输出失败时取消唯一发送并退役，下一轮不接收迟到事件', async () => {
    mode = 'normal';
    const pid = nativeEngine.workerPid, count = requests.length;
    const prepared = prepareInput(parseInput({ request_id: 'native-emission-failure', body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '合成采集输出失败' }], stream: true } }));
    const started = performance.now();
    await expect(nativeEngine.run(prepared, new AbortController().signal, async event => {
      if (event.type === 'cc_prepared') throw new Error('合成事件消费者失败');
    })).rejects.toThrow('合成事件消费者失败');
    expect(performance.now() - started).toBeLessThan(5000);
    expect(nativeEngine.workerPid).toBeNull();
    const next = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '采集输出失败后的新请求' }], stream: false });
    expect(next.response.status).toBe(200); expect(next.raw).toBe(expectedResponse);
    expect(nativeEngine.workerPid).not.toBe(pid);
    const observed = requests.slice(count);
    expect(observed.filter(value => JSON.stringify(value.body.messages).includes('合成采集输出失败')).length).toBeLessThanOrEqual(1);
    expect(observed.filter(value => JSON.stringify(value.body.messages).includes('采集输出失败后的新请求'))).toHaveLength(1);
    for (const request of observed) assertCch(request.raw);
  });

  test.each([['sse_error', 'stream_error'], ['incomplete', 'incomplete']] as const)('真实原生 %s 的日志终态正确', async (kind, state) => {
    mode = kind;
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '流终态验证' }], stream: true });
    expect(result.raw).toBe(expectedResponse);
    await app.store.flush();
    expect((await fetch(base + '/api/logs/' + result.id).then(r => r.json())).request.state).toBe(state);
  });

  test('取消传播至原生流，下一请求继续运行且取消请求没有重试', async () => {
    mode = 'slow'; const count = requests.length;
    const cancel = new AbortController();
    const response = await fetch(base + '/api/requests', {
      method: 'POST', signal: cancel.signal, headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ request_id: 'native-cancel', body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '取消验证' }], stream: true } }),
    });
    const reader = response.body!.getReader(); void reader.closed.catch(() => {});
    const canceledPid = nativeEngine.workerPid;
    await reader.read(); cancel.abort(); await reader.cancel().catch(() => {});
    let state: string | undefined;
    for (let i = 0; i < 100; i++) {
      await Bun.sleep(25); await app.store.flush();
      state = (await app.store.detail('native-cancel'))?.request.state;
      if (state && !['queued', 'running'].includes(state)) break;
    }
    expect(state).toBe('canceled'); expect(requests.length - count).toBe(1);
    expect((await app.store.detail('native-cancel'))?.captures.find(item => item.stage === 'upstream_response')?.status).toBe('incomplete');
    mode = 'normal';
    const next = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '取消后的下一请求' }], stream: false });
    expect(next.response.status).toBe(200); expect(next.raw).toBe(expectedResponse);
    expect(nativeEngine.workerPid).not.toBe(canceledPid);
    expect(requests.length - count).toBe(2);
  });

  test('相同 session 的多轮保持同一 PID，主子代理与 Unicode 正文不串入下一轮', async () => {
    mode = 'normal';
    const sessionId = '55555555-5555-4555-8555-555555555555';
    let pid: number | null = null;
    for (let i = 0; i < 6; i++) {
      const promptId = '66666666-6666-4666-8666-' + String(i).padStart(12, '0');
      const text = '第 ' + i + ' 轮：中文 العربية ภาษาไทย e\u0301 👨‍👩‍👧‍👦';
      const count = requests.length;
      const extra = i % 2 === 0 ? {} : { agentId: 'child-' + i, parentAgentId: 'parent-' + i, agentType: 'Explore' };
      const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: text }], stream: false }, { sessionId, promptId, ...extra });
      expect(result.response.status).toBe(200);
      expect(requests.length - count).toBe(1);
      pid ??= nativeEngine.workerPid;
      expect(nativeEngine.workerPid).toBe(pid);
      const request = requests.at(-1)!;
      const headers = new Headers(request.headers);
      expect(headers.get('x-claude-code-prompt-id')).toBe(promptId);
      expect(headers.get('x-claude-code-session-id')).toBe(sessionId);
      expect(headers.get('x-claude-code-agent-id')).toBe(i % 2 ? 'child-' + i : null);
      expect(request.raw).toContain('cc_prompt_id=' + promptId);
      expect(JSON.stringify(request.body.messages)).toContain(text);
      if (i) expect(request.raw).not.toContain('第 ' + (i - 1) + ' 轮');
      assertCch(request.raw);
      await app.store.flush();
      expect((await app.store.detail(result.id))?.request.binarySha256).toBe(nativeEngine.binarySha256);
    }
  });

  test('暖进程交替模型和工具后恢复原生正文，不复用其它条件的静态文本', async () => {
    mode = 'normal';
    const count = requests.length;
    const pid = nativeEngine.workerPid;
    const variants = [
      { model: 'claude-sonnet-4-6' },
      { model: 'claude-opus-4-6' },
      { model: 'claude-haiku-4-5' },
      { model: 'claude-sonnet-4-6', tools: [] },
      { model: 'claude-sonnet-4-6', tools: [{ name: 'static_cache_probe', description: '离线工具声明', input_schema: { type: 'object', properties: {} } }] },
      { model: 'claude-sonnet-4-6' },
    ];
    const systems: unknown[][] = [];
    for (const [index, variant] of variants.entries()) {
      const text = '静态正文条件切换 ' + index;
      const result = await send({ ...variant, messages: [{ role: 'user', content: text }], stream: false });
      expect(result.response.status).toBe(200);
      expect(nativeEngine.workerPid).toBe(pid);
      const request = requests.at(-1)!;
      expect(request.body.model).toBe(variant.model);
      expect(request.raw).toContain(text);
      if ('tools' in variant) expect(request.body.tools).toEqual(variant.tools);
      else expect(request.body.tools).toEqual([]);
      systems.push((request.body.system as unknown[]).slice(1));
      assertCch(request.raw);
    }
    expect(requests.length - count).toBe(variants.length);
    expect(systems.at(-1)).toEqual(systems[0]);
  });

  test('进程意外退出后下一作业重建，不重放已完成请求', async () => {
    const pid = nativeEngine.workerPid!;
    process.kill(pid, 'SIGKILL');
    for (let i = 0; i < 100 && nativeEngine.workerPid; i++) await Bun.sleep(10);
    const count = requests.length;
    const result = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '崩溃后的下一轮' }], stream: false });
    expect(result.response.status).toBe(200);
    expect(nativeEngine.workerPid).not.toBe(pid);
    expect(requests.length - count).toBe(1);
  });

  test('流中进程被终止时保留已返回字节，收口后下一轮重建且不重放', async () => {
    mode = 'slow';
    const count = requests.length;
    const response = await fetch(base + '/api/requests', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ request_id: 'native-stream-crash', body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '流中故障验证' }], stream: true } }) });
    const reader = response.body!.getReader();
    const first = await reader.read();
    expect(Buffer.from(first.value!).toString()).toContain('message_start');
    const pid = nativeEngine.workerPid!;
    process.kill(pid, 'SIGKILL');
    while (!(await reader.read()).done) {}
    await app.store.flush();
    const detail = await app.store.detail('native-stream-crash');
    expect(detail?.request.state).toBe('error');
    expect(detail?.captures.find(item => item.stage === 'upstream_response')?.status).toBe('incomplete');
    expect(requests.length - count).toBe(1);
    mode = 'normal';
    const next = await send({ model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '流故障后的下一轮' }], stream: false });
    expect(next.response.status).toBe(200);
    expect(nativeEngine.workerPid).not.toBe(pid);
    expect(requests.length - count).toBe(2);
  });

  test('sub2api 实际原生发送保留所有权、缓存预算与原生 CCH', async () => {
    mode = 'normal';
    const dedicated = join(root, 'cache-policy');
    await mkdir(join(dedicated, 'home'), { recursive: true });
    await mkdir(join(dedicated, 'config'));
    await writeFile(join(dedicated, 'config', '.claude.json'), JSON.stringify({ userID: 'd'.repeat(64) }));
    const settings = { ...config, dataDir: join(dedicated, 'data'), engine: { ...config.engine, cachePolicy: 'sub2api' as const, home: join(dedicated, 'home'), configDir: join(dedicated, 'config'), cwd: join(dedicated, 'home') } };
    const local = await startServer(settings);
    const messages = [{ role: 'user', content: 'u1' }, { role: 'assistant', content: 'a1' }, { role: 'user', content: 'u2' }, { role: 'assistant', content: 'a2' }, { role: 'user', content: 'u3' }];
    const scenarios: [string, Record<string, unknown>, string][] = [
      ['api', { model: 'claude-sonnet-4-6', system: '缓存测试', messages, max_tokens: 128, stream: false }, '已应用 sub2api'],
      ['native', nativeBody({ messages }), '已应用 sub2api'],
      ['caller-marked', nativeBody(), '调用方已有消息缓存断点'],
      ['automatic', nativeBody({ messages, cache_control: { type: 'ephemeral' } }), '保留根级缓存机制'],
      ['budget', nativeBody({ messages, tools: Array.from({ length: 4 }, (_, index) => ({ name: 't' + index, input_schema: { type: 'object' }, cache_control: { type: 'ephemeral', ttl: '1h' } })), system: (nativeBody().system as unknown[]).slice(0, 1) }), '预算已用完'],
    ];
    try {
      const health = await fetch('http://127.0.0.1:' + local.server.port + '/api/health').then(response => response.json());
      expect(health.runtimePolicy.cachePolicy).toBe('sub2api');
      for (const [name, body, note] of scenarios) {
        const count = requests.length;
        const before = structuredClone(body);
        const response = await fetch('http://127.0.0.1:' + local.server.port + '/api/requests', { method: 'POST', headers: { 'content-type': 'application/json', 'CCRB_CACHE_POLICY': 'preserve' }, body: JSON.stringify({ request_id: 'policy-' + name, body }) });
        const raw = await response.text();
        expect(response.status).toBe(200);
        expect(raw).toContain('msg_native_fixture');
        expect(requests.length - count).toBe(1);
        const wire = requests.at(-1)!;
        assertCch(wire.raw);
        await local.store.flush();
        const detail = await local.store.detail('policy-' + name);
        const prepared = detail?.captures.find(capture => capture.stage === 'cc_prepared');
        expect(prepared?.note).toContain(note);
        expect(detail?.captures.find(capture => capture.stage === 'wire_final')?.status).toBe('unavailable');
        if (name === 'native') {
          expect((wire.body.messages as { content: unknown }[])[2]!.content).toEqual([{ type: 'text', text: 'u2', cache_control: { type: 'ephemeral', ttl: '5m' } }]);
          expect((wire.body.messages as { content: unknown }[])[4]!.content).toEqual([{ type: 'text', text: 'u3', cache_control: { type: 'ephemeral', ttl: '5m' } }]);
        }
        if (name === 'caller-marked' || name === 'automatic' || name === 'budget') expect(wire.body.messages).toEqual(body.messages);
        expect(body).toEqual(before);
        policyCases.push({ name, body, raw: wire.raw, detail });
      }
    } finally { await local.close(); }
  }, 30000);

  test('第一方遥测只采集真实业务，关闭零上传且不影响缓存与模型单次发送', async () => {
    mode = 'normal';
    const combinations = [
      { cache: 'preserve', telemetry: 'off', failure: 'normal' },
      { cache: 'sub2api', telemetry: 'off', failure: 'normal' },
      { cache: 'preserve', telemetry: 'on', failure: 'normal' },
      { cache: 'sub2api', telemetry: 'on', failure: 'normal' },
      { cache: 'preserve', telemetry: 'on', failure: 'error' },
      { cache: 'preserve', telemetry: 'on', failure: 'slow' },
    ] as const;
    for (const combination of combinations) {
      telemetryMode = combination.failure;
      const key = [combination.cache, combination.telemetry, combination.failure].join('-');
      const dedicated = join(root, 'telemetry-' + key);
      await mkdir(join(dedicated, 'home'), { recursive: true });
      await mkdir(join(dedicated, 'config'));
      await writeFile(join(dedicated, 'config', '.claude.json'), JSON.stringify({ userID: 'e'.repeat(64) }));
      const settings = { ...config, dataDir: join(dedicated, 'data'), engine: { ...config.engine, cachePolicy: combination.cache, telemetryPolicy: combination.telemetry, home: join(dedicated, 'home'), configDir: join(dedicated, 'config'), cwd: join(dedicated, 'home') } };
      const local = await startServer(settings);
      const modelsBefore = requests.length, telemetryBefore = telemetryRequests.length, targetsBefore = proxyTargets.length, proxyHttpBefore = proxyHttpRequests.length, auxiliaryBefore = auxiliaryRequests.length;
      const sessions = new Set<string>();
      const times: number[] = [];
      let closed = false;
      try {
        const healthUrl = 'http://127.0.0.1:' + local.server.port + '/api/health';
        expect((await fetch(healthUrl).then(response => response.json())).runtimePolicy.telemetryState).toBe(combination.telemetry === 'on' ? 'pending' : 'off');
        for (let round = 0; round < 2; round++) {
          const started = performance.now();
          const id = 'telemetry-' + key + '-' + round;
          const body = { model: 'claude-sonnet-4-6', system: '第一方遥测离线验证', messages: [{ role: 'user', content: 'u1' }, { role: 'assistant', content: 'a1' }, { role: 'user', content: 'u2' }, { role: 'assistant', content: 'a2' }, { role: 'user', content: 'u3' }], max_tokens: 128, stream: false };
          const context = round ? { requestClass: 'subagent', agentId: 'telemetry-child', parentAgentId: 'telemetry-parent', agentType: 'Explore' } : {};
          const response = await fetch('http://127.0.0.1:' + local.server.port + '/api/requests', { method: 'POST', headers: { 'content-type': 'application/json', 'CCRB_TELEMETRY': combination.telemetry === 'on' ? 'off' : 'on' }, body: JSON.stringify({ request_id: id, body, context }) });
          const text = await response.text();
          expect(response.status).toBe(200);
          expect(text).toContain('msg_native_fixture');
          times.push(performance.now() - started);
          assertCch(requests.at(-1)!.raw);
          await local.store.flush();
          const detail = await local.store.detail(id);
          expect(detail?.request.state).toBe('success');
          sessions.add(detail!.context!.sessionId);
        }
        const state = (await fetch(healthUrl).then(response => response.json())).runtimePolicy;
        expect(state.telemetry).toBe(combination.telemetry);
        expect(state.telemetryState).toBe(combination.telemetry === 'on' ? 'initialized' : 'off');
        const closeStarted = performance.now();
        await local.close(); closed = true;
        const closeMs = performance.now() - closeStarted;
        expect(closeMs).toBeLessThan(2200);
        const uploads = telemetryRequests.slice(telemetryBefore);
        const events = uploads.flatMap(request => request.body.events);
        if (combination.telemetry === 'off') expect(uploads.length).toBe(0);
        else {
          expect(events.length).toBeGreaterThan(0);
          for (const event of events) {
            expect(event.event_type).toBe('ClaudeCodeInternalEvent');
            expect(sessions.has(String(event.event_data.session_id))).toBe(true);
            expect(event.event_data.device_id).toBe('e'.repeat(64));
            expect(event.event_data.entrypoint).toBe('cli');
            if (typeof event.event_data.process === 'string') {
              const metrics = JSON.parse(Buffer.from(event.event_data.process, 'base64').toString());
              expect(metrics.rss).toBeGreaterThan(0);
              expect(metrics.cpuUsage.user).toBeGreaterThanOrEqual(0);
            }
          }
          expect(JSON.stringify(uploads.map(request => request.body))).not.toContain(upstreamSecret);
        }
        expect(requests.length - modelsBefore).toBe(2);
        const targets = proxyTargets.slice(targetsBefore);
        expect(targets.length).toBeGreaterThan(0);
        expect(targets.every(target => target === 'api.anthropic.com:443')).toBe(true);
        expect(proxyHttpRequests.length - proxyHttpBefore).toBe(0);
        expect(auxiliaryRequests.slice(auxiliaryBefore)).toEqual([]);
        if (combination.failure !== 'normal') expect(times[1]!).toBeLessThan(1000);
        telemetryCases.push({ ...combination, state, model_requests: requests.length - modelsBefore, telemetry_requests: uploads.length, event_names: events.map(event => event.event_data.event_name), sessions: [...sessions], times_ms: times, close_ms: closeMs });
      } finally { if (!closed) await local.close(); telemetryMode = 'normal'; }
    }
  }, 90000);

  test('开启遥测时取消退役有界，重建后事件仍归属各自业务会话', async () => {
    const dedicated = join(root, 'telemetry-cancel-rebuild');
    await mkdir(join(dedicated, 'home'), { recursive: true });
    await mkdir(join(dedicated, 'config'));
    await writeFile(join(dedicated, 'config', '.claude.json'), JSON.stringify({ userID: 'e'.repeat(64) }));
    const settings = { ...config, dataDir: join(dedicated, 'data'), engine: { ...config.engine, telemetryPolicy: 'on' as const, home: join(dedicated, 'home'), configDir: join(dedicated, 'config'), cwd: join(dedicated, 'home') } };
    const engine = await createEngine(settings.engine);
    const local = await startServer(settings, engine);
    const localBase = 'http://127.0.0.1:' + local.server.port;
    const modelsBefore = requests.length, telemetryBefore = telemetryRequests.length, targetsBefore = proxyTargets.length, auxiliaryBefore = auxiliaryRequests.length, proxyHttpBefore = proxyHttpRequests.length;
    const cancel = new AbortController();
    let closed = false;
    try {
      mode = 'slow';
      const response = await fetch(localBase + '/api/requests', { method: 'POST', signal: cancel.signal, headers: { 'content-type': 'application/json' }, body: JSON.stringify({ request_id: 'telemetry-cancel', body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '遥测取消验证' }], stream: true } }) });
      expect(response.status).toBe(200);
      const reader = response.body!.getReader(); void reader.closed.catch(() => {});
      await reader.read();
      const canceledPid = engine.workerPid;
      const cancelStarted = performance.now();
      cancel.abort(); await reader.cancel().catch(() => {});
      let canceled = await local.store.detail('telemetry-cancel');
      for (let i = 0; i < 120; i++) {
        await local.store.flush(); canceled = await local.store.detail('telemetry-cancel');
        if (canceled?.request.state === 'canceled' && engine.workerPid === null) break;
        await Bun.sleep(25);
      }
      const cancelMs = performance.now() - cancelStarted;
      expect(cancelMs).toBeLessThan(3000);
      expect(canceled?.request.state).toBe('canceled');
      expect(engine.workerPid).toBeNull();
      expect(requests.length - modelsBefore).toBe(1);
      expect((await fetch(localBase + '/api/health').then(value => value.json())).runtimePolicy.telemetryState).toBe('pending');
      mode = 'normal';
      const next = await fetch(localBase + '/api/requests', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ request_id: 'telemetry-rebuilt', body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '遥测重建后的下一轮' }], stream: false } }) });
      expect(next.status).toBe(200); expect(await next.text()).toBe(expectedResponse);
      expect(engine.workerPid).not.toBe(canceledPid);
      expect(engine.telemetryState).toBe('initialized');
      await local.store.flush();
      const rebuilt = await local.store.detail('telemetry-rebuilt');
      expect(rebuilt?.request.state).toBe('success');
      const sessions = [canceled!.context!.sessionId, rebuilt!.context!.sessionId];
      expect(sessions[0]).not.toBe(sessions[1]);
      const closeStarted = performance.now();
      await local.close(); closed = true;
      const closeMs = performance.now() - closeStarted;
      expect(closeMs).toBeLessThan(2200);
      const uploads = telemetryRequests.slice(telemetryBefore), events = uploads.flatMap(request => request.body.events);
      expect(events.some(event => event.event_data.session_id === sessions[1])).toBe(true);
      for (const event of events) {
        expect(sessions).toContain(String(event.event_data.session_id));
        expect(event.event_data.device_id).toBe('e'.repeat(64));
        expect(event.event_data.entrypoint).toBe('cli');
      }
      expect(requests.length - modelsBefore).toBe(2);
      for (const request of requests.slice(modelsBefore)) assertCch(request.raw);
      expect(proxyTargets.slice(targetsBefore).every(target => target === 'api.anthropic.com:443')).toBe(true);
      expect(proxyHttpRequests.length - proxyHttpBefore).toBe(0);
      expect(auxiliaryRequests.slice(auxiliaryBefore)).toEqual([]);
      telemetryCases.push({ lifecycle: 'cancel-rebuild', telemetry: 'on', model_requests: requests.length - modelsBefore, telemetry_requests: uploads.length, sessions, event_names: events.map(event => event.event_data.event_name), cancel_ms: cancelMs, close_ms: closeMs });
    } finally { cancel.abort(); mode = 'normal'; if (!closed) await local.close(); }
  }, 30000);

  function nativeBody(extra: Record<string, unknown> = {}): Record<string, unknown> {
    return { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: [{ type: 'text', text: '原生正文保真验证', cache_control: { type: 'ephemeral', ttl: '5m' } }] }], system: [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=12345; cc_prompt_id=11111111-1111-4111-8111-111111111111; cc_turn_origin=human; cc_prompt_index=3; cc_turn_index=4;' }, { type: 'text', text: '原生调用方业务 system', cache_control: { type: 'ephemeral', ttl: '5m' } }], metadata: { user_id: JSON.stringify({ device_id: 'c'.repeat(64), account_uuid: '44444444-4444-4444-8444-444444444444', session_id: '22222222-2222-4222-8222-222222222222' }), trace_extension: 'kept' }, max_tokens: 128, stream: false, ...extra };
  }
  const nativeTool = { name: 'lookup_status', input_schema: { type: 'object', properties: {} } };
  const nativeHistory = [{ role: 'user', content: '查询状态' }, { role: 'assistant', content: [{ type: 'thinking', thinking: '已有推理', signature: 'synthetic-native-signature' }, { type: 'tool_use', id: 'toolu_native_history', name: 'lookup_status', input: {} }] }, { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_native_history', content: 'ready' }] }];
  test.each(['api', 'claude_code'] as const)('根本机设置被清理，TLS 实收只包含业务工具字段：%s', async format => {
    mode = 'normal';
    const tool = { name: 'set_config', input_schema: { type: 'object', properties: { settings: { type: 'object' }, claude_settings: { type: 'string' }, env: { type: 'object' } } } };
    const base = format === 'claude_code' ? nativeBody() : { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '离线设置清理验证' }], stream: false };
    const body = { ...base, tools: [tool], settings: { env: { ANTHROPIC_BASE_URL: 'https://untrusted.invalid' } }, claude_settings: { hooks: { synthetic: 'never-execute' } }, env: { PATH: '/untrusted', ANTHROPIC_API_KEY: 'ignored-settings-canary' } };
    const before = structuredClone(body), count = requests.length;
    const result = await send(body);
    expect(result.response.status).toBe(200); expect(requests.length - count).toBe(1);
    const wire = requests.at(-1)!;
    for (const key of ['settings', 'claude_settings', 'env']) expect(Object.hasOwn(wire.body, key)).toBe(false);
    expect(wire.body.tools).toHaveLength(1); expect(wire.body.tools).toMatchObject([tool]);
    expect(body).toEqual(before);
    expect(wire.raw).not.toContain('ignored-settings-canary');
    assertCch(wire.raw);
  });
  test.each(['api', 'claude_code'] as const)('协议白名单过滤客户端附加头，合法多值覆盖 SDK 默认值：%s', async format => {
    mode = 'normal';
    const body = format === 'claude_code' ? nativeBody() : { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '离线头部合并验证' }], stream: false };
    for (const [accept, browserAccess] of [['application/json', 'true'], ['application/json;q=0.9', 'false']] as const) {
      const count = requests.length;
      const dropped: HeaderPair[] = [['X-Forwarded-For', '198.51.100.10'], ['x-forwarded-for', '198.51.100.11'], ['X-Real-IP', '198.51.100.10'], ['Via', 'synthetic-proxy'], ['X-Amz-Cf-Id', 'synthetic-cdn'], ['CloudFront-Viewer-Country', 'CN'], ['New-Api-User', 'synthetic-user'], ['X-Oneapi-Request-Id', 'synthetic-request'], ['Traceparent', 'synthetic-trace'], ['x-claude-code-future', 'synthetic'], ['x-future-feature', 'synthetic']];
      const optional: HeaderPair[] = [['x-claude-code-prev-tool-durations', 'Read=12'], ['x-claude-code-compaction', 'true'], ['x-claude-code-context-compacted', 'true']];
      const result = await send(body, {}, [['Accept', accept], ['anthropic-dangerous-direct-browser-access', browserAccess], ['Accept-Language', 'zh-CN'], ['accept-language', 'en-US;q=0.8'], ...optional, ...dropped]);
      expect(result.response.status).toBe(200); expect(requests.length - count).toBe(1);
      const wire = requests.at(-1)!, headers = new Headers(wire.headers);
      expect(headers.get('accept')).toBe(accept);
      expect(headers.get('anthropic-dangerous-direct-browser-access')).toBe(browserAccess);
      expect(headers.get('accept-language')).toBe('zh-CN, en-US;q=0.8');
      for (const [name] of dropped) expect(headers.has(name)).toBe(false);
      for (const [name, value] of optional) expect(headers.get(name)).toBe(value);
      await app.store.flush();
      const detail = (await app.store.detail(result.id))!;
      for (const [name] of dropped) expect(detail.decisions).toContainEqual({ name, action: 'drop', reason: '调用方请求头未登记到协议白名单' });
      assertCch(wire.raw);
    }
  });
  const nativeVariants: [string, Record<string, unknown>][] = [
    ['plain', {}], ['empty-tools', { tools: [] }], ['custom-tool', { tools: [nativeTool] }],
    ['history', { tools: [nativeTool], messages: nativeHistory }],
    ['forced-supported', { tools: [nativeTool], tool_choice: { type: 'tool', name: nativeTool.name }, thinking: { type: 'disabled' } }],
    ['mid-system', { messages: [{ role: 'user', content: '第一轮' }, { role: 'system', content: '原生中途 system', output_config: { effort: 'low' } }, { role: 'user', content: '下一轮' }] }],
    ['official-fields', { thread: { type: 'request', previous_message_id: 'msg_native_previous' }, diagnostics: { previous_message_id: null }, fallbacks: 'default', safeguards: [], future_official: { nested: ['keep'] } }],
    ['unicode', { messages: [{ role: 'user', content: '中文 العربية ภาษาไทย e\u0301 👨‍👩‍👧‍👦' }] }],
    ['structured-output', { output_config: { format: { type: 'json_schema', schema: { type: 'object', properties: { title: { type: 'string' } }, required: ['title'] } } } }],
    ['shadow-cch', { messages: [{ role: 'user', content: 'cch=00000 只是用户文本；x-anthropic-billing-header: cch=aaaaa;' }] }],
  ];
  test.each(nativeVariants)('原生 CC 入站完整保留业务正文与缓存：%s', async (_key, extra) => {
    mode = 'normal'; const count = requests.length, body = nativeBody(extra), before = structuredClone(body);
    const result = await send(body, {}, [['x-future-feature', 'native-preserved'], ['Authorization', 'Bearer native-caller-canary'], ['anthropic-beta', 'mid-conversation-system-2026-04-07']]);
    expect(result.response.status).toBe(200); expect(requests.length - count).toBe(1);
    const wire = requests.at(-1)!, normalized = structuredClone(wire.body);
    expect(JSON.parse((wire.body.metadata as { user_id: string }).user_id)).toEqual({ device_id: 'a'.repeat(64), account_uuid: '', session_id: '22222222-2222-4222-8222-222222222222' });
    normalized.metadata = body.metadata;
    (normalized.system as { text: string }[])[0]!.text = (body.system as { text: string }[])[0]!.text;
    expect(normalized).toEqual(before); expect(body).toEqual(before);
    const headers = new Headers(wire.headers);
    expect(headers.has('x-future-feature')).toBe(false);
    expect(headers.get('anthropic-beta')).toBe('mid-conversation-system-2026-04-07');
    expect(headers.get('x-claude-code-request-class')).toBe('main');
    assertCch(wire.raw);
    await app.store.flush(); const detail = await app.store.detail(result.id);
    expect(detail?.context?.inputFormat).toBe('claude_code');
    expect(detail?.captures.find(c => c.stage === 'cc_prepared')?.source).toBe('claude_code_293_native_ingress_prepared');
    expect(JSON.stringify(detail)).not.toContain('native-caller-canary');
  });

  test('原生省略 stream/max_tokens/tools 不由 SDK 种子补入', async () => {
    const body = nativeBody(); delete body.stream; delete body.max_tokens;
    const result = await send(body); expect(result.response.status).toBe(200);
    const wire = requests.at(-1)!;
    for (const key of ['stream', 'max_tokens', 'tools']) expect(Object.hasOwn(wire.body, key)).toBe(false);
    assertCch(wire.raw);
  });

  test.each(['main', 'subagent', 'workflow', 'compaction', 'auxiliary', 'side_reply'])('原生 CC 六类归因保持一致：%s', async requestClass => {
    const child = requestClass === 'subagent' || requestClass === 'workflow';
    const body = nativeBody({ tools: [nativeTool], messages: nativeHistory });
    if (child) (body.system as { text: string }[])[0]!.text += ' cc_is_subagent=true;';
    const context = { requestClass, ...(child ? { agentId: 'native-child', parentAgentId: 'native-parent', agentType: 'Explore' } : {}), ...(requestClass === 'workflow' ? { workflowRunId: 'native-workflow' } : {}) };
    const result = await send(body, context); expect(result.response.status).toBe(200);
    const wire = requests.at(-1)!, headers = new Headers(wire.headers);
    expect(headers.get('x-claude-code-request-class')).toBe(requestClass);
    expect(headers.get('x-claude-code-agent-id')).toBe(child ? 'native-child' : null);
    expect(headers.get('x-claude-code-parent-agent-id')).toBe(child ? 'native-parent' : null);
    expect(wire.body.messages).toEqual(body.messages); expect(wire.body.tools).toEqual(body.tools); assertCch(wire.raw);
  });

  test.each(['main', 'subagent'])('普通 API 无 thinking 历史的原生提醒合并不再被误判：%s', async requestClass => {
    const context = requestClass === 'subagent' ? { requestClass, agentId: 'history-child', parentAgentId: 'history-parent', agentType: 'Explore' } : {};
    const messages = nativeHistory.map(message => message.role === 'assistant' ? { ...message, content: (message.content as { type: string }[]).filter(block => block.type !== 'thinking') } : message);
    const started = performance.now();
    const result = await send({ model: 'claude-sonnet-5-5', messages, tools: [nativeTool], stream: true }, context);
    expect(result.response.status).toBe(200); expect(performance.now() - started).toBeLessThan(10000);
    expect(requests.at(-1)!.raw).toContain('toolu_native_history'); assertCch(requests.at(-1)!.raw);
  });

  test.each(['main', 'subagent', 'workflow', 'compaction', 'auxiliary', 'side_reply'])('普通 API 工具续轮的 Prompt ID 与实际用户轮次一致：%s', async requestClass => {
    mode = 'normal';
    const promptId = '77777777-7777-4777-8777-777777777777';
    const sessionId = '88888888-8888-4888-8888-888888888888';
    const child = requestClass === 'subagent' || requestClass === 'workflow';
    const context = { requestClass, promptId, sessionId, ...(child ? { agentId: 'tool-child', parentAgentId: 'tool-parent', agentType: 'Explore' } : {}), ...(requestClass === 'workflow' ? { workflowRunId: 'tool-workflow' } : {}) };
    const messages = nativeHistory.map(message => message.role === 'assistant' ? { ...message, content: (message.content as { type: string }[]).filter(block => block.type !== 'thinking') } : message);
    const before = requests.length;
    const result = await send({ model: 'claude-sonnet-5-5', messages, tools: [nativeTool], stream: true }, context);
    expect(result.response.status).toBe(200); expect(requests.length).toBe(before + 1);
    const wire = requests.at(-1)!, headers = new Headers(wire.headers);
    expect(headers.get('x-claude-code-prompt-id')).toBe(promptId);
    expect(headers.get('x-claude-code-session-id')).toBe(sessionId);
    expect(wire.raw).toContain('cc_prompt_id=' + promptId);
    const detail = await app.store.detail(result.id);
    expect(detail?.context?.promptId).toBe(promptId);
    expect(detail?.request.promptId).toBe(promptId);
    assertCch(wire.raw);
  });

  test('普通 API 工具续轮自动 ID、多个用户轮次与混合结果保持同次归因', async () => {
    mode = 'normal';
    const messages = [
      ...nativeHistory.map(message => message.role === 'assistant' ? { ...message, content: (message.content as { type: string }[]).filter(block => block.type !== 'thinking') } : message),
      { role: 'user', content: '继续查询最新状态' },
      { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_second', name: 'lookup_status', input: {} }] },
      { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_second', content: 'new-ready' }, { type: 'text', text: '客户端补充的结果说明' }] },
    ];
    const sessionId = '99999999-9999-4999-8999-999999999999';
    const ids: string[] = [];
    for (let round = 0; round < 2; round++) {
      const before = requests.length;
      const result = await send({ model: 'claude-sonnet-5-5', messages, tools: [nativeTool], stream: true }, { sessionId });
      expect(result.response.status).toBe(200); expect(requests.length).toBe(before + 1);
      const detail = (await app.store.detail(result.id))!;
      ids.push(detail.context!.promptId);
      const wire = requests.at(-1)!;
      expect(new Headers(wire.headers).get('x-claude-code-prompt-id')).toBe(detail.context!.promptId);
      expect(detail.context!.promptId).not.toBe(sessionId);
      expect(wire.raw).toContain('new-ready'); expect(wire.raw).toContain('客户端补充的结果说明');
      assertCch(wire.raw);
    }
    expect(ids[0]).not.toBe(ids[1]);
  });

  test('工具续轮缺少可归属用户轮次时明确拒绝且零发送', async () => {
    const before = requests.length;
    const result = await send({ model: 'claude-sonnet-5-5', messages: nativeHistory.slice(1), tools: [nativeTool], stream: true });
    expect(result.response.status).toBe(422);
    expect(JSON.parse(result.raw).error.type).toBe('unsupported_parameter');
    expect(requests.length).toBe(before);
  });

  test('原生版本和上下文冲突、私有控制字段在发送前明确拒绝', async () => {
    const wrong = nativeBody(); (wrong.system as { text: string }[])[0]!.text = (wrong.system as { text: string }[])[0]!.text.replace('2.1.293', '2.1.303');
    for (const [body, context] of [[wrong, {}], [nativeBody(), { sessionId: 'different' }], [nativeBody({ settings: {}, proxy_url: 'http://untrusted.invalid' }), {}]] as [Record<string, unknown>, Record<string, unknown>][]) {
      const count = requests.length, started = performance.now(); const result = await send(body, context);
      expect([400, 422]).toContain(result.response.status); expect(requests.length).toBe(count); expect(performance.now() - started).toBeLessThan(10000);
    }
  });

  test('原生模型参数原值到达回环上游，不用种子能力推断业务合法性', async () => {
    mode = 'normal';
    for (const change of [{ model: 'claude-sonnet-5', tools: [nativeTool], tool_choice: { type: 'tool', name: nativeTool.name } }, { thinking: { type: 'unknown' } }, { thinking: { type: 'enabled', budget_tokens: 1023 }, temperature: 2, max_tokens: 128000 }]) {
      const body = nativeBody(change), count = requests.length, result = await send(body);
      expect(result.response.status).toBe(200); expect(requests.length).toBe(count + 1);
      expect(requests.at(-1)!.body).toMatchObject(change); assertCch(requests.at(-1)!.raw);
    }
  });

  test('原生 26 MiB 正文穿过工作进程协议后完整到达 TLS 回环', async () => {
    mode = 'normal';
    const messages = [{ role: 'user', content: 'x'.repeat(26 * 1024 * 1024) }], count = requests.length;
    const result = await send(nativeBody({ model: 'claude-sonnet-5', messages }));
    expect(result.response.status).toBe(200); expect(requests.length).toBe(count + 1);
    expect(requests.at(-1)!.body.messages).toEqual(messages); assertCch(requests.at(-1)!.raw);
  }, 45000);

  test('原生 billing 的合法间隔保留且最终 CCH 有效', async () => {
    const body = nativeBody(), billing = (body.system as { text: string }[])[0]!;
    billing.text = billing.text.replace('cch=12345;', 'cch=12345 \t;');
    const count = requests.length, result = await send(body);
    expect(result.response.status).toBe(200); expect(requests.length - count).toBe(1);
    const wire = requests.at(-1)!;
    expect((wire.body.system as { text: string }[])[0]!.text).toContain(' \t;');
    assertCch(wire.raw);
    await app.store.flush();
    const detail = await app.store.detail(result.id);
    expect(detail?.captures.find(capture => capture.stage === 'cc_prepared')?.text).toContain('cch=00000 \\t;');
  });
});
