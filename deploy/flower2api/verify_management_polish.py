"""验证品牌入口及真实浏览器剪贴板；所有网络使用合成夹具。"""
import argparse
import asyncio
import json
from pathlib import Path

from source_layout import source_path
from verify_environment_ui import BASE, ROOT
from verify_management_ui import ManagementFixture


async def run(output: Path) -> dict:
    """验收四种复制能力和品牌资源。@param output 证据目录。@return 聚合结果。"""
    from playwright.async_api import async_playwright, expect

    output.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    request_id = '11111111-1111-4111-8111-111111111111'
    secure = 'https://environment-ui.test'
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        for mode in ['https', 'http', 'rejected', 'failed']:
            context = await browser.new_context(viewport={'width': 1280, 'height': 900})
            fixture = ManagementFixture(source_path(ROOT, 'cc2api/web/dist'))
            await context.route('**/*', fixture.route)
            await context.route('**/clipboard-probe', lambda route: route.fulfill(content_type='text/html', body='<button>剪贴板验证</button>'))
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
            if mode == 'rejected':
                await context.add_init_script("if (location.pathname !== '/clipboard-probe') Object.defineProperty(navigator, 'clipboard', {value: {writeText: async () => {throw new DOMException('合成拒绝','NotAllowedError')}}})")
            elif mode == 'failed':
                await context.add_init_script("if (location.pathname !== '/clipboard-probe') Object.defineProperty(navigator, 'clipboard', {value: undefined});if (location.pathname !== '/clipboard-probe') document.execCommand = () => false")
            await context.grant_permissions(['clipboard-read', 'clipboard-write'], origin=secure)
            probe = await context.new_page()
            # 探针使用原生 API，不继承失败注入；被测页面仍保留指定能力。
            await probe.goto(secure + '/clipboard-probe')
            await probe.evaluate("delete navigator.clipboard")
            page = await context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto((BASE if mode in ['http', 'failed'] else secure) + '/requests')
            assert await page.evaluate('isSecureContext') == (mode not in ['http', 'failed'])
            if mode == 'http':
                assert await page.evaluate('typeof navigator.clipboard') == 'undefined'
            for detail in [False, True]:
                if detail:
                    await page.get_by_role('button', name='详情', exact=True).click()
                    button = page.get_by_role('button', name='复制完整请求 ID', exact=True)
                else:
                    button = page.get_by_role('button', name='复制请求 ' + request_id, exact=True)
                await probe.bring_to_front()
                await probe.locator('button').click()
                await probe.evaluate("navigator.clipboard.writeText('sentinel')")
                await page.bring_to_front()
                await button.click()
                await expect(button).to_be_focused()
                message = '复制失败，请选择文本手动复制' if mode == 'failed' else '已复制'
                await expect(page.get_by_text(message, exact=True).last).to_be_visible()
                assert await page.locator('textarea').count() == 0
                await probe.bring_to_front()
                await probe.locator('button').click()
                actual = await probe.evaluate('navigator.clipboard.readText()')
                assert actual == ('sentinel' if mode == 'failed' else request_id), (mode, detail, actual)
                await page.bring_to_front()
                if detail:
                    await page.keyboard.press('Escape')
                    await expect(page.get_by_role('button', name='详情', exact=True)).to_be_focused()
                results.append({'mode': mode, 'detail': detail, 'clipboard_value_verified': True})
            if mode == 'https':
                icon = page.locator('img[alt="flower2api 标志"]')
                await expect(icon).to_have_attribute('src', '/favicon.svg?v=flower2api-pink-04')
                assert await page.locator('link[rel="icon"]').get_attribute('href') == '/favicon.svg?v=flower2api-pink-04'
                await page.evaluate("""() => {
                    const board = document.createElement('div');
                    board.style.cssText = 'position:fixed;inset:120px 30px auto;z-index:100;background:white;padding:20px;display:flex;gap:24px';
                    for (const color of ['white','#171717']) for (const size of [24,40,256]) {
                        const surface = document.createElement('div'); surface.style.cssText = `padding:16px;background:${color}`;
                        const img = document.createElement('img'); img.src='/favicon.svg?v=flower2api-pink-04'; img.width=size; img.height=size;
                        surface.append(img); board.append(surface);
                    }
                    document.body.append(board);
                }""")
                await page.screenshot(path=str(output / 'brand-surfaces.png'))
                await page.evaluate("localStorage.removeItem('claude-code-gateway_auth')")
                await context.route('**/login', lambda route: route.fulfill(path=str(source_path(ROOT, 'cc2api/web/dist') / 'index.html'), content_type='text/html'))
                await page.goto(secure + '/login')
                await expect(page.locator('img[alt="flower2api 标志"]')).to_have_attribute('src', '/favicon.svg?v=flower2api-pink-04')
                await page.screenshot(path=str(output / 'brand-login.png'))
            assert not fixture.writes and not fixture.unexpected and not fixture.external, (fixture.writes, fixture.unexpected, fixture.external)
            await context.close()
        await browser.close()
    assert not errors, errors
    return {'passed': True, 'clipboard_cases': results, 'errors': errors, 'real_model_requests': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run(args.output))
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))
