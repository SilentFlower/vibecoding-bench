"""以真实账号配置 API 和独立 SQLite 验证原生任务配置及原型计算样式。"""
import asyncio
import json
import re
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from test_account_cli_settings import AccountCliSettingsTests
from verify_environment_ui import BASE, ROOT
from verify_task_feedback import TaskFeedbackFixture


def contrast(foreground, background):
    """计算文字与背景对比度。@param foreground 前景RGB。@param background 背景RGB。@return 对比度。"""
    def luminance(value):
        """计算线性相对亮度。@param value CSS颜色。@return 亮度。"""
        channels = [int(channel) / 255 for channel in re.findall(r'\d+', value)[:3]]
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
    """验证保存、取消、子窗草稿、局部路由、迟到响应和原型一致性。@return 无。"""
    backend = AccountCliSettingsTests()
    backend.setUp()
    output = ROOT / '.deploy/frontend-sidebar-refresh/task-account-config'
    output.mkdir(parents=True, exist_ok=True)
    fixture = AccountConfigFixture(backend)
    differences, errors = {}, []
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
            await context.route('**/*', fixture.route)
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','dark')")
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
            reference = await browser.new_page(viewport={'width': 1440, 'height': 1000})
            await reference.goto((ROOT / 'doc/design/flower2api-concept.html').as_uri())
            await reference.evaluate("navigate('tasks');taskTab='accounts';repaintWork();configureWorkAccount(101)")
            await reference.evaluate('document.fonts.ready')
            await page.evaluate('document.fonts.ready')
            box_keys = ['width', 'padding', 'borderWidth', 'borderRadius']
            box_script = '(e,keys)=>{const s=getComputedStyle(e);return Object.fromEntries(keys.map(k=>[k,s[k]]))}'
            expected_box = await reference.locator('dialog[open]').evaluate(box_script, box_keys)
            actual_box = await modal.locator('.modal-card').evaluate(box_script, box_keys)
            differences['弹窗'] = {key: [expected_box[key], actual_box[key]] for key in box_keys if expected_box[key] != actual_box[key]}
            keys = ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'padding', 'margin', 'gap', 'color', 'borderRadius']
            for label, left, right in [('标题', 'h2', '#cli-settings-title'), ('内容', '.dialog-body', '.dialog-body'),
                    ('标签', '.field', '.field'), ('输入框', '[name=name]', '[name=display_name]'),
                    ('操作', '.work-account-links', '.work-account-links'), ('页脚', '.work-form-footer', '.work-form-footer'),
                    ('维护', '.work-advanced-maintenance', '.work-advanced-maintenance'),
                    ('保存按钮', 'button[type=submit]', 'button[type=submit]'),
                    ('快捷操作', '.work-account-links button', '.work-account-links button')]:
                script = '(e,keys)=>{const s=getComputedStyle(e);return Object.fromEntries(keys.map(k=>[k,s[k]]))}'
                expected = await reference.locator('dialog[open]').locator(left).first.evaluate(script, keys)
                observed = await modal.locator(right).first.evaluate(script, keys)
                differences[label] = {key: [expected[key], observed[key]] for key in keys if expected[key] != observed[key]}
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
            assert await root.get_attribute('data-theme') == 'light'
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
            assert all(not value for value in differences.values()), differences
            print('任务账号配置：原型样式、真实 API/SQLite、草稿层级、路由保持、维护操作和迟到响应验证通过')
            await browser.close()
    finally:
        backend.doCleanups()


if __name__ == '__main__':
    asyncio.run(main())
