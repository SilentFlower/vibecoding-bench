"""验证账号数字步进与组件选择菜单。"""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright,expect
async def main():
 """检查上下界、键盘、表单草稿和菜单定位。@return 无。"""
 out=Path('.deploy/frontend-sidebar-refresh/concept');errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1000})
  page.on('pageerror',lambda error:errors.append(str(error)))
  await page.goto(Path('doc/design/flower2api-concept.html').resolve().as_uri())
  await page.locator('[data-account-card="1"] [data-account-action="edit"]').click()
  number=page.locator('[name=concurrency]');group=number.locator('..')
  await number.fill('1');await expect(group.locator('[data-step="-1"]')).to_be_disabled()
  await group.locator('[data-step="1"]').click();await expect(number).to_have_value('2')
  await number.focus();await page.keyboard.press('ArrowUp');await expect(number).to_have_value('3')
  await expect(group.locator('[data-step="-1"]')).to_be_enabled()
  percent=page.locator('[name=five_hour_usage_limit_percent]');await percent.fill('100')
  await expect(percent.locator('..').locator('[data-step="1"]')).to_be_disabled()
  await percent.fill('90')
  await number.scroll_into_view_if_needed();await number.focus()
  assert await number.evaluate('el=>getComputedStyle(el).outlineStyle')=='none'
  await page.screenshot(path=str(out/'account-number-controls.png'))
  trigger=page.get_by_role('combobox',name='Billing 模式',exact=True)
  await trigger.click();popup=page.locator('#account-choice-popup')
  await expect(popup).to_be_visible()
  await page.screenshot(path=str(out/'account-select-menu.png'))
  await expect(popup.locator('[aria-selected=true]')).to_contain_text('清除')
  await page.keyboard.press('ArrowDown');await page.keyboard.press('Escape')
  await expect(popup).not_to_be_visible();await expect(page.locator('#account-drawer')).to_be_visible()
  await expect(page.locator('[name=billing_mode]')).to_have_value('strip')
  await trigger.focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('End');await page.keyboard.press('Enter')
  await expect(page.locator('[name=billing_mode]')).to_have_value('rewrite')
  await expect(trigger).to_contain_text('重写')
  await page.locator('.account-advanced summary').click()
  subscription=page.get_by_role('combobox',name='订阅类型',exact=True)
  await subscription.click();await page.keyboard.press('p');await page.keyboard.press('Enter')
  await expect(page.locator('[name=subscription_type]')).to_have_value('pro')
  await subscription.click();await page.keyboard.press('Home');await page.keyboard.press('End');await page.keyboard.press('Tab')
  await expect(popup).not_to_be_visible();await expect(page.locator('[name=subscription_type]')).to_have_value('pro')
  await page.get_by_role('button',name='保存修改',exact=True).click()
  assert await page.evaluate('accounts[0].billing_mode')=='rewrite'
  for width,height in [(1440,650),(390,800)]:
   await page.set_viewport_size({'width':width,'height':height})
   await page.locator('[data-account-card="1"] [data-account-action="edit"]').click()
   await page.locator('.account-advanced summary').click()
   trigger=page.get_by_role('combobox',name='订阅类型',exact=True)
   await trigger.click();await expect(popup).to_be_visible()
   box=await popup.bounding_box();assert box['x']>=0 and box['x']+box['width']<=width and box['y']>=0 and box['y']+box['height']<=height,(width,box)
   await page.screenshot(path=str(out/f'account-select-{width}.png'))
   await popup.get_by_role('option',name='Ultra',exact=True).click()
   await expect(trigger).to_contain_text('Ultra')
   await trigger.click();await page.locator('#drawer-title').click();await expect(popup).not_to_be_visible()
   await trigger.click();await page.locator('#drawer-body').evaluate('el=>el.scrollTop=0');await expect(popup).not_to_be_visible()
   await page.keyboard.press('Escape')
   assert await page.evaluate('accounts[0].subscription_type')=='pro'
  assert not errors,errors
  await browser.close()
 (out/'account-controls-verification.json').write_text(json.dumps({'passed':True,'errors':errors,'scenes':['步进按钮边界与手动输入','数字输入键盘','菜单鼠标与键盘、首尾键及字母定位','取消保持原值、保存提交','视口避让与滚动关闭','390px菜单与输入控件']},ensure_ascii=False,indent=2))
 print('账号表单控件验证通过')
asyncio.run(main())
