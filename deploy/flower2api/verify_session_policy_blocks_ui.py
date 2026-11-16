"""使用真实前端产物与合成管理接口验证会话封禁页面及设置。"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from verify_environment_ui import BASE, ROOT, Fixture


class BlockFixture(Fixture):
    """沿用现有离线静态资源夹具，提供封禁记录及设置。"""

    def __init__(self, gateway: Path) -> None:
        """建立合成状态。@param gateway 前端产物。@return 无。"""
        super().__init__(gateway)
        now = int(time.time() * 1000)
        self.blocks = [dict(id=f'00000000-0000-4000-8000-{index:012d}', session_key=f'{index:064x}',
            api_token_id=21, token_name='演示令牌', account_id=7, account_name='演示账号',
            model='claude-opus-5-5', reason='reasoning_extraction', source_request_id=None,
            blocked_at_ms=now - 60000, expires_at_ms=now + 86400000, released_at_ms=None,
            blocked_request_count=3, last_blocked_at_ms=now - 1000, state='active') for index in range(1, 22)]
        self.blocks.append(dict(self.blocks[0], id='00000000-0000-4000-8000-000000000022', session_key='e'*64,
            state='expired', expires_at_ms=now - 1000))
        self.settings = {'session_policy_block_enabled':'true', 'session_policy_block_duration_minutes':'1440'}
        self.release_fail = False
        self.read_fail = False
        self.read_delay = 0
        self.reads = []
        self.releases = 0
        self.saves = []

    async def route(self, route) -> None:
        """拦截本轮接口，其余资源复用已有夹具。@param route 浏览器路由。@return 无。"""
        request = route.request
        parsed = urlsplit(request.url)
        path = parsed.path
        payload = None
        status = 200
        if path == '/admin/session-policy-blocks':
            self.reads.append(parse_qs(parsed.query, keep_blank_values=True))
            if self.read_delay:
                await asyncio.sleep(self.read_delay)
            if self.read_fail:
                status, payload = 503, {'error':'合成读取失败'}
            else:
                query = parse_qs(parsed.query)
                state = query.get('state', ['active'])[0]
                prefix = query.get('session_prefix', [''])[0]
                page = int(query.get('page', ['1'])[0])
                size = int(query.get('page_size', ['20'])[0])
                rows = [row for row in self.blocks if (state == 'all' or row['state'] == state) and row['session_key'].startswith(prefix)]
                payload = dict(items=rows[(page-1)*size:page*size], total=len(rows), page=page, page_size=size, observed_at_ms=int(time.time()*1000))
        elif path.startswith('/admin/session-policy-blocks/') and path.endswith('/release'):
            assert request.method == 'POST'
            if self.release_fail:
                status, payload = 503, {'error':'合成解除失败'}
            else:
                self.releases += 1
                row = next(row for row in self.blocks if row['id'] == path.split('/')[-2])
                row.update(state='released', released_at_ms=int(time.time()*1000))
                payload = row
        elif path == '/admin/settings':
            if request.method == 'PUT':
                self.saves.append(json.loads(request.post_data))
                self.settings.update(self.saves[-1])
                payload = {'ok':True}
            else:
                payload = self.settings
        elif path == '/admin/prime-logs':
            payload = []
        elif path in ('/session-blocks', '/settings'):
            await route.fulfill(path=str(self.gateway/'index.html'), content_type='text/html')
            return
        else:
            await super().route(route)
            return
        await route.fulfill(status=status, content_type='application/json', body=json.dumps(payload))


async def run(output: Path, gateway: Path) -> dict:
    """验证真实页面交互并输出截图。@param output 证据目录。@param gateway 前端产物。@return 验证摘要。"""
    from playwright.async_api import async_playwright, expect
    checks = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        for width in (1440, 1920, 2560, 390):
            fixture = BlockFixture(gateway)
            context = await browser.new_context(viewport={'width':width, 'height':1000}, timezone_id='Asia/Shanghai')
            await context.route('**/*', fixture.route)
            await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-admin')")
            await context.add_init_script("{const actual=Date.now;Date.now=()=>actual()+172800000;}")
            page = await context.new_page()
            await page.clock.install()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(BASE+'/session-blocks')
            await expect(page.get_by_role('heading', name='会话封禁', exact=True)).to_be_visible()
            await expect(page.locator('tr[data-block-id]')).to_have_count(20)
            await expect(page.locator('tr[data-block-id]').first.get_by_text('封禁中', exact=True)).to_be_visible()
            await page.get_by_role('button', name='下一页', exact=True).click()
            await expect(page.locator('tr[data-block-id]')).to_have_count(1)
            await page.get_by_role('button', name='上一页', exact=True).click()
            await expect(page.locator('tr[data-block-id]')).to_have_count(20)
            await page.get_by_role('button', name='解除封禁', exact=True).first.click()
            await page.get_by_role('dialog').get_by_role('button', name='取消', exact=True).click()
            await expect(page.get_by_role('dialog')).to_have_count(0)
            assert fixture.releases == 0
            await page.get_by_role('button', name='解除封禁', exact=True).first.click()
            fixture.release_fail = True
            await page.get_by_role('dialog').get_by_role('button', name='解除封禁', exact=True).click()
            await expect(page.get_by_role('dialog').get_by_role('alert')).to_contain_text('合成解除失败')
            fixture.release_fail = False
            await page.get_by_role('dialog').get_by_role('button', name='解除封禁', exact=True).click()
            await expect(page.get_by_role('dialog')).to_have_count(0)
            assert fixture.releases == 1
            search = page.get_by_role('searchbox', name='搜索会话')
            await search.fill('ffffffff')
            await search.press('Enter')
            empty = page.get_by_text('暂无匹配的封禁记录', exact=True)
            await expect(empty).to_be_visible()
            await page.screenshot(path=str(output/f'blocks-empty-{width}.png'), full_page=True)
            assert await page.locator('tbody > tr').count() == 1
            assert await page.locator('tr tr').count() == 0
            assert await page.locator('.session-block-empty').evaluate("el=>getComputedStyle(el).textAlign") == 'center'
            bounds = await page.locator('.session-block-panel').bounding_box()
            fixture.read_delay = 0.3
            await search.fill('a')
            async with page.expect_response('**/admin/session-policy-blocks?*'):
                async with page.expect_request('**/admin/session-policy-blocks?*'):
                    await page.clock.fast_forward(5000)
                await expect(page.get_by_role('button', name='刷新', exact=True)).to_be_enabled()
                await expect(page.locator('.session-block-records')).to_have_attribute('aria-busy', 'false')
                await expect(empty).to_be_visible()
                assert await page.locator('.session-block-panel').bounding_box() == bounds
                read_count = len(fixture.reads)
                await page.clock.fast_forward(5000)
                assert len(fixture.reads) == read_count
            assert fixture.reads[-1]['session_prefix'] == ['ffffffff']
            await expect(empty).to_be_visible()
            fixture.read_delay = 0
            await page.get_by_role('button', name='重置查询', exact=True).click()
            await expect(search).to_have_value('')
            await expect(page.locator('tr[data-block-id]')).to_have_count(20)
            picker = page.get_by_role('combobox', name='封禁状态', exact=True)
            await picker.click()
            await page.get_by_role('option', name='已到期', exact=True).click()
            await expect(page.locator('tr[data-block-id]')).to_have_count(1)
            await picker.click()
            await page.get_by_role('option', name='已解除', exact=True).click()
            await expect(page.locator('tr[data-block-id]')).to_have_count(1)
            await picker.click()
            await page.get_by_role('option', name='全部记录', exact=True).click()
            await expect(page.locator('tr[data-block-id]')).to_have_count(20)
            await picker.click()
            await page.get_by_role('option', name='封禁中', exact=True).click()
            await expect(page.locator('tr[data-block-id]')).to_have_count(20)
            fixture.read_fail = True
            await page.get_by_role('button', name='刷新', exact=True).click()
            await expect(page.get_by_role('alert')).to_contain_text('合成读取失败')
            assert await page.locator('tr[data-block-id]').count() == 20
            fixture.read_fail = False
            await page.get_by_role('button', name='重试', exact=True).click()
            await expect(page.get_by_role('alert')).to_have_count(0)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.screenshot(path=str(output/f'blocks-{width}.png'), full_page=True)
            await page.get_by_role('button', name='封禁设置', exact=True).click()
            await expect(page.locator('#session-policy-block')).to_be_visible()
            duration = page.get_by_role('spinbutton', name='封禁时长（分钟）', exact=True)
            await expect(duration).to_have_value('1440')
            help_text = page.locator('[data-settings-field="session_policy_block_duration_minutes"] .setting-help')
            await expect(help_text).to_contain_text('默认 24 小时（1440 分钟）。')
            assert await help_text.evaluate("el=>getComputedStyle(el).textDecorationLine") == 'none'
            assert await help_text.evaluate("el=>getComputedStyle(el).whiteSpace") == 'pre-line'
            await duration.fill('60')
            await page.get_by_role('button', name='保存配置', exact=True).click()
            await expect(duration).to_have_value('60')
            await page.wait_for_function("document.querySelector('[data-settings-field=\"session_policy_block_duration_minutes\"] input').value==='60'")
            assert fixture.saves and fixture.saves[-1]['session_policy_block_duration_minutes'] == '60'
            assert all(isinstance(value,str) for value in fixture.saves[-1].values())
            await page.screenshot(path=str(output/f'settings-{width}.png'), full_page=True)
            assert not errors, errors
            assert not fixture.external, fixture.external
            assert not fixture.unexpected, fixture.unexpected
            checks.append({'width':width, 'checks':['服务器时间基准','分页','状态筛选','取消解除','解除失败重试','居中空态与重置','静默刷新布局稳定','未提交搜索保持','读取失败保留','设置直达','默认时长分行说明','字符串设置保存','窄屏无溢出'], 'passed':True})
            await context.close()
        await browser.close()
    return {'passed':True, 'scenes':checks, 'real_model_requests':0}


def main() -> None:
    """读取产物路径并执行离线验证。@return 无。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'.deploy/session-policy-block-ui')
    parser.add_argument('--gateway-dist', type=Path, default=ROOT/'apps/web/dist')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run(args.output.resolve(), args.gateway_dist.resolve()))
    (args.output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
