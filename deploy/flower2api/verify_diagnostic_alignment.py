"""逐控件对齐账号环境诊断摘要与底部操作，并核对代理按钮状态。"""
import asyncio,json
from playwright.async_api import async_playwright,expect
from verify_workspace_stability import StabilityFixture
from verify_environment_ui import ROOT,BASE


async def main():
    """验证原型实际样式、技术详情可达性及操作按钮悬停。@return 无。"""
    fixture=StabilityFixture();errors=[];out=ROOT/'.deploy/frontend-sidebar-refresh/diagnostic-alignment';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();ref=await browser.new_page(viewport={'width':1440,'height':1000});await ref.goto((ROOT/'doc/design/flower2api-concept.html').as_uri());await ref.evaluate("selected=accounts[0].id;detail='diagnostics';renderDetail();document.querySelector('#account-drawer').showModal()");context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/proxies');row=page.locator('[data-proxy-id=proxy-1]');buttons=row.locator('.proxy-row-actions button');await expect(buttons).to_have_count(3)
        for button in await buttons.all():
            assert await button.evaluate("e=>getComputedStyle(e).cursor")=='pointer';assert await button.evaluate("e=>getComputedStyle(e).fontSize")=='12px';assert await button.locator('svg').count()==1
        delete=row.get_by_role('button',name='删除',exact=True);await delete.hover();await page.wait_for_timeout(200);assert await delete.evaluate("e=>getComputedStyle(e).backgroundColor")=='rgb(253, 240, 243)'
        await row.locator('.proxy-user-chips button').click();workspace=page.locator('.account-workspace');await workspace.locator('.account-workspace-tabs').get_by_role('button',name='环境与诊断').click();await expect(workspace.locator('.account-diagnostic-summary')).to_contain_text('就绪');await page.evaluate('document.fonts.ready');await ref.evaluate('document.fonts.ready');keys=['fontFamily','fontSize','fontWeight','lineHeight','color','padding','margin','gap','borderRadius'];read='e=>Object.fromEntries('+json.dumps(keys)+'.map(k=>[k,getComputedStyle(e)[k]]))';pairs=[('#drawer-body','.account-diagnostics'),('#drawer-body .kv','.account-diagnostic-summary>div'),('#drawer-body .kv span','.account-diagnostic-summary dt'),('#drawer-body .kv strong','.account-diagnostic-summary dd'),('#drawer-body .buttons','.account-diagnostic-actions'),('#drawer-body .btn','.account-diagnostic-actions [data-slot=button]')];differences={}
        for source,actual in pairs:
            expected=await ref.locator(source).first.evaluate(read);observed=await page.locator(actual).first.evaluate(read);differences[source]={key:[expected[key],observed[key]] for key in keys if expected[key]!=observed[key]}
        (out/'styles.json').write_text(json.dumps(differences,ensure_ascii=False,indent=2));assert all(not v for v in differences.values()),differences;await workspace.locator('.account-diagnostic-technical>summary').click();await expect(workspace.locator('.account-detail-scroll')).to_be_visible();await workspace.locator('.account-diagnostic-technical>summary').click()
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});assert await workspace.evaluate('e=>e.scrollWidth<=e.clientWidth');await page.screenshot(animations='disabled',path=str(out/f'diagnostics-{width}.png'))
        assert not errors,errors;assert not fixture.writes;print(json.dumps({'passed':True,'style_differences':0,'sampled_controls':len(pairs),'checks':['摘要在上操作在下','三个统一操作入口','技术详情保留','代理按钮图标/指针/删除悬停','1440/720/390px'],'errors':errors},ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
