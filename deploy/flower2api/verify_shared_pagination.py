"""验证分页组件各宿主的选中对比、键盘焦点、大页数和窄屏。"""
import asyncio,json
from playwright.async_api import async_playwright,expect
from verify_page_sizes import PageFixture
from verify_environment_ui import BASE,ROOT


async def token(nav,name):
    """读取主题 token 在分页所在位置的实际渲染色，分页配色随主题变化。@param nav 分页导航。@param name token 名。@return rgb 字符串。"""
    return await nav.evaluate("(e,n)=>{const probe=document.createElement('i');probe.style.color='var('+n+')';e.append(probe);const value=getComputedStyle(probe).color;probe.remove();return value}",name)


async def verify(page,label):
    """核对真实页码与计算样式。@param page 页面或原生宿主。@param label 分页名称。@return 无。"""
    nav=page.get_by_role('navigation',name=label)
    await expect(nav).to_be_visible()
    current=nav.locator('[aria-current=page]')
    await expect(current).to_have_count(1)
    primary=await token(nav,'--ui-color-primary')
    await expect(current).to_have_css('background-color',primary)
    await expect(current).to_have_css('color',await token(nav,'--ui-color-on-primary'))
    await expect(nav.get_by_role('button',name='上一页',exact=True)).to_be_disabled()
    await nav.get_by_role('button',name='下一页',exact=True).click()
    await expect(current).to_have_text('2')
    await expect(current).to_have_css('background-color',primary)
    await expect(nav.get_by_role('button',name='第 1 页',exact=True)).to_have_css('color',await token(nav,'--ui-color-text'))


async def main():
    """覆盖七个共享入口的实际渲染和请求。@return 无。"""
    fixture=PageFixture();errors=[]
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000})
            await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
            page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack))
            for path,label in [('/', '账号列表分页'),('/proxies','代理列表分页'),('/requests','请求记录分页')]:
                await page.goto(BASE+path);await verify(page,label)
            fixture.request_rows*=20
            await page.goto(BASE+'/requests');nav=page.get_by_role('navigation',name='请求记录分页');await expect(nav.get_by_role('button',name='第 55 页',exact=True)).to_be_visible();await nav.get_by_role('button',name='第 55 页',exact=True).click();await expect(nav.locator('[aria-current=page]')).to_have_text('55');await expect(nav.get_by_role('button',name='下一页',exact=True)).to_be_disabled()
            for width in [720,390]:
                await page.set_viewport_size({'width':width,'height':1000});await nav.scroll_into_view_if_needed();assert await nav.evaluate('e=>e.getBoundingClientRect().right<=innerWidth && e.scrollWidth<=e.clientWidth');await nav.screenshot(path=str(ROOT/f'.deploy/frontend-sidebar-refresh/pagination/shared-{width}.png'))
            await page.goto(BASE+'/?account=1');workspace=page.locator('.account-workspace');await workspace.locator('.account-workspace-tabs').get_by_role('button',name='调度',exact=True).click();await verify(page,'绑定会话分页');await page.keyboard.press('Escape')
            await page.goto(BASE+'/tasks?tab=projects');frame=page.locator('.task-runtime');await frame.locator('#projects-capture').click();await verify(frame,'抓包索引分页')
            await frame.get_by_role('button',name='关闭抓包详情',exact=True).click();await page.set_viewport_size({'width':1440,'height':1000})
            for kind,label in [('history','工程记录分页'),('events','交互记录分页')]:
                await frame.locator('[data-project-pane='+('history' if kind=='history' else 'overview')+']').click()
                if kind=='events':await frame.locator('#projects-tab-events').click()
                nav=frame.get_by_role('navigation',name=label);await expect(nav).to_be_visible();await expect(nav.locator('[aria-current=page]')).to_have_css('background-color',await token(nav,'--ui-color-primary'));await expect(nav.locator('[aria-current=page]')).to_have_css('height','32px');await expect(nav.get_by_role('button',name='上一页',exact=True)).to_be_disabled();await expect(nav.get_by_role('button',name='最新一页',exact=True)).to_be_disabled()
            assert not errors,errors
            print(json.dumps({'passed':True,'checks':['七入口共享选中对比','首尾禁用','55页省略与直达','720/390px页码不溢出','抓包宿主样式'],'errors':errors},ensure_ascii=False));await browser.close()
    finally:fixture.fixture.doCleanups()


if __name__=='__main__':asyncio.run(main())
