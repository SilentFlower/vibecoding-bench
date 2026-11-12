import { expect, test } from 'bun:test';
import { createHash } from 'node:crypto';
import ts from 'typescript';
import { rewriteStaticText } from '../../scripts/runtime/static-prompts';
import type { StaticTextRule } from '../../scripts/runtime/static-prompts';
import { staticTextFits } from '../../src/runtime/293/static-text';

const source = 'function render(model){counts.formats++;return [style(model),enabled()?"已开":"已关"].join("|");}';
const rule: StaticTextRule = {
  sha256: createHash('sha256').update(source).digest('hex'),
  reads: [{ call: 'style(model)', value: 'style(model)' }, { call: 'enabled()', value: 'enabled()' }],
  key: ['__ccrb_static_dep0', '__ccrb_static_dep1'],
};

function transform(text: string, value: StaticTextRule = rule): string {
  const tree = ts.createSourceFile('fixture.js', text, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
  const result = rewriteStaticText(tree, { render: value }, {});
  let rewritten = text;
  for (const change of result.changes.sort((a, b) => b.start - a.start)) rewritten = rewritten.slice(0, change.start) + change.text + rewritten.slice(change.end);
  return result.declarations.join('\n') + '\n' + rewritten;
}

test('静态工厂命中仍读取当前条件，模型和功能变化保持原生正文', () => {
  const counts = { formats: 0, style: 0, enabled: 0 };
  const state = { enabled: false, fail: false };
  const style = (model: string): string => { counts.style++; if (state.fail) throw new Error('合成条件读取失败'); return model === 'one' ? '甲' : '乙'; };
  const enabled = (): boolean => { counts.enabled++; return state.enabled; };
  const render = new Function('counts', 'style', 'enabled', '__ccrb_static_fits', transform(source) + ';return render;')(counts, style, enabled, staticTextFits) as (model: string) => string;
  expect(render('one')).toBe('甲|已关');
  expect(render('one')).toBe('甲|已关');
  expect(counts).toEqual({ formats: 1, style: 2, enabled: 2 });
  expect(render('two')).toBe('乙|已关');
  state.enabled = true;
  expect(render('one')).toBe('甲|已开');
  expect(counts).toEqual({ formats: 3, style: 4, enabled: 4 });
  state.fail = true;
  expect(() => render('one')).toThrow('条件读取失败');
  expect(counts.formats).toBe(3);
});

test('正文外的动态段落与钩子逐次运行，缓存不保留整份请求', () => {
  const counts = { formats: 0 };
  const render = new Function('counts', 'style', 'enabled', '__ccrb_static_fits', transform(source) + ';return render;')(counts, () => '固定', () => false, staticTextFits) as (model: string) => string;
  let hooks = 0;
  const request = (session: string): string => render('one') + '|会话=' + session + '|钩子=' + ++hooks;
  expect(request('A')).toBe('固定|已关|会话=A|钩子=1');
  expect(request('B')).toBe('固定|已关|会话=B|钩子=2');
  expect(request('A')).toBe('固定|已关|会话=A|钩子=3');
  expect(counts.formats).toBe(1);
});

test('静态格式化失败与超限结果不会被保存', () => {
  const text = source.replace('counts.formats++;', 'counts.formats++;if(counts.fail)throw new Error("合成格式化失败");');
  const changed = { ...rule, sha256: createHash('sha256').update(text).digest('hex') };
  const counts = { formats: 0, fail: true };
  let large = false;
  const render = new Function('counts', 'style', 'enabled', '__ccrb_static_fits', transform(text, changed) + ';return render;')(counts, () => large ? '测'.repeat(30_000) : '正常', () => false, staticTextFits) as (model: string) => string;
  expect(() => render('one')).toThrow('合成格式化失败');
  counts.fail = false;
  expect(render('one')).toBe('正常|已关');
  expect(render('one')).toBe('正常|已关');
  expect(counts.formats).toBe(2);
  large = true;
  render('one'); render('one');
  expect(counts.formats).toBe(4);
  large = false;
  expect(render('one')).toBe('正常|已关');
  expect(counts.formats).toBe(4);
});

test('静态转换拒绝函数摘要、依赖位置和辅助函数漂移', () => {
  expect(() => transform(source + ' ', { ...rule, sha256: '0'.repeat(64) })).toThrow('工厂不匹配');
  expect(() => transform(source, { ...rule, reads: [{ call: 'missing()', value: 'missing()' }] })).toThrow('条件读取不匹配');
  const tree = ts.createSourceFile('fixture.js', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
  expect(() => rewriteStaticText(tree, { render: rule }, { missing: '0'.repeat(64) })).toThrow('辅助函数不匹配');
});

test('静态转换拒绝异步、生成器和构建绑定冲突', () => {
  for (const text of ['async function render(){return "value";}', 'function* render(){yield "value";}']) {
    expect(() => transform(text, { sha256: createHash('sha256').update(text).digest('hex'), reads: [], key: [] })).toThrow('工厂不匹配');
  }
  expect(() => transform(source + ';const __ccrb_static_text = null;')).toThrow('名称冲突');
});
