"""运行环境页与环境管理抽屉的第二版外观：结构节点存在、页面自有元素的颜色只取 token，保存桌面与窄屏截图
（代理页见 verify_records_pages_design.py，环境页对 console-v2 设计稿的逐项比对见 verify_native_pages_design.py）。"""
import asyncio,json
from playwright.async_api import async_playwright
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import ROOT,BASE
from verify_native_pages_design import tokens_only


async def main():
    """输出桌面与窄屏证据，核对所选节点存在且颜色只取 token。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/environment-proxy-audit';out.mkdir(parents=True,exist_ok=True);problems=[]
    # 旧原型用例已移除：环境页换成第二版实体卡（EntityCard），节点按新结构定位。
    nodes={'卡片':'.environment-rich','卡片头部':'.environment-rich .fui-entity-card-head','环境名称':'.environment-rich .fui-entity-card-name','组件状态':'.environment-role-strip','资源':'.environment-resources-grid','预热':'.environment-readiness','操作栏':'.environment-rich .fui-entity-card-actions'}
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        for width in (1440,390):
            fixture=WorkspaceFixture();context=await browser.new_context(viewport={'width':width,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");page=await context.new_page()
            await page.goto(BASE+'/environments');await page.locator('.environment-rich').first.wait_for();await page.evaluate('document.fonts.ready')
            for label,selector in nodes.items():
                if not await page.locator(selector).count():problems.append(f'{width} 缺少节点：{label} {selector}')
            await tokens_only(page,'.runtime-environments',f'environments-{width}',problems)
            await page.screenshot(animations='disabled',path=str(out/f'environments-{width}.png'))
            await page.locator('.environment-rich').first.get_by_role('button',name='环境详情',exact=True).click();await page.locator('.runtime-environment-workspace').wait_for()
            await tokens_only(page,'.runtime-environment-workspace',f'environment-drawer-{width}',problems)
            await page.screenshot(animations='disabled',path=str(out/f'environment-workspace-{width}.png'));await context.close()
        (out/'styles.json').write_text(json.dumps(problems,ensure_ascii=False,indent=2));print(json.dumps(problems,ensure_ascii=False,indent=2));await browser.close();assert not problems,problems


if __name__=='__main__':asyncio.run(main())
