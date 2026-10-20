"""在独立管理栈核对项目模式 DOM、API、SQLite 和按需目录展示。"""
import base64
import asyncio
import json
import shutil
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


@contextmanager
def project_browser_fixture(client, deployment: str, data: Path, browser, base: str):
    """准备永不进入真实模型的窗口等待账号与页面场景。

    :param client: 本次 Docker 客户端。
    :param deployment: 本次随机部署。
    :param data: 本次独立数据根。
    :param browser: 已登录 HTTP 会话。
    :param base: 本地网关地址。
    :return: 供现有 Chrome 验证器调用的场景函数。
    """
    database = data/'bench/db.sqlite'
    day = (datetime.now(timezone.utc).weekday()+3)%7
    window = {'schema':1,'enabled':True,'days':[day],'intervals':[{'start':'00:00','end':'00:01'}]}
    with sqlite3.connect(database) as connection:
        aid = connection.execute('INSERT INTO accounts(name,profile_path,timezone,run_window_json) VALUES(?,?,?,?)',
            ('project-ui-fixture','profiles/project-ui-fixture','UTC',json.dumps(window))).lastrowid
    root = Path(__file__).resolve().parents[2]
    unsafe_name = '自动项目 <img src=x onerror="window.__projectXss=1">'

    async def exercise(rpc,evaluate,wait_for,session_id):
        """通过真实页面创建、启动、暂停与停止，并核对独立存储。

        :param rpc: CDP 命令。
        :param evaluate: 页面执行器。
        :param wait_for: 有界条件等待。
        :param session_id: 浏览器会话。
        :return: None；失败时抛出断言。
        """
        doc = "document.querySelector('iframe').contentDocument"
        await wait_for(f'Boolean({doc}?.querySelector(".tabs"))')
        await evaluate(f'{doc}.defaultView.location.hash="#projects"')
        await wait_for(f'{doc}.querySelector("#project-library-count")?.textContent.includes("100 个项目")')
        assert await evaluate(f'{doc}.querySelector("#project-library-count").textContent.includes("2000 个步骤")')
        await evaluate(f'{doc}.querySelector("#project-batch-form").elements.account_id.value="{aid}"')
        await evaluate(f'{doc}.querySelector("#project-batch-form").elements.name.value={json.dumps(unsafe_name)}')
        for width,height in ((1280,900),(390,844)):
            await rpc('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<500},session_id)
            assert await evaluate(f'{doc}.documentElement.scrollWidth <= {doc}.defaultView.innerWidth+2')
            shot = await rpc('Page.captureScreenshot',{'format':'png'},session_id)
            Path(f'/tmp/v3-project-scheduling-form-{width}.png').write_bytes(base64.b64decode(shot['data']))
        await evaluate(f'{doc}.querySelector("#project-batch-form").requestSubmit()')
        await wait_for(f'{doc}.querySelectorAll("[data-project-instance]").length===100')
        batch = browser.get(base+'/runtime/api/project-iteration-batches',timeout=10).json()[0]
        bid = batch['id']
        details = browser.get(base+f'/runtime/api/project-iteration-batches/{bid}',timeout=10).json()
        assert len(details['instances'])==100 and all(item['workspace_path'] is None for item in details['instances'])
        assert details['policy']=={'schema':2,'concurrency':2,'active_projects':3,'rotation_steps':5,
            'steps_per_plan':2,'timeout_sec':1800,'interval_min_sec':0,'interval_max_sec':0,'repair_limit':2}
        assert details['scheduling']['account_concurrency_limit']==2
        order = [item['project_key'] for item in details['instances']]
        assert not list((data/'bench/environments').glob('*/projects/project-*'))
        assert not await evaluate(f'Boolean({doc}.defaultView.__projectXss)')
        assert await evaluate(f'{doc}.querySelectorAll("#project-batch-detail img").length')==0
        await evaluate(f'{doc}.querySelector("[data-project-action=start]").click()')
        await wait_for(f'Boolean({doc}.querySelector("[data-project-action=pause]")) && {doc}.querySelector("#project-batch-detail")?.textContent.includes("下次开放")')
        with sqlite3.connect(database) as connection:
            assert connection.execute('SELECT COUNT(*) FROM project_instances WHERE batch_id=? AND workspace_relative IS NOT NULL',(bid,)).fetchone()[0]==0
            assert connection.execute('SELECT COUNT(*) FROM runs WHERE run_kind=\'project_iteration\' AND status=\'queued\'').fetchone()[0]==0
        assert not list((data/'bench/environments').glob('*/projects/project-*'))
        await evaluate(f'{doc}.querySelector("[data-project-action=pause]").click()')
        await wait_for(f'{doc}.querySelector("#project-batch-detail")?.textContent.includes("已暂停")')
        # 这一段只准备已有实例的页面夹具；真实执行与两步验收由 verify_project_execution 独立证明。
        instance = details['instances'][0]
        relative = 'environments/project-ui-fixture/projects/project-ui-started'
        workspace = data/'bench'/relative
        shutil.copytree(root/'project_library/projects'/instance['project_key']/'seed',workspace)
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE project_instances SET workspace_relative=?,started_at=?,status='ready',next_step_index=1,visit_completed=1,in_pool=1 WHERE id=?",
                (relative,time.time(),instance['id']))
            task_id = connection.execute("INSERT INTO tasks(topic_no,title,prompt,account_id) VALUES(1,'Project plan UI fixture','Continue the current project step.',?)",(aid,)).lastrowid
            run_id = 'project-ui-timeout'
            connection.execute("INSERT INTO runs(id,task_id,account_id,status,run_kind,error) VALUES(?,?,?,'timeout','project_iteration','合成半步超时场景')",(run_id,task_id,aid))
            plan_id = connection.execute("INSERT INTO project_execution_plans(instance_id,generation,start_index,target_index,completed_steps,session_id,execution_json,status,created_at,updated_at) VALUES(?,1,0,2,1,'fixture-session','{}','ready',?,?)",
                (instance['id'],time.time(),time.time())).lastrowid
            attempt_id = connection.execute("INSERT INTO project_step_attempts(instance_id,step_id,attempt_no,generation,run_id,expected_checkpoint_digest,validation_status,created_at,ended_at,plan_id) VALUES(?,'step-02',1,1,?,?,'failed',?,?,?)",
                (instance['id'],run_id,instance['checkpoint_digest'],time.time(),time.time(),plan_id)).lastrowid
            connection.execute('INSERT INTO project_plan_executions(plan_id,run_id,current_attempt_id,created_at,ended_at) VALUES(?,?,?,?,?)',
                (plan_id,run_id,attempt_id,time.time(),time.time()))
        await wait_for(f'{doc}.querySelector("#project-batch-detail")?.textContent.includes("/home/node/projects/project-ui-started")')
        selector = json.dumps(f'[data-project-instance="{instance["id"]}"]')
        await evaluate(f'{doc}.querySelector({selector}).click()')
        await wait_for(f'{doc}.querySelector("#project-instance-detail")?.textContent.includes("迭代路线")')
        assert await evaluate(f'{doc}.querySelector("#project-instance-detail").textContent.includes("已通过 1/2")')
        assert await evaluate(f'{doc}.querySelector("#project-instance-detail").textContent.includes("当前第 2 步待完成")')
        await evaluate(f'{doc}.querySelector("[data-project-run=project-ui-timeout]").click()')
        await wait_for(f'{doc}.querySelector("#modal-content")?.textContent.includes("project-ui-timeout")')
        await evaluate(f'{doc}.querySelector("#modal-close").click()')
        await wait_for(f'{doc}.querySelector("#modal").classList.contains("hidden")')
        assert await evaluate(f'{doc}.querySelector(".project-instances-table tbody tr:first-child td:first-child .pill").textContent')=='活动池'
        assert await evaluate(f'{doc}.querySelectorAll("#project-instance-detail ol li").length')==20
        await evaluate(f'{doc}.querySelector("[data-project-roadmap]").open=true')
        await evaluate(f'{doc}.querySelector("#project-batch-detail .project-table-scroll").scrollTop=240')
        await evaluate(f'{doc}.defaultView.eval("window.__projectUpdates=0;state.projectEventSource.addEventListener(\'project-state\',()=>window.__projectUpdates++)")')
        await wait_for(f'{doc}.defaultView.__projectUpdates>=2')
        assert await evaluate(f'{doc}.querySelector("[data-project-roadmap]").open')
        assert await evaluate(f'{doc}.querySelector("#project-batch-detail .project-table-scroll").scrollTop')==240
        # 瞬态会被后台迅速收口；暂停推送后，用真实公开结构验证每个渲染分支。
        await evaluate(f'{doc}.defaultView.eval("state.projectEventSource.close();state.projectEventSource=null")')
        for status, message in (('active','按保存的队列与容量自动推进'),('paused','批次已暂停'),
                ('pausing','正在暂停'),('stopping','正在停止'),('stopped','批次已停止'),
                ('blocked','批次已阻塞'),('completed','全部项目路线已完成')):
            program = f"state.projectBatchDetail={{...state.projectBatchDetail,status:{json.dumps(status)},next_launch_at:Date.now()/1000+600,scheduling:{{...state.projectBatchDetail.scheduling,wait_reasons:[]}}}};paintProjectBatch()"
            await evaluate(f'{doc}.defaultView.eval({json.dumps(program)})')
            hint = await evaluate(f'{doc}.querySelector(".project-scheduling-hint").textContent')
            assert message in hint and '等待批次启动' not in hint,(status,hint)
            assert ('下一投放最早' in hint)==(status=='active'),(status,hint)
        await evaluate(f'{doc}.defaultView.eval("selectProjectBatch({bid})")')
        await wait_for(f'{doc}.querySelector(".project-scheduling-hint")?.textContent.includes("批次已暂停")')
        for width,height in ((1280,900),(390,844)):
            await rpc('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<500},session_id)
            for theme in ('dark','light'):
                if await evaluate(f'{doc}.documentElement.dataset.theme')!=theme:
                    await evaluate(f'{doc}.querySelector("#theme-toggle").click()')
                await wait_for(f'{doc}.documentElement.dataset.theme=="{theme}"')
                assert await evaluate(f'{doc}.documentElement.scrollWidth <= {doc}.defaultView.innerWidth+2')
                shot = await rpc('Page.captureScreenshot',{'format':'png'},session_id)
                Path(f'/tmp/v3-project-iteration-{width}-{theme}.png').write_bytes(base64.b64decode(shot['data']))
        await evaluate(f'setTimeout(()=>{doc}.querySelector("[data-project-action=stop]").click(),0)')
        await asyncio.sleep(0.2)
        await rpc('Page.handleJavaScriptDialog',{'accept':True},session_id)
        await wait_for(f'{doc}.querySelector("#project-batch-detail")?.textContent.includes("已停止")')
        assert workspace.exists()
        orchestrator = client.containers.list(filters={'label':['vibebench.deployment='+deployment,'vibebench.role=orchestrator']})[0]
        orchestrator.restart(timeout=5)
        await wait_for('fetch("/runtime/api/project-iteration-batches").then(r=>r.status===200).catch(()=>false)',timeout=45)
        after = browser.get(base+f'/runtime/api/project-iteration-batches/{bid}',timeout=10).json()
        assert order==[item['project_key'] for item in after['instances']]
        assert after['instances'][0]['workspace_path']=='/home/node/projects/project-ui-started'
        assert (workspace/'app.py').exists()
        assert sum(item['workspace_path'] is not None for item in after['instances'])==1
        await evaluate(f'{doc}.defaultView.location.hash="#topics"')
        await wait_for(f'{doc}.defaultView.eval("state.projectEventSource===null")')
        print('通过：项目 UI→API→SQLite；100 项目初始零目录；窗口等待／暂停／停止；已开始目录跨重启保留；1280/390px 明暗主题与 XSS；页面夹具不代表模型执行',flush=True)

    try:
        yield exercise
    finally:
        # 保留项目和目录证据，同时让后续离线导入验证只面对停用的合成账号。
        with sqlite3.connect(database) as connection:
            connection.execute('UPDATE accounts SET enabled=0,warmup_enabled=0,cc2api_account_id=NULL WHERE id=?',(aid,))
