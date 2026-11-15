"""验证任务深层弹窗、局部代理及工程/养号共享视觉与真实载荷。"""
import asyncio,copy,json,re,time
from urllib.parse import urlsplit
from playwright.async_api import async_playwright,expect
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import BASE,ROOT


class TaskFeedbackFixture(WorkspaceFixture):
    """提供额度零值、缺失值、两类养号及有状态工程快照。"""
    def __init__(self):
        """冻结本地示例状态与可控查询回执。@return 无。"""
        super().__init__();self.task_accounts[0].update(warmup_engine='projects',warmup_quota_5h_limit_percent=90,warmup_quota_7d_limit_percent=90)
        self.quota={'ok':True,'five_hour':{'utilization':0,'resets_at':'2026-11-18T10:00:00Z'},'seven_day':{'utilization':82},'seven_day_fable':None};self.quota_gate=None;self.quota_started=asyncio.Event();self.policy_writes=[];self.with_work=True
        self.agent={'account_id':1,'controller_active':True,'status':'running','project_keys':['sample'],'budget_sec':3600,'schedule':{'enabled':False,'state':'off','interval_minutes':60},'work':{'id':'w-current','project_key':'sample','objective_id':'now','goal':'补齐输入验证','session_id':'synthetic-session','status':'running','work_sec':80},'progress':{'completed':1,'remaining':2,'total':3},'passed':[{'project_key':'sample','objective_id':'before','goal':'梳理校验流程'}],'available_objectives':[{'project_key':'sample','objective_id':'now','goal':'补齐输入验证'}],'waiting_objectives':[{'project_key':'sample','objective_id':'after','goal':'补齐边界测试','message':'等待前置目标通过'}],'admission':{'allowed':True,'cli_capacity':{'active':0,'limit':2},'window':{'enabled':False,'allowed':True,'timezone':'Asia/Shanghai'},'quota':{'known':True,'observed_at':time.time(),'limits':{'five_hour':90,'seven_day':90},'windows':{'five_hour':{'utilization':0},'seven_day':{'utilization':42}}}},'verification':None}
        self.events=[{'id':1,'kind':'pi','created_at':time.time(),'payload':{'text':'读取当前实现，检查空值与边界输入。'}},{'id':2,'kind':'input','created_at':time.time(),'payload':{'text':'<script>window.injected=1</script>\n补齐边界测试。'}}]

    async def route(self,route):
        """隔离配置写入与查询，保留原请求路径和字段。@param route 浏览器请求。@return 无。"""
        path=urlsplit(route.request.url).path
        if path=='/runtime/api/accounts/1/quota':
            assert route.request.method=='POST';self.quota_started.set()
            if self.quota_gate:await self.quota_gate.wait()
            return await self.respond(route,copy.deepcopy(self.quota))
        if path=='/runtime/api/accounts/1/warmup' and route.request.method=='PUT':
            body=route.request.post_data_json;self.policy_writes.append(body);self.task_accounts[0].update({('warmup_enabled' if key=='enabled' else key):value for key,value in body.items()});return await self.respond(route,{'ok':True})
        match=re.fullmatch(r'/runtime/api/(projects|accounts/warmup/pi)(.*)',path)
        if match:
            suffix=match[2];agent=copy.deepcopy(self.agent)
            if not self.with_work:agent.update(work=None,controller_active=False,verification=None,passed=[],available_objectives=[],waiting_objectives=[])
            if suffix=='':return await self.respond(route,{'agents':[agent],'pi_available':True})
            if suffix=='/agents/1/snapshot':return await self.respond(route,{'state':{'agents':[agent]},'cursor':2,'events':{'items':self.events if self.with_work else [],'next_before':None},'observation':None})
            if suffix=='/agents/1/events/page':return await self.respond(route,{'items':self.events if self.with_work else [],'next_before':None})
            if suffix=='/agents/1/work/page':return await self.respond(route,{'items':[],'next_before':None})
        return await super().route(route)


async def main():
    """对照参考结构并验证保存、取消、迟到回包及窄屏。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/task-feedback';out.mkdir(parents=True,exist_ok=True);fixture=TaskFeedbackFixture();errors=[];checks=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/tasks');root=page.locator('.task-runtime');await expect(root.locator('.work-account')).to_have_count(1);identity=await root.element_handle()
        await root.locator('[data-quota]').click();quota=root.locator('#modal');await expect(quota.locator('.work-quota-window')).to_have_count(3);await expect(quota.locator('.work-quota-number').first).to_have_text('0%');await expect(quota.locator('.quota-fable .work-quota-number')).to_have_text('—');await expect(quota.locator('.quota-fable .work-quota-remaining')).to_contain_text('未观测');await expect(quota.locator('.quota-fable')).to_have_css('grid-column','1 / -1');await expect(quota.locator('.work-quota-number').first).to_have_css('font-size','38px');await expect(quota.locator('.modal-card')).to_have_css('width','600px');await page.screenshot(animations='disabled',path=str(out/'quota-after-1440.png'))
        fixture.quota['five_hour']['utilization']=27;await quota.locator('[data-quota-refresh]').click();await expect(quota.locator('.work-quota-number').first).to_have_text('27%');fixture.quota_gate=asyncio.Event();fixture.quota_started.clear();await quota.locator('[data-quota-refresh]').click();await fixture.quota_started.wait();await page.keyboard.press('Escape');fixture.quota_gate.set();await expect(quota).to_be_hidden();fixture.quota_gate=None;checks.append('额度原型双卡、Fable、零值未知、手动刷新及关闭迟到回执')
        await root.locator('[data-warmup-config]').click();policy=root.locator('#warmup-modal');await expect(policy).to_be_visible();await expect(policy.locator('#warmup-legacy-interval')).to_be_hidden();field=policy.locator('[name=warmup_quota_5h_limit_percent]');await expect(field).to_have_value('90');await policy.locator('[name=quota_5h_enabled]').uncheck();await expect(field).to_be_disabled();await expect(field.locator('..').get_by_role('button')).to_have_count(2);await expect(field.locator('..').get_by_role('button').first).to_be_disabled();await policy.locator('[name=quota_5h_enabled]').check();await expect(field).to_have_value('90');await page.screenshot(animations='disabled',path=str(out/'policy-after-1440.png'));await policy.get_by_role('button',name='取消',exact=True).click();assert not fixture.policy_writes
        await root.locator('[data-warmup-config]').click();await policy.locator('[name=quota_5h_enabled]').uncheck();await policy.get_by_role('button',name='保存额度配置',exact=True).click();await expect(policy).to_be_hidden();assert fixture.policy_writes[-1]=={'warmup_quota_5h_limit_percent':None,'warmup_quota_7d_limit_percent':90};checks.append('额度关闭禁用步进、保留草稿、取消零保存与工程字段隔离')
        fixture.task_accounts[0]['warmup_engine']='worker';await page.reload();await root.locator('[data-warmup-config]').click();await expect(policy.locator('#warmup-legacy-interval')).to_be_visible();await policy.locator('[name=interval_min_hours]').fill('4');await policy.locator('[name=interval_max_hours]').fill('6');await policy.get_by_role('button',name='保存额度配置',exact=True).click();await expect(policy).to_be_hidden();assert fixture.policy_writes[-1]['interval_min_hours']==4 and fixture.policy_writes[-1]['interval_max_hours']==6;checks.append('旧养号间隔及开关载荷保留')
        await root.locator('[data-run-window-config]').click();window=page.locator('.runtime-environment-dialog');await expect(window.get_by_role('tabpanel',name='运行时段',exact=True)).to_be_visible();assert page.url==BASE+'/tasks';await window.get_by_role('switch',name='启用运行时段').check();await window.get_by_role('button',name='时段 1 开始',exact=True).click();popup=page.get_by_role('dialog',name='时段 1 开始',exact=True);await popup.get_by_role('spinbutton',name='小时',exact=True).fill('11');await popup.get_by_role('button',name='确认',exact=True).click();await expect(window.get_by_role('button',name='时段 1 开始',exact=True)).to_contain_text('11:00');await page.screenshot(animations='disabled',path=str(out/'window-after-1440.png'));await window.get_by_role('button',name='保存时段',exact=True).click();await expect(window.get_by_text('运行时段已保存',exact=True)).to_be_visible();assert fixture.writes[-1]['body']['intervals'][0]['start']=='11:00';await window.get_by_role('button',name='关闭环境详情').click();checks.append('原型环境工作区内运行时段、原字段保存与任务路由保持')
        identity=await root.element_handle();await root.locator('[data-proxy-config]').click();workspace=page.locator('.account-workspace');await expect(workspace).to_be_visible();await expect(workspace.locator('.account-proxy-picker')).to_be_visible();assert page.url==BASE+'/tasks';await workspace.get_by_role('button',name='取消',exact=True).click();await expect(workspace).to_have_count(0);assert page.url==BASE+'/tasks';checks.append('切换代理局部配置与取消保持任务路由')
        await root.locator('[data-proxy-config]').click();await expect(workspace).to_be_visible();await workspace.locator('.proxy-picker-trigger').click();await page.locator('.proxy-picker-options').get_by_role('button',name='直连',exact=False).click();await workspace.get_by_role('button',name='保存修改',exact=True).click();await expect(workspace).to_have_count(0);assert page.url==BASE+'/tasks';assert fixture.writes[-1]['body'].get('proxy_id','missing') is None;assert await identity.evaluate('e=>e===document.querySelector(".task-runtime")');checks.append('代理目录选择保存保持任务页并回读摘要')
        for tab in ['projects','warmup']:
            await root.locator('[data-tab='+tab+']').click();await root.locator('#projects-tab-events').click();assert not errors,errors;await expect(root.locator('#projects-events article')).to_have_count(2);await expect(root.locator('.work-event-avatar').first).to_have_text('P');assert await page.evaluate('window.injected===undefined');await page.screenshot(animations='disabled',path=str(out/f'{tab}-events-1440.png'));await expect(root.locator('#projects-admission-badge')).to_have_text('满足执行条件');await expect(root.locator('#projects-capacity')).to_have_text('0 / 2');await expect(root.locator('#projects-current>li')).to_have_count(3);await expect(root.locator('#projects-current>.current')).to_contain_text('补齐输入验证');await root.locator('#projects-tab-verification').click();await expect(root.locator('#projects-verification-empty li')).to_have_count(3);await page.screenshot(animations='disabled',path=str(out/f'{tab}-verification-empty-1440.png'));await root.locator('[data-project-pane=history]').click();await expect(root.locator('#projects-history h3')).to_have_text('暂无工程与交付记录');await page.screenshot(animations='disabled',path=str(out/f'{tab}-history-empty-1440.png'))
        checks.append('工程养号两空间的交互卡片、转义、目标列表、验收步骤及空记录')
        fixture.agent['verification']={'active':True,'status':'verifying','started_at':time.time()-12,'stages':[{'message':'执行独立验收','started_at':time.time()-10}]};await root.locator('[data-project-pane=overview]').click();await root.locator('#projects-refresh').click();await expect(root.locator('#projects-verification-stages li')).to_have_count(1);await root.locator('#projects-tab-verification').click();await expect(root.locator('#projects-verification-empty')).to_be_hidden();node=await root.locator('#projects-verification-stages li').element_handle();await page.wait_for_timeout(1100);assert await node.evaluate('e=>e.isConnected');checks.append('验收实时计时保持节点')
        for width in [720,390]:
            await page.set_viewport_size({'width':width,'height':1000});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.screenshot(animations='disabled',path=str(out/f'project-{width}.png'));await root.locator('[data-tab=accounts]').click()
            for button,selector,name in [('[data-quota]','#modal','quota'),('[data-warmup-config]','#warmup-modal','policy'),('[data-run-window-config]','.runtime-environment-dialog','window')]:
                await root.locator(button).click();modal=page.locator(selector);await expect(modal).to_be_visible();assert await (modal if name=='window' else modal.locator('.modal-card')).evaluate('e=>e.scrollWidth<=e.clientWidth');await page.screenshot(animations='disabled',path=str(out/f'{name}-after-{width}.png'));await page.keyboard.press('Escape')
            await root.locator('[data-tab=projects]').click()
        assert not errors,errors;print(json.dumps({'passed':True,'checks':checks,'errors':errors},ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
