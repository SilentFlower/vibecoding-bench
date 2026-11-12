import { expect, test } from 'bun:test';
import type { JsonObject } from '../../src/shared/contracts';
import { applyCachePolicy } from '../../src/shared/cache-policy';
import { readCachePolicy, isCachePolicyDecision } from '../../src/shared/runtime-policy';
import { readConfig } from '../../src/control/server';
import { NativeEngine, createEngine } from '../../src/control/engine';

const history = (): JsonObject => ({ messages: [
  { role: 'user', content: 'u1' }, { role: 'assistant', content: 'a1' },
  { role: 'user', content: 'u2' }, { role: 'assistant', content: 'a2' },
  { role: 'user', content: 'u3' },
] });

test('缓存配置默认保真，非法值在服务和直接引擎入口均失败', async () => {
  expect(readCachePolicy(undefined)).toBe('preserve');
  expect(readConfig({}).engine.cachePolicy).toBe('preserve');
  expect(readConfig({ CCRB_CACHE_POLICY: 'sub2api' }).engine.cachePolicy).toBe('sub2api');
  const config = readConfig({ CCRB_MODE: 'demo' }).engine;
  for (const value of ['', 'auto', 'SUB2API', false, null]) {
    expect(() => readCachePolicy(value)).toThrow('CCRB_CACHE_POLICY');
    const invalid = { ...config, cachePolicy: value } as unknown as typeof config;
    expect(() => new NativeEngine(invalid)).toThrow('CCRB_CACHE_POLICY');
    await expect(createEngine(invalid)).rejects.toThrow('CCRB_CACHE_POLICY');
  }
});

test('保真路径不规范化字符串、不改输入，也不扫描未知缓存布局', () => {
  const input = { ...history(), cache_control: { future: true } };
  const before = JSON.stringify(input);
  const result = applyCachePolicy(input, input, 'preserve');
  expect(result.body).toBe(input);
  expect(JSON.stringify(input)).toBe(before);
  expect(result.decision.action).toBe('preserved');
  expect(isCachePolicyDecision(result.decision)).toBe(true);
});

test('尾部与倒数第二个用户断点跨轮稳定，只转换选中的字符串', () => {
  const input = history();
  const before = structuredClone(input);
  const result = applyCachePolicy(input, input, 'sub2api');
  expect(result.decision.selected).toEqual([{ message: 2, block: 0 }, { message: 4, block: 0 }]);
  expect(result.decision.breakpoints).toBe(2);
  expect(result.decision.ttl).toBe('1h');
  const messages = result.body.messages as JsonObject[];
  expect(messages[0]!.content).toBe('u1');
  expect(messages[2]!.content).toEqual([{ type: 'text', text: 'u2', cache_control: { type: 'ephemeral', ttl: '1h' } }]);
  expect(input).toEqual(before);
  expect(isCachePolicyDecision(result.decision)).toBe(true);
});

test('四条消息的助手尾部与倒数第二个用户分别选点', () => {
  const input = history();
  (input.messages as unknown[]).pop();
  expect(applyCachePolicy(input, input, 'sub2api').decision.selected).toEqual([{ message: 0, block: 0 }, { message: 3, block: 0 }]);
});

test('短历史只选尾部，tool_result 可选且业务对象中的同名键不控制策略', () => {
  const input = { messages: [{ role: 'user', content: [
    { type: 'tool_result', tool_use_id: 'tool_1', content: 'result', extension: { cache_control: { future: true } } },
  ] }] };
  const result = applyCachePolicy(input, input, 'sub2api');
  expect(result.decision.selected).toEqual([{ message: 0, block: 0 }]);
  expect((result.body.messages as JsonObject[])[0]!.content).toEqual([{ ...input.messages[0]!.content[0], cache_control: { type: 'ephemeral', ttl: '1h' } }]);
});

test('调用方已有消息断点及嵌套协议标记均完整保留', () => {
  for (const content of [
    [{ type: 'text', text: 'caller', cache_control: { type: 'ephemeral', ttl: '5m', scope: 'global' } }],
    [{ type: 'tool_result', tool_use_id: 'tool_1', content: [{ type: 'text', text: 'nested', cache_control: { type: 'ephemeral' } }] }],
  ]) {
    const input = { messages: [{ role: 'user', content }] };
    const result = applyCachePolicy(input, input, 'sub2api');
    expect(result.body).toBe(input);
    expect(result.decision.reason).toBe('caller_message_breakpoints');
  }
});

test('调用方或原生构造的根缓存机制优先', () => {
  const original = history();
  for (const [input, outgoing] of [[{ ...original, cache_control: { type: 'ephemeral' } }, original], [original, { ...original, cache_control: { type: 'ephemeral' } }]]) {
    const result = applyCachePolicy(input!, outgoing!, 'sub2api');
    expect(result.body).toBe(outgoing!);
    expect(result.decision.reason).toBe('root_cache_control_present');
  }
});

test('只有一个空位时优先尾部，预算耗尽不转换字符串', () => {
  for (const count of [3, 4]) {
    const input = { ...history(), tools: Array.from({ length: count }, (_, i) => ({ name: 't' + i, cache_control: { type: 'ephemeral', ttl: '1h' } })) };
    const result = applyCachePolicy(input, input, 'sub2api');
    if (count === 3) {
      expect(result.decision.selected).toEqual([{ message: 4, block: 0 }]);
      expect(result.decision.breakpoints).toBe(4);
    } else {
      expect(result.body).toBe(input);
      expect(result.decision.reason).toBe('no_available_slots');
    }
  }
});

test.each([undefined, '5m', '1h'])('保留 system/tools TTL 与 scope，新 TTL 遵守前缀顺序：%s', ttl => {
  const input = { ...history(), system: [{ type: 'text', text: 'system', cache_control: { type: 'ephemeral', ...(ttl ? { ttl } : {}), scope: 'global' } }] };
  const before = structuredClone(input);
  const result = applyCachePolicy(input, input, 'sub2api');
  expect(result.body.system).toEqual(before.system);
  expect(result.decision.ttl).toBe(ttl === '1h' ? '1h' : '5m');
  expect(input).toEqual(before);
});

test('不覆盖未知缓存格式，也不修复既有反向 TTL 布局', () => {
  const layouts = [
    { system: [{ cache_control: { type: 'ephemeral', ttl: '2h' } }] },
    { tools: [{ cache_control: { type: 'future' } }] },
    { tools: [{ cache_control: { type: 'ephemeral', ttl: '5m' } }], system: [{ cache_control: { type: 'ephemeral', ttl: '1h' } }] },
  ];
  for (const layout of layouts) {
    const input = { ...history(), ...layout };
    const result = applyCachePolicy(input, input, 'sub2api');
    expect(result.body).toBe(input);
    expect(result.decision.reason).toBe('unsupported_cache_control');
  }
});

test('不选 thinking、图片或 tool_use，保留签名与块顺序', () => {
  const content = [{ type: 'text', text: 'answer' }, { type: 'thinking', thinking: 'private', signature: 'signed' }, { type: 'tool_use', id: 'tool_1', name: 'Read', input: {} }];
  const input = { messages: [{ role: 'assistant', content }] };
  const result = applyCachePolicy(input, input, 'sub2api');
  expect(result.decision.selected).toEqual([{ message: 0, block: 0 }]);
  expect(((result.body.messages as JsonObject[])[0]!.content as JsonObject[]).slice(1)).toEqual(content.slice(1));
  for (const block of [{ type: 'image', source: {} }, { type: 'thinking', thinking: 'x', signature: 's' }, { type: 'redacted_thinking', data: 'x' }, { type: 'tool_use', id: 'tool_1' }]) {
    const body = { messages: [{ role: 'assistant', content: [block] }] };
    expect(applyCachePolicy(body, body, 'sub2api').body).toBe(body);
  }
});

test('普通 API 的自动断点可被替换，原输入及工具声明不变', () => {
  const original = history();
  const outgoing = structuredClone(original);
  const messages = outgoing.messages as JsonObject[];
  messages[0] = { role: 'user', content: [{ type: 'text', text: 'u1', cache_control: { type: 'ephemeral', scope: 'global' } }] };
  const before = structuredClone(outgoing);
  const result = applyCachePolicy(original, outgoing, 'sub2api');
  expect(result.decision.action).toBe('applied');
  expect(((result.body.messages as JsonObject[])[0]!.content as JsonObject[])[0]!.cache_control).toBeUndefined();
  expect(outgoing).toEqual(before);
  for (const invalid of [{ ...result.decision, ttl: ['1h'] }, { ...result.decision, selected: [{ message: -1, block: 0 }] }, { ...result.decision, breakpoints: 5 }]) expect(isCachePolicyDecision(invalid)).toBe(false);
});

test('受信TTL覆盖仅处理已有协议断点，支持关闭及跨轮切换', async () => {
  const { rewriteCacheTtl } = await import('../../src/shared/cache-policy');
  const { readCacheTtlRewrite } = await import('../../src/shared/runtime-policy');
  const business = { type: 'ephemeral', ttl: '5m' };
  const body = {
    cache_control: { type: 'ephemeral' },
    system: [{ type: 'text', text: 'prefix', cache_control: { type: 'ephemeral', ttl: '5m' } }],
    tools: [{ name: 'lookup', input_schema: { cache_control: business }, cache_control: { type: 'ephemeral' } }],
    messages: [{ role: 'user', content: [{ type: 'tool_result', tool_use_id: 'tool_synthetic', content: [{ type: 'text', text: 'business', cache_control: business }], cache_control: { type: 'ephemeral' } }, { type: 'text', text: 'tail' }] }],
  };
  expect(rewriteCacheTtl(body, 'off')).toBe(body);
  let previous: JsonObject = body;
  for (const mode of ['1h', '5m'] as const) {
    const rewritten = rewriteCacheTtl(previous, mode);
    expect(rewritten).toEqual({
      ...body,
      cache_control: { type: 'ephemeral', ttl: mode },
      system: body.system.map(block => ({ ...block, cache_control: { ...block.cache_control, ttl: mode } })),
      tools: body.tools.map(tool => ({ ...tool, cache_control: { ...tool.cache_control, ttl: mode } })),
      messages: body.messages.map(message => ({ ...message, content: message.content.map((block, index) => index === 0 ? { ...block, cache_control: { type: 'ephemeral', ttl: mode } } : block) })),
    });
    previous = rewritten;
  }
  expect(body.cache_control).toEqual({ type: 'ephemeral' });
  expect(readCacheTtlRewrite(undefined)).toBe('off');
  for (const value of ['', '1H', 'auto', null, true]) expect(() => readCacheTtlRewrite(value)).toThrow('TTL');
});
