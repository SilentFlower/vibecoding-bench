import { expect, test } from 'bun:test';
import { decodeWorkerFrame } from '../../src/shared/protocol';

test.each(['configuration', 'unknown', 'bounded'])('初始化失败输出等待写入并保护秘密：%s', async scenario => {
  const workerId = '11111111-1111-4111-8111-111111111111';
  const key = 'startup-config-secret-canary';
  const program = "import {reportStartupFailure} from './src/runtime/293/worker'; import {BridgeError} from './src/shared/errors'; const scenario=process.env.CCRB_FAILURE_CASE; await reportStartupFailure(scenario==='unknown'?new Error('/private/config '+process.env.ANTHROPIC_API_KEY):new BridgeError('native_configuration',scenario==='bounded'?'测'.repeat(1000):'配置失败：'+process.env.ANTHROPIC_API_KEY,503)); process.exit(111);";
  const child = Bun.spawn([process.execPath, '--eval', program], { env: { PATH: process.env.PATH ?? '/usr/bin:/bin', CCRB_WORKER_ID: workerId, CCRB_FAILURE_CASE: scenario, ANTHROPIC_API_KEY: key }, stdout: 'pipe', stderr: 'pipe' });
  const [stdout, stderr, code] = await Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited]);
  expect({ code, stderr }).toEqual({ code: 111, stderr: '' });
  expect(stdout).not.toContain(key);
  const frame = decodeWorkerFrame(stdout.trim(), workerId);
  expect(frame.type).toBe('worker_error');
  if (frame.type !== 'worker_error') throw new Error('缺少初始化错误帧');
  expect(frame.status).toBe(503);
  if (scenario === 'unknown') expect(frame.error).toBe('固定运行时初始化失败');
  else if (scenario === 'configuration') expect(frame.error).toBe('配置失败：[REDACTED]');
  else expect(Buffer.byteLength(frame.error)).toBeLessThanOrEqual(2048);
});
