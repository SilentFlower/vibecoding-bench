"""以真实账号配置 API 和独立 SQLite 验证原生任务配置，并核对第二版弹窗外观只取 token。"""
import asyncio
import json
import re
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from test_account_cli_settings import AccountCliSettingsTests
from verify_environment_ui import BASE, ROOT
from verify_native_pages_design import shell, tokens_only
from verify_task_feedback import TaskFeedbackFixture


def contrast(foreground, background):
    """计算文字与背景对比度。@param foreground 前景RGB。@param background 背景RGB。@return 对比度。"""
    def luminance(value):
        """计算线性相对亮度；半透明颜色（如输入框的填充底）先叠在白色弹窗表面上。@param value CSS颜色。@return 亮度。"""
        numbers = [float(number) for number in re.findall(r'[\d.]+', value)]
        alpha = numbers[3] if len(numbers) > 3 else 1
        channels = [(number * alpha + 255 * (1 - alpha)) / 255 for number in numbers[:3]]
        return sum(weight * (channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4)
            for weight, channel in zip([.2126, .7152, .0722], channels))
    first, second = luminance(foreground), luminance(background)
    return (max(first, second) + .05) / (min(first, second) + .05)


class AccountConfigFixture(TaskFeedbackFixture):
    """配置请求进入真实后端，环境与模型请求使用本地合成数据。"""

    def __init__(self, backend):
        """保留独立数据库客户端。@param backend 后端测试夹具。@return 无。"""
        super().__init__()
        self.backend = backend
        self.config_writes = []
        self.process_writes = 0
        self.config_gate = None
        self.config_started = asyncio.Event()

    async def route(self, route):
        """代理配置的真实读写，记录维护操作。@param route 浏览器请求。@return 无。"""
        path = urlsplit(route.request.url).path
        if path == '/runtime/api/accounts/1/cli-settings':
            if route.request.method == 'PUT':
                self.config_writes.append(route.request.post_data_json)
                result = self.backend.client.put('/api/accounts/1/cli-settings', json=route.request.post_data_json)
            else:
                self.config_started.set()
                if self.config_gate:
                    await self.config_gate.wait()
                result = self.backend.client.get('/api/accounts/1/cli-settings')
            return await self.respond(route, result.json(), result.status_code)
        if path == '/runtime/api/accounts':
            saved = self.backend.client.get('/api/accounts').json()[0]
            self.task_accounts[0].update(name=saved['name'], display_name=saved['display_name'],
                claude_code_version=saved['claude_code_version'])
        if path == '/runtime/api/accounts/1/cc2api/process':
            self.process_writes += 1
            return await self.respond(route, {'cc2api_account_id': 11,
                'canonical_process': {'observation': {'sample_count': 1}}})
        return await super().route(route)


async def main():
    """验证保存、取消、子窗草稿、局部路由、迟到响应和第二版外观。@return 无。"""
    backend = AccountCliSettingsTests()
    backend.setUp()
    output = ROOT / '.deploy/frontend-sidebar-refresh/task-account-config'
    output.mkdir(parents=True, exist_ok=True)
    fixture = AccountConfigFixture(backend)
    differences, errors = [], []
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
            await context.route('**/*', fixture.route)
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
            page = await context.new_page()
            page.on('pageerror', lambda error: errors.append(error.stack))
            await page.goto(BASE + '/tasks')
            root = page.locator('.task-runtime')
            modal = root.locator('#cli-settings-modal')
            name = modal.locator('[name=display_name]')
            save = modal.get_by_role('button', name='保存账号配置', exact=True)
            await root.locator('[data-cli-settings]').click()
            await expect(save).to_be_enabled()
            await expect(name).to_have_value('main')
            await expect(modal.locator('#cli-settings-capture')).to_be_hidden()
            await expect(modal.locator('#cli-settings-process')).to_be_hidden()
            # 外观已换成第二版：外壳圆角与阴影、标题字重、颜色只取 token（对照组件库规格，旧原型逐项比对移除）。
            await page.evaluate('document.fonts.ready')
            await shell(page, '#cli-settings-modal .modal-card', '.modal-titlebar-name', '任务账号配置', differences)
            await tokens_only(page, '#cli-settings-modal .modal-card', '任务账号配置', differences)
            await name.fill('未保存的草稿')
            await modal.locator('#cli-settings-quota').click()
            policy = root.locator('#warmup-modal')
            await expect(policy).to_be_visible()
            await page.keyboard.press('Escape')
            await expect(policy).to_be_hidden()
            await expect(name).to_have_value('未保存的草稿')
            await modal.get_by_role('button', name='取消', exact=True).click()
            assert fixture.config_writes == []
            await root.locator('[data-cli-settings]').click()
            await expect(save).to_be_enabled()
            await expect(name).to_have_value('main')
            await name.fill('团队账号 <安全显示>')
            await modal.locator('[name=claude_code_version]').fill('2.1.303')
            await save.click()
            await expect(modal).to_be_hidden()
            await expect(root.locator('.work-account h3')).to_have_text('团队账号 <安全显示>')
            stored = backend.sql('SELECT name,claude_code_version FROM accounts WHERE id=1')[0]
            assert stored == {'name': 'main', 'claude_code_version': '2.1.303'}, stored
            assert backend.client.get('/api/accounts/1/cli-settings').json()['display_name'] == '团队账号 <安全显示>'
            await root.locator('[data-cli-settings]').click()
            await expect(save).to_be_enabled()
            await modal.locator('summary').click()
            await modal.locator('#cli-settings-process').click()
            await expect(modal.locator('#cli-settings-feedback')).to_contain_text('进程指标')
            assert fixture.process_writes == 1
            for width in [1440, 720, 390]:
                await page.set_viewport_size({'width': width, 'height': 1000})
                assert await modal.locator('.modal-card').evaluate('e=>e.scrollWidth<=e.clientWidth')
                await page.screenshot(path=str(output / f'config-{width}.png'))
            # 任务宿主跟随主题模式：系统浅色、未保存模式时文档根为浅色。
            assert await page.locator('html').get_attribute('data-ui-scheme') == 'light'
            colors = await modal.evaluate("""e=>['.field','.work-note','summary','.work-account-links button','input'].map(selector=>{
                const node=e.querySelector(selector),s=getComputedStyle(node);
                return {selector,color:s.color,background:selector==='input'?s.backgroundColor:getComputedStyle(e.querySelector('.modal-card')).backgroundColor};
            })""")
            assert all(contrast(item['color'], item['background']) >= 4.5 for item in colors), colors
            await page.screenshot(path=str(output / 'config-saved-dark.png'))
            await modal.locator('#cli-settings-environment').click()
            await expect(page.locator('.runtime-environment-dialog')).to_be_visible()
            await expect(modal).to_be_hidden()
            assert page.url == BASE + '/tasks'
            await page.get_by_role('button', name='关闭环境详情').click()
            await root.locator('[data-cli-settings]').click()
            await expect(save).to_be_enabled()
            await modal.locator('#cli-settings-gateway').click()
            await expect(page.get_by_role('dialog', name='切换代理 · 团队账号 <安全显示>', exact=True)).to_be_visible()
            assert page.url == BASE + '/tasks'
            await page.keyboard.press('Escape')
            fixture.config_gate = asyncio.Event()
            fixture.config_started.clear()
            await root.locator('[data-cli-settings]').click()
            await fixture.config_started.wait()
            await modal.get_by_role('button', name='取消', exact=True).click()
            fixture.config_gate.set()
            await page.wait_for_load_state('networkidle')
            await expect(modal).to_be_hidden()
            assert len(fixture.config_writes) == 1, fixture.config_writes
            assert not errors, errors
            (output / 'verification.json').write_text(json.dumps({'style_differences': differences,
                'config_writes': fixture.config_writes, 'process_writes': fixture.process_writes,
                'errors': errors}, ensure_ascii=False, indent=2))
            assert not differences, differences
            print('任务账号配置：第二版外观、真实 API/SQLite、草稿层级、路由保持、维护操作和迟到响应验证通过')
            await browser.close()
    finally:
        backend.doCleanups()


if __name__ == '__main__':
    asyncio.run(main())
