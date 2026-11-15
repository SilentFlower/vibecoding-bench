"""从定稿CSSOM提取环境工作区样式并限定作用域。"""
import asyncio
from playwright.async_api import async_playwright
from verify_environment_ui import ROOT

async def main():
    """保持规则顺序，写出环境视觉声明。@return 无。"""
    async with async_playwright() as p:
        browser=await p.chromium.launch();page=await browser.new_page();await page.goto((ROOT/'doc/design/flower2api-concept.html').as_uri())
        css=await page.evaluate(r'''()=>{
          function selectors(text){let result=[],start=0,depth=0;for(let i=0;i<text.length;i++){if(text[i]==='('||text[i]==='[')depth++;if(text[i]===')'||text[i]===']')depth--;if(text[i]===','&&!depth){result.push(text.slice(start,i));start=i+1;}}result.push(text.slice(start));return result.map(value=>':root.console-design '+value.trim()).join(',');}
          function walk(rules){return [...rules].map(rule=>{if(rule.selectorText){if(!/\.(?:environment-|workspace-|cpu-fields|kernel-version|schedule-fields|maintenance-option|unit-input)/.test(rule.selectorText))return '';return selectors(rule.selectorText)+'{'+rule.style.cssText+'}';}if(rule.cssRules){const children=walk(rule.cssRules);return children?rule.cssText.slice(0,rule.cssText.indexOf('{')+1)+children+'}':'';}return '';}).filter(Boolean).join('\n');}
          return [...document.styleSheets].map(sheet=>walk(sheet.cssRules)).join('\n');
        }''');target=ROOT/'apps/legacy-web/environment-design.css';old=target.read_text() if target.exists() else '';marker='/* 原生事件与定稿结构的适配。 */';adapters=old[old.index(marker):] if marker in old else marker+'\n';target.write_text('/* 声明取自已确认原型的CSSOM。 */\n'+css+'\n'+adapters);await browser.close()

if __name__=='__main__':asyncio.run(main())
