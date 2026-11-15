"""验证共享日期面板拒绝夏令时不存在时刻并保留原草稿。"""
import asyncio,json,re
from playwright.async_api import async_playwright,expect
from verify_remaining_pages import RemainingPagesFixture
from verify_environment_ui import ROOT,BASE


async def main():
    """使用洛杉矶本地跳时时刻验证确认、修正和取消。@return 无。"""
    fixture=RemainingPagesFixture();errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(timezone_id='America/Los_Angeles',viewport={'width':1440,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));await page.goto(BASE+'/proxies');await page.get_by_role('button',name='添加代理',exact=True).click();await page.get_by_role('button',name='到期时间',exact=True).click();calendar=page.locator('.fui-calendar');await expect(calendar).to_be_visible()
        for _ in range(24):
            heading=(await calendar.locator('.fui-calendar-header').inner_text()).replace(' ','').replace('\n','');match=re.search(r'(\d{4})年(\d{1,2})月',heading)
            assert match,heading
            value=(int(match[1]),int(match[2]))
            if value==(2027,3):break
            await calendar.get_by_role('button',name='下个月' if value<(2027,3) else '上个月',exact=True).click()
        else:raise AssertionError('日历未到达目标月份')
        await calendar.locator('td button').filter(has_text=re.compile('^14$')).click();await calendar.get_by_role('spinbutton',name='小时',exact=True).fill('2');await calendar.get_by_role('spinbutton',name='分钟',exact=True).fill('30');await calendar.get_by_role('button',name='确定',exact=True).click();await expect(calendar.get_by_role('alert')).to_contain_text('当前时区不存在这个时间');await expect(calendar).to_be_visible()
        await calendar.get_by_role('spinbutton',name='小时',exact=True).fill('3');await calendar.get_by_role('button',name='确定',exact=True).click();await expect(calendar).to_be_hidden();await expect(page.get_by_role('button',name='到期时间',exact=True)).to_contain_text('03:30');await page.get_by_role('button',name='取消',exact=True).click();assert not fixture.writes;assert not errors,errors
        out=ROOT/'.deploy/frontend-sidebar-refresh/all-pages/datetime-boundary.json';out.write_text(json.dumps({'passed':True,'timezone':'America/Los_Angeles','rejected':'2027-03-14 02:30','accepted':'2027-03-14 03:30','writes':0,'errors':errors},ensure_ascii=False,indent=2));print('日期跳时拒绝、修正及取消验证通过');await browser.close()


if __name__=='__main__':asyncio.run(main())
