/** 在网关交换的同源管理会话内访问编排服务。@param path 受控API路径。@param options 请求参数。@return 实际JSON回执。 */
export async function runtimeRequest<T>(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const response = await fetch(`/runtime/api${path}`, { method: options.method ?? 'GET', credentials: 'same-origin', cache: 'no-store', signal: options.signal,
    headers: options.body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: options.body === undefined ? undefined : JSON.stringify(options.body) });
  const value = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof value?.detail === 'string' ? value.detail : typeof value?.error === 'string' ? value.error : `操作失败（${response.status}）`);
  return value as T;
}

/** 账号当地运行窗口的服务端配置。 */
export interface RunWindowConfig { enabled: boolean; days: number[]; intervals: { start: string; end: string }[] }
/** 公开运行窗口。 */
export interface RunWindow { config: RunWindowConfig; timezone: string; message?: string; server_now?: number; next_open_at?: number | null; next_close_at?: number | null }
/** 冻结的资源配置及CAS版本。 */
export interface CpuResources { generation: number; revision: string; host_cpus: number; cpus: Record<'cli' | 'sender' | 'network', number> }
/** 采集及加速配置的共有版本；能力缺失保持未知。 */
export interface EnvironmentFeature {
  enabled?: boolean; applied?: boolean; supported?: boolean; generation: number; revision: string;
  state?: string; reason?: string | null; platform_enabled?: boolean; memory_mib?: number; required_memory_mib?: number;
  last_start_source?: string; tls_observer?: { state?: string; reason?: string | null };
}
/** 签名内核分发的公开身份。 */
export interface KernelReference { release: string; launcher_sha256: string }
/** 持久内核操作状态。 */
export interface EnvironmentKernel {
  state: string; revision: string; current?: KernelReference | null; prepared?: KernelReference | null;
  previous?: KernelReference | null; builtin?: KernelReference | null; error?: string | null; pid?: number;
  image_sha256?: string; warmup?: unknown;
}
/** 内核版本发现结果。 */
export interface KernelReleases { state: string; latest?: string; versions?: { release: string }[] }
/** 环境列表的真实公开投影，所有身份继续由服务端解释。 */
export interface RuntimeEnvironment {
  environment_id: string; name: string; account_id: number | null; gateway_account_id?: number | null;
  generation: number; state: string; busy: boolean; isolation_version?: number; identity_status?: string;
  fingerprint?: { tz?: string; mem?: string; hostname?: string; lang?: string; profile_version?: number };
  role_status?: Partial<Record<'cli' | 'sender' | 'network', string>>; cli_versions?: string[];
  can_reprofile?: boolean; reprofile_message?: string; run_window?: RunWindow | null;
  request_backend?: string; content_capture?: EnvironmentFeature | null; criu?: EnvironmentFeature | null;
  native_kernel?: EnvironmentKernel | null;
  native_preparation?: { state: string; reason?: string; checking?: boolean; idle_workers?: number; live_workers?: number; pid?: number; checked_at_ms?: number; adaptive_prewarm?: boolean } | null;
  credential_ownership?: { phase?: string; direction?: string; message?: string } | null;
  physical_features?: { message?: string; observed_at?: number; fields: { key: string; label: string; configured?: string | number | boolean | null; observed?: string | number | boolean | null; status: string }[] };
}
