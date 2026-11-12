import { mkdtemp, mkdir, readFile, readlink, readdir, rm, writeFile, open } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { build } from './build';
import { verifyRuntime } from '../src/runtime/profile';
import { Redactor } from '../src/control/redaction';
import type { JsonObject } from '../src/shared/contracts';
import { isObject } from '../src/shared/errors';
import { CAPTURE_LIMIT, POOL_MODEL, SYNTHETIC_KEY, decodeDriverFrame, decodeForwarderFrame, loadPoolConfig, poolLedgerName, poolProxyEnvironment, sample, verifyCch, type BodySample, type DriverFrame, type ForwarderFrame, type PoolConfig, type PoolScene } from './testing/pool-common';
import { PrivateProcess } from './testing/pool-process';
import { poolScenes } from './testing/pool-scenes';
import { startPoolFixture, type PoolFixture } from './testing/pool-fixture';
import { renderPoolReport, servePoolReport, type PoolCaseReport, type PoolReport, type ReportStage } from './testing/pool-report';

/** 命令行只接收非秘密路径，真实池必须显式启用。 */
interface Options { live: boolean; isolated: boolean; binary: string; output: string; poolEnv?: string; liveRun?: string; serve?: number; reportOnly?: string }

function options(args: string[]): Options {
  const result: Options = { live: false, isolated: false, binary: resolve('runtime/claude-293-cache-telemetry-release'), output: resolve('artifacts/pool-tls-forwarder-' + new Date().toISOString().replace(/[:.]/g, '-')) };
  for (let i = 0; i < args.length; i++) {
    const flag = args[i]!;
    if (flag === '--live') result.live = true;
    else if (flag === '--offline-child') result.isolated = true;
    else if (['--binary','--output','--pool-env','--live-run','--serve','--report-only'].includes(flag)) {
      const value = args[++i]; if (!value || value.startsWith('--')) throw new Error('测试选项缺少参数');
      if (flag === '--binary') result.binary = resolve(value);
      if (flag === '--output') result.output = resolve(value);
      if (flag === '--pool-env') result.poolEnv = resolve(value);
      if (flag === '--live-run') { poolLedgerName(value); result.liveRun = value; }
      if (flag === '--report-only') result.reportOnly = resolve(value);
      if (flag === '--serve') { result.serve = Number(value); if (!Number.isSafeInteger(result.serve) || result.serve < 0 || result.serve > 65535) throw new Error('报告端口不合法'); }
    } else throw new Error('未知测试选项');
  }
  if (result.live && (!result.poolEnv || result.isolated || result.reportOnly)) throw new Error('真实池需要显式 --pool-env，且不能混用离线或只读模式');
  if (!result.live && result.poolEnv) throw new Error('离线模式不读取真实池配置');
  if (!result.live && result.liveRun !== undefined) throw new Error('显式验收轮次仅用于 --live');
  return result;
}

/** 一轮私有收发状态，只有两个回执都结束后才能切到下一场景。 */
interface Active {
  scene: PoolScene; captureId: number | null; captures: number; final: PoolCaseReport['ccFinal']; raw: string | null; finished: Extract<ForwarderFrame, { type: 'finished' }> | null; error: string | null;
  done: Promise<void>; resolve(): void; reject(error: unknown): void;
}

function activeScene(scene: PoolScene): Active {
  let resolve!: () => void, reject!: (error: unknown) => void;
  const done = new Promise<void>((a, b) => { resolve = a; reject = b; }); void done.catch(() => {});
  return { scene, captureId: null, captures: 0, final: null, raw: null, finished: null, error: null, done, resolve, reject };
}

async function withDeadline<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try { return await Promise.race([promise, new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('测试收口超过预算')), ms); })]); }
  finally { clearTimeout(timer); }
}

/** 控制端二次脱敏驱动回执，保留原始哈希。 @param value 私有样本。 @param redactor 持有真实池 Key 的脱敏器。 @return 安全样本。 */
export function safePoolSample(value: BodySample, redactor: Redactor): BodySample {
  const preview = redactor.preview(value.text, CAPTURE_LIMIT, value.status !== 'complete');
  return { ...value, text: preview.text, storedBytes: Buffer.byteLength(preview.text), status: value.status === 'incomplete' ? 'incomplete' : value.status === 'truncated' || preview.truncated ? 'truncated' : 'complete' };
}

async function hasSecret(directory: string, secret: string): Promise<boolean> {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory() ? await hasSecret(path, secret) : entry.isFile() && (await readFile(path)).includes(Buffer.from(secret))) return true;
  }
  return false;
}

async function run(config: Options): Promise<PoolReport> {
  if (process.platform !== 'linux') throw new Error('池测试需要 Linux 网络命名空间');
  const namespace = await readlink('/proc/self/ns/net');
  const interfaces = (await readFile('/proc/net/dev', 'utf8')).split('\n').slice(2).filter(x => x.includes(':')).map(x => x.split(':')[0]!.trim());
  if (!config.live && (!config.isolated || namespace === await readlink('/proc/1/ns/net') || interfaces.length !== 1 || interfaces[0] !== 'lo')) throw new Error('离线控制端必须没有外网接口');
  const runtime = await verifyRuntime(config.binary); await runtime.handle.close();
  await build();
  const root = await mkdtemp(join(tmpdir(), 'ccrb-pool-'));
  let fixture: PoolFixture | undefined, forwarder: PrivateProcess<ForwarderFrame> | undefined, driver: PrivateProcess<DriverFrame> | undefined, current: Active | null = null, closing = false;
  const getActive = (): Active | null => current;
  let loop: Promise<void> = Promise.resolve(), channelError: Error | null = null, step = '读取池测试配置';
  const report: PoolReport = { schemaVersion: 1, createdAt: new Date().toISOString(), mode: config.live ? 'live' : 'offline', model: POOL_MODEL, baseUrl: '', binary: { path: config.binary, kind: runtime.identity.kind, distributionSha256: runtime.identity.launcherSha256, executionSha256: runtime.identity.imageSha256 }, environment: { controllerNamespace: namespace, controllerInterfaces: interfaces, productionNativeFinalCapture: false, telemetry: 'off', poolKeyInWorkerConfiguration: false }, calls: 0, budget: config.live ? 3 : 100, stopped: null, cases: [] };
  let pool: PoolConfig | undefined;
  try {
    pool = config.live ? await loadPoolConfig(config.poolEnv!) : { baseUrl: '', apiKey: 'pool-fixture-secret-cross-chunk-79b381', live: false, maxRequests: 100, timeoutMs: 1000 };
    if (!config.live) { fixture = startPoolFixture(pool.apiKey); pool.baseUrl = fixture.baseUrl; }
    report.baseUrl = pool.baseUrl;
    const redactor = new Redactor(); redactor.register({ api_key: pool.apiKey, token: SYNTHETIC_KEY });
    const safe = (value: BodySample): BodySample => safePoolSample(value, redactor);
    const stage = (source: string, representation: string, body: BodySample, headers: ReportStage['headers']): ReportStage => ({ source, representation, body: safe(body), headers: redactor.headers(headers) });
    step = '启动 TLS 采集端及原始头自检';
    const keyFile = join(root, 'key.pem'), certFile = join(root, 'cert.pem'), socketPath = join(root, 'tls.sock');
    const generated = Bun.spawnSync(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',keyFile,'-out',certFile,'-days','1','-subj','/CN=api.anthropic.com','-addext','subjectAltName=DNS:api.anthropic.com'], { stdout: 'ignore', stderr: 'ignore' });
    if (generated.exitCode !== 0) throw new Error('本机测试证书生成失败');
    const built = await Bun.build({ entrypoints: [resolve('scripts/testing/pool-forwarder.ts')], target: 'node', format: 'esm', outdir: root, naming: 'forwarder.mjs' });
    if (!built.success) throw new Error('Node 采集器构建失败');
    const env = { HOME: root, LANG: 'C.UTF-8', PATH: process.env.PATH ?? '/usr/bin:/bin' };
    const node = Bun.which('node'); if (!node) throw new Error('缺少 Node TLS 接收端');
    const proxyEnv = poolProxyEnvironment(process.env, config.live);
    report.environment.poolProxy = { source: 'host_standard_proxy_environment', enabled: !!(proxyEnv.HTTP_PROXY || proxyEnv.HTTPS_PROXY), keys: Object.keys(proxyEnv), inheritedByDriver: false };
    forwarder = new PrivateProcess([node, ...(Object.keys(proxyEnv).length ? ['--use-env-proxy'] : []), join(root, 'forwarder.mjs')], { ...env, ...proxyEnv }, decodeForwarderFrame);
    await forwarder.send({ type: 'init', socketPath, keyFile, certFile, config: pool });
    const ready = await forwarder.next(10000);
    if (ready.type !== 'ready' || !ready.rawHeadersMatched || ready.namespace !== namespace) throw new Error('TLS 接收端原始头或空间校验失败');
    report.environment.rawHeadersProbeMatched = true;
    loop = (async () => {
      while (true) {
        const frame = await forwarder!.next();
        if (frame.type === 'fatal' || frame.type === 'ready') throw new Error('TLS 采集端出现异常或重复握手');
        const row = getActive();
        if (!row) throw new Error('最终出站没有活动场景');
        if (frame.type === 'captured') {
          row.captures++; row.raw = frame.body; row.captureId = frame.id;
          let cch: { actual: string; expected: string } | null = null;
          try {
            if (row.captures !== 1 || frame.method !== 'POST' || frame.body.includes(pool!.apiKey)) throw new Error('最终出站次数、方法或凭据边界错误');
            cch = verifyCch(frame.body);
            const value: unknown = JSON.parse(frame.body);
            if (!isObject(value) || !isObject(value.metadata) || typeof value.metadata.user_id !== 'string' || !isObject(row.scene.input.context) || JSON.parse(value.metadata.user_id).session_id !== row.scene.input.context.sessionId) throw new Error('最终出站会话归属不匹配');
          } catch { row.error = '最终出站独立核验失败，未转发池请求'; }
          row.final = { ...stage('node_tls_receiver', 'http_entity_body_after_native_transport', sample(frame.body, redactor), frame.headers), method: frame.method, path: frame.path, httpVersion: frame.httpVersion, cch, capturedAt: new Date().toISOString() };
          await forwarder!.send({ type: row.error ? 'reject' : 'forward', id: frame.id });
        } else {
          if (row.finished || row.captureId !== frame.id) throw new Error('采集端重复终态或归属不匹配');
          row.finished = frame; if (frame.attempted) report.calls++; row.resolve();
        }
      }
    })().catch(() => { if (!closing) { channelError = new Error('TLS 私有通道失败，未自动重放'); current?.reject(channelError); } });
    step = '驱动网络、环境和目标拒绝自检';
    driver = new PrivateProcess(['unshare','--net',process.execPath,resolve('scripts/testing/pool-driver.ts')], env, decodeDriverFrame);
    await driver.send({ root: join(root, 'driver'), socketPath, certFile, binary: config.binary });
    const driverReady = await driver.next(10000);
    if (driverReady.type !== 'driver_ready' || driverReady.namespace === namespace || driverReady.interfaces.join(',') !== 'lo' || !driverReady.rejectedTargetProbe) throw new Error('CC 驱动网络边界校验失败');
    report.environment.driver = driverReady;
    let ledger: string | undefined;
    if (config.live) {
      step = '排他创建本轮真实调用账本（已有账本不会重复推理）';
      ledger = resolve('artifacts', poolLedgerName(config.liveRun)); report.environment.liveRun = config.liveRun ?? 'first-run';
      await mkdir(resolve('artifacts'), { recursive: true });
      const lock = await open(ledger, 'wx', 0o600);
      try { await lock.writeFile(JSON.stringify({ run: config.liveRun ?? 'first-run', createdAt: report.createdAt, output: config.output, reserved: [], calls: 0, budget: 3, model: POOL_MODEL, state: 'started' }, null, 2)); } finally { await lock.close(); }
    }
    const reserved: string[] = [];
    for (const scene of poolScenes(config.live)) {
      step = '场景 ' + scene.id + ' 的采集与收口';
      if (channelError) throw channelError;
      current = activeScene(scene); fixture?.select(scene.fixture);
      if (ledger) { reserved.push(scene.id); report.environment.reservedCases = [...reserved]; await writeFile(ledger, JSON.stringify({ run: config.liveRun ?? 'first-run', createdAt: report.createdAt, output: config.output, reserved, calls: report.calls, budget: 3, model: POOL_MODEL, state: 'running' }, null, 2), { mode: 0o600 }); }
      const before = fixture?.calls.length ?? 0, cancellations = fixture?.canceled ?? 0;
      await driver.send({ type: 'run', scene });
      const result = await driver.next(); if (result.type !== 'result' || result.id !== scene.id) throw new Error('驱动场景回执不匹配');
      if (current.captures) await withDeadline(current.done, 5000);
      const wire = current.final, end = current.finished;
      const checks: PoolCaseReport['checks'] = [];
      const check = (name: string, passed: boolean): void => { checks.push({ name, passed }); };
      check('原生最终 CCH 核验、单次 TLS 请求', current.captures === 1 && wire?.cch !== null && !!wire);
      check('池发送一次，固定 deepseek-flash', !!end?.attempted && end.prepared?.model === POOL_MODEL);
      check('HTTP 状态保留', result.statusCode === scene.expectedStatus);
      check('合成凭据与遥测关闭', result.syntheticCredential && result.telemetry === 'off' && result.rejectedRequests === 0);
      if (fixture) {
        const calls = fixture.calls.slice(before), expected = current.raw ? JSON.parse(current.raw) as JsonObject : null;
        check('假池实收正文仅根 model 改变', calls.length === 1 && !!expected && JSON.stringify(calls[0]!.body) === JSON.stringify({ ...expected, model: POOL_MODEL }));
        check('池端鉴权已替换，扩展头保留', calls.length === 1 && calls[0]!.authenticated && calls[0]!.extension === 'preserved');
        if (scene.cancel) check('假池观察到取消', fixture.canceled > cancellations);
        if (scene.fixture === 'redirect') check('没有跟随重定向', fixture.redirected === 0 && end?.outcome === 'redirect_blocked');
      }
      if (scene.cancel) check('客户端取消并中止池转发', result.state === 'canceled' && result.response.status === 'incomplete' && end?.outcome === 'canceled' && result.workerPid === null);
      else if (scene.fixture === 'timeout') check('池超时终止且无重试', end?.outcome === 'timeout' && !['success'].includes(result.state));
      else {
        check('逻辑响应字节原样返回', !!end && end.response.sha256 === result.response.sha256 && end.response.bytes === result.response.bytes);
        const expectedState = scene.fixture === 'incomplete' ? 'incomplete' : scene.fixture === 'event-error' ? 'stream_error' : scene.expectedStatus >= 400 ? 'http_error' : scene.fixture === 'redirect' ? 'incomplete' : 'success';
        check('响应语义终态', result.state === expectedState);
      }
      const reportRow: PoolCaseReport = {
        id: scene.id, fixture: scene.fixture, cachePolicy: scene.cachePolicy, passed: checks.every(x => x.passed), checks, context: result.context ? redactor.value(result.context) as JsonObject : null, elapsedMs: result.elapsedMs, state: result.state, bridgeStatus: result.statusCode,
        ingress: stage('synthetic_scene_http_input', 'http_entity_body_utf8', sample(result.ingress, redactor), []),
        ccPrepared: result.prepared ? stage('native_transport_prepared', 'transport_arguments_middle_value', result.prepared.body, result.prepared.headers) : null,
        ccFinal: wire, poolPrepared: end?.prepared ? { ...end.prepared, headers: redactor.headers(end.prepared.headers), body: safe(end.prepared.body), source: 'pool_http_client_arguments', representation: 'assembled_client_arguments_not_pool_wire_headers' } : null,
        forwarding: end ? { attempted: end.attempted, outcome: end.outcome, upstreamStatus: end.upstreamStatus, localStatus: end.statusCode, failureCode: end.failureCode ?? null, error: end.error ?? null } : null,
        poolResponse: end && end.upstreamStatus !== null ? { ...stage(config.live ? 'real_pool_response' : 'offline_pool_fixture_response', 'response_logical_bytes', end.response, end.headers), statusCode: end.upstreamStatus, outcome: end.outcome, attempted: end.attempted } : null,
        bridgeResponse: stage('bridge_http_response', 'response_logical_bytes', result.response, result.headers), note: current.error ?? (!wire ? '未采集最终出站，不能用中间值替代' : end?.upstreamStatus === null ? '未观测到池 HTTP 响应；调用方状态由本地转发器生成。' : null),
      };
      report.environment.lastWorker = { envNames: result.workerEnvNames, syntheticCredential: result.syntheticCredential, telemetry: result.telemetry, proxyRequests: result.proxyRequests, rejectedRequests: result.rejectedRequests };
      report.cases.push(reportRow);
      console.log(scene.id + '：' + (reportRow.passed ? '通过' : '未通过') + '，HTTP ' + result.statusCode + '，' + result.state);
      if (config.live && !reportRow.passed) { report.stopped = '本轮出现未通过的真实场景，已停止后续调用；没有重试、换模型或删字段。'; break; }
      current = null;
    }
    if (ledger) await writeFile(ledger, JSON.stringify({ run: config.liveRun ?? 'first-run', createdAt: report.createdAt, output: config.output, reserved, calls: report.calls, budget: 3, model: POOL_MODEL, state: report.stopped ? 'stopped' : 'finished' }, null, 2), { mode: 0o600 });
    await driver.close(); driver = undefined;
    step = '核对驱动目录的凭据持久化';
    if (await hasSecret(join(root, 'driver'), pool.apiKey)) throw new Error('检测到驱动目录的池秘密持久化，报告禁止完成');
    report.environment.workerDirectorySecretScan = 'passed';
  } catch { report.environment.failedAt = step; report.stopped ??= '测试在“' + step + '”未完成；未自动重放模型。缺失回执时，预留数是调用次数上界。'; }
  finally {
    await driver?.close(); closing = true; await forwarder?.close(); await loop; await fixture?.close(); await rm(root, { recursive: true, force: true });
  }
  // 最后的防线必须清空不安全原文；只抛异常再返回同一报告仍可能把秘密写到磁盘。
  const serialized = JSON.stringify(report);
  if ((pool && serialized.includes(pool.apiKey)) || serialized.includes(SYNTHETIC_KEY)) {
    report.cases = []; report.baseUrl = '[REDACTED]'; report.binary.path = '[REDACTED]'; report.environment = { captureStatus: 'failed', reason: '报告脱敏核验失败，原文未保存' }; report.stopped = '报告脱敏核验失败，已丢弃不安全采集内容；未重放模型。';
  }
  return report;
}

async function main(): Promise<void> {
  const config = options(process.argv.slice(2));
  if (config.reportOnly) { const server = await servePoolReport(config.reportOnly, config.serve ?? 8789); console.log('只读报告：http://127.0.0.1:' + server.port); return; }
  if (!config.live && !config.isolated) {
    const child = Bun.spawn(['unshare','--net',process.execPath,import.meta.path,'--offline-child','--binary',config.binary,'--output',config.output], { env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: process.env.HOME ?? '/tmp', LANG: 'C.UTF-8' }, stdin: 'inherit', stdout: 'inherit', stderr: 'inherit' });
    process.exitCode = await child.exited;
    if (config.serve !== undefined) { const server = await servePoolReport(config.output, config.serve); console.log('只读报告：http://127.0.0.1:' + server.port); }
    return;
  }
  if (!config.live && Bun.spawnSync(['ip','link','set','lo','up']).exitCode !== 0) throw new Error('无法启用离线回环');
  // 独立新目录和首次真实调用账本都使用排他创建，避免重跑覆盖证据或超出已确认预算。
  await mkdir(dirname(config.output), { recursive: true }); await mkdir(config.output, { recursive: false, mode: 0o700 });
  const report = await run(config);
  await writeFile(join(config.output, 'report.json'), JSON.stringify(report, null, 2), { mode: 0o600 });
  await writeFile(join(config.output, 'index.html'), renderPoolReport(report), { mode: 0o600 });
  console.log('报告：' + config.output + '/index.html；模型尝试 ' + report.calls);
  if (report.stopped || report.cases.some(row => !row.passed) || report.cases.length === 0) process.exitCode = 1;
  if (config.serve !== undefined) { const server = await servePoolReport(config.output, config.serve); console.log('只读报告：http://127.0.0.1:' + server.port); }
}

if (import.meta.main) await main().catch(() => { console.error('池测试启动失败，请检查非秘密选项、目录或配置权限。'); process.exitCode = 1; });
