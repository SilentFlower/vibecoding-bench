import { afterEach, beforeEach, expect, test } from 'bun:test';
import type { JsonObject } from '../../src/shared/contracts';
import { readTelemetryPolicy, isTelemetryHandshake } from '../../src/shared/runtime-policy';
import { createNativeTelemetry } from '../../src/runtime/293/telemetry';
import { readConfig } from '../../src/control/server';
import { NativeEngine, createEngine } from '../../src/control/engine';

const keys = ['DISABLE_TELEMETRY', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', 'DO_NOT_TRACK', 'DISABLE_AUTOUPDATER', 'DISABLE_ERROR_REPORTING', 'DISABLE_GROWTHBOOK'];
let saved: Record<string, string | undefined>;
beforeEach(() => { saved = Object.fromEntries(keys.map(key => [key, process.env[key]])); });
afterEach(() => { for (const key of keys) { if (saved[key] === undefined) delete process.env[key]; else process.env[key] = saved[key]; } });

function fixture() {
  const calls = { init: 0, network: 0, settle: 0, shutdown: 0, records: [] as { name: string; metadata: JsonObject | undefined }[] };
  let sink!: Parameters<Parameters<typeof createNativeTelemetry>[0]['analytics']['G_o']>[0];
  const bindings: Parameters<typeof createNativeTelemetry>[0] = {
    analytics: { G_o(value) { sink = value; } },
    network: { Jb() { calls.network++; } },
    context: {
      a4: () => true, SLe() { calls.init++; },
      async MDs() { calls.settle++; }, async bLe() { calls.shutdown++; },
      async Jk(name, metadata) { calls.records.push({ name, metadata }); },
      gyr: () => null, Yus: metadata => ({ ...metadata, native_filtered: true }),
      Nco: () => true, w9t: async () => {}, gDn: model => model, tt: () => 'fixture-model',
    },
  };
  return { calls, bindings, sink: () => sink };
}

test('遥测配置默认关闭，各入口拒绝非法值，握手不能伪造上传状态', async () => {
  expect(readTelemetryPolicy(undefined)).toBe('off');
  expect(readConfig({}).engine.telemetryPolicy).toBe('off');
  expect(readConfig({ CCRB_TELEMETRY: 'on' }).engine.telemetryPolicy).toBe('on');
  const config = readConfig({ CCRB_MODE: 'demo' }).engine;
  for (const value of ['', 'true', 'ON', true, null]) {
    expect(() => readTelemetryPolicy(value)).toThrow('CCRB_TELEMETRY');
    const invalid = { ...config, telemetryPolicy: value } as unknown as typeof config;
    expect(() => new NativeEngine(invalid)).toThrow('CCRB_TELEMETRY');
    await expect(createEngine(invalid)).rejects.toThrow('CCRB_TELEMETRY');
  }
  for (const invalid of [{ policy: 'on', state: 'pending' }, { policy: 'off', state: 'initialized' }, { policy: 'on', state: 'uploaded' }]) expect(isTelemetryHandshake(invalid)).toBe(false);
});

test('关闭时不初始化、不采集或退出上传', async () => {
  const mock = fixture();
  const telemetry = createNativeTelemetry(mock.bindings, 'off', () => true);
  expect(telemetry.start()).toEqual({ policy: 'off', state: 'off' });
  await mock.sink().logEventAsync('tengu_fixture', { input: 'synthetic' });
  await telemetry.close();
  expect(mock.calls).toEqual({ init: 0, network: 0, settle: 0, shutdown: 0, records: [] });
  for (const key of keys) expect(process.env[key]).toBe('1');
});

test('开启后只采集活跃业务，沿用原生采样与脱敏并保持其他通道关闭', async () => {
  const mock = fixture();
  let business = false;
  const telemetry = createNativeTelemetry(mock.bindings, 'on', () => business);
  mock.sink().logEvent('bootstrap', {});
  expect(telemetry.start()).toEqual({ policy: 'on', state: 'initialized' });
  expect(mock.calls.network).toBe(1);
  mock.sink().logEvent('outside', {});
  business = true;
  mock.sink().logEvent('tengu_fixture', { source: 'business' });
  business = false;
  mock.sink().logEvent('late', {});
  await telemetry.close();
  expect(mock.calls.records).toEqual([{ name: 'tengu_fixture', metadata: { source: 'business', native_filtered: true } }]);
  expect(mock.calls.settle).toBe(1); expect(mock.calls.shutdown).toBe(1);
  for (const key of keys.slice(0, 3)) expect(process.env[key]).toBeUndefined();
  for (const key of keys.slice(3)) expect(process.env[key]).toBe('1');
});

test('尊重官方策略抑制与零采样，初始化异常只返回受控说明', async () => {
  const denied = fixture(); denied.bindings.context.a4 = () => false;
  const suppressed = createNativeTelemetry(denied.bindings, 'on', () => true);
  expect(suppressed.start()).toEqual({ policy: 'on', state: 'suppressed' });
  await denied.sink().logEventAsync('tengu_fixture');
  await suppressed.close();
  expect(denied.calls.network).toBe(0); expect(denied.calls.records).toHaveLength(0);
  expect(process.env.DISABLE_TELEMETRY).toBe('1');
  const sampled = fixture(); sampled.bindings.context.gyr = () => 0;
  const telemetry = createNativeTelemetry(sampled.bindings, 'on', () => true);
  telemetry.start(); await sampled.sink().logEventAsync('sampled'); await telemetry.close();
  expect(sampled.calls.records).toHaveLength(0);
  const failed = fixture(); failed.bindings.context.SLe = () => { throw new Error('private-secret-canary'); };
  const invalid = createNativeTelemetry(failed.bindings, 'on', () => true);
  expect(() => invalid.start()).toThrow('无法初始化固定运行时的第一方遥测');
});

test('可等待事件也不阻塞业务，退出会等待已经开始的原生采集', async () => {
  const mock = fixture();
  let release!: () => void;
  let completed = false;
  mock.bindings.context.Jk = () => new Promise<void>(resolve => { release = () => { completed = true; resolve(); }; });
  const telemetry = createNativeTelemetry(mock.bindings, 'on', () => true);
  telemetry.start();
  await mock.sink().logEventAsync('background');
  expect(completed).toBe(false);
  const closing = telemetry.close();
  expect(mock.calls.shutdown).toBe(0);
  release(); await closing;
  expect(mock.calls.shutdown).toBe(1);
});

test('原生元数据同步记录嵌套事件时沿用官方重入保护', async () => {
  const mock = fixture();
  let entered = false;
  mock.bindings.context.Yus = metadata => {
    if (!entered) { entered = true; mock.sink().logEvent('nested'); }
    return metadata;
  };
  const telemetry = createNativeTelemetry(mock.bindings, 'on', () => true);
  telemetry.start(); await mock.sink().logEventAsync('outer'); await telemetry.close();
  expect(mock.calls.records.map(record => record.name)).toEqual(['outer']);
});

test('模型脱敏目录尚未就绪时在后台等待，完成后才生成原生事件', async () => {
  const mock = fixture();
  let release!: () => void;
  let hydrated = false;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  mock.bindings.context.Nco = () => false;
  mock.bindings.context.w9t = async () => { await waiting; hydrated = true; };
  mock.bindings.context.Yus = metadata => { expect(hydrated).toBe(true); return { ...metadata, model: 'native-masked' }; };
  const telemetry = createNativeTelemetry(mock.bindings, 'on', () => true);
  telemetry.start(); await mock.sink().logEventAsync('catalog', { model: 'private-alias' });
  expect(mock.calls.records).toHaveLength(0);
  release(); await telemetry.close();
  expect(mock.calls.records[0]!.metadata!.model).toBe('native-masked');
});

test('正在采集的原生任务有界，错误不影响业务且关闭后不再采集', async () => {
  const mock = fixture();
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  let starts = 0;
  mock.bindings.context.Jk = async () => { starts++; await waiting; };
  const telemetry = createNativeTelemetry(mock.bindings, 'on', () => true);
  telemetry.start();
  for (let index = 0; index < 140; index++) mock.sink().logEvent('bounded');
  expect(starts).toBe(128);
  release(); await telemetry.close();
  mock.sink().logEvent('closed'); expect(starts).toBe(128);
  const broken = fixture(); broken.bindings.context.Jk = async () => { throw new Error('synthetic failure'); };
  const resilient = createNativeTelemetry(broken.bindings, 'on', () => true);
  resilient.start(); await broken.sink().logEventAsync('failure'); await resilient.close();
});

test('原生退出永久等待时仍遵守一秒清理预算', async () => {
  const mock = fixture();
  mock.bindings.context.MDs = () => new Promise<void>(() => {});
  mock.bindings.context.bLe = () => new Promise<void>(() => {});
  const telemetry = createNativeTelemetry(mock.bindings, 'on', () => true);
  telemetry.start();
  const started = performance.now();
  await telemetry.close();
  expect(performance.now() - started).toBeLessThan(1400);
});
