"""对照已确认原型验证正式账号与系统更新的结构及交互。"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, expect
from verify_accounts_design import AccountDesignFixture
from verify_environment_ui import BASE, ROOT


async def main():
    """同视口核对定稿与正式构建，补齐服务端搜索和工作区生命周期证据。@return 无。"""
    out = ROOT / '.deploy/frontend-sidebar-refresh/parity'
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        reference = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        await reference.goto((ROOT/'doc/design/flower2api-concept.html').as_uri())
        await reference.locator('[data-account-action="edit"]').first.click()
        ref_sections = await reference.locator('#account-drawer .account-form-section > h3').all_text_contents()
        ref_tabs = await reference.locator('#account-drawer [data-detail]').all_text_contents()
        ref_box = await reference.locator('#account-drawer').bounding_box()
        await reference.screenshot(path=str(out/'reference-editor.png'))
        await reference.keyboard.press('Escape')
        await reference.evaluate('actions.updates()')
        ref_update_width = (await reference.locator('#update-dialog').bounding_box())['width']
        await reference.screenshot(path=str(out/'reference-updates.png'))
        context = await browser.new_context(viewport={'width':1440,'height':1000})
        fixture = AccountDesignFixture()
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page(); errors=[]
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(BASE+'/')
        await expect(page.locator('.console-metrics')).to_have_count(0)
        await expect(page.locator('.account-filter-tabs button')).to_have_count(4)
        await page.get_by_role('searchbox', name='搜索账号', exact=True).fill('design13@')
        await expect(page.locator('.account-card')).to_have_count(1)
        await expect(page.locator('.account-card')).to_contain_text('正式账号 13')
        assert fixture.account_reads[-1]==1
        await page.get_by_role('button',name='清空搜索账号').click()
        await expect(page.locator('.account-card')).to_have_count(12)
        await page.get_by_role('button',name='已停用',exact=False).first.click()
        await expect(page.locator('.account-card')).to_have_count(0)
        await page.get_by_role('button',name='全部账号',exact=False).click()
        await expect(page.locator('.account-card')).to_have_count(12)
        card=page.locator('.account-card').first
        await card.get_by_role('button',name='编辑',exact=True).click()
        workspace=page.locator('.account-workspace')
        await expect(workspace).to_have_css('opacity','1')
        assert await workspace.locator('.account-form-section > h3').all_text_contents()==ref_sections
        assert await workspace.locator('.account-workspace-tabs button').all_text_contents()==ref_tabs
        rect=await workspace.bounding_box()
        assert abs(rect['x']-ref_box['x'])<=4 and abs(rect['width']-ref_box['width'])<=4,(rect,ref_box)
        await expect(workspace.locator('.forwarding-options input[type=radio]')).to_have_count(2)
        for label in ['Billing 模式','TTL 刷新策略']:
            await expect(workspace.get_by_role('combobox',name=label,exact=True)).to_be_visible()
        await workspace.get_by_role('spinbutton',name='并发上限',exact=True).fill('7')
        await workspace.get_by_role('button',name='概览',exact=True).click()
        await workspace.get_by_role('button',name='调度',exact=True).click()
        await expect(workspace).to_contain_text('真实提交时间轴')
        await expect(page.get_by_role('dialog')).to_have_count(1)
        await workspace.get_by_role('button',name='配置',exact=True).click()
        await expect(workspace.get_by_role('spinbutton',name='并发上限',exact=True)).to_have_value('7')
        await page.screenshot(path=str(out/'actual-editor.png'))
        await workspace.get_by_role('button',name='取消',exact=True).click()
        assert not fixture.writes
        await card.get_by_role('button',name='详情',exact=True).click()
        await workspace.get_by_role('button',name='配置',exact=True).click()
        await expect(workspace.get_by_role('spinbutton',name='并发上限',exact=True)).to_have_value('3')
        await page.keyboard.press('Escape')
        before=page.url
        await page.get_by_role('link',name='系统更新',exact=True).click()
        update=page.locator('.approved-update-dialog')
        await expect(update.locator('.approved-update-banner')).to_be_visible()
        assert page.url==before
        rect=await update.bounding_box()
        await page.screenshot(path=str(out/'actual-updates.png'))
        await update.get_by_role('button',name='查看更新计划',exact=True).click()
        confirm=update.locator('.update-page > dialog')
        await expect(confirm).to_be_visible()
        await expect(confirm.get_by_role('combobox',name='等待在途完成')).to_contain_text('1 分钟')
        await confirm.get_by_role('combobox',name='等待在途完成').click()
        await page.get_by_role('option',name='5 分钟',exact=True).click()
        await confirm.get_by_role('button',name='取消',exact=True).click()
        assert not fixture.writes
        await expect(update).to_be_visible()
        await page.keyboard.press('Escape')
        await expect(update).not_to_be_visible()
        for width in [720,390]:
            await page.set_viewport_size({'width':width,'height':900})
            await card.get_by_role('button',name='编辑',exact=True).click()
            await expect(workspace).to_have_css('opacity','1')
            rect=await workspace.bounding_box()
            assert rect['x']>=0 and rect['x']+rect['width']<=width
            assert await workspace.evaluate('e=>e.scrollWidth<=e.clientWidth+1')
            await page.screenshot(path=str(out/f'actual-editor-{width}.png'))
            await page.keyboard.press('Escape')
            await page.get_by_role('button',name='打开主导航').click()
            await page.get_by_role('link',name='系统更新',exact=True).click()
            await expect(update.locator('.approved-update-banner')).to_be_visible()
            assert await update.evaluate('e=>e.scrollWidth<=e.clientWidth+1')
            await page.screenshot(path=str(out/f'actual-updates-{width}.png'))
            await page.keyboard.press('Escape')
        assert not errors,errors
        result=dict(passed=True,sections=ref_sections,tabs=ref_tabs,reference_update_width=ref_update_width,checks=['移除旧统计区','四状态与跨页搜索','定稿分组与侧栏定位','单工作区与草稿保留/丢弃','品牌更新保持路由','分栏/计划/取消/返回','720/390px'],errors=errors)
        (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
        await browser.close()


if __name__=='__main__':
    asyncio.run(main())
