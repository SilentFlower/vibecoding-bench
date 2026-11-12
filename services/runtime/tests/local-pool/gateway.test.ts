import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { mkdtemp, mkdir, readFile, readlink, readdir, rm, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import { chromium } from '@playwright/test';
import { startLocalPool, type LocalPoolRunning } from '../../scripts/local-pool';
import { startPoolFixture, type PoolFixture } from '../../scripts/testing/pool-fixture';
import { verifyCch, type PoolConfig } from '../../scripts/testing/pool-common';
import type { MessageBody, RequestDetail } from '../../src/shared/contracts';

const binary = process.env.CCRB_TEST_ORIGINAL_BINARY!;
const secret = 'local-manual-pool-canary-827451';
let root: string, running: LocalPoolRunning, fixture: PoolFixture, base: string;
let previewId: string;

beforeAll(async () => {
  if (!binary || Bun.spawnSync(['ip','link','set','lo','up']).exitCode !== 0 || await readlink('/proc/self/ns/net') === await readlink('/proc/1/ns/net')) throw new Error('本地联调测试必须在隔离空间使用固定原版');
  const interfaces = (await readFile('/proc/net/dev', 'utf8')).split('\n').slice(2).filter(line => line.includes(':')).map(line => line.split(':')[0]!.trim());
  if (interfaces.join(',') !== 'lo') throw new Error('测试存在外网接口');
  root = await mkdtemp(join(tmpdir(), 'ccrb-local-test-'));
  await writeFile(join(root, 'tool-fixture.txt'), '仅供离线 Read 工具读取的内容\n');
  fixture = startPoolFixture(secret, join(root, 'tool-fixture.txt'));
  const pool: PoolConfig = { baseUrl: fixture.baseUrl, apiKey: secret, live: false, mode: 'manual', maxRequests: 20, timeoutMs: 500 };
  running = await startLocalPool({ binary, pool, runId: 'offline-manual', directory: join(root, 'gateway'), port: 0 });
  base = 'http://127.0.0.1:' + running.app.server.port;
}, 30000);

afterAll(async () => { await running?.close(); await fixture?.close(); if (root) await rm(root, { recursive: true, force: true }); });

/** 等待同请求日志终态，不以固定睡眠推断 worker_idle。
 * @param id 请求 ID。
 * @param instance 读取日志的本地实例，缺省使用原有限测试实例。
 * @return 已结束详情。
 */
async function detail(id: string, instance = running): Promise<RequestDetail> {
  const until = performance.now() + 8000;
  while (performance.now() < until) {
    await instance.app.store.flush();
    const value = await instance.app.store.detail(id);
    if (value?.request.finishedAt) return value;
    await Bun.sleep(10);
  }
  throw new Error('请求日志没有收口');
}

/** 以真实 293 客户端验证 Base URL，包括它自行执行隔离 Read 工具的续轮。
 * @param tool 是否要求工具续轮。
 * @return 客户端输出。
 */
async function client(tool: boolean): Promise<string> {
  const home = join(root, tool ? 'tool-client' : 'client');
  await mkdir(join(home, 'config'), { recursive: true, mode: 0o700 });
  await writeFile(join(home, 'config/.claude.json'), JSON.stringify({ userID: 'a'.repeat(64), hasCompletedOnboarding: true }));
  const cli = Bun.spawn([binary, '--print', '--model', 'claude-sonnet-4-6', '--max-turns', tool ? '3' : '1', ...(tool ? ['--tools','Read','--allowedTools','Read'] : []), '--', tool ? '读取 tool-fixture.txt 然后回复 OK' : '仅回复 OK'], { cwd: root, env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: home, LANG: 'C.UTF-8', CLAUDE_CONFIG_DIR: join(home, 'config'), ANTHROPIC_BASE_URL: base, ANTHROPIC_AUTH_TOKEN: 'local-client-synthetic-827451', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1', DISABLE_AUTOUPDATER: '1', DISABLE_AUTO_COMPACT: '1' }, stdout: 'pipe', stderr: 'pipe' });
  const stdout = new Response(cli.stdout).text(), stderr = new Response(cli.stderr).text();
  const timer = setTimeout(() => cli.kill(), 25000);
  try { const code = await cli.exited; const output = await stdout, diagnostic = await stderr; if (code !== 0) throw new Error('离线 CLI 未成功：' + output.slice(0, 1000) + diagnostic.slice(0, 1000)); return output; }
  finally { clearTimeout(timer); }
}

function nativeBody(entry = 'cli'): MessageBody {
  return { model: 'claude-sonnet-4-6', max_tokens: 64, stream: false, messages: [{ role: 'user', content: '离线原生请求' }], system: [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=' + entry + ';' }, { type: 'text', text: '业务 system' }], metadata: { user_id: JSON.stringify({ device_id: 'a'.repeat(64), account_uuid: '', session_id: '11111111-1111-4111-8111-111111111111' }) } };
}

describe('本地常驻 Base URL 的原生闭环', () => {
  test('启动、健康和页面零推理，只有本地实例提供最终采集能力', async () => {
    for (let index = 0; index < 3; index++) {
      const health = await (await fetch(base + '/api/health')).json();
      expect(health.nativeFinalCapture).toBe(true); expect(health.localPool).toMatchObject({ live: false, budget: 20, reserved: 0, remaining: 20 });
      expect((await fetch(base + '/')).status).toBe(200);
    }
    expect(fixture.calls).toHaveLength(0);
  });

  test('实际 --print 客户端缺少 CCH、sdk-cli、默认输出和完整工具列表可以请求', async () => {
    fixture.select('sse'); const before = fixture.calls.length;
    expect(await client(false)).toContain('本机假池 OK');
    expect(fixture.calls.length).toBe(before + 1);
    const row = running.app.store.list().rows[0]!, value = await detail(row.id);
    expect(value.context?.inputFormat).toBe('claude_code'); expect(value.request.state).toBe('success');
    const ingress = JSON.parse(value.captures.find(item => item.stage === 'ingress')!.text!);
    const wire = value.captures.find(item => item.stage === 'wire_final')!;
    expect(ingress.system[0].text).toContain('cc_entrypoint=sdk-cli;'); expect(ingress.system[0].text).not.toContain('cch=');
    expect(ingress.max_tokens).toBe(32000); expect(ingress.tools.length).toBeGreaterThan(0);
    expect(wire.status).toBe('complete'); expect(wire.source).toBe('local_pool_node_tls_receiver');
    const wireHeaders = new Headers(wire.headers);
    expect(wireHeaders.get('accept')).toBe('application/json');
    expect(wireHeaders.get('anthropic-dangerous-direct-browser-access')).toBe('true');
    const ledger = await Bun.file(join(running.directory, 'ledger.json')).json();
    expect(ledger.reservations).toContainEqual(expect.objectContaining({ requestId: row.id, transportDiagnostics: expect.objectContaining({ phase: 'response_body', bodySentObserved: true }) }));
    const outgoing = JSON.parse(wire.text!);
    expect(outgoing.system[0].text).toContain('cc_entrypoint=cli;');
    // 预览允许脱敏；用假池内存实收与原始哈希证明，不反向修改持久预览。
    const observed = JSON.stringify({ ...fixture.calls.at(-1)!.body, model: ingress.model });
    expect(wire.sha256).toBe(createHash('sha256').update(observed).digest('hex')); verifyCch(observed);
    expect(outgoing.messages).toEqual(ingress.messages); expect(outgoing.tools).toEqual(ingress.tools);
    expect(outgoing.system.slice(1)).toEqual(ingress.system.slice(1));
    expect(fixture.calls.at(-1)!.body.model).toBe('deepseek-flash');
    expect(fixture.calls.at(-1)!.authenticated).toBe(true);
  }, 30000);

  test('实际客户端执行隔离 Read 工具并把 tool_result 作为新一轮转发', async () => {
    fixture.select('tool'); const before = fixture.calls.length;
    expect(await client(true)).toContain('本机假池 OK');
    expect(fixture.calls.length).toBe(before + 2);
    expect(JSON.stringify(fixture.calls.at(-1)!.body.messages)).toContain('tool_result');
    expect(JSON.stringify(fixture.calls.at(-1)!.body.messages)).toContain('仅供离线 Read 工具读取');
  }, 30000);

  test('真实伪终端的交互 CLI 使用 cli 入站并取得响应', async () => {
    fixture.select('sse'); const before = fixture.calls.length;
    const home = join(root, 'interactive-client'), config = join(home, 'config');
    await mkdir(config, { recursive: true, mode: 0o700 });
    await writeFile(join(config, '.claude.json'), JSON.stringify({ userID: 'a'.repeat(64), hasCompletedOnboarding: true, theme: 'dark', projects: { [root]: { hasTrustDialogAccepted: true, hasCompletedProjectOnboarding: true } } }));
    const child = Bun.spawn(['python3',resolve('tests/local-pool/pty-client.py'),binary,'--model','claude-sonnet-4-6','仅回复 OK'], { cwd: root, env: { HOME: home, CLAUDE_CONFIG_DIR: config, PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8', TERM: 'xterm-256color', ANTHROPIC_BASE_URL: base, ANTHROPIC_AUTH_TOKEN: 'local-interactive-synthetic-token', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1', DISABLE_AUTOUPDATER: '1', DISABLE_AUTO_COMPACT: '1' }, stdout: 'pipe', stderr: 'pipe' });
    const text = new Response(child.stdout).text(), diagnostics = new Response(child.stderr).text();
    const code = await child.exited, result = JSON.parse(await text); await diagnostics;
    if (!result.finalSeen || code !== 0) throw new Error('离线交互终端未成功：' + JSON.stringify(result) + '；新增池请求：' + (fixture.calls.length - before));
    expect(fixture.calls.length).toBeGreaterThan(before);
    const incoming = fixture.calls[before]!.body.system as { text: string }[];
    expect(incoming[0]!.text).toContain('cc_entrypoint=cli;');
    const value = await detail(running.app.store.list().rows[0]!.id);
    expect(JSON.parse(value.captures.find(item => item.stage === 'ingress')!.text!).system[0].text).toContain('cc_entrypoint=cli;');
  }, 30000);

  test('cli 入站无 CCH、工具省略、根模型映射和 JSON 响应均保持', async () => {
    fixture.select('json');
    for (const cch of ['', ' cch=abcde;']) {
      const body = nativeBody(); (body.system as { text: string }[])[0]!.text += cch;
      const response = await fetch(base + '/v1/messages', { method: 'POST', body: JSON.stringify(body) });
      expect(response.status).toBe(200); expect((await response.json()).model).toBe('deepseek-flash');
      const value = await detail(response.headers.get('x-ccrb-request-id')!);
      const wire = value.captures.find(item => item.stage === 'wire_final')!;
      expect(wire.status).toBe('complete'); expect(JSON.parse(wire.text!).tools).toBeUndefined(); verifyCch(wire.text!);
    }
  }, 15000);

  test('端口冲突明确报错并清理启动资源，不产生池推理', async () => {
    const before = fixture.calls.length;
    await expect(startLocalPool({ binary, pool: { baseUrl: fixture.baseUrl, apiKey: secret, mode: 'manual', live: false, maxRequests: 20, timeoutMs: 500 }, runId: 'port-conflict', directory: join(root, 'port-conflict'), port: running.app.server.port })).rejects.toThrow('端口已占用');
    expect(fixture.calls.length).toBe(before);
    expect((await Bun.file(join(root, 'port-conflict', 'ledger.json')).json()).reserved).toBe(0);
  }, 15000);

  test('损坏证据、版本、控制字段与非法输出参数的请求不调用池', async () => {
    const before = fixture.calls.length;
    for (const change of [{ system: [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.303.abc; cc_entrypoint=cli;' }] }, { workdir: {} }, { max_tokens: '64' }]) {
      const response = await fetch(base + '/v1/messages', { method: 'POST', body: JSON.stringify({ ...nativeBody(), ...change }) });
      expect(response.status).toBeGreaterThanOrEqual(400); await response.text();
    }
    expect(fixture.calls.length).toBe(before);
  }, 15000);

  test('原生子代理身份与父子标识沿 TLS 和第二段保持', async () => {
    fixture.select('json'); const body = nativeBody(); (body.system as { text: string }[])[0]!.text += ' cc_is_subagent=true;';
    const response = await fetch(base + '/v1/messages', { method: 'POST', headers: { 'x-claude-code-request-class': 'subagent', 'x-claude-code-agent-id': 'child-local', 'x-claude-code-parent-agent-id': 'parent-local', 'x-claude-code-agent-type': 'Explore' }, body: JSON.stringify(body) });
    expect(response.status).toBe(200); await response.text();
    const value = await detail(response.headers.get('x-ccrb-request-id')!);
    expect(value.context).toMatchObject({ requestClass: 'subagent', agentKind: 'subagent', agentId: 'child-local', parentAgentId: 'parent-local' });
    expect((fixture.calls.at(-1)!.body.system as { text: string }[])[0]!.text).toContain('cc_is_subagent=true;');
    expect(value.captures.find(item => item.stage === 'wire_final')!.headers).toContainEqual(['x-claude-code-parent-agent-id', 'parent-local']);
  }, 15000);

  test('取消传到池、日志保留 TLS 样本，下一请求可重建并成功', async () => {
    fixture.select('cancel'); const canceledBefore = fixture.canceled;
    const controller = new AbortController();
    const response = await fetch(base + '/v1/messages', { method: 'POST', signal: controller.signal, body: JSON.stringify({ ...nativeBody(), stream: true }) });
    const reader = response.body!.getReader(); await reader.read(); controller.abort(); await reader.cancel().catch(() => {});
    const value = await detail(response.headers.get('x-ccrb-request-id')!);
    expect(value.request.state).toBe('canceled'); expect(value.captures.find(item => item.stage === 'wire_final')!.status).toBe('complete');
    expect(fixture.canceled).toBeGreaterThan(canceledBefore);
    fixture.select('sse');
    const next = await fetch(base + '/v1/messages', { method: 'POST', body: JSON.stringify({ ...nativeBody(), stream: true }) });
    expect(next.status).toBe(200); expect(await next.text()).toContain('event: message_stop');
    expect((await detail(next.headers.get('x-ccrb-request-id')!)).request.state).toBe('success');
  }, 20000);

  test('池完整和跨块凭据回显不落盘，原始逻辑哈希保持', async () => {
    for (const choice of ['secret', '401', 'event-error']) {
      fixture.select(choice);
      const response = await fetch(base + '/v1/messages', { method: 'POST', body: JSON.stringify({ ...nativeBody(), ...(choice === 'event-error' ? { stream: true } : {}) }) });
      const raw = await response.text(), value = await detail(response.headers.get('x-ccrb-request-id')!);
      if (choice === 'secret') previewId = value.request.id;
      expect(raw).toContain(secret); expect(JSON.stringify(value)).not.toContain(secret);
      expect(value.captures.find(item => item.stage === 'upstream_response')!.sha256).toBe(createHash('sha256').update(raw).digest('hex'));
    }
    const scan = async (directory: string): Promise<void> => {
      for (const entry of await readdir(directory, { withFileTypes: true })) {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) await scan(path); else expect((await readFile(path)).includes(Buffer.from(secret))).toBe(false);
      }
    };
    await scan(running.directory);
  }, 15000);

  test('桌面和手机日志页展示真实 TLS 来源，刷新零推理、秘密和脚本不泄漏', async () => {
    const before = fixture.calls.length, browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--no-sandbox','--disable-dev-shm-usage'] });
    try {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(base); await page.getByLabel('每 3 秒刷新').uncheck();
      await page.getByTitle(previewId, { exact: true }).click();
      const dialog = page.getByRole('dialog');
      await dialog.getByRole('tab', { name: '原始数据', exact: true }).click();
      await dialog.getByRole('button', { name: /最终出站采样/ }).click();
      expect(await dialog.locator('.capture-meta').textContent()).toContain('local_pool_node_tls_receiver');
      expect(await dialog.textContent()).toContain('独立 CCH 核验通过');
      await mkdir(resolve('artifacts'), { recursive: true });
      await page.screenshot({ path: 'artifacts/local-pool-offline-desktop.png' });
      await dialog.getByRole('button', { name: /上游响应/ }).click();
      expect(await dialog.textContent()).not.toContain(secret); expect(await dialog.locator('script').count()).toBe(0);
      expect(await page.evaluate(() => 'poolXss' in globalThis)).toBe(false);
      await page.setViewportSize({ width: 390, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
      await page.screenshot({ path: 'artifacts/local-pool-offline-mobile.png' });
      for (let index = 0; index < 3; index++) await page.reload();
      expect(fixture.calls.length).toBe(before); expect(errors).toEqual([]);
      await writeFile('artifacts/local-pool-offline-page-proof.json', JSON.stringify({ passed: true, source: 'local_pool_node_tls_receiver', desktop: 1440, mobile: 390, refreshes: 3, inferenceOnRefresh: 0, realUpstreamRequests: 0, pageErrors: errors }, null, 2) + '\n');
    } finally { await browser.close(); }
  }, 20000);

  test('池超时、本地状态、HTTP 错误和重定向分别记录，均不重试', async () => {
    for (const choice of ['timeout','429','500','redirect']) {
      fixture.select(choice); const before = fixture.calls.length;
      const response = await fetch(base + '/v1/messages', { method: 'POST', body: JSON.stringify(nativeBody()) });
      expect(response.status).toBe(choice === 'timeout' ? 502 : choice === 'redirect' ? 302 : Number(choice)); await response.text();
      await detail(response.headers.get('x-ccrb-request-id')!);
      expect(fixture.calls.length).toBe(before + 1); expect(fixture.redirected).toBe(0);
      const ledger = await Bun.file(join(running.directory, 'ledger.json')).json();
      expect(ledger.reservations.at(-1).upstreamStatus).toBe(choice === 'timeout' ? null : response.status);
    }
  }, 15000);

  test('同运行目录不能重置，20 次额度耗尽后不发生第 21 次池请求', async () => {
    fixture.select('json');
    while (running.status().reserved < 20) {
      const response = await fetch(base + '/v1/messages', { method: 'POST', body: JSON.stringify(nativeBody()) });
      expect(response.status).toBe(200); await response.text();
    }
    expect(fixture.calls).toHaveLength(20);
    const response = await fetch(base + '/v1/messages', { method: 'POST', body: JSON.stringify(nativeBody()) });
    expect(response.status).toBe(429); expect(await response.text()).toContain('额度'); expect(fixture.calls).toHaveLength(20);
    const saved = await Bun.file(join(running.directory, 'ledger.json')).json();
    expect(saved.reserved).toBe(20); expect(saved.reservations).toHaveLength(20);
    await expect(startLocalPool({ binary, pool: { baseUrl: fixture.baseUrl, apiKey: secret, mode: 'manual', live: false, maxRequests: 20, timeoutMs: 2000 }, runId: 'offline-manual', directory: running.directory, port: 0 })).rejects.toThrow();
    expect(await Bun.file(join(running.directory, 'ledger.json')).json()).toEqual(saved);
    const health = await (await fetch(base + '/api/health')).json(); expect(health.localPool.remaining).toBe(0);
  }, 30000);

  test('不限次数的手工实例原样转发 128000 与 adaptive，超过 20 次仍继续计数', async () => {
    fixture.select('json'); const before = fixture.calls.length;
    const unlimited = await startLocalPool({ binary, pool: { baseUrl: fixture.baseUrl, apiKey: secret, mode: 'manual', live: false, maxRequests: null, timeoutMs: 500 }, runId: 'unlimited-manual', directory: join(root, 'unlimited-manual'), port: 0 });
    const url = 'http://127.0.0.1:' + unlimited.app.server.port;
    try {
      expect(unlimited.status()).toMatchObject({ budget: null, remaining: null, reserved: 0 });
      const body = { ...nativeBody(), model: 'claude-opus-5-5', max_tokens: 128000, thinking: { type: 'adaptive' } };
      for (let index = 0; index < 25; index++) {
        const response = await fetch(url + '/v1/messages', { method: 'POST', body: JSON.stringify(body) });
        expect(response.status).toBe(200); await response.text();
        expect(fixture.calls.at(-1)!.body).toMatchObject({ model: 'deepseek-flash', max_tokens: 128000, thinking: { type: 'adaptive' } });
      }
      expect(fixture.calls.length).toBe(before + 25);
      const health = await (await fetch(url + '/api/health')).json();
      expect(health.localPool).toMatchObject({ budget: null, remaining: null, reserved: 25 });
      const ledger = await Bun.file(join(unlimited.directory, 'ledger.json')).json();
      expect(ledger.reservations).toHaveLength(25); expect(ledger.reservations.every((row: { attempted: boolean }) => row.attempted)).toBe(true);
    } finally { await unlimited.close(); }
  }, 20000);

  test('薄桥接保留原生分类和参数，26 MiB 正文及 66 秒长请求均可完成', async () => {
    const thin = await startLocalPool({ binary, pool: { baseUrl: fixture.baseUrl, apiKey: secret, mode: 'manual', live: false, maxRequests: null, timeoutMs: 0 }, runId: 'thin-manual', directory: join(root, 'thin-manual'), port: 0 });
    const url = 'http://127.0.0.1:' + thin.app.server.port;
    try {
      fixture.select('json');
      const classifier = { ...nativeBody(), model: 'claude-sonnet-5', thinking: { type: 'disabled' }, stop_sequences: ['合成分类结束'] };
      for (const change of [{}, { max_tokens: 128000, temperature: 2, thinking: { type: 'enabled', budget_tokens: 512 }, tools: [], tool_choice: { type: 'any' } }]) {
        const body = { ...classifier, ...change }, before = fixture.calls.length;
        const response = await fetch(url + '/v1/messages', { method: 'POST', body: JSON.stringify(body) });
        expect(response.status).toBe(200); await response.text();
        expect(fixture.calls.length).toBe(before + 1);
        const received = fixture.calls.at(-1)!.body;
        for (const key of ['messages', 'max_tokens', 'temperature', 'thinking', 'tool_choice', 'tools', 'stop_sequences']) expect(received[key]).toEqual((body as MessageBody)[key]);
        expect((received.system as unknown[]).slice(1)).toEqual((body.system as unknown[]).slice(1));
        verifyCch(JSON.stringify({ ...received, model: body.model }));
      }

      const large = { ...classifier, messages: [{ role: 'user', content: 'x'.repeat(26 * 1024 * 1024) }] };
      const largeResponse = await fetch(url + '/v1/messages', { method: 'POST', body: JSON.stringify(large) });
      const largeText = await largeResponse.text();
      if (largeResponse.status !== 200) {
        const failed = await detail(largeResponse.headers.get('x-ccrb-request-id')!, thin);
        const evidence = { status: largeResponse.status, response: largeText, captures: failed.captures.map(item => ({ stage: item.stage, status: item.status, bytes: item.observedBytes, note: item.note })), ledger: await Bun.file(join(thin.directory, 'ledger.json')).json() };
        await writeFile('artifacts/thin-runtime-failure.json', JSON.stringify(evidence, null, 2) + '\n');
        throw new Error('大正文转发失败：' + JSON.stringify(evidence));
      }
      expect(fixture.calls.at(-1)!.body.messages).toEqual(large.messages);
      const largeDetail = await detail(largeResponse.headers.get('x-ccrb-request-id')!, thin);
      const wire = largeDetail.captures.find(item => item.stage === 'wire_final')!;
      const raw = JSON.stringify({ ...fixture.calls.at(-1)!.body, model: large.model });
      expect(wire.status).toBe('truncated'); expect(wire.observedBytes).toBe(Buffer.byteLength(raw));
      expect(wire.sha256).toBe(createHash('sha256').update(raw).digest('hex')); verifyCch(raw);

      fixture.select('long-sse'); const before = fixture.calls.length, started = performance.now();
      const long = await fetch(url + '/v1/messages', { method: 'POST', body: JSON.stringify({ ...nativeBody(), stream: true }) });
      const headersMs = performance.now() - started;
      expect(long.status).toBe(200); expect(await long.text()).toContain('event: message_stop');
      const elapsedMs = performance.now() - started;
      expect(headersMs).toBeGreaterThan(50000); expect(elapsedMs).toBeGreaterThan(65000);
      expect(fixture.calls.length).toBe(before + 1);
      expect((await detail(long.headers.get('x-ccrb-request-id')!, thin)).request.state).toBe('success');
      await writeFile('artifacts/thin-runtime-offline-proof.json', JSON.stringify({ passed: true, realUpstreamRequests: 0, classifier: 'claude-sonnet-5', originalParameters: true, bodyBytes: wire.observedBytes, sha256: wire.sha256, headersMs, elapsedMs, retries: 0 }, null, 2) + '\n');
    } finally { await thin.close(); }
  }, 90000);
});
