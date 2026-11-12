import { expect, test } from 'bun:test';

test('Node TLS 转发故障矩阵始终在无外网空间执行', async () => {
  const child = Bun.spawn(['unshare','--net',process.execPath,'test','tests/pool','--timeout','15000'], { env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: '/tmp', LANG: 'C.UTF-8' }, stdin: 'ignore', stdout: 'pipe', stderr: 'pipe' });
  const output = Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text()]);
  const code = await child.exited, logs = await output;
  if (code !== 0) throw new Error('离线 TLS 矩阵失败：\n' + logs.join('\n'));
  expect(code).toBe(0);
}, 30000);
