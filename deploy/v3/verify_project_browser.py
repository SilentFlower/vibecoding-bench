"""在独立管理栈核对项目模式 DOM、API、SQLite 和按需目录展示。"""
import base64
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
        await evaluate(f'{doc}.querySelector("#project-batch-form").requestSubmit()')
        await wait_for(f'{doc}.querySelectorAll("[data-project-instance]").length===100')
        batch = browser.get(base+'/runtime/api/project-iteration-batches',timeout=10).json()[0]
        bid = batch['id']
        details = browser.get(base+f'/runtime/api/project-iteration-batches/{bid}',timeout=10).json()
        assert len(details['instances'])==100 and all(item['workspace_path'] is None for item in details['instances'])
        assert not list((data/'bench/environments').glob('*/projects/project-*'))
        assert not await evaluate(f'Boolean({doc}.defaultView.__projectXss)')
        assert await evaluate(f'{doc}.querySelectorAll("#project-batch-detail img").length')==0
        await evaluate(f'{doc}.querySelector("[data-project-action=start]").click()')
        await wait_for(f'{doc}.querySelector("#project-batch-detail")?.textContent.includes("时段等待")')
        with sqlite3.connect(database) as connection:
            assert connection.execute('SELECT COUNT(*) FROM project_instances WHERE batch_id=? AND workspace_relative IS NOT NULL',(bid,)).fetchone()[0]==0
            assert connection.execute('SELECT COUNT(*) FROM runs WHERE run_kind=\'project_iteration\' AND status=\'queued\'').fetchone()[0]==1
        assert not list((data/'bench/environments').glob('*/projects/project-*'))
        await evaluate(f'{doc}.querySelector("[data-project-action=pause]").click()')
        await wait_for(f'{doc}.querySelector("#project-batch-detail")?.textContent.includes("已暂停")')
        # 这一段只准备已有实例的页面夹具；真实执行与两步验收由 verify_project_execution 独立证明。
        instance = details['instances'][0]
        relative = 'environments/project-ui-fixture/projects/project-ui-started'
        workspace = data/'bench'/relative
        shutil.copytree(root/'project_library/projects/project-001/seed',workspace)
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE project_instances SET workspace_relative=?,started_at=?,status='ready' WHERE id=?",
                (relative,time.time(),instance['id']))
        await wait_for(f'{doc}.querySelector("#project-batch-detail")?.textContent.includes("/home/node/projects/project-ui-started")')
        selector = json.dumps(f'[data-project-instance="{instance["id"]}"]')
        await evaluate(f'{doc}.querySelector({selector}).click()')
        await wait_for(f'{doc}.querySelector("#project-instance-detail")?.textContent.includes("迭代路线")')
        assert await evaluate(f'{doc}.querySelectorAll("#project-instance-detail ol li").length')==20
        await evaluate(f'{doc}.querySelector("[data-project-roadmap]").open=true')
        await evaluate(f'{doc}.querySelector("#project-batch-detail .project-table-scroll").scrollTop=240')
        await evaluate(f'{doc}.defaultView.eval("window.__projectUpdates=0;state.projectEventSource.addEventListener(\'project-state\',()=>window.__projectUpdates++)")')
        await wait_for(f'{doc}.defaultView.__projectUpdates>=2')
        assert await evaluate(f'{doc}.querySelector("[data-project-roadmap]").open')
        assert await evaluate(f'{doc}.querySelector("#project-batch-detail .project-table-scroll").scrollTop')==240
        for width,height in ((1280,900),(390,844)):
            await rpc('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<500},session_id)
            for theme in ('dark','light'):
                if await evaluate(f'{doc}.documentElement.dataset.theme')!=theme:
                    await evaluate(f'{doc}.querySelector("#theme-toggle").click()')
                await wait_for(f'{doc}.documentElement.dataset.theme=="{theme}"')
                assert await evaluate(f'{doc}.documentElement.scrollWidth <= {doc}.defaultView.innerWidth+2')
                shot = await rpc('Page.captureScreenshot',{'format':'png'},session_id)
                Path(f'/tmp/v3-project-iteration-{width}-{theme}.png').write_bytes(base64.b64decode(shot['data']))
        await evaluate(f'{doc}.querySelector("[data-project-action=stop]").click()')
        await wait_for(f'{doc}.querySelector("#project-batch-detail")?.textContent.includes("已停止")')
        assert workspace.exists()
        orchestrator = client.containers.list(filters={'label':['vibebench.deployment='+deployment,'vibebench.role=orchestrator']})[0]
        orchestrator.restart(timeout=5)
        await wait_for('fetch("/runtime/api/project-iteration-batches").then(r=>r.status===200).catch(()=>false)',timeout=45)
        after = browser.get(base+f'/runtime/api/project-iteration-batches/{bid}',timeout=10).json()
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
