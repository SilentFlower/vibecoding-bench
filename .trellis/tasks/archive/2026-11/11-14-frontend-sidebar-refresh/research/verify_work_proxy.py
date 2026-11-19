"""验证任务账号代理展示及授权草稿中的网络配置归属。"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, expect


async def main():
    """验证代理观测、脱敏、配置保持和响应式布局。@return 无。"""
    out=Path('.deploy/frontend-sidebar-refresh/concept')
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={'width':1280,'height':1000})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(Path('doc/design/flower2api-concept.html').resolve().as_uri()+'#tasks')
        first=page.locator('[data-work-account-card="101"]')
        for text in ['新加坡主线路','新加坡','68','America/Los_Angeles','build@example.test']:
            await expect(first).to_contain_text(text)
        await expect(page.locator('.work-login-drafts')).to_contain_text('新加坡主线路')
        await first.get_by_role('button',name='重新授权并同步').click()
        dialog=page.locator('#action-dialog')
        await expect(dialog.locator('[name="proxyId"]')).to_have_value('1')
        await expect(dialog.locator('[name="proxyId"]')).to_be_disabled()
        await expect(dialog.locator('[name="timezone"]')).to_be_disabled()
        await dialog.get_by_role('button',name='进入授权预览',exact=True).click()
        await expect(dialog).to_contain_text('新加坡主线路')
        await dialog.locator('[data-work-login-simulate]').click()
        await dialog.locator('[data-work-login-commit]').click()
        assert await page.evaluate("workAccounts[0].proxyId===1&&workAccounts[0].timezone==='America/Los_Angeles'")
        # 新账号选择直连、时区，草稿关闭恢复后继续提交。
        await page.locator('[data-work-action="create"]').click()
        await dialog.locator('[name="name"]').fill('网络配置测试')
        await dialog.get_by_role('combobox',name='代理线路',exact=True).click()
        await page.get_by_role('option',name='直连',exact=True).click()
        await dialog.get_by_role('combobox',name='环境时区',exact=True).click()
        await page.get_by_role('option',name='东京 · Asia/Tokyo',exact=True).click()
        await dialog.get_by_role('button',name='进入授权预览',exact=True).click()
        await expect(dialog).to_contain_text('直连')
        await page.keyboard.press('Escape')
        await expect(page.locator('.work-login-drafts')).to_contain_text('Asia/Tokyo')
        await page.locator('[data-work-login-resume="2"]').click()
        await dialog.locator('[data-work-login-simulate]').click()
        await dialog.locator('[data-work-login-commit]').click()
        new=page.locator('[data-work-account-card="104"]')
        await expect(new).to_contain_text('直连')
        await expect(new).to_contain_text('Asia/Tokyo')
        assert await page.evaluate('workAccounts.at(-1).proxyId===null')
        # 缺失和陈旧观测区分，原始地址中的账密不进入卡片和搜索。
        await page.evaluate("previewProxies[0].url='socks5://private-user:private-password@sg.example.test:1080';previewProxies[0].status='failed';repaintWork()")
        await first.locator('[data-work-proxy-detail]').click()
        await expect(dialog).to_contain_text('上次成功结果')
        await expect(dialog).to_contain_text('203.0.113.18')
        await expect(dialog).not_to_contain_text('private-password')
        await page.keyboard.press('Escape')
        await expect(first).to_contain_text('检测失败')
        await expect(page.locator('#work-content')).not_to_contain_text('private-password')
        await page.locator('#work-search').fill('private-user')
        await expect(page.locator('[data-work-account-card]')).to_have_count(0)
        await page.locator('#work-search').fill('203.0.113.18')
        await expect(page.locator('[data-work-account-card]')).to_have_count(2)
        await page.locator('#work-search').fill('')
        await page.evaluate("accounts[1].proxyId=999;accounts[0].proxyId=3;repaintWork()")
        await expect(first).to_contain_text('原代理已不可用')
        await expect(page.locator('[data-work-account-card="102"]')).to_contain_text('待检测')
        await expect(page.locator('[data-work-account-card="102"]')).not_to_contain_text('0 ms')
        await page.reload()
        await page.evaluate("previewProxies[0].name='一个用于验证截断展示的超长代理线路名称'.repeat(8);repaintWork()")
        for width in [1600,1280,720,390]:
            await page.set_viewport_size({'width':width,'height':1000})
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        await page.reload()
        for width in [1280,390]:
            await page.set_viewport_size({'width':width,'height':1000})
            await first.screenshot(path=str(out/f'work-account-proxy-{width}.png'))
        assert not errors,errors
        result={'status':'passed','errors':errors,'checks':['代理出口观测','邮箱与时区','绑定账号网络配置保持','草稿直连与时区保存','失败观测标注','缺失线路与待检测','地址脱敏及搜索','长线路窄屏']}
        (out/'work-proxy-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result,ensure_ascii=False))
        await browser.close()


if __name__=='__main__':
    asyncio.run(main())
