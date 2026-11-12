import { randomUUID } from 'node:crypto';
import type { JsonObject } from '../../src/shared/contracts';
import type { PoolScene } from './pool-common';

/** 建立合成入站；真实池只复用三个有界场景。 @param live 是否显式真实验收。 @return 串行场景定义。 */
export function poolScenes(live: boolean): PoolScene[] {
  const definitions: [string, string, boolean, boolean, boolean, number][] = [
    ['native-main-json', 'json', true, false, false, 200],
    ['native-child-sse', 'sse', true, true, false, 200],
    ['native-cancel-sse', 'cancel', true, true, true, 200],
  ];
  if (!live) definitions.push(
    ['api-json', 'json', false, false, false, 200], ['api-sse-sub2api', 'sse', false, true, false, 200],
    ['native-tools', 'json', true, false, false, 200], ['secret-echo', 'secret', true, false, false, 200],
    ['pool-401', '401', true, false, false, 401], ['pool-429', '429', true, false, false, 429], ['pool-500', '500', true, false, false, 500],
    ['pool-redirect', 'redirect', true, false, false, 302], ['pool-incomplete', 'incomplete', true, true, false, 200],
    ['pool-event-error', 'event-error', true, true, false, 200], ['pool-timeout', 'timeout', true, false, false, 502],
    ['pool-large-response', 'large', true, true, false, 200],
  );
  return definitions.map(([id, fixture, native, stream, cancel, expectedStatus]) => {
    const sessionId = randomUUID(), promptId = randomUUID(), child = id === 'native-child-sse';
    const body: JsonObject = { model: 'claude-sonnet-4-6', max_tokens: 128, stream, messages: [{ role: 'user', content: cancel ? '请逐行列出数字 1 到 100，只输出数字。' : '请只回答 OK。' }] };
    if (native) {
      body.system = [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=12345; cc_prompt_id=' + promptId + '; cc_turn_origin=human;' + (child ? ' cc_is_subagent=true;' : '') }, { type: 'text', text: '测试请求，请按用户要求回答。', cache_control: { type: 'ephemeral' } }];
      body.metadata = { user_id: JSON.stringify({ device_id: 'a'.repeat(64), account_uuid: '', session_id: sessionId }) };
    }
    if (!live && native) { body.thread = { type: 'request', previous_message_id: null }; body.future_extension = { nested: ['保留'], signature: 'opaque-signature' }; }
    if (id === 'native-tools') {
      body.tools = [{ name: 'lookup_fixture', description: '仅展示定义，不执行工具', input_schema: { type: 'object', properties: { query: { type: 'string' } } } }];
      body.messages = [{ role: 'user', content: '上一轮' }, { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_fixture', name: 'lookup_fixture', input: { query: '样本' } }] }, { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_fixture', content: '合成结果' }, { type: 'text', text: '请回答 OK。' }] }];
    }
    const input = { schema_version: 1, request_id: id, body, headers: [['x-future-pool-test', 'preserved']], context: { sessionId, promptId, ...(child ? { requestClass: 'subagent', agentKind: 'subagent', agentId: 'pool-child', parentAgentId: 'pool-parent', agentType: 'Explore' } : {}) } };
    return { id, fixture, input, cancel, expectedStatus, cachePolicy: !live && (child || id === 'api-sse-sub2api') ? 'sub2api' : 'preserve' };
  });
}
