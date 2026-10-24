/** 使用实际宿主分类器验证临时错误覆盖与硬错误边界，不发网络请求。 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';

const source = await readFile(new URL('./host.mjs', import.meta.url), 'utf8');
const start = source.indexOf('function unavailable(message, response) {');
const end = source.indexOf('\n/**', start);
assert.ok(start >= 0 && end > start);
const classify = runInNewContext(source.slice(start, end) + '\nunavailable', {Number});
const message = errorMessage => ({stopReason: 'error', errorMessage});
const response = (status, overrides = {}) => ({status, should_retry: null,
  retry_after_ms: null, retry_after_valid: true, ...overrides});

test('实际HTTP类别覆盖全部服务端错误、超时、限流及冲突，不靠少量错误码逐个补漏', () => {
  for (let status = 400; status <= 599; status += 1) {
    const expected = status === 402 ? 'quota' : status === 409 ? 'conflict'
      : [408, 425, 429].includes(status) || status >= 500 ? 'transient' : null;
    assert.equal(classify(message(`${status} status code (no body)`), response(status)), expected, String(status));
  }
});

test('服务端明确允许恢复可覆盖其它临时状态，权限、端点和请求硬错误始终优先', () => {
  assert.equal(classify(message('400 Temporary server contention'), response(400, {should_retry: true})), 'transient');
  assert.equal(classify(message('499 Temporary server contention'), response(499, {should_retry: true})), 'transient');
  for (const status of [401, 403, 404, 405, 406, 410, 413, 414, 415, 422]) {
    assert.equal(classify(message(`${status} status code (no body)`), response(status, {should_retry: true})), null);
  }
  for (const detail of ['authentication failed', 'invalid_api_key', 'api key expired', 'invalid request',
    'maximum context length exceeded', 'content_filter', 'content_policy_violation', 'safety rejection']) {
    assert.equal(classify(message(`503 ${detail}`), response(503, {should_retry: true})), null, detail);
    assert.equal(classify(message(`409 ${detail}`), response(409, {should_retry: true})), null, detail);
  }
});

test('只对明确不可用的模型开放备用模型，不把错误端点或权限问题当成模型缺失', () => {
  for (const detail of ['model_not_found', 'invalid_model', 'unknown model', 'Model primary does not exist']) {
    assert.equal(classify(message(`404 ${detail}`), response(404)), 'model', detail);
    assert.equal(classify(message(`401 ${detail}`), response(401)), null, detail);
    assert.equal(classify(message(`404 ${detail}`), response(404, {should_retry: false})), null, detail);
  }
  assert.equal(classify(message('404 endpoint not found'), response(404)), null);
});

test('显式禁止重试和无效等待均不会被临时错误状态覆盖', () => {
  for (const status of [408, 409, 425, 429, 500, 529, 599]) {
    assert.equal(classify(message(`${status} unavailable`), response(status, {should_retry: false})), null);
    assert.equal(classify(message(`${status} unavailable`), response(status, {retry_after_valid: false})), null);
  }
});

test('网络及断流可恢复，取消、成功正文和未经HTTP响应补证的409不误恢复', () => {
  for (const detail of ['Provider finish_reason: network_error', 'Connection error.', 'Request timed out.',
    'fetch failed', 'socket hang up', 'ECONNRESET', 'ETIMEDOUT', 'EAI_AGAIN']) {
    assert.equal(classify(message(detail), null), 'transient', detail);
  }
  assert.equal(classify(message('409 status code (no body)'), null), null);
  assert.equal(classify(message('A business log mentions 503 but has no HTTP failure'), response(200)), null);
  assert.equal(classify({stopReason: 'stop', errorMessage: '503'}, response(503)), null);
  assert.equal(classify({stopReason: 'aborted', errorMessage: 'Connection error.'}, null), null);
});
