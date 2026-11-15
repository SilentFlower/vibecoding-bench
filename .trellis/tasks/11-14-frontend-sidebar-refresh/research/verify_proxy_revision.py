"""验证代理搜索、结构化识别、到期草稿以及精简导航。"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright,expect
async def main():
 """运行本地示例交互，不访问代理或提交外部请求。@return 无。"""
 out=Path('.deploy/frontend-sidebar-refresh/concept');errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1000},timezone_id='America/Los_Angeles')
  page.on('pageerror',lambda error:errors.append(str(error)))
  await page.goto(Path('doc/design/flower2api-concept.html').resolve().as_uri()+'#proxies')
  await expect(page.locator('.topbar,.workspace')).to_have_count(0)
  await expect(page.locator('.sidebar-foot .collapse-toggle')).to_be_visible()
  await page.locator('.collapse-toggle').click();await expect(page.locator('.sidebar')).to_have_css('width','76px')
  await page.locator('.collapse-toggle').click()
  await expect(page.locator('[data-proxy-row]')).to_have_count(3)
  for query,expected in [('新加坡',1),('us.example',1),('203.0.113.18',1),('洛杉矶',1),('不存在',0)]:
   await page.get_by_role('searchbox',name='搜索代理').fill(query)
   await expect(page.locator('[data-proxy-row]')).to_have_count(expected)
  await page.get_by_role('button',name='清空代理搜索').click();await expect(page.locator('[data-proxy-row]')).to_have_count(3)
  await expect(page.locator('[data-proxy-row="2"] .proxy-expiry')).to_contain_text('剩余')
  await expect(page.locator('[data-proxy-row="3"] .proxy-expiry')).to_contain_text('已过期')
  await page.screenshot(path=str(out/'proxies-search-expiry.png'),full_page=True)
  # 解析格式覆盖编码凭据、IPv6、默认协议和拒绝路径，均为合成数据。
  cases=[('socks5://demo:p%40ss%3Aword@host.example:1080','socks5','host.example',1080,'demo','p@ss:word'),('host.example:8080:demo:p:a:ss','http','host.example',8080,'demo','p:a:ss'),('demo:secret@host.example:8080','http','host.example',8080,'demo','secret'),('host.example:8080','http','host.example',8080,'',''),('socks5h://[2001:db8::1]:1080','socks5h','2001:db8::1',1080,'','')]
  for raw,protocol,host,port,user,password in cases:
   parsed=await page.evaluate('text=>parseProxyInput(text)',raw)
   assert parsed=={'protocol':protocol,'host':host,'port':port,'username':user,'password':password},parsed
  for raw in ['ftp://host:21','http://host:999999','socks5://user:%ZZ@host:1080','http://host:80/path','host','']:
   assert await page.evaluate('text=>{try{parseProxyInput(text);return false}catch{return true}}',raw),raw
  await page.locator('[data-proxy-row="1"] [data-proxy-action="edit"]').click()
  form=page.locator('[data-form="proxy"]');expiry=form.locator('[name=expiresAt]')
  original=await page.evaluate('previewProxies[0].expiresAt')
  expected=await expiry.evaluate('el=>{const date=new Date(el.value);date.setDate(date.getDate()+30);return proxyLocalDate(date)}')
  await form.get_by_role('button',name='延长 30 天',exact=True).click();await expect(expiry).to_have_value(expected)
  expected90=await expiry.evaluate('el=>{const date=new Date(el.value);date.setDate(date.getDate()+90);return proxyLocalDate(date)}')
  await form.get_by_role('button',name='延长 90 天',exact=True).click();await expect(expiry).to_have_value(expected90)
  await form.get_by_role('button',name='取消',exact=True).click();assert await page.evaluate('previewProxies[0].expiresAt')==original
  await page.locator('[data-proxy-row="1"] [data-proxy-action="edit"]').click()
  await form.locator('[name=proxy_input]').fill(cases[0][0]);await form.get_by_role('button',name='识别填入').click()
  await expect(form.locator('[name=host]')).to_have_value('host.example');await expect(form.locator('[name=username]')).to_have_value('demo');await expect(form.locator('[name=password]')).to_have_value('p@ss:word')
  await form.locator('[name=proxy_input]').fill('ftp://bad:21');await form.get_by_role('button',name='识别填入').click();await expect(form.locator('[name=host]')).to_have_value('host.example')
  await expect(form.locator('[data-proxy-feedback]')).to_contain_text('支持')
  await form.locator('[name=proxy_input]').fill('socks5://demo:p%40ss%3Aword@host.example:1080');await form.get_by_role('button',name='识别填入').click()
  await form.get_by_role('button',name='延长 30 天',exact=True).click()
  await page.screenshot(path=str(out/'proxy-editor-recognition.png'))
  await form.get_by_role('button',name='保存代理',exact=True).click()
  assert await page.evaluate('previewProxies[0].password==="p@ss:word"')
  await expect(page.locator('[data-proxy-row="1"]')).not_to_contain_text('p@ss:word')
  await expect(page.locator('[data-proxy-row="1"]')).not_to_contain_text('demo@')
  # 修改到期时间不影响已有检测结果。
  await page.locator('[data-proxy-row="2"] [data-proxy-action="edit"]').click()
  await form.get_by_role('button',name='不设置',exact=True).click();await form.get_by_role('button',name='保存代理',exact=True).click()
  await expect(page.locator('[data-proxy-row="2"] .proxy-expiry')).to_have_text('未设置')
  assert await page.evaluate('previewProxies[1].status')=='ready'
  for proxy_id in (2,3):
   await page.locator(f'[data-proxy-row="{proxy_id}"] [data-proxy-action="edit"]').click()
   await form.get_by_role('button',name='延长 90 天',exact=True).click()
   days=await expiry.evaluate('el=>(new Date(el.value)-Date.now())/86400000');assert 89.9<days<90.1,days
   await form.get_by_role('button',name='取消',exact=True).click()
  await page.get_by_role('button',name='添加代理',exact=True).click()
  await form.locator('[name=proxy_input]').fill('[2001:db8::2]:8080');await form.get_by_role('button',name='识别填入').click();await form.get_by_role('button',name='保存代理',exact=True).click()
  await expect(page.locator('[data-proxy-row]')).to_have_count(4)
  await page.set_viewport_size({'width':390,'height':800});await page.get_by_role('button',name='打开导航',exact=True).click()
  await page.locator('#action-dialog [data-page="proxies"]').click()
  await expect(page.locator('#page h1')).to_have_text('代理管理')
  assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  await page.get_by_role('button',name='添加代理',exact=True).click()
  assert await form.evaluate('el=>el.scrollWidth<=el.clientWidth')
  await page.screenshot(path=str(out/'proxy-editor-390.png'))
  assert not errors,errors
  await browser.close()
 (out/'proxy-revision-verification.json').write_text(json.dumps({'passed':True,'errors':errors,'scenes':['公开资料搜索与清空','解析格式及失败原子性','未来、过期、未设置延长与取消','本地时区日期及倒计时','凭据脱敏与检测状态保持','侧栏折叠与移动导航']},ensure_ascii=False,indent=2))
 print('代理与导航增量验证通过')
asyncio.run(main())
