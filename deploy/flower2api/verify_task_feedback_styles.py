"""任务深层控件（额度弹窗、养号额度设置、工程交互记录、运行条件、验收）的第二版外观：弹窗外壳与标题取 token，
页面自有元素的文字色、背景色只取 --ui-color-* token，正文字体为 Inter Variable。旧原型逐项比对已移除（设计稿未画这些画面），
页面级设计稿比对见 verify_native_pages_design.py。"""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'deploy/flower2api'))
from verify_task_feedback import TaskFeedbackFixture
from verify_environment_ui import BASE,ROOT
from verify_native_pages_design import shell,tokens_only
from playwright.async_api import async_playwright,expect
async def main():
 """逐个打开深层控件并核对外观只取 token。@return 无。"""
 out=ROOT/'.deploy/frontend-sidebar-refresh/task-feedback';out.mkdir(parents=True,exist_ok=True);problems=[]
 async with async_playwright() as p:
  b=await p.chromium.launch();ctx=await b.new_context(viewport={'width':1440,'height':1000});await ctx.route('**/*',TaskFeedbackFixture().route);await ctx.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");actual=await ctx.new_page();await actual.goto(BASE+'/tasks');root=actual.locator('.task-runtime');await root.locator('.work-account').first.wait_for()
  async def font(selector,label):
   """正文字体为第二版字体。@param selector 节点。@param label 场景。@return 无。"""
   family=await root.locator(selector).first.evaluate("e=>getComputedStyle(e).fontFamily.split(',')[0].replaceAll('\"','')")
   if family!='Inter Variable':problems.append(f'{label} 字体 {family}')
  await root.locator('[data-quota]').click();await expect(root.locator('.work-quota-number').first).to_be_visible();await actual.evaluate('document.fonts.ready')
  await shell(actual,'#modal .modal-card','.modal-titlebar-name','额度',problems);await tokens_only(actual,'#modal .modal-card','额度',problems);await font('.work-quota-number','额度数值')
  await actual.screenshot(animations='disabled',path=str(out/'quota-1440.png'));await actual.keyboard.press('Escape')
  await root.locator('[data-warmup-config]').click();await expect(root.locator('[name=warmup_quota_5h_limit_percent]')).to_be_visible()
  await shell(actual,'#warmup-modal .modal-card','.modal-titlebar-name','养号额度设置',problems);await tokens_only(actual,'#warmup-modal .modal-card','养号额度设置',problems);await font('#warmup-modal .field','养号额度字段')
  await actual.screenshot(animations='disabled',path=str(out/'warmup-policy-1440.png'));await actual.keyboard.press('Escape')
  await root.locator('[data-tab=projects]').click();await root.locator('#projects-tab-events').click();await expect(root.locator('#projects-events article')).to_have_count(2)
  await tokens_only(actual,'.work-events','交互记录',problems);await tokens_only(actual,'.work-side-stack','运行条件',problems);await font('.work-events strong','交互记录标题')
  await root.locator('#projects-tab-verification').click();await expect(root.locator('.work-verification')).to_be_visible()
  await tokens_only(actual,'.work-verification','独立验收',problems);await actual.screenshot(animations='disabled',full_page=True,path=str(out/'projects-verification-1440.png'))
  (out/'style-problems.json').write_text(json.dumps(problems,ensure_ascii=False,indent=2));await b.close();assert not problems,problems
  print('任务深层控件：额度、养号额度设置、交互记录、运行条件与验收的第二版外观只取 token')
if __name__=='__main__':asyncio.run(main())
