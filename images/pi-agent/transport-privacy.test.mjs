/** 隔离执行候选实际响应投影，验证请求与响应正文完全不被读取。 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';

test('真实投影只读取受控响应头并恢复原fetch，不读取请求头和两侧正文', async () => {
  const source = await readFile(new URL('./host.mjs', import.meta.url), 'utf8');
  const start = source.indexOf('function providerResponses(config) {');
  const end = source.indexOf('\n/**', start);
  assert.ok(start >= 0 && end > start);
  const readHeaders = [];
  let forbiddenReads = 0;
  const forbidden = () => { forbiddenReads += 1; throw new Error('禁止读取正文或请求头'); };
  const response = {status: 409, headers: {get(name) {
    readHeaders.push(name);
    if (name === 'x-should-retry') return 'false';
    if (name === 'retry-after') return '120';
    throw new Error('禁止投影其它响应头');
  }}, get body() { return forbidden(); }, get text() { return forbidden(); }};
  const request = {url: 'http://127.0.0.1:9876/v1/chat/completions',
    get headers() { return forbidden(); }, get body() { return forbidden(); }};
  const options = {get headers() { return forbidden(); }, get body() { return forbidden(); }};
  const original = async (selected, selectedOptions) => {
    assert.equal(selected, request); assert.equal(selectedOptions, options); return response;
  };
  const globalObject = {fetch: original};
  const factory = runInNewContext(source.slice(start, end) + '\nproviderResponses',
    {globalThis: globalObject, URL, Date, Number});
  const transport = factory({base_url: 'http://127.0.0.1:9876/v1'});
  assert.notEqual(globalObject.fetch, original);
  assert.equal(await globalObject.fetch(request, options), response);
  assert.deepEqual(JSON.parse(JSON.stringify(transport.current())),
    {status: 409, should_retry: false, retry_after_ms: 120000, retry_after_valid: true});
  assert.deepEqual(readHeaders, ['x-should-retry', 'retry-after']);
  assert.equal(forbiddenReads, 0);
  transport.reset(); assert.equal(transport.current(), null);
  transport.restore(); assert.equal(globalObject.fetch, original);
});
