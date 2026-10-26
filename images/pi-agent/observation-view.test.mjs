/** 验证真实终端内容的可还原增量、基线恢复及字段保留。 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ObservationView } from './observation-view.mjs';

/**
 * 按模型收到的行片段恢复原画面。
 * @param {string} before 基线原文。
 * @param {object} result 真实投影回执。
 * @return {string} 恢复的画面。
 */
function restore(before, result) {
  if (result.screen_mode === 'full') return result.screen;
  if (result.screen_mode === 'unchanged') return before;
  const lines = before.split('\n');
  lines.splice(result.screen_patch.start_line, result.screen_patch.delete_count, ...result.screen_patch.lines);
  return lines.join('\n');
}

test('大画面增量可还原，新增事件和完整原始对象保留', () => {
  const view = new ObservationView();
  const before = Array.from({length: 120}, (_, i) => `真实业务行 ${i} ${'正文'.repeat(10)}`).join('\n') + '\n';
  assert.equal(view.project({observation_id: 'one', screen: before}).screen_mode, 'full');
  const after = before.replace('真实业务行 60', '菜单：请选择兼容方式 60');
  const raw = {observation_id: 'two', screen: after, events: [{role: 'assistant', text: '请确认'}],
    interactions: [{tool: 'AskUserQuestion'}], cursor: 42, running: true, terminal_ready: true};
  const result = view.project(raw);
  assert.equal(result.screen_mode, 'patch');
  assert.equal(result.screen_base_observation_id, 'one');
  assert.equal(restore(before, result), after);
  assert.equal(raw.screen, after);
  assert.equal(result.events, raw.events);
  assert.equal(result.interactions, raw.interactions);
  assert.ok(JSON.stringify(result).length < JSON.stringify(raw).length / 10);
});

test('相同画面省去正文，完整读取和上下文重置恢复整屏', () => {
  const view = new ObservationView();
  view.project({observation_id: 'one', screen: '菜单\n❯ 选择'});
  const same = view.project({observation_id: 'two', screen: '菜单\n❯ 选择'});
  assert.equal(same.screen_mode, 'unchanged');
  assert.equal(same.screen_base_observation_id, 'one');
  assert.equal('screen' in same, false);
  assert.equal(view.project({observation_id: 'three', screen: '菜单\n❯ 选择'}, true).screen_mode, 'full');
  view.reset();
  assert.equal(view.project({observation_id: 'four', screen: '菜单\n❯ 选择'}).screen_mode, 'full');
});

test('删除、增加和尾部换行都能精确恢复，小差异元数据过大时退回整屏', () => {
  const cases = [['a\n'.repeat(200), 'a\n'.repeat(100)], ['a\n'.repeat(100), 'a\n'.repeat(200)],
    ['a\n'.repeat(200), 'a\n'.repeat(200) + '末行'], ['a\n'.repeat(200), 'a\n'.repeat(199) + 'a'], ['a', 'b']];
  for (const [before, after] of cases) {
    const view = new ObservationView();
    view.project({observation_id: 'one', screen: before});
    const result = view.project({observation_id: 'two', screen: after});
    assert.equal(restore(before, result), after);
  }
  const view = new ObservationView();
  view.project({observation_id: 'one', screen: 'a'});
  assert.equal(view.project({observation_id: 'two', screen: 'b'}).screen_mode, 'full');
});

test('拒绝或非法观察不推进基线', () => {
  const view = new ObservationView();
  view.project({observation_id: 'one', screen: '已确认的画面'});
  const invalid = {status: 'rejected', message: '当前工作已变化'};
  assert.equal(view.project(invalid), invalid);
  assert.equal(view.project({observation_id: 'two', screen: '已确认的画面'}).screen_base_observation_id, 'one');
});
