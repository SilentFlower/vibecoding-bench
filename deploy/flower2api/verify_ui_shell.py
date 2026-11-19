"""验证第二版控制台外壳：侧栏、页头、移动端应用栏与抽屉、系统设置保存栏、登录页。

与 doc/design/console-v2/mock.html（登录页为 doc/design/console-v2/v1/mock.html#login）逐项比对计算样式，并核对折叠、
矮视口内部滚动、版本号两态、导航、保存栏计数与撤销、登录三条路径及密码显示切换。
需先构建前端（npm --prefix apps/web run build）；只使用合成接口，不访问真实服务。
"""
import argparse
import asyncio
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_dashboard_update import DashboardUpdateFixture
from verify_environment_ui import BASE, ROOT

MOCK = (ROOT / 'doc/design/console-v2/mock.html').as_uri()
LOGIN_MOCK = (ROOT / 'doc/design/console-v2/v1/mock.html').as_uri()
TEXT = ['color', 'font-size', 'font-weight', 'font-family', 'line-height']
BOX = ['background-color', 'color', 'height', 'padding-left', 'padding-right', 'border-top-left-radius', 'font-size', 'font-weight', 'column-gap']
# (设计稿选择器, 控制台选择器, 属性)；画面为 mock.html#accounts，1440×900。
SIDEBAR_PAIRS = [
    ('body', '.console-shell', ['background-color']),
    ('.sb', '.console-sidebar', ['background-color', 'box-shadow', 'width', 'padding-top', 'padding-left', 'padding-bottom']),
    ('.sb-brand', '.console-sidebar .console-brand-row', ['padding-left']),
    ('.sb-mark', '.console-sidebar .console-brand-mark', ['width', 'height', 'border-top-left-radius', 'background-color']),
    ('.sb-brand b', '.console-sidebar .console-brand-name', TEXT + ['letter-spacing']),
    ('.sb-ver.up', '.console-sidebar .brand-update', BOX + ['font-family', 'margin-left']),
    ('.sb-ver.up svg', '.console-sidebar .brand-update svg', ['width', 'height']),
    ('.sb-brand small', '.console-sidebar .sidebar-tagline', TEXT + ['margin-top']),
    ('.sb-label', '.console-sidebar .navigation-group-label', TEXT + ['padding-top', 'padding-left', 'padding-bottom']),
    ('.sb-item:not(.on)', '.console-sidebar .navigation-item:not(.is-active)', BOX),
    ('.sb-item:not(.on) svg', '.console-sidebar .navigation-item:not(.is-active) svg', ['color', 'width', 'height']),
    ('.sb-item.on', '.console-sidebar .navigation-item.is-active', ['background-color', 'color', 'font-weight']),
    ('.sb-item.on svg', '.console-sidebar .navigation-item.is-active svg', ['color']),
    ('.sb-count', '.console-sidebar .navigation-count', BOX + ['min-width', 'font-family']),
    ('.sb-run', '.console-sidebar .navigation-running', BOX + ['font-family']),
    ('.sb-foot', '.console-sidebar .sidebar-footer', ['background-color', 'border-top-left-radius', 'padding-top', 'padding-left', 'column-gap']),
    ('.sb-foot .av', '.console-sidebar .sidebar-avatar', ['width', 'height', 'border-top-left-radius', 'background-color', 'color', 'font-weight']),
    ('.sb-foot b', '.console-sidebar .sidebar-identity strong', TEXT),
    ('.sb-foot div:not(.av):not(.tools) > span', '.console-sidebar .sidebar-identity small', TEXT),
    ('.sb-foot .tools span', '.console-sidebar .sidebar-tool', ['width', 'height', 'border-top-left-radius', 'color']),
    ('.page', '#console-content', ['padding-top', 'padding-left', 'padding-right']),
    ('.ph h1', '#console-content .fui-page-header-title', TEXT + ['letter-spacing']),
    ('.ph p', '#console-content .fui-page-header-description', TEXT + ['margin-top']),
    ('.ph-actions', '#console-content .fui-page-header-actions', ['column-gap']),
    ('.ph-actions .btn-primary', '#console-content .fui-page-header-actions [data-variant=default]', BOX),
    ('.ph-actions .btn:not(.btn-primary)', '#console-content .fui-page-header-actions [data-variant=outline]', BOX),
]
# 无新版本：设计稿只画了有更新态，去掉 up 类得到常态。
VERSION_PAIRS = [('.sb-ver', '.console-sidebar .brand-update', BOX + ['font-family'])]
MOBILE_PAIRS = [
    ('.m-app', '.console-shell', ['background-color']),
    ('.m-top', '.console-toolbar', ['background-color', 'box-shadow', 'padding-top', 'padding-left', 'column-gap']),
    ('.m-top .sb-mark', '.console-toolbar-mark', ['width', 'height', 'border-top-left-radius', 'background-color']),
    ('.m-top b', '.toolbar-page', TEXT),
    ('.m-top .r span', '.mobile-sidebar-toggle', ['width', 'height', 'border-top-left-radius', 'background-color', 'color']),
]
SAVEBAR_PAIRS = [
    ('.savebar', '.settings-save-bar', ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'padding-right', 'column-gap']),
    ('.savebar b', '.settings-save-bar .fui-save-bar-title', TEXT + ['column-gap']),
    ('.savebar .hint', '.settings-save-bar .fui-save-bar-hint', TEXT),
]
LOGIN_PAIRS = [
    ('.login', '.login-page', ['grid-template-columns']),
    ('.login-art', '.login-art', ['background-color', 'color', 'padding-top', 'padding-left']),
    ('.login-art > div:nth-of-type(1) b', '.login-art-brand b', TEXT),
    ('.login-art h2', '.login-art-copy h2', TEXT + ['letter-spacing']),
    ('.login-art p', '.login-art-copy p', TEXT + ['margin-top', 'max-width']),
    ('.login-art > div:nth-of-type(2) > div', '.login-art-meta', ['color', 'font-size', 'column-gap', 'margin-top']),
    ('.login-form > div', '.login-form', ['width', 'row-gap']),
    ('.login-form h1', '.login-heading h1', TEXT),
    ('.login-form h1 + p', '.login-heading p', TEXT + ['margin-top']),
    ('.login-form .input', '.login-password', ['height']),
    ('.login-form .btn-primary', '.login-submit', ['height', 'width']),
    ('.login-form > div > .muted', '.login-note', ['font-size', 'text-align', 'color']),
]
# 结构写法不同但视觉等价、或有意的偏差，比对时跳过对应属性并注明原因。
KNOWN = {
    '.sb-ver.up': {'margin-left'},  # 设计稿名称与版本号由父级 flex 的 7px 间距隔开，外壳为网格布局，用版本号左外边距 7px 实现同一间距
    '.login-form h1': {'color'},  # 表单文字取第二版 text token，第一版为 #141a2a
    '.login-form h1 + p': {'color'},  # 同上，第二版 text-3
    '.login-form > div > .muted': {'color'},  # 同上
    '.login-form .input': {'height'},  # 统一为组件库大号控件 44px（第一版 40px），见 design §6
    '.login-form .btn-primary': {'height'},  # 同上
}
PAGES = [('账号', '账号管理'), ('请求记录', '请求记录'), ('会话封禁', '会话封禁'), ('访问令牌', '访问令牌'),
         ('代理管理', '代理管理'), ('运行环境', '运行环境'), ('节点管理', '节点管理'), ('系统设置', '系统设置')]
SAMPLE = '(e, names) => Object.fromEntries(names.map(n => [n, n === "font-family" ? getComputedStyle(e).fontFamily.split(",")[0].trim().replaceAll(\'"\', "") : getComputedStyle(e).getPropertyValue(n)]))'


class ShellFixture(DashboardUpdateFixture):
    """在版本角标夹具上补齐会话封禁与节点列表，并按密码模拟登录失败。"""

    async def route(self, route):
        """补齐外壳验证用到的接口。@param route 浏览器路由。@return None。"""
        path = urlsplit(route.request.url).path
        if path == '/admin/session-policy-blocks':
            return await self.respond(route, dict(items=[], total=0, page=1, page_size=20, observed_at_ms=int(time.time() * 1000)))
        if path == '/runtime/api/nodes':
            return await self.respond(route, {'items': [dict(id=1, name='本机执行节点', kind='local', node_key='local', enabled=True)]})
        if path == '/admin/dashboard' and 'wrong-password' in (route.request.headers.get('authorization') or ''):
            return await self.respond(route, {'error': '合成鉴权失败'}, 401)
        return await super().route(route)


async def sample(page, selector: str, props: list) -> dict:
    """读取第一个匹配元素的计算样式。@param page 页面。@param selector 选择器。@param props 属性。@return 属性值。"""
    locator = page.locator(selector).first
    assert await locator.count(), f'找不到 {selector}'
    return await locator.evaluate(SAMPLE, props)


async def compare(mock, actual, pairs: list, problems: list, label: str) -> int:
    """逐项比对设计稿与控制台。@param mock 设计稿页。@param actual 控制台页。@param pairs 比对清单。@param problems 差异列表。@param label 画面名。@return 比对项数。"""
    for mock_selector, actual_selector, props in pairs:
        expected, observed = await sample(mock, mock_selector, props), await sample(actual, actual_selector, props)
        skip = KNOWN.get(mock_selector, set())
        problems.extend(f'{label} {mock_selector} {prop}: 设计稿 {expected[prop]} 控制台 {observed[prop]}'
                        for prop in props if prop not in skip and expected[prop] != observed[prop])
    return len(pairs)


async def open_mock(browser, url: str, screen: str, width: int, height: int):
    """打开设计稿指定画面。@param url 设计稿。@param screen 画面名。@return 页面。"""
    page = await browser.new_page(viewport={'width': width, 'height': height})
    await page.goto(f'{url}?s={screen}#{screen}')
    await page.evaluate('document.fonts.ready')
    return page


async def open_console(browser, scenario: str, width: int, height: int, errors: list, authed: bool = True):
    """以合成夹具打开真实构建。@param scenario 更新场景。@param authed 是否预置登录。@return (上下文, 页面)。"""
    context = await browser.new_context(viewport={'width': width, 'height': height})
    await context.route('**/*', ShellFixture(scenario).route)
    if authed:
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
    page = await context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    return context, page


async def verify_desktop(browser, output: Path, problems: list, errors: list) -> dict:
    """1440 桌面：侧栏与页头比对、版本号两态、悬停、折叠保持、矮视口滚动、8 个页头、保存栏。@return 摘要。"""
    mock = await open_mock(browser, MOCK, 'accounts', 1440, 900)
    context, page = await open_console(browser, 'normal', 1440, 900, errors)
    await page.goto(BASE + '/')
    badge = page.locator('.console-sidebar .brand-update')
    await expect(badge).to_have_class('brand-update has-update', timeout=12000)
    await expect(page.locator('.console-sidebar .navigation-running')).to_be_visible()
    await page.evaluate('document.fonts.ready')
    compared = await compare(mock, page, SIDEBAR_PAIRS, problems, 'accounts')
    await page.screenshot(path=str(output / 'shell-1440.png'))

    # 悬停与键盘焦点：设计稿未画，按 design §3.1 的约定核对（默认主题取值）。
    item = page.locator('.console-sidebar .navigation-item:not(.is-active)').first
    await item.hover()
    await page.wait_for_timeout(250)
    hovered = await item.evaluate(SAMPLE, ['background-color', 'color'])
    if hovered != {'background-color': 'rgba(98, 96, 158, 0.075)', 'color': 'rgb(15, 21, 39)'}:
        problems.append(f'导航悬停: {hovered}')

    # 版本号点击沿用现有更新面板。
    await badge.click()
    await expect(page.locator('.approved-update-dialog')).to_be_visible()
    await page.get_by_role('button', name='关闭更新面板').click()
    await expect(page.locator('.approved-update-dialog')).to_be_hidden()

    # 折叠：宽度 76、只留图标，刷新后保持。
    await page.get_by_role('button', name='收起侧边栏').click()
    await expect(page.locator('.console-shell')).to_have_class('console-shell sidebar-collapsed')
    await page.reload()
    await expect(page.locator('.console-shell')).to_have_class('console-shell sidebar-collapsed')
    collapsed = await page.locator('.console-sidebar').evaluate('e => e.getBoundingClientRect().width')
    assert collapsed == 76, collapsed
    await expect(page.locator('.console-sidebar .console-brand-name')).to_be_hidden()
    await expect(page.locator('.console-sidebar .brand-update svg')).to_be_visible()
    await page.screenshot(path=str(output / 'shell-collapsed-1440.png'))
    await page.get_by_role('button', name='展开侧边栏').click()
    await expect(page.locator('.console-shell')).to_have_class('console-shell')

    # 矮视口：只有导航滚动，底部管理员区仍在视口内。
    await page.set_viewport_size({'width': 1440, 'height': 560})
    short = await page.evaluate("""() => { const nav = document.querySelector('.console-sidebar .console-navigation'), foot = document.querySelector('.console-sidebar .sidebar-footer').getBoundingClientRect();
        return { scrolls: nav.scrollHeight > nav.clientHeight, overflow: getComputedStyle(nav).overflowY, footBottom: foot.bottom, navBottom: nav.getBoundingClientRect().bottom, height: innerHeight }; }""")
    assert short['scrolls'] and short['overflow'] == 'auto' and short['footBottom'] <= short['height'] and short['navBottom'] <= short['footBottom'], short
    await page.screenshot(path=str(output / 'shell-short-1440.png'))
    await page.set_viewport_size({'width': 1440, 'height': 900})

    # 8 个页面的页头：无分组名、单个 h1、样式等于设计稿。
    title_style = await sample(mock, '.ph h1', TEXT + ['letter-spacing'])
    headers = []
    for label, title in PAGES:
        await page.locator('.console-sidebar').get_by_role('link', name=label, exact=True).click()
        header = page.locator('#console-content .fui-page-header').first
        await expect(header.locator('h1')).to_have_text(title)
        assert await page.locator('#console-content .page-eyebrow').count() == 0, label
        assert await page.locator('#console-content h1').count() == 1, label
        observed = await sample(page, '#console-content .fui-page-header-title', list(title_style))
        if observed != title_style:
            problems.append(f'{title} 页头标题: 设计稿 {title_style} 控制台 {observed}')
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(output / f'header-{len(headers) + 1}-1440.png'))
        headers.append(title)

    # 系统设置：浮动保存栏比对，修改计数与撤销语义不变。
    settings_mock = await open_mock(browser, MOCK, 'settings', 1440, 900)
    compared += await compare(settings_mock, page, SAVEBAR_PAIRS, problems, 'settings')
    bar = page.locator('.settings-save-bar')
    await expect(bar).to_contain_text('配置已同步')
    await page.locator('[name=v3_admission_wait_seconds]').fill('99')
    await expect(bar).to_contain_text('1 项待保存')
    await expect(bar).to_have_attribute('data-dirty', 'true')
    await page.screenshot(path=str(output / 'settings-savebar-1440.png'))
    await page.get_by_role('button', name='撤销修改').click()
    await expect(bar).to_contain_text('配置已同步')

    # 无新版本时版本号为常态灰底、无上箭头。
    latest_context, latest = await open_console(browser, 'latest', 1440, 900, errors)
    await latest.goto(BASE + '/')
    await expect(latest.locator('.console-sidebar .navigation-count')).to_be_visible()
    await latest.wait_for_timeout(500)
    await expect(latest.locator('.console-sidebar .brand-update')).to_have_class('brand-update')
    assert await latest.locator('.console-sidebar .brand-update svg').count() == 0
    await mock.evaluate("document.querySelector('.sb-ver').classList.remove('up')")
    compared += await compare(mock, latest, VERSION_PAIRS, problems, 'accounts 无新版本')
    await latest_context.close()
    await settings_mock.close()
    await mock.close()
    await context.close()
    return {'compared': compared, 'headers': headers, 'short_viewport': short}


async def verify_mobile(browser, output: Path, problems: list, errors: list) -> dict:
    """390 移动端：应用栏比对、标题随路由、抽屉贴左铺满并在导航后关闭、页头只留操作、无横向溢出。@return 摘要。"""
    mock = await open_mock(browser, MOCK, 'mobile', 390, 844)
    context, page = await open_console(browser, 'normal', 390, 844, errors)
    await page.goto(BASE + '/')
    await expect(page.locator('.toolbar-page')).to_have_text('账号管理')
    await page.evaluate('document.fonts.ready')
    compared = await compare(mock, page, MOBILE_PAIRS, problems, 'mobile')
    assert await page.locator('.fui-page-header-title').evaluate('e => e.getBoundingClientRect().width') <= 1
    await expect(page.locator('.fui-page-header-actions')).to_be_visible()
    await page.screenshot(path=str(output / 'shell-390.png'))
    await page.get_by_role('button', name='打开主导航').click()
    panel = page.locator('.mobile-navigation-panel')
    await expect(panel).to_be_visible()
    await page.wait_for_timeout(400)
    box = await panel.bounding_box()
    assert box and abs(box['x']) < 1 and abs(box['y']) < 1 and abs(box['height'] - 844) < 1, box
    await page.screenshot(path=str(output / 'drawer-390.png'))
    await page.get_by_role('dialog').get_by_role('link', name='请求记录', exact=True).click()
    await expect(panel).to_have_count(0)
    await expect(page.locator('.toolbar-page')).to_have_text('请求记录')
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    await mock.close()
    await context.close()
    return {'compared': compared}


async def verify_login(browser, output: Path, problems: list, errors: list) -> dict:
    """登录页：1440 比对第一版设计稿，390 形态，空密码 / 错误密码 / 成功三条路径与密码显示切换。@return 摘要。"""
    mock = await open_mock(browser, LOGIN_MOCK, 'login', 1440, 900)
    context, page = await open_console(browser, 'latest', 1440, 900, errors, authed=False)
    await page.goto(BASE + '/login')
    field = page.locator('#admin-password')
    await field.wait_for()
    await page.evaluate('document.fonts.ready')
    compared = await compare(mock, page, LOGIN_PAIRS, problems, 'login')
    await page.screenshot(path=str(output / 'login-1440.png'))

    submit = page.get_by_role('button', name='登录', exact=True)
    await submit.click()
    await expect(page.get_by_role('alert')).to_have_text('请输入密码')
    await field.fill('wrong-password')
    reveal = page.get_by_role('button', name='显示密码')
    await reveal.click()
    await expect(field).to_have_attribute('type', 'text')
    await expect(page.get_by_role('button', name='隐藏密码')).to_have_attribute('aria-pressed', 'true')
    await page.get_by_role('button', name='隐藏密码').click()
    await expect(field).to_have_attribute('type', 'password')
    await submit.click()
    await expect(page.get_by_role('alert')).to_have_text('密码错误')
    await field.fill('synthetic-only')
    await submit.click()
    await expect(page).to_have_url(BASE + '/')
    await expect(page.locator('.console-sidebar')).to_be_visible()
    assert await page.evaluate("localStorage.getItem('claude-code-gateway_auth')") == 'synthetic-only'
    await context.close()

    context, page = await open_console(browser, 'latest', 390, 844, errors, authed=False)
    await page.goto(BASE + '/login')
    await page.locator('#admin-password').wait_for()
    await expect(page.locator('.login-art')).to_be_hidden()
    await expect(page.locator('.login-mobile-brand')).to_be_visible()
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    await page.screenshot(path=str(output / 'login-390.png'))
    await context.close()
    await mock.close()
    return {'compared': compared, 'paths': ['空密码', '错误密码', '成功', '显示 / 隐藏密码']}


async def verify(output: Path) -> None:
    """执行全部检查并写入证据。@param output 证据目录。@return 无。"""
    output.mkdir(parents=True, exist_ok=True)
    problems, errors = [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        result = {
            'desktop': await verify_desktop(browser, output, problems, errors),
            'mobile': await verify_mobile(browser, output, problems, errors),
            'login': await verify_login(browser, output, problems, errors),
        }
        await browser.close()
    # 错误密码请求按设计返回 401，浏览器会记一条资源加载错误，不属于页面脚本错误。
    errors = [error for error in errors if '401' not in error]
    result.update(problems=problems, errors=errors, passed=not problems and not errors)
    (output / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    assert not problems, '\n'.join(problems)
    assert not errors, errors
    print('控制台外壳验证通过')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='验证第二版控制台外壳与登录页')
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/console-ui-revamp/ui-shell/verify')
    args = parser.parse_args()
    asyncio.run(verify(args.output))
