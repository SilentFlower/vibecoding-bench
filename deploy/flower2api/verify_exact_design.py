"""同视口、同数据对照定稿和真实页面，保存逐属性差异与截图。"""
import asyncio
import copy
import json
from playwright.async_api import async_playwright, expect
from verify_run_detail_design import RunDetailFixture
from verify_environment_ui import BASE, ROOT

PROPERTIES=['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','color','backgroundColor','borderRadius','padding','gap','boxShadow']
# 侧栏、品牌、版本号、页头（含分组名与页头主按钮）已换为第二版外壳，由 verify_ui_shell.py 对照 doc/design/console-v2 核对，这里只比对页面主体。
MAPPING={
    '筛选容器':('.account-toolbar .tabs','.account-filter-tabs'),
    '筛选按钮':('.account-toolbar .tab:not(.active)','.account-filter-tabs button:not(.active)'),
    '筛选选中态':('.account-toolbar .tab.active','.account-filter-tabs button.active'),
    '筛选计数':('.account-toolbar .tab span','.account-filter-tabs button span'),
    '全局字体根':('html','html'),
    '卡片名称':('.account-name strong','.account-identity h3'),
    '邮箱文字':('.account-name small','.account-identity p'),
    '卡片表面':('.account-card','.account-card'),
    '卡片底栏':('.account-card-actions button','.account-card-actions button'),
    '用量标题':('.aligned-usage-label','.usage-window-label'),
    '用量数值':('.aligned-usage-label strong','.usage-window-label strong'),
}


async def styles(page,selector):
    """读取实际渲染样式，缺失元素使验证失败。@param page 页面。@param selector 元素。@return 样式表。"""
    locator=page.locator(selector).first
    await expect(locator).to_be_visible()
    return await locator.evaluate('(element,keys)=>{const style=getComputedStyle(element);return Object.fromEntries(keys.map(key=>[key,style[key]]))}',PROPERTIES)


async def main():
    """以原型自身数据驱动真实组件，禁止截图使用不相同业务数据。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/exact';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        reference=await browser.new_page(viewport={'width':1440,'height':1000})
        await reference.goto((ROOT/'doc/design/flower2api-concept.html').as_uri())
        # 原型顶部示例说明不属于产品界面，隐藏后统一产品视口原点。
        await reference.add_style_tag(content='.preview-bar{display:none!important}:root{--preview-visible-height:0px}.app{min-height:100dvh}.sidebar{height:100dvh}')
        source=await reference.evaluate('accounts')
        fixture=RunDetailFixture()
        fixture.accounts=[]
        for row in source:
            value=copy.deepcopy(fixture.account_template);value.update(row)
            value['status']='error' if row['status']=='attention' else row['status']
            value['proxy_name']=await reference.evaluate('(id)=>previewProxies.find(p=>p.id===id)?.name||null',row.get('proxyId'))
            value['v3_scheduling']=None;value['current_concurrency']=row.get('current_concurrency',0);value['active_requests']=row.get('current_concurrency',0)
            fixture.accounts.append(value)
        context=await browser.new_context(viewport={'width':1440,'height':1000})
        await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        actual=await context.new_page();await actual.goto(BASE+'/');await expect(actual.locator('.account-card')).to_have_count(len(source))
        await actual.evaluate('document.fonts.ready');await reference.evaluate('document.fonts.ready')
        compared={};differences=[]
        for key,(ref_selector,actual_selector) in MAPPING.items():
            expected,observed=await styles(reference,ref_selector),await styles(actual,actual_selector)
            diff={prop:{'reference':expected[prop],'actual':observed[prop]} for prop in PROPERTIES if expected[prop]!=observed[prop]}
            compared[key]={'reference':expected,'actual':observed,'differences':diff}
            if diff:differences.append(key)
        rendered_fonts = {}
        # 页面标题已由第二版页头接管（verify_ui_shell.py），字体回退只核对页面主体文字。
        for key in ['卡片名称','邮箱文字','用量数值']:
            ref_selector,actual_selector = MAPPING[key]
            faces = {}
            for name,current,selector in [('reference',reference,ref_selector),('actual',actual,actual_selector)]:
                session = await current.context.new_cdp_session(current)
                await session.send('DOM.enable');await session.send('CSS.enable')
                document = await session.send('DOM.getDocument')
                node = await session.send('DOM.querySelector',{'nodeId':document['root']['nodeId'],'selector':selector})
                platform = await session.send('CSS.getPlatformFontsForNode',{'nodeId':node['nodeId']})
                faces[name] = sorted(set(font['familyName'] for font in platform['fonts']))
                await session.detach()
            rendered_fonts[key] = faces
            assert faces['reference'] == faces['actual'],(key,faces)
        for width in [1440,720,390]:
            for name,page in [('reference',reference),('actual',actual)]:
                await page.set_viewport_size({'width':width,'height':1000});await page.screenshot(path=str(out/f'{name}-accounts-{width}.png'))
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(name,width)
        result={'same_data':True,'same_viewport':True,'rendered_fonts':rendered_fonts,'compared':compared,'remaining':differences,'passed':not differences}
        (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({key:value['differences'] for key,value in compared.items() if value['differences']},ensure_ascii=False))
        await browser.close()
        assert not differences,differences


if __name__=='__main__':asyncio.run(main())
