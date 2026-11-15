"""用真实SQLite工程夹具核对研究、交付及冻结预览工作区。"""
import asyncio,json,re,sys
from urllib.parse import urlsplit,parse_qs
from playwright.async_api import async_playwright,expect
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import ROOT,BASE
sys.path.insert(0,str(ROOT/'services/orchestrator'))
from test_projects_agent import ProjectsAgentTests,CatalogFixture
from project_library import materialize_snapshot,read_document


class DesignCatalog(CatalogFixture):
    """沿用工程合同，追加可见研究文本。"""
    def project(self,key,detail=True):
        """返回同一项目的完整公开结构。@param key 项目。@param detail 详细标记。@return 研究资料。"""
        value=super().project(key,detail);value.update(title='输入校验工程',research={'report':'<img src=x onerror="window.researchInjected=1">研究正文','roadmap':'先补齐校验，再增加测试。'});return value


class ProjectFixture(WorkspaceFixture):
    """在临时数据库和物理目录中生成两份冻结成果。"""
    def __init__(self):
        """准备隔离服务与故意变化的当前源码。@return 无。"""
        super().__init__();self.fixture=ProjectsAgentTests('test_pause_rejects_old_generation_before_any_terminal_write');self.fixture.setUp();f=self.fixture;f.catalog=DesignCatalog(f.root);f.service.catalog=f.catalog;f.activate();started=f.start_work();work=f.service._one('SELECT * FROM projects_work WHERE id=?',(started['work_id'],));self.work_id=work['id'];path=f.terminal.workspace(work)/'library/app.py';path.write_text('VALUE = 2\n');self.first=f.tool('project_submit',{'summary':'首次冻结'},call_id='first')['submission_id'];path.write_text('VALUE = 3\n');f.verification={'status':'passed','feedback':['隔离验收通过']};self.latest=f.tool('project_submit',{'summary':'修复后冻结'},call_id='latest')['submission_id'];path.write_text('VALUE = 999\n');
        for identifier in [self.first,self.latest]:
            directory=f.root/'projects/submissions'/identifier;materialize_snapshot(read_document(directory/'snapshot.json'),f.root/'projects/objects',directory/'candidate')
        self.read_gate=None;self.read_started=asyncio.Event();self.files=[]
    async def route(self,route):
        """只将工程读取映射到真实服务，其他流量复用管理夹具。@param route 请求。@return 无。"""
        url=urlsplit(route.request.url);path=url.path;service=self.fixture.service;value=None
        if path.startswith('/runtime/api/projects'):
            suffix=path[len('/runtime/api/projects'):];query=parse_qs(url.query)
            if suffix=='':value=service.view()
            elif suffix=='/catalog':value=service.catalog.listing()
            elif suffix.startswith('/catalog/'):value=service.catalog.project(suffix.rsplit('/',1)[1])
            elif suffix=='/agents/1/snapshot':value=service.snapshot(1)
            elif suffix=='/agents/1/work/page':value=service.work_page(1,query.get('before',[None])[0],int(query.get('limit',['10'])[0]))
            elif suffix=='/agents/1/events/page':value=service.event_page(1,int(query['before'][0]) if query.get('before') else None,int(query.get('limit',['20'])[0]))
            elif suffix=='/agents/1/actions':value=service.actions(1)
            elif suffix.startswith('/work/'):value=service.work_detail(suffix.rsplit('/',1)[1])
            elif suffix.startswith('/submissions/'):
                relative=query.get('path',[None])[0];identifier=suffix.rsplit('/',1)[1];value=service.submission(identifier,relative)
                if relative:
                    self.files.append((identifier,relative));gate=self.read_gate;self.read_gate=None
                    if gate:self.read_started.set();await gate.wait()
            elif suffix=='/stream':return await route.fulfill(content_type='text/event-stream',body='retry: 60000\n\n')
            if value is not None:return await self.respond(route,value)
        return await super().route(route)


async def main():
    """验证真实冻结版本、自动预览、取消和迟到回包。@return 无。"""
    fixture=ProjectFixture();errors=[];out=ROOT/'.deploy/frontend-sidebar-refresh/projects-deep';out.mkdir(parents=True,exist_ok=True)
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/tasks');await page.locator('.task-runtime [data-tab=projects]').click();f=page.locator('.task-runtime');await expect(f.locator('#projects-goal')).to_have_text('修复实际行为');await f.locator('[data-project-pane=pool]').click();await f.locator('[data-research=example]').click();research=f.locator('#projects-research');await expect(research).to_be_visible();await expect(research).to_contain_text('研究正文');await research.get_by_role('button',name='实施路线',exact=True).click();await expect(research).to_contain_text('先补齐校验');await research.get_by_role('button',name='工程目标',exact=True).click();await expect(research.locator('.upgrade-objective')).to_have_count(1);await research.get_by_role('button',name='研究报告',exact=True).click();assert await f.evaluate('()=>window.researchInjected===undefined');await page.screenshot(animations='disabled',path=str(out/'research-1440.png'));await research.get_by_role('button',name='关闭项目研究').click()
            await f.locator('[data-project-pane=history]').click();await f.locator('[data-work]').first.click();delivery=f.locator('#projects-delivery');await expect(delivery).to_be_visible();preview=delivery.locator('#projects-delivery-preview');await expect(preview).to_have_text('VALUE = 3\n');assert fixture.files[-1]==(fixture.latest,'library/app.py');await delivery.locator('#projects-submission').select_option(fixture.first);await expect(preview).to_have_text('VALUE = 2\n');await page.screenshot(animations='disabled',path=str(out/'delivery-1440.png'))
            fixture.read_gate=asyncio.Event();gate=fixture.read_gate;await delivery.locator('#projects-submission').select_option(fixture.latest);await fixture.read_started.wait();await delivery.get_by_role('button',name='关闭冻结交付').click();gate.set();await page.wait_for_timeout(100);await expect(delivery).to_be_hidden();await f.locator('[data-work]').first.click();await expect(preview).to_have_text('VALUE = 3\n')
            for width in [720,390]:
                await page.set_viewport_size({'width':width,'height':1000});assert await delivery.evaluate('e=>e.scrollWidth<=e.clientWidth');assert await f.evaluate('e=>e.scrollWidth<=innerWidth');await page.screenshot(animations='disabled',path=str(out/f'delivery-{width}.png'))
            await delivery.get_by_role('button',name='关闭冻结交付').click();await f.locator('[data-project-pane=pool]').click();await f.locator('[data-research=example]').click();await page.go_back();await expect(f.locator('#projects-research')).to_have_count(0);assert not errors,errors;print('工程研究文本、真实SQLite交付、冻结源码自动预览、历史切换、关闭迟到响应、切页收口和三种宽度通过');await browser.close()
    finally:fixture.fixture.doCleanups()


if __name__=='__main__':asyncio.run(main())
