import type { CachePolicy, CachePolicyDecision, CacheTtlRewrite, TelemetryHandshake } from './runtime-policy';
import type { NativeErrorDiagnostics } from './native-error-diagnostics';

/** JSON 对象，解析和验证由共享入口统一负责。 */
export type JsonObject = Record<string, unknown>;

/** 保留头名、大小写和重复项的输入表示。 */
export type HeaderPair = [string, string];

/** 仅由服务启动配置选择的原生入站策略，不能由 HTTP 正文授权。 */
export type NativeIngressPolicy = 'strict' | 'local_base_url';

/** 固定 293 已识别的请求类别。 */
export type RequestClass = 'main' | 'subagent' | 'workflow' | 'compaction' | 'auxiliary' | 'side_reply';

/** 一个 API 消息，不把用户工具转换为本地可执行工具。 */
export interface ApiMessage extends JsonObject {
  role: 'user' | 'assistant' | 'system';
  content: string | JsonObject[];
}

/** 首版能够适配的 Messages API 参数。 */
export interface MessageBody extends JsonObject {
  model: string;
  messages: ApiMessage[];
  system?: string | JsonObject[];
  tools?: JsonObject[];
  tool_choice?: JsonObject;
  max_tokens?: number;
  thinking?: JsonObject;
  temperature?: number;
  output_config?: JsonObject;
  stream?: boolean;
}

/** 调用方可以显式提供的关联信息。 */
export interface ContextInput {
  requestClass?: RequestClass;
  sessionId?: string;
  promptId?: string;
  agentId?: string;
  parentAgentId?: string;
  agentType?: string;
  agentKind?: 'main' | 'subagent' | 'teammate';
  workflowRunId?: string;
}

/** 固定原生构造的分类用途证据，不作为客户端身份认证。 */
export type NativeClassification = { source: 'native_profile' } & (
  { purpose: 'auto_permission_classifier'; profile: 'cc293-auto-mode-xml-s1' | 'cc293-auto-mode-xml-s2' }
  | { purpose: 'session_title'; profile: 'cc293-session-title-v1' }
  | { purpose: 'compaction'; profile: 'cc293-compact-full-v1' }
);

/** 从同一请求的 Agent 调用与成功结果中配对的关联声明。 */
export interface AgentLaunchEvidence {
  childAgentId: string;
  parentAgentId: string | null;
  agentType: string | null;
  toolUseId: string;
}

/** 有界提取结果；不完整时不能据已保存前缀宣称证据完整。 */
export interface AgentLaunches {
  state: 'complete' | 'incomplete';
  links: AgentLaunchEvidence[];
}

/** 详情中的关联证据定位，不包含工具原文。 */
export interface AgentAssociationEvidence {
  requestId: string;
  toolUseId: string;
}

/** 只读关联视图，和发生时的原始上下文保持独立。 */
export interface AgentAssociation {
  state: 'explicit' | 'linked' | 'unknown' | 'conflict' | 'incomplete';
  parentAgentId: string | null;
  agentType: string | null;
  parentSource: 'explicit' | 'client_tool_result' | 'unknown';
  typeSource: 'explicit' | 'client_tool_result' | 'unknown';
  evidence: AgentAssociationEvidence[];
}

/** 经验证的内部调用，不允许头部改变控制配置。 */
export interface BridgeInput {
  schema_version: 1;
  request_id: string;
  body: MessageBody;
  headers: HeaderPair[];
  context: ContextInput;
  inputFormat?: 'api' | 'claude_code';
  nativeIngressPolicy?: NativeIngressPolicy;
}

/** 发生时的根模型选择，不等同于未经采集的上游响应模型。 */
export interface ModelSelection {
  requested: string;
  effective: string;
  source: 'request' | 'startup_override';
}

/** 已解析的调用上下文，各表示都以此为同一来源。 */
export interface RequestContext {
  modelSelection?: ModelSelection;
  classification?: NativeClassification;
  inputFormat?: 'api' | 'claude_code';
  requestClass: RequestClass;
  sessionId: string;
  promptId: string;
  agentId?: string;
  parentAgentId?: string;
  agentType?: string;
  agentKind: 'main' | 'subagent' | 'teammate';
  workflowRunId?: string;
  querySource: string;
  source: 'client' | 'bridge-default';
}

/** 可供日志和页面直接展示的头部处理结果，不记录秘密值。 */
export interface HeaderDecision {
  name: string;
  action: 'keep' | 'drop' | 'runtime' | 'context';
  reason: string;
}

/** 策略结果，运行时不会再从任意头中读取配置。 */
export interface PreparedInput {
  input: BridgeInput;
  context: RequestContext;
  headers: HeaderPair[];
  decisions: HeaderDecision[];
}

/** 请求及流的终态。 */
export type RequestState = 'queued' | 'running' | 'success' | 'http_error' | 'stream_error' | 'incomplete' | 'canceled' | 'error';

/** 采集来源，与传输是否完成分开记录。 */
export type CaptureStage = 'ingress' | 'header_policy' | 'cc_prepared' | 'wire_final' | 'upstream_response';

/** 阶段持久记录；哈希对应原始观测字节，内容为脱敏后的预览。 */
export interface CaptureRecord {
  stage: CaptureStage;
  attempt: number;
  capturedAt: string;
  source: string;
  representation: string;
  status: 'complete' | 'truncated' | 'unavailable' | 'failed' | 'incomplete';
  observedBytes: number;
  storedBytes: number;
  sha256: string | null;
  text: string | null;
  headers: HeaderPair[];
  note: string | null;
}

/** 一个请求的列表行及发生时的运行快照。 */
export interface RequestRow {
  agentLaunches?: AgentLaunches;
  id: string;
  createdAt: string;
  finishedAt: string | null;
  model: string;
  requestClass: string;
  sessionId: string;
  promptId: string;
  agentId: string | null;
  parentAgentId: string | null;
  state: RequestState;
  httpStatus: number | null;
  durationMs: number | null;
  headersMs: number | null;
  firstOutputMs: number | null;
  mode: 'off' | 'summary' | 'debug';
  engine: string;
  binarySha256: string | null;
  error: string | null;
  captureError: string | null;
}

/** 详情接口一次返回可审计的字段与阶段数据。 */
export interface RequestDetail {
  agentAssociation?: AgentAssociation;
  request: RequestRow;
  context: RequestContext | null;
  decisions: HeaderDecision[];
  captures: CaptureRecord[];
}

/** 查询列表时支持的服务端过滤参数。 */
export interface LogFilters {
  requestId?: string;
  model?: string;
  state?: string;
  requestClass?: string;
  sessionId?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

/** 控制进程与固定运行时之间的消息。 */
export type RuntimePayload =
  | { type: 'ready'; version: string }
  | { type: 'final_capture_ready'; attempt: 1 }
  | { type: 'header_policy'; attempt: 1; decisions: HeaderDecision[] }
  | { type: 'cc_prepared'; attempt: number; headers: HeaderPair[]; body: string; body_bytes: number; body_sha256: string; cache_policy?: CachePolicyDecision }
  | { type: 'response_headers'; attempt: number; status: number; headers: HeaderPair[] }
  | { type: 'response_chunk'; attempt: number; data_b64: string }
  | { type: 'completed'; attempt: number; state: RequestState; error?: string }
  | { type: 'error'; error: string; code?: string; status?: number; diagnostics?: NativeErrorDiagnostics; diagnostics_state?: 'invalid' };

/** 每条运行时消息都绑定请求，stdout 不混入普通日志。 */
export type RuntimeEvent = RuntimePayload & { schema_version: 1; request_id: string };

/** 控制进程交给独立工作进程的一次作业。 */
export interface RuntimeJob {
  type: 'request_start';
  schema_version: 1;
  request_id: string;
  prepared: PreparedInput;
}

/** 账号常驻进程接收的私有指令，进程和请求归属分别绑定。 */
export type WorkerCommand =
  | { type: 'worker_restore_bind'; schema_version: 2; worker_id: string; template_id: string; new_worker_id: string; nonce: string }
  | { type: 'request_start'; schema_version: 2; worker_id: string; request_id: string; prepared: PreparedInput }
  | { type: 'request_input'; schema_version: 2; worker_id: string; request_id: string; input: unknown; cache_ttl_rewrite?: CacheTtlRewrite }
  | { type: 'request_cancel'; schema_version: 2; worker_id: string; request_id: string }
  | { type: 'worker_shutdown'; schema_version: 2; worker_id: string };

/** 常驻进程输出；请求载荷解包后继续使用外部 schema 1。 */
export type WorkerFrame =
  | { type: 'worker_ready'; schema_version: 2; worker_id: string; version: string; pid: number; cache_policy?: CachePolicy; telemetry?: TelemetryHandshake; raw_input_protocol?: 1; cache_ttl_rewrite_protocol?: 1; restore_protocol?: 1; restore_template?: string; restore_binding?: { template_id: string; nonce: string; entropy_profile: 'bun143-wipeonfork-v1' } }
  | { type: 'worker_error'; schema_version: 2; worker_id: string; code: 'native_configuration'; status: 503; error: string }
  | { type: 'request_event'; schema_version: 2; worker_id: string; request_id: string; payload: RuntimePayload }
  | { type: 'worker_idle'; schema_version: 2; worker_id: string; request_id: string };
