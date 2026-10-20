"""在独立管理栈验证时段表单、当地时钟及物理面板，数据均为合成资料。"""
import hashlib
import json
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


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
        doc = "document.querySelector('iframe').contentDocument"
        await evaluate(f'{doc}.defaultView.location.hash="#accounts"')
        selector = f'[data-run-window-config="{aid}"]'
        await wait_for(f'Boolean({doc}.querySelector({json.dumps(selector)}))')
        assert await evaluate(f'{doc}.body.textContent.includes("北京时间")')
        await evaluate(f'{doc}.querySelector({json.dumps(selector)}).click()')
        await wait_for(f'!{doc}.querySelector("#run-window-modal").classList.contains("hidden")')
        assert await evaluate(f'{doc}.querySelector("#run-window-timezone").textContent') == "America/New_York"
        await evaluate(f'''(() => {{const form={doc}.querySelector('#run-window-form');
            form.elements.enabled.checked=true;
            form.querySelectorAll('[data-window-day]').forEach(input=>input.checked=['0','4'].includes(input.value));
            form.querySelector('[data-window-start]').value='22:00';
            form.querySelector('[data-window-end]').value='02:00';
            {doc}.querySelector('#run-window-add').click();
            const rows=form.querySelectorAll('.run-window-interval');
            rows[1].querySelector('[data-window-start]').value='07:00';
            rows[1].querySelector('[data-window-end]').value='08:30';form.requestSubmit();}})()''')
        await wait_for(f'{doc}.querySelector("#run-window-modal").classList.contains("hidden")')
        policy = await evaluate(f'fetch("/runtime/api/accounts/{aid}/run-window").then(response=>response.json())')
        assert policy["timezone"] == "America/New_York" and policy["enabled"] and policy["config"]["days"] == [0, 4], policy
        assert policy["config"]["intervals"] == [{"start": "07:00", "end": "08:30"}, {"start": "22:00", "end": "02:00"}], policy
        await evaluate(f'{doc}.querySelector({json.dumps(selector)}).click()')
        await wait_for(f'!{doc}.querySelector("#run-window-modal").classList.contains("hidden")')
        assert await evaluate(f'{doc}.querySelectorAll(".run-window-interval").length') == 2
        await evaluate(f'{doc}.querySelector("#run-window-form").elements.enabled.checked=false;{doc}.querySelector("#run-window-form").requestSubmit()')
        await wait_for(f'{doc}.querySelector("#run-window-modal").classList.contains("hidden")')
        await evaluate(f'{doc}.defaultView.location.hash="#environments"')
        details_selector = f'[data-physical-details="{environment_id}"]'
        await wait_for(f'Boolean({doc}.querySelector({json.dumps(details_selector)}))')
        await evaluate(f'{doc}.querySelector({json.dumps(details_selector)}).open=true')
        content = await evaluate(f'{doc}.querySelector({json.dumps(details_selector)}).textContent')
        assert all(text in content for text in ("保存配置", "容器实测", "上次容器实测", "CPU 型号", "厂商", "machine-id", malicious)), content
        assert await evaluate(f'{doc}.querySelectorAll("img[src=x]").length') == 0
        assert await evaluate(f'{doc}.defaultView.__windowXss||0') == 0
        refresh_selector = f'[data-physical-refresh="{environment_id}"]'
        assert await evaluate(f'{doc}.querySelector({json.dumps(refresh_selector)}).disabled')
        result = await evaluate(f'fetch("/runtime/api/environments/{environment_id}/physical-features/refresh",{{method:"POST"}}).then(response=>response.status)')
        assert result in (409, 503), result
        for width in (1280, 390):
            await rpc("Emulation.setDeviceMetricsOverride", {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": False}, session_id)
            for theme in ("dark", "light"):
                await evaluate(f'(() => {{const doc={doc};if(doc.documentElement.dataset.theme!=="{theme}")doc.querySelector("#theme-toggle").click();}})()')
                bounds = await evaluate(f'(() => {{const doc={doc};const rect=doc.querySelector({json.dumps(details_selector)}).getBoundingClientRect();return {{left:rect.left,right:rect.right,width:doc.defaultView.innerWidth}};}})()')
                assert bounds["left"] >= -1 and bounds["right"] <= bounds["width"] + 1, bounds
        await rpc("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False}, session_id)
        with sqlite3.connect(database) as connection:
            saved = json.loads(connection.execute("SELECT run_window_json FROM accounts WHERE id=?", (aid,)).fetchone()[0])
            current_fingerprint = connection.execute("SELECT fingerprint_json FROM account_environments WHERE environment_id=?", (environment_id,)).fetchone()[0]
        assert not saved["enabled"] and saved["days"] == [0, 4] and len(saved["intervals"]) == 2
        assert current_fingerprint == fingerprint and hashlib.sha256(cache.read_bytes()).hexdigest() == digest
        print("通过：真实页面时段保存/重读/关闭、固化当地时区/双时钟、物理特征来源/XSS/停止不唤醒、1280/390px 明暗主题", flush=True)

    try:
        yield exercise
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM account_environments WHERE environment_id=?", (environment_id,))
            connection.execute("DELETE FROM accounts WHERE id=?", (aid,))
        shutil.rmtree(runtime, ignore_errors=True)
