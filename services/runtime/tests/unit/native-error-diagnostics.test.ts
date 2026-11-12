import { expect, test } from 'bun:test';
import { readFile } from 'node:fs/promises';
import { NATIVE_ERROR_CODES, NATIVE_ERROR_NAMES, NATIVE_ERROR_STAGES, isNativeErrorDiagnostics, nativeErrorDiagnostics } from '../../src/shared/native-error-diagnostics';
import { decodeRuntimeEvent, decodeWorkerFrame, runtimeEvent } from '../../src/shared/protocol';
import { BridgeError } from '../../src/shared/errors';
import type { WorkerFrame } from '../../src/shared/contracts';
import { decodeLocalDriverFrame } from '../../scripts/testing/local-pool-protocol';

const workerId = '11111111-1111-4111-8111-111111111111';
const secret = 'synthetic-private-secret@example.test';

test('类型化 cause 只保留阶段和受控字段，忽略任意异常正文', () => {
  const cause = Object.assign(new Error('Bearer ' + secret), { code: 'ECONNRESET', url: 'https://private.test/' + secret });
  const error = new TypeError(secret, { cause });
  expect(nativeErrorDiagnostics(error, 'dispatch')).toEqual({ schema_version: 1, stage: 'dispatch', causes: [
    { name: 'TypeError', code: 'unknown' }, { name: 'Error', code: 'ECONNRESET' },
  ], chain_truncated: false, cycle_detected: false, inspection_failed: false });
  expect(JSON.stringify(nativeErrorDiagnostics(error, 'dispatch'))).not.toContain(secret);
  const unknown = Object.assign(new Error(secret), { name: secret, code: secret });
  expect(nativeErrorDiagnostics(unknown, 'construction').causes).toEqual([{ name: 'unknown', code: 'unknown' }]);
  expect(nativeErrorDiagnostics(new BridgeError('unsupported_parameter', secret, 422), 'construction').causes[0]).toEqual({ name: 'BridgeError', code: 'unsupported_parameter' });
});

test('未知抛出值、恶意 getter 和撤销代理保持安全且有界', () => {
  const hostile = Object.defineProperties({}, Object.fromEntries(['name', 'code', 'cause'].map(key => [key, { get() { throw new Error(secret); } }])));
  const revoked = Proxy.revocable({}, {}); revoked.revoke();
  for (const value of [hostile, revoked.proxy]) {
    const result = nativeErrorDiagnostics(value, 'input');
    expect(result.inspection_failed).toBe(true);
    expect(result.causes).toEqual([{ name: 'unknown', code: 'unknown' }]);
    expect(isNativeErrorDiagnostics(result)).toBe(true);
    expect(JSON.stringify(result)).not.toContain(secret);
  }
  for (const value of [null, undefined, secret, 42, Symbol(secret)]) {
    expect(nativeErrorDiagnostics(value, 'context').causes).toEqual([{ name: 'unknown', code: 'unknown' }]);
  }
  const messageTrap = Object.defineProperty(new Error(), 'message', { get() { throw new Error(secret); } });
  expect(nativeErrorDiagnostics(messageTrap, 'dispatch').inspection_failed).toBe(false);
});

test('cause 环与超过八层明确标记，正好八层不误标截断', () => {
  const cycle: { name: string; cause?: unknown } = { name: 'Error' }; cycle.cause = cycle;
  expect(nativeErrorDiagnostics(cycle, 'response_body')).toMatchObject({ cycle_detected: true, chain_truncated: false, causes: [{ name: 'Error', code: 'unknown' }] });
  let error = new Error(secret);
  for (let i = 0; i < 7; i++) error = new Error(secret, { cause: error });
  expect(nativeErrorDiagnostics(error, 'dispatch')).toMatchObject({ chain_truncated: false, cycle_detected: false });
  error = new Error(secret, { cause: error });
  const result = nativeErrorDiagnostics(error, 'dispatch');
  expect(result.causes).toHaveLength(8); expect(result.chain_truncated).toBe(true);
});

test('本地实际 fetch 超时保留受控 TimeoutError，消息保持私有', async () => {
  let release: (() => void) | undefined;
  const server = Bun.serve({ hostname: '127.0.0.1', port: 0, fetch: () => new Promise<Response>(resolve => { release = () => resolve(new Response('合成响应')); }) });
  try {
    const error = await fetch('http://127.0.0.1:' + server.port + '/?secret=' + secret, { signal: AbortSignal.timeout(15) }).then(() => { throw new Error('夹具应超时'); }, error => error);
    const diagnostics = nativeErrorDiagnostics(error, 'dispatch');
    expect(diagnostics.causes[0]?.name).toBe('TimeoutError');
    expect(JSON.stringify(diagnostics)).not.toContain(secret);
  } finally { release?.(); await server.stop(true); }
});

test('共享夹具同时固定 TypeScript 和 Rust 的诊断目录及事件结构', async () => {
  const fixture = JSON.parse(await readFile(new URL('../../../gateway/tests/fixtures/native-error-diagnostics.json', import.meta.url), 'utf8'));
  expect(fixture.stages).toEqual([...NATIVE_ERROR_STAGES]);
  expect(fixture.names).toEqual([...NATIVE_ERROR_NAMES]);
  expect(fixture.codes).toEqual([...NATIVE_ERROR_CODES]);
  const actual = nativeErrorDiagnostics(new TypeError(secret, { cause: Object.assign(new Error(secret), { code: 'ECONNRESET' }) }), 'dispatch');
  expect(actual).toEqual(fixture.diagnostics);
  const frame: Extract<WorkerFrame, { type: 'request_event' }> = { schema_version: 2, type: 'request_event', worker_id: workerId, request_id: 'diagnostic-job', payload: { type: 'error', error: '私有错误说明', code: 'unsupported_parameter', status: 422, diagnostics: actual } };
  expect(decodeWorkerFrame(JSON.stringify(frame), workerId)).toEqual(frame);
  expect(decodeWorkerFrame(JSON.stringify({ ...frame, payload: { type: 'error', error: '旧内核' } }), workerId).type).toBe('request_event');
  for (const diagnostics of [null, {}, { ...actual, schema_version: 2 }, { ...actual, message: secret }, { ...actual, stage: secret }, { ...actual, causes: [] }, { ...actual, causes: Array(9).fill(actual.causes[0]) }, { ...actual, causes: [{ name: 'Error', code: secret }] }, { ...actual, causes: [{ name: 'Error', code: 'unknown', stack: secret }] }]) {
    expect(isNativeErrorDiagnostics(diagnostics)).toBe(false);
    const decoded = decodeWorkerFrame(JSON.stringify({ ...frame, payload: { ...frame.payload, diagnostics, extra: secret } }), workerId);
    if (decoded.type !== 'request_event') throw new Error('缺少请求事件');
    expect(decoded.payload).toEqual({ type: 'error', error: '私有错误说明', code: 'unsupported_parameter', status: 422, diagnostics_state: 'invalid' });
    expect(JSON.stringify(decoded)).not.toContain(secret);
    const event = runtimeEvent(frame.request_id, decoded.payload);
    expect(decodeRuntimeEvent(JSON.stringify(event), frame.request_id)).toEqual(event);
    const driver = decodeLocalDriverFrame(JSON.stringify({ type: 'event', workerPid: 1, event: { ...frame.payload, diagnostics, extra: secret, schema_version: 1, request_id: frame.request_id } }));
    if (driver.type !== 'event') throw new Error('缺少驱动事件');
    expect(driver.event).toEqual(event);
    expect(JSON.stringify(driver)).not.toContain(secret);
    expect(() => decodeRuntimeEvent(JSON.stringify(event), 'other-request')).toThrow('匹配');
  }
  expect(() => decodeWorkerFrame(JSON.stringify({ ...frame, worker_id: 'other' }), workerId)).toThrow('归属');
  for (const status of [399, 600, '422']) expect(() => decodeWorkerFrame(JSON.stringify({ ...frame, payload: { type: 'error', error: '合成错误', status, diagnostics: null } }), workerId)).toThrow('格式');
});
