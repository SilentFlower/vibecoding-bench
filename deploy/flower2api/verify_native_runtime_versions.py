"""用真实浏览器验证单版内核在新旧环境回执中的只读展示。"""
import asyncio
import copy
import json
from urllib.parse import urlsplit
from playwright.async_api import async_playwright, expect
from verify_native_diagnostics_cpu import DiagnosticsCpuFixture
from verify_environment_ui import BASE, ENVIRONMENT, ROOT


class VersionFixture(DiagnosticsCpuFixture):
    """沿真实环境接口提供双版内置及独立准备观察。"""

    def __init__(self, gateway=None):
        """初始化合成版本身份。@param gateway 独立前端产物目录。@return None。"""
        super().__init__(gateway or ROOT / 'apps/web/dist', '2.1.280')
        self.kernel_requests = []
        row = self.rows[0]
        kernel = copy.deepcopy(row['native_kernel'])
        kernel.update(management='platform', source_version='2.1.280', state='builtin', platform_release='synthetic-platform')
        kernel['builtin'] = {'release': 'builtin-2.1.280', 'launcher_sha256': 'b' * 64}
        row['native_kernel'].update(management='platform', state='builtin', platform_release='synthetic-platform')
        row['native_kernel']['builtin'] = {'release': 'v0.1.0-beta.7', 'launcher_sha256': 'a' * 64}
        row['native_kernels'] = {'2.1.280': kernel, '2.1.293': row['native_kernel']}
        row['native_preparation']['versions'] = {
            '2.1.280': {'state': 'unknown', 'reason': 'runtime_unavailable'},
            '2.1.293': copy.deepcopy(row['native_preparation'])}

    async def route(self, route):
        """记录退役入口的意外调用。@param route 浏览器请求。@return None。"""
        if '/native-kernel' in urlsplit(route.request.url).path:
            self.kernel_requests.append(route.request.url)
            await route.fulfill(status=410, content_type='application/json', body='{"detail":"平台统一管理"}')
            return
        await super().route(route)


async def run(gateway=None, output=None):
    """验证只读内核身份和移动布局。@param gateway 前端产物目录。@param output 截图目录。@return 验收摘要。"""
    fixture, errors = VersionFixture(gateway), []
    output = output or ROOT / '.deploy/native-kernel-platform-managed/browser'
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1280, 'height': 1000}, service_workers='block')
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(BASE + '/environments')
        await page.locator('.environment-rich').first.get_by_role('button', name='请求内核', exact=True).click()
        workspace = page.locator('.runtime-environment-dialog')
        await expect(workspace).to_contain_text('随 flower2api 版本统一交付')
        await expect(workspace).to_contain_text('内置内核版本')
        await expect(workspace).not_to_contain_text('bbbbbbbbbbbb')
        await expect(workspace).to_contain_text('aaaaaaaaaaaa')
        await expect(workspace).not_to_contain_text('v0.1.0-beta.7')
        await expect(workspace).not_to_contain_text('builtin-2.1.280')
        await expect(workspace).not_to_contain_text('准备候选')
        await workspace.locator('.environment-kernel .runtime-technical summary').first.click()
        await expect(workspace.locator('.environment-kernel .runtime-technical code').first).to_have_text('a' * 64)
        await expect(workspace).to_contain_text('Claude Code 2.1.293')
        for label in ('检查更新', '选择版本', '激活候选', '回滚内核', '恢复对账'):
            await expect(workspace.get_by_role('button', name=label, exact=True)).to_have_count(0)
        cc280 = workspace.get_by_role('region', name='Claude Code 2.1.280 内核')
        await expect(cc280).to_have_count(0)
        for theme in ('light', 'dark'):
            await page.evaluate("value=>document.documentElement.classList.toggle('dark',value==='dark')", theme)
            for width in (1280, 390):
                await page.set_viewport_size({'width': width, 'height': 1000})
                # 等待窗口缩放动画收敛，再核对实际视口边界与内容宽度。
                await expect(workspace).to_have_css('width', f'{390 if width == 390 else 940}px')
                box = await workspace.bounding_box()
                assert box and box['x'] >= 0 and box['x'] + box['width'] <= width
                assert await workspace.evaluate('node=>node.scrollWidth<=node.clientWidth')
                await page.screenshot(path=str(output / f'{theme}-{width}.png'))
        await workspace.get_by_role('button', name='关闭环境详情').click()
        await page.goto(BASE + '/runtime/?view=environments#environments')
        await page.locator('[data-env-open="kernel"]').first.click()
        legacy = page.locator('#environment-workspace')
        await expect(legacy).to_contain_text('随平台版本交付')
        await expect(legacy).to_contain_text('Claude Code 2.1.293（平台内置）')
        await expect(legacy).not_to_contain_text('2.1.280')
        await expect(legacy).to_contain_text('aaaaaaaaaaaa')
        await expect(legacy).not_to_contain_text('bbbbbbbbbbbb')
        await expect(legacy).not_to_contain_text('v0.1.0-beta.7')
        await expect(legacy).not_to_contain_text('builtin-2.1.280')
        await expect(legacy.locator('[data-kernel-action], [data-kernel-check]')).to_have_count(0)
        row = fixture.rows[0]
        row.update(gateway_account_id=12, runtime_release='synthetic-account', cli_versions=['2.1.293', '2.1.321'],
            role_status={'cli': 'running', 'sender': 'exited', 'network': '缺失'},
            tui_runtime={'ready': True, 'idle': True, 'direct': False})
        for backend, label in (('tui_v2', '交互运行时 V2'), ('legacy', '原有转发'),
                               ('native293', '原生运行时 V1'), (None, '未观测')):
            row['request_backend'] = backend
            await page.goto(BASE + '/environments')
            card = page.locator('.environment-rich').first
            await expect(card.locator('.environment-version-line button')).to_contain_text(label)
            await card.get_by_role('button', name='请求内核', exact=True).click()
            await expect(workspace.locator('.workspace-panel-context')).to_contain_text('网关账号 #12 · 第 10 代')
            kernel = workspace.get_by_role('tabpanel', name='请求内核', exact=True)
            await expect(kernel.locator('.kernel-version').first.locator('strong')).to_have_text(label)
            await expect(kernel.get_by_role('region', name='Claude Code 2.1.293 内核')).to_have_count(int(backend == 'native293'))
            await expect(kernel.get_by_text('兼容发送', exact=True)).to_have_count(int(backend == 'tui_v2'))
            for section in ('请求内核', '运行概览'):
                await workspace.get_by_role('tab', name=section, exact=True).click()
                pane = workspace.get_by_role('tabpanel', name=section, exact=True)
                basic = pane.get_by_role('region', name='基本信息')
                for value in (ENVIRONMENT, '2.1.293 / 2.1.321', 'synthetic-account', '运行中', '已退出', '缺失'):
                    await expect(basic).to_contain_text(value)
        assert not fixture.kernel_requests, fixture.kernel_requests
        assert not fixture.writes, fixture.writes
        assert not errors, errors
        await browser.close()
    return {'passed': True, 'checks': ['平台内置版本与制品摘要', '独立操作退役零请求', '旧双版回执只展示 293', '独立兼容入口只读', '已生效的后端与未知状态文案', '明暗390/1280px'], 'errors': errors}


if __name__ == '__main__':
    print(json.dumps(asyncio.run(run()), ensure_ascii=False))
