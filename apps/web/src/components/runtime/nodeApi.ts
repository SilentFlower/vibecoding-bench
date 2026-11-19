import { runtimeRequest } from './runtimeApi';

/** 节点最近一次真实检查，资源缺失时保持未知。 */
export interface NodeObservation {
  state: 'reachable' | 'unreachable'; observed_at: number; stale: boolean; reason?: string;
  host_cpus?: number | null; docker_cpus?: number | null; docker_version?: string;
  memory?: { MemTotal: number; MemAvailable: number; SwapTotal: number; SwapFree: number };
  disk_available_bytes?: number; architecture?: string;
}
/** 中央提供的节点公开投影，SSH 认证材料仅存在于写入请求。 */
export interface ExecutionNode {
  id: number; node_key: string; name: string; kind: 'local' | 'ssh'; revision: number; enabled: boolean;
  account_count: number; host: string | null; port: number | null; username: string | null;
  data_root: string | null; host_key_sha256: string | null; observation: NodeObservation | null;
  auth_method?: 'private_key' | 'password' | null;
  preparation: { state: 'preparing' | 'prepared' | 'failed' | 'needs_check'; release?: string; protocol?: number; updated_at: number; reason?: string; phase?: string; current_release?: string | null; target_release?: string; retry_at?: number } | null;
}
/** 主机公钥候选，管理员通过可信渠道核对后选择。 */
export interface NodeHostKey { key: string; algorithm: string; sha256: string }
/** 账号人工归属的唯一公开合同，分配版本用于防止覆盖他人的修改。 */
export interface AccountNodeAssignment {
  account_id: number; node_id: number; node_key: string; node_name: string;
  kind: 'local' | 'ssh'; enabled: boolean; revision: number; phase: 'ready' | 'maintenance' | 'reconcile';
}
/** 账号列表的只读节点摘要，缓存观察与持久归属分别解释。 */
export interface AccountNodeSummary {
  id: number; cc2api_account_id?: number | null;
  node?: Omit<AccountNodeAssignment, 'account_id'> | null;
  node_observation?: Pick<NodeObservation, 'state' | 'stale' | 'observed_at'> | null;
}
/** 节点选择与迁移所需的任务账号投影。 */
export interface NodeTaskAccount {
  id: number; name: string; enabled: number; cc2api_account_id?: number | null;
  effective_claude_code_version?: string;
}
/** 人工迁移的公开阶段，内部收据和执行秘密由中央保管。 */
export interface NodeMigration {
  operation_id: string; account_id: number; source: { id: number; name: string }; target: { id: number; name: string };
  phase: 'requested' | 'draining' | 'source_fenced' | 'exporting' | 'importing' | 'verified' | 'committed' | 'completed' | 'cancelled' | 'reconcile';
  failure?: { code: string; stage: string; message: string; action: string } | null;
  last_confirmed_phase: string; message: string; running: boolean; can_resume: boolean; can_cancel: boolean;
  source_revision: number; target_revision: number | null; cancelling: boolean; created_at: number; updated_at: number;
}
/** 点击确认时冻结的唯一迁移范围。 */
export interface NodeMigrationStart { operation_id: string; node_id: number; revision: number; version: string }
/** 新节点登记的只写认证材料。 */
export type NodeRegistration = {
  name: string; host: string; port: number; username: string; data_root: string;
  host_key: string;
} & ({ auth_method?: 'private_key'; private_key: string; password?: never }
  | { auth_method: 'password'; password: string; private_key?: never });
/** 节点接口统一经过同源运行时会话桥。 */
export const nodeApi = {
  /** 读取账号迁移历史。@param id 任务账号。@param signal 取消读取。@return 公开列表。 */
  migrations: (id: number, signal?: AbortSignal) => runtimeRequest<{ items: NodeMigration[] }>(`/accounts/${id}/node-migrations`, { signal }),
  /** 读取原操作，未知提交使用同一ID核对。@param id 账号。@param operation 原操作。@param signal 取消。@return 公开状态。 */
  migration: (id: number, operation: string, signal?: AbortSignal) => runtimeRequest<NodeMigration>(`/accounts/${id}/node-migrations/${operation}`, { signal }),
  /** 启动已冻结人工迁移。@param id 账号。@param body 原分配和目标。@return 后台操作状态。 */
  migrate: (id: number, body: NodeMigrationStart) => runtimeRequest<NodeMigration>(`/accounts/${id}/node-migrations`, { method: 'POST', body }),
  /** 继续或取消原迁移。@param id 账号。@param operation 原操作。@param action 原阶段动作。@return 公开状态。 */
  migrationAction: (id: number, operation: string, action: 'resume' | 'cancel') => runtimeRequest<NodeMigration>(`/accounts/${id}/node-migrations/${operation}/${action}`, { method: 'POST' }),
  /** 读取账号归属。@param id 任务账号。@param signal 页面取消。@return 权威归属。 */
  assignment: (id: number, signal?: AbortSignal) => runtimeRequest<AccountNodeAssignment>(`/accounts/${id}/node`, { signal }),
  /** 人工选择首次执行节点。@param id 任务账号。@param nodeId 目标。@param revision 原分配版本。@return 持久归属。 */
  assignInitial: (id: number, nodeId: number, revision: number) => runtimeRequest<AccountNodeAssignment>(`/accounts/${id}/node`, { method: 'PUT', body: { node_id: nodeId, revision } }),
  /** 读取公开节点。@param signal 页面生命周期。@return 节点列表。 */
  list: (signal?: AbortSignal) => runtimeRequest<{ items: ExecutionNode[] }>('/nodes', { signal }),
  /** 探测未认证公钥。@param host SSH地址。@param port SSH端口。@param signal 取消。@return 待核对候选。 */
  hostKeys: (host: string, port: number, signal?: AbortSignal) => runtimeRequest<{ items: NodeHostKey[] }>('/nodes/host-keys', { method: 'POST', body: { host, port }, signal }),
  /** 登记已确认身份。@param body 配置与只写密钥。@return 公开节点。 */
  register: (body: NodeRegistration) => runtimeRequest<ExecutionNode>('/nodes', { method: 'POST', body }),
  /** 检查原配置。@param node 节点版本。@return 最新观测。 */
  check: (node: ExecutionNode) => runtimeRequest<ExecutionNode>(`/nodes/${node.id}/check`, { method: 'POST', body: { revision: node.revision } }),
  /** 后台同步全部节点到当前可信批次。@return 节点公开状态。 */
  synchronize: () => runtimeRequest<{ items: ExecutionNode[] }>('/nodes/synchronize', { method: 'POST', body: {} }),
  /** 安装同批执行组件。@param node 当前节点版本。@return 公开安装状态。 */
  prepare: (node: ExecutionNode) => runtimeRequest<ExecutionNode>(`/nodes/${node.id}/prepare`, { method: 'POST', body: { revision: node.revision } }),
  /** 更新新工作接纳。@param node 原节点。@param enabled 新状态。@return 新版本。 */
  enable: (node: ExecutionNode, enabled: boolean) => runtimeRequest<ExecutionNode>(`/nodes/${node.id}/enabled`, { method: 'PUT', body: { revision: node.revision, enabled } }),
  /** 归档无引用节点。@param node 节点版本。@return 完成回执。 */
  remove: (node: ExecutionNode) => runtimeRequest<{ ok: boolean }>(`/nodes/${node.id}`, { method: 'DELETE', body: { revision: node.revision } }),
};
