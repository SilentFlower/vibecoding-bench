"""核对设置字段完整性及编辑、保存、校验行为。"""
import asyncio,json,re
from pathlib import Path
from playwright.async_api import async_playwright,expect
async def choose(page,name,label):
 """通过可见组件选择枚举。@param page 页面。@param name 控件标签。@param label 选项。@return 无。"""
 await page.get_by_role('combobox',name=name,exact=True).click();await page.locator('#account-choice-popup').get_by_role('option',name=label,exact=True).click()
async def main():
 """使用本地示例检查原55项配置与响应式交互。@return 无。"""
 out=Path('.deploy/frontend-sidebar-refresh/concept');errors=[];network=[]
 source=Path('apps/web/src/components/Settings.vue').read_text().split('await api.updateSettings({',1)[1].split('\n    });',1)[0]
 original=set(re.findall(r'^      (\w+):',source,re.M))
 async with async_playwright() as p:
  browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1000})
  page.on('pageerror',lambda error:errors.append(str(error)));page.on('request',lambda request:network.append(request.url) if request.url.startswith(('http:','https:')) else None)
  await page.goto(Path('doc/design/flower2api-concept.html').resolve().as_uri()+'#settings')
  keys=await page.evaluate('settingsFields.map(field=>field.key)');assert len(keys)==len(set(keys))==56;assert original==set(keys)-{'request_diagnostics_log_mode'}
  seen=set()
  for category in ['scheduling','models','access','connections','warmup','observability']:
   await page.locator(f'[data-settings-category={category}]').click();seen.update(await page.locator('[data-settings-field]').evaluate_all('nodes=>nodes.map(node=>node.dataset.settingsField)'))
  assert set(keys)==seen,(set(keys)-seen)
  await page.locator('[data-settings-category=scheduling]').click()
  await page.screenshot(path=str(out/'settings-scheduling.png'),full_page=True)
  await page.locator('[name=v3_admission_wait_seconds]').fill('60')
  await page.get_by_role('button',name='增加可用负载权重',exact=True).click();await expect(page.locator('[name=v3_smart_weight_load]')).to_have_value('1.1')
  await page.locator('[data-settings-category=models]').click();await choose(page,'cache_control.ttl','1 小时')
  await page.locator('[data-settings-category=scheduling]').click();await expect(page.locator('[name=v3_admission_wait_seconds]')).to_have_value('60')
  assert await page.evaluate('settingsSaved.v3_admission_wait_seconds')=='120'
  await expect(page.locator('#settings-dirty-label')).to_contain_text('3 项')
  await page.locator('.sidebar [data-page=accounts]').click();await page.locator('.sidebar [data-page=settings]').click();await expect(page.locator('[name=v3_admission_wait_seconds]')).to_have_value('60')
  await page.locator('[data-settings-save]').click();await expect(page.locator('#settings-dirty-label')).to_have_text('所有修改已保存')
  assert await page.evaluate('settingsSaved.v3_admission_wait_seconds')=='60';assert await page.evaluate('Object.values(settingsSaved).every(value=>typeof value==="string")')
  for suffix in ['load','quota','health','latency']:await page.locator('[name=v3_smart_weight_'+suffix+']').fill('0')
  await page.locator('[data-settings-save]').click();await expect(page.locator('.setting-error')).to_contain_text('不能全部为零')
  assert await page.evaluate('settingsSaved.v3_smart_weight_load')=='1.1'
  await page.locator('[data-settings-undo]').click()
  await page.get_by_role('textbox',name='搜索系统设置').fill('fable_weekly_usage_limit_percent')
  await expect(page.locator('[data-settings-field]')).to_have_count(1)
  await page.locator('[name=fable_weekly_usage_limit_percent]').fill('0');await page.locator('[data-settings-save]').click();await expect(page.locator('.setting-error')).to_contain_text('有效范围')
  await page.locator('[data-settings-undo]').click()
  await page.locator('[data-settings-category=models]').click();await page.locator('[name=bootstrap_additional_model_options]').fill('[1]');await page.locator('[data-settings-save]').click();await expect(page.locator('.setting-error')).to_contain_text('JSON数组')
  await page.locator('[data-settings-undo]').click()
  await page.locator('[data-settings-category=connections]').click()
  await expect(page.get_by_role('switch',name='探测失败时阻断',exact=True)).to_be_disabled()
  await page.get_by_role('switch',name='首次 Hello 代理探测',exact=True).check()
  await page.get_by_role('switch',name='探测失败时阻断',exact=True).check()
  await page.get_by_role('switch',name='首次 Hello 代理探测',exact=True).uncheck()
  await expect(page.get_by_role('switch',name='探测失败时阻断',exact=True)).to_be_checked();await expect(page.locator('[name=session_hello_probe_timeout_secs]')).to_be_disabled()
  await page.locator('[data-settings-undo]').click()
  await page.locator('[data-settings-category=warmup]').click()
  await page.get_by_role('switch',name='缺失时注入 Claude Code 身份块',exact=True).check()
  await choose(page,'后台分类处理','本地模拟')
  await expect(page.get_by_role('switch',name='缺失时注入 Claude Code 身份块',exact=True)).to_be_checked();await expect(page.get_by_role('switch',name='缺失时注入 Claude Code 身份块',exact=True)).to_be_disabled()
  await page.locator('[data-settings-undo]').click()
  await page.locator('[data-settings-category=access]').click();await page.get_by_role('button',name='仅允许 280 / 293',exact=True).click()
  await expect(page.locator('[name=blocked_claude_code_versions]')).to_have_value('2.1.89-2.1.279,2.1.281-2.1.292')
  await choose(page,'画像选择方式','使用账号画像');await choose(page,'默认版本画像','2.1.280')
  await expect(page.locator('[name=allowed_claude_code_versions]')).to_have_value('2.1.89-2.1.280')
  await page.screenshot(path=str(out/'settings-access.png'),full_page=True)
  await page.locator('[data-settings-undo]').click()
  await page.locator('[data-settings-category=observability]').click();await choose(page,'后续请求日志','debug · 脱敏内容');await page.locator('[data-settings-save]').click();await expect(page.locator('#settings-dirty-label')).to_have_text('所有修改已保存');assert await page.evaluate('requestView.mode')=='debug'
  await page.locator('[data-settings-category=scheduling]').click()
  for key in ['score_weight_7d','score_weight_5h','score_weight_concurrency']:await page.locator(f'[name={key}]').fill('0.4')
  await expect(page.locator('#settings-weight-total')).to_contain_text('建议为 1.00');await page.locator('[data-settings-save]').click();await expect(page.locator('#settings-dirty-label')).to_have_text('所有修改已保存')
  await page.locator('[data-settings-category=history]').click();await expect(page.locator('.settings-log-state.success')).to_have_count(1);await expect(page.locator('.settings-log-state.skipped')).to_have_count(1);await expect(page.locator('.settings-log-state.failed')).to_have_count(1)
  await page.get_by_role('button',name='刷新',exact=True).click();await page.screenshot(path=str(out/'settings-prime-history.png'))
  await page.get_by_role('textbox',name='搜索系统设置').fill('not-a-setting');await expect(page.locator('.settings-empty')).to_contain_text('没有匹配')
  await page.locator('[data-settings-clear-search]').first.click()
  for width in [1280,720,390]:
   await page.set_viewport_size({'width':width,'height':900});await page.locator('[data-settings-category=scheduling]').click()
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   await page.screenshot(path=str(out/f'settings-{width}.png'),full_page=True)
   await page.locator('[data-settings-category=history]').click();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  assert not errors,errors;assert not network,network
  await browser.close()
 (out/'settings-verification.json').write_text(json.dumps({'passed':True,'original_fields':len(original),'preview_fields':len(keys),'errors':errors,'network':network,'scenes':['原55项完整映射','跨分类与跨页草稿、统一保存撤销','全零权重、Fable边界、JSON错误定位','禁用依赖值保留','画像范围与访问预设','日志模式同步','成功/跳过/失败预热记录','搜索与1280/720/390px布局']},ensure_ascii=False,indent=2))
 print('系统设置字段与交互验证通过')
asyncio.run(main())
