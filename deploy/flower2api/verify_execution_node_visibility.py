"""用真实构建核对节点归属、历史执行位置及桌面和手机布局。"""
import asyncio
import json
import re
import time
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_accounts_design import AccountDesignFixture
from verify_environment_ui import BASE, ROOT


class ExecutionNodeFixture(AccountDesignFixture):
    """隔离节点、环境和请求记录，所有观察均为合成数据。"""

    def __init__(self):
        """准备当前归属和迁移前的历史节点。:return: None。"""
        super().__init__()
        self.accounts[2]['platform'] = 'antigravity'
        self.rows[1]['platform'] = 'antigravity'
        self.node_failed = False
        self.local_node_failed = False
        self.node_reads = 0
        self.task_accounts = []
        for index, name in enumerate(('默认本机', '上海 · 工程执行节点', '历史账号'), 1):
            node = None if index == 3 else dict(account_id=index, node_id=index, node_key='local' if index == 1 else 'b' * 32,
                node_name=name, kind='local' if index == 1 else 'ssh', enabled=True, revision=3, phase='ready')
            self.task_accounts.append(dict(id=index, name=f'任务账号 {index}', enabled=1, cc2api_account_id=index,
                node=node, node_observation=dict(state='reachable' if index == 1 else 'unreachable', stale=False,
                    observed_at=time.time()) if node else None, warmup_engine='projects'))
        for index, row in enumerate(self.rows):
            account = self.task_accounts[min(index, 2)]
            row.update(gateway_account_id=index + 1, node=account['node'], node_observed=index == 0)
            if index == 1:
                row.update(state='node_unreachable', node_message='所属节点暂不可达，保留已保存归属')
        self.attempts = [dict(attempt_id=f'{index}' * 8 + '-1111-4111-8111-' + f'{index}' * 12,
            ordinal=index, account_id=1, account_name='迁移前请求', account_email='history@example.test',
            profile_selection='native293_cc_prepared', status_code=200, outcome='success', capture_status='disabled',
            execution_location=dict(node_key='local' if index == 1 else 'a' * 32, environment_id=str(index) * 32,
                generation=index + 4, assignment_revision=index)) for index in (1, 2)]
        self.requests = [dict(request_id=str(index) * 8 + '-2222-4222-8222-' + str(index) * 12,
            started_at='2026-11-18T00:00:00Z', finished_at='2026-11-18T00:00:01Z', account_id=1,
            account_name='历史执行请求' if index == 1 else '旧日志' if index == 2 else '本地拒绝',
            context=dict(platform='claude_code' if index == 1 else 'antigravity') if index != 3 else None,
            account_email='history@example.test', status_code=400 if index == 3 else 200,
            outcome='local_rejected' if index == 3 else 'success', log_mode='info',
            attempt_count=2 if index == 1 else 1 if index == 2 else 0,
            last_attempt=self.attempts[-1] if index == 1 else None) for index in (1, 2, 3)]

    async def route(self, route):
        """截获只读节点和历史请求接口。:param route: 浏览器请求。:return: None。"""
        path = urlsplit(route.request.url).path
        if path == '/runtime/api/nodes':
            return await self.respond(route, {'detail': '本机节点读取故障'} if self.local_node_failed else {
                'items': [dict(id=1, name='本机执行节点', kind='local', node_key='local', enabled=True)]},
                503 if self.local_node_failed else 200)
        if path == '/runtime/api/accounts':
            self.node_reads += 1
            return await self.respond(route, {'detail': '合成节点读取故障'} if self.node_failed else self.task_accounts,
                503 if self.node_failed else 200)
        if path == '/runtime/api/environments':
            self.reads += 1
            return await self.respond(route, self.rows)
        if re.fullmatch(r'/runtime/api/accounts/\d+/cli-settings', path):
            return await self.respond(route, dict(display_name='任务账号', claude_code_version='',
                effective_claude_code_version='2.1.293', claude_code_version_source='global'))
        if path == '/admin/request-diagnostics':
            return await self.respond(route, dict(items=self.requests, total=3, health={}))
        if path.startswith('/admin/request-diagnostics/'):
            record = next(item for item in self.requests if path.endswith(item['request_id']))
            return await self.respond(route, dict(request={key: value for key, value in record.items() if key != 'last_attempt'},
                attempts=self.attempts if record is self.requests[0] else []))
        return await super().route(route)


async def node_details(page, badge, expected):
    """悬停显示节点完整信息，Escape 关闭说明。:param page: 页面。:param badge: 节点链接。:param expected: 原始身份或状态。:return: None。"""
    await badge.scroll_into_view_if_needed()
    await badge.hover()
    tooltip = page.locator('[data-reka-popper-content-wrapper] .fui-info-content')
    await expect(tooltip).to_contain_text(expected)
    await page.keyboard.press('Escape')
    await expect(tooltip).not_to_be_visible()
    await page.mouse.move(0, 0)


async def snapshot(page, output, name):
    """核对三档宽度与节点文本边界并保存实际截图。:param page: 页面。:param output: 目录。:param name: 场景。:return: None。"""
    for width in (1440, 720, 390):
        await page.set_viewport_size({'width': width, 'height': 1000})
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (name, width)
        for badge in await page.locator('[data-execution-node]:visible').all():
            assert await badge.evaluate('e=>e.scrollWidth<=e.clientWidth+1'), (name, width)
        for identity in await page.locator('.request-account-name').all():
            assert await identity.evaluate('e=>{const r=document.createRange();r.selectNodeContents(e);return new Set(Array.from(r.getClientRects(),v=>Math.round(v.top))).size===1}'), (name, width, '账号名称应单行')
        dialogs = page.locator('[role=dialog]:visible')
        for dialog in await dialogs.all():
            assert await dialog.evaluate('e=>e.scrollWidth<=e.clientWidth+1'), (name, width)
        await page.screenshot(path=str(output / f'{name}-{width}.png'), full_page=not await dialogs.count(), animations='disabled')


async def main():
    """验证三个入口及历史、多次尝试、失败刷新和独立工作区。:return: None。"""
    output = ROOT / '.trellis/.runtime/execution-node-ui'
    output.mkdir(parents=True, exist_ok=True)
    fixture, errors = ExecutionNodeFixture(), []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(BASE + '/')
        cards = page.locator('.account-card')
        await expect(cards).to_have_count(12)
        await expect(cards.first.locator('[data-execution-node]')).to_contain_text('默认本机')
        await expect(cards.first.locator('[data-platform-badge]')).to_have_text('Claude Code')
        agy = cards.nth(2)
        await expect(agy.locator('[data-platform-badge]')).to_have_text('反重力')
        await expect(agy.locator('[data-execution-node]')).to_have_text('本机执行节点')
        await node_details(page, agy.locator('[data-execution-node]'), '反重力 API 在本机执行')
        await node_details(page, cards.nth(1).locator('[data-execution-node]'), '最近观测不可达')
        await node_details(page, cards.nth(1).locator('[data-execution-node]'), 'b' * 32)
        for card in await cards.all():
            await expect(card.locator('.account-network [data-execution-node]')).to_have_count(1)
            await expect(card.locator('.account-card-topline').get_by_role('switch')).to_have_count(1)
            await expect(card.locator('.account-card-topline').get_by_role('button', name='停用账号', exact=True)).to_have_count(1)
        await cards.first.get_by_role('switch').click()
        await expect(cards.first.get_by_role('switch')).to_have_attribute('aria-checked', 'false')
        assert fixture.accounts[0]['work_control']['work_enabled']
        await cards.first.get_by_role('button', name='停用账号', exact=True).click()
        await expect(cards.first.get_by_role('button', name='启用账号', exact=True)).to_be_visible()
        assert not fixture.accounts[0]['work_control']['work_enabled']
        await cards.first.get_by_role('button', name='启用账号', exact=True).click()
        assert fixture.accounts[0]['work_control']['work_enabled']
        assert not fixture.accounts[0]['work_control']['api_accepting']
        assert fixture.reads == 0, '账号节点展示应复用只读归属'
        await snapshot(page, output, 'accounts')
        await cards.nth(1).get_by_role('button', name='详情', exact=True).click()
        await expect(page.locator('.account-workspace [data-execution-node]').first).to_contain_text('上海 · 工程执行节点')
        await snapshot(page, output, 'account-detail')
        await page.keyboard.press('Escape')
        await agy.get_by_role('button', name='详情', exact=True).click()
        await expect(page.locator('.account-workspace [data-execution-node]').first).to_have_text('本机执行节点')
        await page.keyboard.press('Escape')
        fixture.node_failed = True
        await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        await node_details(page, cards.nth(1).locator('[data-execution-node]'), '归属待刷新')
        await node_details(page, cards.nth(1).locator('[data-execution-node]'), 'b' * 32)
        await expect(agy.locator('[data-execution-node]')).to_have_text('本机执行节点')
        fixture.node_failed = False
        fixture.local_node_failed = True
        await page.reload()
        await expect(agy.locator('[data-execution-node]')).to_have_text('默认本机')
        await expect(cards.nth(1).locator('[data-execution-node]')).to_have_text('上海 · 工程执行节点')
        fixture.local_node_failed = False
        await agy.locator('[data-execution-node]').click()
        await expect(page).to_have_url(BASE + '/nodes')
        await page.goto(BASE + '/environments')
        environments = page.locator('.environment-rich')
        await expect(environments).to_have_count(4)
        await node_details(page, environments.nth(1).locator('[data-execution-node]'), '所属节点暂不可达')
        await expect(environments.nth(1).locator('.fui-entity-card-head [data-platform-badge]')).to_have_text('反重力')
        await expect(environments.nth(1).locator('.fui-entity-card-head [data-execution-node]')).to_have_count(1)
        await snapshot(page, output, 'environments')
        await environments.nth(1).get_by_role('button', name='环境详情', exact=True).click()
        await node_details(page, page.locator('.runtime-environment-dialog [data-execution-node]'), 'b' * 32)
        await expect(page.locator('.runtime-environment-dialog')).to_be_visible()
        await snapshot(page, output, 'environment-detail')
        await page.get_by_role('button', name='关闭环境详情', exact=True).click()
        await environments.first.locator('[data-execution-node]').click()
        await expect(page).to_have_url(BASE + '/nodes')
        await page.goto(BASE + '/requests')
        records = page.locator('.request-records tbody tr')
        await expect(records).to_have_count(3)
        await node_details(page, records.first.locator('[data-execution-node]'), 'a' * 32)
        await expect(records.first.locator('.request-account-identity')).to_have_text('历史执行请求')
        await records.first.locator('.request-account-identity button').hover()
        await expect(page.locator('.fui-info-content')).to_contain_text('history@example.test')
        await page.keyboard.press('Escape')
        await page.mouse.move(0, 0)
        await expect(records.nth(1).locator('[data-platform-badge]')).to_have_text('反重力')
        await expect(records.nth(2).locator('[data-platform-badge]')).to_have_text('平台未记录')
        await expect(records.first).not_to_contain_text('b' * 32)
        await expect(records.nth(1)).to_contain_text('节点未观测')
        await expect(records.nth(2)).to_contain_text('无执行尝试')
        await snapshot(page, output, 'requests')
        await records.first.get_by_role('button', name='详情', exact=True).click()
        await node_details(page, page.locator('.request-definitions').first.locator('[data-execution-node]'), 'a' * 32)
        await page.get_by_role('tab', name='请求链路', exact=True).click()
        chain = page.locator('.request-chain-card')
        await expect(chain.first).to_contain_text('默认本机')
        await node_details(page, chain.nth(1).locator('[data-execution-node]'), 'a' * 32)
        await expect(chain.nth(1)).to_contain_text('2' * 32 + ' · 6')
        await snapshot(page, output, 'request-chain')
        await page.keyboard.press('Escape')
        await records.first.locator('[data-execution-node]').click()
        await expect(page).to_have_url(BASE + '/nodes')
        await page.goto(BASE + '/tasks')
        task_cards = page.locator('.work-account')
        await expect(task_cards).to_have_count(3)
        await expect(task_cards.nth(1)).to_contain_text('b' * 32)
        await snapshot(page, output, 'task-accounts')
        await task_cards.nth(1).locator('[data-cli-settings]').click()
        await expect(page.locator('#cli-settings-node')).to_contain_text('上海 · 工程执行节点')
        await snapshot(page, output, 'task-detail')
        assert not errors and not fixture.unexpected and not fixture.external, (errors, fixture.unexpected, fixture.external)
        await browser.close()
    print(json.dumps({'passed': True, 'scenes': 8, 'widths': [1440, 720, 390], 'errors': errors,
        'real_model_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
