import { expect, test } from 'bun:test';
import { mkdir, mkdtemp, readFile, readlink, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { startLocalPool, type LocalPoolRunning } from '../../scripts/local-pool';
import { verifyCch } from '../../scripts/testing/pool-common';
import { readNativeClassification } from '../../src/shared/native-classifier';
import { isObject } from '../../src/shared/errors';
import type { HeaderPair, JsonObject, MessageBody, RequestDetail } from '../../src/shared/contracts';

type Label = 'A' | 'B';
/** 原始入站仅留测试内存，日志匹配使用原始摘要。 */
interface Ingress { label: Label; phase: string; raw: string; sha: string; body: MessageBody; headers: HeaderPair[]; child: boolean; aborted: boolean }
/** 假池实收与取消观测，不保存真实凭据。 */
interface Call { label: Label; phase: string; body: MessageBody; child: boolean; agentId: string | null }
/** 由实际发送触发的可控闸门，避免以随机时长制造竞争。 */
interface Gate {
  label: Label;
  child: boolean;
  call: Call | null;
  ready: boolean;
  canceled: boolean;
  /** 放行当前合成响应。@return 响应已结束或此前已取消。 */
  release(): void;
}
/** 一个实际终端客户端及其安全回执。 */
interface Client {
  child: Bun.Subprocess<'pipe', 'pipe', 'pipe'>;
  frames: JsonObject[];
  markers: Set<string>;
  read: Promise<void>;
  stderr: Promise<string>;
  /** 向测试终端发送指令。@param command 合成控制对象。@return 指令已写入。 */
  send(command: JsonObject): Promise<void>;
}

/** 有界等待实际证据，使用单调时间而非墙钟。
 * @param condition 同步或异步证据检查。
 * @param message 缺失证据时的受控说明。
 * @return 条件成立。
 */
async function until(condition: () => boolean | Promise<boolean>, message: string): Promise<void> {
  const start = performance.now();
  while (!(await condition())) { if (performance.now() - start > 20000) throw new Error(message); await Bun.sleep(20); }
}

/** 计算原文摘要，不使用脱敏预览恢复原文。@param raw 完整正文。@return 摘要。 */
function sha(raw: string): string { return createHash('sha256').update(raw).digest('hex'); }

/** 只提取实际子代理回传框架，不能把 Agent 调用提示当成完成证据。
 * @param value 消息或工具结果。
 * @return 真实报告文本。
 */
function reports(value: unknown): string[] {
  if (typeof value === 'string') return value.includes('[Subagent hand-back]') ? [value] : [];
  if (Array.isArray(value)) return value.flatMap(reports);
  if (isObject(value)) return [...(value.type === 'text' ? reports(value.text) : []), ...reports(value.content)];
  return [];
}

/** 生成原生 Messages JSON/SSE，工具执行仍交实际客户端。
 * @param body 实际请求。
 * @param blocks 合成回复。
 * @return 完整模型响应。
 */
function answer(body: MessageBody, blocks: JsonObject[]): Response {
  const stop = blocks.some(block => block.type === 'tool_use') ? 'tool_use' : 'end_turn';
  const message = { id: 'msg_isolation_' + randomUUID(), type: 'message', role: 'assistant', model: 'deepseek-flash', content: blocks, stop_reason: stop, stop_sequence: null, usage: { input_tokens: 100, output_tokens: 20 } };
  if (!body.stream) return Response.json(message);
  const events: JsonObject[] = [{ type: 'message_start', message: { ...message, content: [], stop_reason: null } }];
  for (const [index, block] of blocks.entries()) {
    events.push({ type: 'content_block_start', index, content_block: block.type === 'tool_use' ? { ...block, input: {} } : { type: 'text', text: '' } });
    events.push({ type: 'content_block_delta', index, delta: block.type === 'tool_use' ? { type: 'input_json_delta', partial_json: JSON.stringify(block.input) } : { type: 'text_delta', text: block.text } });
    events.push({ type: 'content_block_stop', index });
  }
  events.push({ type: 'message_delta', delta: { stop_reason: stop }, usage: { output_tokens: 20 } }, { type: 'message_stop' });
  return new Response(events.map(event => 'event: ' + event.type + '\ndata: ' + JSON.stringify(event) + '\n\n').join(''), { headers: { 'content-type': 'text/event-stream' } });
}

test('双实际终端各三个子代理，取消及异常退出不污染另一会话', async () => {
  if (await readlink('/proc/self/ns/net') === await readlink('/proc/1/ns/net') || Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode !== 0) throw new Error('实际会话隔离验收必须在独立网络');
  if ((await readFile('/proc/net/dev', 'utf8')).split('\n').slice(2).filter(line => line.includes(':')).map(line => line.split(':')[0]!.trim()).join(',') !== 'lo') throw new Error('会话隔离验收只允许回环接口');
  const root = await mkdtemp(join(tmpdir(), 'ccrb-session-isolation-')), home = join(root, 'home'), config = join(home, 'config'), cwd = join(root, 'work');
  await mkdir(config, { recursive: true, mode: 0o700 }); await mkdir(cwd);
  await writeFile(join(config, '.claude.json'), JSON.stringify({ userID: 'a'.repeat(64), hasCompletedOnboarding: true, theme: 'dark', projects: { [cwd]: { hasTrustDialogAccepted: true, hasCompletedProjectOnboarding: true } } }), { mode: 0o600 });
  const binary = process.env.CCRB_TEST_ORIGINAL_BINARY!, sessions = { A: randomUUID(), B: randomUUID() }, incoming: Ingress[] = [], calls: Call[] = [], clients: Client[] = [];
  const launched = new Set<Label>(), receipts = { A: new Set<number>(), B: new Set<number>() }, scenarios: JsonObject[] = [], gates: Gate[] = [];
  let phase = 'initial', activeGate: Gate | null = null, running: LocalPoolRunning | undefined, passed = false, verifiedWireSamples = 0;
  const subagents: JsonObject[] = [];

  /** 只从实际原生 metadata 识别登记会话。@param body 实际正文。@return 合成窗口。 */
  function labelOf(body: MessageBody): Label {
    if (!isObject(body.metadata) || typeof body.metadata.user_id !== 'string') throw new Error('实际请求缺少会话');
    const session = JSON.parse(body.metadata.user_id).session_id;
    if (session === sessions.A) return 'A'; if (session === sessions.B) return 'B'; throw new Error('请求不属于登记会话');
  }

  /** 激活下一次指定业务发送的闸门。@param label 窗口。@param child 是否子代理。@return 闸门。 */
  function arm(label: Label, child: boolean): Gate {
    const gate: Gate = { label, child, call: null, ready: false, canceled: false, release() {} };
    activeGate = gate; gates.push(gate); return gate;
  }

  const pool = Bun.serve({ hostname: '127.0.0.1', port: 0, idleTimeout: 0, async fetch(request) {
    const body = await request.json() as MessageBody, label = labelOf(body), child = body.tools?.some(tool => tool.name === 'SubagentHandback') ?? false;
    const call: Call = { label, phase, body, child, agentId: request.headers.get('x-claude-code-agent-id') }; calls.push(call);
    expect(JSON.stringify(body.messages)).not.toContain('ISO_' + (label === 'A' ? 'B' : 'A') + '_');
    const classification = readNativeClassification(body);
    if (classification) return answer(body, [{ type: 'text', text: classification.purpose === 'auto_permission_classifier' ? '<block>no</block>' : '本机会话隔离' }]);
    let blocks: JsonObject[];
    if (child) {
      const marker = [...JSON.stringify(body.messages).matchAll(/ISO_[AB]_CHILD_[123]/g)].at(-1)?.[0];
      if (!marker) throw new Error('实际子代理缺少独立标记');
      blocks = [{ type: 'tool_use', id: 'toolu_handback_' + randomUUID(), name: 'SubagentHandback', input: { message: marker } }];
    } else if (body.tools?.some(tool => tool.name === 'Agent')) {
      if (!launched.has(label)) {
        launched.add(label);
        await until(async () => {
          if (!running) return false; await running.app.store.flush();
          return (['A', 'B'] as const).every(key => running!.app.store.list().rows.some(row => row.sessionId === sessions[key] && row.requestClass === 'main'));
        }, '两个实际主会话未同时进入桥接');
        blocks = [1, 2, 3].map(index => ({ type: 'tool_use', id: 'toolu_launch_' + label + '_' + index, name: 'Agent', input: { description: '窗口' + label + '的第' + index + '个隔离子代理', prompt: '通过 SubagentHandback 回传 ISO_' + label + '_CHILD_' + index, subagent_type: 'Explore' } }));
      } else {
        const frames = reports(body.messages);
        for (const index of [1, 2, 3]) if (frames.some(frame => frame.includes('\n  ISO_' + label + '_CHILD_' + index + '\n'))) receipts[label].add(index);
        const command = [...JSON.stringify(body.messages).matchAll(new RegExp('ISO_' + label + '_PROMPT_([A-Z0-9]+)', 'g'))].at(-1)?.[1] ?? 'INITIAL';
        blocks = [{ type: 'text', text: command === 'INITIAL' ? 'ISO_' + label + (receipts[label].size === 3 ? '_ALL_THREE_DONE' : '_WAITING') : 'ISO_' + label + '_' + command + '_DONE' }];
      }
    } else blocks = [{ type: 'text', text: '本机辅助调用完成' }];
    const gate = activeGate;
    // 提前阻塞子代理会占住串行池，使其余 Agent 的权限辅助调用无法完成。
    // 第六个独立子代理已实际发送时才阻塞，此时两个客户端都确实创建了三个子代理。
    const initialReady = phase !== 'initial' || new Set(calls.filter(value => value.child).map(value => value.agentId)).size === 6;
    if (gate && phase === 'initial' && child && initialReady && !gate.call) gate.label = label;
    if (gate && initialReady && !gate.call && gate.label === label && gate.child === child) {
      gate.call = call;
      if (!body.stream) throw new Error('故障闸门要求实际流式业务');
      const text = await answer(body, blocks).text(), boundary = text.indexOf('event: content_block_delta');
      const bytes = new TextEncoder();
      return new Response(new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(bytes.encode(text.slice(0, boundary))); gate.ready = true;
          gate.release = () => { if (!gate.canceled) { try { controller.enqueue(bytes.encode(text.slice(boundary))); controller.close(); } catch {} } };
          request.signal.addEventListener('abort', () => { gate.canceled = true; }, { once: true });
        },
        cancel() { gate.canceled = true; },
      }), { headers: { 'content-type': 'text/event-stream' } });
    }
    return answer(body, blocks);
  } });

  running = await startLocalPool({ binary, pool: { baseUrl: 'http://127.0.0.1:' + pool.port, apiKey: 'isolation-synthetic-pool-key', live: false, mode: 'manual', maxRequests: null, timeoutMs: 0 }, runId: 'actual-session-isolation', directory: join(root, 'run'), port: 0 });
  const recorder = Bun.serve({ hostname: '127.0.0.1', port: 0, idleTimeout: 0, async fetch(request) {
    const raw = await request.text(), body = JSON.parse(raw) as MessageBody, path = new URL(request.url), abort = new AbortController();
    const record: Ingress = { raw, sha: sha(raw), body, label: labelOf(body), phase, headers: [...request.headers], child: request.headers.has('x-claude-code-agent-id'), aborted: false }; incoming.push(record);
    // 录制层也要传递断开；否则测到的是录制器持有连接，而非实际 CLI 的取消。
    const cancel = (): void => { record.aborted = true; abort.abort(); }; request.signal.addEventListener('abort', cancel, { once: true });
    try {
      const response = await fetch('http://127.0.0.1:' + running!.app.server.port + path.pathname + path.search, { method: request.method, headers: request.headers, body: raw, signal: abort.signal });
      const reader = response.body!.getReader();
      return new Response(new ReadableStream<Uint8Array>({
        async pull(controller) {
          try { const next = await reader.read(); if (next.done) { request.signal.removeEventListener('abort', cancel); controller.close(); } else controller.enqueue(next.value); }
          catch { controller.error(new Error('录制转发已中止')); }
        },
        async cancel() { cancel(); request.signal.removeEventListener('abort', cancel); await reader.cancel().catch(() => {}); },
      }), { status: response.status, headers: response.headers });
    } catch (error) { request.signal.removeEventListener('abort', cancel); if (abort.signal.aborted) return new Response(null, { status: 499 }); throw error; }
  } });

  /** 启动真正的交互客户端，共享配置与目录但保持独立 session。
   * @param label 窗口标记。
   * @param resume 是否恢复此前窗口。
   * @return 客户端及持续安全回执读取器。
   */
  function client(label: Label, resume = false): Client {
    const child = Bun.spawn(['python3', resolve('tests/local-pool/isolation-client.py'), label, binary, '--model', 'claude-sonnet-4-6', resume ? '--resume' : '--session-id', sessions[label], '--tools', 'Agent', '--allowedTools', 'Agent', '--', 'ISO_' + label + '_PROMPT_' + (resume ? 'RESTART' : 'INITIAL')], { cwd, env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: home, CLAUDE_CONFIG_DIR: config, LANG: 'C.UTF-8', TERM: 'xterm-256color', ANTHROPIC_BASE_URL: 'http://127.0.0.1:' + recorder.port, ANTHROPIC_AUTH_TOKEN: 'isolation-synthetic-client-token', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1', DISABLE_AUTOUPDATER: '1', DISABLE_AUTO_COMPACT: '1', CLAUDE_CODE_MAX_OUTPUT_TOKENS: '128', MAX_THINKING_TOKENS: '0' }, stdin: 'pipe', stdout: 'pipe', stderr: 'pipe' });
    const frames: JsonObject[] = [], markers = new Set<string>();
    const read = (async () => {
      const reader = child.stdout.getReader(), decoder = new TextDecoder(); let buffer = '';
      try { while (true) { const next = await reader.read(); if (next.done) break; buffer += decoder.decode(next.value, { stream: true }); let index: number; while ((index = buffer.indexOf('\n')) >= 0) { const frame: JsonObject = JSON.parse(buffer.slice(0, index)); buffer = buffer.slice(index + 1); frames.push(frame); if (frame.type === 'marker' && typeof frame.value === 'string') markers.add(frame.value); } } } finally { reader.releaseLock(); }
    })();
    const result: Client = { child, frames, markers, read, stderr: new Response(child.stderr).text(), async send(command) { child.stdin.write(JSON.stringify(command) + '\n'); await child.stdin.flush(); } };
    clients.push(result); return result;
  }

  /** 按原始入站 SHA 找到请求，不能通过到达顺序猜归属。
   * @param record 已观测入站。
   * @return 其唯一日志详情，尚未落盘时为 null。
   */
  async function detail(record: Ingress): Promise<RequestDetail | null> {
    await running!.app.store.flush();
    for (const row of running!.app.store.list({ sessionId: sessions[record.label], limit: 100 }).rows) {
      const value = await running!.app.store.detail(row.id);
      if (value?.captures.some(capture => capture.stage === 'ingress' && capture.sha256 === record.sha)) return value;
    }
    return null;
  }

  /** 提交下一轮输入，成功标记只由假池回复产生。@param value 实际终端。@param label 窗口。@param command 轮次。@return 输入已送达。 */
  async function prompt(value: Client, label: Label, command: string): Promise<void> { await value.send({ type: 'prompt', text: 'ISO_' + label + '_PROMPT_' + command }); }

  /** 等待指定窗口的本轮主请求排队。@param label 窗口。@return 入站及其日志。 */
  async function queued(label: Label): Promise<{ record: Ingress; value: RequestDetail }> {
    let found: { record: Ingress; value: RequestDetail } | undefined;
    await until(async () => {
      const record = incoming.find(value => value.label === label && value.phase === phase && !value.child && value.body.tools?.some(tool => tool.name === 'Agent'));
      if (!record) return false; const value = await detail(record); if (value?.request.state !== 'queued') return false; found = { record, value }; return true;
    }, '实际客户端未进入预期排队阶段：' + phase);
    return found!;
  }

  try {
    const first = arm('A', true), initialClients = { A: client('A'), B: client('B') };
    await until(() => first.ready && (['A', 'B'] as const).every(label => new Set(incoming.filter(value => value.label === label && value.child).map(value => new Headers(value.headers).get('x-claude-code-agent-id'))).size === 3), '未观察到两个窗口各三个实际子代理及活动闸门');
    const victim = first.label, survivor: Label = victim === 'A' ? 'B' : 'A';
    let a = initialClients[victim]; const b = initialClients[survivor];
    await a.send({ type: 'kill' });
    await until(() => first.canceled && b.markers.has('ISO_' + survivor + '_ALL_THREE_DONE'), '子代理期间异常退出未传播或另一会话未完成');
    await until(() => a.frames.some(frame => frame.type === 'exit' && frame.code === -9), '未观察到真实客户端异常退出');
    activeGate = null; phase = 'after_exit'; await prompt(b, survivor, 'FIRSTSURVIVE');
    await until(() => b.markers.has('ISO_' + survivor + '_FIRSTSURVIVE_DONE'), '子代理退出后另一窗口未能继续新一轮');
    scenarios.push({ scenario: 'active_subagent_exit', canceledObserved: first.canceled, survivor, survivorCompleted: true });
    phase = 'restart'; a = client(victim, true); await until(() => a.markers.has('ISO_' + victim + '_RESTART_DONE'), '异常退出后独立恢复未成功');

    phase = 'queue_cancel'; const second = arm(victim, false); await prompt(a, victim, 'HOLD2');
    await until(() => second.ready, '主请求未进入活动闸门'); await prompt(b, survivor, 'QUEUED2'); const canceledQueue = await queued(survivor);
    await b.send({ type: 'cancel' }); await until(() => canceledQueue.record.aborted, '实际排队客户端未断开自己的请求');
    expect(second.canceled).toBe(false); second.release(); activeGate = null;
    // 日志终态在串行槽位轮到该请求后收口；先验证断开，再验证不会进入模型。
    await until(async () => (await detail(canceledQueue.record))?.request.state === 'canceled', '排队取消未完成');
    await until(() => a.markers.has('ISO_' + victim + '_HOLD2_DONE'), '排队取消影响了另一活动会话');
    scenarios.push({ scenario: 'queued_cancel', requestId: canceledQueue.value.request.id, survivor: victim, survivorCompleted: true });
    phase = 'after_queue_cancel'; await prompt(b, survivor, 'AFTERQUEUE'); await until(() => b.markers.has('ISO_' + survivor + '_AFTERQUEUE_DONE'), '排队取消后的窗口未能继续');

    phase = 'active_cancel'; const third = arm(victim, false); await prompt(a, victim, 'HOLD3'); await until(() => third.ready, '活动取消场景未进入闸门');
    await prompt(b, survivor, 'SURVIVE3'); const survivorQueue = await queued(survivor);
    await a.send({ type: 'cancel' }); await until(() => third.canceled && b.markers.has('ISO_' + survivor + '_SURVIVE3_DONE'), '活动取消影响了排队会话');
    scenarios.push({ scenario: 'active_cancel', canceledObserved: third.canceled, survivorRequestId: survivorQueue.value.request.id, survivor, survivorCompleted: true }); activeGate = null;
    phase = 'after_active_cancel'; await prompt(a, victim, 'AFTERACTIVE'); await until(() => a.markers.has('ISO_' + victim + '_AFTERACTIVE_DONE'), '活动取消后原窗口未能继续');

    phase = 'queue_exit'; const fourth = arm(victim, false); await prompt(a, victim, 'HOLD4'); await until(() => fourth.ready, '排队退出场景未进入活动闸门');
    await prompt(b, survivor, 'QUEUED4'); const exitedQueue = await queued(survivor); await b.send({ type: 'kill' });
    await until(() => exitedQueue.record.aborted, '排队窗口退出未断开自己的请求');
    expect(fourth.canceled).toBe(false); fourth.release(); activeGate = null;
    await until(async () => (await detail(exitedQueue.record))?.request.state === 'canceled', '排队窗口退出未取消自己的作业');
    await until(() => a.markers.has('ISO_' + victim + '_HOLD4_DONE'), '排队窗口退出影响了活动会话');
    scenarios.push({ scenario: 'queued_exit', requestId: exitedQueue.value.request.id, survivor: victim, survivorCompleted: true });
    phase = 'final'; await prompt(a, victim, 'FINAL'); await until(() => a.markers.has('ISO_' + victim + '_FINAL_DONE'), '故障场景后存活会话未能继续');
    await until(async () => { await running!.app.store.flush(); return running!.app.store.list({ limit: 100 }).rows.every(row => row.state !== 'running' && row.state !== 'queued'); }, '故障场景仍有未收口请求');

    const details = (await Promise.all(running.app.store.list({ limit: 100 }).rows.map(row => running!.app.store.detail(row.id)))).filter((value): value is RequestDetail => value !== null);
    for (const value of details) {
      const ingress = value.captures.find(capture => capture.stage === 'ingress'), input = incoming.find(record => record.sha === ingress?.sha256);
      expect(input).toBeDefined(); expect(value.context?.sessionId).toBe(sessions[input!.label]);
      expect(JSON.stringify(input!.body.messages)).not.toContain('ISO_' + (input!.label === 'A' ? 'B' : 'A') + '_');
      const wire = value.captures.find(capture => capture.stage === 'wire_final');
      const matched = calls.filter(call => call.label === input!.label && sha(JSON.stringify({ ...call.body, model: input!.body.model })) === wire?.sha256);
      expect(matched.length).toBeLessThanOrEqual(1);
      if (wire?.status === 'complete') {
        expect(matched).toHaveLength(1); const actual = JSON.stringify({ ...matched[0]!.body, model: input!.body.model }); verifyCch(actual); verifiedWireSamples++;
        expect(matched[0]!.body.messages).toEqual(input!.body.messages); expect(matched[0]!.body.tools).toEqual(input!.body.tools);
        expect(new Headers(wire.headers).get('x-claude-code-session-id')).toBe(sessions[input!.label]);
        expect(new Headers(wire.headers).get('x-claude-code-agent-id')).toBe(new Headers(input!.headers).get('x-claude-code-agent-id'));
      }
      if (value.context?.agentKind === 'subagent') {
        subagents.push({ requestId: value.request.id, context: value.context, association: value.agentAssociation });
        expect(value.context.agentId).toBe(new Headers(input!.headers).get('x-claude-code-agent-id') ?? undefined);
        const association = value.agentAssociation!; expect(association.state).not.toBe('conflict');
        if (association.state === 'linked' || association.state === 'explicit') {
          expect(association.parentAgentId).toBe(sessions[input!.label]); expect(association.agentType).toBe('Explore');
          for (const evidence of association.evidence) expect(details.find(item => item.request.id === evidence.requestId)?.context?.sessionId).toBe(sessions[input!.label]);
        } else { expect(association.parentAgentId).toBeNull(); expect(association.parentSource).toBe('unknown'); }
      }
    }
    for (const label of ['A', 'B'] as const) expect(new Set(details.filter(value => value.context?.sessionId === sessions[label] && value.context.agentKind === 'subagent').map(value => value.context?.agentId)).size).toBe(3);
    const ledger = await Bun.file(join(running.directory, 'ledger.json')).json();
    expect(ledger.reservations.filter((row: JsonObject) => row.attempted === true)).toHaveLength(calls.length);
    expect(new Set(ledger.reservations.map((row: JsonObject) => row.requestId)).size).toBe(ledger.reservations.length);
    for (const record of [canceledQueue, exitedQueue]) expect(ledger.reservations.some((row: JsonObject) => row.requestId === record.value.request.id)).toBe(false);
    expect(verifiedWireSamples).toBe(calls.length);
    passed = true;
  } finally {
    for (const gate of gates) gate.release();
    for (const value of clients) { if (value.child.exitCode === null) await value.send({ type: 'close' }).catch(() => {}); }
    for (const value of clients) {
      const exited = await Promise.race([value.child.exited.then(() => true), Bun.sleep(3000).then(() => false)]);
      if (!exited) { value.child.kill('SIGTERM'); await value.child.exited; }
      await value.read;
    }
    const terminalFrames = clients.flatMap(value => value.frames), diagnostics = await Promise.all(clients.map(value => value.stderr));
    await running.app.store.flush();
    const requestStates = running.app.store.list({ limit: 100 }).rows.map(row => ({ id: row.id, sessionId: row.sessionId, state: row.state, requestClass: row.requestClass }));
    await recorder.stop(true); await running.close(); await pool.stop(true);
    await mkdir('artifacts', { recursive: true });
    const terminalsValid = terminalFrames.filter(frame => frame.type === 'exit').length === clients.length && terminalFrames.filter(frame => frame.type === 'exit').every(frame => frame.foreignMarkerSeen === false);
    const proof = { passed: passed && terminalsValid && diagnostics.every(value => value === ''), isolated: true, realUpstreamRequests: 0, sharedHome: true, sharedConfig: true, sharedCwd: true, sessions, phase, incoming: incoming.length, modelCalls: calls.length, verifiedWireSamples, subagents, scenarios, requestStates, gates: gates.map(gate => ({ label: gate.label, child: gate.child, ready: gate.ready, canceled: gate.canceled, sent: gate.call !== null })), terminals: terminalFrames, diagnosticsEmpty: diagnostics.every(value => value === '') };
    await writeFile('artifacts/local-pool-session-isolation-' + randomUUID() + '.json', JSON.stringify(proof, null, 2) + '\n', { mode: 0o600 });
    await writeFile('artifacts/local-pool-session-isolation-proof.json', JSON.stringify(proof, null, 2) + '\n', { mode: 0o600 });
    await rm(root, { recursive: true, force: true });
    expect(diagnostics.every(value => value === '')).toBe(true);
    expect(terminalsValid).toBe(true);
  }
}, 150000);
