"""验证任务授权复用目录组件、完整视口弹窗与原登录载荷。"""
import asyncio,json,re
from urllib.parse import urlsplit
from playwright.async_api import async_playwright,expect
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import ROOT,BASE


class LoginFixture(WorkspaceFixture):
    """隔离登录启动与取消，浏览器不连接真实认证服务。"""
    def __init__(self):
        """初始化公开选线和可控登录回执。@return 无。"""
        super().__init__();self.login_calls=[];self.fail_start=True;self.cancelled=[]
    async def route(self,route):
        """接管登录接口，其余使用代理目录分页夹具。@param route 请求。@return 无。"""
        path=urlsplit(route.request.url).path
        if path=='/runtime/api/accounts/login/synthetic-login/status':return await self.respond(route,{'phase':'authorizing','reconnectable':True,'credentials_ready':False,'authorization_url':None})
        if path=='/runtime/api/terminal-ticket':return await self.respond(route,{'ticket':'synthetic-only'})
        if path=='/runtime/api/accounts/login/start':
            self.login_calls.append(route.request.post_data_json)
            if self.fail_start:return await self.respond(route,{'error':'合成登录暂不可用'},400)
            return await self.respond(route,dict(session_id='synthetic-login',ws_path='/api/accounts/login/ws/synthetic-login',has_sidecar=True,name='design-login',reconnectable=True,environment_id='synthetic-environment',draft_generation='draft-1'))
        if path=='/runtime/api/accounts/login/synthetic-login' and route.request.method=='DELETE':self.cancelled.append(path);return await self.respond(route,{'ok':True})
        return await super().route(route)


async def main():
    """覆盖目录搜索、Esc、取消零写入、版本载荷、手动兼容与终端工作区。@return 无。"""
    fixture=LoginFixture();errors=[];out=ROOT/'.deploy/frontend-sidebar-refresh/task-login-deep';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light')");page=await context.new_page();await page.route_web_socket(re.compile('.*'),lambda ws:ws.on_message(lambda _:None));page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/tasks');f=page.locator('.task-runtime');await f.locator('#add-account').click();modal=f.locator('#acc-modal');picker=f.locator('#runtime-login-proxy .proxy-picker-trigger');await expect(picker).to_be_visible();await expect(page.locator('iframe')).to_have_count(0);bounds=await modal.bounding_box();assert bounds==dict(x=0,y=0,width=1440,height=1000),bounds;assert await page.evaluate("document.elementFromPoint(30,300).closest('#acc-modal')!==null")
        await picker.click();await expect(f.locator('.proxy-picker-popup')).to_be_visible();await page.keyboard.press('Escape');await expect(f.locator('.proxy-picker-popup')).to_have_count(0);await expect(modal).to_be_visible();await picker.click();await modal.locator('[name=name]').click();await expect(f.locator('.proxy-picker-popup')).to_have_count(0);await picker.click();await f.get_by_role('searchbox',name='搜索代理线路').fill('线路 21');await f.locator('.proxy-picker-options').get_by_role('button',name='线路 21',exact=False).click();await expect(picker).to_contain_text('线路 21');await modal.locator('[name=name]').fill('design-login');await page.screenshot(animations='disabled',path=str(out/'config-1440.png'));await modal.get_by_role('button',name='开始授权',exact=True).click();await expect(page.locator('.fui-toast-stack')).to_contain_text('合成登录暂不可用');assert fixture.login_calls[-1]==dict(name='design-login',force_reauth=False,proxy_id='proxy-21',proxy_revision='revision-1'),fixture.login_calls
        await modal.locator('#acc-modal-close').click();await expect(modal).to_be_hidden();await expect(page.locator('iframe')).to_have_count(0);await f.locator('#add-account').click();await expect(picker).to_be_visible();await modal.locator('[name=name]').fill('direct');await modal.get_by_role('button',name='开始授权',exact=True).click();assert fixture.login_calls[-1]['proxy_id'] is None;assert not any(k.startswith('upstream_') for k in fixture.login_calls[-1]);await modal.locator('#acc-modal-close').click()
        await f.locator('#add-account').click();await modal.locator('[name=name]').fill('manual');await modal.locator('#acc-proxy-manual summary').click();await modal.locator('#acc-use-manual').check();await modal.locator('[name=upstream_socks5_host]').fill('manual.example.test');await modal.locator('[name=upstream_socks5_port]').fill('8080');await modal.get_by_role('button',name='开始授权',exact=True).click();assert fixture.login_calls[-1]['upstream_socks5_host']=='manual.example.test' and 'proxy_id' not in fixture.login_calls[-1];await modal.locator('#acc-modal-close').click()
        fixture.fail_start=False;await f.locator('#add-account').click();await modal.locator('[name=name]').fill('design-login');await modal.get_by_role('button',name='开始授权',exact=True).click();await expect(modal.locator('.login-session')).to_be_visible();await expect(modal.locator('.upgrade-steps')).to_contain_text('浏览器授权');await expect(modal.locator('#acc-login-xterm .xterm')).to_be_visible();await expect(modal.locator('#acc-login-connection-status')).to_contain_text('已连接')
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});assert await modal.evaluate('e=>e.scrollWidth<=e.clientWidth');await page.screenshot(animations='disabled',path=str(out/f'session-{width}.png'))
        await modal.get_by_role('button',name='取消登录',exact=True).click();await expect(modal).to_be_hidden();assert len(fixture.cancelled)==1;assert not errors,errors;print('任务授权复用目录选线、服务端分页搜索、Esc层级、ID/revision载荷、直连、手动兼容、完整视口、终端工作区和取消通过');await browser.close()


if __name__=='__main__':asyncio.run(main())
