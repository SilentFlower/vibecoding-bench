"""用真实页面与合成接口验证全站入口、响应式布局及离线预览。"""
import argparse
import asyncio
import json
from pathlib import Path

from export_frontend_preview import PreviewFixture
from verify_environment_ui import BASE, ROOT


async def run(output):
    """运行桌面/窄屏入口回归。@param output 证据目录。@return 场景结果。"""
    from playwright.async_api import async_playwright, expect
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    scenes = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1280, 'height': 900})
        fixture = PreviewFixture()
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');if(!localStorage.getItem('vibebench-theme'))localStorage.setItem('vibebench-theme','light');")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width in [1280, 720, 390]:
            await page.set_viewport_size({'width': width, 'height': 900})
            # /updates 在账号页之上打开系统更新弹窗；关闭后回到账号页（地址 /）。
            await page.goto(BASE + '/updates')
            await expect(page.locator('.system-update-dialog')).to_be_visible()
            await expect(page.locator('.toolbar-page')).to_have_text('系统更新')
            await page.locator('.system-update-dialog').get_by_role('button', name='关闭', exact=True).click()
            await expect(page).to_have_url(BASE + '/')
            for label, path in [('账号', '/'), ('访问令牌', '/tokens'), ('系统设置', '/settings'), ('请求记录', '/requests'),
                    ('运行环境', '/environments'), ('任务与工程', '/tasks'), ('系统更新', '/updates')]:
                if width < 768:
                    await page.get_by_role('button', name='打开主导航', exact=True).click()
                    await expect(page.get_by_role('dialog')).to_be_visible()
                if label == '系统更新':
                    before = page.url
                    await page.get_by_role('link', name=label, exact=True).click()
                    await expect(page.locator('.system-update-dialog')).to_be_visible()
                    assert page.url == before
                    await page.locator('.system-update-dialog').get_by_role('button', name='关闭', exact=True).click()
                    await expect(page.locator('.system-update-dialog')).to_be_hidden()
                    assert page.url == before
                    await page.goto(BASE + '/updates')
                    await expect(page.locator('.system-update-dialog')).to_be_visible()
                else:
                    await page.get_by_role('link', name=label, exact=True).click()
                await expect(page).to_have_url(BASE + path)
                # 应用栏显示页面标题：账号页标题为「账号管理」，其余与导航名相同。
                await expect(page.locator('.toolbar-page')).to_have_text('账号管理' if label == '账号' else label)
                if width < 768:
                    await expect(page.locator('.mobile-navigation-panel')).to_have_count(0)
                elif label != '系统更新':
                    await expect(page.get_by_role('link', name=label, exact=True)).to_have_attribute('aria-current', 'page')
                assert await page.locator('html').evaluate('node=>node.scrollWidth<=innerWidth'), (width, label)
            scenes.append(f'{width}px 七个入口、选中态、移动抽屉和页面宽度')
            await page.goto(BASE + '/')
            await page.get_by_role('button', name='添加账号', exact=True).click()
            await expect(page.get_by_role('dialog')).to_be_visible()
            await page.keyboard.press('Escape')
            await expect(page.get_by_role('dialog')).to_have_count(0)
            await page.get_by_role('button', name='授权登录', exact=True).click()
            await expect(page.get_by_role('dialog')).to_be_visible()
            await page.keyboard.press('Escape')
            await expect(page.get_by_role('dialog')).to_have_count(0)
            card = page.locator('.resource-grid > [data-slot="card"]').first
            await card.get_by_role('button', name='详情', exact=True).click()
            await page.get_by_role('dialog').get_by_role('button',name='环境与诊断',exact=True).click()
            await page.get_by_role('dialog').locator('.account-diagnostic-technical>summary').click()
            await expect(page.get_by_role('dialog').get_by_text('画像选择方式', exact=True)).to_be_visible()
            await page.keyboard.press('Escape')
            await expect(card.get_by_role('button', name='编辑', exact=True)).to_be_visible()
            await card.get_by_role('button', name='编辑', exact=True).click()
            await expect(page.get_by_role('dialog')).to_be_visible()
            await page.keyboard.press('Escape')
            await expect(page.get_by_role('dialog')).to_have_count(0)
            await page.goto(BASE + '/tokens')
            await page.get_by_role('button', name='创建令牌', exact=True).click()
            await expect(page.get_by_role('dialog')).to_be_visible()
            await page.keyboard.press('Escape')
            await expect(page.get_by_role('dialog')).to_have_count(0)
            await page.goto(BASE + '/settings')
            await expect(page.locator('.system-settings-nav button')).to_have_count(7)
            await page.get_by_role('button',name='客户端与画像',exact=True).click()
            await expect(page.get_by_role('button', name='保存配置', exact=True)).to_be_in_viewport()
            scenes.append(f'{width}px 账号创建/编辑/OAuth、详情折叠、令牌创建与设置分类')
        await page.set_viewport_size({'width': 1280, 'height': 900})
        await page.goto(BASE + '/tasks')
        frame = page.locator('.task-runtime')
        await expect(frame.locator('#accounts-body .work-account')).to_have_count(1)
        await page.locator('.task-runtime').evaluate("node=>node.__navigationIdentity='stable'")
        await page.get_by_role('button', name='收起侧边栏').click()
        await expect(page.locator('.console-shell')).to_have_class('console-shell sidebar-collapsed console-native-tasks')
        assert await page.locator('.task-runtime').evaluate("node=>node.__navigationIdentity==='stable'")
        await page.get_by_role('button', name='展开侧边栏').click()
        for tab in ['topics', 'tasks', 'runs', 'projects']:
            await frame.locator(f'[data-tab="{tab}"]').click()
            await expect(page).to_have_url(BASE + '/tasks?tab=' + tab)
        await frame.locator('[data-tab="warmup"]').click()
        await expect(page).to_have_url(BASE + '/tasks?tab=warmup')
        assert await page.locator('.task-runtime').evaluate("node=>node.__navigationIdentity==='stable'")
        await frame.locator('#theme-toggle').click()
        await expect(frame).to_have_attribute('data-theme', 'dark')
        await page.reload()
        await expect(frame).to_have_attribute('data-theme', 'dark')
        scenes.append('侧栏折叠与六个任务域页面保持文档身份，明暗偏好跨刷新保留')
        await page.screenshot(path=str(output / 'tasks-dark.png'), full_page=True)
        assert not fixture.writes, fixture.writes
        assert not errors, errors
        await context.close()
        # 静态文件必须离线加载，实际业务脚本不会进入导出文件。
        preview = ROOT / '.deploy/frontend-sidebar-refresh/preview/index.html'
        context = await browser.new_context()
        page = await context.new_page()
        remote = []
        page.on('request', lambda request: remote.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(preview.as_uri())
        await expect(page.locator('#pages option')).to_have_count(13)
        for index in range(13):
            await page.select_option('#pages', str(index))
            await page.wait_for_timeout(120)
            assert await page.frame_locator('#stage').locator('body').inner_text()
        await page.select_option('#pages', '1')
        await page.frame_locator('#stage').get_by_role('link', name='账号', exact=True).click()
        await expect(page.locator('#pages')).to_have_value('0')
        await page.get_by_role('button', name='窄屏预览').click()
        assert (await page.locator('#stage').bounding_box())['width'] == 390
        assert not remote, remote
        assert not errors, errors
        scenes.append('13页离线预览、侧栏切换、390px预览与零网络请求')
        await browser.close()
    result = {'passed': True, 'scenes': scenes, 'errors': errors, 'business_writes': 0, 'real_model_requests': 0}
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/frontend-sidebar-refresh/navigation')
    print(json.dumps(asyncio.run(run(parser.parse_args().output)), ensure_ascii=False))
