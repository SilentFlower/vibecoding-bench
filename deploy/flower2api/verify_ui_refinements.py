"""核对账号列数、用量气泡、悬停反馈和授权选线的真实行为。"""
import asyncio
import json
import re
from playwright.async_api import async_playwright,expect
from verify_interaction_parity import InteractionFixture
from verify_environment_ui import ROOT,BASE


async def main():
    """按同一断点与交互场景比较定稿。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/refinements';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();reference=await browser.new_page()
        await reference.goto((ROOT/'doc/design/flower2api-concept.html').as_uri());await reference.emulate_media(reduced_motion='reduce')
        context=await browser.new_context();fixture=InteractionFixture();await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)));await page.emulate_media(reduced_motion='reduce');await page.goto(BASE+'/');await page.locator('.account-card').first.wait_for()
        widths=[390,720,760,761,767,768,1000,1280,1340,1440,1600,1680,1920,2560,3440];layout=[]
        for width in widths:
            result={'width':width}
            for key,current,selector in [('reference',reference,'.account-card-grid'),('actual',page,'.account-card-grid')]:
                await current.set_viewport_size({'width':width,'height':1000})
                result[key]=await current.locator(selector).evaluate('(e)=>({columns:getComputedStyle(e).gridTemplateColumns.split(" ").length,width:e.getBoundingClientRect().width,card:e.firstElementChild.getBoundingClientRect().width})')
            # 侧栏宽度与内容区边距属于外壳，已按第二版设计稿调整并由 verify_ui_shell.py 核对；这里改为核对卡片区铺满内容区，列数仍与定稿一致。
            result['content']=await page.locator('#console-content').evaluate('(e)=>{const s=getComputedStyle(e);return e.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight)}')
            assert result['reference']['columns']==result['actual']['columns'],result
            if width>1762:
                assert result['actual']['columns']==4,result
            assert abs(result['content']-result['actual']['width'])<1,result
            layout.append(result)
        await page.set_viewport_size({'width':1680,'height':1000});await page.screenshot(path=str(out/'accounts-four-columns.png'))
        await page.set_viewport_size({'width':1440,'height':1000});await reference.set_viewport_size({'width':1440,'height':1000})
        await reference.locator('[data-usage-bubble]').first.hover();await page.get_by_role('button',name='查看5h完整费用统计',exact=True).first.hover()
        original=reference.locator('#usage-bubble');bubble=page.locator('.usage-cost-bubble');await expect(original).to_be_visible();await expect(bubble).to_be_visible()
        await expect(bubble.locator('header')).to_have_text('5 小时用量统计网关记录');await expect(bubble.locator('.usage-bubble-grid>div')).to_have_count(4)
        # 气泡表面阴影属于组件库（.fui-popover 取 --ui-shadow-pop，由 verify_ui_kit.py 核对），不再与旧原型比对。
        props=['width','padding','borderRadius','borderColor','backgroundColor','color','fontSize','lineHeight']
        get='(e,keys)=>Object.fromEntries(keys.map(k=>[k,getComputedStyle(e)[k]]))'
        expected=await original.evaluate(get,props);actual=await bubble.evaluate(get,props);assert expected==actual,(expected,actual)
        await page.screenshot(path=str(out/'usage-bubble.png'));await page.keyboard.press('Escape');await reference.keyboard.press('Escape')
        hover=[]
        # 侧栏悬停已换为第二版外壳，由 verify_ui_shell.py 核对，这里只比对页面主体的悬停态。
        for name,refsel,selector in [('卡片编辑','[data-account-action=edit]','.account-card-actions button:first-child'),('调度优先级','.scheduling-group','.account-routing button')]:
            original=reference.locator(refsel).first;current=page.locator(selector).first
            if not await original.count():continue
            await original.hover();await current.hover()
            target='strong' if name=='调度优先级' else None
            left=await (original.locator(target) if target else original).evaluate(get,['backgroundColor','color'])
            right=await (current.locator(target) if target else current).evaluate(get,['backgroundColor','color'])
            assert left==right,(name,left,right);hover.append(name)
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
