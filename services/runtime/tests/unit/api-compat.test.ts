import { describe, expect, test } from 'bun:test';
import { parseInput } from '../../src/shared/input';
import { prepareInput } from '../../src/control/header-policy';
import { applyContextManagement, prepareApiSystemMessages } from '../../src/shared/api-compat';
import type { MessageBody } from '../../src/shared/contracts';

const session = '22222222-2222-4222-8222-222222222222';
const base = { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '合成问题' }] };
const beta = new Headers({ 'anthropic-beta': 'other, context-management-2025-06-27' });

describe('普通API身份和历史管理兼容', () => {
  test('普通API原位保留消息级system、effort、clear_at和缓存，身份取自同次SDK', () => {
    const messages: MessageBody['messages'] = [{ role: 'user', content: '合成问题' }, { role: 'system', content: [], output_config: { effort: 'high' } },
      { role: 'system', content: [{ type: 'text', text: '后续指令', cache_control: { type: 'ephemeral', ttl: '1h' } }], clear_at: 'next_user_message' }];
    const body = { ...base, system: [{ type: 'text', text: '业务系统指令', cache_control: { type: 'ephemeral', ttl: '1h' } }], messages };
    const before = structuredClone(body);
    const input = parseInput(body);
    expect(input.inputFormat).toBe('api');
    expect(input.body.messages).toEqual(messages);
    for (const version of ['2.1.280', '2.1.293'] as const) for (const cch of ['', ' cch=12345;']) {
      const billing = { type: 'text', text: 'x-anthropic-billing-header: cc_version=' + version + '.abc; cc_entrypoint=cli;' + cch };
      const metadata = { user_id: JSON.stringify({ device_id: 'a'.repeat(64), account_uuid: '', session_id: session }) };
      const generated = { system: [billing, { type: 'text', text: '种子指令' }], metadata, messages: [{ role: 'user', content: '不应外发的种子' }], tools: [{ name: '不应增加的工具' }], max_tokens: 4096, fallbacks: [{ model: 'seed-model' }], output_config: { effort: 'medium' } };
      const result = prepareApiSystemMessages(input.body, generated, version);
      expect(result.messages).toEqual(messages);
      expect(result.system).toEqual([{ ...billing, text: billing.text.replace('cch=12345', 'cch=00000') }, ...body.system]);
      expect(result.metadata).toEqual(metadata);
      expect(result.tools).toEqual([]);
      expect(result.max_tokens).toBe(4096);
      expect(result.fallbacks).toBeUndefined();
      expect(result.output_config).toBeUndefined();
      expect(() => prepareApiSystemMessages(input.body, {}, version)).toThrow('归因上下文');
    }
    expect(body).toEqual(before);
    for (const message of [{ role: 'tool', content: '错误角色' }, { role: 'user', content: 'q', output_config: {} },
      { role: 'system', content: [], output_config: [] }, { role: 'system', content: '指令', clear_at: 'unknown' },
      { role: 'system', content: '指令', clear_at: ['never'] }]) {
      expect(() => parseInput({ ...base, messages: [message] })).toThrow();
    }
  });
  test('先提取JSON或旧格式会话，移除普通API身份，原输入保持原样', () => {
    for (const user_id of [JSON.stringify({ session_id: session, device_id: 'client-device', account_uuid: 'client-account' }), 'user_client_account_client_session_' + session]) {
      const body = { ...base, metadata: { user_id, client_extension: 'remove' } };
      const before = structuredClone(body);
      const prepared = prepareInput(parseInput(body));
      expect(prepared.context.sessionId).toBe(session);
      expect(prepared.context.source).toBe('client');
      expect(prepared.input.body.metadata).toBeUndefined();
      expect(body).toEqual(before);
    }
    const ordinary = prepareInput(parseInput({ ...base, metadata: { user_id: 'ordinary-user' } }));
    expect(ordinary.context.source).toBe('bridge-default');
    expect(ordinary.input.body.metadata).toBeUndefined();
  });

  test('会话冲突及畸形metadata明确拒绝，未知业务参数继续拒绝', () => {
    const body = { ...base, metadata: { user_id: JSON.stringify({ session_id: session }) } };
    expect(() => parseInput({ body, context: { sessionId: 'different' } })).toThrow('冲突');
    expect(() => prepareInput(parseInput(body, [['x-claude-code-session-id', 'different']]))).toThrow('冲突');
    for (const metadata of [null, [], 'raw', { user_id: 1 }, { user_id: '{"session_id":1}' }, { user_id: '{"session_id":""}' }]) expect(() => parseInput({ ...base, metadata })).toThrow();
    expect(() => parseInput({ ...base, top_p: 1 })).toThrow('top_p');
  });

  test('两类已支持指令保留原参数，明确值覆盖SDK默认值', () => {
    const context_management = { edits: [
      { type: 'clear_thinking_20251015', keep: { type: 'thinking_turns', value: 2 } },
      { type: 'clear_tool_uses_20250919', trigger: { type: 'input_tokens', value: 30000 }, keep: { type: 'tool_uses', value: 3 }, clear_at_least: { type: 'input_tokens', value: 5000 }, exclude_tools: ['lookup'], clear_tool_inputs: true },
    ] };
    const input = parseInput({ ...base, context_management });
    expect(input.body.context_management).toEqual(context_management);
    const generated = { thinking: { type: 'adaptive' }, context_management: { edits: [{ type: 'clear_thinking_20251015', keep: 'all' }] } };
    const result = applyContextManagement(input.body, generated, beta);
    expect(result.context_management).toEqual(context_management);
    expect(generated.context_management.edits[0]!.keep).toBe('all');
    expect(applyContextManagement(base, generated, beta)).toBe(generated);
  });

  test('未知策略、错误结构、thinking顺序和失效计数在发送前拒绝', () => {
    for (const context_management of [null, [], { unknown: true }, { edits: {} }, { edits: [null] }, { edits: [{ type: 'future' }] },
      { edits: [{ type: 'clear_thinking_20251015', keep: { type: 'thinking_turns', value: 0 } }] },
      { edits: [{ type: 'clear_tool_uses_20250919' }, { type: 'clear_thinking_20251015' }] },
      { edits: [{ type: 'clear_tool_uses_20250919', clear_tool_inputs: 'yes' }] },
      { edits: [{ type: 'clear_tool_uses_20250919', trigger: { type: { toString: 'invalid' }, value: 1 } }] },
      { edits: [{ type: 'clear_tool_uses_20250919', trigger: { type: 'input_tokens', value: Infinity } }] }]) expect(() => parseInput({ ...base, context_management })).toThrow();
  });

  test('同次SDK能力和thinking开关约束显式历史管理', () => {
    const input = parseInput({ ...base, context_management: { edits: [{ type: 'clear_thinking_20251015', keep: 'all' }] } });
    expect(() => applyContextManagement(input.body, { thinking: { type: 'adaptive' } }, new Headers())).toThrow('能力');
    expect(() => applyContextManagement(input.body, { thinking: { type: 'disabled' } }, beta)).toThrow('启用 thinking');
    const tool = parseInput({ ...base, context_management: { edits: [{ type: 'clear_tool_uses_20250919' }] } });
    expect(applyContextManagement(tool.body, {}, beta).context_management).toEqual(tool.body.context_management);
  });
});
