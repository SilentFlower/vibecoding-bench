"""核对运行及工程共享抓包组件的真实入口、分页、文件与TLS白名单。"""
import asyncio,json
from urllib.parse import urlsplit,parse_qs
from playwright.async_api import async_playwright,expect
from verify_project_workspace_design import ProjectFixture
from verify_environment_ui import ROOT,BASE


class CaptureFixture(ProjectFixture):
    """保留真实冻结工程，抓包使用独立脱敏元数据。"""
    def __init__(self):
        """准备45条索引和受限文件。@return 无。"""
        super().__init__();self.task_runs[0]['run_kind']='capture';self.file_reads=[];self.fail_file=False
        self.capture=dict(available=True,message='仅展示脱敏索引',claude_code_version='2.1.293',claude_effort_level='high',permission_mode='bypassPermissions',index=dict(total_flows=45,entries=[dict(flow_id=f'flow-{i}',client_connection_id='client-1',request=dict(method='POST',host='api.example.test',path='/v1/messages',body_bytes=0),response=dict(status=200,body_bytes=200),capture_state='complete') for i in range(45)]),files=[dict(path='capture_index.json',size=100),dict(path='tls_clienthello.jsonl',size=200),dict(path='raw-body.bin',size=1024)],tls_clienthello=dict(count_exact=True,total_records=1,entries=[dict(sni='api.example.test',ja3=dict(string=None,md5=None),unexpected_secret='禁止展示的内部字段')]))
    async def route(self,route):
        """隔离两类抓包入口并记录预览请求。@param route 请求。@return 无。"""
        url=urlsplit(route.request.url);path=url.path
        if '/capture' in path and path.startswith('/runtime/api/'):
            if 'path' in parse_qs(url.query):
                selected=parse_qs(url.query)['path'][0];self.file_reads.append((path,selected))
                if self.fail_file:return await self.respond(route,{'detail':'文件预览暂不可用'},503)
                return await self.respond(route,{'public_preview':'<img src=x onerror="window.captureInjected=1">','path':selected})
            if path.endswith('/capture'):return await self.respond(route,self.capture)
        return await super().route(route)


async def main():
    """验证共享组件与真实按钮，覆盖失败重试、刷新和三种视口。@return 无。"""
    fixture=CaptureFixture();errors=[];out=ROOT/'.deploy/frontend-sidebar-refresh/capture-deep';out.mkdir(parents=True,exist_ok=True)
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/tasks?tab=projects');f=page.locator('.task-runtime');await expect(f.locator('#projects-capture')).to_be_enabled();await f.locator('#projects-capture').click();workspace=f.locator('.capture-workspace');await expect(workspace.locator('.work-table tbody tr')).to_have_count(20);await workspace.get_by_role('button',name='下一页',exact=True).click();await expect(workspace.locator('.work-table')).to_contain_text('flow-20');await workspace.get_by_role('button',name='下一页',exact=True).click();await expect(workspace.locator('.work-table tbody tr')).to_have_count(5);await workspace.get_by_role('button',name='查看',exact=True).last.click();await expect(workspace.locator('.work-log:visible')).to_contain_text('flow-44');await page.screenshot(animations='disabled',path=str(out/'index-1440.png'))
            await workspace.get_by_role('tab',name='采集文件',exact=True).click();assert await workspace.locator('.work-file').filter(has_text='raw-body.bin').get_by_role('button').is_disabled();row=workspace.locator('.work-file').filter(has_text='capture_index.json');await row.get_by_role('button',name='预览',exact=True).click();await expect(workspace.locator('.capture-file-preview')).to_contain_text('public_preview');assert fixture.file_reads[-1][0].endswith('/capture/file');assert await page.evaluate('()=>window.captureInjected===undefined')
            fixture.fail_file=True;await workspace.locator('.work-file').filter(has_text='tls_clienthello.jsonl').get_by_role('button',name='预览',exact=True).click();await expect(workspace.get_by_role('alert')).to_contain_text('文件预览暂不可用');fixture.fail_file=False;await workspace.get_by_role('button',name='重试',exact=True).click();await expect(workspace.locator('.capture-file-preview pre')).to_contain_text('tls_clienthello.jsonl');await f.locator('#work-capture-refresh').click();await expect(workspace.get_by_role('tab',name='采集文件',exact=True)).to_have_attribute('aria-selected','true');await expect(workspace.locator('.capture-file-preview pre')).to_contain_text('tls_clienthello.jsonl')
            await workspace.get_by_role('tab',name='TLS 握手',exact=True).click();await workspace.locator('.capture-tls-entry summary').click();await expect(workspace.locator('.capture-tls-entry')).to_contain_text('api.example.test');await expect(workspace).not_to_contain_text('禁止展示的内部字段')
            for width in [1440,720,390]:
                await page.set_viewport_size({'width':width,'height':1000});assert await workspace.evaluate('e=>e.scrollWidth<=e.clientWidth');await page.screenshot(animations='disabled',path=str(out/f'tls-{width}.png'))
            await f.get_by_role('button',name='关闭抓包详情',exact=True).click();await expect(workspace).to_have_count(0);await page.set_viewport_size({'width':1440,'height':1000});await page.goto(BASE+'/tasks?tab=runs');await f.locator('[data-detail]').first.click();await page.get_by_role('tab',name='抓包',exact=True).click();run_workspace=page.locator('.capture-workspace');await expect(run_workspace).to_be_visible();await run_workspace.get_by_role('tab',name='采集文件',exact=True).click();await run_workspace.locator('.work-file').filter(has_text='capture_index.json').get_by_role('button',name='预览',exact=True).click();await expect(run_workspace.locator('.capture-file-preview')).to_contain_text('public_preview');assert '/runs/' in fixture.file_reads[-1][0];assert not errors,errors;print('工程及运行复用抓包组件、45条索引分页、文件白名单、读取重试、刷新草稿、TLS白名单和三种宽度通过');await browser.close()
    finally:fixture.fixture.doCleanups()


if __name__=='__main__':asyncio.run(main())
