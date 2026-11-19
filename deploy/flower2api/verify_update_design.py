"""对照第二版设计稿核对系统更新弹窗的概览与进度画面，并验证说明展开、文本转义与零写入边界。"""
import asyncio
import json
import uuid

from playwright.async_api import async_playwright, expect

from verify_system_update_browser import BASE, ROOT, UpdateFixture

MOCK = (ROOT / 'doc/design/console-v2/mock.html').as_uri()
TEXT = ['color', 'font-size', 'font-weight', 'font-family', 'line-height']
CHIP = ['height', 'padding-left', 'border-top-left-radius', 'background-color', 'color', 'font-size', 'font-weight', 'column-gap']
STRIP = ['height', 'padding-left', 'border-top-left-radius', 'background-color', 'color', 'font-size', 'font-weight', 'column-gap']
BUTTON = ['height', 'padding-left', 'border-top-left-radius', 'background-color', 'color', 'font-size', 'font-weight', 'column-gap']
DIALOG = '.system-update-dialog'
# 与设计稿逐项对照：(画面, 设计稿选择器, 弹窗选择器, 属性)
PAIRS = [
    ('update', '.um', DIALOG, ['width', 'border-top-left-radius', 'background-color', 'box-shadow']),
    ('update', '.um .mh .ico', f'{DIALOG} .su-head-icon', ['width', 'height', 'border-top-left-radius', 'background-color', 'color']),
    ('update', '.um .mh h2', f'{DIALOG} .fui-modal-title', TEXT),
    ('update', '.um .mh p', f'{DIALOG} .fui-modal-description', TEXT),
    ('update', '.um .mb', f'{DIALOG} .fui-modal-body', ['row-gap', 'padding-top', 'padding-left', 'padding-bottom']),
    ('update', '.mb > .u-sec:nth-child(1)', '[data-update-view=overview] > .su-section:nth-child(1)', ['background-color', 'border-top-left-radius', 'padding-top', 'padding-left', 'row-gap']),
    ('update', '.u-head small', '[data-update-view=overview] .su-head small', TEXT),
    ('update', '.mb > .u-sec:nth-child(1) .u-head b', '[data-update-view=overview] .su-head h3', TEXT + ['margin-top']),
    ('update', '.pill.s', '[data-update-view=overview] .su-pill[data-tone=success]', CHIP),
    ('update', '.u-tiles', '[data-update-view=overview] .su-tiles', ['column-gap', 'grid-template-columns']),
    ('update', '.u-tiles div', '[data-update-view=overview] .su-tiles > div', ['background-color', 'border-top-left-radius', 'padding-top', 'padding-left']),
    ('update', '.u-tiles span', '[data-update-view=overview] .su-tiles span', TEXT),
    ('update', '.u-tiles b', '[data-update-view=overview] .su-tiles b', TEXT + ['margin-top']),
    ('update', '.strip.s', '[data-update-view=overview] .fui-strip[data-tone=success]', STRIP),
    ('update', '.mb > .u-sec:nth-child(2) .u-head b', '[data-update-view=overview] .su-head h4', ['font-size', 'font-weight', 'color']),
    ('update', '.mb > .u-sec:nth-child(2) .u-head span', '[data-update-view=overview] .su-head .su-mono', ['font-size', 'font-weight', 'font-family', 'color']),
    ('update', '.u-notes', '[data-update-view=overview] .su-notes', ['font-size', 'font-weight', 'color', 'row-gap', 'padding-left', 'list-style-type']),
    ('update', '.mb > .u-sec:nth-child(2) > span', '[data-update-view=overview] .su-link', ['font-size', 'font-weight', 'color']),
    ('update', '.u-plan', '[data-update-view=overview] .su-plan', ['column-gap', 'align-items', 'padding-top', 'padding-left']),
    ('update', '.u-plan .ico', '[data-update-view=overview] .su-plan-icon', ['width', 'height', 'border-top-left-radius', 'background-color', 'color']),
    ('update', '.u-plan b', '[data-update-view=overview] .su-plan-copy b', ['font-size', 'font-weight', 'color']),
    ('update', '.u-plan p', '[data-update-view=overview] .su-plan-copy p', TEXT + ['margin-top']),
    ('update', '.u-plan .field', '[data-update-view=overview] .su-plan-minutes', ['width']),
    ('update', '.mf', f'{DIALOG} .fui-modal-foot', ['background-color', 'padding-top', 'padding-left', 'column-gap']),
    ('update', '.mf .btn-text', f'{DIALOG} .fui-modal-foot .fui-button-ghost', BUTTON),
    ('update', '.mf .btn-primary', f'{DIALOG} .fui-modal-foot .fui-button-default', BUTTON),
    ('update', '.mf .btn:not(.btn-text):not(.btn-primary)', f'{DIALOG} .fui-modal-foot .fui-button-outline', BUTTON),
    ('update-progress', '.pill.i', '[data-update-view=progress] .su-pill[data-tone=info]', CHIP),
    ('update-progress', '.strip.n', '[data-update-view=progress] .fui-strip[data-tone=neutral]', STRIP),
    ('update-progress', '.mb > .u-sec:nth-child(2)', '[data-update-view=progress] .su-progress', ['row-gap', 'padding-top', 'padding-left']),
    ('update-progress', '.mb > .u-sec:nth-child(2) .u-head > b', '[data-update-view=progress] .su-progress h4', ['font-size', 'font-weight', 'color', 'column-gap']),
    ('update-progress', '.mb > .u-sec:nth-child(2) .u-head > b > span', '[data-update-view=progress] .su-progress h4 .su-mono', ['font-size', 'font-weight', 'font-family', 'color']),
    ('update-progress', '.live', '[data-update-view=progress] .su-live', CHIP),
    ('update-progress', '.u-log', '[data-update-view=progress] .su-log', ['row-gap']),
    ('update-progress', '.u-log .ok', '[data-update-view=progress] [data-update-step][data-state=done]', ['height', 'padding-left', 'border-top-left-radius', 'background-color', 'font-size', 'column-gap', 'grid-template-columns']),
    ('update-progress', '.u-log .ok time', '[data-update-view=progress] [data-state=done] time', TEXT),
    ('update-progress', '.u-log .ok i', '[data-update-view=progress] [data-state=done] i', ['width', 'height', 'background-color', 'border-top-left-radius']),
    ('update-progress', '.u-log .ok b', '[data-update-view=progress] [data-state=done] b', TEXT),
    ('update-progress', '.u-log .run', '[data-update-view=progress] [data-state=active]', ['height', 'box-shadow', 'background-color']),
    ('update-progress', '.u-log .run i', '[data-update-view=progress] [data-state=active] i', ['background-color', 'box-shadow']),
    ('update-progress', '.u-log .run b', '[data-update-view=progress] [data-state=active] b', ['color', 'font-weight']),
    ('update-progress', '.u-log .run em', '[data-update-view=progress] [data-state=active] em', TEXT),
    ('update-progress', '.u-log .wait', '[data-update-view=progress] [data-state=pending]', ['height', 'background-color']),
    ('update-progress', '.u-log .wait i', '[data-update-view=progress] [data-state=pending] i', ['background-color']),
    ('update-progress', '.u-log .wait b', '[data-update-view=progress] [data-state=pending] b', ['color', 'font-weight']),
]
# 结构写法不同但视觉等价、或已记录的有意偏差，比对时跳过对应属性。
KNOWN = {
    # 99px 与 999px 都是全圆；token 规则只允许 999px 这一全圆字面量。
    ('update', '.pill.s'): {'border-top-left-radius'},
    ('update-progress', '.pill.i'): {'border-top-left-radius'},
    ('update-progress', '.live'): {'border-top-left-radius'},
}
SCRIPT = '(e, names) => Object.fromEntries(names.map(n => [n, n === "font-family" ? getComputedStyle(e).fontFamily.split(",")[0].replaceAll(\'"\', "").replaceAll("\'", "") : getComputedStyle(e).getPropertyValue(n)]))'


async def compare(mock, page, screen: str, problems: list) -> int:
    """逐项比对一个画面。@param mock 设计稿页。@param page 弹窗页。@param screen 画面名。@param problems 差异收集。@return 比对项数。"""
    await mock.goto(f'{MOCK}?s={screen}#{screen}')
    await mock.evaluate('document.fonts.ready')
    compared = 0
    for name, source, target, props in PAIRS:
        if name != screen:
            continue
        expected_node, actual_node = mock.locator(source).first, page.locator(target).first
        if not await expected_node.count() or not await actual_node.count():
            problems.append(f'{screen} {source}: 找不到对应元素')
            continue
        expected = await expected_node.evaluate(SCRIPT, props)
        actual = await actual_node.evaluate(SCRIPT, props)
        skip = KNOWN.get((screen, source), set())
        problems.extend(f'{screen} {source} {prop}: 设计稿 {expected[prop]} 弹窗 {actual[prop]}' for prop in props if prop not in skip and expected[prop] != actual[prop])
        compared += 1
    return compared


async def main():
    """对比设计稿画面，并验证真实维护入口的阅读与零写入边界。@return 无。"""
    out = ROOT / '.deploy/frontend-sidebar-refresh/update-deep'
    out.mkdir(parents=True, exist_ok=True)
    fixture = UpdateFixture()
    fixture.catalog['releases'][0]['changes'] = '平台版本：v1.0.1\n\n账号管理\n用量与状态集中呈现。\n\n任务工作区\n保留执行与交付入口。\n\n维护反馈\n<img src=x onerror="window.releaseInjected=1">'
    errors, problems = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        mock = await browser.new_page(viewport={'width': 1440, 'height': 900})
        context = await browser.new_context(viewport={'width': 1440, 'height': 900})
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda e: errors.append(e.stack))
        await page.goto(BASE)
        await page.locator('.console-sidebar .brand-update').click()
        dialog = page.locator(DIALOG)
        overview = dialog.locator('[data-update-view=overview]')
        await expect(overview.locator('.su-notes > li')).to_have_count(3)
        await page.evaluate('document.fonts.ready')
        await dialog.evaluate('e => Promise.all(e.getAnimations().map(a => a.finished))')
        compared = await compare(mock, page, 'update', problems)
        # 说明展开与收起，发布文本按纯文本显示。
        await dialog.get_by_role('button', name='查看完整发布说明', exact=True).click()
        await expect(dialog.locator('[data-release-details]')).to_have_count(1)
        await expect(dialog.locator('[data-release-details]')).to_contain_text('<img src=x')
        assert await page.evaluate('window.releaseInjected===undefined')
        await dialog.get_by_role('button', name='收起完整发布说明', exact=True).click()
        await expect(dialog.locator('[data-release-details]')).to_have_count(0)
        for width in [1440, 720, 390]:
            await page.set_viewport_size({'width': width, 'height': 1000})
            await page.wait_for_timeout(300)
            assert await dialog.locator('.fui-modal-body').evaluate('e=>e.scrollWidth<=e.clientWidth'), width
            await page.screenshot(animations='disabled', path=str(out / f'updates-{width}.png'))
        # 只读自动检查以外不产生写入：浏览、展开与关闭都不登记安装。
        assert all(write['path'] == '/runtime/api/system-updates/check' for write in fixture.writes), fixture.writes
        # 进度画面：维护中、两步已记录、其余待执行。
        await page.set_viewport_size({'width': 1440, 'height': 900})
        fixture.state.update(busy=True, operation={'operation_id': str(uuid.uuid4()), 'action': 'install', 'phase': 'draining',
            'target_release': 'system-ci-101-1', 'created_at': '2026-11-11T00:00:00Z', 'updated_at': '2026-11-11T00:00:05Z',
            'blockers': ['合成长流', '合成 CLI 作业'], 'error': None,
            'steps': [{'phase': 'preparing', 'at': '2026-11-11T00:00:00Z'}, {'phase': 'draining', 'at': '2026-11-11T00:00:05Z'}]})
        await expect(dialog.locator('[data-update-view=progress] [data-state=active]')).to_be_visible(timeout=15000)
        compared += await compare(mock, page, 'update-progress', problems)
        await page.screenshot(animations='disabled', path=str(out / 'progress-1440.png'))
        await page.get_by_role('button', name='关闭', exact=True).click()
        await expect(dialog).to_be_hidden()
        await browser.close()
    (out / 'styles.json').write_text(json.dumps(problems, ensure_ascii=False, indent=2))
    assert not problems, '\n'.join(problems)
    assert not errors, errors
    print(json.dumps({'passed': True, 'compared': compared, 'style_differences': 0,
        'checks': ['概览与进度画面对照第二版设计稿', '发布摘要真实文本', '完整说明展开与收起', '文本转义', '浏览零安装写入', '1440/720/390px'], 'errors': errors}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
