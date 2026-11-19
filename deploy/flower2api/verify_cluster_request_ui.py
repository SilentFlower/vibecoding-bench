"""真实构建页面展示冻结请求节点与历史缺失状态的宽窄屏验证。"""
import asyncio
import json
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_environment_ui import BASE, ROOT, Fixture


class RequestNodeFixture(Fixture):
    """请求位置由合成历史记录提供，页面资源使用实际构建。"""

    platform = 'claude_code'

    async def route(self, route) -> None:
        """响应本次请求详情，其他读取沿原环境夹具。

        :param route: 已拦截浏览器请求。
        :return: None。
        """
        path = urlsplit(route.request.url).path
        if not path.startswith('/admin/request-diagnostics'):
            return await super().route(route)
        request = {'request_id': '11111111-1111-4111-8111-111111111111',
            'started_at': '2026-11-18T00:00:00Z', 'status_code': 200, 'account_id': 1,
            'account_name': '合成节点请求', 'outcome': 'success', 'attempt_count': 2, 'log_mode': 'info'}
        first = {'attempt_id': '22222222-2222-4222-8222-222222222222', 'account_id': 1,
            'ordinal': 1, 'profile_selection': 'native293_cc_prepared', 'status_code': 200, 'outcome': 'success',
            'execution_location': {'node_key': 'a' * 32, 'environment_id': 'e' * 32,
                'generation': 5, 'assignment_revision': 3}}
        if self.platform == 'antigravity':
            request['context'] = {'platform': 'antigravity', 'entry_protocol': 'gemini'}
            first['profile_selection'] = 'agy_native'
            first['execution_location'].update(node_key='local', assignment_revision=None)
            first['context'] = {'platform': 'antigravity', 'kernel': 'agy', 'kernel_version': '1.5.9',
                'credential_generation': 8, 'worker_id': 'synthetic-worker', 'control_state': 'completed'}
        history = {**first, 'attempt_id': '33333333-3333-4333-8333-333333333333', 'ordinal': 2}
        history.pop('execution_location')
        history.pop('context', None)
        value = ({'items': [request], 'total': 1, 'health': {}} if path == '/admin/request-diagnostics'
            else {'request': request, 'attempts': [first, history]})
        await route.fulfill(content_type='application/json', body=json.dumps(value))


async def main() -> None:
    """核对实际节点、历史未知及1440/390视口。:return: None。"""
    output = ROOT / '.trellis/.runtime/cluster-request-ui'
    output.mkdir(parents=True, exist_ok=True)
    fixture, errors = RequestNodeFixture(ROOT / 'apps/web/dist'), []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(BASE + '/requests')
        await page.get_by_role('button', name='详情', exact=True).click()
        await page.get_by_role('tab', name='请求链路', exact=True).click()
        cards = page.locator('.request-chain-card')
        await expect(cards).to_have_count(2)
        await expect(cards.first).to_contain_text('a' * 32)
        await expect(cards.first).to_contain_text('e' * 32 + ' · 5')
        await expect(cards.nth(1).locator('dt').filter(has_text='执行节点').locator('+ dd')).to_have_text('节点未观测')
        for width in (1440, 390):
            await page.set_viewport_size({'width': width, 'height': 1000})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert await page.locator('.request-workspace').evaluate('element => element.scrollWidth <= element.clientWidth')
            await page.screenshot(path=str(output / f'location-{width}.png'), full_page=True)
        fixture.platform = 'antigravity'
        await page.reload()
        await page.get_by_role('button', name='详情', exact=True).click()
        await page.get_by_role('tab', name='请求链路', exact=True).click()
        await expect(cards.first).to_contain_text('Antigravity · agy 1.5.9')
        await expect(cards.first.locator('dt').filter(has_text='执行节点').locator('+ dd').locator('.execution-node-heading > span')).to_have_text('默认本机')
        await expect(cards.first.locator('dt').filter(has_text='执行节点').locator('+ dd code')).to_have_text('local')
        await expect(cards.first.locator('dt').filter(has_text='凭据代次').locator('+ dd')).to_have_text('8')
        await expect(cards.first).to_contain_text('synthetic-worker')
        await expect(cards.nth(1).locator('dt').filter(has_text='执行节点').locator('+ dd')).to_have_text('节点未观测')
        for width in (1440, 390):
            await page.set_viewport_size({'width': width, 'height': 1000})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert await page.locator('.request-workspace').evaluate('element => element.scrollWidth <= element.clientWidth')
            await page.screenshot(path=str(output / f'agy-location-{width}.png'), full_page=True)
        assert not errors and not fixture.unexpected and not fixture.external, (errors, fixture.unexpected, fixture.external)
        await browser.close()
    print(json.dumps({'passed': True, 'scenes': ['冻结节点与实际环境代次', '历史缺失保持未观测', 'AGY上下文与本机位置共存', '1440与390布局'],
        'errors': errors, 'real_model_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
