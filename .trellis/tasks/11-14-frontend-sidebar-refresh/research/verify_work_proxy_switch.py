"""验证任务账号独立切换代理的草稿、同步和维护边界。"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright,expect

async def main():
    """运行本地代理切换流程并保留截图。@return 无。"""
    out=Path('.deploy/frontend-sidebar-refresh/concept')
    async with async_playwright() as p:
        browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1280,'height':1000});errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(Path('doc/design/flower2api-concept.html').resolve().as_uri()+'#tasks')
        card=page.locator('[data-work-account-card="102"]');dialog=page.locator('#action-dialog')
        async def choose(name):
            await dialog.get_by_role('combobox',name='代理线路',exact=True).click()
            await page.get_by_role('option',name=name,exact=True).click()
        await card.locator('[data-work-proxy-switch]').click();await expect(dialog).to_contain_text('同步更新')
        await choose('美国工作线路');await expect(dialog.locator('[data-work-proxy-candidate]')).to_contain_text('198.51.100.42')
        await dialog.get_by_role('button',name='取消',exact=True).click()
        assert await page.evaluate('accounts[0].proxyId===1&&workAccounts[1].proxyId===1')
        await card.locator('[data-work-proxy-switch]').click();await choose('美国工作线路')
        await dialog.get_by_role('button',name='保存并切换',exact=True).click();await expect(card).to_contain_text('美国工作线路')
        assert await page.evaluate('accounts[0].proxyId===2&&workAccounts[1].proxyId===2&&accounts[1].proxyId===1')
        # 网关处变更后，任务卡片读取权威选择。
        await page.evaluate('accounts[0].proxyId=null;repaintWork()');await expect(card).to_contain_text('直连')
        await card.locator('[data-work-proxy-switch]').click();await expect(dialog.locator('[name="work_proxy_id"]')).to_have_value('')
        await choose('新加坡主线路');await page.evaluate('accounts[0].proxyId=3')
        await dialog.get_by_role('button',name='保存并切换',exact=True).click();await expect(dialog.locator('.work-form-error')).to_contain_text('已变化')
        await page.keyboard.press('Escape')
        # 活动账号维护门禁和未关联账号的独立选择。
        await page.locator('[data-work-proxy-switch="101"]').click();await choose('美国工作线路')
        await dialog.get_by_role('button',name='保存并切换',exact=True).click();await expect(dialog.locator('.work-form-error')).to_contain_text('任务正在执行')
        assert await page.evaluate('accounts[1].proxyId===1');await page.keyboard.press('Escape')
        await page.locator('[data-work-proxy-switch="103"]').click();await choose('新加坡主线路')
        await dialog.get_by_role('button',name='保存并切换',exact=True).click()
        assert await page.evaluate('workAccounts[2].proxyId===1&&accounts[2].proxyId===2')
        await page.reload()
        for width in [1280,390]:
            await page.set_viewport_size({'width':width,'height':1000})
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await card.screenshot(path=str(out/f'work-proxy-switch-card-{width}.png'))
            await card.locator('[data-work-proxy-switch]').click()
            assert await dialog.evaluate('node=>node.scrollWidth<=node.clientWidth+1')
            await page.screenshot(path=str(out/f'work-proxy-switch-{width}.png'))
            await page.keyboard.press('Escape')
        assert not errors,errors
        result={'status':'passed','errors':errors,'checks':['取消不保存','任务和网关一致','反向网关权威读取','原配置变化阻断','活动任务维护门禁','未绑定账号独立切换','桌面和390px']}
        (out/'work-proxy-switch-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(result);await browser.close()

if __name__=='__main__':asyncio.run(main())
