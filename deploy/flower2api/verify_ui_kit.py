"""验证第二版组件库与主题运行时：与设计稿逐项比对、组件取值与交互状态、预设与局部主题、存储回退、减少动效及真实构建首屏。"""
import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright, expect

from verify_environment_ui import BASE, ROOT
from verify_remaining_pages import RemainingPagesFixture

THEME_KEY = 'flower2api.theme'
DEFAULT_SEED = {'version': 1, 'primary': '#6c54b4', 'success': '#12b981', 'warning': '#f59e0b', 'danger': '#ef4444', 'info': '#5983f4',
                'surface': 'default', 'fontSize': 13, 'spaceUnit': 4, 'controlHeight': 38, 'sizeStep': 6, 'radius': 8, 'shadow': 1}
PRIMARY = 'rgb(108, 84, 180)'
RING = 'rgb(108, 84, 180) 0px 0px 0px 1px, rgba(108, 84, 180, 0.18) 0px 0px 0px 4px'
# 默认主题基准：取自 doc/design/console-v2/mock.css，只在本脚本写一次。
STATIC = [
    ('主要按钮', '[data-testid=button-default]', {'background-color': PRIMARY, 'color': 'rgb(255, 255, 255)', 'height': '38px', 'border-radius': '6px', 'font-size': '13px', 'font-weight': '700', 'padding-left': '16px', 'border-top-width': '0px'}),
    ('次要按钮', '[data-testid=button-outline]', {'background-color': 'rgba(98, 96, 158, 0.075)', 'color': 'rgb(15, 21, 39)'}),
    ('柔和按钮', '[data-testid=button-soft]', {'background-color': 'rgb(243, 240, 251)', 'color': 'rgb(91, 68, 163)'}),
    ('危险按钮', '[data-testid=button-destructive]', {'background-color': 'rgb(254, 240, 240)', 'color': 'rgb(195, 45, 50)'}),
    ('文字按钮', '[data-testid=button-ghost]', {'background-color': 'rgba(0, 0, 0, 0)', 'color': 'rgb(65, 74, 92)', 'padding-left': '8px'}),
    ('小号按钮', '[data-testid=button-sm-default]', {'height': '32px', 'font-size': '12px', 'padding-left': '12px'}),
    ('图标按钮', '[data-testid=button-icon]', {'width': '38px', 'height': '38px'}),
    ('禁用按钮', '[data-testid=button-disabled]', {'opacity': '0.45', 'cursor': 'not-allowed'}),
    ('输入框', '[data-testid=input-default]', {'background-color': 'rgba(98, 96, 158, 0.075)', 'height': '38px', 'border-radius': '8px', 'font-size': '13px', 'border-top-width': '0px'}),
    ('只读输入', '[data-testid=input-readonly]', {'background-color': 'rgb(241, 242, 247)', 'color': 'rgb(95, 104, 120)'}),
    ('校验失败', '[data-testid=input-invalid]', {'box-shadow': 'rgb(239, 68, 68) 0px 0px 0px 1px'}),
    ('字段标签', '.fui-label >> nth=0', {'font-size': '12px', 'font-weight': '700', 'color': 'rgb(65, 74, 92)'}),
    ('分段托盘', '[data-testid=kit-segmented] .fui-segmented', {'background-color': 'rgba(98, 96, 158, 0.075)', 'border-radius': '8px', 'padding-top': '3px'}),
    ('分段选中', '[data-testid=kit-segmented] .fui-segmented-item[data-state=checked]', {'background-color': 'rgb(255, 255, 255)', 'height': '32px', 'font-size': '12.5px', 'font-weight': '650', 'border-radius': '7px', 'box-shadow': 'rgba(14, 23, 38, 0.08) 0px 1px 3px 0px'}),
    ('分段计数', '[data-testid=kit-segmented] .fui-segmented-item[data-state=checked] .fui-segmented-count', {'color': 'rgb(91, 68, 163)', 'font-size': '11px'}),
    ('成功徽标', '[data-testid=badge-success]', {'color': 'rgb(6, 118, 85)', 'background-color': 'rgb(236, 249, 245)', 'height': '22px', 'border-radius': '8px', 'font-size': '11.5px', 'font-weight': '650'}),
    ('平台徽标', '[data-testid=badge-cc]', {'color': 'rgb(154, 86, 52)', 'background-color': 'rgb(251, 241, 234)'}),
    ('开关开', '[data-testid=switch-on]', {'background-color': PRIMARY, 'width': '36px', 'height': '20px'}),
    ('开关关', '[data-testid=switch-off]', {'background-color': 'rgb(216, 220, 232)'}),
    ('复选选中', '[data-testid=checkbox-checked] .fui-checkbox-box', {'background-color': PRIMARY}),
    ('单选卡选中', '[data-testid=radio-cards] .fui-radio-card[data-state=checked]', {'background-color': 'rgb(243, 240, 251)', 'box-shadow': 'rgb(108, 84, 180) 0px 0px 0px 1.5px inset', 'border-radius': '12px'}),
    ('卡片', '[data-testid=card]', {'background-color': 'rgb(255, 255, 255)', 'border-radius': '18px', 'box-shadow': 'rgba(14, 23, 38, 0.03) 0px 1px 2px 0px, rgba(14, 23, 38, 0.12) 0px 10px 22px -18px', 'border-top-width': '0px'}),
    ('表头', '[data-testid=table] th >> nth=0', {'background-color': 'rgb(239, 241, 248)', 'height': '40px', 'font-size': '12px', 'font-weight': '700', 'color': 'rgb(65, 74, 92)', 'border-top-left-radius': '8px'}),
    ('表格行', '[data-testid=table] tbody tr >> nth=0 >> td >> nth=0', {'height': '60px', 'font-size': '13px'}),
    ('斑马行', '[data-testid=table] tbody tr >> nth=1 >> td >> nth=0', {'background-color': 'rgb(248, 249, 252)'}),
    ('分页当前页', '[data-testid=kit-data] [aria-current=page]', {'background-color': PRIMARY, 'color': 'rgb(255, 255, 255)', 'height': '32px', 'border-radius': '8px'}),
    ('分页普通页', '[data-testid=kit-data] .fui-pagination-number:not([aria-current]) >> nth=0', {'background-color': 'rgb(247, 248, 251)', 'color': 'rgb(15, 21, 39)'}),
    ('空态标题', '[data-testid=empty] .fui-empty-state-title', {'color': 'rgb(15, 21, 39)', 'font-size': '14px'}),
]
# 设计稿只给静止态的交互状态，按 design.md §5 的状态约定核对。
HOVER = [
    ('主要按钮悬停', '[data-testid=button-default]', {'background-color': 'rgb(95, 71, 159)'}),
    ('次要按钮悬停', '[data-testid=button-outline]', {'background-color': 'rgba(98, 96, 158, 0.11)'}),
    ('文字按钮悬停', '[data-testid=button-ghost]', {'background-color': 'rgba(98, 96, 158, 0.075)', 'color': 'rgb(15, 21, 39)'}),
    ('表格行悬停', '[data-testid=table] tbody tr >> nth=2 >> td >> nth=0', {'background-color': 'rgb(240, 241, 249)'}),
]

MOCK = (ROOT / 'doc/design/console-v2/mock.html').as_uri()
BOX = ['background-color', 'color', 'height', 'padding-top', 'padding-left', 'padding-right', 'border-top-left-radius', 'font-size', 'font-weight', 'box-shadow', 'column-gap']
TEXT = ['color', 'font-size', 'font-weight', 'font-family', 'line-height']
# 与设计稿逐项对照：(画面, 设计稿选择器, 演示页选择器, 属性, 演示页准备动作)
DESIGN_PAIRS = [
    ('proxies', '.ph-actions .btn-primary', '[data-testid=button-icon-label]', BOX, None),
    ('proxies', '.ph-actions .btn:not(.btn-primary)', '[data-testid=button-outline]', BOX, None),
    ('proxies', '.tcard', '[data-testid=card]', ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left'], None),
    ('proxies', '.tcard-h h3', '[data-testid=card] [data-slot=card-title]', TEXT, None),
    ('proxies', '.tcard-h h3 small', '[data-testid=card-count]', TEXT, None),
    ('proxies', '.tcard-h .input', '[data-testid=input-group]', BOX, None),
    ('proxies', '.t th', '[data-testid=table] th', BOX + ['text-align'], None),
    ('proxies', '.t tbody tr:nth-child(1) td', '[data-testid=table] tbody tr:nth-child(1) td', BOX, None),
    ('proxies', '.t tbody tr:nth-child(2) td', '[data-testid=table] tbody tr:nth-child(2) td', ['background-color'], None),
    ('proxies', '.t tbody tr.hover td', '[data-testid=table] tbody tr:nth-child(4) td', ['background-color'], 'hover'),
    ('proxies', '.t td b', '[data-testid=table] tbody tr:nth-child(1) td b', TEXT, None),
    ('proxies', '.t .sub', '[data-testid=table] .fui-table-sub', TEXT + ['margin-top'], None),
    ('proxies', '.t td b.mono', '[data-testid=latency]', TEXT, None),
    ('proxies', '.t .t4', '[data-testid=latency-unit]', TEXT, None),
    ('proxies', '.t .tile', '[data-testid=table] .kit-tile', ['width', 'height', 'border-top-left-radius', 'background-color', 'color'], None),
    ('proxies', '.ops .btn-sm', '[data-testid=table] .kit-op', BOX, None),
    ('proxies', '.tag.dot.tg-success', '[data-testid=badge-success]', BOX, None),
    ('proxies', 'td .tag.tg-warning:not(.dot)', '[data-testid=expiry-warning]', BOX, None),
    ('requests', '.tfoot', '[data-testid=kit-data] .fui-pagination', TEXT, None),
    ('requests', '.psize', '[data-testid=kit-data] .pagination-size .fui-choice', BOX, None),
    ('requests', '.pager span.on', '[data-testid=kit-data] [aria-current=page]', BOX + ['min-width'], None),
    ('requests', '.pager span:not(.on):not(.dis)', '[data-testid=kit-data] .fui-pagination-number:not([aria-current])', BOX, None),
    ('requests', '.pager span.dis', '[data-testid=kit-data] .fui-pagination-controls button:disabled', BOX, None),
    ('requests', '.seg', '[data-testid=kit-segmented] .fui-segmented', BOX, None),
    ('requests', '.seg span.on', '[data-testid=kit-segmented] .fui-segmented-item[data-state=checked]', BOX, None),
    ('requests', '.seg span:not(.on)', '[data-testid=kit-segmented] .fui-segmented-item[data-state=unchecked]', BOX, None),
    ('requests', '.seg span.on em', '[data-testid=kit-segmented] [data-state=checked] .fui-segmented-count', TEXT, None),
    ('requests', '.seg span:not(.on) em', '[data-testid=kit-segmented] [data-state=unchecked] .fui-segmented-count', TEXT, None),
    ('accounts', '.switch.on', '[data-testid=switch-on]', ['width', 'height', 'border-top-left-radius', 'background-color'], None),
    ('accounts', '.acc-ctl .btn-danger', '[data-testid=button-sm-destructive]', BOX, None),
    ('accounts', '.acc-ctl', '[data-testid=switch-label]', TEXT, None),
    ('account-edit', '.modal', '.kit-dialog', ['background-color', 'border-top-left-radius', 'box-shadow'], 'dialog'),
    ('account-edit', '.mask', '[data-slot=dialog-overlay]', ['background-color', 'backdrop-filter'], 'dialog'),
    ('account-edit', '.mh h2', '.kit-dialog [data-slot=dialog-title]', TEXT + ['line-height'], 'dialog'),
    ('account-edit', '.mh p', '.kit-dialog [data-slot=dialog-description]', TEXT, 'dialog'),
    ('account-edit', '.rc.on', '[data-testid=radio-cards] .fui-radio-card[data-state=checked]', BOX, None),
    ('account-edit', '.rc:not(.on)', '[data-testid=radio-cards] .fui-radio-card[data-state=unchecked]', ['background-color'], None),
    ('account-edit', '.rc b', '[data-testid=radio-cards] .fui-radio-card-label', TEXT, None),
    ('account-edit', '.rc span', '[data-testid=radio-cards] .fui-radio-card-description', TEXT, None),
    ('account-edit', '.rc.on .rd', '[data-testid=radio-cards] [data-state=checked] .fui-radio-card-dot', ['width', 'height', 'border-top-width', 'border-top-color'], None),
    ('account-edit', '.rc:not(.on) .rd', '[data-testid=radio-cards] [data-state=unchecked] .fui-radio-card-dot', ['width', 'height', 'border-top-width', 'border-top-color'], None),
    ('account-edit', '.field label', '.fui-label', TEXT, None),
    ('account-edit', '.field .input:not(.ro)', '[data-testid=input-default]', [p for p in BOX if p != 'column-gap'], None),
    ('account-edit', '.field .input.ro', '[data-testid=input-readonly]', ['background-color', 'color', 'height', 'border-top-left-radius'], None),
    ('account-edit', '.mb', '.kit-dialog', ['line-height'], 'dialog'),
    ('settings', '.input.focus', '[data-testid=input-default]', ['background-color', 'box-shadow'], 'focus'),
    ('settings', '.input .end span', '.fui-stepper button', ['width', 'height', 'border-top-left-radius', 'color'], None),
    ('settings', '.field .help', '[data-testid=field-help]', TEXT, None),
    ('settings', '.field label .tag', '[data-testid=label-extra-badge]', ['height', 'padding-left', 'border-top-left-radius', 'background-color', 'color', 'font-size', 'font-weight'], None),
    # 组合组件（子任务 2）：页头、概览卡、数据表卡片、工具栏、实体卡、浮动保存栏、居中弹窗。
    ('accounts', '.ph', '[data-testid=page-header]', ['column-gap', 'align-items'], None),
    ('accounts', '.ph h1', '[data-testid=page-header] .fui-page-header-title', TEXT + ['letter-spacing'], None),
    ('accounts', '.ph p', '[data-testid=page-header] .fui-page-header-description', TEXT + ['margin-top'], None),
    ('accounts', '.ph-actions', '[data-testid=page-header] .fui-page-header-actions', ['column-gap'], None),
    ('proxies', '.grid.g4', '[data-testid=overview-grid]', ['column-gap', 'row-gap'], None),
    ('proxies', '.ov', '[data-testid=overview-card]', ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'column-gap'], None),
    ('proxies', '.ov p', '[data-testid=overview-card] .fui-overview-card-label', TEXT, None),
    ('proxies', '.ov strong', '[data-testid=overview-card] .fui-overview-card-value', TEXT + ['margin-top', 'margin-bottom', 'letter-spacing'], None),
    ('proxies', '.ov strong small', '[data-testid=overview-card-unit] .fui-overview-card-value small', TEXT + ['margin-left'], None),
    ('proxies', '.ov > div > span', '[data-testid=overview-card] .fui-overview-card-caption', TEXT, None),
    ('proxies', '.ov .ico', '[data-testid=overview-card] .fui-icon-tile', ['width', 'height', 'border-top-left-radius', 'background-color', 'color'], None),
    ('proxies', '.ov .ico.s', '[data-testid=overview-card-unit] .fui-icon-tile', ['background-color', 'color'], None),
    ('proxies', '.tcard', '[data-testid=table-card]', ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'padding-bottom', 'row-gap'], None),
    ('proxies', '.tcard-h', '[data-testid=table-card] .fui-table-card-head', ['column-gap', 'align-items'], None),
    ('proxies', '.tcard-h h3', '[data-testid=table-card] .fui-table-card-title', TEXT + ['column-gap'], None),
    ('proxies', '.tcard-h h3 small', '[data-testid=table-card] .fui-table-card-count', TEXT, None),
    ('environments', '.tb', '[data-testid=toolbar]', ['column-gap', 'align-items'], None),
    ('environments', '.ent', '[data-testid=entity-card]', ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'row-gap'], None),
    ('environments', '.ent-head', '[data-testid=entity-card] .fui-entity-card-head', ['column-gap', 'align-items'], None),
    ('environments', '.ent .tile', '[data-testid=entity-card] .fui-icon-tile', ['width', 'height', 'border-top-left-radius', 'background-color', 'color'], None),
    ('environments', '.ent-head h4', '[data-testid=entity-card] .fui-entity-card-title', TEXT, None),
    ('environments', '.ent-head p', '[data-testid=entity-card] .fui-entity-card-subtitle', TEXT + ['margin-top'], None),
    ('environments', '.ent-acts', '[data-testid=entity-card] .fui-entity-card-actions', ['border-top-width', 'border-top-color', 'padding-top', 'padding-left', 'margin-left'], None),
    ('environments', '.ent-acts span:first-child', '[data-testid=entity-action-primary]', ['color', 'font-size', 'font-weight', 'height', 'column-gap', 'border-top-left-radius'], None),
    ('environments', '.ent-acts span:nth-child(2)', '[data-testid=entity-action]', ['color', 'font-size', 'font-weight', 'height'], None),
    ('settings', '.savebar', '[data-testid=save-bar]', ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'padding-right', 'column-gap'], None),
    ('settings', '.savebar b', '[data-testid=save-bar] .fui-save-bar-title', TEXT + ['column-gap'], None),
    ('settings', '.savebar .hint', '[data-testid=save-bar] .fui-save-bar-hint', TEXT, None),
    ('tasks', '.strip.s', '[data-testid=notice-strip]', BOX + ['font-family', 'align-items'], None),
    ('tasks', '.strip.s svg', '[data-testid=notice-strip] svg', ['width', 'height'], None),
    ('update-progress', '.strip.n', '[data-testid=notice-strip-neutral]', BOX + ['font-family'], None),
    ('account-edit', '.modal', '[data-testid=modal]', ['background-color', 'border-top-left-radius', 'box-shadow'], 'modal'),
    ('account-edit', '.mh', '[data-testid=modal] .fui-modal-head', ['padding-top', 'padding-left', 'padding-bottom', 'column-gap', 'align-items'], 'modal'),
    ('account-edit', '.mh h2', '[data-testid=modal] .fui-modal-title', TEXT + ['column-gap'], 'modal'),
    ('account-edit', '.mh p', '[data-testid=modal] .fui-modal-description', TEXT, 'modal'),
    ('account-edit', '.modal > div[style*="padding:0 24px 18px"]', '[data-testid=modal] .fui-modal-nav', ['padding-top', 'padding-left', 'padding-right', 'padding-bottom'], 'modal'),
    ('account-edit', '.modal .seg', '[data-testid=modal-nav]', ['background-color', 'padding-top', 'column-gap', 'border-top-left-radius'], 'modal'),
    ('account-edit', '.mb', '[data-testid=modal] .fui-modal-body', ['padding-top', 'padding-left', 'padding-bottom', 'row-gap', 'line-height'], 'modal'),
    ('account-edit', '.mf', '[data-testid=modal] .fui-modal-foot', ['background-color', 'padding-top', 'padding-left', 'column-gap'], 'modal'),
    # 4-2 扩展：可点击概览卡、无标题表格卡片头部、32px 图标块、靠右抽屉外框。
    ('requests', '.ov:last-child', '[data-testid=overview-card-interactive]', ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'column-gap'], None),
    ('requests', '.ov:last-child p', '[data-testid=overview-card-interactive] .fui-overview-card-label', TEXT, None),
    ('requests', '.ov:last-child > div > span', '[data-testid=overview-card-interactive] .fui-overview-card-caption', TEXT, None),
    ('requests', '.tcard-h', '[data-testid=table-card-bare] .fui-table-card-head', ['column-gap', 'align-items'], None),
    ('requests', '.tcard-h .seg', '[data-testid=table-card-bare] .fui-segmented', ['background-color', 'padding-top', 'column-gap', 'border-top-left-radius'], None),
    ('proxies', '.t td .tile', '[data-testid=icon-tile-sm]', ['width', 'height', 'border-top-left-radius', 'background-color', 'color'], None),
    ('account-edit', '.modal', '[data-testid=modal-side]', ['background-color', 'border-top-left-radius', 'box-shadow'], 'side'),
    ('account-edit', '.mh', '[data-testid=modal-side] .fui-modal-head', ['padding-top', 'padding-left', 'padding-bottom', 'column-gap', 'align-items'], 'side'),
]
# 结构写法不同但视觉等价、或已记录的有意偏差，比对时跳过对应属性。
KNOWN = {
    ('proxies', '.tcard'): {'padding-left'},  # 设计稿内边距写在卡片上，组件写在卡片内各块上，内容起点一致
    ('requests', '.pager span.on'): {'column-gap'},  # 设计稿是单元素网格，组件是图标与文字的 flex 间距
    ('requests', '.pager span:not(.on):not(.dis)'): {'column-gap'},
    ('requests', '.pager span.dis'): {'column-gap'},
    ('accounts', '.switch.on'): {'border-top-left-radius'},  # 99px 与 999px 都是全圆
    ('tasks', '.strip.s'): {'padding-top'},  # 设计稿固定高 36、上下零内边距；组件用 9px + 18px 行高凑成同高，长文本可换行
    ('update-progress', '.strip.n'): {'padding-top'},
}

async def styles(locator, props: dict) -> dict:
    """读取计算样式。@param locator 目标元素。@param props 期望属性。@return 实际值。"""
    return await locator.evaluate('(e, names) => Object.fromEntries(names.map(n => [n, getComputedStyle(e).getPropertyValue(n)]))', list(props))


async def compare(page, items, problems: list, prepare=None) -> dict:
    """逐项比对并收集差异。@param page 页面。@param items 检查清单。@param problems 差异列表。@param prepare 读取前的交互。@return 实际值。"""
    actual = {}
    for name, selector, expected in items:
        locator = page.locator(selector).first
        await locator.scroll_into_view_if_needed()
        if prepare:
            await prepare(locator)
        values = await styles(locator, expected)
        actual[name] = values
        problems.extend(f'{name} {prop}: 期望 {value} 实际 {values[prop]}' for prop, value in expected.items() if values[prop] != value)
    return actual


async def hover(locator) -> None:
    """悬停并等待过渡完成。@param locator 元素。@return 无。"""
    await locator.hover()
    await locator.page.wait_for_timeout(250)


async def root_var(page, name: str) -> dict:
    """读取根元素的内联值与计算值。@param page 页面。@param name 变量名。@return 内联与计算结果。"""
    return await page.evaluate('n => ({ inline: document.documentElement.style.getPropertyValue(n), computed: getComputedStyle(document.documentElement).getPropertyValue(n).trim() })', name)


async def verify_preview(browser, url: str, output: Path) -> dict:
    """演示页：组件取值、交互状态、预设、局部主题、持久化与截图。@return 结果摘要。"""
    problems, errors, business = [], [], []
    context = await browser.new_context(viewport={'width': 1440, 'height': 900})
    page = await context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.on('request', lambda request: business.append(request.url) if any(path in request.url for path in ('/admin/', '/api/', '/v1/')) else None)
    await page.goto(url)
    await page.evaluate('document.fonts.ready')
    assert (await root_var(page, '--ui-color-primary'))['inline'] == '', '未保存主题时根元素不应有内联变量'
    static = await compare(page, STATIC, problems)
    hovered = await compare(page, HOVER, problems, hover)
    family = await page.locator('[data-testid=button-default]').evaluate('e => getComputedStyle(e).fontFamily')
    if 'Inter Variable' not in family:
        problems.append(f'按钮字体 {family}')
    await page.screenshot(path=str(output / 'kit-1440.png'), full_page=True)

    # 键盘焦点：交互控件主色外框，输入类主色细环加外圈。
    button = page.locator('[data-testid=button-default]')
    await button.evaluate('e => e.focus({ focusVisible: true })')
    focus = await button.evaluate('e => [e.matches(":focus-visible"), getComputedStyle(e).outlineStyle, getComputedStyle(e).outlineColor, getComputedStyle(e).outlineWidth]')
    if focus != [True, 'solid', PRIMARY, '2px']:
        problems.append(f'按钮键盘焦点 {focus}')
    field = page.locator('[data-testid=input-default]')
    await field.click()
    await page.wait_for_timeout(250)
    ring = await styles(field, {'box-shadow': '', 'background-color': '', 'outline-style': ''})
    if ring != {'box-shadow': RING, 'background-color': 'rgb(255, 255, 255)', 'outline-style': 'none'}:
        problems.append(f'输入聚焦 {ring}')
    await page.locator('[data-testid=input-group] input').click()
    await page.wait_for_timeout(250)
    group = await styles(page.locator('[data-testid=input-group]'), {'box-shadow': ''})
    if group['box-shadow'] != RING:
        problems.append(f'前后缀输入聚焦 {group}')

    # 浮层：选择菜单、弹窗、通知、确认框。
    await page.get_by_role('combobox', name='订阅类型', exact=True).click()
    menu = await styles(page.locator('.fui-choice-menu'), {'border-radius': '', 'box-shadow': '', 'border-top-width': ''})
    if menu != {'border-radius': '12px', 'box-shadow': 'rgba(14, 23, 38, 0.09) 0px 1px 6px -1px, rgba(14, 23, 38, 0.08) 0px 8px 20px -10px', 'border-top-width': '0px'}:
        problems.append(f'选择菜单 {menu}')
    await page.keyboard.press('Escape')
    await page.get_by_role('button', name='打开弹窗示例').click()
    dialog = page.locator('.kit-dialog')
    await expect(dialog).to_be_visible()
    await page.wait_for_timeout(300)
    shell = await styles(dialog, {'border-radius': '', 'box-shadow': '', 'background-color': ''})
    title = await styles(dialog.locator('[data-slot=dialog-title]'), {'font-size': '', 'font-weight': ''})
    overlay = await styles(page.locator('[data-slot=dialog-overlay]'), {'background-color': ''})
    if shell != {'border-radius': '18px', 'box-shadow': 'rgba(14, 23, 38, 0.35) 0px 24px 60px -20px', 'background-color': 'rgb(255, 255, 255)'} or title != {'font-size': '20px', 'font-weight': '780'} or overlay['background-color'] != 'rgba(14, 23, 38, 0.3)':
        problems.append(f'弹窗 {shell} {title} {overlay}')
    await page.screenshot(path=str(output / 'kit-dialog.png'))
    await page.keyboard.press('Escape')
    await expect(dialog).to_have_count(0)
    await page.get_by_role('button', name='成功通知').click()
    notice = await styles(page.locator('.fui-notice').first, {'background-color': '', 'border-radius': ''})
    if notice != {'background-color': 'rgb(25, 27, 44)', 'border-radius': '12px'}:
        problems.append(f'通知 {notice}')
    await page.get_by_role('button', name='关闭消息').click()
    await page.get_by_role('button', name='确认弹窗').click()
    await page.wait_for_timeout(300)
    footer = await styles(page.locator('.fui-confirm-footer'), {'background-color': ''})
    if footer['background-color'] != 'rgb(247, 248, 251)':
        problems.append(f'确认框底栏 {footer}')
    await page.screenshot(path=str(output / 'kit-confirm.png'))
    await page.get_by_role('button', name='取消').click()

    # 预设与自定义主色：组件随之变化；浅亮主色改用深色按钮文字。
    presets = {}
    for preset, expected in [('ocean', {'background-color': 'rgb(47, 107, 216)', 'color': 'rgb(255, 255, 255)'}),
                             ('teal', {'background-color': 'rgb(15, 159, 143)', 'color': 'rgb(15, 21, 39)'}),
                             ('dusk', {'background-color': 'rgb(226, 116, 43)', 'color': 'rgb(15, 21, 39)'}),
                             ('rose', {'color': 'rgb(255, 255, 255)'}),
                             ('graphite', {'background-color': 'rgb(61, 67, 82)', 'color': 'rgb(255, 255, 255)'})]:
        await page.get_by_test_id(f'preset-{preset}').click()
        await page.wait_for_timeout(250)
        values = await styles(page.locator('[data-testid=button-default]'), {'background-color': '', 'color': ''})
        presets[preset] = values
        problems.extend(f'预设 {preset} {prop}: 期望 {value} 实际 {values[prop]}' for prop, value in expected.items() if values[prop] != value)
        await page.locator('[data-testid=kit-buttons]').scroll_into_view_if_needed()
        await page.screenshot(path=str(output / f'preset-{preset}.png'))
    if presets['rose']['background-color'] == 'rgb(214, 74, 123)':
        problems.append('玫瑰红白字对比不足时应压暗主色')
    await page.get_by_test_id('custom-primary').evaluate("e => { e.value = '#118844'; e.dispatchEvent(new Event('input', { bubbles: true })); }")
    await page.wait_for_timeout(250)
    custom = await styles(page.locator('[data-testid=button-default]'), {'background-color': ''})
    if custom['background-color'] != 'rgb(17, 136, 68)':
        problems.append(f'自定义主色 {custom}')
    badge = await styles(page.locator('[data-testid=badge-default]'), {'color': ''})
    if badge['color'] == 'rgb(91, 68, 163)':
        problems.append('自定义主色后主色徽标未变化')
    await page.get_by_test_id('preset-petal').click()
    await page.get_by_role('radiogroup', name='表面材质').get_by_role('radio', name='柔光').click()
    layout = await root_var(page, '--ui-color-layout')
    if layout['computed'] in ('', '#f5f6fa'):
        problems.append(f'柔光材质 {layout}')
    await page.screenshot(path=str(output / 'surface-soft.png'), full_page=True)
    await page.get_by_role('radiogroup', name='表面材质').get_by_role('radio', name='默认').click()

    # 局部主题只影响容器内部。
    local = page.locator('[data-testid=local-theme]')
    local_button = await styles(local.locator('[data-testid=local-button]'), {'background-color': '', 'border-radius': ''})
    outside = await styles(page.locator('[data-testid=button-default]'), {'background-color': ''})
    if local_button != {'background-color': 'rgb(15, 159, 143)', 'border-radius': '2px'} or outside['background-color'] != PRIMARY or await local.get_attribute('data-ui-theme') is None:
        problems.append(f'局部主题 {local_button} 外部 {outside}')

    # 持久化：保存后刷新首屏即为保存值；恢复默认后清除内联变量。
    await page.get_by_test_id('preset-ocean').click()
    await page.get_by_test_id('theme-save').click()
    await expect(page.get_by_test_id('theme-status')).to_contain_text('已保存')
    await page.reload()
    saved = await root_var(page, '--ui-color-primary')
    if saved['inline'] != '#2f6bd8':
        problems.append(f'刷新后主题 {saved}')
    await page.get_by_test_id('theme-reset').click()
    await page.reload()
    reset = await root_var(page, '--ui-color-primary')
    if reset != {'inline': '', 'computed': '#6c54b4'}:
        problems.append(f'恢复默认 {reset}')

    for width in (390,):
        await page.set_viewport_size({'width': width, 'height': 844})
        await page.screenshot(path=str(output / f'kit-{width}.png'), full_page=True)
        overflow = await page.evaluate('document.documentElement.scrollWidth - innerWidth')
        if overflow > 0:
            problems.append(f'{width}px 横向溢出 {overflow}')
    await context.close()
    return {'problems': problems, 'errors': errors, 'business': business, 'static': static, 'hover': hovered, 'presets': presets}


async def verify_storage(browser, url: str) -> dict:
    """存储缺失、损坏、越界、版本不符、存储抛错时回退默认且无报错。@return 结果摘要。"""
    cases = {
        '缺失': '',
        '损坏': f"localStorage.setItem('{THEME_KEY}', '{{broken')",
        '版本不符': f"localStorage.setItem('{THEME_KEY}', JSON.stringify({{...{json.dumps(DEFAULT_SEED)}, version: 2, primary: '#2f6bd8'}}))",
        '越界': f"localStorage.setItem('{THEME_KEY}', JSON.stringify({{...{json.dumps(DEFAULT_SEED)}, radius: 99, primary: '#2f6bd8'}}))",
        '大写色值': f"localStorage.setItem('{THEME_KEY}', JSON.stringify({{...{json.dumps(DEFAULT_SEED)}, primary: '#2F6BD8'}}))",
        '存储抛错': "Object.defineProperty(window, 'localStorage', { configurable: true, get() { throw new DOMException('denied', 'SecurityError'); } })",
    }
    results, problems = {}, []
    for name, script in cases.items():
        context = await browser.new_context()
        if script:
            await context.add_init_script(script)
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error, bucket=errors: bucket.append(str(error)))
        page.on('console', lambda message, bucket=errors: bucket.append(message.text) if message.type == 'error' else None)
        await page.goto(url)
        await expect(page.locator('[data-testid=button-default]')).to_be_visible()
        value = await root_var(page, '--ui-color-primary')
        background = await styles(page.locator('[data-testid=button-default]'), {'background-color': ''})
        results[name] = {'root': value, 'button': background, 'errors': errors}
        if value != {'inline': '', 'computed': '#6c54b4'} or background['background-color'] != PRIMARY or errors:
            problems.append(f'{name}: {results[name]}')
        await context.close()
    return {'problems': problems, 'cases': results}


async def verify_motion(browser, url: str) -> dict:
    """减少动效偏好下组件无过渡与动画。@return 结果摘要。"""
    context = await browser.new_context(reduced_motion='reduce')
    page = await context.new_page()
    await page.goto(url)
    values = {
        'button': await page.locator('[data-testid=button-default]').evaluate('e => getComputedStyle(e).transitionDuration'),
        'switch': await page.locator('[data-testid=switch-on] .fui-switch-thumb').evaluate('e => getComputedStyle(e).transitionDuration'),
        'skeleton': await page.locator('[data-testid=skeleton] .fui-skeleton').first.evaluate('e => getComputedStyle(e).animationName'),
    }
    await page.get_by_role('button', name='打开弹窗示例').click()
    # 全站减少动效规则把动画时长压为 0（style.css），弹窗进出场因此不再有动画。
    values['dialog'] = await page.locator('.kit-dialog').evaluate('e => getComputedStyle(e).animationDuration')
    await context.close()
    expected = {'button': '0s', 'switch': '0s', 'skeleton': 'none', 'dialog': '0s'}
    return {'problems': [f'{key}: {values[key]}' for key in expected if values[key] != expected[key]], 'values': values}


async def verify_first_paint(browser, output: Path) -> dict:
    """真实构建入口：#app 首次出现内容时根变量已是保存的主题。@return 结果摘要。"""
    fixture = RemainingPagesFixture()
    context = await browser.new_context(viewport={'width': 1440, 'height': 900})
    await context.route('**/*', fixture.route)
    seed = {**DEFAULT_SEED, 'primary': '#2f6bd8'}
    await context.add_init_script(f"""
      localStorage.setItem('claude-code-gateway_auth', 'synthetic-only');
      localStorage.setItem('{THEME_KEY}', {json.dumps(json.dumps(seed))});
      window.__firstPaintPrimary = null;
      new MutationObserver((records, observer) => {{
        const app = document.getElementById('app');
        if (app && app.firstElementChild) {{
          window.__firstPaintPrimary = getComputedStyle(document.documentElement).getPropertyValue('--ui-color-primary').trim();
          observer.disconnect();
        }}
      }}).observe(document, {{ childList: true, subtree: true }});
    """)
    page = await context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    await page.goto(BASE + '/')
    await expect(page.locator('#app > *').first).to_be_attached()
    first = await page.evaluate('window.__firstPaintPrimary')
    await page.screenshot(path=str(output / 'console-ocean.png'))
    await context.close()
    problems = [] if first == '#2f6bd8' and not errors else [f'首屏主色 {first} 错误 {errors}']
    return {'problems': problems, 'first_paint_primary': first}


async def verify_design(browser, url: str) -> dict:
    """演示页与 doc/design/console-v2 设计稿逐项比对计算样式。@return 结果摘要。"""
    mock = await browser.new_page(viewport={'width': 1440, 'height': 900})
    demo = await browser.new_page(viewport={'width': 1440, 'height': 900})
    await demo.goto(url)
    await demo.evaluate('document.fonts.ready')
    # 需要先打开示例弹窗的比对动作 → 演示页上的打开按钮。
    openers = {'dialog': '打开弹窗示例', 'modal': '打开居中弹窗示例', 'side': '打开靠右抽屉示例'}
    problems, compared, opened = [], 0, None
    for screen, mock_selector, demo_selector, props, action in DESIGN_PAIRS:
        # 设计稿只在加载时读取 #画面，带不同查询参数强制重新渲染。
        await mock.goto(f'{MOCK}?s={screen}#{screen}')
        await mock.evaluate('document.fonts.ready')
        if opened and action != opened:
            await demo.keyboard.press('Escape')
            await demo.wait_for_timeout(300)
            opened = None
        if action in openers and not opened:
            await demo.get_by_role('button', name=openers[action]).click()
            await demo.wait_for_timeout(400)
            opened = action
        target = demo.locator(demo_selector).first
        if action in ('hover', 'focus'):
            await (target.hover() if action == 'hover' else target.click())
            await demo.wait_for_timeout(250)
        script = '(e, names) => Object.fromEntries(names.map(n => [n, n === "font-family" ? getComputedStyle(e).fontFamily.split(",")[0] : getComputedStyle(e).getPropertyValue(n)]))'
        source = mock.locator(mock_selector).first
        if not await source.count() or not await target.count():
            problems.append(f'{screen} {mock_selector}: 找不到对应元素')
            continue
        expected = await source.evaluate(script, props)
        actual = await target.evaluate(script, props)
        skip = KNOWN.get((screen, mock_selector), set())
        problems.extend(f'{screen} {mock_selector} {prop}: 设计稿 {expected[prop]} 演示页 {actual[prop]}' for prop in props if prop not in skip and expected[prop] != actual[prop])
        compared += 1
        if action in ('hover', 'focus'):
            await demo.mouse.click(5, 5)
    await mock.close()
    await demo.close()
    return {'problems': problems, 'compared': compared}


async def verify(url: str, output: Path) -> None:
    """执行全部检查并写入证据。@param url 演示页地址。@param output 证据目录。@return 无。"""
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        result = {
            'design': await verify_design(browser, url),
            'preview': await verify_preview(browser, url, output),
            'storage': await verify_storage(browser, url),
            'motion': await verify_motion(browser, url),
            'first_paint': await verify_first_paint(browser, output),
        }
        await browser.close()
    problems = [item for part in result.values() for item in part['problems']]
    problems += [f'控制台错误 {item}' for item in result['preview']['errors']]
    problems += [f'业务请求 {item}' for item in result['preview']['business']]
    result['passed'] = not problems
    (output / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    assert not problems, '\n'.join(problems)
    print('组件库与主题运行时验证通过')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='验证组件库演示页与主题运行时')
    parser.add_argument('--url', default='http://127.0.0.1:4187/ui-preview.html')
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/console-ui-revamp/ui-kit/verify')
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.output))
