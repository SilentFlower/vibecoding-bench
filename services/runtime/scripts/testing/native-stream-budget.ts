/** 隔离回环验证SDK首响应预算、完整长流与真实取消；使用合成凭据，不产生真实模型调用。 */
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { connect } from 'node:net';
import { randomUUID, createHash } from 'node:crypto';
import { strict as assert } from 'node:assert';
import { PrivateProcess } from './pool-process';
import { decodeWorkerFrame } from '../../src/shared/protocol';

if (process.env.CCRB_PROBE_ISOLATED !== '1') {
  const child = Bun.spawn(['unshare', '--net', process.execPath, import.meta.path], { env: { ...process.env, CCRB_PROBE_ISOLATED: '1' }, stdout: 'inherit', stderr: 'inherit' });
  process.exit(await child.exited);
}
assert.equal(Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode, 0);
const root = await mkdtemp(join(tmpdir(), 'native-first-byte-probe-'));
const binary = process.env.CCRB_PROBE_BINARY;
const expectedSha = process.env.CCRB_PROBE_BINARY_SHA;
if (!binary || !expectedSha || !/^[a-f0-9]{64}$/.test(expectedSha)) throw new Error('必须指定待验收二进制与固定SHA256');
assert.equal(createHash('sha256').update(await readFile(binary)).digest('hex'), expectedSha);
const key = join(root, 'key.pem'), cert = join(root, 'cert.pem');
assert.equal(Bun.spawnSync(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', cert, '-days', '1', '-subj', '/CN=api.anthropic.com', '-addext', 'subjectAltName=DNS:api.anthropic.com'], { stdout: 'pipe', stderr: 'pipe' }).exitCode, 0);
const duration = Number(process.env.CCRB_PROBE_DURATION_MS ?? '22000');
let submissions = 0, ticks = 0;
const timers = new Set<ReturnType<typeof setInterval>>();
const server = Bun.serve({hostname:'127.0.0.1',port:0,tls:{key:Bun.file(key),cert:Bun.file(cert)},idleTimeout:0,
  async fetch(request) {
    assert.equal(new URL(request.url).pathname,'/v1/messages');
    await request.arrayBuffer(); submissions++;
    const started = performance.now();
    return new Response(new ReadableStream({start(controller) {
      controller.enqueue(Buffer.from('event: message_start\ndata: {"type":"message_start","message":{"id":"msg_synthetic","type":"message","role":"assistant","model":"claude-sonnet-4-6","content":[],"stop_reason":null,"usage":{"input_tokens":1,"output_tokens":0}}}\n\n'));
      const timer = setInterval(() => {
        try {
          ticks++;
          if (performance.now()-started >= duration) {
            clearInterval(timer); timers.delete(timer);
            controller.enqueue(Buffer.from('event: message_stop\ndata: {"type":"message_stop"}\n\n')); controller.close();
          } else controller.enqueue(Buffer.from('event: ping\ndata: {"type":"ping"}\n\n'));
        } catch {clearInterval(timer);timers.delete(timer);}
      },1000);timers.add(timer);
    },cancel() {}}),{headers:{'content-type':'text/event-stream','request-id':'req_synthetic_timeout_probe'}});
  }});
const proxy = createServer();
proxy.on('connect',(request,socket,head)=>{
 assert.equal(request.url,'api.anthropic.com:443');
 const target=connect(server.port!,'127.0.0.1',()=>{socket.write('HTTP/1.1 200 Connection Established\r\n\r\n');if(head.length)target.write(head);socket.pipe(target);target.pipe(socket);});
 target.on('error',()=>socket.destroy());socket.on('error',()=>target.destroy());
});
await new Promise<void>(done=>proxy.listen(0,'127.0.0.1',done));
const address=proxy.address();assert.ok(address&&typeof address!=='string');
const config=join(root,'config'),home=join(root,'home');await mkdir(config);await mkdir(home);
await writeFile(join(config,'.claude.json'),JSON.stringify({userID:'a'.repeat(64),oauthAccount:{accountUuid:'11111111-1111-4111-8111-111111111111',organizationUuid:'22222222-2222-4222-8222-222222222222',emailAddress:'fixture@example.test'}}));
const workerId=randomUUID(),jobId=randomUUID();
const env:Record<string,string>={HOME:home,CLAUDE_CONFIG_DIR:config,PATH:'/usr/bin:/bin',LANG:'C.UTF-8',CCRB_WORKER_ID:workerId,CCRB_TELEMETRY:'off',CLAUDE_CODE_ENTRYPOINT:'cli',DISABLE_AUTO_COMPACT:'1',CLAUDE_CODE_GATEWAY_HINT_HEADERS:'1',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC:'1',DISABLE_AUTOUPDATER:'1',DISABLE_TELEMETRY:'1',DISABLE_ERROR_REPORTING:'1',CLAUDE_CODE_OAUTH_TOKEN:'synthetic-bearer-probe',HTTPS_PROXY:`http://127.0.0.1:${address.port}`,HTTP_PROXY:`http://127.0.0.1:${address.port}`,NODE_EXTRA_CA_CERTS:cert};
if(process.env.CCRB_PROBE_FIRST_BYTE_MS)env.CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS=process.env.CCRB_PROBE_FIRST_BYTE_MS;
if (process.env.CCRB_PROBE_PRELOAD) env.BUN_OPTIONS = '--preload ' + process.env.CCRB_PROBE_PRELOAD;
const worker=new PrivateProcess([binary,'--version'],env,line=>decodeWorkerFrame(line,workerId),home);
const events:{type:string;at_ms:number;state?:string}[]=[];
let cancelTimer: ReturnType<typeof setTimeout> | undefined;
try {
 const ready=await worker.next();assert.equal(ready.type,'worker_ready');
 const started=performance.now();
 await worker.send({type:'request_input',schema_version:2,worker_id:workerId,request_id:jobId,input:{schema_version:1,request_id:jobId,body:{model:'claude-sonnet-4-6',max_tokens:64,stream:true,messages:[{role:'user',content:'离线流超时核查'}]}}});
 if (process.env.CCRB_PROBE_CANCEL_MS) cancelTimer = setTimeout(() => { void worker.send({type:'request_cancel',schema_version:2,worker_id:workerId,request_id:jobId}); }, Number(process.env.CCRB_PROBE_CANCEL_MS));
 while(true) {
  const frame=await worker.next(duration+40000);
  if(frame.type==='worker_idle')break;
  if(frame.type!=='request_event')throw new Error('观察帧类型异常');
  events.push({type:frame.payload.type,at_ms:Math.round(performance.now()-started),...(frame.payload.type==='completed'?{state:frame.payload.state}:{})});
  if(frame.payload.type==='error') {
   console.log(JSON.stringify({event:'runtime_error',at_ms:events.at(-1)!.at_ms,error_sha256:createHash('sha256').update(frame.payload.error).digest('hex')}));
  }
 }
 const result={binary_sha256:expectedSha,first_byte_override_ms:env.CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS??null,planned_stream_ms:duration,submissions,synthetic_upstream_ticks:ticks,events,real_model_requests:0};
 await writeFile(process.env.CCRB_PROBE_REPORT??'/tmp/native-first-byte-probe.json',JSON.stringify(result,null,2));
 const expected = process.env.CCRB_PROBE_EXPECT ?? 'completed';
 assert.equal(events.at(-1)?.type, expected==='canceled'?'completed':expected);
 if (expected==='canceled') assert.equal(events.at(-1)?.state,'canceled');
 assert.equal(submissions,1);
 assert.ok(events.some(event=>event.type==='response_headers'));
 console.log(JSON.stringify({...result,events:undefined,chunks:events.filter(event=>event.type==='response_chunk').length,terminal:events.at(-1)}));
} finally {
 if(cancelTimer)clearTimeout(cancelTimer);await worker.close();for(const timer of timers)clearInterval(timer);server.stop(true);proxy.closeAllConnections();proxy.close();await rm(root,{recursive:true,force:true});
}
