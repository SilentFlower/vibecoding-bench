"""用合成接口验证任务选线、独立测试反馈和全站阅读尺寸。"""
import asyncio
import copy
import json
import re
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import BASE, ROOT


class ConsoleFixture(WorkspaceFixture):
    """记录真实组件提交并控制乱序测试回执。"""

    def __init__(self):
        """初始化两种任务与独立测试闸门。@return None。"""
        super().__init__()
        second = copy.deepcopy(self.task_accounts[0]);second.update(id=2,name='独立任务',cc2api_account_id=None)
        self.task_accounts.append(second)
        self.selected = {1: 'proxy-1', 2: 'proxy-2'}
        self.proxies[0]['expires_at'] = '2020-01-01T00:00:00Z'
        self.test_calls = []
        self.test_gate = asyncio.Event()
        self.fail_save = False
        self.fail_token = False

    def selection(self, identity):
        """生成公共版本快照。@param identity 任务ID。@return 公开选择。"""
        account = next(a for a in self.task_accounts if a['id']==identity)
        proxy = next((p for p in self.proxies if p['id']==self.selected[identity]),None)
        current = {**proxy,'kind':'directory'} if proxy else {'kind':'direct','name':'直连','public_url':'','status':'unknown','observation':None}
        return dict(account_id=identity,name=account['name'],gateway_account_id=account.get('cc2api_account_id'),selection_revision='a'*64,current=current)

    async def route(self, route):
        """拦截新接口及测试请求，所有外部访问沿已有夹具关闭。@param route 浏览器请求。@return None。"""
        req=route.request;path=urlsplit(req.url).path
        if self.fail_token and path.startswith('/admin/tokens/') and req.method != 'GET':
            return await self.respond(route, {'error': '合成保存失败，保留表单草稿'}, 500)
        if path=='/runtime/api/accounts':
            return await self.respond(route,[{**a,'proxy_selection':self.selection(a['id'])['current']} for a in self.task_accounts])
        match=re.fullmatch('/runtime/api/accounts/(1|2)/proxy-selection',path)
        if match:
            identity=int(match[1])
            if req.method=='PUT':
                body=req.post_data_json;self.writes.append(dict(path=path,method=req.method,body=body))
                if self.fail_save:return await self.respond(route,{'error':'合成版本冲突，请重新读取'},409)
                assert set(body)<= {'selection_revision','proxy_id','proxy_revision'} and body['selection_revision']=='a'*64
                self.selected[identity]=body['proxy_id']
            return await self.respond(route,self.selection(identity))
        match=re.fullmatch(r'/admin/accounts/(\d+)/test',path)
        if match:
            identity=int(match[1]);self.test_calls.append(identity)
            if identity==1:await self.test_gate.wait()
            return await self.respond(route,dict(status='ok' if identity==1 else 'error',message='连接正常' if identity==1 else '<script>window.injected=1</script>\n合成连接失败：'+('请检查线路。'*40)))
        return await super().route(route)


async def main():
    """执行可观察行为及七档CSS视口断言。@return None。"""
    out=ROOT/'.deploy/console-proxy-typography-feedback/after';out.mkdir(parents=True,exist_ok=True)
    fixture=ConsoleFixture();errors=[];checks=[];metrics={}
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000})
        await context.route('**/*',fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack))
        await page.goto(BASE+'/tasks');await expect(page.locator('.work-account')).to_have_count(2)
        root=await page.locator('.task-runtime').element_handle()
        first_task=page.locator('[data-work-account-card="1"]')
        await first_task.locator('.fui-info-trigger').hover();await expect(page.locator('.fui-info-content')).to_contain_text('线路 1');await page.keyboard.press('Escape')
        before_writes=len(fixture.writes);await first_task.get_by_role('button',name='删除',exact=True).click()
        await expect(page.locator('.fui-confirm-dialog')).to_be_visible();await page.locator('.fui-confirm-dialog').get_by_role('button',name='取消',exact=True).click();assert len(fixture.writes)==before_writes
        checks.append('任务线路组件气泡及统一确认取消零写入')
        for identity in [1,2]:
            card=page.locator(f'[data-work-account-card="{identity}"]');opener=card.locator('.work-proxy-switch')
            await opener.click();dialog=page.locator('.task-proxy-dialog');await expect(dialog).to_be_visible();await expect(page.locator('.account-workspace')).to_have_count(0)
            if identity == 1: await expect(dialog.locator('.task-proxy-expiry')).to_contain_text('已过期')
            await dialog.locator('.proxy-picker-trigger').click();popup=page.locator('.proxy-picker-popup')
            await popup.get_by_role('searchbox',name='搜索代理线路').fill('线路 21');await popup.get_by_role('button',name=re.compile('线路 21')).click()
            before=len(fixture.writes);await dialog.get_by_role('button',name='取消',exact=True).click();assert len(fixture.writes)==before
            await expect(opener).to_be_focused();assert page.url==BASE+'/tasks'
            await opener.click();await dialog.locator('.proxy-picker-trigger').click();await popup.get_by_role('button',name=re.compile('直连')).click()
            fixture.fail_save=True;await dialog.get_by_role('button',name='保存并切换').click();await expect(dialog.get_by_role('alert')).to_contain_text('合成版本冲突');await expect(dialog.locator('.proxy-picker-trigger')).to_contain_text('直连')
            fixture.fail_save=False;await dialog.get_by_role('button',name='保存并切换').click();await expect(dialog).to_have_count(0);await expect(card.locator('.work-proxy-name')).to_have_text('直连')
            assert fixture.writes[-1]['body']==dict(selection_revision='a'*64,proxy_id=None)
            assert await root.evaluate('e=>e===document.querySelector(".task-runtime")');await expect(opener).to_be_focused();assert page.url==BASE+'/tasks'
        checks.append('关联与独立任务专用选线、取消零写、失败草稿、精确载荷与原路由焦点')
        await page.goto(BASE+'/');cards=page.locator('.account-card-grid>[data-slot=card]');await expect(cards).to_have_count(12)
        first,second=cards.nth(0),cards.nth(1);before=[await x.evaluate('e=>{const r=e.getBoundingClientRect();return {height:r.height,top:r.top+scrollY,left:r.left}}') for x in [first,second]]
        await first.get_by_role('button',name='测试',exact=True).evaluate('(e)=>{e.click();e.click()}')
        await expect(first.get_by_role('button',name='测试结果：测试中')).to_be_disabled()
        await second.get_by_role('button',name='测试',exact=True).click();await expect(second.get_by_role('button',name='测试结果：测试失败')).to_be_visible()
        fixture.test_gate.set();await expect(first.get_by_role('button',name='测试结果：连接正常')).to_be_visible()
        assert fixture.test_calls==[1,2],fixture.test_calls
        for i,node in enumerate([first,second]):
            after=await node.evaluate('e=>{const r=e.getBoundingClientRect();return {height:r.height,top:r.top+scrollY,left:r.left}}');assert all(abs(after[key]-before[i][key])<1 for key in before[i]),(before[i],after)
        await second.get_by_role('button',name='测试结果：测试失败').click();await expect(page.locator('.fui-operation-result')).to_contain_text('<script>window.injected=1</script>');assert await page.evaluate('window.injected===undefined')
        await page.screenshot(path=str(out/'test-result-1440.png'));await page.keyboard.press('Escape')
        await first.get_by_role('button',name='删除',exact=True).click();confirm=page.locator('.fui-confirm-dialog');await expect(confirm).to_be_visible();await confirm.get_by_role('button',name='取消',exact=True).click()
        checks.append('账号并发测试隔离、同账号去重、固定卡片尺寸、文本错误与公共确认')
        await page.goto(BASE+'/tokens');fixture.fail_token=True
        await page.get_by_role('button',name='编辑权限',exact=True).click();editor=page.locator('.approved-token-editor')
        await editor.locator('.token-name input').fill('保留的表单草稿');save=editor.get_by_role('button',name='保存权限',exact=True);await save.click()
        await expect(page.locator('.fui-notice')).to_contain_text('合成保存失败');await page.keyboard.press('F8');await expect(page.locator('.fui-notice-close')).to_be_focused()
        await page.keyboard.press('Escape');await expect(page.locator('.fui-notice')).to_have_count(0);await expect(editor).to_be_visible();await expect(editor.locator('.token-name input')).to_have_value('保留的表单草稿');await expect(save).to_be_focused()
        await save.click();await page.locator('.fui-notice-close').click();await expect(page.locator('.fui-notice')).to_have_count(0);await expect(editor).to_be_visible()
        for action in ['cancel', 'escape']:
            await save.click();await expect(page.locator('.fui-notice')).to_be_visible()
            if action == 'cancel':await editor.get_by_role('button',name='取消',exact=True).click()
            else:await page.keyboard.press('Escape')
            await expect(editor).to_have_count(0);await expect(page.locator('.fui-notice')).to_be_visible()
            await page.get_by_role('button',name='编辑权限',exact=True).click();await expect(page.locator('.fui-notice')).to_be_visible()
            await page.locator('.fui-notice-close').click();await expect(page.locator('.fui-notice')).to_have_count(0);await expect(editor).to_be_visible()
        await save.click();await expect(page.locator('.fui-notice')).to_be_visible();await editor.get_by_role('button',name='取消',exact=True).click()
        await page.locator('.navigation-item[href="/"]').click();await expect(page.locator('.fui-notice')).to_be_visible();await page.keyboard.press('F8');await expect(page.locator('.fui-notice-close')).to_be_focused();await page.keyboard.press('Escape');await expect(page.locator('.fui-notice')).to_have_count(0);fixture.fail_token=False
        checks.append('模态表单失败通知的F8、Escape、鼠标关闭、草稿和焦点保持')
        for path,name,ready in [('/','accounts','.account-card-grid'),('/tasks','tasks','.work-account'),('/proxies','proxies','.proxy-panel'),('/requests','requests','.request-records'),('/tokens','tokens','.token-row'),('/settings','settings','.settings-layout'),('/environments','environments','.environment-rich')]:
            await page.goto(BASE+path)
            if name=='settings':await page.get_by_role('heading',name='系统设置',exact=True).wait_for()
            else:await page.locator(ready).first.wait_for()
            await page.evaluate('document.fonts.ready')
            for width in [390,1280,1440,1680,1920,2560,3440]:
                await page.set_viewport_size({'width':width,'height':1000})
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(name,width)
                font=await page.locator('html').evaluate('e=>getComputedStyle(e).fontSize');expected='16px' if width>=2560 else '15px' if width>=1920 else '14px';assert font==expected,(name,width,font)
                if name=='accounts' and width>=1680:
                    columns=await page.locator('.account-card-grid').evaluate('e=>getComputedStyle(e).gridTemplateColumns.split(" ").length');assert columns==4,(width,columns)
                metrics[f'{name}-{width}']={'root_font':font}
                if width in [390,1440,2560]:await page.screenshot(path=str(out/f'{name}-{width}.png'))
        checks.append('七页七档实际字号、四列与无页面横向溢出')
        assert not errors,errors
        await browser.close()
    (out/'verification.json').write_text(json.dumps(dict(passed=True,checks=checks,metrics=metrics,errors=errors),ensure_ascii=False,indent=2))
    print(json.dumps(dict(passed=True,checks=checks),ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
