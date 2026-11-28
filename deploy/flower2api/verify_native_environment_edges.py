"""原生环境迁移的状态许可、乱序、长字段和迟到事务回归。"""
import asyncio,copy,json
from pathlib import Path
from playwright.async_api import async_playwright,expect
from verify_native_diagnostics_cpu import DiagnosticsCpuFixture
from verify_environment_ui import BASE,ROOT,ENVIRONMENT


async def run(output=None,gateway=None):
    """覆盖旧环境验收的边界行为。@param output 证据目录。@param gateway 构建路径。@return 验证记录。"""
    fixture=DiagnosticsCpuFixture(gateway or ROOT/'apps/web/dist');errors=[];checks=[];original=copy.deepcopy(fixture.rows)
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1280,'height':1000});await context.route('**/*',fixture.route);await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(BASE+'/environments');cards=page.locator('.environment-rich');await expect(cards).to_have_count(4);assert fixture.sessions==1 and not fixture.writes;await expect(cards.last).to_contain_text('未知状态：future-state');search=page.get_by_role('searchbox',name='搜索运行环境');await search.fill(ENVIRONMENT);await expect(cards).to_have_count(1);await search.fill('');await page.get_by_role('radio',name='需要关注 1',exact=True).click();await expect(cards).to_have_count(1);await page.get_by_role('radio',name='全部环境 4',exact=True).click();checks.append('统一会话首屏只读、名称ID筛选和未知状态')
        workspace=page.locator('.runtime-environment-dialog')
        async def refresh():
            before=fixture.reads;await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            for _ in range(100):
                if fixture.reads>before:break
                await page.wait_for_timeout(10)
            await expect(page.locator('.runtime-environments .fui-page-header button')).to_be_enabled()
        async def open_tab(tab):
            if not await workspace.is_visible():await cards.first.get_by_role('button',name='环境详情',exact=True).click()
            await workspace.get_by_role('tab',name=tab,exact=True).click()
        fixture.rows[1]['native_kernel']=copy.deepcopy(fixture.rows[0]['native_kernel']);fixture.rows[1]['native_kernel']['revision']='second-revision';await refresh();await cards.nth(1).get_by_role('button',name='请求内核',exact=True).click();await expect(workspace).to_contain_text('演示环境 2');await expect(workspace).to_contain_text('随 flower2api 版本统一交付');await expect(workspace.get_by_role('button',name='激活候选',exact=True)).to_have_count(0);await workspace.get_by_role('button',name='关闭环境详情').click();assert not fixture.writes;checks.append('多账号平台内核上下文隔离与只读零写入')
        await open_tab('请求内核');await expect(workspace).not_to_contain_text('Claude Code 2.1.280');await expect(workspace).to_contain_text('Claude Code 2.1.293');await expect(workspace.get_by_role('button',name='检查更新',exact=True)).to_have_count(0);await expect(workspace.get_by_role('button',name='选择版本',exact=True)).to_have_count(0);assert fixture.release_reads==0 and not fixture.writes;checks.append('平台内核版本只读与退休接口零调用')
        fixture.rows[0].update(request_backend='tui_v2', runtime_release='ci-123-1')
        await refresh()
        for panel in ('请求内核', '运行概览'):
            await open_tab(panel)
            basic = workspace.get_by_role('tabpanel', name=panel, exact=True).get_by_role('region', name='基本信息')
            for value in (ENVIRONMENT, '2.1.293', 'ci-123-1'):
                await expect(basic).to_contain_text(value)
        await open_tab('请求内核')
        basic = workspace.get_by_role('tabpanel', name='请求内核', exact=True).get_by_role('region', name='基本信息')
        fixture.rows[0].pop('cli_versions')
        fixture.rows[0]['runtime_release'] = None
        await refresh()
        await expect(basic).to_contain_text('未观测')
        await expect(basic).not_to_contain_text('未安装')
        fixture.rows[0]['cli_versions'] = []
        await refresh()
        await expect(basic).to_contain_text('未安装')
        await expect(basic).not_to_contain_text('2.1.293')
        fixture.rows[0].update(node_observed=False, runtime_release_error='所属节点的实际镜像来源待核对')
        await refresh()
        await expect(basic).to_contain_text('未观测')
        await expect(basic).to_contain_text('待核对')
        await expect(basic).not_to_contain_text('未安装')
        await expect(cards.first.locator('.environment-version-line')).to_contain_text('未观测')
        assert not fixture.writes
        fixture.rows[0] = copy.deepcopy(original[0])
        await refresh()
        checks.append('V2 保留同一环境的基本信息，缺失、实收和节点失联的安装表分别展示')
        for state,reason,label,checking in [('unknown','snapshot_pending','正在检查',True),('unknown','snapshot_missing','等待快照',False),('unknown','check_expired','检查已过期',False),('maintenance','system_maintenance','维护中',False)]:
            fixture.rows[0]['native_preparation']={'state':state,'reason':reason,'checking':checking};await refresh();await expect(cards.first.locator('.environment-readiness strong')).to_have_text(label)
        await workspace.get_by_role('tab',name='运行概览').click();await workspace.get_by_text('运行组件与准备详情',exact=True).click();await expect(workspace).to_contain_text('平台更新中');fixture.rows[0]['native_preparation']['reason']='maintenance';await refresh();await expect(workspace).to_contain_text('账号正在维护');checks.append('首轮快照、过期、平台与账号维护分别展示')
        fixture.rows[0].update(request_backend='native293',state='stopped',native_kernel=None,native_preparation={'state':'unprepared','reason':'backend_pending'},criu={'supported':False});await refresh();await expect(workspace.get_by_role('button',name='重试原生准备',exact=True)).to_be_enabled();await workspace.get_by_role('button',name='重试原生准备',exact=True).click();await expect(cards.first.locator('.environment-readiness strong')).to_have_text('正在准备');assert fixture.writes[-1]['body']=={};checks.append('旧布局准备等待与显式准备原接口')
        fixture.rows=copy.deepcopy(original);fixture.rows[0]['criu'].update(state='unavailable',reason='memory_budget',memory_mib=1024);await refresh();await workspace.get_by_role('tab',name='资源与采集').click();await expect(workspace).to_contain_text('恢复需 2056 MiB')
        for state,label in [('ready','已就绪'),('preparing','准备中'),('unavailable','暂不可用'),('not_installed','需系统更新安装采集器'),('stopped','停止待启动')]:
            fixture.rows[0]['content_capture']['tls_observer']={'state':state};await refresh();await expect(workspace).to_contain_text('原生 TLS 采集：'+label)
        checks.append('CRIU内存门槛与五种TLS采集状态')
        await workspace.get_by_role('tab',name='维护操作').click();fixture.rows[0]['busy']=True;await refresh();await expect(workspace.get_by_role('button',name='停止环境',exact=True)).to_be_disabled();fixture.rows[0]['busy']=False;fixture.rows[0]['native_kernel']['prepared']=None;await refresh();await expect(workspace.get_by_role('button',name='停止环境',exact=True)).to_be_enabled();fixture.rows[0]['native_kernel']['state']='reconcile';await refresh();await expect(workspace.get_by_role('button',name='故障对账',exact=True)).to_be_enabled();checks.append('CLI忙碌与原维护动作许可')
        fixture.rows=copy.deepcopy(original);await refresh();before=len(fixture.writes);await workspace.get_by_role('button',name='停止环境',exact=True).click();dialog=page.get_by_role('dialog',name='停止环境',exact=True);await expect(dialog).to_contain_text('演示环境 A');await dialog.get_by_role('button',name='取消',exact=True).click();assert len(fixture.writes)==before;await workspace.get_by_role('button',name='停止环境',exact=True).click();dialog=page.get_by_role('dialog',name='停止环境',exact=True);await dialog.get_by_role('button',name='确认操作',exact=True).click();await expect(dialog).to_have_count(0);assert fixture.writes[-1]['body']=={'operation':'stop','expected_generation':10};checks.append('原维护确认目标、代次及取消零写入')
        await workspace.get_by_role('tab',name='运行概览').click();await workspace.get_by_text('环境与物理详情',exact=True).click();await expect(workspace).to_contain_text('无对应配置');await expect(workspace).to_contain_text('未限制')
        physical_writes = len(fixture.writes)
        async with page.expect_response(lambda response: response.request.method == 'POST'
                and response.url.endswith('/physical-features/refresh')) as received:
            await workspace.get_by_role('button', name='刷新物理实测', exact=True).click()
        assert (await received.value).ok
        assert len(fixture.writes) == physical_writes + 1
        assert fixture.writes[-1]['path'].endswith('/physical-features/refresh')
        checks.append('物理实测的显式动作、未采集和无限值')
        await workspace.get_by_role('button',name='关闭环境详情').click();fixture.fail_read=True;await refresh();await expect(page.get_by_role('alert')).to_contain_text('合成读取故障');await expect(cards).to_have_count(4);fixture.fail_read=False;fixture.rows[0]['name']='<img src=x onerror="window.envInjected=1">';fixture.rows[0]['native_kernel']['error']='<script>window.envInjected=2</script>';await refresh();await open_tab('请求内核');await expect(workspace).to_contain_text('<script>window.envInjected=2</script>');assert await page.evaluate('window.envInjected===undefined');await workspace.get_by_role('button',name='关闭环境详情').click();checks.append('读取失败保留快照和文本转义')
        fixture.hold_next_read=True;fixture.read_started.clear();await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))");await fixture.read_started.wait();fixture.rows[0]['name']='较新快照';await refresh();fixture.read_gate.set();await expect(cards.first.locator('.fui-entity-card-name')).to_have_text('较新快照');checks.append('乱序列表丢弃旧快照')
        fixture.rows[0]['fingerprint']['hostname']='long-'*70;await open_tab('运行概览');await workspace.get_by_text('环境与物理详情',exact=True).click();await page.set_viewport_size({'width':390,'height':844});assert await workspace.evaluate('e=>e.scrollWidth<=e.clientWidth');await workspace.get_by_role('button',name='关闭环境详情').click();fixture.rows=[];await refresh();await expect(cards).to_have_count(0);await expect(page.get_by_text('暂无账号环境。',exact=True)).to_be_visible();checks.append('手机长字段与真正空列表')
        fixture.rows=copy.deepcopy(original);await page.set_viewport_size({'width':1280,'height':1000});await page.goto(BASE+'/requests');await page.get_by_role('link',name='运行环境',exact=True).first.click();await expect(cards).to_have_count(4);await open_tab('维护操作');fixture.operation_gate=asyncio.Event();fixture.operation_started.clear();await workspace.get_by_role('button',name='停止环境',exact=True).click();dialog=page.get_by_role('dialog',name='停止环境',exact=True);button=dialog.get_by_role('button',name='确认操作',exact=True);handle=await button.element_handle();await button.click();await fixture.operation_started.wait();before=len(fixture.writes);await handle.evaluate("e=>e.dispatchEvent(new MouseEvent('click',{bubbles:true}))");assert len(fixture.writes)==before;await page.go_back();fixture.operation_gate.set();await expect(page).to_have_url(BASE+'/requests');await expect(workspace).to_have_count(0);checks.append('原维护提交去重、离页关闭与迟到回执收口')
        assert not errors,errors;assert not fixture.unexpected,fixture.unexpected;await browser.close()
    return {'passed':True,'checks':checks,'errors':errors}


if __name__=='__main__':print(json.dumps(asyncio.run(run()),ensure_ascii=False))
