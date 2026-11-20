"""核对账号环境诊断页签的摘要、操作与技术详情布局，并核对代理按钮状态。诊断页签设计稿未画，外观由 verify_account_page_design.py 截图目视确认。"""
import asyncio,json
from playwright.async_api import async_playwright,expect
from verify_workspace_stability import StabilityFixture
from verify_environment_ui import ROOT,BASE


async def main():
    """验证诊断摘要在上、三个操作在下、技术详情默认收起且可达，以及代理操作按钮悬停。@return 无。"""
    fixture=StabilityFixture();errors=[];out=ROOT/'.deploy/frontend-sidebar-refresh/diagnostic-alignment';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/proxies');row=page.locator('[data-proxy-id=proxy-1]');buttons=row.locator('.proxy-row-actions button');await expect(buttons).to_have_count(3)
        # 第二版：行操作为小号按钮，字号与删除悬停底色取 token 在当前主题下的实际渲染值，不写死色值。
        probe="(e,[prop,value])=>{const i=document.createElement('i');i.style[prop]=value;e.append(i);const v=getComputedStyle(i)[prop];i.remove();return v}"
        small=await row.evaluate(probe,['fontSize','var(--ui-font-size-sm)']);danger=await row.evaluate(probe,['backgroundColor','var(--ui-color-danger-bg)'])
        for button in await buttons.all():
            assert await button.evaluate("e=>getComputedStyle(e).cursor")=='pointer';assert await button.evaluate("e=>getComputedStyle(e).fontSize")==small;assert await button.locator('svg').count()==1
        delete=row.get_by_role('button',name='删除',exact=True);await delete.hover();await page.wait_for_timeout(200);assert await delete.evaluate("e=>getComputedStyle(e).backgroundColor")==danger
        await row.locator('.proxy-user-chips button').click();workspace=page.locator('.account-workspace');await workspace.locator('.account-workspace-tabs').get_by_role('radio',name='环境与诊断').click();summary=workspace.locator('.account-diagnostic-summary');await expect(summary).to_contain_text('就绪')
        # 第二版：摘要为浅灰信息块内两列键值，三个跳转在其下方，技术详情默认收起（旧原型逐项比对已移除）。
        actions=workspace.locator('.account-diagnostic-actions');await expect(actions.locator('[data-slot=button]')).to_have_count(3);assert await actions.evaluate('e=>e.getBoundingClientRect().top')>await summary.evaluate('e=>e.getBoundingClientRect().bottom')
        assert await summary.locator(':scope>div').count()==4;await expect(workspace.locator('.account-diagnostic-technical')).not_to_have_attribute('open','')
        await workspace.locator('.account-diagnostic-technical>summary').click();await expect(workspace.locator('.account-detail-scroll')).to_be_visible();await workspace.locator('.account-diagnostic-technical>summary').click()
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});assert await workspace.evaluate('e=>e.scrollWidth<=e.clientWidth');await page.screenshot(animations='disabled',path=str(out/f'diagnostics-{width}.png'))
        assert not errors,errors;assert not fixture.writes;print(json.dumps({'passed':True,'checks':['摘要在上操作在下','三个统一操作入口','技术详情保留','代理按钮图标/指针/删除悬停','1440/720/390px'],'errors':errors},ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
