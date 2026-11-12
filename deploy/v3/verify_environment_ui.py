"""用合成接口验证真实环境页面；阻断所有实际网络和模型请求。"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import mimetypes
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://environment-ui.test'
OLD_SHA = 'a' * 64
NEW_SHA = 'b' * 64
ENVIRONMENT = '1' * 32


def sample_rows() -> list[dict]:
    """生成按现有公开字段组织的环境样例。@return 四种环境及单账号内核试点。"""
    row = {'environment_id': ENVIRONMENT, 'name': '演示环境 A', 'account_id': 1, 'generation': 10,
        'state': 'ready', 'busy': False, 'fingerprint': {'tz': 'America/Los_Angeles', 'mem': 'unlimited',
            'hostname': 'demo-machine', 'lang': 'en_US.UTF-8', 'profile_version': 1},
        'identity_status': '已确认 CLI 本地设备身份', 'cli_versions': ['2.1.293'],
        'role_status': {'cli': 'running', 'network': 'running', 'sender': 'running'},
        'can_reprofile': False, 'reprofile_message': '已有运行历史，保留原画像。',
        'run_window': {'timezone': 'America/Los_Angeles', 'server_now': time.time(),
            'message': '全天可运行', 'next_open_at': None, 'next_close_at': None,
            'config': {'enabled': False, 'days': [0, 1, 2, 3, 4], 'intervals': [{'start': '09:00', 'end': '18:00'}]}},
        'physical_features': {'message': '上次采集快照', 'observed_at': time.time(), 'fields': [
            {'key': 'ram_bytes', 'label': '容器 RAM 上限', 'configured': 0, 'observed': 0, 'status': 'match'},
            {'key': 'cpu', 'label': 'CPU 型号', 'configured': None, 'observed': None, 'status': 'unobserved'}]},
        'native_preparation': {'state': 'ready', 'idle_workers': 1, 'live_workers': 1,
            'pid': 27, 'checked_at_ms': int(time.time() * 1000)},
        'content_capture': {'enabled': True, 'applied': True, 'supported': True,
            'generation': 10, 'revision': 'a'*64,
            'tls_observer': {'state': 'ready', 'reason': None, 'protocol_version': 1}},
        'native_kernel': {'state': 'active', 'revision': '10:initial',
            'current': {'release': 'v0.1.0-beta.3', 'launcher_sha256': OLD_SHA},
            'prepared': {'release': 'v0.1.0-beta.4', 'launcher_sha256': NEW_SHA},
            'previous': {'release': 'v0.1.0-beta.4', 'launcher_sha256': NEW_SHA},
            'pid': 27, 'image_sha256': OLD_SHA, 'error': None}}
    rows = [row]
    for number, status in [(2, 'ready'), (3, 'stopped'), (4, 'future-state')]:
        other = copy.deepcopy(row)
        other.update(environment_id=str(number) * 32, name=f'演示环境 {number}', account_id=number,
            state=status, native_kernel=None, native_preparation=None)
        if status != 'ready':
            other['role_status'] = {'cli': 'exited', 'network': 'missing', 'sender': 'exited'}
        rows.append(other)
    return rows


class Fixture:
    """托管合成 API 与真实静态资源。所有浏览器请求都在本进程内完成。"""

    def __init__(self, gateway: Path) -> None:
        """初始化夹具。@param gateway 网关静态产物。@return None。"""
        self.gateway = gateway
        self.rows = sample_rows()
        self.writes: list[dict] = []
        self.sessions = 0
        self.reads = 0
        self.revision = 0
        self.fail_read = False
        self.fail_operation = False
        self.operation_gate: asyncio.Event | None = None
        self.operation_started = asyncio.Event()
        self.hold_next_read = False
        self.read_gate = asyncio.Event()
        self.read_started = asyncio.Event()
        self.unexpected: list[str] = []
        self.external: list[str] = []

    async def route(self, route) -> None:
        """在网络前拦截全部资源及接口。@param route 浏览器路由。@return None。"""
        request = route.request
        parsed = urlsplit(request.url)
        if parsed.netloc != 'environment-ui.test':
            # 字体及终端 CDN 在合成场景中不加载，页面按钮不会连接 OAuth 或模型。
            self.external.append(parsed.netloc)
            await route.fulfill(status=200, body='')
            return
        path = parsed.path
        payload: dict | list = {}
        status = 200
        if path == '/admin/dashboard':
            payload = {'accounts': {'total': 0, 'active': 0, 'error': 0, 'disabled': 0}, 'tokens': {'total': 0}}
        elif path == '/admin/runtime/session':
            assert request.method == 'POST'
            self.sessions += 1
            payload = {'ok': True}
        elif path == '/admin/settings':
            payload = {'request_diagnostics_log_mode': 'info'}
        elif path.startswith('/admin/request-diagnostics'):
            root = {'request_id': '11111111-1111-4111-8111-111111111111', 'started_at': '2026-11-12T00:00:00Z',
                'status_code': 200, 'account_id': 1, 'outcome': 'success', 'attempt_count': 2, 'log_mode': 'info'}
            if path == '/admin/request-diagnostics':
                payload = {'items': [root], 'total': 1, 'health': {}}
            else:
                attempt = {'attempt_id': '22222222-2222-4222-8222-222222222222', 'account_id': 1,
                    'ordinal': 1, 'profile_selection': 'native293_cc_prepared', 'status_code': 200,
                    'outcome': 'success', 'log_mode': 'info', 'capture_status': 'disabled'}
                legacy = dict(attempt, ordinal=2, attempt_id='33333333-3333-4333-8333-333333333333')
                attempt['runtime'] = {'worker_id': '44444444-4444-4444-8444-444444444444', 'worker_pid': 27,
                    'kernel_generation': None, 'warm_hit': True, 'preparation_wait_ms': 0, 'checkout_ms': 1,
                    'worker_start_ms': None, 'prepared_ms': 185}
                payload = {'request': root, 'attempts': [attempt, legacy]}
        elif '/api/' in path:
            api = path.split('/api/', 1)[1]
            if request.method != 'GET':
                body = json.loads(request.post_data or '{}')
                self.writes.append({'path': path, 'body': body})
                if api.endswith('/content-capture'):
                    current = self.rows[0]['content_capture']
                    if body['expected_generation'] != current['generation'] or body['expected_revision'] != current['revision']:
                        status, payload = 409, {'detail': '采集配置已变化，请重新读取'}
                    else:
                        self.revision += 1
                        current.update(enabled=body['enabled'], revision=str(self.revision)*64,
                            tls_observer={'state': 'preparing' if body['enabled'] else 'disabled', 'reason': None})
                        payload = copy.deepcopy(current)
                elif api.endswith('/native-kernel'):
                    kernel = self.rows[0]['native_kernel']
                    self.operation_started.set()
                    if self.operation_gate:
                        await self.operation_gate.wait()
                    if self.fail_operation or body['expected_revision'] != kernel['revision']:
                        status, payload = 409, {'detail': '内核状态已变更，请刷新后重新操作'}
                    else:
                        self.revision += 1
                        kernel['revision'] = f'10:revision-{self.revision}'
                        if body['operation'] in ('activate', 'rollback'):
                            target = kernel['prepared'] if body['operation'] == 'activate' else kernel['previous']
                            kernel['previous'], kernel['current'] = kernel['current'], target
                        kernel['state'] = 'active'
                        payload = copy.deepcopy(kernel)
                elif api.endswith('/physical-features/refresh') or api.endswith('/maintenance'):
                    payload = {'ok': True}
                elif api.endswith('/run-window') and request.method == 'PUT':
                    self.rows[0]['run_window']['config'] = body
                    payload = self.rows[0]['run_window']
                else:
                    self.unexpected.append(request.method + ' ' + path)
                    status, payload = 400, {'detail': '夹具拒绝额外写入'}
            elif api == 'environments':
                self.reads += 1
                payload = copy.deepcopy(self.rows)
                if self.hold_next_read:
                    self.hold_next_read = False
                    self.read_started.set()
                    await self.read_gate.wait()
                if self.fail_read:
                    status, payload = 503, {'detail': '合成读取故障'}
            elif api.endswith('/content-capture'):
                payload = copy.deepcopy(self.rows[0]['content_capture'])
            elif api.endswith('/run-window'):
                payload = self.rows[0]['run_window']
            elif api in ('accounts', 'accounts/login-drafts', 'topics', 'task-batches'):
                payload = []
            elif api == 'auth/me':
                payload = {'user': '合成验证', 'authenticated': True}
            else:
                self.unexpected.append(request.method + ' ' + path)
                status, payload = 404, {'detail': '未定义的合成接口'}
        else:
            if path.startswith('/runtime/'):
                filename = path.removeprefix('/runtime/') or 'index.html'
                directory = ROOT / 'webui'
            elif path in ('/', '/environments', '/tasks', '/requests', '/updates'):
                directory, filename = self.gateway, 'index.html'
            else:
                directory, filename = self.gateway, path.lstrip('/')
            resource = (directory / filename).resolve()
            assert resource.is_relative_to(directory.resolve()) and resource.is_file(), str(resource)
            await route.fulfill(path=str(resource), content_type=mimetypes.guess_type(resource)[0] or 'application/octet-stream')
            return
        await route.fulfill(status=status, content_type='application/json', body=json.dumps(payload))


async def run(output: Path, gateway: Path) -> dict:
    """执行浏览器验收。@param output 证据目录。@param gateway 网关静态产物。@return 验收报告。"""
    from playwright.async_api import async_playwright, expect

    scenes: list[str] = []
    errors: list[str] = []
    fixture = Fixture(gateway)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1280, 'height': 1000})
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','dark');")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            # 真实网关产物负责外层路由、导航及 iframe，认证接口只返回合成会话。
            await page.goto(BASE + '/environments')
            frame = page.frame_locator('iframe')
            await page.get_by_role('link', name='环境', exact=True).click()
            await expect(frame.locator('.env-card')).to_have_count(4)
            target = frame.locator('.env-card').filter(has=frame.get_by_role('heading', name='演示环境 A', exact=True))
            await expect(target).to_be_visible()
            assert fixture.sessions == 1 and not fixture.writes
            assert not fixture.unexpected, fixture.unexpected
            scenes.append('真实网关导航和统一会话嵌入；首屏只读')
            await frame.locator('.env-page-head p').evaluate("node=>node.textContent+=' · 合成验证，无真实模型调用'")

            async def refresh() -> None:
                """模拟只读状态刷新。@return 当前快照完成。"""
                await frame.locator('#environment-refresh').click()
                await expect(frame.locator('#environment-refresh')).to_be_enabled()

            async def open_operation(label: str) -> None:
                """通过真实按钮打开操作窗口。@param label 按钮文字。@return 窗口可见。"""
                await target.get_by_role('button', name=label, exact=True).click()
                await expect(frame.locator('#native-kernel-modal')).to_be_visible()

            async def submit_operation(label: str) -> None:
                """通过真实表单提交。@param label 动作文字。@return 操作及刷新完成。"""
                await frame.locator('#native-kernel-form').get_by_role('button', name=label, exact=True).click()
                await expect(frame.locator('#native-kernel-modal')).to_be_hidden()
                await expect(frame.locator('#environment-refresh')).to_be_enabled()

            # 两个原生环境均提供管理入口，打开第二个账号的窗口必须保持其独立归属。
            fixture.rows[1]['native_kernel'] = copy.deepcopy(fixture.rows[0]['native_kernel'])
            fixture.rows[1]['native_kernel']['revision'] = '11:second-account'
            await refresh()
            other = frame.locator('.env-card').filter(has=frame.get_by_role('heading', name='演示环境 2', exact=True))
            await expect(frame.locator('.env-tag').filter(has_text='在线内核管理')).to_have_count(2)
            await other.get_by_role('button', name='准备内核', exact=True).click()
            await expect(frame.locator('#native-kernel-account')).to_have_text('演示环境 2')
            await frame.locator('#native-kernel-modal').get_by_role('button', name='取消', exact=True).click()
            assert not fixture.writes
            scenes.append('两个原生账号均显示在线管理，第二账号窗口保持独立归属且取消零写入')

            for width in (1280, 720, 390):
                await page.set_viewport_size({'width': width, 'height': 1000 if width > 390 else 844})
                for theme in ('dark', 'light'):
                    await frame.locator('html').evaluate('(node,theme)=>node.dataset.theme=theme', theme)
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert await frame.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
                    assert (await frame.locator('body').evaluate('node=>getComputedStyle(node).backgroundColor')).startswith('oklch(0.995')
                    assert await target.evaluate('node=>getComputedStyle(node).backgroundColor') == 'rgb(255, 255, 255)'
                    await page.screenshot(path=str(output / f'environments-{width}-{theme}.png'), full_page=True)
            scenes.append('1280/720/390px，原明暗偏好下与主后台色板一致且无溢出')
            await page.set_viewport_size({'width': 1280, 'height': 1000})

            search = frame.locator('#environment-search')
            await search.fill('演示环境 A')
            await expect(frame.locator('.env-card')).to_have_count(1)
            await refresh()
            await expect(search).to_have_value('演示环境 A')
            await search.fill('3' * 32)
            await expect(frame.locator('.env-card h3')).to_have_text('演示环境 3')
            await search.fill('')
            await frame.locator('#environment-status').select_option('stopped')
            await refresh()
            await expect(frame.locator('.env-card')).to_have_count(1)
            await expect(frame.locator('#environment-status')).to_have_value('stopped')
            await frame.locator('#environment-status').select_option('future-state')
            await expect(frame.locator('.env-badge')).to_have_text('未知状态：future-state')
            await frame.locator('#environment-status').select_option('all')
            scenes.append('名称/ID 搜索、实际状态筛选和未知状态，刷新保留选择')

            previous = len(fixture.writes)
            preparation = target.locator('[data-native-preparation]')
            await expect(preparation).to_contain_text('热进程就绪')
            await expect(preparation).to_contain_text('27')
            fixture.rows[0]['native_preparation'] = {'state': 'unknown', 'reason': 'check_expired'}
            await refresh()
            await expect(preparation).to_contain_text('最近检查已过期')
            await expect(preparation).to_contain_text('未观测')
            fixture.rows[0]['native_preparation'] = {'state': 'preparing', 'checked_at_ms': int(time.time() * 1000)}
            await refresh()
            await expect(preparation).to_contain_text('正在准备')
            fixture.rows[0]['native_preparation'] = sample_rows()[0]['native_preparation']
            await refresh()
            assert len(fixture.writes) == previous
            scenes.append('实时准备、过期与准备中状态准确展示，状态读取零业务写入')

            await target.get_by_text('环境与物理详情', exact=True).click()
            physical = target.locator('details.physical-features')
            await physical.locator('summary').click()
            await target.get_by_role('button', name='刷新实测', exact=True).click()
            await expect(target.get_by_role('button', name='刷新实测')).to_be_enabled()
            await expect(physical).to_have_attribute('open', '')
            assert fixture.writes[-1]['path'].endswith('/physical-features/refresh')
            assert '未采集' in await physical.inner_text() and '未限制' in await physical.inner_text()
            scenes.append('物理实测显式刷新，缺失/无限口径及详情展开保留')

            previous = len(fixture.writes)
            await open_operation('准备内核')
            await frame.locator('[name="release"]').fill('v0.1.0-beta.4')
            await frame.locator('#native-kernel-modal').get_by_role('button', name='取消', exact=True).click()
            await open_operation('准备内核')
            await frame.locator('[name="release"]').press('Escape')
            await expect(frame.locator('#native-kernel-modal')).to_be_hidden()
            assert len(fixture.writes) == previous
            await open_operation('准备内核')
            await frame.locator('#native-kernel-modal').click(position={'x': 2, 'y': 2})
            await expect(frame.locator('#native-kernel-modal')).to_be_hidden()
            await open_operation('准备内核')
            field = frame.locator('[name="release"]')
            await field.fill('https://invalid.example/release')
            await frame.locator('#native-kernel-form').get_by_role('button', name='准备内核', exact=True).click()
            assert len(fixture.writes) == previous
            await field.fill('v0.1.0-beta.4')
            await field.evaluate('node=>node.setSelectionRange(3,3)')
            await field.evaluate('()=>renderEnvironments()')
            await expect(field).to_have_value('v0.1.0-beta.4')
            assert await field.evaluate('node=>document.activeElement===node&&node.selectionStart===3')
            await page.screenshot(path=str(output / 'prepare-dialog-1280.png'))
            await page.set_viewport_size({'width': 390, 'height': 844})
            await page.screenshot(path=str(output / 'prepare-dialog-390.png'))
            assert await frame.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
            await page.set_viewport_size({'width': 1280, 'height': 1000})
            await submit_operation('准备内核')
            write = fixture.writes[-1]['body']
            assert set(write) == {'operation', 'operation_id', 'release', 'expected_sha256', 'expected_revision'}
            assert write['operation'] == 'prepare' and write['release'] == 'v0.1.0-beta.4'
            assert write['expected_sha256'] is None and write['expected_revision'] == '10:initial'
            assert len(write['operation_id']) == 36
            scenes.append('准备表单校验、取消/Esc 零提交、刷新保留输入焦点及原请求合同')

            await open_operation('激活候选')
            await expect(frame.locator('#native-kernel-target')).to_have_text('v0.1.0-beta.4')
            await submit_operation('激活候选')
            assert fixture.writes[-1]['body']['expected_sha256'] == NEW_SHA
            assert fixture.writes[-1]['body']['expected_revision'] == '10:revision-1'
            await expect(target.locator('.env-kernel-version strong')).to_have_text('v0.1.0-beta.4')
            await expect(target.get_by_role('button', name='激活候选', exact=True)).to_be_disabled()
            await open_operation('回滚内核')
            await expect(frame.locator('#native-kernel-target')).to_have_text('v0.1.0-beta.3')
            await submit_operation('回滚内核')
            assert fixture.writes[-1]['body']['release'] is None and fixture.writes[-1]['body']['expected_sha256'] == OLD_SHA
            await expect(target.locator('.env-kernel-version strong')).to_have_text('v0.1.0-beta.3')
            scenes.append('激活/回滚明确目标、摘要与状态前置条件，当前版本按服务器回执更新')

            kernel = fixture.rows[0]['native_kernel']
            fixture.rows[0]['busy'] = True
            await refresh()
            await expect(target.get_by_role('button', name='准备内核', exact=True)).to_be_disabled()
            fixture.rows[0]['busy'] = False
            saved = kernel['prepared']
            kernel['prepared'] = None
            await refresh()
            await expect(target.get_by_role('button', name='激活候选', exact=True)).to_be_disabled()
            kernel['prepared'] = saved
            kernel['state'] = 'reconcile'
            await refresh()
            await expect(target.get_by_role('button', name='准备内核', exact=True)).to_be_disabled()
            await open_operation('恢复对账')
            await submit_operation('恢复对账')
            assert fixture.writes[-1]['body']['operation'] == 'recover'
            scenes.append('CLI 忙碌、候选缺失、管理未开放及待对账状态的操作许可')

            await open_operation('激活候选')
            frozen = kernel['revision']
            kernel['revision'] = '10:external-change'
            await frame.locator('#native-kernel-form').evaluate('()=>renderEnvironments()')
            await frame.locator('#native-kernel-form').get_by_role('button', name='激活候选', exact=True).click()
            await expect(frame.locator('#native-kernel-feedback')).to_contain_text('状态已变更')
            assert fixture.writes[-1]['body']['expected_revision'] == frozen
            previous = len(fixture.writes)
            await expect(frame.locator('#native-kernel-form button[type="submit"]')).to_be_disabled()
            await frame.locator('#native-kernel-modal').get_by_role('button', name='取消', exact=True).click()
            assert len(fixture.writes) == previous
            scenes.append('弹窗冻结原版本，冲突可见并阻止自动重放')

            await target.get_by_role('button', name='配置时段', exact=True).click()
            await expect(frame.locator('#run-window-modal')).to_be_visible()
            await frame.locator('#run-window-form [name="enabled"]').check()
            await frame.locator('#run-window-add').click()
            await expect(frame.locator('.run-window-interval')).to_have_count(2)
            await frame.locator('#run-window-modal').get_by_role('button', name='取消', exact=True).click()
            assert len(fixture.writes) == previous
            scenes.append('直接进入环境页即可操作原运行窗口表单，取消保持只读')

            fixture.fail_read = True
            await refresh()
            await expect(frame.locator('#environment-feedback')).to_contain_text('读取环境失败')
            await expect(frame.locator('.env-card')).to_have_count(4)
            fixture.fail_read = False
            await refresh()
            fixture.rows[0]['name'] = '<img src=x onerror="alert(1)">'
            fixture.rows[0]['native_kernel']['error'] = '<script>window.injected=true</script>'
            await refresh()
            assert await frame.locator('.env-card img').count() == 0
            assert await frame.locator('#environment-list script').count() == 0
            await expect(frame.locator('.env-card h3').first).to_contain_text('<img')
            fixture.rows[0]['name'] = '演示环境 A'
            kernel['error'] = None
            await refresh()
            scenes.append('读取故障保留快照；账号名与错误文本安全转义')

            fixture.hold_next_read = True
            await frame.locator('#environment-refresh').click()
            await fixture.read_started.wait()
            fixture.rows[0]['name'] = '较新快照'
            await frame.locator('#environment-search').evaluate('()=>renderEnvironments()')
            fixture.read_gate.set()
            await expect(frame.locator('.env-card h3').first).to_have_text('较新快照')
            fixture.rows[0]['name'] = '演示环境 A'
            await refresh()
            scenes.append('乱序列表回执按请求序号丢弃旧快照')

            fixture.operation_gate = asyncio.Event()
            fixture.operation_started = asyncio.Event()
            runtime = next(item for item in page.frames if item.url.startswith(BASE + '/runtime/'))
            before_request = await runtime.evaluate('state.environmentUI.request')
            await open_operation('激活候选')
            await frame.locator('#native-kernel-form button[type="submit"]').dblclick(force=True)
            await fixture.operation_started.wait()
            previous = len(fixture.writes)
            await expect(frame.locator('#native-kernel-form button[type="submit"]')).to_be_disabled()
            await runtime.wait_for_function('(before)=>state.environmentUI.request>=before+2', arg=before_request)
            await expect(frame.locator('#native-kernel-target')).to_have_text('v0.1.0-beta.4')
            assert len(fixture.writes) == previous
            await frame.locator('#native-kernel-form').evaluate("()=>{location.hash='#topics'}")
            await expect(frame.locator('#environment-list')).to_have_count(0)
            assert await frame.locator('html').evaluate("()=>state.environmentUI.timer===null&&state.kernelDialog===null")
            fixture.operation_gate.set()
            await page.get_by_role('link', name='环境', exact=True).click()
            await expect(frame.locator('.env-card')).to_have_count(4)
            await expect(frame.locator('#native-kernel-modal')).to_be_hidden()
            assert len(fixture.writes) == previous
            fixture.operation_gate = None
            scenes.append('重复提交仅发一次；离页收口定时器/窗口，迟到写回执不污染页面')

            # 长 ID/摘要使用真实 DOM 展开验收，不用截短后的文案假称移动适配成功。
            fixture.rows[0]['fingerprint']['hostname'] = 'long-host-' * 30
            fixture.rows[0]['environment_id'] = '1234567890abcdef' * 8
            await refresh()
            await target.get_by_text('环境与物理详情', exact=True).click()
            await target.get_by_text('版本摘要与预热回执', exact=True).click()
            await page.set_viewport_size({'width': 390, 'height': 844})
            assert await frame.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
            await target.locator('.env-kernel').scroll_into_view_if_needed()
            await page.screenshot(path=str(output / 'kernel-details-390.png'))
            fixture.rows = []
            await refresh()
            await expect(frame.locator('.env-empty')).to_contain_text('暂无账号环境')
            fixture.rows = sample_rows()
            await refresh()
            scenes.append('手机长 ID/主机名/完整摘要展开及真正空列表')

            await frame.locator('html').evaluate("node=>node.dataset.theme='dark'")
            await page.get_by_role('link', name='任务', exact=True).click()
            await frame.locator('[data-tab="topics"]').click()
            await expect(frame.locator('html')).not_to_have_class(re.compile('environment-page'))
            await expect(frame.locator('html')).to_have_attribute('data-theme', 'dark')
            await expect(frame.locator('body')).not_to_have_css('background-color', 'rgb(249, 246, 241)')
            await page.get_by_role('link', name='环境', exact=True).click()
            await expect(frame.locator('.env-card')).to_have_count(4)
            scenes.append('环境作用域退出后恢复原主题偏好和其他页样式')
            await page.get_by_role('link', name='请求记录', exact=True).click()
            await page.get_by_role('button', name='详情', exact=True).click()
            await page.get_by_role('tab', name='性能', exact=True).click()
            runtime = page.locator('[data-native-runtime]')
            await expect(runtime).to_contain_text('命中热进程')
            await expect(runtime).to_contain_text('PID 27')
            await expect(runtime).to_contain_text('本地准备合计 185 ms')
            await expect(page.get_by_text('原生进程与本地阶段：未观测', exact=True)).to_be_visible()
            assert await page.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
            scenes.append('请求详情展示真实 PID/热命中/本地分段；历史记录保留未观测，手机无溢出')
            await page.keyboard.press('Escape')
            await page.get_by_role('link', name='环境', exact=True).click()
            target = frame.locator('.env-card').filter(has=frame.get_by_role('heading', name='演示环境 A', exact=True))
            toggle = target.locator('[data-content-capture]')
            await expect(toggle).to_have_attribute('aria-checked', 'true')
            await expect(target).to_contain_text('原生 TLS 采集：已就绪')
            before = len(fixture.writes)
            await toggle.click()
            await frame.locator('#content-capture-modal').get_by_role('button', name='取消', exact=True).click()
            assert len(fixture.writes) == before
            for enabled in (False, True):
                await toggle.click()
                await expect(frame.locator('#content-capture-form button[type="submit"]')).to_be_enabled()
                await frame.locator('#content-capture-form button[type="submit"]').click()
                await expect(toggle).to_have_attribute('aria-checked', str(enabled).lower())
                assert fixture.writes[-1]['body']['enabled'] is enabled
            for state, text in [('not_installed', '需系统更新'), ('preparing', '准备中'), ('unavailable', '暂不可用'),
                                ('stopped', '停止待启动'), ('ready', '已就绪')]:
                fixture.rows[0]['content_capture']['tls_observer'] = {'state': state, 'reason': None}
                await refresh()
                await expect(target).to_contain_text('原生 TLS 采集：' + text)
            await page.screenshot(path=str(output/'tls-capture-390.png'))
            assert await frame.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
            scenes.append('默认开启、取消零写入、关闭再开启及五种TLS能力状态，390px无溢出')
            assert not errors, errors
            assert not fixture.unexpected, fixture.unexpected
            return {'status': 'passed', 'scenes': scenes, 'scene_count': len(scenes), 'script_errors': errors,
                'business_writes': len(fixture.writes), 'synthetic_only': True, 'real_model_requests': 0,
                'actual_gateway_dist': str(gateway), 'screenshots': sorted(p.name for p in output.glob('*.png'))}
        except Exception:
            await page.screenshot(path=str(output / 'failure.png'), full_page=True)
            (output / 'partial.json').write_text(json.dumps({'scenes': scenes, 'script_errors': errors,
                'writes': fixture.writes, 'unexpected': fixture.unexpected}, ensure_ascii=False, indent=2))
            raise
        finally:
            await browser.close()


def main() -> None:
    """解析本地证据路径并执行验收。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/environment-ui-verification')
    parser.add_argument('--gateway-dist', type=Path, default=ROOT / 'cc2api/web/dist')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    assert (args.gateway_dist / 'index.html').is_file(), '先在 cc2api/web 执行 npm run build 准备主后台静态产物'
    result = asyncio.run(run(args.output.resolve(), args.gateway_dist.resolve()))
    (args.output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
