"""验证请求详情四分区、阶段证据和窄屏布局（第二版靠右抽屉，旧原型比对已移除）。"""
import asyncio,json
from playwright.async_api import async_playwright,expect
from verify_environment_ui import ROOT,BASE
from verify_native_diagnostics_cpu import DiagnosticsCpuFixture,REQUEST


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
        await page.keyboard.press('Escape');await expect(dialog).to_have_count(0);assert not errors,errors;assert not fixture.unexpected,fixture.unexpected;print(json.dumps({'status':'passed','screens':[1440,720,390],'flows':['概览与链路','性能','采集与动作筛选','原文阶段','历史缺失','HTML转义','关闭']},ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
