import type { ProxyRoute } from '../../api';
import { runtimeRequest } from './runtimeApi';

/** 只包含目录公开字段，未知、直连与历史自定义分别呈现。 */
export interface TaskProxySummary {
  kind: 'directory' | 'custom' | 'direct' | 'unknown';
  id?: string; name: string; revision?: string; public_url: string;
  status: ProxyRoute['status']; observation: ProxyRoute['observation'];
  checked_at?: string | null; expires_at?: string | null;
}
/** 任务身份、当前关系与受控保存快照。 */
export interface TaskProxySelection { account_id: number; name: string; gateway_account_id: number | null; selection_revision: string; current: TaskProxySummary }
/** 读取单个任务的真实线路。@param id 任务ID。@param signal 读取生命周期。@return 选择快照。 */
export function readTaskProxy(id: number, signal: AbortSignal): Promise<TaskProxySelection> {
  return runtimeRequest(`/accounts/${id}/proxy-selection`, { signal });
}
/** 保存明确选择，仅传目录身份与原版本。@param snapshot 打开时快照。@param choice 用户选择。@param signal 界面生命周期。@return 当前公开快照。 */
export function saveTaskProxy(snapshot: TaskProxySelection, choice: ProxyRoute | null, signal: AbortSignal): Promise<TaskProxySelection> {
  return runtimeRequest(`/accounts/${snapshot.account_id}/proxy-selection`, { method: 'PUT', signal,
    body: { selection_revision: snapshot.selection_revision, proxy_id: choice?.id ?? null, ...(choice ? { proxy_revision: choice.revision } : {}) } });
}
