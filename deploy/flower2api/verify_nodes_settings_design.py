"""对照第二版设计稿（mock.html #nodes、#settings）核对节点管理与系统设置两页的计算样式，
并验证节点待处理口径与状态徽标色、节点弹窗宽度、设置「已修改」标签与分类计数、撤销清零、搜索结果、390 无横向滚动与零控制台错误；
设计稿未画的画面（八种节点状态、弹窗、搜索结果与空态、预热记录、390 形态）截图供目视确认。真实构建 + 合成接口，不触达外部服务。"""
import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_cluster_ui import ClusterUiFixture
from verify_environment_ui import BASE, ROOT
from verify_remaining_pages import RemainingPagesFixture

MOCK = (ROOT / 'doc/design/console-v2/mock.html').as_uri()
DIST = ROOT / 'apps/web/dist'
TEXT = ['color', 'font-size', 'font-weight', 'font-family', 'line-height']
BOX = ['height', 'padding-left', 'border-top-left-radius', 'background-color', 'color', 'font-size', 'font-weight']
CARD = ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'column-gap']
TILE = ['width', 'height', 'border-top-left-radius', 'background-color', 'color']
# 与设计稿逐项对照：(画面, 设计稿选择器, 页面选择器, 属性)
PAIRS = [
    # 节点管理：概览卡、实体卡、账号执行节点卡
    ('nodes', '.grid.g4', '.nodes-overview', ['column-gap', 'row-gap']),
    ('nodes', '.ov', '.nodes-overview > :first-child', CARD),
    ('nodes', '.ov p', '.nodes-overview > :first-child .fui-overview-card-label', TEXT),
    ('nodes', '.ov strong', '.nodes-overview > :first-child .fui-overview-card-value', TEXT),
    ('nodes', '.ov > div > span', '.nodes-overview > :first-child .fui-overview-card-caption', TEXT),
    ('nodes', '.ov .ico.i', '.nodes-overview > :nth-child(2) .fui-icon-tile', ['background-color', 'color']),
    ('nodes', '.ov .ico.s', '.nodes-overview > :nth-child(3) .fui-icon-tile', ['background-color', 'color']),
    ('nodes', '.ov .ico.w', '.nodes-overview > :nth-child(4) .fui-icon-tile', ['background-color', 'color']),
    ('nodes', '.grid.g2', '.nodes-grid', ['column-gap']),
    ('nodes', '.card.ent', '.node-card', ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'padding-bottom', 'row-gap']),
    ('nodes', '.ent-head', '.node-card .fui-entity-card-head', ['column-gap', 'align-items']),
    ('nodes', '.ent-head .tile', '.node-card .fui-icon-tile', TILE),
    ('nodes', '.ent-head h4', '.node-card .fui-entity-card-title', TEXT),
    ('nodes', '.ent-head p', '.node-card .fui-entity-card-subtitle', ['font-size', 'font-weight', 'color']),
    ('nodes', '.ent-head p.mono', '.node-card .node-address', ['font-family']),
    ('nodes', '.ent-head > .tag', '.node-card .node-state', BOX),
    ('nodes', '.ent-head > .tag.tg-warning', '.node-card:nth-child(2) .node-state', ['background-color', 'color']),
    ('nodes', '.res4', '.node-resources', ['column-gap']),
    ('nodes', '.res4 div', '.node-resources > div', ['row-gap']),
    ('nodes', '.res4 span', '.node-resources dt', TEXT),
    ('nodes', '.res4 b', '.node-resources dd', TEXT),
    ('nodes', '.ent .block', '.node-meta', ['background-color', 'border-top-left-radius', 'padding-top', 'padding-left', 'row-gap']),
    ('nodes', '.ent .block .meta-row', '.node-meta > div', ['font-size', 'font-weight', 'color']),
    ('nodes', '.ent .block .meta-row b', '.node-meta time', ['color', 'font-weight']),
    ('nodes', '.ent .links', '.node-identity summary', ['font-size', 'font-weight', 'color', 'column-gap']),
    ('nodes', '.ent .btn-sm', '.node-actions [data-slot=button]', BOX),
    ('nodes', '.ent .btn-text.dg', '.node-remove', ['color', 'font-size', 'font-weight', 'height', 'padding-left']),
    ('nodes', '.page > section.card', '.account-node-selector', ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'row-gap']),
    ('nodes', '.page > section.card .sec-t', '.account-node-selector h2', TEXT),
    ('nodes', '.page > section.card .sec-t + p', '.account-node-selector > header p', TEXT + ['margin-top']),
    ('nodes', '.page > section.card .fg', '.assignment-fields', ['column-gap', 'row-gap']),
    ('nodes', '.page > section.card .field label', '.account-node-selector .fui-label', TEXT),
    # 系统设置：页头搜索、分类导航、段落卡、字段与「已修改」
    ('settings', '.ph-actions .input', '.settings-header-tools > .fui-search', ['width', 'height', 'background-color', 'border-top-left-radius']),
    ('settings', '.ph-actions > .t3', '.settings-total', TEXT),
    ('settings', '.set', '.system-settings-layout', ['column-gap']),
    ('settings', '.set-nav', '.system-settings-nav', ['row-gap', 'width']),
    ('settings', '.set-nav span.on', '.system-settings-nav button.active', ['height', 'padding-left', 'border-top-left-radius', 'background-color', 'box-shadow', 'column-gap'] + TEXT),
    ('settings', '.set-nav span:not(.on)', '.system-settings-nav button:not(.active)', ['height', 'background-color'] + TEXT),
    ('settings', '.set-nav span.on svg', '.system-settings-nav button.active svg', ['width', 'color']),
    ('settings', '.set-nav span:not(.on) svg', '.system-settings-nav button:not(.active) svg', ['color']),
    ('settings', '.set-nav span.on em', '.system-settings-nav .is-dirty', ['font-size', 'font-weight', 'font-family', 'color']),
    ('settings', '.set-nav span:last-of-type em', '.system-settings-nav button:last-of-type em', ['font-size', 'font-weight', 'font-family', 'color']),
    ('settings', '.set-nav p', '.system-settings-nav > p', TEXT),
    ('settings', '.set > section.card', '.settings-section-card', ['background-color', 'border-top-left-radius', 'box-shadow', 'padding-top', 'padding-left', 'row-gap']),
    ('settings', '.set > section.card > div:first-child', '.settings-section-card > header', ['column-gap', 'align-items']),
    ('settings', '.set > section.card .tile', '.settings-section-card .fui-icon-tile', TILE),
    ('settings', '.set > section.card .sec-t', '.settings-section-card h3', TEXT),
    ('settings', '.set > section.card .sec-t + p', '.settings-section-card > header p', TEXT + ['margin-top']),
    ('settings', '.set .fg', '.settings-field-grid', ['column-gap', 'row-gap']),
    ('settings', '.set .field', '.setting-field', ['row-gap']),
    ('settings', '.set .field label', '.setting-field .fui-label', TEXT),
    ('settings', '.set .field label .tag', '[data-settings-field=v3_admission_wait_seconds] .fui-badge', BOX),
    ('settings', '.set .field:nth-child(2) .input', '.setting-field:nth-child(2) .fui-number', ['height', 'background-color', 'border-top-left-radius']),
    ('settings', '.set .field .help', '.setting-help', TEXT),
    ('settings', '.savebar', '.settings-save-bar', ['background-color', 'border-top-left-radius', 'box-shadow']),
]
# 结构写法不同但视觉等价、或已记录的有意偏差，比对时跳过对应属性。
KNOWN: dict[tuple[str, str], set[str]] = {}
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
        await dialog.evaluate('e => Promise.all(e.getAnimations().map(a => a.finished.catch(() => null)))')
    await page.wait_for_timeout(300)


def node(number: int, name: str, kind: str = 'ssh', **fields) -> dict:
    """合成一台节点。@param number 编号。@param name 名称。@param kind local 或 ssh。@param fields 覆盖字段。@return 节点。"""
    value = {'id': number, 'node_key': 'local' if kind == 'local' else f'{number:032x}', 'name': name, 'kind': kind, 'revision': 1,
        'enabled': True, 'account_count': 0, 'host': None if kind == 'local' else f'node{number}.example.invalid', 'port': 22,
        'username': 'synthetic', 'data_root': '/srv/synthetic', 'host_key_sha256': 'SHA256:synthetic', 'auth_method': 'private_key',
        'observation': None, 'preparation': None if kind == 'local' else {'state': 'prepared', 'release': 'r1', 'updated_at': time.time()}}
    value.update(fields)
    return value


def observed(state: str = 'reachable', stale: bool = False, reason: str | None = None) -> dict:
    """合成一次连接观测。@param state 可达状态。@param stale 是否过期。@param reason 原因。@return 观测。"""
    value = {'state': state, 'observed_at': time.time() - 30, 'stale': stale, 'host_cpus': 8, 'docker_version': '27.3',
        'memory': {'MemTotal': 16 * 1024 ** 3, 'MemAvailable': int(9.4 * 1024 ** 3), 'SwapTotal': 0, 'SwapFree': 0}, 'disk_available_bytes': 66 * 1024 ** 3}
    if reason:
        value['reason'] = reason
    return value


class StatesFixture(ClusterUiFixture):
    """八种节点状态；节点列表原样返回，不经集群夹具的移除模拟改写。"""

    def __init__(self, gateway: Path) -> None:
        """准备覆盖全部状态的节点。@param gateway 构建目录。@return 无。"""
        super().__init__(gateway)
        self.nodes = [
            node(1, '默认节点', 'local', observation=observed(), account_count=1),
            node(2, '待检查节点'),
            node(3, '连接异常节点', observation=observed('unreachable', reason='SSH 连接超时')),
            node(4, '观测过期节点', observation=observed(stale=True)),
            node(5, '组件异常节点', observation=observed(), preparation={'state': 'failed', 'release': 'r1', 'updated_at': time.time(), 'reason': '组件下载失败'}),
            node(6, '暂停接单节点', enabled=False, observation=observed('unreachable')),
            node(7, '移除中节点', enabled=False, removal={'operation_id': 'a' * 32, 'state': 'removing', 'phase': 'clearing_data', 'reason': None}),
            node(8, '移除待重试节点', enabled=False, removal={'operation_id': 'b' * 32, 'state': 'needs_check', 'phase': 'checking', 'reason': 'SSH 连接中断，请核对节点网络'}),
        ]

    async def route(self, route) -> None:
        """节点列表原样返回，其余沿用集群夹具。@param route 浏览器请求。@return 无。"""
        if urlsplit(route.request.url).path == '/runtime/api/nodes':
            await route.fulfill(content_type='application/json', body=json.dumps({'items': self.nodes}))
            return
        await super().route(route)


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


def card(page, name: str):
    """按标题定位节点卡。@param page 页面。@param name 节点名。@return 定位器。"""
    return page.locator('.node-card').filter(has=page.get_by_role('heading', name=name, exact=True))


async def main(output: Path) -> None:
    """对比设计稿画面并验证两页的口径、状态与交互边界。@param output 截图与结果目录。@return 无。"""
    output.mkdir(parents=True, exist_ok=True)
    errors, problems, compared = [], [], 0
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        mock = await browser.new_page(viewport={'width': 1440, 'height': 900})

        # ---------- 节点管理：与设计稿同构的两台节点 ----------
        fixture = ClusterUiFixture(DIST)
        fixture.nodes[0]['observation'] = observed()
        page, context = await open_page(browser, fixture, '/nodes', 1440, 900, errors)
        await expect(page.locator('.node-card')).to_have_count(2)
        await expect(page.locator('.nodes-overview > :nth-child(3) .fui-overview-card-value')).to_have_text('3')
        await settle(page)
        compared += await compare(mock, page, 'nodes', problems)
        await page.screenshot(animations='disabled', path=str(output / 'nodes-1440.png'))
        # 添加节点 640、修改名称 420，均按视口居中。
        await page.get_by_role('button', name='添加节点', exact=True).click()
        editor = page.locator('.node-editor')
        await settle(page, editor)
        geometry = await editor.evaluate('e=>{const r=e.getBoundingClientRect();return {width:e.offsetWidth,center:Math.round(r.left+r.width/2)}}')
        assert geometry == {'width': 640, 'center': 720}, geometry
        await expect(editor.get_by_label('节点名称', exact=True)).to_be_visible()
        await page.screenshot(animations='disabled', path=str(output / 'node-editor-1440.png'))
        await page.keyboard.press('Escape')
        await expect(editor).to_have_count(0)
        await card(page, '上海执行节点').get_by_role('button', name='改名', exact=True).click()
        rename = page.locator('.node-rename')
        await settle(page, rename)
        assert await rename.evaluate('e=>e.offsetWidth') == 420
        await expect(rename.get_by_label('节点名称', exact=True)).to_have_value('上海执行节点')
        await page.screenshot(animations='disabled', path=str(output / 'node-rename-1440.png'))
        await page.keyboard.press('Escape')
        # 关闭淡出期间说明仍是原地址，不出现空字段拼出的 undefined。
        closing = []
        while await rename.count():
            # 不等待的读取：淡出结束时弹窗可能在 count 与读取之间被移除，等待式 inner_text 会一直等到超时。
            closing += await rename.locator('.fui-modal-description').all_inner_texts()
            await page.wait_for_timeout(20)
        assert closing and set(closing) == {'synthetic@node.example.invalid:22'}, closing
        await context.close()

        # ---------- 节点管理：八种状态 ----------
        fixture = StatesFixture(DIST)
        page, context = await open_page(browser, fixture, '/nodes', 1440, 900, errors)
        await expect(page.locator('.node-card')).to_have_count(8)
        overview = page.locator('.nodes-overview')
        await expect(overview.locator('> :nth-child(1) .fui-overview-card-caption')).to_have_text('1 台本机 · 7 台远程')
        await expect(overview.locator('> :nth-child(2) .fui-overview-card-value')).to_have_text('7')
        await expect(overview.locator('> :nth-child(2) .fui-overview-card-caption')).to_have_text('5 台待处理')
        await expect(overview.locator('> :nth-child(4) .fui-overview-card-value')).to_have_text('5')
        await expect(overview.locator('> :nth-child(4) .fui-overview-card-caption')).to_have_text('3 台需检查连接 · 1 台组件异常 · 1 台移除待重试')
        # 状态文案不变，色调按语义：待检查与观测过期为琥珀色。
        for name, text, variant in (('默认节点', '连接正常', 'success'), ('待检查节点', '待检查', 'warning'), ('连接异常节点', '连接异常', 'destructive'),
                ('观测过期节点', '观测已过期', 'warning'), ('组件异常节点', '连接正常', 'success'), ('暂停接单节点', '已暂停接单', 'secondary'),
                ('移除中节点', '移除中', 'info'), ('移除待重试节点', '移除待重试', 'destructive')):
            state = card(page, name).locator('.node-state')
            await expect(state).to_have_text(text)
            await expect(state).to_have_class(re.compile(rf'\bfui-badge-{variant}\b'))
        await expect(card(page, '组件异常节点').locator('.node-alert')).to_have_text('组件下载失败')
        await expect(card(page, '移除待重试节点').get_by_role('button', name='重试移除', exact=True)).to_be_visible()
        await expect(card(page, '移除中节点')).to_contain_text('正在后台移除')
        await settle(page)
        await page.screenshot(animations='disabled', full_page=True, path=str(output / 'nodes-states-1440.png'))
        await context.close()
        # 全部正常时待处理为 0、说明「全部正常」；没有远程节点时远程服务器卡说明「尚未添加」。
        fixture = StatesFixture(DIST)
        fixture.nodes = fixture.nodes[:1]
        page, context = await open_page(browser, fixture, '/nodes', 1440, 900, errors)
        overview = page.locator('.nodes-overview')
        await expect(overview.locator('> :nth-child(4) .fui-overview-card-value')).to_have_text('0')
        await expect(overview.locator('> :nth-child(4) .fui-overview-card-caption')).to_have_text('全部正常')
        await expect(overview.locator('> :nth-child(2) .fui-overview-card-caption')).to_have_text('尚未添加')
        await context.close()

        # ---------- 系统设置 ----------
        fixture = RemainingPagesFixture()
        page, context = await open_page(browser, fixture, '/settings', 1440, 900, errors)
        save = page.get_by_role('button', name='保存配置', exact=True)
        await expect(save).to_be_disabled()
        await expect(page.locator('.settings-total')).to_have_text('60 项配置')
        await expect(page.locator('.fui-badge-warning')).to_have_count(0)
        await page.locator('[name=v3_admission_wait_seconds]').fill('99')
        field = page.locator('[data-settings-field=v3_admission_wait_seconds]')
        await expect(field.locator('.fui-badge-warning')).to_have_text('已修改')
        # 「已修改」不进入字段名称；分类计数只作视觉提示，分类按钮名称保持分类名。
        await expect(page.get_by_role('spinbutton', name='准入等待上限（秒）', exact=True)).to_have_value('99')
        scheduling = page.get_by_role('button', name='会话与调度', exact=True)
        await expect(scheduling.locator('.is-dirty')).to_have_text('1')
        await expect(page.locator('.settings-save-bar')).to_contain_text('1 项待保存')
        await page.locator('.settings-page').evaluate('e => e.ownerDocument.activeElement.blur()')
        await page.mouse.move(0, 0)
        await settle(page)
        compared += await compare(mock, page, 'settings', problems)
        await page.screenshot(animations='disabled', path=str(output / 'settings-1440.png'))
        await page.get_by_role('switch', name='自动封禁', exact=True).click()
        await expect(page.locator('[data-settings-field=session_policy_block_enabled] .fui-badge-warning')).to_have_text('已修改')
        await expect(scheduling.locator('.is-dirty')).to_have_text('2')
        await expect(page.locator('.settings-save-bar')).to_contain_text('2 项待保存')
        await page.screenshot(animations='disabled', path=str(output / 'settings-dirty-1440.png'))
        await page.get_by_role('button', name='撤销修改', exact=True).click()
        await expect(page.locator('.fui-badge-warning')).to_have_count(0)
        await expect(page.locator('.system-settings-nav .is-dirty')).to_have_count(0)
        await expect(page.locator('[name=v3_admission_wait_seconds]')).to_have_value('120')
        await expect(page.get_by_role('switch', name='自动封禁', exact=True)).to_have_attribute('aria-checked', 'true')
        await expect(save).to_be_disabled()
        assert not [write for write in fixture.writes if write['path'] == '/admin/settings']
        # 搜索：跨分类结果行与分类标签，草稿保留。
        await page.locator('[name=v3_admission_wait_seconds]').fill('98')
        await page.get_by_role('button', name='模型与缓存', exact=True).click()
        search = page.get_by_role('searchbox', name='搜索系统设置', exact=True)
        await search.fill('准入等待')
        await expect(page.locator('.settings-search-result')).to_have_text('搜索结果 · 找到 1 项配置')
        await expect(page.locator('.settings-result-category')).to_have_text('会话与调度')
        await expect(page.locator('[name=v3_admission_wait_seconds]')).to_have_value('98')
        await page.screenshot(animations='disabled', path=str(output / 'settings-search-1440.png'))
        await search.fill('不存在的配置项')
        await expect(page.get_by_role('heading', name='没有匹配的配置', exact=True)).to_be_visible()
        await page.screenshot(animations='disabled', path=str(output / 'settings-search-empty-1440.png'))
        await page.get_by_role('button', name='清空搜索', exact=True).click()
        await page.get_by_role('button', name='撤销修改', exact=True).click()
        await page.locator('.system-settings-nav button').filter(has_text='预热记录').click()
        await expect(page.get_by_role('heading', name='最近模型预热记录', exact=True)).to_be_visible()
        await settle(page)
        await page.screenshot(animations='disabled', path=str(output / 'settings-history-1440.png'))
        await context.close()

        # ---------- 390 形态 ----------
        for path, name in (('/nodes', 'nodes'), ('/settings', 'settings')):
            fixture = StatesFixture(DIST) if name == 'nodes' else RemainingPagesFixture()
            page, context = await open_page(browser, fixture, path, 390, 844, errors)
            await expect(page.locator('.node-card' if name == 'nodes' else '.settings-section-card').first).to_be_visible()
            await settle(page)
            await no_overflow(page, f'{name}-390')
            if name == 'nodes':
                # 节点卡单列，资源保持四列。
                widths = await page.locator('.node-card').evaluate_all('cards => cards.map(c => Math.round(c.getBoundingClientRect().width))')
                assert len(set(widths)) == 1 and widths[0] >= 340, widths
                assert await page.locator('.node-resources').first.evaluate('e => getComputedStyle(e).gridTemplateColumns.split(" ").length') == 4
            else:
                # 搜索框占满内容宽，分类导航横向滚动，字段单列。
                search = await page.locator('.settings-header-tools > .fui-search').evaluate('e => Math.round(e.getBoundingClientRect().width)')
                content = await page.locator('.settings-section-card').first.evaluate('e => Math.round(e.getBoundingClientRect().width)')
                assert search == content, (search, content)
                assert await page.locator('.system-settings-nav').evaluate('e => e.scrollWidth > e.clientWidth && getComputedStyle(e).overflowX === "auto"')
                assert await page.locator('.settings-field-grid').first.evaluate('e => getComputedStyle(e).gridTemplateColumns.split(" ").length') == 1
            await page.screenshot(animations='disabled', full_page=True, path=str(output / f'{name}-390.png'))
            await context.close()

        assert not problems, json.dumps(problems, ensure_ascii=False, indent=1)
        assert not errors, errors
        result = dict(passed=True, compared=compared, whitelisted=len(KNOWN), checks=[
            '两页 1440 逐项比对设计稿', '节点添加 640 / 改名 420 居中', '八种状态的文案与徽标色、待处理口径与说明', '全部正常与无远程节点的说明',
            '已修改标签、分类计数与保存栏计数', '开关修改计数、撤销清零且零写入', '搜索结果行、分类标签与草稿保留', '搜索空态', '预热记录',
            '两页 390 无横向滚动、节点卡单列、设置搜索满宽与导航横向滚动', '零控制台错误'])
        (output / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
        await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/console-ui-revamp/nodes-settings/verify')
    asyncio.run(main(parser.parse_args().output))
