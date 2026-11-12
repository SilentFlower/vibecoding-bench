import { describe, expect, test } from 'bun:test';
import type { MessageBody } from '../../src/shared/contracts';
import { parseInput } from '../../src/shared/input';
import { prepareInput } from '../../src/control/header-policy';
import { readNativeInput, prepareNativeBody } from '../../src/shared/native-input';

const session = '22222222-2222-4222-8222-222222222222';
const prompt = '11111111-1111-4111-8111-111111111111';
const marker = { type: 'ephemeral', ttl: '5m' };

function fixture(): MessageBody {
  return { model: 'claude-sonnet-4-6', system: [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=12345; cc_prompt_id=' + prompt + '; cc_turn_origin=human; cc_prompt_index=3; cc_turn_index=4;' }, { type: 'text', text: '调用方业务 system', cache_control: marker }], messages: [{ role: 'user', content: [{ type: 'text', text: '历史', cache_control: marker }] }, { role: 'system', content: '原生会话中的系统消息' }, { role: 'user', content: '下一轮' }], metadata: { user_id: JSON.stringify({ device_id: 'a'.repeat(64), account_uuid: '', session_id: session }), trace_extension: 'keep' }, thread: { type: 'request', previous_message_id: 'msg_previous' }, diagnostics: { previous_message_id: null }, fallbacks: 'default', safeguards: [], future_official: { nested: ['keep'] } };
}

describe('固定 293 原生入站合同', () => {
  test('内部自定义目标省略 CCH 时，不由入站兼容补丁重新增加', () => {
    const generated = fixture();
    (generated.system as { text: string }[])[0]!.text = (generated.system as { text: string }[])[0]!.text.replace('cch=12345;', '');
    for (const policy of ['strict', 'local_base_url'] as const) {
      const body = fixture(), before = structuredClone(body);
      if (policy === 'local_base_url') (body.system as { text: string }[])[0]!.text = (body.system as { text: string }[])[0]!.text.replace('cch=12345;', '').replace('cc_entrypoint=cli', 'cc_entrypoint=sdk-cli');
      const inputBefore = structuredClone(body);
      const result = prepareNativeBody(body, generated.metadata, policy, generated.system);
      const parsed = readNativeInput(result, 'local_base_url');
      expect(parsed?.fields.cch).toBeUndefined();
      expect(parsed?.fields.cc_entrypoint).toBe('cli');
      expect(parsed?.fields.cc_prompt_id).toBe(prompt);
      expect(result.messages).toEqual(before.messages);
      expect((result.system as unknown[]).slice(1)).toEqual((before.system as unknown[]).slice(1));
      expect(body).toEqual(inputBefore);
    }
  });

  test('本地 Base URL 兼容只能由启动侧打开，原始入站保持且策略沿内部合同传递', () => {
    for (const entry of ['cli', 'sdk-cli']) {
      const body = fixture(), billing = body.system as { text: string }[];
      billing[0]!.text = billing[0]!.text.replace('cch=12345;', '').replace('cc_entrypoint=cli', 'cc_entrypoint=' + entry);
      const before = structuredClone(body);
      expect(() => parseInput(body)).toThrow();
      expect(() => parseInput({ ...body, nativeIngressPolicy: 'local_base_url' })).toThrow();
      expect(() => parseInput({ body, nativeIngressPolicy: 'local_base_url' })).toThrow();
      const input = parseInput(body, [], 'local_base_url');
      expect(input.body).toEqual(before); expect(input.nativeIngressPolicy).toBe('local_base_url');
      expect(prepareInput(input).input.nativeIngressPolicy).toBe('local_base_url');
      const generated = fixture();
      const result = prepareNativeBody(input.body, generated.metadata, input.nativeIngressPolicy, generated.system);
      expect((result.system as { text: string }[])[0]!.text).toContain('cc_entrypoint=cli;');
      expect((result.system as { text: string }[])[0]!.text).toContain('cch=00000;');
      expect(readNativeInput(result)?.fields.cc_turn_index).toBe('4');
      expect(result.messages).toEqual(body.messages);
      expect((result.system as unknown[]).slice(1)).toEqual((body.system as unknown[]).slice(1));
      expect(body).toEqual(before);
    }
  });

  test('兼容模式不接纳损坏证据，也不能在缺少实际 CLI 生成上下文时伪造发送入口', () => {
    const body = fixture(), text = (body.system as { text: string }[])[0]!.text;
    for (const billing of [text + ' cch=aaaaa;', text.replace('cch=12345', 'cch=xyz'), text.replace('cch=12345;', 'future=opaque cch=12345;'), text.replace('2.1.293', '2.1.303'), text.replace('cc_entrypoint=cli', 'cc_entrypoint=unknown')]) {
      expect(() => parseInput({ ...body, system: [{ type: 'text', text: billing }] }, [], 'local_base_url')).toThrow();
    }
    expect(() => prepareNativeBody(body, body.metadata, 'local_base_url')).toThrow('CLI billing');
    const sdk = structuredClone(body.system) as { text: string }[];
    sdk[0]!.text = sdk[0]!.text.replace('cc_entrypoint=cli', 'cc_entrypoint=sdk-cli');
    expect(() => prepareNativeBody(body, body.metadata, 'local_base_url', sdk)).toThrow();
    expect(() => parseInput({ body, context: { sessionId: 'different' } }, [], 'local_base_url')).toThrow('冲突');
  });

  test('普通 API 维持窄合同，原生字段及系统角色保留', () => {
    expect(() => parseInput({ model: 'm', messages: [{ role: 'user', content: 'q' }], thread: {} })).toThrow('暂不支持字段');
    const body = fixture(), input = parseInput(body), prepared = prepareInput(input);
    expect(input.inputFormat).toBe('claude_code');
    expect(input.body).toEqual(body);
    expect(prepared.context).toMatchObject({ inputFormat: 'claude_code', sessionId: session, promptId: prompt, agentKind: 'main', requestClass: 'main' });
  });

  test('只替换账号身份及 CCH 占位，不改变原生业务、缓存或线程', () => {
    const body = fixture(), before = structuredClone(body);
    const result = prepareNativeBody(body, { user_id: JSON.stringify({ device_id: 'b'.repeat(64), account_uuid: '33333333-3333-4333-8333-333333333333', session_id: 'should-not-replace-native-session' }) });
    expect(body).toEqual(before);
    expect(JSON.parse((result.metadata as Record<string, string>).user_id!)).toEqual({ device_id: 'b'.repeat(64), account_uuid: '33333333-3333-4333-8333-333333333333', session_id: session });
    expect((result.metadata as Record<string, unknown>).trace_extension).toBe('keep');
    expect((result.system as { text: string }[])[0]!.text).toContain('cch=00000;');
    for (const key of Object.keys(body).filter(key => !['metadata', 'system'].includes(key))) expect(result[key]).toEqual(body[key]);
    expect((result.system as unknown[]).slice(1)).toEqual((body.system as unknown[]).slice(1));
  });

  test('原生省略字段保持省略，空工具不增加默认声明', () => {
    for (const tools of [undefined, []]) {
      const body: MessageBody = { ...fixture(), ...(tools ? { tools } : {}) };
      expect(prepareNativeBody(body, body.metadata).tools).toEqual(tools);
      expect(prepareNativeBody(body, body.metadata).stream).toBeUndefined();
    }
  });

  test('已接纳的 billing 间隔保持原样，CCH 仍须替换为原生占位', () => {
    const body = fixture(), blocks = body.system as { text: string }[];
    blocks[0]!.text = blocks[0]!.text.replace('cch=12345;', 'cch=12345 \t;');
    expect(readNativeInput(body)).not.toBeNull();
    const result = prepareNativeBody(body, body.metadata);
    expect((result.system as { text: string }[])[0]!.text).toBe(blocks[0]!.text.replace('12345', '00000'));
  });

  test('两条接入路径只检查 thinking 结构，不推断模型能力', () => {
    for (const base of [fixture(), { model: 'm', messages: [{ role: 'user', content: 'q' }] }]) {
      for (const thinking of [{ type: 'unknown' }, { type: 'enabled' }, { type: 'enabled', budget_tokens: 1023 }]) expect(parseInput({ ...base, thinking }).body.thinking).toEqual(thinking);
      for (const thinking of ['enabled', 1, []]) expect(() => parseInput({ ...base, thinking })).toThrow('必须是对象');
    }
  });

  test('原生正文与显式信封或头部不一致时拒绝', () => {
    const body = fixture();
    expect(() => parseInput({ body, context: { sessionId: 'different' } })).toThrow('冲突');
    expect(() => prepareInput(parseInput(body, [['x-claude-code-prompt-id', '33333333-3333-4333-8333-333333333333']]))).toThrow('冲突');
    expect(() => prepareInput(parseInput(body, [['x-claude-code-request-class', 'subagent'], ['x-claude-code-agent-id', 'child']]))).toThrow('主代理上下文');
  });

  test('原生子代理压缩保留分类及父子关系', () => {
    const body = fixture();
    (body.system as { text: string }[])[0]!.text += ' cc_is_subagent=true;';
    const prepared = prepareInput(parseInput(body, [['x-claude-code-request-class', 'compaction'], ['x-claude-code-agent-id', 'child'], ['x-claude-code-parent-agent-id', session], ['x-claude-code-agent-type', 'Explore']]));
    expect(prepared.context).toMatchObject({ requestClass: 'compaction', agentKind: 'subagent', agentId: 'child', parentAgentId: session, querySource: 'compact' });
  });

  test('未知版本、重复归因和不完整身份不能回落成普通 API', () => {
    const change = (text: string) => { const b = fixture(); (b.system as { text: string }[])[0]!.text = text; return b; };
    const billing = (fixture().system as { text: string }[])[0]!.text;
    for (const text of [billing.replace('2.1.293', '2.1.303'), billing + ' cch=aaaaa;', billing.replace('cch=12345;', ''), billing.replace('cc_entrypoint=cli', 'cc_entrypoint=sdk-cli')]) expect(() => parseInput(change(text))).toThrow();
    const repeated = fixture(); (repeated.system as unknown[]).push((repeated.system as unknown[])[0]);
    expect(() => parseInput(repeated)).toThrow('唯一');
    expect(() => parseInput({ ...fixture(), metadata: { user_id: '{}' } })).toThrow('结构不合法');
  });

  test('两类入站删除根本机设置，原始输入及嵌套同名业务字段保持', () => {
    const business = { settings: { selected: 'business' }, claude_settings: ['business'], env: { mode: 'business' } };
    const tool = { name: 'set_config', input_schema: { type: 'object', properties: { settings: { type: 'object' }, claude_settings: { type: 'array' }, env: { type: 'object' } } } };
    const bases: MessageBody[] = [fixture(), { model: 'm', messages: [{ role: 'user', content: 'q' }] }];
    for (const base of bases) {
      const expected: MessageBody = { ...base, tools: [tool], messages: [...base.messages, { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_settings', name: tool.name, input: business }] }] };
      for (const value of [null, false, 'ignored', [], { env: { ANTHROPIC_BASE_URL: 'https://client.invalid' } }]) {
        const body = Object.freeze({ ...expected, settings: value, claude_settings: value, env: value });
        const before = structuredClone(body);
        for (const envelope of [false, true]) for (const policy of ['strict', 'local_base_url'] as const) {
          const input = parseInput(envelope ? { body } : body, [], policy);
          expect(input.body).toEqual(expected);
          expect(input.body.tools).toEqual([tool]);
          expect(body).toEqual(before);
        }
      }
    }
  });

  test('其余本机控制字段明确拒绝，合法扩展及工具参数中的同名字段保留', () => {
    for (const key of ['extra_headers', 'extra_body', 'headers', 'proxy_url', 'api_key', 'oauth_token', 'claude_binary', 'claude_home', 'claude_config_dir', 'workdir']) expect(() => parseInput({ ...fixture(), settings: {}, [key]: {} })).toThrow('本机控制字段');
    expect(() => readNativeInput({ ...fixture(), settings: {} })).toThrow('本机控制字段');
    const body = { ...fixture(), tools: [{ name: 'set_config', input_schema: { type: 'object', properties: { env: { type: 'string' } } } }] };
    expect(parseInput(body).body.tools).toEqual(body.tools);
    expect(readNativeInput({ model: 'm', messages: [] })).toBeNull();
  });
});

describe('模型参数由前置与上游判断', () => {
  const body: MessageBody = { model: 'm', messages: [{ role: 'user', content: 'q' }], tools: [{ name: 'chosen', input_schema: { type: 'object' } }] };
  test('原生工具定义和组合原值保留，不在入口套用固定模型政策', () => {
    for (const change of [{ tools: [], tool_choice: { type: 'auto' } }, { tools: [body.tools![0]!, body.tools![0]!] }, { tool_choice: { type: 'tool', name: 'missing' }, thinking: { type: 'adaptive' } }, { tool_choice: { type: 'future', name: 'chosen' } }]) {
      const request = { ...fixture(), ...change }, before = structuredClone(request);
      expect(parseInput(request).body).toEqual(before); expect(request).toEqual(before);
    }
  });
  test('数值范围不在入口重复限制，非 JSON 数值及错误类型仍拒绝', () => {
    for (const base of [fixture(), body]) for (const max_tokens of [0, -1, 1.5, 128000]) {
      const request = { ...base, max_tokens, temperature: 2 };
      expect(parseInput(request).body).toEqual(request);
    }
    for (const max_tokens of ['64', Infinity, NaN]) expect(() => parseInput({ ...body, max_tokens })).toThrow('有限数值');
  });
});
