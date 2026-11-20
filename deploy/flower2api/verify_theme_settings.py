"""验证主题设置页：侧栏入口与 /theme 直达、预设与参数编辑、隔离预览画板（真实首页 iframe）、待应用数与「已修改」、
单项恢复 / 撤销草稿 / 恢复默认、保存并应用与刷新首屏、保存默认清除存储、输入校验、存储损坏与写入失败、离开保护、
画板缩放平移与只读、画板内不重复检查更新，以及 1440 对 mock.html#theme 的计算样式比对与 390 单列布局。
需先构建前端（npm --prefix apps/web run build）；只使用合成接口，不访问真实服务。"""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_environment_ui import BASE, ROOT
from verify_ui_shell import ShellFixture

MOCK = (ROOT / 'doc/design/console-v2/mock.html').as_uri()
STORAGE_KEY = 'flower2api.theme'
DEFAULT_PRIMARY = '#6c54b4'
# 预设主色经派生后不变的几个（玫瑰红白字不足会压暗主色，单独只断言发生变化）。
STABLE_PRESETS = {'ocean': '#2f6bd8', 'teal': '#0f9f8f', 'dusk': '#e2742b', 'graphite': '#3d4352', 'petal': DEFAULT_PRIMARY}
TEXT = ['color', 'font-size', 'font-weight']
# (设计稿选择器, 控制台选择器, 属性)；画面为 mock.html#theme（深海蓝草稿、1 处修改），1440×900。
PAIRS = [
    ('.ph p .dirty', '.fui-page-header [data-theme-sync]', TEXT + ['margin-left', 'column-gap']),
    ('.th', '.theme-layout', ['column-gap']),
    ('.th-panel', '.theme-panel', ['width', 'padding-top', 'padding-left', 'row-gap', 'border-top-left-radius', 'background-color', 'box-shadow']),
    ('.th-group h5', '.theme-group h2', ['font-size', 'font-weight']),
    ('.th-presets', '.theme-presets', ['column-gap', 'row-gap']),
    ('.th-presets div:not(.on)', '.theme-presets button[aria-pressed=false]', ['padding-top', 'padding-left', 'padding-bottom', 'border-top-left-radius', 'background-color', 'row-gap']),
    ('.th-presets i', '.theme-presets i', ['height', 'border-top-left-radius', 'margin-bottom']),
    ('.th-presets b', '.theme-presets b', ['font-size', 'font-weight']),
    ('.th-presets small', '.theme-presets small', TEXT),
    ('.th-presets svg', '.theme-presets svg', ['right', 'bottom']),
    ('.tf', '.theme-color-field', ['padding-top', 'padding-left', 'border-top-left-radius', 'background-color', 'column-gap']),
    ('.tf i', '.theme-swatch', ['width', 'height']),
    ('.tf b', '.theme-field-label label', ['font-size', 'font-weight']),
    ('.tf b .tag', '.theme-field-label .fui-badge', ['height', 'padding-left', 'font-size', 'background-color', 'color']),
    ('.tf small', '.theme-field-text small', TEXT),
    ('.th-preview', '.theme-preview', ['padding-top', 'padding-left', 'row-gap', 'border-top-left-radius', 'box-shadow']),
    ('.th-preview .tb p', '.theme-preview-head p', TEXT + ['margin-top']),
    ('.zoom', '.theme-zoom', ['padding-top', 'column-gap', 'border-top-left-radius', 'background-color']),
    ('.zoom span', '.theme-zoom button', ['height', 'min-width', 'border-top-left-radius', 'font-size', 'font-weight', 'color']),
    ('.canvas', '.theme-canvas', ['border-top-left-radius']),
    ('.canvas .hint', '.theme-canvas-hint', TEXT + ['left', 'bottom']),
]
SAMPLE = '(e, names) => Object.fromEntries(names.map(n => [n, getComputedStyle(e).getPropertyValue(n)]))'
ROOT_VAR = "name => getComputedStyle(document.documentElement).getPropertyValue(name).trim()"


class ThemeFixture(ShellFixture):
    """在外壳夹具上登记 /theme 页面地址，并记录预览画板（子框架）发出的非 GET 请求。"""

    def __init__(self):
        """初始化常规更新场景。@return None。"""
        super().__init__('normal')
        self.frame_writes = []
        # 首页第一页放一个可用的反重力账号：直接打开账号页会自动刷新它的额度，预览画板里不得刷新。
        self.accounts[11].update(platform='antigravity', name='画板反重力账号', credential_state={'phase': 'ready', 'generation': 1})

    async def route(self, route):
        """提供 /theme 页面并记录子框架写请求。@param route 浏览器路由。@return None。"""
        request = route.request
        path = urlsplit(request.url).path
        try:
            nested = request.frame.parent_frame is not None
        except Exception:  # 导航请求的框架可能尚未就绪，按顶层处理。
            nested = False
        if nested and request.method != 'GET':
            self.frame_writes.append(f'{request.method} {path}')
        if path in ('/theme', '/theme/'):
            return await route.fulfill(path=str(ROOT / 'apps/web/dist/index.html'), content_type='text/html')
        return await super().route(route)


async def open_console(browser, width: int, height: int, errors: list, init: str = ''):
    """以合成夹具打开真实构建。@param init 额外的初始化脚本（篡改存储等）。@return (上下文, 页面, 夹具)。"""
    fixture = ThemeFixture()
    context = await browser.new_context(viewport={'width': width, 'height': height})
    await context.route('**/*', fixture.route)
    await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');" + init)
    page = await context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    return context, page, fixture


async def preview_frame(page):
    """等待预览画板载入首页外壳并返回其框架。@param page 主题设置页。@return 画板框架。"""
    await expect(page.frame_locator('.theme-artboard iframe').locator('.console-shell')).to_be_visible(timeout=15000)
    await expect(page.locator('.theme-canvas-loading')).to_have_count(0)
    return next(frame for frame in page.frames if 'theme-preview=1' in frame.url)


async def wait_var(target, name: str, expected: str) -> None:
    """轮询根上的变量直到等于期望值。@param target 页面或框架。@param name 变量名。@param expected 期望值。@return None。"""
    value = None
    for _ in range(40):
        value = await target.evaluate(ROOT_VAR, name)
        if value == expected:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f'{name}: 期望 {expected}，实际 {value}')


async def sync_text(page) -> str:
    """读取页头的同步状态文字。@param page 页面。@return 文字。"""
    return (await page.locator('.fui-page-header [data-theme-sync]').text_content()).strip()


async def stored(page):
    """读取浏览器保存的主题。@param page 页面。@return 解析后的种子或 None。"""
    raw = await page.evaluate('key => localStorage.getItem(key)', STORAGE_KEY)
    return json.loads(raw) if raw else None


async def compare(mock, page, problems: list) -> int:
    """逐项比对设计稿与控制台。@param mock 设计稿页。@param page 控制台页。@param problems 差异列表。@return 比对组数。"""
    for mock_selector, selector, props in PAIRS:
        expected = await mock.locator(mock_selector).first.evaluate(SAMPLE, props)
        observed = await page.locator(selector).first.evaluate(SAMPLE, props)
        problems.extend(f'{mock_selector} {prop}: 设计稿 {expected[prop]} 控制台 {observed[prop]}' for prop in props if expected[prop] != observed[prop])
    return len(PAIRS)


async def verify_desktop(browser, output: Path, problems: list, errors: list) -> dict:
    """1440：入口、预览隔离、编辑与计数、校验、保存与刷新、恢复默认、画板、离开保护与设计稿比对。@return 摘要。"""
    context, page, fixture = await open_console(browser, 1440, 900, errors)
    await page.goto(BASE + '/')
    await expect(page.locator('.console-sidebar .brand-update')).to_be_visible()
    # 入口：底部组为「主题设置」「系统设置」，点击后选中、地址为 /theme。
    system = page.locator('.console-sidebar .navigation-system .navigation-item')
    assert [text.strip() for text in await system.all_text_contents()] == ['主题设置', '系统设置']
    await page.locator('.console-sidebar').get_by_role('link', name='主题设置', exact=True).click()
    await expect(page).to_have_url(BASE + '/theme')
    await expect(page.locator('.console-sidebar .navigation-item.is-active')).to_have_text('主题设置')
    await expect(page.locator('#console-content h1')).to_have_text('主题设置')
    frame = await preview_frame(page)
    header = page.locator('.fui-page-header')
    undo, reset, save = (header.get_by_role('button', name=name) for name in ('撤销草稿', '恢复默认', '保存并应用'))
    assert await sync_text(page) == '已同步'
    for button in (undo, reset, save):
        await expect(button).to_be_disabled()
    await expect(page.locator('[data-preset=petal]')).to_have_attribute('aria-pressed', 'true')

    # 预设：草稿只进画板；逐个切换验证注入稳定，玫瑰红主色经压暗后只断言发生变化。
    for preset in ['ocean', 'teal', 'dusk', 'rose', 'graphite', 'petal', 'ocean']:
        await page.locator(f'[data-preset={preset}]').click()
        await expect(page.locator(f'[data-preset={preset}]')).to_have_attribute('aria-pressed', 'true')
        if preset in STABLE_PRESETS:
            await wait_var(frame, '--ui-color-primary', STABLE_PRESETS[preset])
        else:
            await wait_var(frame, '--ui-color-on-primary', '#ffffff')
            assert await frame.evaluate(ROOT_VAR, '--ui-color-primary') not in STABLE_PRESETS.values()
        assert await page.evaluate(ROOT_VAR, '--ui-color-primary') == DEFAULT_PRIMARY, f'{preset} 泄漏到画板外'
    # 按钮背景有 .15s 过渡，等过渡结束再读。
    await expect(frame.locator('.fui-button-default').first).to_have_css('background-color', 'rgb(47, 107, 216)')
    assert await sync_text(page) == '1 处修改待应用'
    primary_row = page.locator('[data-field=primary]')
    await expect(primary_row.locator('.fui-badge')).to_have_text('已修改')
    await expect(primary_row.locator('input.theme-hex')).to_have_value('#2f6bd8')
    await expect(save).to_be_enabled()

    # 设计稿比对与截图：设计稿 #theme 正是深海蓝草稿、1 处修改。
    mock = await browser.new_page(viewport={'width': 1440, 'height': 900})
    await mock.goto(f'{MOCK}?s=theme#theme')
    await mock.evaluate('document.fonts.ready')
    await page.evaluate('document.fonts.ready')
    compared = await compare(mock, page, problems)
    await mock.screenshot(path=str(output / 'mock-theme-1440.png'))
    await mock.close()
    await page.mouse.move(0, 0)
    await page.screenshot(path=str(output / 'theme-1440.png'), animations='disabled')
    layout = await page.evaluate("""() => { const panel = document.querySelector('.theme-panel').getBoundingClientRect(), preview = document.querySelector('.theme-preview').getBoundingClientRect();
        return { panel: panel.width, sameRow: Math.abs(panel.top - preview.top) < 1, overflow: document.documentElement.scrollWidth > innerWidth, bottom: Math.max(panel.bottom, preview.bottom), height: innerHeight }; }""")
    assert layout['panel'] == 340 and layout['sameRow'] and not layout['overflow'] and layout['bottom'] <= layout['height'], layout

    # 数值：改字号计数 +1，单项恢复后回到 1；越界、清空、步长不对齐都拒绝且不影响画板。
    category = page.get_by_role('radiogroup', name='参数分类')
    await category.get_by_role('radio', name='尺寸').click()
    font = page.locator('[name=theme-fontSize]')
    await font.fill('15')
    await wait_var(frame, '--ui-font-size-base', '15px')
    assert await sync_text(page) == '2 处修改待应用'
    await page.get_by_role('button', name='恢复已保存的基础字号').click()
    await wait_var(frame, '--ui-font-size-base', '13px')
    assert await sync_text(page) == '1 处修改待应用'
    for value, message in (('17', '请输入 12–16 之间的整数'), ('', '请输入 12–16 之间的整数'), ('13.5', '请输入 12–16 之间的整数')):
        await font.fill(value)
        await expect(page.locator('#theme-fontSize-error')).to_have_text(message)
        await expect(save).to_be_disabled()
        assert await frame.evaluate(ROOT_VAR, '--ui-font-size-base') == '13px'
    await expect(page.locator('[data-field=fontSize] .fui-badge')).to_have_text('已修改')
    await page.locator('.theme-panel').screenshot(path=str(output / 'theme-size-invalid-1440.png'), animations='disabled')
    # 无效输入不计入待应用数但单独说明；切到别的分类后，分类计数仍指出哪里有问题。
    size_count = category.get_by_role('radio', name='尺寸').locator('.fui-segmented-count')
    assert await sync_text(page) == '1 处修改待应用 · 1 项输入无效'
    await expect(page.locator('.fui-page-header [data-theme-sync]')).to_have_attribute('data-invalid', 'true')
    await category.get_by_role('radio', name='颜色').click()
    await expect(size_count).to_have_text('1')
    await expect(category.get_by_role('radio', name='颜色').locator('.fui-segmented-count')).to_have_text('1')
    await expect(category.get_by_role('radio', name='风格').locator('.fui-segmented-count')).to_have_count(0)
    await expect(save).to_be_disabled()
    await category.get_by_role('radio', name='尺寸').click()
    await page.get_by_role('button', name='恢复已保存的基础字号').click()
    await expect(page.locator('#theme-fontSize-error')).to_have_count(0)
    await expect(font).to_have_value('13')
    await expect(size_count).to_have_count(0)
    assert await sync_text(page) == '1 处修改待应用'
    await category.get_by_role('radio', name='风格').click()
    await page.locator('[name=theme-shadow]').fill('0.3')
    await expect(page.locator('#theme-shadow-error')).to_have_text('请输入 0–2 之间、步长 0.25 的数值')
    await page.locator('[name=theme-shadow]').fill('1.25')
    await expect(page.locator('#theme-shadow-error')).to_have_count(0)
    await wait_var(frame, '--ui-shadow-raised', '0 1px 3px rgba(14, 23, 38, 0.1)')
    await page.get_by_role('button', name='恢复已保存的阴影强度').click()
    await wait_var(frame, '--ui-shadow-raised', '0 1px 3px rgba(14, 23, 38, 0.08)')

    # hex：格式错误拒绝，#ABC 规整为 #aabbcc；取色器直接写入草稿。
    await category.get_by_role('radio', name='颜色').click()
    hex_input = primary_row.locator('input.theme-hex')
    await hex_input.fill('#12')
    await expect(page.locator('#theme-primary-error')).to_have_text('请输入 #rgb 或 #rrggbb 格式的颜色')
    await expect(save).to_be_disabled()
    assert await frame.evaluate(ROOT_VAR, '--ui-color-primary') == '#2f6bd8'
    await hex_input.fill('#ABC')
    await hex_input.press('Tab')
    await expect(hex_input).to_have_value('#aabbcc')
    await wait_var(frame, '--ui-color-primary', '#aabbcc')
    assert await page.locator('.theme-presets [aria-pressed=true]').count() == 0
    await page.locator('[data-field=success] .theme-swatch').fill('#00aa55')
    await wait_var(frame, '--ui-color-success', '#00aa55')
    assert await sync_text(page) == '2 处修改待应用'

    # 撤销草稿回到已保存（默认）主题；恢复默认在已是默认时禁用。
    await undo.click()
    assert await sync_text(page) == '已同步'
    await wait_var(frame, '--ui-color-primary', DEFAULT_PRIMARY)
    await wait_var(frame, '--ui-color-success', '#12b981')
    await expect(reset).to_be_disabled()

    # 保存：深海蓝 + 圆角 4，控制台立即生效并写入存储；刷新后首屏已是新主题。
    await page.locator('[data-preset=ocean]').click()
    await category.get_by_role('radio', name='风格').click()
    await page.locator('[name=theme-radius]').fill('4')
    assert await sync_text(page) == '2 处修改待应用'
    await save.click()
    await expect(page.locator('.fui-notice', has_text='主题已保存并应用')).to_be_visible()
    await wait_var(page, '--ui-color-primary', '#2f6bd8')
    await wait_var(page, '--ui-radius-control', '4px')
    seed = await stored(page)
    assert seed and seed['primary'] == '#2f6bd8' and seed['radius'] == 4 and seed['version'] == 1, seed
    assert await sync_text(page) == '已同步'
    await expect(reset).to_be_enabled()
    await page.reload(wait_until='domcontentloaded')
    inline = await page.evaluate("() => document.documentElement.style.getPropertyValue('--ui-color-primary')")
    assert inline == '#2f6bd8', f'首屏未应用已保存主题：{inline!r}'
    frame = await preview_frame(page)
    await expect(page.locator('[data-preset=ocean]')).to_have_attribute('aria-pressed', 'true')
    assert await sync_text(page) == '已同步'
    await wait_var(frame, '--ui-color-primary', '#2f6bd8')

    # 恢复默认只改草稿，保存后清除存储。
    await reset.click()
    assert await sync_text(page) == '2 处修改待应用'
    assert await page.evaluate(ROOT_VAR, '--ui-color-primary') == '#2f6bd8'
    await wait_var(frame, '--ui-color-primary', DEFAULT_PRIMARY)
    await save.click()
    await wait_var(page, '--ui-color-primary', DEFAULT_PRIMARY)
    assert await stored(page) is None
    await expect(reset).to_be_disabled()

    # 画板：按钮、滚轮、适应改变比例；拖动平移；iframe 不接收指针与焦点。
    zoom = page.locator('[data-theme-zoom]')
    fit_text = (await zoom.text_content()).strip()
    fit_value = int(fit_text.rstrip('%'))
    await page.get_by_role('button', name='放大').click()
    await expect(zoom).to_have_text(f'{fit_value + 10}%')
    await page.get_by_role('button', name='缩小').click()
    await page.get_by_role('button', name='缩小').click()
    await expect(zoom).to_have_text(f'{fit_value - 10}%')
    canvas = await page.locator('.theme-canvas').bounding_box()
    center = (canvas['x'] + canvas['width'] / 2, canvas['y'] + canvas['height'] / 2)
    await page.mouse.move(*center)
    await page.mouse.wheel(0, -100)
    await expect(zoom).to_have_text(f'{fit_value}%')
    before = await page.locator('.theme-artboard').bounding_box()
    await page.mouse.down()
    await page.mouse.move(center[0] + 60, center[1] + 40, steps=4)
    await page.mouse.up()
    after = await page.locator('.theme-artboard').bounding_box()
    assert abs(after['x'] - before['x'] - 60) < 1 and abs(after['y'] - before['y'] - 40) < 1, (before, after)
    await page.get_by_role('button', name='适应画布').click()
    await expect(zoom).to_have_text(fit_text)
    hit = await page.evaluate("([x, y]) => document.elementFromPoint(x, y).tagName", list(center))
    iframe = page.locator('.theme-artboard iframe')
    assert hit != 'IFRAME' and await iframe.get_attribute('inert') is not None and await iframe.get_attribute('tabindex') == '-1', hit
    # 子框架请求归属可用（画板外壳签发运行会话）；除会话签发外没有写请求，尤其没有检查更新。
    assert 'POST /admin/runtime/session' in fixture.frame_writes, fixture.frame_writes
    unexpected = sorted(set(fixture.frame_writes) - {'POST /admin/runtime/session'})
    assert not unexpected, f'画板发出写请求：{unexpected}'

    # 离开保护：有草稿时站内导航先确认；取消留下，确认离开；无草稿直接离开。
    await page.locator('[data-preset=teal]').click()
    accounts = page.locator('.console-sidebar').get_by_role('link', name='账号', exact=True)
    await accounts.click()
    dialog = page.get_by_role('dialog', name='放弃未保存的主题修改？')
    await expect(dialog).to_be_visible()
    await dialog.get_by_role('button', name='取消').click()
    await expect(dialog).to_have_count(0)
    await expect(page).to_have_url(BASE + '/theme')
    assert await sync_text(page) == '1 处修改待应用'
    await accounts.click()
    await page.get_by_role('dialog', name='放弃未保存的主题修改？').get_by_role('button', name='放弃并离开').click()
    await expect(page).to_have_url(BASE + '/')
    await page.locator('.console-sidebar').get_by_role('link', name='主题设置', exact=True).click()
    await preview_frame(page)
    assert await sync_text(page) == '已同步'
    await accounts.click()
    await expect(page).to_have_url(BASE + '/')
    assert await page.get_by_role('dialog').count() == 0

    # 刷新或关闭：有草稿触发原生 beforeunload，无草稿不触发。
    dialogs = []
    async def answer(native):
        dialogs.append(native.type)
        await native.dismiss()
    page.on('dialog', answer)
    await page.locator('.console-sidebar').get_by_role('link', name='主题设置', exact=True).click()
    await page.locator('[data-preset=dusk]').click()
    await page.close(run_before_unload=True)
    for _ in range(40):
        if dialogs:
            break
        await asyncio.sleep(0.05)
    assert dialogs == ['beforeunload'], dialogs
    assert not page.is_closed()
    await undo.click()
    await page.close(run_before_unload=True)
    for _ in range(40):
        if page.is_closed():
            break
        await asyncio.sleep(0.05)
    assert page.is_closed() and dialogs == ['beforeunload'], dialogs

    # 退出登录：有草稿也直接退出，不弹确认。
    page = await context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    await page.goto(BASE + '/theme')
    await preview_frame(page)
    await page.locator('[data-preset=dusk]').click()
    await page.locator('.sidebar-exit').click()
    await expect(page).to_have_url(BASE + '/login')
    await context.close()
    return {'compared': compared, 'fit': fit_text, 'frame_writes': sorted(set(fixture.frame_writes))}


async def verify_storage(browser, errors: list) -> dict:
    """存储损坏、越界回退默认；写入抛错时提示失败、控制台不变。@return 摘要。"""
    results = {}
    for name, init in (('损坏', f"localStorage.setItem('{STORAGE_KEY}','{{broken')"),
                       ('越界', f"localStorage.setItem('{STORAGE_KEY}',JSON.stringify({{version:1,primary:'#2f6bd8',success:'#12b981',warning:'#f59e0b',danger:'#ef4444',info:'#5983f4',surface:'default',fontSize:13,spaceUnit:4,controlHeight:38,sizeStep:6,radius:99,shadow:1}}))")):
        context, page, _ = await open_console(browser, 1440, 900, errors, init)
        await page.goto(BASE + '/theme')
        await preview_frame(page)
        assert await page.evaluate(ROOT_VAR, '--ui-color-primary') == DEFAULT_PRIMARY, name
        assert await sync_text(page) == '已同步', name
        await expect(page.locator('[data-preset=petal]')).to_have_attribute('aria-pressed', 'true')
        results[name] = 'default'
        await context.close()
    deny = f"const original = Storage.prototype.setItem; Storage.prototype.setItem = function (key, value) {{ if (key === '{STORAGE_KEY}') throw new Error('denied'); return original.call(this, key, value); }};"
    context, page, _ = await open_console(browser, 1440, 900, errors, deny)
    await page.goto(BASE + '/theme')
    await preview_frame(page)
    await page.locator('[data-preset=ocean]').click()
    await page.locator('.fui-page-header').get_by_role('button', name='保存并应用').click()
    await expect(page.locator('.fui-notice', has_text='当前浏览器无法保存主题')).to_be_visible()
    assert await page.evaluate(ROOT_VAR, '--ui-color-primary') == DEFAULT_PRIMARY
    assert await sync_text(page) == '1 处修改待应用'
    results['写入失败'] = 'unchanged'
    await context.close()
    return results


async def verify_mobile(browser, output: Path, errors: list) -> dict:
    """390：应用栏标题、可见同步状态、单列、画布 320 高、无横向溢出。@return 摘要。"""
    context, page, _ = await open_console(browser, 390, 844, errors)
    await page.goto(BASE + '/theme')
    await preview_frame(page)
    await expect(page.locator('.toolbar-page')).to_have_text('主题设置')
    await expect(page.locator('.theme-mobile-state')).to_have_text('已同步')
    await page.locator('[data-preset=ocean]').click()
    await expect(page.locator('.theme-mobile-state')).to_have_text('1 处修改待应用')
    layout = await page.evaluate("""() => { const panel = document.querySelector('.theme-panel').getBoundingClientRect(), preview = document.querySelector('.theme-preview').getBoundingClientRect();
        return { stacked: preview.top >= panel.bottom, sameLeft: Math.abs(panel.left - preview.left) < 1, canvas: document.querySelector('.theme-canvas').getBoundingClientRect().height,
          overflow: document.documentElement.scrollWidth > innerWidth }; }""")
    assert layout['stacked'] and layout['sameLeft'] and layout['canvas'] == 320 and not layout['overflow'], layout
    await page.screenshot(path=str(output / 'theme-390.png'), full_page=True, animations='disabled')
    await context.close()
    return layout


async def main() -> None:
    """运行全部场景并写出报告。@return None。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/console-ui-revamp/theme-settings/verify')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    assert (ROOT / 'apps/web/dist/index.html').is_file(), '先执行 npm --prefix apps/web run build'
    problems, errors = [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        report = {'desktop': await verify_desktop(browser, args.output, problems, errors),
                  'storage': await verify_storage(browser, errors),
                  'mobile': await verify_mobile(browser, args.output, errors)}
        await browser.close()
    report.update(problems=problems, errors=errors)
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    assert not problems, '\n'.join(problems)
    assert not errors, errors
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
