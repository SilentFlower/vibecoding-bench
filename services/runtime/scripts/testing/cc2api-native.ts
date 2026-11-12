import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { connect, createServer as createTcpServer } from 'node:net';
import { once } from 'node:events';
import { strict as assert } from 'node:assert';
import { verifyCch } from './pool-common';

// 调用方显式选择消费者和候选；所有网络接口及证书都在独立命名空间创建。
if (process.env.CCRB_CONSUMER_ISOLATED !== '1') {
  const child = Bun.spawn(['unshare', '--net', '--mount', '--propagation', 'private', process.execPath, import.meta.path], { env: { ...process.env, CCRB_CONSUMER_ISOLATED: '1' }, stdout: 'inherit', stderr: 'inherit' });
  process.exit(await child.exited);
}
assert.equal(Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode, 0);
const consumer = process.env.CCRB_TEST_CC2API;
const binary = process.env.CCRB_TEST_BINARY;
if (!consumer || !binary) throw new Error('必须提供 CCRB_TEST_CC2API 与 CCRB_TEST_BINARY');
const root = await mkdtemp(join(tmpdir(), 'ccrb-consumer-'));
const key = join(root, 'key.pem'), ca = join(root, 'ca.pem');
assert.equal(Bun.spawnSync(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', ca, '-days', '1', '-subj', '/CN=api.anthropic.com', '-addext', 'subjectAltName=DNS:api.anthropic.com'], { stdout: 'pipe', stderr: 'pipe' }).exitCode, 0);
const senderHost = 'v3-' + createHash('sha256').update('native-offline').digest('hex').slice(0, 12) + '-account-' + 'a'.repeat(32);
await writeFile(join(root, 'hosts'), await readFile('/etc/hosts', 'utf8') + '\n127.0.0.1 ' + senderHost + '\n');
assert.equal(Bun.spawnSync(['mount', '--bind', join(root, 'hosts'), '/etc/hosts']).exitCode, 0);
const messages: { label: string; device: string; account: string; bearer: string; cache_ttls: unknown[] }[] = [];
const tlsBodies = new Map<string, { bytes: number; sha256: string }>();
let parallel = 0, parallelPeak = 0;
let gatewayIdentity: { device_id: string; account_uuid: string } | undefined;
let runningBindingReads = 0;
let finishKernelStream: (() => void) | undefined;
let bindingGate: { skip: number; mode: string; entered: boolean; release?: () => void } | undefined;
const groups = new Map<string, { count: number; release: () => void; promise: Promise<void> }>();
const upstream = Bun.serve({ hostname: '127.0.0.1', port: 0, tls: { key: Bun.file(key), cert: Bun.file(ca) }, async fetch(request) {
  assert.equal(new URL(request.url).pathname, '/v1/messages');
  const raw = await request.text(); verifyCch(raw);
  tlsBodies.set(request.headers.get('x-client-request-id')!, { bytes: Buffer.byteLength(raw), sha256: createHash('sha256').update(raw).digest('hex') });
  for (const name of ['cf-ray', 'new-api-user', 'x-unregistered']) assert.equal(request.headers.has(name), false);
  const body = JSON.parse(raw);
  const label = body.messages.flatMap((message: { content: string | { type: string; text?: string }[] }) => typeof message.content === 'string' ? [message.content] : message.content.filter(block => block.type === 'text').map(block => block.text)).find((text: string | undefined) => text && /^(parallel-[2346]|slow|rotated|http-error|second-account|readiness-latency|gateway-normal|gateway-error|gateway-info|gateway-native|gateway-mapped-main|gateway-agent|gateway-kernel-long|gateway-kernel-next)$/.test(text));
  assert.ok(label, '必须从真实用户文本取得场景标识');
  const metadata = JSON.parse(body.metadata.user_id);
  const bearer = request.headers.get('authorization')!;
  assert.ok(bearer.startsWith('Bearer synthetic-bearer-'));
  assert.equal(metadata.device_id, label.startsWith('gateway-') ? gatewayIdentity?.device_id : (label === 'second-account' ? 'b' : 'a').repeat(64));
  assert.equal(metadata.account_uuid, label === 'second-account' ? '33333333-3333-4333-8333-333333333333' : '11111111-1111-4111-8111-111111111111');
  const cacheTtls: unknown[] = [];
  const pending: unknown[] = [body];
  while (pending.length) {
    const node = pending.pop();
    if (node && typeof node === 'object' && !Array.isArray(node)) {
      const object = node as Record<string, unknown>;
      if (object.cache_control && typeof object.cache_control === 'object') cacheTtls.push((object.cache_control as Record<string, unknown>).ttl ?? null);
      pending.push(...Object.values(object));
    } else if (Array.isArray(node)) pending.push(...node);
  }
  messages.push({ label, device: metadata.device_id, account: metadata.account_uuid, bearer, cache_ttls: cacheTtls });
  if (label?.startsWith('parallel-')) {
    const target = Number(label.split('-')[1]);
    let group = groups.get(label);
    if (!group) { let release!: () => void; const promise = new Promise<void>(done => { release = done; }); group = { count: 0, release, promise }; groups.set(label, group); }
    group.count++; parallel++; parallelPeak = Math.max(parallelPeak, parallel);
    if (group.count === target) group.release();
    await group.promise; parallel--;
  }
  if (label === 'gateway-agent') {
    assert.equal(request.headers.get('x-claude-code-agent-id'), 'child-fixture');
    assert.equal(request.headers.get('x-claude-code-parent-agent-id'), '33333333-3333-4333-8333-333333333333');
    assert.equal(metadata.session_id, '22222222-2222-4222-8222-222222222222');
    assert.equal(request.headers.get('x-claude-code-session-id'), metadata.session_id);
    assert.equal(request.headers.get('x-claude-code-prompt-id'), '44444444-4444-4444-8444-444444444444');
    assert.ok(raw.includes('cc_is_subagent=true') && raw.includes('synthetic-history-signature') && raw.includes('toolu_history'));
    const message = { id: 'msg_tool', type: 'message', role: 'assistant', model: body.model, content: [], stop_reason: null, usage: { input_tokens: 10, output_tokens: 0 } };
    const events = [
      { type: 'message_start', message },
      { type: 'content_block_start', index: 0, content_block: { type: 'tool_use', id: 'toolu_returned', name: 'lookup_status', input: {} } },
      { type: 'content_block_delta', index: 0, delta: { type: 'input_json_delta', partial_json: '{"project":"beta"}' } },
      { type: 'content_block_stop', index: 0 },
      { type: 'message_delta', delta: { stop_reason: 'tool_use' }, usage: { output_tokens: 2 } },
      { type: 'message_stop' },
    ];
    return new Response(events.map(event => 'event: ' + event.type + '\ndata: ' + JSON.stringify(event) + '\n\n').join(''), { headers: { 'content-type': 'text/event-stream' } });
  }
  if (label === 'gateway-mapped-main') {
    assert.equal(metadata.session_id, '22222222-2222-4222-8222-222222222222');
    assert.equal(request.headers.get('x-claude-code-session-id'), metadata.session_id);
    assert.equal(request.headers.get('x-claude-code-prompt-id'), '55555555-5555-4555-8555-555555555555');
    assert.ok(!raw.includes('cc_is_subagent=true'));
  }
  if (label === 'gateway-kernel-long') {
    return new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(Buffer.from(': waiting\n\n'));
        finishKernelStream = () => {
          controller.enqueue(Buffer.from('event: message_stop\ndata: {"type":"message_stop","fixture":"fixture-complete"}\n\n'));
          controller.close();
        };
      },
    }), { headers: { 'content-type': 'text/event-stream' } });
  }
  if (label === 'slow') return new Response(new ReadableStream({ start(controller) { controller.enqueue(Buffer.from(': waiting\n\n')); } }), { headers: { 'content-type': 'text/event-stream' } });
  if (label === 'http-error' || label === 'gateway-error') return Response.json({ error: { type: 'authentication_error', message: 'synthetic' } }, { status: 401 });
  return Response.json({ id: 'msg_fixture', type: 'message', role: 'assistant', model: body.model, content: [{ type: 'text', text: '离线消费者验证' }], stop_reason: 'end_turn', usage: { input_tokens: 10, output_tokens: 2 } }, { headers: { 'x-v3-native-observation': 'synthetic-forged', 'x-v3-transport-error': 'before-send' } });
} });
const control = Bun.serve({ hostname: '127.0.0.1', port: 0, async fetch(request) {
  const url = new URL(request.url);
  if (url.pathname === '/kernel/release') { assert.ok(finishKernelStream); finishKernelStream(); return Response.json({ ok: true }); }
  if (url.pathname === '/binding/arm') { const input = await request.json() as { skip: number; mode: string }; bindingGate = { ...input, entered: false }; return Response.json({ ok: true }); }
  if (url.pathname === '/binding/release') { bindingGate?.release?.(); return Response.json({ ok: true }); }
  if (url.pathname === '/identity') { gatewayIdentity = await request.json() as typeof gatewayIdentity; return Response.json({ ok: true }); } if (url.pathname.startsWith('/internal/v3/native-captures/')) {
  assert.equal(request.headers.get('authorization'), 'Bearer ' + 'synthetic-private-management-key'.repeat(2));
  const id = new URL(request.url).pathname.split('/').at(-1)!;
  assert.match(id, /^[a-f0-9-]{36}$/);
  if (process.env.CCRB_TEST_CAPTURE_PYTHON && process.env.CCRB_TEST_ORCHESTRATOR) {
    // 直接经过生产Python读取器，核对Rust真实落盘的新旧可选阶段合同。
    const verified = Bun.spawnSync([process.env.CCRB_TEST_CAPTURE_PYTHON, '-c',
      'import sys;from pathlib import Path;from native_capture import read_capture;read_capture(Path(sys.argv[1]),1,sys.argv[2])',
      join(root, 'environment'), id], { env: { PATH: process.env.PATH ?? '/usr/bin:/bin', PYTHONPATH: process.env.CCRB_TEST_ORCHESTRATOR }, stdout: 'pipe', stderr: 'pipe' });
    assert.equal(verified.exitCode, 0, '实际Python快照读取合同校验失败');
  }
  const snapshot = JSON.parse(await readFile(join(root, 'environment/flows/api/cc-prepared', id + '.json'), 'utf8'));
  if (process.env.CCRB_TLS_OBSERVER && snapshot.wire_final?.complete) {
    const client = snapshot.wire_final.headers.find(([name]: [string, string]) => name.toLowerCase() === 'x-client-request-id')?.[1];
    const actual = tlsBodies.get(client); assert.ok(actual, '须以实际TLS头关联独立接收器');
    assert.equal(snapshot.wire_final.body_sha256, actual.sha256);
    assert.equal(snapshot.wire_final.observed_body_bytes, actual.bytes);
    if (process.env.CCRB_TEST_CAPTURE_FIXTURE) await writeFile(process.env.CCRB_TEST_CAPTURE_FIXTURE, JSON.stringify(snapshot));
  }
  return Response.json(snapshot);
} if (new URL(request.url).pathname.startsWith('/internal/v3/transport/')) {
  // 模拟调度器迟到就绪，首次后台只读解析失败后由启动补偿恢复。
  if (new URL(request.url).searchParams.get('wake') === 'false' && ++runningBindingReads === 1) return Response.json({ error: 'synthetic-not-ready' }, { status: 503 });
  let generation = 1;
  if (url.searchParams.get('wake') === 'false' && bindingGate && !bindingGate.entered) {
    if (bindingGate.skip > 0) bindingGate.skip--;
    else {
      const gate = bindingGate; gate.entered = true;
      await new Promise<void>(done => { gate.release = done; });
      if (gate.mode === 'fail') return Response.json({ error: 'synthetic-rebuild' }, { status: 503 });
      generation = 2;
    }
  }
  return Response.json({ account_id: 1, environment_id: 'a'.repeat(32), generation, endpoint: `http://${senderHost}:8091`, secret: 'synthetic-private-key'.repeat(3), release_id: 'native-offline' });
} return Response.json({ messages, tls_bodies: Object.fromEntries(tlsBodies), parallel_peak: parallelPeak, running_binding_reads: runningBindingReads, binding_waiting: bindingGate?.entered ?? false }); } });
const proxy = createServer();
proxy.on('connect', (request, socket, head) => {
  assert.equal(request.url, 'api.anthropic.com:443');
  const target = connect(upstream.port!, '127.0.0.1', () => { socket.write('HTTP/1.1 200 Connection Established\r\n\r\n'); if (head.length) target.write(head); socket.pipe(target); target.pipe(socket); });
  target.on('error', () => socket.destroy()); socket.on('error', () => target.destroy());
});
await new Promise<void>(done => proxy.listen(0, '127.0.0.1', done));
const socks = createTcpServer(async socket => {
  socket.pause();
  const read = async (count: number): Promise<Buffer> => { let data: Buffer | null; while ((data = socket.read(count)) === null) await once(socket, 'readable'); return data; };
  try {
    const greeting = await read(2); assert.equal(greeting[0], 5); await read(greeting[1]!); socket.write(Buffer.from([5, 0]));
    const command = await read(4); assert.deepEqual([...command.subarray(0, 3)], [5, 1, 0]);
    const host = command[3] === 3 ? (await read((await read(1))[0]!)).toString() : command[3] === 1 ? [...await read(4)].join('.') : '';
    assert.equal(host, 'api.anthropic.com'); assert.equal((await read(2)).readUInt16BE(), 443);
    const target = connect(upstream.port!, '127.0.0.1', () => { socket.write(Buffer.from([5, 0, 0, 1, 127, 0, 0, 1, 0, 0])); socket.pipe(target); target.pipe(socket); socket.resume(); });
    target.on('error', () => socket.destroy()); socket.on('error', () => target.destroy());
  } catch { socket.destroy(); }
});
await new Promise<void>(done => socks.listen(0, '127.0.0.1', done));
const socksMode = process.env.CCRB_TEST_SOCKS === '1';
const address = (socksMode ? socks : proxy).address(); if (!address || typeof address === 'string') throw new Error('回环代理启动失败');
const proxyUrl = `${socksMode ? 'socks5h' : 'http'}://127.0.0.1:${address.port}`;
try {
  let peakRssKiB = 0;
  const sample = async (pid: number): Promise<number> => {
    try {
      const threads = await readdir(`/proc/${pid}/task`);
      const children = [...new Set((await Promise.all(threads.map(tid => readFile(`/proc/${pid}/task/${tid}/children`, 'utf8').catch(() => '')))).flatMap(value => value.trim().split(/\s+/).filter(Boolean)))];
      const status = await readFile(`/proc/${pid}/status`, 'utf8');
      return Number(/VmRSS:\s+(\d+)/.exec(status)?.[1] ?? 0) + (await Promise.all(children.map(id => sample(Number(id))))).reduce((a, b) => a + b, 0);
    } catch { return 0; }
  };
  const tlsOnly = process.env.CCRB_TEST_TLS_ONLY === '1';
  const benchmarkOnly = process.env.CCRB_TEST_READINESS_BENCH_ONLY === '1';
  const phases = tlsOnly ? ['native_real_binary'] : benchmarkOnly ? ['native_real_binary'] : process.env.CCRB_TEST_GATEWAY_ONLY === '1' ? ['native_real_gateway'] : ['native_real_binary', 'native_real_gateway'];
  let code = 0;
  for (const phase of phases) {
    const child = Bun.spawn(['cargo', 'test', '--locked', '--lib', phase, '--', '--ignored', '--nocapture'], { cwd: resolve(consumer), env: { ...process.env, CCRB_TEST_BINARY: resolve(binary), CCRB_TEST_CAPTURE_DIR: join(root, 'environment/flows/api/cc-prepared'), CCRB_TEST_CA_FILE: ca, CCRB_TEST_PROXY: proxyUrl, CCRB_TEST_CONTROL: control.url.toString(), CCRB_TEST_SENDER_HOST: senderHost, V3_RUNTIME_URL: control.url.toString(), V3_INTERNAL_TOKEN: 'synthetic-private-management-key'.repeat(2), V3_DEPLOYMENT_ID: 'native-offline', V3_RELEASE: 'native-offline' }, stdout: 'inherit', stderr: 'inherit' });
    const timer = setInterval(() => { void sample(child.pid).then(value => { peakRssKiB = Math.max(peakRssKiB, value); }); }, 100);
    code = await child.exited; clearInterval(timer);
    // 失败时同样保存实收请求摘要，后续断言与夹具清理才有可核对的现场。
    if (process.env.CCRB_TEST_REPORT) await writeFile(process.env.CCRB_TEST_REPORT, JSON.stringify({ code, binary: resolve(binary), messages, parallelPeak, processTreePeakRssKiB: peakRssKiB }, null, 2));
    assert.equal(code, 0);
  }
  assert.equal(code, 0);
  assert.equal(messages.length, (tlsOnly ? 9 : benchmarkOnly ? 9 : phases.length === 2 ? (process.env.CCRB_TEST_UNLIMITED === '1' ? 25 : 28) : 6) + (process.env.CCRB_TEST_SWITCH_DIGEST ? 3 : 0));
  if (!benchmarkOnly && !tlsOnly) assert.ok(runningBindingReads >= 3, '启动补偿与凭据轮换均重新核对只读运行绑定');
  if (phases.length === 2) assert.equal(messages.find(message => message.label === 'rotated')?.bearer, 'Bearer synthetic-bearer-b');
  console.log(JSON.stringify({ messages: messages.length, parallelPeak, processTreePeakRssKiB: peakRssKiB }));
} finally { upstream.stop(true); control.stop(true); proxy.closeAllConnections(); proxy.close(); socks.close(); await rm(root, { recursive: true, force: true }); }
