"""验证其余管理页面的真实草稿、筛选与定稿样式，使用本地合成接口。"""
import asyncio
import json
from urllib.parse import urlsplit,parse_qs
from playwright.async_api import async_playwright,expect
from verify_tokens_design import TokenDesignFixture
from verify_environment_ui import ROOT,BASE


class RemainingPagesFixture(TokenDesignFixture):
    """保留设置及诊断查询回执，支持保存期间继续编辑。"""
    def __init__(self):
        """初始化合成字段及读取记录。@return 无。"""
        super().__init__()
        self.settings={}
        self.settings_gate=None
        self.settings_started=asyncio.Event()
        self.diagnostic_queries=[]

    async def route(self,route):
        """模拟管理配置与诊断。@param route 请求。@return 无。"""
        request=route.request;parsed=urlsplit(request.url)
        if parsed.path=='/runtime/api/environments' and request.method=='GET':
            return await self.respond(route,self.rows)
        if parsed.path=='/admin/settings':
            if request.method=='PUT':
                body=request.post_data_json;self.writes.append({'path':parsed.path,'body':body});self.settings_started.set()
                if self.settings_gate:await self.settings_gate.wait()
                self.settings.update(body)
            return await self.respond(route,self.settings)
        if parsed.path=='/admin/request-diagnostics':
            query=parse_qs(parsed.query);self.diagnostic_queries.append(query)
            attempt={'parameters':{'model':'claude-fable-5'},'profile_selection':'native293_cc_prepared','first_output_ms':0,'tokens':{'input_tokens':0,'output_tokens':128,'cache_read_tokens':2048}}
            row={'request_id':'11111111-1111-4111-8111-111111111111','started_at':'2026-11-15T00:01:00Z','finished_at':'2026-11-15T00:01:02Z','status_code':200,'account_id':11,'account_name':'主用演示账号','account_email':'primary@example.test','outcome':'success','attempt_count':2,'log_mode':'debug','last_attempt':attempt}
            items=[] if query.get('outcome') else [row]
            return await self.respond(route,{'items':items,'total':len(items),'health':{},'counts':{'all':53,'errors':7,'processing':2}})
        return await super().route(route)


async def main():
    """核对完整设置字段、分类、搜索、草稿、撤销和请求快捷筛选。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/all-pages';out.mkdir(parents=True,exist_ok=True)
    fixture=RemainingPagesFixture();errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(BASE+'/settings');await expect(page.get_by_role('button',name='保存配置',exact=True)).to_be_disabled()
        await page.locator('[name=v3_admission_wait_seconds]').fill('99');await expect(page.locator('.settings-save-bar')).to_contain_text('1 项待保存')
        await page.get_by_role('button',name='模型与缓存',exact=True).click();await page.get_by_role('searchbox',name='搜索系统设置',exact=True).fill('准入等待');await expect(page.locator('[name=v3_admission_wait_seconds]')).to_have_value('99')
        await page.get_by_role('button',name='撤销修改',exact=True).click();await expect(page.locator('[name=v3_admission_wait_seconds]')).to_have_value('120')
        await page.get_by_role('searchbox',name='搜索系统设置',exact=True).fill('');await page.get_by_role('button',name='会话与调度',exact=True).click();await page.locator('[name=v3_admission_wait_seconds]').fill('99')
        # 保存载荷为 Settings.vue fieldBindings 的全部键：settingsSchema 57 项加会话封禁 2 项，与页头「59 项配置」一致。
        await expect(page.locator('.settings-total')).to_have_text('59 项配置')
        fixture.settings_gate=asyncio.Event();fixture.settings_started.clear();await page.get_by_role('button',name='保存配置',exact=True).click();await asyncio.wait_for(fixture.settings_started.wait(),5);await page.locator('[name=v3_admission_wait_seconds]').fill('98');fixture.settings_gate.set();await expect(page.get_by_role('button',name='保存配置',exact=True)).to_be_enabled();assert fixture.settings['v3_admission_wait_seconds']=='99';await expect(page.locator('[name=v3_admission_wait_seconds]')).to_have_value('98');assert len(fixture.settings)==59;assert all(isinstance(value,str) for value in fixture.settings.values())
        await page.get_by_role('button',name='撤销修改',exact=True).click();await expect(page.locator('[name=v3_admission_wait_seconds]')).to_have_value('99')
        await page.locator('[name=v3_admission_wait_seconds]').fill('0');await page.get_by_role('button',name='保存配置',exact=True).click();await expect(page.locator('.setting-error').first).to_be_visible();assert len([write for write in fixture.writes if write['path']=='/admin/settings'])==1
        await page.get_by_role('button',name='撤销修改',exact=True).click()
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.screenshot(path=str(out/f'settings-{width}.png'),full_page=True)
        await page.set_viewport_size({'width':1440,'height':1000});await page.goto(BASE+'/requests');await expect(page.locator('.request-records')).to_contain_text('claude-fable-5');await expect(page.locator('.request-records')).to_contain_text('0 ms');await expect(page.get_by_role('radio',name='错误 7',exact=True)).to_be_visible();await page.get_by_role('radio',name='错误 7',exact=True).click();await expect(page.locator('.request-empty')).to_be_visible();assert fixture.diagnostic_queries[-1]['outcome']==['errors']
        await page.get_by_role('radio',name='全部 53',exact=True).click();await expect(page.locator('.request-records')).to_contain_text('claude-fable-5');await page.get_by_role('button',name='筛选',exact=True).click();await expect(page.locator('#request-filters')).to_be_visible()
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.screenshot(path=str(out/f'requests-{width}.png'),full_page=True)
        assert not errors,errors
        (out/'verification.json').write_text(json.dumps({'passed':True,'settings_keys':sorted(fixture.settings),'errors':errors,'queries':fixture.diagnostic_queries},ensure_ascii=False,indent=2));await browser.close();print('系统设置56字段与请求列表交互验证通过')


if __name__=='__main__':asyncio.run(main())
