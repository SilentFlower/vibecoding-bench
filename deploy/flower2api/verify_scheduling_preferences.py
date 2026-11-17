"""用合成管理接口验证智能调度新系数、旧评分移除和状态解释。"""
import asyncio
import json
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_accounts_design import AccountDesignFixture
from verify_environment_ui import BASE, ROOT


class SchedulingFixture(AccountDesignFixture):
    """提供可保存的字符串设置和真实组件使用的调度摘要。"""

    def __init__(self):
        """初始化离线样例。@return 无。"""
        super().__init__()
        self.settings = dict(v3_smart_weight_reset='0', v3_smart_weight_queue='0',
                             v3_smart_reset_weight_5h='1', v3_smart_reset_weight_7d='1',
                             v3_scheduling_mode='legacy_score', score_weight_7d='0.5')
        self.saved = []
        self.fail_save = False
        self.summary['config'].update(reset_weight=0.4, queue_weight=0.7,
                                      reset_window_weights=[1.0, 1.0])
        self.summary['factors'].update(reset=0.6, queue=0.8, wait_score=0.72,
                                      estimated_wait_ms=2500, wait_basis='sampled')

    async def route(self, route):
        """拦截设置读写，其余复用离线夹具。@param route 浏览器路由。@return 无。"""
        path = urlsplit(route.request.url).path
        if path == '/runtime/api/system-updates/status':
            return await self.respond(route, {'installed': False})
        if path == '/admin/settings':
            if route.request.method == 'PUT':
                if self.fail_save:
                    return await self.respond(route, {'error': '合成保存失败'}, 500)
                body = route.request.post_data_json
                assert all(isinstance(value, str) for value in body.values())
                assert not any(key in body for key in ['v3_scheduling_mode', 'score_weight_7d',
                                                      'score_weight_5h', 'score_weight_concurrency'])
                self.saved.append(body)
                self.settings.update(body)
                return await self.respond(route, {'ok': True})
            return await self.respond(route, self.settings)
        return await super().route(route)


async def main():
    """验证实际构建的保存、回退、错误定位与两档状态展示。@return 无。"""
    output = ROOT / '.trellis/.runtime/scheduling-preferences-ui'
    output.mkdir(parents=True, exist_ok=True)
    fixture = SchedulingFixture()
    errors = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(BASE + '/settings')
        reset = page.locator('[data-settings-field="v3_smart_weight_reset"] input')
        queue = page.locator('[data-settings-field="v3_smart_weight_queue"] input')
        await expect(reset).to_have_value('0')
        await expect(page.locator('[data-settings-field="v3_scheduling_mode"]')).to_have_count(0)
        await expect(page.get_by_text('兼容排序权重', exact=True)).to_have_count(0)
        await reset.fill('0.4')
        await queue.fill('0.7')
        await page.get_by_role('button', name='撤销修改', exact=True).click()
        await expect(reset).to_have_value('0')
        await expect(queue).to_have_value('0')
        await reset.fill('0.4')
        await queue.fill('0.01')
        await page.get_by_role('button', name='保存配置', exact=True).click()
        await expect(page.locator('[data-settings-field="v3_smart_weight_queue"] [role="alert"]')).to_be_visible()
        assert not fixture.saved
        await queue.fill('0.7')
        await page.get_by_role('button', name='保存配置', exact=True).click()
        await expect(page.get_by_text('配置已同步', exact=True)).to_be_visible()
        assert fixture.saved[-1]['v3_smart_weight_reset'] == '0.4'
        assert fixture.saved[-1]['v3_smart_weight_queue'] == '0.7'
        await page.screenshot(path=str(output / 'settings-1440.png'), full_page=True)
        fixture.fail_save = True
        await reset.fill('0.5')
        await page.get_by_role('button', name='保存配置', exact=True).click()
        await expect(page.locator('.fui-notice').filter(has_text='合成保存失败')).to_be_visible()
        await expect(reset).to_have_value('0.5')
        await page.get_by_role('button', name='撤销修改', exact=True).click()
        await expect(reset).to_have_value('0.4')
        await page.goto(BASE + '/')
        card = page.locator('.account-card').first
        await card.locator('.account-live-metrics button').nth(2).click()
        dialog = page.get_by_role('dialog')
        await expect(dialog.get_by_text('重置偏好', exact=True)).to_be_visible()
        await expect(dialog.get_by_text('排队偏好', exact=True)).to_be_visible()
        await expect(dialog).to_contain_text('预计等待 2.5 秒')
        await expect(dialog).not_to_contain_text('旧评分')
        await page.screenshot(path=str(output / 'details-1440.png'), full_page=True)
        await page.keyboard.press('Escape')
        fixture.summary['factors'].update(estimated_wait_ms=None, wait_basis='pressure')
        await card.locator('.account-live-metrics button').nth(2).click()
        await expect(dialog).to_contain_text('按队列压力比较，预计时长未知')
        await page.keyboard.press('Escape')
        for key in ['reset_weight', 'queue_weight', 'reset_window_weights']:
            fixture.summary['config'].pop(key, None)
        await card.locator('.account-live-metrics button').nth(2).click()
        await expect(dialog.get_by_text('排队偏好', exact=True)).to_have_count(0)
        await page.keyboard.press('Escape')
        await page.set_viewport_size({'width': 390, 'height': 900})
        await page.goto(BASE + '/settings')
        await expect(reset).to_have_value('0.4')
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(output / 'settings-390.png'), full_page=True)
        assert not errors, errors
        await browser.close()
    result = {'passed': True, 'checks': ['字符串保存与撤销', '精度错误定位', '失败保留草稿',
                                       '旧评分退出页面与提交', '等待估算与压力回退', '旧响应兼容', '1440/390px'],
              'errors': errors}
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
