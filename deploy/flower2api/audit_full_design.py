"""逐入口比对确认稿与真实页面的可见控件，避免只检查外层容器。"""
import asyncio,json,re
from playwright.async_api import async_playwright
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import ROOT,BASE

PROPERTIES=['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','color','backgroundColor','padding','borderRadius','boxShadow']
COLLECT='''(root)=>[...root.querySelectorAll('button,th,h1,h2,h3,label')].filter(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden').map(e=>{const c=getComputedStyle(e),walker=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);let textNode;while((textNode=walker.nextNode())&&!textNode.textContent.trim()){}const font=textNode?getComputedStyle(textNode.parentElement):c;const text=e.innerText.replace(/\\s+/g,' ').trim(),key=(e.matches('.queue-alert,.account-queue-alert')?'queue-alert:':'')+text.replace(/\\d+(?:[.,]\\d+)*/g,'#');return {tag:e.tagName[0]==='H'?'heading':e.tagName,key,text,disabled:!!e.disabled,styles:Object.fromEntries(KEYS.map(k=>[k,(k.startsWith('font')||k==='lineHeight'||k==='letterSpacing'||k==='color')?font[k]:c[k]]))}}).filter(x=>x.key&&x.key.length<60)'''.replace('KEYS',json.dumps(PROPERTIES))


async def main():
    """输出逐页截图、控件差异及未覆盖入口。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/full-design-audit';out.mkdir(parents=True,exist_ok=True);results={};errors=[]
    cases=[('accounts','/','accounts',None),('proxies','/proxies','proxies',None),('requests','/requests','requests',None),('tokens','/tokens','tokens',None),('settings','/settings','settings',None),('environments','/environments','environments',None)]+[(f'tasks-{tab}','/tasks'+('' if tab=='accounts' else '?tab='+tab),'tasks',tab) for tab in ['accounts','projects','warmup','tasks','runs','topics']]
    async with async_playwright() as p:
        browser=await p.chromium.launch();ref=await browser.new_page(viewport={'width':1440,'height':1000});await ref.goto((ROOT/'doc/design/flower2api-concept.html').as_uri());await ref.add_style_tag(content='.preview-bar{display:none!important}:root{--preview-visible-height:0px}.app{min-height:100dvh}.sidebar{height:100dvh}')
        fixture=WorkspaceFixture();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light')");actual=await context.new_page();actual.on('pageerror',lambda e:errors.append(e.stack))
        for name,path,page,tab in cases:
            await ref.evaluate('(page)=>navigate(page)',page)
            if tab:await ref.evaluate('(tab)=>{taskTab=tab;workView.pane="overview";repaintWork()}',tab)
            await actual.goto(BASE+path);target=actual;root=actual.locator('.task-runtime' if page=='tasks' else '.runtime-environments' if page=='environments' else '#console-content');await root.wait_for();await target.locator('h1:visible,h2:visible').first.wait_for();await target.locator('body').evaluate('()=>document.fonts.ready');await ref.evaluate('document.fonts.ready')
            if page=='tasks':await target.locator('.work-navigation').wait_for()
            if page=='environments':await target.locator('.environment-rich').first.wait_for()
            expected=await ref.locator('#page').evaluate(COLLECT);observed=await root.evaluate(COLLECT);matches=[]
            used=set()
            for item in expected:
                index=next((i for i,x in enumerate(observed) if i not in used and x['tag']==item['tag'] and x['key']==item['key'] and x['disabled']==item['disabled']),None)
                if index is None:continue
                used.add(index);value=observed[index];differences={key:[item['styles'][key],value['styles'][key]] for key in PROPERTIES if item['styles'][key]!=value['styles'][key]}
                matches.append({'text':item['text'],'differences':differences})
            results[name]={'compared':len(matches),'differences':[item for item in matches if item['differences']]};(out/'differences.json').write_text(json.dumps({'pages':results,'errors':errors},ensure_ascii=False,indent=2))
            for width in [1440,390]:
                await ref.set_viewport_size({'width':width,'height':1000});await actual.set_viewport_size({'width':width,'height':1000});await ref.screenshot(animations='disabled',path=str(out/f'{name}-{width}-reference.png'));await actual.screenshot(animations='disabled',path=str(out/f'{name}-{width}-actual.png'));assert await target.locator('html').evaluate('e=>e.scrollWidth<=innerWidth'),name
            await ref.set_viewport_size({'width':1440,'height':1000});await actual.set_viewport_size({'width':1440,'height':1000});print(name,results[name]['compared'],len(results[name]['differences']),flush=True)
        (out/'differences.json').write_text(json.dumps({'pages':results,'errors':errors},ensure_ascii=False,indent=2));await browser.close();assert not errors,errors


if __name__=='__main__':asyncio.run(main())
