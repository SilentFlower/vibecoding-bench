import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
import type { HeaderPair, JsonObject } from '../../src/shared/contracts';
import { isObject } from '../../src/shared/errors';
import { Redactor } from '../../src/control/redaction';
import { decodeLocalPoolStartup, type LocalPoolStartupDiagnostics } from './local-pool-startup';

export const POOL_MODEL = 'deepseek-flash';
export const CAPTURE_LIMIT = 1024 * 1024;
/** 仅用于有限自动验收的请求预算，不限制用户手工转发。 */
export const REQUEST_LIMIT = 2 * 1024 * 1024;
export const SYNTHETIC_KEY = 'ccrb-pool-synthetic-cc-key';

/** 仅表示本地观测进度，不能用阶段顺序推断模型是否执行或是否可重试。 */
export const POOL_TRANSPORT_PHASES = ['unknown', 'before_send', 'sending', 'awaiting_headers', 'response_body'] as const;
/** 可持久化的网络及本地转发错误码；任意异常文本不进入诊断。 */
export const POOL_FAILURE_CODES = new Set(['ENOTFOUND','EAI_AGAIN','ECONNREFUSED','ECONNRESET','ENETUNREACH','EHOSTUNREACH','ETIMEDOUT','DEPTH_ZERO_SELF_SIGNED_CERT','UNABLE_TO_VERIFY_LEAF_SIGNATURE','CERT_HAS_EXPIRED','ERR_TLS_CERT_ALTNAME_INVALID','UND_ERR_CONNECT_TIMEOUT','UND_ERR_HEADERS_TIMEOUT','UND_ERR_SOCKET','UND_ERR_REQ_CONTENT_LENGTH_MISMATCH','ERR_INVALID_CHAR','CALLER_CANCELED','POOL_TIMEOUT','POOL_FETCH_ERROR','REQUEST_REJECTED','POOL_BUDGET_EXHAUSTED']);

/** 池第二段的安全观测；计数属于关联连接累计值，null 明确表示没有证据。 */
export interface PoolTransportDiagnostics {
  phase: typeof POOL_TRANSPORT_PHASES[number];
  bodySentObserved: boolean | null;
  connectionBytesWritten: number | null;
  connectionBytesRead: number | null;
}

/** 池联调配置；手工 maxRequests=null 不限次数，timeoutMs=0 不附加请求总时限。 */
export interface PoolConfig { baseUrl: string; apiKey: string; live: boolean; maxRequests: number | null; timeoutMs: number; mode?: 'acceptance' | 'manual' }
/** 原始观测的哈希与脱敏预览分开保存。 */
export interface BodySample { bytes: number; sha256: string; storedBytes: number; text: string; status: 'complete' | 'truncated' | 'incomplete' }
/** 第二段参数只描述提交给客户端的值，不冒充池端原始头。 */
export interface PoolPrepared { url: string; model: string; headers: HeaderPair[]; body: BodySample; changes: { name: string; reason: string }[] }
/** 采集器的可信进程仍需通过同一私有协议边界解码。 */
export type ForwarderFrame =
  | { type: 'ready'; namespace: string; rawHeadersMatched: boolean }
  | { type: 'captured'; id: number; method: string; path: string; httpVersion: string; headers: HeaderPair[]; body: string }
  | { type: 'finished'; id: number; attempted: boolean; outcome: string; prepared?: PoolPrepared; statusCode: number; upstreamStatus: number | null; headers: HeaderPair[]; response: BodySample; error?: string; failureCode?: string; transportDiagnostics?: PoolTransportDiagnostics }
  | { type: 'fatal'; message: string; startup?: LocalPoolStartupDiagnostics };
/** 每个场景的输入与预期由宿主指定，不含池凭据。 */
export interface PoolScene { id: string; input: JsonObject; cancel: boolean; fixture: string; cachePolicy: 'preserve' | 'sub2api'; expectedStatus: number }
/** 驱动回执只在私有管道传输，统一由宿主脱敏后落盘。 */
export interface DriverResult { type: 'result'; id: string; ingress: string; context: JsonObject | null; prepared: { body: BodySample; headers: HeaderPair[] } | null; response: BodySample; headers: HeaderPair[]; statusCode: number; state: string; elapsedMs: number; workerPid: number | null; workerEnvNames: string[]; syntheticCredential: boolean; proxyRequests: number; rejectedRequests: number; telemetry: string }
/** 隔离驱动的启动、结果和退出回执。 */
export type DriverFrame = DriverResult | { type: 'driver_ready'; namespace: string; interfaces: string[]; envNames: string[]; rejectedTargetProbe: boolean } | { type: 'fatal'; message: string };

/** 解析受保护配置，绝不执行文件内容。 @param path 显式 env 文件。 @return 只读取得的池配置。 */
export async function loadPoolConfig(path: string): Promise<PoolConfig> {
  const info = await stat(path);
  if (!info.isFile() || (info.mode & 0o077) !== 0 || info.size > 65536) throw new Error('池配置必须为仅所有者可读的有界普通文件');
  const values = new Map<string, string>();
  for (const line of (await readFile(path, 'utf8')).split(/\r?\n/)) {
    if (!line.trim() || line.trimStart().startsWith('#')) continue;
    const match = /^(?:export\s+)?([A-Z_][A-Z0-9_]*)=(.*)$/.exec(line);
    if (!match || values.has(match[1]!)) throw new Error('池配置格式错误或字段重复');
    let value = match[2]!.trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
    values.set(match[1]!, value);
  }
  const pick = (local: string, legacy: string): string => {
    const a = values.get(local), b = values.get(legacy);
    if (a !== undefined && b !== undefined && a !== b) throw new Error('池配置来源冲突');
    return a ?? b ?? '';
  };
  const config: PoolConfig = { baseUrl: pick('CCRB_TEST_POOL_BASE_URL', 'PROJECT_REQUESTER_BASE_URL'), apiKey: pick('CCRB_TEST_POOL_API_KEY', 'PROJECT_REQUESTER_API_KEY'), live: true, maxRequests: 3, timeoutMs: 30000 };
  validatePoolConfig(config);
  return config;
}

/** 只给真实池 Node 端复用宿主标准代理，不进入 CC 驱动。 @param env 宿主环境。 @param live 是否真实池。 @return 无凭据的标准代理环境白名单。 */
export function poolProxyEnvironment(env: Record<string, string | undefined>, live: boolean): Record<string, string> {
  if (!live) return {};
  const result: Record<string, string> = {};
  for (const name of ['HTTP_PROXY','HTTPS_PROXY','NO_PROXY']) {
    const upper = env[name], lower = env[name.toLowerCase()];
    if (upper !== undefined && lower !== undefined && upper !== lower) throw new Error('宿主代理大小写来源冲突');
    const value = upper ?? lower; if (!value) continue;
    if (value.length > 8192 || /[\x00-\x1f\x7f]/.test(value)) throw new Error('宿主代理值不合法');
    if (name !== 'NO_PROXY') {
      let url: URL; try { url = new URL(value); } catch { throw new Error('宿主代理 URL 不合法'); }
      if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname !== '/' || /(^|\.)anthropic\.com$|(^|\.)claude\.ai$/i.test(url.hostname.replace(/\.$/, ''))) throw new Error('测试池只接纳无 URL 凭据的 HTTP(S) 宿主代理');
    }
    result[name] = value;
  }
  return result;
}

/** 校验目标及调用上限。 @param config 已解析的本机配置。 @return 非法配置抛出受控错误。 */
export function validatePoolConfig(config: PoolConfig): void {
  if (typeof config.live !== 'boolean' || typeof config.apiKey !== 'string' || typeof config.baseUrl !== 'string') throw new Error('池配置字段类型不合法');
  if (config.mode !== undefined && !['acceptance', 'manual'].includes(config.mode)) throw new Error('池运行模式不合法');
  let url: URL;
  try { url = new URL(config.baseUrl); } catch { throw new Error('池 Base URL 不合法'); }
  const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname);
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || /(^|\.)anthropic\.com$|(^|\.)claude\.ai$/i.test(url.hostname.replace(/\.$/, '')) || (config.live ? url.protocol !== 'https:' : !loopback)) throw new Error('池目标不符合显式测试边界');
  // 仅接纳常见 ASCII 令牌，避免 JSON 的引号、反斜杠或 Unicode 转义绕过原文字面脱敏。
  if (!/^[A-Za-z0-9._~-]{4,4096}$/.test(config.apiKey)) throw new Error('池凭据格式不受支持，仅接受 4–4096 位 ASCII 字母数字及 ._~-');
  const validRequests = config.maxRequests === null ? config.mode === 'manual' : Number.isSafeInteger(config.maxRequests) && config.maxRequests >= 1 && config.maxRequests <= (config.mode === 'manual' ? 20 : config.live ? 3 : 100);
  const validTimeout = Number.isSafeInteger(config.timeoutMs) && (config.mode === 'manual' ? config.timeoutMs >= 0 && config.timeoutMs <= 0x7fffffff : config.timeoutMs >= 50 && config.timeoutMs <= 30000);
  if (!validRequests || !validTimeout) throw new Error('池请求预算不合法');
}

/** 显式轮次绑定独立账本，默认保持首轮，不能借路径穿越覆盖旧记录。 @param runId 经操作者选择的轮次。 @return artifacts 下的账本文件名。 */
export function poolLedgerName(runId = 'first-run'): string {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(runId)) throw new Error('真实验收轮次 ID 不合法');
  return 'pool-tls-forwarder-live-' + runId + '.json';
}

/** 拼接唯一 Messages 路径，保留原生查询串。 @param base 池地址。 @param path 原生路径。 @return 确定的第二段 URL。 */
export function poolMessagesUrl(base: string, path: string): string {
  const original = new URL(path, 'https://api.anthropic.com');
  if (original.origin !== 'https://api.anthropic.com' || original.pathname !== '/v1/messages') throw new Error('仅允许固定 Messages 路径');
  const target = new URL(base);
  const prefix = target.pathname.replace(/\/+$/, '');
  if (prefix.endsWith('/messages')) throw new Error('Base URL 应为服务前缀而非完整 Messages 地址');
  target.pathname = prefix + (prefix.endsWith('/v1') ? '/messages' : '/v1/messages');
  target.search = original.search;
  return target.href;
}

/** 流式记录有界前缀，原始字节继续参与哈希。 */
export class BodyCapture {
  private hash = createHash('sha256');
  private chunks: Buffer[] = [];
  private saved = 0;
  private bytes = 0;
  /** 绑定预览上限。 @param limit 最大保存前缀。 */
  constructor(private readonly limit = CAPTURE_LIMIT) {}
  /** 添加原始片段。 @param bytes 观测字节。 @return 无。 */
  push(bytes: Uint8Array): void {
    this.hash.update(bytes); this.bytes += bytes.length;
    if (this.saved < this.limit) { const part = Buffer.from(bytes.subarray(0, this.limit - this.saved)); this.chunks.push(part); this.saved += part.length; }
  }
  /** 收口原始哈希及安全预览，只调用一次。 @param redactor 已注册秘密。 @param complete 是否完整 EOF。 @return 可持久化样本。 */
  finish(redactor: Redactor, complete = true): BodySample {
    const preview = redactor.preview(new TextDecoder().decode(Buffer.concat(this.chunks), { stream: !complete || this.bytes > this.saved }), this.limit, !complete || this.bytes > this.saved);
    return { bytes: this.bytes, sha256: this.hash.digest('hex'), storedBytes: Buffer.byteLength(preview.text), text: preview.text, status: !complete ? 'incomplete' : preview.truncated ? 'truncated' : 'complete' };
  }
}

/** 从完整字节生成独立样本。 @param raw 原始文本。 @param redactor 已注册秘密。 @return 脱敏快照。 */
export function sample(raw: string, redactor: Redactor): BodySample { const capture = new BodyCapture(); capture.push(Buffer.from(raw)); return capture.finish(redactor); }

/** 仅在原生处理后独立核验，不能用于生成出站 CCH。 @param raw TLS 实收正文。 @return 实际与独立计算值。 */
export function verifyCch(raw: string): { actual: string; expected: string } {
  const body: unknown = JSON.parse(raw);
  if (!isObject(body) || JSON.stringify(body) !== raw || !Array.isArray(body.system)) throw new Error('原生最终正文不满足核验条件');
  const billing = body.system.find(block => isObject(block) && typeof block.text === 'string' && block.text.startsWith('x-anthropic-billing-header:'));
  if (!isObject(billing) || typeof billing.text !== 'string') throw new Error('缺少原生 billing');
  const actual = /\bcch=([a-f0-9]{5})/.exec(billing.text)?.[1];
  if (!actual || actual === '00000') throw new Error('未观测到完成的原生 CCH');
  billing.text = billing.text.replace(/\bcch=[a-f0-9]{5}/, 'cch=00000'); delete body.max_tokens;
  const neutralize = (value: unknown): unknown => Array.isArray(value) ? value.map(neutralize) : isObject(value) ? Object.fromEntries(Object.entries(value).map(([key, child]) => [key, key === 'model' && typeof child === 'string' ? '' : neutralize(child)])) : value;
  const expected = (Bun.hash.xxHash64(JSON.stringify(neutralize(body)), 0x4D659218E32A3268n) & 0xfffffn).toString(16).padStart(5, '0');
  if (actual !== expected) throw new Error('原生最终 CCH 核验失败');
  return { actual, expected };
}

/** 明确第二段的必要变化。 @param raw 完整原生正文。 @param headers 原始头。 @param path 原生路径。 @param config 池配置。 @return 提交参数和无秘密诊断。 */
export function preparePoolRequest(raw: string, headers: HeaderPair[], path: string, config: PoolConfig): { url: string; headers: HeaderPair[]; body: string; changes: PoolPrepared['changes'] } {
  const value: unknown = JSON.parse(raw);
  if (!isObject(value) || typeof value.model !== 'string') throw new Error('模型正文不合法');
  // 自动验收继续限制付费预算；手工转发保留原生输出参数，由池判断模型能力。
  if (config.live && config.mode !== 'manual' && (!Number.isSafeInteger(value.max_tokens) || Number(value.max_tokens) < 1 || Number(value.max_tokens) > 128)) throw new Error('真实验收调用预算不合法');
  const blocked = new Set(['host','content-length','connection','keep-alive','proxy-connection','transfer-encoding','te','trailer','upgrade','authorization','x-api-key','proxy-authorization','cookie']);
  for (const [name, content] of headers) if (name.toLowerCase() === 'connection') for (const token of content.split(',')) blocked.add(token.trim().toLowerCase());
  const changes: PoolPrepared['changes'] = [{ name: 'model', reason: '仅第二段映射为 deepseek-flash' }, { name: 'host', reason: '由池目标重建' }, { name: 'content-length', reason: '由修改后的实体长度重建' }];
  const forwarded = headers.filter(([name]) => { if (!blocked.has(name.toLowerCase())) return true; changes.push({ name, reason: /authorization|key|cookie/i.test(name) ? '原 CC 或代理凭据不进入池' : '连接或实体传输字段重新生成' }); return false; });
  const body = JSON.stringify({ ...value, model: POOL_MODEL });
  forwarded.push(['x-api-key', config.apiKey], ['content-length', String(Buffer.byteLength(body))]);
  return { url: poolMessagesUrl(config.baseUrl, path), headers: forwarded, body, changes };
}

/** 规范化可选诊断，损坏观测降为未知，不影响模型结果或保留额外载荷。
 * @param value 私有帧中的可选观测对象。
 * @return 仅含固定字段的安全诊断。
 */
export function decodePoolTransportDiagnostics(value: unknown): PoolTransportDiagnostics {
  const counter = (value: unknown): number | null => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
  return {
    phase: POOL_TRANSPORT_PHASES.find(phase => isObject(value) && value.phase === phase) ?? 'unknown',
    bodySentObserved: isObject(value) && typeof value.bodySentObserved === 'boolean' ? value.bodySentObserved : null,
    connectionBytesWritten: isObject(value) ? counter(value.connectionBytesWritten) : null,
    connectionBytesRead: isObject(value) ? counter(value.connectionBytesRead) : null,
  };
}

/** 校验私有 JSONL 基础及每种字段，统一供控制端消费。 @param line 单条私有帧。 @return 已验证的采集器帧。 */
export function decodeForwarderFrame(line: string): ForwarderFrame {
  const value: unknown = JSON.parse(line);
  const pairs = (x: unknown): x is HeaderPair[] => Array.isArray(x) && x.every(p => Array.isArray(p) && p.length === 2 && p.every(v => typeof v === 'string'));
  const body = (x: unknown): x is BodySample => isObject(x) && Number.isSafeInteger(x.bytes) && Number(x.bytes) >= 0 && typeof x.sha256 === 'string' && /^[a-f0-9]{64}$/.test(x.sha256) && Number.isSafeInteger(x.storedBytes) && Number(x.storedBytes) >= 0 && Number(x.storedBytes) <= CAPTURE_LIMIT && typeof x.text === 'string' && Buffer.byteLength(x.text) === x.storedBytes && ['complete','truncated','incomplete'].includes(String(x.status));
  if (isObject(value)) {
    if (value.type === 'ready' && typeof value.namespace === 'string' && typeof value.rawHeadersMatched === 'boolean') return value as unknown as ForwarderFrame;
    if (value.type === 'fatal' && typeof value.message === 'string') return { type: 'fatal', message: 'TLS 采集转发器已失败', ...(value.startup === undefined ? {} : { startup: decodeLocalPoolStartup(value.startup) }) };
    if (Number.isSafeInteger(value.id) && Number(value.id) > 0) {
      if (value.type === 'captured' && ['method','path','httpVersion','body'].every(key => typeof value[key] === 'string') && pairs(value.headers)) return value as unknown as ForwarderFrame;
      if (value.type === 'finished' && typeof value.attempted === 'boolean' && typeof value.outcome === 'string' && Number.isInteger(value.statusCode) && (value.upstreamStatus === null || Number.isInteger(value.upstreamStatus)) && pairs(value.headers) && body(value.response) && (value.error === undefined || typeof value.error === 'string') && (value.failureCode === undefined || typeof value.failureCode === 'string')) {
        const p = value.prepared;
        if (p === undefined || (isObject(p) && typeof p.url === 'string' && p.model === POOL_MODEL && pairs(p.headers) && body(p.body) && Array.isArray(p.changes) && p.changes.every(c => isObject(c) && typeof c.name === 'string' && typeof c.reason === 'string'))) return {
          ...value,
          ...(value.failureCode === undefined ? {} : { failureCode: POOL_FAILURE_CODES.has(value.failureCode as string) ? value.failureCode : value.attempted ? 'POOL_FETCH_ERROR' : 'REQUEST_REJECTED' }),
          ...(value.transportDiagnostics === undefined ? {} : { transportDiagnostics: decodePoolTransportDiagnostics(value.transportDiagnostics) }),
        } as unknown as ForwarderFrame;
      }
    }
  }
  throw new Error('采集器私有帧格式错误');
}

/** 校验驱动回执，正文与头形状复用采集器边界。 @param line 私有驱动帧。 @return 已验证回执。 */
export function decodeDriverFrame(line: string): DriverFrame {
  const value: unknown = JSON.parse(line);
  const strings = (x: unknown): x is string[] => Array.isArray(x) && x.every(s => typeof s === 'string');
  if (isObject(value)) {
    if (value.type === 'fatal' && typeof value.message === 'string') return value as unknown as DriverFrame;
    if (value.type === 'driver_ready' && typeof value.namespace === 'string' && strings(value.interfaces) && strings(value.envNames) && typeof value.rejectedTargetProbe === 'boolean') return value as unknown as DriverFrame;
    if (value.type === 'result' && typeof value.id === 'string' && typeof value.ingress === 'string' && (value.context === null || isObject(value.context)) && typeof value.state === 'string' && typeof value.elapsedMs === 'number' && (value.workerPid === null || Number.isSafeInteger(value.workerPid)) && strings(value.workerEnvNames) && typeof value.syntheticCredential === 'boolean' && Number.isSafeInteger(value.proxyRequests) && Number.isSafeInteger(value.rejectedRequests) && typeof value.telemetry === 'string') {
      decodeForwarderFrame(JSON.stringify({ type: 'finished', id: 1, attempted: false, outcome: value.state, statusCode: value.statusCode, upstreamStatus: null, headers: value.headers, response: value.response }));
      if (value.prepared !== null) {
        if (!isObject(value.prepared)) throw new Error('中间值回执错误');
        decodeForwarderFrame(JSON.stringify({ type: 'finished', id: 1, attempted: false, outcome: '', statusCode: 200, upstreamStatus: null, headers: value.prepared.headers, response: value.prepared.body }));
      }
      return value as unknown as DriverFrame;
    }
  }
  throw new Error('隔离驱动私有帧格式错误');
}
