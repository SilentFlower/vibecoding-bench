import type { HeaderPair, RuntimeEvent } from './contracts';
import { BridgeError } from './errors';

/** 独立辅助程序的画像和私有协议，不冒用官方执行体身份。 */
export const TLS_VERIFIER_PROFILE = 'claude-code-2.1.293';

/** 绑定实际物理工作进程的一次作业。 */
export interface TlsBinding { request_id: string; worker_id: string; worker_pid: number }

/** 原生构造点的校验依据，只观察 CCH 槽位，不计算最终 CCH。 */
export interface TlsExpected { request_id: string; body_bytes: number; body_sha256: string; cch_offset: number | null; headers: HeaderPair[] }

/** 最后 TLS 写入器的观测；正文预览有界，哈希和计数覆盖实际接受范围。 */
export interface TlsWriteCapture {
  binding: TlsBinding;
  connection_id: number;
  sequence: number;
  body_preview_b64: string;
  head_b64: string;
  headers: HeaderPair[];
  body_bytes: number;
  body_sha256: string;
  normalized_sha256: string;
  http_bytes: number;
  http_sha256: string;
  complete: boolean;
  flushed: boolean;
  verified: boolean;
  captured_unix_ms: number;
  reason: string;
}

/** 辅助程序输出事件的集中合同。 */
export type TlsVerifierEvent =
  | { type: 'ready'; command_id: number; profile: typeof TLS_VERIFIER_PROFILE; pid: number; port: number }
  | { type: 'ack'; command_id: number; error: string | null }
  | { type: 'capture'; capture: TlsWriteCapture }
  | { type: 'failure'; binding: TlsBinding | null; reason: string };

function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function integer(value: unknown, min = 0): value is number { return Number.isSafeInteger(value) && Number(value) >= min; }
function hash(value: unknown): value is string { return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value); }
function base64(value: unknown): value is string { return typeof value === 'string' && value.length % 4 === 0 && /^[A-Za-z0-9+/]*={0,2}$/.test(value) && Buffer.from(value, 'base64').toString('base64') === value; }
function binding(value: unknown): value is TlsBinding {
  return object(value) && typeof value.request_id === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value.request_id) && typeof value.worker_id === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value.worker_id) && integer(value.worker_pid, 1);
}
function headers(value: unknown): value is HeaderPair[] {
  return Array.isArray(value) && value.every(pair => Array.isArray(pair) && pair.length === 2 && typeof pair[0] === 'string' && typeof pair[1] === 'string' && !/[\r\n\0]/.test(pair[0] + pair[1]));
}
function code(value: unknown): value is string { return typeof value === 'string' && /^[a-z_]{1,64}$/.test(value); }

/** 校验私有帧的实例、数值和完整性关系；作业时序由控制器继续验证。
 * @param line 私有 stdout JSONL。
 * @param instanceId 当前辅助进程实例。
 * @param previewLimit 启动时冻结的预览上限。
 * @return 可信类型事件；非法帧明确失败。
 */
export function decodeTlsVerifierFrame(line: string, instanceId: string, previewLimit: number): TlsVerifierEvent {
  const fail = (): never => { throw new BridgeError('tls_verifier_protocol', 'TLS 验证器私有帧不合法或归属不匹配', 502); };
  let value: unknown;
  try { value = JSON.parse(line); } catch { return fail(); }
  if (!object(value) || value.schema_version !== 1 || value.instance_id !== instanceId || !object(value.event)) return fail();
  const event = value.event;
  if (event.type === 'ready' && event.profile === TLS_VERIFIER_PROFILE && integer(event.command_id, 1) && integer(event.pid, 1) && integer(event.port, 1) && event.port <= 65535) return event as TlsVerifierEvent;
  if (event.type === 'ack' && integer(event.command_id, 1) && (event.error === null || code(event.error))) return event as TlsVerifierEvent;
  if (event.type === 'failure' && (event.binding === null || binding(event.binding)) && code(event.reason)) return event as TlsVerifierEvent;
  if (event.type !== 'capture' || !object(event.capture)) return fail();
  const capture = event.capture;
  if (!binding(capture.binding) || !integer(capture.connection_id, 1) || !integer(capture.sequence, 1)
    || !base64(capture.body_preview_b64) || !base64(capture.head_b64) || !headers(capture.headers)
    || !integer(capture.body_bytes) || !integer(capture.http_bytes) || !integer(capture.captured_unix_ms, 1)
    || !hash(capture.body_sha256) || !hash(capture.normalized_sha256) || !hash(capture.http_sha256)
    || typeof capture.complete !== 'boolean' || typeof capture.flushed !== 'boolean' || typeof capture.verified !== 'boolean' || !code(capture.reason)) return fail();
  const previewBytes = Buffer.from(capture.body_preview_b64, 'base64').length;
  const headBytes = Buffer.from(capture.head_b64, 'base64').length;
  if (previewBytes > previewLimit || previewBytes > capture.body_bytes || headBytes > 128 * 1024 || capture.http_bytes < capture.body_bytes + headBytes
    || (capture.complete && capture.http_bytes !== capture.body_bytes + headBytes)
    || (capture.verified && (!capture.complete || !capture.flushed))) return fail();
  return event as unknown as TlsVerifierEvent;
}

/** 定位原生 billing 中唯一 CCH 占位的 UTF-8 偏移，避免误把消息内容当作槽位。
 * @param event 实际同次 cc_prepared 事件。
 * @return 辅助程序校验依据；无法明确定位时拒绝验证而非猜测。
 */
export function expectedTlsWrite(event: Extract<RuntimeEvent, { type: 'cc_prepared' }>): TlsExpected {
  const result: TlsExpected = { request_id: event.request_id, body_bytes: event.body_bytes, body_sha256: event.body_sha256, cch_offset: null, headers: event.headers };
  const value: unknown = JSON.parse(event.body);
  if (!object(value) || JSON.stringify(value) !== event.body) throw new BridgeError('tls_verifier_protocol', '无法核对原生正文序列化边界', 502);
  if (!Array.isArray(value.system)) return result;
  const blocks = value.system.filter(block => object(block) && typeof block.text === 'string' && /^\s*x-anthropic-billing-header:/.test(block.text));
  if (blocks.length === 0) return result;
  if (blocks.length !== 1) throw new BridgeError('tls_verifier_protocol', '原生 billing 证据不唯一', 502);
  const block = blocks[0] as Record<string, unknown> & { text: string };
  const slot = /(?:x-anthropic-billing-header:\s*|;\s*)cch=00000(?=\s*(?:;|$))/.exec(block.text);
  if (!slot) return result;
  const offset = slot.index + slot[0].lastIndexOf('00000');
  // 只改变解析副本中的一个已知 ASCII 字符，首个差异即真实槽位；任意业务文本都不再与哨兵冲突。
  block.text = block.text.slice(0, offset) + '1' + block.text.slice(offset + 1);
  const marked = JSON.stringify(value);
  let index = 0;
  while (index < event.body.length && event.body[index] === marked[index]) index++;
  result.cch_offset = Buffer.byteLength(event.body.slice(0, index));
  return result;
}
