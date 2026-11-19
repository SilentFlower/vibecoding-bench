"""验证定稿令牌行和权限搜索组件，全部读写使用合成管理接口。"""
import asyncio
import copy
import json
import re
from urllib.parse import urlsplit, parse_qs
from playwright.async_api import async_playwright,expect
from verify_run_detail_design import RunDetailFixture
from verify_environment_ui import ROOT,BASE


class TokenDesignFixture(RunDetailFixture):
    """令牌操作回读真实载荷，避免静态点击验证。"""
    def __init__(self):
        """将反重力账号放在第二页，验证完整平台范围。@return 无。"""
        super().__init__()
        self.scope_queries = []
        for identity in range(14, 102):
            self.accounts.append(dict(copy.deepcopy(self.account_template), id=identity,
                name='反重力开发' if identity == 101 else f'合成账号 {identity}',
                email=f'agy{identity}@example.test', platform='antigravity' if identity == 101 else 'claude_code'))

    async def route(self,route):
        """模拟令牌CRUD。@param route 请求。@return 无。"""
        req=route.request;path=urlsplit(req.url).path
        if path == '/admin/accounts' and req.method == 'GET':
            self.scope_queries.append(parse_qs(urlsplit(req.url).query))
        if path.startswith('/admin/tokens') and req.method!='GET':
            body=req.post_data_json if req.post_data else {}
            self.writes.append(dict(path=path,method=req.method,body=body))
            if req.method=='POST':
                value=dict(id=max((item['id'] for item in self.tokens),default=0)+1,token='sk-synthetic-token',status='active',created_at='2026-11-15T00:00:00Z',**body);self.tokens.append(value)
            else:
                value=next(item for item in self.tokens if item['id']==int(path.split('/')[-1]))
                if req.method=='DELETE':self.tokens.remove(value)
                else:value.update(body)
            return await self.respond(route,value)
        return await super().route(route)


async def main():
    """覆盖选择、搜索、取消、保存、启停及删除。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/exact';out.mkdir(parents=True,exist_ok=True)
    fixture=TokenDesignFixture();errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));await page.goto(BASE+'/tokens');await expect(page.locator('.token-row')).to_have_count(1)
        await page.get_by_role('button',name='编辑权限',exact=True).click();dialog=page.locator('.approved-token-editor');await expect(dialog).to_have_css('width','760px')
        allowed=dialog.get_by_role('group',name='允许的账号');await allowed.get_by_role('button',name='选择账号',exact=True).click();await allowed.get_by_role('searchbox',name='搜索允许的账号',exact=True).fill('design13@');await expect(allowed.locator('.picker-option')).to_have_count(1);await allowed.get_by_role('checkbox').check();await expect(allowed.locator('.account-chip')).to_contain_text('正式账号 13')
        await dialog.get_by_role('button',name='取消',exact=True).click();assert not fixture.writes
        await page.get_by_role('button',name='编辑权限',exact=True).click();allowed=dialog.get_by_role('group',name='允许的账号');await allowed.get_by_role('button',name='选择账号',exact=True).click();await allowed.get_by_role('searchbox',name='搜索允许的账号',exact=True).fill('design13@');await allowed.get_by_role('checkbox').check()
        await allowed.get_by_role('searchbox',name='搜索允许的账号',exact=True).fill('agy101@')
        await expect(allowed.locator('.picker-option')).to_have_count(1)
        await expect(allowed.locator('[data-platform-badge]')).to_have_text('反重力')
        await allowed.get_by_role('checkbox').check()
        assert all(query.get('platform') == ['all'] for query in fixture.scope_queries)
        assert {query['page'][0] for query in fixture.scope_queries} == {'1', '2'}
        blocked=dialog.get_by_role('group',name='排除的账号');await blocked.get_by_role('button',name='选择账号',exact=True).click();await blocked.get_by_role('searchbox',name='搜索排除的账号',exact=True).fill('design2@');await blocked.get_by_role('checkbox').check()
        await dialog.get_by_role('button',name='保存权限',exact=True).click();await expect(dialog).to_have_count(0);assert fixture.writes[-1]['body']==dict(name='开发客户端',allowed_accounts='13,101',blocked_accounts='2')
        await expect(page.locator('.token-row')).to_contain_text('正式账号 13');await page.get_by_role('switch').click();await expect(page.get_by_role('switch')).to_have_attribute('aria-checked','false')
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});await page.screenshot(path=str(out/f'actual-tokens-{width}.png'));assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.get_by_role('button',name='编辑权限',exact=True).click()
            # 同一渲染帧读取按钮，避免入场动画造成分次测量坐标漂移。
            bounds = await dialog.locator('.token-editor-footer').evaluate('e=>({footer:e.getBoundingClientRect().toJSON(),cancel:e.children[0].getBoundingClientRect().toJSON(),submit:e.children[1].getBoundingClientRect().toJSON()})')
            footer, cancel, submit = bounds['footer'], bounds['cancel'], bounds['submit']
            assert cancel['x'] > footer['x'] and submit['x'] + submit['width'] < footer['x'] + footer['width'] - 15
            assert abs(cancel['y'] - submit['y']) < 1
            await page.screenshot(path=str(out/f'actual-token-editor-{width}.png'));assert await dialog.evaluate('e=>e.scrollWidth<=e.clientWidth+1');await page.keyboard.press('Escape')
        await page.get_by_role('button',name='删除',exact=True).click();confirm=page.get_by_role('dialog');await confirm.get_by_role('button',name='取消',exact=True).click();assert len(fixture.tokens)==1
        await page.get_by_role('button',name='删除',exact=True).click();await confirm.get_by_role('button',name='删除',exact=True).click();await expect(page.locator('.token-row')).to_have_count(0)
        assert not errors,errors
        result=dict(passed=True,checks=['行布局与直接操作','跨页账号搜索','取消零写入','允许排除CSV载荷','启停','删除确认','1440/720/390px'],errors=errors);(out/'token-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
