import type { JsonObject } from '../../src/shared/contracts';
import { POOL_MODEL } from './pool-common';

/** 假池只记录内存证据，不保存鉴权值。 */
export interface FixtureCall { path: string; body: JsonObject; authenticated: boolean; extension: string | null }
/** 无外网假池的控制和观测接口。 */
export interface PoolFixture {
  baseUrl: string; calls: FixtureCall[]; canceled: number; redirected: number;
  /** 选择下一次单请求的响应。 @param fixture 夹具名称。 @return 无。 */
  select(fixture: string): void;
  /** 终止本机夹具。 @return 连接均已关闭。 */
  close(): Promise<void>;
}

/** 运行 Messages 假池，必须由外层网络命名空间隔离。 @param apiKey 合成池 Key。 @param toolFile 工具续轮读取的隔离夹具文件。 @return 本机服务及观测。 */
export function startPoolFixture(apiKey: string, toolFile?: string): PoolFixture {
  let fixture = 'json', canceled = 0, redirected = 0;
  const calls: FixtureCall[] = [];
  const server = Bun.serve({
    hostname: '127.0.0.1', port: 0, idleTimeout: 120,
    async fetch(request) {
      const url = new URL(request.url);
      if (url.pathname === '/redirect-target') { redirected++; return new Response('不应到达', { status: 500 }); }
      if (request.method !== 'POST' || url.pathname !== '/v1/messages') return new Response('不支持', { status: 400 });
      const body = await request.json() as JsonObject;
      calls.push({ path: url.pathname + url.search, body, authenticated: request.headers.get('x-api-key') === apiKey && !request.headers.has('authorization'), extension: request.headers.get('x-future-pool-test') });
      const chosen = fixture;
      const delay = (ms: number): Promise<void> => new Promise(resolve => {
        if (request.signal.aborted) { resolve(); return; }
        const done = (): void => { clearTimeout(timer); request.signal.removeEventListener('abort', done); resolve(); };
        const timer = setTimeout(done, ms);
        request.signal.addEventListener('abort', done, { once: true });
      });
      // 一次真实等待同时跨越旧的 30 秒池时限和 45 秒桥接时限，不能用虚假计时证明。
      if (chosen === 'long-sse') await delay(52000);
      if (body.model !== POOL_MODEL) return Response.json({ type: 'error', error: { message: '模型未映射' } }, { status: 400 });
      if (chosen === 'redirect') return new Response('池重定向原文', { status: 302, headers: { location: '/redirect-target' } });
      if (['401','429','500'].includes(chosen)) return Response.json({ type: 'error', error: { message: '合成池错误回显：' + apiKey } }, { status: Number(chosen), headers: { 'x-echo-secret': apiKey } });
      const agentMode = chosen === 'agent' || chosen === 'agent-two-stage' || chosen === 'agent-foreground';
      if (agentMode && (Array.isArray(body.stop_sequences) && body.stop_sequences.includes('</block>') || body.max_tokens === 8192)) return Response.json({ id: 'msg_classifier_fixture', type: 'message', role: 'assistant', model: POOL_MODEL, content: [{ type: 'text', text: chosen === 'agent-two-stage' && body.max_tokens === 64 ? '<block>yes</block><category>Irreversible Local Destruction</category><reason>合成复核测试</reason>' : '<block>no</block>' }], stop_reason: 'end_turn', stop_sequence: null, usage: { input_tokens: 1, output_tokens: 1 } });
      const sessionMode = chosen === 'session-purpose', history = sessionMode ? JSON.stringify(body.messages) : '';
      const compact = sessionMode && history.includes('CRITICAL: Respond with TEXT ONLY.');
      const title = sessionMode && Array.isArray(body.system) && body.system.some(block => typeof block.text === 'string' && block.text.startsWith('You are naming a coding session'));
      const responseText = chosen === 'secret' ? '前缀' + apiKey + '后缀</pre><script>globalThis.poolXss=1</script>' : compact ? '<summary>本机假池 OK，保留当前会话。</summary>' : title ? '{"title":"本机会话用途测试"}' : '本机假池 OK';
      const hasToolResult = Array.isArray(body.messages) && body.messages.some(message => message && Array.isArray(message.content) && message.content.some((block: JsonObject) => block.type === 'tool_result'));
      const handback = agentMode && Array.isArray(body.tools) && body.tools.some(tool => tool.name === 'SubagentHandback');
      const tool = chosen === 'tool' && !hasToolResult && toolFile ? { type: 'tool_use', id: 'toolu_local_fixture', name: 'Read', input: { file_path: toolFile } }
        : handback ? { type: 'tool_use', id: 'toolu_handback_fixture', name: 'SubagentHandback', input: { message: '本机假池 OK' } }
        : agentMode && !hasToolResult ? { type: 'tool_use', id: 'toolu_agent_fixture', name: 'Agent', input: { description: '验证实际子代理关联', prompt: '只回复本机假池 OK，然后调用 SubagentHandback 交回报告。', subagent_type: 'Explore', ...(chosen === 'agent-foreground' ? { run_in_background: false } : {}) } } : null;
      // 用量只驱动真实客户端的预算分支，不表示真实模型执行或计费。
      const message = { id: 'msg_pool_fixture', type: 'message', role: 'assistant', model: POOL_MODEL, content: tool ? [tool] : [{ type: 'text', text: responseText }], stop_reason: tool ? 'tool_use' : 'end_turn', stop_sequence: null, usage: { input_tokens: sessionMode && !compact && history.includes('CCRB_LONG_HISTORY_') ? 125000 : 1, output_tokens: 1 } };
      if (chosen === 'json') return Response.json(message, { headers: { 'access-control-allow-credentials': 'true' } });
      if (chosen === 'secret') {
        const text = JSON.stringify(message), at = text.indexOf(apiKey) + Math.floor(apiKey.length / 2);
        return new Response(new ReadableStream({ async start(controller) { controller.enqueue(Buffer.from(text.slice(0, at))); await Bun.sleep(5); controller.enqueue(Buffer.from(text.slice(at))); controller.close(); } }), { headers: { 'content-type': 'application/json', 'x-echo-secret': apiKey } });
      }
      if (chosen === 'timeout') {
        await new Promise<void>(resolve => { const timer = setTimeout(resolve, 1500); request.signal.addEventListener('abort', () => { canceled++; clearTimeout(timer); resolve(); }, { once: true }); });
        return Response.json(message);
      }
      const event = (value: JsonObject): Uint8Array => Buffer.from('event: ' + value.type + '\ndata: ' + JSON.stringify(value) + '\n\n');
      let timer: ReturnType<typeof setInterval> | undefined, stopped = false;
      const stream = new ReadableStream<Uint8Array>({
        async start(controller) {
          const abort = (): void => { if (!stopped) { stopped = true; canceled++; if (timer) clearInterval(timer); try { controller.close(); } catch {} } };
          request.signal.addEventListener('abort', abort, { once: true });
          controller.enqueue(event({ type: 'message_start', message: { ...message, content: [], stop_reason: null } }));
          if (chosen === 'long-sse') await delay(14000);
          if (stopped) return;
          if (chosen === 'cancel') { timer = setInterval(() => { if (!stopped) controller.enqueue(Buffer.from(': keepalive\n\n')); }, 25); return; }
          if (tool) {
            controller.enqueue(event({ type: 'content_block_start', index: 0, content_block: { ...tool, input: {} } }));
            controller.enqueue(event({ type: 'content_block_delta', index: 0, delta: { type: 'input_json_delta', partial_json: JSON.stringify(tool.input) } }));
            controller.enqueue(event({ type: 'content_block_stop', index: 0 }));
            controller.enqueue(event({ type: 'message_delta', delta: { stop_reason: 'tool_use' }, usage: { output_tokens: 1 } }));
            controller.enqueue(event({ type: 'message_stop' }));
            stopped = true; request.signal.removeEventListener('abort', abort); controller.close(); return;
          }
          controller.enqueue(event({ type: 'content_block_start', index: 0, content_block: { type: 'text', text: '' } }));
          const count = chosen === 'large' ? 150 : 1;
          for (let i = 0; i < count && !stopped; i++) { controller.enqueue(event({ type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: chosen === 'large' ? 'x'.repeat(8192) : responseText } })); if (chosen === 'large') await Bun.sleep(1); }
          if (stopped) return;
          if (chosen === 'event-error') controller.enqueue(event({ type: 'error', error: { message: '合成 SSE 错误 ' + apiKey } }));
          else if (chosen !== 'incomplete') { controller.enqueue(event({ type: 'content_block_stop', index: 0 })); controller.enqueue(event({ type: 'message_delta', delta: { stop_reason: 'end_turn' }, usage: { output_tokens: 1 } })); controller.enqueue(event({ type: 'message_stop' })); }
          stopped = true; request.signal.removeEventListener('abort', abort); controller.close();
        },
        cancel() { if (!stopped) { stopped = true; canceled++; if (timer) clearInterval(timer); } },
      });
      return new Response(stream, { headers: { 'content-type': 'text/event-stream' } });
    },
  });
  return { baseUrl: 'http://127.0.0.1:' + server.port + '/v1', calls, get canceled() { return canceled; }, get redirected() { return redirected; }, select(value) { fixture = value; }, async close() { await server.stop(true); } };
}
