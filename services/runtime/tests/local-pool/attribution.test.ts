import { expect, test } from 'bun:test';
import { mkdtemp, mkdir, readlink, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { startLocalPool } from '../../scripts/local-pool';
import { startPoolFixture } from '../../scripts/testing/pool-fixture';
import { verifyCch } from '../../scripts/testing/pool-common';
import { parseInput } from '../../src/shared/input';
import { prepareInput } from '../../src/control/header-policy';
import type { MessageBody } from '../../src/shared/contracts';

test('实际 CLI 的分类、子代理启动及报告回传具有正确归因', async () => {
  if (await readlink('/proc/self/ns/net') === await readlink('/proc/1/ns/net') || Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode !== 0) throw new Error('实际 CLI 归因验证必须使用隔离网络');
  const binary = process.env.CCRB_TEST_ORIGINAL_BINARY!;
  const root = await mkdtemp(join(tmpdir(), 'ccrb-attribution-')), config = join(root, 'config');
  const cases: Record<string, unknown>[] = [];
  await mkdir('artifacts', { recursive: true });
  await writeFile('artifacts/cli-attribution-proof.json', JSON.stringify({ passed: false, inProgress: true, realUpstreamRequests: 0 }) + '\n', { mode: 0o600 });
  await mkdir(config);
  await writeFile(join(config, '.claude.json'), JSON.stringify({ userID: 'a'.repeat(64), hasCompletedOnboarding: true }));
  const fixture = startPoolFixture('attribution-synthetic-pool-key'); fixture.select('agent');
  // 固定四组离线场景合计超过 20 次，使用手工不限次数账本并逐次核对假池实收。
  const running = await startLocalPool({ binary, pool: { baseUrl: fixture.baseUrl, apiKey: 'attribution-synthetic-pool-key', live: false, mode: 'manual', maxRequests: null, timeoutMs: 3000 }, runId: 'actual-attribution', directory: join(root, 'run'), port: 0 });
  const received: { raw: string; body: MessageBody }[] = [];
  // 原始内存样本用于业务比较；脱敏预览只能展示，不能反推出原始内容。
  const recorder = Bun.serve({ hostname: '127.0.0.1', port: 0, async fetch(request) {
    const raw = await request.text(); received.push({ raw, body: JSON.parse(raw) as MessageBody });
    const path = new URL(request.url);
    const response = await fetch('http://127.0.0.1:' + running.app.server.port + path.pathname + path.search, { method: request.method, headers: request.headers, body: raw });
    return new Response(response.body, { status: response.status, headers: response.headers });
  } });
  try {
    for (const mode of ['default', 'deny', 'two-stage', 'foreground']) {
      const deny = mode === 'deny'; fixture.select(mode === 'two-stage' ? 'agent-two-stage' : mode === 'foreground' ? 'agent-foreground' : 'agent');
      await writeFile(join(config, 'settings.json'), JSON.stringify(deny ? { permissions: { deny: ['Bash(rm *)'] } } : {}));
      const sessionId = randomUUID(), before = fixture.calls.length;
      const cli = Bun.spawn([binary, '--print', '--model', 'claude-sonnet-4-6', '--session-id', sessionId, '--max-turns', '3', '--tools', 'Agent', '--allowedTools', 'Agent', '--', '调用 Explore 子代理，再根据它交回的报告回复。'], { cwd: root, env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: root, CLAUDE_CONFIG_DIR: config, LANG: 'C.UTF-8', ANTHROPIC_BASE_URL: 'http://127.0.0.1:' + recorder.port, ANTHROPIC_AUTH_TOKEN: 'attribution-synthetic-client-token', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1', DISABLE_AUTOUPDATER: '1', DISABLE_AUTO_COMPACT: '1', CLAUDE_CODE_MAX_OUTPUT_TOKENS: '128', MAX_THINKING_TOKENS: '0' }, stdout: 'pipe', stderr: 'pipe', stdin: 'ignore' });
      const stdout = new Response(cli.stdout).text(), stderr = new Response(cli.stderr).text();
      const timer = setTimeout(() => cli.kill(), 25000);
      const code = await cli.exited; clearTimeout(timer);
      expect(code).toBe(0); expect(await stdout).toContain('本机假池 OK'); await stderr;
      await running.app.store.flush();
      const rows = running.app.store.list({ sessionId }).rows;
      const details = await Promise.all(rows.map(row => running.app.store.detail(row.id)));
      const classifiers = details.filter(value => { const b = JSON.parse(value!.captures.find(c => c.stage === 'ingress')!.text!); return b.stop_sequences?.includes('</block>') || b.max_tokens === 8192; });
      expect(classifiers.length).toBe(mode === 'two-stage' ? 4 : 2);
      for (const value of classifiers) {
        if (value!.request.requestClass !== 'auxiliary') {
          await mkdir('artifacts', { recursive: true });
          await writeFile('artifacts/classifier-unrecognized-' + value!.request.id + '.json', value!.captures.find(c => c.stage === 'ingress')!.text!, { mode: 0o600 });
        }
        expect(value!.request.requestClass).toBe('auxiliary');
        expect(value!.context).toMatchObject({ requestClass: 'auxiliary', querySource: 'auto_mode', classification: { purpose: 'auto_permission_classifier', source: 'native_profile' } });
      }
      const classifierCapture = classifiers[0]!.captures.find(c => c.stage === 'ingress')!;
      const actualClassifier = received.find(r => createHash('sha256').update(r.raw).digest('hex') === classifierCapture.sha256)!.body;
      if (deny) expect((actualClassifier.system as { text: string }[])[1]!.text).toContain('`Bash(rm *)`');
      for (const change of ['system', 'footer', 'stop', 'temperature', 'tools']) {
        const modified = structuredClone(actualClassifier);
        if (change === 'system') (modified.system as { text: string }[])[1]!.text += '不同静态内容';
        if (change === 'footer') (modified.messages.at(-1)!.content as { text: string }[]).at(-1)!.text += '不同收尾';
        if (change === 'stop') modified.stop_sequences = ['different'];
        if (change === 'temperature') modified.temperature = 0;
        if (change === 'tools') modified.tools = [];
        expect(prepareInput(parseInput(modified, [], 'local_base_url')).context.classification).toBeUndefined();
      }
      expect(() => prepareInput(parseInput({ body: actualClassifier, context: { requestClass: 'main' } }, [], 'local_base_url'))).toThrow('冲突');
      const thinkingVariant = { ...actualClassifier, max_tokens: Number(actualClassifier.max_tokens) + 1024, thinking: { type: 'enabled', budget_tokens: 1024 } };
      expect(prepareInput(parseInput(thinkingVariant, [], 'local_base_url')).context.classification).toBeDefined();
      const child = details.find(value => value?.context?.agentKind === 'subagent')!;
      expect(child.context?.parentAgentId).toBeUndefined(); expect(child.context?.agentType).toBeUndefined();
      expect(child).toMatchObject({ agentAssociation: { state: 'linked', parentAgentId: sessionId, agentType: 'Explore', parentSource: 'client_tool_result', typeSource: 'client_tool_result' } });
      const calls = fixture.calls.slice(before);
      expect(calls.some(call => JSON.stringify(call.body.messages).includes('[Subagent hand-back]'))).toBe(true);
      for (const value of details) {
        expect(value!.request.state).toBe('success');
        const ingress = value!.captures.find(c => c.stage === 'ingress')!;
        const input = received.find(r => createHash('sha256').update(r.raw).digest('hex') === ingress.sha256)!.body;
        const wire = value!.captures.find(c => c.stage === 'wire_final')!;
        const raw = calls.map(call => JSON.stringify({ ...call.body, model: input.model })).find(raw => createHash('sha256').update(raw).digest('hex') === wire.sha256);
        expect(raw).toBeDefined(); verifyCch(raw!);
        const output = JSON.parse(raw!);
        expect(output.messages).toEqual(input.messages); expect(output.tools).toEqual(input.tools);
        expect(output.system.slice(1)).toEqual((input.system as unknown[]).slice(1));
        expect(new Headers(wire.headers).get('accept')).toBe('application/json');
        expect(new Headers(wire.headers).get('anthropic-dangerous-direct-browser-access')).toBe('true');
      }
      expect(calls.length).toBe(rows.length);
      cases.push({ mode, denyRules: deny, sessionId, classifierIds: classifiers.map(d => ({ requestId: d!.request.id, profile: d!.context!.classification!.profile })), childRequestId: child.request.id, association: child.agentAssociation, modelPosts: calls.length, verifiedWireSamples: details.length });
    }
    await writeFile('artifacts/cli-attribution-proof.json', JSON.stringify({ passed: true, isolated: true, realUpstreamRequests: 0, cases }, null, 2) + '\n', { mode: 0o600 });
  } finally { await recorder.stop(true); await running.close(); await fixture.close(); await rm(root, { recursive: true, force: true }); }
}, 65000);
