import { expect, test } from 'bun:test';
import { mkdtemp, mkdir, readlink, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { startLocalPool } from '../../scripts/local-pool';
import { startPoolFixture } from '../../scripts/testing/pool-fixture';
import { verifyCch } from '../../scripts/testing/pool-common';
import { parseInput } from '../../src/shared/input';
import { prepareInput } from '../../src/control/header-policy';
import { readNativeClassification } from '../../src/shared/native-classifier';
import { decodeLogDetail } from '../../src/shared/log-api';
import { Redactor } from '../../src/control/redaction';
import type { HeaderPair, MessageBody } from '../../src/shared/contracts';

test('实际交互标题、手动和自动压缩保持用途证据，局部相似业务不误分类', async () => {
  if (await readlink('/proc/self/ns/net') === await readlink('/proc/1/ns/net') || Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode !== 0) throw new Error('实际 CLI 用途验证必须使用隔离网络');
  const binary = process.env.CCRB_TEST_ORIGINAL_BINARY!;
  const root = await mkdtemp(join(tmpdir(), 'ccrb-session-purpose-')), config = join(root, 'config'), sessionId = randomUUID(), localizedSessionId = randomUUID();
  await mkdir(config);
  await writeFile(join(config, '.claude.json'), JSON.stringify({ userID: 'a'.repeat(64), hasCompletedOnboarding: true, theme: 'dark', projects: { [root]: { hasTrustDialogAccepted: true, hasCompletedProjectOnboarding: true } } }));
  await mkdir('artifacts', { recursive: true });
  await writeFile('artifacts/cli-session-purpose-proof.json', JSON.stringify({ passed: false, inProgress: true, realUpstreamRequests: 0 }) + '\n', { mode: 0o600 });
  const fixture = startPoolFixture('purpose-synthetic-pool-key'); fixture.select('session-purpose');
  const running = await startLocalPool({ binary, pool: { baseUrl: fixture.baseUrl, apiKey: 'purpose-synthetic-pool-key', live: false, mode: 'manual', maxRequests: 20, timeoutMs: 5000 }, runId: 'actual-session-purpose', directory: join(root, 'run'), port: 0 });
  const received: { raw: string; body: MessageBody; headers: HeaderPair[] }[] = [];
  const recorder = Bun.serve({ hostname: '127.0.0.1', port: 0, async fetch(request) {
    const raw = await request.text(); received.push({ raw, body: JSON.parse(raw) as MessageBody, headers: [...request.headers] });
    const path = new URL(request.url);
    const response = await fetch('http://127.0.0.1:' + running.app.server.port + path.pathname + path.search, { method: request.method, headers: request.headers, body: raw });
    return new Response(response.body, { status: response.status, headers: response.headers });
  } });

  /** 在同一实际会话中触发不同客户端入口；长输入通过 stdin 避免单参数容量限制。
   * @param mode 默认或中文交互、恢复、手动压缩、长输入或自动压缩。
   * @param prompt 客户端输入。
   * @return 已核对成功退出的客户端输出。
   */
  async function client(mode: 'interactive' | 'localized' | 'resume' | 'compact' | 'long' | 'auto', prompt: string): Promise<string> {
    const interactive = mode === 'interactive' || mode === 'localized';
    const base = [binary, '--model', 'claude-sonnet-4-6', interactive ? '--session-id' : '--resume', mode === 'localized' ? localizedSessionId : sessionId, '--tools', '', ...(mode === 'localized' ? ['--settings', JSON.stringify({ language: '简体中文' })] : [])];
    const args = interactive ? ['python3', resolve('tests/local-pool/pty-client.py'), ...base, '--', prompt] : [...base, '--print', '--max-turns', '3', '--output-format', 'json', ...(mode === 'auto' ? ['--autocompact', '100k'] : []), ...(mode === 'long' ? [] : ['--', prompt])];
    const cli = Bun.spawn(args, { cwd: root, env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: root, CLAUDE_CONFIG_DIR: config, LANG: 'C.UTF-8', TERM: 'xterm-256color', ANTHROPIC_BASE_URL: 'http://127.0.0.1:' + recorder.port, ANTHROPIC_AUTH_TOKEN: 'purpose-synthetic-client-token', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1', DISABLE_AUTOUPDATER: '1', ...(mode === 'auto' ? {} : { DISABLE_AUTO_COMPACT: '1' }), CLAUDE_CODE_MAX_OUTPUT_TOKENS: '128', MAX_THINKING_TOKENS: '0' }, stdout: 'pipe', stderr: 'pipe', stdin: mode === 'long' ? 'pipe' : 'ignore' });
    const stdout = new Response(cli.stdout).text(), stderr = new Response(cli.stderr).text();
    const timer = setTimeout(() => cli.kill(), 25000);
    try {
      if (mode === 'long') { cli.stdin!.write(prompt); await cli.stdin!.flush(); cli.stdin!.end(); }
      const code = await cli.exited, output = await stdout, diagnostics = await stderr;
      if (code !== 0) {
        await writeFile('artifacts/cli-session-purpose-proof.json', JSON.stringify({ passed: false, mode, code, output, diagnostics, modelPosts: fixture.calls.length, requestStates: running.app.store.list().rows.map(row => ({ state: row.state, error: row.error })), realUpstreamRequests: 0 }, null, 2) + '\n', { mode: 0o600 });
        throw new Error('实际 CLI 用途验证失败：' + mode + '；退出码 ' + code + '；输出 ' + output + '；诊断 ' + diagnostics);
      }
      if (interactive) expect(JSON.parse(output).finalSeen).toBe(true);
      else if (mode !== 'compact') expect(output).toContain('本机假池 OK');
      return output;
    } finally { clearTimeout(timer); }
  }

  try {
    await client('interactive', '验证会话标题与请求归类，仅回复 OK。');
    await client('localized', '验证显式中文设置下的会话标题，仅回复 OK。');
    await client('resume', '第一轮恢复，仅回复 OK。');
    await client('resume', '第二轮恢复，仅回复 OK。');
    await client('compact', '/compact 保留本机会话用途验证结果。');
    await client('resume', '根据摘要继续，仅回复 OK。');
    await client('long', Array.from({ length: 4000 }, (_, i) => 'CCRB_LONG_HISTORY_' + i + ' 合成记录，用于触发自动压缩。' + 'abcdefghijklmnpqrstuvwxyz0123456789'.repeat(3)).join('\n'));
    await client('auto', '继续当前会话，允许自动压缩，仅回复 OK。');
    await running.app.store.flush();
    const details = await Promise.all(running.app.store.list().rows.map(row => running.app.store.detail(row.id)));
    const classified = details.filter(d => d?.context?.classification?.purpose === 'session_title' || d?.context?.classification?.purpose === 'compaction');
    if (classified.length !== 4) {
      const redactor = new Redactor(); redactor.register({ api_key: 'purpose-synthetic-pool-key', token: 'purpose-synthetic-client-token' });
      await writeFile('artifacts/session-purpose-unrecognized.json', redactor.text(JSON.stringify(received.map(r => ({ body: r.body })), null, 2)) + '\n', { mode: 0o600 });
    }
    expect(classified.filter(d => d!.context!.classification!.purpose === 'session_title')).toHaveLength(2);
    expect(classified.filter(d => d!.context!.classification!.purpose === 'compaction')).toHaveLength(2);
    for (const detail of details) {
      expect(detail!.request.state).toBe('success'); expect(detail!.request.captureError).toBeNull();
      expect(decodeLogDetail(detail).context).toEqual(detail!.context);
      const ingress = detail!.captures.find(c => c.stage === 'ingress')!, wire = detail!.captures.find(c => c.stage === 'wire_final')!;
      const input = received.find(r => createHash('sha256').update(r.raw).digest('hex') === ingress.sha256)!;
      const output = fixture.calls.map(c => JSON.stringify({ ...c.body, model: input.body.model })).find(raw => createHash('sha256').update(raw).digest('hex') === wire.sha256);
      expect(output).toBeDefined(); verifyCch(output!);
      expect(JSON.parse(output!).messages).toEqual(input.body.messages);
      expect(JSON.parse(output!).tools).toEqual(input.body.tools);
      expect(JSON.parse(output!).system.slice(1)).toEqual((input.body.system as unknown[]).slice(1));
      if (!detail!.context?.classification) continue;
      const title = detail!.context.classification.purpose === 'session_title';
      expect(detail!.context).toMatchObject(title ? { requestClass: 'auxiliary', querySource: 'generate_session_title' } : { requestClass: 'compaction', querySource: 'compact' });
      expect(readNativeClassification({ ...input.body, max_tokens: 32769, thinking: { type: 'enabled', budget_tokens: 1024 } })).toEqual(detail!.context.classification);
      expect(() => prepareInput(parseInput({ body: input.body, context: { requestClass: 'main' } }, input.headers, 'local_base_url'))).toThrow('冲突');
      const damaged = structuredClone(input.body);
      if (title) (damaged.system as { text: string }[])[2]!.text += '不同静态内容';
      else {
        const message = damaged.messages.at(-1)!;
        if (typeof message.content === 'string') message.content += '不同固定收尾';
        else (message.content as { text: string }[]).at(-1)!.text += '不同固定收尾';
      }
      expect(readNativeClassification(damaged)).toBeUndefined();
      const framing = structuredClone(input.body), last = framing.messages.at(-1)!;
      if (typeof last.content === 'string') last.content = '不同固定前缀' + last.content;
      else (last.content as { text: string }[]).at(-1)!.text = '不同固定前缀' + (last.content as { text: string }[]).at(-1)!.text;
      expect(readNativeClassification(framing)).toBeUndefined();
      if (title) expect(readNativeClassification({ ...input.body, tools: [{ name: 'Read', input_schema: { type: 'object' } }] })).toBeUndefined();
      const later = structuredClone(input.body); later.messages.push({ role: 'user', content: [{ type: 'text', text: '这是一条普通后续业务消息。' }] });
      expect(readNativeClassification(later)).toBeUndefined();
      if (!title) {
        const child = structuredClone(input.body), billing = child.system as { text: string }[];
        expect(billing[0]!.text).not.toContain('cc_is_subagent='); billing[0]!.text += ' cc_is_subagent=true;';
        expect(prepareInput(parseInput({ body: child, context: { agentId: 'child-fixture', parentAgentId: sessionId, agentType: 'Explore' } }, input.headers, 'local_base_url')).context).toMatchObject({ requestClass: 'compaction', agentKind: 'subagent', agentId: 'child-fixture', parentAgentId: sessionId, agentType: 'Explore', querySource: 'compact' });
      }
    }
    expect(fixture.calls.length).toBe(details.length);
    await writeFile('artifacts/cli-session-purpose-proof.json', JSON.stringify({ passed: true, isolated: true, realUpstreamRequests: 0, sessionId, localizedSessionId, modelPosts: fixture.calls.length, verifiedWireSamples: details.length, purposes: classified.map(d => ({ requestId: d!.request.id, context: d!.context })) }, null, 2) + '\n', { mode: 0o600 });
  } finally { await recorder.stop(true); await running.close(); await fixture.close(); await rm(root, { recursive: true, force: true }); }
}, 65000);
