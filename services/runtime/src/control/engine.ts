import { readFile } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { resolve } from 'node:path';
import type { PreparedInput, RuntimeEvent, RuntimePayload, WorkerCommand } from '../shared/contracts';
import { decodeWorkerFrame, runtimeEvent } from '../shared/protocol';
import { BridgeError, errorText } from '../shared/errors';
import { PROFILE_293, runtimeFileStamp, verifyRuntime, verifyExecutionImage, type RuntimeIdentity, type VerifiedRuntime } from '../runtime/profile';
import { readCachePolicy, readTelemetryPolicy, type CachePolicy, type TelemetryPolicy, type TelemetryState, type TelemetryHandshake } from '../shared/runtime-policy';
import { readNativeBaseUrl } from '../shared/upstream';
import type { FinalCaptureSample } from './trace';

/** 运行时启动配置，均来自控制配置，不从调用方请求头读取。 */
export interface EngineConfig {
  mode: 'native' | 'demo';
  binaryPath?: string;
  home?: string;
  configDir?: string;
  apiKey?: string;
  oauthToken?: string;
  proxyUrl?: string;
  caFile?: string;
  baseUrl?: string;
  preloadPath: string;
  cwd: string;
  /** 显式请求总预算，0 表示交由前置取消或关闭信号控制。 */
  timeoutMs: number;
  cachePolicy?: CachePolicy;
  telemetryPolicy?: TelemetryPolicy;
}

/** 统一运行时接口，演示与真实原生来源始终分别标记。 */
export interface Engine {
  readonly name: string;
  readonly binarySha256: string | null;
  readonly workerPid: number | null;
  readonly telemetryState?: TelemetryState;
  readonly tlsVerifierIdentity?: { readonly profile: string; readonly sha256: string; readonly target: string; readonly recipe: number };
  readonly tlsVerifierState?: 'ready' | 'failed' | 'closed';
  /** 取得并清除控制侧独立观测，缺失不以准备值补写。
   * @param requestId 当前请求标识。
   * @return 最后写出样本或空。
   */
  takeFinalCapture?(requestId: string): FinalCaptureSample | null;
  /** 执行单轮请求并等待事件消费者。
   * @param prepared 已验证请求。
   * @param signal 取消信号。
   * @param emit 有背压的事件接收器。
   * @return 作业及工作进程清理已结束。
   */
  run(prepared: PreparedInput, signal: AbortSignal, emit: (event: RuntimeEvent) => Promise<void>): Promise<void>;
  /** 关闭常驻工作进程并取消执行中的作业。
   * @return 所有进程已退出。
   */
  close(): Promise<void>;
}

/** 握手、作业及进程故障使用同一可收口承诺。 */
interface Completion { promise: Promise<void>; resolve(): void; reject(error: unknown): void }

function completion(): Completion {
  let resolve!: () => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<void>((done, fail) => { resolve = done; reject = fail; });
  void promise.catch(() => {});
  return { promise, resolve, reject };
}

/** 每一物理进程独占读取器和活动作业，旧代次不能访问新代次字段。 */
interface WorkerProcess {
  id: string;
  child: Bun.Subprocess<'pipe', 'pipe', 'pipe'>;
  verified: VerifiedRuntime;
  ready: Completion;
  stopped: Completion;
  loop: Promise<void>;
  initialized: boolean;
  failed: boolean;
  failure?: unknown;
  telemetry?: TelemetryHandshake;
  current: {
    id: string;
    done: Completion;
    emit(event: RuntimeEvent): Promise<void>;
    terminal: boolean;
    prepared: boolean;
    headers: boolean;
    retire: boolean;
  } | null;
}

/** 固定账号、惰性启动并串行复用的官方原生引擎。 */
export class NativeEngine implements Engine {
  readonly name = 'claude-code/2.1.293';
  private readonly config: EngineConfig;
  private identity: RuntimeIdentity | null = null;
  private stamp = '';
  private worker: WorkerProcess | null = null;
  private running = false;
  private closed = false;
  private activeAbort: AbortController | null = null;
  private inFlight: Completion | null = null;

  /** 绑定不可按请求变更的账号及运行环境。
   * @param config 显式控制配置。
   */
  constructor(config: EngineConfig) { this.config = Object.freeze({ ...config, baseUrl: readNativeBaseUrl(config.baseUrl), cachePolicy: readCachePolicy(config.cachePolicy), telemetryPolicy: readTelemetryPolicy(config.telemetryPolicy) }); }

  /** 读取 worker 的实际遥测初始化状态，不表示上传成功。
   * @return 当前物理进程状态；读取不会创建进程。
   */
  get telemetryState(): TelemetryState {
    if (!this.worker?.initialized) return this.config.telemetryPolicy === 'off' ? 'off' : 'pending';
    return this.worker.telemetry?.state ?? 'unavailable';
  }

  /** 读取实际执行体身份，不以来源哈希冒充内存展开载荷。
   * @return 已核验的执行体 SHA256。
   */
  get binarySha256(): string { return this.identity?.imageSha256 ?? PROFILE_293.sha256; }

  /** 只读当前 PID；查询不会初始化 CC。
   * @return 当前工作进程 PID，未启动或已失效时为空。
   */
  get workerPid(): number | null { return this.worker?.child.pid ?? null; }

  /** 只读核验程序和原版预加载入口。
   * @return 校验完成，不发账号或模型请求。
   */
  async verify(): Promise<void> {
    if (!this.config.binaryPath || !this.config.home || !this.config.configDir) throw new BridgeError('native_configuration', '原生模式需要 CCRB_CLAUDE_BINARY、CCRB_CLAUDE_HOME 和 CCRB_CLAUDE_CONFIG_DIR', 503);
    const verified = await verifyRuntime(this.config.binaryPath);
    try {
      if (verified.identity.kind === 'original') await readFile(this.config.preloadPath);
      if (verified.identity.kind !== 'original' && this.config.baseUrl !== undefined) throw new BridgeError('native_configuration', '旧精简运行时尚未验证显式上游配置，请使用固定官方原版', 503);
      this.identity = verified.identity;
      this.stamp = verified.stamp;
    } finally { await verified.handle.close(); }
  }

  private fail(worker: WorkerProcess, error: unknown): void {
    if (worker.failed) return;
    worker.failed = true;
    worker.failure = error;
    if (this.worker === worker) this.worker = null;
    worker.ready.reject(error);
    worker.stopped.reject(error);
    worker.current?.done.reject(error);
    worker.child.kill('SIGKILL');
  }

  private async retire(worker: WorkerProcess): Promise<void> {
    this.fail(worker, new BridgeError('runtime_closed', '工作进程已关闭', 502));
    await worker.loop;
  }

  private send(worker: WorkerProcess, command: WorkerCommand): void {
    // 握手后的故障可能早于首个作业发送，保留原始配置/协议错误，避免微任务时序改变错误类型。
    if (worker.failed) throw worker.failure ?? new BridgeError('runtime_exit', '工作进程已失效', 502);
    worker.child.stdin.write(JSON.stringify(command) + '\n');
  }

  private async read(worker: WorkerProcess): Promise<void> {
    const diagnostics = (async () => {
      const reader = worker.child.stderr.getReader();
      while (!(await reader.read()).done) {}
    })().catch(error => this.fail(worker, error));
    try {
      const reader = worker.child.stdout.getReader();
      const decoder = new TextDecoder('utf-8', { fatal: true });
      let pending = '';
      while (true) {
        const next = await reader.read();
        if (next.done) break;
        pending += decoder.decode(next.value, { stream: true });
        let index: number;
        while ((index = pending.indexOf('\n')) >= 0) {
          const line = pending.slice(0, index);
          pending = pending.slice(index + 1);
          if (!line) throw new BridgeError('runtime_protocol', '工作进程返回空帧', 502);
          const frame = decodeWorkerFrame(line, worker.id);
          if (frame.type === 'worker_error') {
            if (worker.initialized || worker.current) throw new BridgeError('runtime_protocol', '初始化错误帧只能在握手前返回', 502);
            throw new BridgeError(frame.code, frame.error, frame.status);
          }
          if (frame.type === 'worker_ready') {
            if (worker.initialized || frame.version !== PROFILE_293.version || frame.pid !== worker.child.pid) throw new BridgeError('runtime_protocol', '工作进程握手不匹配或重复', 502);
            if ((frame.cache_policy ?? 'preserve') !== this.config.cachePolicy) throw new BridgeError('native_configuration', '运行时不支持或未应用所选缓存策略，需要更新精简产物', 503);
            if ((frame.telemetry?.policy ?? 'off') !== this.config.telemetryPolicy) throw new BridgeError('native_configuration', '运行时不支持或未应用所选遥测开关，需要更新精简产物', 503);
            worker.telemetry = frame.telemetry;
            await Promise.race([verifyExecutionImage(worker.child.pid, worker.verified.identity), worker.stopped.promise]);
            worker.initialized = true;
            worker.ready.resolve();
            continue;
          }
          const active = worker.current;
          if (!worker.initialized || !active || frame.request_id !== active.id) throw new BridgeError('runtime_protocol', '工作进程事件不能归到当前作业', 502);
          if (frame.type === 'worker_idle') {
            if (!active.terminal) throw new BridgeError('runtime_protocol', '工作进程在终态前宣布空闲', 502);
            worker.current = null;
            active.done.resolve();
            continue;
          }
          if (active.terminal) throw new BridgeError('runtime_protocol', '工作进程在终态后返回事件', 502);
          const payload = frame.payload;
          if (payload.type === 'cc_prepared') {
            if (active.prepared || active.headers) throw new BridgeError('runtime_protocol', '工作进程重复构造请求', 502);
            active.prepared = true;
          } else if (payload.type === 'response_headers') {
            if (!active.prepared || active.headers) throw new BridgeError('runtime_protocol', '工作进程响应头顺序错误', 502);
            active.headers = true;
          } else if (payload.type === 'response_chunk' && !active.headers) throw new BridgeError('runtime_protocol', '响应头之前出现正文', 502);
          if (payload.type === 'completed' || payload.type === 'error') {
            if (payload.type === 'completed' && ['success', 'http_error'].includes(payload.state) && !active.headers) throw new BridgeError('runtime_protocol', '工作进程缺少响应头', 502);
            active.terminal = true;
            active.retire = payload.type === 'error' || ['canceled', 'error'].includes(payload.state);
          }
          // 消费者等待期间仍可由取消/故障解除背压，避免孤儿进程和永久挂起。
          await Promise.race([active.emit(runtimeEvent(active.id, payload)), worker.stopped.promise]);
        }
      }
      decoder.decode();
      if (!worker.initialized && !pending) throw new BridgeError('native_configuration', '固定运行时在初始化完成前退出', 503);
      throw new BridgeError('runtime_exit', pending ? '工作进程退出时存在截断帧' : '工作进程在关闭前退出', 502);
    } catch (error) { this.fail(worker, error); }
    finally {
      await Promise.all([diagnostics, worker.child.exited]);
      await worker.verified.handle.close();
    }
  }

  private async getWorker(signal: AbortSignal): Promise<WorkerProcess> {
    if (!this.identity) await this.verify();
    if (await runtimeFileStamp(this.config.binaryPath!) !== this.stamp) throw new BridgeError('runtime_identity', '运行时文件身份发生改变', 503);
    if (this.worker && !this.worker.failed) return this.worker;
    const verified = await verifyRuntime(this.config.binaryPath!);
    try {
      if (this.closed || signal.aborted) throw new DOMException('请求已取消', 'AbortError');
      if (verified.stamp !== this.stamp) throw new BridgeError('runtime_identity', '运行时文件身份发生改变', 503);
      const config = this.config;
      const id = randomUUID();
      const env: Record<string, string> = {
        HOME: config.home!, CLAUDE_CONFIG_DIR: config.configDir!, PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8',
        CCRB_WORKER_ID: id, CCRB_CACHE_POLICY: config.cachePolicy!, CCRB_TELEMETRY: config.telemetryPolicy!, CLAUDE_CODE_ENTRYPOINT: 'cli', DISABLE_AUTO_COMPACT: '1',
        CLAUDE_CODE_GATEWAY_HINT_HEADERS: '1', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1',
        DISABLE_AUTOUPDATER: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1',
      };
      if (verified.identity.kind === 'original') env.BUN_OPTIONS = '--preload ' + resolve(config.preloadPath);
      if (config.apiKey) env.ANTHROPIC_API_KEY = config.apiKey;
      if (config.oauthToken) env.CLAUDE_CODE_OAUTH_TOKEN = config.oauthToken;
      if (config.proxyUrl) { env.HTTP_PROXY = config.proxyUrl; env.HTTPS_PROXY = config.proxyUrl; }
      if (config.caFile) env.NODE_EXTRA_CA_CERTS = config.caFile;
      if (config.baseUrl !== undefined) env.ANTHROPIC_BASE_URL = config.baseUrl;
      // 通过已核验 FD 启动确切 inode，避免校验后路径原子替换导致执行另一文件。
      const child = Bun.spawn(['/proc/' + process.pid + '/fd/' + verified.handle.fd, '--version'], { cwd: config.cwd, env, stdin: 'pipe', stdout: 'pipe', stderr: 'pipe' });
      const worker: WorkerProcess = { id, child, verified, ready: completion(), stopped: completion(), loop: Promise.resolve(), initialized: false, failed: false, current: null };
      this.worker = worker;
      worker.loop = this.read(worker);
      return worker;
    } catch (error) { await verified.handle.close(); throw error; }
  }

  /** 在账号常驻进程中执行一轮；失败作业不会隐式重放。
   * @param prepared 已验证的请求和上下文。
   * @param signal 调用方取消信号。
   * @param emit 有背压的事件消费者。
   * @return 唯一终态和匹配空闲确认均已收到。
   */
  async run(prepared: PreparedInput, signal: AbortSignal, emit: (event: RuntimeEvent) => Promise<void>): Promise<void> {
    if (this.closed) throw new BridgeError('runtime_closed', '引擎已经关闭', 503);
    if (this.running) throw new BridgeError('runtime_busy', '单账号运行时正在处理其他请求', 429);
    this.running = true;
    const budget = new AbortController();
    this.activeAbort = budget;
    const finished = completion();
    this.inFlight = finished;
    const combined = AbortSignal.any([signal, budget.signal]);
    let worker = this.worker;
    let forceKill: ReturnType<typeof setTimeout> | undefined;
    const cancel = (): void => {
      if (!worker || worker.failed) return;
      if (!worker.current) { this.fail(worker, combined.reason); return; }
      try { this.send(worker, { type: 'request_cancel', schema_version: 2, worker_id: worker.id, request_id: prepared.input.request_id }); } catch {}
      forceKill ??= setTimeout(() => worker && this.fail(worker, combined.reason), 1500);
    };
    combined.addEventListener('abort', cancel, { once: true });
    const timer = this.config.timeoutMs > 0 ? setTimeout(() => budget.abort(new BridgeError('request_timeout', '请求超过运行预算', 504)), this.config.timeoutMs) : undefined;
    let reusable = false;
    try {
      if (combined.aborted) throw combined.reason;
      worker = await this.getWorker(combined);
      if (combined.aborted) { cancel(); throw combined.reason; }
      await worker.ready.promise;
      await Promise.race([emit(runtimeEvent(prepared.input.request_id, { type: 'ready', version: PROFILE_293.version })), worker.stopped.promise]);
      if (combined.aborted) throw combined.reason;
      const active = { id: prepared.input.request_id, done: completion(), emit, terminal: false, prepared: false, headers: false, retire: false };
      worker.current = active;
      this.send(worker, { type: 'request_start', schema_version: 2, worker_id: worker.id, request_id: active.id, prepared });
      await active.done.promise;
      if (combined.aborted) throw combined.reason;
      reusable = !active.retire && !worker.failed;
    } finally {
      clearTimeout(timer);
      if (forceKill) clearTimeout(forceKill);
      combined.removeEventListener('abort', cancel);
      if (worker && !reusable) await this.retire(worker);
      this.running = false;
      this.activeAbort = null;
      this.inFlight = null;
      finished.resolve();
    }
  }

  /** 停止本轮并释放常驻进程，重复关闭安全。
   * @return 当前工作进程和读取循环均已结束。
   */
  async close(): Promise<void> {
    this.closed = true;
    this.activeAbort?.abort(new DOMException('引擎正在关闭', 'AbortError'));
    const worker = this.worker;
    if (worker && !this.running && worker.initialized && !worker.failed) {
      const forceKill = setTimeout(() => this.fail(worker, new Error('工作进程关闭超时')), 1500);
      try {
        this.send(worker, { type: 'worker_shutdown', schema_version: 2, worker_id: worker.id });
        await worker.loop;
      } finally { clearTimeout(forceKill); }
    } else if (worker) await this.retire(worker);
    await this.inFlight?.promise;
  }
}

/** 明确标记为演示的合成引擎，供页面预览与故障夹具使用。 */
export class DemoEngine implements Engine {
  readonly name = 'demo/fixture';
  readonly binarySha256 = null;
  readonly workerPid = null;

  /** 演示引擎没有持久进程。
   * @return 无资源需要释放。
   */
  async close(): Promise<void> {}

  /** 产生可审计的合成响应，不启动官方程序。
   * @param prepared 已验证输入。
   * @param signal 取消信号。
   * @param emit 事件接收器。
   * @return 演示响应结束。
   */
  async run(prepared: PreparedInput, signal: AbortSignal, emit: (event: RuntimeEvent) => Promise<void>): Promise<void> {
    const send = (payload: RuntimePayload): Promise<void> => emit(runtimeEvent(prepared.input.request_id, payload));
    const body = prepared.input.body;
    const headers: [string, string][] = [['content-type', 'application/json'], ['x-claude-code-request-class', prepared.context.requestClass], ...prepared.headers];
    const preparedBody = JSON.stringify({ ...body, metadata: { source: '演示夹具，非官方生成' } });
    await send({ type: 'cc_prepared', attempt: 1, headers, body: preparedBody, body_bytes: Buffer.byteLength(preparedBody), body_sha256: createHash('sha256').update(preparedBody).digest('hex') });
    if (signal.aborted) { await send({ type: 'completed', attempt: 1, state: 'canceled' }); return; }
    const message = { id: 'msg_demo_' + prepared.input.request_id, type: 'message', role: 'assistant', model: body.model, content: [{ type: 'text', text: '这是本地演示响应，未调用上游模型。' }], stop_reason: 'end_turn', usage: { input_tokens: 0, output_tokens: 0 } };
    const streaming = body.stream === true;
    await send({ type: 'response_headers', attempt: 1, status: 200, headers: [['content-type', streaming ? 'text/event-stream' : 'application/json'], ['request-id', 'req_demo_' + prepared.input.request_id]] });
    if (streaming) {
      const events = [
        { type: 'message_start', message: { ...message, content: [] } },
        { type: 'content_block_start', index: 0, content_block: { type: 'text', text: '' } },
        { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: message.content[0]!.text } },
        { type: 'content_block_stop', index: 0 },
        { type: 'message_delta', delta: { stop_reason: 'end_turn' }, usage: message.usage },
        { type: 'message_stop' },
      ];
      for (const event of events) {
        if (signal.aborted) { await send({ type: 'completed', attempt: 1, state: 'canceled' }); return; }
        await send({ type: 'response_chunk', attempt: 1, data_b64: Buffer.from('event: ' + event.type + '\ndata: ' + JSON.stringify(event) + '\n\n').toString('base64') });
        await Bun.sleep(8);
      }
    } else await send({ type: 'response_chunk', attempt: 1, data_b64: Buffer.from(JSON.stringify(message)).toString('base64') });
    await send({ type: 'completed', attempt: 1, state: 'success' });
  }
}

/** 创建并校验显式选定的引擎，原生失败不会暗中回退演示。
 * @param config 控制配置。
 * @return 可执行引擎。
 */
export async function createEngine(config: EngineConfig): Promise<Engine> {
  readCachePolicy(config.cachePolicy);
  readTelemetryPolicy(config.telemetryPolicy);
  if (config.mode === 'demo') return new DemoEngine();
  const engine = new NativeEngine(config);
  try { await engine.verify(); } catch (error) { throw new BridgeError('native_configuration', errorText(error), 503); }
  return engine;
}
