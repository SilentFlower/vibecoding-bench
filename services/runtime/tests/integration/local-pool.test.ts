import { expect, test } from 'bun:test';
import { mkdir, writeFile } from 'node:fs/promises';

const binary = process.env.CCRB_TEST_ORIGINAL_BINARY ?? Bun.which('claude');

test.skipIf(!binary)('常驻池联调使用真实 293 客户端与无外网模拟池', async () => {
  const child = Bun.spawn(['unshare','--net',process.execPath,'test','tests/local-pool','--timeout','30000'], { env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: '/tmp', LANG: 'C.UTF-8', CCRB_TEST_ORIGINAL_BINARY: binary! }, stdin: 'ignore', stdout: 'pipe', stderr: 'pipe' });
  const output = Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text()]);
  const code = await child.exited, logs = await output;
  await mkdir('artifacts', { recursive: true });
  await writeFile('artifacts/local-pool-offline-proof.json', JSON.stringify({ passed: code === 0, realUpstreamRequests: 0, isolated: true, exitCode: code, output: logs.join('\n') }, null, 2) + '\n', { mode: 0o600 });
  if (code !== 0) throw new Error('离线常驻池联调失败：\n' + logs.join('\n'));
  expect(code).toBe(0);
}, 300000);
