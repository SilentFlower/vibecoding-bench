"""验证后续运行配置整合保存、部分失败与抓包创建布局。"""
import asyncio,json
from urllib.parse import urlsplit
from playwright.async_api import async_playwright,expect
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import ROOT,BASE


class SettingsFixture(WorkspaceFixture):
    """三个原设置接口分别回读，验证只重试失败项。"""
    def __init__(self):
        """准备可编辑设置和失败开关。@return 无。"""
        super().__init__();self.config=dict(model='old-model',version='2.1.293',effort='high');self.calls=[];self.fail_effort=True
    async def route(self,route):
        """实现原设置字段，不合并后台事务。@param route 请求。@return 无。"""
        path=urlsplit(route.request.url).path
        mapping={'/runtime/api/settings/runtime-model':('model','default_model','configured_model','effective_model'),'/runtime/api/settings/runtime-effort':('effort','effort_level','configured_effort','effective_effort'),'/runtime/api/settings/claude-code-version':('version','claude_code_version','configured_version','effective_version')}
        if path in mapping:
            key,field,configured,effective=mapping[path]
            if route.request.method=='PUT':
                body=route.request.post_data_json;self.calls.append((key,body))
                if key=='effort' and self.fail_effort:return await self.respond(route,{'detail':'合成思考预算保存失败'},503)
                self.config[key]=body[field]
            return await self.respond(route,{configured:self.config[key],effective:self.config[key],**({'allowed_efforts':['low','medium','high','max']} if key=='effort' else {})})
        return await super().route(route)


async def main():
    """覆盖整合保存、部分成功重试、取消零写入与窄屏。@return 无。"""
    fixture=SettingsFixture();errors=[];out=ROOT/'.deploy/frontend-sidebar-refresh/run-settings-deep';out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')");page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/tasks?tab=runs');f=page.locator('.task-runtime');await f.locator('#runtime-open-settings').click();modal=f.locator('#runtime-settings-modal');await expect(modal).to_be_visible();await expect(modal.locator('#runtime-settings-save')).to_be_enabled();await modal.locator('[name=default_model]').fill('new-model');await modal.locator('[name=claude_code_version]').fill('2.1.303');await modal.locator('[name=effort_level]').select_option('max');await modal.get_by_role('button',name='保存运行配置',exact=True).click();await expect(modal.locator('#runtime-settings-feedback')).to_contain_text('部分配置保存失败');assert len(fixture.calls)==3;assert fixture.config==dict(model='new-model',version='2.1.303',effort='high');await expect(modal.locator('[name=effort_level]')).to_have_value('max');fixture.fail_effort=False;await modal.get_by_role('button',name='保存运行配置',exact=True).click();await expect(modal).to_be_hidden();assert fixture.calls[-1]==('effort',{'effort_level':'max'});assert len(fixture.calls)==4
        await f.locator('#runtime-open-settings').click();await modal.locator('[name=default_model]').fill('cancelled-draft');await modal.get_by_role('button',name='取消',exact=True).click();assert len(fixture.calls)==4;await f.locator('#runtime-open-settings').click();await expect(modal.locator('[name=default_model]')).to_have_value('new-model');await modal.get_by_role('button',name='取消',exact=True).click()
        await f.locator('#work-capture-new').click();capture=f.locator('#runtime-capture-modal');await expect(capture.locator('.upgrade-card')).to_have_count(2);await expect(capture.locator('#capture-form [name=account_id]')).to_have_count(1);await expect(capture.locator('#capture-form [name=prompt_mode]')).to_have_value('canonical')
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});assert await capture.evaluate('e=>e.scrollWidth<=e.clientWidth');await page.screenshot(animations='disabled',path=str(out/f'capture-create-{width}.png'))
        await capture.get_by_role('button',name='取消',exact=True).click();assert len(fixture.calls)==4;assert not errors,errors;print('后续运行整合保存、三接口回读、部分失败重试、取消零写入、抓包创建双分区与三档宽度通过');await browser.close()


if __name__=='__main__':asyncio.run(main())
