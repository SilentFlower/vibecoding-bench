import { expect, test } from 'bun:test';
import { chmod, mkdir, mkdtemp, readFile, readdir, readlink, rm, symlink, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';
import { build } from '../../scripts/build';
import { LocalPoolEngine } from '../../scripts/testing/local-pool-engine';
import { LocalPoolLedger } from '../../scripts/testing/local-pool-ledger';
import { LocalPoolStartupError, type LocalPoolStartupDiagnostics } from '../../scripts/testing/local-pool-startup';

const canary = 'startup-stderr-private-canary-62935';

/** 仅用于本地测试 shim 的路径引用，不执行动态内容。
 * @param value 固定工具或测试文件路径。
 * @return 单引号保护的 shell 参数。
 */
function quote(value: string): string { return "'" + value.replaceAll("'", "'\\''") + "'"; }

test('启动故障保留首错、零调用并清理；独立重启及四实例并发正常', async () => {
  if (await readlink('/proc/self/ns/net') === await readlink('/proc/1/ns/net') || Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode !== 0) throw new Error('启动验收必须在隔离网络执行');
  if ((await readFile('/proc/net/dev', 'utf8')).split('\n').slice(2).filter(line => line.includes(':')).map(line => line.split(':')[0]!.trim()).join(',') !== 'lo') throw new Error('启动验收只允许回环接口');
  const binary = process.env.CCRB_TEST_ORIGINAL_BINARY!, root = await mkdtemp(join(tmpdir(), 'ccrb-startup-test-'));
  const basePath = process.env.PATH ?? '/usr/bin:/bin', node = Bun.which('node')!, openssl = Bun.which('openssl')!, ip = Bun.which('ip')!;
  const reports: unknown[] = [];
  const parallel: { index: number; ready: boolean; reserved: number; closeFailed: boolean; failure: LocalPoolStartupDiagnostics | null }[] = [];
  const temporaryBefore = new Set((await readdir(tmpdir())).filter(name => /^ccrb-(local-pool|proxy)-/.test(name)));
  const childrenPath = '/proc/' + process.pid + '/task/' + process.pid + '/children';
  const childrenBefore = new Set((await readFile(childrenPath, 'utf8')).trim().split(/\s+/).filter(Boolean));
  let passed = false, parallelModelCalls = 0;
  const pool = Bun.serve({ hostname: '127.0.0.1', port: 0, fetch() { parallelModelCalls++; return new Response('启动不应访问模型', { status: 500 }); } });

  /** 新进程启动前设置 PATH，使故障只作用于当前测试，不修改服务或配置。
   * @param scenario 合成故障名称。
   * @param suffix 同一场景的独立轮次。
   * @return 真实引擎返回的安全证据。
   */
  async function attempt(scenario: string, suffix: string) {
    const directory = join(root, scenario + '-' + suffix), bin = join(directory, 'bin');
    await mkdir(bin, { recursive: true, mode: 0o700 });
    const hook = `
const { appendFileSync } = require('node:fs');
appendFileSync(${JSON.stringify(join(directory, 'node-pids.jsonl'))}, JSON.stringify(process.pid)+'\\n', {mode:0o600});
const scenario=${JSON.stringify(scenario)}, canary=${JSON.stringify(canary)};
const forwarder=process.argv[1]?.endsWith('/forwarder.mjs'), proxy=process.argv[1]?.endsWith('/proxy.mjs');
if (forwarder && scenario==='early_exit') { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,200); process.stderr.write(canary); process.exit(9); }
if (forwarder && scenario==='timeout') Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,60000);
if (forwarder && (scenario==='tls' || scenario==='headers')) {
  const tls=require('node:tls'), original=tls.connect;
  tls.connect=function(...args) {
    if (scenario==='tls') { const socket=new (require('node:stream').PassThrough)(); queueMicrotask(()=>socket.destroy(Object.assign(new Error(canary),{code:'CERT_NOT_YET_VALID'}))); return socket; }
    const socket=original.apply(this,args), write=socket.write;
    socket.write=function(data,...rest) { return write.call(this,typeof data==='string'?data.replace('X-Dup: one','X-Dup: changed'):data,...rest); };
    return socket;
  };
  require('node:module').syncBuiltinESMExports();
}
if (proxy && scenario==='target') {
  const http=require('node:http'), original=http.createServer;
  http.createServer=function(...args) { const server=original.apply(this,args); server.prependListener('request',(_request,response)=>{const write=response.writeHead;response.writeHead=function(_code,...rest){return write.call(this,200,...rest);};}); return server; };
  require('node:module').syncBuiltinESMExports();
}
`;
    await writeFile(join(directory, 'hook.cjs'), hook, { mode: 0o600 });
    await writeFile(join(bin, 'node'), '#!/bin/sh\nexec ' + quote(node) + ' --require ' + quote(join(directory, 'hook.cjs')) + ' "$@"\n');
    await chmod(join(bin, 'node'), 0o700);
    if (scenario === 'certificate') { await writeFile(join(bin, 'openssl'), '#!/bin/sh\nexit 7\n'); await chmod(join(bin, 'openssl'), 0o700); }
    if (scenario === 'node') { await rm(join(bin, 'node')); await symlink(openssl, join(bin, 'openssl')); await symlink(ip, join(bin, 'ip')); }
    if (scenario === 'isolation') { await writeFile(join(bin, 'unshare'), '#!/bin/sh\nshift\nexec "$@"\n'); await chmod(join(bin, 'unshare'), 0o700); }
    const child = Bun.spawn([process.execPath, resolve('tests/fixtures/local-pool-startup.ts'), scenario, directory, binary], { env: { PATH: bin + (scenario === 'node' ? '' : ':' + basePath), HOME: '/tmp', LANG: 'C.UTF-8' }, stdin: 'ignore', stdout: 'pipe', stderr: 'pipe' });
    const output = Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text()]);
    expect(await child.exited).toBe(0);
    const [stdout, stderr] = await output;
    expect(stdout).not.toContain(canary); expect(stderr).not.toContain(canary);
    const result = JSON.parse(await readFile(join(directory, 'result.json'), 'utf8'));
    reports.push(result);
    expect(result).toMatchObject({ modelCalls: 0, reserved: 0, remainingPids: [], remainingTmp: [], samplingFailed: false, closeFailed: false });
    return result;
  }

  try {
    await build();
    const cases = [
      ['certificate', 'certificate', 'CERTIFICATE_GENERATION_FAILED'],
      ['build', 'forwarder_build', 'BUILD_FAILED'],
      ['node', 'node', 'NODE_NOT_FOUND'],
      ['tls', 'tls_probe', 'CERT_NOT_YET_VALID'],
      ['headers', 'tls_probe', 'RAW_HEADERS_MISMATCH'],
      ['early_exit', 'forwarder_start', 'CHANNEL_CLOSED'],
      ['timeout', 'forwarder_start', 'CHANNEL_TIMEOUT'],
      ['isolation', 'driver_isolation', 'ISOLATION_CHECK_FAILED'],
      ['target', 'proxy_probe', 'TARGET_REJECTION_FAILED'],
      ['runtime', 'runtime_verify', 'RUNTIME_VERIFY_FAILED'],
      ['cleanup', 'runtime_verify', 'RUNTIME_VERIFY_FAILED'],
    ] as const;
    for (const [scenario, stage, failureCode] of cases) {
      const result = await attempt(scenario, 'failure');
      expect(result).toMatchObject({ ready: false, failure: { code: 'local_pool_startup', status: 503, startup: { stage, failureCode } } });
      if (scenario === 'cleanup') { expect(result.failure.message).toContain('清理出现异常'); expect(result.failure.message).not.toContain('canary'); }
      expect((await attempt('healthy', scenario)).ready).toBe(true);
    }
    // 构建已完成，并发实例仅使用各自目录与账本，避免共享 dist 构建干扰。
    const settled = await Promise.allSettled([0, 1, 2, 3].map(async index => {
      const directory = join(root, 'parallel-' + index); await mkdir(directory);
      const ledger = await LocalPoolLedger.create(join(directory, 'ledger.json'), 'parallel-' + index, false, null);
      const row: typeof parallel[number] = { index, ready: false, reserved: 0, closeFailed: false, failure: null };
      let engine: LocalPoolEngine | undefined;
      try {
        engine = await LocalPoolEngine.open(binary, { baseUrl: 'http://127.0.0.1:' + pool.port, apiKey: 'startup-synthetic-key', live: false, mode: 'manual', maxRequests: null, timeoutMs: 0 }, ledger);
        row.ready = true; expect(engine.workerPid).toBeNull();
      } catch (error) { row.failure = error instanceof LocalPoolStartupError ? error.startup : { stage: 'unknown', failureCode: 'UNKNOWN' }; }
      finally { await engine?.close().catch(() => { row.closeFailed = true; }); row.reserved = ledger.status().reserved; parallel.push(row); }
    }));
    expect(settled.every(value => value.status === 'fulfilled')).toBe(true);
    expect(parallel).toHaveLength(4); expect(parallel.every(value => value.ready && value.reserved === 0 && !value.closeFailed && !value.failure)).toBe(true);
    expect(parallelModelCalls).toBe(0);
    expect((await readdir(tmpdir())).filter(name => /^ccrb-(local-pool|proxy)-/.test(name) && !temporaryBefore.has(name))).toEqual([]);
    expect((await readFile(childrenPath, 'utf8')).trim().split(/\s+/).filter(value => value && !childrenBefore.has(value))).toEqual([]);
    passed = true;
  } finally {
    await pool.stop(true);
    await mkdir('artifacts', { recursive: true });
    const proof = JSON.stringify({ passed, realUpstreamRequests: 0, concurrentInstances: parallel.length, parallelModelCalls, parallel, reports }, null, 2) + '\n';
    await writeFile('artifacts/local-pool-startup-' + randomUUID() + '.json', proof, { mode: 0o600 });
    await writeFile('artifacts/local-pool-startup-proof.json', proof, { mode: 0o600 });
    await rm(root, { recursive: true, force: true });
  }
}, 150000);
