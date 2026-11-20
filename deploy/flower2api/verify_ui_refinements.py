"""核对账号列数、用量气泡、悬停反馈和授权选线的真实行为（第二版：列数按定稿规则、外观取 token）。"""
import asyncio
import json
import re
from playwright.async_api import async_playwright,expect
from verify_interaction_parity import InteractionFixture
from verify_environment_ui import ROOT,BASE


async def token(page,name):
    """读取主题 token 的计算色值。@param page 页面。@param name token 名。@return rgb() 字符串。"""
    return await page.evaluate("n=>{const e=document.createElement('i');e.style.color=`var(${n})`;document.body.append(e);const c=getComputedStyle(e).color;e.remove();return c}",name)


def expected_columns(viewport,width):
    """账号网格列规则（ui-guidelines 定稿响应式合同）：≤760 单列，≥1680 四列，其余按卡片最小 320px、间距 16px 自动填充。
    @param viewport 视口宽。@param width 网格实际宽。@return 期望列数。"""
    if viewport<=760:return 1
    if viewport>=1680:return 4
    return max(1,int((width+16)//(320+16)))


async def main():
    """核对第二版账号网格列数、用量气泡与悬停取 token，以及授权选线行为。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/refinements';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        context=await browser.new_context();fixture=InteractionFixture();await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)));await page.emulate_media(reduced_motion='reduce');await page.goto(BASE+'/');await page.locator('.account-card').first.wait_for()
        widths=[390,720,760,761,767,768,1000,1280,1340,1440,1600,1680,1920,2560,3440];layout=[]
        # 账号页按第二版设计稿迁移后不再对照旧原型：列数按定稿响应式规则逐档断言，卡片间距 16px（设计稿 .grid）。
        for width in widths:
            await page.set_viewport_size({'width':width,'height':1000})
            result={'width':width,'actual':await page.locator('.account-card-grid').evaluate('(e)=>({columns:getComputedStyle(e).gridTemplateColumns.split(" ").length,width:e.getBoundingClientRect().width,gap:getComputedStyle(e).columnGap})')}
            result['content']=await page.locator('#console-content').evaluate('(e)=>{const s=getComputedStyle(e);return e.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight)}')
            assert result['actual']['columns']==expected_columns(width,result['actual']['width']),result
            assert result['actual']['gap']=='16px',result
            assert abs(result['content']-result['actual']['width'])<1,result
            layout.append(result)
        await page.set_viewport_size({'width':1680,'height':1000});await page.screenshot(path=str(out/'accounts-four-columns.png'))
        await page.set_viewport_size({'width':1440,'height':1000})
        await page.get_by_role('button',name='查看5h完整费用统计',exact=True).first.hover()
        bubble=page.locator('.usage-cost-bubble');await expect(bubble).to_be_visible()
        await expect(bubble.locator('header')).to_have_text('5 小时用量统计网关记录');await expect(bubble.locator('.usage-bubble-grid>div')).to_have_count(4)
        # 气泡外观取组件库气泡（.fui-info-content）与语义 token。
        props=['width','padding','borderRadius','backgroundColor','color','fontSize']
        get='(e,keys)=>Object.fromEntries(keys.map(k=>[k,getComputedStyle(e)[k]]))'
        actual=await bubble.evaluate(get,props)
        expected={'width':'300px','padding':'16px 18px','borderRadius':'12px','backgroundColor':await token(page,'--ui-color-surface'),'color':await token(page,'--ui-color-text-2'),'fontSize':'12px'}
        assert actual==expected,(expected,actual)
        await page.screenshot(path=str(out/'usage-bubble.png'));await page.keyboard.press('Escape')
        hover=[]
        # 悬停：卡片操作取填充底与正文色，调度优先级的箭头转主色文字（设计稿未画悬停，按组件库约定）。
        edit=page.locator('.account-card-actions button').first;await edit.hover();await page.wait_for_timeout(200)
        assert await edit.evaluate(get,['backgroundColor','color'])=={'backgroundColor':await token(page,'--ui-color-fill'),'color':await token(page,'--ui-color-text')};hover.append('卡片编辑')
        routing=page.locator('.account-routing button').first;await routing.hover()
        assert await routing.locator('strong svg').evaluate("e=>getComputedStyle(e).color")==await token(page,'--ui-color-primary-text');hover.append('调度优先级')
        await page.get_by_role('button',name='授权登录',exact=True).click();dialog=page.locator('.approved-oauth-dialog')
        await dialog.locator('.proxy-picker-trigger').click();popup=page.locator('.proxy-picker-popup');await popup.get_by_role('searchbox',name='搜索代理线路',exact=True).fill('线路 21');await popup.get_by_role('button',name=re.compile('线路 21')).click()
        assert not fixture.writes
        await dialog.get_by_role('button',name='生成授权链接',exact=True).click();await expect(dialog.get_by_role('link',name='点击打开授权页面 ↗')).to_be_visible();assert fixture.writes[-1]['body']=={'proxy_id':'proxy-21','proxy_revision':'revision-1'}
        await dialog.get_by_label('授权码',exact=True).fill('synthetic-code');await dialog.get_by_role('button',name='完成授权',exact=True).click();await dialog.get_by_role('button',name='填入账号配置',exact=True).click();workspace=page.locator('.account-workspace');await expect(workspace.locator('.proxy-picker-trigger')).to_contain_text('线路 21')
        assert not any(item['path']=='/admin/accounts' and item['method']=='POST' for item in fixture.writes)
        await page.keyboard.press('Escape');await page.get_by_role('button',name='授权登录',exact=True).click();await dialog.get_by_role('button',name='生成授权链接',exact=True).click();assert fixture.writes[-1]['body']=={};await page.keyboard.press('Escape')
        assert not errors,errors
        result={'passed':True,'layout':layout,'bubble_styles':actual,'hover':hover,'oauth':['跨页搜索','目录ID提交','授权后回填','取消零创建','直连'],'errors':errors}
        (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
