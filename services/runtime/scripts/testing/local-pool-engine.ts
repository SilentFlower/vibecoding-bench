import { mkdir, mkdtemp, readlink, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import type { Engine } from '../../src/control/engine';
import type { FinalCaptureSample } from '../../src/control/trace';
import type { PreparedInput, RuntimeEvent } from '../../src/shared/contracts';
import type { TelemetryState } from '../../src/shared/runtime-policy';
import { BridgeError, isObject } from '../../src/shared/errors';
import { readNativeInput } from '../../src/shared/native-input';
import { PrivateProcess } from './pool-process';
import { decodeForwarderFrame, poolProxyEnvironment, preparePoolRequest, validatePoolConfig, verifyCch, type ForwarderFrame, type PoolConfig } from './pool-common';
import { decodeLocalDriverFrame, type LocalDriverFrame } from './local-pool-protocol';
import { LocalPoolLedger } from './local-pool-ledger';
import { LocalPoolStartupError, type LocalPoolStartupStage } from './local-pool-startup';

/** 活动作业同时绑定原生私有事件和唯一 TLS 实收。 */
interface ActiveRequest {
  prepared: PreparedInput;
  captureId: number | null;
  final: FinalCaptureSample | null;
  finishedObserved: boolean;
  finished: Promise<void>;
  resolve(): void;
  reject(error: unknown): void;
}

/** 宿主持有池凭据，原生驱动仅持有合成身份的隔离引擎。 */
export class LocalPoolEngine implements Engine {
  readonly name: string;
  readonly binarySha256: string;
  workerPid: number | null = null;
  telemetryState: TelemetryState = 'off';
  private active: ActiveRequest | null = null;
  private readonly captures = new Map<string, FinalCaptureSample>();
  private closing = false;
  private failure: Error | null = null;
  private loop: Promise<void> = Promise.resolve();
  /** 绑定已就绪的两个私有进程。 @param root 临时私有资源目录。 @param pool 池配置。 @param ledger 手工额度。 @param forwarder Node TLS 接收端。 @param driver 隔离原生驱动。 @param ready 驱动就绪证据。 */
  private constructor(private readonly root: string, private readonly pool: PoolConfig, private readonly ledger: LocalPoolLedger, private readonly forwarder: PrivateProcess<ForwarderFrame>, private readonly driver: PrivateProcess<LocalDriverFrame>, ready: Extract<LocalDriverFrame, { type: 'ready' }>) {
    this.name = ready.name + '/local-pool'; this.binarySha256 = ready.binarySha256;
  }

  /** 只做本地证书、原始头和目标拒绝自检，不请求池模型。
   * @param binary 固定运行时路径。
   * @param pool 已选择的手工模式池配置。
   * @param ledger 本轮已排他创建的预算。
   * @return 可被现有控制服务注入的原生引擎。
   */
  static async open(binary: string, pool: PoolConfig, ledger: LocalPoolLedger): Promise<LocalPoolEngine> {
    validatePoolConfig(pool);
    if (pool.mode !== 'manual') throw new Error('常驻入口必须显式选择手工联调模式');
    let root: string | undefined, stage: LocalPoolStartupStage = 'workspace';
    let forwarder: PrivateProcess<ForwarderFrame> | undefined, driver: PrivateProcess<LocalDriverFrame> | undefined;
    try {
      root = await mkdtemp(join(tmpdir(), 'ccrb-local-pool-'));
      const keyFile = join(root, 'key.pem'), certFile = join(root, 'cert.pem'), socketPath = join(root, 'tls.sock');
      stage = 'certificate';
      const certificate = Bun.spawnSync(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',keyFile,'-out',certFile,'-days','1','-subj','/CN=api.anthropic.com','-addext','subjectAltName=DNS:api.anthropic.com'], { stdout: 'ignore', stderr: 'ignore' });
      if (certificate.exitCode !== 0) throw new LocalPoolStartupError(stage, 'CERTIFICATE_GENERATION_FAILED');
      stage = 'forwarder_build';
      let bundle: Awaited<ReturnType<typeof Bun.build>>;
      try { bundle = await Bun.build({ entrypoints: [resolve('scripts/testing/pool-forwarder.ts')], target: 'node', format: 'esm', outdir: root, naming: 'forwarder.mjs' }); }
      catch { throw new LocalPoolStartupError('forwarder_build', 'BUILD_FAILED'); }
      if (!bundle.success) throw new LocalPoolStartupError(stage, 'BUILD_FAILED');
      stage = 'node';
      const node = Bun.which('node'); if (!node) throw new LocalPoolStartupError(stage, 'NODE_NOT_FOUND');
      stage = 'proxy_environment';
      const proxyEnv = poolProxyEnvironment(process.env, pool.live);
      if (Object.keys(proxyEnv).length && !new TextDecoder().decode(Bun.spawnSync([node,'--help']).stdout).includes('--use-env-proxy')) throw new LocalPoolStartupError(stage, 'PROXY_CONFIG_UNSUPPORTED');
      const env = { HOME: root, LANG: 'C.UTF-8', PATH: process.env.PATH ?? '/usr/bin:/bin' };
      stage = 'forwarder_start';
      forwarder = new PrivateProcess([node, ...(Object.keys(proxyEnv).length ? ['--use-env-proxy'] : []), join(root, 'forwarder.mjs')], { ...env, ...proxyEnv }, decodeForwarderFrame);
      await forwarder.send({ type: 'init', socketPath, keyFile, certFile, config: pool });
      const tlsReady = await forwarder.next(10000);
      if (tlsReady.type === 'fatal') throw new LocalPoolStartupError(tlsReady.startup?.stage ?? stage, tlsReady.startup?.failureCode);
      stage = 'forwarder_verify';
      const namespace = await readlink('/proc/self/ns/net');
      if (tlsReady.type !== 'ready') throw new LocalPoolStartupError(stage, 'CHANNEL_INVALID');
      if (!tlsReady.rawHeadersMatched) throw new LocalPoolStartupError(stage, 'RAW_HEADERS_MISMATCH');
      if (tlsReady.namespace !== namespace) throw new LocalPoolStartupError(stage, 'ISOLATION_CHECK_FAILED');
      stage = 'driver_setup';
      await mkdir(join(root, 'driver'), { mode: 0o700 });
      stage = 'driver_start';
      driver = new PrivateProcess(['unshare','--net',process.execPath,resolve('scripts/testing/local-pool-driver.ts')], env, decodeLocalDriverFrame);
      await driver.send({ root: join(root, 'driver'), socketPath, certFile, binary: resolve(binary) });
      const ready = await driver.next(10000);
      if (ready.type === 'fatal') throw new LocalPoolStartupError(ready.startup?.stage ?? stage, ready.startup?.failureCode);
      stage = 'driver_isolation';
      if (ready.type !== 'ready') throw new LocalPoolStartupError(stage, 'CHANNEL_INVALID');
      if (ready.namespace === namespace || ready.interfaces.join(',') !== 'lo' || !ready.rejectedTargetProbe || ready.envNames.some(name => /POOL|REQUESTER|PROXY|ANTHROPIC|CLAUDE/.test(name))) throw new LocalPoolStartupError(stage, 'ISOLATION_CHECK_FAILED');
      const engine = new LocalPoolEngine(root, pool, ledger, forwarder, driver, ready);
      engine.loop = engine.readCaptures();
      return engine;
    } catch (error) {
      const failure = new LocalPoolStartupError(stage, error);
      // 每项都尝试收口；清理异常不能阻止后续清理或覆盖启动首错。
      const cleanup = await Promise.allSettled([driver?.close(), forwarder?.close()]);
      if (root) cleanup.push(...await Promise.allSettled([rm(root, { recursive: true, force: true })]));
      if (cleanup.some(result => result.status === 'rejected')) failure.message += '；本地资源清理出现异常';
      throw failure;
    }
  }

  private async readCaptures(): Promise<void> {
    try {
      while (!this.closing) {
        const frame = await this.forwarder.next(0);
        if (frame.type === 'ready' || frame.type === 'fatal') throw new Error('TLS 通道异常');
        const current = this.active;
        if (!current) throw new Error('最终出站缺少活动归属');
        if (frame.type === 'captured') {
          if (current.captureId !== null) throw new Error('同一入站出现重复最终发送');
          current.captureId = frame.id;
          current.final = { body: frame.body, headers: frame.headers, httpVersion: frame.httpVersion, capturedAt: new Date().toISOString(), verified: false, note: 'TLS 实收未通过独立核验，未转发池' };
          this.captures.set(current.prepared.input.request_id, current.final);
          let reason: string | undefined;
          try {
            if (frame.method !== 'POST' || frame.body.includes(this.pool.apiKey)) throw new Error('凭据或方法边界错误');
            verifyCch(frame.body);
            const body: unknown = JSON.parse(frame.body);
            const native = isObject(body) ? readNativeInput(body) : null;
            if (!native || native.context.sessionId !== current.prepared.context.sessionId) throw new Error('TLS 会话归属错误');
            current.final.verified = true;
            current.final.note = '独立 CCH 核验通过；采集在池映射之前，第二段根 model=deepseek-flash，重建池鉴权与传输字段';
          } catch { reason = 'invalid_capture'; }
          if (!reason) {
            try { preparePoolRequest(frame.body, frame.headers, frame.path, this.pool); } catch { reason = 'invalid_request'; }
          }
          if (!reason) {
            try { await this.ledger.reserve(current.prepared.input.request_id); }
            catch (error) { if (error instanceof BridgeError && error.code === 'pool_budget_exhausted') reason = 'budget_exhausted'; else throw error; }
          }
          if (reason) current.final.note += '；本地拒绝原因：' + reason;
          await this.forwarder.send({ type: reason ? 'reject' : 'forward', id: frame.id, ...(reason ? { reason } : {}) });
        } else {
          if (frame.id !== current.captureId || current.finishedObserved) throw new Error('TLS 终态归属错误或重复');
          current.finishedObserved = true;
          await this.ledger.finish(current.prepared.input.request_id, frame);
          current.resolve();
        }
      }
    } catch {
      if (!this.closing) {
        this.failure = new BridgeError('local_capture', '本地 TLS 私有采集通道失败，未自动重放', 502);
        this.active?.reject(this.failure);
        if (this.active) await this.driver.send({ type: 'cancel', requestId: this.active.prepared.input.request_id }).catch(() => {});
      }
    }
  }

  /** 取出同请求真实 TLS 样本，中间值永不补写。
   * @param requestId 控制层当前请求。
   * @return 实收样本或缺失；通道失败明确抛错。
   */
  takeFinalCapture(requestId: string): FinalCaptureSample | null {
    if (this.failure) throw this.failure;
    const result = this.captures.get(requestId) ?? null; this.captures.delete(requestId); return result;
  }

  /** 转交一轮已验证请求，收到真实 idle 后才释放串行槽位。
   * @param prepared 产品控制层已准备的输入。
   * @param signal 客户端或超时取消。
   * @param emit 有背压的产品事件消费者。
   * @return 作业和最终采集已收口。
   */
  async run(prepared: PreparedInput, signal: AbortSignal, emit: (event: RuntimeEvent) => Promise<void>): Promise<void> {
    if (this.closing || this.failure) throw this.failure ?? new BridgeError('local_pool_closed', '本地池联调已关闭', 503);
    if (this.active) throw new BridgeError('local_pool_busy', '本地隔离引擎已有活动请求', 429);
    let resolve!: () => void, reject!: (error: unknown) => void;
    const finished = new Promise<void>((done, fail) => { resolve = done; reject = fail; }); void finished.catch(() => {});
    const current: ActiveRequest = { prepared, captureId: null, final: null, finishedObserved: false, finished, resolve, reject };
    this.active = current;
    let consumerError: unknown, terminal = false;
    const cancel = (): void => { void this.driver.send({ type: 'cancel', requestId: prepared.input.request_id }).catch(() => {}); };
    try {
      await this.driver.send({ type: 'run', job: { type: 'request_start', schema_version: 1, request_id: prepared.input.request_id, prepared } });
      signal.addEventListener('abort', cancel, { once: true }); if (signal.aborted) cancel();
      while (true) {
        const frame = await this.driver.next(0);
        if (frame.type === 'fatal' || frame.type === 'ready') throw new BridgeError('local_driver_protocol', '本地驱动通道失败，未自动重放', 502);
        this.workerPid = frame.workerPid;
        if (frame.type === 'event') {
          if (frame.event.request_id !== prepared.input.request_id || terminal) throw new BridgeError('local_driver_protocol', '本地驱动事件归属或顺序错误', 502);
          if (frame.event.type === 'completed' || frame.event.type === 'error') terminal = true;
          if (!consumerError) {
            try { await emit(frame.event); } catch (error) { consumerError = error; cancel(); }
          }
        } else {
          if (frame.requestId !== prepared.input.request_id) throw new BridgeError('local_driver_protocol', '本地驱动 idle 归属错误', 502);
          this.telemetryState = frame.telemetryState;
          if (current.captureId !== null) {
            let timer: ReturnType<typeof setTimeout> | undefined;
            try { await Promise.race([current.finished, new Promise<never>((_, fail) => { timer = setTimeout(() => fail(new Error('TLS 终态未收口')), 5000); })]); }
            finally { clearTimeout(timer); }
          }
          if (consumerError) throw consumerError;
          if (frame.error) throw new BridgeError(frame.error.code, frame.error.message, frame.error.status);
          if (!terminal) throw new BridgeError('local_driver_protocol', '本地驱动缺少请求终态', 502);
          return;
        }
      }
    } catch (error) {
      if (!terminal && !signal.aborted) this.failure = new BridgeError('local_driver_protocol', '本地隔离通道异常，请重启联调服务；未自动重放', 502);
      cancel(); throw error;
    } finally {
      signal.removeEventListener('abort', cancel); this.active = null;
    }
  }

  /** 只清理本次创建的进程、临时证书和 socket。
   * @return 资源已释放，持久日志与账本保留。
   */
  async close(): Promise<void> {
    if (this.closing) return;
    this.closing = true;
    await this.driver.close(); await this.forwarder.close(); await this.loop;
    this.captures.clear();
    await rm(this.root, { recursive: true, force: true });
  }
}
