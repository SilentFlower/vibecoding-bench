import { expect, test } from 'bun:test';
import { createServer } from 'node:http';
import { mkdir, mkdtemp, readFile, readlink, readdir, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';
import { startLocalPool, type LocalPoolRunning } from '../../scripts/local-pool';
import type { MessageBody } from '../../src/shared/contracts';
import type { PoolIncidentReport } from '../../scripts/testing/local-pool-incidents';

/** 只构造隔离测试的原生正文。 @param label 场景。 @param session 会话。 @param child 是否子代理。 @return 无真实身份的入站正文。 */
function body(label: string, session: string, child = false): MessageBody {
  return { model: 'claude-sonnet-4-6', max_tokens: 64, stream: label === 'stream' || label === 'incomplete', messages: [{ role: 'user', content: label }], system: [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli;' + (child ? ' cc_is_subagent=true;' : '') }], metadata: { user_id: JSON.stringify({ device_id: 'a'.repeat(64), account_uuid: '', session_id: session }) } };
}

/** 等待已排他发布的报告，不靠中间状态推断取证完成。 @param path 报告文件。 @return 报告。 */
async function waitReport(path: string): Promise<PoolIncidentReport> {
  const deadline = performance.now() + 18000;
  while (performance.now() < deadline) {
    try { return JSON.parse(await readFile(path, 'utf8')); } catch { await Bun.sleep(30); }
  }
  throw new Error('自动取证报告未收口');
}

test('实际本地池自动取证覆盖断连、HTTP、流错误、多会话及收口，零真实推理', async () => {
  if (await readlink('/proc/self/ns/net') === await readlink('/proc/1/ns/net') || Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode !== 0) throw new Error('取证验收必须在无外网空间');
  const binary = process.env.CCRB_TEST_ORIGINAL_BINARY ?? Bun.which('claude');
  if (!binary) throw new Error('取证验收需要已登记的原版运行时');
  const root = await mkdtemp(join(tmpdir(), 'ccrb-incidents-native-'));
  const key = 'incident-pool-synthetic-private-canary-542387';
  const calls: { label: string; clientId: string | undefined }[] = [], reports: PoolIncidentReport[] = [];
  const running: LocalPoolRunning[] = [];
  let passed = false;
  const fake = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on('data', chunk => chunks.push(Buffer.from(chunk)));
    request.on('end', () => {
      const input = JSON.parse(Buffer.concat(chunks).toString()) as MessageBody, label = String(input.messages[0]!.content);
      calls.push({ label, clientId: typeof request.headers['x-client-request-id'] === 'string' ? request.headers['x-client-request-id'] : undefined });
      if (label === 'disconnect') { request.socket.destroy(); return; }
      const headers = { 'x-oneapi-request-id': 'fixture-' + label, 'x-echo-secret': key };
      if (label === 'http') { response.writeHead(429, { ...headers, 'content-type': 'application/json' }); response.end(JSON.stringify({ type: 'error', error: { message: key } })); return; }
      const message = { id: 'msg_incident', type: 'message', role: 'assistant', model: 'deepseek-flash', content: [{ type: 'text', text: '离线取证成功' }], stop_reason: 'end_turn', stop_sequence: null, usage: { input_tokens: 1, output_tokens: 1 } };
      if (input.stream) {
        response.writeHead(200, { ...headers, 'content-type': 'text/event-stream' });
        response.write('event: message_start\ndata: ' + JSON.stringify({ type: 'message_start', message: { ...message, content: [], stop_reason: null } }) + '\n\n');
        if (label === 'stream') response.write('event: error\ndata: ' + JSON.stringify({ type: 'error', error: { message: key } }) + '\n\n');
        response.end(); return;
      }
      response.writeHead(200, { ...headers, 'content-type': 'application/json' }); response.end(JSON.stringify(message));
    });
  });
  await new Promise<void>(resolve => fake.listen(0, '127.0.0.1', resolve));
  const address = fake.address(); if (!address || typeof address === 'string') throw new Error('假池未就绪');
  const baseUrl = 'http://127.0.0.1:' + address.port;
  const start = async (name: string) => {
    const value = await startLocalPool({ binary, runId: name, directory: join(root, name), port: 0, pool: { baseUrl, apiKey: key, mode: 'manual', live: false, maxRequests: null, timeoutMs: 0 } }); running.push(value); return value;
  };
  const send = async (instance: LocalPoolRunning, label: string, index = 0, child = false) => {
    const session = index % 2 ? '11111111-1111-4111-8111-111111111111' : '22222222-2222-4222-8222-222222222222';
    const response = await fetch('http://127.0.0.1:' + instance.app.server.port + '/v1/messages', { method: 'POST', headers: { 'x-claude-code-prompt-id': randomUUID(), ...(child ? { 'x-claude-code-request-class': 'subagent', 'x-claude-code-agent-id': 'child-' + index, 'x-claude-code-parent-agent-id': 'parent-' + index, 'x-claude-code-agent-type': 'Explore' } : {}) }, body: JSON.stringify(body(label, session, child)) });
    await response.text(); return { id: response.headers.get('x-ccrb-request-id')!, status: response.status };
  };
  try {
    const app = await start('automatic');
    expect(calls).toHaveLength(0); expect(app.status().reserved).toBe(0);
    const labels = ['disconnect', 'http', 'stream', 'incomplete'];
    const results = await Promise.all(labels.map((label, index) => send(app, label, index, index === 2)));
    expect(results.map(item => item.status)).toEqual([502, 429, 200, 200]);
    for (let index = 0; index < results.length; index++) {
      const result = results[index]!, label = labels[index]!;
      const report = await waitReport(join(app.directory, 'incidents/reports', result.id + '.json')); reports.push(report);
      expect(report).toMatchObject({ runId: 'automatic', requestId: result.id });
      expect(report.request.state).toBe(index < 2 ? 'http_error' : index === 2 ? 'stream_error' : 'incomplete');
      expect(report.captures.find(item => item.stage === 'wire_final')!.recordedStatus).toBe('complete');
      if (label === 'disconnect') {
        expect(report.forwarding).toMatchObject({ localStatus: 502, upstreamStatus: null, failureCode: 'UND_ERR_SOCKET' });
        expect(report.transport).toMatchObject({ phase: 'awaiting_headers', bodySentObserved: true });
      } else {
        expect(report.forwarding.upstreamStatus).toBe(index === 1 ? 429 : 200);
        expect(report.correlations).toContainEqual(expect.objectContaining({ header: 'x-oneapi-request-id', values: ['fixture-' + label], state: 'known' }));
      }
      expect(report.correlations).toContainEqual(expect.objectContaining({ header: 'x-client-request-id', values: [calls.find(call => call.label === label)!.clientId], state: 'known' }));
      expect(JSON.stringify(report)).not.toContain(key);
    }
    expect(calls).toHaveLength(4); expect(app.status().reserved).toBe(4);
    expect((await send(app, 'success')).status).toBe(200);
    expect(calls).toHaveLength(5); expect(app.status().reserved).toBe(5);
    await app.close();
    expect(JSON.parse(await readFile(join(app.directory, 'incidents/status.json'), 'utf8')).phase).toBe('stopped');
    expect(await readdir(join(app.directory, 'incidents/reports'))).toHaveLength(4);

    // 同一目标先拒绝连接，再开启假池；恢复必须来自新的独立入站，不能自动重放。
    await new Promise<void>(resolve => fake.close(() => resolve()));
    const refused = await start('before-send');
    const failure = await send(refused, 'refused'); expect(failure.status).toBe(502);
    await new Promise<void>(resolve => fake.listen(address.port, '127.0.0.1', resolve));
    expect((await send(refused, 'recovered')).status).toBe(200);
    await refused.close();
    const beforeSend = await waitReport(join(refused.directory, 'incidents/reports', failure.id + '.json')); reports.push(beforeSend);
    expect(beforeSend.forwarding).toMatchObject({ upstreamStatus: null, failureCode: 'ECONNREFUSED' });
    expect(beforeSend.transport).toEqual({ phase: 'before_send', bodySentObserved: false, connectionBytesWritten: null, connectionBytesRead: null });
    expect(refused.status().reserved).toBe(2); expect(calls).toHaveLength(6);

    await mkdir(join(root, 'output-failure')); await writeFile(join(root, 'output-failure/incidents'), 'private-output-canary');
    const obstructed = await start('output-failure');
    expect((await send(obstructed, 'healthy-without-forensics')).status).toBe(200);
    expect(obstructed.status().reserved).toBe(1); expect(calls).toHaveLength(7);
    await obstructed.close();
    expect(await readFile(join(root, 'output-failure/incidents'), 'utf8')).toBe('private-output-canary');
    passed = true;
  } finally {
    for (const instance of running) await instance.close();
    await new Promise<void>(resolve => fake.close(() => resolve()));
    await mkdir('artifacts', { recursive: true });
    await writeFile('artifacts/local-pool-incidents-proof.json', JSON.stringify({ passed, realModelRequests: 0, syntheticPosts: calls.length, reportCount: reports.length, reports }, null, 2) + '\n', { mode: 0o600 });
    await rm(root, { recursive: true, force: true });
  }
}, 60000);
