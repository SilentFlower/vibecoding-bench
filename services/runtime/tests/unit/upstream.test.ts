import { describe, expect, test } from 'bun:test';
import { readConfig } from '../../src/control/server';
import { prepareInput } from '../../src/control/header-policy';
import { parseInput } from '../../src/shared/input';
import { decodeRuntimeJob } from '../../src/shared/protocol';
import { readModelOverride, readNativeBaseUrl, selectUpstreamModel } from '../../src/shared/upstream';

describe('本机上游与模型选择合同', () => {
  test('默认不覆盖端点和模型，不从宿主 Anthropic 环境取得配置', () => {
    const config = readConfig({ ANTHROPIC_BASE_URL: 'https://must-not-inherit.invalid', ANTHROPIC_API_KEY: 'host-key' });
    expect(config.engine.baseUrl).toBeUndefined();
    expect(config.engine.apiKey).toBeUndefined();
    expect(config.modelOverride).toBeUndefined();
    expect(config.tlsCapture).toBe('off');
    expect(config.nativeIngressPolicy).toBe('strict');
  });

  test('显式配置与本地入站策略独立，SDK 路径前缀不被擅自裁剪', () => {
    const config = readConfig({ CCRB_NATIVE_BASE_URL: 'https://pool.invalid/prefix/', CCRB_MODEL_OVERRIDE: 'local/model:variant', CCRB_TLS_CAPTURE: 'verify', CCRB_NATIVE_INGRESS_POLICY: 'local_base_url' });
    expect(config.engine.baseUrl).toBe('https://pool.invalid/prefix/');
    expect(config.modelOverride).toBe('local/model:variant');
    expect(config.tlsCapture).toBe('verify');
    expect(config.nativeIngressPolicy).toBe('local_base_url');
  });

  test('非法 URL 与控制字符在启动阶段拒绝，错误不回显 URL 凭据', () => {
    for (const value of ['', 'ftp://pool.invalid', 'https://user:secret-canary@pool.invalid', 'https://pool.invalid/?', 'https://pool.invalid/#', ' https://pool.invalid', 'https://pool.invalid/\n']) {
      expect(() => readNativeBaseUrl(value)).toThrow('CCRB_NATIVE_BASE_URL');
      try { readNativeBaseUrl(value); } catch (error) { expect(String(error)).not.toContain('secret-canary'); }
    }
    for (const value of ['', ' ', 'model\nname', ' model']) expect(() => readModelOverride(value)).toThrow('CCRB_MODEL_OVERRIDE');
    expect(() => readConfig({ CCRB_TLS_CAPTURE: 'unknown' })).toThrow('CCRB_TLS_CAPTURE');
    expect(() => readConfig({ CCRB_NATIVE_INGRESS_POLICY: 'unknown' })).toThrow('CCRB_NATIVE_INGRESS_POLICY');
  });

  test('只选择根模型，保留入站对象、嵌套业务与发生时归因', () => {
    const input = parseInput({ model: 'requested-model', messages: [{ role: 'user', content: [{ type: 'tool_result', tool_use_id: 'fixture', content: [{ type: 'text', text: '历史' }], future: { model: 'nested-model' } }] }], tools: [{ name: 'lookup', input_schema: { type: 'object', properties: { model: { type: 'string', default: 'tool-model' } } } }] });
    const prepared = prepareInput(input), before = structuredClone(prepared);
    const selected = selectUpstreamModel(prepared, 'effective-model');
    expect(prepared).toEqual(before);
    expect(selected.input.body.model).toBe('effective-model');
    expect(selected.input.body.messages).toEqual(before.input.body.messages);
    expect(selected.input.body.tools).toEqual(before.input.body.tools);
    expect(selected.context).toEqual({ ...before.context, modelSelection: { requested: 'requested-model', effective: 'effective-model', source: 'startup_override' } });
    expect(selectUpstreamModel(prepared).context.modelSelection).toEqual({ requested: 'requested-model', effective: 'requested-model', source: 'request' });
    const job = { type: 'request_start', schema_version: 1, request_id: selected.input.request_id, prepared: selected };
    expect(decodeRuntimeJob(job).prepared.context.modelSelection?.effective).toBe('effective-model');
    selected.context.modelSelection!.effective = 'forged-model';
    expect(() => decodeRuntimeJob(job)).toThrow('模型选择证据');
  });
});
