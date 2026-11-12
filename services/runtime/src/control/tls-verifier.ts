import { createHash, randomUUID, randomBytes } from 'node:crypto';
import { mkdtemp, open, readFile, rm, writeFile, type FileHandle } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { isIP } from 'node:net';
import type { PreparedInput, RuntimeEvent } from '../shared/contracts';
import { BridgeError } from '../shared/errors';
import { runtimeEvent } from '../shared/protocol';
import { decodeTlsVerifierFrame, expectedTlsWrite, type TlsBinding, type TlsExpected, type TlsVerifierEvent } from '../shared/tls-verifier-protocol';
import { readNativeBaseUrl } from '../shared/upstream';
import { TLS_VERIFIER_IDENTITY } from '../runtime/tls-verifier-profile';
import { verifyRuntime } from '../runtime/profile';
import { NativeEngine, type Engine, type EngineConfig } from './engine';
import type { FinalCaptureSample } from './trace';

type HelperChild = Bun.Subprocess<'pipe', 'pipe', 'pipe'>;
interface Pending { type: 'ready' | 'ack'; resolve(event: TlsVerifierEvent): void; reject(error: unknown): void }
interface Active {
  binding: TlsBinding;
  expected: TlsExpected | null;
  emit(event: RuntimeEvent): Promise<void>;
  abort: AbortController;
  captured: boolean;
}

function failure(): BridgeError { return new BridgeError('tls_verifier_unavailable', 'TLS 验证器不可用，未切换发送方式或重放请求', 503); }

async function openssl(args: string[]): Promise<void> {
  const child = Bun.spawn(['openssl', ...args], { stdin: 'ignore', stdout: 'ignore', stderr: 'ignore' });
  if (await child.exited !== 0) throw new BridgeError('tls_verifier_configuration', '生成实例私有证书失败，需要本机 OpenSSL', 503);
}

/** 使用固定画像 TLS 辅助进程的可选引擎；业务构造仍由同一原版 CC 完成。 */
export class TlsVerifierEngine implements Engine {
  readonly name = 'claude-code/2.1.293+tls-verifier';
  readonly tlsVerifierIdentity = TLS_VERIFIER_IDENTITY;
  private readonly instance = randomUUID();
  private readonly pending = new Map<number, Pending>();
  private readonly samples = new Map<string, FinalCaptureSample>();
  private readonly connections = new Map<number, string>();
  private active: Active | null = null;
  private generation: { pid: number; id: string } | null = null;
  private commandId = 0;
  private sequence = 0;
  private failed: unknown = null;
  private closed = false;
  private stopping = false;
  private running = false;
  private loop: Promise<void> = Promise.resolve();

  private constructor(private native: NativeEngine, private readonly child: HelperChild, private readonly handle: FileHandle, private readonly root: string, private readonly previewLimit: number) {}

  /** 核验独立执行体并仅在 verify 模式创建私有监听、证书和辅助进程。
   * @param config 启动侧冻结的原生配置。
   * @param previewLimit 最后写出正文预览上限。
   * @return 可用验证引擎；未支持组合明确失败。
   */
  static async create(config: EngineConfig, previewLimit: number): Promise<TlsVerifierEngine> {
    const target = new URL(readNativeBaseUrl(config.baseUrl) ?? 'https://api.anthropic.com');
    if (process.platform !== 'linux' || process.arch !== 'x64' || config.mode !== 'native' || target.protocol !== 'https:' || (config.telemetryPolicy ?? 'off') !== 'off' || !config.binaryPath) throw new BridgeError('tls_verifier_configuration', 'TLS verify 仅支持 Linux x64 固定官方原版、HTTPS Messages 和关闭遥测的组合', 503);
    const verified = await verifyRuntime(config.binaryPath);
    try { if (verified.identity.kind !== 'original') throw new BridgeError('tls_verifier_configuration', 'TLS verify 尚未验证旧精简运行时', 503); }
    finally { await verified.handle.close(); }
    let proxy: { host: string; port: number; authorization: string | null } | null = null;
    if (config.proxyUrl) {
      let value: URL;
      try { value = new URL(config.proxyUrl); } catch { throw new BridgeError('tls_verifier_configuration', 'TLS verify 上游代理地址无效', 503); }
      if (value.protocol !== 'http:' || (value.pathname !== '/' && value.pathname !== '') || value.search || value.hash) throw new BridgeError('tls_verifier_configuration', 'TLS verify 当前仅支持 HTTP CONNECT 上游代理', 503);
      proxy = { host: value.hostname.replace(/^\[|\]$/g, ''), port: Number(value.port || 80), authorization: value.username || value.password ? 'Basic ' + Buffer.from(decodeURIComponent(value.username) + ':' + decodeURIComponent(value.password)).toString('base64') : null };
    }
    const handle = await open(resolve(import.meta.dir, '../../dist/tls-verifier'), 'r').catch(() => { throw failure(); });
    let root: string | null = null;
    let child: HelperChild | null = null;
    try {
      const before = await handle.stat({ bigint: true });
      const hash = createHash('sha256');
      for await (const chunk of handle.createReadStream({ start: 0, autoClose: false })) hash.update(chunk);
      const after = await handle.stat({ bigint: true });
      if (hash.digest('hex') !== TLS_VERIFIER_IDENTITY.sha256 || before.ino !== after.ino || before.size !== after.size || before.mtimeNs !== after.mtimeNs || before.ctimeNs !== after.ctimeNs) throw new BridgeError('tls_verifier_identity', 'TLS 辅助程序校验不匹配，需要构建并验证登记产物', 503);
      root = await mkdtemp(join(tmpdir(), 'ccrb-tls-'));
      const host = target.hostname.replace(/^\[|\]$/g, '');
      const ca = join(root, 'ca.pem');
      const key = join(root, 'leaf.key');
      const certificate = join(root, 'leaf.pem');
      const extension = join(root, 'leaf.ext');
      await writeFile(extension, 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=' + (isIP(host) ? 'IP:' : 'DNS:') + host + '\n', { mode: 0o600 });
      await openssl(['req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes', '-keyout', join(root, 'ca.key'), '-out', ca, '-days', '1', '-subj', '/CN=CCRB private verification CA', '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign']);
      await openssl(['req', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes', '-keyout', key, '-out', join(root, 'leaf.csr'), '-subj', '/CN=CCRB private verification endpoint']);
      await openssl(['x509', '-req', '-in', join(root, 'leaf.csr'), '-CA', ca, '-CAkey', join(root, 'ca.key'), '-CAcreateserial', '-out', certificate, '-days', '1', '-extfile', extension]);
      const trust = join(root, 'worker-trust.pem');
      await writeFile(trust, await readFile(ca, 'utf8') + (config.caFile ? '\n' + await readFile(config.caFile, 'utf8') : ''), { mode: 0o600 });
      child = Bun.spawn(['/proc/' + process.pid + '/fd/' + handle.fd], { env: { PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8' }, stdin: 'pipe', stdout: 'pipe', stderr: 'pipe' });
      const token = randomBytes(32).toString('hex');
      // 原生实例只信任本次私有 CA；上游仍使用独立的配置和信任根。
      const native = new NativeEngine({ ...config, proxyUrl: 'http://ccrb:' + token + '@127.0.0.1:1', caFile: trust });
      const engine = new TlsVerifierEngine(native, child, handle, root, previewLimit);
      engine.loop = engine.read();
      const ready = await engine.command({ type: 'init', config: { target_host: host, target_port: Number(target.port || 443), authority: target.hostname + ':' + (target.port || '443'), host_header: target.host, certificate_file: certificate, key_file: key, ca_file: config.caFile ?? null, proxy, authorization: 'Basic ' + Buffer.from('ccrb:' + token).toString('base64'), capture_bytes: previewLimit } });
      if (ready.type !== 'ready' || ready.pid !== child.pid) throw failure();
      // 只在任何原生工作进程创建前设置本次私有代理。
      engine.native = new NativeEngine({ ...config, proxyUrl: 'http://ccrb:' + token + '@127.0.0.1:' + ready.port, caFile: trust });
      await engine.native.verify();
      return engine;
    } catch (error) {
      child?.kill('SIGKILL');
      if (child) await child.exited;
      await handle.close();
      if (root) await rm(root, { recursive: true, force: true });
      throw error;
    }
  }

  /** 官方工作进程的实际执行体身份。
   * @return 已核验的官方 SHA256。
   */
  get binarySha256(): string { return this.native.binarySha256; }
  /** 当前物理进程；读取不会创建工作进程。
   * @return PID 或空。
   */
  get workerPid(): number | null { return this.native.workerPid; }
  /** 本组合只支持关闭遥测。
   * @return 原生实际遥测状态。
   */
  get telemetryState() { return this.native.telemetryState; }
  /** 当前辅助进程可用性，不把配置开启当作采集成功。
   * @return 就绪、失败或关闭状态。
   */
  get tlsVerifierState(): 'ready' | 'failed' | 'closed' { return this.closed ? 'closed' : this.failed ? 'failed' : 'ready'; }

  private fail(error: unknown): void {
    if (this.failed) return;
    this.failed = error;
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
    this.active?.abort.abort(error);
    this.child.kill('SIGKILL');
  }

  private command(operation: Record<string, unknown>): Promise<TlsVerifierEvent> {
    if (this.failed || this.closed) return Promise.reject(this.failed ?? failure());
    const commandId = ++this.commandId;
    return new Promise((resolve, reject) => {
      this.pending.set(commandId, { type: operation.type === 'init' ? 'ready' : 'ack', resolve, reject });
      try { this.child.stdin.write(JSON.stringify({ schema_version: 1, instance_id: this.instance, command_id: commandId, operation }) + '\n'); }
      catch (error) { this.fail(error); }
    });
  }

  private async read(): Promise<void> {
    const diagnostics = (async () => { const reader = this.child.stderr.getReader(); try { while (!(await reader.read()).done) {} } finally { reader.releaseLock(); } })().catch(error => this.fail(error));
    try {
      const reader = this.child.stdout.getReader();
      const decoder = new TextDecoder('utf-8', { fatal: true });
      let pending = '';
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        pending += decoder.decode(chunk.value, { stream: true });
        if (pending.length > this.previewLimit * 2 + 512 * 1024) throw failure();
        let index: number;
        while ((index = pending.indexOf('\n')) >= 0) {
          const event = decodeTlsVerifierFrame(pending.slice(0, index), this.instance, this.previewLimit);
          pending = pending.slice(index + 1);
          if (event.type === 'ready' || event.type === 'ack') {
            const waiter = this.pending.get(event.command_id);
            if (!waiter || waiter.type !== event.type) throw failure();
            this.pending.delete(event.command_id);
            if (event.type === 'ack' && event.error) waiter.reject(failure());
            else waiter.resolve(event);
          } else if (event.type === 'capture') {
            const capture = event.capture;
            const active = this.active;
            if (!active || !active.expected || active.captured || capture.binding.request_id !== active.binding.request_id || capture.binding.worker_id !== active.binding.worker_id || capture.binding.worker_pid !== active.binding.worker_pid || capture.sequence !== this.sequence + 1) throw failure();
            const owner = this.connections.get(capture.connection_id);
            if (owner && owner !== active.binding.worker_id) throw failure();
            this.connections.set(capture.connection_id, active.binding.worker_id);
            // 每个物理进程串行发送；只保留当前连接归属，避免长期重连使诊断索引无限增长。
            for (const id of this.connections.keys()) if (id !== capture.connection_id) this.connections.delete(id);
            this.sequence = capture.sequence;
            active.captured = true;
            if (capture.verified && (capture.normalized_sha256 !== active.expected.body_sha256 || capture.body_bytes !== active.expected.body_bytes)) throw failure();
            const preview = Buffer.from(capture.body_preview_b64, 'base64');
            this.samples.set(active.binding.request_id, { body: new TextDecoder().decode(preview, { stream: preview.length < capture.body_bytes }), headers: capture.headers, httpVersion: '1.1', capturedAt: new Date(capture.captured_unix_ms).toISOString(), verified: capture.verified, source: 'native_tls_verifier', observedBytes: capture.body_bytes, sha256: capture.body_sha256, complete: capture.complete, flushed: capture.flushed, note: '固定画像 TLS 本地写出，非上游实收证明；worker=' + capture.binding.worker_id + '；PID=' + capture.binding.worker_pid + '；connection=' + capture.connection_id + '；HTTP bytes=' + capture.http_bytes + '；HTTP SHA256=' + capture.http_sha256 + '；刷出=' + capture.flushed + '；原因=' + capture.reason });
            await active.emit(runtimeEvent(active.binding.request_id, { type: 'final_capture_ready', attempt: 1 }));
          } else if (event.type === 'failure' && this.active && event.binding?.request_id === this.active.binding.request_id && event.binding.worker_id === this.active.binding.worker_id && !this.active.captured) {
            this.active.captured = true;
            this.samples.set(event.binding.request_id, this.missingSample(event.reason));
            await this.active.emit(runtimeEvent(event.binding.request_id, { type: 'final_capture_ready', attempt: 1 }));
          }
        }
      }
      decoder.decode();
      if (!this.stopping || this.pending.size || pending) throw failure();
    } catch (error) { this.fail(error); }
    finally { await Promise.allSettled([diagnostics, this.child.exited]); }
  }

  /** 取得并清除本请求的最终写出样本。
   * @param requestId 当前请求 ID。
   * @return 最后 TLS 写出观测；缺失时为空，不回填准备值。
   */
  takeFinalCapture(requestId: string): FinalCaptureSample | null {
    const sample = this.samples.get(requestId) ?? (this.failed ? this.missingSample('private_channel_failed') : null);
    this.samples.delete(requestId);
    return sample;
  }

  private missingSample(reason: string): FinalCaptureSample {
    return { body: '', headers: [], httpVersion: '1.1', capturedAt: new Date().toISOString(), source: 'native_tls_verifier', verified: false, observedBytes: 0, sha256: null, complete: false, flushed: false, status: 'failed', note: '未取得最后 TLS 写出证据，观测范围未知；原因=' + reason };
  }

  /** 保持原版单轮执行，在实际 ready 后绑定物理进程。
   * @param prepared 已验证业务及归因上下文。
   * @param signal 调用方取消。
   * @param emit 有背压的逻辑事件消费者。
   * @return 原版执行与采集收口完成。
   */
  async run(prepared: PreparedInput, signal: AbortSignal, emit: (event: RuntimeEvent) => Promise<void>): Promise<void> {
    if (this.failed || this.closed) throw this.failed ?? failure();
    if (this.running) throw new BridgeError('runtime_busy', 'TLS 验证器正在处理其他作业', 429);
    this.running = true;
    const abort = new AbortController();
    let terminal: RuntimeEvent | null = null;
    let bound = false;
    let error: unknown;
    try {
      await this.native.run(prepared, AbortSignal.any([signal, abort.signal]), async event => {
        if (event.type === 'ready') {
          const pid = this.native.workerPid;
          if (!pid) throw failure();
          if (this.generation?.pid !== pid) this.generation = { pid, id: randomUUID() };
          this.active = { binding: { request_id: prepared.input.request_id, worker_id: this.generation.id, worker_pid: pid }, expected: null, emit, abort, captured: false };
          await this.command({ type: 'begin', binding: this.active.binding });
          bound = true;
        } else if (event.type === 'cc_prepared') {
          if (!this.active) throw failure();
          this.active.expected = expectedTlsWrite(event);
          await emit(event);
          await this.command({ type: 'expected', expected: this.active.expected });
          return;
        } else if (event.type === 'completed' || event.type === 'error') { terminal = event; return; }
        await emit(event);
      });
    } catch (caught) { error = caught; }
    finally {
      if (bound) {
        try { await this.command({ type: 'finish', request_id: prepared.input.request_id, close_connections: !!error || signal.aborted || this.native.workerPid === null }); }
        catch { /* 采集通道的缺失由 wire_final 显示，不能触发模型重放。 */ }
      }
      this.active = null;
      this.running = false;
      if (this.native.workerPid === null) { this.generation = null; this.connections.clear(); }
    }
    if (error) throw error;
    if (!terminal) throw failure();
    await emit(terminal);
  }

  /** 有序取消原生作业、关闭辅助程序并删除私有证书。
   * @return 所有私有资源已释放。
   */
  async close(): Promise<void> {
    if (this.closed) return;
    await this.native.close();
    this.stopping = true;
    const kill = setTimeout(() => this.child.kill('SIGKILL'), 1500);
    try {
      if (!this.failed) await this.command({ type: 'shutdown' });
      this.child.stdin.end();
      await this.loop;
    } finally {
      clearTimeout(kill); this.closed = true;
      await this.handle.close();
      await rm(this.root, { recursive: true, force: true });
    }
  }
}
