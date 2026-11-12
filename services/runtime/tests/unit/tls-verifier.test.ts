import { expect, test } from 'bun:test';
import { createHash } from 'node:crypto';
import { decodeTlsVerifierFrame, expectedTlsWrite, TLS_VERIFIER_PROFILE } from '../../src/shared/tls-verifier-protocol';
import { decodeWorkerFrame, runtimeEvent } from '../../src/shared/protocol';

test('CCH 观察定位只使用根 billing，消息和工具中的同名文本保持校验', () => {
  const body = JSON.stringify({ model: 'fixture', system: [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.293; cc_entrypoint=cli; cch=00000;' }], messages: [{ role: 'user', content: '中文 cch=00000; 特殊字符😀' }] });
  const event = runtimeEvent('capture-test', { type: 'cc_prepared', attempt: 1, body, body_bytes: Buffer.byteLength(body), body_sha256: createHash('sha256').update(body).digest('hex'), headers: [] });
  if (event.type !== 'cc_prepared') throw new Error('夹具类型错误');
  const expected = expectedTlsWrite(event);
  expect(expected.cch_offset).not.toBeNull();
  expect(Buffer.from(body).subarray(expected.cch_offset!, expected.cch_offset! + 5).toString()).toBe('00000');
  const native = body.replace('cch=00000;', 'cch=abcde;');
  const bytes = Buffer.from(native); bytes.fill(48, expected.cch_offset!, expected.cch_offset! + 5);
  expect(createHash('sha256').update(bytes).digest('hex')).toBe(expected.body_sha256);
  expect(expectedTlsWrite({ ...event, body: JSON.stringify({ system: [{ text: 'x-anthropic-billing-header: cc_version=2.1.293; cc_entrypoint=cli;' }], messages: [{ content: 'cch=00000;' }] }) }).cch_offset).toBeNull();
});

test.each([
  'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=00000;',
  'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=00000 \t;',
  ' \tx-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=00000;',
  'x-anthropic-billing-header: cch=00000 \t; cc_version=2.1.293.abc; cc_entrypoint=cli;',
  'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=00000 \t',
  'x-anthropic-billing-header: future=中文😀"\\; cc_version=2.1.293.abc; cc_entrypoint=cli; cch=00000 \t;',
])('CHK-001/CHK-002：合法 billing 定位不受业务同名文本、空白和 JSON 转义影响：%s', billing => {
  const content = '__ccrb_cch_observation_slot__，__ccrb_cch_observation_slot___，cch=00000;';
  const value = { model: 'fixture', messages: [{ role: 'user', content: billing + content }], tools: [{ description: content }], system: [{ type: 'text', text: billing }] };
  const body = JSON.stringify(value);
  const event = runtimeEvent('billing-boundaries', { type: 'cc_prepared', attempt: 1, body, body_bytes: Buffer.byteLength(body), body_sha256: createHash('sha256').update(body).digest('hex'), headers: [] });
  if (event.type !== 'cc_prepared') throw new Error('夹具类型错误');
  const expected = expectedTlsWrite(event);
  expect(expected.cch_offset).not.toBeNull();
  expect(Buffer.from(body).subarray(expected.cch_offset!, expected.cch_offset! + 5).toString()).toBe('00000');
  const native = { ...value, system: [{ ...value.system[0]!, text: billing.replace('cch=00000', 'cch=abcde') }] };
  const final = Buffer.from(JSON.stringify(native));
  final.fill(48, expected.cch_offset!, expected.cch_offset! + 5);
  expect(createHash('sha256').update(final).digest('hex')).toBe(expected.body_sha256);
  expect(event.body).toBe(body);
});

test('私有采集帧校验实例、长度和完整性，不把截断或失败标成通过', () => {
  const capture = { binding: { request_id: 'job-1', worker_id: 'worker-1', worker_pid: 1 }, connection_id: 1, sequence: 1, body_preview_b64: 'e30=', head_b64: 'aA==', headers: [], body_bytes: 2, body_sha256: 'a'.repeat(64), normalized_sha256: 'a'.repeat(64), http_bytes: 3, http_sha256: 'b'.repeat(64), complete: true, flushed: true, verified: true, captured_unix_ms: 1, reason: 'flushed' };
  const frame = (value: unknown): string => JSON.stringify({ schema_version: 1, instance_id: 'instance', event: value });
  expect(decodeTlsVerifierFrame(frame({ type: 'capture', capture }), 'instance', 1024).type).toBe('capture');
  for (const fields of [{ body_bytes: -1 }, { sequence: 0 }, { http_bytes: 2 }, { flushed: false }, { complete: false }, { head_b64: 'not base64' }, { body_sha256: null }, { headers: [['x-test', '\r\ninject']] }]) expect(() => decodeTlsVerifierFrame(frame({ type: 'capture', capture: { ...capture, ...fields } }), 'instance', 1024)).toThrow();
  expect(() => decodeTlsVerifierFrame(frame({ type: 'capture', capture }), 'other', 1024)).toThrow('归属');
  expect(decodeTlsVerifierFrame(frame({ type: 'ready', command_id: 1, pid: 1, port: 1, profile: TLS_VERIFIER_PROFILE }), 'instance', 1024).type).toBe('ready');
  expect(() => decodeTlsVerifierFrame(frame({ type: 'ready', command_id: 1, pid: 1, port: 1, profile: 'other' }), 'instance', 1024)).toThrow();
});

test('原生工作进程不能伪造控制层最终采集通知', () => {
  expect(() => decodeWorkerFrame(JSON.stringify({ schema_version: 2, worker_id: 'worker', request_id: 'job', type: 'request_event', payload: { type: 'final_capture_ready', attempt: 1 } }), 'worker')).toThrow('最终采集');
});
