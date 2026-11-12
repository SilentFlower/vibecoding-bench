import { expect, test } from 'bun:test';
import { projectPoolIncident, poolIncidentCode, PoolIncidentError, type PoolIncidentEvidence } from '../../scripts/testing/local-pool-incidents';
import { incidentRow, incidentCapture, INCIDENT_STAGES, INCIDENT_TIME } from '../fixtures/pool-incidents';

/** 生成纯投影证据。 @return 不触发文件或模型访问的合成输入。 */
function evidence(): PoolIncidentEvidence {
  return { runId: 'test-run', requestId: 'request-a', request: incidentRow('request-a'), captures: INCIDENT_STAGES.map(stage => ({ stage, attempt: 1, value: incidentCapture(stage), bodyStorage: 'not_saved' })), ledgerState: 'matched', reservation: { requestId: 'request-a', reservedAt: INCIDENT_TIME, attempted: true, localStatus: 502, upstreamStatus: null, outcome: 'error', failureCode: 'UND_ERR_SOCKET', transportDiagnostics: { phase: 'awaiting_headers', bodySentObserved: true, connectionBytesWritten: 322, connectionBytesRead: 0 } } };
}

test('精确保留本地与上游状态、传输证据和零计数，不推断模型执行', () => {
  const report = projectPoolIncident(evidence());
  expect(report.forwarding).toMatchObject({ sourceState: 'matched', attempted: true, localStatus: 502, upstreamStatus: null, failureCode: 'UND_ERR_SOCKET' });
  expect(report.transport).toEqual({ phase: 'awaiting_headers', bodySentObserved: true, connectionBytesWritten: 322, connectionBytesRead: 0 });
  expect(report.interpretation.rootCause).toBe('unknown');
  expect(report.interpretation.transport).toContain('不证明池端');
  expect(report.captures.find(item => item.stage === 'wire_final')).toMatchObject({ source: 'local_pool_node_tls_receiver', recordedStatus: 'complete', bodyStorage: 'not_saved' });
});

test('字段白名单丢弃正文、凭据、地址、异常原文及额外嵌套载荷', () => {
  const input = evidence(), canary = 'untrusted-private-canary-192837';
  input.request = { ...incidentRow('request-a'), error: canary, context: canary, sessionId: canary, model: canary, captureError: canary };
  input.captures[3]!.value = { ...incidentCapture('wire_final'), text: canary, note: canary, headers: [['authorization', canary], ['x-client-request-id', 'client-observed-1'], ['x-private', canary]], extra: canary };
  input.reservation = { requestId: 'request-a', error: canary, apiKey: canary, url: canary, failureCode: canary, transportDiagnostics: { phase: 'sending', bodySentObserved: false, connectionBytesWritten: 0, connectionBytesRead: -1, socket: canary } };
  const report = projectPoolIncident(input), output = JSON.stringify(report);
  expect(output).not.toContain(canary); expect(output).not.toContain('authorization'); expect(output).not.toContain('x-private');
  expect(report.request.captureErrorPresent).toBe(true); expect(report.forwarding.failureCode).toBeNull();
  expect(report.transport).toEqual({ phase: 'sending', bodySentObserved: false, connectionBytesWritten: 0, connectionBytesRead: null });
  expect(report.correlations).toContainEqual(expect.objectContaining({ header: 'x-client-request-id', state: 'known', values: ['client-observed-1'], stage: 'wire_final' }));
});

test('旧账本和缺阶段保持未知，不能用本地状态补成池状态', () => {
  const input = evidence(); input.reservation = { requestId: 'request-a', localStatus: 502, upstreamStatus: null }; input.captures = [];
  const report = projectPoolIncident(input);
  expect(report.transport).toEqual({ phase: 'unknown', bodySentObserved: null, connectionBytesWritten: null, connectionBytesRead: null });
  expect(report.forwarding).toMatchObject({ attempted: null, upstreamStatus: null, failureCode: null, outcome: 'unknown' });
  expect(report.captures).toHaveLength(5); expect(report.captures.every(item => item.recordedStatus === 'unknown')).toBe(true);
  expect(report.evidenceGaps).toContain('CAPTURE_MISSING');
});

test('标识按同源同头去重与判冲突，代理标识没有证据时未知', () => {
  const input = evidence();
  input.captures[4]!.value = { ...incidentCapture('upstream_response'), headers: [['X-Oneapi-Request-Id', 'a'], ['x-oneapi-request-id', 'a'], ['x-oneapi-request-id', 'b'], ['x-ds-trace-id', 'other-source']] };
  const report = projectPoolIncident(input);
  expect(report.correlations).toContainEqual(expect.objectContaining({ header: 'x-oneapi-request-id', state: 'conflict', values: ['a', 'b'] }));
  expect(report.correlations).toContainEqual(expect.objectContaining({ header: 'x-ds-trace-id', state: 'known', values: ['other-source'] }));
  expect(report.correlations.at(-1)).toEqual({ stage: null, attempt: null, header: null, state: 'unknown', values: [], reason: 'proxy_not_captured' });
});

test('非法、脱敏、带控制符或超长标识不导出；中间头不补写最终头', () => {
  for (const value of ['[REDACTED]', 'bad\nvalue', 'x'.repeat(257), 'https://private.example/secret']) {
    const input = evidence(); input.captures[3]!.value = { ...incidentCapture('wire_final'), headers: [['x-client-request-id', value]] };
    input.captures[2]!.value = { ...incidentCapture('cc_prepared'), headers: [['x-client-request-id', 'intermediate-private']] };
    const report = projectPoolIncident(input);
    expect(report.correlations.find(item => item.header === 'x-client-request-id')).toMatchObject({ state: 'unknown', values: [], reason: 'invalid' });
    expect(JSON.stringify(report)).not.toContain('intermediate-private');
  }
});

test('来源损坏、时间非法及正文存储缺失与记录完整性分开', () => {
  const input = evidence(); input.request = { ...incidentRow('request-a'), createdAt: '2026-02-31T00:00:00.000Z', finishedAt: null };
  input.captures[3] = { stage: 'wire_final', attempt: 1, bodyStorage: 'missing', value: { ...incidentCapture('wire_final'), source: 'private-source', sha256: 'invalid' } };
  const report = projectPoolIncident(input);
  expect(report.request.createdAt).toBeNull(); expect(report.evidenceGaps).toContain('FINISH_NOT_OBSERVED');
  expect(report.evidenceGaps).toContain('CAPTURE_INVALID'); expect(report.evidenceGaps).toContain('BODY_MISSING');
  expect(report.captures.find(item => item.stage === 'wire_final')).toMatchObject({ source: 'unknown', sha256: null, recordedStatus: 'complete', bodyStorage: 'missing' });
});

test('重复预留不能任选一行，不存在预留不能解释成未执行', () => {
  const input = evidence(); input.ledgerState = 'conflict';
  let report = projectPoolIncident(input);
  expect(report.forwarding.attempted).toBeNull(); expect(report.evidenceGaps).toContain('RESERVATION_CONFLICT');
  input.ledgerState = 'missing'; report = projectPoolIncident(input);
  expect(report.forwarding.attempted).toBeNull(); expect(report.evidenceGaps).toContain('NO_RESERVATION');
});

test('摘要模式没有头值时明确未保存，不用中间头补齐标识', () => {
  const input = evidence(); input.request = { ...incidentRow('request-a'), mode: 'summary' };
  const report = projectPoolIncident(input);
  expect(report.request.mode).toBe('summary'); expect(report.evidenceGaps).toContain('HEADERS_NOT_SAVED');
  expect(report.correlations.filter(item => item.header !== null).every(item => item.state === 'unknown' && item.reason === 'not_saved')).toBe(true);
});

test('投影拒绝身份错配与非失败终态，错误分类不泄露任意异常', () => {
  const input = evidence(); input.request = incidentRow('other');
  expect(() => projectPoolIncident(input)).toThrow('SOURCE_INVALID');
  input.request = incidentRow('request-a', 'running'); expect(() => projectPoolIncident(input)).toThrow('REQUEST_NOT_TERMINAL');
  input.request = incidentRow('request-a', 'canceled'); expect(() => projectPoolIncident(input)).toThrow('REQUEST_NOT_TERMINAL');
  expect(poolIncidentCode(new Error('private-message'))).toBe('SOURCE_INVALID');
  expect(poolIncidentCode(new PoolIncidentError('RUN_MISMATCH'))).toBe('RUN_MISMATCH');
});
