import type { CaptureRecord, HeaderDecision, RequestDetail, RequestRow } from './contracts';
import { isObject } from './errors';
import { isAgentAssociation, isAgentLaunches, isNativeClassificationContext } from './request-attribution';
import { isModelSelection } from './upstream';

function row(value: unknown): RequestRow {
  if (!isObject(value) || ['id', 'createdAt', 'model', 'requestClass', 'sessionId', 'promptId', 'state', 'mode', 'engine'].some(key => typeof value[key] !== 'string')) throw new Error('日志列表合同不匹配');
  for (const key of ['httpStatus', 'durationMs', 'headersMs', 'firstOutputMs']) if (value[key] !== null && typeof value[key] !== 'number') throw new Error('日志性能字段不匹配');
  if (value.agentLaunches !== undefined && !isAgentLaunches(value.agentLaunches)) throw new Error('代理启动证据合同不匹配');
  return value as unknown as RequestRow;
}

/** 解码列表响应，由 UI 统一消费字段。
 * @param value 查询返回的未知 JSON。
 * @return 已验证列表。
 */
export function decodeLogList(value: unknown): { rows: RequestRow[]; total: number } {
  if (!isObject(value) || !Array.isArray(value.rows) || typeof value.total !== 'number') throw new Error('日志列表响应不合法');
  return { rows: value.rows.map(row), total: value.total };
}

/** 解码详情，未知或损坏阶段不交给渲染器猜测。
 * @param value 详情 JSON。
 * @return 已验证详情。
 */
export function decodeLogDetail(value: unknown): RequestDetail {
  if (!isObject(value) || !Array.isArray(value.decisions) || !Array.isArray(value.captures) || (value.context !== null && !isObject(value.context))) throw new Error('日志详情响应不合法');
  const request = row(value.request);
  if (isObject(value.context) && value.context.inputFormat !== undefined && !['api', 'claude_code'].includes(String(value.context.inputFormat))) throw new Error('日志接入类型不合法');
  if (isObject(value.context) && value.context.classification !== undefined && !isNativeClassificationContext(value.context)) throw new Error('分类证据合同不匹配');
  if (isObject(value.context) && value.context.modelSelection !== undefined && (!isModelSelection(value.context.modelSelection) || value.context.modelSelection.effective !== request.model)) throw new Error('模型选择证据合同不匹配');
  if (value.agentAssociation !== undefined && !isAgentAssociation(value.agentAssociation)) throw new Error('代理关联视图合同不匹配');
  for (const decision of value.decisions) if (!isObject(decision) || typeof decision.name !== 'string' || typeof decision.reason !== 'string' || !['keep', 'drop', 'runtime', 'context'].includes(String(decision.action))) throw new Error('头部决策合同不匹配');
  for (const capture of value.captures) {
    if (!isObject(capture) || !['ingress', 'header_policy', 'cc_prepared', 'wire_final', 'upstream_response'].includes(String(capture.stage)) || typeof capture.source !== 'string' || typeof capture.status !== 'string' || typeof capture.observedBytes !== 'number' || !Array.isArray(capture.headers) || (capture.text !== null && typeof capture.text !== 'string')) throw new Error('采集阶段合同不匹配');
  }
  return { request, context: value.context as RequestDetail['context'], decisions: value.decisions as HeaderDecision[], captures: value.captures as CaptureRecord[],
    ...(value.agentAssociation === undefined ? {} : { agentAssociation: value.agentAssociation as RequestDetail['agentAssociation'] }),
  };
}
