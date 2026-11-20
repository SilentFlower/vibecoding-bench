"""任务模块六个入口与工程五个分区的第二版外观：结构节点存在、页面自有元素的颜色只取 token，并保存截图（令牌页见 verify_records_pages_design.py，页面级设计稿比对见 verify_native_pages_design.py）。"""
import asyncio,json
from playwright.async_api import async_playwright
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import ROOT,BASE
from verify_native_pages_design import tokens_only



async def main():
    """逐入口核对结构节点与颜色 token，保存截图。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/token-task-audit';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();fixture=WorkspaceFixture();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");actual=await context.new_page();results={}
        # 旧原型逐项比对已移除：任务页换成第二版外观，页签、区块头与任务账号卡由 verify_native_pages_design.py 对 console-v2 设计稿核对；
        # 这里逐入口确认结构节点存在、颜色只取 token，并保存截图供目视。
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
            await actual.goto(BASE+route);target=actual;await target.locator('.work-navigation').first.wait_for();
            if name.startswith(('task-projects-','task-warmup-')):
                await target.locator('#projects-cli-settings:not([disabled])').wait_for();await target.locator(f'[data-project-pane={name.split("-")[-1]}]').click()
            await actual.evaluate('document.fonts.ready');await target.locator(next(iter(mapping.values()))[1]).first.wait_for()
            problems=[]
            for key,(_,right) in mapping.items():
                if not await target.locator(right).count():problems.append(f'缺少节点：{key} {right}');continue
                await tokens_only(target,right,f'{name} {key}',problems)
            results[name]=problems;await actual.screenshot(path=str(out/f'{name}-actual.png'))
        (out/'styles.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2));assert not any(results.values()),results;await browser.close()

if __name__=='__main__':asyncio.run(main())
