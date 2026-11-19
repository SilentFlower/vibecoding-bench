"""使用正式前端构建验证平台、两账号策略及原生授权交互，API均为合成。"""
import asyncio
import copy
import json
import time
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect
from verify_accounts_design import AccountDesignFixture
from verify_environment_ui import BASE, ROOT


class PlatformFixture(AccountDesignFixture):
    """保留原CC夹具，增加独立AGY账号与授权会话。"""

    def __init__(self):
        """创建两AGY及一CC账号。@return 无。"""
        super().__init__()
        self.accounts = [dict(copy.deepcopy(self.account_template), id=i, platform='antigravity',
            name=f'AGY账号{i}', email=f'agy{i}@example.test', agy_system_prompt_homoglyph_enabled=False,
            credential_state={'phase':'ready','generation':1}, usage_data={'platform':'antigravity',
                'capabilities':{'source':'agy:1.5.9:native','observed_at_ms':int(time.time()*1000),
                    'models':['gemini-synthetic'], 'provider':{'userTier':{'name':'合成分级'}}}}) for i in [1,2]]
        self.accounts.append(dict(copy.deepcopy(self.account_template), id=3, name='CC兼容账号', platform='claude_code'))
        now = int(time.time() * 1000)
        self.accounts[0]['usage_data']['platform_quota'] = {
            'status': 'ok', 'plan': '演示 Pro', 'checked_at_ms': now,
            'groups': {'observed_at_ms': now, 'items': [{'name': 'Gemini Pro', 'windows': [
                {'id': 'pro-5h', 'period': '5h', 'remaining_fraction': 0, 'reset_at': '2099-01-01T05:00:00Z'},
                {'id': 'pro-week', 'period': 'weekly', 'remaining_fraction': None, 'reset_at': None},
            ]}]},
            'models': {'observed_at_ms': now, 'items': [
                {'model': 'gemini-synthetic', 'remaining_fraction': 0.4, 'reset_at': None},
            ]},
        }
        self.accounts[0]['agy_request_usage'] = {
            'five_hour': {'requests': 1, 'tokens': 0, 'partial_requests': 0},
            'seven_day': {'requests': 2, 'tokens': 1200, 'partial_requests': 1},
        }
        self.accounts[0].update(current_concurrency=1, active_requests=1, rpm_current=5, queued_requests=2)
        self.oauth_sessions = {}
        self.held_generate = None

    async def route(self, route):
        """模拟平台授权和取消，记录准确请求。@param route 请求。@return 无。"""
        path = urlsplit(route.request.url).path
        if path == '/admin/oauth/generate-auth-url':
            body = route.request.post_data_json
            self.writes.append(dict(path=path, method='POST', body=body))
            identity = ('a' if body.get('account_id') else 'b')*32
            self.oauth_sessions[identity] = body
            if self.held_generate:
                await self.held_generate.wait()
            return await self.respond(route, {'session_id':identity,'auth_url':'https://accounts.google.com/synthetic-only'})
        if path.endswith('/cancel') and '/admin/oauth/' in path:
            self.writes.append(dict(path=path,method='POST',body={}))
            return await self.respond(route, {'phase':'cancelled'})
        if path == '/admin/oauth/exchange-code':
            body = route.request.post_data_json
            self.writes.append(dict(path=path,method='POST',body=body))
            target = self.oauth_sessions[body['session_id']].get('account_id')
            email = f'agy{target}@example.test' if target else 'new-agy@example.test'
            return await self.respond(route, dict(access_token='synthetic-at',refresh_token='synthetic-rt',
                expires_at=4070908800,expires_in=3600,email_address=email))
        return await super().route(route)


async def main():
    """验证实际DOM、差异载荷及授权目标。@return 无。"""
    fixture = PlatformFixture()
    errors = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width':1440,'height':1000})
        await context.route('**/*',fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror',lambda error: errors.append(str(error)))
        await page.goto(BASE+'/')
        await expect(page.locator('.account-card')).to_have_count(3)
        first = page.locator('.account-card').filter(has_text='AGY账号1')
        second = page.locator('.account-card').filter(has_text='AGY账号2')
        await expect(first.locator('.account-usage-windows')).to_have_count(0)
        windows = first.locator('.agy-quota-window')
        await expect(windows.first).to_contain_text('5 小时')
        await expect(windows.first.locator('.agy-quota-value')).to_have_text('已用 100% · 剩余 0%')
        assert await windows.first.locator('.usage-window-bar i').evaluate('e=>e.style.width') == '100%'
        await expect(windows.first.locator('.usage-window-bar i')).to_have_css('background-color', 'rgb(207, 89, 100)')
        await expect(windows.nth(1)).to_contain_text('额度未知')
        await expect(windows.nth(1).locator('.usage-window-bar')).to_have_count(0)
        await expect(first.locator('.agy-gateway-windows')).to_have_count(0)
        await expect(first.locator('.account-work-status')).to_have_count(0)
        await expect(second.locator('.agy-account-usage')).to_contain_text('未刷新')
        await expect(first.locator('.account-routing')).to_contain_text('低负载优先')
        await expect(first.locator('.account-live-metrics button')).to_have_count(4)
        await expect(first.locator('.account-live-metrics button').nth(1)).to_contain_text('5')
        await expect(first.locator('.account-live-metrics button').nth(3)).to_contain_text('在途请求')
        await first.get_by_role('button',name='编辑',exact=True).click()
        dialog = page.get_by_role('dialog')
        switch = dialog.get_by_role('checkbox',name='系统提示词同形体转换')
        await expect(switch).not_to_be_checked()
        await expect(dialog.get_by_role('combobox',name='账号平台')).to_be_disabled()
        await switch.check()
        await asyncio.sleep(5.2)
        await expect(switch).to_be_checked()
        await dialog.get_by_role('button',name='保存修改',exact=True).click()
        await expect(dialog).to_have_count(0)
        assert fixture.writes[-1]['body']=={'agy_system_prompt_homoglyph_enabled':True},fixture.writes[-1]
        await second.get_by_role('button',name='编辑',exact=True).click()
        await expect(switch).not_to_be_checked()
        await dialog.get_by_role('button',name='取消',exact=True).click()
        await first.get_by_role('button',name='详情',exact=True).click()
        await expect(dialog.locator('.account-model-list')).to_be_hidden()
        await dialog.locator('.account-capabilities summary').filter(has_text='可用模型').click()
        await expect(dialog.locator('.account-model-list')).to_contain_text('gemini-synthetic')
        await expect(dialog).to_contain_text('平台额度')
        await expect(dialog.locator('.agy-gateway-windows')).to_contain_text('0 Token')
        await expect(dialog.locator('.agy-gateway-windows')).to_contain_text('部分记录')
        await expect(dialog.locator('.account-overview-control .account-overview-note')).to_have_count(0)
        await dialog.locator('summary').filter(has_text='按模型查看').click()
        await expect(dialog.locator('.agy-model-quotas')).to_contain_text('已用 60% · 剩余 40%')
        await expect(dialog.locator('.agy-model-quotas .usage-window-bar i')).to_have_css('background-color', 'rgb(212, 166, 89)')
        await dialog.locator('summary').filter(has_text='套餐与来源').click()
        await expect(dialog.locator('.account-provider-details')).to_contain_text('演示 Pro')
        await expect(dialog.locator('.account-provider-details')).to_contain_text('合成分级')
        await expect(dialog.locator('.account-provider-details pre')).to_have_count(0)
        await expect(dialog.get_by_role('button',name='环境与诊断',exact=True)).to_have_count(1)
        await page.keyboard.press('Escape')
        await first.get_by_role('button',name='编辑',exact=True).click()
        await dialog.get_by_role('button',name='重新授权',exact=True).click()
        oauth = page.locator('.approved-oauth-dialog')
        await expect(oauth.get_by_role('combobox',name='授权平台')).to_contain_text('Antigravity')
        await oauth.get_by_role('button',name='生成授权链接',exact=True).click()
        await expect(oauth.get_by_role('link',name='点击打开授权页面 ↗')).to_be_visible()
        assert fixture.oauth_sessions['a'*32]['account_id']==1
        await oauth.get_by_role('textbox',name='授权码',exact=True).fill('synthetic-code')
        await oauth.get_by_role('button',name='完成授权',exact=True).click()
        await expect(oauth).to_contain_text('已保存到原账号')
        await oauth.get_by_role('button',name='完成',exact=True).click()
        await dialog.get_by_role('button',name='取消',exact=True).click()
        fixture.held_generate=asyncio.Event()
        await page.get_by_role('button',name='授权登录',exact=True).click()
        await oauth.get_by_role('combobox',name='授权平台').click()
        await page.get_by_role('option',name='Antigravity',exact=True).click()
        await oauth.get_by_role('button',name='生成授权链接',exact=True).click()
        for _ in range(100):
            if 'b'*32 in fixture.oauth_sessions: break
            await asyncio.sleep(.05)
        else: raise AssertionError('原生成请求尚未进入')
        await page.keyboard.press('Escape')
        await expect(oauth).to_have_count(0)
        await page.get_by_role('button',name='授权登录',exact=True).click()
        fixture.held_generate.set()
        for _ in range(100):
            if any('/'+('b'*32)+'/cancel' in write['path'] for write in fixture.writes): break
            await asyncio.sleep(.05)
        else: raise AssertionError('迟到的原生会话未被取消')
        await expect(oauth.get_by_role('combobox',name='授权平台')).to_contain_text('Claude Code')
        await expect(oauth.get_by_role('link',name='点击打开授权页面 ↗')).to_have_count(0)
        await page.keyboard.press('Escape')
        fixture.held_generate=None
        await page.get_by_role('combobox',name='平台筛选').click()
        await page.get_by_role('option',name='Claude Code',exact=True).click()
        await expect(page.locator('.account-card')).to_have_count(1)
        await expect(page.locator('.account-card')).to_contain_text('CC兼容账号')
        await page.get_by_role('combobox',name='平台筛选').click()
        await page.get_by_role('option',name='Antigravity',exact=True).click()
        await expect(page.locator('.account-card')).to_have_count(2)
        await page.set_viewport_size({'width':390,'height':844})
        await first.get_by_role('button',name='编辑',exact=True).click()
        assert await dialog.evaluate('e=>e.scrollWidth<=e.clientWidth+1')
        await expect(switch).to_be_checked()
        output = ROOT/'.trellis/.runtime/agy-account-ui-390.png'
        await page.screenshot(path=str(output))
        assert not errors,errors
        print(json.dumps({'passed':True,'platform_filter':True,'independent_switches':True,'draft_survives_poll':True,'late_native_session_cancelled':True,
            'reauth_original_account':True,'mobile_390':True,'model_submissions':0},ensure_ascii=False))
        await browser.close()


if __name__=='__main__':
    asyncio.run(main())
