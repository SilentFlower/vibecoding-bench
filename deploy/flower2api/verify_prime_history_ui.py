"""使用真实前端产物和合成接口验证模型预热记录的视觉与交互。"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from verify_session_policy_blocks_ui import BASE, ROOT, BlockFixture


class PrimeFixture(BlockFixture):
    """为预热记录提供成功、跳过、失败和异步加载样例。"""

    def __init__(self, gateway: Path) -> None:
        """初始化合成数据。@param gateway 前端产物目录。@return 无。"""
        super().__init__(gateway)
        self.delay = 0.35
        self.rows = [dict(id=index, account_id=7, account_name='预热账号',
            triggered_at='2026-11-17T04:10:00+08:00', hour=4,
            model='claude-haiku-4-5-' + '长模型名称' * 25,
            success=index == 1, error_message='' if index == 1 else
            'skipped: rate-limited until 2026-11-17T05:00:00Z' if index == 2 else
            'http 503: ' + '合成完整错误原因，保留所有内容。' * 30, duration_ms=0 if index == 2 else 1234)
            for index in (1, 2, 3)]

    async def route(self, route) -> None:
        """只替换预热记录接口。@param route 浏览器请求路由。@return 无。"""
        if urlsplit(route.request.url).path == '/admin/prime-logs':
            await asyncio.sleep(self.delay)
            await route.fulfill(content_type='application/json', body=json.dumps(self.rows))
            return
        await super().route(route)


async def run(output: Path, gateway: Path) -> dict:
    """验证四档视口与说明气泡。@param output 证据目录。@param gateway 产物目录。@return 汇总结果。"""
    from playwright.async_api import async_playwright, expect
    scenes = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        for width in (390, 1440, 1920, 2560):
            fixture = PrimeFixture(gateway)
            context = await browser.new_context(viewport={'width': width, 'height': 1000}, has_touch=width == 390)
            await context.route('**/*', fixture.route)
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-admin')")
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(BASE + '/settings?category=history')
            await page.locator('.system-settings-nav button').filter(has_text='预热记录').click()
            records = page.locator('.settings-prime-records')
            await expect(page.get_by_role('heading', name='最近模型预热记录')).to_be_visible()
            await expect(records.locator('tbody tr')).to_have_count(3)
            for label in ('成功', '跳过', '失败'):
                await expect(records.get_by_text(label, exact=True)).to_be_visible()
            await expect(page.get_by_role('link', name='进程准备状态见环境页面 →')).to_have_attribute('href', '/environments')
            await expect(records.get_by_text('0ms', exact=True).filter(visible=True)).to_have_count(1)
            reason = page.get_by_role('button', name='查看预热原因 3', exact=True)
            await reason.focus()
            await page.keyboard.press('Enter')
            await expect(page.locator('.fui-info-content')).to_contain_text(fixture.rows[2]['error_message'])
            await page.keyboard.press('Escape')
            await expect(page.locator('.fui-info-content')).to_have_count(0)
            await expect(reason).to_be_focused()
            if width == 390:
                await reason.tap()
                await expect(page.locator('.fui-info-content')).to_contain_text(fixture.rows[2]['error_message'])
                await page.keyboard.press('Escape')
            await page.get_by_role('button', name='查看模型 1', exact=True).filter(visible=True).click()
            await expect(page.locator('.fui-info-content')).to_contain_text(fixture.rows[0]['model'])
            await page.keyboard.press('Escape')
            font = await records.locator('td').first.evaluate("e=>parseFloat(getComputedStyle(e).fontSize)")
            assert font == (14 if width >= 2560 else 13 if width >= 1920 else 12), font
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
            await page.screenshot(path=str(output/f'prime-history-{width}.png'), full_page=True)
            fixture.rows = []
            fixture.delay = 0.6
            refresh = page.get_by_role('button', name='刷新', exact=True)
            # Escape 关闭气泡后鼠标仍停在模型触发器上，悬停延迟会重新打开气泡并挡住按钮，先移开鼠标。
            await page.mouse.move(0, 0)
            await refresh.click()
            await expect(page.get_by_role('button', name='加载中…', exact=True)).to_be_disabled()
            await expect(records.locator('tbody tr')).to_have_count(3)
            await expect(records.get_by_text('暂无模型预热记录', exact=True)).to_be_visible()
            await expect(records.locator('tbody > tr')).to_have_count(1)
            assert await records.locator('tbody tr tr').count() == 0
            await page.get_by_role('button', name='刷新', exact=True).click()
            await expect(records.get_by_text('正在读取预热记录…', exact=True)).to_be_visible()
            await expect(records.get_by_text('暂无模型预热记录', exact=True)).to_be_visible()
            await page.screenshot(path=str(output/f'prime-empty-{width}.png'), full_page=True)
            assert not fixture.saves, fixture.saves
            assert not errors, errors
            assert not fixture.external, fixture.external
            assert not fixture.unexpected, fixture.unexpected
            scenes.append({'width': width, 'passed': True, 'font_px': font})
            await context.close()
        await browser.close()
    return {'passed': True, 'scenes': scenes, 'real_model_requests': 0}


def main() -> None:
    """执行合成浏览器验证并保存结果。@return 无。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'.deploy/native-prime-ui')
    parser.add_argument('--gateway-dist', type=Path, default=ROOT/'apps/web/dist')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run(args.output.resolve(), args.gateway_dist.resolve()))
    (args.output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
