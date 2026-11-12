import { describe, expect, test } from 'bun:test';
import type { HeaderPair } from '../../src/shared/contracts';
import { parseInput } from '../../src/shared/input';
import { prepareInput } from '../../src/control/header-policy';
import { Redactor } from '../../src/control/redaction';

const body = { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: 'hello' }], stream: true };

describe('协议白名单、凭据与调用语义', () => {
  test('登记头保留，未知头、动态连接字段及调用方凭据按归属删除', () => {
    const input = parseInput({ body, headers: [
      ['Accept', 'application/json'], ['X-Future-Feature', 'remove'], ['Connection', 'X-Local-Hop'], ['connection', 'x-other-hop'],
      ['X-Local-Hop', 'remove'], ['x-other-hop', 'remove'], ['Authorization', 'Bearer client-secret'],
      ['X-Api-Key', 'client-key'], ['Host', 'evil.invalid'], ['X-Stainless-Runtime', 'fake'], ['x-client-request-id', 'forged'],
    ] });
    const result = prepareInput(input);
    expect(result.headers).toEqual([['Accept', 'application/json']]);
    expect(result.decisions).toContainEqual({ name: 'X-Future-Feature', action: 'drop', reason: '调用方请求头未登记到协议白名单' });
    expect(result.decisions.filter(x => x.action === 'drop').map(x => x.name)).toContain('X-Local-Hop');
    expect(input.headers.find(x => x[0] === 'Authorization')?.[1]).toBe('Bearer client-secret');
  });

  test('代理、CDN、客户端私有及未登记协议字段的大小写与重复项统一过滤', () => {
    const names = ['Forwarded', 'X-Forwarded-For', 'x-FORWARDED-for', 'X-Forwarded-Proto', 'X-Forwarded-Host', 'X-Real-IP', 'Via', 'X-Amz-Cf-Id', 'CloudFront-Viewer-Country', 'CF-Connecting-IP', 'New-Api-User', 'X-Oneapi-Request-Id', 'Traceparent', 'Tracestate', 'X-Future-Feature', 'x-claude-code-future', 'anthropic-future', 'constructor', '__proto__'];
    const input = parseInput({ body, headers: names.map(name => [name, 'synthetic']) });
    const result = prepareInput(input);
    expect(result.headers).toEqual([]);
    expect(result.decisions).toEqual(names.map(name => ({ name, action: 'drop', reason: '调用方请求头未登记到协议白名单' })));
    expect(result.context.source).toBe('bridge-default');
    expect(input.headers.map(([name]) => name)).toEqual(names);
  });

  test('已登记协议头保留完整值，合法多值保持输入顺序', () => {
    const headers: HeaderPair[] = [
      ['Accept', 'application/json'], ['accept', 'text/event-stream'], ['Accept-Language', 'zh-CN'], ['accept-language', 'en-US;q=0.8'],
      ['Cache-Control', 'no-cache'], ['cache-control', 'no-store'], ['anthropic-version', '2023-06-01'],
      ['anthropic-beta', 'first-beta'], ['Anthropic-Beta', 'second-beta'], ['anthropic-dangerous-direct-browser-access', 'true'],
      ['x-claude-code-prev-tool-durations', 'Read=12'], ['x-claude-code-compaction', 'true'], ['x-claude-code-context-compacted', 'true'],
    ];
    const result = prepareInput(parseInput({ body, headers }));
    expect(result.headers).toEqual(headers);
    expect(result.decisions.filter(value => value.action === 'keep')).toHaveLength(10);
  });

  test('子代理头进入关联上下文，不会统一变为 main', () => {
    const result = prepareInput(parseInput({ body, headers: [
      ['x-claude-code-request-class', 'subagent'], ['x-claude-code-agent-id', 'child-1'],
      ['x-claude-code-parent-agent-id', 'parent-1'], ['x-claude-code-agent-type', 'Explore'],
      ['x-claude-code-session-id', 'session-1'], ['x-claude-code-prompt-id', '11111111-1111-4111-8111-111111111111'],
    ] }));
    expect(result.context).toMatchObject({ requestClass: 'subagent', agentKind: 'subagent', agentId: 'child-1', parentAgentId: 'parent-1', agentType: 'Explore', sessionId: 'session-1', source: 'client', querySource: 'agent:builtin:Explore' });
    expect(result.headers).toHaveLength(0);
  });

  test('未知来源有明确默认标记，正文里的 agent 字样不会改变分类', () => {
    const result = prepareInput(parseInput({ ...body, messages: [{ role: 'user', content: '我叫 subagent，请处理' }] }));
    expect(result.context.requestClass).toBe('main');
    expect(result.context.source).toBe('bridge-default');
    expect(result.context.querySource).toBe('repl_main_thread');
    expect(result.context.agentId).toBe(result.context.sessionId);
  });

  test('显式主代理身份允许使用独立的 root agentId', () => {
    const result = prepareInput(parseInput({ body, context: { agentKind: 'main', agentId: 'root-agent' } }));
    expect(result.context).toMatchObject({ requestClass: 'main', agentKind: 'main', agentId: 'root-agent' });
  });

  test('压缩可以发生在子代理中，不能只靠 request-class 判断内部 agent 类型', () => {
    const result = prepareInput(parseInput({ body, context: { requestClass: 'compaction', agentId: 'child', parentAgentId: 'parent' } }));
    expect(result.context).toMatchObject({ requestClass: 'compaction', agentKind: 'subagent', querySource: 'compact' });
  });

  test.each([
    { headers: [['x-claude-code-request-class', 'main'], ['x-claude-code-agent-id', 'child']] },
    { context: { requestClass: 'subagent', agentKind: 'main', agentId: 'child' } },
    { headers: [['x-claude-code-request-class', 'subagent']] },
    { context: { sessionId: 'one' }, headers: [['x-claude-code-session-id', 'two']] },
    { headers: [['anthropic-version', '2023-06-01'], ['Anthropic-Version', '2023-06-01']] },
    { headers: [['x-claude-code-compaction', 'true'], ['X-Claude-Code-Compaction', 'false']] },
    { headers: [['x-name', 'bad\r\ninjection']] },
    { headers: [['x-claude-code-request-class', 'future-unknown']] },
  ])('冲突或无法保真的输入明确拒绝 %#', value => {
    expect(() => prepareInput(parseInput({ body, ...value }))).toThrow();
  });

  test('未知显式正文参数继续明确拒绝', () => {
    expect(() => parseInput({ ...body, top_p: 0.7 })).toThrow('top_p');
  });

  test('日志脱敏不改变参与发送的数据', () => {
    const original = { headers: [['Authorization', 'Bearer client-canary-credential']], body: { text: '引用 client-canary-credential', password: 'password-canary' } };
    const redactor = new Redactor(); redactor.register(original);
    const text = JSON.stringify(redactor.value(original));
    expect(text).not.toContain('client-canary-credential');
    expect(text).not.toContain('password-canary');
    expect(original.body.text).toBe('引用 client-canary-credential');
    expect(redactor.text('https://user:password@proxy.invalid')).not.toContain('password');
  });
});
