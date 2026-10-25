/** 验证 token 判定、完整历史摘要及目标边界，不请求外部模型。 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { SessionManager } from '@earendil-works/pi-coding-agent';
import { compactContext, contextTokens, DEFAULT_COMPACTION_THRESHOLD_TOKENS, freshContext,
  isContextLimit, requestMessages } from './context-policy.mjs';

const user = text => ({role: 'user', content: [{type: 'text', text}], timestamp: 1});
const assistant = (calls, tokens = 0) => ({role: 'assistant', api: 'openai-completions', provider: 'projects', model: 'test-model',
  content: calls.map(id => ({type: 'toolCall', id, name: 'account_state', arguments: {}})),
  stopReason: calls.length ? 'toolUse' : 'stop', timestamp: 2,
  usage: {input: 0, output: 0, cacheRead: tokens, cacheWrite: 0, totalTokens: tokens}});
const result = (id, text) => ({role: 'toolResult', toolCallId: id, toolName: 'account_state',
  content: [{type: 'text', text}], isError: false, timestamp: 3});

test('350K 判定包含缓存输入，错误和取消零用量不覆盖最后成功用量', () => {
  assert.equal(DEFAULT_COMPACTION_THRESHOLD_TOKENS, 350000);
  assert.equal(contextTokens([assistant([], 349999)]), 349999);
  const history = [assistant([], 350000), {...assistant([]), stopReason: 'aborted', timestamp: 3},
    {...assistant([]), stopReason: 'error', timestamp: 4}];
  assert.equal(contextTokens(history), 350000);
  const compacted = [{role: 'compactionSummary', summary: '当前目标与待办', timestamp: 5}, ...history];
  assert.ok(contextTokens(compacted, 100) < 200);
  assert.ok(contextTokens([...history, user('新增工具正文'.repeat(20))]) > 350000);
});

test('阈值以内保留完整业务正文，损坏工具历史仍按真实回执配对', () => {
  const material = '公开材料🧪'.repeat(12000);
  const page = result('material', JSON.stringify({content: material}));
  const history = [user('原目标'), assistant(['material']), page];
  assert.deepEqual(requestMessages(history), history);
  assert.equal(JSON.parse(requestMessages(history).at(-1).content[0].text).content, material);
  const invalid = [result('orphan', '未知结果'), assistant(['missing']), user('本轮要求')];
  assert.ok(requestMessages(invalid).every(message => message.role === 'user'));
});

test('分段摘要读取完整旧正文并保留近期工具，原文与同一会话仍可审计', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pi-token-summary-'));
  try {
    const manager = SessionManager.create(directory, directory);
    manager.appendMessage(user('ARCHIVED_BACKGROUND'.repeat(12000)));
    manager.appendMessage(assistant(['old']));
    manager.appendMessage(result('old', 'x'.repeat(60000) + 'CRITICAL_DECISION_AFTER_2000'));
    manager.appendMessage(assistant(['recent'], 350000));
    manager.appendMessage(result('recent', 'confirmed-operation'));
    manager.appendMessage({...assistant([]), stopReason: 'aborted'});
    const path = manager.getSessionFile(), id = manager.getSessionId();
    const chunks = [];
    const compacted = await compactContext(manager, {threshold: 350000, fixedTokens: 100}, async (messages, previous) => {
      chunks.push(messages[0].content[0].text);
      if (chunks.length > 1) assert.ok(previous);
      assert.equal(manager.getEntries().filter(entry => entry.type === 'compaction').length, 0);
      return '保留当前目标、已确认决定和待观察事项，不重发已投递输入。';
    }, new AbortController().signal);
    assert.ok(chunks.length > 1);
    assert.ok(chunks.join('').includes('CRITICAL_DECISION_AFTER_2000'));
    assert.ok(compacted.before_tokens >= 350000);
    assert.ok(compacted.after_tokens < 350000);
    const reopened = SessionManager.open(path, directory);
    assert.equal(reopened.getSessionId(), id);
    const projected = JSON.stringify(reopened.buildSessionContext().messages);
    assert.ok(!projected.includes('ARCHIVED_BACKGROUND'));
    assert.ok(projected.includes('已确认决定'));
    assert.ok(projected.includes('confirmed-operation'));
    assert.ok((await readFile(path, 'utf8')).includes('CRITICAL_DECISION_AFTER_2000'));
    freshContext(reopened);
    assert.ok(!JSON.stringify(reopened.buildSessionContext().messages).includes('confirmed-operation'));
    assert.ok((await readFile(path, 'utf8')).includes('confirmed-operation'));
  } finally { await rm(directory, {recursive: true, force: true}); }
});

test('未到阈值不调用摘要，摘要失败或取消不能发布半成品检查点', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pi-token-summary-failure-'));
  try {
    const manager = SessionManager.create(directory, directory);
    manager.appendMessage(user('需要保留的旧事实'.repeat(20000)));
    manager.appendMessage(assistant([], 349999));
    const path = manager.getSessionFile();
    const before = await readFile(path, 'utf8');
    assert.equal(await compactContext(manager, {threshold: 350000}, () => assert.fail(), new AbortController().signal), null);
    await assert.rejects(compactContext(manager, {threshold: 350000, force: true}, async () => {
      throw new Error('合成摘要失败');
    }, new AbortController().signal), /合成摘要失败/);
    assert.equal(await readFile(path, 'utf8'), before);
    await assert.rejects(compactContext(manager, {threshold: 350000, force: true, deadline: Date.now() - 1},
      () => assert.fail('原截止时间已过，不能再调用摘要模型'), new AbortController().signal), /时限已到/);
    assert.equal(await readFile(path, 'utf8'), before);
    const stopped = new AbortController();
    await assert.rejects(compactContext(manager, {threshold: 350000, force: true}, async () => {
      stopped.abort(); return '未完成的摘要';
    }, stopped.signal));
    assert.equal(await readFile(path, 'utf8'), before);
  } finally { await rm(directory, {recursive: true, force: true}); }
});

test('上下文识别只匹配真实400或413拒绝，认证、409和正文提及不误判', () => {
  const errorMessage = '400 The input token count exceeds the maximum number of tokens allowed 1048576.';
  const failure = {stopReason: 'error', errorMessage};
  assert.ok(isContextLimit(failure, {status: 400}));
  assert.ok(isContextLimit(failure, null));
  for (const status of [200, 401, 403, 409, 500]) assert.equal(isContextLimit(failure, {status}), false);
  assert.equal(isContextLimit({...failure, stopReason: 'stop'}, {status: 400}), false);
  assert.equal(isContextLimit({...failure, errorMessage: '400 invalid request maximum context length'}, {status: 400}), false);
});
