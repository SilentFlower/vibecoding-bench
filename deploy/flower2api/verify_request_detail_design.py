"""验证请求详情四分区、阶段证据和窄屏布局（第二版靠右抽屉，旧原型比对已移除）。"""
import asyncio,json
from playwright.async_api import async_playwright,expect
from verify_environment_ui import ROOT,BASE
from verify_native_diagnostics_cpu import DiagnosticsCpuFixture,REQUEST


async def verify_tui_stages(page, dialog):
    """验证 V2 详情按来源展示已观测正文和 TLS 缺口。
    @param page 隔离浏览器页。@param dialog 请求详情。@return 无。
    """
    detail = BASE + '/admin/request-diagnostics/' + REQUEST
    attempt = '44444444-4444-4444-8444-444444444444'
    row = {'request_id': REQUEST, 'account_id': 1, 'attempt_count': 1, 'outcome': 'success', 'log_mode': 'debug'}
    observed = {'attempt_id': attempt, 'account_id': 1, 'ordinal': 1, 'status_code': 200,
                'outcome': 'success', 'context': {'kernel': 'tui_v2'}, 'capture_status': 'queued', 'log_mode': 'debug'}
    preview = {'headers': [], 'body_truncated': False, 'headers_truncated': False,
               'original_body_bytes': None, 'original_body_sha256': None}
    missing = '独立提供方的对外 TLS 写出尚未观测'
    snapshot = {**preview, 'stage': 'tui_provider_request', 'body': '{"model":"test"}', 'headers': [['Accept','text/event-stream']],
                'ingress': {**preview, 'headers': [['X-Trace','fixture']], 'body': '{"metadata":{"audit_label":"test"}}'},
                'stages': [{'stage':'ingress', 'status':'complete', 'source':'gateway_http_ingress', 'representation':'http_logical_bytes'},
                           {'stage':'tui_provider_request', 'status':'complete', 'source':'tui_sender_http', 'representation':'http_request_to_local_provider'},
                           {'stage':'wire_final', 'status':'unavailable', 'source':'unavailable', 'representation':'unavailable', 'note':missing}]}
    await page.route(detail, lambda route: route.fulfill(json={'request':row, 'attempts':[observed]}))
    await page.route(detail+'/captures/'+attempt, lambda route: route.fulfill(json={'state':'saved', 'snapshot':snapshot}))
    await page.get_by_role('button', name='详情', exact=True).first.click()
    await dialog.get_by_role('button', name='阶段证据', exact=True).click()
    stages = dialog.locator('[data-native-stages]')
    await expect(stages.get_by_role('button', name='模型请求提交')).to_have_attribute('aria-pressed', 'true')
    await expect(stages.get_by_role('columnheader', name='最终 TLS', exact=True)).to_be_visible()
    await expect(stages.get_by_role('row').filter(has_text='accept').first).to_contain_text('未知')
    await expect(stages.get_by_role('row').filter(has_text='x-trace')).to_contain_text('逐字段处理原因未记录')
    await expect(stages.locator('pre').last).to_contain_text('"model"')
    await stages.get_by_role('button', name='入口原文').click()
    await expect(stages.locator('pre').last).to_contain_text('audit_label')
    await stages.get_by_role('button', name='最终TLS写出').click()
    await expect(stages.locator('.request-empty-capture')).to_contain_text('最终 TLS 写出未采集')
    await expect(stages.locator('pre')).to_have_count(0)
    for representation, target, label, note in (
        ('request_to_account_sender', None, '提交给账号发送器', '当前发送器未采集最终 TLS 写出。'),
        ('http_request_written_to_loopback_provider', None, '提交给本地提供方', missing),
        ('http_request_to_local_provider', 'request_to_account_sender', '提交给账号发送器', '本次只保存提交阶段。'),
        ('http_request_to_local_provider', 'http_request_written_to_loopback_provider', '提交给本地提供方', missing),
    ):
        snapshot['stages'][1]['representation'] = representation
        if target:
            snapshot['stages'][1]['submission_format'] = target
        snapshot['stages'][2]['note'] = note
        await dialog.get_by_role('button', name='刷新阶段证据').click()
        await expect(stages.get_by_role('button', name=label)).to_be_visible()
        await stages.get_by_role('button', name='最终TLS写出').click()
        await expect(stages.locator('.request-empty-capture')).to_contain_text(note)

    snapshot['header_policy'] = {
        'source': 'native_header_policy', 'status': 'complete', 'observed_count': 2, 'stored_count': 2,
        'decisions': [{'name': 'accept', 'action': 'runtime', 'reason': '由账号发送器生成'},
                      {'name': 'x-trace', 'action': 'drop', 'reason': '网关未转交该头'}],
    }
    snapshot['wire_final'] = {**preview, 'headers': [['Host', 'fixture.test']], 'body': '{}',
                              'complete': True, 'status': 'complete', 'source': 'tui_sender_tls'}
    snapshot['ingress']['headers_truncated'] = True
    await dialog.get_by_role('button', name='刷新阶段证据').click()
    await expect(stages.locator('.request-header-runtime')).to_contain_text('由账号发送器生成')
    host = stages.get_by_role('row').filter(has=page.get_by_text('host', exact=True))
    await expect(host).to_contain_text('未知')
    await expect(host).to_contain_text('已记录')
    for width in (1440, 720, 390):
        await page.set_viewport_size({'width': width, 'height': 1000})
        assert await dialog.evaluate('e => e.scrollWidth <= e.clientWidth')
        await expect(stages.get_by_role('columnheader', name='最终 TLS')).to_be_visible()
    await stages.get_by_role('combobox', name='筛选头部处理动作').click()
    await page.get_by_role('option', name='只看删除', exact=True).click()
    await expect(stages.locator('.request-evidence-table tbody tr')).to_have_count(1)
    await expect(stages.locator('.request-header-drop')).to_contain_text('x-trace')


async def main():
    """核对真实组件及字体尺寸，所有请求使用合成证据。@return 无。"""
    fixture=DiagnosticsCpuFixture(ROOT/'apps/web/dist');errors=[];out=ROOT/'.deploy/frontend-sidebar-refresh/request-deep';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/requests');await page.get_by_role('button',name='详情',exact=True).click();dialog=page.locator('.request-workspace');await expect(dialog.locator('.request-attempt-summary')).to_have_count(2)
        # 第二版：详情为靠右抽屉（ModalDialog placement=side），外框由 verify_ui_kit.py 对设计稿核对、各页签由 verify_records_pages_design.py 截图目视；旧原型逐项比对已移除。
        await page.evaluate('document.fonts.ready');await page.screenshot(animations='disabled',path=str(out/'overview-1440.png'))
        await dialog.get_by_role('button',name='查看链路',exact=True).first.click();await expect(dialog.locator('.request-chain-card')).to_have_count(2);await expect(dialog.get_by_role('tab',name='请求链路')).to_have_attribute('aria-selected','true')
        await dialog.get_by_role('tab',name='性能',exact=True).click();await expect(dialog.locator('.request-performance-card')).to_have_count(2);await page.screenshot(animations='disabled',path=str(out/'performance-1440.png'))
        await dialog.get_by_role('tab',name='概览',exact=True).click();await dialog.get_by_role('button',name='阶段证据',exact=True).first.click();stages=dialog.locator('[data-native-stages]');await expect(stages.locator('.request-stages article')).to_have_count(4);await expect(stages.locator('.request-header-drop')).to_contain_text('x-unregistered');await expect(stages.locator('.request-header-runtime')).to_contain_text('authorization')
        await stages.get_by_role('combobox',name='筛选头部处理动作').click();await page.get_by_role('option',name='只看删除',exact=True).click();await expect(stages.locator('.request-evidence-table tbody tr')).to_have_count(1);await stages.get_by_role('button',name='入口原文',exact=True).click();await expect(stages.locator('.request-code-block pre').last).to_contain_text('[REDACTED]');assert await page.evaluate('window.stageInjected===undefined')
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});assert await dialog.evaluate('e=>e.scrollWidth<=e.clientWidth');assert await page.locator('html').evaluate('e=>e.scrollWidth<=innerWidth');await page.screenshot(animations='disabled',path=str(out/f'raw-{width}.png'))
        await dialog.get_by_role('combobox',name='当前尝试',exact=True).click();await page.get_by_role('option',name='尝试 2',exact=False).click();await dialog.get_by_role('button',name='读取阶段证据',exact=True).click();await expect(stages.get_by_text('历史记录未保存逐字段处理明细。',exact=True)).to_be_visible();await expect(stages.get_by_text('本次未采集独立最终TLS写出',exact=True)).to_be_visible()
        await page.keyboard.press('Escape')
        await expect(dialog).to_have_count(0)
        await verify_tui_stages(page, dialog)
        await page.keyboard.press('Escape')
        await expect(dialog).to_have_count(0)
        assert not errors, errors
        assert not fixture.unexpected, fixture.unexpected
        print(json.dumps({'status': 'passed', 'screens': [1440, 720, 390],
                          'flows': ['概览与链路', '性能', '采集与动作筛选', '原文阶段', '历史缺失',
                                    'V2 提供方请求与 TLS 缺口', 'HTML转义', '关闭']}, ensure_ascii=False))
        await browser.close()


if __name__=='__main__':asyncio.run(main())
