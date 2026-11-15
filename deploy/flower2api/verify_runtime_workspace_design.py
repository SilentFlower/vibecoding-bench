"""验证原生任务模块的新分区及共享控件；业务接口使用合成回执。"""
import asyncio,json,re
from urllib.parse import urlsplit
from playwright.async_api import async_playwright,expect
from verify_remaining_pages import RemainingPagesFixture
from verify_environment_ui import ROOT,BASE


class WorkspaceFixture(RemainingPagesFixture):
    """提供真实字段结构，隔离工程和养号命名空间。"""
    async def route(self,route):
        """回传合成工作区快照。@param route 请求。@return 无。"""
        request=route.request;path=urlsplit(request.url).path
        if path=='/runtime/api/topics':return await self.respond(route,[{'id':1,'no':1,'title':'输入校验与异常处理','category':'工程质量','description':'完善输入校验，提供清楚的错误反馈。','followups':['覆盖边界场景']}])
        if path=='/runtime/api/task-batches':return await self.respond(route,[{'id':1,'account_id':1,'status':'paused','done_count':2,'item_count':8,'concurrency':2,'interval_min_sec':10,'interval_max_sec':30}])
        match=re.match(r'^/runtime/api/(projects|accounts/warmup/pi)(/.*)?$',path)
        if match:
            suffix=match[2] or '';agent={'account_id':1,'status':'off','controller_active':False,'project_keys':['sample'],'instructions':'原有指南','budget_sec':3600,'work':None,'schedule':{'enabled':False,'interval_minutes':60,'interval_max_minutes':None,'state':'off'},'progress':{'passed':0,'total':1,'remaining':1}}
            if suffix=='':return await self.respond(route,{'agents':[agent],'pi_available':True})
            if suffix=='/catalog':return await self.respond(route,{'projects':[{'project_key':'sample','title':'示例项目','ready':True,'objectives':[{'id':'validate','title':'输入校验'}]}]})
            if suffix.endswith('/snapshot'):return await self.respond(route,{'state':{'agents':[agent]},'cursor':0,'events':{'items':[],'next_before':None},'observation':None})
            if suffix.endswith('/work/page'):return await self.respond(route,{'items':[],'next_before':None})
            if suffix.endswith('/actions'):return await self.respond(route,[])
            if suffix=='/stream':return await route.fulfill(content_type='text/event-stream',body=': 本地合成事件\n\n')
        return await super().route(route)


async def main():
    """覆盖六个入口、分区草稿、子窗层级、数字和选择控件及窄屏。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/all-pages/runtime';out.mkdir(parents=True,exist_ok=True);fixture=WorkspaceFixture();errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light')")
        page=await context.new_page();page.on('pageerror',lambda error:errors.append(error.stack));await page.goto(BASE+'/tasks');frame=page.locator('.task-runtime');await expect(frame.locator('.work-account')).to_have_count(1)
        for action in ['data-cli-settings','data-quota','data-warmup-config','data-run-window-config','data-relogin','data-cc2-unbind','data-del']:await expect(frame.locator(f'[{action}]')).to_be_visible()
        await frame.locator('[data-account-details]').click();await expect(frame.locator('#modal .modal-titlebar-name')).to_have_text('账号详情');await frame.locator('#modal-close').click()
        search=frame.locator('#work-account-search');await search.fill('不存在的合成账号');await expect(frame.locator('.work-account')).to_be_hidden();await search.fill('');await expect(frame.locator('.work-account')).to_be_visible()
        assert await frame.locator('.work-account-grid').evaluate('e=>getComputedStyle(e).gridTemplateColumns.split(" ").length')==3
        await frame.locator('[data-run-window-config]').click();window=page.locator('.runtime-environment-dialog');await expect(window.get_by_role('tabpanel',name='运行时段',exact=True)).to_be_visible();await window.get_by_role('switch',name='启用运行时段').check();trigger=window.get_by_role('button',name='时段 1 开始',exact=True);previous=await trigger.inner_text();await trigger.click();popup=page.get_by_role('dialog',name='时段 1 开始',exact=True);await popup.get_by_role('spinbutton',name='小时',exact=True).fill('14');await popup.get_by_role('button',name='取消',exact=True).click();await expect(trigger).to_have_text(previous);await trigger.click();await popup.get_by_role('spinbutton',name='小时',exact=True).fill('14');await popup.get_by_role('spinbutton',name='分钟',exact=True).fill('15');await popup.get_by_role('button',name='确认',exact=True).click();await expect(trigger).to_contain_text('14:15');await window.get_by_role('button',name='关闭环境详情').click();assert page.url==BASE+'/tasks'
        await frame.locator('[data-tab=tasks]').click();await frame.get_by_role('button',name='新建批次',exact=False).click();modal=frame.locator('#batch-create-modal');await expect(modal).to_be_visible();await expect(modal.locator('.native-number')).to_have_count(4);await modal.locator('[name=concurrency]').fill('1');await modal.locator('.native-choice-trigger').first.click();await expect(frame.locator('.native-choice-popup')).to_be_visible();await frame.locator('.native-choice-popup').press('Escape');await expect(modal).to_be_visible();await modal.locator('[name=concurrency]').press('Escape');await expect(modal).to_be_hidden()
        await frame.locator('[data-tab=runs]').click();await expect(frame.locator('.run-config-grid')).to_be_hidden();await frame.get_by_role('button',name='运行配置',exact=True).click();await expect(frame.locator('#runtime-settings-modal')).to_be_visible();await frame.get_by_role('button',name='关闭运行配置',exact=True).click()
        await frame.locator('[data-tab=projects]').click();await expect(frame.locator('#projects-account')).to_have_value('1');await frame.get_by_role('button',name='项目池与指南',exact=True).click();guide=frame.locator('#projects-agent-form [name=instructions]');await guide.fill('未保存的工程指南');await frame.get_by_role('button',name='自动计划',exact=True).click();await expect(frame.locator('#projects-schedule-form')).to_be_visible();await frame.get_by_role('button',name='项目池与指南',exact=True).click();await expect(guide).to_have_value('未保存的工程指南');await frame.get_by_role('button',name='模型配置',exact=True).click();await expect(frame.locator('#projects-model-form')).to_be_visible();await frame.get_by_role('button',name='交付历史',exact=True).click();await expect(frame.locator('.projects-records')).to_be_visible()
        await frame.locator('[data-tab=topics]').click();await frame.locator('[data-topic-batch]').click();await expect(frame.locator('#batch-create-modal')).to_be_visible();await expect(frame.locator('#batch-topic-list input[type=checkbox]:checked')).to_have_count(1);await frame.locator('#batch-create-modal').get_by_role('button',name='取消',exact=True).click()
        await frame.locator('[data-tab=runs]').click();await frame.locator('#work-capture-new').click();await expect(frame.locator('#runtime-capture-modal')).to_be_visible();await expect(frame.locator('#runtime-settings-modal')).to_be_hidden();await frame.get_by_role('button',name='关闭抓包配置',exact=True).click()
        for tab in ['accounts','projects','warmup','tasks','runs','topics']:
            await frame.locator(f'[data-tab={tab}]').click();await expect(page).to_have_url(BASE+('/tasks' if tab=='accounts' else '/tasks?tab='+tab+('&account=1' if tab in ('projects','warmup') else '')));await page.screenshot(path=str(out/f'{tab}-1440.png'))
            await page.set_viewport_size({'width':390,'height':844});assert await frame.evaluate('e=>e.scrollWidth<=innerWidth'),tab;await page.screenshot(path=str(out/f'{tab}-390.png'));await page.set_viewport_size({'width':1440,'height':1000})
        assert not fixture.writes,fixture.writes;assert not errors,errors
        (out/'verification.json').write_text(json.dumps({'passed':True,'modules':6,'preserved_actions':7,'drafts':'分类往返保持','native_select_escape':'只关闭最上层','errors':errors},ensure_ascii=False,indent=2));print('任务六模块、分类草稿和共享控件验证通过');await browser.close()


if __name__=='__main__':asyncio.run(main())
