/** 使用本地流式上游验证真实 Pi SDK 的工具执行、恢复和取消，不调用外部模型。 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';

/**
 * 返回 OpenAI 兼容的实际流式文本或工具调用。
 * @param {object} response HTTP 响应。
 * @param {boolean} tool 是否请求工具。
 * @return {void}
 */
function stream(response, tool) {
  response.writeHead(200, {'content-type': 'text/event-stream'});
  const delta = tool ? {role: 'assistant', tool_calls: [{index: 0, id: 'call-account', type: 'function',
    function: {name: 'account_state', arguments: '{}'}}]} : {role: 'assistant', content: '账号已核对，原会话继续。'};
  for (const value of [
    {choices: [{index: 0, delta, finish_reason: null}]},
    {choices: [{index: 0, delta: {}, finish_reason: tool ? 'tool_calls' : 'stop'}]},
    {choices: [], usage: {prompt_tokens: 11, completion_tokens: 7, total_tokens: 18}},
  ]) response.write('data: ' + JSON.stringify({id: 'chat-test', object: 'chat.completion.chunk',
    model: 'test-model', created: 1, ...value}) + '\n\n');
  response.end('data: [DONE]\n\n');
}

/**
 * 启动真实入口并与其交换父进程工具协议。
 * @param {object} config 启动配置。
 * @param {Function} onTool 工具处理器。
 * @return {Promise<Array<object>>} 实际协议事件。
 */
async function execute(config, onTool) {
  const process = spawn('node', ['host.mjs'], {cwd: import.meta.dirname, stdio: ['pipe', 'pipe', 'pipe']});
  const records = [];
  let buffer = '', errors = '';
  process.stdout.setEncoding('utf8'); process.stderr.setEncoding('utf8');
  process.stderr.on('data', chunk => { errors += chunk; });
  process.stdout.on('data', chunk => {
    buffer += chunk;
    let boundary;
    while ((boundary = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 1);
      if (!line.trim()) continue;
      const event = JSON.parse(line); records.push(event);
      if (event.type === 'tool') onTool(event, value => process.stdin.write(JSON.stringify(value) + '\n'));
    }
  });
  const timer = setTimeout(() => process.kill('SIGKILL'), 15000);
  process.stdin.write(JSON.stringify({type: 'configure', api_key: 'local-test-key', models: ['test-model'],
    instructions: '通过 account_state 核对账号。', prompt: '继续原任务', ...config}) + '\n');
  const [code] = await once(process, 'exit'); clearTimeout(timer);
  assert.equal(code, 0, errors);
  return records;
}

test('真实工具调用与明确原会话恢复，禁用宿主默认工具及自动扩展', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'projects-pi-sdk-'));
  const requests = [];
  const server = createServer(async (request, response) => {
    let body = ''; for await (const chunk of request) body += chunk;
    const value = JSON.parse(body); requests.push(value);
    assert.equal(request.headers.authorization, 'Bearer local-test-key');
    assert.deepEqual(value.tools.map(tool => tool.function.name), ['account_state']);
    stream(response, !value.messages.some(message => message.role === 'tool'));
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    await mkdir(join(directory, '.pi/extensions'), {recursive: true});
    await writeFile(join(directory, '.pi/extensions/malicious.mjs'), "throw new Error('不得加载项目扩展');");
    await writeFile(join(directory, 'AGENTS.md'), 'HOST_CONTEXT_MUST_NOT_ENTER_MODEL');
    const config = {session_dir: directory, base_url: `http://127.0.0.1:${server.address().port}/v1`,
      tools: [{name: 'account_state', description: '当前账号', parameters: {
        type: 'object', properties: {}, required: [], additionalProperties: false}}]};
    const records = await execute(config, (event, send) => {
      assert.equal(event.name, 'account_state');
      send({type: 'tool_result', id: event.id, result: {account_id: 17, status: 'running'}});
    });
    assert.equal(records.at(-1).type, 'settled', JSON.stringify(records));
    assert.equal(records.filter(value => value.type === 'tool').length, 1);
    const ready = records.find(value => value.type === 'ready');
    assert.ok((await readFile(ready.session_file, 'utf8')).includes('account_state'));
    assert.ok(!JSON.stringify(requests).includes('HOST_CONTEXT_MUST_NOT_ENTER_MODEL'));
    const resumed = await execute({...config, session_file: ready.session_file}, () => assert.fail('原工具不得重发'));
    assert.equal(resumed.find(value => value.type === 'ready').session_id, ready.session_id);
    assert.equal(resumed.at(-1).type, 'settled');
    assert.equal(requests.length, 3);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});

test('工具等待期间取消 Pi，不再发起下一次模型请求', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'projects-pi-abort-'));
  let requests = 0;
  const server = createServer(async (request, response) => {
    for await (const chunk of request) { /* 消费本地请求后提供确定的工具调用。 */ }
    requests += 1; stream(response, true);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const records = await execute({session_dir: directory, base_url: `http://127.0.0.1:${server.address().port}/v1`,
      tools: [{name: 'account_state', description: '等待', parameters: {type: 'object', properties: {}}}]},
      (event, send) => send({type: 'abort'}));
    assert.equal(requests, 1);
    assert.equal(records.filter(value => value.type === 'tool').length, 1);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});

test('明确额度错误有限降级，认证错误不通过更换模型掩盖', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'projects-pi-fallback-'));
  const models = [];
  let status = 429;
  const server = createServer(async (request, response) => {
    let body = ''; for await (const chunk of request) body += chunk;
    const value = JSON.parse(body); models.push(value.model);
    if (value.model === 'primary') {
      response.writeHead(status, {'content-type': 'application/json'});
      response.end(JSON.stringify({error: {message: '本地合成服务拒绝', type: 'test', code: status}}));
    } else stream(response, false);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const config = {session_dir: directory, base_url: `http://127.0.0.1:${server.address().port}/v1`,
      models: ['primary', 'secondary'], tools: []};
    const fallback = await execute(config, () => assert.fail('本轮不应调用工具'));
    assert.equal(fallback.at(-1).type, 'settled');
    assert.deepEqual(models, ['primary', 'secondary']);
    models.length = 0; status = 401;
    const denied = await execute({...config, session_dir: join(directory, 'unauthorized')}, () => assert.fail());
    assert.equal(denied.at(-1).type, 'error');
    assert.deepEqual(models, ['primary']);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});
