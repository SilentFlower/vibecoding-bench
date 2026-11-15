"""在独立管理栈验证时段表单、当地时钟及物理面板，数据均为合成资料。"""
import hashlib
import base64
import json
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from native_ui import click_text, time_value


@contextmanager
def run_boundaries_browser_fixture(client, deployment: str, data: Path, browser, base: str):
    """创建停用合成账号及旧观察，验证页面不会为展示启动容器。

    :param client: 本次 Docker 客户端。
    :param deployment: 独立测试部署标识。
    :param data: 本次临时数据根。
    :param browser: 已登录的本地 HTTP 会话。
    :param base: 回环管理栈地址。
    :return: 已登录 Chrome 的页面场景，退出只清理本次合成记录。
    """
    database = data / "bench/db.sqlite"
    name = "window-ui-" + uuid.uuid4().hex[:8]
    with sqlite3.connect(database) as connection:
        aid = connection.execute("INSERT INTO accounts(name,profile_path,timezone,enabled) VALUES(?,?,?,0)",
            (name, "profiles/" + name, "America/New_York")).lastrowid
    control = client.containers.list(filters={"label": ["vibebench.deployment=" + deployment, "vibebench.role=orchestrator"]})[0]
    code = "import main;from account_runtime import AccountRuntime;import docker;" \
        "r=AccountRuntime(docker.from_env(),main.BENCH_DATA,main.HOST_BENCH_DATA,main.get_db,main.derive_v3_fingerprint,main.cc2api_client);" \
        f"print(r._row({name!r},{aid},'America/New_York')['environment_id']);r.heartbeat_pool.shutdown()"
    created = control.exec_run(["python", "-c", code])
    assert created.exit_code == 0, "合成环境记录创建失败"
    environment_id = created.output.decode().strip().splitlines()[-1]
    with sqlite3.connect(database) as connection:
        fingerprint = connection.execute("SELECT fingerprint_json FROM account_environments WHERE environment_id=?", (environment_id,)).fetchone()[0]
        connection.execute("UPDATE account_environments SET container_id=?,isolation_version=2,state='stopped' WHERE environment_id=?",
            ("synthetic-observation-" + uuid.uuid4().hex, environment_id))
        # 用不同的账号表配置证明页面/调度仍以既有环境固化时区为准。
        connection.execute("UPDATE accounts SET timezone='UTC' WHERE id=?", (aid,))
    response = browser.get(base + "/runtime/api/environments", timeout=5)
    response.raise_for_status()
    environment = next(row for row in response.json() if row["environment_id"] == environment_id)
    values = {field["key"]: None for field in environment["physical_features"]["fields"]}
    malicious = 'Observed CPU <img src=x onerror="window.__windowXss=1">'
    values.update(cpu=malicious, hostname="observed-other-host", manufacturer="Synthetic Vendor", os="Synthetic Linux", machine_id=True)
    runtime = data / "bench/environments" / environment_id
    cache = runtime / "runtime/physical-features.json"
    cache.parent.mkdir(parents=True, mode=0o700)
    cache.write_text(json.dumps({"schema": 1, "environment_id": environment_id, "generation": environment["generation"],
        "container_id": environment["container_id"], "observed_at": time.time(), "values": values}))
    cache.chmod(0o600)
    digest = hashlib.sha256(cache.read_bytes()).hexdigest()

    async def exercise(rpc, evaluate, wait_for, session_id: str) -> None:
        """交叉核对真实表单、服务端响应、SQLite、缓存及两个主题尺寸。@return None。"""
        selector = f'[data-run-window-config="{aid}"]'
        await wait_for(f'Boolean(document.querySelector({json.dumps(selector)}))')
        await evaluate(f'document.querySelector({json.dumps(selector)}).click()')
        await wait_for('Boolean(document.querySelector(".runtime-run-window fieldset"))')
        assert await evaluate('document.querySelector(".runtime-run-window").textContent.includes("America/New_York")')
        assert await evaluate('document.querySelector(".runtime-run-window fieldset").disabled')
        await evaluate('document.querySelector(".runtime-run-window [role=switch]").focus()')
        for kind in ('keyDown','keyUp'):
            await rpc('Input.dispatchKeyEvent',{'type':kind,'key':' ','code':'Space','windowsVirtualKeyCode':32},session_id)
        await wait_for('!document.querySelector(".runtime-run-window fieldset").disabled')
        for day in range(7):
            await evaluate(f"(() => {{const input=document.querySelector('.runtime-weekdays input[value=\\\"{day}\\\"]');if(input.checked!=={str(day in (0,4)).lower()})input.click();}})()")
            await evaluate('new Promise(resolve=>requestAnimationFrame(resolve))')
        await time_value(evaluate,wait_for,'时段 1 开始','22:00')
        await time_value(evaluate,wait_for,'时段 1 结束','02:00')
        await click_text(evaluate,'.runtime-run-window button','添加时段')
        await time_value(evaluate,wait_for,'时段 2 开始','07:00')
        await time_value(evaluate,wait_for,'时段 2 结束','08:30')
        await evaluate('document.querySelector(".runtime-run-window").requestSubmit()')
        await wait_for('document.querySelector(".runtime-run-window").textContent.includes("运行时段已保存")')
        policy = await evaluate(f'fetch("/runtime/api/accounts/{aid}/run-window").then(response=>response.json())')
        assert policy["timezone"] == "America/New_York" and policy["enabled"] and policy["config"]["days"] == [0,4],policy
        assert policy["config"]["intervals"] == [{"start":"07:00","end":"08:30"},{"start":"22:00","end":"02:00"}],policy
        await evaluate('document.querySelector("[aria-label=关闭环境详情]").click()')
        assert await evaluate('location.pathname') == '/tasks'
        await wait_for(f'Boolean(document.querySelector({json.dumps(selector)}))')
        await evaluate(f'document.querySelector({json.dumps(selector)}).click()')
        await wait_for('document.querySelectorAll(".runtime-time-interval").length===2')
        for width in (1280,390):
            await rpc('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False},session_id)
            await wait_for("(() => {const r=document.querySelector('.runtime-environment-dialog').getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1;})()")
            bounds=await evaluate("""(() => {const form=document.querySelector('.runtime-run-window'),options=form.querySelector('fieldset');
                const rect=document.querySelector('.runtime-environment-dialog').getBoundingClientRect();
                return {left:rect.left,right:rect.right,width:innerWidth,formOverflow:form.scrollWidth>form.clientWidth+2,
                optionsOverflow:options.scrollWidth>options.clientWidth+2,days:[...form.querySelectorAll('.runtime-weekdays label')].every(e=>getComputedStyle(e).flexDirection==='row')};})()""")
            assert bounds['left']>=-1 and bounds['right']<=bounds['width']+1 and bounds['days'],bounds
            assert not bounds['formOverflow'] and not bounds['optionsOverflow'],bounds
            shot=await rpc('Page.captureScreenshot',{'format':'png'},session_id)
            Path(f'/tmp/v3-native-run-window-{width}.png').write_bytes(base64.b64decode(shot['data']))
        await evaluate('document.querySelector(".runtime-run-window [role=switch]").click()')
        await wait_for('document.querySelector(".runtime-run-window fieldset").disabled')
        await evaluate('document.querySelector(".runtime-run-window [role=switch]").click()')
        assert await evaluate('document.querySelectorAll(".runtime-weekdays input:checked").length')==2
        assert await evaluate('document.querySelectorAll(".runtime-time-interval").length')==2
        # 关闭限制时保留已保存区间，不把尚未保存的新草稿写入账号。
        await time_value(evaluate,wait_for,'时段 1 开始','11:15')
        await evaluate('document.querySelector(".runtime-run-window [role=switch]").click()')
        await evaluate('document.querySelector(".runtime-run-window").requestSubmit()')
        await wait_for('document.querySelector(".runtime-run-window").textContent.includes("运行时段已保存")')
        await click_text(evaluate,'.environment-sections button','运行概览')
        await evaluate('document.querySelector(".runtime-technical:has(.runtime-physical-table)").open=true')
        content=await evaluate('document.querySelector(".runtime-technical:has(.runtime-physical-table)").textContent')
        assert all(text in content for text in ('保存配置','容器实测','CPU 型号','厂商','machine-id',malicious)),content
        assert await evaluate('document.querySelectorAll("img[src=x]").length')==0
        assert await evaluate('window.__windowXss||0')==0
        assert await evaluate("[...document.querySelectorAll('.workspace-inline-actions button')].find(e=>e.textContent.includes('刷新物理实测')).disabled")
        result=await evaluate(f'fetch("/runtime/api/environments/{environment_id}/physical-features/refresh",{{method:"POST"}}).then(response=>response.status)')
        assert result in (409,503),result
        for width in (1280,390):
            await rpc('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False},session_id)
            await wait_for("(() => {const r=document.querySelector('.runtime-environment-dialog').getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1;})()")
            bounds=await evaluate("(() => {const r=document.querySelector('.runtime-technical:has(.runtime-physical-table)').getBoundingClientRect();return {left:r.left,right:r.right,width:innerWidth};})()")
            assert bounds['left']>=-1 and bounds['right']<=bounds['width']+1,bounds
        await evaluate('document.querySelector("[aria-label=关闭环境详情]").click()')
        await rpc('Emulation.setDeviceMetricsOverride',{'width':1280,'height':900,'deviceScaleFactor':1,'mobile':False},session_id)
        with sqlite3.connect(database) as connection:
            saved = json.loads(connection.execute("SELECT run_window_json FROM accounts WHERE id=?", (aid,)).fetchone()[0])
            current_fingerprint = connection.execute("SELECT fingerprint_json FROM account_environments WHERE environment_id=?", (environment_id,)).fetchone()[0]
        assert not saved["enabled"] and saved["days"] == [0, 4] and len(saved["intervals"]) == 2
        assert current_fingerprint == fingerprint and hashlib.sha256(cache.read_bytes()).hexdigest() == digest
        print("通过：真实页面时段保存/重读/关闭、固化当地时区/双时钟、物理特征来源/XSS/停止不唤醒、1280/390px 原生控件与弹窗边界", flush=True)

    try:
        yield exercise
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM account_environments WHERE environment_id=?", (environment_id,))
            connection.execute("DELETE FROM accounts WHERE id=?", (aid,))
        shutil.rmtree(runtime, ignore_errors=True)
