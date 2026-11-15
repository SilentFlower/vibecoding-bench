"""验证已有、导入、新增与异常地址的代理编辑入口。"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright,expect
async def main():
 """使用合成代理覆盖编辑恢复与低视口保存。@return 无。"""
 errors=[]
 async with async_playwright() as p:
  b=await p.chromium.launch();page=await b.new_page(viewport={'width':1000,'height':600});page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto(Path('doc/design/flower2api-concept.html').resolve().as_uri()+'#proxies')
  for id in [1,2,3]:
   await page.locator(f'[data-proxy-row="{id}"] [data-proxy-action="edit"]').click()
   await expect(page.locator('[data-form=proxy]')).to_be_visible()
   await page.locator('[data-form=proxy] [name=name]').fill('编辑成功 '+str(id))
   await page.get_by_role('button',name='保存代理',exact=True).click()
   await expect(page.locator(f'[data-proxy-row="{id}"]')).to_contain_text('编辑成功 '+str(id))
  await page.evaluate("previewProxies[0].url='http://host:invalid';navigate('proxies')")
  await page.locator('[data-proxy-row="1"] [data-proxy-action="edit"]').click()
  await expect(page.locator('[data-proxy-feedback]')).to_contain_text('当前地址需要修正')
  await page.get_by_role('button',name='取消',exact=True).click()
  assert await page.evaluate('previewProxies[0].url')=='http://host:invalid'
  await page.locator('[data-proxy-row="1"] [data-proxy-action="edit"]').click()
  await page.locator('[name=host]').fill('fixed.example.test')
  await page.locator('[name=port]').fill('8080')
  await page.get_by_role('button',name='保存代理',exact=True).click()
  await expect(page.locator('[data-proxy-row="1"]')).to_contain_text('fixed.example.test:8080')
  await page.get_by_role('button',name='批量导入',exact=True).click()
  await page.locator('[name=urls]').fill('socks5://import.example.test:1080')
  await page.get_by_role('button',name='导入代理',exact=True).click()
  await page.locator('[data-proxy-row="4"] [data-proxy-action="edit"]').click()
  await page.locator('[name=name]').fill('导入后编辑')
  await page.get_by_role('button',name='保存代理',exact=True).click()
  await expect(page.locator('[data-proxy-row="4"]')).to_contain_text('导入后编辑')
  await page.set_viewport_size({'width':390,'height':400})
  await page.get_by_role('button',name='添加代理',exact=True).click()
  await page.locator('[name=proxy_input]').fill('new.example.test:8080:demo:example-only')
  await page.get_by_role('button',name='识别填入').click()
  await page.get_by_role('button',name='保存代理',exact=True).click()
  await page.locator('[data-proxy-row="5"] [data-proxy-action="edit"]').click()
  await page.locator('[name=name]').fill('新增后编辑')
  await page.get_by_role('button',name='保存代理',exact=True).click()
  await expect(page.locator('[data-proxy-row="5"]')).to_contain_text('新增后编辑')
  assert not errors,errors
  await b.close()
 Path('.deploy/frontend-sidebar-refresh/concept/proxy-edit-recovery.json').write_text(json.dumps({'passed':True,'errors':errors,'scenes':['三个已有代理编辑保存','异常地址打开/取消/修复','导入后编辑','390x400新增后编辑保存']},ensure_ascii=False,indent=2))
 print('代理编辑与异常地址恢复验证通过')
asyncio.run(main())
