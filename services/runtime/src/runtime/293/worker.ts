import { AsyncLocalStorage } from 'node:async_hooks';
import { createInterface } from 'node:readline';
import { once } from 'node:events';
import { randomUUID } from 'node:crypto';
import type { PreparedInput, RuntimePayload, WorkerFrame } from '../../shared/contracts';
import { decodeWorkerCommand } from '../../shared/protocol';
import { BridgeError, errorText, isObject } from '../../shared/errors';
import { Redactor } from '../../control/redaction';
import { prepareInput } from '../../control/header-policy';
import { parseInput } from '../../shared/input';
import type { NativeBindings, NativeSession } from './native';
import { NATIVE_EXPORTS_293, PROFILE_293 } from './source-profile';
import { generateNativeRequest, runNativeJob } from './job';
import { initializeCli } from './cli';
import { readCachePolicy, readTelemetryPolicy, readCacheTtlRewrite } from '../../shared/runtime-policy';
import { createNativeTelemetry } from './telemetry';
import { readNativeIngressPolicy } from '../../shared/upstream';
import { resetRestoredRandomState } from './restore';
import { nativeErrorDiagnostics, type NativeErrorStage } from '../../shared/native-error-diagnostics';

const WORKER_ID = /^[a-f0-9-]{36}$/;

/** 在握手前报告受控配置失败，等待管道写入后才允许入口退出。
 * @param error 原生初始化异常；未知异常使用通用说明。
 * @return 错误帧已交给控制层，或管道不可用时仅写固定诊断。
 */
export async function reportStartupFailure(error: unknown): Promise<void> {
  const workerId = process.env.CCRB_WORKER_ID;
  const redactor = new Redactor();
  redactor.register({ apiKey: process.env.ANTHROPIC_API_KEY, oauthToken: process.env.CLAUDE_CODE_OAUTH_TOKEN, proxyUrl: process.env.HTTPS_PROXY });
  const message = error instanceof BridgeError && error.code === 'native_configuration' && error.status === 503 ? error.message : '固定运行时初始化失败';
  try {
    if (!workerId || !WORKER_ID.test(workerId)) throw new Error('缺少工作进程归属');
    const frame: WorkerFrame = { type: 'worker_error', schema_version: 2, worker_id: workerId, code: 'native_configuration', status: 503, error: redactor.preview(message, 2048).text || '固定运行时初始化失败' };
    // stdout.write 返回值只表示背压；退出前还必须等待写入回调，避免丢失短错误帧。
    await new Promise<void>((resolve, reject) => process.stdout.write(JSON.stringify(frame) + '\n', error => error ? reject(error) : resolve()));
  } catch { process.stderr.write('固定运行时初始化失败\n'); }
}

/** 在固定账号环境中启动串行常驻循环。
 * @param bindings 来自固定源程序的原生绑定。
 * @return 控制管道关闭且当前作业已收口。
 */
export async function startWorker(bindings: NativeBindings): Promise<void> {
  const initialWorkerId = process.env.CCRB_WORKER_ID;
  if (!initialWorkerId || !WORKER_ID.test(initialWorkerId)) throw new Error('缺少工作进程归属');
  let workerId = initialWorkerId;
  const templateId = process.env.CCRB_TEMPLATE_ID;
  if (templateId !== undefined && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(templateId)) throw new Error('模板归属不合法');
  let bound = templateId === undefined;
  let binding = false;
  const cachePolicy = readCachePolicy(process.env.CCRB_CACHE_POLICY);
  const telemetryPolicy = readTelemetryPolicy(process.env.CCRB_TELEMETRY);
  const ingressPolicy = readNativeIngressPolicy(process.env.CCRB_NATIVE_INGRESS_POLICY);
  for (const [role, names] of Object.entries(NATIVE_EXPORTS_293)) {
    const module = bindings[role as keyof NativeBindings] as unknown as Record<string, unknown>;
    for (const name of names) {
      const value = module?.[name];
      if (role === 'cliFiles' && name === 'dC' && Number.isSafeInteger(value) && Number(value) > 0) continue;
      if (role === 'cliTools' && name === 'Bq' && isObject(value) && ['getAllBaseTools', 'getTools', 'assembleToolPool'].every(key => typeof value[key] === 'function')) continue;
      if (typeof value !== 'function') throw new Error('固定版本的内部接口不匹配');
    }
  }
  const storage = new AsyncLocalStorage<{ session: NativeSession; telemetry: boolean }>();
  const telemetry = createNativeTelemetry(bindings, telemetryPolicy, () => storage.getStore()?.telemetry === true);
  await initializeCli(bindings);
  const base = bindings.state.F();
  bindings.state.yLs(() => storage.getStore());
  // 固定源的 SDK/构造依赖是惰性初始化；就绪前只做本地构造，并在原生发送前中止。
  // 初始化根与业务根隔离，不产生上游请求、请求事件或持久业务日志；其成本计入总启动时间。
  const bootstrap = prepareInput(parseInput({ request_id: 'local-bootstrap', body: { model: 'claude-sonnet-4-6', messages: [{ role: 'user', content: '本地初始化' }], max_tokens: 64, stream: false }, context: { sessionId: randomUUID(), promptId: randomUUID() } }));
  const session = bindings.state.nEr({ host: base.host, id: bootstrap.context.sessionId, project: base.project });
  await storage.run({ session, telemetry: false }, async () => {
    bindings.state.t_(bootstrap.context.sessionId, 'resume');
    await generateNativeRequest(bootstrap, bindings, new AbortController().signal);
  });
  const telemetryState = telemetry.start();
  if (templateId) Bun.gc(true);
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  let current: { id: string; abort: AbortController; finished: Promise<void> } | null = null;
  let closing = false;
  let finish!: () => void;
  const closed = new Promise<void>(resolve => { finish = resolve; });
  const write = async (frame: WorkerFrame): Promise<void> => {
    if (!process.stdout.write(JSON.stringify(frame) + '\n')) await once(process.stdout, 'drain');
  };
  const ready = (receipt?: { template_id: string; nonce: string; entropy_profile: 'bun143-wipeonfork-v1' }): WorkerFrame => ({
    type: 'worker_ready', schema_version: 2, worker_id: workerId, version: PROFILE_293.version, pid: process.pid,
    cache_policy: cachePolicy, telemetry: telemetryState, raw_input_protocol: 1, cache_ttl_rewrite_protocol: 1,
    restore_protocol: 1, ...(templateId && !receipt ? { restore_template: templateId } : {}),
    ...(receipt ? { restore_binding: receipt } : {}),
  });
  const stop = (): void => {
    closing = true;
    input.close();
    if (current) {
      current.abort.abort();
      void current.finished.finally(finish);
    } else finish();
  };
  const fatal = (): void => {
    // 畸形或跨代次输入无法安全归到当前请求，退出由控制层收口，不能改写为下一轮事件。
    process.stderr.write('工作进程协议错误，已隔离\n');
    process.exit(111);
  };
  input.on('line', (line: string) => {
    try {
      if (closing) throw new Error('工作进程正在关闭');
      const command = decodeWorkerCommand(JSON.parse(line), workerId);
      if (command.type === 'worker_shutdown') { stop(); return; }
      if (command.type === 'worker_restore_bind') {
        if (!templateId || command.template_id !== templateId || bound || binding || current) throw new Error('恢复绑定状态错误');
        binding = true;
        void (async () => {
          await resetRestoredRandomState();
          workerId = command.new_worker_id;
          process.env.CCRB_WORKER_ID = workerId;
          delete process.env.CCRB_TEMPLATE_ID;
          await write(ready({ template_id: templateId, nonce: command.nonce, entropy_profile: PROFILE_293.restore.entropyProfile }));
          bound = true;
          binding = false;
        })().catch(async error => { await reportStartupFailure(error); fatal(); });
        return;
      }
      if (!bound) throw new Error('恢复实例尚未完成绑定');
      if (command.type === 'request_cancel') {
        if (!current || current.id !== command.request_id) throw new Error('取消归属错误');
        current.abort.abort();
        return;
      }
      if (current) throw new Error('常驻进程只允许串行作业');
      const abort = new AbortController();
      const redactor = new Redactor();
      redactor.register(command.type === 'request_input' ? command.input : command.prepared.input);
      let active = true;
      let terminal = false;
      let retire = false;
      const emit = async (payload: RuntimePayload): Promise<void> => {
        if (!active || terminal) throw new Error('本轮终态后仍有事件');
        if (payload.type === 'completed' || payload.type === 'error') terminal = true;
        await write({ type: 'request_event', schema_version: 2, worker_id: workerId, request_id: command.request_id, payload });
      };
      let prepared: PreparedInput | undefined;
      let failureStage: NativeErrorStage = 'input';
      const finished = Promise.resolve().then(async () => {
        try {
          if (abort.signal.aborted) throw abort.signal.reason;
          const job = command.type === 'request_input' ? prepareInput(parseInput(command.input, [], ingressPolicy)) : command.prepared;
          prepared = job;
          failureStage = 'context';
          if (command.type === 'request_input') await emit({ type: 'header_policy', attempt: 1, decisions: job.decisions });
          // 每轮都建立独立原生根，池内复用不能继承上一轮上下文或迟到事件。
          const session = bindings.state.nEr({ host: base.host, id: job.context.sessionId, project: base.project });
          const scope = { session, telemetry: true };
          try {
            await storage.run(scope, async () => {
              bindings.state.t_(job.context.sessionId, 'resume');
              await runNativeJob(job, bindings, abort.signal, redactor, emit, cachePolicy,
                readCacheTtlRewrite(command.type === 'request_input' ? command.cache_ttl_rewrite : undefined), stage => { failureStage = stage; });
            });
          } finally { scope.telemetry = false; }
        } catch (error) {
          // 输入校验失败尚未进入原生作业，保留已初始化进程供后续正确请求使用。
          retire = prepared !== undefined;
          if (terminal) throw error;
          if (abort.signal.aborted) await emit({ type: 'completed', attempt: 1, state: 'canceled' });
          else {
            const diagnostics = nativeErrorDiagnostics(error, failureStage);
            let message = '原生异常详情不可读取';
            try { message = errorText(error); } catch { /* 异常 getter 不能阻断安全诊断。 */ }
            let contract: { code?: string; status?: number } = {};
            try {
              if (error instanceof BridgeError) contract = { code: error.code, status: error.status };
            } catch { diagnostics.inspection_failed = true; }
            await emit({ type: 'error', error: redactor.text(message), diagnostics, ...contract });
          }
        } finally {
          active = false;
        }
        if (!terminal) throw new Error('本轮缺少终态');
        await write({ type: 'worker_idle', schema_version: 2, worker_id: workerId, request_id: command.request_id });
        current = null;
        if (retire || abort.signal.aborted || closing) stop();
      }).catch(fatal);
      current = { id: command.request_id, abort, finished };
    } catch { fatal(); }
  });
  input.on('close', () => { if (!closing) stop(); });
  await write(ready());
  await closed;
  await telemetry.close();
  storage.disable();
}
