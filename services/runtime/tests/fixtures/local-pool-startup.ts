import { readFile, readdir, readlink, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { LocalPoolEngine } from '../../scripts/testing/local-pool-engine';
import { LocalPoolLedger } from '../../scripts/testing/local-pool-ledger';
import { LocalPoolStartupError } from '../../scripts/testing/local-pool-startup';
import { PrivateProcess } from '../../scripts/testing/pool-process';

const [scenario, directory, binary] = process.argv.slice(2) as [string, string, string];
if (await readlink('/proc/self/ns/net') === await readlink('/proc/1/ns/net') || Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode !== 0) throw new Error('启动故障工装必须使用独立网络空间');
if ((await readFile('/proc/net/dev', 'utf8')).split('\n').slice(2).filter(line => line.includes(':')).map(line => line.split(':')[0]!.trim()).join(',') !== 'lo') throw new Error('启动故障工装只允许回环接口');
const root = resolve(directory), cwd = process.cwd();
const before = new Set((await readdir(tmpdir())).filter(name => /^ccrb-(local-pool|proxy)-/.test(name)));
const pids = new Set<number>();
let sampling = Promise.resolve(), samplingFailed = false;
const sample = (): void => {
  sampling = sampling.then(async () => {
    try {
      const ids = (await readFile('/proc/' + process.pid + '/task/' + process.pid + '/children', 'utf8')).trim().split(/\s+/).filter(Boolean).map(Number);
      for (const pid of ids) pids.add(pid);
    } catch { samplingFailed = true; }
  });
};
const timer = setInterval(sample, 10);
let modelCalls = 0;
const pool = Bun.serve({ hostname: '127.0.0.1', port: 0, fetch() { modelCalls++; return new Response('初始化不应调用模型', { status: 500 }); } });
const ledger = await LocalPoolLedger.create(join(root, 'ledger.json'), 'startup-fixture', false, null);
if (scenario === 'cleanup') {
  const close = PrivateProcess.prototype.close;
  // 真实资源已关闭后模拟清理回执失败；若上层只清理一项，其他进程与目录仍会遗留。
  PrivateProcess.prototype.close = async function () { await close.call(this); throw new Error('startup-private-cleanup-canary'); };
}
let engine: LocalPoolEngine | undefined, failure: unknown = null, closeFailed = false;
try {
  // 错误工作目录让真实构建找不到入口，不新增产品故障开关。
  if (scenario === 'build') process.chdir(root);
  engine = await LocalPoolEngine.open(scenario === 'runtime' || scenario === 'cleanup' ? join(root, 'missing-runtime') : binary, { baseUrl: 'http://127.0.0.1:' + pool.port, apiKey: 'startup-synthetic-key', live: false, mode: 'manual', maxRequests: null, timeoutMs: 0 }, ledger);
} catch (error) {
  failure = error instanceof LocalPoolStartupError ? { code: error.code, status: error.status, message: error.message, startup: error.startup } : { code: 'unknown', message: '启动失败但缺少受控证据' };
} finally {
  process.chdir(cwd);
  await engine?.close().catch(() => { closeFailed = true; });
  clearInterval(timer); sample(); await sampling;
  await pool.stop(true);
}
const pidFile = join(root, 'node-pids.jsonl');
if (await Bun.file(pidFile).exists()) for (const line of (await readFile(pidFile, 'utf8')).trim().split('\n').filter(Boolean)) pids.add(JSON.parse(line));
const remainingPids: number[] = [];
for (const pid of pids) if (await Bun.file('/proc/' + pid + '/stat').exists()) remainingPids.push(pid);
const remainingTmp = (await readdir(tmpdir())).filter(name => /^ccrb-(local-pool|proxy)-/.test(name) && !before.has(name));
const report = { scenario, ready: failure === null, failure, modelCalls, reserved: ledger.status().reserved, remainingPids, remainingTmp, samplingFailed, closeFailed };
await writeFile(join(root, 'result.json'), JSON.stringify(report) + '\n', { mode: 0o600 });
process.stdout.write(JSON.stringify(report) + '\n');
