"""验证产物预览的真实读取、空值、二进制、大文件和切换竞态。"""
import asyncio,json
from urllib.parse import urlsplit,parse_qs
from playwright.async_api import async_playwright,expect
from verify_run_detail_design import RunDetailFixture
from verify_environment_ui import ROOT,BASE


class PreviewFixture(RunDetailFixture):
    """提供多种产物回执并允许有界延迟。"""
    def __init__(self):
        """准备合成文本与失败开关。@return 无。"""
        super().__init__();self.fail=False
    async def route(self,route):
        """拦截产物读取。@param route 请求。@return 无。"""
        parsed=urlsplit(route.request.url)
        if parsed.path.endswith('/synthetic-run/files'):
            return await self.respond(route,[{'path':path,'type':'dir' if path=='src' else 'file','size':0 if path=='empty.txt' else 128} for path in ['src','a.py','b.py','empty.txt','binary.bin','large.txt','missing.txt']])
        if parsed.path.endswith('/synthetic-run/file'):
            self.reads.append(parsed.path);path=parse_qs(parsed.query)['path'][0]
            if path=='a.py':await asyncio.sleep(.3)
            if path=='missing.txt' and self.fail:return await self.respond(route,{'detail':'合成文件暂时不可读取'},404)
            return await self.respond(route,{'path':path,'text':'' if path in ['empty.txt','binary.bin'] else '<script id="preview-unsafe">文本产物</script>'+path,'binary':path=='binary.bin','truncated':path=='large.txt'})
        return await super().route(route)


async def main():
    """所有状态经实际组件和同源JSON接口验证。@return 无。"""
    fixture=PreviewFixture();errors=[];out=ROOT/'.deploy/frontend-sidebar-refresh/run-detail';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));await page.goto(BASE+'/tasks?tab=runs');frame=page.locator('.task-runtime');await frame.get_by_role('button',name='详情',exact=True).first.click();modal=page.locator('.approved-run-dialog');await modal.get_by_role('tab',name='产物文件').click();await expect(modal.locator('.work-file-preview')).to_contain_text('a.py')
        await expect(modal.get_by_role('button',name='src 目录')).to_be_disabled();await modal.get_by_role('button',name='a.py').click();await modal.get_by_role('button',name='b.py').click();await expect(modal.locator('.work-file-preview')).to_contain_text('b.py');await page.wait_for_timeout(400);await expect(modal.locator('.work-file-preview')).to_contain_text('b.py');await expect(page.locator('#preview-unsafe')).to_have_count(0)
        await modal.get_by_role('button',name='empty.txt').click();await expect(modal.locator('.work-file-preview')).to_have_text('（空文件）')
        await modal.get_by_role('button',name='binary.bin').click();await expect(modal.locator('.run-file-placeholder')).to_contain_text('二进制文件')
        await modal.get_by_role('button',name='large.txt').click();await expect(modal.locator('.run-file-truncated')).to_contain_text('64 KiB')
        fixture.fail=True;await modal.get_by_role('button',name='missing.txt').click();await expect(modal.get_by_role('alert')).to_contain_text('暂时不可读取');fixture.fail=False;await modal.get_by_role('button',name='重新读取').click();await expect(modal.locator('.work-file-preview')).to_contain_text('missing.txt')
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});assert await modal.evaluate('e=>e.scrollWidth<=e.clientWidth');await page.screenshot(animations='disabled',path=str(out/f'files-{width}.png'))
        await modal.get_by_role('button',name='关闭',exact=True).click();count=len(fixture.reads);await page.wait_for_timeout(2800);assert len(fixture.reads)==count;assert not errors,errors;print('产物预览：文本转义、目录、空文件、二进制、截断、失败重试、切换竞态、关闭清理与三档宽度通过');await browser.close()


if __name__=='__main__':asyncio.run(main())
