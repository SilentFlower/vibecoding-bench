"""对照定稿验证按钮状态、授权登录尺寸及异步会话隔离。"""
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import async_playwright, expect
from verify_proxy_design import ProxyDesignFixture
from verify_environment_ui import BASE, ROOT


class InteractionFixture(ProxyDesignFixture):
    """授权接口使用可控合成回执。"""
    delay = 0
    fail = False

    async def route(self, route):
        """模拟授权交换，避免外部授权操作。@param route 请求。@return 无。"""
        path=urlsplit(route.request.url).path
        if path.startswith('/admin/oauth/'):
            self.writes.append(dict(path=path,method=route.request.method,body=route.request.post_data_json))
            await asyncio.sleep(self.delay)
            if self.fail: return await self.respond(route,{'error':'授权码无效，请重试'},400)
            if 'generate' in path: return await self.respond(route,dict(auth_url='https://auth.example.test/local-only',session_id='synthetic-session'))
            return await self.respond(route,dict(access_token='synthetic-access-secret',refresh_token='synthetic-refresh-secret',expires_at=4102444800,email_address='authorized@example.test',account_uuid='synthetic-account',organization_uuid='synthetic-org',scope='user:profile user:inference'))
        return await super().route(route)


async def main():
    """核对参考样式与真实交互。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/interactions';out.mkdir(parents=True,exist_ok=True)
    reference=json.loads((out/'reference.json').read_text()); fixture=InteractionFixture(); errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(); context=await browser.new_context(viewport={'width':1440,'height':1000})
        await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));await page.goto(BASE+'/')
        actual={}
        for key,label in [('primary','添加账号'),('outline','授权登录')]:
            button=page.get_by_role('button',name=label,exact=True)
            async def sample(): return await button.evaluate('(e)=>{const s=getComputedStyle(e);return Object.fromEntries(["backgroundColor","color","borderColor","boxShadow","transform","borderRadius"].map(k=>[k,s[k]]))}')
            await page.mouse.move(1400,980);await page.wait_for_timeout(180);actual[key]={'default':await sample()}
            await button.hover();await page.wait_for_timeout(180);actual[key]['hover']=await sample()
            for state in ['default','hover']:
                for prop,value in actual[key][state].items(): assert value==reference[key][state][prop],(key,state,prop,value,reference[key][state][prop])
            await page.screenshot(path=str(out/f'actual-{key}-hover.png'))
        await page.get_by_role('button',name='授权登录',exact=True).click();dialog=page.locator('.approved-oauth-dialog');await expect(dialog).to_be_visible()
        await expect(dialog).to_have_css('width',f"{round(reference['oauth']['width'])}px")
        await dialog.evaluate('async e=>Promise.all(e.getAnimations().map(a=>a.finished))')
        await expect(dialog.get_by_role('combobox',name='授权方式')).to_contain_text('OAuth')
        await page.screenshot(path=str(out/'actual-oauth.png'))
        fixture.delay=.5
        await dialog.get_by_role('button',name='生成授权链接').click();await page.keyboard.press('Escape');await page.get_by_role('button',name='授权登录',exact=True).click()
        await page.wait_for_timeout(650);await expect(dialog.get_by_role('button',name='生成授权链接')).to_be_visible()
        fixture.delay=0
        await dialog.get_by_role('button',name='生成授权链接').click();await expect(dialog.get_by_role('link',name='点击打开授权页面 ↗')).to_be_visible()
        await dialog.get_by_label('授权码',exact=True).fill('synthetic-code');fixture.fail=True
        await dialog.get_by_role('button',name='完成授权',exact=True).click();await expect(dialog.get_by_role('alert')).to_contain_text('授权码无效');await expect(dialog.get_by_label('授权码',exact=True)).to_have_value('synthetic-code')
        fixture.fail=False;await dialog.get_by_role('button',name='完成授权',exact=True).click();await expect(dialog).to_contain_text('授权成功');await expect(dialog).not_to_contain_text('synthetic-access-secret')
        await dialog.get_by_text('查看授权详情',exact=True).click();await expect(dialog.get_by_role('button',name='复制 Access Token')).to_be_visible()
        await dialog.get_by_role('button',name='填入账号配置').click();workspace=page.locator('.account-workspace');await expect(workspace.get_by_label('邮箱',exact=True)).to_have_value('authorized@example.test');await expect(workspace.get_by_label('Refresh Token',exact=True)).to_have_value('synthetic-refresh-secret')
        assert not any(w['path']=='/admin/accounts' and w['method']=='POST' for w in fixture.writes)
        await page.keyboard.press('Escape')
        for width in [720,390]:
            await page.set_viewport_size({'width':width,'height':900});await page.get_by_role('button',name='授权登录',exact=True).click();await expect(dialog).to_be_visible();assert await dialog.evaluate('e=>e.scrollWidth<=e.clientWidth+1');await page.screenshot(path=str(out/f'actual-oauth-{width}.png'));await page.keyboard.press('Escape')
        await page.emulate_media(reduced_motion='reduce');await expect(page.get_by_role('button',name='添加账号',exact=True)).to_have_css('transition-duration','0s')
        assert not errors,errors
        result=dict(passed=True,checks=['按钮默认及悬停六项视觉属性与定稿一致','授权440px','授权方式与步骤','关闭丢弃迟到回执','失败保留授权码','凭据遮蔽及原复制入口','结果填入配置且不提前创建','720/390px','减少动效'],actual=actual,errors=errors)
        (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
