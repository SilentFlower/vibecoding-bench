"""以同一视口读取定稿与任务模块的布局和样式，保存差异证据（令牌页已迁至第二版，见 verify_records_pages_design.py）。"""
import asyncio,json
from playwright.async_api import async_playwright
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import ROOT,BASE

PROPS=['display','flexDirection','flexWrap','flexBasis','alignItems','justifyContent','fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','color','backgroundColor','borderColor','borderRadius','padding','margin','gap','boxShadow']


async def sample(page,selector):
    """获取元素样式。@param page 页面或子文档。@param selector 选择器。@return 属性。"""
    node=page.locator(selector).first
    if not await node.count():raise AssertionError(f'缺少对照节点：{selector}')
    return await node.evaluate('(node,keys)=>Object.fromEntries(keys.map(key=>[key,getComputedStyle(node)[key]]))',PROPS)


async def main():
    """输出两模块逐元素差异与对照截图。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/token-task-audit';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();reference=await browser.new_page(viewport={'width':1440,'height':1000});await reference.goto((ROOT/'doc/design/flower2api-concept.html').as_uri());await reference.add_style_tag(content='.preview-bar{display:none!important}:root{--preview-visible-height:0px}.app{min-height:100dvh}.sidebar{height:100dvh}')
        fixture=WorkspaceFixture();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light')");actual=await context.new_page();results={}
        # 「权限按钮」等基础组件外观由组件库负责，已迁至 verify_ui_kit.py 按 token 与 console-v2 设计稿核对；这里只比对页面结构。
        # 令牌页已换成第二版数据表，由 verify_records_pages_design.py 对 console-v2 设计稿核对，旧原型用例移除。
        for name,route,script,mapping in [
            ('task-accounts','/tasks',"navigate('tasks');taskTab='accounts';repaintWork()",{'模块导航':('.work-navigation','.work-navigation'),'模块工具栏':('.work-list-toolbar','.work-list-toolbar'),'账号卡片':('.work-account','.work-account'),'账号标题':('.work-account>header','.work-account>header'),'卡片名称':('.work-account h3','.work-account h3'),'信息行':('.work-condition','.work-condition'),'网关关联':('.work-gateway-actions','.work-gateway-actions'),'卡片底栏':('.work-account>footer','.work-account>footer')}),
            *[(f'task-{tab}-{pane}',f'/tasks?tab={tab}',f"navigate('tasks');taskTab='{tab}';workView.pane='{pane}';repaintWork()",mapping) for tab,pane,mapping in [
                ('projects','overview',{'上下文':('.work-context','.work-context'),'概览':('.work-hero','.work-hero'),'指标':('.work-summary-grid','.work-summary-grid'),'执行布局':('.work-execution-grid','.work-execution-grid'),'终端':('.work-terminal','.work-terminal')}),
                ('projects','pool',{'表单':('.work-config','#projects-agent-settings'),'分栏':('.work-config-columns','.work-config-columns')}),
                ('projects','schedule',{'表单':('.work-config','#projects-schedule-settings')}),
                ('projects','model',{'表单':('.work-config','#projects-model-settings')}),
                ('projects','history',{'历史面板':('.work-panel','.work-history')}),
                ('warmup','overview',{'概览':('.work-hero','.work-hero')}),
                ('topics','overview',{'题目卡片':('.work-topic','.work-topic')}),
                ('tasks','overview',{'任务表格':('.work-table','.work-table')}),
                ('runs','overview',{'运行表格':('.work-table','.work-table')}),
            ]],
        ]:
            await reference.evaluate(script);await actual.goto(BASE+route);target=actual;await target.locator('.work-navigation').first.wait_for();
            if name.startswith(('task-projects-','task-warmup-')):
                await target.locator('#projects-cli-settings:not([disabled])').wait_for();await target.locator(f'[data-project-pane={name.split("-")[-1]}]').click()
            await actual.evaluate('document.fonts.ready');await reference.evaluate('document.fonts.ready');await target.locator('body').evaluate('()=>document.fonts.ready');await target.locator(next(iter(mapping.values()))[1]).first.wait_for()
            values={}
            for key,(left,right) in mapping.items():
                expected,observed=await sample(reference,left),await sample(target,right);values[key]={'reference':expected,'actual':observed,'differences':{prop:[expected[prop],observed[prop]] for prop in PROPS if prop!='borderColor' and expected and observed and expected[prop]!=observed[prop]}}
            results[name]=values;await reference.screenshot(path=str(out/f'{name}-reference.png'));await actual.screenshot(path=str(out/f'{name}-actual.png'));(out/f'{name}-reference.html').write_text(await reference.locator('#page').inner_html())
        (out/'styles.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps({name:{key:value['differences'] for key,value in values.items()} for name,values in results.items()},ensure_ascii=False,indent=2));assert not any(value['differences'] for values in results.values() for value in values.values()),'存在待修正的渲染样式差异';await browser.close()


if __name__=='__main__':asyncio.run(main())
