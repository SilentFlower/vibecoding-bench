"""用合成后台验证真实AGY环境页面和既有CPU草稿生命周期。"""
import asyncio
import json

from playwright.async_api import async_playwright, expect
from verify_environment_ui import BASE, ROOT
from verify_native_diagnostics_cpu import DiagnosticsCpuFixture


async def run() -> dict:
    """核对平台展示、原控件、草稿、焦点和移动布局。@return 浏览器证据。"""
    fixture=DiagnosticsCpuFixture(ROOT/'apps/web/dist')
    row=fixture.rows[0]
    account_name = '反重力测试账号'
    row.update(platform='antigravity',account_id=None,gateway_account_id=17,name='agy:17',
        gateway_account_name=account_name,request_backend='agy159',run_window=None,
        native_kernel=None,native_kernels=None,native_preparation=None,cli_versions=[],criu=None,
        agy_runtime={'version':'1.5.9','source_sha256':'39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43',
            'state':'unprepared','preparation_reason':'waiting_capacity','workers':0,'idle_workers':0,
            'active':0,'tool_waiting':0,'max_workers':1,'image_bytes':265700040,'controller':{'Rss':22000}})
    errors=[]
    out=ROOT/'.trellis/.runtime/agy-environment-ui';out.mkdir(parents=True,exist_ok=True)

    async def kernel_catalog(route):
        """返回当前环境的候选目录。@param route 候选目录请求。@return 无。"""
        if route.request.method != 'GET':
            await fixture.route(route)
            return
        payload = {'generation': row['generation'], 'kernel': None, 'candidates': []}
        await route.fulfill(content_type='application/json', body=json.dumps(payload))

    async def tool_continuation(route):
        """提供当前环境的只读续轮策略。@param route 管理请求。@return 无。"""
        await route.fulfill(content_type='application/json', body=json.dumps({
            'mode': 'claim', 'revision': 0, 'generation': row['generation'], 'supported': True,
        }))

    async with async_playwright() as driver:
        browser=await driver.chromium.launch()
        context=await browser.new_context(viewport={'width':1440,'height':1000})
        await context.route('**/*',fixture.route)
        await context.route(BASE + '/runtime/api/environments/' + row['environment_id'] + '/agy-kernel', kernel_catalog)
        await context.route(BASE + '/runtime/api/environments/' + row['environment_id'] + '/agy-tool-continuation', tool_continuation)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda error:errors.append(error.stack))
        await page.goto(BASE+'/environments')
        card = page.locator('[data-environment="' + row['environment_id'] + '"]')
        # 第二版实体卡标题为 h3（EntityCard）。
        await expect(card.get_by_role('heading', level=3)).to_contain_text(account_name)
        await expect(card.get_by_text('网关账号 #17', exact=True)).to_be_visible()
        await expect(card.get_by_text('等待准备 · 等待节点容量', exact=True)).to_be_visible()
        for reason, label in [('credentials_not_ready', '等待凭据就绪'),
                              ('agy_environment_unavailable', '环境登记或绑定暂不可用'),
                              ('orchestrator_upgrade_required', '编排服务需升级')]:
            row['agy_runtime']['preparation_reason'] = reason
            await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            await expect(card.get_by_text(f'等待准备 · {label}', exact=True)).to_be_visible()
        row['agy_runtime'].update(state='failed', preparation_reason='agy_warm_failed')
        await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        await expect(card.get_by_text('准备失败 · 热进程启动失败', exact=True)).to_be_visible()
        row['agy_runtime'].update(state='ready', preparation_reason=None, workers=1, idle_workers=1)
        await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        await expect(card.get_by_text('热进程就绪', exact=True)).to_be_visible()
        await card.get_by_role('button',name='请求内核',exact=True).click()
        workspace=page.locator('.runtime-environment-dialog')
        await expect(workspace.locator('.workspace-panel-context')).to_contain_text(account_name)
        await expect(workspace).to_contain_text('Antigravity 1.5.9')
        await expect(workspace.get_by_role('combobox', name='请求内核', exact=True)).to_be_visible()
        await expect(workspace.get_by_role('tab',name='运行时段',exact=True)).to_have_count(0)
        await expect(workspace.get_by_text('此环境当前使用基础转发方式。',exact=True)).to_have_count(0)
        await workspace.get_by_role('tab',name='资源与采集',exact=True).click()
        cpu=workspace.get_by_role('spinbutton',name='CLI CPU',exact=True)
        await expect(cpu).to_be_enabled();await cpu.fill('2.25');await cpu.focus()
        handle=await cpu.element_handle()
        await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        await page.wait_for_timeout(500)
        await expect(cpu).to_have_value('2.25')
        if not await handle.evaluate('element=>element===document.activeElement'):raise ValueError('环境轮询改变草稿焦点')
        await expect(workspace.get_by_role('switch',name='CRIU 加速',exact=True)).to_have_count(0)
        await expect(workspace.get_by_role('switch',name='请求内容采集',exact=True)).to_be_enabled()
        for width in (1440,720,390):
            await page.set_viewport_size({'width':width,'height':900})
            if not await workspace.evaluate('element=>element.scrollWidth<=element.clientWidth'):raise ValueError('AGY环境窄屏溢出')
            await page.screenshot(path=str(out/f'environment-{width}.png'))
            if width==390:
                details=await workspace.evaluate('element=>Array.from(element.querySelectorAll("form, .workspace-form-footer, button, [role=switch]")).map(node=>({text:node.textContent?.trim(),role:node.getAttribute("role"),width:node.getBoundingClientRect().width,x:node.getBoundingClientRect().x})).filter(item=>item.width>0)')
                (out/'bounds.json').write_text(json.dumps(details,ensure_ascii=False))
                ancestors=await cpu.evaluate('element=>{let result=[];while(element){let box=element.getBoundingClientRect();let style=getComputedStyle(element);result.push({tag:element.tagName,classes:element.className,x:box.x,width:box.width,csswidth:style.width,min:style.minWidth,display:style.display,overflow:style.overflow});element=element.parentElement;}return result;}')
                (out/'ancestors.json').write_text(json.dumps(ancestors,ensure_ascii=False))
                for item in details:
                    if item['text']=='保存并应用' or item['role']=='switch':
                        if item['x']<0 or item['x']+item['width']>width:raise ValueError('移动端操作控件越过视口')
        await workspace.get_by_role('button',name='关闭环境详情',exact=True).click()
        await page.set_viewport_size({'width':1440,'height':1000})
        await page.get_by_role('link',name='请求记录',exact=True).first.click()
        reads=fixture.reads;await page.wait_for_timeout(2200)
        if fixture.reads!=reads or errors or fixture.unexpected:raise ValueError('AGY环境离页清理或浏览器回归失败')
        await browser.close()
    return {'passed':True,'checks':['AGY账号名称、平台版本和资源','等待容量、准备失败、热进程已就绪',
        '原CPU和采集控件','轮询草稿节点与焦点','1440/720/390px','离页轮询释放'],'errors':errors}


if __name__=='__main__':print(json.dumps(asyncio.run(run()),ensure_ascii=False))
