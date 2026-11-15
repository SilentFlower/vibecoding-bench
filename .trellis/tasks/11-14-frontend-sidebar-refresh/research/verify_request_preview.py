"""验证请求记录查询、信息口径、详情及共享时间选择。"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright,expect
async def choose(page,name,label):
 """使用组件菜单选择可见选项。@param page 页面。@param name 控件名称。@param label 选项文字。@return 无。"""
 await page.get_by_role('combobox',name=name,exact=True).click()
 await page.locator('#account-choice-popup').get_by_role('option',name=label,exact=True).click()
async def main():
 """以合成数据验证完整请求交互。@return 无。"""
 out=Path('.deploy/frontend-sidebar-refresh/concept');errors=[];network=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1600,'height':1100},timezone_id='Asia/Shanghai')
  page.on('pageerror',lambda error:errors.append(str(error)))
  page.on('request',lambda request:network.append(request.url) if request.url.startswith(('http:','https:')) else None)
  await page.add_init_script("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async value=>{window.previewCopied=value}}})")
  await page.goto(Path('doc/design/flower2api-concept.html').resolve().as_uri()+'#requests')
  await expect(page.locator('[data-request-row]')).to_have_count(20)
  await expect(page.locator('#request-results')).to_contain_text('28 条匹配记录')
  await expect(page.locator('#request-results')).to_contain_text('claude-opus-4-6')
  await page.screenshot(path=str(out/'requests-desktop.png'),full_page=True)
  await page.get_by_role('button',name='下一页',exact=True).click();await expect(page.locator('[data-request-row]')).to_have_count(8)
  await page.locator('[data-request-quick=errors]').click()
  assert await page.locator('[data-request-row]').count()>0
  assert await page.locator('[data-request-row]').evaluate_all('rows=>rows.every(row=>row.querySelector(".is-error"))')
  await expect(page.locator('[data-request-row="req_demo_0002_a18c27d4"]')).to_contain_text('200')
  await expect(page.locator('[data-request-row="req_demo_0002_a18c27d4"]')).to_contain_text('未完整结束')
  await page.locator('[data-request-quick=processing]').click();await expect(page.locator('[data-request-row]')).to_have_count(2)
  await page.locator('[data-request-quick=all]').click()
  await page.locator('[data-request-filter-toggle]').click()
  await page.get_by_role('combobox',name='账号',exact=True).click()
  await page.get_by_role('combobox',name='搜索账号名称或邮箱',exact=True).fill('backup@')
  await page.locator('#account-choice-popup').get_by_role('option',name='备用账号 · backup@example.test',exact=True).click()
  await page.get_by_role('button',name='查询',exact=True).click()
  await expect(page.locator('[data-request-row="req_demo_0003_a18c27d4"]')).to_have_count(1)
  await page.locator('[data-request-quick=errors]').click();await expect(page.locator('[name=account_id]')).to_have_value('4')
  await page.get_by_role('combobox',name='账号',exact=True).click();await page.get_by_role('combobox',name='搜索账号名称或邮箱',exact=True).fill('not-an-account');await expect(page.locator('.choice-search-empty')).to_be_visible();await page.keyboard.press('Escape');await expect(page.locator('[name=account_id]')).to_have_value('4')
  await page.locator('[data-request-reset]').first.click()
  await page.get_by_role('textbox',name='请求关联 ID').fill('upstream_demo_2_0')
  await page.get_by_role('button',name='查询',exact=True).click();await expect(page.locator('[data-request-row]')).to_have_count(1)
  await page.get_by_role('textbox',name='请求关联 ID').fill('does-not-exist');await page.get_by_role('button',name='查询',exact=True).click();await expect(page.locator('.request-empty')).to_contain_text('没有符合条件')
  await page.locator('[data-request-reset]').first.click()
  if not await page.locator('.request-filter-fields').is_visible():await page.locator('[data-request-filter-toggle]').click()
  await page.get_by_role('button',name='开始时间',exact=True).click()
  calendar=page.locator('#date-time-popup');await expect(calendar).to_be_visible()
  await page.screenshot(path=str(out/'request-date-picker.png'))
  await calendar.get_by_role('button',name='今天',exact=True).click();await calendar.get_by_role('spinbutton',name='小时').fill('0');await calendar.get_by_role('spinbutton',name='分钟').fill('0');await calendar.get_by_role('button',name='确定',exact=True).click()
  assert (await page.locator('[name=request_since]').input_value()).endswith('T00:00')
  await page.get_by_role('button',name='结束时间',exact=True).click();await calendar.get_by_role('button',name='今天',exact=True).click();await calendar.get_by_role('spinbutton',name='小时').fill('0');await calendar.get_by_role('spinbutton',name='分钟').fill('0');await calendar.get_by_role('button',name='确定',exact=True).click()
  await page.get_by_role('button',name='查询',exact=True).click();await expect(page.locator('[data-request-query-error]')).to_contain_text('晚于')
  await page.get_by_role('button',name='结束时间',exact=True).click();await calendar.get_by_role('button',name='清空',exact=True).click();await expect(page.locator('[name=request_until]')).to_have_value('')
  await page.locator('[data-request-reset]').first.click()
  # 模式修改只作用于后续演示设置，历史行保持冻结模式。
  previous=await page.evaluate('requestFixtures[0].log_mode')
  await choose(page,'后续请求日志','debug · 脱敏内容')
  assert await page.evaluate('requestFixtures[0].log_mode')==previous
  row=page.locator('[data-request-row="req_demo_0001_a18c27d4"]')
  await row.locator('[data-request-copy]').click();assert await page.evaluate('previewCopied')=='req_demo_0001_a18c27d4'
  await row.locator('.request-detail-link').click()
  drawer=page.locator('#request-drawer');await expect(drawer).to_be_visible()
  await page.get_by_role('button',name='复制完整请求 ID',exact=True).click();assert await page.evaluate('previewCopied')=='req_demo_0001_a18c27d4'
  await page.screenshot(path=str(out/'request-overview.png'))
  await page.evaluate("navigator.clipboard.writeText=async()=>{throw Error('模拟拒绝')};document.execCommand=()=>{window.copyFallback=document.activeElement.value;return true}")
  await page.get_by_role('button',name='复制完整请求 ID',exact=True).click();assert await page.evaluate('copyFallback')=='req_demo_0001_a18c27d4';await expect(page.locator('.request-copy-buffer')).to_have_count(0)
  await page.evaluate('document.execCommand=()=>false');await page.get_by_role('button',name='复制完整请求 ID',exact=True).click();await expect(page.locator('#toast')).to_contain_text('复制失败')
  await page.locator('[data-request-tab=overview]').focus();await page.keyboard.press('ArrowRight');await expect(page.locator('[data-request-tab=chain]')).to_have_attribute('aria-selected','true')
  await page.locator('[data-request-tab=performance]').click();await expect(drawer).to_contain_text('响应头耗时');await expect(drawer).to_contain_text('首次有效输出')
  await page.screenshot(path=str(out/'request-performance.png'))
  await page.locator('[data-request-tab=raw]').click();await page.locator('[data-request-read]').click();await expect(drawer).to_contain_text('demo_fixture')
  await expect(page.locator('[data-header-action=drop] .request-header-badge')).to_have_text('删除');assert await page.locator('[data-header-action=drop] td').first.evaluate('el=>getComputedStyle(el).backgroundColor')=='rgb(255, 244, 245)'
  await choose(page,'处理动作','删除');await expect(page.locator('.request-evidence-table tbody tr')).to_have_count(1)
  await page.locator('[data-request-stage=wire_final]').click();await expect(drawer).to_contain_text('未保存所选阶段')
  await page.screenshot(path=str(out/'request-raw.png'))
  # 请求关闭后迟到回执不重新打开窗口。
  await page.locator('[data-request-read]').click();await page.keyboard.press('Escape');await page.wait_for_timeout(450);await expect(drawer).not_to_be_visible()
  await page.locator('[data-request-row="req_demo_0003_a18c27d4"] .request-detail-link').click();await page.locator('[data-request-tab=chain]').click();await expect(drawer).to_contain_text('备用账号');await expect(drawer).to_contain_text('实验工作区')
  await page.screenshot(path=str(out/'request-retry-chain.png'))
  await page.keyboard.press('Escape')
  await page.locator('[data-request-row="req_demo_0002_a18c27d4"] .request-detail-link').click();await page.locator('[data-request-tab=raw]').click();await expect(drawer).to_contain_text('本次仅保存摘要');await expect(drawer.locator('[data-request-read]')).to_have_count(0);await page.keyboard.press('Escape')
  await page.locator('[data-request-row="req_demo_0012_a18c27d4"] .request-detail-link').click();await page.locator('[data-request-tab=performance]').click();await expect(drawer).to_contain_text('0 ms');await expect(drawer.locator('.request-token-metrics strong').first).to_have_text('0');await page.keyboard.press('Escape')
  await page.locator('[data-request-row="req_demo_0011_a18c27d4"] .request-detail-link').click();await page.locator('[data-request-tab=performance]').click();await expect(drawer).to_contain_text('未观测');await page.keyboard.press('Escape')
  for width in [1280,720,390]:
   await page.set_viewport_size({'width':width,'height':900});await page.evaluate('window.scrollTo(0,0)')
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   await page.screenshot(path=str(out/f'requests-{width}.png'),full_page=True)
   await page.locator('[data-request-row="req_demo_0003_a18c27d4"] .request-detail-link').click();await page.locator('[data-request-tab=performance]').click()
   assert await page.locator('#request-detail-body').evaluate('el=>el.scrollWidth<=el.clientWidth')
   await page.screenshot(path=str(out/f'request-detail-{width}.png'));await page.keyboard.press('Escape')
  # 同一时间组件用于代理编辑；取消时间草稿与外层弹窗保持独立。
  await page.evaluate("navigate('proxies')");await page.locator('[data-proxy-row="1"] [data-proxy-action=edit]').click()
  form=page.locator('[data-form=proxy]');old=await form.locator('[name=expiresAt]').input_value()
  await page.get_by_role('button',name='到期时间',exact=True).click();await calendar.get_by_role('button',name='下个月',exact=True).click();await page.keyboard.press('Escape');await expect(form).to_be_visible();await expect(form.locator('[name=expiresAt]')).to_have_value(old)
  await page.get_by_role('button',name='到期时间',exact=True).click();await calendar.get_by_role('spinbutton',name='小时').fill('24');await calendar.get_by_role('button',name='确定',exact=True).click();await expect(calendar.locator('[data-time-error]')).to_be_visible();await calendar.get_by_role('spinbutton',name='小时').fill('12');await calendar.get_by_role('button',name='确定',exact=True).click();assert (await form.locator('[name=expiresAt]').input_value()).endswith(':00') or 'T12:' in await form.locator('[name=expiresAt]').input_value()
  assert not errors,errors;assert not network,network
  await browser.close()
 (out/'requests-verification.json').write_text(json.dumps({'passed':True,'errors':errors,'network':network,'scenes':['组合查询、错误与处理中快捷切换、分页','跨账号和上游ID精确查询','持久状态与HTTP200区分、未知与零','详情四页签、重试、完整ID复制','采集门槛、阶段查看、关闭迟到回执','共享日期面板、时区、取消与非法时间','1280/720/390px列表与详情']},ensure_ascii=False,indent=2))
 print('请求记录与统一时间组件验证通过')
asyncio.run(main())
