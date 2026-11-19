"""以真实前端验证运行时版本优先级、旧端兼容及请求生命周期。"""
import asyncio
import json
import subprocess
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_dashboard_update import DashboardUpdateFixture
from verify_environment_ui import BASE, ROOT


class RuntimeVersionFixture(DashboardUpdateFixture):
    """提供独立于更新器的控制版本场景。"""

    def __init__(self, scenario):
        """初始化只读场景。@param scenario 场景名。@return None。"""
        super().__init__(scenario)
        self.version_reads = 0
        self.session_ready = False
        self.session_started = asyncio.Event()
        self.session_gate = asyncio.Event()
        self.early_reads = []
        if scenario != 'unmount':
            self.session_gate.set()

    async def route(self, route):
        """托管版本及更新状态接口。@param route 拦截请求。@return None。"""
        path = urlsplit(route.request.url).path
        if path == '/admin/runtime/session':
            assert route.request.method == 'POST'
            self.sessions += 1
            self.session_started.set()
            await self.session_gate.wait()
            if self.scenario == 'session-failure':
                return await self.respond(route, {'error': '合成会话签发失败'}, 503)
            if self.scenario == 'delayed':
                await asyncio.sleep(0.3)
            self.session_ready = True
            return await self.respond(route, {'ok': True})
        if path.startswith('/runtime/api/') and not self.session_ready:
            self.early_reads.append(path)
            return await self.respond(route, {'error': '合成管理会话缺失'}, 401)
        if path == '/runtime/api/system-updates/version':
            self.version_reads += 1
            if self.scenario.startswith('old'):
                return await self.respond(route, {'error': '旧端接口'}, 404)
            value = None if self.scenario == 'null' else 'invalid' if self.scenario == 'invalid' else 'v1.17.2'
            return await self.respond(route, {'version': value})
        if path == '/runtime/api/system-updates/status':
            if self.scenario == 'offline':
                return await self.respond(route, {'error': '更新器暂不可用'}, 503)
            return await self.respond(route, {'installed': self.scenario != 'uninstalled',
                'current_release': self.current, 'busy': True, 'message': '更新器待接入'})
        if path == '/runtime/api/system-updates/releases':
            self.catalog_reads += 1
            releases = [self.releases[0]] if self.scenario in ('missing-current', 'old-missing') else self.releases
            return await self.respond(route, {'fresh': True, 'releases': releases, 'checking': False})
        return await super().route(route)


async def verify_lifecycle(browser):
    """验证真实组合函数取消旧读、隔离实例及丢弃卸载回执。@param browser 浏览器。@return 通过标识。"""
    # 直接转译实际源码，延迟响应忽略网络取消，用于确定性验证应用层回执归属。
    sources = ['apps/web/src/api.ts', 'apps/web/src/lib/platformVersion.ts',
        'apps/web/src/composables/usePlatformVersion.ts']
    script = "const ts=require('./apps/web/node_modules/typescript');const fs=require('fs');process.stdout.write(JSON.stringify(process.argv.slice(1).map(p=>ts.transpileModule(fs.readFileSync(p,'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText)))"
    compiled = json.loads(subprocess.check_output(['node', '-e', script, *sources], cwd=ROOT, text=True))
    modules = dict(zip(['/api', '/lib/platformVersion', '/composables/usePlatformVersion'], compiled))
    modules['/vue'] = (ROOT / 'apps/web/node_modules/vue/dist/vue.esm-browser.js').read_text()
    context = await browser.new_context()

    async def route(request):
        """只服务实际模块和本地验证页。@param request 拦截路由。@return None。"""
        path = urlsplit(request.request.url).path
        if path in modules:
            return await request.fulfill(body=modules[path], content_type='application/javascript')
        return await request.fulfill(body='<script type="importmap">{"imports":{"vue":"/vue"}}</script>', content_type='text/html')

    await context.route('**/*', route)
    page = await context.new_page()
    await page.goto(BASE)
    result = await page.evaluate("""async () => {
      const {api} = await import('/api');
      const {usePlatformVersion} = await import('/composables/usePlatformVersion');
      const pending = [];
      api.systemPlatformVersion = signal => new Promise((resolve, reject) => pending.push({signal, resolve, reject}));
      const check = (value, message) => {if (!value) throw new Error(message);};
      const lifecycle = new AbortController();
      const first = usePlatformVersion(), second = usePlatformVersion();
      const oldRead = first.refresh(lifecycle.signal), newRead = first.refresh(lifecycle.signal);
      check(pending[0].signal.aborted, '旧读应被取消');
      pending[1].resolve({version:'v2.0.0'}); await newRead;
      pending[0].resolve({version:'v1.0.0'}); await oldRead;
      check(first.version.value === 'v2.0.0', '迟到旧读覆盖版本');
      const independent = second.refresh(lifecycle.signal);
      pending[2].resolve({version:'v3.0.0'}); await independent;
      check(first.version.value === 'v2.0.0' && second.version.value === 'v3.0.0', '视图实例应独立');
      const unmounted = first.refresh(lifecycle.signal); lifecycle.abort();
      check(pending[3].signal.aborted, '卸载应取消请求');
      pending[3].resolve({version:'v9.0.0'}); await unmounted;
      check(first.version.value === 'v2.0.0', '卸载回执改变状态');
      const before = pending.length; await first.refresh(lifecycle.signal);
      check(pending.length === before, '卸载后应停止读取');
      for (const value of [null, 'invalid', 'v01.0.0', 'v1.2.3\\n', 'v１.2.3']) {
        const read = second.refresh(new AbortController().signal);
        pending.at(-1).resolve({version:value}); await read;
        check(second.version.value === null, '非法响应应回退');
      }
      const failed = second.refresh(new AbortController().signal);
      pending.at(-1).reject(new Error('合成接口失败')); await failed;
      check(second.version.value === null, '失败应回退');
      return true;
    }""")
    await context.close()
    return result


async def main():
    """覆盖两个实际展示入口与组合函数生命周期。@return None。"""
    scenes = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        for scenario in ('runtime', 'delayed', 'missing-current', 'uninstalled', 'offline', 'old', 'null', 'invalid', 'old-missing', 'session-failure', 'unmount'):
            fixture = RuntimeVersionFixture(scenario)
            context = await browser.new_context(viewport={'width': 1280, 'height': 900})
            await context.route('**/*', fixture.route)
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(error.message))
            await page.goto(BASE)
            expected = 'v1.0.0' if scenario in ('old', 'null', 'invalid') else 'v1.17.2'
            sidebar = page.locator('.console-sidebar .brand-update')
            await fixture.session_started.wait()
            if scenario == 'unmount':
                await page.get_by_role('button', name='退出', exact=True).click()
                await expect(page).to_have_url(BASE + '/login')
                fixture.session_gate.set()
                await page.wait_for_timeout(500)
                assert fixture.version_reads == fixture.catalog_reads == 0
                assert not fixture.early_reads, fixture.early_reads
                assert not errors, errors
                scenes.append(scenario)
                await context.close()
                continue
            await expect(sidebar).to_contain_text('版本' if scenario in ('old-missing', 'session-failure') else expected)
            await page.goto(BASE + '/updates')
            if scenario == 'session-failure':
                await expect(page.get_by_role('alert')).to_contain_text('合成会话签发失败')
                assert fixture.version_reads == fixture.catalog_reads == 0
            elif scenario in ('uninstalled', 'offline'):
                await expect(page.get_by_text('当前版本：' + expected, exact=True)).to_be_visible()
                assert fixture.catalog_reads == 0
            else:
                await expect(page.locator('.approved-platform dd').first).to_have_text('历史构建' if scenario == 'old-missing' else expected)
            if scenario != 'session-failure':
                assert fixture.version_reads >= 2
            assert fixture.sessions >= 1
            assert not fixture.early_reads, fixture.early_reads
            assert not fixture.writes, fixture.writes
            assert not fixture.unexpected, fixture.unexpected
            assert not errors, errors
            scenes.append(scenario)
            await context.close()
        lifecycle = await verify_lifecycle(browser)
        await browser.close()
    print(json.dumps({'passed': True, 'scenes': scenes, 'lifecycle': lifecycle, 'real_model_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
