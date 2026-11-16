"""通过合成慢接口验证真实构建的分区加载与阅读空间。"""
import asyncio
import copy
import json
import time
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_environment_ui import BASE, ROOT
from verify_project_workspace_design import ProjectFixture
from verify_runtime_workspace_design import WorkspaceFixture
from verify_task_feedback import TaskFeedbackFixture


class SlowFixture(WorkspaceFixture):
    """用请求屏障确定页面在慢接口返回前的状态。"""

    def __init__(self, path, fail=False):
        """设置单个阻塞路径。@param path 路径。@param fail 首次失败。@return 无。"""
        super().__init__()
        self.path, self.fail = path, fail
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.hits = 0

    async def route(self, route):
        """阻塞目标请求后交给原合同夹具。@param route 请求。@return 无。"""
        if urlsplit(route.request.url).path == self.path:
            self.hits += 1
            if self.hits == 1:
                self.started.set()
                await self.release.wait()
                if self.fail:
                    return await self.respond(route, {'detail': '合成首次读取失败'}, 503)
        return await super().route(route)


class ReadingFixture(ProjectFixture):
    """在真实冻结交付合同上补充长文本阅读场景。"""

    def __init__(self):
        """初始使用真实短内容。@return 无。"""
        super().__init__()
        self.long_text = False

    async def respond(self, route, payload, status=200):
        """仅扩展阅读字段，保留候选身份与路径。@param route 请求。@param payload 回执。@param status 状态。@return 无。"""
        if self.long_text and '/projects/' in route.request.url and isinstance(payload, dict):
            payload = copy.deepcopy(payload)
            if 'work' in payload:
                payload['work']['goal'] = '长目标标题与边界验收说明' * 20
            if isinstance(payload.get('report'), dict):
                payload['report']['feedback'] = ['验收过程与环境说明。' * 300]
            if 'text' in payload:
                payload['text'] = ('冻结源码长行' * 100 + '\n') * 150
        return await super().respond(route, payload, status)


async def main():
    """验证会话、字体、草稿、历史和两类阅读区域。@return 无。"""
    output = ROOT / '.deploy/console-workspace-experience'
    output.mkdir(parents=True, exist_ok=True)
    result, errors = {}, []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()

        async def page_for(fixture, path='/tasks'):
            """创建带旧主题偏好的隔离页面。@param fixture 接口夹具。@param path 路由。@return 上下文与页面。"""
            context = await browser.new_context(viewport={'width': 1440, 'height': 900}, color_scheme='dark')
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','dark')")
            await context.route('**/*', fixture.route)
            page = await context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(BASE + path, wait_until='domcontentloaded')
            return context, page

        fixture = SlowFixture('/admin/runtime/session')
        started = time.monotonic()
        context, page = await page_for(fixture)
        await asyncio.wait_for(fixture.started.wait(), 5)
        root = page.locator('.task-runtime')
        await expect(root.locator('.runtime-heading')).to_be_visible()
        result['session_shell_ms'] = round((time.monotonic() - started) * 1000)
        assert await root.evaluate('e=>e.inert')
        await page.locator('.brand-update').click()
        await expect(page.locator('.approved-update-dialog')).to_be_visible()
        await page.wait_for_timeout(1500)
        assert fixture.hits == 1
        fixture.release.set()
        await expect(root.locator('.work-account')).to_have_count(1)
        await page.get_by_role('button', name='关闭更新面板').click()
        assert await root.get_attribute('data-theme') == 'light'
        assert await page.locator('#theme-toggle').count() == 0
        await page.goto(BASE + '/environments')
        await expect(page.locator('.environment-rich').first).to_be_visible()
        assert fixture.hits >= 2
        await context.close()

        fixture = SlowFixture('/admin/runtime/session', fail=True)
        context, page = await page_for(fixture)
        await asyncio.wait_for(fixture.started.wait(), 5)
        fixture.release.set()
        await expect(page.locator('.task-connect-error')).to_be_visible()
        assert await page.locator('.task-runtime').evaluate('e=>e.inert')
        await page.get_by_role('button', name='重新连接', exact=True).click()
        await expect(page.locator('.work-account')).to_have_count(1)
        assert fixture.hits == 2
        result['session_retry'] = '失败保持动作受控，重新连接再次交换会话'
        await context.close()

        for path, pane, form in [('/runtime/api/settings/project-requester', 'model', '#projects-model-form'),
                                 ('/runtime/api/projects/catalog', 'pool', '#projects-agent-form')]:
            fixture = SlowFixture(path)
            context, page = await page_for(fixture, '/tasks?tab=projects&account=1')
            await asyncio.wait_for(fixture.started.wait(), 5)
            await expect(page.locator('#projects-account')).to_be_enabled()
            await page.locator(f'[data-project-pane={pane}]').click()
            assert await page.locator(form).evaluate('e=>e.inert')
            await page.wait_for_timeout(1500)
            fixture.release.set()
            await expect(page.locator(form)).not_to_have_attribute('inert', '')
            result[pane + '_gate'] = '独立等待期间主状态可用，完成后开放配置'
            await context.close()

        fixture = SlowFixture('/runtime/api/environments')
        started = time.monotonic()
        context, page = await page_for(fixture, '/environments')
        await asyncio.wait_for(fixture.started.wait(), 5)
        await expect(page.get_by_role('heading', name='运行环境', exact=True)).to_be_visible()
        result['environment_shell_ms'] = round((time.monotonic() - started) * 1000)
        await page.wait_for_timeout(1500)
        fixture.release.set()
        await expect(page.locator('.environment-rich').first).to_be_visible()
        result['environment_gate'] = '环境列表延迟期间框架可见'
        await context.close()

        fixture = SlowFixture('/runtime/api/accounts/login-drafts', fail=True)
        started = time.monotonic()
        context, page = await page_for(fixture)
        await asyncio.wait_for(fixture.started.wait(), 5)
        await expect(page.locator('.work-account')).to_have_count(1)
        result['accounts_with_slow_drafts_ms'] = round((time.monotonic() - started) * 1000)
        await page.wait_for_timeout(1500)
        fixture.release.set()
        await page.get_by_role('button', name='重试登录草稿', exact=True).click()
        assert fixture.hits == 2
        await expect(page.locator('.work-account')).to_have_count(1)
        await context.close()

        fixture = SlowFixture('/runtime/api/projects', fail=True)
        context, page = await page_for(fixture, '/tasks?tab=projects&account=1')
        await asyncio.wait_for(fixture.started.wait(), 5)
        fixture.release.set()
        await page.get_by_role('button', name='重试工作区', exact=True).click()
        await expect(page.locator('#projects-account')).to_have_value('1')
        assert fixture.hits == 2
        await context.close()

        fixture = WorkspaceFixture()
        context, page = await page_for(fixture)
        await context.add_init_script("Object.defineProperty(document.fonts,'ready',{value:new Promise(resolve=>window.releaseFonts=resolve)})")
        await page.reload(wait_until='domcontentloaded')
        await expect(page.locator('.work-account')).to_have_count(1)
        await page.wait_for_timeout(1500)
        await page.evaluate('window.releaseFonts()')
        result['font_gate'] = '字体尚未就绪时账号与导航可见'
        await context.close()

        fixture = SlowFixture('/runtime/api/projects/agents/1/work/page', fail=True)
        context, page = await page_for(fixture, '/tasks?tab=projects&account=1')
        await asyncio.wait_for(fixture.started.wait(), 5)
        await expect(page.locator('#projects-account')).to_have_value('1')
        await expect(page.locator('#projects-account')).to_be_enabled()
        await page.locator('[data-project-pane=pool]').click()
        await page.locator('#projects-agent-form [name=instructions]').fill('慢历史期间编辑指南')
        await page.wait_for_timeout(1500)
        fixture.release.set()
        await expect(page.locator('#projects-agent-form [name=instructions]')).to_have_value('慢历史期间编辑指南')
        await page.locator('[data-project-pane=history]').click()
        await page.get_by_role('button', name='交付历史读取失败，点击重试', exact=True).click()
        assert fixture.hits == 2
        await page.locator('[data-project-pane=pool]').click()
        await expect(page.locator('#projects-agent-form [name=instructions]')).to_have_value('慢历史期间编辑指南')
        result['history_gate'] = '历史等待期间可编辑指南并保留输入'
        for width, height in [(1440, 900), (1280, 720), (390, 844)]:
            await page.set_viewport_size({'width': width, 'height': height})
            nav = page.locator('.work-navigation')
            await nav.locator('[data-tab=projects]').focus()
            await nav.locator('[data-tab=topics]').focus()
            await expect(nav.locator('[data-tab=topics]')).to_be_in_viewport()
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.screenshot(path=str(output / f'tabs-{width}.png'))
        await context.close()

        fixture = ReadingFixture()
        try:
            context, page = await page_for(fixture, '/tasks?tab=projects&account=1')
            await expect(page.locator('#projects-goal')).to_have_text('修复实际行为')
            await expect(page.locator('#projects-account')).to_be_enabled()
            await expect(page.locator('#projects-target-label')).to_be_visible()
            await page.locator('#projects-target-delivery').click()
            dialog = page.locator('.work-delivery-workspace')
            await expect(page.locator('#projects-delivery-preview')).to_have_text('VALUE = 3\n')
            for width, height in [(1440, 900), (1280, 720), (390, 844)]:
                await page.set_viewport_size({'width': width, 'height': height})
                await expect(dialog).to_be_visible()
                box = await dialog.bounding_box()
                assert box['y'] >= 0 and box['y'] + box['height'] <= height + 1, box
                for view in ['source', 'report']:
                    await page.locator(f'[data-delivery-view={view}]').click()
                    panel = page.locator(f'[data-delivery-panel={view}]')
                    await expect(panel).to_be_visible()
                    panel_box = await panel.bounding_box()
                    if width > 760:
                        assert panel_box['height'] + 1 >= box['height'] / 2, (box, panel_box)
                    assert await dialog.evaluate('e=>e.scrollWidth<=e.clientWidth')
                    await page.screenshot(path=str(output / f'delivery-{view}-{width}.png'))
            await page.keyboard.press('Escape')
            await expect(page.locator('#projects-delivery')).to_be_hidden()
            await expect(page.locator('#projects-target-delivery')).to_be_focused()
            fixture.long_text = True
            await page.locator('#projects-target-delivery').click()
            await expect(page.locator('#projects-delivery-preview')).to_contain_text('冻结源码长行')
            for width, height in [(1280, 720), (390, 844)]:
                await page.set_viewport_size({'width': width, 'height': height})
                for view, selector in [('source', '#projects-delivery-preview'), ('report', '#projects-delivery-report')]:
                    await page.locator(f'[data-delivery-view={view}]').click()
                    assert await page.locator(selector).evaluate('e=>e.scrollHeight>e.clientHeight')
                    assert await dialog.evaluate('e=>e.scrollWidth<=e.clientWidth')
                await page.screenshot(path=str(output / f'long-delivery-{width}.png'))
            await context.close()
        finally:
            fixture.fixture.doCleanups()
        context, page = await page_for(WorkspaceFixture(), '/runtime/#accounts')
        await expect(page.locator('.work-account')).to_have_count(1)
        assert await page.locator('html').get_attribute('data-theme') == 'light'
        assert await page.locator('#theme-toggle').count() == 0
        await context.close()
        fixture = TaskFeedbackFixture()
        for status, label in [('running', '当前目标'), ('passed', '最近完成目标'),
                              ('stopped', '最近停止目标'), ('deferred', '待复验目标')]:
            fixture.agent['work']['status'] = status
            fixture.agent['controller_active'] = status == 'running'
            for tab in ['projects', 'warmup']:
                context, page = await page_for(fixture, f'/tasks?tab={tab}&account=1')
                await expect(page.locator('#projects-target-label')).to_have_text(label)
                await expect(page.locator('#projects-target-delivery')).to_be_visible()
                assert await page.locator('.work-live>footer [data-show-project-pane=history]').count() == 0
                await page.screenshot(path=str(output / f'target-{tab}-{status}.png'))
                await context.close()
        assert not errors, errors
        result.update(passed=True, errors=errors, delay_ms=1500)
        (output / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
