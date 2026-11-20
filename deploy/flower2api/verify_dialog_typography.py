"""测量实际弹窗内部排版：代理编辑宽度、启动抓包表单两列字段对齐与图标关闭（第二版外观由 verify_native_pages_design.py 核对）。"""
import asyncio,json
from playwright.async_api import async_playwright,expect
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import BASE,ROOT
KEYS=['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','padding','margin','gap','borderRadius']
async def sample(node):
 """读取目标控件实际计算样式。@param node 控件定位器。@return 样式字典。"""
 return await node.evaluate('(e)=>Object.fromEntries('+json.dumps(KEYS)+'.map(k=>[k,getComputedStyle(e)[k]]))')
async def main():
 """验证嵌套弹窗排版、输入对齐和图标关闭。@return 无。"""
 out=ROOT/'.deploy/frontend-sidebar-refresh/full-design-audit';r={}
 async with async_playwright() as p:
  b=await p.chromium.launch()
  context=await b.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',WorkspaceFixture().route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light')");actual=await context.new_page();await actual.goto(BASE+'/proxies');await actual.get_by_role('button',name='添加代理',exact=True).click()
  # 代理编辑已换成第二版居中弹窗（ModalDialog，外框由 verify_ui_kit.py 对设计稿核对、页面由 verify_records_pages_design.py 截图目视），旧原型逐项比对移除，只保留宽度。
  # 读布局宽度，入场缩放动画不影响结果。
  width=await actual.locator('.proxy-editor').evaluate('e=>e.offsetWidth');assert width==680,width
  await actual.screenshot(animations='disabled',path=str(out/'proxy-editor-1440.png'));await actual.get_by_role('button',name='关闭',exact=True).click()
  # 启动抓包弹窗属于原生任务页，已换成第二版外观：外壳与标题取 token、颜色只取 token 由 verify_native_pages_design.py 核对，
  # 旧原型逐项比对移除；这里保留实际排版行为（两列字段顶边对齐、图标关闭）。
  await actual.goto(BASE+'/tasks?tab=runs');f=actual.locator('.task-runtime');await f.locator('#work-capture-new').click()
  for name,ac in [('capture-title','#runtime-capture-title'),('capture-header','#runtime-capture-modal .modal-titlebar'),('capture-label','#capture-form .field'),('capture-intro','#capture-form .upgrade-intro h3')]:
   r[name]=await sample(f.locator(ac).first)
  # 下拉由原生增强器异步替换成触发按钮，弹窗还有进场动画：等两者都稳定后再量顶边。
  await f.locator('#capture-form .native-choice-trigger').first.wait_for();await actual.evaluate('()=>Promise.all(document.getAnimations().filter(a=>a.effect?.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>null)))')
  for left,right in [('claude_code_version','effort_level'),('timeout_sec','permission_mode')]:
   nodes=f.locator('#capture-form');y=[]
   for field in [left,right]:y.append((await nodes.locator('[name='+field+']').evaluate("e=>{const field=e.closest('.field');return field.querySelector('.native-number,.native-choice-trigger,input:not([type=hidden])').getBoundingClientRect().top}")))
   assert abs(y[0]-y[1])<1,(left,right,y)
  await actual.screenshot(animations='disabled',path=str(out/'capture-create-1440.png'));await f.locator('#runtime-capture-modal .modal-close svg').click();await expect(f.locator('#runtime-capture-modal')).to_be_hidden();(out/'nested-dialog-styles.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print('弹窗排版：代理编辑宽 680、抓包表单字段对齐与图标关闭验证通过');await b.close()
asyncio.run(main())
