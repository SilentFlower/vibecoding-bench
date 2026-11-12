/** 原生失败发生的实际边界，不能由异常文案推断。 */
export const NATIVE_ERROR_STAGES = ['input', 'context', 'construction', 'dispatch', 'response_headers', 'response_body', 'unknown'] as const;

/** 可公开记录的异常类型，未知名字不原样透传。 */
export const NATIVE_ERROR_NAMES = ['Error', 'TypeError', 'RangeError', 'SyntaxError', 'AbortError', 'TimeoutError', 'DOMException', 'AggregateError', 'BridgeError', 'unknown'] as const;

/** 系统、TLS 与本地合同的受控错误码目录。 */
export const NATIVE_ERROR_CODES = [
  'ECONNREFUSED', 'ECONNRESET', 'ECONNABORTED', 'EPIPE', 'ETIMEDOUT', 'ENOTFOUND', 'EAI_AGAIN',
  'EHOSTUNREACH', 'ENETUNREACH', 'ENOENT', 'EACCES', 'EPERM', 'EADDRINUSE',
  'CERT_NOT_YET_VALID', 'CERT_HAS_EXPIRED', 'DEPTH_ZERO_SELF_SIGNED_CERT',
  'SELF_SIGNED_CERT_IN_CHAIN', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY',
  'ERR_TLS_CERT_ALTNAME_INVALID', 'ERR_TLS_CERT_SIGNATURE_ALGORITHM_UNSUPPORTED',
  'ERR_SSL_WRONG_VERSION_NUMBER', 'ERR_SSL_SSLV3_ALERT_HANDSHAKE_FAILURE',
  'ConnectionRefused', 'ConnectionClosed', 'ConnectionReset', 'SocketClosed',
  'ERR_STREAM_PREMATURE_CLOSE', 'ABORT_ERR', 'UND_ERR_CONNECT_TIMEOUT', 'UND_ERR_SOCKET',
  'request_timeout', 'runtime_protocol', 'native_configuration', 'native_construction',
  'native_identity', 'unsupported_parameter', 'context_conflict', 'unknown',
] as const;

/** 单次原生作业的失败阶段。 */
export type NativeErrorStage = typeof NATIVE_ERROR_STAGES[number];

/** 最多八层的安全异常投影，普通日志只消费本合同。 */
export interface NativeErrorDiagnostics {
  schema_version: 1;
  stage: NativeErrorStage;
  causes: { name: typeof NATIVE_ERROR_NAMES[number]; code: typeof NATIVE_ERROR_CODES[number] }[];
  chain_truncated: boolean;
  cycle_detected: boolean;
  inspection_failed: boolean;
}

/** 提取有限类型与错误码，拒绝错误对象中的任意文本及异常 getter。
 * @param error 实际捕获的异常。
 * @param stage 调用方记录的实际边界。
 * @return 可安全进入私有协议及普通日志的有界摘要。
 */
export function nativeErrorDiagnostics(error: unknown, stage: NativeErrorStage): NativeErrorDiagnostics {
  const result: NativeErrorDiagnostics = { schema_version: 1, stage, causes: [], chain_truncated: false, cycle_detected: false, inspection_failed: false };
  const seen = new Set<unknown>();
  const read = (value: unknown, key: string): unknown => {
    if ((typeof value !== 'object' || value === null) && typeof value !== 'function') return undefined;
    try { return Reflect.get(value, key); } catch { result.inspection_failed = true; return undefined; }
  };
  let current = error;
  // 只遍历直接 cause；聚合错误的任意数组及业务对象不进入日志。
  while (true) {
    if (seen.has(current)) { result.cycle_detected = true; break; }
    if (result.causes.length === 8) { result.chain_truncated = true; break; }
    seen.add(current);
    const name = read(current, 'name'), code = read(current, 'code');
    result.causes.push({
      name: NATIVE_ERROR_NAMES.find(known => known === name) ?? 'unknown',
      code: NATIVE_ERROR_CODES.find(known => known === code) ?? 'unknown',
    });
    const cause = read(current, 'cause');
    if (cause === undefined || cause === null) break;
    current = cause;
  }
  return result;
}

/** 校验跨进程的安全摘要，拒绝可携带秘密的扩展字段。
 * @param value 私有协议中的可选字段。
 * @return 字段符合固定版本、枚举及有界结构时为真。
 */
export function isNativeErrorDiagnostics(value: unknown): value is NativeErrorDiagnostics {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return Object.keys(record).length === 6 && record.schema_version === 1
    && NATIVE_ERROR_STAGES.some(stage => stage === record.stage)
    && typeof record.chain_truncated === 'boolean' && typeof record.cycle_detected === 'boolean' && typeof record.inspection_failed === 'boolean'
    && Array.isArray(record.causes) && record.causes.length > 0 && record.causes.length <= 8
    && record.causes.every(cause => cause && typeof cause === 'object' && !Array.isArray(cause) && Object.keys(cause).length === 2
      && NATIVE_ERROR_NAMES.some(name => name === cause.name) && NATIVE_ERROR_CODES.some(code => code === cause.code));
}
