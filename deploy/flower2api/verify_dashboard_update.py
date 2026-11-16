"""使用真实前端和合成目录验证首页自动检查及版本角标。"""
import asyncio
import json
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_environment_ui import BASE
from verify_runtime_workspace_design import WorkspaceFixture


class DashboardUpdateFixture(WorkspaceFixture):
    """提供异步检查、维护及失败场景的合成接口。"""

    def __init__(self, scenario):
        """初始化独立场景。@param scenario 场景名。@return None。"""
        super().__init__()
        self.scenario = scenario
        self.checks = 0
        self.check_started = asyncio.Event()
        self.catalog_reads = 0
        self.pending = 2 if scenario == 'checking' else 0

    async def route(self, route):
        """模拟更新检查，记录所有更新写入。@param route 请求路由。@return None。"""
        path = urlsplit(route.request.url).path
        if path == '/runtime/logout':
            assert route.request.method == 'POST'
            return await self.respond(route, {'ok': True})
        if path == '/runtime/api/system-updates/status':
            return await self.respond(route, {'installed': self.scenario != 'uninstalled',
                'current_release': self.current, 'busy': self.scenario == 'busy'})
        if path == '/runtime/api/system-updates/check':
            assert route.request.method == 'POST'
            self.checks += 1
            self.check_started.set()
            self.writes.append({'path': path, 'body': route.request.post_data_json})
            if self.scenario == 'failure':
                return await self.respond(route, {'error': '合成检查失败'}, 503)
            self.pending = 2
            return await self.respond(route, {'checking': True})
        if path == '/runtime/api/system-updates/releases':
            self.catalog_reads += 1
            checking = self.pending > 0
            if checking:
                self.pending -= 1
            completed = self.catalog_reads > 1 and not checking
            releases = self.releases if completed or self.scenario == 'failure' else [self.releases[1]]
            if self.scenario == 'missing-current':
                releases = [self.releases[0]]
            if self.scenario == 'latest':
                releases = [self.releases[1]]
            return await self.respond(route, {'fresh': True, 'releases': releases, 'checking': checking})
        return await super().route(route)


async def main():
    """验证自动检查、轮询结束、桌面和移动提示及卸载清理。@return None。"""
    scenes = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        for scenario in ['normal', 'checking', 'uninstalled', 'busy', 'failure', 'missing-current', 'latest', 'unmount']:
            fixture = DashboardUpdateFixture(scenario)
            context = await browser.new_context(viewport={'width': 1280, 'height': 900})
            await context.route('**/*', fixture.route)
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(error.message))
            await page.goto(BASE)
            badge = page.locator('.console-sidebar .brand-update')
            await expect(badge).to_be_visible()
            if scenario == 'uninstalled':
                await page.wait_for_timeout(2300)
                assert fixture.checks == fixture.catalog_reads == 0
            elif scenario == 'busy':
                await page.wait_for_timeout(2300)
                assert fixture.checks == 0 and fixture.catalog_reads == 1
            elif scenario == 'unmount':
                await asyncio.wait_for(fixture.check_started.wait(), timeout=5)
                await page.get_by_role('button', name='退出', exact=True).click()
                await expect(page).to_have_url(BASE + '/login')
                reads = fixture.catalog_reads
                await page.wait_for_timeout(2300)
                assert fixture.catalog_reads == reads
            else:
                has_update = scenario != 'latest'
                if has_update:
                    await expect(badge).to_have_class('brand-update has-update', timeout=12000)
                else:
                    await page.wait_for_timeout(7000)
                    await expect(badge).to_have_class('brand-update')
                assert fixture.checks == (0 if scenario == 'checking' else 1)
                if scenario in ['normal', 'checking']:
                    reads = fixture.catalog_reads
                    await page.wait_for_timeout(2300)
                    assert fixture.catalog_reads == reads
                    await page.get_by_role('link', name='运行环境', exact=False).first.click()
                    await expect(page).to_have_url(BASE + '/environments')
                    assert fixture.checks == (0 if scenario == 'checking' else 1)
                await page.set_viewport_size({'width': 390, 'height': 900})
                await page.get_by_role('button', name='打开主导航').click()
                mobile = page.locator('.mobile-navigation-panel .brand-update')
                await expect(mobile).to_be_visible()
                await expect(mobile).to_have_attribute('title', '系统更新 · 有可用新版' if has_update else '系统更新')
            assert not errors, errors
            assert not fixture.unexpected, fixture.unexpected
            assert all(item['path'].endswith('/system-updates/check') for item in fixture.writes), fixture.writes
            scenes.append({'scenario': scenario, 'checks': fixture.checks, 'catalog_reads': fixture.catalog_reads})
            await context.close()
        await browser.close()
    print(json.dumps({'passed': True, 'scenes': scenes, 'real_model_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
