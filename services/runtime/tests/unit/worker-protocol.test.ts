import { expect, test } from 'bun:test';
import { decodeWorkerCommand, decodeWorkerFrame, runtimeEvent } from '../../src/shared/protocol';
import { parseInput } from '../../src/shared/input';
import { prepareInput } from '../../src/control/header-policy';
import type { WorkerCommand, WorkerFrame } from '../../src/shared/contracts';
import { applyCachePolicy } from '../../src/shared/cache-policy';

const workerId = '11111111-1111-4111-8111-111111111111';
const restoredWorker = '22222222-2222-4222-8222-222222222222';
const templateId = '33333333-3333-4333-8333-333333333333';
const prepared = prepareInput(parseInput({ request_id: 'protocol-job', body: { model: 'fixture', messages: [{ role: 'user', content: '测试' }] } }));

test('恢复绑定严格核对模板、实例及挑战，拒绝额外控制字段', () => {
  const command: WorkerCommand = { schema_version: 2, type: 'worker_restore_bind', worker_id: workerId,
    template_id: templateId, new_worker_id: restoredWorker, nonce: 'a'.repeat(64) };
  expect(decodeWorkerCommand(command, workerId)).toEqual(command);
  for (const changes of [{ template_id: 'other' }, { new_worker_id: workerId }, { new_worker_id: 'invalid' },
    { nonce: 'a'.repeat(63) }, { nonce: 'A'.repeat(64) }, { pid: 1 }, { path: '/proc/1/mem' }]) {
    expect(() => decodeWorkerCommand({ ...command, ...changes }, workerId)).toThrow('恢复绑定');
  }
  expect(() => decodeWorkerCommand(command, restoredWorker)).toThrow('归属');
});

test('恢复后握手须声明已知能力与完整归属，保留旧内核兼容', () => {
  const ready: WorkerFrame = { schema_version: 2, type: 'worker_ready', worker_id: restoredWorker,
    version: '2.1.293', pid: 100, restore_protocol: 1,
    restore_binding: { template_id: templateId, nonce: 'a'.repeat(64), entropy_profile: 'bun143-wipeonfork-v1' } };
  expect(decodeWorkerFrame(JSON.stringify(ready), restoredWorker)).toEqual(ready);
  for (const changes of [{ restore_protocol: 2 }, { restore_protocol: undefined }, { restore_template: templateId },
    { restore_binding: {} }, { restore_binding: { ...ready.restore_binding, nonce: '' } },
    { restore_binding: { ...ready.restore_binding, entropy_profile: 'unknown' } },
    { restore_binding: { ...ready.restore_binding, token: 'unexpected' } }]) {
    expect(() => decodeWorkerFrame(JSON.stringify({ ...ready, ...changes }), restoredWorker)).toThrow('恢复');
  }
  const legacy: WorkerFrame = { schema_version: 2, type: 'worker_ready', worker_id: workerId, version: '2.1.293', pid: 10 };
  expect(decodeWorkerFrame(JSON.stringify(legacy), workerId)).toEqual(legacy);
});

test('原始输入协商与请求归属严格匹配，业务格式留给作业校验', () => {
  const input = { schema_version: 1, request_id: 'raw-job', body: null };
  const command: WorkerCommand = { schema_version: 2, type: 'request_input', worker_id: workerId, request_id: 'raw-job', input };
  expect(decodeWorkerCommand(command, workerId)).toEqual(command);
  for (const invalid of [null, { ...input, request_id: 'other' }, { ...input, schema_version: 2 }]) expect(() => decodeWorkerCommand({ ...command, input: invalid }, workerId)).toThrow('归属');
  const ready: WorkerFrame = { schema_version: 2, worker_id: workerId, type: 'worker_ready', version: '2.1.293', pid: 1, raw_input_protocol: 1 };
  expect(decodeWorkerFrame(JSON.stringify(ready), workerId)).toEqual(ready);
  for (const raw_input_protocol of [0, 2, '1', true]) expect(() => decodeWorkerFrame(JSON.stringify({ ...ready, raw_input_protocol }), workerId)).toThrow();
});

test('头部策略事件只传实际动作，拒绝畸形决策和秘密值载荷', () => {
  const frame: Extract<WorkerFrame, { type: 'request_event' }> = { schema_version: 2, worker_id: workerId, type: 'request_event', request_id: 'raw-job', payload: { type: 'header_policy', attempt: 1, decisions: [{ name: 'x-forwarded-for', action: 'drop', reason: '未登记' }] } };
  expect(decodeWorkerFrame(JSON.stringify(frame), workerId)).toEqual(frame);
  for (const decisions of [null, [{}], [{ name: 'x', action: 'unknown', reason: 'x' }], [{ name: 'x', action: 'keep', reason: 'x', value: 'synthetic-secret' }]]) expect(() => decodeWorkerFrame(JSON.stringify({ ...frame, payload: { ...frame.payload, decisions } }), workerId)).toThrow('格式');
});

test('缓存握手与诊断只能使用已知枚举及完整位置结构', () => {
  const ready: WorkerFrame = { schema_version: 2, worker_id: workerId, type: 'worker_ready', version: '2.1.293', pid: 1, cache_policy: 'sub2api' };
  expect(decodeWorkerFrame(JSON.stringify(ready), workerId)).toEqual(ready);
  expect(() => decodeWorkerFrame(JSON.stringify({ ...ready, cache_policy: 'unknown' }), workerId)).toThrow();
  const cache = applyCachePolicy({}, { messages: [{ role: 'user', content: 'x' }] }, 'sub2api').decision;
  const frame: Extract<WorkerFrame, { type: 'request_event' }> = { schema_version: 2, worker_id: workerId, type: 'request_event', request_id: 'protocol-job', payload: { type: 'cc_prepared', attempt: 1, body: '{}', headers: [], body_bytes: 2, body_sha256: 'a'.repeat(64), cache_policy: cache } };
  expect(decodeWorkerFrame(JSON.stringify(frame), workerId)).toEqual(frame);
  for (const invalid of [{ ...cache, ttl: ['1h'] }, { ...cache, selected: [{ message: 0 }] }, { ...cache, action: 'skipped' }]) expect(() => decodeWorkerFrame(JSON.stringify({ ...frame, payload: { ...frame.payload, cache_policy: invalid } }), workerId)).toThrow('格式');
});

test('遥测握手只接纳实际初始化结果，配置与状态必须对应', () => {
  const base = { schema_version: 2, worker_id: workerId, type: 'worker_ready', version: '2.1.293', pid: 1 };
  for (const telemetry of [{ policy: 'off', state: 'off' }, { policy: 'on', state: 'initialized' }, { policy: 'on', state: 'suppressed' }]) expect(decodeWorkerFrame(JSON.stringify({ ...base, telemetry }), workerId).type).toBe('worker_ready');
  for (const telemetry of [{ policy: 'off', state: 'initialized' }, { policy: 'on', state: 'pending' }, { policy: 'on', state: 'uploaded' }, { policy: true, state: 'initialized' }]) expect(() => decodeWorkerFrame(JSON.stringify({ ...base, telemetry }), workerId)).toThrow();
});

test('常驻协议同时校验进程与作业归属，不接纳旧协议握手', () => {
  const command: WorkerCommand = { schema_version: 2, type: 'request_start', worker_id: workerId, request_id: prepared.input.request_id, prepared };
  expect(decodeWorkerCommand(command, workerId)).toEqual(command);
  expect(() => decodeWorkerCommand({ ...command, worker_id: 'other' }, workerId)).toThrow('归属');
  expect(() => decodeWorkerCommand({ ...command, prepared: { ...prepared, input: { ...prepared.input, request_id: 'other' } } }, workerId)).toThrow('上下文');
  expect(() => decodeWorkerFrame(JSON.stringify({ schema_version: 1, type: 'ready', version: '2.1.293' }), workerId)).toThrow('归属');
  expect(() => decodeWorkerFrame(JSON.stringify({ schema_version: 2, worker_id: workerId, type: 'worker_ready', version: '2.1.293', pid: 0 }), workerId)).toThrow();
});

test('本地入站兼容策略在私有作业中有明确枚举且只属于原生输入', () => {
  const command = { schema_version: 2, type: 'request_start', worker_id: workerId, request_id: prepared.input.request_id, prepared };
  for (const policy of ['unknown', true, {}]) expect(() => decodeWorkerCommand({ ...command, prepared: { ...prepared, input: { ...prepared.input, inputFormat: 'claude_code', nativeIngressPolicy: policy } } }, workerId)).toThrow('策略');
  expect(() => decodeWorkerCommand({ ...command, prepared: { ...prepared, input: { ...prepared.input, nativeIngressPolicy: 'local_base_url' } } }, workerId)).toThrow('策略');
  for (const policy of ['strict', 'local_base_url']) expect(() => decodeWorkerCommand({ ...command, prepared: { ...prepared, input: { ...prepared.input, inputFormat: 'claude_code', nativeIngressPolicy: policy } } }, workerId)).not.toThrow();
});

test('包装事件继续严格验证原生载荷及单次发送，不接受请求内伪造握手', () => {
  const event: WorkerFrame = { schema_version: 2, type: 'request_event', worker_id: workerId, request_id: 'protocol-job', payload: { type: 'response_chunk', attempt: 1, data_b64: '5rWL6K+V' } };
  expect(decodeWorkerFrame(JSON.stringify(event), workerId)).toEqual(event);
  expect(() => decodeWorkerFrame(JSON.stringify({ ...event, payload: { ...event.payload, attempt: 2 } }), workerId)).toThrow('格式');
  expect(() => decodeWorkerFrame(JSON.stringify({ ...event, payload: { type: 'ready', version: '2.1.293' } }), workerId)).toThrow('握手');
  expect(() => decodeWorkerFrame(JSON.stringify({ ...event, payload: { ...event.payload, data_b64: 'invalid!' } }), workerId)).toThrow('格式');
  expect(() => decodeWorkerFrame(JSON.stringify({ ...event, payload: { ...event.payload, request_id: 'old-request' } }), workerId)).toThrow('归属');
  expect(() => decodeWorkerFrame(JSON.stringify({ ...event, payload: { ...event.payload, schema_version: 1 } }), workerId)).toThrow('归属');
  const payload = { type: 'completed' as const, attempt: 1, state: 'success' as const, schema_version: 2, request_id: 'old-request' };
  expect(runtimeEvent('current', payload).request_id).toBe('current');
  expect(runtimeEvent('current', payload).schema_version).toBe(1);
});

test('初始化错误帧只接纳有界配置说明，不允许混入业务归属或改变状态', () => {
  const frame: WorkerFrame = { type: 'worker_error', schema_version: 2, worker_id: workerId, code: 'native_configuration', status: 503, error: '专用 CLI 配置已拒绝当前显式密钥' };
  expect(decodeWorkerFrame(JSON.stringify(frame), workerId)).toEqual(frame);
  for (const fields of [{ worker_id: 'other' }, { status: 502 }, { code: 'runtime_exit' }, { request_id: 'injected' }, { error: '' }, { error: '测'.repeat(683) }]) {
    expect(() => decodeWorkerFrame(JSON.stringify({ ...frame, ...fields }), workerId)).toThrow();
  }
});

test('逐请求TTL仅通过受信私有指令传递，旧握手保持兼容', () => {
  const input = { schema_version: 1, request_id: 'ttl-job', body: { model: 'synthetic', messages: [{ role: 'user', content: 'x' }] } };
  const command = { schema_version: 2, worker_id: workerId, type: 'request_input', request_id: 'ttl-job', input };
  for (const mode of ['off', '5m', '1h']) expect(decodeWorkerCommand({ ...command, cache_ttl_rewrite: mode }, workerId).type).toBe('request_input');
  for (const mode of ['', '1H', 'auto', null, true]) expect(() => decodeWorkerCommand({ ...command, cache_ttl_rewrite: mode }, workerId)).toThrow('TTL');
  expect(() => parseInput({ ...input, cache_ttl_rewrite: '1h' })).toThrow('信封');
  const ready = { schema_version: 2, worker_id: workerId, type: 'worker_ready', version: '2.1.293', pid: 1 };
  expect(decodeWorkerFrame(JSON.stringify(ready), workerId).type).toBe('worker_ready');
  expect(decodeWorkerFrame(JSON.stringify({ ...ready, cache_ttl_rewrite_protocol: 1 }), workerId).type).toBe('worker_ready');
  expect(() => decodeWorkerFrame(JSON.stringify({ ...ready, cache_ttl_rewrite_protocol: 2 }), workerId)).toThrow();
});
