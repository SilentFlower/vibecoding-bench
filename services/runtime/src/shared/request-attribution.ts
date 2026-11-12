import type { AgentAssociation, AgentAssociationEvidence, AgentLaunches, AgentLaunchEvidence, NativeClassification, PreparedInput, RequestContext } from './contracts';
import { isObject } from './errors';

export const AGENT_EVIDENCE_LIMIT = 32;
const EVIDENCE_BYTES = 16384;
const ID = /^[A-Za-z0-9_-]{1,128}$/;
const LAUNCH_HEADER = 'Async agent launched successfully. (This tool result is internal metadata — never quote or paste any part of it, including the agentId below, into a user-facing reply.)';
const HANDBACK_PREFIX = 'This agent\'s report was delivered to you as a message from "';
const RESULT_TEXT_LIMIT = 1024;

function field(value: unknown): value is string { return typeof value === 'string' && value.trim().length > 0 && value.length <= 512 && !/[\0-\x1f\x7f]/.test(value) && [...value].every(c => c.charCodeAt(0) <= 255); }

/** 校验内部分类证据，避免 API 和私有进程分别解释字段。
 * @param value 未知分类元数据。
 * @return 是否为当前接纳的证据合同。
 */
export function isNativeClassification(value: unknown): value is NativeClassification {
  if (!isObject(value) || value.source !== 'native_profile') return false;
  switch (value.purpose) {
    case 'auto_permission_classifier': return ['cc293-auto-mode-xml-s1', 'cc293-auto-mode-xml-s2'].includes(String(value.profile));
    case 'session_title': return value.profile === 'cc293-session-title-v1';
    case 'compaction': return value.profile === 'cc293-compact-full-v1';
    default: return false;
  }
}

/** 将已验证用途映射到统一类别和官方来源，避免入口与解码边界各自维护规则。
 * @param classification 已验证的固定版本用途证据。
 * @return 对应请求类别和原生 querySource。
 */
export function classificationContext(classification: NativeClassification): Pick<RequestContext, 'requestClass' | 'querySource'> {
  switch (classification.purpose) {
    case 'auto_permission_classifier': return { requestClass: 'auxiliary', querySource: 'auto_mode' };
    case 'session_title': return { requestClass: 'auxiliary', querySource: 'generate_session_title' };
    case 'compaction': return { requestClass: 'compaction', querySource: 'compact' };
  }
}

/** 核对用途证据与上下文，私有协议和日志读取复用同一合同。
 * @param value 未知上下文；不据此验证上下文的其他字段。
 * @return 接入类型、用途、类别及来源是否一致。
 */
export function isNativeClassificationContext(value: unknown): boolean {
  if (!isObject(value) || value.inputFormat !== 'claude_code' || !isNativeClassification(value.classification)) return false;
  const expected = classificationContext(value.classification);
  return value.requestClass === expected.requestClass && value.querySource === expected.querySource;
}

/** 校验有界启动证据，旧记录或损坏数据不能当作空的完整结果。
 * @param value 未知持久字段。
 * @return 是否为可消费的启动证据。
 */
export function isAgentLaunches(value: unknown): value is AgentLaunches {
  return isObject(value) && ['complete', 'incomplete'].includes(String(value.state)) && Array.isArray(value.links) && value.links.length <= AGENT_EVIDENCE_LIMIT && value.links.every(link => isObject(link) && typeof link.childAgentId === 'string' && ID.test(link.childAgentId) && (link.parentAgentId === null || field(link.parentAgentId)) && (link.agentType === null || field(link.agentType)) && typeof link.toolUseId === 'string' && ID.test(link.toolUseId)) && new TextEncoder().encode(JSON.stringify(value)).length <= EVIDENCE_BYTES;
}

/** 校验只读关联视图，页面不解析原生工具文本。
 * @param value 未知详情字段。
 * @return 是否满足关联视图合同。
 */
export function isAgentAssociation(value: unknown): value is AgentAssociation {
  if (!isObject(value) || !['explicit', 'linked', 'unknown', 'conflict', 'incomplete'].includes(String(value.state)) || !(value.parentAgentId === null || field(value.parentAgentId)) || !(value.agentType === null || field(value.agentType)) || !['explicit', 'client_tool_result', 'unknown'].includes(String(value.parentSource)) || !['explicit', 'client_tool_result', 'unknown'].includes(String(value.typeSource)) || !Array.isArray(value.evidence) || value.evidence.length > AGENT_EVIDENCE_LIMIT || !value.evidence.every(e => isObject(e) && typeof e.requestId === 'string' && ID.test(e.requestId) && typeof e.toolUseId === 'string' && ID.test(e.toolUseId))) return false;
  if ((value.parentAgentId === null) !== (value.parentSource === 'unknown') || (value.agentType === null) !== (value.typeSource === 'unknown')) return false;
  if (value.state === 'explicit' && (value.parentSource !== 'explicit' || value.typeSource !== 'explicit')) return false;
  if (value.state === 'linked' && (!value.parentAgentId || !value.agentType || !value.evidence.length || value.parentSource !== 'client_tool_result' && value.typeSource !== 'client_tool_result')) return false;
  if (value.state === 'unknown' && value.parentAgentId !== null && value.agentType !== null) return false;
  return true;
}

/** 提取客户端声明的配对启动证据，不执行工具，也不修改准备好的上下文。
 * @param prepared 已解析请求。
 * @return 有界证据；损坏、重复或超限均显式不完整。
 */
export function collectAgentLaunches(prepared: PreparedInput): AgentLaunches {
  const result: AgentLaunches = { state: 'complete', links: [] };
  const uses = new Map<string, { name: string; agentType: string | null } | null>();
  const completed = new Set<string>();
  // 包括 JSON 容器、分隔符，并预留 complete 变为 incomplete 的长度差。
  let blocks = 0, bytes = new TextEncoder().encode(JSON.stringify(result)).length + 2;
  for (const message of prepared.input.body.messages) {
    if (!Array.isArray(message.content)) continue;
    for (const block of message.content) {
      if (++blocks > 4096) { result.state = 'incomplete'; return result; }
      if (message.role === 'assistant' && block.type === 'tool_use' && typeof block.id === 'string' && ID.test(block.id)) {
        if (uses.has(block.id)) { uses.set(block.id, null); result.state = 'incomplete'; continue; }
        uses.set(block.id, { name: typeof block.name === 'string' ? block.name : '', agentType: isObject(block.input) && field(block.input.subagent_type) ? block.input.subagent_type : null });
      }
      if (message.role !== 'user' || block.type !== 'tool_result' || (block.is_error !== undefined && block.is_error !== false) || typeof block.tool_use_id !== 'string') continue;
      const use = uses.get(block.tool_use_id);
      if (use?.name !== 'Agent') continue;
      if (!Array.isArray(block.content)) { result.state = 'incomplete'; continue; }
      if (completed.has(block.tool_use_id)) { result.state = 'incomplete'; continue; }
      completed.add(block.tool_use_id);
      blocks += block.content.length;
      if (blocks > 4096) { result.state = 'incomplete'; return result; }
      // 前台交付说明是固定短句，不扫描报告正文猜身份；未知、混合或重复元数据仍明确不完整。
      const texts = block.content.filter(isObject).filter(b => {
        if (b.type !== 'text' || typeof b.text !== 'string') return false;
        return b.text.startsWith(LAUNCH_HEADER + '\n') || b.text.length <= RESULT_TEXT_LIMIT && b.text.trimStart().startsWith(HANDBACK_PREFIX);
      });
      if (texts.length !== 1) { result.state = 'incomplete'; continue; }
      const text = texts[0]!.text as string;
      const match = text.startsWith(LAUNCH_HEADER + '\n')
        ? /^agentId: ([A-Za-z0-9_-]{1,128}) \(internal ID - do not mention to user\.(?:\)| Use )/.exec(text.slice(LAUNCH_HEADER.length + 1, LAUNCH_HEADER.length + RESULT_TEXT_LIMIT))
        : /^This agent's report was delivered to you as a message from "([A-Za-z0-9_-]{1,128})" \(its SubagentHandback call\)(?:, under a SECURITY WARNING from auto mode — the warning above the report says why)?\. Read it there; it is not repeated here\.$/.exec(text.trim());
      if (!match) { result.state = 'incomplete'; continue; }
      const parentAgentId = prepared.context.agentId ?? null;
      if (parentAgentId === match[1]) { result.state = 'incomplete'; continue; }
      const link: AgentLaunchEvidence = { childAgentId: match[1]!, parentAgentId, agentType: use.agentType, toolUseId: block.tool_use_id };
      bytes += new TextEncoder().encode(JSON.stringify(link)).length + (result.links.length ? 1 : 0);
      if (result.links.length >= AGENT_EVIDENCE_LIMIT || bytes > EVIDENCE_BYTES) { result.state = 'incomplete'; return result; }
      result.links.push(link);
    }
  }
  return result;
}

/** 合并显式关联与仍在保留期内的证据，不任意选择冲突值。
 * @param context 发生时的上下文。
 * @param candidates 已按会话和子代理 ID 查询的声明。
 * @param incomplete 查询、提取或采集是否存在缺口。
 * @return 不改写原快照的有效关联视图。
 */
export function resolveAgentAssociation(context: RequestContext, candidates: (AgentLaunchEvidence & AgentAssociationEvidence)[], incomplete: boolean): AgentAssociation {
  const parents = new Set(candidates.map(c => c.parentAgentId).filter((v): v is string => v !== null));
  const types = new Set(candidates.map(c => c.agentType).filter((v): v is string => v !== null));
  const choose = (explicit: string | undefined, values: Set<string>): string | null => explicit ?? (!incomplete && values.size === 1 ? [...values][0]! : null);
  const parentAgentId = choose(context.parentAgentId, parents), agentType = choose(context.agentType, types);
  const conflict = parents.size > 1 || types.size > 1 || !!context.parentAgentId && [...parents].some(p => p !== context.parentAgentId) || !!context.agentType && [...types].some(t => t !== context.agentType);
  const evidence = [...new Map(candidates.map(c => [c.requestId + '/' + c.toolUseId, { requestId: c.requestId, toolUseId: c.toolUseId }])).values()].slice(0, AGENT_EVIDENCE_LIMIT);
  return {
    state: conflict ? 'conflict' : incomplete ? 'incomplete' : !parentAgentId || !agentType ? 'unknown' : context.parentAgentId && context.agentType ? 'explicit' : 'linked',
    parentAgentId, agentType,
    parentSource: context.parentAgentId ? 'explicit' : parentAgentId ? 'client_tool_result' : 'unknown',
    typeSource: context.agentType ? 'explicit' : agentType ? 'client_tool_result' : 'unknown', evidence,
  };
}
