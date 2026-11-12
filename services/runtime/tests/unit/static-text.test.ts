import { expect, test } from 'bun:test';
import { staticTextFits } from '../../src/runtime/293/static-text';

test('静态正文预算同时计算 UTF-8 文本与条件键', () => {
  expect(staticTextFits('你好', ['模型', true])).toBe(true);
  expect(staticTextFits('测'.repeat(21_844), [])).toBe(true);
  expect(staticTextFits('测'.repeat(21_845), [])).toBe(false);
  expect(staticTextFits('x'.repeat(32_768), ['y'.repeat(32_768)])).toBe(false);
});

test('超限文本和条件不进入单项缓存，空文本是合法结果', () => {
  expect(staticTextFits('', [])).toBe(true);
  expect(staticTextFits('x'.repeat(65_536), [])).toBe(false);
  expect(staticTextFits('', ['测'.repeat(21_845)])).toBe(false);
});
