"""采样运行环境与代理的定稿字体、布局及工作区，保存实际渲染对照。"""
import asyncio,json
from playwright.async_api import async_playwright
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import ROOT,BASE
from audit_token_task_design import sample


async def main():
    """输出桌面与窄屏证据，严格核对所选组件的渲染样式。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/environment-proxy-audit';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();ref=await browser.new_page(viewport={'width':1440,'height':1000});await ref.goto((ROOT/'doc/design/flower2api-concept.html').as_uri());await ref.add_style_tag(content='.preview-bar{display:none!important}:root{--preview-visible-height:0px}.app{min-height:100dvh}.sidebar{height:100dvh}')
        fixture=WorkspaceFixture();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light')");actual=await context.new_page();results={}
        cases=[('proxies','/proxies',"navigate('proxies')",{
            '表头':('.proxy-table th','.proxy-table th'),'名称':('.proxy-table .account-name strong','.proxy-identity strong'),'地址':('.proxy-table .account-name code','.proxy-identity code'),'出口IP':('.proxy-exit>code','.proxy-exit>code'),'地区':('.proxy-exit>span','.proxy-exit>span'),'延迟':('.proxy-latency>strong','.proxy-latency>strong'),'时间':('.proxy-latency>span','.proxy-latency>span'),'状态':('.proxy-table .status-dot','.proxy-status')}),
            ('environments','/environments',"navigate('environments')",{'卡片':('.environment-rich','.environment-rich'),'卡片标题':('.environment-card-head','.environment-card-head'),'环境名称':('.environment-identity h2','.environment-identity h2'),'组件状态':('.environment-role-strip','.environment-role-strip'),'资源':('.environment-resources-grid','.environment-resources-grid'),'准备状态':('.environment-readiness','.environment-readiness'),'操作栏':('.environment-card-actions','.environment-card-actions')})]
        for name,path,script,mapping in cases:
            await ref.evaluate(script);await actual.goto(BASE+path);target=actual;await target.locator('.environment-rich' if name=='environments' else '.proxy-identity').first.wait_for();await target.locator('body').evaluate('()=>document.fonts.ready');await ref.evaluate('document.fonts.ready')
            data={}
            for label,(left,right) in mapping.items():
                if not await target.locator(right).count():data[label]={'missing':right};continue
                expected,observed=await sample(ref,left),await sample(target,right);data[label]={'reference':expected,'actual':observed,'differences':{key:[expected[key],observed[key]] for key in expected if key!='borderColor' and expected[key]!=observed[key]}}
            results[name]=data;await ref.screenshot(animations='disabled',path=str(out/f'{name}-reference.png'));await actual.screenshot(animations='disabled',path=str(out/f'{name}-actual.png'))
            if name=='environments':
                await ref.evaluate('selected=accounts[0].id;openEnvironmentWorkspace()');await target.locator('.environment-rich').first.get_by_role('button',name='环境详情',exact=True).click();await target.locator('.runtime-environment-dialog').wait_for();await actual.screenshot(animations='disabled',path=str(out/'workspace-actual.png'));await ref.screenshot(animations='disabled',path=str(out/'workspace-reference.png'))
        (out/'styles.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps({name:{key:value.get('differences',value) for key,value in data.items()} for name,data in results.items()},ensure_ascii=False,indent=2));await browser.close()


if __name__=='__main__':asyncio.run(main())
