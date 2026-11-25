"""真实 Vue 构建配合合成 API 验证系统更新弹窗，全部网络在浏览器前拦截。"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import mimetypes
import uuid
from pathlib import Path
from source_layout import source_path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://system-update.test'


class UpdateFixture:
    """维护独立合成现场，实际脚本和样式均读取网关构建产物。"""

    def __init__(self) -> None:
        """准备精确响应字段。

        :return: None。
        """
        self.state = {'installed': True, 'revision': str(uuid.uuid4()), 'deployment': 'synthetic',
            'current_release': 'system-ci-100-1', 'busy': False, 'operation': None,
            'components': {role: {'release': 'ci-100-1', 'reference': f'ghcr.io/silentflower/vibebench-v3-{role}:v3-ci-100-1',
                'content_sha256': 'a' * 64} for role in ('control', 'account')},
            'history': [{'release': 'system-ci-99-1', 'manifest_sha256': 'c' * 64, 'rollback_available': True}],
            'environments': [{'environment_id': 'synthetic', 'name': '合成环境', 'release': 'ci-100-1', 'running': True, 'verified': True}],
            'checked_at': '2026-11-11T00:00:00Z', 'check_error': None, 'migration_capability': True}
        self.catalog = {'releases': [{'release': 'system-ci-101-1', 'sequence': [101, 1],
            'published_at': '2026-11-11T00:00:00Z', 'changes': '统一平台更新\n兼容账号环境继续复用',
            'manifest_sha256': 'b' * 64, 'data_compatible': True, 'account_changed': False,
            'migrations': [{'database': name, 'target_version': 1, 'steps': 1} for name in ('bench', 'gateway')]},
            {'release': 'system-ci-102-1', 'sequence': [102, 1], 'published_at': '2026-11-11T00:00:00Z',
                'changes': '<img src=x onerror="window.fixtureXss=true">', 'manifest_sha256': 'd' * 64,
                'data_compatible': False, 'account_changed': True, 'compatibility_reason': 'migration_evidence_missing'}],
            'fresh': True, 'checking': False, 'checked_at': '2026-11-11T00:00:00Z', 'check_error': None}
        self.writes = []
        self.requests = []
        self.conflict = False
        self.unavailable = False
        self.hold = None
        self.started = asyncio.Event()
        self.external = []
        self.receipts = {}
        self.receipt_writes = []
        self.receipt_online = False

    async def route(self, route) -> None:
        """在网络前响应实际资源及全部合成接口。

        :param route: Playwright 路由。
        :return: None。
        """
        request = route.request
        parsed = urlsplit(request.url)
        self.requests.append(parsed.path)
        if parsed.netloc != 'system-update.test':
            self.external.append(parsed.netloc)
            await route.abort()
            return
        path = parsed.path
        status, payload = 200, {}
        if path == '/admin/dashboard':
            payload = {'accounts': {'total': 0, 'active': 0, 'error': 0, 'disabled': 0}, 'tokens': {'total': 0}}
        elif path == '/admin/runtime/session':
            payload = {'ok': True}
        elif path == '/runtime/':
            await route.fulfill(content_type='text/html', body='<p>合成环境管理入口</p>')
            return
        elif path == '/admin/runtime/system-update/tui-receipts':
            payload = {'items': list(self.receipts.values()), 'next': None}
        elif path.startswith('/admin/runtime/system-update/tui-receipts/') and request.method == 'POST':
            account, record = path.rsplit('/', 2)[1:]
            current = self.receipts.get(record)
            body = json.loads(request.post_data or '{}')
            self.receipt_writes.append((int(account), record, body))
            if not current or int(account) != current['account_id'] or body.get('revision') != current['revision']:
                status, payload = 409, {'error': '工具回执已经变化，请刷新更新页'}
            elif self.receipt_online:
                payload = {**self.receipts.pop(record), 'state': 'recovered_delivery_unknown'}
            else:
                payload = current
        elif path == '/runtime/api/system-updates/status':
            if self.unavailable:
                status, payload = 503, {'detail': '平台切换中'}
            else:
                payload = copy.deepcopy(self.state)
        elif path == '/runtime/api/system-updates/releases':
            payload = self.catalog
        elif path == '/runtime/api/system-updates/check':
            payload = {'checking': True}
        elif path.startswith('/runtime/api/system-updates/') and request.method == 'POST':
            body = json.loads(request.post_data or '{}')
            self.writes.append({'path': path, 'body': body})
            self.started.set()
            if self.hold:
                await self.hold.wait()
            if self.conflict or body.get('expected_revision') != self.state['revision']:
                status, payload = 409, {'detail': '现场版本已经变化，请刷新后确认'}
            elif path.endswith(('/prepare', '/install', '/rollback')):
                self.state.update(busy=True, revision=str(uuid.uuid4()), operation={
                    'operation_id': body['operation_id'], 'action': path.rsplit('/', 1)[1],
                    'phase': 'preparing' if path.endswith('/prepare') else 'draining', 'target_release': body['target_release'],
                    'created_at': '2026-11-11T00:00:00Z', 'updated_at': '2026-11-11T00:00:00Z',
                    'blockers': ['合成账号：等待原 CLI 作业自然完成'], 'error': None,
                    'steps': [{'phase': 'preparing', 'at': '2026-11-11T00:00:00Z'}] + ([] if path.endswith('/prepare')
                        else [{'phase': 'draining', 'at': '2026-11-11T00:00:05Z'}])})
                payload = self.state['operation']
            elif path.endswith('/retry-account'):
                account = next(item for item in self.state['account_rollout']['accounts'] if item['environment_id'] == body['environment_id'])
                account.update(state='updated', error=None)
                payload = self.state['account_rollout']
            elif path.endswith('/cancel'):
                self.state['operation']['cancel_requested'] = True
                payload = self.state['operation']
            elif path.endswith('/recover'):
                payload = self.state['operation']
        elif path.startswith('/assets/') or path == '/favicon.svg':
            source = source_path(ROOT, 'cc2api/web/dist') / path.lstrip('/')
            await route.fulfill(content_type=mimetypes.guess_type(str(source))[0] or 'application/octet-stream', body=source.read_bytes())
            return
        elif path in ('/', '/updates', '/login', '/environments'):
            await route.fulfill(content_type='text/html', body=(source_path(ROOT, 'cc2api/web/dist/index.html')).read_bytes())
            return
        else:
            status, payload = 404, {'error': '合成夹具未声明接口'}
        await route.fulfill(status=status, content_type='application/json', body=json.dumps(payload, ensure_ascii=False))


async def verify(output: Path) -> dict:
    """执行弹窗交互及移动端验收。

    :param output: 全新证据目录。
    :return: 脱敏结果。
    """
    from playwright.async_api import async_playwright, expect
    output.mkdir(parents=True, exist_ok=True)
    errors, cases, total_writes = [], [], 0
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        async def page_for(fixture, width=1280, height=900):
            context = await browser.new_context(viewport={'width': width, 'height': height}, timezone_id='Asia/Shanghai')
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth', 'synthetic-password')")
            await context.route('**/*', fixture.route)
            page = await context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(BASE + '/updates')
            dialog = page.locator('.system-update-dialog')
            await expect(dialog.get_by_role('heading', name='系统更新', exact=True)).to_be_visible()
            return context, page, dialog

        async def install_plan(dialog):
            return dialog.get_by_role('spinbutton', name='在途等待上限（分钟）')

        # 1. 桌面：版本记录、兼容原因、迁移计划、文本转义；弹窗居中；关闭、Esc 与嵌套确认零写入。
        fixture = UpdateFixture()
        context, page, dialog = await page_for(fixture)
        await expect(dialog.locator('[data-update-view=overview]')).to_be_visible()
        await expect(dialog.get_by_role('button', name='安装更新', exact=True)).to_be_enabled()
        await dialog.get_by_role('button', name='版本记录与回退', exact=True).click()
        await expect(dialog.locator('[data-update-view=history]')).to_be_visible()
        await dialog.get_by_role('button', name='查看历史版本与回退', exact=False).click()
        await expect(dialog.get_by_role('button', name='待验证兼容')).to_be_disabled()
        await dialog.locator('[data-release-card]').nth(1).locator('button[aria-expanded]').click()
        await expect(dialog.get_by_text('此来源版本的升级与回退演练证据待发布端补齐。')).to_be_visible()
        await dialog.locator('[data-release-card]').first.locator('button[aria-expanded]').click()
        await expect(dialog.get_by_text('平台数据库 → 版本 1 · 1 项登记')).to_be_visible()
        assert await page.evaluate('window.fixtureXss') is None
        await page.screenshot(path=str(output / 'history-1280.png'))
        # 版本记录中的安装走二次确认；Esc 只关闭上层确认框。
        await dialog.locator('[data-release-card]').first.get_by_role('button', name='安装更新', exact=True).click()
        confirm = page.get_by_role('dialog', name='确认安装更新')
        await expect(confirm).to_be_visible()
        await expect(confirm.get_by_role('spinbutton', name='在途等待上限（分钟）')).to_have_value('1')
        await page.keyboard.press('Escape')
        await expect(confirm).to_be_hidden()
        await expect(dialog).to_be_visible()
        await dialog.locator('[data-release-card]').first.get_by_role('button', name='安装更新', exact=True).click()
        await confirm.get_by_role('button', name='取消', exact=True).click()
        await expect(confirm).to_be_hidden()
        assert not fixture.writes
        await dialog.get_by_role('button', name='返回', exact=True).click()
        await expect(dialog.locator('[data-update-view=overview]')).to_be_visible()
        for width, height in [(1280, 900), (390, 900), (390, 300)]:
            await page.set_viewport_size({'width': width, 'height': height})
            # 入场动画与视口变化后的重新布局完成后再量尺寸。
            await page.wait_for_timeout(300)
            await dialog.evaluate('e => Promise.all(e.getAnimations().map(a => a.finished))')
            box = await dialog.bounding_box()
            assert box and abs(box['x'] + box['width'] / 2 - width / 2) <= 1, box
            assert abs(box['y'] + box['height'] / 2 - height / 2) <= 1, box
            assert box['y'] >= 14 and box['y'] + box['height'] <= height - 14, box
            control = await dialog.get_by_role('button', name='安装更新', exact=True).bounding_box()
            assert control and control['y'] >= 0 and control['y'] + control['height'] <= height, control
            await page.screenshot(path=str(output / f'centered-dialog-{width}-{height}.png'))
        await page.set_viewport_size({'width': 1280, 'height': 900})
        await page.mouse.click(5, 5)
        await expect(dialog).to_be_hidden()
        await expect(page).to_have_url(BASE + '/')
        await page.goto(BASE + '/updates')
        await expect(dialog).to_be_visible()
        await page.keyboard.press('Escape')
        await expect(dialog).to_be_hidden()
        await expect(page).to_have_url(BASE + '/')
        assert not fixture.writes
        cases.append('桌面版本记录、具体兼容原因、迁移计划、普通文本转义、居中与矮视口、嵌套确认 Esc、遮罩与 Esc 关闭回到账号页零写入')
        await context.close()

        # 2. 直接安装：等待上限默认一分钟，修改后关闭重开仍为一分钟，直接安装提交 60 秒。
        fixture = UpdateFixture()
        context, page, dialog = await page_for(fixture, 390)
        minutes = await install_plan(dialog)
        await expect(minutes).to_have_value('1')
        await minutes.fill('5')
        await page.keyboard.press('Escape')
        await expect(dialog).to_be_hidden()
        await page.goto(BASE + '/updates')
        await expect(await install_plan(dialog)).to_have_value('1')
        assert not fixture.writes
        await dialog.get_by_role('button', name='安装更新', exact=True).click()
        await expect(dialog.locator('[data-update-view=progress]')).to_be_visible()
        assert len(fixture.writes) == 1 and fixture.writes[0]['body']['drain_timeout_seconds'] == 60
        cases.append('初开及修改后关闭重开均默认一分钟，直接安装提交60秒')
        await context.close()

        # 3. 移动端：30 分钟双击只登记一次；步骤与时间；断线重连；快照与迁移；数据恢复；完成与刷新。
        fixture = UpdateFixture()
        context, page, dialog = await page_for(fixture, 390)
        await (await install_plan(dialog)).fill('30')
        await page.screenshot(path=str(output / 'install-plan-390.png'), full_page=True)
        await dialog.get_by_role('button', name='安装更新', exact=True).dblclick()
        progress = dialog.locator('[data-update-view=progress]')
        await expect(progress).to_be_visible()
        assert len(fixture.writes) == 1
        body = fixture.writes[0]['body']
        assert body['drain_timeout_seconds'] == 1800 and body['target_manifest_sha256'] == 'b' * 64
        assert str(uuid.UUID(body['operation_id'])) == body['operation_id']
        await expect(progress.get_by_text('合成账号：等待原 CLI 作业自然完成')).to_be_visible()
        active = progress.locator('[data-update-step][data-state=active]')
        await expect(active).to_contain_text('等待在途完成')
        await expect(active).to_contain_text('08:00:05')
        await expect(active).to_contain_text('仍有 1 项在途工作，新工作已暂缓')
        await expect(progress.locator('[data-update-step][data-state=done]').first).to_contain_text('08:00:00')
        await expect(progress.locator('[data-update-step][data-state=pending]').first).to_contain_text('保存数据库快照')
        await expect(dialog.get_by_role('button', name='取消等待', exact=True)).to_be_visible()
        await dialog.get_by_role('button', name='操作详情与数据库快照', exact=True).click()
        details = dialog.locator('[data-update-view=details]')
        await expect(details).to_contain_text(body['operation_id'])
        fixture.unavailable = True
        await expect(dialog.get_by_role('alert').first).to_contain_text('正在重新连接', timeout=7000)
        fixture.unavailable = False
        operation = fixture.state['operation']
        operation['steps'] += [{'phase': 'switching', 'at': '2026-11-11T00:01:00Z'}, {'phase': 'snapshotting', 'at': '2026-11-11T00:01:01Z'}]
        operation.update(phase='snapshotting', blockers=[],
            database_snapshot={'state': 'verified', 'bytes': 1048576, 'completed_at': '2026-11-11T00:00:00Z'})
        await expect(details.get_by_text('数据库快照已校验 · 1.0 MiB')).to_be_visible(timeout=15000)
        await dialog.get_by_role('button', name='返回', exact=True).click()
        await expect(active).to_contain_text('保存数据库快照', timeout=15000)
        # 越过取消边界的第一次切换不单独成行。
        await expect(progress.locator('[data-update-step][data-state=done]')).to_have_count(2)
        operation['steps'].append({'phase': 'migrating', 'at': '2026-11-11T00:01:30Z'})
        operation.update(phase='migrating', database_migrations={
            'bench': {'state': 'completed', 'target_version': 1}, 'gateway': {'state': 'running', 'target_version': 1}})
        await expect(active).to_contain_text('平台数据库 迁移完成 · 网关数据库 正在迁移', timeout=15000)
        await page.screenshot(path=str(output / 'migrations-390.png'), full_page=True)
        await dialog.get_by_role('button', name='操作详情与数据库快照', exact=True).click()
        await expect(details.get_by_text('网关数据库 · 目标版本 1 · 正在迁移')).to_be_visible()
        operation['database_migrations']['gateway']['state'] = 'synthetic-new-state'
        await expect(details.get_by_text('网关数据库 · 目标版本 1 · synthetic-new-state', exact=True)).to_be_visible(timeout=15000)
        await dialog.get_by_role('button', name='返回', exact=True).click()
        operation['steps'] += [{'phase': 'restoring', 'at': '2026-11-11T00:02:00Z'}, {'phase': 'restoring_data', 'at': '2026-11-11T00:02:01Z'}]
        operation.update(phase='restoring_data')
        await expect(active).to_contain_text('正在恢复数据库', timeout=15000)
        fixture.state.update(busy=False, current_release='system-ci-101-1')
        fixture.state['components']['control'].update(release='ci-101-1', reference='ghcr.io/silentflower/vibebench-v3-control:v3-ci-101-1')
        operation['steps'] = operation['steps'][:5] + [{'phase': 'switching', 'at': '2026-11-11T00:02:30Z'}, {'phase': 'succeeded', 'at': '2026-11-11T00:03:00Z'}]
        operation.update(phase='succeeded', blockers=[])
        await expect(progress.get_by_role('status')).to_contain_text('更新完成', timeout=15000)
        await expect(progress.locator('[data-update-step][data-state=active]')).to_have_count(0)
        await page.screenshot(path=str(output / 'succeeded-390.png'), full_page=True)
        await dialog.get_by_role('button', name='完成', exact=True).click()
        await expect(dialog.locator('[data-update-view=overview]')).to_contain_text('上次操作 · 更新完成')
        await page.reload()
        await expect(dialog.locator('[data-update-view=overview]')).to_contain_text('上次操作 · 更新完成')
        await dialog.get_by_role('button', name='查看记录', exact=True).click()
        await expect(progress.get_by_role('status')).to_contain_text('更新完成')
        assert len(fixture.writes) == 1
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        await page.screenshot(path=str(output / 'updates-390.png'), full_page=True)
        total_writes += len(fixture.writes)
        cases.append('移动端、冻结参数、双击幂等、步骤与时间、切换断线、快照和迁移进度、数据恢复、完成与刷新后的上次操作')
        await context.close()

        # 4. 409：弹窗内提示并禁用安装，不自动重放。
        fixture = UpdateFixture()
        fixture.conflict = True
        context, page, dialog = await page_for(fixture)
        await dialog.get_by_role('button', name='安装更新', exact=True).click()
        await expect(dialog.get_by_role('alert').filter(has_text='现场版本已经变化')).to_be_visible()
        await expect(dialog.get_by_role('button', name='安装更新', exact=True)).to_be_disabled()
        await page.wait_for_timeout(2500)
        assert len(fixture.writes) == 1
        total_writes += len(fixture.writes)
        cases.append('409 弹窗内提示、禁用安装并阻止旧现场自动重放')
        await context.close()

        # 5. 未接入。
        fixture = UpdateFixture()
        fixture.state['installed'] = False
        fixture.state['message'] = '需要首次接入系统更新底座'
        context, page, dialog = await page_for(fixture)
        await expect(dialog.get_by_role('heading', name='首次接入系统更新')).to_be_visible()
        assert await dialog.get_by_role('button', name='安装更新', exact=True).count() == 0
        assert not fixture.writes
        cases.append('缺少底座时展示接入状态')
        await context.close()

        # 6. 回退二次确认默认一分钟；取消等待使用原操作身份。
        fixture = UpdateFixture()
        context, page, dialog = await page_for(fixture)
        await dialog.get_by_role('button', name='版本记录与回退', exact=True).click()
        await dialog.get_by_role('button', name='查看历史版本与回退', exact=False).click()
        await dialog.get_by_role('button', name='回退到此版本').click()
        confirm = page.get_by_role('dialog', name='确认版本回退')
        await expect(confirm).to_be_visible()
        await expect(confirm.get_by_role('spinbutton', name='在途等待上限（分钟）')).to_have_value('1')
        await confirm.get_by_role('button', name='确认执行').click()
        await expect(dialog.locator('[data-update-view=progress]')).to_be_visible()
        assert fixture.writes[0]['path'].endswith('/rollback')
        assert fixture.writes[0]['body']['target_release'] == 'system-ci-99-1'
        assert fixture.writes[0]['body']['drain_timeout_seconds'] == 60
        await dialog.get_by_role('button', name='取消等待').click()
        assert fixture.writes[-1]['path'].endswith('/cancel')
        total_writes += len(fixture.writes)
        cases.append('回退二次确认冻结目标，取消等待使用原操作身份')
        await context.close()

        # 6b. 二次确认遇到 409：确认框保留并提示，确认按钮禁用，不自动重放。
        fixture = UpdateFixture()
        fixture.conflict = True
        context, page, dialog = await page_for(fixture)
        await dialog.get_by_role('button', name='版本记录与回退', exact=True).click()
        await dialog.get_by_role('button', name='查看历史版本与回退', exact=False).click()
        await dialog.get_by_role('button', name='回退到此版本').click()
        confirm = page.get_by_role('dialog', name='确认版本回退')
        await confirm.get_by_role('button', name='确认执行').click()
        await expect(confirm.get_by_role('alert')).to_contain_text('现场版本已经变化')
        await expect(confirm.get_by_role('button', name='确认执行')).to_be_disabled()
        await expect(confirm.get_by_role('button', name='取消', exact=True)).to_be_enabled()
        await page.wait_for_timeout(2500)
        assert len(fixture.writes) == 1 and fixture.writes[0]['path'].endswith('/rollback')
        total_writes += len(fixture.writes)
        cases.append('二次确认 409 保留确认框、禁用确认并阻止自动重放')
        await context.close()

        # 7. 快速切换：等待在途改称关闭推理连接；中央恢复接单后提示随轮询更新，远程节点后台独立更新并可进入节点页。
        fixture = UpdateFixture()
        fixture.state.update(busy=True, operation={
            'operation_id': str(uuid.uuid4()), 'phase': 'draining', 'action': 'install',
            'target_release': 'system-ci-101-1', 'fast_transition': True, 'blockers': [],
            'admission_blocked_at': '2026-11-11T00:00:00Z', 'updated_at': '2026-11-11T00:00:00Z',
            'cluster_nodes': {'phase': 'background', 'nodes': [{'node_id': 2, 'name': 'main', 'phase': 'background', 'running': False}]},
        })
        context, page, dialog = await page_for(fixture, 390)
        progress = dialog.locator('[data-update-view=progress]')
        await expect(progress.locator('[data-update-step][data-state=active]')).to_contain_text('正在关闭推理连接')
        await expect(progress.locator('[data-update-maintenance]')).to_have_text('新请求暂缓。系统正在关闭旧推理连接，并等待资源释放。')
        await expect(progress.get_by_text('远程节点将在中央切换后独立更新', exact=True)).to_be_visible()
        await expect(progress.locator('.su-nodes')).to_have_count(0)
        fixture.state['operation'].update(phase='cleaning', admission_reopened_at='2026-11-11T00:00:10Z')
        await expect(progress.get_by_text('平台已恢复接单。', exact=True)).to_be_visible(timeout=7000)
        await expect(progress.locator('.su-pill')).to_have_text('平台已恢复接单')
        await expect(progress.get_by_role('link', name='查看节点进度')).to_have_attribute('href', '/nodes')
        await expect(progress.get_by_text('远程节点独立更新', exact=True)).to_be_visible()
        assert not fixture.writes
        cases.append('快速切换关闭推理连接；中央恢复接单后，远程节点继续独立更新并可进入节点页')
        await context.close()

        # 8. 分步更新：下载直接提交并继续接单；下载完成后刷新，安装方式改为立即重启，不问等待上限并带下载操作 ID；
        #    恢复接单后在账号后台更新中单项重试。
        fixture = UpdateFixture()
        fixture.state['staged_updates'] = True
        context, page, dialog = await page_for(fixture, 390)
        plan = dialog.locator('[data-update-plan]')
        await expect(plan).to_have_attribute('data-update-plan', 'prepare')
        await expect(plan).to_contain_text('先在后台下载并校验')
        await expect(await install_plan(dialog)).to_have_count(0)
        await dialog.get_by_role('button', name='下载更新', exact=True).click()
        progress = dialog.locator('[data-update-view=progress]')
        await expect(progress.locator('[data-update-step][data-state=active]')).to_contain_text('下载与校验')
        await expect(progress.locator('.su-pill')).to_have_text('正在后台准备')
        await expect(progress.locator('[data-update-maintenance]')).to_have_text('后台准备候选镜像与项目库，平台继续接单。')
        assert len(fixture.writes) == 1 and fixture.writes[0]['path'].endswith('/prepare')
        download = fixture.writes[0]['body']
        assert download['drain_timeout_seconds'] == 60 and 'prepared_operation_id' not in download, download
        readings = {'source': 'registry', 'component': 'control', 'state': 'downloading',
            'downloaded_bytes': 1024, 'total_bytes': 4096}
        fixture.state['operation']['download_progress'] = readings
        transfer = progress.locator('[data-update-download]')
        await expect(transfer).to_contain_text('已下载 1 KiB / 4 KiB · 25%', timeout=7000)
        await expect(transfer.get_by_role('progressbar')).to_have_attribute('aria-valuenow', '25')
        readings.update(component='account', downloaded_bytes=731439795, total_bytes=None)
        await page.reload()
        await expect(transfer).to_contain_text('已下载 697.6 MiB · 总大小待获取')
        await transfer.locator('summary').click()
        await expect(transfer.get_by_text('已下载 731,439,795 B', exact=True)).to_be_visible()
        await transfer.locator('summary').press('Enter')
        await expect(transfer.get_by_text('已下载 731,439,795 B', exact=True)).to_be_hidden()
        await expect(transfer.get_by_role('progressbar')).to_have_count(0)
        await page.emulate_media(reduced_motion='reduce')
        await expect(transfer.locator('.su-download-state svg')).to_have_css('animation-name', 'none')
        await page.screenshot(path=str(output / 'download-unknown-390.png'), full_page=True)
        await page.set_viewport_size({'width': 1280, 'height': 900})
        await page.evaluate("localStorage.setItem('flower2api.theme-mode','dark')")
        readings.update(total_bytes=1073741824)
        await page.reload()
        track = transfer.get_by_role('progressbar')
        await expect(track).to_be_visible()
        await expect(page.locator('html')).to_have_attribute('data-ui-scheme', 'dark')
        assert await track.evaluate('''track => {
            const marker = document.createElement('i')
            marker.style.backgroundColor = 'var(--ui-color-track)'
            track.append(marker)
            const matches = getComputedStyle(marker).backgroundColor === getComputedStyle(track).backgroundColor
            marker.remove()
            return matches
        }''')
        await expect(track).to_have_attribute('aria-valuenow', '68')
        await page.screenshot(path=str(output / 'download-dark-1280.png'), full_page=True)
        await page.set_viewport_size({'width': 390, 'height': 900})
        await page.evaluate("localStorage.removeItem('flower2api.theme-mode')")
        await page.reload()
        readings.update(source='bundle', component='bundle', state='verifying', downloaded_bytes=8192, total_bytes=8192)
        await expect(transfer).to_contain_text('正在校验', timeout=7000)
        await expect(transfer).to_contain_text('已下载 8 KiB / 8 KiB · 100%')
        fixture.state.update(busy=False, prepared_candidate={'operation_id': download['operation_id'],
            'target_release': download['target_release'], 'manifest_sha256': download['target_manifest_sha256'],
            'fast_transition': True})
        fixture.state['operation'].update(phase='prepared', fast_transition=True, blockers=[])
        await expect(progress.locator('.su-pill')).to_have_text('待重启', timeout=7000)
        await expect(progress.get_by_text('重启会断开正在执行的推理。控制服务就绪后可重新请求。', exact=True)).to_be_visible()
        fixture.state['prepared_candidate']['manifest_sha256'] = 'e' * 64
        await page.reload()
        await expect(dialog.get_by_role('button', name='立即重启', exact=True)).to_have_count(0)
        fixture.state['prepared_candidate']['manifest_sha256'] = download['target_manifest_sha256']
        await page.reload()
        await expect(progress.locator('.su-pill')).to_have_text('待重启')
        await expect(await install_plan(dialog)).to_have_count(0)
        await page.screenshot(path=str(output / 'restart-390.png'), full_page=True)
        await dialog.get_by_role('button', name='立即重启', exact=True).evaluate('(button) => { button.click(); button.click(); }')
        await expect(progress.locator('.su-pill')).not_to_have_text('待重启', timeout=7000)
        restart = fixture.writes[-1]
        assert len(fixture.writes) == 2 and restart['path'].endswith('/install'), fixture.writes
        assert restart['body']['prepared_operation_id'] == download['operation_id'] and restart['body']['drain_timeout_seconds'] == 60
        assert restart['body']['operation_id'] != download['operation_id']
        active = fixture.state['operation']
        active.update(phase='succeeded', admission_reopened_at='2026-11-11T00:00:10Z', blockers=[])
        fixture.state.update(busy=False, current_release=active['target_release'], prepared_candidate=None,
            account_rollout={'operation_id': active['operation_id'], 'target_release': active['target_release'], 'accounts': [
                {'environment_id': 'retry-environment', 'name': '账号 A', 'state': 'waiting', 'error': '账号仍有活动'},
                {'environment_id': 'settled-environment', 'name': '账号 B', 'state': 'updated'}]})
        await page.reload()
        rollout = dialog.locator('.su-rollout')
        await expect(rollout).to_contain_text('账号后台更新')
        await expect(rollout.locator('[data-rollout-state=waiting]')).to_contain_text('账号仍有活动')
        await rollout.get_by_role('button', name='重试', exact=True).click()
        assert fixture.writes[-1]['path'].endswith('/' + active['operation_id'] + '/retry-account')
        assert fixture.writes[-1]['body'] == {'environment_id': 'retry-environment', 'expected_revision': fixture.state['revision']}
        await expect(rollout.get_by_text('已更新', exact=True)).to_have_count(2)
        await expect(rollout.get_by_role('button', name='重试', exact=True)).to_have_count(0)
        await page.screenshot(path=str(output / 'account-rollout-390.png'), full_page=True)
        await dialog.get_by_role('button', name='查看记录', exact=True).click()
        await expect(dialog.locator('[data-update-view=progress]').get_by_text('平台已恢复接单。', exact=True)).to_be_visible()
        await expect(rollout).to_be_visible()
        total_writes += len(fixture.writes)
        cases.append('下载直接提交并继续接单，下载后刷新继续重启（带下载操作 ID、不问期限），恢复接单后独立重试单账号更新')
        await context.close()

        # 8b. 已下载但不支持快速切换：兼容安装保留在途等待上限并带下载操作 ID；版本记录里下载直接提交、重启走重启确认框。
        fixture = UpdateFixture()
        fixture.state.update(staged_updates=True, prepared_candidate={'operation_id': 'prepared-compatible',
            'target_release': 'system-ci-101-1', 'manifest_sha256': 'b' * 64, 'fast_transition': False})
        context, page, dialog = await page_for(fixture, 390)
        await expect(dialog.locator('[data-update-view=overview] .su-head .su-pill')).to_have_text('已下载更新')
        await expect(dialog.locator('[data-update-plan]')).to_have_attribute('data-update-plan', 'install')
        await (await install_plan(dialog)).fill('5')
        await dialog.get_by_role('button', name='安装更新', exact=True).click()
        await expect(dialog.locator('[data-update-view=progress]')).to_be_visible()
        assert len(fixture.writes) == 1 and fixture.writes[0]['path'].endswith('/install'), fixture.writes
        assert fixture.writes[0]['body']['prepared_operation_id'] == 'prepared-compatible'
        assert fixture.writes[0]['body']['drain_timeout_seconds'] == 300
        total_writes += len(fixture.writes)
        await context.close()

        fixture = UpdateFixture()
        fixture.state['staged_updates'] = True
        context, page, dialog = await page_for(fixture)
        await dialog.get_by_role('button', name='版本记录与回退', exact=True).click()
        latest_card = dialog.locator('[data-release-card]').first
        await latest_card.get_by_role('button', name='下载更新', exact=True).click()
        await expect(dialog.locator('[data-update-view=progress]')).to_be_visible()
        await expect(page.get_by_role('dialog', name='确认安装更新')).to_have_count(0)
        assert len(fixture.writes) == 1 and fixture.writes[0]['path'].endswith('/prepare'), fixture.writes
        download = fixture.writes[0]['body']
        fixture.state.update(busy=False, prepared_candidate={'operation_id': download['operation_id'],
            'target_release': download['target_release'], 'manifest_sha256': download['target_manifest_sha256'], 'fast_transition': True})
        fixture.state['operation'].update(phase='prepared', fast_transition=True, blockers=[])
        await page.reload()
        await dialog.get_by_role('button', name='返回', exact=True).click()
        await dialog.get_by_role('button', name='版本记录与回退', exact=True).click()
        await latest_card.get_by_role('button', name='立即重启', exact=True).click()
        confirm = page.get_by_role('dialog', name='重启并切换版本')
        await expect(confirm).to_contain_text('重启会断开正在执行的推理。控制服务就绪后可重新请求。')
        await expect(confirm.get_by_role('spinbutton')).to_have_count(0)
        await confirm.get_by_role('button', name='立即重启', exact=True).click()
        await expect(confirm).to_be_hidden()
        assert len(fixture.writes) == 2 and fixture.writes[1]['path'].endswith('/install'), fixture.writes
        assert fixture.writes[1]['body']['prepared_operation_id'] == download['operation_id'] and fixture.writes[1]['body']['drain_timeout_seconds'] == 60
        total_writes += len(fixture.writes)
        cases.append('已下载的兼容安装带期限与下载操作 ID；版本记录中下载直接提交，重启走重启确认框且不问期限')
        await context.close()

        # 9. 候选失败与恢复两组健康探测分别展示，保留状态码、耗时与次数；暂停 / 恢复接单时间进入操作详情。
        fixture = UpdateFixture()
        fixture.state['operation'] = {'operation_id': str(uuid.uuid4()), 'phase': 'restored', 'action': 'install',
            'target_release': 'system-ci-101-1', 'updated_at': '2026-11-11T00:00:00Z',
            'admission_blocked_at': '2026-11-11T00:00:00Z', 'admission_reopened_at': '2026-11-11T00:00:20Z',
            'error': '候选控制服务健康验收超时', 'control_health': {
                'candidate': {'gateway': {'state': 'ready', 'attempts': 2, 'http_status': 200, 'duration_ms': 12},
                    'orchestrator': {'state': 'http_error', 'attempts': 2, 'http_status': 503, 'duration_ms': 104}},
                'restore': {'gateway': {'state': 'ready', 'attempts': 1, 'http_status': 200},
                    'orchestrator': {'state': 'ready', 'attempts': 1, 'http_status': 200}}}}
        context, page, dialog = await page_for(fixture, 390)
        await expect(dialog.locator('[data-update-view=overview]')).to_contain_text('上次操作 · 已恢复原版本')
        await dialog.get_by_role('button', name='查看记录', exact=True).click()
        progress = dialog.locator('[data-update-view=progress]')
        await expect(progress.locator('.su-pill')).to_have_text('已恢复原版本')
        await expect(progress.get_by_role('alert')).to_contain_text('候选控制服务健康验收超时')
        await dialog.get_by_role('button', name='操作详情与数据库快照', exact=True).click()
        details = dialog.locator('[data-update-view=details]')
        await expect(details.get_by_role('heading', name='新版本健康检查', exact=True)).to_be_visible()
        await expect(details.get_by_text('网关 · 就绪 · HTTP 200 · 0.01 秒 · 第 2 次', exact=True)).to_be_visible()
        await expect(details.get_by_text('调度器 · 响应错误 · HTTP 503 · 0.10 秒 · 第 2 次', exact=True)).to_be_visible()
        await expect(details.get_by_role('heading', name='恢复原版本健康检查', exact=True)).to_be_visible()
        await expect(details.get_by_text('调度器 · 就绪 · HTTP 200 · 第 1 次', exact=True)).to_be_visible()
        await expect(details.locator('.su-ids dt')).to_contain_text(['目标发行', '操作 ID', '更新时间', '暂停接单', '恢复接单'])
        await page.screenshot(path=str(output / 'control-health-390.png'), full_page=True)
        assert not fixture.writes
        cases.append('候选失败与恢复探测分别展示，保留状态码及耗时；操作详情含暂停与恢复接单时间')
        await context.close()

        # 10. 等待对账：打开即进度视图；旧操作无步骤记录正常显示；恢复确认居中并沿用原操作身份。
        fixture = UpdateFixture()
        operation_id = str(uuid.uuid4())
        fixture.state.update(busy=True, operation={'operation_id': operation_id, 'phase': 'reconcile',
            'action': 'install', 'target_release': 'system-ci-101-1'})
        context, page, dialog = await page_for(fixture, 390)
        await expect(dialog.locator('[data-update-view=progress]')).to_contain_text('本次操作没有步骤记录。')
        await expect(dialog.locator('[data-update-view=progress]').get_by_role('status')).to_contain_text('等待恢复与对账')
        await dialog.get_by_role('button', name='恢复操作', exact=True).click()
        confirm = page.get_by_role('dialog', name='恢复本次操作')
        await expect(confirm).to_be_visible()
        await confirm.evaluate('e => Promise.all(e.getAnimations().map(a => a.finished))')
        box = await confirm.bounding_box()
        assert box and abs(box['x'] + box['width'] / 2 - 195) <= 1, box
        await confirm.get_by_role('button', name='开始恢复', exact=True).click()
        assert len(fixture.writes) == 1 and fixture.writes[0]['path'].endswith('/' + operation_id + '/recover')
        assert fixture.writes[0]['body'] == {'expected_revision': fixture.state['revision']}
        total_writes += len(fixture.writes)
        cases.append('等待对账直接显示进度，无步骤记录的旧操作正常，恢复窗口居中并沿用原操作身份')
        await context.close()
        # 单条 V2 回执离线提示、恢复联系、精确账号和修订，以及同账号后台续办。
        fixture = UpdateFixture()
        receipt, peer = str(uuid.uuid4()), str(uuid.uuid4())
        fixture.receipts = {
            receipt: {'id': receipt, 'account_id': 3, 'account_name': '离线节点账号', 'revision': 'a' * 64, 'state': 'deferred'},
            peer: {'id': peer, 'account_id': 4, 'account_name': '另一账号', 'revision': 'b' * 64, 'state': 'waiting'},
        }
        fixture.state['account_rollout'] = {'operation_id': str(uuid.uuid4()), 'target_release': 'system-ci-100-1',
            'accounts': [{'environment_id': 'matched', 'gateway_account_id': 3, 'name': '离线节点账号', 'state': 'waiting'},
                         {'environment_id': 'other', 'gateway_account_id': 4, 'name': '另一账号', 'state': 'waiting'}]}
        context, page, dialog = await page_for(fixture)
        row = dialog.locator('[data-tui-receipt-state=deferred]')
        await expect(row).to_contain_text('该账号延期、平台可继续')
        await expect(dialog.get_by_role('button', name='安装更新', exact=True)).to_be_enabled()
        await row.get_by_role('button', name='核对并恢复').click()
        await expect(page.get_by_text('该账号延期、平台可继续', exact=True).last).to_be_visible()
        assert fixture.receipt_writes == [(3, receipt, {'revision': 'a' * 64})]
        assert not fixture.writes
        fixture.receipt_online = True
        await row.get_by_role('button', name='核对并恢复').click()
        await expect(row).to_have_count(0)
        await expect(dialog.locator('[data-tui-receipt-state=waiting]')).to_contain_text('另一账号')
        await expect(dialog.locator('[data-rollout-state=updated]')).to_contain_text('离线节点账号')
        assert fixture.writes[0]['body']['environment_id'] == 'matched'
        assert fixture.writes[0]['path'].endswith('/retry-account')
        assert fixture.receipt_writes == [(3, receipt, {'revision': 'a' * 64})] * 2
        total_writes += len(fixture.writes) + len(fixture.receipt_writes)
        cases.append('工具回执失联延期、恢复联系后单条核对及账号续办、其余回执保留')
        await context.close()
        await browser.close()
    if errors:
        raise AssertionError('浏览器脚本异常：' + '; '.join(errors))
    result = {'status': 'passed', 'cases': cases, 'script_errors': errors, 'synthetic_writes': total_writes,
        'real_model_requests': 0, 'evidence': '真实 Vue 弹窗与完全合成 API 的交互验证'}
    (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    """输出可复核浏览器证据。

    :return: None。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.output)), ensure_ascii=False))


if __name__ == '__main__':
    main()
