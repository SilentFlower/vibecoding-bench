import { expect, test } from 'bun:test';
import type { NativeClassification, RequestClass, RequestDetail } from '../../src/shared/contracts';
import { decodeLogDetail, decodeLogList } from '../../src/shared/log-api';
import { prepareInput } from '../../src/control/header-policy';
import { parseInput } from '../../src/shared/input';
import { decodeRuntimeJob } from '../../src/shared/protocol';
import { classificationContext, isNativeClassification } from '../../src/shared/request-attribution';

/** 创建只用于边界解码的旧版详情。
 * @return 不含新字段的完整旧记录。
 */
function fixture(): RequestDetail {
  return { request: { id: 'fixture', createdAt: '2026-11-07T00:00:00Z', finishedAt: '2026-11-07T00:00:00Z', model: 'fixture', requestClass: 'subagent', sessionId: 'session', promptId: 'prompt', agentId: 'child', parentAgentId: null, state: 'success', httpStatus: 200, durationMs: 1, headersMs: 1, firstOutputMs: 1, mode: 'summary', engine: 'demo/fixture', binarySha256: null, error: null, captureError: null }, context: { requestClass: 'subagent', sessionId: 'session', promptId: 'prompt', agentId: 'child', agentKind: 'subagent', querySource: 'agent:custom', source: 'client' }, decisions: [], captures: [] };
}

test('旧日志保持可读，关联字段来源与空值必须一致', () => {
  const value = fixture(); expect(decodeLogDetail(value)).toEqual(value);
  value.agentAssociation = { state: 'linked', parentAgentId: 'parent', agentType: 'Explore', parentSource: 'client_tool_result', typeSource: 'client_tool_result', evidence: [{ requestId: 'evidence', toolUseId: 'toolu' }] };
  expect(decodeLogDetail(value)).toEqual(value);
  expect(() => decodeLogDetail({ ...value, agentAssociation: { ...value.agentAssociation, state: 'unknown' } })).toThrow('关联视图');
  value.agentAssociation.parentAgentId = null;
  expect(() => decodeLogDetail(value)).toThrow('关联视图');
  value.request.agentLaunches = { state: 'complete', links: [] };
  expect(decodeLogList({ rows: [value.request], total: 1 }).rows[0]?.agentLaunches).toEqual({ state: 'complete', links: [] });
  expect(() => decodeLogList({ rows: [{ ...value.request, agentLaunches: { state: 'complete', links: [{}] } }], total: 1 })).toThrow('启动证据');
});

test('模型选择字段保持旧记录兼容，未知来源和有效模型冲突拒绝', () => {
  const value = fixture();
  value.context!.modelSelection = { requested: 'incoming', effective: value.request.model, source: 'startup_override' };
  expect(decodeLogDetail(value).context?.modelSelection?.requested).toBe('incoming');
  expect(() => decodeLogDetail({ ...value, context: { ...value.context, modelSelection: { ...value.context!.modelSelection, source: 'request' } } })).toThrow('模型选择证据');
  expect(() => decodeLogDetail({ ...value, context: { ...value.context, modelSelection: { ...value.context!.modelSelection, effective: 'wrong' } } })).toThrow('模型选择证据');
});

test('分类用途须与auxiliary和auto_mode一致，私有作业不能只贴识别标签', () => {
  const value = fixture(), classification = { purpose: 'auto_permission_classifier' as const, source: 'native_profile' as const, profile: 'cc293-auto-mode-xml-s1' as const };
  value.context = { ...value.context!, inputFormat: 'claude_code', requestClass: 'auxiliary', querySource: 'auto_mode', classification };
  expect(decodeLogDetail(value).context?.classification).toEqual(classification);
  value.context.querySource = 'repl_main_thread';
  expect(() => decodeLogDetail(value)).toThrow('分类证据');
  const prepared = prepareInput(parseInput({ model: 'fixture', messages: [{ role: 'user', content: '离线' }] }));
  prepared.context.classification = classification;
  expect(() => decodeRuntimeJob({ type: 'request_start', schema_version: 1, request_id: prepared.input.request_id, prepared })).toThrow('分类证据');
});

test('三种用途的类别和官方来源在日志及私有作业中保持一致，混搭证据拒绝', () => {
  const cases: { classification: NativeClassification; requestClass: RequestClass; querySource: string }[] = [
    { classification: { purpose: 'auto_permission_classifier', source: 'native_profile', profile: 'cc293-auto-mode-xml-s2' }, requestClass: 'auxiliary', querySource: 'auto_mode' },
    { classification: { purpose: 'session_title', source: 'native_profile', profile: 'cc293-session-title-v1' }, requestClass: 'auxiliary', querySource: 'generate_session_title' },
    { classification: { purpose: 'compaction', source: 'native_profile', profile: 'cc293-compact-full-v1' }, requestClass: 'compaction', querySource: 'compact' },
  ];
  for (const item of cases) {
    expect(classificationContext(item.classification)).toEqual({ requestClass: item.requestClass, querySource: item.querySource });
    const value = fixture(), resolved = classificationContext(item.classification);
    value.context = { ...value.context!, inputFormat: 'claude_code', ...resolved, classification: item.classification };
    expect(decodeLogDetail(value).context?.classification).toEqual(item.classification);
    const prepared = prepareInput(parseInput({ model: 'fixture', messages: [{ role: 'user', content: '离线' }] }));
    prepared.input.inputFormat = 'claude_code'; prepared.context = value.context;
    const job = { type: 'request_start', schema_version: 1, request_id: prepared.input.request_id, prepared };
    expect(decodeRuntimeJob(job).prepared.context.classification).toEqual(item.classification);
    for (const change of [{ requestClass: 'main' }, { querySource: 'side_query' }, { inputFormat: 'api' }, { classification: { ...item.classification, profile: 'unknown' } }, { classification: { ...item.classification, source: 'bridge_default' } }]) {
      const context = { ...value.context, ...change };
      expect(() => decodeLogDetail({ ...value, context })).toThrow('分类证据');
      expect(() => decodeRuntimeJob({ ...job, prepared: { ...prepared, context } })).toThrow('分类证据');
    }
  }
  expect(isNativeClassification({ purpose: 'session_title', source: 'native_profile', profile: 'cc293-compact-full-v1' })).toBe(false);
  expect(isNativeClassification({ purpose: 'compaction', source: 'native_profile', profile: 'cc293-session-title-v1' })).toBe(false);
});
