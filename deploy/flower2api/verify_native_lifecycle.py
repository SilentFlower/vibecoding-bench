"""验证原生任务路由的身份、键盘、历史和订阅释放。"""
import asyncio,json
from playwright.async_api import async_playwright,expect
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import BASE


async def main():
    """离页不会遗留任务流，初始焦点和侧栏焦点保持模块快捷键。@return 无。"""
    errors=[];fixture=WorkspaceFixture()
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route)
        await context.add_init_script("""localStorage.setItem('claude-code-gateway_auth','synthetic-only');window.liveSources=new Set();const NativeSource=window.EventSource;window.EventSource=class extends NativeSource{constructor(...args){super(...args);liveSources.add(this)}close(){super.close();liveSources.delete(this)}};""")
        page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/tasks');root=page.locator('.task-runtime');await expect(root.locator('.work-account')).to_have_count(1);await expect(page.locator('iframe')).to_have_count(0);identity=await root.element_handle();await page.keyboard.press('4');await expect(page).to_have_url(BASE+'/tasks?tab=tasks');await root.locator('[data-tab=projects]').click();await expect(root.locator('#projects-account')).to_be_visible();await page.wait_for_function('liveSources.size>0');await root.locator('[data-tab=topics]').click();await page.go_back();await expect(page).to_have_url(BASE+'/tasks?tab=projects&account=1');assert await identity.evaluate('node=>node===document.querySelector(".task-runtime")');await expect(page.locator('html')).to_have_attribute('data-ui-scheme','light');await page.get_by_role('button',name='收起侧边栏',exact=True).click();assert await identity.evaluate('node=>node===document.querySelector(".task-runtime")');await page.get_by_role('link',name='请求记录',exact=True).first.click();await expect(root).to_have_count(0);await page.wait_for_function('liveSources.size===0');await page.keyboard.press('4');await expect(page).to_have_url(BASE+'/requests');assert not errors,errors;print(json.dumps({'passed':True,'checks':['无iframe','初始焦点快捷键','连续历史','模块根保留','任务宿主固定浅色','侧栏折叠保留模块','离页SSE释放','离页键盘监听释放'],'errors':errors},ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
