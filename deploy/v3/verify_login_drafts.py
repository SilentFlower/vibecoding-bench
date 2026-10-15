"""真实页面/HTTP/SQLite/Docker 草稿演练，使用随机部署和合成 CLI。"""
import json
import shutil
import sqlite3
import time

from requests import RequestException

from manage import REPO


async def verify_login_drafts(client, deployment, data, browser, base, proxy_address, rpc, evaluate, wait_for, session_id):
    """验证未提交账号发现、终态、重启、提交和完整删除。

    :param client: 本次本地 Docker 客户端
    :param deployment: 随机隔离部署
    :param data: 本次独立数据根
    :param browser: 已鉴权的 HTTP 客户端
    :param base: 本地网关地址
    :param proxy_address: 合成代理地址
    :param rpc: Chrome CDP 命令
    :param evaluate: 浏览器脚本执行
    :param wait_for: 有界 DOM 等待
    :param session_id: 私有 Chrome 会话
    :return: None；偏差立即失败，由外层清理本次部署
    """
    name = "draft-ui-fixture"
    doc = "document.querySelector('iframe').contentDocument"
    win = "document.querySelector('iframe').contentWindow"
    state = win + ".eval('state.accLogin')"
    orchestrator = client.containers.list(filters={"label": ["vibebench.deployment=" + deployment, "vibebench.role=orchestrator"]})[0]
    code = "import main,docker;from account_runtime import AccountRuntime;" \
        "r=AccountRuntime(docker.from_env(),main.BENCH_DATA,main.HOST_BENCH_DATA,main.get_db,main.derive_v3_fingerprint,main.cc2api_client);" \
        f"print(r._row({name!r})['environment_id']);r.heartbeat_pool.shutdown()"
    created = orchestrator.exec_run(["python", "-c", code])
    assert created.exit_code == 0
    environment_id = created.output.decode().strip().splitlines()[-1]
    root = data / "bench/environments" / environment_id
    home = root / "home"
    home.mkdir(parents=True)
    (home / ".claude.json").write_text(json.dumps({"userID": "d" * 64}))
    binary = root / "cli/9.9.9/node_modules/.bin/claude"
    binary.parent.mkdir(parents=True)
    shutil.copy2(REPO / "deploy/v3/fixtures/mock_cli.py", binary)
    binary.chmod(0o755)
    (root / "cli/9.9.9/.ready").touch()
    (home / ".synthetic-login.json").write_text(json.dumps({"wait_for_code": True, "new_endpoint": True}))
    bench_db = data / "bench/db.sqlite"

    async def reload_iframe():
        """等待新文档完成，避免误点刷新前的旧按钮。@return None。"""
        await evaluate(f"{win}.__draftReloadMarker=true;{win}.location.reload()")
        await wait_for(f"Boolean({doc}?.readyState==='complete' && !{win}.__draftReloadMarker && {doc}.querySelector('#add-account'))")
        # 页面脚本已加载不等于首次账号查询已完成；重复渲染会并发争用草稿只读快照锁。
        await wait_for(f"typeof {doc}.querySelector('#accounts-body').onclick === 'function'")

    async def restart_manager():
        """模拟本次管理器突然退出，等待对账恢复后载入新文档。@return None。"""
        orchestrator.kill(signal="SIGKILL")
        orchestrator.start()
        deadline = time.monotonic() + 30
        while True:
            try:
                if browser.get(base + "/runtime/api/environments", timeout=2).status_code == 200:
                    break
            except RequestException:
                pass
            assert time.monotonic() < deadline, "测试管理器未恢复"
            await evaluate("new Promise(resolve=>setTimeout(resolve,100))")
        await reload_iframe()

    async def click_button(selector):
        """滚动到实际可见按钮，用 Chrome 鼠标事件点击。@param selector DOM 选择器；@return None。"""
        selected = json.dumps(selector)
        await evaluate(f"{doc}.querySelector({selected}).scrollIntoView({{block:'center',inline:'center'}})")
        point = await evaluate(f"(() => {{const d={doc},b=d.querySelector({selected}),r=b.getBoundingClientRect(),f=document.querySelector('iframe').getBoundingClientRect();if(d.elementFromPoint(r.left+r.width/2,r.top+r.height/2)!==b) throw Error('按钮被遮挡');return {{x:f.left+r.left+r.width/2,y:f.top+r.top+r.height/2}};}})()")
        await rpc("Input.dispatchMouseEvent", {"type": "mousePressed", **point, "button": "left", "clickCount": 1}, session_id)
        await rpc("Input.dispatchMouseEvent", {"type": "mouseReleased", **point, "button": "left", "clickCount": 1}, session_id)

    await evaluate(f"{doc}.querySelector('#add-account').click()")
    await evaluate(f"(() => {{const f={doc}.querySelector('#acc-form');f.elements.name.value='{name}';f.elements.upstream_proxy_scheme.value='socks5h';f.elements.upstream_socks5_host.value='{proxy_address}';f.elements.upstream_socks5_port.value='1080';f.requestSubmit();}})()")
    await wait_for(f"Boolean({state}?.authorizationURL)")
    sid = await evaluate(f"{state}.sid")
    assert await evaluate(f"{doc}.querySelector('#acc-auth-url').value.startsWith('https://claude.com/cai/oauth/authorize?')")
    draft = browser.get(base + "/runtime/api/accounts/login-drafts", timeout=10).json()[0]
    assert draft["environment_id"] == environment_id and draft["state"] == "authorizing"
    assert not any(row["name"] == name for row in browser.get(base + "/runtime/api/accounts", timeout=10).json())
    assert not await evaluate(f"{win}.eval('state.accounts').some(a=>a.name==='{name}')")
    container = client.containers.list(filters={"label": ["vibebench.deployment=" + deployment, "vibebench.environment=" + environment_id]})[0]
    container.reload()
    original_container = container.id
    assert container.attrs["HostConfig"]["RestartPolicy"]["Name"] == "no"
    print("通过：新草稿/新官方入口可见，不进入正式账号及任务/养号选择，账号容器按需启动")

    # 刷新销毁浏览器句柄，服务端原 SID/tmux 必须仍可继续。
    await reload_iframe()
    await wait_for(f"Boolean({doc}?.querySelector('[data-draft-resume=\"{environment_id}\"]'))")
    await evaluate(f"{win}.__draftAlerts=[];{win}.alert=message=>{win}.__draftAlerts.push(message)")
    await click_button(f'[data-draft-resume="{environment_id}"]')
    try:
        await wait_for(f"Boolean({state}?.authorizationURL && {state}?.ws?.readyState===1)")
    except TimeoutError:
        print("草稿继续诊断：", browser.get(base + "/runtime/api/accounts/login-drafts", timeout=10).json(), flush=True)
        print("页面继续诊断：", await evaluate(f"[Boolean({state}),{doc}.querySelector('#acc-login-link-status').textContent,{doc}.querySelector('#acc-login-connection-status').textContent,{win}.__draftAlerts]"), flush=True)
        raise
    assert await evaluate(f"{state}.sid") == sid
    await evaluate(f"{doc}.querySelector('#acc-auth-code').focus()")
    await rpc("Input.insertText", {"text": "synthetic-exit"}, session_id)
    await click_button('#acc-code-send')
    await wait_for(f"!{doc}.querySelector('#acc-login-restart').classList.contains('hidden')")
    ended_message = await evaluate(f"{doc}.querySelector('#acc-login-connection-status').textContent")
    assert "已结束" in ended_message
    await evaluate(f"{state}.ws.onerror(new Event('error'))")
    await evaluate(f"{state}.term.paste('must-not-replay\\r')")
    assert await evaluate(f"{doc}.querySelector('#acc-login-connection-status').textContent") == ended_message
    await click_button('#acc-login-restart')
    try:
        await wait_for(f"Boolean({state}?.authorizationURL && {state}.sid !== '{sid}')")
    except TimeoutError:
        print("草稿重新登录诊断：", browser.get(base + "/runtime/api/accounts/login-drafts", timeout=10).json(), flush=True)
        print("页面重新登录诊断：", await evaluate(f"[{win}.__draftAlerts,Boolean({state}),{doc}.querySelector('#acc-login-connection-status').textContent]"), flush=True)
        raise
    assert await evaluate(f"{state}.environmentId") == environment_id
    assert json.loads((home / ".claude.json").read_text())["userID"] == "d" * 64
    with sqlite3.connect(bench_db) as connection:
        assert connection.execute("SELECT container_id FROM account_environments WHERE environment_id=?", (environment_id,)).fetchone()[0] == original_container
    print("通过：刷新继续原 SID，真实 CLI 退出明确终态，离线输入不覆盖原因，新 SID 保留固定容器/HOME/身份")

    await restart_manager()
    # 管理器启动 reconcile 收口原执行；刷新列表只发现草稿，不创建新 CLI。
    await wait_for(f"{doc}.querySelector('#accounts-body').textContent.includes('登录已中断')")
    interrupted = browser.get(base + "/runtime/api/accounts/login-drafts", timeout=10).json()[0]
    assert interrupted["state"] == "interrupted" and interrupted["session_id"] is None
    container.reload()
    assert container.status != "running"
    assert home.exists() and json.loads((home / ".claude.json").read_text())["userID"] == "d" * 64
    await click_button(f'[data-draft-restart="{environment_id}"]')
    await wait_for(f"Boolean({state}?.authorizationURL && {state}?.ws?.readyState===1)")
    await evaluate(f"{doc}.querySelector('#acc-auth-code').focus()")
    await rpc("Input.insertText", {"text": "synthetic-code"}, session_id)
    await click_button('#acc-code-send')
    await wait_for(f"{doc}.querySelector('#acc-login-link-status').textContent.includes('可以提交保存')")
    print("通过：管理器重启后草稿可见、原账号停止且 HOME 保留，重新登录验证真实 CLI 认证")

    # 产物已写但尚未提交，再重启：继续只验证产物，不启动另一个授权 CLI。
    await restart_manager()
    try:
        await wait_for(f"Boolean({doc}.querySelector('[data-draft-resume=\"{environment_id}\"]:not([disabled])'))")
    except TimeoutError:
        print("重启后草稿入口诊断：", browser.get(base + "/runtime/api/accounts/login-drafts", timeout=10).json(), flush=True)
        print("重启后草稿按钮诊断：", await evaluate(f"{doc}.querySelector('#accounts-body').textContent"), flush=True)
        raise
    await click_button(f'[data-draft-resume="{environment_id}"]')
    try:
        await wait_for(f"{doc}.querySelector('#acc-login-link-status').textContent.includes('可以提交保存')")
    except TimeoutError:
        print("重启后提交诊断：", browser.get(base + "/runtime/api/accounts/login-drafts", timeout=10).json(), flush=True)
        print("重启后页面诊断：", await evaluate(f"[Boolean({state}),{doc}.querySelector('#acc-login-link-status').textContent,{doc}.querySelector('#acc-login-connection-status').textContent]"), flush=True)
        raise
    await click_button('#acc-login-commit')
    await wait_for(f"{doc}.querySelector('#acc-modal').classList.contains('hidden')")
    await wait_for(f"{doc}.querySelector('#account-login-result').textContent.includes('仅保存到本地，尚未关联 cc2api')")
    with sqlite3.connect(bench_db) as connection:
        account_id = connection.execute("SELECT id FROM accounts WHERE name=?", (name,)).fetchone()[0]
        assert connection.execute("SELECT account_id FROM account_environments WHERE environment_id=?", (environment_id,)).fetchone()[0] == account_id
    assert browser.delete(base + f"/runtime/api/accounts/login-drafts/{environment_id}", params={"generation": interrupted["generation"]}, timeout=10).status_code == 409
    assert browser.get(base + "/runtime/api/accounts/login-drafts", timeout=10).json() == []
    print("通过：重启后真实认证检查保留产物，原环境完成提交，正式账号不能被草稿删除")

    # 单独合成草稿完整删除，不能删除刚保存账号；同名可重新创建。
    name = "delete-draft-fixture"
    created = orchestrator.exec_run(["python", "-c", code.replace("draft-ui-fixture", name)])
    assert created.exit_code == 0
    delete_id = created.output.decode().strip().splitlines()[-1]
    delete_root = data / "bench/environments" / delete_id
    (delete_root / "home").mkdir(parents=True)
    delete_binary = delete_root / "cli/9.9.9/node_modules/.bin/claude"
    delete_binary.parent.mkdir(parents=True)
    shutil.copy2(REPO / "deploy/v3/fixtures/mock_cli.py", delete_binary)
    delete_binary.chmod(0o755)
    (delete_root / "cli/9.9.9/.ready").touch()
    (delete_root / "home/.synthetic-login.json").write_text(json.dumps({"wait_for_code": True}))
    (delete_root / "home/.claude.json").write_text(json.dumps({"userID": "e" * 64}))
    response = browser.post(base + "/runtime/api/accounts/login/start", json={"name": name,
        "upstream_proxy_scheme": "socks5h", "upstream_socks5_host": proxy_address, "upstream_socks5_port": 1080}, timeout=60)
    assert response.status_code == 200
    failed_sid = response.json()["session_id"]
    draft_container = client.containers.list(filters={"label": ["vibebench.deployment=" + deployment, "vibebench.environment=" + delete_id]})[0]
    before_home = (delete_root / "home/.claude.json").read_bytes()
    # 只破坏本次合成容器的 Recorder 入口，复现取消后的隔离保护，不碰正式镜像/账号。
    assert draft_container.exec_run(["mv", "/usr/local/bin/v3-network-context", "/usr/local/bin/v3-network-context.disabled"]).exit_code == 0
    assert browser.delete(base + f"/runtime/api/accounts/login/{failed_sid}", timeout=20).status_code == 503
    failed = next(row for row in browser.get(base + "/runtime/api/accounts/login-drafts", timeout=10).json() if row["environment_id"] == delete_id)
    assert failed["state"] == "reconcile" and failed["can_reconcile"]
    assert failed["proxy_known"] and failed["proxy_summary"] == f"socks5h://{proxy_address}:1080"
    await evaluate(f"{win}.renderAccounts()")
    await wait_for(f"Boolean({doc}.querySelector('[data-draft-reconcile=\"{delete_id}\"]'))")
    assert f"socks5h://{proxy_address}:1080" in await evaluate(f"{doc}.querySelector('#accounts-body').textContent")
    await click_button(f'[data-draft-reconcile="{delete_id}"]')
    await wait_for(f"Boolean({doc}.querySelector('[data-draft-delete=\"{delete_id}\"]:not([disabled])'))")
    assert browser.get(base + f"/runtime/api/accounts/login/{failed_sid}/status", timeout=10).status_code == 404
    assert (delete_root / "home/.claude.json").read_bytes() == before_home
    assert not (delete_root / "runtime/execution.json").exists()
    print("通过：真实清理故障后页面恢复检查收口原 SID，恢复删除操作，HOME 保留且草稿代理可见")
    await evaluate(f"{win}.__draftDeleteConfirmation='';{win}.confirm=message=>{{{win}.__draftDeleteConfirmation=message;return true}};{win}.renderAccounts()")
    await wait_for(f"Boolean({doc}.querySelector('[data-draft-delete=\"{delete_id}\"]'))")
    await click_button(f'[data-draft-delete="{delete_id}"]')
    await wait_for(f"!{doc}.querySelector('[data-draft-delete=\"{delete_id}\"]')")
    assert not delete_root.exists() and not (data / "bench/profiles" / name).exists()
    assert "未提交授权产物" in await evaluate(f"{win}.__draftDeleteConfirmation")
    assert not client.containers.list(all=True, filters={"label": ["vibebench.deployment=" + deployment, "vibebench.environment=" + delete_id]})
    with sqlite3.connect(bench_db) as connection:
        assert connection.execute("SELECT count(*) FROM account_environments WHERE environment_id=?", (delete_id,)).fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM accounts WHERE id=?", (account_id,)).fetchone()[0] == 1
    print("通过：页面完整删除草稿、专属容器/HOME/profile/DB，无正式账号误删")
    # 正式删除沿用原接口；恢复空账号基线，供外层离线导入验证继续使用。
    removed = browser.delete(base + f"/runtime/api/accounts/{account_id}", timeout=15)
    assert removed.status_code == 200
    with sqlite3.connect(bench_db) as connection:
        assert connection.execute("SELECT count(*) FROM accounts WHERE id=?", (account_id,)).fetchone()[0] == 0
        connection.execute("DELETE FROM account_environments WHERE environment_id=? AND account_id=?", (environment_id, account_id))
    container.reload()
    assert container.labels.get("vibebench.deployment") == deployment and container.labels.get("vibebench.environment") == environment_id
    container.stop(timeout=5)
    container.remove()
