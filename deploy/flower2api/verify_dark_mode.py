"""验证控制台深色模式：深色设计稿（mock.html?mode=dark）对深色产品的计算样式比对（外壳、账号、账号编辑、请求、系统更新与进度、
任务与工程、运行环境、主题设置、390 移动端、授权登录终端），21 个原生深层弹窗与页面颜色只取 token、正文对比度抽样，
以及主题模式行为：跟随系统实时切换（含内嵌任务页与独立 /runtime/ 文档）、侧栏快捷切换与刷新保持、首帧深浅、模式存储篡改与写入失败、
主题设置页的模式草稿。需先构建前端（npm --prefix apps/web run build）；只使用合成接口，不访问真实服务。"""
import argparse
import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright, expect

import verify_account_page_design as account_design
import verify_native_pages_design as native_design
import verify_records_pages_design as records_design
import verify_theme_settings as theme_design
import verify_ui_shell as shell_design
import verify_update_design as update_design
from verify_environment_ui import BASE, ROOT
from verify_runtime_workspace_design import WorkspaceFixture
from verify_system_update_browser import BASE as UPDATE_BASE, UpdateFixture
from verify_task_login_design import LoginFixture

MOCK = (ROOT / 'doc/design/console-v2/mock.html').as_uri()
MODE_KEY = 'flower2api.theme-mode'
AUTH = "localStorage.setItem('claude-code-gateway_auth','synthetic-only');"
TOKEN = "name => { const probe = document.createElement('i'); probe.style.color = `var(${name})`; document.body.append(probe); const color = getComputedStyle(probe).color; probe.remove(); return color; }"
SCHEME = "() => document.documentElement.dataset.uiScheme"
# 正文类文字色（占位与禁用用的 text-4 不计入正文）：在页面上找取这些颜色的文字节点，算它对实际底色（逐层向上合成）的对比度。
TEXT_TOKENS = ['--ui-color-text', '--ui-color-text-2', '--ui-color-text-3', '--ui-color-primary-text', '--ui-color-on-primary', '--ui-color-ink-text',
    '--ui-color-success-text', '--ui-color-warning-text', '--ui-color-danger-text', '--ui-color-info-text', '--ui-color-neutral-text',
    '--ui-color-cc-text', '--ui-color-agy-text', '--ui-color-feedback-text']
CONTRAST = '''(root, [colors, label]) => {
  const parse = c => { const m = /rgba?\\(([^)]+)\\)/.exec(c); if (!m) return null; const p = m[1].split(/[\\s,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const channel = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const lum = c => 0.2126 * channel(c[0]) + 0.7152 * channel(c[1]) + 0.0722 * channel(c[2]);
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
  const allowed = new Set(colors), out = []; let checked = 0;
  for (const e of [root, ...root.querySelectorAll('*')]) {
    if (![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) || !e.getClientRects().length) continue;
    if (e.closest('svg, .xterm, [disabled], [aria-disabled=true], [data-disabled], [hidden]')) continue;
    const s = getComputedStyle(e);
    if (!allowed.has(s.color)) continue;
    // 逐层向上收集底色直到不透明；中途遇到渐变或半透明祖先（禁用、淡出）不计。
    const layers = []; let skip = false;
    for (let n = e; n; n = n.parentElement) {
      const t = getComputedStyle(n);
      if (t.backgroundImage !== 'none' || Number(t.opacity) < 1) { skip = true; break; }
      const c = parse(t.backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
    }
    if (skip || !layers.length || layers[layers.length - 1][3] < 1) continue;
    let bg = layers.pop();
    while (layers.length) { const top = layers.pop(); bg = [0, 1, 2].map(i => top[i] * top[3] + bg[i] * (1 - top[3])).concat(1); }
    const value = ratio(parse(s.color), bg);
    checked++;
    if (value < 4.5) out.push(`${label} ${e.tagName.toLowerCase()}.${[...e.classList].join('.')} 「${e.textContent.trim().slice(0, 16)}」 ${s.color} / rgb(${bg.slice(0, 3).map(Math.round).join(', ')}) = ${value.toFixed(2)}`);
  }
  return { checked, failures: out.slice(0, 20) }; }'''
SCANNED = []


async def wait_scheme(target, expected: str) -> None:
    """等文档根的深浅变为期望值（跟随系统与画板注入都是异步的）。@param target 页面或框架。@param expected 深浅。@return 无。"""
    await target.wait_for_function('expected => document.documentElement.dataset.uiScheme === expected', arg=expected, timeout=5000)


class DarkBrowser:
    """浏览器代理：新建的上下文与页面都设系统深色偏好，复用其它脚本的打开流程与弹窗清单。"""

    def __init__(self, browser):
        """@param browser Playwright 浏览器。@return 无。"""
        self.browser = browser

    async def new_context(self, **options):
        """@param options 上下文参数。@return 系统深色的上下文。"""
        return await self.browser.new_context(color_scheme='dark', **options)

    async def new_page(self, **options):
        """@param options 页面参数。@return 系统深色的页面。"""
        return await self.browser.new_page(color_scheme='dark', **options)


async def open_mock(browser, screen: str, width: int = 1440, height: int = 900):
    """打开深色设计稿画面。@param screen 画面名。@return 页面。"""
    page = await browser.new_page(viewport={'width': width, 'height': height})
    await page.goto(f'{MOCK}?mode=dark&s={screen}#{screen}')
    await page.evaluate('document.fonts.ready')
    return page


async def compare(mock, page, pairs: list, known: dict, script: str, label: str, problems: list) -> int:
    """逐项比对深色设计稿与深色产品。@param pairs (设计稿选择器, 产品选择器, 属性)。@param known 设计稿选择器 → 跳过的属性。@return 比对组数。"""
    for source, target, props in pairs:
        expected_node, actual_node = mock.locator(source).first, page.locator(target).first
        if not await expected_node.count() or not await actual_node.count():
            problems.append(f'{label} {source} → {target}: 找不到对应元素')
            continue
        expected, actual = await expected_node.evaluate(script, props), await actual_node.evaluate(script, props)
        skip = known.get(source, set())
        problems.extend(f'{label} {source} {prop}: 设计稿 {expected[prop]} 产品 {actual[prop]}' for prop in props if prop not in skip and expected[prop] != actual[prop])
    return len(pairs)


def screen_pairs(module, screen: str) -> tuple[list, dict]:
    """从 (画面, 设计稿, 产品, 属性) 形式的对照表取出一个画面。@param module 设计脚本模块。@return 对照与跳过项。"""
    pairs = [(source, target, props) for name, source, target, props in module.PAIRS if name == screen]
    known = {source: props for (name, source), props in getattr(module, 'KNOWN', {}).items() if name == screen}
    return pairs, known


async def scan(page, scope: str, label: str, problems: list) -> None:
    """范围内正文对比度抽样 ≥ 4.5。@param scope 根选择器。@param label 场景名。@return 无。"""
    await page.evaluate(native_design.SETTLED)
    colors = [await page.evaluate(TOKEN, name) for name in TEXT_TOKENS]
    result = await page.locator(scope).first.evaluate(CONTRAST, [colors, label])
    SCANNED.append((label, result['checked']))
    problems.extend(result['failures'])


async def open_dark(browser, fixture, url: str, width: int, errors: list, init: str = '', height: int | None = None, sockets=None):
    """以系统深色打开页面。@param fixture 合成夹具。@param url 完整地址。@param init 额外初始化脚本。@param sockets 导航前接管 WebSocket 的处理函数。@return 上下文与页面。"""
    context = await browser.new_context(viewport={'width': width, 'height': height or (900 if width > 760 else 844)}, color_scheme='dark', timezone_id='Asia/Shanghai')
    await context.route('**/*', fixture.route)
    if sockets:
        await context.route_web_socket(re.compile('.*'), sockets)
    await context.add_init_script(AUTH + init)
    page = await context.new_page()
    page.on('pageerror', lambda e: errors.append(f'{url} {e}'))
    page.on('console', lambda m: errors.append(f'{url} {m.text}') if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
    await page.goto(url)
    return context, page


async def design(browser, output: Path, problems: list, errors: list, checks: list) -> int:
    """深色设计稿比对、颜色 token 与正文对比度、气泡与通知取深色 token、深色截图。@return 比对组数。"""
    compared = 0
    # ---------- 外壳与账号 ----------
    context, page = await open_dark(browser, account_design.fixture_with_states(), BASE + '/', 1440, errors)
    await expect(page.locator('.account-card-grid > .account-card')).to_have_count(12)
    await account_design.settle(page)
    assert await page.evaluate(SCHEME) == 'dark'
    mock = await open_mock(browser, 'accounts')
    pairs, known = screen_pairs(account_design, 'accounts')
    compared += await compare(mock, page, pairs, known, account_design.SCRIPT, 'accounts', problems)
    await scan(page, '#console-content', 'accounts', problems)
    await page.screenshot(animations='disabled', path=str(output / 'accounts-1440.png'))
    await page.locator('.account-card-grid > .account-card').first.get_by_role('button', name='编辑', exact=True).click()
    workspace = page.locator(account_design.EDIT)
    await expect(workspace).to_be_visible()
    await account_design.settle(page, workspace)
    await mock.goto(f'{MOCK}?mode=dark&s=account-edit#account-edit')
    pairs, known = screen_pairs(account_design, 'account-edit')
    compared += await compare(mock, page, pairs, known, account_design.SCRIPT, 'account-edit', problems)
    await scan(page, account_design.EDIT, 'account-edit', problems)
    await page.screenshot(animations='disabled', path=str(output / 'account-edit-1440.png'))
    await context.close()
    # 外壳：沿用 verify_ui_shell 的夹具状态（有新版本、运行中任务 1 个）对深色稿 #accounts 比对。
    context, page = await open_dark(browser, shell_design.ShellFixture('normal'), BASE + '/', 1440, errors)
    await expect(page.locator('.console-sidebar .brand-update')).to_have_class('brand-update has-update', timeout=12000)
    await expect(page.locator('.console-sidebar .navigation-running')).to_be_visible()
    await page.evaluate('document.fonts.ready')
    await mock.goto(f'{MOCK}?mode=dark&s=accounts#accounts')
    compared += await compare(mock, page, shell_design.SIDEBAR_PAIRS, shell_design.KNOWN, shell_design.SAMPLE, 'shell', problems)
    await scan(page, '.console-sidebar', 'shell', problems)
    await mock.close()
    await context.close()

    # ---------- 390 移动端：应用栏与账号页 ----------
    context, page = await open_dark(browser, account_design.fixture_with_states(), BASE + '/', 390, errors)
    await expect(page.locator('.toolbar-page')).to_have_text('账号管理')
    await account_design.settle(page)
    mock = await open_mock(browser, 'mobile', 390, 844)
    compared += await compare(mock, page, shell_design.MOBILE_PAIRS, shell_design.KNOWN, shell_design.SAMPLE, 'mobile', problems)
    pairs, known = screen_pairs(account_design, 'mobile')
    compared += await compare(mock, page, pairs, known, account_design.SCRIPT, 'mobile', problems)
    await page.screenshot(animations='disabled', path=str(output / 'accounts-390.png'))
    # 抽屉里同样有快捷切换，名称随深浅变化。
    await page.get_by_role('button', name='打开主导航').click()
    drawer = page.locator('.mobile-navigation-panel')
    await expect(drawer.locator('.sidebar-theme-toggle')).to_have_attribute('aria-label', '切换到浅色')
    await account_design.settle(page, drawer)
    await scan(page, '.mobile-navigation-panel', 'drawer', problems)
    await page.screenshot(animations='disabled', path=str(output / 'drawer-390.png'))
    await mock.close()
    await context.close()

    # ---------- 请求记录：比对、气泡取深色 token ----------
    context, page = await open_dark(browser, records_design.records_fixture(), BASE + '/requests', 1440, errors)
    await expect(page.locator('.request-records tbody tr').first).to_be_visible()
    await records_design.settle(page)
    mock = await open_mock(browser, 'requests')
    pairs, known = screen_pairs(records_design, 'requests')
    compared += await compare(mock, page, pairs, known, records_design.SCRIPT, 'requests', problems)
    await scan(page, '#console-content', 'requests', problems)
    await page.screenshot(animations='disabled', path=str(output / 'requests-1440.png'))
    await page.locator('tbody .request-account-identity button').first.hover()
    bubble = page.locator('.fui-info-content').first
    await expect(bubble).to_be_visible()
    await page.evaluate(native_design.SETTLED)
    # 气泡（kit.css 浮层组）取卡片底与次要正文，靠深色阴影的亮描边与页面区分。
    colors = await bubble.evaluate("e => [getComputedStyle(e).backgroundColor, getComputedStyle(e).color, getComputedStyle(e).boxShadow]")
    expected = [await page.evaluate(TOKEN, '--ui-color-surface'), await page.evaluate(TOKEN, '--ui-color-text-2')]
    if colors[:2] != expected or 'rgba(255, 255, 255, 0.07)' not in colors[2]:
        problems.append(f'气泡取色 {colors} 期望 {expected} 与亮描边')
    await scan(page, '.fui-info-content', 'tooltip', problems)
    await page.screenshot(animations='disabled', path=str(output / 'tooltip-1440.png'))
    await mock.close()
    await context.close()
    checks.append('外壳、账号、账号编辑、390 应用栏与账号页、请求对深色设计稿比对；气泡底色取深色卡片底')

    # ---------- 系统更新与进度 ----------
    fixture = UpdateFixture()
    context, page = await open_dark(browser, fixture, UPDATE_BASE, 1440, errors)
    await page.locator('.console-sidebar .brand-update').click()
    dialog = page.locator(update_design.DIALOG)
    await expect(dialog.locator('[data-update-view=overview]')).to_be_visible()
    await account_design.settle(page, dialog)
    mock = await open_mock(browser, 'update')
    pairs, known = screen_pairs(update_design, 'update')
    compared += await compare(mock, page, pairs, known, update_design.SCRIPT, 'update', problems)
    await scan(page, update_design.DIALOG, 'update', problems)
    await page.screenshot(animations='disabled', path=str(output / 'update-1440.png'))
    fixture.state.update(busy=True, operation={'operation_id': 'synthetic-dark-operation', 'action': 'install', 'phase': 'draining',
        'target_release': 'system-ci-101-1', 'created_at': '2026-11-11T00:00:00Z', 'updated_at': '2026-11-11T00:00:05Z',
        'blockers': ['合成长流', '合成 CLI 作业'], 'error': None,
        'steps': [{'phase': 'preparing', 'at': '2026-11-11T00:00:00Z'}, {'phase': 'draining', 'at': '2026-11-11T00:00:05Z'}]})
    await expect(dialog.locator('[data-update-view=progress] [data-state=active]')).to_be_visible(timeout=15000)
    await account_design.settle(page, dialog)
    await mock.goto(f'{MOCK}?mode=dark&s=update-progress#update-progress')
    pairs, known = screen_pairs(update_design, 'update-progress')
    compared += await compare(mock, page, pairs, known, update_design.SCRIPT, 'update-progress', problems)
    await scan(page, update_design.DIALOG, 'update-progress', problems)
    await page.screenshot(animations='disabled', path=str(output / 'update-progress-1440.png'))
    await mock.close()
    await context.close()

    # ---------- 任务与工程、运行环境：比对、部件一致性、颜色只取 token ----------
    dark = DarkBrowser(browser)
    page, context = await native_design.open_page(dark, WorkspaceFixture(), '/tasks', 1440, errors)
    root = await native_design.open_tasks(page)
    assert await page.evaluate(SCHEME) == 'dark'
    mock = await open_mock(browser, 'tasks')
    pairs, known = screen_pairs(native_design, 'tasks')
    compared += await compare(mock, page, pairs, known, native_design.SCRIPT, 'tasks', problems)
    compared += await native_design.parity(page, problems)
    await native_design.tokens_only(page, '.task-runtime', 'tasks-accounts', problems)
    await scan(page, '.task-runtime', 'tasks-accounts', problems)
    await page.screenshot(animations='disabled', full_page=True, path=str(output / 'tasks-accounts-1440.png'))
    for tab in ('projects', 'warmup', 'tasks', 'runs', 'topics'):
        await root.locator(f'.work-navigation a[data-tab={tab}]').click()
        await native_design.open_tasks(page, tab)
        await native_design.tokens_only(page, '.task-runtime', f'tasks-{tab}', problems)
        await scan(page, '.task-runtime', f'tasks-{tab}', problems)
        await page.screenshot(animations='disabled', full_page=True, path=str(output / f'tasks-{tab}-1440.png'))
    await context.close()
    page, context = await native_design.open_page(dark, WorkspaceFixture(), '/environments', 1440, errors)
    await expect(page.locator('.environment-rich')).to_have_count(4)
    await native_design.settle(page)
    await mock.goto(f'{MOCK}?mode=dark&s=environments#environments')
    pairs, known = screen_pairs(native_design, 'environments')
    compared += await compare(mock, page, pairs, known, native_design.SCRIPT, 'environments', problems)
    await scan(page, '#console-content', 'environments', problems)
    await page.screenshot(animations='disabled', path=str(output / 'environments-1440.png'))
    await mock.close()
    await context.close()
    for path, name in (('/tasks', 'tasks'), ('/environments', 'environments')):
        page, context = await native_design.open_page(dark, WorkspaceFixture(), path, 390, errors)
        await (native_design.open_tasks(page) if name == 'tasks' else expect(page.locator('.environment-rich').first).to_be_visible())
        await native_design.settle(page)
        await native_design.no_overflow(page, f'{name}-390')
        await page.screenshot(animations='disabled', full_page=True, path=str(output / f'{name}-390.png'))
        await context.close()
    checks.append('任务与工程、运行环境对深色设计稿比对，原生部件与组件库一致，六个页签颜色只取 token')

    # ---------- 主题设置：深色稿为深海蓝草稿、深色模式、2 处修改 ----------
    context, page, _fixture = await theme_design.open_console(dark, 1440, 900, errors)
    await page.goto(BASE + '/theme')
    await theme_design.preview_frame(page)
    await page.locator('[data-preset=ocean]').click()
    await page.locator('.theme-mode [role=radio][value=dark]').click()
    await expect(page.locator('.fui-page-header [data-theme-sync]')).to_have_text('2 处修改待应用')
    await page.evaluate(native_design.SETTLED)
    mock = await open_mock(browser, 'theme')
    compared += await compare(mock, page, theme_design.PAIRS, {}, theme_design.SAMPLE, 'theme', problems)
    # 深色下预设色块按派生规则提亮，与设计稿一致。
    for index, preset in enumerate(['petal', 'ocean', 'teal', 'dusk', 'rose', 'graphite']):
        expected = await mock.locator('.th-presets i').nth(index).evaluate("e => getComputedStyle(e).backgroundImage")
        actual = await page.locator(f'[data-preset={preset}] i').evaluate("e => getComputedStyle(e).backgroundImage")
        if expected != actual:
            problems.append(f'theme 预设 {preset}: 设计稿 {expected} 产品 {actual}')
    await scan(page, '#console-content', 'theme', problems)
    await page.screenshot(animations='disabled', path=str(output / 'theme-1440.png'))
    await mock.close()
    await context.close()
    checks.append('主题设置对深色设计稿比对（深海蓝草稿 + 深色模式 = 2 处修改），预设色块取深色派生值')

    # ---------- 授权登录终端：容器墨色、xterm 文字与 ANSI 色取终端 token，切换深浅不重建 ----------
    compared += await terminal(browser, output, problems, errors, checks)
    return compared


async def terminal(browser, output: Path, problems: list, errors: list, checks: list) -> int:
    """任务账号授权弹窗里的登录终端。@return 比对组数。"""
    fixture = LoginFixture()
    fixture.fail_start = False
    # 终端连上后推一段 ANSI 输出：红、绿、黄、蓝、品红、青、暗色与普通文字各一段。
    sample = '\x1b[31mRED\x1b[0m \x1b[32mGREEN\x1b[0m \x1b[33mYELLOW\x1b[0m \x1b[34mBLUE\x1b[0m \x1b[35mMAGENTA\x1b[0m \x1b[36mCYAN\x1b[0m \x1b[90mDIM\x1b[0m PLAIN\r\n'
    sockets = []

    def accept(ws) -> None:
        """接管终端连接：只连不回，连上后由脚本推送输出。@param ws 模拟连接。@return 无。"""
        ws.on_message(lambda _message: None)
        sockets.append(ws)

    context, page = await open_dark(browser, fixture, BASE + '/tasks', 1440, errors, height=1000, sockets=accept)
    runtime = page.locator('.task-runtime')
    await runtime.locator('#add-account').click()
    modal = runtime.locator('#acc-modal')
    await modal.locator('[name=name]').fill('dark-login')
    await modal.get_by_role('button', name='开始授权', exact=True).click()
    host = modal.locator('#acc-login-xterm')
    await expect(modal.locator('#acc-login-connection-status')).to_contain_text('已连接')
    sockets[-1].send(sample.encode())
    await expect(host.locator('.xterm-rows')).to_contain_text('PLAIN')
    await native_design.settle(page)
    mock = await open_mock(browser, 'terminal')
    pairs = [('.term', '#acc-modal #acc-login-xterm', ['background-color']), ('.term pre', '#acc-login-xterm .xterm-rows', ['color'])]
    compared = await compare(mock, page, pairs, {}, native_design.SCRIPT, 'terminal', problems)
    spans = '''(rows, words) => Object.fromEntries(words.map(word => { const span = [...rows.querySelectorAll('span')].find(e => e.textContent === word); return [word, span ? getComputedStyle(span).color : null]; }))'''
    words = {'RED': 'red', 'GREEN': 'green', 'YELLOW': 'yellow', 'BLUE': 'blue', 'MAGENTA': 'magenta', 'CYAN': 'cyan', 'DIM': 'dim'}
    colors = await host.locator('.xterm-rows').evaluate(spans, list(words))
    for word, token in words.items():
        expected = await page.evaluate(TOKEN, f'--ui-color-term-{token}')
        if colors[word] != expected:
            problems.append(f'terminal {word}: 期望 {expected} 实际 {colors[word]}')
    viewport = await host.locator('.xterm-viewport').evaluate("e => getComputedStyle(e).backgroundColor")
    if viewport != 'rgba(0, 0, 0, 0)':
        problems.append(f'terminal 视口底色应透明: {viewport}')
    await page.screenshot(animations='disabled', path=str(output / 'terminal-1440.png'))
    # 切到浅色：容器底色随墨色变化，已打开的终端文字色不变（两种模式相同），无需重建。
    before = await host.locator('.xterm-rows').evaluate("e => getComputedStyle(e).color")
    await page.emulate_media(color_scheme='light')
    await wait_scheme(page, 'light')
    background = await host.evaluate("e => getComputedStyle(e).backgroundColor")
    if background != await page.evaluate(TOKEN, '--ui-color-ink') or await host.locator('.xterm-rows').evaluate("e => getComputedStyle(e).color") != before:
        problems.append(f'terminal 切换浅色后底色 {background} 或文字色变化')
    await page.screenshot(animations='disabled', path=str(output / 'terminal-light-1440.png'))
    await mock.close()
    await context.close()
    checks.append('授权登录终端：容器墨色、xterm 文字与七种 ANSI 色取终端 token、视口透明，切换深浅后已打开的终端无需重建')
    return compared


async def modes(browser, output: Path, problems: list, errors: list, checks: list) -> None:
    """主题模式行为。@return 无。"""
    # ---------- 跟随系统：控制台、内嵌任务页实时切换，文档身份不变 ----------
    context = await browser.new_context(viewport={'width': 1440, 'height': 900}, color_scheme='light')
    await context.route('**/*', WorkspaceFixture().route)
    await context.add_init_script(AUTH)
    page = await context.new_page()
    page.on('pageerror', lambda e: errors.append(f'follow {e}'))
    await page.goto(BASE + '/tasks')
    root = await native_design.open_tasks(page)
    await root.evaluate("node => { node.__darkIdentity = 'stable'; }")
    assert await page.evaluate(SCHEME) == 'light'
    light_card = await root.locator('.work-account').evaluate("e => getComputedStyle(e).backgroundColor")
    await page.emulate_media(color_scheme='dark')
    await wait_scheme(page, 'dark')
    dark_card = await root.locator('.work-account').evaluate("e => getComputedStyle(e).backgroundColor")
    assert dark_card == await page.evaluate(TOKEN, '--ui-color-surface') and dark_card != light_card, (light_card, dark_card)
    assert await root.evaluate("node => node.__darkIdentity === 'stable'"), '跟随系统不应重建任务页'
    assert await page.locator('.console-sidebar .sidebar-theme-toggle').get_attribute('aria-label') == '切换到浅色'
    await page.emulate_media(color_scheme='light')
    await wait_scheme(page, 'light')
    assert await page.evaluate(f'localStorage.getItem({json.dumps(MODE_KEY)})') is None
    checks.append('跟随系统：切换系统深浅，控制台与内嵌任务页无需刷新即切换，不写模式存储')

    # ---------- 侧栏快捷切换：保存明确模式，刷新保持 ----------
    toggle = page.locator('.console-sidebar .sidebar-theme-toggle')
    await expect(toggle).to_have_attribute('aria-label', '切换到深色')
    await toggle.click()
    assert await page.evaluate(SCHEME) == 'dark'
    assert await page.evaluate(f'localStorage.getItem({json.dumps(MODE_KEY)})') == 'dark'
    await expect(toggle).to_have_attribute('aria-label', '切换到浅色')
    await page.reload()
    await native_design.open_tasks(page)
    assert await page.evaluate(SCHEME) == 'dark', '刷新后应保持深色（系统为浅色）'
    await page.screenshot(animations='disabled', path=str(output / 'toggle-dark-1440.png'))
    await toggle.click()
    assert await page.evaluate(SCHEME) == 'light'
    assert await page.evaluate(f'localStorage.getItem({json.dumps(MODE_KEY)})') == 'light'
    # 明确选择浅色后，系统切到深色不再跟随。
    await page.emulate_media(color_scheme='dark')
    await page.wait_for_timeout(200)
    assert await page.evaluate(SCHEME) == 'light'
    await context.close()
    checks.append('侧栏快捷切换：按当前深浅切到另一种并保存为明确模式，刷新保持，明确模式不再跟随系统')

    # ---------- 首帧：脚本模块不执行时，内联脚本与样式表已给出所选深浅 ----------
    for system, stored, expected in (('dark', None, 'dark'), ('dark', 'light', 'light'), ('light', 'dark', 'dark'), ('dark', 'purple', 'dark'), ('light', 'purple', 'light')):
        context = await browser.new_context(viewport={'width': 1440, 'height': 900}, color_scheme=system)
        await context.route('**/*', WorkspaceFixture().route)
        await context.route(re.compile(r'/assets/index-[^/]+\.js$'), lambda route: route.abort())
        init = AUTH + (f'localStorage.setItem({json.dumps(MODE_KEY)},{json.dumps(stored)});' if stored else '')
        # 记录 body 刚插入时根上的深浅：此刻只有 head 里的内联脚本执行过。
        init += "new MutationObserver((_, observer) => { if (document.body) { window.__firstScheme = document.documentElement.dataset.uiScheme; observer.disconnect(); } }).observe(document, { childList: true, subtree: true });"
        await context.add_init_script(init)
        page = await context.new_page()
        await page.goto(BASE + '/')
        first = await page.evaluate('window.__firstScheme')
        body = await page.evaluate("getComputedStyle(document.body).backgroundColor")
        layout = await page.evaluate(TOKEN, '--ui-color-layout')
        expected_layout = 'rgb(15, 16, 24)' if expected == 'dark' else 'rgb(245, 246, 250)'
        if first != expected or body != expected_layout or layout != expected_layout:
            problems.append(f'首帧 系统{system} 存储{stored}: 根 {first} 页面底 {body} layout {layout}')
        await context.close()
    checks.append('首帧：模块脚本被拦截时，body 插入前根标记与页面底色已是所选深浅；模式存储被篡改时按跟随系统处理')

    # ---------- 模式存储写入失败：提示失败，界面仍按本次选择 ----------
    context, page = await shell_design.open_console(browser, 'normal', 1440, 900, errors)
    await context.add_init_script(f"const setItem = Storage.prototype.setItem; Storage.prototype.setItem = function (key, value) {{ if (key === {json.dumps(MODE_KEY)}) throw new Error('denied'); return setItem.call(this, key, value); }};")
    await page.goto(BASE + '/')
    await page.locator('.console-sidebar .sidebar-theme-toggle').click()
    assert await page.evaluate(SCHEME) == 'dark'
    notice = page.locator('.fui-notice', has_text='当前浏览器无法保存主题模式')
    await expect(notice).to_be_visible()
    await page.evaluate(native_design.SETTLED)
    colors = await notice.evaluate("e => [getComputedStyle(e).backgroundColor, getComputedStyle(e).color]")
    if colors != [await page.evaluate(TOKEN, '--ui-color-feedback-surface'), await page.evaluate(TOKEN, '--ui-color-feedback-text')]:
        problems.append(f'通知取色 {colors}')
    await page.screenshot(animations='disabled', path=str(output / 'notice-dark-1440.png'))
    await context.close()
    checks.append('模式存储写入失败时提示且界面按本次选择切到深色；通知取深色反馈 token')

    # ---------- 独立 /runtime/ 文档：跟随模式与系统，配色只用默认主题 ----------
    context = await browser.new_context(viewport={'width': 1440, 'height': 900}, color_scheme='light')
    await context.route('**/*', WorkspaceFixture().route)
    await context.add_init_script(AUTH + f"localStorage.setItem('flower2api.theme',{json.dumps(json.dumps(native_design.THEME))});")
    page = await context.new_page()
    page.on('pageerror', lambda e: errors.append(f'runtime {e}'))
    await page.goto(BASE + '/runtime/#accounts')
    await expect(page.locator('.work-account')).to_have_count(1)
    assert await page.evaluate(SCHEME) == 'light'
    await page.emulate_media(color_scheme='dark')
    await wait_scheme(page, 'dark')
    primary = await page.evaluate(TOKEN, '--ui-color-primary')
    if primary != 'rgb(114, 90, 187)':
        problems.append(f'独立文档深色主色应为默认派生值: {primary}')
    await page.evaluate(f'localStorage.setItem({json.dumps(MODE_KEY)},"light")')
    await page.reload()
    await expect(page.locator('.work-account')).to_have_count(1)
    assert await page.evaluate(SCHEME) == 'light', '独立文档应按保存的浅色模式显示'
    await page.screenshot(animations='disabled', path=str(output / 'runtime-light-1440.png'))
    await context.close()
    checks.append('独立 /runtime/ 文档跟随系统与保存的模式，深色主色为默认派生值、不应用自定义种子')

    # ---------- 主题设置页：模式属于草稿 ----------
    context, page, _fixture = await theme_design.open_console(browser, 1440, 900, errors)
    await page.goto(BASE + '/theme')
    frame = await theme_design.preview_frame(page)
    sync = page.locator('.fui-page-header [data-theme-sync]')
    mode = lambda value: page.locator(f'.theme-mode [role=radio][value={value}]')
    await expect(mode('system')).to_have_attribute('aria-checked', 'true')
    await mode('dark').click()
    await expect(sync).to_have_text('1 处修改待应用')
    await wait_scheme(frame, 'dark')
    assert await page.evaluate(SCHEME) == 'light', '草稿模式不应影响控制台'
    await expect(frame.locator('.console-sidebar')).to_have_css('background-color', 'rgb(23, 24, 36)')
    await expect(frame.locator('.console-sidebar .sidebar-theme-toggle')).to_have_attribute('aria-label', '切换到浅色')
    await page.screenshot(animations='disabled', path=str(output / 'theme-draft-dark-1440.png'))
    await page.locator('.fui-page-header').get_by_role('button', name='撤销草稿').click()
    await expect(sync).to_have_text('已同步')
    await wait_scheme(frame, 'light')
    # 草稿跟随系统时画板随系统切换。
    await page.emulate_media(color_scheme='dark')
    await wait_scheme(frame, 'dark')
    await wait_scheme(page, 'dark')
    await page.emulate_media(color_scheme='light')
    await wait_scheme(frame, 'light')
    # 保存：控制台切到深色并写入存储。
    await mode('dark').click()
    await page.locator('.fui-page-header').get_by_role('button', name='保存并应用').click()
    await expect(sync).to_have_text('已同步')
    assert await page.evaluate(SCHEME) == 'dark'
    assert await page.evaluate(f'localStorage.getItem({json.dumps(MODE_KEY)})') == 'dark'
    # 侧栏切换：草稿与已保存一致时同步跟随。
    await page.locator('.console-sidebar .sidebar-theme-toggle').click()
    await expect(mode('light')).to_have_attribute('aria-checked', 'true')
    await expect(sync).to_have_text('已同步')
    # 草稿与已保存不同时保留为待应用修改。
    await mode('system').click()
    await page.locator('.console-sidebar .sidebar-theme-toggle').click()
    await expect(mode('system')).to_have_attribute('aria-checked', 'true')
    await expect(sync).to_have_text('1 处修改待应用')
    # 恢复默认：模式回到跟随系统、种子回到默认；保存后删除模式键。
    # 此时已保存的模式为深色（上一步侧栏切换），草稿选浅色与深海蓝共 2 处修改。
    await page.locator('[data-preset=ocean]').click()
    await mode('light').click()
    await expect(sync).to_have_text('2 处修改待应用')
    await page.locator('.fui-page-header').get_by_role('button', name='恢复默认').click()
    await expect(mode('system')).to_have_attribute('aria-checked', 'true')
    await expect(page.locator('[data-preset=petal]')).to_have_attribute('aria-pressed', 'true')
    await expect(sync).to_have_text('1 处修改待应用')
    await page.locator('.fui-page-header').get_by_role('button', name='保存并应用').click()
    await expect(sync).to_have_text('已同步')
    assert await page.evaluate(f'localStorage.getItem({json.dumps(MODE_KEY)})') is None
    assert await page.evaluate(SCHEME) == 'light'
    # 离开保护计入模式草稿。
    await mode('dark').click()
    await page.locator('.console-sidebar').get_by_role('link', name='系统设置', exact=True).click()
    confirm = page.locator('.fui-confirm-dialog')
    await expect(confirm).to_be_visible()
    await confirm.get_by_role('button', name='取消').click()
    await expect(page).to_have_url(BASE + '/theme')
    await context.close()
    checks.append('主题设置页：模式计入草稿与待应用数，画板随草稿与系统变化而控制台不变，保存、撤销、恢复默认、侧栏同步与离开保护按约定')


async def main(output: Path) -> None:
    """运行全部深色模式验证。@param output 截图与结果目录。@return 无。"""
    output.mkdir(parents=True, exist_ok=True)
    errors, problems, checks = [], [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        compared = await design(browser, output, problems, errors, checks)
        dialogs_output = output / 'dialogs'
        dialogs_output.mkdir(exist_ok=True)
        # 21 个深层弹窗在深色下：外壳、颜色只取 token、底栏、控件与组件库一致，1440 / 390 无溢出。
        compared += await native_design.dialogs(DarkBrowser(browser), dialogs_output, errors, problems, checks)
        await modes(browser, output, problems, errors, checks)
        await browser.close()
    checks.append('正文对比度抽样（正文类文字色对逐层合成的实际底色 ≥ 4.5）：' + '、'.join(f'{label} {count}' for label, count in SCANNED))
    result = {'passed': not problems and not errors, 'compared': compared, 'checks': checks, 'problems': problems, 'errors': errors}
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps(result, ensure_ascii=False, indent=1))
    assert not problems and not errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/console-ui-revamp/dark-mode/verify')
    asyncio.run(main(parser.parse_args().output))
