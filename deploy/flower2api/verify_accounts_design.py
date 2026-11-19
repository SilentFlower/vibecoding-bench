"""验证正式账号设计的真实组件、请求合同及响应式布局，全部使用合成API。"""
import asyncio
import copy
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from playwright.async_api import async_playwright, expect
from export_frontend_preview import PreviewFixture
from verify_environment_ui import BASE, ROOT


class AccountDesignFixture(PreviewFixture):
    """为编辑、分页和OAuth提供独立可回读的合成状态。"""

    def __init__(self):
        """初始化13个账号及费用样例。@return 无。"""
        super().__init__()
        source = self.accounts[0]
        self.account_template = copy.deepcopy(source)
        self.accounts = [dict(copy.deepcopy(source), id=i, name=f'正式账号 {i}', email=f'design{i}@example.test', queued_requests=4 if i == 1 else 0) for i in range(1, 14)]
        for account in [self.account_template, *self.accounts]:
            account['work_control'] = dict(api_accepting=True, work_enabled=True, revision=0,
                admitted_requests=2 if account.get('id') == 1 else 0, phase='enabled', coordinated=False)
        stats = dict(requests=128, tokens=845000, cost_usd=4.85, unpriced_requests=0, partial_requests=0, starts_at='2026-11-15T00:00:00Z', ends_at='2099-11-15T05:00:00Z', basis='quota', coverage_complete=True, estimated_total_cost_usd=15.16)
        self.accounts[0].update(proxy_url='socks5://demo-user:demo-secret@proxy.example.test:1080', request_backend='native293', request_usage=dict(recorded_since='2026-11-01T00:00:00Z', five_hour=stats, seven_day=copy.deepcopy(stats)))
        now = int(time.time()*1000)
        self.summary = dict(config=dict(mode='smart',wait_seconds=30,weights=[0.25]*4), factors=dict(load=0.5,quota=0.7,health=0.9,latency=0.6,score=0.675), capacity=dict(immediate=True,can_queue=True,reason='ready',earliest_submit_at_ms=now), observed_at_ms=now, bound_sessions=3,active_sessions=2,unbound_requests=0,phases=dict(waiting_concurrency=4,preparing=0,waiting_send=0,running=1,backoff=0),next_send_at_ms=None,submissions_last_60s=8,history_available_from_ms=now-300000,history_truncated=False)
        self.accounts[0]['v3_scheduling'] = self.summary
        self.accounts[0]['usage_data'] = dict(five_hour=dict(utilization=32,resets_at='2099-11-15T05:00:00Z'),seven_day=dict(utilization=18,resets_at='2099-11-17T05:00:00Z'),seven_day_fable=dict(utilization=9,resets_at='2099-11-17T05:00:00Z'))
        # 用户预览使用当前周期，避免长期固定日期显示成数万天倒计时。
        current = datetime.now(timezone.utc)
        for key, duration in [('five_hour',timedelta(hours=3,minutes=6)),('seven_day',timedelta(days=2,hours=8)),('seven_day_fable',timedelta(days=2,hours=8))]:
            self.accounts[0]['usage_data'][key]['resets_at'] = (current + duration).isoformat()
            if key in self.accounts[0]['request_usage']:
                self.accounts[0]['request_usage'][key]['ends_at'] = (current + duration).isoformat()
        self.scheduling_reads = []
        self.account_reads = []
        self.background_checks = 0

    async def route(self, route):
        """仅截获账号新增调用，其余沿用已有合成页面。@param route 浏览器请求。@return 无。"""
        request = route.request
        url = urlsplit(request.url)
        path = url.path
        work = re.fullmatch(r'/admin/accounts/(\d+)/work-control', path)
        if work:
            account = next(account for account in self.accounts if account['id'] == int(work[1]))
            state = account['work_control']
            if request.method == 'PUT':
                body = request.post_data_json
                assert body['expected_revision'] == state['revision']
                self.writes.append(dict(path=path, method=request.method, body=body))
                state.update({key: body[key] for key in ('api_accepting', 'work_enabled') if key in body})
                state['revision'] += 1
                state['phase'] = 'enabled' if state['work_enabled'] else 'draining' if state['admitted_requests'] else 'disabled'
            return await self.respond(route, state)
        if path == '/runtime/api/system-updates/check':
            self.background_checks += 1
            return await self.respond(route, {'checking': False})
        if path == '/admin/dashboard':
            return await self.respond(route, {'accounts': {'total':len(self.accounts),**{key:sum(a['status']==key for a in self.accounts) for key in ['active','error','disabled']}}, 'tokens':1})
        if path == '/admin/accounts':
            if request.method == 'GET':
                page = int(parse_qs(url.query).get('page', ['1'])[0])
                self.account_reads.append(page)
                query=parse_qs(url.query); size=int(query.get('page_size',['12'])[0]); search=query.get('q',[''])[0].lower(); status=query.get('status',[''])[0]
                platform=query.get('platform',['claude_code'])[0]
                rows=[a for a in self.accounts if (platform=='all' or a.get('platform','claude_code')==platform) and (not status or a['status']==status) and search in (a['name']+' '+a['email']).lower()]
                return await self.respond(route, dict(data=rows[(page-1)*size:page*size], total=len(rows), page=page, page_size=size, total_pages=(len(rows)+size-1)//size))
            body = request.post_data_json
            self.writes.append(dict(path=path, method=request.method, body=body))
            value = dict(copy.deepcopy(self.account_template), **body, id=max((a['id'] for a in self.accounts),default=0)+1)
            self.accounts.append(value)
            return await self.respond(route, value)
        if '/scheduling' in path:
            self.scheduling_reads.append(request.url)
            if path.endswith('/sessions'):
                return await self.respond(route, dict(items=[],total=0,page=1,page_size=20,observed_at_ms=self.summary['observed_at_ms']))
            snapshot = dict(observed_at_ms=self.summary['observed_at_ms'],history_available_from_ms=self.summary['history_available_from_ms'],history_truncated=False,dropped_events=0,submissions_last_60s=8,requests=[],events=[])
            return await self.respond(route, dict(summary=self.summary,snapshot=snapshot))
        match = re.fullmatch(r'/admin/accounts/(\d+)(/(test|usage))?', path)
        if match:
            account_id = int(match[1]); account = next(a for a in self.accounts if a['id'] == account_id)
            if request.method == 'GET' and not match[3]:
                return await self.respond(route, account)
            self.writes.append(dict(path=path, method=request.method, body=request.post_data_json if request.post_data else None))
            if request.method == 'PUT':
                account.update(request.post_data_json)
                return await self.respond(route, account)
            if request.method == 'DELETE':
                self.accounts.remove(account)
                return await self.respond(route, {})
            return await self.respond(route, dict(status='ok', usage=account['usage_data']) if match[3] == 'usage' else dict(status='ok'))
        if path in ('/admin/oauth/generate-auth-url', '/admin/oauth/generate-setup-token-url'):
            self.writes.append(dict(path=path, method=request.method, body=request.post_data_json))
            return await self.respond(route, dict(auth_url='https://auth.example.test/local-only', session_id='synthetic-session'))
        return await super().route(route)


async def main():
    """运行正式构建的保存/取消/导航/布局回归。@return 无。"""
    out = ROOT / '.deploy/frontend-sidebar-refresh/production'
    out.mkdir(parents=True, exist_ok=True)
    fixture = AccountDesignFixture(); errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(BASE + '/')
        card = page.locator('.account-card').first
        await expect(page.locator('.account-card')).to_have_count(12)
        await page.evaluate('document.fonts.ready')
        assert await page.evaluate('document.fonts.check(\'14px "Inter Variable"\')')
        await expect(card).to_contain_text('排队')
        await expect(card.locator('.account-work-status')).to_have_count(0)
        await expect(card).not_to_contain_text('demo-secret')
        await expect(card).not_to_contain_text('7 天 Sonnet')
        await card.get_by_role('button', name='查看5h完整费用统计').click()
        await expect(page.locator('.fui-info-content')).to_contain_text('15.16')
        await page.keyboard.press('Escape')
        assert await card.locator('.usage-stats-line').first.evaluate('e=>getComputedStyle(e).whiteSpace===\'nowrap\'')
        await card.locator('.account-live-metrics button').nth(2).click()
        scheduling = page.get_by_role('dialog')
        await expect(scheduling).to_contain_text('已绑定／活跃会话')
        await scheduling.get_by_role('combobox', name='会话活跃状态').click()
        await page.get_by_role('option', name='活跃', exact=True).click()
        await scheduling.get_by_role('searchbox', name='会话摘要前缀').fill('abc123')
        await scheduling.get_by_role('searchbox', name='会话摘要前缀').press('Enter')
        await expect(scheduling).to_contain_text('当前筛选没有有效绑定')
        assert any('state=active' in url and 'prefix=abc123' in url for url in fixture.scheduling_reads)
        await page.screenshot(path=str(out/'scheduling-1440.png'))
        await page.keyboard.press('Escape')
        await card.get_by_role('button', name='编辑', exact=True).click()
        dialog = page.get_by_role('dialog')
        await expect(dialog.locator('input[type=radio][value=native293]')).to_be_checked()
        await expect(dialog.locator('.account-auth-fields')).not_to_have_attribute('open', '')
        before_edit = len(fixture.writes)
        await dialog.get_by_role('spinbutton', name='并发上限', exact=True).fill('')
        await dialog.get_by_role('button', name='保存修改', exact=True).click()
        assert len(fixture.writes) == before_edit, fixture.writes[before_edit:]
        await dialog.get_by_role('spinbutton', name='并发上限', exact=True).fill('4')
        await dialog.locator('input[type=radio][value=legacy]').check()
        await dialog.get_by_role('button', name='保存修改', exact=True).click()
        await expect(dialog).to_have_count(0)
        assert fixture.writes[-1]['body'] == {'concurrency': 4, 'request_backend': 'legacy'}, fixture.writes[-1]
        await card.get_by_role('button', name='编辑', exact=True).click()
        await dialog.get_by_role('spinbutton', name='并发上限', exact=True).fill('6')
        await dialog.get_by_role('button', name='取消', exact=True).click()
        assert len(fixture.writes) == before_edit + 1
        await card.get_by_role('button', name='详情', exact=True).click()
        await dialog.get_by_role('button',name='环境与诊断',exact=True).click()
        await expect(dialog).to_contain_text('画像选择方式')
        await expect(dialog).to_contain_text('上游池槽位')
        await expect(dialog).not_to_contain_text('demo-secret')
        await page.keyboard.press('Escape')
        await card.get_by_role('switch').click()
        await expect(card.get_by_role('switch')).to_have_attribute('aria-checked', 'false')
        assert fixture.writes[-1]['body'] == {'api_accepting': False, 'expected_revision': 0}
        assert fixture.accounts[0]['status'] == 'active' and fixture.accounts[0]['work_control']['work_enabled']
        await card.get_by_role('button', name='停用账号', exact=True).click()
        await expect(card.locator('.account-work-status')).to_have_text('正在收尾 · 剩余 2 个请求')
        await expect(card.get_by_role('switch')).to_have_attribute('aria-checked', 'false')
        assert fixture.accounts[0]['status'] == 'active'
        await card.get_by_role('button', name='启用账号', exact=True).click()
        await expect(card.locator('.account-work-status')).to_have_count(0)
        await expect(card.get_by_role('switch')).to_have_attribute('aria-checked', 'false')
        await card.get_by_role('button', name='用量', exact=True).click()
        assert fixture.writes[-1]['path'].endswith('/usage')
        await card.get_by_role('button', name='测试', exact=True).click()
        await expect(card.get_by_role('button', name='测试结果：连接正常', exact=True)).to_be_visible()
        await card.get_by_role('button', name='删除', exact=True).click()
        await dialog.get_by_role('button', name='取消', exact=True).click()
        assert all(write['method'] != 'DELETE' for write in fixture.writes if write['path'].startswith('/admin/accounts'))
        await page.get_by_role('button', name='下一页', exact=True).click()
        await expect(page.locator('.account-card')).to_have_count(1)
        await expect(page.locator('.account-card')).to_contain_text('正式账号 13')
        assert fixture.account_reads[-1] == 2
        await page.get_by_role('button', name='上一页', exact=True).click()
        await expect(page.locator('.account-card')).to_have_count(12)
        await page.get_by_role('button', name='添加账号', exact=True).click()
        await expect(dialog.locator('.account-auth-fields')).to_have_attribute('open', '')
        await dialog.get_by_label('备注名（选填）',exact=True).fill('新增真实组件样例')
        await dialog.get_by_label('邮箱',exact=True).fill('created@example.test')
        await dialog.get_by_label('Setup Token',exact=True).fill('sk-ant-oat01-synthetic-only')
        await dialog.get_by_role('button', name='保存修改', exact=True).click()
        await expect(dialog).to_have_count(0)
        created = next(write['body'] for write in fixture.writes if write['path']=='/admin/accounts' and write['method']=='POST')
        assert created['email']=='created@example.test' and isinstance(created['concurrency'], int) and created['setup_token']=='sk-ant-oat01-synthetic-only'
        await page.get_by_role('button', name='授权登录', exact=True).click()
        await dialog.get_by_role('combobox', name='授权方式', exact=True).click()
        await page.get_by_role('option', name='Setup Token', exact=True).click()
        await dialog.get_by_role('button', name='生成授权链接', exact=True).click()
        await expect(dialog.get_by_role('link', name='点击打开授权页面 ↗')).to_have_attribute('href', 'https://auth.example.test/local-only')
        assert fixture.writes[-1]['path'] == '/admin/oauth/generate-setup-token-url'
        await page.keyboard.press('Escape')
        await page.get_by_role('button', name='收起侧边栏').click()
        await page.reload()
        await expect(page.locator('.console-shell')).to_have_class(re.compile('sidebar-collapsed'))
        await page.get_by_role('link', name='系统更新', exact=True).click()
        await expect(page.locator('.system-update-dialog')).to_be_visible()
        await expect(page).to_have_url(BASE + '/')
        await page.locator('.system-update-dialog').get_by_role('button', name='关闭', exact=True).click()
        await page.get_by_role('button', name='展开侧边栏').click()
        for width in [1440, 720, 390]:
            await page.set_viewport_size({'width': width, 'height': 1000})
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
            await page.screenshot(path=str(out / f'accounts-{width}.png'), full_page=True)
            await card.get_by_role('button', name='编辑', exact=True).click()
            assert await dialog.evaluate('e=>e.scrollWidth<=e.clientWidth+1'), width
            await expect(dialog).to_have_css('opacity', '1')
            await page.screenshot(path=str(out / f'account-editor-{width}.png'))
            scroll = dialog.locator('.account-editor-scroll')
            await scroll.evaluate('e=>e.scrollTop=500')
            await expect(scroll).to_have_attribute('data-active-scroll', '')
            await expect(scroll).not_to_have_attribute('data-active-scroll', '', timeout=2000)
            await page.keyboard.press('Escape')
            if width < 768:
                await page.get_by_role('button', name='打开主导航').click()
                await page.get_by_role('link', name='任务与工程', exact=True).click()
                await expect(page).to_have_url(BASE + '/tasks')
                await page.get_by_role('button', name='打开主导航').click()
                await page.get_by_role('link', name='账号', exact=True).click()
        assert not errors, errors
        assert set(fixture.external) <= {'fonts.googleapis.com', 'cdn.jsdelivr.net'}, fixture.external
        result = dict(passed=True, checks=['全部字段与增量保存', '数字空值校验', '取消零写入', '代理脱敏', '完整费用气泡', '三个额度窗口', '启停用量测试删除', '分页', 'OAuth类型', '品牌更新与折叠持久化', '1440/720/390px', '活动滚动条与移动导航'], errors=errors, blocked_static_hosts=sorted(set(fixture.external)), real_model_requests=0)
        (out/'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
