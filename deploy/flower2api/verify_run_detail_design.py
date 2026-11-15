"""验证真实运行详情布局与原轮询生命周期，全部使用合成接口。"""
import asyncio
import json
from urllib.parse import urlsplit
from playwright.async_api import async_playwright, expect
from verify_interaction_parity import InteractionFixture
from verify_environment_ui import BASE, ROOT


class RunDetailFixture(InteractionFixture):
    """提供运行状态、日志、产物与观测。"""

    def __init__(self):
        """建立明确的合成运行。@return 无。"""
        super().__init__()
        self.task_runs=[dict(id='synthetic-run',task_id=1,account_id=1,status='running',run_kind='normal',exit_code=None,claude_code_version='2.1.293',claude_effort_level='high',execution_model='synthetic-model',prompt='完善输入校验，覆盖边界场景。',followups={})]
        self.reads=[]

    async def route(self, route):
        """返回有界合成观测。@param route 请求。@return 无。"""
        path=urlsplit(route.request.url).path
        if path.startswith('/runtime/api/runs/synthetic-run'):
            self.reads.append(path)
            if path.endswith('/transcript'):return await route.fulfill(content_type='text/plain',body='开始执行\n正在验证输入\n等待下一次观测')
            if path.endswith('/file'):return await self.respond(route,dict(path='src/main.py',text='print("合成产物预览")',truncated=False,binary=False))
            if path.endswith('/stats'):return await self.respond(route,dict(available=True,usage_available=True,tokens_in=18420,tokens_out=3260,requests=12))
            if path.endswith('/files'):return await self.respond(route,[dict(type='file',path='src/main.py',size=2048)])
            return await self.respond(route,self.task_runs[0])
        if path=='/runtime/api/tasks':return await self.respond(route,[dict(id=1,topic_no=1,title='输入校验与异常处理',account_id=1,repeat_n=1,timeout_sec=600)])
        return await super().route(route)


async def main():
    """检查页签、固定区域、数据与关闭清理。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/run-detail';out.mkdir(parents=True,exist_ok=True)
    fixture=RunDetailFixture();errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));await page.goto(BASE+'/tasks?tab=runs')
        frame=page.locator('.task-runtime');await expect(frame.locator('#runs-body')).to_be_visible();await frame.get_by_role('button',name='详情',exact=True).first.click()
        modal=page.locator('.approved-run-dialog');await expect(modal).to_be_visible();await expect(modal).to_contain_text('输入校验与异常处理');await expect(modal.locator('.run-stat-grid article').nth(3).locator('strong')).to_have_text('待结束');await expect(modal.locator('.run-stat-grid article')).to_have_count(4)
        await modal.get_by_role('tab',name='日志',exact=True).click();await expect(modal.locator('.run-log-panel')).to_contain_text('正在验证输入');await modal.get_by_role('tab',name='日志',exact=True).press('ArrowRight');await expect(modal.get_by_role('tab',name='产物文件')).to_have_attribute('aria-selected','true');await expect(modal.locator('.run-files')).to_contain_text('src/main.py');await expect(modal.locator('.work-file-preview')).to_contain_text('合成产物预览')
        await modal.get_by_role('tab',name='抓包',exact=True).click();await expect(modal).to_contain_text('本次运行未启用抓包');await modal.get_by_role('tab',name='概览',exact=True).click()
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});await expect(modal).to_have_css('width',f'{min(900,width-28)}px');await expect(modal).to_have_css('height','740px');await page.screenshot(path=str(out/f'run-{width}.png'))
            assert await modal.evaluate('e=>e.scrollWidth<=e.clientWidth+1'),width
            header=await modal.locator('[data-slot=dialog-header]').bounding_box();await modal.locator('.run-detail-scroll').evaluate('e=>e.scrollTop=500');assert (await modal.locator('[data-slot=dialog-header]').bounding_box())['y']==header['y'];await modal.locator('.run-detail-scroll').evaluate('e=>e.scrollTop=0')
        await modal.get_by_role('button',name='关闭',exact=True).click();await expect(modal).to_be_hidden();count=len(fixture.reads);await page.wait_for_timeout(2800);assert len(fixture.reads)==count
        assert not errors,errors
        result=dict(passed=True,checks=['四张统计卡片','运行中退出码待结束','需求与配置分区','四页签与方向键','日志和文件更新','未抓包空态','标题固定及正文滚动','关闭停止轮询','1440/720/390px'],errors=errors)
        (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
