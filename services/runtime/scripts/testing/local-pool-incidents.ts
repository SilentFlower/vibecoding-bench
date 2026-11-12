import { Database } from 'bun:sqlite';
import { constants } from 'node:fs';
import { link, lstat, mkdir, open, rename, unlink } from 'node:fs/promises';
import { dirname, join, parse, resolve, sep } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { CaptureRecord, CaptureStage, RequestRow } from '../../src/shared/contracts';
import { isObject } from '../../src/shared/errors';
import { decodePoolTransportDiagnostics, POOL_FAILURE_CODES, type PoolTransportDiagnostics } from './pool-common';

const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
const REQUEST_ID = /^[A-Za-z0-9_-]{1,128}$/;
const FAILURE_STATES = ['error', 'http_error', 'stream_error', 'incomplete'] as const;
const STAGES: readonly CaptureStage[] = ['ingress', 'header_policy', 'cc_prepared', 'wire_final', 'upstream_response'];
const SOURCES = ['http_ingress', 'header_policy', 'unavailable', 'demo_fixture', 'claude_code_293_cli_prepared', 'claude_code_293_native_ingress_prepared', 'local_pool_node_tls_receiver', 'native_response'];
const REPRESENTATIONS = ['utf8', 'json', 'unknown', 'json_before_native_transport', 'http_entity_body_after_native_transport', 'response_logical_bytes'];
const CAPTURE_STATES: readonly CaptureRecord['status'][] = ['complete', 'truncated', 'unavailable', 'failed', 'incomplete'];
const OUTCOMES = ['success', 'http_error', 'error', 'canceled', 'timeout', 'redirect_blocked'];
const TRACE_HEADERS: Partial<Record<CaptureStage, readonly string[]>> = { wire_final: ['x-client-request-id'], upstream_response: ['x-oneapi-request-id', 'x-ds-trace-id', 'x-amz-cf-id'] };
const INCIDENT_CODES = ['UNKNOWN', 'SOURCE_MISSING', 'SOURCE_INVALID', 'SOURCE_OVERSIZE', 'SOURCE_BUSY', 'RUN_MISMATCH', 'REPORT_WRITE_FAILED', 'REPORT_CONFLICT', 'REQUEST_NOT_FOUND', 'REQUEST_NOT_TERMINAL', 'LOG_CAPTURE_DISABLED', 'LOG_CAPTURE_GAP', 'SHUTDOWN_PARTIAL'] as const;
const EVIDENCE_GAPS = [...INCIDENT_CODES, 'FIELD_INVALID', 'CAPTURE_MISSING', 'CAPTURE_INVALID', 'BODY_MISSING', 'NO_RESERVATION', 'RESERVATION_CONFLICT', 'TRANSPORT_UNAVAILABLE', 'FINISH_NOT_OBSERVED', 'CORRELATION_MISSING', 'CORRELATION_INVALID', 'CORRELATION_CONFLICT', 'HEADERS_NOT_SAVED'] as const;
const INTERPRETATION = { tls: 'wire_final 仅证明本地 TLS 接收端的第一段实收；未复核正文内容', transport: '发送事件及关联连接累计计数不证明池端接收、执行或安全重试', rootCause: 'unknown' } as const;
const META_LIMIT = 1024 * 1024;
const LEDGER_LIMIT = 32 * META_LIMIT;
const PAGE_SIZE = 100;
const INTERVAL_MS = 2000;
const SETTLE_MS = 5000;

/** 只包含受控故障分类，任何底层异常原文均不进入取证输出。 */
export type PoolIncidentCode = typeof INCIDENT_CODES[number];
/** 报告中的固定缺口分类，不包含任意来源文本。 */
type EvidenceGap = typeof EVIDENCE_GAPS[number];
/** 正文只检查存储元数据，不读取内容。 */
type BodyStorage = 'present' | 'not_saved' | 'missing' | 'inconsistent' | 'unknown';
/** 已从 SQLite 取出的单条捕获，载荷在投影边界仍按未知数据处理。 */
export interface IncidentCaptureInput { stage: string; attempt: number; value: unknown; bodyStorage: BodyStorage }
/** 纯投影的输入，账本行必须由同轮只读采集器精确选择。 */
export interface PoolIncidentEvidence {
  runId: string;
  requestId: string;
  request: unknown;
  captures: IncidentCaptureInput[];
  reservation: unknown;
  ledgerState: 'matched' | 'missing' | 'unavailable' | 'conflict';
  sourceCodes?: PoolIncidentCode[];
}
/** 已收窄的采集摘要，recordedStatus 不等于正文仍然存在。 */
interface IncidentCapture {
  stage: CaptureStage; attempt: number | null; capturedAt: string | null;
  source: string; representation: string; recordedStatus: CaptureRecord['status'] | 'unknown';
  observedBytes: number | null; storedBytes: number | null; sha256: string | null; bodyStorage: BodyStorage;
}
/** 标识只说明来自哪个观测位置，不推定其生成方。 */
interface IncidentCorrelation {
  stage: CaptureStage | null; attempt: number | null; header: string | null;
  state: 'known' | 'unknown' | 'conflict'; values: string[];
  reason: 'observed' | 'missing' | 'invalid' | 'conflict' | 'not_saved' | 'proxy_not_captured';
}
/** schemaVersion=1 的安全现场快照，不包含正文、凭据、地址或原始异常。 */
export interface PoolIncidentReport {
  schemaVersion: 1; collectedAt: string; runId: string; requestId: string;
  request: { createdAt: string | null; finishedAt: string | null; state: typeof FAILURE_STATES[number]; httpStatus: number | null; mode: RequestRow['mode'] | 'unknown'; captureErrorPresent: boolean | null };
  forwarding: { sourceState: PoolIncidentEvidence['ledgerState']; reservedAt: string | null; attempted: boolean | null; localStatus: number | null; upstreamStatus: number | null; outcome: string; failureCode: string | null };
  transport: PoolTransportDiagnostics;
  captures: IncidentCapture[];
  correlations: IncidentCorrelation[];
  evidenceGaps: EvidenceGap[];
  interpretation: { tls: string; transport: string; rootCause: 'unknown' };
}
/** 取证进度与故障可读状态，不替代业务健康或调用预算。 */
export interface PoolIncidentStatus {
  schemaVersion: 1; runId: string; phase: 'active' | 'degraded' | 'stopped';
  checkedAt: string | null; completedCycles: number; scanned: number; written: number; existing: number;
  logMode: RequestRow['mode'] | 'unknown'; logCaptureErrorPresent: boolean | null; codes: PoolIncidentCode[];
}
/** 采集器仅接收运行目录及安全日志状态，不持有真实池配置。 */
export interface PoolIncidentOptions {
  runId: string; directory: string; output?: string;
  getLogStatus?: () => { mode: RequestRow['mode']; captureErrorPresent: boolean };
  onDiagnostic?: (code: PoolIncidentCode) => void;
}

/** 受控取证异常，不保留 cause 或底层 message。 */
export class PoolIncidentError extends Error {
  /** 创建固定分类异常。 @param code 受控分类。 */
  constructor(readonly code: PoolIncidentCode) { super('本地池取证失败：' + code); }
}

/** 将任意异常压缩为可公开代码。 @param error 原始异常。 @return 固定代码。 */
export function poolIncidentCode(error: unknown): PoolIncidentCode {
  if (error instanceof PoolIncidentError) return error.code;
  if (isObject(error) && (error.code === 'SQLITE_BUSY' || error.code === 'SQLITE_LOCKED')) return 'SOURCE_BUSY';
  if (isObject(error) && error.code === 'ENOENT') return 'SOURCE_MISSING';
  return 'SOURCE_INVALID';
}

function count(value: unknown): number | null { return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null; }
function httpStatus(value: unknown): number | null { return typeof value === 'number' && Number.isInteger(value) && value >= 100 && value <= 599 ? value : null; }
function date(value: unknown): string | null {
  return typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value ? value : null;
}
function member<T extends string>(value: unknown, choices: readonly T[]): T | undefined { return choices.find(item => item === value); }
function fields(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  return isObject(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function nullable(value: unknown, check: (value: unknown) => unknown): boolean { return value === null || check(value) !== null; }

function validCapture(value: unknown): value is IncidentCapture {
  if (!fields(value, ['stage', 'attempt', 'capturedAt', 'source', 'representation', 'recordedStatus', 'observedBytes', 'storedBytes', 'sha256', 'bodyStorage'])) return false;
  return member(value.stage, STAGES) !== undefined && (value.attempt === null || count(value.attempt) !== null && Number(value.attempt) > 0)
    && nullable(value.capturedAt, date) && (value.source === 'unknown' || member(value.source, SOURCES) !== undefined)
    && member(value.representation, REPRESENTATIONS) !== undefined && (value.recordedStatus === 'unknown' || member(value.recordedStatus, CAPTURE_STATES) !== undefined)
    && nullable(value.observedBytes, count) && nullable(value.storedBytes, count)
    && (value.sha256 === null || typeof value.sha256 === 'string' && /^[a-f0-9]{64}$/.test(value.sha256))
    && member(value.bodyStorage, ['present', 'not_saved', 'missing', 'inconsistent', 'unknown']) !== undefined;
}

function validCorrelation(value: unknown): value is IncidentCorrelation {
  if (!fields(value, ['stage', 'attempt', 'header', 'state', 'values', 'reason']) || !Array.isArray(value.values)
    || !value.values.every(item => typeof item === 'string' && /^[A-Za-z0-9._~+/=-]{1,256}$/.test(item)) || new Set(value.values).size !== value.values.length) return false;
  if (value.stage === null) return value.attempt === null && value.header === null && value.state === 'unknown' && value.values.length === 0 && value.reason === 'proxy_not_captured';
  const stage = member(value.stage, STAGES);
  if (!stage || typeof value.header !== 'string' || !(TRACE_HEADERS[stage] ?? []).includes(value.header)
    || value.attempt !== null && (count(value.attempt) === null || Number(value.attempt) < 1)) return false;
  if (value.state === 'known') return value.values.length === 1 && value.reason === 'observed';
  // 来源头组损坏时投影会省略值，但仍保留已观测到冲突这一事实。
  if (value.state === 'conflict') return value.values.length !== 1 && value.reason === 'conflict';
  return value.state === 'unknown' && value.values.length === 0 && member(value.reason, ['missing', 'invalid', 'not_saved']) !== undefined;
}

// 去重必须校验完整合同；合法缺证用显式 null/unknown 表达，不能把字段缺失当作同一回事。
function validReport(value: unknown): value is PoolIncidentReport {
  if (!fields(value, ['schemaVersion', 'collectedAt', 'runId', 'requestId', 'request', 'forwarding', 'transport', 'captures', 'correlations', 'evidenceGaps', 'interpretation'])
    || value.schemaVersion !== 1 || !date(value.collectedAt) || typeof value.runId !== 'string' || !RUN_ID.test(value.runId) || typeof value.requestId !== 'string' || !REQUEST_ID.test(value.requestId)) return false;
  const row = value.request, forwarding = value.forwarding, transport = value.transport;
  if (!fields(row, ['createdAt', 'finishedAt', 'state', 'httpStatus', 'mode', 'captureErrorPresent'])
    || !nullable(row.createdAt, date) || !nullable(row.finishedAt, date) || !member(row.state, FAILURE_STATES) || !nullable(row.httpStatus, httpStatus)
    || !member(row.mode, ['off', 'summary', 'debug', 'unknown']) || row.captureErrorPresent !== null && typeof row.captureErrorPresent !== 'boolean') return false;
  if (!fields(forwarding, ['sourceState', 'reservedAt', 'attempted', 'localStatus', 'upstreamStatus', 'outcome', 'failureCode'])
    || !member(forwarding.sourceState, ['matched', 'missing', 'unavailable', 'conflict']) || !nullable(forwarding.reservedAt, date)
    || forwarding.attempted !== null && typeof forwarding.attempted !== 'boolean' || !nullable(forwarding.localStatus, httpStatus) || !nullable(forwarding.upstreamStatus, httpStatus)
    || forwarding.outcome !== 'unknown' && !member(forwarding.outcome, OUTCOMES)
    || forwarding.failureCode !== null && (typeof forwarding.failureCode !== 'string' || !POOL_FAILURE_CODES.has(forwarding.failureCode))) return false;
  const normalized = decodePoolTransportDiagnostics(transport);
  if (!fields(transport, ['phase', 'bodySentObserved', 'connectionBytesWritten', 'connectionBytesRead']) || !Object.entries(normalized).every(([key, item]) => transport[key] === item)) return false;
  const captures = value.captures;
  if (!Array.isArray(captures) || captures.length > 105 || !captures.every(validCapture) || !STAGES.every(stage => captures.some(capture => capture.stage === stage))) return false;
  const knownCaptures = captures.filter(capture => capture.attempt !== null).map(capture => capture.stage + ':' + capture.attempt);
  if (new Set(knownCaptures).size !== knownCaptures.length || !Array.isArray(value.correlations) || !value.correlations.every(validCorrelation)) return false;
  const correlations: IncidentCorrelation[] = value.correlations;
  if (correlations.filter(item => item.stage === null).length !== 1) return false;
  const expected = captures.flatMap(capture => (TRACE_HEADERS[capture.stage] ?? []).map(header => capture.stage + ':' + capture.attempt + ':' + header)).sort();
  const actual = correlations.filter(item => item.stage !== null).map(item => item.stage + ':' + item.attempt + ':' + item.header).sort();
  if (expected.length !== actual.length || expected.some((key, index) => key !== actual[index])) return false;
  if (!Array.isArray(value.evidenceGaps) || !value.evidenceGaps.every(gap => member(gap, EVIDENCE_GAPS) !== undefined)) return false;
  const interpretation = value.interpretation;
  return fields(interpretation, ['tls', 'transport', 'rootCause']) && Object.entries(INTERPRETATION).every(([key, item]) => interpretation[key] === item);
}

/** 从已脱敏证据重建白名单报告，绝不透传来源对象。
 * @param input 同请求、同轮次的证据及明确缺口。
 * @return 安全报告；身份或终态不合法时抛出固定错误。
 */
export function projectPoolIncident(input: PoolIncidentEvidence): PoolIncidentReport {
  if (!RUN_ID.test(input.runId) || !REQUEST_ID.test(input.requestId)) throw new PoolIncidentError('SOURCE_INVALID');
  const row = input.request;
  if (!isObject(row) || row.id !== input.requestId) throw new PoolIncidentError('SOURCE_INVALID');
  const state = member(row.state, FAILURE_STATES);
  if (!state) throw new PoolIncidentError('REQUEST_NOT_TERMINAL');
  const gaps = new Set<EvidenceGap>(input.sourceCodes);
  const mode = member(row.mode, ['off', 'summary', 'debug'] as const) ?? 'unknown';
  if (mode === 'summary') gaps.add('HEADERS_NOT_SAVED');
  if (!date(row.createdAt) || row.finishedAt !== null && !date(row.finishedAt) || mode === 'unknown' || row.httpStatus !== null && httpStatus(row.httpStatus) === null) gaps.add('FIELD_INVALID');
  if (!date(row.finishedAt)) gaps.add('FINISH_NOT_OBSERVED');
  const captureErrorPresent = row.captureError === null ? false : typeof row.captureError === 'string' ? row.captureError.length > 0 : null;
  if (captureErrorPresent) gaps.add('LOG_CAPTURE_GAP');
  const captures: IncidentCapture[] = [];
  const correlations: IncidentCorrelation[] = [];
  for (const stage of STAGES) {
    const inputs = input.captures.filter(item => item.stage === stage);
    if (!inputs.length) { gaps.add('CAPTURE_MISSING'); inputs.push({ stage, attempt: 0, value: null, bodyStorage: 'unknown' }); }
    for (const item of inputs) {
      const valid = isObject(item.value) && item.value.stage === stage && item.value.attempt === item.attempt && count(item.attempt) !== null && item.attempt > 0;
      const value = valid && isObject(item.value) ? item.value : {};
      const observedBytes = count(value.observedBytes), storedBytes = count(value.storedBytes);
      const recordedStatus = member(value.status, CAPTURE_STATES) ?? 'unknown';
      const source = member(value.source, SOURCES) ?? 'unknown', representation = member(value.representation, REPRESENTATIONS) ?? 'unknown';
      const sha256 = typeof value.sha256 === 'string' && /^[a-f0-9]{64}$/.test(value.sha256) ? value.sha256 : null;
      if (!valid || recordedStatus === 'unknown' || !date(value.capturedAt) || observedBytes === null || storedBytes === null || value.sha256 !== null && sha256 === null || source === 'unknown' || representation === 'unknown' && value.representation !== 'unknown') gaps.add('CAPTURE_INVALID');
      if (item.bodyStorage === 'missing' || item.bodyStorage === 'inconsistent') gaps.add('BODY_MISSING');
      const attempt = valid ? item.attempt : null;
      captures.push({ stage, attempt, capturedAt: date(value.capturedAt), source, representation, recordedStatus, observedBytes, storedBytes, sha256, bodyStorage: valid ? item.bodyStorage : 'unknown' });
      const names = TRACE_HEADERS[stage] ?? [];
      for (const header of names) {
        const values = new Set<string>();
        let invalid = !Array.isArray(value.headers);
        if (Array.isArray(value.headers)) for (const pair of value.headers) {
          if (!Array.isArray(pair) || pair.length !== 2 || typeof pair[0] !== 'string' || typeof pair[1] !== 'string') { invalid = true; continue; }
          if (pair[0].toLowerCase() !== header) continue;
          if (/^[A-Za-z0-9._~+/=-]{1,256}$/.test(pair[1])) values.add(pair[1]); else invalid = true;
        }
        const conflict = values.size > 1;
        const status = conflict ? 'conflict' : invalid || values.size === 0 ? 'unknown' : 'known';
        if (status !== 'known') gaps.add(conflict ? 'CORRELATION_CONFLICT' : invalid ? 'CORRELATION_INVALID' : 'CORRELATION_MISSING');
        correlations.push({ stage, attempt, header, state: status, values: invalid ? [] : [...values], reason: conflict ? 'conflict' : invalid ? 'invalid' : values.size ? 'observed' : mode === 'summary' ? 'not_saved' : 'missing' });
      }
    }
  }
  correlations.push({ stage: null, attempt: null, header: null, state: 'unknown', values: [], reason: 'proxy_not_captured' });
  const reservation = input.ledgerState === 'matched' && isObject(input.reservation) && input.reservation.requestId === input.requestId ? input.reservation : {};
  if (input.ledgerState === 'missing') gaps.add('NO_RESERVATION');
  if (input.ledgerState === 'conflict') gaps.add('RESERVATION_CONFLICT');
  const failureCode = typeof reservation.failureCode === 'string' && POOL_FAILURE_CODES.has(reservation.failureCode) ? reservation.failureCode : null;
  const transport = decodePoolTransportDiagnostics(reservation.transportDiagnostics);
  if (transport.phase === 'unknown' || transport.bodySentObserved === null || transport.connectionBytesWritten === null || transport.connectionBytesRead === null) gaps.add('TRANSPORT_UNAVAILABLE');
  if (reservation.failureCode !== undefined && failureCode === null) gaps.add('FIELD_INVALID');
  return {
    schemaVersion: 1, collectedAt: new Date().toISOString(), runId: input.runId, requestId: input.requestId,
    request: { createdAt: date(row.createdAt), finishedAt: date(row.finishedAt), state, httpStatus: httpStatus(row.httpStatus), mode, captureErrorPresent },
    forwarding: { sourceState: input.ledgerState, reservedAt: date(reservation.reservedAt), attempted: typeof reservation.attempted === 'boolean' ? reservation.attempted : null, localStatus: httpStatus(reservation.localStatus), upstreamStatus: httpStatus(reservation.upstreamStatus), outcome: member(reservation.outcome, OUTCOMES) ?? 'unknown', failureCode },
    transport, captures, correlations, evidenceGaps: [...gaps],
    interpretation: { ...INTERPRETATION },
  };
}

// 读取到文件尺寸之外的一字节，用于识别采样期间增长，不能解析截断前缀冒充完整文件。
async function readJson(path: string, limit: number): Promise<unknown> {
  const file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const info = await file.stat();
    if (!info.isFile()) throw new PoolIncidentError('SOURCE_INVALID');
    if (info.size > limit) throw new PoolIncidentError('SOURCE_OVERSIZE');
    const bytes = Buffer.alloc(info.size + 1);
    let used = 0;
    while (used < bytes.length) {
      const part = await file.read(bytes, used, bytes.length - used, used);
      if (!part.bytesRead) break;
      used += part.bytesRead;
    }
    if (used !== info.size) throw new PoolIncidentError('SOURCE_INVALID');
    try { return JSON.parse(bytes.subarray(0, used).toString('utf8')); } catch { throw new PoolIncidentError('SOURCE_INVALID'); }
  } finally { await file.close(); }
}

async function directory(path: string, create: boolean): Promise<void> {
  let current = parse(path).root;
  for (const part of path.slice(current.length).split(sep).filter(Boolean)) {
    current = join(current, part);
    let info;
    try { info = await lstat(current); }
    catch (error) {
      if (!create || !isObject(error) || error.code !== 'ENOENT') throw error;
      try { await mkdir(current, { mode: 0o700 }); } catch (error) { if (!isObject(error) || error.code !== 'EEXIST') throw error; }
      info = await lstat(current);
    }
    if (!info.isDirectory() || info.isSymbolicLink()) throw new PoolIncidentError('SOURCE_INVALID');
  }
}

/** 按创建时间及 ID 分页的候选索引；载荷另行读取并校验，state 不替代载荷归属。 */
interface Candidate { id: string; created_at: string; state: string }
/** 捕获表的有界原始索引；payload 超限时为 null，body_file 只用于存储元数据检查。 */
interface CaptureRow { stage: string; attempt: number; payload: string | null; body_file: string | null }
/** 同轮账本的精确请求索引；重复预留映射为 null，来源缺口只保留固定代码。 */
interface RunSources { reservations: Map<string, Record<string, unknown> | null>; available: boolean; codes: PoolIncidentCode[] }

/** 独立只读采集器；不持有引擎，也没有提交模型请求的入口。 */
export class PoolIncidentCollector {
  private db: Database | null = null;
  private readonly output: string;
  private readonly root: string;
  private databaseIdentity = '';
  private cursor: { time: string; id: string } | null = null;
  private readonly pending = new Map<string, number>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private active: Promise<void> = Promise.resolve();
  private closing: Promise<void> | undefined;
  private stopping = false;
  private watching = false;
  private outputReady = false;
  private readonly reportedCodes = new Set<PoolIncidentCode>();
  private readonly progress: PoolIncidentStatus;

  private constructor(private readonly options: PoolIncidentOptions) {
    this.root = resolve(options.directory); this.output = resolve(options.output ?? join(this.root, 'incidents'));
    this.progress = { schemaVersion: 1, runId: options.runId, phase: 'active', checkedAt: null, completedCycles: 0, scanned: 0, written: 0, existing: 0, logMode: 'unknown', logCaptureErrorPresent: null, codes: [] };
  }

  /** 打开既有运行记录及独立输出，绝不创建或迁移源数据库。
   * @param options 显式运行身份、目录及安全状态提供者。
   * @return 就绪采集器；失败时留下可写的安全状态并抛出受控异常。
   */
  static async open(options: PoolIncidentOptions): Promise<PoolIncidentCollector> {
    if (!RUN_ID.test(options.runId)) throw new PoolIncidentError('SOURCE_INVALID');
    const collector = new PoolIncidentCollector(options);
    try {
      await directory(collector.root, false);
      await directory(dirname(collector.output), true);
      if (options.output) await mkdir(collector.output, { mode: 0o700 });
      else await directory(collector.output, true);
      const info = await lstat(collector.output);
      if (!info.isDirectory() || (info.mode & 0o077) !== 0) throw new PoolIncidentError('REPORT_WRITE_FAILED');
      const previous = await readJson(join(collector.output, 'status.json'), META_LIMIT).catch(error => { if (poolIncidentCode(error) !== 'SOURCE_MISSING') throw new PoolIncidentError('REPORT_CONFLICT'); return null; });
      if (previous !== null && (!isObject(previous) || previous.schemaVersion !== 1 || previous.runId !== options.runId)) throw new PoolIncidentError('REPORT_CONFLICT');
      collector.outputReady = true;
      await directory(join(collector.output, 'reports'), true);
      if (((await lstat(join(collector.output, 'reports'))).mode & 0o077) !== 0) throw new PoolIncidentError('REPORT_WRITE_FAILED');
      await collector.sources();
      await directory(join(collector.root, 'data'), false);
      const database = await lstat(join(collector.root, 'data/logs.sqlite'));
      if (!database.isFile() || database.isSymbolicLink()) throw new PoolIncidentError('SOURCE_INVALID');
      collector.databaseIdentity = database.dev + ':' + database.ino;
      collector.db = new Database(join(collector.root, 'data/logs.sqlite'), { readonly: true, strict: true });
      collector.db.exec('PRAGMA query_only=ON; PRAGMA busy_timeout=50;');
      await collector.saveStatus();
      return collector;
    } catch (error) {
      collector.db?.close(); collector.db = null;
      collector.note(poolIncidentCode(error));
      // 输出目录身份冲突时不覆盖属于另一个采集器的状态。
      if (poolIncidentCode(error) !== 'REPORT_CONFLICT') await collector.saveStatus().catch(() => {});
      throw new PoolIncidentError(poolIncidentCode(error));
    }
  }

  private note(code: PoolIncidentCode): void {
    if (!this.progress.codes.includes(code)) this.progress.codes.push(code);
    if (this.progress.phase !== 'stopped') this.progress.phase = 'degraded';
    if (!this.reportedCodes.has(code)) { this.reportedCodes.add(code); try { this.options.onDiagnostic?.(code); } catch {} }
  }

  private async sources(): Promise<RunSources> {
    const result: RunSources = { reservations: new Map(), available: false, codes: [] };
    let confirmed = false;
    for (const name of ['ready.json', 'ledger.json']) {
      let value: unknown;
      try { value = await readJson(join(this.root, name), name === 'ledger.json' ? LEDGER_LIMIT : META_LIMIT); }
      catch (error) { result.codes.push(poolIncidentCode(error)); continue; }
      if (!isObject(value) || typeof value.runId !== 'string' || !RUN_ID.test(value.runId)) { result.codes.push('SOURCE_INVALID'); continue; }
      if (value.runId !== this.options.runId) throw new PoolIncidentError('RUN_MISMATCH');
      if (name === 'ready.json') { confirmed = true; continue; }
      if (value.schemaVersion !== 1 || value.mode !== 'manual' || !Array.isArray(value.reservations)) { result.codes.push('SOURCE_INVALID'); continue; }
      confirmed = true; result.available = true;
      for (const row of value.reservations) {
        if (!isObject(row) || typeof row.requestId !== 'string' || !REQUEST_ID.test(row.requestId)) { result.codes.push('SOURCE_INVALID'); continue; }
        result.reservations.set(row.requestId, result.reservations.has(row.requestId) ? null : row);
      }
    }
    if (!confirmed) throw new PoolIncidentError('SOURCE_INVALID');
    result.codes = [...new Set(result.codes)];
    return result;
  }

  private logStatus(): void {
    try {
      const value = this.options.getLogStatus?.();
      this.progress.logMode = member(value?.mode, ['off', 'summary', 'debug'] as const) ?? 'unknown';
      this.progress.logCaptureErrorPresent = typeof value?.captureErrorPresent === 'boolean' ? value.captureErrorPresent : null;
      if (this.progress.logMode === 'off') this.note('LOG_CAPTURE_DISABLED');
      if (this.progress.logCaptureErrorPresent) this.note('LOG_CAPTURE_GAP');
    } catch { this.note('SOURCE_INVALID'); }
  }

  private async publish(name: string, value: unknown, exclusive: boolean): Promise<void> {
    const text = JSON.stringify(value, null, 2) + '\n';
    if (Buffer.byteLength(text) > META_LIMIT) throw new PoolIncidentError('SOURCE_OVERSIZE');
    await directory(dirname(join(this.output, name)), false);
    const temporary = join(this.output, '.incident-' + randomUUID() + '.tmp');
    const file = await open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    try {
      await file.writeFile(text); await file.close();
      if (exclusive) await link(temporary, join(this.output, name)); else await rename(temporary, join(this.output, name));
    } finally { await file.close().catch(() => {}); await unlink(temporary).catch(() => {}); }
  }

  private async saveStatus(): Promise<void> {
    this.logStatus();
    if (!this.outputReady) return;
    try { await this.publish('status.json', this.progress, false); }
    catch { this.note('REPORT_WRITE_FAILED'); }
  }

  private async existing(id: string): Promise<boolean> {
    try { await directory(join(this.output, 'reports'), false); } catch { throw new PoolIncidentError('REPORT_WRITE_FAILED'); }
    // 新报告与状态分目录；旧平铺报告只读识别，旧 status.json 始终属于进度文件。
    const names = [join('reports', id + '.json'), ...(id === 'status' ? [] : [id + '.json'])];
    for (const name of names) {
      let value: unknown;
      try { value = await readJson(join(this.output, name), META_LIMIT); }
      catch (error) { if (poolIncidentCode(error) === 'SOURCE_MISSING') continue; throw new PoolIncidentError('REPORT_CONFLICT'); }
      if (!validReport(value) || value.runId !== this.options.runId || value.requestId !== id) throw new PoolIncidentError('REPORT_CONFLICT');
      return true;
    }
    return false;
  }

  private async bodyStorage(row: CaptureRow, id: string, value: unknown): Promise<BodyStorage> {
    if (row.body_file === null) return isObject(value) && value.storedBytes === 0 ? 'not_saved' : 'unknown';
    if (typeof row.body_file !== 'string' || !member(row.stage, STAGES) || !Number.isSafeInteger(row.attempt) || row.attempt < 1 || !row.body_file.startsWith(id + '-' + row.stage + '-' + row.attempt + '-') || !/^\d+\.txt$/.test(row.body_file.slice((id + '-' + row.stage + '-' + row.attempt + '-').length))) return 'unknown';
    try {
      await directory(join(this.root, 'data/bodies'), false);
      const info = await lstat(join(this.root, 'data/bodies', row.body_file));
      if (!info.isFile() || info.isSymbolicLink()) return 'unknown';
      return isObject(value) && count(value.storedBytes) !== null && info.size === value.storedBytes ? 'present' : 'inconsistent';
    } catch (error) { return poolIncidentCode(error) === 'SOURCE_MISSING' ? 'missing' : 'unknown'; }
  }

  private async evidence(candidate: Candidate, sources: RunSources): Promise<PoolIncidentReport> {
    const db = this.db!;
    const snapshot = db.transaction(() => {
      const row = db.query<{ payload: string | null; state: string }, [number, string]>('SELECT CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END AS payload,state FROM requests WHERE id=?').get(META_LIMIT, candidate.id);
      const captures = db.query<CaptureRow, [number, string]>('SELECT stage,attempt,CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END AS payload,body_file FROM captures WHERE request_id=? ORDER BY stage,attempt LIMIT 101').all(META_LIMIT, candidate.id);
      return { row, captures };
    }).deferred();
    if (!snapshot.row) throw new PoolIncidentError('REQUEST_NOT_FOUND');
    if (snapshot.row.payload === null || snapshot.captures.length > 100) throw new PoolIncidentError('SOURCE_OVERSIZE');
    let request: unknown;
    try { request = JSON.parse(snapshot.row.payload); } catch { throw new PoolIncidentError('SOURCE_INVALID'); }
    if (!isObject(request) || request.state !== snapshot.row.state || request.createdAt !== candidate.created_at) throw new PoolIncidentError('SOURCE_INVALID');
    const captures: IncidentCaptureInput[] = [];
    for (const row of snapshot.captures) {
      let value: unknown = null;
      try { if (row.payload !== null) value = JSON.parse(row.payload); } catch {}
      captures.push({ stage: row.stage, attempt: row.attempt, value, bodyStorage: await this.bodyStorage(row, candidate.id, value) });
    }
    const reservation = sources.reservations.get(candidate.id);
    return projectPoolIncident({ runId: this.options.runId, requestId: candidate.id, request, captures, reservation,
      ledgerState: !sources.available ? 'unavailable' : reservation === null ? 'conflict' : reservation ? 'matched' : 'missing',
      sourceCodes: [...sources.codes, ...(this.progress.logCaptureErrorPresent ? ['LOG_CAPTURE_GAP' as const] : [])] });
  }

  private async batch(force: boolean, requestId?: string, deadline = Infinity): Promise<boolean> {
    if (!this.db) throw new PoolIncidentError('SOURCE_INVALID');
    this.progress.codes = []; this.progress.phase = 'active'; this.logStatus();
    const identity = await lstat(join(this.root, 'data/logs.sqlite'));
    if (identity.isSymbolicLink() || identity.dev + ':' + identity.ino !== this.databaseIdentity) throw new PoolIncidentError('RUN_MISMATCH');
    const sources = await this.sources();
    for (const code of sources.codes) this.note(code);
    const rows = requestId
      ? this.db.query<Candidate, [string]>('SELECT id,created_at,state FROM requests WHERE id=?').all(requestId)
      : this.db.query<Candidate, [string, string, string, number]>(`SELECT id,created_at,state FROM requests WHERE state IN ('error','http_error','stream_error','incomplete') AND (created_at>? OR (created_at=? AND id>?)) ORDER BY created_at,id LIMIT ?`).all(this.cursor?.time ?? '', this.cursor?.time ?? '', this.cursor?.id ?? '', PAGE_SIZE);
    if (requestId && !rows.length) throw new PoolIncidentError('REQUEST_NOT_FOUND');
    // 只保留当前页的收口时间，迟到的旧请求改变分页位置时也不能累积无界候选。
    const pageIds = new Set(rows.map(row => row.id));
    for (const id of this.pending.keys()) if (!pageIds.has(id)) this.pending.delete(id);
    let pending = false;
    for (const row of rows) {
      if (performance.now() >= deadline) { this.note('SHUTDOWN_PARTIAL'); return false; }
      try {
        if (typeof row.id !== 'string' || !REQUEST_ID.test(row.id) || !date(row.created_at)) throw new PoolIncidentError('SOURCE_INVALID');
        this.progress.scanned++;
        if (await this.existing(row.id)) { this.progress.existing++; continue; }
        if (!force) {
          const seen = this.pending.get(row.id) ?? performance.now(); this.pending.set(row.id, seen);
          const reservation = sources.reservations.get(row.id), age = performance.now() - seen;
          const finished = isObject(reservation) && typeof reservation.attempted === 'boolean' && httpStatus(reservation.localStatus) !== null;
          if (age < INTERVAL_MS || !finished && age < SETTLE_MS) { pending = true; continue; }
        }
        const report = await this.evidence(row, sources);
        try { await this.publish(join('reports', row.id + '.json'), report, true); this.progress.written++; }
        catch (error) { if (isObject(error) && error.code === 'EEXIST' && await this.existing(row.id)) this.progress.existing++; else throw new PoolIncidentError('REPORT_WRITE_FAILED'); }
        this.pending.delete(row.id);
      } catch (error) { this.note(poolIncidentCode(error)); }
    }
    this.progress.checkedAt = new Date().toISOString();
    if (!pending) {
      this.pending.clear();
      if (!requestId && rows.length === PAGE_SIZE) { const last = rows.at(-1)!; this.cursor = { time: last.created_at, id: last.id }; }
      else { this.cursor = null; this.progress.completedCycles++; }
    }
    await this.saveStatus();
    return !pending && this.cursor === null;
  }

  /** 读取安全进度副本。 @return 不含模型预算或秘密的当前取证状态。 */
  status(): PoolIncidentStatus { return { ...this.progress, codes: [...this.progress.codes] }; }

  /** 一次性补采所有候选或指定终态请求，适用于已经停止的服务。
   * @param requestId 可选的精确请求 ID。
   * @return 本次采集结束后的状态；不启动自动轮询。
   */
  async collect(requestId?: string): Promise<PoolIncidentStatus> {
    if (this.stopping || this.watching || requestId !== undefined && !REQUEST_ID.test(requestId)) throw new PoolIncidentError('SOURCE_INVALID');
    const codes = new Set<PoolIncidentCode>();
    this.active = this.active.then(async () => {
      try {
        let done = false;
        while (!done && !this.stopping) { done = await this.batch(true, requestId); for (const code of this.progress.codes) codes.add(code); await new Promise<void>(resolve => setTimeout(resolve, 0)); }
      } catch (error) { this.note(poolIncidentCode(error)); codes.add(poolIncidentCode(error)); }
      for (const code of codes) this.note(code);
      await this.saveStatus();
    });
    await this.active;
    return this.status();
  }

  /** 启动有界后台扫描，不影响进程退出或请求响应。 @return 无。 */
  start(): void {
    if (this.stopping || this.watching) return;
    this.watching = true;
    const schedule = (): void => {
      if (this.stopping) return;
      this.timer = setTimeout(() => {
        this.active = this.active.then(async () => { try { await this.batch(false); } catch (error) { this.note(poolIncidentCode(error)); await this.saveStatus(); } }).finally(schedule);
      }, INTERVAL_MS);
      this.timer.unref();
    };
    schedule();
  }

  /** 停止轮询，最终扫描后关闭独立只读连接；重复关闭复用同一收口。
   * @param finalScan 是否补采关闭前持久化的终态，CLI 已采集时可禁用。
   * @return 取证活动结束；失败仅记录安全状态。
   */
  close(finalScan = true): Promise<void> {
    return this.closing ??= (async () => {
      const deadline = performance.now() + SETTLE_MS;
      this.stopping = true; clearTimeout(this.timer); await this.active;
      const codes = new Set<PoolIncidentCode>();
      try {
        if (finalScan) {
          this.cursor = null;
          let done = false;
          while (!done && performance.now() < deadline) {
            done = await this.batch(true, undefined, deadline);
            // batch 会重置单批诊断，收口必须累计，不能用末页成功遮掉前页失败。
            for (const code of this.progress.codes) codes.add(code);
            await new Promise<void>(resolve => setTimeout(resolve, 0));
          }
          if (!done) this.note('SHUTDOWN_PARTIAL');
        }
      } catch (error) { this.note(poolIncidentCode(error)); }
      finally {
        for (const code of codes) this.note(code);
        this.db?.close(); this.db = null; this.pending.clear(); this.progress.phase = 'stopped'; await this.saveStatus(); this.progress.phase = 'stopped';
      }
    })();
  }
}
