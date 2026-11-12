import { describe, expect, test } from 'bun:test';
import { mkdtemp, writeFile, chmod, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import { channel } from 'node:diagnostics_channel';
import { Redactor } from '../../src/control/redaction';
import { BodyCapture, CAPTURE_LIMIT, POOL_MODEL, decodeDriverFrame, decodeForwarderFrame, loadPoolConfig, poolLedgerName, poolMessagesUrl, poolProxyEnvironment, preparePoolRequest, sample, validatePoolConfig, verifyCch, type PoolConfig } from '../../scripts/testing/pool-common';
import { poolScenes } from '../../scripts/testing/pool-scenes';
import { safePoolSample } from '../../scripts/test-pool';
import { renderPoolReport, servePoolReport, type PoolReport } from '../../scripts/testing/pool-report';
import { LocalPoolLedger } from '../../scripts/testing/local-pool-ledger';
import { PoolTransportObserver } from '../../scripts/testing/pool-transport';

const secret = 'pool-canary-over-chunks-58af';
const config: PoolConfig = { baseUrl: 'http://127.0.0.1:1234/v1', apiKey: secret, live: false, maxRequests: 10, timeoutMs: 500 };
const redactor = new Redactor(); redactor.register({ api_key: secret });
const empty = sample('', redactor);

describe('池测试的配置、映射与有界采集', () => {
  test('手工模式原样转发输出预算，真实标志与旧验收限制不变', () => {
    const manual: PoolConfig = { ...config, baseUrl: 'https://pool.example/v1', live: true, mode: 'manual', maxRequests: 20 };
    expect(() => validatePoolConfig(manual)).not.toThrow();
    expect(() => validatePoolConfig({ ...manual, maxRequests: 21 })).toThrow('预算');
    expect(() => validatePoolConfig({ ...manual, maxRequests: null })).not.toThrow();
    expect(() => validatePoolConfig({ ...manual, timeoutMs: 0 })).not.toThrow();
    expect(() => validatePoolConfig({ ...config, timeoutMs: 0 })).toThrow('预算');
    expect(() => validatePoolConfig({ ...manual, mode: 'acceptance', maxRequests: null })).toThrow('预算');
    expect(() => validatePoolConfig({ ...config, maxRequests: null })).toThrow('预算');
    expect(() => validatePoolConfig({ ...manual, live: false })).toThrow('目标');
    const body = { model: 'claude-sonnet-4-6', max_tokens: 32000, messages: [] };
    expect(JSON.parse(preparePoolRequest(JSON.stringify(body), [], '/v1/messages', manual).body)).toEqual({ ...body, model: POOL_MODEL });
    for (const live of [true, false]) {
      const target = { ...manual, live, baseUrl: live ? manual.baseUrl : config.baseUrl };
      for (const max_tokens of [1, 32768, 32769, 128000, Number.MAX_SAFE_INTEGER]) {
        expect(JSON.parse(preparePoolRequest(JSON.stringify({ ...body, max_tokens }), [], '/v1/messages', target).body)).toEqual({ ...body, max_tokens, model: POOL_MODEL });
      }
    }
    expect(() => preparePoolRequest(JSON.stringify(body), [], '/v1/messages', { ...manual, mode: 'acceptance' })).toThrow('预算');
  });

  test('手工预算先持久预留，20 次耗尽且相同运行目录不能覆盖', async () => {
    const root = await mkdtemp(join(tmpdir(), 'ccrb-manual-ledger-'));
    try {
      const path = join(root, 'ledger.json'), ledger = await LocalPoolLedger.create(path, 'manual-unit', false, 20);
      for (let index = 0; index < 20; index++) await ledger.reserve('request-' + index);
      expect(ledger.status()).toMatchObject({ reserved: 20, remaining: 0, live: false });
      await expect(ledger.reserve('over-budget')).rejects.toThrow('额度');
      await ledger.finish('request-0', { attempted: true, upstreamStatus: null, statusCode: 502, outcome: 'error' });
      const saved = await Bun.file(path).json();
      expect(saved.reservations).toHaveLength(20); expect(saved.reservations[0]).toMatchObject({ attempted: true, upstreamStatus: null, localStatus: 502 });
      await expect(LocalPoolLedger.create(path, 'manual-unit', false, 20)).rejects.toThrow();
      expect(await Bun.file(path).json()).toEqual(saved);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  test('不限次数的手工账本持续计数，超过 20 次也保留结果', async () => {
    const root = await mkdtemp(join(tmpdir(), 'ccrb-manual-unlimited-'));
    try {
      const path = join(root, 'ledger.json'), ledger = await LocalPoolLedger.create(path, 'manual-unlimited', false, null);
      for (let index = 0; index < 25; index++) await ledger.reserve('request-' + index);
      await ledger.finish('request-24', { attempted: true, upstreamStatus: 200, statusCode: 200, outcome: 'success' });
      expect(ledger.status()).toMatchObject({ budget: null, remaining: null, reserved: 25 });
      const saved = await Bun.file(path).json();
      expect(saved.budget).toBeNull(); expect(saved.reservations).toHaveLength(25); expect(saved.reservations[24].upstreamStatus).toBe(200);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  test('断连诊断经过私有边界后持久化，未知字段和任意错误码不落账本', async () => {
    const root = await mkdtemp(join(tmpdir(), 'ccrb-pool-diagnostics-'));
    try {
      const path = join(root, 'ledger.json'), ledger = await LocalPoolLedger.create(path, 'diagnostics-unit', false, null);
      await ledger.reserve('socket-failure');
      const frame = decodeForwarderFrame(JSON.stringify({ type: 'finished', id: 1, attempted: true, outcome: 'error', statusCode: 502, upstreamStatus: null, headers: [], response: empty, failureCode: 'UND_ERR_SOCKET', transportDiagnostics: { phase: 'awaiting_headers', bodySentObserved: true, connectionBytesWritten: 322, connectionBytesRead: 0, api_key: secret } }));
      if (frame.type !== 'finished') throw new Error('断连回执类型错误');
      await ledger.finish('socket-failure', frame);
      const saved = await Bun.file(path).json();
      expect(saved.reservations[0]).toMatchObject({ upstreamStatus: null, localStatus: 502, failureCode: 'UND_ERR_SOCKET', transportDiagnostics: { phase: 'awaiting_headers', bodySentObserved: true, connectionBytesWritten: 322, connectionBytesRead: 0 } });
      expect(JSON.stringify(frame)).not.toContain(secret); expect(JSON.stringify(saved)).not.toContain(secret);
      const damaged = decodeForwarderFrame(JSON.stringify({ ...frame, failureCode: secret, transportDiagnostics: { phase: secret, bodySentObserved: 'true', connectionBytesWritten: -1, connectionBytesRead: '0', raw: secret } }));
      if (damaged.type !== 'finished') throw new Error('损坏观测不能改变正常回执类型');
      expect(damaged.failureCode).toBe('POOL_FETCH_ERROR');
      expect(damaged.transportDiagnostics).toEqual({ phase: 'unknown', bodySentObserved: null, connectionBytesWritten: null, connectionBytesRead: null });
      expect(JSON.stringify(damaged)).not.toContain(secret);
      await ledger.reserve('legacy-result');
      await ledger.finish('legacy-result', { attempted: true, upstreamStatus: 200, statusCode: 200, outcome: 'success' });
      const legacy = (await Bun.file(path).json()).reservations[1];
      expect(legacy.failureCode).toBeUndefined(); expect(legacy.transportDiagnostics).toBeUndefined();
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  test('诊断回调失效不改变原操作结果，关闭后不遗留订阅', async () => {
    const source = channel('undici:request:create'), hadSubscribers = source.hasSubscribers;
    const observer = new PoolTransportObserver();
    try {
      expect(await observer.run(async () => {
        source.publish({ request: { get method(): string { throw new Error('合成观测失败'); } } });
        return '原调用结果';
      })).toBe('原调用结果');
      expect(observer.snapshot()).toEqual({ phase: 'unknown', bodySentObserved: null, connectionBytesWritten: null, connectionBytesRead: null });
    } finally { observer.close(); observer.close(); }
    expect(source.hasSubscribers).toBe(hadSubscribers);
  });

  test('FBK-001：配置边界拒绝 JSON 转义和非 ASCII 凭据，不回显原值', async () => {
    const unsafe = ['pool-quote"back\\slash-canary', 'pool/escape/slash', 'pool\tcontrol', 'pool 中文', "pool'apostrophe"];
    for (const apiKey of unsafe) {
      const raw = JSON.stringify({ type: 'error', error: { message: apiKey } });
      expect(JSON.parse(raw).error.message).toBe(apiKey);
      try { validatePoolConfig({ ...config, apiKey }); throw new Error('非法凭据被放行'); }
      catch (error) { expect(error).toBeInstanceOf(Error); expect((error as Error).message).toContain('格式不受支持'); expect((error as Error).message).not.toContain(apiKey); }
    }
    const root = await mkdtemp(join(tmpdir(), 'ccrb-pool-invalid-key-'));
    try {
      const path = join(root, 'pool.env');
      await writeFile(path, 'CCRB_TEST_POOL_BASE_URL=https://pool.example/v1\nCCRB_TEST_POOL_API_KEY=' + unsafe[0] + '\n', { mode: 0o600 });
      await expect(loadPoolConfig(path)).rejects.toThrow('格式不受支持');
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  test('支持的 ASCII 凭据在 JSON/SSE 跨片段回显中被遮住，原始哈希保持', () => {
    const apiKey = 'sk-compatible._~-12345', redactor = new Redactor(); redactor.register({ api_key: apiKey });
    validatePoolConfig({ ...config, apiKey });
    const json = JSON.stringify({ type: 'error', error: { message: apiKey } });
    for (const raw of [json, 'event: error\ndata: ' + json + '\n\n']) {
      const capture = new BodyCapture(), at = raw.indexOf(apiKey) + 7;
      capture.push(Buffer.from(raw.slice(0, at))); capture.push(Buffer.from(raw.slice(at)));
      const result = safePoolSample(capture.finish(redactor), redactor);
      expect(result.text).not.toContain(apiKey); expect(result.text).toContain('[REDACTED]');
      expect(result.sha256).toBe(createHash('sha256').update(raw).digest('hex'));
    }
  });

  test('显式轮次使用独立账本，默认首轮名称不变且拒绝路径穿越', () => {
    expect(poolLedgerName()).toBe('pool-tls-forwarder-live-first-run.json');
    expect(poolLedgerName('repair-20261106')).toBe('pool-tls-forwarder-live-repair-20261106.json');
    expect(poolLedgerName('repair-20261106')).not.toBe(poolLedgerName());
    for (const id of ['', '../first-run', '/tmp/file', 'a/b', 'a.b', '含中文', '-leading', 'a'.repeat(65)]) expect(() => poolLedgerName(id)).toThrow('轮次');
  });

  test('代理只进入真实池 Node，离线不继承宿主，拒绝冲突及 URL 凭据', () => {
    const env = { HTTPS_PROXY: 'http://127.0.0.1:7890', https_proxy: 'http://127.0.0.1:7890', NO_PROXY: 'localhost,127.0.0.1', PRIVATE_KEY: secret };
    expect(poolProxyEnvironment(env, false)).toEqual({});
    expect(poolProxyEnvironment(env, true)).toEqual({ HTTPS_PROXY: env.HTTPS_PROXY, NO_PROXY: env.NO_PROXY });
    expect(() => poolProxyEnvironment({ ...env, https_proxy: 'http://127.0.0.1:7891' }, true)).toThrow('冲突');
    for (const proxy of ['http://user:pass@127.0.0.1:7890','socks5://127.0.0.1:7890','https://api.anthropic.com','http://127.0.0.1:7890/path','http://127.0.0.1:7890\r\nx-a:b']) expect(() => poolProxyEnvironment({ HTTPS_PROXY: proxy }, true)).toThrow();
  });

  test('只读受保护 env，忽略 Gemini 和 fallback，禁止执行 shell 内容', async () => {
    const root = await mkdtemp(join(tmpdir(), 'ccrb-pool-unit-'));
    try {
      const path = join(root, 'pool.env');
      await writeFile(path, 'PROJECT_REQUESTER_BASE_URL=https://pool.example/v1\nPROJECT_REQUESTER_API_KEY=' + secret + '\nPROJECT_REQUESTER_MODEL=gemini-3-flash-agent\nPROJECT_REQUESTER_FALLBACK_MODEL=other\nUNUSED=$(false)\n', { mode: 0o600 });
      expect(await loadPoolConfig(path)).toEqual({ baseUrl: 'https://pool.example/v1', apiKey: secret, live: true, maxRequests: 3, timeoutMs: 30000 });
      await chmod(path, 0o644); await expect(loadPoolConfig(path)).rejects.toThrow('仅所有者');
      await chmod(path, 0o600);
      await writeFile(path, 'CCRB_TEST_POOL_BASE_URL=https://one.example\nPROJECT_REQUESTER_BASE_URL=https://two.example\nCCRB_TEST_POOL_API_KEY=' + secret);
      await expect(loadPoolConfig(path)).rejects.toThrow('冲突');
      await writeFile(path, 'CCRB_TEST_POOL_API_KEY=a\nCCRB_TEST_POOL_API_KEY=b\n'); await expect(loadPoolConfig(path)).rejects.toThrow('重复');
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  test('真实目标、身份和次数预算在启动时拒绝非法值', () => {
    for (const baseUrl of ['https://api.anthropic.com','https://sub.anthropic.com','https://api.anthropic.com.','https://claude.ai','https://a:b@pool.example','https://pool.example?key=value','https://pool.example#x','ftp://pool.example','http://pool.example']) expect(() => validatePoolConfig({ ...config, live: true, baseUrl })).toThrow();
    expect(() => validatePoolConfig({ ...config, baseUrl: 'https://public.example' })).toThrow();
    for (const maxRequests of [0, 4, 1.5, NaN]) expect(() => validatePoolConfig({ ...config, baseUrl: 'https://pool.example', live: true, maxRequests })).toThrow();
    for (const apiKey of ['', 'abc', 'key\r\nvalue']) expect(() => validatePoolConfig({ ...config, apiKey })).toThrow();
    expect(() => validatePoolConfig({ ...config, live: undefined } as unknown as PoolConfig)).toThrow('类型');
  });

  test('Messages 路径只拼接一次，查询串保留，其他 API 拒绝', () => {
    for (const base of ['https://pool.example', 'https://pool.example/', 'https://pool.example/v1', 'https://pool.example/v1/']) expect(poolMessagesUrl(base, '/v1/messages?beta=true')).toBe('https://pool.example/v1/messages?beta=true');
    expect(poolMessagesUrl('https://pool.example/prefix/v1', '/v1/messages')).toBe('https://pool.example/prefix/v1/messages');
    for (const path of ['/v1/models','/v1/messages/','https://evil.example/v1/messages']) expect(() => poolMessagesUrl(config.baseUrl, path)).toThrow();
    expect(() => poolMessagesUrl('https://pool.example/v1/messages', '/v1/messages')).toThrow('服务前缀');
  });

  test('仅根 model 改写，工具、opaque signature、缓存、线程和扩展头保留', () => {
    const body = { model: 'claude-sonnet-4-6', max_tokens: 128, stream: true, metadata: { user_id: 'opaque' }, tools: [{ name: 'fixture', input_schema: { type: 'object', properties: { model: { const: 'nested-model' } } } }], system: [{ type: 'text', text: 'business', cache_control: { type: 'ephemeral' } }], messages: [{ role: 'assistant', content: [{ type: 'thinking', signature: 'opaque-signature', thinking: 'kept' }] }], thread: { previous_message_id: 'msg_old' }, future: { model: 'nested-model' } };
    const raw = JSON.stringify(body);
    const outgoing = preparePoolRequest(raw, [['Host','api.anthropic.com'],['Authorization','Bearer cc-secret'],['X-Api-Key','cc-key'],['Proxy-Authorization','proxy-secret'],['Connection','X-Hop, keep-alive'],['X-Hop','drop'],['X-Future','one'],['x-FUTURE','two'],['x-claude-code-agent-id','child'],['content-length','0']], '/v1/messages?beta=true', config);
    expect(JSON.parse(outgoing.body)).toEqual({ ...body, model: POOL_MODEL });
    expect(JSON.stringify(body)).toBe(raw);
    expect(outgoing.headers).toEqual([['X-Future','one'],['x-FUTURE','two'],['x-claude-code-agent-id','child'],['x-api-key',secret],['content-length', String(Buffer.byteLength(outgoing.body))]]);
    expect(outgoing.changes.some(x => x.name === 'X-Hop')).toBe(true);
    expect(outgoing.url.endsWith('?beta=true')).toBe(true);
    for (const max_tokens of [0, 129, 1.5, undefined]) expect(() => preparePoolRequest(JSON.stringify({ ...body, max_tokens }), [], '/v1/messages', { ...config, live: true })).toThrow('预算');
  });

  test('预览脱敏不改变原始哈希，跨片段和截断不留下部分 Key', () => {
    const raw = '前缀' + secret + '后缀', capture = new BodyCapture();
    capture.push(Buffer.from(raw.slice(0, 12))); capture.push(Buffer.from(raw.slice(12)));
    const result = capture.finish(redactor);
    expect(result.sha256).toBe(createHash('sha256').update(raw).digest('hex'));
    expect(result.bytes).toBe(Buffer.byteLength(raw)); expect(result.text).toContain('[REDACTED]'); expect(result.text).not.toContain(secret);
    const partial = new BodyCapture(32); partial.push(Buffer.from('x'.repeat(25) + secret));
    const truncated = partial.finish(redactor); expect(truncated.status).toBe('truncated'); expect(truncated.text).not.toContain('pool-');
    const large = new BodyCapture(); large.push(Buffer.alloc(CAPTURE_LIMIT + 1024, 120)); const largeResult = large.finish(redactor);
    expect(largeResult.bytes).toBe(CAPTURE_LIMIT + 1024); expect(largeResult.storedBytes).toBeLessThanOrEqual(CAPTURE_LIMIT); expect(largeResult.status).toBe('truncated');
  });

  test('不知道池 Key 的驱动回执在宿主重新脱敏，原始哈希保持', () => {
    const unknown = sample('pool echoed ' + secret, new Redactor()), safe = safePoolSample(unknown, redactor);
    expect(safe.sha256).toBe(unknown.sha256); expect(safe.bytes).toBe(unknown.bytes); expect(safe.text).not.toContain(secret);
    const incomplete = new BodyCapture(); incomplete.push(Buffer.from('prefix ' + secret.slice(0, 8)));
    expect(safePoolSample(incomplete.finish(new Redactor(), false), redactor).text).not.toContain('pool-');
  });

  test('没有真实最终 CCH 的正文明确失败，不补写值', () => {
    for (const raw of ['{}', '{"system":[]}', '{"system":[{"text":"x-anthropic-billing-header: cch=00000;"}]}', '{"system":[{"text":"x-anthropic-billing-header: cch=12345;"}]}']) expect(() => verifyCch(raw)).toThrow();
  });

  test('私有边界校验结构和归属，大正文不套用业务上限', () => {
    const finished = { type: 'finished' as const, id: 1, attempted: true, outcome: 'success', statusCode: 200, upstreamStatus: 200, headers: [], response: empty };
    expect(decodeForwarderFrame(JSON.stringify(finished))).toEqual(finished);
    for (const value of [{ ...finished, id: 0 }, { ...finished, headers: [['name', 2]] }, { ...finished, response: { ...empty, sha256: '' } }, { ...finished, response: { ...empty, storedBytes: 1 } }, { ...finished, prepared: { url: 'x', model: 'gemini', headers: [], body: empty, changes: [] } }]) expect(() => decodeForwarderFrame(JSON.stringify(value))).toThrow();
    expect(() => decodeForwarderFrame('{')).toThrow();
    const captured = { type: 'captured' as const, id: 1, method: 'POST', path: '/v1/messages', httpVersion: '1.1', headers: [], body: 'x'.repeat(9 * 1024 * 1024) };
    expect(decodeForwarderFrame(JSON.stringify(captured))).toEqual(captured);
    expect(() => decodeDriverFrame('{"type":"result","id":"x"}')).toThrow();
    expect(decodeDriverFrame('{"type":"driver_ready","namespace":"net:[1]","interfaces":["lo"],"envNames":["PATH"],"rejectedTargetProbe":true}').type).toBe('driver_ready');
  });

  test('真实场景只有三次小预算，无工具且保持原生正文', () => {
    const scenes = poolScenes(true); expect(scenes).toHaveLength(3);
    expect(scenes.map(x => [x.fixture, x.cancel])).toEqual([['json', false], ['sse', false], ['cancel', true]]);
    for (const scene of scenes) { const body = scene.input.body as Record<string, unknown>; expect(body.max_tokens).toBe(128); expect(body.model).toBe('claude-sonnet-4-6'); expect(body.tools).toBeUndefined(); expect(body.future_extension).toBeUndefined(); }
    expect(poolScenes(false).length).toBeGreaterThan(3);
  });
});

test('只读报告转义 HTML、限定文件路径，刷新不调用任何模型', async () => {
  const report: PoolReport = { schemaVersion: 1, createdAt: 'now', mode: 'offline', model: POOL_MODEL, baseUrl: 'http://127.0.0.1', binary: { path: '</pre><script>globalThis.poolXss=1</script>', distributionSha256: '', executionSha256: '', kind: 'fixture' }, environment: {}, calls: 0, budget: 3, stopped: null, cases: [] };
  const html = renderPoolReport(report);
  expect(html).not.toContain('<script>'); expect(html).toContain('&lt;script&gt;'); expect(html).toContain('生产最终采集能力仍为未实现');
  const root = await mkdtemp(join(tmpdir(), 'ccrb-pool-report-'));
  await writeFile(join(root, 'index.html'), html); await writeFile(join(root, 'report.json'), JSON.stringify(report)); await writeFile(join(root, 'secret.env'), secret);
  const server = await servePoolReport(root, 0), base = 'http://127.0.0.1:' + server.port;
  try {
    for (let i = 0; i < 3; i++) { const response = await fetch(base); expect(response.status).toBe(200); expect(await response.text()).toBe(html); }
    expect((await fetch(base + '/secret.env')).status).toBe(404); expect((await fetch(base, { method: 'POST' })).status).toBe(403);
    expect(await (await fetch(base + '/report.json')).json()).toEqual(report); expect(report.calls).toBe(0);
  } finally { await server.stop(true); await rm(root, { recursive: true, force: true }); }
});
