"""用真实浏览器和合成接口验证双版本原生内核管理。"""
import asyncio
import copy
import json
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import async_playwright, expect

from verify_native_diagnostics_cpu import DiagnosticsCpuFixture
from verify_environment_ui import BASE, ROOT


class VersionFixture(DiagnosticsCpuFixture):
    """保留历史293夹具，新增独立280内核及迟到发行回执。"""

    def __init__(self):
        """创建独立双版本状态。@return None。"""
        super().__init__(ROOT / 'apps/web/dist', '2.1.280')
        row = self.rows[0]
        kernel = copy.deepcopy(row['native_kernel'])
        kernel.update(source_version='2.1.280', revision='280:initial')
        kernel['current']['release'] = 'builtin-2.1.280'
        row['native_kernels'] = {'2.1.280': kernel, '2.1.293': row['native_kernel']}
        row['native_preparation']['versions'] = {
            '2.1.280': {'state': 'unknown', 'reason': 'runtime_unavailable'},
            '2.1.293': copy.deepcopy(row['native_preparation'])}
        self.release_gate = asyncio.Event()
        self.release_started = asyncio.Event()
        self.hold_release = False

    async def route(self, route):
        """按实际请求版本分派，验证280独立CAS。@param route 浏览器请求。@return None。"""
        parsed = urlsplit(route.request.url)
        if parsed.path.endswith('/native-kernel/releases'):
            version = parse_qs(parsed.query).get('source_version', ['2.1.293'])[0]
            if version == '2.1.280' and self.hold_release:
                self.release_started.set()
                await self.release_gate.wait()
            release = 'v0.1.0-beta.' + version.rsplit('.', 1)[1]
            await route.fulfill(content_type='application/json', body=json.dumps({
                'state': 'ready', 'latest': release, 'versions': [{'release': release}]}))
            return
        if parsed.path.endswith('/native-kernel') and route.request.method == 'POST':
            body = route.request.post_data_json
            if body['source_version'] == '2.1.280':
                kernel = self.rows[0]['native_kernels']['2.1.280']
                assert body['expected_revision'] == kernel['revision']
                self.writes.append({'path': parsed.path, 'body': body})
                kernel['revision'] = '280:prepared'
                await route.fulfill(content_type='application/json', body=json.dumps(kernel))
                return
        await super().route(route)


async def run():
    """覆盖版本冻结、旧响应、部分就绪及移动端。@return 安全验收摘要。"""
    fixture, errors = VersionFixture(), []
    output = ROOT / '.deploy/native-runtime-280/browser'
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
        selector = workspace.get_by_role('combobox', name='原生运行时版本')

        async def select(version):
            """沿公开控件切换。@param version 官方版本。@return None。"""
            await selector.click()
            await page.get_by_role('option', name='Claude Code ' + version, exact=True).click()

        await expect(selector).to_contain_text('2.1.293')
        await select('2.1.280')
        await expect(workspace.locator('.kernel-version strong')).to_have_text('builtin-2.1.280')
        fixture.hold_release = True
        await workspace.get_by_role('button', name='检查更新', exact=True).click()
        await fixture.release_started.wait()
        await select('2.1.293')
        await workspace.get_by_role('button', name='检查更新', exact=True).click()
        await expect(workspace).to_contain_text('最新发现版本：v0.1.0-beta.293')
        fixture.release_gate.set()
        await page.wait_for_timeout(100)
        await expect(workspace).not_to_contain_text('最新发现版本：v0.1.0-beta.280')
        fixture.hold_release = False
        await select('2.1.280')
        selector_node = await selector.element_handle()
        await workspace.get_by_role('button', name='选择版本', exact=True).click()
        dialog = page.get_by_role('dialog', name='准备内核', exact=True)
        await expect(dialog).to_contain_text('2.1.280')
        assert await selector_node.is_disabled()
        await expect(dialog.get_by_role('button', name='准备内核', exact=True)).to_be_enabled()
        await dialog.get_by_role('button', name='准备内核', exact=True).click()
        await expect(dialog).to_have_count(0)
        assert fixture.writes[-1]['body']['source_version'] == '2.1.280'
        assert fixture.writes[-1]['body']['expected_revision'] == '280:initial'
        assert fixture.rows[0]['native_kernel']['revision'] == '10:initial'
        await workspace.get_by_role('tab', name='运行概览', exact=True).click()
        await workspace.get_by_text('运行组件与准备详情', exact=True).click()
        await expect(workspace).to_contain_text('2.1.280 运行时')
        await expect(workspace).to_contain_text('此版本的准备状态暂不可用')
        for theme in ('light', 'dark'):
            await page.evaluate("value=>document.documentElement.classList.toggle('dark',value==='dark')", theme)
            for width in (1280, 390):
                await page.set_viewport_size({'width': width, 'height': 1000})
                assert await workspace.evaluate('node=>node.scrollWidth<=node.clientWidth')
                await page.screenshot(path=str(output / f'{theme}-{width}.png'))
        await workspace.get_by_role('button', name='关闭环境详情').click()
        await page.goto(BASE + '/requests')
        await page.get_by_role('button', name='详情', exact=True).click()
        await page.get_by_role('button', name='阶段证据', exact=True).first.click()
        await expect(page.locator('[data-native-stages] .request-stages article')).to_have_count(4)
        assert not fixture.unexpected, fixture.unexpected
        assert not errors, errors
        await browser.close()
    return {'passed': True, 'checks': ['版本选择', '280独立CAS与293状态隔离', '旧发行回执失效', '部分就绪', '明暗390/1280px', '280诊断阶段入口'], 'errors': errors}


if __name__ == '__main__':
    print(json.dumps(asyncio.run(run()), ensure_ascii=False))
