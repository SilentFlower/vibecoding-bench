/** 使用本地流式上游验证真实 Pi SDK 的工具执行、恢复和取消，不调用外部模型。 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile, mkdir, stat, symlink } from 'node:fs/promises';
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
 * @param {Function} onEvent 协议事件处理器。
 * @return {Promise<Array<object>>} 实际协议事件。
 */
async function execute(config, onTool, onEvent = () => {}) {
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
      onEvent(event, value => process.stdin.write(JSON.stringify(value) + '\n'));
    }
  });
  const timer = setTimeout(() => process.kill('SIGKILL'), 120000);
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


test('上游内容过滤准确分类且不重试、不切模型、不执行失败响应中的工具', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'projects-pi-filter-'));
  const models = [];
  const server = createServer(async (request, response) => {
    let body = ''; for await (const chunk of request) body += chunk;
    const value = JSON.parse(body); models.push(value.model);
    response.writeHead(200, {'content-type': 'text/event-stream'});
    // 即使失败响应包含完整工具参数，过滤结束原因也必须阻止工具执行。
    for (const chunk of [
      {choices: [{index: 0, delta: {role: 'assistant', tool_calls: [{index: 0,
        id: 'call-filtered', type: 'function', function: {name: 'account_state', arguments: '{}'}}]}, finish_reason: null}]},
      {choices: [{index: 0, delta: {}, finish_reason: 'content_filter'}]},
      {choices: [], usage: {prompt_tokens: 11, completion_tokens: 7, total_tokens: 18}},
    ]) response.write('data: ' + JSON.stringify({id: 'chat-filter', object: 'chat.completion.chunk',
      model: value.model, created: 1, ...chunk}) + '\n\n');
    response.end('data: [DONE]\n\n');
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const records = await execute({session_dir: directory, base_url: `http://127.0.0.1:${server.address().port}/v1`,
      models: ['primary', 'secondary'], tools: [{name: 'account_state', description: '当前账号',
        parameters: {type: 'object', properties: {}, required: [], additionalProperties: false}}]},
      () => assert.fail('被过滤响应中的工具不得执行'));
    assert.deepEqual(models, ['primary']);
    assert.equal(records.filter(value => value.type === 'tool').length, 0);
    assert.equal(records.filter(value => value.type === 'error').length, 1);
    assert.equal(records.at(-1).type, 'error');
    assert.equal(records.at(-1).reason, 'provider_content_filter');
    assert.equal(records.at(-1).message, 'Pi 上游模型返回内容过滤，原工作已保留，需人工核对后恢复');
    assert.equal(records.findLast(value => value.type === 'assistant').stop_reason, 'error');
    const ready = records.find(value => value.type === 'ready');
    const messages = (await readFile(ready.session_file, 'utf8')).trim().split('\n')
      .map(line => JSON.parse(line)).filter(value => value.type === 'message');
    const failed = messages.findLast(value => value.message.role === 'assistant');
    assert.equal(failed.message.stopReason, 'error');
    assert.equal(failed.message.errorMessage, 'Provider finish_reason: content_filter');
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});

test('普通模型正文提及内容过滤不会产生错误分类', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'projects-pi-filter-text-'));
  let requests = 0;
  const server = createServer(async (request, response) => {
    for await (const chunk of request) { /* 仅消费本地合成请求，不访问真实模型。 */ }
    requests += 1;
    response.writeHead(200, {'content-type': 'text/event-stream'});
    for (const chunk of [
      {choices: [{index: 0, delta: {role: 'assistant', content: 'Provider finish_reason: content_filter'}, finish_reason: null}]},
      {choices: [{index: 0, delta: {}, finish_reason: 'stop'}]},
    ]) response.write('data: ' + JSON.stringify({id: 'chat-filter-text', object: 'chat.completion.chunk',
      model: 'test-model', created: 1, ...chunk}) + '\n\n');
    response.end('data: [DONE]\n\n');
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const records = await execute({session_dir: directory,
      base_url: `http://127.0.0.1:${server.address().port}/v1`, tools: []}, () => assert.fail());
    assert.equal(requests, 1);
    assert.equal(records.at(-1).type, 'settled');
    assert.equal(records.filter(value => value.type === 'error').length, 0);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});

test('已确认工具后的内容过滤保留会话且不重放工具或切换模型', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'projects-pi-filter-after-tool-'));
  const models = [];
  let toolCalls = 0;
  const server = createServer(async (request, response) => {
    let body = ''; for await (const chunk of request) body += chunk;
    const value = JSON.parse(body); models.push(value.model);
    if (models.length === 1) return stream(response, true);
    response.writeHead(200, {'content-type': 'text/event-stream'});
    response.write('data: ' + JSON.stringify({id: 'chat-filter-after-tool', object: 'chat.completion.chunk',
      model: value.model, created: 1,
      choices: [{index: 0, delta: {role: 'assistant'}, finish_reason: 'content_filter'}]}) + '\n\n');
    response.end('data: [DONE]\n\n');
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const records = await execute({session_dir: directory, base_url: `http://127.0.0.1:${server.address().port}/v1`,
      models: ['primary', 'secondary'], tools: [{name: 'account_state', description: '当前账号',
        parameters: {type: 'object', properties: {}, required: [], additionalProperties: false}}]},
    (event, send) => {
      toolCalls += 1;
      send({type: 'tool_result', id: event.id, result: {status: 'running'}});
    });
    assert.equal(toolCalls, 1);
    assert.deepEqual(models, ['primary', 'primary']);
    assert.equal(records.filter(value => value.type === 'tool').length, 1);
    assert.equal(records.at(-1).reason, 'provider_content_filter');
    const ready = records.find(value => value.type === 'ready');
    const messages = (await readFile(ready.session_file, 'utf8')).trim().split('\n')
      .map(line => JSON.parse(line)).filter(value => value.type === 'message').map(value => value.message);
    assert.equal(messages.filter(value => value.role === 'toolResult').length, 1);
    assert.equal(messages.findLast(value => value.role === 'assistant').errorMessage, 'Provider finish_reason: content_filter');
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});

test('单模型在已确认工具后遇到网络结束错误，真实续接且失败工具不执行', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pi-self-heal-network-'));
  const requests = [];
  const server = createServer(async (request, response) => {
    let body = ''; for await (const chunk of request) body += chunk;
    const value = JSON.parse(body); requests.push(value);
    if (requests.length === 1) return stream(response, true);
    if (requests.length === 2) {
      response.writeHead(200, {'content-type': 'text/event-stream'});
      const values = [
        {choices:[{index:0,delta:{role:'assistant',tool_calls:[{index:0,id:'failed-tool',type:'function',function:{name:'account_state',arguments:'{}'}}]},finish_reason:null}]},
        {choices:[{index:0,delta:{},finish_reason:'network_error'}]},
      ];
      for (const chunk of values) response.write('data: '+JSON.stringify({id:'network-error',object:'chat.completion.chunk',model:value.model,created:1,...chunk})+'\n\n');
      return response.end('data: [DONE]\n\n');
    }
    stream(response, false);
  });
  server.listen(0,'127.0.0.1'); await once(server,'listening');
  try {
    const records = await execute({session_dir:directory,base_url:'http://127.0.0.1:'+server.address().port+'/v1',tools:[{name:'account_state',description:'当前账号',parameters:{type:'object',properties:{}}}]}, (event,send)=>send({type:'tool_result',id:event.id,result:{confirmed:'真实结果'}}));
    assert.equal(records.at(-1).type,'settled',JSON.stringify(records));
    assert.equal(records.filter(value=>value.type==='tool').length,1);
    assert.equal(requests.length,3);
    assert.equal(requests[2].messages.filter(value=>value.role==='user').length,1);
    assert.equal(requests[2].messages.filter(value=>value.role==='tool').length,1);
    assert.ok(JSON.stringify(requests[2]).includes('真实结果'));
    assert.ok(!JSON.stringify(requests[2]).includes('failed-tool'));
    assert.equal(records.filter(value=>value.type==='recovery').length,2);
    const ready=records.find(value=>value.type==='ready');
    const transcript=await readFile(ready.session_file,'utf8');
    assert.ok(transcript.includes('Provider finish_reason: network_error'));
  } finally { server.closeAllConnections(); await new Promise(resolve=>server.close(resolve)); await rm(directory,{recursive:true,force:true}); }
});

test('跨轮记住成功模型且配置修订变化清除优先级', async()=>{
  const directory=await mkdtemp(join(tmpdir(),'pi-self-heal-sticky-'));
  const models=[];
  const server=createServer(async(request,response)=>{
    let body='';for await(const chunk of request)body+=chunk;const value=JSON.parse(body);models.push(value.model);
    if(value.model==='primary'){response.writeHead(503,{'content-type':'application/json'});return response.end(JSON.stringify({error:{message:'本地不可用'}}));}
    stream(response,false);
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  try{
    const config={session_dir:directory,base_url:'http://127.0.0.1:'+server.address().port+'/v1',models:['primary','secondary'],tools:[]};
    const first=await execute(config,()=>assert.fail());assert.equal(first.at(-1).type,'settled');
    const sessionFile=first.find(value=>value.type==='ready').session_file;
    const next=await execute({...config,session_file:sessionFile},()=>assert.fail());assert.equal(next.at(-1).type,'settled');
    assert.deepEqual(models,['primary','secondary','secondary']);
    const health=await readFile(join(directory,'.model-health.json'),'utf8');assert.ok(!health.includes('local-test-key'));assert.ok(!health.includes(config.base_url));
    await execute({...config,session_file:sessionFile,revision:'updated'},()=>assert.fail());
    assert.deepEqual(models,['primary','secondary','secondary','primary','secondary']);
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));await rm(directory,{recursive:true,force:true});}
});

test('原预算不足以退避时退出，新轮遵守冷却且不探测',async()=>{
  const directory=await mkdtemp(join(tmpdir(),'pi-self-heal-cooldown-'));let count=0;
  const server=createServer(async(request,response)=>{for await(const chunk of request){}count+=1;response.writeHead(503,{'content-type':'application/json'});response.end(JSON.stringify({error:{message:'本地不可用'}}));});
  server.listen(0,'127.0.0.1');await once(server,'listening');
  try{const config={session_dir:directory,base_url:'http://127.0.0.1:'+server.address().port+'/v1',timeout_sec:1,tools:[]};
    const first=await execute(config,()=>assert.fail());assert.equal(first.at(-1).reason,'model_unavailable');assert.equal(count,1);
    const second=await execute(config,()=>assert.fail());assert.equal(second.at(-1).reason,'model_unavailable');assert.ok(second.at(-1).retry_at>Date.now()/1000);assert.equal(count,1);
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));await rm(directory,{recursive:true,force:true});}
});

test('单模型首次 503 后本轮自动恢复，健康记录仅存哈希且权限受限', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pi-self-heal-single-'));
  let requests = 0;
  const server = createServer(async (request, response) => {
    for await (const chunk of request) { /* 消费本地请求。 */ }
    requests += 1;
    if (requests === 1) {
      response.writeHead(503, {'content-type': 'application/json'});
      return response.end(JSON.stringify({error: {message: '本地服务暂不可用'}}));
    }
    stream(response, false);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const records = await execute({session_dir: directory,
      base_url: `http://127.0.0.1:${server.address().port}/v1`, tools: []}, () => assert.fail());
    assert.equal(records.at(-1).type, 'settled');
    assert.equal(requests, 2);
    assert.deepEqual(records.filter(value => value.type === 'recovery').map(value => value.phase), ['retry', 'recovered']);
    const healthPath = join(directory, '.model-health.json');
    const health = JSON.parse(await readFile(healthPath, 'utf8'));
    assert.equal((await stat(healthPath)).mode & 0o777, 0o600);
    assert.equal(health.models['test-model'].cooldown_until, 0);
    assert.equal(health.preferred_model, 'test-model');
    assert.match(health.fingerprint, /^[a-f0-9]{64}$/);
    assert.ok(!JSON.stringify(health).includes('local-test-key'));
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});

test('已确认工具后的 HTTP 500 在原上下文续接，不重新追加用户要求', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pi-self-heal-after-tool-'));
  const requests = [];
  const server = createServer(async (request, response) => {
    let body = ''; for await (const chunk of request) body += chunk;
    const value = JSON.parse(body); requests.push(value);
    if (requests.length === 1) return stream(response, true);
    if (requests.length === 2) {
      response.writeHead(500, {'content-type': 'application/json'});
      return response.end(JSON.stringify({error: {message: '本地临时错误'}}));
    }
    stream(response, false);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const records = await execute({session_dir: directory,
      base_url: `http://127.0.0.1:${server.address().port}/v1`,
      tools: [{name: 'account_state', description: '当前账号', parameters: {type: 'object', properties: {}}}]},
      (event, send) => send({type: 'tool_result', id: event.id, result: {confirmed: '已落盘的工具结果'}}));
    assert.equal(records.at(-1).type, 'settled');
    assert.equal(records.filter(value => value.type === 'tool').length, 1);
    assert.equal(requests.length, 3);
    assert.equal(requests[2].messages.filter(value => value.role === 'user').length, 1);
    assert.equal(requests[2].messages.filter(value => value.role === 'tool').length, 1);
    assert.ok(JSON.stringify(requests[2]).includes('已落盘的工具结果'));
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});

test('退避等待时取消立即结束，取消后不继续请求任何模型', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pi-self-heal-abort-'));
  let requests = 0;
  let abortedAt;
  const server = createServer(async (request, response) => {
    for await (const chunk of request) { /* 消费本地请求。 */ }
    requests += 1;
    response.writeHead(503, {'content-type': 'application/json'});
    response.end(JSON.stringify({error: {message: '本地临时错误'}}));
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const records = await execute({session_dir: directory,
      base_url: `http://127.0.0.1:${server.address().port}/v1`, tools: []}, () => assert.fail(),
      (event, send) => {
        if (event.type === 'recovery') { abortedAt = Date.now(); send({type: 'abort'}); }
      });
    assert.equal(requests, 1);
    assert.ok(Date.now() - abortedAt < 1500);
    assert.equal(records.filter(value => value.type === 'settled').length, 0);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});

test('402 只向其它配置模型降级，认证和上下文硬错误均不隐式压缩重试', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pi-self-heal-hard-errors-'));
  const models = [];
  let status = 402;
  let detail = '本地额度不足';
  const server = createServer(async (request, response) => {
    let body = ''; for await (const chunk of request) body += chunk;
    const value = JSON.parse(body); models.push(value.model);
    if (value.model === 'secondary') return stream(response, false);
    response.writeHead(status, {'content-type': 'application/json'});
    response.end(JSON.stringify({error: {message: detail}}));
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const config = {session_dir: directory, models: ['primary', 'secondary'],
      base_url: `http://127.0.0.1:${server.address().port}/v1`, tools: []};
    const fallback = await execute(config, () => assert.fail());
    assert.equal(fallback.at(-1).type, 'settled');
    assert.deepEqual(models, ['primary', 'secondary']);
    models.length = 0;
    const alone = await execute({...config, session_dir: join(directory, 'quota-only'), models: ['primary']}, () => assert.fail());
    assert.equal(alone.at(-1).reason, 'model_unavailable');
    assert.deepEqual(models, ['primary']);
    for (const value of [401, 403, 404, 400]) {
      models.length = 0; status = value;
      detail = value === 400 ? 'maximum context length exceeded; 503 mentioned in body' : '本地硬错误';
      const records = await execute({...config, session_dir: join(directory, `hard-${value}`)}, () => assert.fail());
      assert.equal(records.at(-1).type, 'error');
      assert.equal(records.filter(event => event.type === 'recovery').length, 0);
      assert.deepEqual(models, ['primary']);
    }
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});

test('健康文件链接不会被跟随或覆盖，停止前不向模型发出请求', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pi-self-heal-link-'));
  const target = join(directory, 'protected.json');
  await writeFile(target, '{"protected":true}');
  await symlink(target, join(directory, '.model-health.json'));
  try {
    const records = await execute({session_dir: directory, base_url: 'http://127.0.0.1:1/v1', tools: []}, () => assert.fail());
    assert.equal(records.at(-1).type, 'error');
    assert.equal(records.filter(value => value.type === 'ready').length, 0);
    assert.equal(await readFile(target, 'utf8'), '{"protected":true}');
  } finally { await rm(directory, {recursive: true, force: true}); }
});

test('八个候选中的最后一个可用时仍有恢复机会，整体次数受限', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pi-self-heal-eight-'));
  const configured = Array.from({length: 8}, (_, index) => `candidate-${index + 1}`);
  const requested = [];
  const server = createServer(async (request, response) => {
    let body = ''; for await (const chunk of request) body += chunk;
    const value = JSON.parse(body); requested.push(value.model);
    if (value.model === configured.at(-1)) return stream(response, false);
    response.writeHead(503, {'content-type': 'application/json'});
    response.end(JSON.stringify({error: {message: '本地候选暂不可用'}}));
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const records = await execute({session_dir: directory, models: configured, timeout_sec: 120,
      base_url: `http://127.0.0.1:${server.address().port}/v1`, tools: []}, () => assert.fail());
    assert.equal(records.at(-1).type, 'settled');
    assert.deepEqual(requested, configured);
    assert.equal(records.filter(value => value.type === 'recovery' && value.phase !== 'recovered').length, 7);
    assert.equal(records.findLast(value => value.type === 'recovery').attempt, 7);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});

test('单模型持续 503 仅恢复三次，耗尽后返回冷却原因且不形成请求风暴', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pi-self-heal-exhausted-'));
  let requests = 0;
  const server = createServer(async (request, response) => {
    for await (const chunk of request) { /* 消费本地请求。 */ }
    requests += 1;
    response.writeHead(503, {'content-type': 'application/json'});
    response.end(JSON.stringify({error: {message: '本地服务持续不可用'}}));
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const records = await execute({session_dir: directory, timeout_sec: 60,
      base_url: `http://127.0.0.1:${server.address().port}/v1`, tools: []}, () => assert.fail());
    assert.equal(requests, 4);
    assert.deepEqual(records.filter(value => value.type === 'recovery').map(value => value.attempt), [1, 2, 3]);
    assert.equal(records.at(-1).reason, 'model_unavailable');
    assert.ok(records.at(-1).retry_at > Date.now() / 1000);
    assert.ok(records.at(-1).retry_at <= Date.now() / 1000 + 301);
    assert.equal(records.filter(value => value.type === 'settled').length, 0);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await rm(directory, {recursive: true, force: true}); }
});
