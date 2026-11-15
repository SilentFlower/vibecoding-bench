"""验证运行详情的分区、固定页签、状态语义及窄屏表现。"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright,expect

async def main():
    """使用本地示例验证详情四页签及样式隔离。@return 无。"""
    out=Path('.deploy/frontend-sidebar-refresh/concept')
    async with async_playwright() as p:
        browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(Path('doc/design/flower2api-concept.html').resolve().as_uri()+'#tasks?tab=runs')
        await page.locator('[data-work-run="run-demo-038"]').first.click();dialog=page.locator('#action-dialog')
        await expect(dialog.locator('.run-stat-grid article')).to_have_count(4)
        await expect(dialog.locator('.run-stat-grid')).to_contain_text('待结束')
        await expect(dialog.locator('.run-followups>div')).to_have_count(2)
        for width in [1440,1280,720,390]:
            await page.set_viewport_size({'width':width,'height':900})
            for tab in ['overview','logs','files','capture']:
                await dialog.locator('[data-work-detail-tab="'+tab+'"]').click()
                await expect(dialog.locator('[data-work-detail-panel="'+tab+'"]').first).to_be_visible()
                assert await dialog.evaluate('el=>el.scrollWidth<=el.clientWidth+1'),(width,tab)
                if tab=='files':
                    await dialog.locator('[data-work-file="tests/test_validation.py"]').click()
                    await expect(dialog.locator('.work-file-preview')).to_be_visible()
                    await expect(dialog.locator('.run-file-placeholder')).not_to_be_visible()
                    await expect(dialog.locator('[data-run-file-label]')).to_have_text('tests/test_validation.py')
                await page.screenshot(path=str(out/f'run-detail-{tab}-{width}.png'))
            await dialog.locator('[data-work-detail-tab="overview"]').click()
            heading=await dialog.locator('.dialog-head').bounding_box();tabs=await dialog.locator('.run-detail-tabs').bounding_box()
            await dialog.locator('.run-detail-scroll').evaluate('el=>el.scrollTop=el.scrollHeight')
            assert heading['y']==(await dialog.locator('.dialog-head').bounding_box())['y']
            assert tabs['y']==(await dialog.locator('.run-detail-tabs').bounding_box())['y']
        await dialog.locator('[data-work-detail-tab="overview"]').focus();await page.keyboard.press('ArrowRight')
        await expect(dialog.locator('[data-work-detail-tab="logs"]')).to_have_attribute('aria-selected','true')
        await page.keyboard.press('Escape')
        await page.locator('[data-work-run="run-demo-037"]').first.click();await expect(dialog.locator('.run-stat-grid article').last.locator('strong')).to_have_text('0');await page.keyboard.press('Escape')
        await page.locator('[data-work-run="run-demo-036"]').first.click();await expect(dialog.locator('.run-stat-grid article').first).to_contain_text('未采集');await expect(dialog).to_contain_text('等待额度恢复');await page.keyboard.press('Escape')
        # 编辑题库不能改变历史运行需求。
        await page.evaluate("workTopics[0].description='编辑后的题库内容'")
        await page.locator('[data-work-run="run-demo-038"]').first.click();await expect(dialog.locator('.run-prompt')).not_to_contain_text('编辑后的题库内容');await page.keyboard.press('Escape')
        await page.evaluate("taskTab='accounts';navigate('tasks');configureWorkAccount(102)")
        assert not await dialog.evaluate("el=>el.classList.contains('work-run-dialog')")
        assert not errors,errors
        result={'status':'passed','viewports':[1440,1280,720,390],'checks':['四页签','文件选择与预览','固定标题及页签','方向键操作','零值和未观测','执行中退出码','冻结需求','其他弹窗隔离'],'errors':errors}
        (out/'run-detail-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(result);await browser.close()

if __name__=='__main__':asyncio.run(main())
