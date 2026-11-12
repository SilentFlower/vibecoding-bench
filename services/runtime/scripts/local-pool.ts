import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { build } from './build';
import { readConfig, startServer, type RunningServer, type LocalPoolStatus } from '../src/control/server';
import { loadPoolConfig, validatePoolConfig, POOL_MODEL, SYNTHETIC_KEY, type PoolConfig } from './testing/pool-common';
import { LocalPoolEngine } from './testing/local-pool-engine';
import { LocalPoolLedger } from './testing/local-pool-ledger';
import { PoolIncidentCollector, poolIncidentCode, type PoolIncidentCode } from './testing/local-pool-incidents';
import { BridgeError, isObject } from '../src/shared/errors';
import { verifyRuntime } from '../src/runtime/profile';

/** 显式手工模式入口参数，真实 Key 仅通过内存配置传入。 */
export interface LocalPoolOptions {
  binary: string;
  pool: PoolConfig;
  runId: string;
  directory: string;
  port?: number;
  logMode?: 'off' | 'summary' | 'debug';
}

/** 常驻 API 及不触发推理的只读预算。 */
export interface LocalPoolRunning {
  app: RunningServer;
  directory: string;
  /** 读取本轮预算。 @return 已预留和剩余次数。 */
  status(): LocalPoolStatus;
  /** 有序关闭 HTTP、原生驱动和 TLS 转发器。 @return 日志及账本保留。 */
  close(): Promise<void>;
}

/** 启动完成后等待用户请求，初始化和自检不会访问池模型。
 * @param options 显式轮次、手工池配置与回环监听设置。
 * @return 可供 Claude Code 使用的本机服务。
 */
export async function startLocalPool(options: LocalPoolOptions): Promise<LocalPoolRunning> {
  validatePoolConfig(options.pool);
  if (options.pool.mode !== 'manual') throw new Error('必须显式使用手工池模式');
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(options.runId)) throw new Error('手工轮次 ID 不合法');
  const verified = await verifyRuntime(options.binary);
  try {
    // 已发布轻量文件内嵌旧入口；此模式用原版和当前预加载，避免混用未验证的私有合同。
    if (verified.identity.kind !== 'original') throw new BridgeError('local_pool_runtime', '本地 Base URL 联调需要固定原版 2.1.293；现有轻量产物内嵌旧入口，暂不支持此模式', 503);
  } finally { await verified.handle.close(); }
  await build();
  const directory = resolve(options.directory);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const ledger = await LocalPoolLedger.create(join(directory, 'ledger.json'), options.runId, options.pool.live, options.pool.maxRequests);
  const engine = await LocalPoolEngine.open(options.binary, options.pool, ledger);
  let app: RunningServer | undefined;
  try {
    const config = readConfig({ CCRB_PORT: String(options.port ?? 8787), CCRB_DATA_DIR: join(directory, 'data'), CCRB_LOG_MODE: options.logMode ?? 'debug', CCRB_TIMEOUT_MS: '0', CCRB_TELEMETRY: 'off' });
    app = await startServer(config, engine, { nativeIngressPolicy: 'local_base_url', secrets: { pool_api_key: options.pool.apiKey, synthetic_token: SYNTHETIC_KEY }, finalCapture: id => engine.takeFinalCapture(id), localPoolStatus: () => ledger.status() });
    const info = { pid: process.pid, baseUrl: 'http://127.0.0.1:' + app.server.port, ...ledger.status(), startedAt: new Date().toISOString() };
    await writeFile(join(directory, 'ready.json'), JSON.stringify(info, null, 2) + '\n', { mode: 0o600 });
    let closing: Promise<void> | undefined;
    const running = app;
    let incidents: PoolIncidentCollector | undefined;
    const diagnostic = (code: PoolIncidentCode): void => { try { process.stderr.write('本地池取证：' + code + '\n'); } catch {} };
    // 取证与业务启动隔离，只读取已脱敏持久证据，失败不能令已就绪的服务退役。
    try {
      incidents = await PoolIncidentCollector.open({ directory, runId: options.runId, getLogStatus: () => ({ mode: config.logMode, captureErrorPresent: running.store.error !== null }), onDiagnostic: diagnostic });
      incidents.start();
    } catch (error) { diagnostic(poolIncidentCode(error)); }
    return { app, directory, status: () => ledger.status(), close: () => closing ??= (async () => {
      try { await running.close(); }
      finally { try { await incidents?.close(); } catch (error) { diagnostic(poolIncidentCode(error)); } }
    })() };
  } catch (error) {
    if (app) await app.close(); else await engine.close();
    if (isObject(error) && error.code === 'EADDRINUSE') throw new BridgeError('local_pool_port', '本地监听端口已占用：' + (options.port ?? 8787), 503);
    throw error;
  }
}

/** 解析有限命令行设置，不从命令行接收或回显凭据。
 * @param args 本机启动参数。
 * @return 已核对的显式轮次与只读配置文件路径。
 */
function readArguments(args: string[]): { runId: string; poolEnv: string; binary: string; port: number } {
  const values = new Map<string, string>();
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index], value = args[index + 1];
    if (!key || !['--run','--pool-env','--binary','--port'].includes(key) || !value || values.has(key)) throw new Error('参数不合法；需要 --run <新轮次> --pool-env <受保护文件> --binary <原版程序>，可选 --port');
    values.set(key, value);
  }
  const runId = values.get('--run') ?? '', poolEnv = values.get('--pool-env') ?? '', binary = values.get('--binary') ?? '', port = Number(values.get('--port') ?? 8787);
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(runId) || !poolEnv || !binary || !Number.isSafeInteger(port) || port < 1 || port > 65535) throw new Error('必须显式提供新 --run、--pool-env、原版 --binary 及有效回环端口');
  return { runId, poolEnv, binary, port };
}

if (import.meta.main) {
  try {
    const args = readArguments(process.argv.slice(2));
    const pool: PoolConfig = { ...await loadPoolConfig(args.poolEnv), mode: 'manual', maxRequests: null, timeoutMs: 0 };
    const running = await startLocalPool({ binary: args.binary, pool, runId: args.runId, directory: join('artifacts/local-pool-runs', args.runId), port: args.port });
    process.stdout.write('本地池联调已启动：http://127.0.0.1:' + running.app.server.port + '\n模型：' + POOL_MODEL + '；请求次数：不限；模型参数：原样转发；无本地请求总超时\nPID：' + process.pid + '；停止：Ctrl+C 或 kill ' + process.pid + '\n运行记录：' + running.directory + '\n失败取证及状态：' + join(running.directory, 'incidents') + '\n启动真实推理次数：0\n');
    let closing = false;
    const close = async (): Promise<void> => { if (closing) return; closing = true; await running.close(); process.exit(0); };
    process.on('SIGTERM', () => { void close(); }); process.on('SIGINT', () => { void close(); });
  } catch (error) {
    process.stderr.write((error instanceof BridgeError ? error.message : '本地联调启动失败：请核对参数、受保护配置、端口和未使用的运行 ID') + '\n'); process.exitCode = 1;
  }
}
