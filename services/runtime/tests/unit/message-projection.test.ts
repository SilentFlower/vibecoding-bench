import { expect, test } from 'bun:test';
import { ensureMessages } from '../../src/runtime/293/job';
import type { NativeMessage } from '../../src/runtime/293/native';
import type { ApiMessage } from '../../src/shared/contracts';

const reminders = ['<system-reminder>原生附件一</system-reminder>', '<system-reminder>原生附件二</system-reminder>'];
const metadata: NativeMessage[] = reminders.map((text, i) => ({ type: 'user', uuid: String(i), message: { role: 'user', content: [{ type: 'text', text }] } }));
const business: ApiMessage[] = [{ role: 'user', content: 'q' }, { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_one', name: 'lookup', input: {} }] }, { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_one', content: 'ready' }] }];
const output = () => [{ role: 'user', content: [{ type: 'text', text: 'q' }] }, business[1]!, { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_one', content: 'ready\n\n' + reminders.join('\n\n') }] }];

test('原生提醒合入工具结果时仍逐块验证业务前缀及完整附件', () => {
  expect(() => ensureMessages(business, metadata, output())).not.toThrow();
  expect(() => ensureMessages(business, metadata, business)).toThrow('完整');
  const changed = output(); (changed[2]!.content as { content: string }[])[0]!.content = 'changed\n\n' + reminders.join('\n\n');
  expect(() => ensureMessages(business, metadata, changed)).toThrow();
  const injected = output(); (injected[2]!.content as { content: string }[])[0]!.content += '\n\n<system-reminder>未知注入</system-reminder>';
  expect(() => ensureMessages(business, metadata, injected)).toThrow();
});

test('数组工具结果的额外提醒可关联，业务块被删改仍拒绝', () => {
  const extra = output();
  (extra[2]!.content as { content: unknown }[])[0]!.content = [{ type: 'text', text: 'ready' }, { type: 'text', text: reminders.join('\n\n') }];
  expect(() => ensureMessages(business, metadata, extra)).not.toThrow();
  (extra[2]!.content as { content: unknown }[])[0]!.content = [{ type: 'text', text: reminders.join('\n\n') }];
  expect(() => ensureMessages(business, metadata, extra)).toThrow();
});

test('无其他附件时 Environment 的已知提升表示可核验，未知 system 不能混入', () => {
  const environment = '# Environment\n原生环境';
  const native: NativeMessage[] = [{ type: 'user', uuid: 'env', message: { role: 'user', content: [{ type: 'text', text: '<system-reminder>\n' + environment + '\n</system-reminder>' }] } }];
  expect(() => ensureMessages(business, native, [...business, { role: 'system', content: [{ type: 'text', text: environment }] }])).not.toThrow();
  expect(() => ensureMessages(business, native, [...business, { role: 'system', content: [{ type: 'text', text: '未知环境' }] }])).toThrow();
});
