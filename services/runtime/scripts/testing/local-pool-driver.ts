import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import { once } from 'node:events';
import { createEngine } from '../../src/control/engine';
import { readConfig } from '../../src/control/server';
import { BridgeError, isObject } from '../../src/shared/errors';
import { decodeRuntimeJob } from '../../src/shared/protocol';
import { startIsolatedProxy } from './pool-network';
import { SYNTHETIC_KEY } from './pool-common';
import { LocalPoolStartupError, type LocalPoolStartupStage } from './local-pool-startup';
import type { LocalDriverFrame, LocalDriverSetup, LocalDriverError } from './local-pool-protocol';

const send = async (frame: LocalDriverFrame): Promise<void> => { if (!process.stdout.write(JSON.stringify(frame) + '\n')) await once(process.stdout, 'drain'); };
let startupStage: LocalPoolStartupStage | null = 'driver_setup';

/** 在独立仅回环空间复用原生引擎，主循环持续接收取消指令。
 * @return 私有输入关闭后所有原生资源已释放。
 */
async function main(): Promise<void> {
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const commands = input[Symbol.asyncIterator]();
  const first = await commands.next(), value: unknown = JSON.parse(first.value ?? 'null');
  if (!isObject(value) || !['root','socketPath','certFile','binary'].every(key => typeof value[key] === 'string')) throw new LocalPoolStartupError('driver_setup', 'INIT_FRAME_INVALID');
  const setup = value as unknown as LocalDriverSetup;
  startupStage = 'driver_isolation';
  const network = await startIsolatedProxy(setup.socketPath);
  try {
    startupStage = 'driver_setup';
    await mkdir(join(setup.root, 'home'), { recursive: true, mode: 0o700 });
    await mkdir(join(setup.root, 'config'), { recursive: true, mode: 0o700 });
    await writeFile(join(setup.root, 'config/.claude.json'), JSON.stringify({ userID: 'd'.repeat(64) }), { mode: 0o600 });
    const config = readConfig({ CCRB_CLAUDE_BINARY: setup.binary, CCRB_CLAUDE_HOME: join(setup.root, 'home'), CCRB_CLAUDE_CONFIG_DIR: join(setup.root, 'config'), CCRB_WORKDIR: setup.root, CCRB_NATIVE_API_KEY: SYNTHETIC_KEY, CCRB_CA_FILE: setup.certFile, CCRB_PROXY_URL: network.url, CCRB_TIMEOUT_MS: '0', CCRB_TELEMETRY: 'off' });
    startupStage = 'runtime_verify';
    const engine = await createEngine(config.engine).catch(() => { throw new LocalPoolStartupError('runtime_verify', 'RUNTIME_VERIFY_FAILED'); });
    let verifiedWorkerPid: number | null = null, verifiedWorkerEnvNames: string[] = [];
    let active: { id: string; abort: AbortController; done: Promise<void> } | null = null;
    try {
      await send({ type: 'ready', namespace: network.namespace, interfaces: network.interfaces, envNames: Object.keys(process.env).sort(), rejectedTargetProbe: true, name: engine.name, binarySha256: engine.binarySha256! });
      startupStage = null;
      while (true) {
        const next = await commands.next(); if (next.done) break;
        const command: unknown = JSON.parse(next.value);
        if (!isObject(command)) throw new Error('本地驱动指令错误');
        if (command.type === 'shutdown') break;
        if (command.type === 'cancel') {
          if (active && command.requestId === active.id) active.abort.abort();
          continue;
        }
        if (command.type !== 'run' || active) throw new Error('本地驱动作业重叠或类型错误');
        const job = decodeRuntimeJob(command.job), abort = new AbortController();
        const current = { id: job.request_id, abort, done: Promise.resolve() };
        active = current;
        current.done = (async () => {
          let error: LocalDriverError | undefined, workerEnvNames: string[] = [], syntheticCredential = false;
          try {
            await engine.run(job.prepared, abort.signal, async event => {
              if (event.type === 'ready') {
                // ready 回调结束后引擎才投递正文；只在此处逐物理进程核对完整启动环境。
                // 大正文处理后的 /proc 环境采样可能缺失，不能把它当作实际凭据发生变化。
                const workerPid = engine.workerPid;
                if (workerPid === null) throw new BridgeError('local_isolation', '原生就绪事件缺少实际进程', 503);
                if (workerPid !== verifiedWorkerPid) {
                  const entries = (await readFile('/proc/' + workerPid + '/environ')).toString().split('\0').filter(Boolean);
                  const names = entries.map(entry => entry.split('=', 1)[0]!).sort();
                  if (!entries.includes('ANTHROPIC_API_KEY=' + SYNTHETIC_KEY) || names.some(name => /POOL|REQUESTER|ANTHROPIC_BASE_URL|OAUTH/.test(name))) throw new BridgeError('local_isolation', '原生工作进程启动环境未通过凭据隔离核验', 503);
                  verifiedWorkerPid = workerPid; verifiedWorkerEnvNames = names;
                }
                workerEnvNames = verifiedWorkerEnvNames; syntheticCredential = true;
              }
              await send({ type: 'event', event, workerPid: engine.workerPid });
            });
          } catch (cause) {
            error = cause instanceof BridgeError ? { code: cause.code, message: cause.code === 'local_isolation' ? cause.message : '隔离原生作业失败：' + cause.code, status: cause.status } : { code: 'local_driver', message: '隔离原生作业未完成，未自动重放', status: 502 };
          } finally {
            if (engine.workerPid === null) { verifiedWorkerPid = null; verifiedWorkerEnvNames = []; }
            // idle 晚于引擎真正收口，宿主收到它后才能释放串行槽位。
            active = null;
            await send({ type: 'idle', requestId: current.id, workerPid: engine.workerPid, telemetryState: engine.telemetryState ?? 'unavailable', workerEnvNames, syntheticCredential, ...(error ? { error } : {}) });
          }
        })();
        void current.done.catch(() => { input.close(); });
      }
    } finally {
      input.close(); active?.abort.abort(); await active?.done;
      await engine.close();
    }
  } finally { await network.close(); }
}

if (import.meta.main) void main().then(() => process.exit(0)).catch(async error => { await send({ type: 'fatal', message: '本地隔离驱动失败，未自动重放', ...(startupStage === null ? {} : { startup: new LocalPoolStartupError(startupStage, error).startup }) }).catch(() => {}); process.exit(1); });
