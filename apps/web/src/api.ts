import type { AccountNodeSummary } from './components/runtime/nodeApi'

const BASE = ''

let authToken = ''
let runtimeSessionRequest: Promise<{ ok: boolean }> | undefined

/** 管理请求错误，保留冲突状态供操作确认窗口处理。 */
export class ApiError extends Error {
  readonly status: number
  /** @param status 实际 HTTP 状态。@param message 用户可读错误。@return 错误实例。 */
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** 更新管理凭据并释放旧凭据的会话交换引用。@param token 管理凭据。@return 无。 */
export function setAuth(token: string) {
  if (token !== authToken) runtimeSessionRequest = undefined
  authToken = token
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    signal,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${authToken}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    const detail = typeof err.error === 'string' ? err.error
      : typeof err.error?.message === 'string' ? err.error.message
      : typeof err.detail === 'string' ? err.detail : res.statusText
    throw new ApiError(res.status, detail)
  }
  return res.json()
}

/** 合并当前进行中的会话交换，结束后由后续入口重新核验。@return 同批会话签发结果。 */
function openRuntimeSession(): Promise<{ ok: boolean }> {
  if (runtimeSessionRequest) return runtimeSessionRequest
  const pending = request<{ ok: boolean }>('POST', '/admin/runtime/session').finally(() => {
    if (runtimeSessionRequest === pending) runtimeSessionRequest = undefined
  })
  runtimeSessionRequest = pending
  return pending
}

/** 账号持久信息，以及账号管理页使用的运行状态摘要。 */
/** 网关独立工作开关与真实请求收尾状态。 */
export interface AccountWorkControl {
  api_accepting: boolean
  work_enabled: boolean
  revision: number
  admitted_requests: number
  phase: 'enabled' | 'draining' | 'disabled'
  coordinated: boolean
}

/** 整体协调观察，任务和 API 的状态由各执行器确认。 */
export interface OverallWorkStatus {
  enabled?: boolean
  phase: 'enabled' | 'draining' | 'disabled' | 'reconcile'
  active_work?: number | null
  message?: string | null
}

export interface Account {
  id: number
  platform?: string
  agy_system_prompt_homoglyph_enabled?: boolean
  credential_state?: {generation:number; phase:string; operation_id?:string | null}
  name: string
  email: string
  status: string
  work_control?: AccountWorkControl
  auth_type: string
  setup_token: string
  access_token: string
  refresh_token: string
  expires_at?: number | null
  oauth_refreshed_at?: string
  auth_error?: string
  credential_ownership?: { protocol: number; owner: string; phase: string } | null
  proxy_url: string
  proxy_id?: string
  proxy_name?: string
  device_id: string
  canonical_env?: Record<string, unknown>
  canonical_prompt_env?: Record<string, unknown>
  canonical_process?: {
    constrained_memory?: number
    rss_range?: number[]
    heap_total_range?: number[]
    heap_used_range?: number[]
    observation?: {
      source: string
      environment_id: string
      cli_version: string
      observed_at: number
      sampled_at?: number | null
      sample_count: number
      rss_bytes?: number | null
      rss_min_bytes?: number | null
      rss_max_bytes?: number | null
    }
  }
  billing_mode: string
  request_backend?: 'legacy' | 'native293'
  account_uuid?: string | null
  organization_uuid?: string | null
  subscription_type?: string | null
  rate_limit_tier?: string | null
  concurrency: number
  priority: number
  rpm_limit: number
  five_hour_usage_limit_percent: number
  seven_day_usage_limit_percent: number
  rpm_current?: number
  rpm_remaining?: number | null
  rpm_window_reset_at?: string
  rpm_saturated?: boolean
  auto_telemetry: boolean
  auto_poll_usage: boolean
  allow_1m_models: string
  allow_fast_mode: boolean
  upstream_session_pool_enabled: boolean
  upstream_session_pool_size: number
  upstream_session_ttl_minutes: number
  upstream_session_refresh_policy: 'mapped_request' | 'owner_only' | string
  upstream_session_pool_active_count?: number
  upstream_session_pool_capacity?: number
  upstream_session_pool_oldest_last_seen_ms?: number | null
  upstream_session_pool_newest_last_seen_ms?: number | null
  telemetry_count: number
  telemetry_expires_at?: string
  v3_scheduling?: SchedulingSummary
  v3_scheduling_error?: string
  current_concurrency?: number
  current_concurrency_units?: number
  max_concurrency_units?: number
  active_requests?: number
  queued_requests?: number
  queued_request_units?: number
  transient_backoff_waiting?: number
  transient_backoff_remaining_ms?: number
  rate_limited_at?: string
  rate_limit_reset_at?: string
  disable_reason?: string
  usage_data?: UsageData
  usage_fetched_at?: string
  request_usage?: RequestUsage | null
  agy_request_usage?: AgyRequestUsage | null
  created_at: string
  updated_at: string
}

/** v3 当前请求阶段计数，独立于绑定会话数与加权槽位。 */
export interface SchedulingPhases {
  waiting_concurrency: number
  preparing: number
  waiting_send: number
  running: number
  backoff: number
}

/** v3 调度器的真实生效配置和可解释容量摘要。 */
export interface SchedulingSummary {
  config: { mode: 'smart'; reset_weight?: number; queue_weight?: number; reset_window_weights?: [number, number]; wait_seconds: number; weights: [number, number, number, number] }
  factors: { load: number; quota: number; quota_state?: 'unknown' | 'reset_pending' | 'observed'; health: number; latency: number; score: number; reset?: number; queue?: number; wait_score?: number; estimated_wait_ms?: number | null; wait_basis?: 'pacing' | 'sampled' | 'pressure' }
  capacity: { immediate: boolean; can_queue: boolean; reason: string; earliest_submit_at_ms: number }
  observed_at_ms: number
  bound_sessions: number
  active_sessions: number
  unbound_requests: number
  phases: SchedulingPhases
  next_send_at_ms: number | null
  submissions_last_60s: number
  history_available_from_ms: number
  history_truncated: boolean
}

/** 无正文或原始会话 ID 的管理调度详情。 */
export interface SchedulingDetail {
  summary: SchedulingSummary
  snapshot: {
    observed_at_ms: number
    history_available_from_ms: number
    history_truncated: boolean
    dropped_events: number
    submissions_last_60s: number
    requests: { request_id: string; session_key: string | null; account_id: number; bound: boolean; phase: string; started_at_ms: number; phase_since_ms: number }[]
    events: { request_id: string; account_id: number; submitted_at_ms: number }[]
  }
}

/** 一个按 Token 隔离的匿名网关绑定及当前请求分布。 */
export interface SchedulingSession {
  session_key: string
  account_id: number
  created_at_ms: number
  last_seen_at_ms: number
  expires_at_ms: number
  phases: SchedulingPhases
}

/** 有界分页会话结果，不含官方聊天内容。 */
export interface SchedulingSessions {
  items: SchedulingSession[]
  total: number
  page: number
  page_size: number
  observed_at_ms: number
}

export interface PagedResult<T> {
  data: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface UsageWindow {
  utilization: number
  resets_at?: string | null
}

/** 账号从网关实际响应记录的两个用量窗口。 */
export interface RequestUsage {
  recorded_since: string
  five_hour: WindowUsageStats
  seven_day: WindowUsageStats
}

/** 本地窗口统计；basis 区分官方周期和最近滚动时间段。 */
export interface WindowUsageStats {
  requests: number
  tokens: number
  cost_usd: number
  unpriced_requests: number
  partial_requests: number
  starts_at: string
  ends_at: string
  basis: 'quota' | 'rolling'
  coverage_complete: boolean
  estimated_total_cost_usd: number | null
}

export interface UsageLimit {
  kind?: string
  group?: string
  percent?: number
  resets_at?: string | null
  scope?: {
    model?: {
      id?: string | null
      display_name?: string | null
    } | null
  } | null
}

/** 反重力已记录的网关用量窗口。 */
export interface AgyUsageWindow {
  requests: number
  tokens: number | null
  partial_requests: number
}

/** 基于请求记录的滚动用量。 */
export interface AgyRequestUsage {
  five_hour: AgyUsageWindow
  seven_day: AgyUsageWindow
}

/** 上游返回的剩余比例和重置时间。 */
export interface AgyQuotaReading {
  remaining_fraction: number | null
  remaining_amount?: number | null
  reset_at: string | null
}

/** 共享额度查询和逐模型查询各自保留独立观测时间。 */
export interface AgyPlatformQuota {
  checked_at_ms: number
  status: 'ok' | 'partial' | 'unavailable'
  plan?: string | null
  tier?: string | null
  groups?: {observed_at_ms: number; items: {
    name: string
    windows: (AgyQuotaReading & { id: string; period: '5h' | 'weekly' })[]
  }[]}
  models?: {observed_at_ms: number; items: (AgyQuotaReading & { model: string })[]}
}

export interface UsageData {
  platform?: string
  capabilities?: {source:string; observed_at_ms:number; models:string[]; provider?:Record<string,unknown>}
  platform_quota?: AgyPlatformQuota
  five_hour?: UsageWindow | null
  seven_day?: UsageWindow
  seven_day_sonnet?: UsageWindow
  seven_day_fable?: UsageWindow
  limits?: UsageLimit[]
}

export interface ApiToken {
  id: number;
  name: string;
  token: string;
  allowed_accounts: string;
  blocked_accounts: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Dashboard {
  accounts: { total: number; active: number; error: number; disabled: number };
  tokens: number;
}

export interface OAuthGenerateResult {
  auth_url: string;
  session_id: string;
}

export interface OAuthExchangeResult {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  expires_at: number;
  scope: string;
  account_uuid: string;
  organization_uuid: string;
  email_address: string;
}

/** 峰值预热调用日志,对应后端 `prime_logs` 表单行。 */
export interface PrimeLogEntry {
  id: number;
  account_id: number;
  account_name: string;
  /** ISO8601 本地时间字符串 */
  triggered_at: string;
  /** 触发的小时(0-23) */
  hour: number;
  model: string;
  success: boolean;
  error_message: string;
  duration_ms: number;
}

export type SettingsMap = Record<string, string>

/** 一次持久系统更新操作的公开进度。 */
export interface SystemUpdateOperation {
  operation_id: string
  action: 'prepare' | 'install' | 'rollback'
  phase: string
  target_release: string
  created_at: string
  updated_at: string
  error?: string | null
  blockers?: string[]
  cancel_requested?: boolean
  cluster_nodes?: { phase: string; nodes: Array<{ node_id: number; name?: string; phase: string; running: boolean; preparation?: { phase?: string; reason?: string; state?: string } }> } | null
  database_snapshot?: { state: string; completed_at: string; bytes: number } | null
  database_migrations?: Record<string, { state: string; target_version: number }> | null
  cleanup?: { status: string; removed: string[]; retained?: string[] } | null
  /** 按实际顺序记录的阶段与进入时间；旧操作没有记录时为空。 */
  steps?: Array<{ phase: string; at: string }> | null
}

/** 当前控制镜像提供的独立平台版本。 */
export interface SystemPlatformVersion {
  version: string | null
}

/** 已安装底座的实际组件及恢复入口。 */
export interface SystemUpdateStatus {
  installed: boolean
  migration_capability?: boolean
  message?: string
  revision?: string
  current_release?: string
  deployment?: string
  components?: Record<'control' | 'account', { release: string; reference: string; content_sha256: string }>
  environments?: Array<{ environment_id: string; name: string; release: string | null; running: boolean; verified: boolean }>
  busy?: boolean
  operation?: SystemUpdateOperation | null
  history?: Array<{ release: string; manifest_sha256: string; installed_at?: string; rollback_available: boolean }>
  checked_at?: string | null
  check_error?: string | null
}

/** 可安装的已验签发行摘要。 */
export interface SystemUpdateRelease {
  release: string
  sequence: number[]
  published_at: string
  changes: string
  manifest_sha256: string
  data_compatible: boolean
  account_changed: boolean
  compatibility_reason?: 'data_contract_unverified' | 'migration_evidence_missing' | null
  migrations?: Array<{ database: string; target_version: number; steps: number }>
}

/** 目录状态与最近受信发行。 */
export interface SystemUpdateCatalog {
  fresh: boolean
  releases: SystemUpdateRelease[]
  checking: boolean
  checked_at?: string | null
  check_error?: string | null
}

/** 点击安装时冻结的现场、目标及等待期限。 */
export interface SystemUpdateRequest {
  operation_id: string
  expected_revision: string
  target_release: string
  target_manifest_sha256: string
  drain_timeout_seconds: number
}

type RawSettingsMap = Record<string, unknown>

/** 将历史或代理返回的非字符串 settings 值规整为前端表单契约使用的字符串。 */
function normalizeSettingsMap(data: RawSettingsMap): SettingsMap {
  return Object.fromEntries(
    Object.entries(data).map(([key, value]) => {
      if (typeof value === 'string') return [key, value]
      if (value == null) return [key, '']
      if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
        return [key, String(value)]
      }
      const encoded = JSON.stringify(value)
      return [key, encoded ?? String(value)]
    }),
  )
}

/** 一轮会话封禁的安全摘要。 */
export interface SessionPolicyBlock {
  id: string
  session_key: string
  api_token_id: number
  token_name: string | null
  account_id: number
  account_name: string | null
  model: string
  reason: string
  source_request_id: string | null
  blocked_at_ms: number
  expires_at_ms: number
  released_at_ms: number | null
  blocked_request_count: number
  last_blocked_at_ms: number | null
  state: 'active' | 'expired' | 'released'
}
/** 会话封禁分页与服务器观察时刻。 */
export interface SessionPolicyBlockPage { items: SessionPolicyBlock[]; total: number; page: number; page_size: number; observed_at_ms: number }

/** 管理端请求诊断列表行。 */
export interface DiagnosticRequest {
  context?: DiagnosticContext | null
  native_rejection?: { reason: string | null; capture_id: string; capture_status: string } | null
  original_session_id?: string | null
  account_name?: string | null
  account_email?: string | null
  log_mode?: 'info' | 'debug' | null
  request_id: string
  started_at: string
  finished_at?: string | null
  response_request_id?: string | null
  error_stage?: string | null
  status_code: number | null
  account_id: number | null
  outcome: string
  attempt_count: number
  last_attempt?: DiagnosticAttempt | null
}

/** 原生请求实际复用的进程及本地阶段观测。 */
export interface NativeRuntimeObservation {
  worker_id: string
  worker_pid: number
  kernel_generation: string | null
  warm_hit: boolean
  preparation_wait_ms: number
  checkout_ms: number
  worker_start_ms: number | null
  prepared_ms: number
}

/** 单次实际提交及私有采集状态。 */
export interface DiagnosticAttempt {
  context?: DiagnosticContext | null
  execution_location?: { node_key: string; environment_id: string; generation: number; assignment_revision: number | null } | null
  account_name?: string | null
  account_email?: string | null
  runtime?: NativeRuntimeObservation | null
  log_mode?: 'info' | 'debug' | null
  attempt_id: string
  account_id: number
  ordinal: number
  profile_selection: string
  capture_status?: string | null
  status_code: number | null
  outcome: string
  request_id?: string
  profile_version?: string
  started_at?: string
  finished_at?: string | null
  duration_ms?: number | null
  ttft_ms?: number | null
  first_output_ms?: number | null
  response_model?: string | null
  upstream_request_id?: string | null
  error_stage?: string | null
  error_type?: string | null
  retry_reason?: string | null
  stop_reason?: string | null
  partial?: boolean
  parameters?: { model: string | null; max_tokens: number | null; thinking_type: string | null;
    thinking_budget: number | null; effort: string | null; stream: boolean | null; tools_count: number | null }
  sessions?: { real_session_hash: string | null; upstream_session_hash: string | null;
    mapping_action: string | null; previous_message_hash: string | null }
  tokens?: { input_tokens: number | null; output_tokens: number | null; cache_read_tokens: number | null;
    cache_write_tokens: number | null; cache_write_5m_tokens: number | null; cache_write_1h_tokens: number | null }
}

/** 入口冻结与本次源事件的跨平台诊断事实。 */
export interface DiagnosticContext {
  platform?: string | null
  entry_protocol?: string | null
  requested_model?: string | null
  kernel?: string | null
  kernel_version?: string | null
  submitted_model?: string | null
  response_model_version?: string | null
  source_sha256?: string | null
  credential_generation?: number | null
  environment_id?: string | null
  environment_generation?: number | null
  worker_id?: string | null
  worker_generation?: string | null
  conversation_id?: string | null
  trajectory_id?: string | null
  native_model_calls?: number | null
  control_state?: string | null
  control_observed_at?: string | null
  response_headers_source?: string | null
  usage?: { source: string; usage_metadata: unknown; total_tokens: number | null; thoughts_tokens: number | null; complete: boolean } | null
  system_prompt_policy?: { enabled: boolean; rule_version: string; rule_sha256: string | null; source: string | null;
    changed: boolean | null; replaced_codepoints: number | null; system_codepoints: number | null } | null
  tool_turn?: { continuation_of_request_id: string | null; previous_attempt_id: string | null; state: string;
    observed_at: string; call_hashes: string[] } | null
}

/** 阶段证据的来源与完整性。 */
export interface NativeCaptureStage {
  stage: string
  source: string
  representation: string
  status: string
  note?: string
}

/** 原始逻辑字节对应的脱敏预览，哈希保持实际观测语义。 */
export interface NativeCapturePreview {
  headers: [string, string][]
  body: string
  body_truncated: boolean
  headers_truncated: boolean
  original_body_bytes: number
  original_body_sha256: string
}

/** 原生TLS实际接受的实体证据；未知范围与网络刷出单独表示。 */
export interface NativeTlsCapture extends Omit<NativeCapturePreview, 'original_body_bytes' | 'original_body_sha256'> {
  source: 'native_tls_uprobe'
  representation: 'http_entity_from_tls_accepted_write'
  status: 'complete' | 'incomplete' | 'unavailable'
  reason: string | null
  original_body_bytes: number | null
  original_body_sha256: string | null
  observed_body_bytes: number | null
  body_sha256: string | null
  observed_http_bytes?: number
  http_sha256?: string
  complete: boolean
  flushed: null
  worker_id?: string
  capture_id?: string
  worker_pid?: number
  connection_id?: string
  binding_generation?: number
}

/** 已脱敏的 CC 组装后快照。 */
export interface NativeCapture {
  state: string
  message?: string
  snapshot?: {
    stage: 'cc_prepared' | 'ingress_rejected' | 'agy_prepared'
    decoded_gemini?: NativeCapturePreview
    ingress?: NativeCapturePreview
    wire_final?: NativeTlsCapture
    final_body_changes?: {
      source: string
      status: string
      items: { path: string; action: 'added' | 'removed' | 'changed'; reason: string }[]
    }
    final_header_changes?: {
      source: string
      status: string
      items: { name: string; action: 'added' | 'removed' | 'changed'; reason: string }[]
    }
    stages?: NativeCaptureStage[]
    header_policy?: {
      source: string
      status: string
      observed_count?: number
      stored_count?: number
      note?: string
      decisions: { name: string; action: 'keep' | 'drop' | 'runtime' | 'context'; reason: string }[]
    }
    body_changes?: {
      source: string
      status: string
      note?: string
      items: { path: string; action: 'added' | 'removed' | 'changed'; reason: string }[]
    }
    headers: [string, string][]
    body: string
    body_truncated: boolean
    headers_truncated: boolean
    original_body_bytes: number | null
    original_body_sha256: string | null
  }
}

/** 代理线路公开投影，认证字段仅显示是否已设置。 */
export interface ProxyRoute {
  id: string; name: string; protocol: string; host: string; port: number; public_url: string;
  has_username: boolean; has_password: boolean; expires_at: string | null; revision: string;
  status: 'unknown' | 'ready' | 'failed'; checked_at: string | null;
  observation: { ip: string; country: string | null; country_code: string | null; region: string | null; city: string | null; latency_ms: number; observed_at: string } | null;
  users: { kind: 'gateway' | 'task' | 'draft' | 'authorization'; id: string; name: string; status: string; in_flight: number | null }[];
  sync_pending?: boolean; references_complete: boolean; active_accounts: number; in_flight: number;
}
/** 账号诊断读取的环境公开摘要，身份匹配采用网关账号ID。 */
export interface RuntimeEnvironmentSummary {
  environment_id: string; gateway_account_id?: number | null; state: string;
  cli_versions?: string[]; native_kernel?: { current?: { release?: string } | null } | null;
  run_window?: { message?: string } | null;
}
/** 结构化代理表单；缺省认证字段表示保留。 */
export interface ProxyConnectionInput { protocol: string; host: string; port: number; username?: string; password?: string }
/** 线路编辑快照。 */
export interface ProxyInput extends ProxyConnectionInput { name: string; expires_at: string | null; revision?: string }

export const api = {
  /** 批量只读账号节点归属，沿原同源管理会话。@param signal 取消读取。@return 公开账号摘要。 */
  runtimeAccountNodes: (signal: AbortSignal) => request<AccountNodeSummary[]>('GET', '/runtime/api/accounts', undefined, signal),
  /** 搜索公开线路。@param page 页码。@param q 公开搜索。@param signal 取消信号。@return 分页。 */
  listProxies: (page = 1, q = '', signal?: AbortSignal, usage = true, pageSize = 20) => request<PagedResult<ProxyRoute> & { references_complete: boolean; counts?: { all:number; available:number; used:number|null } }>('GET', `/admin/proxies?page=${page}&page_size=${pageSize}&q=${encodeURIComponent(q)}&usage=${usage}`, undefined, signal),
  /** 保存线路。@param id 编辑身份，空为新建。@param input 草稿。@return 保存身份。 */
  saveProxy: (id: string | null, input: ProxyInput) => request<{id: string; sync_pending?: boolean}>(id ? 'PUT' : 'POST', id ? `/admin/proxies/${encodeURIComponent(id)}` : '/admin/proxies', input),
  /** 原子导入。@param text 多行连接。@return 创建条数。 */
  importProxies: (text: string) => request<{created: number}>('POST', '/admin/proxies/import', {text}),
  /** 拆分刚输入的连接。@param text 私有连接。@return 结构化字段。 */
  identifyProxy: (text: string) => request<ProxyConnectionInput>('POST', '/admin/proxies/identify', {text}),
  /** 探测出口。@param id 线路身份。@return 实际状态。 */
  probeProxy: (id: string) => request<Pick<ProxyRoute, 'id' | 'status' | 'observation' | 'checked_at'>>('POST', `/admin/proxies/${encodeURIComponent(id)}/probe`),
  /** 删除确认版本。@param id 线路身份。@param revision 原版本。@return 回执。 */
  deleteProxy: (id: string, revision: string) => request<{ok: boolean}>('DELETE', `/admin/proxies/${encodeURIComponent(id)}`, {revision}),
  /** 读取系统更新底座及实际安装。@param signal 取消信号。@return 更新状态。 */
  /** 读取任务运行数量，使用数据库聚合避免下载运行列表。@param signal 取消信号。@return 活动运行数。 */
  runtimeSummary: (signal?: AbortSignal) => request<{active_runs:number}>('GET','/runtime/api/summary',undefined,signal),
  /** 读取账号诊断摘要。@param signal 取消信号。@return 环境公开列表。 */
  runtimeEnvironments: (signal: AbortSignal) => request<RuntimeEnvironmentSummary[]>('GET', '/runtime/api/environments', undefined, signal),
  /** 读取当前控制端版本，独立于宿主更新器。@param signal 取消信号。@return 版本或未知值。 */
  systemPlatformVersion: (signal?: AbortSignal) => request<SystemPlatformVersion>('GET', '/runtime/api/system-updates/version', undefined, signal),
  systemUpdateStatus: (signal?: AbortSignal) => request<SystemUpdateStatus>('GET', '/runtime/api/system-updates/status', undefined, signal),
  /** 读取已验证目录。@param signal 取消信号。@return 版本缓存。 */
  systemUpdateReleases: (signal?: AbortSignal) => request<SystemUpdateCatalog>('GET', '/runtime/api/system-updates/releases', undefined, signal),
  /** 请求后台检查，安装由独立操作触发。@return 检查状态。 */
  systemUpdateCheck: () => request<{ checking: boolean }>('POST', '/runtime/api/system-updates/check', {}),
  /** 提交冻结组合。@param action 受支持动作。@param body 冻结参数。@return 持久操作。 */
  systemUpdateInstall: (action: 'install' | 'rollback', body: SystemUpdateRequest) => request<SystemUpdateOperation>('POST', `/runtime/api/system-updates/${action}`, body),
  /** 原操作取消或恢复。@param id 原操作。@param action 受控动作。@param revision 当前现场版本。@return 操作状态。 */
  systemUpdateControl: (id: string, action: 'cancel' | 'recover', revision: string) => request<SystemUpdateOperation>('POST', `/runtime/api/system-updates/operations/${encodeURIComponent(id)}/${action}`, { expected_revision: revision }),
  /** 查询会话封禁。@param query 已编码条件。@param signal 取消信号。@return 安全分页。 */
  sessionPolicyBlocks: (query: string, signal?: AbortSignal) => request<SessionPolicyBlockPage>('GET', `/admin/session-policy-blocks?${query}`, undefined, signal),
  /** 提前解除单轮封禁。@param id 记录标识。@return 最新摘要。 */
  releaseSessionPolicyBlock: (id: string) => request<SessionPolicyBlock>('POST', `/admin/session-policy-blocks/${encodeURIComponent(id)}/release`),
  /** 分页读取请求诊断。@param query 已编码筛选。@return 请求列表与采集健康。 */
  requestDiagnostics: (query: string, signal?: AbortSignal) => request<{ items: DiagnosticRequest[]; total: number; health: Record<string, number>; counts?: {all: number; errors: number; processing: number} }>('GET', `/admin/request-diagnostics?${query}`, undefined, signal),
  /** 读取请求尝试详情。@param id 请求 UUID。@return 摘要与尝试列表。 */
  requestDiagnosticDetail: (id: string, signal?: AbortSignal) => request<{ request: DiagnosticRequest; attempts: DiagnosticAttempt[] }>('GET', `/admin/request-diagnostics/${encodeURIComponent(id)}`, undefined, signal),
  /** 读取归属本请求的私有快照。@param requestId 请求 UUID。@param attemptId 尝试 UUID。@return 脱敏组装内容。 */
  nativeCapture: (requestId: string, attemptId: string, signal?: AbortSignal) => request<NativeCapture>('GET', `/admin/request-diagnostics/${encodeURIComponent(requestId)}/captures/${encodeURIComponent(attemptId)}`, undefined, signal),

  /** 换取 v3 的独立浏览器会话。@return 会话签发结果。 */
  openRuntime: openRuntimeSession,
  /** 撤销当前 v3 会话。@return 撤销成功结果，未启用 v3 时兼容旧部署。 */
  closeRuntime: () => request<{ ok: boolean }>('POST', '/runtime/logout'),
  /**
   * 加载账号分页和当前生效的画像配置。
   * @param page 页码。
   * @param pageSize 每页账号数。
   * @return 账号分页及画像配置；兼容旧后端缺少新增字段的响应。
   */
  /** 按身份读取账号供跨页直达。@param id 账号身份。@return 账号。 */
  accountById: (id: number) => request<Account>('GET', `/admin/accounts/${id}`),
  /** 局部切换 API 接单。@param id 账号。@param input 明确增量。@return 当前开关与收尾状态。 */
  updateAccountWork: (id: number, input: {api_accepting?: boolean; work_enabled?: boolean; expected_revision?: number}) => request<AccountWorkControl>('PUT', `/admin/accounts/${id}/work-control`, input),
  /** 读取整体协调进度。@param id 网关账号。@return API 与任务实际状态。 */
  overallWork: (id: number) => request<OverallWorkStatus>('GET', `/runtime/api/gateway-accounts/${id}/work-control`),
  /** 沿账号原关联协调整体启停。@param id 网关账号。@param enabled 目标。@return 实际收口状态。 */
  setOverallWork: (id: number, enabled: boolean) => request<OverallWorkStatus>('PUT', `/runtime/api/gateway-accounts/${id}/work-control`, {enabled}),
  listAccounts: (page = 1, pageSize = 12, query = '', status = '', signal?: AbortSignal, platform?: string) =>
    request<PagedResult<Account> & {
      account_counts?: {total:number;active:number;error:number;disabled:number}
      claude_code_profile_selection_mode?: 'client_version' | 'account'
      claude_code_version_profile?: string
    }>('GET', `/admin/accounts?page=${page}&page_size=${pageSize}&q=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}${platform ? `&platform=${encodeURIComponent(platform)}` : ''}`, undefined, signal),
  /** 获取只读调度快照。@param id 账号 ID。@param signal 关闭详情时取消读取。@return 当前状态与真实提交点。 */
  accountScheduling: (id: number, signal?: AbortSignal) =>
    request<SchedulingDetail>('GET', `/admin/accounts/${id}/scheduling`, undefined, signal),
  /** 分页读取匿名会话。@param id 账号。@param page 页码。@param state 活跃筛选。@param prefix 摘要前缀。@param signal 取消信号。@return 绑定分页。 */
  accountSchedulingSessions: (id: number, page: number, state = 'all', prefix = '', signal?: AbortSignal, pageSize = 20) =>
    request<SchedulingSessions>('GET', `/admin/accounts/${id}/scheduling/sessions?page=${page}&page_size=${pageSize}&state=${encodeURIComponent(state)}&prefix=${encodeURIComponent(prefix)}`, undefined, signal),
  createAccount: (a: Partial<Account>) => request<Account>('POST', '/admin/accounts', a),
  updateAccount: (id: number, a: Partial<Account>) => request<Account>('PUT', `/admin/accounts/${id}`, a),
  deleteAccount: (id: number) => request<void>('DELETE', `/admin/accounts/${id}`),
  testAccount: (id: number, signal?: AbortSignal) => request<{ status: string; message?: string }>('POST', `/admin/accounts/${id}/test`, undefined, signal),
  refreshUsage: (id: number) => request<{ status: string; usage?: UsageData; message?: string }>('POST', `/admin/accounts/${id}/usage`),
  listTokens: (page = 1, pageSize = 20) =>
    request<PagedResult<ApiToken>>('GET', `/admin/tokens?page=${page}&page_size=${pageSize}`),
  createToken: (t: Partial<ApiToken>) => request<ApiToken>('POST', '/admin/tokens', t),
  updateToken: (id: number, t: Partial<ApiToken>) => request<ApiToken>('PUT', `/admin/tokens/${id}`, t),
  deleteToken: (id: number) => request<void>('DELETE', `/admin/tokens/${id}`),
  getDashboard: () => request<Dashboard>('GET', '/admin/dashboard'),

  generateAuthUrl: (proxy?: { proxy_id?: string; proxy_revision?: string; proxy_url?: string; platform?:string; account_id?:number }, signal?: AbortSignal) =>
    request<OAuthGenerateResult>('POST', '/admin/oauth/generate-auth-url', proxy ?? {}, signal),
  /** 结束原授权进程。@param sessionId 原会话。@param platform 冻结平台。@return 脱敏阶段。 */
  cancelOAuth: (sessionId: string, platform: string) => request<{phase:string}>('POST', `/admin/oauth/${encodeURIComponent(sessionId)}/cancel?platform=${encodeURIComponent(platform)}`),
  /** 读取已有私有回执并对账。@param id 原账号。@return 管理状态。 */
  recoverAgyCredentials: (id:number) => request<{phase:string}>('POST', `/admin/accounts/${id}/agy-credentials/recover`),
  generateSetupTokenUrl: (proxy?: { proxy_id?: string; proxy_revision?: string; proxy_url?: string }, signal?: AbortSignal) =>
    request<OAuthGenerateResult>('POST', '/admin/oauth/generate-setup-token-url', proxy ?? {}, signal),
  exchangeCode: (sessionId: string, code: string, signal?: AbortSignal) =>
    request<OAuthExchangeResult>('POST', '/admin/oauth/exchange-code', { session_id: sessionId, code }, signal),
  exchangeSetupTokenCode: (sessionId: string, code: string, signal?: AbortSignal) =>
    request<OAuthExchangeResult>('POST', '/admin/oauth/exchange-setup-token-code', { session_id: sessionId, code }, signal),

  // 设置
  getSettings: (signal?: AbortSignal) => request<RawSettingsMap>('GET', '/admin/settings', undefined, signal).then(normalizeSettingsMap),
  updateSettings: (data: SettingsMap) => request<{ ok: boolean }>('PUT', '/admin/settings', data),

  // 峰值预热日志
  getPrimeLogs: () => request<PrimeLogEntry[]>('GET', '/admin/prime-logs'),
}
