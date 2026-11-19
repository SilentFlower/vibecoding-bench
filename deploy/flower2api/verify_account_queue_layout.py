"""用合成账号验证排队提示切换时卡片尺寸和相邻布局保持稳定。"""

import asyncio
import json

from playwright.async_api import async_playwright, expect

from verify_accounts_design import AccountDesignFixture
from verify_environment_ui import BASE, ROOT


async def main():
    """比较桌面和移动端排队切换前后的实际布局。@return 无。"""
    fixture = AccountDesignFixture()
    fixture.accounts = fixture.accounts[:4]
    fixture.accounts[0]['v3_scheduling']['phases']['running'] = 4
    fixture.accounts[0]['v3_scheduling']['capacity']['reason'] = 'concurrency'
    output = ROOT / '.deploy/account-queue-layout'
    output.mkdir(parents=True, exist_ok=True)
    results = []
    errors = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 2248, 'height': 1000})
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width in [2248, 1440, 390]:
            await page.set_viewport_size({'width': width, 'height': 1000})
            baseline = None
            for queued in [0, 1, 8, 0]:
                fixture.accounts[0]['queued_requests'] = queued
                await page.goto(BASE + '/')
                cards = page.locator('.account-card')
                await expect(cards).to_have_count(4)
                await page.evaluate('document.fonts.ready')
                alert = cards.first.locator('.account-queue-alert')
                await expect(alert).to_have_count(1 if queued else 0)
                boxes = await cards.evaluate_all('elements => elements.map(element => { const rect = element.getBoundingClientRect(); return [rect.x, rect.y, rect.width, rect.height]; })')
                if baseline is None:
                    baseline = boxes
                assert all(abs(before - after) < 0.5 for original, current in zip(baseline, boxes) for before, after in zip(original, current)), (width, queued, baseline, boxes)
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                if queued == 1:
                    await expect(alert).to_be_visible()
                    await page.screenshot(path=str(output / f'queue-{width}.png'), full_page=True)
                    await alert.click()
                    await expect(page.get_by_role('dialog')).to_be_visible()
                    await expect(page.get_by_role('dialog')).to_contain_text('已绑定／活跃会话')
                results.append({'width': width, 'queued': queued, 'stable': True})
        assert not errors, errors
        report = {'passed': True, 'cases': results, 'real_model_requests': 0}
        (output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False))
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
