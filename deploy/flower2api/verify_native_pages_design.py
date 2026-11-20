"""对照第二版设计稿（mock.html #tasks、#environments）核对任务与工程、运行环境两页的计算样式，并验证：
原生部件（按钮、输入、选择、数字、搜索、页签、徽标、提示条、卡片、弹窗）与组件库同名部件外观一致；
保存的主题对原生页生效，独立 /runtime/ 文档保持默认主题；页面与深层弹窗的文字色、背景色只取 --ui-color-* token；
弹窗外壳圆角、阴影取 token；390 单列无横向溢出；零控制台错误。设计稿未画的画面（其余页签、深层弹窗、390 形态）截图供目视确认。
真实构建 + 合成接口，不触达外部服务。"""
import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_capture_workspace_design import CaptureFixture
from verify_console_ui import ConsoleFixture
from verify_environment_ui import BASE, ROOT
from verify_native_diagnostics_cpu import DiagnosticsCpuFixture
from verify_runtime_settings_design import SettingsFixture
from verify_runtime_workspace_design import WorkspaceFixture
from verify_task_feedback import TaskFeedbackFixture

MOCK = (ROOT / 'doc/design/console-v2/mock.html').as_uri()
DIST = ROOT / 'apps/web/dist'
TEXT = ['color', 'font-size', 'font-weight', 'font-family', 'line-height']
BOX = ['height', 'padding-left', 'border-top-left-radius', 'background-color', 'color', 'font-size', 'font-weight']
CARD = ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'row-gap']
SEG = ['background-color', 'padding-top', 'column-gap', 'border-top-left-radius']
FIELD = ['height', 'background-color', 'border-top-left-radius', 'border-top-width']
# 与设计稿逐项对照：(画面, 设计稿选择器, 页面选择器, 属性)
PAIRS = [
    # 任务与工程：页头、页签托盘、区块头、任务账号卡
    ('tasks', '.ph h1', '.runtime-heading h1', TEXT + ['letter-spacing']),
    ('tasks', '.ph p', '.runtime-heading > p:last-child', TEXT + ['margin-top']),
    ('tasks', '.seg', '.work-navigation', SEG),
    ('tasks', '.seg span.on', '.work-navigation a.active', BOX + ['box-shadow', 'column-gap']),
    ('tasks', '.seg span:not(.on)', '.work-navigation a:not(.active)', BOX),
    ('tasks', '.seg span.on em', '.work-navigation a.active .work-tab-count', ['font-size', 'font-weight', 'font-family', 'color']),
    ('tasks', '.tb .sec-t', '.work-list-head:has(#add-account) .work-list-title h2', ['font-size', 'font-weight', 'color']),
    ('tasks', '.tb p', '.work-list-head:has(#add-account) .work-list-title p', ['font-size', 'font-weight', 'color']),
    ('tasks', '.tb .input', '.work-list-head:has(#add-account) .work-search', FIELD + ['width']),
    ('tasks', '.tb .btn-primary', '#add-account', BOX),
    ('tasks', '.grid.g3', '.work-account-grid', ['column-gap', 'row-gap']),
    ('tasks', '.card.ent', '.work-account', CARD),
    ('tasks', '.ent-head', '.work-account > header', ['column-gap', 'align-items']),
    ('tasks', '.ent-head .tile', '.work-account > header .initial', ['width', 'height', 'background-color', 'color']),
    ('tasks', '.ent-head h4', '.work-account h3', ['font-size', 'font-weight', 'color']),
    ('tasks', '.ent-head p', '.work-account > header small', ['font-size', 'font-weight', 'color']),
    ('tasks', '.ent-head .tag', '.work-account .work-badge', BOX),
    ('tasks', '.card.ent .block', '.work-account .work-account-node', ['background-color', 'border-top-left-radius', 'padding-top', 'padding-left', 'font-size', 'font-weight']),
    ('tasks', '.links', '.work-account-links', ['font-size', 'font-weight', 'column-gap']),
    ('tasks', '.links + .block', '.work-gateway-actions', ['background-color', 'border-top-left-radius', 'padding-top', 'padding-left', 'row-gap']),
    ('tasks', '.links + .block .btn-sm', '.work-gateway-buttons .btn:not(.btn-danger)', BOX),
    ('tasks', '.links + .block .btn-danger', '.work-gateway-buttons .btn-danger', BOX),
    ('tasks', '.strip.d', '.work-strip[data-tone=danger]', ['background-color', 'color', 'border-top-left-radius', 'font-size', 'font-weight', 'padding-left', 'column-gap']),
    # 运行环境：工具栏、两列实体卡及卡内各区块
    ('environments', '.tb .seg', '.environment-toolbar .fui-segmented', SEG),
    ('environments', '.tb .seg span.on', '.environment-toolbar .fui-segmented-item[data-state=checked]', BOX + ['box-shadow']),
    ('environments', '.tb .t3', '.runtime-result-count', ['font-size', 'font-weight', 'color']),
    ('environments', '.tb .input', '.environment-toolbar .fui-search', FIELD + ['width']),
    ('environments', '.grid.g2', '.environment-grid', ['column-gap', 'row-gap']),
    ('environments', '.card.ent', '.environment-rich', CARD),
    ('environments', '.ent-head .tile.cc', '.environment-rich .fui-icon-tile', ['width', 'height', 'background-color', 'color']),
    ('environments', '.ent-head h4', '.environment-rich .fui-entity-card-title', ['font-size', 'font-weight', 'color']),
    ('environments', '.ent-head p', '.environment-rich .fui-entity-card-subtitle', ['font-size', 'font-weight', 'color']),
    ('environments', '.ent-head > .tag', '.environment-rich .environment-status', BOX),
    ('environments', '.card.ent > .meta-row', '.environment-id', ['font-size', 'font-weight', 'color']),
    ('environments', '.comp', '.environment-role-strip', ['background-color', 'border-top-left-radius', 'padding-top', 'column-gap']),
    ('environments', '.comp span', '.environment-role-strip > div', ['height', 'background-color', 'border-top-left-radius', 'font-size', 'font-weight']),
    ('environments', '.res4 span', '.environment-resources-grid span', ['font-size', 'font-weight', 'color']),
    ('environments', '.res4 b', '.environment-resources-grid strong', ['font-size', 'font-weight', 'color']),
    ('environments', '.warm.s', '.environment-readiness[data-tone=success]', ['background-color', 'border-top-left-radius', 'padding-top', 'padding-left', 'row-gap']),
    ('environments', '.warm.n', '.environment-readiness[data-tone=neutral]', ['background-color']),
    ('environments', '.warm.s div b', '.environment-readiness[data-tone=success] strong', ['font-size', 'font-weight', 'color']),
    ('environments', '.warm p', '.environment-readiness p', ['font-size', 'font-weight', 'color']),
    ('environments', '.kvl', '.environment-feature-row button', ['font-size', 'font-weight', 'color']),
    ('environments', '.sched', '.environment-schedule-summary', ['font-size', 'font-weight', 'color', 'padding-top', 'border-top-width']),
    ('environments', '.ent-acts', '.environment-rich .fui-entity-card-actions', ['border-top-width', 'padding-top', 'padding-left']),
    ('environments', '.ent-acts span:first-child', '.environment-rich .fui-entity-action[data-tone=primary]', ['height', 'font-size', 'font-weight', 'color']),
]
# 结构写法不同但视觉等价、或已记录的有意偏差，比对时跳过对应属性。
KNOWN = {
    # 设计稿在任务账号卡里给网关提示条写了更紧凑的内联字号与内边距（12px / 10px），与它自己的 .strip 规格不同；
    # 原生提示条按组件库 .fui-strip 规格实现（12.5px / 12px），与组件库的一致性比对见 PARITY。
    ('tasks', '.strip.d'): {'font-size', 'padding-left'},
}
SCRIPT = '(e, names) => Object.fromEntries(names.map(n => [n, n === "font-family" ? getComputedStyle(e).fontFamily.split(",")[0].replaceAll(\'"\', "").replaceAll("\'", "") : getComputedStyle(e).getPropertyValue(n)]))'
# 原生部件 ↔ 组件库同名部件：在文档里放一个组件库探针元素（不在原生作用域内），逐项比对计算样式。
PARITY = [
    ('#add-account', 'button', 'fui-button fui-button-default', {}, BOX + ['font-family']),
    ('.work-gateway-buttons .btn:not(.btn-danger)', 'button', 'fui-button fui-button-sm', {}, BOX + ['font-family']),
    ('.work-gateway-buttons .btn-danger', 'button', 'fui-button fui-button-sm fui-button-destructive', {}, BOX),
    ('.work-list-head:has(#add-account) .work-search', 'div', 'fui-search', {}, FIELD + ['padding-left', 'column-gap']),
    ('.work-navigation', 'div', 'fui-segmented', {}, SEG),
    ('.work-navigation a.active', 'button', 'fui-segmented-item', {'data-state': 'checked'}, BOX + ['box-shadow']),
    ('.work-account .work-badge', 'span', 'fui-badge fui-badge-success', {'data-dot': ''}, BOX),
    ('.work-strip[data-tone=danger]', 'p', 'fui-strip', {'data-tone': 'danger'}, ['background-color', 'color', 'border-top-left-radius', 'padding-left', 'font-size', 'font-weight']),
    ('.work-account', 'article', 'fui-entity-card', {}, ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'row-gap']),
    ('.work-account > footer .btn:not(.btn-danger)', 'button', 'fui-entity-action', {}, ['height', 'font-size', 'font-weight', 'color', 'background-color', 'border-top-left-radius']),
]
PROBE = '''([tag, cls, attrs, names]) => {
  const probe = document.createElement(tag); probe.className = cls; probe.textContent = '探针';
  for (const [key, value] of Object.entries(attrs)) probe.setAttribute(key, value);
  document.body.append(probe);
  const s = getComputedStyle(probe), out = Object.fromEntries(names.map(n => [n, n === 'font-family' ? s.fontFamily.split(',')[0].replaceAll('"', '').replaceAll("'", '') : s.getPropertyValue(n)]));
  probe.remove(); return out;
}'''
TOKEN_NAMES = re.findall(r'(--ui-color-[a-z0-9-]+):', (ROOT / 'apps/legacy-web/ui-foundation.css').read_text())
PALETTE = '''(names) => { const probe = document.createElement('i'); document.body.append(probe); const colors = ['rgba(0, 0, 0, 0)'];
  for (const name of names) { probe.style.color = `var(${name})`; colors.push(getComputedStyle(probe).color); } probe.remove(); return colors; }'''
# 页面自己的元素（不含组件库控件、终端、图标与视觉隐藏的原始 select / 时间 input）：文字色、背景色必须是某个 --ui-color-* token 的值或透明。
TOKEN_CHECK = '''(root, [palette, label]) => { const allowed = new Set(palette), out = new Set();
  for (const e of [root, ...root.querySelectorAll('*')]) {
    if (!e.getClientRects().length || e.closest('svg, .xterm, [class*="fui-"], [data-slot], [data-vue-managed], input[type=checkbox], input[type=radio], .native-choice-source, .native-time-source')) continue;
    const s = getComputedStyle(e);
    for (const prop of ['color', 'backgroundColor']) if (!allowed.has(s[prop])) out.add(`${label} ${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}.${[...e.classList].join('.')} ${prop}: ${s[prop]}`);
  }
  return [...out].slice(0, 30); }'''
# 弹窗外壳：圆角、阴影、描边取 token，标题字重 780。
SHELL = '''(card, title) => { const s = getComputedStyle(card), root = getComputedStyle(document.documentElement), probe = document.createElement('i');
  document.body.append(probe); probe.style.borderRadius = 'var(--ui-radius-card)'; probe.style.boxShadow = 'var(--ui-shadow-modal)';
  const want = getComputedStyle(probe), expected = {radius: want.borderTopLeftRadius, shadow: want.boxShadow}; probe.remove();
  const node = title ? card.querySelector(title) : null, heading = node ? getComputedStyle(node) : null;
  return {radius: s.borderTopLeftRadius, shadow: s.boxShadow, border: s.borderTopWidth, expected, weight: heading && heading.fontWeight, font: heading && heading.fontFamily.split(',')[0].replaceAll('"', '')}; }'''
# 等进行中的过渡与进场动画结束；无限循环的动画（加载转圈、在线圆点）的 finished 永不兑现，跳过。
SETTLED = '() => Promise.all(document.getAnimations().filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => null)))'
THEME = {'version': 1, 'primary': '#2f6bd8', 'success': '#12b981', 'warning': '#f59e0b', 'danger': '#ef4444', 'info': '#5983f4',
    'surface': 'default', 'fontSize': 14, 'spaceUnit': 4, 'controlHeight': 38, 'sizeStep': 6, 'radius': 4, 'shadow': 1}


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
        expected, actual = await expected_node.evaluate(SCRIPT, props), await actual_node.evaluate(SCRIPT, props)
        skip = KNOWN.get((screen, source), set())
        problems.extend(f'{screen} {source} {prop}: 设计稿 {expected[prop]} 页面 {actual[prop]}' for prop in props if prop not in skip and expected[prop] != actual[prop])
        compared += 1
    return compared


async def parity(page, problems: list) -> int:
    """原生部件与组件库探针逐项比对。@param page 任务页。@param problems 差异收集。@return 比对项数。"""
    for selector, tag, cls, attrs, props in PARITY:
        node = page.locator(selector).first
        if not await node.count():
            problems.append(f'一致性 {selector}: 找不到原生部件')
            continue
        native = await node.evaluate(SCRIPT, props)
        kit = await page.evaluate(PROBE, [tag, cls, attrs, props])
        problems.extend(f'一致性 {selector} ↔ .{cls.split()[-1]} {prop}: 组件库 {kit[prop]} 原生 {native[prop]}' for prop in props if native[prop] != kit[prop])
    return len(PARITY)


async def tokens_only(page, scope: str, label: str, problems: list) -> None:
    """范围内页面自有元素的文字色、背景色只取 token。@param page 页面。@param scope 根选择器。@param label 场景名。@param problems 差异收集。@return 无。"""
    # 悬停、选中等过渡进行中时取到的是中间色，先等动画结束。
    await page.evaluate(SETTLED)
    palette = await page.evaluate(PALETTE, TOKEN_NAMES)
    problems.extend(await page.locator(scope).first.evaluate(TOKEN_CHECK, [palette, label]))


async def shell(page, card: str, title: str | None, label: str, problems: list) -> None:
    """弹窗外壳取 token。@param page 页面。@param card 弹窗表面选择器。@param title 标题选择器。@param label 场景名。@param problems 差异收集。@return 无。"""
    box = await page.locator(card).first.evaluate(SHELL, title)
    if box['radius'] != box['expected']['radius'] or box['shadow'] != box['expected']['shadow'] or box['border'] != '0px':
        problems.append(f'{label} 弹窗外壳 {box}')
    if title and (box['weight'] != '780' or box['font'] != 'Inter Variable'):
        problems.append(f'{label} 弹窗标题 {box}')


async def settle(page) -> None:
    """等字体与进场动画结束再取样。@param page 页面。@return 无。"""
    await page.evaluate('document.fonts.ready')
    await page.evaluate(SETTLED)
    await page.wait_for_timeout(300)


async def open_page(browser, fixture, path: str, width: int, errors: list, theme: dict | None = None, before=None):
    """在新上下文打开页面并收集控制台错误。@param before 导航前的上下文准备（可选）。@return 页面与上下文。"""
    context = await browser.new_context(viewport={'width': width, 'height': 900 if width > 760 else 844}, timezone_id='Asia/Shanghai')
    await context.route('**/*', fixture.route)
    if before:
        await before(context)
    script = "localStorage.setItem('claude-code-gateway_auth','synthetic-only');"
    if theme:
        script += f"localStorage.setItem('flower2api.theme',{json.dumps(json.dumps(theme))});"
    await context.add_init_script(script)
    page = await context.new_page()
    page.on('pageerror', lambda e: errors.append(f'{path} {e}'))
    # 合成夹具不覆盖的接口会 404，浏览器记一条「Failed to load resource」；接口缺口不算页面错误，
    # 但前端构建产物与原生资源（/runtime/ 下的样式、脚本、图标、字体）必须全部加载成功。
    page.on('console', lambda m: errors.append(f'{path} {m.text}') if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
    page.on('response', lambda r: errors.append(f'{path} 资源 {r.status} {r.url}') if r.status >= 400 and re.search(r'/assets/|/runtime/[^?]*\.(css|js|svg|woff2)(\?|$)', r.url) else None)
    await page.goto(BASE + path)
    return page, context


async def open_tasks(page, tab: str = 'accounts'):
    """等待任务页指定分区就绪。@param page 页面。@param tab 分区。@return 任务根。"""
    root = page.locator('.task-runtime')
    await page.locator('.task-runtime[aria-busy=false]').wait_for()
    await root.locator('.work-navigation a.active[data-tab="%s"]' % tab).wait_for()
    await settle(page)
    return root


async def no_overflow(page, label: str) -> None:
    """页面不出现横向滚动。@param page 页面。@param label 场景名。@return 无。"""
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), label


class ContinueFixture(WorkspaceFixture):
    """合成运行改为已完成，并回执续聊会话（工作区夹具没有续聊接口）。"""

    def __init__(self):
        """把合成运行改为已完成。@return 无。"""
        super().__init__()
        self.task_runs[0].update(status='success', exit_code=0)

    async def route(self, route):
        """返回续聊会话，其余沿用工作区夹具。@param route 请求。@return 无。"""
        if urlsplit(route.request.url).path == '/runtime/api/runs/synthetic-run/continue/start':
            return await self.respond(route, {'session_id': 'synthetic-continue', 'claude_session_id': 'synthetic-session',
                'ws_path': '/api/runs/synthetic-run/continue/ws/synthetic-continue', 'status': 'running'})
        return await super().route(route)


class BindingFixture(ConsoleFixture):
    """第二个任务账号未绑定网关账号；补充可关联的网关账号列表（控制台夹具没有该接口）。"""

    async def route(self, route):
        """返回前四个合成网关账号，其余沿用控制台夹具。@param route 请求。@return 无。"""
        if urlsplit(route.request.url).path == '/runtime/api/cc2api/accounts':
            return await self.respond(route, [{'id': account['id'], 'name': account['name'],
                'email_masked': account['email'][:3] + '***@example.test'} for account in self.accounts[:4]])
        return await super().route(route)


async def silent_terminal(context) -> None:
    """续聊终端的 WebSocket 只连不回。@param context 浏览器上下文。@return 无。"""
    await context.route_web_socket('**/*', lambda ws: ws.on_message(lambda _message: None))


async def signed_out(context) -> None:
    """独立文档未登录：鉴权查询回 401，触发登录弹窗。@param context 浏览器上下文。@return 无。"""
    await context.route('**/runtime/api/auth/me', lambda route: route.fulfill(status=401, content_type='application/json', body='{"detail":"auth required"}'))


FIELD = ['background-color', 'border-top-width', 'border-top-left-radius', 'padding-left', 'font-size', 'font-weight', 'color', 'font-family']
# 弹窗里的原生控件与挂进原生宿主的 Vue 控件，逐项比对组件库探针：(选择器, 探针标签, 探针类, 探针属性, 属性)
DIALOG_PARITY = {
    'cli-settings': [('#cli-settings-modal [name=display_name]', 'input', 'fui-input', {}, FIELD + ['height'])],
    'add-account': [('#acc-modal .native-choice-trigger', 'button', 'fui-choice', {}, FIELD + ['min-height']),
        # 原生规则不分层，任何误伤都会压过组件库；选线控件外观只由组件库定义。
        ('#acc-modal .proxy-picker-trigger', 'button', 'proxy-picker-trigger', {}, FIELD + ['height'])],
    'warmup': [('#warmup-modal .native-number', 'div', 'fui-number', {}, ['min-height', 'background-color', 'border-top-left-radius', 'font-size', 'font-family'])],
}
# 弹窗底栏（同 .fui-modal-foot）：填充底、贴住弹窗左右边。
DIALOG_FOOTER = {'cli-settings': '#cli-settings-modal .work-form-footer', 'warmup': '#warmup-modal .work-form-footer', 'add-account': '#acc-modal .acc-step-config .row-end',
    'cc2api-binding': '#cc2api-binding-modal .row-end', 'runtime-settings': '#runtime-settings-modal .runtime-settings-workspace > .work-form-footer',
    'runtime-capture': '#runtime-capture-modal .work-form-footer', 'batch-create': '#batch-create-modal .work-form-footer', 'topic': '#topic-modal .work-form-footer',
    'run-window': '#run-window-modal .work-form-footer', 'content-capture': '#content-capture-modal .row-end', 'auth': '#auth-modal .row-end'}
FOOTER = '''([card, foot]) => { const c = card.getBoundingClientRect(), f = foot.getBoundingClientRect(), probe = document.createElement('i'); document.body.append(probe);
  probe.style.backgroundColor = 'var(--ui-color-fill-subtle)'; const want = getComputedStyle(probe).backgroundColor; probe.remove(); const s = getComputedStyle(foot);
  return {background: s.backgroundColor, want, border: s.borderTopWidth, left: Math.round(f.left - c.left), right: Math.round(c.right - f.right)}; }'''
# (名称, 夹具, 地址, 入口（可多步）, 弹窗表面, 标题, 就绪元素, 打开前的上下文准备)；地址为 /runtime/ 的是独立文档专用弹窗。
DIALOGS = [
    ('cli-settings', WorkspaceFixture, '/tasks', ['[data-cli-settings]'], '#cli-settings-modal .modal-card', '.modal-titlebar-name', '#cli-settings-modal [name=display_name]', None),
    ('account-details', WorkspaceFixture, '/tasks', ['[data-account-details]'], '#modal .modal-card', '.modal-titlebar-name', '#modal .work-dialog-content', None),
    ('quota', TaskFeedbackFixture, '/tasks', ['[data-quota]'], '#modal .modal-card', '.modal-titlebar-name', '#modal .work-quota-window', None),
    ('warmup', TaskFeedbackFixture, '/tasks', ['[data-warmup-config]'], '#warmup-modal .modal-card', '.modal-titlebar-name', '#warmup-modal [name=warmup_quota_5h_limit_percent]', None),
    ('add-account', WorkspaceFixture, '/tasks', ['#add-account'], '#acc-modal .modal-card', '.modal-titlebar-name', '#acc-modal .proxy-picker-trigger', None),
    ('cc2api-binding', BindingFixture, '/tasks', ['[data-cc2-bind]'], '#cc2api-binding-modal .modal-card', '.modal-titlebar-name', '#cc2api-binding-modal button[type=submit]:enabled', None),
    ('env-from-task', WorkspaceFixture, '/tasks', ['[data-run-window-config]'], '.runtime-environment-dialog', None, '.runtime-environment-dialog [role=tabpanel][aria-label=运行时段]', None),
    ('task-proxy', WorkspaceFixture, '/tasks', ['[data-proxy-config]'], '.task-proxy-dialog', None, '.task-proxy-dialog .account-proxy-picker', None),
    ('delivery', CaptureFixture, '/tasks?tab=projects', ['[data-project-pane=history]', '#projects-history [data-work]'], '#projects-delivery .modal-card', 'h2', '#projects-delivery-preview', None),
    ('research', CaptureFixture, '/tasks?tab=projects', ['[data-project-pane=pool]', '[data-research=example]'], '#projects-research .modal-card', 'h2', '#projects-research-body', None),
    ('work-capture', CaptureFixture, '/tasks?tab=projects', ['#projects-capture:enabled'], '#work-capture-modal .modal-card', '.modal-titlebar-name', '#work-capture-modal .capture-workspace', None),
    ('runtime-settings', SettingsFixture, '/tasks?tab=runs', ['#runtime-open-settings'], '#runtime-settings-modal .modal-card', 'h2', '#runtime-settings-save:enabled', None),
    ('runtime-capture', WorkspaceFixture, '/tasks?tab=runs', ['#work-capture-new'], '#runtime-capture-modal .modal-card', '#runtime-capture-title', '#runtime-capture-modal .upgrade-card', None),
    ('run-details', WorkspaceFixture, '/tasks?tab=runs', ['[data-detail]'], '.approved-run-dialog', None, '.approved-run-dialog .run-stat-grid article', None),
    ('continue', ContinueFixture, '/tasks?tab=runs', ['[data-continue]'], '#continue-modal .modal-card', '.modal-titlebar-name', '#continue-modal #continue-xterm .xterm-screen', silent_terminal),
    ('batch-create', WorkspaceFixture, '/tasks?tab=tasks', ['#open-batch-form'], '#batch-create-modal .modal-card', 'h2', '#batch-create-modal #batch-topic-list input', None),
    ('topic', WorkspaceFixture, '/tasks?tab=topics', ['#add-topic'], '#topic-modal .modal-card', '.modal-titlebar-name', '#topic-modal textarea', None),
    ('run-window', WorkspaceFixture, '/runtime/#accounts', ['[data-run-window-config]'], '#run-window-modal .modal-card', '.modal-titlebar-name', '#run-window-modal .run-window-interval', None),
    ('environment-workspace', lambda: DiagnosticsCpuFixture(DIST), '/runtime/#environments', ['.environment-rich [data-env-open="overview"]'], '#environment-workspace .modal-card', 'h2', '#environment-section-overview', None),
    ('content-capture', lambda: DiagnosticsCpuFixture(DIST), '/runtime/#environments', ['.environment-rich [data-env-open="resources"]', '[data-content-capture]'], '#content-capture-modal .modal-card', '.modal-titlebar-name', '#content-capture-modal button[type=submit]:enabled', None),
    ('auth', WorkspaceFixture, '/runtime/#accounts', [], '#auth-modal .modal-card', '.modal-titlebar-name', '#auth-modal input[name=user]', signed_out),
]


async def dialogs(browser, output: Path, errors: list, problems: list, checks: list) -> int:
    """深层弹窗：外壳取 token、颜色只取 token、原生控件与组件库一致，1440 / 390 截图且无横向溢出。@return 一致性比对项数。"""
    compared = 0
    for name, factory, path, triggers, card, title, ready, prepare in DIALOGS:
        for width in (1440, 390):
            page, context = await open_page(browser, factory(), path, width, errors, before=prepare)
            for trigger in triggers:
                # 入口附近的内容异步落地，等入口可见后直接派发点击，不滚动页面。
                await page.locator(trigger).first.wait_for()
                await settle(page)
                await page.locator(trigger).first.evaluate('e => e.click()')
            await page.locator(ready).first.wait_for()
            await settle(page)
            if width == 1440:
                await shell(page, card, title, name, problems)
                await tokens_only(page, card, name, problems)
                if name in DIALOG_FOOTER:
                    foot = await page.locator(card).first.evaluate(f'(card) => ({FOOTER})([card, card.querySelector({json.dumps(DIALOG_FOOTER[name])})])')
                    if foot['background'] != foot['want'] or foot['border'] != '0px' or abs(foot['left']) > 1 or abs(foot['right']) > 1:
                        problems.append(f'{name} 弹窗底栏 {foot}')
                for selector, tag, cls, attrs, props in DIALOG_PARITY.get(name, []):
                    native = await page.locator(selector).first.evaluate(SCRIPT, props)
                    kit = await page.evaluate(PROBE, [tag, cls, attrs, props])
                    problems.extend(f'一致性 {selector} ↔ .{cls.split()[-1]} {prop}: 组件库 {kit[prop]} 原生 {native[prop]}' for prop in props if native[prop] != kit[prop])
                    compared += 1
            assert await page.locator(card).first.evaluate('e => e.scrollWidth <= e.clientWidth + 1'), (name, width)
            await no_overflow(page, f'{name}-{width}')
            await page.screenshot(animations='disabled', path=str(output / f'dialog-{name}-{width}.png'))
            await context.close()
    checks.append(f'{len(DIALOGS)} 个深层弹窗（含独立文档 4 个）外壳与颜色取 token、输入 / 下拉 / 数字 / 选线控件与组件库一致，1440 / 390 无溢出')
    return compared


async def main(output: Path) -> None:
    """比对设计稿并验证两页的部件一致性、主题跟随与深层弹窗。@param output 截图与结果目录。@return 无。"""
    output.mkdir(parents=True, exist_ok=True)
    errors, problems, checks, compared = [], [], [], 0
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        mock = await browser.new_page(viewport={'width': 1440, 'height': 900})

        # ---------- 任务与工程：设计稿比对、部件一致性、六个页签 ----------
        page, context = await open_page(browser, WorkspaceFixture(), '/tasks', 1440, errors)
        root = await open_tasks(page)
        await expect(root.locator('.work-account')).to_have_count(1)
        await expect(root.locator('#work-account-count')).to_have_text('1')
        await expect(root.locator('.page-eyebrow, .scanlines, .modal-frame')).to_have_count(0)
        await expect(root.locator('.work-strip[data-tone=danger]')).to_contain_text('invalid_grant')
        compared += await compare(mock, page, 'tasks', problems)
        compared += await parity(page, problems)
        await tokens_only(page, '.task-runtime', 'tasks-accounts', problems)
        await page.screenshot(animations='disabled', full_page=True, path=str(output / 'tasks-accounts-1440.png'))
        for tab in ('projects', 'warmup', 'tasks', 'runs', 'topics'):
            await root.locator(f'.work-navigation a[data-tab={tab}]').click()
            await open_tasks(page, tab)
            await tokens_only(page, '.task-runtime', f'tasks-{tab}', problems)
            await page.screenshot(animations='disabled', full_page=True, path=str(output / f'tasks-{tab}-1440.png'))
        checks.append('任务与工程六个页签颜色只取 token，页头无分组名，无终端装饰，任务账号计数与危险提示条')
        await context.close()
        # 任务账号读取失败：加载状态为危险提示条（role=alert），保留重试按钮，计数不显示。
        page, context = await open_page(browser, WorkspaceFixture(), '/tasks', 1440, errors,
            before=lambda ctx: ctx.route('**/runtime/api/accounts', lambda route: route.fulfill(status=500, content_type='application/json', body='{"detail":"合成读取故障"}')))
        status = page.locator('#accounts-load-status')
        await expect(status).to_have_attribute('data-tone', 'danger')
        await expect(status).to_have_attribute('role', 'alert')
        await expect(status.get_by_role('button', name='重试任务账号', exact=True)).to_be_visible()
        await expect(page.locator('#work-account-count')).to_be_hidden()
        await page.screenshot(animations='disabled', path=str(output / 'tasks-accounts-failed-1440.png'))
        await context.close()
        checks.append('任务账号读取失败显示危险提示条与重试，计数隐藏')

        # ---------- 运行环境 ----------
        page, context = await open_page(browser, WorkspaceFixture(), '/environments', 1440, errors)
        await expect(page.locator('.environment-rich')).to_have_count(4)
        await expect(page.get_by_role('radio', name='全部环境 4', exact=True)).to_be_checked()
        # 预热块颜色取准备状态：第一张热进程就绪为成功色，其余待核对为中性。
        await expect(page.locator('.environment-readiness').first).to_have_attribute('data-tone', 'success')
        await expect(page.locator('.environment-readiness').nth(1)).to_have_attribute('data-tone', 'neutral')
        await settle(page)
        compared += await compare(mock, page, 'environments', problems)
        await tokens_only(page, '.runtime-environments', 'environments', problems)
        await page.screenshot(animations='disabled', full_page=True, path=str(output / 'environments-1440.png'))
        await page.locator('.environment-rich').first.get_by_role('button', name='环境详情', exact=True).click()
        drawer = page.locator('.runtime-environment-dialog')
        for section in ('运行概览', '资源与采集', '请求内核', '运行时段', '维护操作'):
            await drawer.get_by_role('tab', name=section, exact=True).click()
            await expect(drawer.get_by_role('tabpanel', name=section, exact=True)).to_be_visible()
            await settle(page)
            await tokens_only(page, '.runtime-environment-workspace', f'environment-{section}', problems)
            await page.screenshot(animations='disabled', path=str(output / f'environment-drawer-{section}-1440.png'))
        box = await drawer.evaluate('e => { const r = e.getBoundingClientRect(); return {width: r.width, top: r.top, right: innerWidth - r.right} }')
        assert box == {'width': 940, 'top': 14, 'right': 14}, box
        checks.append('运行环境实体卡、预热状态着色、侧抽屉五个分区颜色只取 token，抽屉 940 贴右')
        await context.close()

        # ---------- 390：单列、无横向溢出 ----------
        for path, ready, name in (('/tasks', '.work-account', 'tasks'), ('/tasks?tab=runs', '#runs-body [data-detail]', 'tasks-runs'), ('/environments', '.environment-rich', 'environments')):
            page, context = await open_page(browser, WorkspaceFixture(), path, 390, errors)
            await page.locator(ready).first.wait_for()
            await settle(page)
            await no_overflow(page, f'{name}-390')
            assert await page.evaluate('scrollY') == 0, f'{name}-390 打开时整页被滚动'
            await expect(page.locator('.console-toolbar')).to_be_in_viewport()
            await page.screenshot(animations='disabled', full_page=True, path=str(output / f'{name}-390.png'))
            await context.close()
        checks.append('390 单列无横向溢出，应用栏不被页签滚动带出视口')

        # ---------- 主题跟随：保存的主题作用于原生页，独立文档保持默认 ----------
        page, context = await open_page(browser, WorkspaceFixture(), '/tasks', 1440, errors, THEME)
        root = await open_tasks(page)
        # token 可能是 calc() 表达式，用探针元素解析成计算值再比较。
        themed = await page.evaluate('''() => { const probe = document.createElement('i'); document.body.append(probe);
            probe.style.cssText = 'color: var(--ui-color-primary); border-radius: var(--ui-radius-card); font-size: var(--ui-font-size-meta)';
            const s = getComputedStyle(probe), out = {primary: s.color, card: s.borderTopLeftRadius, meta: s.fontSize}; probe.remove(); return out; }''')
        assert themed['card'] != '18px' and themed['primary'] != 'rgb(108, 84, 180)', themed
        await expect(root.locator('#add-account')).to_have_css('background-color', themed['primary'])
        await expect(root.locator('.work-account')).to_have_css('border-top-left-radius', themed['card'])
        await expect(root.locator('.work-navigation a.active')).to_have_css('font-size', themed['meta'])
        await root.locator('[data-cli-settings]').click()
        await expect(root.locator('#cli-settings-modal .modal-card')).to_have_css('border-top-left-radius', themed['card'])
        await page.screenshot(animations='disabled', path=str(output / 'theme-tasks-1440.png'))
        await page.goto(BASE + '/environments')
        await expect(page.locator('.environment-rich').first).to_have_css('border-top-left-radius', themed['card'])
        await page.goto(BASE + '/runtime/#accounts')
        await page.locator('.work-account').first.wait_for()
        await expect(page.locator('#add-account')).to_have_css('background-color', 'rgb(108, 84, 180)')
        await expect(page.locator('.work-account').first).to_have_css('border-top-left-radius', '18px')
        await page.screenshot(animations='disabled', path=str(output / 'runtime-standalone-1440.png'))
        await context.close()
        checks.append('保存的主题改变原生页主色、圆角、字号；独立 /runtime/ 文档保持默认主题')

        compared += await dialogs(browser, output, errors, problems, checks)
        await browser.close()
    result = {'passed': not problems and not errors, 'compared': compared, 'whitelisted': len(KNOWN), 'checks': checks, 'problems': problems, 'errors': errors}
    (output / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    assert not problems, '\n'.join(problems)
    assert not errors, errors
    print(json.dumps({key: result[key] for key in ('passed', 'compared', 'whitelisted', 'checks')}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/console-ui-revamp/native-pages/verify')
    asyncio.run(main(parser.parse_args().output))
