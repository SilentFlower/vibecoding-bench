"""验证统一页大小控件、服务端分页与跨文档抓包菜单。"""
import asyncio,json,time
from urllib.parse import urlsplit,parse_qs
from playwright.async_api import async_playwright,expect
from verify_capture_workspace_design import CaptureFixture
from verify_environment_ui import ROOT,BASE


class PageFixture(CaptureFixture):
    """提供超过一页的真实结构合成记录，并记录分页查询。"""
    def __init__(self):
        """准备请求和会话分页数据。@return 无。"""
        super().__init__();self.page_queries=[];self.fail_history=False;self.session_rows=[{'session_key':f'{i:064x}','account_id':1,'created_at_ms':1000,'last_seen_at_ms':2000,'expires_at_ms':int(time.time()*1000)+60000,'phases':{'waiting_concurrency':0,'preparing':0,'waiting_send':0,'running':0,'backoff':0}} for i in range(55)]
        self.request_rows=[{'request_id':f'00000000-0000-4000-8000-{i:012d}','started_at':'2026-11-15T00:01:00Z','finished_at':'2026-11-15T00:01:02Z','status_code':200,'account_id':13,'account_name':'正式账号 13','account_email':'design13@example.test','outcome':'success','attempt_count':1,'log_mode':'info','last_attempt':{'parameters':{'model':'synthetic-model'},'tokens':{'input_tokens':0,'output_tokens':128}}} for i in range(55)]

    async def route(self,route):
        """按请求页大小裁切，只读接口保持零业务写入。@param route 请求。@return 无。"""
        url=urlsplit(route.request.url);q=parse_qs(url.query);self.page_queries.append((url.path,q))
        if self.fail_history and url.path.endswith('/work/page') and q.get('limit')==['100']:return await self.respond(route,{'detail':'分页读取失败，保留原页'},503)
        if url.path=='/admin/request-diagnostics' or url.path.endswith('/scheduling/sessions'):
            page=int(q.get('page',['1'])[0]);size=int(q.get('page_size',['20'])[0]);rows=self.request_rows if url.path=='/admin/request-diagnostics' else self.session_rows
            return await self.respond(route,{'items':rows[(page-1)*size:page*size],'total':len(rows),'page':page,'page_size':size,'observed_at_ms':int(time.time()*1000),'health':{},'counts':{'all':55,'errors':0,'processing':0}})
        return await super().route(route)


async def choose_size(root,value):
    """通过可见组件菜单修改条数。@param root 页面或分区。@param value 页大小。@return 无。"""
    await root.get_by_role('combobox',name='每页条数',exact=True).click()
    await root.get_by_role('option',name=f'{value} 条 / 页',exact=True).click()


async def main():
    """覆盖分页参数、回到第一页、筛选保持、索引完整性及窄屏。@return 无。"""
    fixture=PageFixture();errors=[];out=ROOT/'.deploy/frontend-sidebar-refresh/pagination';out.mkdir(parents=True,exist_ok=True)
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack))
            # 账号总数取夹具实际数据（令牌夹具补齐到第二页之后），末页条数与切换条数后的首页条数都由它算出。
            total=len(fixture.accounts);last=(total-1)//12+1;cards=page.locator('.account-card-grid>.account-card')
            await page.goto(BASE);await expect(cards).to_have_count(min(12,total));await page.get_by_role('button',name='下一页',exact=True).click();await expect(cards).to_have_count(min(12,total-12));assert any(path=='/admin/accounts' and q.get('page')==['2'] and q.get('page_size')==['12'] for path,q in fixture.page_queries)
            await page.get_by_role('button',name=f'第 {last} 页',exact=True).click();await expect(cards).to_have_count(total-(last-1)*12);await choose_size(page,24);await expect(cards).to_have_count(min(24,total));assert any(path=='/admin/accounts' and q.get('page')==['1'] and q.get('page_size')==['24'] for path,q in fixture.page_queries)
            await page.goto(BASE+'/proxies');await page.get_by_role('button',name='下一页',exact=True).click();await expect(page.locator('tr[data-proxy-id]')).to_have_count(1);await choose_size(page,50);await expect(page.locator('tr[data-proxy-id]')).to_have_count(21);assert fixture.proxy_reads[-1]['page']==['1'] and fixture.proxy_reads[-1]['page_size']==['50'];await page.screenshot(animations='disabled',path=str(out/'proxies-1440.png'))
            await page.goto(BASE+'/requests?account=13');await expect(page.locator('.request-records tbody tr')).to_have_count(20);await page.get_by_role('button',name='下一页',exact=True).click();await choose_size(page,50);await expect(page.locator('.request-records tbody tr')).to_have_count(50);q=[q for path,q in fixture.page_queries if path=='/admin/request-diagnostics'][-1];assert q['page']==['1'] and q['page_size']==['50'] and q['account_id']==['13']
            await page.goto(BASE+'/?account=1');workspace=page.locator('.account-workspace');await expect(workspace).to_be_visible();await workspace.locator('.account-workspace-tabs').get_by_role('radio',name='调度').click();await expect(workspace.get_by_text('网关绑定会话',exact=True)).to_be_visible();await choose_size(page,50);await expect(workspace.locator('tbody tr')).to_have_count(50);q=[q for path,q in fixture.page_queries if path.endswith('/scheduling/sessions')][-1];assert q['page']==['1'] and q['page_size']==['50'];await workspace.locator('[data-slot=dialog-close]').click()
            await page.goto(BASE+'/tasks?tab=projects');f=page.locator('.task-runtime');await expect(f.locator('#projects-capture')).to_be_enabled();await f.locator('#projects-capture').click();capture=f.locator('.capture-workspace');await expect(capture.locator('tbody tr')).to_have_count(20);await f.get_by_role('combobox',name='每页条数',exact=True).click();await f.get_by_role('option',name='50 条 / 页',exact=True).click();await expect(capture.locator('tbody tr')).to_have_count(45);await capture.get_by_role('button',name='查看',exact=True).last.click();await expect(capture.locator('.work-log:visible')).to_contain_text('flow-44');await page.screenshot(animations='disabled',path=str(out/'capture-1440.png'))
            for width in [720,390]:
                await page.set_viewport_size({'width':width,'height':1000});assert await capture.evaluate('e=>e.scrollWidth<=e.clientWidth');await page.screenshot(animations='disabled',path=str(out/f'capture-{width}.png'))
            await f.get_by_role('button',name='关闭抓包详情').click();await f.locator('[data-project-pane=history]').click();await choose_size(page,50);await expect(f.locator('#projects-history-page')).to_contain_text('每页 50 条');assert any(path.endswith('/work/page') and q.get('limit')==['50'] for path,q in fixture.page_queries);fixture.fail_history=True;await choose_size(page,100);await expect(f.locator('#projects-history-size')).to_have_value('50');await expect(f.locator('#projects-history-page')).to_contain_text('每页 50 条');await expect(f.locator('#projects-feedback')).to_contain_text('分页读取失败');fixture.fail_history=False;await f.locator('[data-project-pane=overview]').click();await f.locator('#projects-tab-events').click();await choose_size(page,100);await expect(f.locator('#projects-events-page')).to_contain_text('每页 100 条');assert any(path.endswith('/events/page') and q.get('limit')==['100'] for path,q in fixture.page_queries);assert not fixture.writes;assert not errors,errors
            print(json.dumps({'passed':True,'checks':['账号末页与24条','代理50条','请求50条与账号筛选保持','调度会话50条','跨文档抓包45条完整可达','工程历史50条','交互记录100条','切换回第一页','失败恢复旧页大小','720/390px'],'errors':errors},ensure_ascii=False));await browser.close()
    finally:fixture.fixture.doCleanups()


if __name__=='__main__':asyncio.run(main())
