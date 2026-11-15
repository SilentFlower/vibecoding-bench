"""验证最新宽屏铺满与统一交互指针；只使用合成管理接口。"""
import asyncio,json
from playwright.async_api import async_playwright,expect
from verify_remaining_pages import RemainingPagesFixture
from verify_environment_ui import ROOT,BASE


async def main():
    """核对各分辨率的边界、四列卡片及可点击元素指针。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/all-pages';out.mkdir(parents=True,exist_ok=True)
    fixture=RemainingPagesFixture();errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':2560,'height':1440});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));await page.goto(BASE+'/');await expect(page.locator('.account-card')).to_have_count(12)
        dimensions=[]
        for width in [1280,1680,1920,2560,3440]:
            await page.set_viewport_size({'width':width,'height':1440});value=await page.evaluate('''()=>{const sidebar=document.querySelector('.console-sidebar').getBoundingClientRect(),grid=document.querySelector('.account-card-grid').getBoundingClientRect();return {width:innerWidth,sidebarLeft:sidebar.left,right:innerWidth-grid.right,columns:getComputedStyle(document.querySelector('.account-card-grid')).gridTemplateColumns.split(' ').length,overflow:document.documentElement.scrollWidth>innerWidth}}''');dimensions.append(value);assert value['sidebarLeft']==0,value;assert abs(value['right']-40)<=1,value;assert not value['overflow'],value
            if width>=1680:assert value['columns']==4,value
        await page.screenshot(path=str(out/'accounts-wide-3440.png'))
        cursors={}
        for name,selector in [('主按钮','[data-slot=button][data-variant=default]'),('授权按钮','.account-authorize-button'),('筛选按钮','.account-filter-tabs button'),('账号名称','.account-identity-text'),('卡片操作','.account-card-actions button'),('用量气泡','.fui-info-trigger'),('状态开关','.account-status-switch'),('更新','.brand-update'),('侧栏折叠','.desktop-sidebar-toggle')]:
            locator=page.locator(selector).first;await locator.hover();cursor=await locator.evaluate('e=>getComputedStyle(e).cursor');cursors[name]=cursor;assert cursor=='pointer',(name,cursor)
        await page.goto(BASE+'/requests');disabled=page.get_by_role('button',name='上一页',exact=True);await expect(disabled).to_be_disabled();await expect(disabled).to_have_css('cursor','not-allowed')
        await page.goto(BASE+'/tasks');frame=page.locator('.task-runtime');await expect(frame.locator('[data-cli-settings]')).to_be_visible();await expect(frame.locator('[data-cli-settings]')).to_have_css('cursor','pointer')
        assert not errors,errors
        (out/'viewport-interactions.json').write_text(json.dumps({'passed':True,'dimensions':dimensions,'cursors':cursors,'errors':errors},ensure_ascii=False,indent=2));print(json.dumps({'passed':True,'dimensions':dimensions,'cursors':cursors},ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
