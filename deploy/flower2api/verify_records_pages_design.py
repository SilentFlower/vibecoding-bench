"""对照第二版设计稿（mock.html #requests、#proxies、#tokens、#blocks）核对请求记录、代理管理、访问令牌、会话封禁四页的计算样式，
并验证日志级别卡切换、接口计数与缺失兜底、令牌名称搜索、封禁分段计数、请求详情抽屉外框、390 无横向滚动与零控制台错误；
设计稿未画的画面（详情页签、弹窗、展开行、390 形态）截图供目视确认。真实构建 + 合成管理接口，不触达外部服务。"""
import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.async_api import async_playwright, expect

from verify_environment_ui import BASE, ROOT
from verify_remaining_pages import RemainingPagesFixture
from verify_session_policy_blocks_ui import BlockFixture

MOCK = (ROOT / 'doc/design/console-v2/mock.html').as_uri()
DIST = ROOT / 'apps/web/dist'
TEXT = ['color', 'font-size', 'font-weight', 'font-family', 'line-height']
BOX = ['height', 'padding-left', 'border-top-left-radius', 'background-color', 'color', 'font-size', 'font-weight']
CARD = ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'column-gap']
TCARD = ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-bottom', 'row-gap']
SEG = ['background-color', 'padding-top', 'column-gap', 'border-top-left-radius']
HEAD = ['height', 'padding-left', 'font-size', 'font-weight', 'color', 'background-color']
# 与设计稿逐项对照：(画面, 设计稿选择器, 页面选择器, 属性)
PAIRS = [
    # 请求记录：概览卡、表格卡片头部、表格
    ('requests', '.grid.g4', '.request-overview', ['column-gap', 'row-gap']),
    ('requests', '.ov', '.request-overview > :first-child', CARD),
    ('requests', '.ov p', '.request-overview > :first-child .fui-overview-card-label', TEXT),
    ('requests', '.ov strong', '.request-overview > :first-child .fui-overview-card-value', TEXT + ['margin-top', 'margin-bottom']),
    ('requests', '.ov > div > span', '.request-overview > :first-child .fui-overview-card-caption', TEXT),
    ('requests', '.ov .ico.d', '.request-overview > :nth-child(2) .fui-icon-tile', ['width', 'height', 'background-color', 'color']),
    ('requests', '.ov .ico.w', '.request-mode-card .fui-icon-tile', ['background-color', 'color']),
    ('requests', '.ov:last-child', '.request-mode-card', CARD),
    ('requests', '.ov:last-child strong', '.request-mode-card .fui-overview-card-value', ['font-size', 'font-weight', 'font-family', 'color']),
    ('requests', '.tcard', '.request-records', TCARD),
    ('requests', '.tcard-h', '.request-records .fui-table-card-head', ['column-gap', 'align-items']),
    ('requests', '.tcard-h .seg', '.request-records .fui-segmented', SEG),
    ('requests', '.tcard-h .seg span.on', '.request-records .fui-segmented-item[data-state=checked]', BOX + ['box-shadow']),
    ('requests', '.tcard-h .seg span.on em', '.request-records [data-state=checked] .fui-segmented-count', ['font-size', 'font-weight', 'font-family', 'color']),
    ('requests', '.tcard-h .input', '.request-query .fui-toolbar-end > .fui-search', ['width', 'height', 'background-color', 'border-top-left-radius']),
    ('requests', '.tcard-h .btn-primary', '.request-query .fui-toolbar-end > [type=submit]', BOX),
    ('requests', '.tcard-h .btn-icon', '.request-query [aria-label=刷新]', ['width', 'height', 'border-top-left-radius', 'background-color']),
    ('requests', '.t th', '.request-table .fui-table-head', HEAD),
    ('requests', '.t td', '.request-table .fui-table-cell', ['font-size', 'color', 'padding-left', 'vertical-align']),
    ('requests', '.t td .sub', '.request-table .fui-table-sub', TEXT + ['margin-top']),
    ('requests', '.t td.strong', '.request-account-name', ['font-weight', 'color']),
    ('requests', '.t .tag.dot', '.request-result-button .fui-badge', BOX),
    ('requests', '.t .btn-text', '.request-detail-button', ['color', 'font-size', 'font-weight', 'height']),
    ('requests', '.tfoot', '.request-records .fui-pagination', ['font-size', 'font-weight', 'color']),
    # 代理管理
    ('proxies', '.ov', '.proxy-overview > :first-child', CARD),
    ('proxies', '.ov strong small', '.proxy-overview > :nth-child(2) .fui-overview-card-value small', TEXT + ['margin-left']),
    ('proxies', '.ov .ico.w', '.proxy-overview > :nth-child(4) .fui-icon-tile', ['background-color', 'color']),
    ('proxies', '.tcard', '.proxy-panel', TCARD),
    ('proxies', '.tcard-h h3', '.proxy-panel .fui-table-card-title', TEXT + ['column-gap']),
    ('proxies', '.tcard-h h3 small', '.proxy-panel .fui-table-card-count', TEXT),
    ('proxies', '.tcard-h .input', '.proxy-panel .fui-table-card-toolbar > .fui-search', ['width', 'height', 'background-color', 'border-top-left-radius']),
    ('proxies', '.tcard-h .btn', '.proxy-panel .fui-table-card-toolbar > [data-slot=button]', BOX),
    ('proxies', '.t th', '.proxy-table .fui-table-head', HEAD),
    ('proxies', '.t td .tile', '.proxy-identity .fui-icon-tile', ['width', 'height', 'border-top-left-radius', 'background-color', 'color']),
    ('proxies', '.t td div b', '.proxy-identity strong', ['font-weight', 'font-size', 'color']),
    ('proxies', '.t td b.mono', '.proxy-latency b', ['font-size', 'font-family', 'font-weight', 'color']),
    ('proxies', '.t .tag.dot', '.proxy-table tbody .fui-badge[data-dot]', BOX),
    ('proxies', '.t td .tag.tg-warning', '.proxy-table tbody tr:first-child td:nth-child(5) .fui-badge', BOX),
    ('proxies', '.ops .btn-sm:not(.btn-text)', '.proxy-row-actions [data-variant=outline]', BOX),
    ('proxies', '.ops .btn-text.dg', '.proxy-row-actions .proxy-delete', ['color', 'font-size', 'font-weight', 'height']),
    # 访问令牌
    ('tokens', '.tcard', '.token-panel', TCARD),
    ('tokens', '.tcard-h h3', '.token-panel .fui-table-card-title', TEXT + ['column-gap']),
    ('tokens', '.tcard-h h3 small', '.token-panel .fui-table-card-count', TEXT),
    ('tokens', '.tcard-h .input', '.token-panel .fui-search', ['width', 'height', 'background-color', 'border-top-left-radius']),
    ('tokens', '.t th', '.token-panel .fui-table-head', HEAD),
    ('tokens', '.t td .tile', '.token-identity .fui-icon-tile', ['width', 'height', 'border-top-left-radius', 'background-color', 'color']),
    ('tokens', '.t td div b', '.token-identity strong', ['font-weight', 'font-size', 'color']),
    ('tokens', '.t td .tag.tg-neutral', '.token-copy', BOX),
    ('tokens', '.t td .switch.on', '.token-status .fui-switch', ['width', 'height', 'background-color', 'border-top-left-radius']),
    ('tokens', '.t td.num.t3', '.token-created', ['color', 'font-size']),
    ('tokens', '.ops .btn-sm:not(.btn-text)', '.token-actions [data-variant=outline]', BOX),
    ('tokens', '.ops .btn-text.dg', '.token-actions [data-variant=destructive-ghost]', ['color', 'font-size', 'font-weight', 'height']),
    # 会话封禁
    ('blocks', '.tcard', '.session-block-panel', TCARD),
    ('blocks', '.tcard-h .seg', '.session-block-panel .fui-segmented', SEG),
    ('blocks', '.tcard-h .seg span.on', '.session-block-panel .fui-segmented-item[data-state=checked]', BOX + ['box-shadow']),
    ('blocks', '.tcard-h .input', '.session-block-toolbar .fui-search', ['width', 'height', 'background-color', 'border-top-left-radius']),
    ('blocks', '.tcard-h .btn-primary', '.session-block-toolbar [type=submit]', BOX),
    ('blocks', '.tcard-h > .t3', '.session-block-note', ['color', 'font-size', 'font-weight']),
    ('blocks', '.t th', '.session-block-records .fui-table-head', HEAD),
    ('blocks', '.t td .mono', '.session-block-records tbody code', ['font-family', 'font-size', 'color']),
    ('blocks', '.t .tag.dot', '.session-block-records tbody .fui-badge', BOX),
    ('blocks', '.t td.num b', '.block-count-column .fui-table-strong', ['font-weight', 'font-size']),
    ('blocks', '.t td .btn-sm', '.block-actions [data-slot=button]', BOX),
]
# 结构写法不同但视觉等价、或已记录的有意偏差，比对时跳过对应属性。
KNOWN = {
    # 99px 与 999px 都是全圆；token 规则只允许 999px 这一全圆字面量。
    ('tokens', '.t td .switch.on'): {'border-top-left-radius'},
}
SCRIPT = '(e, names) => Object.fromEntries(names.map(n => [n, n === "font-family" ? getComputedStyle(e).fontFamily.split(",")[0].replaceAll(\'"\', "").replaceAll("\'", "") : getComputedStyle(e).getPropertyValue(n)]))'


async def compare(mock, page, screen: str, problems: list) -> int:
    """逐项比对一个画面。@param mock 设计稿页。@param page 产品页。@param screen 画面名。@param problems 差异收集。@return 比对项数。"""
    await mock.goto(f'{MOCK}?s={screen}#{screen}')
    await mock.evaluate('document.fonts.ready')
    compared = 0
    for name, source, target, props in PAIRS:
        if name != screen:
            continue
        expected_node, actual_node = mock.locator(source).first, page.locator(target).first
        if not await expected_node.count() or not await actual_node.count():
            problems.append(f'{screen} {source} → {target}: 找不到对应元素')
            continue
        expected = await expected_node.evaluate(SCRIPT, props)
        actual = await actual_node.evaluate(SCRIPT, props)
        skip = KNOWN.get((screen, source), set())
        problems.extend(f'{screen} {source} {prop}: 设计稿 {expected[prop]} 页面 {actual[prop]}' for prop in props if prop not in skip and expected[prop] != actual[prop])
        compared += 1
    return compared


async def settle(page, dialog=None) -> None:
    """等字体与弹窗进场动画结束再取样。@param page 页面。@param dialog 弹窗定位器。@return 无。"""
    await page.evaluate('document.fonts.ready')
    if dialog is not None:
        # 进场动画可能被后续状态切换取消，finished 会以 AbortError 拒绝；取消即视为结束。
        await dialog.evaluate('e => Promise.all(e.getAnimations().map(a => a.finished.catch(() => null)))')
    await page.wait_for_timeout(300)


def records_fixture() -> RemainingPagesFixture:
    """请求、代理、令牌共用夹具；第 2 条代理已过期、第 3 条未设置到期，其余 5 天后到期。@return 夹具。"""
    fixture = RemainingPagesFixture()
    fixture.proxies[1]['expires_at'] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    fixture.proxies[2]['expires_at'] = None
    return fixture


async def open_page(browser, fixture, path: str, width: int, height: int, errors: list):
    """在新上下文打开页面并收集控制台错误。@return 页面与上下文。"""
    context = await browser.new_context(viewport={'width': width, 'height': height}, timezone_id='Asia/Shanghai')
    await context.route('**/*', fixture.route)
    await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
    page = await context.new_page()
    page.on('pageerror', lambda e: errors.append(f'{path} {e}'))
    page.on('console', lambda m: errors.append(f'{path} {m.text}') if m.type == 'error' else None)
    await page.goto(BASE + path)
    return page, context


async def no_overflow(page, label: str) -> None:
    """页面不出现横向滚动。@param page 页面。@param label 场景名。@return 无。"""
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), label


async def main(output: Path) -> None:
    """对比设计稿画面并验证四页的布局与交互边界。@param output 截图与结果目录。@return 无。"""
    output.mkdir(parents=True, exist_ok=True)
    errors, problems, compared = [], [], 0
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        mock = await browser.new_page(viewport={'width': 1440, 'height': 900})

        # ---------- 请求记录 ----------
        fixture = records_fixture()
        page, context = await open_page(browser, fixture, '/requests', 1440, 900, errors)
        await expect(page.locator('.request-records tbody tr')).to_have_count(1)
        await expect(page.locator('.request-overview > :first-child .fui-overview-card-value')).to_have_text('53')
        await expect(page.get_by_role('radio', name='错误 7', exact=True)).to_be_visible()
        card = page.locator('.request-mode-card')
        await expect(card).to_have_attribute('aria-label', '后续请求日志：info · 摘要，点击切换为 debug · 脱敏内容')
        await settle(page)
        compared += await compare(mock, page, 'requests', problems)
        await page.screenshot(animations='disabled', path=str(output / 'requests-1440.png'))
        # 日志卡：点击保存后续请求模式，保存期间禁用并提示，完成后显示新值。
        fixture.settings_gate = asyncio.Event()
        fixture.settings_started.clear()
        await card.click()
        await asyncio.wait_for(fixture.settings_started.wait(), 5)
        await expect(card).to_be_disabled()
        await expect(card).to_contain_text('保存中…')
        fixture.settings_gate.set()
        await expect(card.locator('.fui-overview-card-value')).to_have_text('debug · 脱敏内容')
        await expect(card).to_be_enabled()
        assert fixture.writes[-1] == {'path': '/admin/settings', 'body': {'request_diagnostics_log_mode': 'debug'}}, fixture.writes[-1]
        fixture.settings_gate = None
        # 快捷分段与筛选区。
        await page.get_by_role('radio', name='错误 7', exact=True).click()
        await expect(page.locator('.request-empty')).to_be_visible()
        assert fixture.diagnostic_queries[-1]['outcome'] == ['errors']
        await page.get_by_role('radio', name='全部 53', exact=True).click()
        await page.get_by_role('button', name='筛选', exact=True).click()
        await expect(page.locator('#request-filters')).to_be_visible()
        await page.screenshot(animations='disabled', path=str(output / 'request-filters-1440.png'))
        await page.get_by_role('button', name='筛选', exact=True).click()
        # 详情抽屉：贴右全高、宽 1020，头部与页签带固定，只有内容区滚动。
        await page.get_by_role('button', name='详情', exact=True).click()
        drawer = page.locator('.request-workspace')
        await expect(drawer).to_be_visible()
        await settle(page, drawer)
        box = await drawer.evaluate('e=>{const r=e.getBoundingClientRect();return {left:r.left,top:r.top,width:r.width,height:r.height,right:innerWidth-r.right,bottom:innerHeight-r.bottom,overflow:getComputedStyle(e).overflowY,body:getComputedStyle(e.querySelector(".fui-modal-body")).overflowY}}')
        assert box['width'] == 1020 and box['top'] == 14 and box['right'] == 14 and box['bottom'] == 14, box
        assert box['overflow'] == 'hidden' and box['body'] == 'auto', box
        for tab in ('概览', '请求链路', '性能', '原始数据'):
            await drawer.get_by_role('tab', name=tab, exact=True).click()
            await expect(drawer.get_by_role('tab', name=tab, exact=True)).to_have_attribute('aria-selected', 'true')
            frame = await drawer.evaluate('e=>e.getBoundingClientRect().width')
            assert frame == 1020, (tab, frame)
            await page.screenshot(animations='disabled', path=str(output / f'request-detail-{tab}-1440.png'))
        await page.keyboard.press('Escape')
        await expect(drawer).to_have_count(0)
        await context.close()

        # ---------- 代理管理 ----------
        fixture = records_fixture()
        page, context = await open_page(browser, fixture, '/proxies', 1440, 900, errors)
        await expect(page.locator('tr[data-proxy-id]')).to_have_count(20)
        overview = page.locator('.proxy-overview')
        await expect(overview.locator('> :nth-child(4) .fui-overview-card-value')).to_have_text('19')
        await expect(overview.locator('> :nth-child(4) .fui-overview-card-caption')).to_have_text('另有 1 条已过期')
        await expect(overview.locator('> :nth-child(2) .fui-overview-card-value')).to_have_text('21/ 21')
        await settle(page)
        compared += await compare(mock, page, 'proxies', problems)
        await page.screenshot(animations='disabled', path=str(output / 'proxies-1440.png'))
        await page.locator('[data-proxy-id=proxy-1]').get_by_role('button', name='查看使用账号').click()
        await expect(page.locator('.proxy-expanded')).to_be_visible()
        await page.screenshot(animations='disabled', path=str(output / 'proxies-expanded-1440.png'))
        await page.get_by_role('button', name='添加代理', exact=True).click()
        editor = page.locator('.proxy-editor')
        await settle(page, editor)
        # 编辑弹窗按视口居中，布局宽度 680。
        geometry = await editor.evaluate('e=>{const r=e.getBoundingClientRect();return {width:e.offsetWidth,center:Math.round(r.left+r.width/2)}}')
        assert geometry == {'width': 680, 'center': 720}, geometry
        await page.screenshot(animations='disabled', path=str(output / 'proxy-editor-1440.png'))
        await page.keyboard.press('Escape')
        await page.get_by_role('button', name='批量导入', exact=True).click()
        await settle(page, page.locator('.proxy-import-dialog'))
        await page.screenshot(animations='disabled', path=str(output / 'proxy-import-1440.png'))
        await page.keyboard.press('Escape')
        await context.close()
        # 旧网关不返回到期计数时显示「—」，说明不写数字，不按当前页推算。
        fixture = records_fixture()
        fixture.directory_counts = lambda: dict(all=21, available=21, used=1)
        page, context = await open_page(browser, fixture, '/proxies', 1440, 900, errors)
        await expect(page.locator('tr[data-proxy-id]')).to_have_count(20)
        await expect(page.locator('.proxy-overview > :nth-child(4) .fui-overview-card-value')).to_have_text('—')
        await expect(page.locator('.proxy-overview > :nth-child(4) .fui-overview-card-caption')).to_have_text('按到期时间统计')
        await context.close()

        # ---------- 访问令牌 ----------
        fixture = records_fixture()
        page, context = await open_page(browser, fixture, '/tokens', 1440, 900, errors)
        await expect(page.locator('.token-row')).to_have_count(1)
        await settle(page)
        compared += await compare(mock, page, 'tokens', problems)
        await page.screenshot(animations='disabled', path=str(output / 'tokens-1440.png'))
        await page.get_by_role('searchbox', name='搜索令牌', exact=True).fill('不存在的令牌')
        await expect(page.get_by_text('没有匹配的令牌', exact=True)).to_be_visible()
        await page.screenshot(animations='disabled', path=str(output / 'tokens-search-empty-1440.png'))
        await page.get_by_role('searchbox', name='搜索令牌', exact=True).fill('')
        await page.get_by_role('button', name='编辑权限', exact=True).click()
        token_editor = page.locator('.approved-token-editor')
        await settle(page, token_editor)
        assert await token_editor.evaluate('e=>e.offsetWidth') == 760
        await page.screenshot(animations='disabled', path=str(output / 'token-editor-1440.png'))
        await page.keyboard.press('Escape')
        await context.close()

        # ---------- 会话封禁 ----------
        fixture = BlockFixture(DIST)
        page, context = await open_page(browser, fixture, '/session-blocks', 1440, 900, errors)
        await expect(page.locator('tr[data-block-id]')).to_have_count(20)
        states = page.get_by_role('radiogroup', name='封禁状态', exact=True)
        for name in ('封禁中 21', '已到期 1', '已解除 0', '全部记录 22'):
            await expect(states.get_by_role('radio', name=name, exact=True)).to_be_visible()
        await settle(page)
        compared += await compare(mock, page, 'blocks', problems)
        await page.screenshot(animations='disabled', path=str(output / 'blocks-1440.png'))
        await states.get_by_role('radio', name='已到期 1', exact=True).click()
        await expect(page.locator('tr[data-block-id]')).to_have_count(1)
        await page.screenshot(animations='disabled', path=str(output / 'blocks-expired-1440.png'))
        await context.close()

        # ---------- 390 形态 ----------
        for path, name, ready, kept in (
                ('/requests', 'requests', '.request-records tbody tr', 4),
                ('/proxies', 'proxies', 'tr[data-proxy-id]', 3),
                ('/tokens', 'tokens', '.token-row', 4),
                ('/session-blocks', 'blocks', 'tr[data-block-id]', 3)):
            fixture = BlockFixture(DIST) if name == 'blocks' else records_fixture()
            page, context = await open_page(browser, fixture, path, 390, 844, errors)
            await expect(page.locator(ready).first).to_be_visible()
            await settle(page)
            await no_overflow(page, f'{name}-390')
            visible = await page.locator('thead th:visible').count()
            assert visible == kept, (name, visible)
            await page.screenshot(animations='disabled', full_page=True, path=str(output / f'{name}-390.png'))
            if name == 'proxies':
                # 使用情况列在窄屏收起，线路列保留使用摘要与展开入口。
                row = page.locator('[data-proxy-id=proxy-1]')
                await row.get_by_role('button', name='查看使用账号').click()
                await expect(page.locator('.proxy-expanded .proxy-account-identity')).to_be_visible()
                await expect(row.get_by_role('button', name='收起账号')).to_be_visible()
                await no_overflow(page, 'proxies-expanded-390')
                await page.screenshot(animations='disabled', full_page=True, path=str(output / 'proxies-expanded-390.png'))
            if name == 'requests':
                await page.get_by_role('button', name='详情', exact=True).click()
                drawer = page.locator('.request-workspace')
                await settle(page, drawer)
                assert await drawer.evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                await page.screenshot(animations='disabled', path=str(output / 'request-detail-390.png'))
            await context.close()

        assert not problems, json.dumps(problems, ensure_ascii=False, indent=1)
        assert not errors, errors
        result = dict(passed=True, compared=compared, whitelisted=len(KNOWN), checks=[
            '四页 1440 逐项比对设计稿', '日志卡点击保存、保存中禁用与新值', '快捷分段与筛选区', '详情抽屉贴右全高 1020、唯一滚动区、四个页签',
            '代理到期计数与旧网关缺失兜底', '代理编辑 680 居中', '令牌名称搜索与编辑 760', '封禁四态分段计数与切换', '四页 390 无横向滚动与列折叠', '代理 390 展开使用账号', '零控制台错误'])
        (output / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
        await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/console-ui-revamp/records/verify')
    asyncio.run(main(parser.parse_args().output))
