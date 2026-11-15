"""验证运行环境卡片的信息层次、筛选和工作区同步。"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, expect


async def main():
    """执行离线交互及宽窄屏验证并输出证据。@return 无。"""
    out = Path('.deploy/frontend-sidebar-refresh/concept')
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': 1600, 'height': 1100})
        errors, network = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: network.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
        await page.goto(Path('doc/design/flower2api-concept.html').resolve().as_uri() + '#environments')
        await page.evaluate('document.fonts.ready')
        cards = page.locator('[data-environment-card]')
        await expect(cards).to_have_count(6)
        first = page.locator('[data-environment-card="1"]')
        for text in ['dev@example.test', '第 12 代', '内存配置', '4 GiB', 'CLI CPU', '发送器 CPU', '网络 CPU', '空闲暖进程', '存活', '空闲 PID 18401', '内容采集', 'CRIU 加速', 'Asia/Shanghai']:
            await expect(first).to_contain_text(text)
        await expect(page.locator('[data-environment-card="2"]')).to_contain_text('CLI 作业执行中')
        await expect(page.locator('[data-environment-card="3"]')).to_contain_text('待生效')
        await expect(page.locator('[data-environment-card="4"]')).to_contain_text('状态未知')
        await expect(page.locator('[data-environment-card="6"] .environment-role-strip')).to_contain_text('已停止')
        await page.locator('[data-environment-filter="attention"]').click()
        await expect(cards).to_have_count(2)
        await page.locator('#environment-search').fill('backup@')
        await expect(cards).to_have_count(1)
        await page.locator('[data-environment-filter="ready"]').click()
        await expect(cards).to_have_count(0)
        await page.locator('[data-environment-reset]').click()
        await expect(cards).to_have_count(6)
        await page.locator('#environment-search').fill('env-demo-0002')
        await expect(cards).to_have_count(1)
        await page.locator('[data-environment-card="2"] [data-environment-open="maintenance"]').click()
        dialog = page.locator('#action-dialog')
        await expect(dialog).to_contain_text('工程主账号')
        await expect(dialog.locator('[data-environment-maintenance="停止环境"]')).to_be_disabled()
        await dialog.get_by_role('tab', name='资源与采集', exact=True).click()
        await expect(dialog.locator('[name="capture"]')).to_be_disabled()
        await page.keyboard.press('Escape')
        await page.locator('#environment-search').fill('')
        await first.locator('[data-environment-open="resources"]').first.click()
        await dialog.locator('[name="cliCpu"]').fill('3.5')
        await dialog.locator('[name="capture"]').uncheck()
        await dialog.get_by_role('tab', name='运行时段', exact=True).click()
        await dialog.get_by_role('tab', name='资源与采集', exact=True).click()
        await expect(dialog.locator('[name="cliCpu"]')).to_have_value('3.5')
        await dialog.get_by_role('button', name='保存配置', exact=True).click()
        await expect(dialog).to_be_visible()
        await expect(first.locator('.environment-resources-grid')).to_contain_text('3.5')
        await expect(first).to_contain_text('待关闭')
        await dialog.get_by_role('tab', name='运行概览', exact=True).click()
        await expect(dialog.locator('[data-env-capture]')).to_have_text('待关闭')
        await dialog.get_by_role('tab', name='运行时段', exact=True).click()
        await dialog.get_by_role('combobox', name='时区', exact=True).click()
        await page.get_by_role('option', name='America/Los_Angeles · 洛杉矶', exact=True).click()
        await dialog.get_by_role('combobox', name='开始时间小时', exact=True).click()
        await page.get_by_role('option', name='10 时', exact=True).click()
        await dialog.get_by_role('combobox', name='开始时间分钟', exact=True).click()
        await page.get_by_role('option', name='30 分', exact=True).click()
        await dialog.get_by_role('button', name='保存时段', exact=True).click()
        await page.keyboard.press('Escape')
        await expect(first).to_contain_text('10:30–23:00')
        await expect(first).to_contain_text('America/Los_Angeles')
        await first.locator('[data-open-environment]').click()
        await dialog.get_by_role('tab', name='运行时段', exact=True).click()
        await expect(dialog.locator('[name="timezone"]')).to_have_value('America/Los_Angeles')
        await dialog.get_by_role('tab', name='维护操作', exact=True).click()
        await dialog.get_by_role('button', name='停止环境', exact=True).click()
        await expect(page.locator('[data-action-layer][open]')).to_have_count(2)
        await page.keyboard.press('Escape')
        await expect(dialog.get_by_role('button', name='停止环境', exact=True)).to_be_focused()
        await page.keyboard.press('Escape')
        # 未知快照与真实零个暖进程分别显示，字符串按文本转义。
        await page.evaluate("environmentDemo.get(1).native_preparation={state:'unknown'};accounts[0].name='<img src=x onerror=alert(1)>';refreshEnvironmentCards()")
        await expect(first).to_contain_text('准备状态待检查')
        await expect(first.locator('img')).to_have_count(0)
        await expect(first).not_to_contain_text('空闲暖进程 0')
        await page.reload()
        for width in [1600, 1280, 720, 390]:
            await page.set_viewport_size({'width': width, 'height': 900})
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
            await page.screenshot(path=str(out / f'environments-{width}.png'), full_page=True)
            await first.locator('[data-open-environment]').click()
            assert await dialog.evaluate('el=>el.scrollWidth<=el.clientWidth+1'), width
            await dialog.get_by_role('tab', name='资源与采集', exact=True).click()
            # 控件外框无溢出并不代表内部正确：输入及加减按钮必须在同一行且完整落在外框内。
            geometry = await dialog.locator('.cpu-fields .account-stepper').evaluate_all("""nodes => nodes.map(node => {
                const box = node.getBoundingClientRect(), input = node.querySelector('input').getBoundingClientRect();
                const actions = node.querySelector('.stepper-actions').getBoundingClientRect();
                return {height: box.height, inputHeight: input.height,
                    contained: input.left >= box.left && actions.right <= box.right && actions.bottom <= box.bottom,
                    aligned: Math.abs((input.top + input.height / 2) - (actions.top + actions.height / 2)) < 1};
            })""")
            assert all(item['height'] == 40 and item['inputHeight'] >= 36 and item['contained'] and item['aligned'] for item in geometry), (width, geometry)
            positions = await dialog.locator('.cpu-fields > .field').evaluate_all('nodes => nodes.map(node => node.getBoundingClientRect().top)')
            assert (positions[0] < positions[1] < positions[2]) if width <= 600 else len(set(positions)) == 1, (width, positions)
            await page.screenshot(path=str(out / f'environment-resources-{width}.png'))
            await page.keyboard.press('Escape')
        assert not errors, errors
        assert not network, network
        (out / 'environments-verification.json').write_text(json.dumps({'status': 'passed', 'cards': 6, 'viewports': [1600, 1280, 720, 390], 'checks': ['状态与缺失区分', '搜索与状态组合', '忙碌保护', '跨页签草稿', '配置保存同步', '时区持久', '二级确认焦点', '文本转义', '宽窄屏'], 'errors': errors, 'network': network}, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
