import { mock } from 'bun:test';
import { chmod, mkdtemp, open, readFile, rm, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { PROFILE_293 } from '../../src/runtime/293/source-profile';
import { parseInput } from '../../src/shared/input';
import { prepareInput } from '../../src/control/header-policy';
import { BridgeError } from '../../src/shared/errors';

// 身份验证只在此独立测试进程替换；生产接纳表及其他测试进程不受影响。
let stamp = 'fixture-inode-1';
let hashes = 0;
let fixtureExecutable = '';
mock.module('../../src/runtime/profile', () => ({
  PROFILE_293,
  runtimeFileStamp: async () => stamp,
  verifyExecutionImage: async () => {},
  verifyRuntime: async () => {
    hashes++;
    return { handle: await open(fixtureExecutable, 'r'), stamp, identity: { kind: 'original', launcherSha256: PROFILE_293.sha256, imageSha256: PROFILE_293.sha256, imageBytes: 1 } };
  },
}));
const { NativeEngine } = await import('../../src/control/engine');
const scenario = process.argv[2]!;
const root = await mkdtemp(join(tmpdir(), 'ccrb-engine-fault-'));
let engine: InstanceType<typeof NativeEngine> | undefined;
try {
  const healthy = ['reuse', 'cancel', 'file_change', 'close', 'backpressure', 'ready_backpressure'].includes(scenario);
  const selected = healthy ? (scenario === 'cancel' || scenario === 'backpressure' ? 'stream_wait' : 'normal') : scenario;
  const preload = join(root, 'preload.mjs');
  fixtureExecutable = preload;
  const prefix = '#!' + process.execPath + '\nimport { fixtureWorker } from ' + JSON.stringify(resolve(import.meta.dir, 'protocol-worker.ts')) + '; await fixtureWorker(';
  await writeFile(preload, prefix + JSON.stringify(selected) + ');');
  await chmod(preload, 0o755);
  engine = new NativeEngine({ mode: 'native', binaryPath: process.execPath, preloadPath: preload, home: root, configDir: root, cwd: root, timeoutMs: scenario === 'missing_idle' ? 1000 : scenario === 'startup_wait' ? 100 : 5000, cachePolicy: scenario.startsWith('cache_') ? 'sub2api' : 'preserve', telemetryPolicy: scenario.startsWith('telemetry_') ? 'on' : 'off' });
  await engine.verify();
  if (engine.workerPid !== null) throw new Error('只读校验提前启动了进程');
  const prepared = (index: number) => prepareInput(parseInput({ request_id: 'job-' + index, body: { model: 'fixture', messages: [{ role: 'user', content: '测试' }] } }));
  const noCancel = new AbortController().signal;
  let rejected = false;
  let pid: number | null = null;
  if (scenario === 'reuse' || scenario === 'file_change' || scenario === 'close' || scenario === 'cache_match' || scenario === 'telemetry_match' || scenario === 'telemetry_suppressed') {
    await engine.run(prepared(1), noCancel, async () => {});
    pid = engine.workerPid;
    if (scenario.startsWith('telemetry_') && engine.telemetryState !== (scenario === 'telemetry_match' ? 'initialized' : 'suppressed')) throw new Error('遥测状态没有来自实际握手');
    if (scenario === 'file_change') {
      stamp = 'fixture-inode-2';
      try { await engine.run(prepared(2), noCancel, async () => {}); } catch { rejected = true; }
      if (!rejected || engine.workerPid !== null) throw new Error('文件替换后仍接受了作业');
    } else if (scenario === 'reuse') {
      await engine.run(prepared(2), noCancel, async () => {});
      if (engine.workerPid !== pid || hashes !== 2) throw new Error('正常作业没有复用或重复全文件哈希');
    }
  } else if (scenario === 'cancel' || scenario === 'backpressure' || scenario === 'ready_backpressure') {
    const abort = new AbortController();
    const job = engine.run(prepared(1), abort.signal, async event => {
      if (event.type === (scenario === 'ready_backpressure' ? 'ready' : 'response_chunk')) {
        pid = engine!.workerPid;
        abort.abort();
        if (scenario === 'backpressure' || scenario === 'ready_backpressure') await new Promise<void>(() => {});
      }
    });
    try { await job; } catch { rejected = true; }
    if (!rejected || engine.workerPid !== null) throw new Error('取消没有隔离进程');
    await writeFile(preload, prefix + '"normal");');
    await engine.run(prepared(2), noCancel, async () => {});
    if (engine.workerPid === pid) throw new Error('取消后继续使用原进程');
  } else if (scenario === 'late') {
    await engine.run(prepared(1), noCancel, async () => {});
    await Bun.sleep(80);
    if (engine.workerPid !== null) throw new Error('空闲期迟到帧没有隔离');
  } else {
    let failure: unknown;
    try { await engine.run(prepared(1), noCancel, async () => {}); } catch (error) { rejected = true; failure = error; }
    if (!rejected || engine.workerPid !== null) throw new Error('故障未被拒绝或进程仍在使用');
    if (['cache_legacy', 'cache_mismatch', 'telemetry_legacy', 'telemetry_mismatch'].includes(scenario)) {
      if (!(failure instanceof BridgeError) || failure.code !== 'native_configuration' || failure.status !== 503) throw new Error('旧产物未明确拒绝缓存配置');
    }
    if (['startup_exit', 'startup_error', 'startup_error_wrong_worker', 'startup_error_after_ready'].includes(scenario)) {
      const configuration = scenario === 'startup_exit' || scenario === 'startup_error';
      if (!(failure instanceof BridgeError) || failure.status !== (configuration ? 503 : 502) || failure.code !== (configuration ? 'native_configuration' : 'runtime_protocol')) throw new Error('初始化失败类型或状态丢失');
      if (scenario === 'startup_error' && failure.message !== '专用 CLI 配置已拒绝当前显式密钥') throw new Error('受控初始化说明丢失');
      await writeFile(preload, prefix + '"normal");');
      await engine.run(prepared(2), noCancel, async () => {});
    }
  }
  await engine.close();
  await engine.close();
  if (engine.workerPid !== null) throw new Error('关闭后仍保留工作进程');
  const calls = await readFile(join(root, 'calls.txt'), 'utf8').catch(() => '');
  const ids = calls.trim().split('\n').filter(Boolean).map(line => line.split(':')[1]);
  if (new Set(ids).size !== ids.length) throw new Error('故障导致请求重放');
  if (scenario === 'reuse' && ids.length !== 2) throw new Error('正常串行轮数不匹配');
  if (!['startup_exit', 'startup_wait', 'duplicate_ready', 'cache_legacy', 'cache_mismatch', 'telemetry_legacy', 'telemetry_mismatch'].includes(scenario) && ids.length === 0) throw new Error('夹具未进入作业，故障验证无效');
  if (['cache_legacy', 'cache_mismatch', 'telemetry_legacy', 'telemetry_mismatch'].includes(scenario) && ids.length !== 0) throw new Error('配置能力不匹配时仍发送了作业');
  if (pid && await Bun.file('/proc/' + pid + '/status').exists()) throw new Error('存在孤儿进程');
  process.stdout.write(JSON.stringify({ scenario, calls: ids.length, hashes, rejected }) + '\n');
} finally {
  await engine?.close();
  await rm(root, { recursive: true, force: true });
}
