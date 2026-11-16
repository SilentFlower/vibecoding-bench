"""核对系统更新深层排版、说明展开与安装取消边界。"""
import asyncio,json
from playwright.async_api import async_playwright,expect
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import ROOT,BASE


async def main():
    """对比同一浏览器中的原型控件，并验证真实维护入口。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/update-deep';out.mkdir(parents=True,exist_ok=True);fixture=WorkspaceFixture();fixture.releases[0]['changes']='平台版本：v1.0.1\n\n账号管理\n用量与状态集中呈现。\n\n任务工作区\n保留执行与交付入口。\n\n维护反馈\n<img src=x onerror="window.releaseInjected=1">';errors=[];differences={}
    async with async_playwright() as p:
        browser=await p.chromium.launch();ref=await browser.new_page(viewport={'width':1440,'height':1000});await ref.goto((ROOT/'doc/design/flower2api-concept.html').as_uri());await ref.locator('[data-action=updates]').click();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE);await page.locator('.console-sidebar .brand-update').click();await expect(page.locator('.approved-change-item')).to_have_count(3);await page.evaluate('document.fonts.ready');await ref.evaluate('document.fonts.ready')
        keys=['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','color','padding','borderRadius','gap'];read='(e)=>Object.fromEntries('+json.dumps(keys)+'.map(k=>[k,getComputedStyle(e)[k]]))'
        pairs=[('#update-dialog .dialog-head h2','.approved-update-head h2'),('#update-dialog .dialog-head p','.approved-update-head p'),('#update-body','.approved-update-scroll'),('.update-banner','.approved-update-banner'),('.version-large','.approved-version'),('.update-banner h2','.approved-update-banner h2'),('.update-banner .eyebrow','.approved-update-banner .eyebrow'),('.section-title','.approved-section-title'),('.change-item h3','.approved-change-item h3'),('.change-item p','.approved-change-item p')]
        for source,actual in pairs:
            expected=await ref.locator(source).first.evaluate(read);observed=await page.locator(actual).first.evaluate(read);differences[source]={key:[expected[key],observed[key]] for key in keys if expected[key]!=observed[key]}
        (out/'styles.json').write_text(json.dumps(differences,ensure_ascii=False,indent=2));assert all(not value for value in differences.values()),differences
        await page.get_by_role('button',name='查看完整发布说明',exact=True).click();await expect(page.locator('[data-release-details]')).to_have_count(1);await expect(page.locator('[data-release-details]')).to_contain_text('<img src=x');assert await page.evaluate('window.releaseInjected===undefined');await page.get_by_role('button',name='收起完整发布说明',exact=True).click();await expect(page.locator('[data-release-details]')).to_have_count(0);await expect(page.locator('details.approved-maintenance')).not_to_have_attribute('open','')
        await page.get_by_role('button',name='查看更新计划',exact=True).click();await expect(page.locator('.update-page>dialog')).to_be_visible();await page.locator('.update-page>dialog').get_by_role('button',name='取消',exact=True).click();assert all(write['path']=='/runtime/api/system-updates/check' for write in fixture.writes),fixture.writes
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});panel=page.locator('.approved-update-dialog');assert await panel.evaluate('e=>e.scrollWidth<=e.clientWidth');await page.screenshot(animations='disabled',path=str(out/f'updates-{width}.png'))
        await page.get_by_role('button',name='关闭更新面板').click();assert not errors,errors;print(json.dumps({'passed':True,'sampled_controls':len(pairs),'style_differences':0,'checks':['发布摘要真实文本','完整说明展开与收起','文本转义','安装计划取消零写入','1440/720/390px'],'errors':errors},ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
