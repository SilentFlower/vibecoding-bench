import { expect, test } from 'bun:test';
import { resolve } from 'node:path';

test.each(['reuse', 'file_change', 'close', 'cancel', 'backpressure', 'ready_backpressure', 'wrong_request', 'wrong_worker', 'double_terminal', 'missing_idle', 'malformed', 'early_exit', 'startup_exit', 'startup_error', 'startup_error_wrong_worker', 'startup_error_after_ready', 'startup_wait', 'duplicate_ready', 'late', 'cache_match', 'cache_legacy', 'cache_mismatch', 'telemetry_match', 'telemetry_suppressed', 'telemetry_legacy', 'telemetry_mismatch'])('常驻生命周期与隔离：%s', async scenario => {
  const child = Bun.spawn([process.execPath, resolve('tests/fixtures/engine-probe.ts'), scenario], { stdout: 'pipe', stderr: 'pipe' });
  const [stdout, stderr, code] = await Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited]);
  expect({ code, stderr }).toEqual({ code: 0, stderr: '' });
  expect(JSON.parse(stdout).scenario).toBe(scenario);
}, 15000);
