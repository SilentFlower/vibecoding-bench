"""真实 Vue 构建配合合成 API 验证系统更新页面，全部网络在浏览器前拦截。"""
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
            elif path.endswith(('/install', '/rollback')):
                self.state.update(busy=True, revision=str(uuid.uuid4()), operation={
                    'operation_id': body['operation_id'], 'action': path.rsplit('/', 1)[1],
                    'phase': 'draining', 'target_release': body['target_release'],
                    'created_at': '2026-11-11T00:00:00Z', 'updated_at': '2026-11-11T00:00:00Z',
                    'blockers': ['合成账号：等待原 CLI 作业自然完成'], 'error': None})
                payload = self.state['operation']
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
    """执行浏览器交互及移动端验收。

    :param output: 全新证据目录。
    :return: 脱敏结果。
    """
    from playwright.async_api import async_playwright, expect
    output.mkdir(parents=True, exist_ok=True)
    errors, cases, total_writes = [], [], 0
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        async def page_for(fixture, width=1280):
            context = await browser.new_context(viewport={'width': width, 'height': 900})
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth', 'synthetic-password')")
            await context.route('**/*', fixture.route)
            page = await context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(BASE + '/updates')
            await expect(page.get_by_role('heading', name='系统更新', exact=True)).to_be_visible()
            return context, page

        fixture = UpdateFixture()
        context, page = await page_for(fixture)
        await expect(page.get_by_role('button', name='安装更新', exact=True)).to_be_visible()
        await expect(page.get_by_role('button', name='兼容验证待补齐')).to_be_disabled()
        await expect(page.get_by_text('此来源版本的升级与回退演练证据待发布端补齐。')).to_be_visible()
        await expect(page.get_by_text('平台数据库 → 版本 1 · 1 项登记')).to_be_visible()
        assert await page.evaluate('window.fixtureXss') is None
        await page.screenshot(path=str(output / 'updates-1280.png'), full_page=True)
        await page.get_by_role('button', name='安装更新', exact=True).click()
        await expect(page.locator('dialog')).to_be_visible()
        assert not fixture.writes
        await page.get_by_role('button', name='取消', exact=True).click()
        assert not fixture.writes
        await page.get_by_role('button', name='安装更新', exact=True).click()
        await page.keyboard.press('Escape')
        await expect(page.locator('dialog')).not_to_be_visible()
        assert not fixture.writes
        cases.append('桌面样式、具体兼容原因、迁移计划、普通文本转义、取消和 Esc 零安装写入')
        await context.close()

        fixture = UpdateFixture()
        context, page = await page_for(fixture, 390)
        await page.get_by_role('button', name='安装更新', exact=True).click()
        await page.get_by_role('combobox').select_option('30')
        await page.screenshot(path=str(output / 'install-dialog-390.png'), full_page=True)
        await page.get_by_role('button', name='确认执行').dblclick()
        await expect(page.get_by_role('heading', name='等待在途完成')).to_be_visible()
        assert len(fixture.writes) == 1
        body = fixture.writes[0]['body']
        assert body['drain_timeout_seconds'] == 1800 and body['target_manifest_sha256'] == 'b' * 64
        assert str(uuid.UUID(body['operation_id'])) == body['operation_id']
        await expect(page.get_by_text('合成账号：等待原 CLI 作业自然完成')).to_be_visible()
        fixture.unavailable = True
        await expect(page.get_by_role('alert')).to_contain_text('正在重新连接', timeout=7000)
        fixture.unavailable = False
        fixture.state['operation'].update(phase='snapshotting', blockers=[],
            database_snapshot={'state': 'verified', 'bytes': 1048576, 'completed_at': '2026-11-11T00:00:00Z'})
        await expect(page.get_by_role('heading', name='保存数据库快照', exact=True)).to_be_visible(timeout=15000)
        await expect(page.get_by_text('数据库快照已校验 · 1.0 MiB')).to_be_visible()
        fixture.state['operation'].update(phase='migrating', database_migrations={
            'bench': {'state': 'completed', 'target_version': 1}, 'gateway': {'state': 'running', 'target_version': 1}})
        await expect(page.get_by_role('heading', name='执行数据库迁移', exact=True)).to_be_visible(timeout=15000)
        await expect(page.get_by_text('网关数据库 · 目标版本 1 · 正在迁移')).to_be_visible()
        await page.screenshot(path=str(output / 'migrations-390.png'), full_page=True)
        fixture.state['operation']['database_migrations']['gateway']['state'] = 'synthetic-new-state'
        await expect(page.get_by_text('网关数据库 · 目标版本 1 · 未知状态：synthetic-new-state')).to_be_visible(timeout=15000)
        fixture.state['operation'].update(phase='restoring_data')
        await expect(page.get_by_role('heading', name='正在恢复数据库', exact=True)).to_be_visible(timeout=15000)
        fixture.state.update(busy=False, current_release='system-ci-101-1')
        fixture.state['components']['control'].update(release='ci-101-1', reference='ghcr.io/silentflower/vibebench-v3-control:v3-ci-101-1')
        fixture.state['operation'].update(phase='succeeded', blockers=[])
        await expect(page.get_by_role('heading', name='更新完成', exact=True)).to_be_visible(timeout=15000)
        await page.reload()
        await expect(page.get_by_role('heading', name='更新完成', exact=True)).to_be_visible()
        assert len(fixture.writes) == 1
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        await page.screenshot(path=str(output / 'updates-390.png'), full_page=True)
        total_writes += len(fixture.writes)
        cases.append('移动端、冻结参数、双击幂等、切换断线、快照和迁移进度、数据恢复、刷新恢复')
        await context.close()

        fixture = UpdateFixture()
        fixture.conflict = True
        context, page = await page_for(fixture)
        await page.get_by_role('button', name='安装更新', exact=True).click()
        await page.get_by_role('button', name='确认执行').click()
        await expect(page.locator('dialog')).to_be_visible()
        await expect(page.get_by_role('button', name='确认执行')).to_be_disabled()
        await expect(page.locator('dialog').get_by_role('alert')).to_contain_text('现场版本已经变化')
        assert len(fixture.writes) == 1
        total_writes += len(fixture.writes)
        cases.append('409 保留确认窗口并阻止旧现场自动重放')
        await context.close()

        fixture = UpdateFixture()
        fixture.state['installed'] = False
        fixture.state['message'] = '需要首次接入系统更新底座'
        context, page = await page_for(fixture)
        await expect(page.get_by_role('heading', name='首次接入系统更新')).to_be_visible()
        assert await page.get_by_role('button', name='安装更新', exact=True).count() == 0
        assert not fixture.writes
        cases.append('缺少底座时展示接入状态')
        await context.close()

        fixture = UpdateFixture()
        context, page = await page_for(fixture)
        await page.get_by_role('button', name='回退到此版本').click()
        await expect(page.get_by_role('heading', name='确认版本回退')).to_be_visible()
        await page.get_by_role('button', name='确认执行').click()
        await expect(page.get_by_role('heading', name='等待在途完成')).to_be_visible()
        assert fixture.writes[0]['path'].endswith('/rollback')
        assert fixture.writes[0]['body']['target_release'] == 'system-ci-99-1'
        await page.get_by_role('button', name='取消等待').click()
        assert fixture.writes[-1]['path'].endswith('/cancel')
        total_writes += len(fixture.writes)
        cases.append('回退冻结目标与取消等待使用原操作身份')
        await context.close()
        await browser.close()
    if errors:
        raise AssertionError('浏览器脚本异常：' + '; '.join(errors))
    result = {'status': 'passed', 'cases': cases, 'script_errors': errors, 'synthetic_writes': total_writes,
        'real_model_requests': 0, 'evidence': '真实 Vue 页面与完全合成 API 的交互验证'}
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
