"""用正式构建验证账号筛选的对齐、键盘和组合查询，全部使用合成数据。"""
import asyncio
import json
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import async_playwright, expect
from verify_agy_accounts_ui import PlatformFixture
from verify_environment_ui import BASE, ROOT


class FilterFixture(PlatformFixture):
    """提供按平台计数、状态组合和乱序响应。"""

    def __init__(self):
        """准备两个AGY账号及一个CC账号。@return 无。"""
        super().__init__()
        self.accounts[1]['status'] = 'disabled'
        self.reads = []
        self.hold_platform = None
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def route(self, route):
        """返回当前筛选的分页和平台计数。@param route 浏览器请求。@return 无。"""
        request = route.request
        url = urlsplit(request.url)
        if url.path != '/admin/accounts' or request.method != 'GET':
            return await super().route(route)
        query = parse_qs(url.query)
        platform = query.get('platform', ['claude_code'])[0]
        status = query.get('status', [''])[0]
        search = query.get('q', [''])[0].lower()
        page = int(query.get('page', ['1'])[0])
        size = int(query.get('page_size', ['12'])[0])
        self.reads.append(dict(platform=platform, status=status, search=search, page=page))
        scope = [row for row in self.accounts if platform == 'all' or row['platform'] == platform]
        rows = [row for row in scope if (not status or row['status'] == status)
            and search in (row['name'] + ' ' + row['email']).lower()]
        counts = {'total': len(scope), **{key: sum(row['status'] == key for row in scope)
            for key in ['active', 'error', 'disabled']}}
        if platform == self.hold_platform:
            self.started.set()
            await self.release.wait()
        return await self.respond(route, dict(data=rows[(page-1)*size:page*size], total=len(rows),
            page=page, page_size=size, total_pages=(len(rows)+size-1)//size, account_counts=counts))


async def main():
    """验证实际布局、无障碍名称和筛选响应归属。@return 无。"""
    fixture = FilterFixture()
    errors = []
    output = ROOT / '.trellis/.runtime'
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        await page.route('**/*', fixture.route)
        await page.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(BASE + '/')
        cards = page.locator('.account-card')
        await expect(cards).to_have_count(3)
        toolbar = page.locator('.account-toolbar')
        platform = toolbar.get_by_role('combobox', name='平台筛选')
        # 状态筛选为分段控件（Segmented，role=radiogroup / radio）。
        states = toolbar.get_by_role('radiogroup', name='账号状态筛选')
        search_toggle = page.get_by_role('button', name='搜索账号', exact=True)
        for width in [1440, 720, 390, 1920]:
            await page.set_viewport_size({'width': width, 'height': 1000})
            if width <= 760:
                # 移动端（设计稿 #mobile）搜索行默认收起，由应用栏搜索按钮展开；分段独占一行。
                await expect(platform).to_be_hidden()
                await expect(states).to_be_visible()
                await search_toggle.click()
                await expect(search_toggle).to_have_attribute('aria-expanded', 'true')
                await expect(toolbar.get_by_role('searchbox', name='搜索账号')).to_be_focused()
            else:
                await expect(search_toggle).to_be_hidden()
            sizes = await toolbar.evaluate('''e => {
                const box = selector => {const r=e.querySelector(selector).getBoundingClientRect();
                    return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,height:r.height}};
                return {platform:box('.fui-choice'),states:box('.account-filter-tabs'),
                    search:box('.fui-search'),label:box('.account-platform-filter .fui-label'),
                    overflow:document.documentElement.scrollWidth>window.innerWidth};
            }''')
            assert sizes['label']['height'] <= 1, sizes
            assert abs(sizes['platform']['height'] - sizes['states']['height']) <= 1, sizes
            assert not sizes['overflow'], sizes
            if width <= 760:
                assert abs(sizes['platform']['top'] - sizes['search']['top']) <= 1, sizes
                assert sizes['states']['top'] >= sizes['platform']['bottom'], sizes
            elif width >= 1440:
                assert abs(sizes['platform']['top'] - sizes['states']['top']) <= 1, sizes
            await toolbar.screenshot(path=str(output / f'account-filters-{width}.png'))
            if width <= 760:
                await search_toggle.click()
                await expect(platform).to_be_hidden()
        await page.set_viewport_size({'width': 1440, 'height': 1000})
        await platform.focus()
        await page.keyboard.press('Enter')
        await page.keyboard.press('ArrowDown')
        await page.keyboard.press('Escape')
        await expect(platform).to_be_focused()
        await expect(platform).to_contain_text('全部平台')
        await platform.click()
        await page.get_by_role('option', name='Antigravity', exact=True).click()
        await expect(cards).to_have_count(2)
        await expect(states.get_by_role('radio', name='全部账号 2', exact=True)).to_be_visible()
        await states.get_by_role('radio', name='已停用 1', exact=True).click()
        await expect(cards).to_have_count(1)
        await expect(cards).to_contain_text('AGY账号2')
        assert fixture.reads[-1] == dict(platform='antigravity', status='disabled', search='', page=1)
        search = toolbar.get_by_role('searchbox', name='搜索账号')
        async with page.expect_response(lambda response: '/admin/accounts?' in response.url and 'q=agy2' in response.url):
            await search.fill('agy2')
        await expect(cards).to_have_count(1)
        await platform.click()
        await page.get_by_role('option', name='Claude Code', exact=True).click()
        await expect(cards).to_have_count(0)
        assert fixture.reads[-1] == dict(platform='claude_code', status='disabled', search='agy2', page=1)
        await search.fill('')
        await states.get_by_role('radio', name='全部账号 1', exact=True).click()
        await expect(cards).to_have_count(1)
        await expect(cards).to_contain_text('CC兼容账号')
        fixture.hold_platform = 'antigravity'
        await platform.click()
        await page.get_by_role('option', name='Antigravity', exact=True).click()
        await asyncio.wait_for(fixture.started.wait(), 5)
        await platform.click()
        await page.get_by_role('option', name='Claude Code', exact=True).click()
        await expect(cards).to_have_count(1)
        fixture.release.set()
        await asyncio.sleep(.2)
        await expect(cards).to_contain_text('CC兼容账号')
        assert not errors, errors
        print(json.dumps(dict(passed=True, aligned=True, widths=[390,720,1440,1920], keyboard=True,
            combined_filters=True, late_response_isolated=True, model_submissions=0)))
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
