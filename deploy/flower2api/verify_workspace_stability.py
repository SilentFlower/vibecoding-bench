"""验证代理局部工作区、诊断入口及实时页面的节点与滚动稳定性。"""
import asyncio,copy,json,re,time
from urllib.parse import urlsplit
from playwright.async_api import async_playwright,expect
from verify_environment_workspace_design import ResourceFixture
from verify_environment_ui import ROOT,BASE,ENVIRONMENT


class StabilityFixture(ResourceFixture):
    """合成关联账号和正在验收的工程，记录读取与业务写入。"""
    def __init__(self):
        """准备跨分页账号、长列表与可控首屏。@return 无。"""
        super().__init__();self.accounts[0]['proxy_id']=None;self.accounts[12].update(proxy_id='proxy-1',proxy_name='线路 1');self.rows[0]['gateway_account_id']=13;self.rows[0]['run_window']['message']='全天可运行';base=copy.deepcopy(self.rows[0]);self.rows=[self.rows[0]]+[dict(copy.deepcopy(base),environment_id=f'{i:032x}',gateway_account_id=100+i,name=f'稳定环境 {i}') for i in range(2,26)];self.environment_gate=None;self.account_gate=None;self.account_started=asyncio.Event();self.account_lists=0;self.started=time.time()

    async def route(self,route):
        """延迟指定只读请求，维持真实接口边界。@param route 请求。@return 无。"""
        path=urlsplit(route.request.url).path
        if path=='/admin/accounts' and route.request.method=='GET':self.account_lists+=1
        if path=='/runtime/api/environments' and self.environment_gate:await self.environment_gate.wait()
        if path=='/admin/accounts/13' and route.request.method=='GET':
            self.account_started.set()
            if self.account_gate:await self.account_gate.wait()
        return await super().route(route)

    async def respond(self,route,payload,status=200):
        """补充验收现场，计时变动时复用同一阶段节点。@param route 请求。@param payload 原回执。@param status 状态。@return 无。"""
        if '/runtime/api/projects' in route.request.url and isinstance(payload,dict):
            agents=payload.get('agents',payload.get('state',{}).get('agents',[]))
            for agent in agents:
                verification={'active':True,'status':'verifying','started_at':self.started,'stages':[{'message':'隔离验收中','started_at':self.started,'elapsed_sec':0}]};agent.update(status='verifying',verification=verification,work={'id':'stable-work','project_key':'sample','objective_id':'validate','goal':'稳定性验证','status':'verifying','session_id':'synthetic-session','created_at':self.started,'work_sec':3,'verification':verification})
        return await super().respond(route,payload,status)


async def main():
    """覆盖路由保持、深链接、DOM身份、草稿、滚动与迟到回执。@return 无。"""
    fixture=StabilityFixture();errors=[];out=ROOT/'.deploy/frontend-sidebar-refresh/stability';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/proxies');used=page.locator('[data-proxy-id=proxy-1]');await used.get_by_role('button',name='查看使用账号').click();await page.locator('.proxy-account-identity').click();workspace=page.locator('.account-workspace');await expect(workspace).to_be_visible();await expect(workspace.locator('[data-slot=dialog-title]')).to_have_text('正式账号 13');assert page.url==BASE+'/proxies';assert fixture.account_lists==0;await workspace.get_by_role('button',name='取消',exact=True).click();await expect(workspace).to_be_hidden();assert not fixture.writes;await expect(used.get_by_role('button',name='收起账号')).to_be_visible()
        await page.locator('.proxy-account-identity').click();await workspace.locator('.account-workspace-tabs').get_by_role('button',name='环境与诊断').click();summary=workspace.locator('.account-diagnostic-summary');await expect(summary).to_contain_text('就绪');await expect(summary).to_contain_text('全天可运行');assert await workspace.locator('.account-diagnostic-actions').evaluate('e=>e.getBoundingClientRect().top')>await summary.evaluate('e=>e.getBoundingClientRect().bottom');await expect(workspace.locator('.account-diagnostic-technical')).not_to_have_attribute('open','');await page.screenshot(animations='disabled',path=str(out/'proxy-local-diagnostics-1440.png'));await workspace.get_by_role('link',name='运行时段',exact=True).click();await expect(page).to_have_url(re.compile('section=schedule'))
        environment=page.locator('.runtime-environment-dialog')
        await expect(environment.get_by_role('tabpanel',name='运行时段',exact=True)).to_be_visible()
        await expect(environment.locator('.runtime-run-window')).to_be_visible()
        await environment.get_by_role('button',name='关闭环境详情').click()
        await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        await expect(environment).to_have_count(0)
        fixture.environment_gate=asyncio.Event()
        await page.goto(BASE+'/environments')
        await expect(page.locator('.environment-empty')).to_have_text('正在读取环境…')
        await expect(page.locator('iframe')).to_have_count(0)
        fixture.environment_gate.set();fixture.environment_gate=None
        await expect(page.locator('.environment-rich')).to_have_count(25)
        await page.evaluate("""()=>{window.stableEnvironment=document.querySelector('.environment-rich');window.stableButton=stableEnvironment.querySelector('.environment-card-actions button');window.scrollTo(0,500)}""")
        before=await page.evaluate('scrollY')
        fixture.rows[0]['native_preparation']['idle_workers']=2
        await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        await expect(page.locator('.runtime-page-heading button')).to_be_enabled()
        assert await page.evaluate("stableEnvironment===document.querySelector('.environment-rich')&&stableButton===stableEnvironment.querySelector('.environment-card-actions button')")
        assert await page.evaluate('scrollY')==before
        await page.set_viewport_size({'width':1440,'height':620})
        await page.locator('.environment-rich').first.get_by_role('button',name='资源与采集',exact=True).click()
        form=environment.locator('.environment-resource-editor form');cpu=form.get_by_role('spinbutton',name='CLI CPU',exact=True)
        await expect(cpu).to_be_enabled();await cpu.fill('1.5');await cpu.focus()
        await page.evaluate("""()=>{window.stableForm=document.querySelector('.environment-resource-editor form');window.stableInput=document.activeElement;window.formDetached=false;window.formObserver=new MutationObserver(records=>{for(const r of records)for(const n of r.removedNodes)if(n===stableForm||n.contains?.(stableForm))window.formDetached=true});formObserver.observe(document.querySelector('.runtime-environment-workspace'),{childList:true,subtree:true});window.resourceScroll=document.querySelector('.runtime-workspace-scroll');resourceScroll.scrollTop=80}""")
        scroll=await page.evaluate('resourceScroll.scrollTop')
        for _ in range(3):
            await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            await expect(page.locator('.runtime-page-heading button')).to_be_enabled()
        assert await page.evaluate("!formDetached&&stableForm===document.querySelector('.environment-resource-editor form')&&stableInput===document.activeElement")
        assert await page.evaluate('resourceScroll.scrollTop')==scroll
        await expect(cpu).to_have_value('1.5');await page.evaluate('formObserver.disconnect()')
        await environment.get_by_role('button',name='关闭环境详情').click()
        await page.set_viewport_size({'width':1440,'height':1000});await page.goto(BASE+'/tasks?tab=projects');f=page.locator('.task-runtime')
        await expect(f.locator('#projects-verification-stages li')).to_have_count(1)
        await page.evaluate("()=>{window.stageNode=document.querySelector('#projects-verification-stages li');window.stageBefore=stageNode.textContent;window.projectRoot=document.querySelector('.task-runtime')}")
        await page.wait_for_function('stageNode.textContent!==stageBefore')
        assert await page.evaluate("stageNode===document.querySelector('#projects-verification-stages li')")
        await f.locator('[data-tab=topics]').click();await expect(f.locator('.work-topic')).to_have_count(1)
        assert await page.evaluate("projectRoot===document.querySelector('.task-runtime')")
        await page.screenshot(animations='disabled',path=str(out/'tasks-stable-1440.png'))
        await page.goto(BASE+'/proxies');await page.locator('[data-proxy-id=proxy-1] .proxy-expand').click();fixture.account_gate=asyncio.Event();fixture.account_started.clear();await page.locator('.proxy-account-identity').click();await fixture.account_started.wait();await page.get_by_role('link',name='请求记录',exact=True).click();fixture.account_gate.set();await page.wait_for_timeout(150);await expect(page.locator('.account-workspace')).to_have_count(0);assert not fixture.writes;assert not errors,errors;print(json.dumps({'passed':True,'checks':['代理查看账号保持路由及展开','跨页账号读取','取消零写入','诊断摘要与底部三入口','运行时段深链接','原生首屏加载状态','环境刷新保持卡片和滚动','CPU表单不拆卸与输入焦点','验收计时增量更新','任务子路由复用文档','离页丢弃账号迟到回执'],'errors':errors},ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
