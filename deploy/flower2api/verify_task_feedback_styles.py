"""从原型实际渲染读取任务深层控件规格，核对计算样式。"""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'deploy/flower2api'))
from verify_task_feedback import TaskFeedbackFixture
from verify_environment_ui import BASE,ROOT
from playwright.async_api import async_playwright,expect
KEYS=['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','padding','margin','gap','backgroundColor','color','borderRadius']
async def main():
 """同视口逐项核对额度、阈值、事件、条件与验收结构。@return 无。"""
 out=ROOT/'.deploy/frontend-sidebar-refresh/task-feedback';result={}
 async with async_playwright() as p:
  b=await p.chromium.launch();ref=await b.new_page(viewport={'width':1440,'height':1000});await ref.goto((ROOT/'doc/design/flower2api-concept.html').as_uri());await ref.evaluate("navigate('tasks');taskTab='accounts';repaintWork()");ctx=await b.new_context(viewport={'width':1440,'height':1000});await ctx.route('**/*',TaskFeedbackFixture().route);await ctx.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");actual=await ctx.new_page();await actual.goto(BASE+'/tasks');root=actual.locator('.task-runtime')
  async def compare(name,a,z):
   """比对同语义节点。@param name 名称。@param a 原型。@param z 实现。@return 无。"""
   expected=await a.evaluate('(e,keys)=>{const c=getComputedStyle(e);return Object.fromEntries(keys.map(k=>[k,c[k]]))}',KEYS);observed=await z.evaluate('(e,keys)=>{const c=getComputedStyle(e);return Object.fromEntries(keys.map(k=>[k,c[k]]))}',KEYS);result[name]={k:[expected[k],observed[k]] for k in KEYS if expected[k]!=observed[k]}
  await ref.evaluate('openWorkQuota(101)');await root.locator('[data-quota]').click();await expect(root.locator('.work-quota-number').first).to_be_visible();await actual.evaluate('document.fonts.ready');await ref.evaluate('document.fonts.ready')
  for name,left,right in [('quota-title','dialog[open] h2','#modal .modal-titlebar-name'),('quota-body','dialog[open] .dialog-body','.work-quota-content'),*[(name,sel,sel) for name,sel in [('quota-identity','.work-quota-identity'),('quota-number','.work-quota-number'),('quota-window','.work-quota-window'),('quota-fable','.quota-fable'),('quota-footer','.work-quota-footer')]]]:await compare(name,ref.locator(left).first,root.locator(right).first)
  await ref.keyboard.press('Escape');await actual.keyboard.press('Escape');await ref.evaluate('openWorkQuotaPolicy(101)');await root.locator('[data-warmup-config]').click()
  for name,left,right in [('policy-title','dialog[open] h2','#warmup-heading'),('policy-toggle','dialog[open] .switch-field','[name=quota_5h_enabled]'),('policy-label','dialog[open] .field','[name=warmup_quota_5h_limit_percent]')]:
   z=root.locator(right);z=z.locator('..') if name in ['policy-toggle'] else z.locator('xpath=ancestor::label') if name=='policy-label' else z;await compare(name,ref.locator(left).first,z)
  await ref.keyboard.press('Escape');await actual.keyboard.press('Escape');await ref.evaluate("taskTab='projects';workView.pane='overview';workView.screen='events';repaintWork()");await root.locator('[data-tab=projects]').click();await root.locator('#projects-tab-events').click();await expect(root.locator('#projects-events article')).to_have_count(2)
  for name,sel in [('events','.work-events'),('event-row','.work-events article'),('event-title','.work-events strong'),('event-text','.work-events p'),('condition','.work-condition'),('condition-value','.work-condition strong'),('objectives','.work-objectives'),('objective','.work-objectives li')]:await compare(name,ref.locator(sel).first,root.locator(sel).first)
  await ref.evaluate("workView.screen='verification';repaintWork()");await root.locator('#projects-tab-verification').click();await compare('verification',ref.locator('.work-verification'),root.locator('.work-verification'));await compare('verification-step',ref.locator('.work-verification>div').first,root.locator('#projects-verification-empty li').first)
  (out/'style-differences.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));await b.close();assert all(not value for value in result.values()),result
if __name__=='__main__':asyncio.run(main())
