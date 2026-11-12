import { build } from './build';

if (process.platform !== 'linux') throw new Error('原生离线验证需要 Linux 网络命名空间');
// 原版通过预加载入口执行；先构建以免测试到上一次生成的旧适配器。
await build();
const child = Bun.spawn(['unshare', '--net', process.execPath, 'test', 'tests/native', '--timeout', '45000', ...process.argv.slice(2)], {
  env: { ...process.env, CCRB_NATIVE_ISOLATED: '1' }, stdin: 'inherit', stdout: 'inherit', stderr: 'inherit',
});
process.exitCode = await child.exited;
