/** 运行记录的实际只读字段，沿用编排服务契约。 */
export interface RuntimeRun {
  id: string; task_id: number; account_id: number; status: string; run_kind?: string;
  started_at?: number | null; ended_at?: number | null;
  exit_code: number | null; claude_code_version?: string; claude_effort_level?: string;
  execution_model?: string; capture_model_override?: string; prompt?: string; error?: string;
  quota_resume_at?: number; passive_quota?: { observed_at?: number };
  followups?: { phase?: string; messages?: string[]; mode?: string; offsets_sec?: number[]; items?: string[]; planned?: number; completed?: number; delivered?: number; consumed?: number };
}
/** 运行统计，未观测与真实零分别呈现。 */
export interface RunStats { available?: boolean; usage_available?: boolean; tokens_in?: number; tokens_out?: number; requests?: number; error?: string }
/** 服务端返回的产物元信息。 */
export interface RunFile { path: string; type?: string; size?: number }
/** 产物预览只返回有界文本，二进制保持独立状态。 */
export interface RunFilePreview { path: string; text: string | null; truncated: boolean; binary?: boolean; size?: number }
/** 公开抓包索引。原文由服务端保持私有。 */
export interface RunCapture {
  available?: boolean; message?: string; mode?: string; permission_mode?: string; model_override?: string;
  claude_code_version?: string; claude_effort_level?: string; files?: RunFile[];
  index?: { total_flows?: number; cc_versions?: string[]; entries?: { flow_id?: string; client_connection_id?: string; request?: { method?: string; host?: string; path?: string; body_bytes?: number }; response?: { status?: number; body_bytes?: number }; analysis?: { cc_version?: string }; capture_state?: string }[] };
  tls_clienthello?: { available?: boolean; message?: string; count_exact?: boolean; total_records?: number; scanned_records?: number; entries?: Record<string, unknown>[] };
}

/** 读取已有会话内的运行接口。@param id 身份。@param suffix 子资源。@param signal 取消信号。@return JSON投影。 */
export async function readRun<T>(id: string, suffix: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/runtime/api/runs/${encodeURIComponent(id)}${suffix}`, { credentials:'same-origin', cache:'no-store', signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `读取失败（${response.status}）`);
  }
  return response.json();
}
/** 读取有界日志尾部，避免每次轮询下载完整历史。@param id 身份。@param signal 取消信号。@return 文本及截断标记。 */
export async function readRunLog(id: string, signal: AbortSignal): Promise<{text: string; truncated: boolean}> {
  const response = await fetch(`/runtime/api/runs/${encodeURIComponent(id)}/transcript?tail_bytes=131072`, { credentials:'same-origin', cache:'no-store', signal });
  if (response.status === 404) return { text:'日志尚未生成', truncated:false };
  if (!response.ok) throw new Error(`日志读取失败（${response.status}）`);
  return { text:await response.text(), truncated:response.headers.get('x-log-truncated') === 'true' };
}

/** 读取当前可见运行或工程的公开抓包文件。@param base 宿主冻结的只读接口。@param path 清单路径。@param signal 取消信号。@return 脱敏JSON。 */
export async function readCaptureFile(base:string,path:string,signal:AbortSignal):Promise<unknown>{
  if(!/^\/runtime\/api\/(?:runs\/[A-Za-z0-9_-]+\/capture|(?:projects|accounts\/warmup\/pi)\/work\/[A-Za-z0-9_-]+\/capture\/file)$/.test(base))throw new Error('抓包来源无效');
  const response=await fetch(base+'?path='+encodeURIComponent(path),{credentials:'same-origin',cache:'no-store',signal});
  if(!response.ok){const value=await response.json().catch(()=>null);throw new Error(value?.detail||value?.error||`读取失败（${response.status}）`);}
  return response.json();
}
