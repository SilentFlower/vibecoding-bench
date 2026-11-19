"""验证原生Vue环境工作区的真实接口合同和资源生命周期。"""
import asyncio,json
from playwright.async_api import async_playwright,expect
from verify_native_diagnostics_cpu import DiagnosticsCpuFixture
from verify_environment_ui import BASE,ROOT,ENVIRONMENT


async def run(output=None,gateway=None):
    """使用合成后台覆盖原维护动作，禁止真实网络。@return 无。"""
    fixture=DiagnosticsCpuFixture(gateway or ROOT/'apps/web/dist');errors=[];out=output or ROOT/'.deploy/frontend-sidebar-refresh/native-environment';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/environments');await expect(page.locator('.environment-rich')).to_have_count(4);await expect(page.locator('iframe')).to_have_count(0)
        await page.screenshot(path=str(out/'list-1440.png'));row=page.locator('.environment-rich').first
        await row.get_by_role('button',name='资源与采集',exact=True).click();workspace=page.locator('.runtime-environment-dialog');cpu=workspace.get_by_role('spinbutton',name='CLI CPU',exact=True);await expect(cpu).to_have_value('1.5');await cpu.fill('2.25');node=await cpu.element_handle()
        await workspace.get_by_role('tab',name='请求内核',exact=True).click();await workspace.get_by_role('tab',name='资源与采集',exact=True).click();await expect(cpu).to_have_value('2.25');assert await node.evaluate('node=>node.isConnected')
        await workspace.get_by_role('button',name='保存并应用',exact=True).click();await expect(workspace.get_by_role('status')).to_contain_text('CPU 额度已应用');assert fixture.cpu_writes[-1]['cpus']['cli']==2.25
        fixture.cpu_revision='c'*64;await cpu.fill('3');await workspace.get_by_role('button',name='保存并应用',exact=True).click();await expect(workspace.get_by_role('alert')).to_contain_text('重新读取');await expect(workspace.get_by_role('button',name='保存并应用',exact=True)).to_be_disabled();await workspace.get_by_role('button',name='重新读取',exact=True).click();await expect(cpu).to_have_value('2.25')
        await workspace.get_by_role('switch',name='请求内容采集',exact=True).click();confirm=page.get_by_role('dialog',name='关闭请求内容采集');await confirm.get_by_role('button',name='取消',exact=True).click();assert not any(write['path'].endswith('/content-capture') for write in fixture.writes)
        await workspace.get_by_role('switch',name='请求内容采集',exact=True).click();await confirm.get_by_role('button',name='确认应用',exact=True).click();await expect(confirm).to_have_count(0);assert fixture.writes[-1]['body']['enabled'] is False
        await workspace.get_by_role('switch',name='CRIU 加速',exact=True).click();await page.get_by_role('dialog',name='关闭CRIU 加速').get_by_role('button',name='确认应用').click();await expect(page.get_by_role('dialog',name='关闭CRIU 加速')).to_have_count(0)
        await workspace.get_by_role('tab',name='运行时段',exact=True).click();await workspace.get_by_role('switch',name='启用运行时段').check();await workspace.get_by_role('button',name='时段 1 开始',exact=True).click();await page.get_by_role('spinbutton',name='小时',exact=True).fill('10');await page.get_by_role('button',name='确认',exact=True).click();await workspace.get_by_role('button',name='保存时段',exact=True).click();await expect(workspace.get_by_text('运行时段已保存',exact=True)).to_be_visible();assert fixture.writes[-1]['body']['intervals'][0]['start']=='10:00'
        await workspace.get_by_role('tab',name='请求内核',exact=True).click();await expect(workspace).to_contain_text('随 flower2api 版本统一交付');await expect(workspace.get_by_role('button',name='选择版本',exact=True)).to_have_count(0);assert not any(write['path'].endswith('/native-kernel') for write in fixture.writes)
        await workspace.get_by_role('tab',name='维护操作',exact=True).click();await workspace.get_by_role('button',name='停止环境',exact=True).click();await page.get_by_role('dialog',name='停止环境',exact=True).get_by_role('button',name='确认操作').click();await expect(page.get_by_role('dialog',name='停止环境',exact=True)).to_have_count(0);assert fixture.writes[-1]['body']=={'operation':'stop','expected_generation':fixture.rows[0]['generation']};await expect(page.get_by_role('dialog')).to_have_count(1)
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});assert await workspace.evaluate('el=>el.scrollWidth<=el.clientWidth');await page.screenshot(path=str(out/f'workspace-{width}.png'))
        await workspace.get_by_role('button',name='关闭环境详情').click();await page.goto(BASE+f'/environments?environment={ENVIRONMENT}&section=schedule');await expect(page.get_by_role('tabpanel',name='运行时段',exact=True)).to_be_visible();await expect(page.locator('iframe')).to_have_count(0)
        await workspace.get_by_role('button',name='关闭环境详情').click();await page.set_viewport_size({'width':1440,'height':1000});await page.get_by_role('link',name='请求记录',exact=True).first.click();await expect(page).to_have_url(BASE+'/requests');reads=fixture.reads;await page.wait_for_timeout(2300);assert fixture.reads==reads;assert not errors,errors;assert not fixture.unexpected,fixture.unexpected
        result={'passed':True,'checks':['无iframe','四态环境','CPU草稿节点保留','CAS失败重读','采集取消零写入与应用','CRIU切换','当地时段与时间控件','平台配套内核只读','维护原动作','1440/720/390px','深链接','离页轮询释放'] ,'errors':errors};await browser.close();return result


if __name__=='__main__':print(json.dumps(asyncio.run(run()),ensure_ascii=False))
