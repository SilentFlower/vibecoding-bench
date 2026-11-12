import { resolve, join } from 'node:path';
import { mkdir } from 'node:fs/promises';
import type { HeaderPair, LogFilters, NativeIngressPolicy } from '../shared/contracts';
import { BridgeError, errorText } from '../shared/errors';
import type { EngineConfig, Engine } from './engine';
import { createEngine } from './engine';
import { LogStore } from './log-store';
import { BridgeService } from './service';
import { readCachePolicy, readTelemetryPolicy } from '../shared/runtime-policy';
import type { FinalCaptureSample } from './trace';
import { readModelOverride, readNativeBaseUrl, readNativeIngressPolicy, readTlsCaptureMode, type TlsCaptureMode } from '../shared/upstream';
import { TlsVerifierEngine } from './tls-verifier';

/** 本地手工池实例的计数，不含地址凭据；budget/remaining 为 null 表示不限次数。 */
export interface LocalPoolStatus { runId: string; model: string; live: boolean; budget: number | null; reserved: number; remaining: number | null }

/** 仅启动调用方可提供的联调能力，HTTP 请求不能修改。 */
export interface ServerStartupOptions {
  nativeIngressPolicy?: NativeIngressPolicy;
  secrets?: Record<string, unknown>;
  finalCapture?: (requestId: string) => FinalCaptureSample | null;
  localPoolStatus?: () => LocalPoolStatus;
}

/** 本地控制服务的显式配置。 */
export interface ServerConfig {
  host: string;
  port: number;
  dataDir: string;
  webDir: string;
  logMode: 'off' | 'summary' | 'debug';
  maxBodyBytes: number;
  maxLogBytes: number;
  retainDays: number;
  debugRetainDays: number;
  engine: EngineConfig;
  modelOverride?: string;
  nativeIngressPolicy?: NativeIngressPolicy;
  tlsCapture?: TlsCaptureMode;
}

/** 已启动的控制服务及有序释放入口。 */
export interface RunningServer {
  server: Bun.Server<undefined>;
  store: LogStore;
  /** 先结束当前作业，再关闭 HTTP 与日志资源。
   * @return 所有服务资源已释放。
   */
  close(): Promise<void>;
}

function numberSetting(value: string | undefined, fallback: number, min: number, max: number): number {
  if (value === undefined) return fallback;
  const result = Number(value);
  if (!Number.isSafeInteger(result) || result < min || result > max) throw new Error('配置数值超出允许范围');
  return result;
}

/** 读取本机配置，默认不继承调用方或宿主的账号凭据。
 * @param env 显式控制环境。
 * @param demo 是否明确选择演示。
 * @return 本地服务配置。
 */
export function readConfig(env = process.env, demo = false): ServerConfig {
  const mode = demo || env.CCRB_MODE === 'demo' ? 'demo' : 'native';
  const logMode = env.CCRB_LOG_MODE ?? 'debug';
  if (!['off', 'summary', 'debug'].includes(logMode)) throw new Error('CCRB_LOG_MODE 必须为 off、summary 或 debug');
  const host = env.CCRB_HOST ?? '127.0.0.1';
  if (!['127.0.0.1', 'localhost', '::1'].includes(host)) throw new Error('首版服务只支持回环监听地址');
  return {
    host, port: numberSetting(env.CCRB_PORT, 8787, 0, 65535),
    dataDir: resolve(env.CCRB_DATA_DIR ?? 'data'), webDir: resolve('dist/web'),
    logMode: logMode as ServerConfig['logMode'],
    maxBodyBytes: numberSetting(env.CCRB_CAPTURE_BYTES, 1024 * 1024, 1024, 8 * 1024 * 1024),
    maxLogBytes: numberSetting(env.CCRB_LOG_BYTES, 512 * 1024 * 1024, 1024, 2 * 1024 * 1024 * 1024),
    retainDays: numberSetting(env.CCRB_RETAIN_DAYS, 7, 1, 90),
    debugRetainDays: numberSetting(env.CCRB_DEBUG_RETAIN_DAYS, 3, 1, 90),
    modelOverride: readModelOverride(env.CCRB_MODEL_OVERRIDE),
    nativeIngressPolicy: readNativeIngressPolicy(env.CCRB_NATIVE_INGRESS_POLICY),
    tlsCapture: readTlsCaptureMode(env.CCRB_TLS_CAPTURE),
    engine: {
      mode, binaryPath: env.CCRB_CLAUDE_BINARY, home: env.CCRB_CLAUDE_HOME, configDir: env.CCRB_CLAUDE_CONFIG_DIR,
      apiKey: env.CCRB_NATIVE_API_KEY, oauthToken: env.CCRB_NATIVE_OAUTH_TOKEN, proxyUrl: env.CCRB_PROXY_URL, caFile: env.CCRB_CA_FILE,
      baseUrl: readNativeBaseUrl(env.CCRB_NATIVE_BASE_URL),
      preloadPath: resolve('dist/preload.mjs'), cwd: resolve(env.CCRB_WORKDIR ?? env.CCRB_CLAUDE_HOME ?? '.'),
      timeoutMs: numberSetting(env.CCRB_TIMEOUT_MS, 0, 0, 0x7fffffff),
      cachePolicy: readCachePolicy(env.CCRB_CACHE_POLICY),
      telemetryPolicy: readTelemetryPolicy(env.CCRB_TELEMETRY),
    },
  };
}

function filters(url: URL): LogFilters {
  const result: LogFilters = {};
  for (const name of ['requestId', 'model', 'state', 'requestClass', 'sessionId', 'since', 'until'] as const) {
    const value = url.searchParams.get(name);
    if (value) {
      if (value.length > 256) throw new BridgeError('invalid_filter', '筛选参数过长');
      result[name] = value;
    }
  }
  for (const name of ['limit', 'offset'] as const) {
    const raw = url.searchParams.get(name);
    if (raw !== null) result[name] = numberSetting(raw, name === 'limit' ? 50 : 0, name === 'limit' ? 1 : 0, name === 'limit' ? 100 : 1000000);
  }
  return result;
}

function secured(response: Response): Response {
  response.headers.set('cache-control', 'no-store');
  response.headers.set('x-content-type-options', 'nosniff');
  response.headers.set('cross-origin-resource-policy', 'same-origin');
  response.headers.set('content-security-policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'");
  return response;
}

/** 启动本地只读日志页面及显式提交接口。
 * @param config 服务配置。
 * @param injectedEngine 可注入的合成或隔离原生引擎。
 * @param startup 仅启动侧可用的兼容、秘密与独立采集设置。
 * @return 已启动服务。
 */
export async function startServer(config: ServerConfig, injectedEngine?: Engine, startup: ServerStartupOptions = {}): Promise<RunningServer> {
  if (config.tlsCapture === 'verify' && (injectedEngine || startup.finalCapture)) throw new BridgeError('tls_verifier_configuration', 'TLS verify 不能与注入引擎或旧池采集器混用', 503);
  const engine = config.tlsCapture === 'verify' ? await TlsVerifierEngine.create(config.engine, config.maxBodyBytes) : injectedEngine ?? await createEngine(config.engine);
  try { await mkdir(config.dataDir, { recursive: true, mode: 0o700 }); }
  catch (error) { await engine.close(); throw error; }
  const store = new LogStore({ dbPath: join(config.dataDir, 'logs.sqlite'), bodyDir: join(config.dataDir, 'bodies'), retainDays: config.retainDays, debugRetainDays: Math.min(config.debugRetainDays, config.retainDays), maxBytes: config.maxLogBytes });
  try { await store.open(); }
  catch (error) { await engine.close(); await store.close(); throw error; }
  const finalCapture = startup.finalCapture ?? (engine.takeFinalCapture ? engine.takeFinalCapture.bind(engine) : undefined);
  const service = new BridgeService(engine, store, { mode: config.logMode, maxBodyBytes: config.maxBodyBytes, timeoutMs: config.engine.timeoutMs, modelOverride: config.modelOverride, nativeIngressPolicy: startup.nativeIngressPolicy ?? config.nativeIngressPolicy, finalCapture, secrets: { api_key: config.engine.apiKey, token: config.engine.oauthToken, proxy_url: config.engine.proxyUrl, ...startup.secrets } });
  let server: Bun.Server<undefined>;
  try {
    server = Bun.serve({
      hostname: config.host, port: config.port, maxRequestBodySize: Number.MAX_SAFE_INTEGER, idleTimeout: 0,
      async fetch(request) {
        try {
          const url = new URL(request.url);
          if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) return secured(Response.json({ error: '仅允许本地 Host' }, { status: 403 }));
          const origin = request.headers.get('origin');
          if (origin && origin !== url.origin) return secured(Response.json({ error: '不接受跨来源请求' }, { status: 403 }));
          if (request.method === 'GET' && url.pathname === '/api/health') return secured(Response.json({ engine: engine.name, logMode: config.logMode, captureError: store.error, nativeFinalCapture: !!finalCapture, tlsCapture: config.tlsCapture ?? 'off', tlsVerifier: engine.tlsVerifierIdentity ? { ...engine.tlsVerifierIdentity, state: engine.tlsVerifierState ?? 'unavailable' } : null, upstream: { endpoint: config.engine.baseUrl ? 'startup_override' : 'native_default', model: config.modelOverride ?? null, ingressPolicy: startup.nativeIngressPolicy ?? config.nativeIngressPolicy ?? 'strict' }, ...(startup.localPoolStatus ? { localPool: startup.localPoolStatus() } : {}), runtimePolicy: { cachePolicy: config.engine.cachePolicy ?? 'preserve', telemetry: config.engine.telemetryPolicy ?? 'off', telemetryState: engine.telemetryState ?? 'unavailable' } }));
          if (request.method === 'GET' && url.pathname === '/api/logs') return secured(Response.json(store.list(filters(url))));
          if (request.method === 'GET' && url.pathname.startsWith('/api/logs/')) {
            const id = decodeURIComponent(url.pathname.slice('/api/logs/'.length));
            if (!/^[A-Za-z0-9_-]{1,128}$/.test(id)) throw new BridgeError('invalid_id', '日志 ID 不合法');
            const detail = await store.detail(id);
            return secured(detail ? Response.json(detail) : Response.json({ error: '记录不存在或已过保留期' }, { status: 404 }));
          }
          if (request.method === 'POST' && (url.pathname === '/v1/messages' || url.pathname === '/api/requests')) {
            const encoding = request.headers.get('content-encoding');
            if (encoding && encoding !== 'identity') throw new BridgeError('unsupported_encoding', '首版 HTTP 入口接收未压缩 JSON', 415);
            const raw = await request.text();
            let value: unknown;
            try { value = JSON.parse(raw); } catch { value = raw; }
            return secured(await service.submit(value, [...request.headers.entries()] as HeaderPair[], request.signal, raw));
          }
          if (request.method === 'GET' && ['/', '/app.js', '/style.css'].includes(url.pathname)) {
            const name = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
            const file = Bun.file(join(config.webDir, name));
            if (!await file.exists()) return secured(Response.json({ error: '页面尚未构建，请运行 bun run build' }, { status: 503 }));
            return secured(new Response(file));
          }
          return secured(Response.json({ error: '接口不存在' }, { status: 404 }));
        } catch (error) {
          return secured(Response.json({ error: error instanceof BridgeError ? error.message : '请求处理失败' }, { status: error instanceof BridgeError ? error.status : 400 }));
        }
      },
    });
  } catch (error) {
    await engine.close();
    await store.close();
    throw error;
  }
  return {
    server, store,
    async close() { await service.close(); await server.stop(true); await store.close(); },
  };
}
