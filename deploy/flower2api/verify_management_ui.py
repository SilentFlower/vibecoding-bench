"""通过真实管理前端和合成 API 验证导航、版本、时区、采集控制及详情隔离。"""
import argparse
import asyncio
import copy
import json
import re
from pathlib import Path
from source_layout import source_path
from urllib.parse import urlsplit

from verify_environment_ui import BASE, ROOT, Fixture


class ManagementFixture(Fixture):
    """复用真实静态资源夹具，补齐本轮管理合同。"""

    def __init__(self, gateway):
        """初始化独立账号及版本。@param gateway 真实生产产物。@return None。"""
        super().__init__(gateway)
        self.capture_reads = 0
        self.capture_status = 'disabled'
        self.capture_state = 'available'
        self.capture_gate = None
        self.capture_started = asyncio.Event()
        self.conflict = False
        self.status_reads = 0
        self.current = 'system-ci-200-1'
        self.diagnostic_account = {'account_name': '主用演示账号', 'account_email': 'primary@example.test'}
        self.diagnostic_account_id = 11
        self.extra_attempt = False
        self.original_session = '55555555-5555-4555-8555-555555555555'
        self.derived_session = None
        self.diagnostic_metrics = {'profile_version': '2.1.293', 'partial': False,
            'tokens': {'input_tokens': 0, 'output_tokens': 100}, 'duration_ms': 2000}
        self.task_accounts = [{'id': 1, 'name': '合成任务账号', 'enabled': 1, 'cc2api_account_id': 11,
            'profile_path': 'profiles/synthetic', 'passive_quota': {'account_error': 'invalid_grant',
                'blocked': True, 'message': 'invalid_grant：账号异常，需重新授权或人工核实'}}]
        self.quota_ok = True
        self.task_runs = []
        self.hold_api = None
        self.api_started = asyncio.Event()
        self.api_gate = asyncio.Event()
        self.releases = [dict(release=f'system-ci-{number}-1', sequence=[number, 1],
            published_at='2026-11-12T05:31:49.455Z', changes=f'平台版本：v1.0.{number-200}\n\n管理后台交互与采集状态改进。',
            manifest_sha256=str(number % 10) * 64, data_compatible=True, account_changed=False) for number in [201, 200, 199, 198]]
        for release in self.releases[2:]:
            release['changes'] = '历史联合构建说明。'
        for row in self.rows:
            row['gateway_account_id'] = row['account_id'] + 10
            row['content_capture'] = dict(environment_id=row['environment_id'], account_id=row['account_id'],
                generation=10, revision='a' * 64, enabled=False, supported=True, applied=True)

    async def respond(self, route, payload, status=200):
        """回传合成 JSON。@param route 请求。@param payload 数据。@param status 状态码。@return None。"""
        await route.fulfill(status=status, content_type='application/json', body=json.dumps(payload))

    async def route(self, route):
        """拦截管理合同；所有其它请求仍受原夹具约束。@param route 浏览器请求。@return None。"""
        request = route.request
        path = urlsplit(request.url).path
        if path == '/runtime/api/accounts/1/quota':
            assert request.method == 'POST'
            self.writes.append({'path': path, 'body': {}})
            if self.hold_api == path:
                self.hold_api = None
                self.api_started.set()
                await self.api_gate.wait()
            if self.quota_ok:
                self.task_accounts[0]['passive_quota'] = {'known': True, 'blocked': False, 'source': 'manual',
                    'windows': {'five_hour': {'utilization': 10}, 'seven_day': {'utilization': 20}}}
                return await self.respond(route, {'ok': True, 'five_hour': {'utilization': 10}, 'seven_day': {'utilization': 20}})
            return await self.respond(route, {'ok': False, 'message': 'invalid_grant'})
        if path == '/runtime/api/runs-stream':
            return await route.fulfill(content_type='text/event-stream', body='event: runs\ndata: ' + json.dumps(self.task_runs) + '\n\n')
        if path == '/runtime/api/accounts/warmup/pi/stream':
            return await route.fulfill(content_type='text/event-stream', body=': synthetic\n\n')
        task_payloads = {'/runtime/api/accounts': self.task_accounts, '/runtime/api/tasks': [], '/runtime/api/runs': self.task_runs,
            '/runtime/api/runs/synthetic-run': self.task_runs[0] if self.task_runs else {},
            '/runtime/api/runs/synthetic-run/stats': {'available': False},
            '/runtime/api/runs/synthetic-run/files': [], '/runtime/api/runs/synthetic-run/transcript': {},
            '/runtime/api/settings/runtime-model': {}, '/runtime/api/settings/runtime-effort': {},
            '/runtime/api/settings/claude-code-version': {},
            '/runtime/api/projects': {'agents': [], 'pi_available': True},
            '/runtime/api/accounts/warmup/pi': {'agents': [], 'pi_available': True},
            '/runtime/api/projects/catalog': {'projects': []}, '/runtime/api/accounts/warmup/pi/catalog': {'projects': []},
            '/runtime/api/accounts/warmup/pi/agents/1/snapshot': {'state': {'agents': []}, 'cursor': 0,
                'observation': None, 'events': {'items': [], 'next_before': None}},
            '/runtime/api/accounts/warmup/pi/agents/1/work/page': {'items': [], 'next_before': None},
            '/runtime/api/accounts/warmup/pi/agents/1/actions': [],
            '/runtime/api/settings/project-requester': {'base_url': '', 'models': [], 'ready': False}}
        if path in task_payloads:
            payload = copy.deepcopy(task_payloads[path])
            if self.hold_api == path:
                self.hold_api = None
                self.api_started.set()
                await self.api_gate.wait()
            return await self.respond(route, payload)
        if path == '/runtime/api/summary':
            return await self.respond(route, {'active_runs': sum(row.get('status') in ['queued','running','stopping','quota_wait'] for row in self.task_runs)})
        if path == '/admin/settings':
            if request.method == 'POST':
                self.writes.append({'path': path, 'body': json.loads(request.post_data)})
            return await self.respond(route, {'request_diagnostics_log_mode': 'debug'})
        if path.startswith('/runtime/api/system-updates/'):
            action = path.rsplit('/', 1)[1]
            if action == 'status':
                self.status_reads += 1
                payload = {'installed': True, 'revision': 'a' * 36, 'current_release': self.current,
                    'busy': False, 'components': {'control': {'release': 'ci-200-1'}, 'account': {'release': 'ci-200-1'}},
                    'environments': [{'environment_id': row['environment_id'], 'name': row['name'],
                        'running': True, 'verified': True, 'release': 'ci-200-1'} for row in self.rows[:2]],
                    'operation': {'operation_id': 'a' * 36, 'action': 'install', 'phase': 'succeeded',
                        'target_release': self.current, 'updated_at': '2026-11-12T05:31:49.455Z'},
                    'history': [{'release': 'system-ci-199-1', 'manifest_sha256': 'b' * 64,
                        'installed_at': '2026-11-11T05:31:49Z', 'rollback_available': True}]}
            elif action == 'releases':
                payload = {'fresh': True, 'releases': self.releases, 'checking': False, 'checked_at': '2026-11-12T05:31:49.455Z'}
            elif action == 'version':
                payload = {'version': 'v1.0.0'}
            else:
                self.writes.append({'path': path, 'body': json.loads(request.post_data or '{}')})
                payload = {'checking': True}
            return await self.respond(route, payload)
        if path.endswith('/content-capture'):
            row = next(row for row in self.rows if row['environment_id'] in path)
            if request.method == 'POST':
                body = json.loads(request.post_data)
                self.writes.append({'path': path, 'body': body})
                if self.conflict:
                    return await self.respond(route, {'detail': '环境或采集配置已变化'}, 409)
                assert set(body) == {'enabled', 'expected_generation', 'expected_revision'}
                assert body['expected_revision'] == row['content_capture']['revision']
                row['content_capture'].update(enabled=body['enabled'], generation=11, revision='b' * 64)
            return await self.respond(route, copy.deepcopy(row['content_capture']))
        if path.startswith('/admin/request-diagnostics'):
            root = {'request_id': '11111111-1111-4111-8111-111111111111', 'started_at': '2026-11-12T05:31:49.455Z',
                'finished_at': '2026-11-12T05:31:51.455Z', 'status_code': 200, 'account_id': 11,
                'outcome': 'success', 'attempt_count': 1, 'log_mode': 'debug', 'response_request_id': 'synthetic-response'}
            root.update(account_id=self.diagnostic_account_id, **self.diagnostic_account)
            if self.original_session is not None:
                root['original_session_id'] = self.original_session
            if self.derived_session is not None:
                root['derived_session_id'] = self.derived_session
            if self.diagnostic_account_id is None:
                root['attempt_count'] = 0
            if '/captures/' in path:
                self.capture_reads += 1
                self.capture_started.set()
                if self.capture_gate:
                    await self.capture_gate.wait()
                return await self.respond(route, {'state': self.capture_state, 'message': '合成阶段证据',
                    'snapshot': {'headers': [], 'body': '{"synthetic":true}', 'body_truncated': False,
                        'headers_truncated': False, 'original_body_bytes': 18, 'original_body_sha256': 'a' * 64}
                        if self.capture_state == 'available' else None})
            attempt = {'attempt_id': '22222222-2222-4222-8222-222222222222', 'account_id': 11,
                'ordinal': 1, 'profile_selection': 'native293_cc_prepared', 'status_code': 200,
                'outcome': 'success', 'log_mode': 'debug', 'capture_status': self.capture_status,
                'duration_ms': 2000, 'ttft_ms': 700, 'first_output_ms': 900, 'tokens': {'input_tokens': 0},
                'runtime': {'worker_id': 'synthetic-worker', 'worker_pid': 16, 'kernel_generation': 'synthetic',
                    'warm_hit': True, 'preparation_wait_ms': 0, 'checkout_ms': 0, 'worker_start_ms': None, 'prepared_ms': 222}}
            attempt.update(account_id=self.diagnostic_account_id, **self.diagnostic_account)
            attempt.update(self.diagnostic_metrics)
            attempts = [attempt] if self.diagnostic_account_id is not None else []
            if self.extra_attempt:
                attempt['ordinal'] = 2
                attempts.insert(0, {**attempt, 'attempt_id': '33333333-3333-4333-8333-333333333333',
                    'ordinal': 1, 'account_id': 12, 'account_name': '备用演示账号', 'account_email': 'backup@example.test'})
                root['attempt_count'] = 2
            if path == '/admin/request-diagnostics':
                if attempts:
                    root['last_attempt'] = attempt
                return await self.respond(route, {'items': [root], 'total': 1, 'health': {}})
            return await self.respond(route, {'request': root, 'attempts': attempts})
        return await super().route(route)


async def verify_request_metadata(page, fixture, expect):
    """验证会话复制、末次版本、平均 TPS 和历史缺字段。@param page 页面。@param fixture 合成接口。@param expect 断言入口。@return None。"""
    session, metrics = fixture.original_session, copy.deepcopy(fixture.diagnostic_metrics)
    await page.set_viewport_size({'width': 1280, 'height': 1000})
    await page.evaluate("""() => Object.defineProperty(navigator, 'clipboard', {configurable:true,
        value:{writeText:async value=>{window.__copiedSession=value}}})""")
    await page.evaluate("""() => {window.__originalCopyCommand=document.execCommand;
        document.execCommand=command=>{window.__copiedSession=document.activeElement?.value;return command==='copy'}}""")
    await expect(page.locator('.request-records th')).to_have_count(9)
    await expect(page.locator('.request-records')).to_contain_text('原始 Session ID')
    for version, selection in [('2.1.280', 'native280_cc_prepared'), ('2.1.293', 'native293_cc_prepared'),
            ('2.1.280', 'client_version')]:
        fixture.diagnostic_metrics.update(profile_version=version, profile_selection=selection)
        await page.get_by_role('button', name='刷新', exact=True).click()
        label = '原生运行时' if selection.startswith('native') else '原有转发'
        await expect(page.locator('tbody')).to_contain_text(label + ' · ' + version)
    for value, expected in [(2400, '2,400'), (0, '0'), (None, '—'), ('missing', '—')]:
        tokens = {'input_tokens': 0, 'output_tokens': 100, 'cache_read_tokens': 1200}
        if value != 'missing':
            tokens['cache_write_tokens'] = value
        fixture.diagnostic_metrics.update(tokens=tokens)
        await page.get_by_role('button', name='刷新', exact=True).click()
        await expect(page.locator('tbody [data-cache-write]')).to_have_text('缓存写 ' + expected)
        await page.get_by_role('button', name='详情', exact=True).click()
        await page.get_by_role('tab', name='性能', exact=True).click()
        metric = page.locator('.request-token-metrics > div').filter(has_text='缓存写入')
        await expect(metric.locator('strong')).to_have_text('未观测' if expected == '—' else expected)
        await page.keyboard.press('Escape')
    for tokens, duration, partial, outcome, expected in [
            (100, 2000, False, 'success', '50.0 token/s'), (0, 2000, False, 'success', '0.0 token/s'),
            (None, 2000, False, 'success', '未观测'), (100, 0, False, 'success', '未观测'),
            (100, None, False, 'in_progress', '未观测'), (100, 2000, True, 'cancelled', '未观测')]:
        fixture.diagnostic_metrics.update(tokens={'output_tokens': tokens}, duration_ms=duration, partial=partial, outcome=outcome)
        await page.get_by_role('button', name='刷新', exact=True).click()
        await expect(page.locator('tbody [data-average-tps]')).to_have_text('平均 TPS ' + expected)
        await page.get_by_role('button', name='详情', exact=True).click()
        await page.get_by_role('tab', name='性能', exact=True).click()
        await expect(page.get_by_role('tabpanel').locator('[data-average-tps]')).to_have_text(expected)
        await page.keyboard.press('Escape')
    fixture.diagnostic_metrics = copy.deepcopy(metrics)
    fixture.original_session = 's' * 256
    fixture.derived_session = 'd' * 64
    await page.get_by_role('button', name='刷新', exact=True).click()
    await page.get_by_role('button', name='复制原始 Session ID ' + fixture.original_session, exact=True).click()
    assert await page.evaluate('window.__copiedSession') == fixture.original_session
    await expect(page.locator('tbody .request-session-source')).to_have_count(0)
    for width in [1280, 390]:
        await page.set_viewport_size({'width': width, 'height': 1000})
        await page.get_by_role('button', name='详情', exact=True).click()
        await expect(page.get_by_role('tabpanel')).to_contain_text(fixture.original_session)
        await page.get_by_role('button', name='复制原始 Session ID ' + fixture.original_session, exact=True).click()
        assert await page.evaluate('window.__copiedSession') == fixture.original_session
        assert await page.get_by_role('tabpanel').evaluate('node=>node.scrollWidth<=node.clientWidth')
        assert await page.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
        await page.keyboard.press('Escape')
    await page.set_viewport_size({'width': 1280, 'height': 1000})
    fixture.original_session = None
    await page.get_by_role('button', name='刷新', exact=True).click()
    await expect(page.locator('tbody .request-session')).to_contain_text('网关派生')
    copy_label = '复制派生 Session ID ' + fixture.derived_session
    await page.get_by_role('button', name=copy_label, exact=True).click()
    assert await page.evaluate('window.__copiedSession') == fixture.derived_session
    await page.set_viewport_size({'width': 390, 'height': 1000})
    await page.get_by_role('button', name='详情', exact=True).click()
    panel = page.get_by_role('tabpanel')
    await expect(panel.locator('.request-session')).to_contain_text('网关派生')
    await panel.get_by_role('button', name=copy_label, exact=True).click()
    assert await page.evaluate('window.__copiedSession') == fixture.derived_session
    assert await panel.evaluate('node=>node.scrollWidth<=node.clientWidth')
    await page.keyboard.press('Escape')
    await page.set_viewport_size({'width': 1280, 'height': 1000})
    fixture.derived_session = None
    fixture.diagnostic_metrics = {'tokens': {}, 'partial': None}
    await page.get_by_role('button', name='刷新', exact=True).click()
    await expect(page.locator('tbody')).to_contain_text('原生运行时 · 未观测')
    await expect(page.locator('tbody .request-extra').nth(4)).to_contain_text('未提供')
    await page.get_by_role('button', name='详情', exact=True).click()
    await expect(page.get_by_role('tabpanel')).to_contain_text('未提供')
    await page.keyboard.press('Escape')
    fixture.original_session, fixture.diagnostic_metrics = session, metrics
    await page.get_by_role('button', name='刷新', exact=True).click()
    await page.evaluate('() => {document.execCommand=window.__originalCopyCommand}')


async def verify_navigation_edges(page, fixture, expect):
    """核对弹窗离页、程序化导航和连续历史。@param page 页面。@param fixture 合成接口。@param expect 断言入口。@return None。"""
    fixture.task_accounts[0]['warmup_engine'] = 'projects'
    await page.goto(BASE + '/tasks')
    frame = page.locator('.task-runtime')
    await expect(frame.locator('[data-quota="1"]')).to_be_visible()
    await expect(frame).to_have_attribute('aria-busy', 'false')
    await expect(page.locator('iframe')).to_have_count(0)
    await page.locator('.task-runtime').evaluate("node=>{node.__taskDocument='edge-cases';}")
    await frame.locator('[data-tab="topics"]').click()
    await frame.locator('[data-tab="accounts"]').click()
    await frame.locator('[data-quota="1"]').click()
    await expect(frame.locator('#modal')).to_be_visible()
    await page.go_back()
    await expect(page).to_have_url(BASE + '/tasks?tab=topics')
    await expect(frame.locator('#modal')).to_be_hidden()
    await page.go_forward()
    await expect(page).to_have_url(BASE + '/tasks')
    await frame.locator('[data-quota="1"]').click()
    await expect(frame.locator('#modal')).to_be_visible()
    await frame.locator('.runtime-body').press('4')
    await expect(page).to_have_url(BASE + '/tasks')
    await expect(frame.locator('#modal')).to_be_visible()
    await frame.locator('.runtime-body').press('Escape')
    await frame.locator('.runtime-body').press('4')
    await expect(page).to_have_url(BASE + '/tasks?tab=tasks')
    await expect(frame.locator('#modal')).to_be_hidden()
    for suffix in ['/tasks', '/tasks?tab=topics', '/tasks']:
        await page.go_back()
        await expect(page).to_have_url(BASE + suffix)
    await frame.locator('.runtime-body').press('/')
    await expect(page).to_have_url(BASE + '/tasks?tab=topics')
    await page.go_back()
    await expect(page).to_have_url(BASE + '/tasks')
    await frame.locator('a[href="#warmup?account=1"]').click()
    await expect(page).to_have_url(BASE + '/tasks?tab=warmup&account=1')
    await page.go_back()
    await expect(page).to_have_url(BASE + '/tasks')
    assert await page.locator('.task-runtime').evaluate("node=>node.__taskDocument==='edge-cases'")
    # 使用实际详情入口，详情已加载或仍在途时，离页均应使旧回执与刷新失效。
    fixture.task_runs = [{'id': 'synthetic-run', 'task_id': 1, 'account_id': 1, 'status': 'running'}]
    await frame.locator('[data-tab="runs"]').click()
    await frame.locator('.run-actions [data-detail="synthetic-run"]').click()
    await expect(page.locator('.approved-run-dialog .run-status')).to_have_attribute('data-status','running')
    await page.go_back()
    await expect(frame.locator('#modal')).to_be_hidden()
    await expect(page.locator('.approved-run-dialog')).to_have_count(0)
    await frame.locator('[data-tab="runs"]').click()
    fixture.hold_api = '/runtime/api/runs/synthetic-run'
    fixture.api_started.clear()
    fixture.api_gate.clear()
    await frame.locator('.run-actions [data-detail="synthetic-run"]').click()
    await asyncio.wait_for(fixture.api_started.wait(), timeout=10)
    await page.go_back()
    fixture.api_gate.set()
    await expect(page.locator('.approved-run-dialog')).to_have_count(0)
    await page.locator('.task-runtime').evaluate('node=>new Promise(resolve=>window.requestAnimationFrame(()=>window.requestAnimationFrame(resolve)))')
    await expect(frame.locator('#modal')).to_be_hidden()
    await expect(page.locator('.approved-run-dialog')).to_have_count(0)
    fixture.task_runs = []
    standalone = await page.context.new_page()
    try:
        await standalone.goto(BASE + '/runtime/#accounts')
        await expect(standalone.locator('[data-quota="1"]')).to_be_visible()
        await standalone.locator('body').press('4')
        await expect(standalone).to_have_url(BASE + '/runtime/#tasks')
        await standalone.go_back()
        await expect(standalone).to_have_url(BASE + '/runtime/#accounts')
    finally:
        await standalone.close()


async def run(output):
    """运行跨主题、宽度与时区交互矩阵。@param output 证据目录。@return 聚合报告。"""
    from playwright.async_api import async_playwright, expect
    output.mkdir(parents=True, exist_ok=True)
    scenes, errors = [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        for zone, theme in [('Asia/Shanghai', 'light'), ('America/Los_Angeles', 'dark')]:
            context = await browser.new_context(viewport={'width': 1280, 'height': 1000}, timezone_id=zone, color_scheme=theme)
            fixture = ManagementFixture(source_path(ROOT, 'cc2api/web/dist'))
            await context.route('**/*', fixture.route)
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');")
            page = await context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            # 从版本号打开系统更新弹窗（/updates 背后是账号页，本夹具未声明账号接口；深链接由 verify_system_update_browser.py 覆盖）。
            await page.goto(BASE + '/environments')
            await page.locator('.console-sidebar .brand-update').click()
            await page.locator('.system-update-dialog').get_by_role('button', name='版本记录与回退', exact=True).click()
            await expect(page.locator('[data-release-card]')).to_have_count(2)
            assert await page.locator('[data-release-details]').count() == 0
            cards = page.locator('[data-release-card]')
            await cards.nth(0).locator('button[aria-expanded]').click()
            await expect(page.locator('[data-release-details]')).to_have_count(1)
            await cards.nth(1).locator('button[aria-expanded]').click()
            await expect(page.locator('[data-release-details]')).to_have_count(1)
            await cards.nth(1).locator('button[aria-expanded]').click()
            await expect(page.locator('[data-release-details]')).to_have_count(0)
            assert 'system-ci-' not in await page.locator('[data-release-card]').first.inner_text()
            # 版本记录中的安装先弹二次确认，取消后零安装写入。
            await cards.nth(0).get_by_role('button', name='安装更新', exact=True).click()
            confirm = page.get_by_role('dialog', name='确认安装更新', exact=True)
            await expect(confirm).to_be_visible()
            assert all(write['path']=='/runtime/api/system-updates/check' for write in fixture.writes),fixture.writes
            await confirm.get_by_role('button', name='取消', exact=True).click()
            await page.get_by_role('button', name='查看历史版本与回退', exact=False).click()
            await expect(cards).to_have_count(4)
            await page.get_by_role('button', name='收起历史版本', exact=True).click()
            for width in [1280, 390]:
                await page.set_viewport_size({'width': width, 'height': 1000})
                assert await page.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
                await page.screenshot(path=str(output / f'updates-{width}-{theme}.png'), full_page=True)
            # 关闭弹窗后仍在运行环境页，再从导航进入运行环境。
            await page.keyboard.press('Escape')
            await expect(page.locator('.system-update-dialog')).to_be_hidden()
            if page.viewport_size['width'] < 768:
                await page.get_by_role('button', name='打开主导航', exact=True).click()
            await page.get_by_role('link', name='运行环境', exact=True).click()
            await expect(page.locator('.environment-rich')).to_have_count(4)
            await expect(page.locator('iframe')).to_have_count(0)
            await page.locator('.environment-rich').first.get_by_role('button',name='资源与采集',exact=True).click()
            workspace = page.locator('.runtime-environment-dialog')
            switch = workspace.get_by_role('switch', name='请求内容采集', exact=True)
            await expect(switch).to_have_attribute('aria-checked', 'false')
            await switch.click()
            confirm = page.get_by_role('dialog', name='开启请求内容采集', exact=True)
            await expect(confirm).to_contain_text('演示环境 A')
            await confirm.get_by_role('button', name='确认应用', exact=True).click()
            await expect(switch).to_have_attribute('aria-checked', 'true')
            assert fixture.rows[1]['content_capture']['enabled'] is False
            fixture.rows[0]['native_kernel']['state'] = 'preparing'
            await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            await expect(switch).to_be_disabled()
            fixture.rows[0]['native_kernel']['state'] = 'active'
            await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            await expect(switch).to_be_enabled()
            fixture.conflict = True
            await switch.click()
            confirm = page.get_by_role('dialog', name='关闭请求内容采集', exact=True)
            await confirm.get_by_role('button', name='确认应用', exact=True).click()
            await expect(confirm.get_by_role('alert')).to_contain_text('已变化')
            await expect(confirm.get_by_role('button', name='确认应用', exact=True)).to_be_disabled()
            await confirm.get_by_role('button', name='取消', exact=True).click()
            await page.screenshot(path=str(output / f'environments-390-{theme}.png'), full_page=True)
            await workspace.get_by_role('button',name='关闭环境详情',exact=True).click()
            frame = page.locator('.task-runtime')
            if page.viewport_size['width'] < 768:
                await page.get_by_role('button', name='打开主导航', exact=True).click()
            await page.get_by_role('link', name='任务与工程', exact=True).click()
            await expect(frame.locator('#accounts-body')).to_contain_text('合成任务账号')
            await expect(frame.locator('[data-tab="environments"]')).to_be_hidden()
            # 保存原生工作区元素，后续点击和浏览历史必须复用同一实例。
            await page.locator('.task-runtime').evaluate("node=>{window.__taskFrame=node;node.__taskDocument='retained';}")
            await frame.locator('[data-tab="topics"]').click()
            await expect(page).to_have_url(BASE + '/tasks?tab=topics')
            assert await page.locator('.task-runtime').evaluate("node=>node===window.__taskFrame && node.__taskDocument==='retained'")
            await page.go_back()
            await expect(frame.locator('#accounts-body')).to_contain_text('合成任务账号')
            await page.go_forward()
            await expect(frame.locator('#topics-list')).to_be_attached()
            assert await page.locator('.task-runtime').evaluate("node=>node.__taskDocument==='retained'")
            await page.reload()
            await expect(frame.locator('[data-tab="topics"]')).to_have_class(re.compile(r'.*\bactive\b.*'))
            await page.go_back()
            await expect(frame.locator('#accounts-body')).to_contain_text('invalid_grant')
            fixture.quota_ok = False
            await frame.locator('[data-quota="1"]').click()
            await expect(frame.locator('#modal')).to_be_visible()
            await expect(frame.locator('#accounts-body')).to_contain_text('invalid_grant')
            await frame.locator('.runtime-body').press('Escape')
            fixture.quota_ok = True
            await frame.locator('[data-quota="1"]').click()
            await expect(frame.locator('#modal')).to_be_visible()
            await expect(frame.locator('#accounts-body')).not_to_contain_text('invalid_grant')
            await expect(frame.locator('#accounts-body')).to_contain_text('手动更新')
            await frame.locator('.runtime-body').press('Escape')
            for width in [1280, 390]:
                await page.set_viewport_size({'width': width, 'height': 1000})
                await page.locator('.task-runtime').evaluate("node=>{node.__taskDocument='retained';}")
                for child_tab, selector in [('tasks', '#batches-body'), ('runs', '#runs-body'),
                        ('projects', '#projects-overview'), ('warmup', '#projects-overview'), ('accounts', '#accounts-body')]:
                    link = frame.locator(f'[data-tab="{child_tab}"]') if child_tab != 'warmup' else frame.locator('[data-tab="warmup"]')
                    await link.click()
                    await expect(frame.locator(selector)).to_be_attached()
                    expected = BASE + ('/tasks' if child_tab == 'accounts' else '/tasks?tab=' + child_tab)
                    await expect(page).to_have_url(expected)
                    assert await page.locator('.task-runtime').evaluate("node=>node.__taskDocument==='retained'")
                await page.screenshot(path=str(output / f'task-accounts-{width}-{theme}.png'), full_page=True)
            # 旧账号 GET 在来回切换后才返回，代次校验应保留新一轮卡片。
            fixture.hold_api = '/runtime/api/accounts'
            fixture.api_gate.clear()
            fixture.api_started.clear()
            await frame.locator('[data-tab="tasks"]').click()
            await asyncio.wait_for(fixture.api_started.wait(), timeout=10)
            fixture.task_accounts[0]['name'] = '新一轮任务账号'
            await frame.locator('[data-tab="accounts"]').click()
            await expect(frame.locator('#accounts-body')).to_contain_text('新一轮任务账号')
            async with page.expect_response(lambda response: urlsplit(response.url).path == '/runtime/api/accounts') as old_accounts:
                fixture.api_gate.set()
            await (await old_accounts.value).body()
            await page.locator('.task-runtime').evaluate('node=>new Promise(resolve=>window.requestAnimationFrame(()=>window.requestAnimationFrame(resolve)))')
            await expect(frame.locator('#accounts-body')).to_contain_text('新一轮任务账号')
            # 在途核验完成时已离页，结果只能更新后台合成事实，不能重新弹出额度窗口。
            fixture.hold_api = '/runtime/api/accounts/1/quota'
            fixture.api_gate.clear()
            fixture.api_started.clear()
            await frame.locator('[data-quota="1"]').click()
            await asyncio.wait_for(fixture.api_started.wait(), timeout=10)
            await frame.locator('[data-tab="topics"]').click()
            async with page.expect_response(lambda response: urlsplit(response.url).path == '/runtime/api/accounts/1/quota') as old_quota:
                fixture.api_gate.set()
            await (await old_quota.value).body()
            await page.locator('.task-runtime').evaluate('node=>new Promise(resolve=>window.requestAnimationFrame(()=>window.requestAnimationFrame(resolve)))')
            await expect(frame.locator('#topics-list')).to_be_attached()
            await expect(frame.locator('#modal')).to_be_hidden()
            await page.goto(BASE + '/tasks?tab=tasks&account=1&environment=synthetic&gateway_account=11')
            await expect(frame.locator('#batches-body')).to_be_attached()
            assert await page.locator('.task-runtime').evaluate("node=>location.search==='?tab=tasks&account=1&environment=synthetic&gateway_account=11' && node.querySelector('[data-tab=tasks]').classList.contains('active')")
            await page.locator('.task-runtime').evaluate("node=>{node.__taskDocument='deep-link';}")
            await frame.locator('[data-tab="topics"]').click()
            await expect(page).to_have_url(BASE + '/tasks?tab=topics')
            await page.go_back()
            await expect(frame.locator('#batches-body')).to_be_attached()
            assert await page.locator('.task-runtime').evaluate("node=>node.__taskDocument==='deep-link' && location.search==='?tab=tasks&account=1&environment=synthetic&gateway_account=11' && node.querySelector('[data-tab=tasks]').classList.contains('active')")
            await verify_navigation_edges(page, fixture, expect)
            if page.viewport_size['width'] < 768:
                await page.get_by_role('button', name='打开主导航', exact=True).click()
            await page.get_by_role('link', name='请求记录', exact=True).click()
            expected_time = '2026/11/12 13:31:49' if zone == 'Asia/Shanghai' else '2026/11/11 21:31:49'
            await expect(page.locator('tbody')).to_contain_text(expected_time)
            await expect(page.locator('tbody time')).not_to_contain_text(zone)
            await verify_request_metadata(page, fixture, expect)
            await expect(page.locator('tbody')).to_contain_text('主用演示账号')
            # 列表只显示账号名称，邮箱在资料气泡里（frontend-guidelines「请求账号保留当前名称和邮箱」）。
            await page.locator('tbody .request-account-identity button').first.hover()
            await expect(page.locator('.fui-info-content')).to_contain_text('primary@example.test')
            await page.keyboard.press('Escape')
            await page.mouse.move(0, 0)
            await page.get_by_role('button', name='详情', exact=True).click()
            await expect(page.get_by_role('tabpanel')).to_contain_text(zone)
            await expect(page.locator('.request-attempt-summary')).to_contain_text('采集已关闭')
            await page.get_by_role('tab', name='原始数据', exact=True).click()
            assert fixture.capture_reads == 0
            assert await page.get_by_role('button', name='读取阶段证据').count() == 0
            await page.get_by_role('tab', name='性能', exact=True).click()
            await expect(page.locator('[data-native-runtime]')).to_contain_text('PID 16')
            await expect(page.locator('[data-native-runtime] .request-runtime-metrics>span').filter(has_text='本地准备合计').locator('b')).to_have_text('222 ms')
            for width in [1280, 390]:
                await page.set_viewport_size({'width': width, 'height': 1000})
                assert await page.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
                await page.screenshot(path=str(output / f'request-detail-{width}-{theme}.png'), animations='disabled')
            await page.get_by_role('tab', name='概览', exact=True).click()
            await page.get_by_role('link', name='内容采集设置',exact=True).click()
            await expect(page.locator('.environment-rich')).to_have_count(1)
            # 环境标题后带平台徽标：标题自身文字与卡片无障碍名称都精确等于环境名，徽标单独核对。
            await expect(page.locator('.environment-rich')).to_have_attribute('aria-label', '演示环境 A')
            heading = page.locator('.environment-rich .fui-entity-card-title')
            await expect(heading.locator('.fui-entity-card-name')).to_have_text('演示环境 A')
            await expect(heading.locator('[data-platform-badge]')).to_have_text('Claude Code')
            assert 'gateway_account=11' in page.url
            await page.get_by_role('button', name='显示全部环境').click()
            await expect(page.locator('.environment-rich')).to_have_count(4)
            if page.viewport_size['width'] < 768:
                await page.get_by_role('button', name='打开主导航', exact=True).click()
            await page.get_by_role('link', name='请求记录', exact=True).click()
            for status in ['queued', 'saved', 'failed', 'dropped', 'timeout']:
                fixture.capture_status = status
                await page.get_by_role('button', name='详情', exact=True).click()
                await page.get_by_role('tab', name='原始数据', exact=True).click()
                button = page.get_by_role('button', name='读取阶段证据', exact=True)
                if status in ['failed', 'dropped']:
                    assert await button.count() == 0
                else:
                    await button.click()
                    await expect(page.locator('[data-native-stages]')).to_be_visible()
                await page.keyboard.press('Escape')
                await expect(page.get_by_role('dialog')).to_have_count(0)
            fixture.capture_status = 'saved'
            for state in ['missing', 'expired']:
                fixture.capture_state = state
                await page.get_by_role('button', name='详情', exact=True).click()
                await page.get_by_role('tab', name='原始数据', exact=True).click()
                await page.get_by_role('button', name='读取阶段证据', exact=True).click()
                await expect(page.get_by_role('status').filter(has_text='阶段证据 · '+('文件缺失或已清理' if state=='missing' else '已超过保留期'))).to_be_visible()
                await page.keyboard.press('Escape')
            fixture.capture_gate = asyncio.Event()
            await page.get_by_role('button', name='详情', exact=True).click()
            await page.get_by_role('tab', name='原始数据', exact=True).click()
            fixture.capture_started.clear()
            await page.get_by_role('button', name='读取阶段证据', exact=True).click()
            await fixture.capture_started.wait()
            await page.keyboard.press('Escape')
            fixture.capture_gate.set()
            await expect(page.get_by_role('dialog')).to_have_count(0)
            await expect(page.get_by_role('button', name='详情', exact=True)).to_be_focused()

            fixture.capture_gate = None
            fixture.diagnostic_account = {'account_name': '长名称演示账号' * 8,
                'account_email': 'long.' + 'address.' * 12 + 'primary@example.test'}
            fixture.extra_attempt = True
            await page.get_by_role('button', name='刷新', exact=True).click()
            for width in [1280, 390]:
                await page.set_viewport_size({'width': width, 'height': 1000})
                await expect(page.locator('tbody')).to_contain_text(fixture.diagnostic_account['account_name'])
                await page.locator('tbody .request-account-identity button').first.hover()
                await expect(page.locator('.fui-info-content')).to_contain_text(fixture.diagnostic_account['account_email'])
                await page.keyboard.press('Escape')
                await page.mouse.move(0, 0)
                assert await page.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
                await page.get_by_role('button', name='详情', exact=True).click()
                for tab in ['概览', '请求链路', '性能']:
                    await page.get_by_role('tab', name=tab, exact=True).click()
                    panel = page.get_by_role('tabpanel')
                    await expect(panel).to_contain_text(fixture.diagnostic_account['account_name'])
                    await expect(panel).to_contain_text('备用演示账号')
                    if tab=='性能':
                        trigger=panel.get_by_role('button',name='账号 '+fixture.diagnostic_account['account_name'],exact=False);await trigger.hover();await expect(page.locator('.fui-info-content')).to_contain_text(fixture.diagnostic_account['account_email']);await page.keyboard.press('Escape');await expect(panel).to_be_visible()
                        await expect(panel.get_by_role('button',name='账号 备用演示账号 · backup@example.test',exact=True)).to_be_visible()
                    else:
                        await expect(panel).to_contain_text(fixture.diagnostic_account['account_email'])
                        await expect(panel).to_contain_text('backup@example.test')
                    assert await panel.evaluate('node=>node.scrollWidth<=node.clientWidth')
                await page.get_by_role('tab', name='原始数据', exact=True).click()
                await page.get_by_role('combobox', name='当前尝试').click()
                options = page.get_by_role('option')
                await expect(options.nth(0)).to_contain_text('backup@example.test')
                await expect(options.nth(1)).to_contain_text(fixture.diagnostic_account['account_email'])
                await page.keyboard.press('Escape')
                assert await page.get_by_role('tabpanel').evaluate('node=>node.scrollWidth<=node.clientWidth')
                await page.screenshot(path=str(output / f'account-names-{width}-{theme}.png'))
                await page.keyboard.press('Escape')

            fixture.extra_attempt = False
            for fields, account_id, label in [({}, 11, '账号信息缺失（ID 11）'),
                    ({'account_name': '', 'account_email': 'email-only@example.test'}, 11, 'email-only@example.test'),
                    ({'account_name': 'name-only', 'account_email': ''}, 11, 'name-only'),
                    ({'account_name': 'same@example.test', 'account_email': 'same@example.test'}, 11, 'same@example.test'),
                    ({}, None, '未知账号')]:
                fixture.diagnostic_account, fixture.diagnostic_account_id = fields, account_id
                await page.get_by_role('button', name='刷新', exact=True).click()
                await expect(page.locator('tbody')).to_contain_text(label)
                await page.get_by_role('button', name='详情', exact=True).click()
                await expect(page.get_by_role('tabpanel')).to_contain_text(label)
                await page.keyboard.press('Escape')
            await page.screenshot(path=str(output / f'requests-390-{theme}.png'), full_page=True)
            assert not errors, errors
            assert not fixture.unexpected, fixture.unexpected
            scenes.append({'timezone': zone, 'theme_preference': theme, 'capture_reads': fixture.capture_reads,
                'synthetic_writes': len(fixture.writes), 'real_model_requests': 0,
                'task_navigation': ['accounts_default', 'stable_document', 'six_tabs', 'history', 'reload', 'deep_link', 'late_response'],
                'quota_verification': ['failed_gate_retained', 'success_card_refreshed', 'late_dialog_discarded'],
                'navigation_repairs': ['dialog_closed_on_history', 'single_keyboard_history', 'search_history',
                    'account_deep_link_history', 'detail_closed_on_leave', 'late_detail_discarded', 'native_module_ready', 'standalone_hash']})
            await context.close()
        await browser.close()
    return {'passed': True, 'scenes': scenes, 'errors': errors, 'real_model_requests': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/management-ui/combined')
    args = parser.parse_args()
    result = asyncio.run(run(args.output))
    (args.output / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))
