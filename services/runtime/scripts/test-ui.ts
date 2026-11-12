import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

if (process.platform !== 'linux') throw new Error('页面离线验收需要 Linux 网络命名空间');
if (process.env.CCRB_UI_ISOLATED !== '1') {
  const child = Bun.spawn(['unshare', '--net', process.execPath, import.meta.path, ...process.argv.slice(2)], {
    env: { ...process.env, CCRB_UI_ISOLATED: '1' }, stdin: 'inherit', stdout: 'inherit', stderr: 'inherit',
  });
  process.exitCode = await child.exited;
} else {
  if (Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode !== 0) throw new Error('无法在独立网络空间启用回环接口');
  const root = await mkdtemp(join(tmpdir(), 'ccrb-ui-test-'));
  try {
    const child = Bun.spawn(['node', 'node_modules/@playwright/test/cli.js', 'test', ...process.argv.slice(2)], {
      env: { ...process.env, CCRB_DATA_DIR: root }, stdin: 'inherit', stdout: 'inherit', stderr: 'inherit',
    });
    process.exitCode = await child.exited;
  } finally { await rm(root, { recursive: true, force: true }); }
}
