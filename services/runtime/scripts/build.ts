import { cp, mkdir } from 'node:fs/promises';

/** 构建预加载入口和本地页面，不打包官方程序。
 * @return 构建完成。
 */
export async function build(): Promise<void> {
  await mkdir('dist/web', { recursive: true });
  const runtime = await Bun.build({ entrypoints: ['src/runtime/293/preload.ts'], target: 'bun', format: 'esm', outdir: 'dist', naming: 'preload.mjs' });
  if (!runtime.success) throw new AggregateError(runtime.logs, '运行时入口构建失败');
  const browser = await Bun.build({ entrypoints: ['web/client.ts'], target: 'browser', format: 'esm', outdir: 'dist/web', naming: 'app.js' });
  if (!browser.success) throw new AggregateError(browser.logs, '日志页面构建失败');
  await cp('web/index.html', 'dist/web/index.html');
  await cp('web/style.css', 'dist/web/style.css');
}

if (import.meta.main) await build();
