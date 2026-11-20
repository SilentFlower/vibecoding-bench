"""对照第二版设计稿（mock.html #accounts、#account-edit、#mobile）核对账号页的计算样式，并验证首屏、健康条语义色、
工作区固定外框、移动端搜索行与零控制台错误；设计稿未画的画面截图供目视确认。真实构建 + 合成管理接口，不触达外部服务。"""
import argparse
import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright, expect

from verify_environment_ui import BASE, ROOT
from verify_interaction_parity import InteractionFixture

MOCK = (ROOT / 'doc/design/console-v2/mock.html').as_uri()
TEXT = ['color', 'font-size', 'font-weight', 'font-family', 'line-height']
BOX = ['height', 'padding-left', 'border-top-left-radius', 'background-color', 'color', 'font-size', 'font-weight']
CARD = '.account-card-grid > .account-card:first-child'
EDIT = '.account-workspace'
# 与设计稿逐项对照：(画面, 设计稿选择器, 页面选择器, 属性)
PAIRS = [
    # 工具栏
    ('accounts', '.tb', '.account-toolbar', ['column-gap', 'align-items']),
    ('accounts', '.tb > .input:first-child', '.account-platform-filter .fui-choice', ['width'] + BOX),
    ('accounts', '.tb .seg', '.account-filter-tabs', ['background-color', 'padding-top', 'column-gap', 'border-top-left-radius']),
    ('accounts', '.tb .seg span.on', '.account-filter-tabs [data-state=checked]', BOX + ['box-shadow', 'column-gap']),
    ('accounts', '.tb .seg span:not(.on)', '.account-filter-tabs [data-state=unchecked]', ['color', 'font-size', 'font-weight', 'background-color']),
    ('accounts', '.tb .seg span.on em', '.account-filter-tabs [data-state=checked] .fui-segmented-count', ['font-size', 'font-weight', 'font-family', 'color']),
    ('accounts', '.tb > .input:last-child', '.account-toolbar .fui-toolbar-end > .fui-search', ['width', 'height', 'background-color', 'border-top-left-radius']),
    # 网格与卡片
    ('accounts', '.grid.g3', '.account-card-grid', ['column-gap', 'grid-template-columns']),
    ('accounts', '.card.acc', CARD, ['padding-top', 'padding-left', 'padding-bottom', 'row-gap', 'border-top-left-radius', 'background-color', 'box-shadow']),
    ('accounts', '.acc-head', f'{CARD} .account-identity', ['column-gap', 'align-items']),
    ('accounts', '.acc .avatar.cc', f'{CARD} .account-avatar', ['width', 'height', 'border-top-left-radius', 'background-color', 'color', 'font-size', 'font-weight']),
    ('accounts', '.acc .avatar i', f'{CARD} .account-avatar-state', ['width', 'height', 'background-color', 'box-shadow', 'right', 'bottom']),
    ('accounts', '.acc-name b', f'{CARD} .account-card-title h3', TEXT),
    ('accounts', '.acc-name b', f'{CARD} .account-card-title', ['column-gap']),
    ('accounts', '.acc-name b .tg-cc', f'{CARD} [data-platform-badge]', BOX),
    ('accounts', '.acc-name b .tg-primary', f'{CARD} .account-plan', BOX),
    ('accounts', '.acc-name span', f'{CARD} .account-identity-text > p', TEXT + ['margin-top']),
    ('accounts', '.acc-ctl', f'{CARD} .account-work-controls', ['column-gap', 'justify-content', 'font-size', 'font-weight', 'color']),
    ('accounts', '.acc-ctl .switch.on', f'{CARD} .account-status-switch', ['width', 'height', 'background-color', 'border-top-left-radius']),
    ('accounts', '.acc-ctl .btn-danger', f'{CARD} .account-work-toggle', BOX),
    ('accounts', '.links', f'{CARD} .account-network', ['column-gap', 'font-size', 'font-weight', 'color']),
    ('accounts', '.links svg', f'{CARD} .account-network > button svg', ['color', 'width']),
    ('accounts', '.strip.s', f'{CARD} .account-health', BOX + ['column-gap']),
    ('accounts', '.strip .tag', f'{CARD} .account-queue-alert', BOX),
    ('accounts', '.block.route', f'{CARD} .account-routing', ['background-color', 'border-top-left-radius', 'padding-top', 'padding-left', 'column-gap']),
    ('accounts', '.route label', f'{CARD} .account-routing > div > span', TEXT),
    ('accounts', '.route b', f'{CARD} .account-routing > div > strong', TEXT),
    ('accounts', '.route b small', f'{CARD} .account-routing > div > strong small', ['font-size', 'font-weight', 'color', 'margin-left']),
    ('accounts', '.route .pri', f'{CARD} .account-routing > button', ['border-left-color', 'border-left-width', 'padding-left', 'row-gap']),
    ('accounts', '.route .pri b', f'{CARD} .account-routing > button > strong', ['column-gap', 'font-size', 'font-weight', 'color']),
    ('accounts', '.route .pri .tag', f'{CARD} .account-score', BOX),
    ('accounts', '.usage-h', f'{CARD} .account-usage-windows > header', TEXT),
    ('accounts', '.usage-h span', f'{CARD} .account-usage-windows > header small', ['font-size', 'font-weight', 'color']),
    ('accounts', '.usage-h span b', f'{CARD} .account-usage-windows > header button', ['font-size', 'font-weight', 'color', 'column-gap']),
    ('accounts', '.since', f'{CARD} .usage-record-start', TEXT + ['margin-top']),
    ('accounts', '.win', f'{CARD} .account-usage-window', ['row-gap']),
    ('accounts', '.win .stat', f'{CARD} .usage-stats', TEXT),
    ('accounts', '.win .row', f'{CARD} .usage-window-label', TEXT),
    ('accounts', '.win .row b', f'{CARD} .usage-window-label strong', TEXT),
    ('accounts', '.win .bar', f'{CARD} .usage-window-bar', ['height', 'border-top-left-radius', 'background-color']),
    ('accounts', '.win .bar i', f'{CARD} .usage-window-bar > i[data-tone=success]', ['background-color']),
    ('accounts', '.win .rs', f'{CARD} .usage-window-reset', TEXT),
    ('accounts', '.metrics', f'{CARD} .account-live-metrics', ['column-gap', 'padding-top', 'border-top-color', 'border-top-width', 'grid-template-columns']),
    ('accounts', '.metrics span', f'{CARD} .account-live-metrics span', TEXT + ['column-gap']),
    ('accounts', '.metrics b', f'{CARD} .account-live-metrics strong', TEXT),
    ('accounts', '.metrics b small', f'{CARD} .account-live-metrics strong small', ['font-size', 'font-weight', 'color']),
    ('accounts', '.metrics .bar', f'{CARD} .metric-track', ['height', 'width', 'background-color', 'border-top-left-radius']),
    ('accounts', '.metrics .bar.p i', f'{CARD} .metric-track > i', ['background-color']),
    ('accounts', '.acts', f'{CARD} .account-card-actions', ['grid-template-columns', 'padding-top', 'padding-left', 'border-top-color', 'margin-left']),
    ('accounts', '.acts span:first-child', f'{CARD} .account-card-actions > button:first-child', ['height', 'border-top-left-radius', 'font-size', 'font-weight', 'color', 'column-gap']),
    ('accounts', '.acts .dg', f'{CARD} .account-card-actions > button.danger', ['color']),
    # 账号工作区配置页
    ('account-edit', '.modal', EDIT, ['width', 'border-top-left-radius', 'background-color', 'box-shadow']),
    ('account-edit', '.mh', f'{EDIT} .fui-modal-head', ['padding-top', 'padding-left', 'column-gap']),
    ('account-edit', '.mh .avatar', f'{EDIT} .account-avatar', ['width', 'height', 'border-top-left-radius', 'background-color']),
    ('account-edit', '.mh h2', f'{EDIT} .fui-modal-title', TEXT + ['column-gap']),
    ('account-edit', '.mh p', f'{EDIT} .fui-modal-description', TEXT),
    ('account-edit', '.modal > div[style*="padding:0 24px 18px"]', f'{EDIT} .fui-modal-nav', ['padding-top', 'padding-left', 'padding-right', 'padding-bottom']),
    ('account-edit', '.modal .seg', f'{EDIT} .account-workspace-tabs', ['background-color', 'padding-top', 'column-gap']),
    ('account-edit', '.modal .seg span:not(.on) em', f'{EDIT} .account-workspace-tabs [data-state=unchecked] .fui-segmented-count', ['font-size', 'font-family']),
    ('account-edit', '.mb', f'{EDIT} .fui-modal-body', ['padding-top', 'padding-left', 'row-gap']),
    ('account-edit', '.sec-t', f'{EDIT} .account-form-section > h3', TEXT),
    ('account-edit', '.mb > .fg.c3', f'{EDIT} .account-form-section .account-edit-grid.three', ['column-gap', 'row-gap', 'grid-template-columns']),
    ('account-edit', '.mb .field label', f'{EDIT} .approved-field > span', TEXT),
    ('account-edit', '.mb .field', f'{EDIT} .approved-field', ['row-gap']),
    ('account-edit', '.mb .field .help', f'{EDIT} .forwarding-field .form-help', TEXT),
    ('account-edit', '.mb .field .fg', f'{EDIT} .forwarding-options', ['column-gap', 'grid-template-columns']),
    ('account-edit', '.rc.on', f'{EDIT} .forwarding-options [data-state=checked]', ['background-color', 'box-shadow', 'padding-top', 'padding-left', 'border-top-left-radius', 'column-gap']),
    ('account-edit', '.rc:not(.on)', f'{EDIT} .forwarding-options [data-state=unchecked]', ['background-color']),
    ('account-edit', '.rc b', f'{EDIT} .fui-radio-card-label', ['font-size', 'font-weight']),
    ('account-edit', '.mb .field:nth-child(3) > .input', f'{EDIT} .approved-field .fui-input', ['height', 'background-color', 'border-top-left-radius', 'font-size', 'padding-left']),
    ('account-edit', '.mf', f'{EDIT} .fui-modal-foot', ['background-color', 'padding-top', 'padding-left', 'column-gap']),
    ('account-edit', '.mf > span.t3', f'{EDIT} .account-save-hint', ['font-size', 'font-weight', 'color']),
    ('account-edit', '.mf .btn-primary', f'{EDIT} .fui-modal-foot .fui-button-default', BOX),
    # 移动端
    ('mobile', '.m-top .r', '.console-toolbar-actions', ['column-gap']),
    ('mobile', '.m-top .r span:first-child', '.account-search-toggle', ['width', 'height', 'border-top-left-radius', 'background-color', 'color']),
    ('mobile', '.m-app .seg', '.account-filter-tabs', ['background-color', 'padding-top']),
    ('mobile', '.m-app .seg span.on', '.account-filter-tabs [data-state=checked]', ['height', 'padding-left', 'font-size', 'font-weight']),
    ('mobile', '.m-app .card.acc', CARD, ['width', 'padding-left', 'padding-top']),
    ('mobile', '.m-app .acts', f'{CARD} .account-card-actions', ['grid-template-columns']),
]
# 结构写法不同但视觉等价、或已记录的有意偏差，比对时跳过对应属性。
KNOWN = {
    # 设计稿 .acc-name span（邮箱行）选择器同时命中名称里的两个徽标，把徽标文字改成了邮箱的 12.5px/500/text-3；
    # 页面徽标按设计稿 .tag 定义（11.5px/650，平台色与主色文字），底色、高度、圆角仍逐项比对。
    ('accounts', '.acc-name b .tg-cc'): {'color', 'font-size', 'font-weight'},
    ('accounts', '.acc-name b .tg-primary'): {'color', 'font-size', 'font-weight'},
    # 99px 与 999px 都是全圆；token 规则只允许 999px 这一全圆字面量。
    ('accounts', '.acc-ctl .switch.on'): {'border-top-left-radius'},
    ('accounts', '.win .bar'): {'border-top-left-radius'},
    ('accounts', '.metrics .bar'): {'border-top-left-radius'},
}
SCRIPT = '(e, names) => Object.fromEntries(names.map(n => [n, n === "font-family" ? getComputedStyle(e).fontFamily.split(",")[0].replaceAll(\'"\', "").replaceAll("\'", "") : getComputedStyle(e).getPropertyValue(n)]))'
TOKEN = "n=>{const e=document.createElement('i');e.style.color=`var(${n})`;document.body.append(e);const c=getComputedStyle(e).color;e.remove();return c}"


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


def fixture_with_states() -> InteractionFixture:
    """第 4–6 号账号分别为限流、认证错误、已停用，覆盖健康条四种色调。@return 夹具。"""
    fixture = InteractionFixture()
    fixture.accounts[3].update(rate_limit_reset_at='2099-01-01T00:00:00Z', disable_reason='接近 5 小时上限')
    fixture.accounts[4].update(auth_error='invalid_grant：凭据已失效，需要重新授权')
    fixture.accounts[5].update(status='disabled', disable_reason='管理员停用')
    return fixture


async def main(output: Path) -> None:
    """对比设计稿画面并验证账号页的布局与交互边界。@param output 截图与结果目录。@return 无。"""
    output.mkdir(parents=True, exist_ok=True)
    errors, problems, compared = [], [], 0
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        mock = await browser.new_page(viewport={'width': 1440, 'height': 900})
        fixture = fixture_with_states()
        context = await browser.new_context(viewport={'width': 1440, 'height': 900})
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        await page.goto(BASE + '/')
        cards = page.locator('.account-card-grid > .account-card')
        await expect(cards).to_have_count(12)
        await settle(page)
        compared += await compare(mock, page, 'accounts', problems)
        # 首屏：三列、间距 16，首行三张卡片的操作栏底边在 900 以内。
        grid = await page.locator('.account-card-grid').evaluate('e=>({columns:getComputedStyle(e).gridTemplateColumns.split(" ").length,gap:getComputedStyle(e).columnGap})')
        assert grid == {'columns': 3, 'gap': '16px'}, grid
        for index in range(3):
            bottom = await cards.nth(index).locator('.account-card-actions').evaluate('e=>e.getBoundingClientRect().bottom')
            assert bottom <= 900, (index, bottom)
        # 健康条语义色：正常 / 限流 / 认证错误 / 停用。
        tones = {0: ('success', '--ui-color-success-bg'), 3: ('warning', '--ui-color-warning-bg'), 4: ('danger', '--ui-color-danger-bg'), 5: ('neutral', '--ui-color-neutral-bg')}
        for index, (tone, token) in tones.items():
            strip = cards.nth(index).locator('.account-health')
            await expect(strip).to_have_attribute('data-tone', tone)
            await expect(strip).to_have_css('background-color', await page.evaluate(TOKEN, token))
            await expect(strip).to_have_css('height', '36px')
        await page.screenshot(animations='disabled', path=str(output / 'accounts-1440.png'))
        await cards.nth(3).scroll_into_view_if_needed()
        await page.screenshot(animations='disabled', path=str(output / 'accounts-states-1440.png'))
        await page.evaluate('scrollTo(0,0)')
        # 工作区：编辑打开配置页，外框 820 居中、只有内容区滚动，四个页签切换时外框不动。
        # 设计稿弹窗相对内容区（不含侧栏）居中；产品弹窗按视口居中并遮罩侧栏，与系统更新弹窗一致，所以只比宽度与外观。
        await cards.first.get_by_role('button', name='编辑', exact=True).click()
        workspace = page.locator(EDIT)
        await expect(workspace).to_be_visible()
        await settle(page, workspace)
        compared += await compare(mock, page, 'account-edit', problems)
        frame = await workspace.bounding_box()
        assert abs(frame['width'] - 820) <= 1 and abs(frame['x'] + frame['width'] / 2 - 720) <= 1, frame
        await page.screenshot(animations='disabled', path=str(output / 'workspace-configuration-1440.png'))
        body = workspace.locator('.fui-modal-body')
        nav_top = await workspace.locator('.fui-modal-nav').evaluate('e=>e.getBoundingClientRect().top')
        await body.evaluate('e=>e.scrollTop=400')
        assert await body.evaluate('e=>e.scrollTop') > 0
        assert await workspace.locator('.fui-modal-nav').evaluate('e=>e.getBoundingClientRect().top') == nav_top
        await expect(workspace.locator('.fui-modal-foot')).to_be_visible()
        tabs = workspace.locator('.account-workspace-tabs')
        await expect(tabs.get_by_role('radio', name='调度')).to_contain_text('4')
        for label, shot in (('概览', 'overview'), ('调度', 'scheduling'), ('环境与诊断', 'diagnostics')):
            await tabs.get_by_role('radio', name=label).click()
            await page.wait_for_timeout(300)
            assert await workspace.bounding_box() == frame, (label, await workspace.bounding_box(), frame)
            await expect(workspace.locator('.fui-modal-foot')).to_have_count(0)
            await page.screenshot(animations='disabled', path=str(output / f'workspace-{shot}-1440.png'))
        await page.keyboard.press('Escape')
        await expect(workspace).to_have_count(0)
        # 新建账号：直接显示配置页，无页签带。
        await page.get_by_role('button', name='添加账号', exact=True).click()
        await expect(workspace.locator('.fui-modal-foot')).to_be_visible()
        await expect(workspace.locator('.fui-modal-nav')).to_have_count(0)
        await page.screenshot(animations='disabled', path=str(output / 'workspace-create-1440.png'))
        await page.keyboard.press('Escape')
        # 授权登录三步与删除确认（设计稿未画，截图目视确认）。
        await page.get_by_role('button', name='授权登录', exact=True).click()
        oauth = page.locator('.approved-oauth-dialog')
        await expect(oauth).to_have_css('width', '440px')
        await settle(page, oauth)
        await page.screenshot(animations='disabled', path=str(output / 'oauth-generate-1440.png'))
        await oauth.get_by_role('button', name='生成授权链接', exact=True).click()
        await expect(oauth.get_by_role('link', name='点击打开授权页面 ↗')).to_be_visible()
        await page.screenshot(animations='disabled', path=str(output / 'oauth-exchange-1440.png'))
        await oauth.get_by_label('授权码', exact=True).fill('synthetic-code')
        await oauth.get_by_role('button', name='完成授权', exact=True).click()
        await expect(oauth.get_by_role('button', name='填入账号配置', exact=True)).to_be_visible()
        await page.screenshot(animations='disabled', path=str(output / 'oauth-done-1440.png'))
        await page.keyboard.press('Escape')
        await cards.first.get_by_role('button', name='删除', exact=True).click()
        await expect(page.locator('.fui-confirm-dialog')).to_be_visible()
        await page.screenshot(animations='disabled', path=str(output / 'delete-confirm-1440.png'))
        await page.get_by_role('button', name='取消', exact=True).click()
        await page.get_by_role('searchbox', name='搜索账号').fill('no-such-account')
        await expect(page.locator('.account-empty')).to_be_visible()
        await page.screenshot(animations='disabled', path=str(output / 'accounts-empty-1440.png'))
        await page.get_by_role('button', name='清空搜索账号').click()
        await expect(cards).to_have_count(12)
        # 移动端：应用栏搜索按钮展开搜索行，有生效筛选时不收起；工作区单列。
        await page.set_viewport_size({'width': 390, 'height': 844})
        mock_mobile = await browser.new_page(viewport={'width': 390, 'height': 844})
        await settle(page)
        compared += await compare(mock_mobile, page, 'mobile', problems)
        toggle = page.get_by_role('button', name='搜索账号', exact=True)
        search = page.get_by_role('searchbox', name='搜索账号')
        await expect(search).to_be_hidden()
        await expect(page.locator('.account-filter-tabs [role=radio]').first).to_have_text(re.compile(r'^全部\d+$'))
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.screenshot(animations='disabled', path=str(output / 'accounts-390.png'))
        await toggle.click()
        await expect(search).to_be_focused()
        await search.fill('design13@')
        await expect(cards).to_have_count(1)
        await toggle.click()
        await expect(search).to_be_visible()
        await expect(toggle).to_have_attribute('aria-expanded', 'true')
        await page.screenshot(animations='disabled', path=str(output / 'accounts-search-390.png'))
        await page.get_by_role('button', name='清空搜索账号').click()
        await expect(cards).to_have_count(12)
        await toggle.click()
        await expect(search).to_be_hidden()
        await cards.first.get_by_role('button', name='编辑', exact=True).click()
        await settle(page, workspace)
        assert await workspace.locator('.account-edit-grid.three').first.evaluate('e=>getComputedStyle(e).gridTemplateColumns.split(" ").length') == 1
        assert await body.evaluate('e=>e.scrollWidth<=e.clientWidth')
        await page.screenshot(animations='disabled', path=str(output / 'workspace-configuration-390.png'))
        await tabs.get_by_role('radio', name='概览').click()
        await page.wait_for_timeout(300)
        await page.screenshot(animations='disabled', path=str(output / 'workspace-overview-390.png'))
        await page.keyboard.press('Escape')
        await page.get_by_role('button', name='授权登录', exact=True).click()
        await settle(page, oauth)
        await page.screenshot(animations='disabled', path=str(output / 'oauth-generate-390.png'))
        await page.keyboard.press('Escape')
        # 其它页面应用栏不显示账号搜索按钮。
        await page.get_by_role('button', name='打开主导航').click()
        await page.get_by_role('link', name='访问令牌', exact=True).click()
        await expect(page).to_have_url(BASE + '/tokens')
        await expect(page.locator('.account-search-toggle')).to_have_count(0)
        assert not problems, json.dumps(problems, ensure_ascii=False, indent=1)
        assert not errors, errors
        result = dict(passed=True, compared=compared, whitelisted=len(KNOWN), checks=['工具栏、卡片、工作区配置页、移动端逐项比对', '首行三张卡片操作栏在首屏内', '健康条四种语义色', '工作区 820 居中、页签切换外框不动、只滚内容区', '新建无页签带', '授权登录 440', '移动端搜索行与筛选保持展开', '其它页面无搜索按钮', '零控制台错误'])
        (output / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
        await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/console-ui-revamp/accounts/verify')
    asyncio.run(main(parser.parse_args().output))
