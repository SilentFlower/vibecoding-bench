import type { HeaderPair, RuntimeEvent, RuntimeJob, RuntimePayload, WorkerCommand, WorkerFrame } from './contracts';
import { BridgeError, isObject } from './errors';
import { isCachePolicyDecision, isTelemetryHandshake, readCacheTtlRewrite } from './runtime-policy';
import { isNativeClassificationContext } from './request-attribution';
import { isModelSelection } from './upstream';
import { isNativeErrorDiagnostics } from './native-error-diagnostics';

const RESTORE_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const RESTORE_NONCE = /^[0-9a-f]{64}$/;

function headerPairs(value: unknown): value is HeaderPair[] {
  return Array.isArray(value) && value.every(x => Array.isArray(x) && x.length === 2 && typeof x[0] === 'string' && typeof x[1] === 'string');
}

/** 解码私有工作进程事件，避免各消费者分别猜测字段。
 * @param line 完整 JSONL 行。
 * @param requestId 期望绑定的请求。
 * @return 经过边界验证的事件。
 */
export function decodeRuntimeEvent(line: string, requestId: string): RuntimeEvent {
  return validateRuntimeEvent(JSON.parse(line), requestId);
}

/** 校验已解析的事件，供隔离转发边界复用同一字段合同。
 * @param value 私有通道解析值。
 * @param requestId 当前请求归属。
 * @return 已验证事件。
 */
export function validateRuntimeEvent(value: unknown, requestId: string): RuntimeEvent {
  if (!isObject(value) || value.schema_version !== 1 || value.request_id !== requestId || typeof value.type !== 'string') throw new BridgeError('runtime_protocol', '运行时消息与请求不匹配', 502);
  let valid = false;
  switch (value.type) {
    case 'ready': valid = typeof value.version === 'string'; break;
    case 'header_policy': valid = value.attempt === 1 && Array.isArray(value.decisions) && value.decisions.every(item => isObject(item) && typeof item.name === 'string' && ['keep', 'drop', 'runtime', 'context'].includes(String(item.action)) && typeof item.reason === 'string' && Object.keys(item).every(key => ['name', 'action', 'reason'].includes(key))); break;
    case 'final_capture_ready': valid = value.attempt === 1; break;
    case 'cc_prepared': valid = value.attempt === 1 && typeof value.body === 'string' && headerPairs(value.headers) && Number.isSafeInteger(value.body_bytes) && Number(value.body_bytes) >= 0 && typeof value.body_sha256 === 'string' && /^[a-f0-9]{64}$/.test(value.body_sha256) && (value.cache_policy === undefined || isCachePolicyDecision(value.cache_policy)); break;
    case 'response_headers': valid = value.attempt === 1 && Number.isInteger(value.status) && Number(value.status) >= 200 && Number(value.status) <= 599 && headerPairs(value.headers); break;
    case 'response_chunk': valid = value.attempt === 1 && typeof value.data_b64 === 'string' && value.data_b64.length % 4 === 0 && /^[A-Za-z0-9+/]*={0,2}$/.test(value.data_b64); break;
    case 'completed': valid = value.attempt === 1 && ['success', 'http_error', 'stream_error', 'incomplete', 'canceled', 'error'].includes(String(value.state)) && (value.error === undefined || typeof value.error === 'string'); break;
    case 'error': valid = typeof value.error === 'string' && (value.code === undefined || typeof value.code === 'string') && (value.status === undefined || (Number.isInteger(value.status) && Number(value.status) >= 400 && Number(value.status) <= 599)); break;
  }
  if (!valid) throw new BridgeError('runtime_protocol', '运行时事件格式错误', 502);
  if (value.type === 'error') {
    // 诊断属于旁路元数据；重建字段可保留真实错误，避免损坏摘要覆盖业务状态或携带扩展原文。
    return runtimeEvent(requestId, {
      type: 'error', error: value.error as string,
      ...(value.code === undefined ? {} : { code: value.code as string }),
      ...(value.status === undefined ? {} : { status: value.status as number }),
      ...(isNativeErrorDiagnostics(value.diagnostics) ? { diagnostics: value.diagnostics }
        : value.diagnostics !== undefined || value.diagnostics_state !== undefined ? { diagnostics_state: 'invalid' as const } : {}),
    });
  }
  return value as unknown as RuntimeEvent;
}

/** 解码控制进程发送的私有作业。
 * @param value 私有管道读到的 JSON。
 * @return 单次作业。
 */
export function decodeRuntimeJob(value: unknown): RuntimeJob {
  if (!isObject(value) || value.type !== 'request_start' || value.schema_version !== 1 || typeof value.request_id !== 'string' || !isObject(value.prepared)) throw new BridgeError('runtime_protocol', '无效运行时作业');
  const prepared = value.prepared;
  if (isObject(prepared.input) && prepared.input.nativeIngressPolicy !== undefined && (!['strict', 'local_base_url'].includes(String(prepared.input.nativeIngressPolicy)) || prepared.input.inputFormat !== 'claude_code')) throw new BridgeError('runtime_protocol', '运行时原生入站策略不合法', 502);
  if (isObject(prepared.input) && prepared.input.inputFormat !== undefined && !['api', 'claude_code'].includes(String(prepared.input.inputFormat))) throw new BridgeError('runtime_protocol', '运行时接入类型不合法', 502);
  if (!isObject(prepared.input) || prepared.input.request_id !== value.request_id || !isObject(prepared.input.body) || !Array.isArray(prepared.input.body.messages) || !isObject(prepared.context) || typeof prepared.context.sessionId !== 'string' || typeof prepared.context.promptId !== 'string' || !headerPairs(prepared.headers)) throw new BridgeError('runtime_protocol', '运行时作业缺少上下文');
  if (prepared.context.classification !== undefined && (prepared.input.inputFormat !== 'claude_code' || !isNativeClassificationContext(prepared.context))) throw new BridgeError('runtime_protocol', '运行时分类证据不匹配');
  if (prepared.context.modelSelection !== undefined && (!isModelSelection(prepared.context.modelSelection) || prepared.context.modelSelection.effective !== prepared.input.body.model)) throw new BridgeError('runtime_protocol', '运行时模型选择证据不匹配');
  return value as unknown as RuntimeJob;
}

/** 建立带版本与归属的运行时事件。
 * @param requestId 请求归属。
 * @param payload 已知事件载荷。
 * @return 可序列化事件。
 */
export function runtimeEvent(requestId: string, payload: RuntimePayload): RuntimeEvent {
  return { ...payload, schema_version: 1, request_id: requestId };
}

/** 校验账号常驻进程收到的指令。
 * @param value 私有管道解析得到的对象。
 * @param workerId 本物理进程的唯一归属。
 * @return 已验证指令；旧协议及跨进程指令明确失败。
 */
export function decodeWorkerCommand(value: unknown, workerId: string): WorkerCommand {
  if (!isObject(value) || value.schema_version !== 2 || value.worker_id !== workerId) throw new BridgeError('runtime_protocol', '工作进程指令归属不匹配', 502);
  if (value.type === 'worker_shutdown') return value as unknown as WorkerCommand;
  if (value.type === 'worker_restore_bind') {
    if (typeof value.template_id !== 'string' || !RESTORE_UUID.test(value.template_id) || typeof value.new_worker_id !== 'string' || !RESTORE_UUID.test(value.new_worker_id) || value.new_worker_id === workerId || typeof value.nonce !== 'string' || !RESTORE_NONCE.test(value.nonce) || Object.keys(value).some(key => !['type', 'schema_version', 'worker_id', 'template_id', 'new_worker_id', 'nonce'].includes(key))) throw new BridgeError('runtime_protocol', '恢复绑定格式错误', 502);
    return value as unknown as WorkerCommand;
  }
  if (typeof value.request_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(value.request_id)) throw new BridgeError('runtime_protocol', '工作进程缺少有效请求归属', 502);
  if (value.type === 'request_cancel') return value as unknown as WorkerCommand;
  if (value.type === 'request_input') {
    if (!isObject(value.input) || value.input.schema_version !== 1 || value.input.request_id !== value.request_id) throw new BridgeError('runtime_protocol', '原始输入与请求归属不匹配', 502);
    readCacheTtlRewrite(value.cache_ttl_rewrite);
    return value as unknown as WorkerCommand;
  }
  if (value.type !== 'request_start') throw new BridgeError('runtime_protocol', '未知工作进程指令', 502);
  // 复用同一 PreparedInput 边界，不允许包装协议绕过原有作业校验。
  decodeRuntimeJob({ ...value, schema_version: 1 });
  return value as unknown as WorkerCommand;
}

/** 校验常驻进程输出的握手及请求事件。
 * @param line 完整 JSONL 行。
 * @param workerId 读取循环绑定的物理进程归属。
 * @return 已验证帧；具体请求状态顺序由引擎统一校验。
 */
export function decodeWorkerFrame(line: string, workerId: string): WorkerFrame {
  const value: unknown = JSON.parse(line);
  if (!isObject(value) || value.schema_version !== 2 || value.worker_id !== workerId) throw new BridgeError('runtime_protocol', '工作进程事件归属不匹配', 502);
  if (value.type === 'worker_error') {
    if (value.code !== 'native_configuration' || value.status !== 503 || typeof value.error !== 'string' || !value.error.trim() || Buffer.byteLength(value.error) > 2048 || Object.keys(value).some(key => !['type', 'schema_version', 'worker_id', 'code', 'status', 'error'].includes(key))) throw new BridgeError('runtime_protocol', '工作进程初始化错误帧格式错误', 502);
    return value as unknown as WorkerFrame;
  }
  if (value.type === 'worker_ready') {
    if (value.restore_protocol !== undefined && value.restore_protocol !== 1) throw new BridgeError('runtime_protocol', '恢复协议版本错误', 502);
    if (value.restore_template !== undefined && (value.restore_protocol !== 1 || typeof value.restore_template !== 'string' || !RESTORE_UUID.test(value.restore_template))) throw new BridgeError('runtime_protocol', '恢复模板归属错误', 502);
    if (value.restore_binding !== undefined) {
      const binding = value.restore_binding;
      if (value.restore_protocol !== 1 || value.restore_template !== undefined || !isObject(binding) || typeof binding.template_id !== 'string' || !RESTORE_UUID.test(binding.template_id) || typeof binding.nonce !== 'string' || !RESTORE_NONCE.test(binding.nonce) || binding.entropy_profile !== 'bun143-wipeonfork-v1' || Object.keys(binding).some(key => !['template_id', 'nonce', 'entropy_profile'].includes(key))) throw new BridgeError('runtime_protocol', '恢复握手归属错误', 502);
    }
  }
  if (value.type === 'worker_ready' && typeof value.version === 'string' && Number.isSafeInteger(value.pid) && Number(value.pid) > 0 && (value.raw_input_protocol === undefined || value.raw_input_protocol === 1) && (value.cache_ttl_rewrite_protocol === undefined || value.cache_ttl_rewrite_protocol === 1) && (value.cache_policy === undefined || value.cache_policy === 'preserve' || value.cache_policy === 'sub2api') && (value.telemetry === undefined || isTelemetryHandshake(value.telemetry))) return value as unknown as WorkerFrame;
  if (typeof value.request_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(value.request_id)) throw new BridgeError('runtime_protocol', '工作进程事件缺少有效请求归属', 502);
  if (value.type === 'worker_idle') return value as unknown as WorkerFrame;
  if (value.type === 'request_event' && isObject(value.payload)) {
    const payload = value.payload;
    if (['schema_version', 'request_id', 'worker_id'].some(key => key in payload)) throw new BridgeError('runtime_protocol', '请求载荷不能覆盖协议归属', 502);
    // 同一 JSONL 已经解析；直接校验对象，避免完整 CLI 正文再次编码和解析。
    const validated = validateRuntimeEvent({ ...payload, schema_version: 1, request_id: value.request_id }, value.request_id);
    if (payload.type === 'ready' || payload.type === 'final_capture_ready') throw new BridgeError('runtime_protocol', '工作进程不能声明控制侧握手或最终采集', 502);
    const { schema_version, request_id, ...normalized } = validated;
    return { ...value, payload: normalized } as unknown as WorkerFrame;
  }
  throw new BridgeError('runtime_protocol', '工作进程帧格式错误', 502);
}
