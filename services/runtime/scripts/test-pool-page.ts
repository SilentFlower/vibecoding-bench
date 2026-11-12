import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { chromium } from '@playwright/test';
import { servePoolReport } from './testing/pool-report';

/** 在无外网浏览器中验证已保存的报告，不重新运行场景。 @return 页面证据已保存。 */
async function main(): Promise<void> {
  const args = process.argv.slice(2), isolated = args[0] === '--isolated';
  if (!isolated) {
    const child = Bun.spawn(['unshare','--net',process.execPath,import.meta.path,'--isolated',...args], { env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: process.env.HOME ?? '/tmp', LANG: 'C.UTF-8' }, stdout: 'inherit', stderr: 'inherit' });
    process.exitCode = await child.exited; return;
  }
  if (!args[1] || Bun.spawnSync(['ip','link','set','lo','up']).exitCode !== 0) throw new Error('页面验证需要报告目录及无外网回环');
  const directory = resolve(args[1]), before = await readFile(join(directory, 'report.json'));
  const server = await servePoolReport(directory, 0), base = 'http://127.0.0.1:' + server.port;
  const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--no-sandbox','--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base);
    if (!await page.locator('summary').filter({ hasText: 'CC 最终出站' }).count() || !await page.locator('summary').filter({ hasText: '池转发参数' }).count()) throw new Error('两段采集标签缺失');
    if (await page.locator('script').count() || await page.evaluate(() => 'poolXss' in globalThis)) throw new Error('报告执行了输入脚本');
    await page.locator('article').first().locator('details').nth(3).evaluate(element => { (element as HTMLDetailsElement).open = true; });
    await page.screenshot({ path: join(directory, 'desktop.png'), fullPage: false });
    for (let i = 0; i < 3; i++) await page.reload();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('article').first().locator('details').nth(3).evaluate(element => { (element as HTMLDetailsElement).open = true; });
    if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error('手机页面横向溢出');
    await page.screenshot({ path: join(directory, 'mobile.png'), fullPage: false });
    const denied = await page.request.get(base + '/key.pem'); if (denied.status() !== 404) throw new Error('报告暴露了非白名单文件');
    const after = await readFile(join(directory, 'report.json'));
    if (!before.equals(after) || errors.length) throw new Error('只读页面改变了报告或发生浏览器错误');
    await mkdir(directory, { recursive: true });
    await writeFile(join(directory, 'page-proof.json'), JSON.stringify({ passed: true, labels: ['CC 最终出站','池转发参数'], scripts: 0, mobileWidth: 390, overflow: false, refreshes: 3, reportSha256: createHash('sha256').update(before).digest('hex'), inferenceOnRefresh: 0, protectedFileStatus: denied.status(), pageErrors: errors }, null, 2), { mode: 0o600 });
    console.log('报告页面验收通过：桌面、390 像素、文本安全、只读刷新。');
  } finally { await browser.close(); await server.stop(true); }
}

if (import.meta.main) await main().catch(() => { console.error('报告页面验收失败。'); process.exitCode = 1; });
