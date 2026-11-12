import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash, randomUUID } from 'node:crypto';
import { createServer } from 'node:http';
import { connect } from 'node:net';
import { readConfig, startServer, type RunningServer } from '../../src/control/server';
import type { CaptureRecord, RequestDetail } from '../../src/shared/contracts';
import { PrivateProcess } from '../../scripts/testing/pool-process';
import { verifyCch } from '../../scripts/testing/pool-common';
import { TlsVerifierEngine } from '../../src/control/tls-verifier';
import { parseInput } from '../../src/shared/input';
import { prepareInput } from '../../src/control/header-policy';

interface Endpoint { port: number; proxyPort: number; caFile: string }
interface Call { index: number; file: string; connection: number; rawBytes: number; rawSha256: string; bodyBytes: number; bodySha256: string; tls: string; alpn: string; resumed: boolean; responseBytes?: number; responseSha256?: string }
interface Report { calls: Call[]; hellos: { connection: number; fields: unknown }[]; targets: string[]; connectHeads: { target: string; headers: string[]; authorizationSha256: string | null }[] }
/** 私有夹具对已启动 TLS 上游响应模式的确认。 */
interface ResponseMode { type: 'response_mode'; port: number; mode: string }
type FixtureFrame = Endpoint | Report | ResponseMode;
const native = process.env.CCRB_NATIVE_ISOLATED === '1' && process.env.CCRB_TLS_VERIFIER_TEST === '1' ? describe : describe.skip;
const binary = process.env.CCRB_TEST_CLAUDE_BINARY ?? '/root/.nvm/versions/node/v22.23.4/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe';

native('可选最终 TLS 写出：实际原版与独立 OpenSSL 对照', () => {
  let root: string;
  let fixture: PrivateProcess<FixtureFrame>;
  let serial = 0;
  const apps: RunningServer[] = [];
  const targets = new Map<RunningServer, Endpoint>();
  const evidence: Record<string, unknown>[] = [];

  beforeAll(async () => {
    if (Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode !== 0) throw new Error('无法启用回环隔离');
    root = await mkdtemp(join(tmpdir(), 'ccrb-tls-test-'));
    fixture = new PrivateProcess(['python3', resolve('tests/fixtures/tls-upstream.py'), join(root, 'upstream')], { PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8', HOME: root }, line => JSON.parse(line) as FixtureFrame);
  });

  afterAll(async () => {
    for (const app of apps) await app.close();
    const report = await inspect();
    const output = process.env.CCRB_TLS_REPORT;
    if (output) { await mkdir(resolve(output, '..'), { recursive: true }); await writeFile(output, JSON.stringify({ realModelCalls: 0, conditions: '实际官方 293；仅回环网络；合成凭据；独立 OpenSSL 实收', cases: evidence, report }, null, 2)); }
    await fixture.close();
    await rm(root, { recursive: true, force: true });
  });

  async function endpoint(mode = 'tls13'): Promise<Endpoint> {
    await fixture.send({ type: 'start', mode });
    const value = await fixture.next();
    if (!('proxyPort' in value)) throw new Error('夹具端点帧错误');
    return value;
  }

  async function inspect(): Promise<Report> {
    await fixture.send({ type: 'report' });
    const value = await fixture.next();
    if (!('calls' in value)) throw new Error('夹具报告帧错误');
    return value;
  }

  async function close(running: RunningServer): Promise<void> {
    apps.splice(apps.indexOf(running), 1);
    targets.delete(running);
    await running.close();
  }

  async function responseMode(running: RunningServer, mode: string): Promise<void> {
    const target = targets.get(running);
    if (!target) throw new Error('响应模式缺少已绑定的上游');
    await fixture.send({ type: 'response_mode', port: target.port, mode });
    const value = await fixture.next();
    if (!('type' in value) || value.type !== 'response_mode' || value.port !== target.port || value.mode !== mode) throw new Error('夹具响应模式确认帧错误');
  }

  function nativeBody(): Record<string, unknown> {
    return { system: [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=12345;' }, { type: 'text', text: '业务 system 保留' }], metadata: { user_id: JSON.stringify({ device_id: 'a'.repeat(64), account_uuid: '', session_id: '11111111-1111-4111-8111-111111111111' }), extra: '保留' } };
  }

  async function app(target: Endpoint, verify = true, extra: Record<string, string> = {}): Promise<RunningServer> {
    const directory = join(root, 'instance-' + serial++);
    await mkdir(join(directory, 'home'), { recursive: true });
    await mkdir(join(directory, 'config'));
    await writeFile(join(directory, 'config/.claude.json'), JSON.stringify({ userID: 'b'.repeat(64) }));
    const config = readConfig({ CCRB_PORT: '0', CCRB_DATA_DIR: join(directory, 'data'), CCRB_CLAUDE_BINARY: binary, CCRB_CLAUDE_HOME: join(directory, 'home'), CCRB_CLAUDE_CONFIG_DIR: join(directory, 'config'), CCRB_WORKDIR: directory, CCRB_NATIVE_API_KEY: 'tls-synthetic-key-' + serial, CCRB_CA_FILE: target.caFile, CCRB_PROXY_URL: 'http://127.0.0.1:' + target.proxyPort, CCRB_TLS_CAPTURE: verify ? 'verify' : 'off', CCRB_TIMEOUT_MS: '0', ...extra });
    const running = await startServer(config);
    apps.push(running);
    targets.set(running, target);
    return running;
  }

  async function detail(running: RunningServer, id: string): Promise<RequestDetail> {
    for (let index = 0; index < 200; index++) {
      await running.store.flush();
      const value = await running.store.detail(id);
      if (value?.request.finishedAt) return value;
      await Bun.sleep(10);
    }
    throw new Error('测试日志未收口');
  }

  async function send(running: RunningServer, mode = 'json', body: Record<string, unknown> = {}, context: Record<string, unknown> = {}) {
    await responseMode(running, mode);
    const response = await fetch('http://127.0.0.1:' + running.server.port + '/api/requests', { method: 'POST', redirect: 'manual', body: JSON.stringify({ body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '真实原版离线 TLS 验证：中文😀、引号"与换行\n' }], max_tokens: 64, stream: false, ...body }, headers: [['x-fixture-mode', mode], ['accept-language', 'zh-CN'], ['accept-language', 'en-US;q=0.8']], context }), headers: { 'content-type': 'application/json' } });
    const raw = await response.text();
    const record = await detail(running, response.headers.get('x-ccrb-request-id')!);
    return { response, raw, record };
  }

  function assertFinal(record: RequestDetail, call: Call, status: CaptureRecord['status'] = 'complete'): void {
    const final = record.captures.find(value => value.stage === 'wire_final')!;
    expect(final.source).toBe('native_tls_verifier');
    expect(final.representation).toBe('http_entity_from_final_tls_write');
    expect(final.status).toBe(status);
    expect(final.observedBytes).toBe(call.bodyBytes);
    expect(final.sha256).toBe(call.bodySha256);
    expect(final.note).toContain('HTTP SHA256=' + call.rawSha256);
    expect(final.note).toContain('HTTP bytes=' + call.rawBytes);
    expect(final.note).toContain('刷出=true');
    expect(final.headers.find(([name]) => name.toLowerCase() === 'x-api-key')?.[1]).toBe('[REDACTED]');
    expect(final.headers.find(([name]) => name.toLowerCase() === 'accept-language')?.[1]).toBe('zh-CN, en-US;q=0.8');
    expect(final.headers.some(([name]) => name.toLowerCase() === 'x-fixture-mode')).toBe(false);
  }

  test('透明中继的单次发送与最后写出完整记录', async () => {
    const target = await endpoint();
    const running = await app(target);
    const count = (await inspect()).calls.length;
    const result = await send(running);
    expect({ status: result.response.status, error: result.response.status === 200 ? '' : result.raw }).toEqual({ status: 200, error: '' });
    expect(result.record.request.state).toBe('success');
    const report = await inspect();
    expect(report.calls.length).toBe(count + 1);
    assertFinal(result.record, report.calls.at(-1)!);
    evidence.push({ case: 'first-actual-relay', state: result.record.request.state, final: result.record.captures.find(value => value.stage === 'wire_final') });
  }, 30000);

  test.each([false, true])('合法媒体类型和 SSE 换行不改变原版响应终态：verify=%s', async verify => {
    const running = await app(await endpoint(), verify);
    try {
      for (const mode of ['json', 'mimecase', 'crline', 'json-mime-parameter']) {
        const before = (await inspect()).calls.length;
        const result = await send(running, mode, { model: 'deepseek-flash', thinking: { type: 'disabled' }, stream: mode !== 'json-mime-parameter' });
        const report = await inspect(), call = report.calls.at(-1)!;
        expect(report.calls.length).toBe(before + 1);
        expect(result.response.status).toBe(200);
        expect(result.record.request.state).toBe('success');
        expect(result.record.request.firstOutputMs).not.toBeNull();
        expect(result.record.request.captureError).toBeNull();
        const sha256 = createHash('sha256').update(result.raw).digest('hex');
        expect(call.responseSha256).toBe(sha256);
        expect(call.responseBytes).toBe(Buffer.byteLength(result.raw));
        expect(result.record.captures.find(value => value.stage === 'upstream_response')?.sha256).toBe(sha256);
        if (verify) assertFinal(result.record, call);
        else expect(result.record.captures.find(value => value.stage === 'wire_final')?.status).toBe('unavailable');
        evidence.push({ case: 'response-format', mode, verify, state: result.record.request.state, responseSha256: sha256, responseBytes: call.responseBytes });
      }
    } finally { await close(running); }
  }, 30000);

  test.each([false, true])('工具续轮六类 Prompt ID 与独立 TLS 实收一致：verify=%s', async verify => {
    const running = await app(await endpoint(), verify);
    const tool = { name: 'lookup_status', input_schema: { type: 'object', properties: {} } };
    const messages = [{ role: 'user', content: '查询工具状态' }, { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_prompt', name: tool.name, input: {} }] }, { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_prompt', content: 'ready' }] }];
    try {
      for (const requestClass of ['main', 'subagent', 'workflow', 'compaction', 'auxiliary', 'side_reply']) {
        const promptId = randomUUID(), sessionId = randomUUID();
        const child = requestClass === 'subagent' || requestClass === 'workflow';
        const context = { requestClass, promptId, sessionId, ...(child ? { agentId: 'tls-child', parentAgentId: 'tls-parent', agentType: 'Explore' } : {}), ...(requestClass === 'workflow' ? { workflowRunId: 'tls-workflow' } : {}) };
        const before = (await inspect()).calls.length;
        const result = await send(running, 'json', { model: 'claude-sonnet-5-5', messages, tools: [tool] }, context);
        expect({ status: result.response.status, error: result.response.status === 200 ? '' : result.raw }).toEqual({ status: 200, error: '' });
        const report = await inspect(), call = report.calls.at(-1)!;
        expect(report.calls.length).toBe(before + 1);
        const received = JSON.parse(await readFile(call.file, 'utf8'));
        expect(new Headers(received.headers).get('x-claude-code-prompt-id')).toBe(promptId);
        expect(result.record.context?.promptId).toBe(promptId);
        expect(result.record.request.captureError).toBeNull();
        verifyCch(received.body);
        if (verify) assertFinal(result.record, call);
        else expect(result.record.captures.find(capture => capture.stage === 'wire_final')?.status).toBe('unavailable');
        evidence.push({ case: 'tool-prompt-' + requestClass, verify, promptId, finalSha256: call.bodySha256, httpSha256: call.rawSha256 });
      }
    } finally { await close(running); }
  }, 30000);

  test.each([[false, false], [true, false], [false, true], [true, true]])('显式 disabled 保留到独立 TLS 实收：verify=%s customBase=%s', async (verify, customBase) => {
    const running = await app(await endpoint(), verify, customBase ? { CCRB_NATIVE_BASE_URL: 'https://fixture.local' } : {});
    const tool = { name: 'lookup_status', input_schema: { type: 'object', properties: {} } };
    const history = [{ role: 'user', content: '查询工具状态' }, { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_disabled', name: tool.name, input: {} }] }, { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_disabled', content: 'ready' }] }];
    try {
      for (const shape of [{ stream: false }, { stream: true }, { stream: false, messages: history, tools: [tool] }]) {
        const body = { model: 'deepseek-flash', thinking: { type: 'disabled' }, ...shape };
        const original = JSON.stringify(body), before = (await inspect()).calls.length;
        const result = await send(running, 'json', body);
        expect({ status: result.response.status, error: result.response.status === 200 ? '' : result.raw }).toEqual({ status: 200, error: '' });
        expect(result.record.request.state).toBe('success');
        expect(result.record.request.captureError).toBeNull();
        expect(result.response.headers.get('content-type')).toContain(shape.stream ? 'text/event-stream' : 'application/json');
        const report = await inspect(), call = report.calls.at(-1)!;
        expect(report.calls.length).toBe(before + 1);
        const received = JSON.parse(await readFile(call.file, 'utf8'));
        expect(JSON.parse(received.body).thinking).toEqual({ type: 'disabled' });
        const prepared = result.record.captures.find(capture => capture.stage === 'cc_prepared')!;
        expect(prepared.sha256).toBe(createHash('sha256').update(prepared.text!).digest('hex'));
        const cch = customBase ? null : verifyCch(received.body);
        expect(cch ? prepared.text!.replace('cch=00000', 'cch=' + cch.actual) : prepared.text).toBe(received.body);
        if (verify) assertFinal(result.record, call);
        else expect(result.record.captures.find(capture => capture.stage === 'wire_final')?.status).toBe('unavailable');
        expect(JSON.stringify(body)).toBe(original);
        evidence.push({ case: 'disabled-' + (shape.messages ? 'tool-history' : shape.stream ? 'sse' : 'json'), verify, customBase, bodySha256: call.bodySha256, httpSha256: call.rawSha256 });
      }
      for (const body of [{ model: 'deepseek-flash' }, { model: 'deepseek-flash', ...nativeBody() }, { model: 'deepseek-flash', ...nativeBody(), thinking: { type: 'disabled', future: '保留原生扩展' } }]) {
        const before = (await inspect()).calls.length;
        const result = await send(running, 'json', body);
        expect(result.response.status).toBe(200);
        const report = await inspect(), call = report.calls.at(-1)!;
        expect(report.calls.length).toBe(before + 1);
        const received = JSON.parse(await readFile(call.file, 'utf8'));
        const thinking = JSON.parse(received.body).thinking;
        if ('thinking' in body) expect(thinking).toEqual(body.thinking);
        else if ('system' in body) expect(thinking).toBeUndefined();
        else expect(thinking).toEqual({ type: 'adaptive', display: 'updates' });
        expect(result.record.context?.inputFormat).toBe('system' in body ? 'claude_code' : 'api');
        if (!customBase) verifyCch(received.body);
        if (verify) assertFinal(result.record, call);
      }
    } finally { await close(running); }
  }, 30000);

  test.each([false, true])('普通 API 不可保留的 thinking 明确拒绝且零发送：verify=%s', async verify => {
    const running = await app(await endpoint(), verify);
    try {
      for (const body of [{ model: 'deepseek-flash', thinking: { type: 'disabled', future: '不能丢弃' } }, { model: 'deepseek-flash', thinking: { type: 'unknown' } }, { model: 'claude-sonnet-4-6', thinking: { type: 'enabled', budget_tokens: 2048 } }]) {
        const before = (await inspect()).calls.length;
        const result = await send(running, 'json', body);
        expect(result.response.status).toBe(422);
        expect(result.raw).toContain('unsupported_parameter');
        expect(result.raw).toContain('thinking');
        expect((await inspect()).calls.length).toBe(before);
      }
    } finally { await close(running); }
  }, 30000);

  test.each(['literal', 'trailing_space', 'leading_space', 'cch_first', 'cch_last', 'escaped_prefix', 'literal_no_cch'])('CHK-001/CHK-002 实际原版回环：%s', async scene => {
    const target = await endpoint();
    const before = (await inspect()).calls.length;
    const literal = '正文包含 __ccrb_cch_observation_slot__ 和 cch=00000;，保持业务原文😀';
    const body: Record<string, unknown> = { messages: [{ role: 'user', content: literal }] };
    if (!scene.startsWith('literal')) {
      Object.assign(body, nativeBody());
      const system = body.system as { type: string; text: string }[];
      const billing = system[0]!.text;
      system[0]!.text = scene === 'trailing_space' ? billing.replace('cch=12345;', 'cch=12345 \t;')
        : scene === 'leading_space' ? ' \t' + billing
        : scene === 'cch_first' ? 'x-anthropic-billing-header: cch=12345 \t; cc_version=2.1.293.abc; cc_entrypoint=cli;'
        : scene === 'cch_last' ? billing.replace('cch=12345;', 'cch=12345 \t')
        : billing.replace('cc_version=', 'future=中文😀"\\; cc_version=').replace('cch=12345;', 'cch=12345 \t;');
    }
    for (const verify of [false, true]) {
      const running = await app(target, verify, scene === 'literal_no_cch' ? { CCRB_NATIVE_BASE_URL: 'https://fixture.local' } : {});
      const original = JSON.stringify(body);
      const result = await send(running, 'json', body);
      expect({ status: result.response.status, error: result.response.status === 200 ? '' : result.raw }).toEqual({ status: 200, error: '' });
      expect(result.record.request.state).toBe('success');
      expect(result.record.request.captureError).toBeNull();
      const call = (await inspect()).calls.at(-1)!;
      const received = JSON.parse(await readFile(call.file, 'utf8'));
      expect(received.body).toContain('__ccrb_cch_observation_slot__');
      if (verify) assertFinal(result.record, call);
      else expect(result.record.captures.find(value => value.stage === 'wire_final')?.status).toBe('unavailable');
      expect(JSON.stringify(body)).toBe(original);
      evidence.push({ case: 'repair-' + scene, verify, requestState: result.record.request.state, captureError: result.record.request.captureError, capture: result.record.captures.find(value => value.stage === 'wire_final')?.status, rawSha256: call.rawSha256, bodySha256: call.bodySha256 });
      await close(running);
    }
    expect((await inspect()).calls.length).toBe(before + 2);
  }, 30000);

  test.each(['tls13', 'tls12', 'hrr'])('完整公开握手、有序头与连接复用对齐：%s', async mode => {
    const target = await endpoint(mode);
    const direct = await app(target, false);
    const verified = await app(target);
    const count = (await inspect()).calls.length;
    const connects = (await inspect()).connectHeads.length;
    for (const running of [direct, verified]) {
      for (let index = 0; index < 3; index++) {
        const result = await send(running);
        expect(result.response.status).toBe(200);
        const call = (await inspect()).calls.at(-1)!;
        if (running === verified) assertFinal(result.record, call);
        else expect(result.record.captures.find(value => value.stage === 'wire_final')?.status).toBe('unavailable');
      }
    }
    const report = await inspect();
    const calls = report.calls.slice(count);
    const proxyHeads = report.connectHeads.slice(connects);
    evidence.push({ case: mode + '-proxy-connect', heads: proxyHeads });
    expect(proxyHeads).toHaveLength(2);
    expect(proxyHeads[0]).toEqual(proxyHeads[1]);
    expect(calls.length).toBe(6);
    expect(new Set(calls.slice(0, 3).map(value => value.connection)).size).toBe(1);
    expect(new Set(calls.slice(3).map(value => value.connection)).size).toBe(1);
    expect(calls[0]!.connection).not.toBe(calls[3]!.connection);
    const hellos = (connection: number) => report.hellos.filter(value => value.connection === connection).map(value => value.fields);
    expect(hellos(calls[0]!.connection).length).toBe(mode === 'hrr' ? 2 : 1);
    expect(hellos(calls[0]!.connection)).toEqual(hellos(calls[3]!.connection));
    const first = JSON.parse(await readFile(calls[0]!.file, 'utf8'));
    const last = JSON.parse(await readFile(calls[3]!.file, 'utf8'));
    // 合成 Key 和每次 prompt 不同，只对照头部名称与顺序；各自全部原字节哈希已独立核对。
    expect(first.headers.map((value: string[]) => value[0])).toEqual(last.headers.map((value: string[]) => value[0]));
    evidence.push({ case: mode, passed: true, calls, hellos: hellos(calls[3]!.connection) });
    await close(direct); await close(verified);
  }, 30000);

  test.each(['tls13', 'tls12'])('关闭后重连与会话恢复策略和原版一致：%s', async mode => {
    const target = await endpoint(mode);
    const first = await app(target, false);
    const last = await app(target);
    const before = (await inspect()).calls.length;
    for (const running of [first, last]) for (const chosen of ['close', 'close', 'json']) {
      const result = await send(running, chosen);
      expect(result.response.status).toBe(200);
      if (running === last) assertFinal(result.record, (await inspect()).calls.at(-1)!);
    }
    const report = await inspect();
    const calls = report.calls.slice(before);
    expect(calls.length).toBe(6);
    expect(new Set(calls.map(value => value.connection)).size).toBe(6);
    expect(calls.map(value => value.resumed)).toEqual([false, false, false, false, false, false]);
    const fields = calls.map(call => report.hellos.find(value => value.connection === call.connection)!.fields);
    expect(fields.slice(0, 3)).toEqual(fields.slice(3));
    evidence.push({ case: mode + '-reconnect', passed: true, calls, fields });
    await close(first); await close(last);
  }, 30000);

  test.each([2, 8])('大正文 %s MiB 完整发送，预览截断与整体哈希独立', async size => {
    const target = await endpoint();
    const running = await app(target, true, { CCRB_CAPTURE_BYTES: '16384' });
    const before = (await inspect()).calls.length;
    const result = await send(running, 'json', { ...nativeBody(), messages: [{ role: 'user', content: '中文😀' + 'x'.repeat(size * 1024 * 1024) }] });
    evidence.push({ case: size + 'MiB-attempt', status: result.response.status, error: result.record.request.error, captures: result.record.captures.map(value => ({ stage: value.stage, status: value.status, observedBytes: value.observedBytes, note: value.note })) });
    expect({ status: result.response.status, error: result.response.status === 200 ? '' : result.raw }).toEqual({ status: 200, error: '' });
    const report = await inspect();
    expect(report.calls.length).toBe(before + 1);
    assertFinal(result.record, report.calls.at(-1)!, 'truncated');
    const final = result.record.captures.find(value => value.stage === 'wire_final')!;
    expect(final.storedBytes).toBeLessThanOrEqual(16384);
    expect(final.observedBytes).toBeGreaterThan(size * 1024 * 1024);
    expect(final.text).not.toContain('�');
    evidence.push({ case: size + 'MiB', state: result.record.request.state, final: { status: final.status, observedBytes: final.observedBytes, storedBytes: final.storedBytes, sha256: final.sha256 } });
    await close(running);
  }, 30000);

  test.each(['401', '429', '500', 'redirect', 'sse-error', 'incomplete'])('HTTP/SSE 错误保持原状态且无重试：%s', async chosen => {
    const target = await endpoint();
    const running = await app(target);
    const before = (await inspect()).calls.length;
    const result = await send(running, chosen, { stream: chosen === 'sse-error' || chosen === 'incomplete' });
    const report = await inspect();
    expect(report.calls.length).toBe(before + 1);
    expect(result.response.status).toBe(chosen === 'redirect' ? 302 : /^\d+$/.test(chosen) ? Number(chosen) : 200);
    expect(result.record.request.state).toBe(chosen === 'sse-error' ? 'stream_error' : chosen === 'incomplete' ? 'incomplete' : 'http_error');
    assertFinal(result.record, report.calls.at(-1)!);
    evidence.push({ case: chosen, state: result.record.request.state, calls: 1 });
    await close(running);
  }, 30000);

  test('健康流超过 30 秒且缓慢消费，最终写出在流结束前可见', async () => {
    const target = await endpoint();
    const running = await app(target);
    const before = (await inspect()).calls.length;
    await responseMode(running, 'long');
    const start = performance.now();
    const response = await fetch('http://127.0.0.1:' + running.server.port + '/api/requests', { method: 'POST', body: JSON.stringify({ body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '长流验证' }], stream: true }, headers: [['x-fixture-mode', 'long']] }) });
    expect(response.status).toBe(200);
    const id = response.headers.get('x-ccrb-request-id')!;
    await running.store.flush();
    const live = await running.store.detail(id);
    expect(live?.request.finishedAt).toBeNull();
    expect(live?.captures.find(value => value.stage === 'wire_final')?.status).toBe('complete');
    const reader = response.body!.getReader();
    let raw = '';
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      raw += new TextDecoder().decode(chunk.value);
      await Bun.sleep(50);
    }
    expect(raw).toContain('message_stop');
    expect(performance.now() - start).toBeGreaterThan(35000);
    const record = await detail(running, id);
    expect(record.request.state).toBe('success');
    const report = await inspect();
    expect(report.calls.length).toBe(before + 1);
    // 此请求未带合并头，只核对相同的最后写出核心证据。
    const final = record.captures.find(value => value.stage === 'wire_final')!;
    expect(final.sha256).toBe(report.calls.at(-1)!.bodySha256);
    expect(final.note).toContain(report.calls.at(-1)!.rawSha256);
    evidence.push({ case: 'long-slow-consumer', elapsedMs: performance.now() - start, liveFinalVisible: true, state: record.request.state });
    await close(running);
  }, 45000);

  test('取消关闭本代连接，后续请求重新建立且不串采集', async () => {
    const target = await endpoint();
    const running = await app(target);
    const before = (await inspect()).calls.length;
    await responseMode(running, 'cancel');
    const cancel = new AbortController();
    const response = await fetch('http://127.0.0.1:' + running.server.port + '/api/requests', { method: 'POST', signal: cancel.signal, body: JSON.stringify({ body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '取消验证' }], stream: true }, headers: [['x-fixture-mode', 'cancel']] }) });
    const reader = response.body!.getReader();
    await reader.read(); cancel.abort(); await reader.cancel().catch(() => {});
    const canceled = await detail(running, response.headers.get('x-ccrb-request-id')!);
    expect(canceled.request.state).toBe('canceled');
    expect(canceled.captures.find(value => value.stage === 'wire_final')?.status).toBe('complete');
    const next = await send(running);
    expect(next.response.status).toBe(200);
    const report = await inspect();
    expect(report.calls.length).toBe(before + 2);
    expect(report.calls.at(-2)!.connection).not.toBe(report.calls.at(-1)!.connection);
    assertFinal(next.record, report.calls.at(-1)!);
    evidence.push({ case: 'cancel-rebuild', canceled: canceled.request.state, next: next.record.request.state, connections: report.calls.slice(before).map(value => value.connection) });
    await close(running);
  }, 30000);

  test.each(['api', 'claude_code'])('端点和根模型四种覆盖组合，原始模型及原生 CCH 分支可核对：%s', async format => {
    const target = await endpoint();
    const before = (await inspect()).calls.length;
    for (const verify of [false, true]) for (const baseUrl of [false, true]) for (const model of [false, true]) {
      const running = await app(target, verify, { ...(baseUrl ? { CCRB_NATIVE_BASE_URL: 'https://fixture.local/prefix' } : {}), ...(model ? { CCRB_MODEL_OVERRIDE: 'fixture-selected-model' } : {}) });
      const body = format === 'api' ? {} : nativeBody();
      const result = await send(running, 'json', body);
      expect({ status: result.response.status, error: result.response.status === 200 ? '' : result.raw }).toEqual({ status: 200, error: '' });
      const report = await inspect();
      const call = report.calls.at(-1)!;
      const received = JSON.parse(await readFile(call.file, 'utf8'));
      const sent = JSON.parse(received.body);
      expect(sent.model).toBe(model ? 'fixture-selected-model' : 'claude-sonnet-4-6');
      expect(result.record.context?.modelSelection).toEqual({ requested: 'claude-sonnet-4-6', effective: sent.model, source: model ? 'startup_override' : 'request' });
      const billing = sent.system.find((block: { text?: string }) => block.text?.startsWith('x-anthropic-billing-header:')).text as string;
      expect(billing.includes('cch=')).toBe(!baseUrl);
      if (!baseUrl) verifyCch(received.body);
      if (verify) assertFinal(result.record, call);
      else expect(result.record.captures.find(value => value.stage === 'wire_final')?.status).toBe('unavailable');
      if (format === 'claude_code') {
        expect(sent.metadata.extra).toBe('保留');
        expect(JSON.parse(sent.metadata.user_id).device_id).toBe('b'.repeat(64));
        expect(JSON.parse(sent.metadata.user_id).session_id).toBe('11111111-1111-4111-8111-111111111111');
      }
      evidence.push({ case: 'configuration', format, verify, baseUrl, model, finalModel: sent.model, nativeCchPresent: !baseUrl });
      await close(running);
    }
    expect((await inspect()).calls.length).toBe(before + 8);
  }, 45000);

  test('两个实际 CLI 并发，每个启动三个真实子代理，实例、账号和会话隔离', async () => {
    const targets = [await endpoint(), await endpoint()];
    const running = await Promise.all(targets.map((target, index) => app(target, true, { CCRB_NATIVE_BASE_URL: index ? 'https://fixture.local/client-b' : 'https://api.anthropic.com/client-a', CCRB_MODEL_OVERRIDE: 'fixture-client-' + index, CCRB_NATIVE_INGRESS_POLICY: 'local_base_url' })));
    const sessions = [randomUUID(), randomUUID()];
    const before = (await inspect()).calls.length;
    const execute = async (index: number): Promise<string> => {
      const directory = join(root, 'actual-client-' + index);
      await mkdir(join(directory, 'config'), { recursive: true });
      await writeFile(join(directory, 'config/.claude.json'), JSON.stringify({ userID: String(index + 1).repeat(64), hasCompletedOnboarding: true, projects: { [directory]: { hasTrustDialogAccepted: true } } }));
      const cli = Bun.spawn([binary, '--print', '--session-id', sessions[index]!, '--model', 'claude-sonnet-4-6', '--max-turns', '5', '--tools', 'Agent', '--allowedTools', 'Agent', '--output-format', 'json', '--', '启动三个 Explore 子代理分别处理本地离线验证，然后汇总。'], { cwd: directory, env: { PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8', HOME: directory, CLAUDE_CONFIG_DIR: join(directory, 'config'), ANTHROPIC_BASE_URL: 'http://127.0.0.1:' + running[index]!.server.port, ANTHROPIC_AUTH_TOKEN: 'client-synthetic-' + index, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', DISABLE_AUTOUPDATER: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1', DISABLE_AUTO_COMPACT: '1', CLAUDE_CODE_MAX_OUTPUT_TOKENS: '128', MAX_THINKING_TOKENS: '0' }, stdin: 'ignore', stdout: 'pipe', stderr: 'pipe' });
      const output = new Response(cli.stdout).text();
      const diagnostic = new Response(cli.stderr).text();
      const timer = setTimeout(() => cli.kill('SIGKILL'), 40000);
      try {
        const [code, text, errors] = await Promise.all([cli.exited, output, diagnostic]);
        if (code !== 0) throw new Error('实际 CLI 未通过：' + text.slice(0, 1200) + errors.slice(0, 200));
        return text;
      } finally { clearTimeout(timer); }
    };
    const outputs = await Promise.all([execute(0), execute(1)]);
    for (const output of outputs) expect(output).toContain('离线');
    const report = await inspect();
    const actualCalls = report.calls.slice(before);
    evidence.push({ case: 'dual-cli-attempt', outputs: outputs.map(value => { const parsed = JSON.parse(value); return { subagent_stats: parsed.subagent_stats, permissionDenials: parsed.permission_denials?.length, result: parsed.result }; }), rows: running.map(instance => instance.store.list({ limit: 100 }).rows) });
    const ownership: Record<string, unknown>[] = [];
    for (let index = 0; index < 2; index++) {
      const instance = running[index]!;
      await instance.store.flush();
      const rows = instance.store.list({ limit: 100 }).rows;
      expect(rows.length).toBeGreaterThanOrEqual(5);
      expect(rows.every(row => row.sessionId === sessions[index] && row.model === 'fixture-client-' + index)).toBe(true);
      const children = rows.filter(row => row.requestClass === 'subagent');
      expect(new Set(children.map(row => row.agentId)).size).toBeGreaterThanOrEqual(3);
      const details = await Promise.all(rows.map(row => detail(instance, row.id)));
      const localCalls: Call[] = [];
      for (const record of details) {
        const final = record.captures.find(value => value.stage === 'wire_final')!;
        expect(final.status).toBe('complete');
        const call = actualCalls.find(value => value.bodySha256 === final.sha256)!;
        expect(call).toBeDefined(); localCalls.push(call);
        const observed = JSON.parse(await readFile(call.file, 'utf8'));
        const sent = JSON.parse(observed.body);
        expect(sent.model).toBe('fixture-client-' + index);
        expect(JSON.parse(sent.metadata.user_id).session_id).toBe(sessions[index]);
        expect(JSON.parse(sent.metadata.user_id).device_id).toBe('b'.repeat(64));
        const key = observed.headers.find(([name]: [string, string]) => name.toLowerCase() === 'x-api-key')[1];
        expect(key).not.toBe('client-synthetic-' + index);
        expect(record.agentAssociation?.state).not.toBe('conflict');
        if (record.agentAssociation?.parentAgentId) expect(rows.some(row => row.agentId === record.agentAssociation!.parentAgentId)).toBe(true);
        if (record.agentAssociation) for (const source of record.agentAssociation.evidence) expect(rows.some(row => row.id === source.requestId)).toBe(true);
        ownership.push({ instance: index, request: record.request.id, session: record.request.sessionId, agent: record.request.agentId, class: record.request.requestClass, connection: call.connection, model: sent.model });
      }
      expect(new Set(localCalls.map(value => value.connection)).size).toBe(1);
    }
    expect(ownership.length).toBe(actualCalls.length);
    evidence.push({ case: 'actual-dual-cli-three-subagents-each', passed: true, sessions, ownership });
    for (const instance of running) await close(instance);
  }, 60000);

  test('关闭验证只保留原生路径，启动和健康读取不创建辅助进程或发请求', async () => {
    const target = await endpoint();
    const childrenFile = '/proc/self/task/' + process.pid + '/children';
    const before = await readFile(childrenFile, 'utf8');
    const count = (await inspect()).calls.length;
    const running = await app(target, false);
    for (let index = 0; index < 3; index++) {
      const health = await (await fetch('http://127.0.0.1:' + running.server.port + '/api/health')).json();
      expect(health.tlsCapture).toBe('off'); expect(health.tlsVerifier).toBeNull(); expect(health.nativeFinalCapture).toBe(false);
    }
    expect(await readFile(childrenFile, 'utf8')).toBe(before);
    expect((await inspect()).calls.length).toBe(count);
    await close(running);
  }, 15000);

  test('不受信证书严格拒绝，没有 HTTP 业务写出，也不回退发送器', async () => {
    const target = await endpoint();
    const wrong = join(root, 'wrong-ca.pem');
    expect(Bun.spawnSync(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes', '-keyout', join(root, 'wrong-ca.key'), '-out', wrong, '-days', '1', '-subj', '/CN=Wrong synthetic CA', '-addext', 'basicConstraints=critical,CA:TRUE'], { stdout: 'ignore', stderr: 'ignore' }).exitCode).toBe(0);
    const running = await app(target, true, { CCRB_CA_FILE: wrong });
    const before = (await inspect()).calls.length;
    const result = await send(running);
    expect(result.response.status).toBe(502);
    expect((await inspect()).calls.length).toBe(before);
    const final = result.record.captures.find(value => value.stage === 'wire_final')!;
    expect(final.source).toBe('native_tls_verifier'); expect(final.status).toBe('incomplete'); expect(final.observedBytes).toBe(0); expect(final.headers).toEqual([]);
    expect(final.note).toContain('upstream_tls_failed');
    evidence.push({ case: 'certificate-rejected', state: result.record.request.state, finalStatus: final.status, bytes: final.observedBytes });
    await close(running);
  }, 30000);

  test('上游在正文中途断开，只记录实际接受的前缀，不重试业务', async () => {
    const target = await endpoint();
    const running = await app(target);
    const before = (await inspect()).calls.length;
    const result = await send(running, 'partial', { ...nativeBody(), messages: [{ role: 'user', content: 'x'.repeat(8 * 1024 * 1024) }] });
    expect(result.response.status).toBe(502);
    const report = await inspect();
    expect(report.calls.length).toBe(before + 1);
    const final = result.record.captures.find(value => value.stage === 'wire_final')!;
    expect(final.status).toBe('incomplete');
    expect(final.observedBytes).toBeGreaterThanOrEqual(65536);
    expect(final.observedBytes).toBeLessThan(8 * 1024 * 1024);
    expect(final.note).toContain('刷出=false');
    expect(final.source).toBe('native_tls_verifier');
    const next = await send(running);
    expect(next.response.status).toBe(200);
    assertFinal(next.record, (await inspect()).calls.at(-1)!);
    evidence.push({ case: 'partial-write-disconnect', acceptedBytes: final.observedBytes, upstreamReadBytes: report.calls.at(-1)!.bodyBytes, finalStatus: final.status, next: next.record.request.state });
    await close(running);
  }, 30000);

  test('辅助进程退出可见，后续请求失败且没有直连兜底', async () => {
    const target = await endpoint();
    const childrenFile = '/proc/self/task/' + process.pid + '/children';
    const before = new Set((await readFile(childrenFile, 'utf8')).trim().split(/\s+/));
    const running = await app(target);
    const child = (await readFile(childrenFile, 'utf8')).trim().split(/\s+/).filter(value => !before.has(value));
    expect(child.length).toBe(1);
    process.kill(Number(child[0]), 'SIGKILL');
    let health;
    for (let index = 0; index < 100; index++) {
      health = await (await fetch('http://127.0.0.1:' + running.server.port + '/api/health')).json();
      if (health.tlsVerifier.state === 'failed') break;
      await Bun.sleep(10);
    }
    expect(health.tlsVerifier.state).toBe('failed');
    const count = (await inspect()).calls.length;
    const result = await send(running);
    expect(result.response.status).toBe(503);
    expect((await inspect()).calls.length).toBe(count);
    expect(result.record.captures.find(value => value.stage === 'wire_final')?.status).toBe('failed');
    evidence.push({ case: 'helper-exit-no-fallback', state: health.tlsVerifier.state, requestStatus: result.response.status });
    await close(running);
  }, 30000);

  test('未支持的验证组合在启动时拒绝，不调用模型', async () => {
    const target = await endpoint();
    const count = (await inspect()).calls.length;
    const unsupported: Record<string, string>[] = [{ CCRB_MODE: 'demo' }, { CCRB_NATIVE_BASE_URL: 'http://fixture.local' }, { CCRB_TELEMETRY: 'on' }, { CCRB_PROXY_URL: 'socks5://127.0.0.1:9' }];
    for (const extra of unsupported) await expect(app(target, true, extra)).rejects.toThrow('TLS verify');
    expect((await inspect()).calls.length).toBe(count);
  }, 15000);

  test('HTTP 自定义端点直连及显式代理都由原版发送，默认没有 TLS 验证', async () => {
    const target = await endpoint();
    const direct: { path: string; model: string; billing: string }[] = [];
    const proxied: { path: string; model: string; billing: string }[] = [];
    const reply = (body: { model: string; system: { text: string }[] }, path: string, output: typeof direct): string => {
      output.push({ path, model: body.model, billing: body.system[0]!.text });
      return JSON.stringify({ id: 'msg_http_fixture', type: 'message', role: 'assistant', model: body.model, content: [{ type: 'text', text: 'HTTP 离线完成' }], stop_reason: 'end_turn', usage: { input_tokens: 1, output_tokens: 1 } });
    };
    const upstream = Bun.serve({ hostname: '127.0.0.1', port: 0, async fetch(request) { return new Response(reply(await request.json(), new URL(request.url).pathname, direct), { headers: { 'content-type': 'application/json' } }); } });
    const proxy = createServer(async (request, response) => {
      const parts = []; for await (const part of request) parts.push(part);
      const value = reply(JSON.parse(Buffer.concat(parts).toString()), request.url!, proxied);
      response.writeHead(200, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(value) }); response.end(value);
    });
    await new Promise<void>(resolve => proxy.listen(0, '127.0.0.1', resolve));
    const address = proxy.address(); if (!address || typeof address === 'string') throw new Error('代理端口无效');
    try {
      for (const useProxy of [false, true]) for (const format of ['api', 'claude_code']) {
        const running = await app(target, false, { CCRB_NATIVE_BASE_URL: useProxy ? 'http://fixture.local/prefix' : 'http://127.0.0.1:' + upstream.port + '/prefix', CCRB_PROXY_URL: useProxy ? 'http://127.0.0.1:' + address.port : '', CCRB_MODEL_OVERRIDE: 'http-selected-model' });
        const result = await send(running, 'json', format === 'api' ? {} : nativeBody());
        expect({ status: result.response.status, error: result.response.status === 200 ? '' : result.raw }).toEqual({ status: 200, error: '' });
        expect(result.record.captures.find(value => value.stage === 'wire_final')?.status).toBe('unavailable');
        await close(running);
      }
      expect(direct.length).toBe(2); expect(proxied.length).toBe(2);
      for (const call of [...direct, ...proxied]) { expect(call.model).toBe('http-selected-model'); expect(call.billing).not.toContain('cch='); expect(call.path).toContain('/prefix/v1/messages'); }
      evidence.push({ case: 'http-direct-and-explicit-proxy', direct, proxied });
    } finally { proxy.closeAllConnections(); await new Promise<void>(resolve => proxy.close(() => resolve())); await upstream.stop(true); }
  }, 30000);

  test('即使持有实例代理凭据，错误 PID 也不能接入或污染真实作业', async () => {
    const target = await endpoint();
    const directory = join(root, 'peer-proof');
    await mkdir(join(directory, 'home'), { recursive: true }); await mkdir(join(directory, 'config'));
    await writeFile(join(directory, 'config/.claude.json'), JSON.stringify({ userID: 'b'.repeat(64) }));
    const configuration = readConfig({ CCRB_CLAUDE_BINARY: binary, CCRB_CLAUDE_HOME: join(directory, 'home'), CCRB_CLAUDE_CONFIG_DIR: join(directory, 'config'), CCRB_NATIVE_API_KEY: 'peer-proof-synthetic', CCRB_CA_FILE: target.caFile, CCRB_PROXY_URL: 'http://127.0.0.1:' + target.proxyPort });
    const engine = await TlsVerifierEngine.create(configuration.engine, 1024 * 1024);
    const before = (await inspect()).calls.length;
    let captures = 0;
    const request = prepareInput(parseInput({ request_id: 'peer-proof', body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '实际 PID 绑定验证' }], stream: false } }));
    try {
      await engine.run(request, new AbortController().signal, async event => {
        if (event.type === 'ready') {
          const env = (await readFile('/proc/' + engine.workerPid + '/environ')).toString().split('\0');
          const proxy = new URL(env.find(value => value.startsWith('HTTPS_PROXY='))!.slice('HTTPS_PROXY='.length));
          await new Promise<void>((resolve, reject) => {
            const socket = connect(Number(proxy.port), '127.0.0.1');
            const timer = setTimeout(() => { socket.destroy(); reject(new Error('错误 PID 的连接未被拒绝')); }, 2000);
            const done = (): void => { clearTimeout(timer); resolve(); };
            socket.once('connect', () => socket.write('CONNECT api.anthropic.com:443 HTTP/1.1\r\nHost: api.anthropic.com:443\r\nProxy-Authorization: Basic ' + Buffer.from(proxy.username + ':' + proxy.password).toString('base64') + '\r\n\r\n'));
            socket.once('close', done); socket.once('error', done);
            socket.on('data', () => { clearTimeout(timer); socket.destroy(); reject(new Error('错误 PID 不应取得 CONNECT 成功响应')); });
          });
        }
        if (event.type === 'final_capture_ready') captures++;
      });
      expect(captures).toBe(1);
      const sample = engine.takeFinalCapture(request.input.request_id)!;
      expect(sample.verified).toBe(true);
      const report = await inspect();
      expect(report.calls.length).toBe(before + 1);
      expect(sample.sha256).toBe(report.calls.at(-1)!.bodySha256);
      evidence.push({ case: 'actual-socket-pid-proof', foreignConnectionRejected: true, legitimateRequestPassed: true, captures });
    } finally { await engine.close(); }
  }, 30000);

  test('上游认证代理的 CONNECT 凭据、头顺序和连接特征与原版一致', async () => {
    const target = await endpoint();
    const before = (await inspect()).connectHeads.length;
    for (const verify of [false, true]) {
      const running = await app(target, verify, { CCRB_PROXY_URL: 'http://fixture-user:fixture-pass@127.0.0.1:' + target.proxyPort });
      const result = await send(running);
      expect(result.response.status).toBe(200);
      if (verify) assertFinal(result.record, (await inspect()).calls.at(-1)!);
      await close(running);
    }
    const heads = (await inspect()).connectHeads.slice(before);
    expect(heads.length).toBe(2); expect(heads[0]).toEqual(heads[1]);
    const expected = 'Basic ' + Buffer.from('fixture-user:fixture-pass').toString('base64');
    expect(heads[1]?.authorizationSha256).toBe(createHash('sha256').update(expected).digest('hex'));
    evidence.push({ case: 'authenticated-proxy-connect', passed: true, heads });
  }, 30000);
});
