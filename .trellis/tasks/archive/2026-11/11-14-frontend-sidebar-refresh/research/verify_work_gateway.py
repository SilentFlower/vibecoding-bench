"""验证任务账号网关创建、关联、指标同步及解绑入口。"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, expect


async def main():
    """核对独立动作、冲突和策略保留，并输出浏览器证据。@return 无。"""
    out = Path('.deploy/frontend-sidebar-refresh/concept')
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1600, 'height': 1100})
        errors, network = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: network.append(r.url) if r.url.startswith(('http:', 'https:')) else None)
        await page.goto(Path('doc/design/flower2api-concept.html').resolve().as_uri()+'#tasks?tab=accounts&account=103')
        bound = page.locator('[data-work-account-card="101"]')
        local = page.locator('[data-work-account-card="103"]')
        dialog = page.locator('#action-dialog')
        for op in ['unbind']:
            await expect(bound.locator('[data-work-gateway-operation="'+op+'"]').first).to_be_visible()
        await expect(bound.get_by_role('button', name='重新授权并同步')).to_be_visible()
        for op in ['create', 'bind']:
            await expect(local.locator('[data-work-gateway-operation="'+op+'"]')).to_be_visible()
        # 创建冲突不会变成隐式绑定。
        await local.locator('[data-work-gateway-operation="create"]').click()
        await dialog.get_by_role('button', name='创建 网关账号', exact=True).click()
        await expect(dialog.locator('.work-form-error')).to_contain_text('已有匹配')
        assert await page.evaluate('accounts.length===6 && workAccounts[2].cc2api_account_id===null')
        await page.keyboard.press('Escape')
        # 关联候选排除已占用账号；身份不匹配会保留当前关系。
        await local.locator('[data-work-gateway-operation="bind"]').click()
        options = await dialog.locator('[name="cc2api_account_id"] option').evaluate_all('nodes=>nodes.map(n=>n.value)')
        assert '1' not in options and '2' not in options and '3' in options
        await dialog.get_by_role('combobox', name='已有 网关账号').click()
        await page.get_by_role('option').filter(has_text='#4').click()
        await dialog.get_by_role('button', name='关联已有账号', exact=True).click()
        await expect(dialog.locator('.work-form-error')).to_contain_text('身份')
        await dialog.get_by_role('combobox', name='已有 网关账号').click()
        await page.get_by_role('option').filter(has_text='#3').click()
        before = await page.evaluate('JSON.stringify(accounts[2])')
        warmup_before = await page.evaluate("JSON.stringify(workSpaces.get('warmup:103').schedule)")
        await dialog.get_by_role('button', name='关联已有账号', exact=True).click()
        await expect(dialog).not_to_be_visible()
        assert await page.evaluate('workAccounts[2].cc2api_account_id===3')
        assert before == await page.evaluate('JSON.stringify(accounts[2])')
        assert warmup_before == await page.evaluate("JSON.stringify(workSpaces.get('warmup:103').schedule)")
        await expect(local.locator('[data-work-gateway-operation="process"]')).to_have_count(0)
        await local.locator('[data-work-account-config]').click()
        await dialog.locator('.work-advanced-maintenance summary').click()
        await dialog.locator('[data-work-gateway-operation="process"]').click()
        await page.locator('dialog.secondary-dialog[open]').get_by_role('button', name='更新进程指标', exact=True).click()
        await expect(page.locator('dialog.secondary-dialog[open]')).to_have_count(0)
        await page.keyboard.press('Escape')
        await expect(local).to_contain_text('CLI RSS 未采集')
        assert before == await page.evaluate('JSON.stringify(accounts[2])')
        # 普通配置保存保持关联，独立解绑取消与确认有不同结果。
        await local.locator('[data-work-account-config]').click()
        await expect(dialog.locator('[name="gateway_account"]')).to_have_count(0)
        await dialog.get_by_role('button', name='保存账号配置').click()
        assert await page.evaluate('workAccounts[2].cc2api_account_id===3')
        await page.evaluate("workSpaces.get('warmup:103').schedule.enabled=true;workAccounts[2].warmup_enabled=1")
        await local.locator('[data-work-gateway-operation="unbind"]').click()
        await dialog.get_by_role('button', name='取消', exact=True).click()
        assert await page.evaluate('workAccounts[2].cc2api_account_id===3')
        await local.locator('[data-work-gateway-operation="unbind"]').click()
        await dialog.get_by_role('button', name='解除 网关关联', exact=True).click()
        await expect(dialog).not_to_be_visible()
        assert await page.evaluate("workAccounts[2].cc2api_account_id===null && !workAccounts[2].warmup_enabled && !workSpaces.get('warmup:103').schedule.enabled && accounts.length===6")
        # 原运行环境仍然可达，关联与环境身份分开。
        await local.locator('[data-work-env]').click()
        await expect(dialog.locator('[data-environment-section="schedule"]')).to_be_visible()
        await page.keyboard.press('Escape')
        # 创建一个未匹配的本地示例身份，模拟提交去重与网关列表同步。
        await page.evaluate("workAccountProfiles.set(103,{email:'new-identity@example.test'})")
        await local.locator('[data-work-gateway-operation="create"]').click()
        await dialog.locator('form').evaluate('(form)=>{form.requestSubmit();form.requestSubmit()}')
        await expect(dialog).not_to_be_visible()
        assert await page.evaluate("accounts.length===7 && workAccounts[2].cc2api_account_id===7")
        created = await page.evaluate('accounts.at(-1)')
        assert created['request_backend']=='native293' and created['billing_mode']=='rewrite'
        assert created['concurrency']==4 and created['rpm_limit']==50
        assert created['five_hour_usage_limit_percent']==85 and created['seven_day_usage_limit_percent']==80
        assert created['upstream_session_pool_size']==4 and created['upstream_session_refresh_policy']=='owner_only'
        # 重授权提交回执指向原绑定账号，原网关策略保持。
        before = await page.evaluate('JSON.stringify(accounts.at(-1))')
        await local.get_by_role('button', name='重新授权并同步').click()
        await dialog.get_by_role('button', name='进入授权预览').click()
        await expect(dialog).to_contain_text('提交后同步关联账号 #7')
        await dialog.locator('[data-work-login-simulate]').click()
        await dialog.locator('[data-work-login-commit]').click()
        await expect(local).to_contain_text('已重新授权并同步关联账号 #7')
        assert before == await page.evaluate('JSON.stringify(accounts.at(-1))')
        await page.evaluate("navigate('accounts')")
        await expect(page.locator('[data-account-card="7"]')).to_be_visible()
        await page.evaluate("taskTab='accounts';navigate('tasks')")
        # 旧养号恢复、立即运行与间隔配置继续可达。
        await local.locator('[data-work-warmup="resume"]').click()
        await expect(local.locator('[data-work-warmup="run"]')).to_be_visible()
        await local.locator('[data-work-warmup="run"]').click()
        await expect(local).to_contain_text('已启动一次本地养号示例')
        await local.locator('[data-work-quota-policy]').click()
        await dialog.locator('[name="interval_min_hours"]').fill('6')
        await dialog.locator('[name="interval_max_hours"]').fill('3')
        await dialog.get_by_role('button', name='保存额度配置').click()
        await expect(dialog.locator('.work-form-error')).to_contain_text('上限不能小于')
        await page.keyboard.press('Escape')
        # 绑定发生变化时，旧授权草稿不能同步到新目标。
        await bound.get_by_role('button', name='重新授权并同步').click()
        await dialog.get_by_role('button', name='进入授权预览').click()
        await dialog.locator('[data-work-login-simulate]').click()
        await page.evaluate('workAccounts[0].cc2api_account_id=null')
        await dialog.locator('[data-work-login-commit]').click()
        await expect(page.locator('#toast')).to_contain_text('关联状态已变化')
        await expect(dialog).to_be_visible()
        await page.keyboard.press('Escape')
        await page.reload()
        for width in [1600, 1280, 720, 390]:
            await page.set_viewport_size({'width': width, 'height': 1000})
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
            await page.screenshot(path=str(out/f'work-account-actions-{width}.png'), full_page=True)
            await local.locator('[data-work-gateway-operation="create"]').click()
            assert await dialog.evaluate('node=>node.scrollWidth<=node.clientWidth+1'), width
            await page.screenshot(path=str(out/f'work-account-create-{width}.png'))
            await page.keyboard.press('Escape')
        assert not errors, errors
        assert not network, network
        result={'status':'passed','errors':errors,'network':network,'viewports':[1600,1280,720,390],'checks':['按绑定显示直接操作','创建冲突','候选占用','身份校验','已有策略保持','指标与凭据独立','解绑取消及计划关闭','环境直达','创建去重及列表同步','重授权同步目标','绑定变化拒绝旧授权','旧养号入口']}
        (out/'work-gateway-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result,ensure_ascii=False))
        await browser.close()


if __name__=='__main__':
    asyncio.run(main())
