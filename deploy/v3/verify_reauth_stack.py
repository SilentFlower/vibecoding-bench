"""隔离部署的关联重授权演练；合成 CLI/代理不访问真实 OAuth 或模型。"""

import base64
import asyncio
import json
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from manage import REPO
from verify_browser import ACCOUNT_STARTUP_TIMEOUT
from verify_login_drafts import verify_login_drafts


@contextmanager
def reauth_fixture(client, deployment, data, manifest, browser, base, authorization):
    """准备专用账号并提供真实浏览器场景，最终只清理本次资源。

    :param client: 本地 Docker 客户端
    :param deployment: 本次随机部署标识
    :param data: 本次空数据目录
    :param manifest: 本地联合镜像清单
    :param browser: 本次已鉴权 HTTP 客户端
    :param base: 本地网关地址
    :param authorization: 本次管理鉴权请求头
    :return: 浏览器场景回调
    """
    name = "reauth-ui-fixture"
    bench_db = data / "bench/db.sqlite"
    gateway_db = data / "gateway/gateway.sqlite"
    fixture_data = data / "synthetic-network"
    fixture_data.mkdir()
    labels = {"vibebench.product": "v3", "vibebench.deployment": deployment, "vibebench.role": "verification"}
    proxy = client.containers.run(manifest["images"]["control"]["reference"],
        ["/fixtures/mock_network.py"], entrypoint="python", detach=True,
        network="vibebench-v3-" + deployment, labels=labels,
        volumes={str(REPO / "deploy/v3/fixtures"): {"bind": "/fixtures", "mode": "ro"},
                 str(fixture_data): {"bind": "/fixtures-data", "mode": "rw"}})
    account_id = None
    environment_id = None
    try:
        proxy.reload()
        address = next(iter(proxy.attrs["NetworkSettings"]["Networks"].values()))["IPAddress"]
        with sqlite3.connect(bench_db) as database:
            cursor = database.execute("INSERT INTO accounts(name,profile_path,timezone,upstream_proxy_scheme,upstream_socks5_host,upstream_socks5_port,enabled,warmup_enabled,warmup_quota_5h_limit_percent) VALUES(?,?,?,?,?,?,1,0,30)",
                                      (name, "profiles/" + name, "Asia/Tokyo", "socks5h", address, 1080))
            account_id = cursor.lastrowid
        orchestrator = client.containers.list(filters={"label": ["vibebench.deployment=" + deployment, "vibebench.role=orchestrator"]})[0]
        # 使用真实模型/迁移创建环境行，避免演练脚本复制固定环境的数据结构。
        code = "import main,docker;from account_runtime import AccountRuntime;" \
            "r=AccountRuntime(docker.from_env(),main.BENCH_DATA,main.HOST_BENCH_DATA,main.get_db,main.derive_v3_fingerprint,main.cc2api_client);" \
            f"print(r._row({name!r},{account_id})['environment_id']);r.heartbeat_pool.shutdown()"
        result = orchestrator.exec_run(["python", "-c", code])
        assert result.exit_code == 0, "合成环境行创建失败"
        environment_id = result.output.decode().strip().splitlines()[-1]
        assert len(environment_id) == 32
        environment_root = data / "bench/environments" / environment_id
        home = environment_root / "home"
        profile = data / "bench/profiles" / name
        profile.mkdir(parents=True)
        home.mkdir(parents=True)
        device_id = "d" * 64
        top = {"userID": device_id, "preserved": True, "oauthAccount": {"emailAddress": "synthetic@example.invalid",
               "accountUuid": "synthetic-account", "organizationUuid": "synthetic-org"}}
        credentials = {"claudeAiOauth": {"accessToken": "old-access", "refreshToken": "old-refresh", "expiresAt": int(time.time() * 1000) + 3600000}}
        (profile / ".credentials.json").write_text(json.dumps(credentials))
        (profile / ".claude.json").write_text(json.dumps(top))
        (home / ".claude.json").write_text(json.dumps(top))
        for version in ("2.1.293", "9.9.9"):
            binary = environment_root / f"cli/{version}/node_modules/.bin/claude"
            binary.parent.mkdir(parents=True)
            shutil.copy2(REPO / "deploy/v3/fixtures/mock_cli.py", binary)
            binary.chmod(0o755)
            (environment_root / f"cli/{version}/.ready").touch()
        # 此处只验证同步产品链；官方二进制与字段映射另由禁网的 verify_cli_quota 验证。
        with sqlite3.connect(bench_db) as database:
            database.execute("INSERT INTO app_settings(key,value) VALUES('claude_code_version','2.1.293') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        response = browser.post(base + f"/runtime/api/accounts/{account_id}/cc2api/sync", timeout=90)
        assert response.status_code == 200, response.status_code
        assert response.json()["created"]
        gateway_id = response.json()["cc2api_account"]["id"]
        with sqlite3.connect(gateway_db) as database:
            assert database.execute("SELECT device_id FROM accounts WHERE id=?", (gateway_id,)).fetchone() == (device_id,)
            policy_before = database.execute("SELECT billing_mode,upstream_session_pool_enabled,upstream_session_pool_size,upstream_session_refresh_policy,concurrency,rpm_limit,upstream_session_ttl_minutes FROM accounts WHERE id=?", (gateway_id,)).fetchone()
            assert policy_before == ('rewrite', 1, 4, 'owner_only', 4, 50, 60)
            database.execute("UPDATE accounts SET status='disabled',auth_error=?,disable_reason=?,rate_limited_at=?,rate_limit_reset_at=? WHERE id=?",
                             ("401 OAuth 认证恢复失败", "401 OAuth 认证恢复失败", "2026-01-01T00:00:00Z", "2099-01-01T00:00:00Z", gateway_id))
        with sqlite3.connect(bench_db) as database:
            assert database.execute("SELECT count(*) FROM runs WHERE account_id=?", (account_id,)).fetchone()[0] == 0
            database.execute("DELETE FROM app_settings WHERE key='claude_code_version'")
            database.execute("UPDATE accounts SET enabled=0 WHERE id=?", (account_id,))
        assert not (environment_root / "runtime/identity.json").exists()
        assert browser.get(base + f"/admin/accounts/{gateway_id}/oauth-credentials/import/" + "a" * 32,
                           headers=authorization, timeout=5).status_code == 401, "管理密码不能代替内部凭据导入证明"
        print("通过：未跑任务、无抓包身份文件的固定账号经正式同步 API 创建并绑定，网关保存原 userID；未调用真实模型或额度")
        control = {"wait_for_code": True, "access_token": "new-access", "refresh_token": "new-refresh",
                   "email": "synthetic@example.invalid", "account_uuid": "synthetic-account", "organization_uuid": "synthetic-org"}
        (home / ".synthetic-login.json").write_text(json.dumps(control))

        async def exercise(rpc, evaluate, wait_for, session_id):
            """操作真实登录窗，核对 tmux、HTTP、凭据文件与两侧数据库。

            :param rpc: CDP 命令调用
            :param evaluate: 页面脚本执行
            :param wait_for: 有界页面等待
            :param session_id: 私有浏览器会话
            :return: None；不符合期望时抛错
            """
            doc = "document.querySelector('iframe').contentDocument"
            win = "document.querySelector('iframe').contentWindow"
            state = win + ".eval('state.accLogin')"
            assert not await evaluate(f"{win}.isSecureContext"), "复制降级必须在真实 HTTP 非安全上下文验证"
            await wait_for(f"Boolean({doc}?.querySelector('[data-relogin=\"{account_id}\"]'))")
            await evaluate(f"{doc}.querySelector('[data-relogin=\"{account_id}\"]').click()")
            assert await evaluate(f"{doc}.querySelector('#acc-form').elements.timezone.disabled")
            await evaluate(f"{doc}.querySelector('#acc-form').requestSubmit()")
            await wait_for(f"Boolean({state}?.sid && {state}?.connection && {state}?.authorizationURL)", timeout=ACCOUNT_STARTUP_TIMEOUT)
            sid = await evaluate(f"{state}.sid")
            url = await evaluate(f"{doc}.querySelector('#acc-auth-url').value")
            assert url.startswith("https://claude.ai/oauth/authorize?")
            await evaluate(f"{win}.open=(...args)=>{{{win}.__syntheticOpened=args;return null}};{doc}.querySelector('#acc-login-open').click()")
            assert await evaluate(f"{win}.__syntheticOpened") == [url, "_blank", "noopener,noreferrer"]
            container = client.containers.list(filters={"label": ["vibebench.deployment=" + deployment,
                "vibebench.environment=" + environment_id, "vibebench.role=account"]})[0]
            original_container = container.id
            pane = container.exec_run(["tmux", "-S", f"/tmp/v3-login-{sid}.sock", "list-sessions"])
            assert pane.exit_code == 0
            lease = browser.get(base + f"/admin/runtime/accounts/{gateway_id}/lease", headers=authorization, timeout=5).json()
            assert lease["lease"]["exclusive"] and lease["lease"]["owner"] == "login:" + sid
            # 真正断开当前 WebSocket，检查自动重连取得新票据而 SID/tmux 保持。
            old_ticket_url = await evaluate(f"{state}.ws.url")
            await evaluate(f"{doc}.querySelector('#acc-login-xterm').scrollIntoView({{block:'center'}})")
            await evaluate(f"{state}.term.focus()")
            assert await evaluate(f"{doc}.activeElement.classList.contains('xterm-helper-textarea')"), "登录终端没有取得键盘焦点"
            await rpc("Input.dispatchKeyEvent", {"type": "keyDown", "key": "x", "code": "KeyX", "text": "x", "windowsVirtualKeyCode": 88}, session_id)
            await rpc("Input.dispatchKeyEvent", {"type": "keyUp", "key": "x", "code": "KeyX", "windowsVirtualKeyCode": 88}, session_id)
            await rpc("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "text": "\r", "windowsVirtualKeyCode": 13}, session_id)
            await rpc("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, session_id)
            for _ in range(50):
                if (home / ".synthetic-code-count.json").exists() and json.loads((home / ".synthetic-code-count.json").read_text())["count"] == 1:
                    break
                await asyncio.sleep(0.1)
            else:
                raise AssertionError("终端键盘输入没有进入原 CLI")
            await evaluate(f"{state}.ws.close();{state}.term.paste('not-replay-code\\r')")
            await wait_for(f"{state}?.ws?.readyState === 1 && {state}.ws.url !== " + json.dumps(old_ticket_url))
            assert await evaluate(f"{state}.sid") == sid
            assert await evaluate(f"{doc}.querySelector('#acc-auth-url').value") == url
            assert json.loads((home / ".synthetic-code-count.json").read_text())["count"] == 1, "离线输入被重放"
            await evaluate(f"{doc}.querySelector('#acc-login-reconnect').click()")
            await wait_for(f"{state}.ws.readyState === 1")
            # 禁用 secure clipboard 与 execCommand，验证真实 HTTP 降级能选择完整文本。
            await evaluate(f"Object.defineProperty({win}.navigator,'clipboard',{{value:undefined,configurable:true}});{doc}.execCommand=()=>false")
            await evaluate(f"{doc}.querySelector('#acc-login-copy').click()")
            await wait_for(f"{doc}.querySelector('#acc-login-link-status').textContent.includes('链接已选中')")
            assert await evaluate(f"{doc}.querySelector('#acc-auth-url').selectionEnd") == len(url)
            for width in (1280, 390):
                await rpc("Emulation.setDeviceMetricsOverride", {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": False}, session_id)
                for theme in ("dark", "light"):
                    await evaluate(f"if({doc}.documentElement.dataset.theme !== '{theme}') {doc}.querySelector('#theme-toggle').click()")
                    await evaluate("new Promise(resolve=>setTimeout(resolve,250))")
                    bounds = await evaluate(f"(() => {{const d={doc},r=d.querySelector('#acc-modal .modal-card').getBoundingClientRect();return {{left:r.left,right:r.right,width:d.defaultView.innerWidth}};}})()")
                    assert bounds["left"] >= -1 and bounds["right"] <= bounds["width"] + 1
                    screenshot = await rpc("Page.captureScreenshot", {"format": "png"}, session_id)
                    Path(f"/tmp/v3-reauth-{width}-{theme}.png").write_bytes(base64.b64decode(screenshot["data"]))
                    await evaluate(f"{doc}.querySelector('#acc-login-commit').scrollIntoView({{block:'center'}})")
                    assert await evaluate(f"(() => {{const d={doc},b=d.querySelector('#acc-login-commit'),r=b.getBoundingClientRect();return r.top>=0 && r.bottom<=d.defaultView.innerHeight && d.elementFromPoint(r.left+r.width/2,r.top+r.height/2)===b;}})()"), "提交按钮被登录卡片裁切"
                    screenshot = await rpc("Page.captureScreenshot", {"format": "png"}, session_id)
                    Path(f"/tmp/v3-reauth-{width}-{theme}-actions.png").write_bytes(base64.b64decode(screenshot["data"]))
                    await evaluate(f"{doc}.querySelector('.acc-step-terminal').scrollTop=0")
            # 复制链接会把焦点留在只读文本框；用真实输入框、键盘和 Ctrl+V 覆盖投递链。
            await rpc("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False}, session_id)
            await evaluate(f"{doc}.querySelector('#acc-login-xterm').scrollIntoView({{block:'center'}})")
            for offset in (1, 5):
                await evaluate(f"{doc}.querySelector('#acc-auth-url').focus()")
                point = await evaluate(f"(() => {{const f=document.querySelector('iframe').getBoundingClientRect(),r={doc}.querySelector('#acc-login-xterm').getBoundingClientRect();return {{x:f.left+r.left+{offset},y:f.top+r.top+20}};}})()")
                await rpc("Input.dispatchMouseEvent", {"type": "mousePressed", **point, "button": "left", "clickCount": 1}, session_id)
                await rpc("Input.dispatchMouseEvent", {"type": "mouseReleased", **point, "button": "left", "clickCount": 1}, session_id)
                assert await evaluate(f"{doc}.activeElement.classList.contains('xterm-helper-textarea')"), "点击终端边缘后没有获得输入焦点"
            await evaluate(f"{doc}.querySelector('#acc-auth-code').scrollIntoView({{block:'center'}})")
            point = await evaluate(f"(() => {{const f=document.querySelector('iframe').getBoundingClientRect(),r={doc}.querySelector('#acc-auth-code').getBoundingClientRect();return {{x:f.left+r.left+r.width/2,y:f.top+r.top+r.height/2}};}})()")
            await rpc("Input.dispatchMouseEvent", {"type": "mousePressed", **point, "button": "left", "clickCount": 1}, session_id)
            await rpc("Input.dispatchMouseEvent", {"type": "mouseReleased", **point, "button": "left", "clickCount": 1}, session_id)
            assert await evaluate(f"{doc}.activeElement.id") == 'acc-auth-code'
            await rpc("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "text": "a", "windowsVirtualKeyCode": 65}, session_id)
            await rpc("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65}, session_id)
            assert await evaluate(f"{doc}.querySelector('#acc-code-length').textContent") == '已输入 1 个字符'
            await rpc("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8}, session_id)
            await rpc("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8}, session_id)
            # 模拟回包丢失：HTTP 实际投递了无效合成码，页面必须查询原回执而不能补发。
            await evaluate(f"{win}.__originalCodeFetch={win}.fetch;{win}.fetch=async(...args)=>{{const r=await {win}.__originalCodeFetch(...args);if(String(args[0]).endsWith('/code'))throw new Error('synthetic response lost');return r;}}")
            await rpc("Input.insertText", {"text": "synthetic-wrong"}, session_id)
            await evaluate(f"{doc}.querySelector('#acc-code-send').scrollIntoView({{block:'center'}})")
            point = await evaluate(f"(() => {{const f=document.querySelector('iframe').getBoundingClientRect(),r={doc}.querySelector('#acc-code-send').getBoundingClientRect();return {{x:f.left+r.left+r.width/2,y:f.top+r.top+r.height/2}};}})()")
            await rpc("Input.dispatchMouseEvent", {"type": "mousePressed", **point, "button": "left", "clickCount": 1}, session_id)
            await rpc("Input.dispatchMouseEvent", {"type": "mouseReleased", **point, "button": "left", "clickCount": 1}, session_id)
            await wait_for(f"{state}.codeStatus === 'uncertain'")
            assert await evaluate(f"{doc}.querySelector('#acc-auth-code').value") == ''
            assert await evaluate(f"{doc}.querySelector('#acc-code-send').disabled")
            await evaluate(f"{win}.fetch={win}.__originalCodeFetch;{doc}.querySelector('#acc-code-query').click()")
            await wait_for(f"{state}.codeStatus === 'delivered' && !{state}.codeSending")
            request_id = await evaluate(f"{state}.codeRequestId")
            duplicate = browser.post(base + f"/runtime/api/accounts/login/{sid}/code", json={"request_id": request_id, "code": "synthetic-wrong"}, timeout=10)
            assert duplicate.json()["status"] == "delivered"
            assert json.loads((home / ".synthetic-code-count.json").read_text())["count"] == 2
            # 恢复浏览器原生剪贴板，真实 Ctrl+V 触发输入事件；右键原生菜单另列未自动驱动项。
            await evaluate(f"delete {win}.navigator.clipboard")
            await rpc("Browser.grantPermissions", {"origin": base, "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"]})
            # 真 HTTP 页面没有 Clipboard API；独立回环安全页只写系统剪贴板，原页面仍保持非安全上下文。
            clipboard_target = await rpc("Target.createTarget", {"url": base + "/login"})
            clipboard_attached = await rpc("Target.attachToTarget", {"targetId": clipboard_target["targetId"], "flatten": True})
            try:
                await asyncio.sleep(0.5)
                copied = await rpc("Runtime.evaluate", {"expression": "navigator.clipboard.writeText('synthetic-code').then(()=>true)", "awaitPromise": True, "returnByValue": True}, clipboard_attached["sessionId"])
                assert "exceptionDetails" not in copied and copied["result"].get("value") is True
            finally:
                await rpc("Target.closeTarget", {"targetId": clipboard_target["targetId"]})
            await evaluate(f"{doc}.querySelector('#acc-auth-code').focus()")
            await rpc("Input.dispatchKeyEvent", {"type": "keyDown", "key": "v", "code": "KeyV", "modifiers": 2, "windowsVirtualKeyCode": 86}, session_id)
            await rpc("Input.dispatchKeyEvent", {"type": "keyUp", "key": "v", "code": "KeyV", "modifiers": 2, "windowsVirtualKeyCode": 86}, session_id)
            await wait_for(f"{doc}.querySelector('#acc-auth-code').value === 'synthetic-code'")
            assert await evaluate(f"{doc}.querySelector('#acc-code-length').textContent") == '已输入 14 个字符'
            await evaluate(f"{doc}.querySelector('#acc-code-toggle').click()")
            assert await evaluate(f"{doc}.querySelector('#acc-auth-code').type") == 'text'
            await evaluate(f"{doc}.querySelector('#acc-code-toggle').click();{doc}.querySelector('#acc-auth-code').focus();{state}.ws.close()")
            assert await evaluate(f"{state}.ws.readyState") != 1
            await rpc("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "text": "\r", "windowsVirtualKeyCode": 13}, session_id)
            await rpc("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, session_id)
            await wait_for(f"{state}.codeStatus === 'delivered'")
            assert await evaluate(f"{doc}.querySelector('#acc-auth-code').value") == ''
            assert json.loads((home / ".synthetic-code-count.json").read_text())["count"] == 3
            print("通过：终端真实键盘交互、授权码输入框原生 Ctrl+V、隐藏/长度、按钮/Enter、丢回包查询与同标识单次投递、WS 断线独立发送；右键系统菜单未自动驱动")
            try:
                await wait_for(f"{doc}.querySelector('#acc-login-link-status').textContent.includes('可以提交保存')")
            except TimeoutError:
                status = browser.get(base + f"/runtime/api/accounts/login/{sid}/status", timeout=5)
                print("关联状态诊断：", status.status_code, {key: value for key, value in status.json().items() if key != "authorization_url"}, flush=True)
                print("页面状态诊断：", await evaluate(f"{doc}.querySelector('#acc-login-link-status').textContent"), flush=True)
                raise
            await evaluate(f"{doc}.querySelector('#acc-login-commit').scrollIntoView({{block:'center'}})")
            point = await evaluate(f"(() => {{const f=document.querySelector('iframe').getBoundingClientRect(),b={doc}.querySelector('#acc-login-commit').getBoundingClientRect();return {{x:f.left+b.left+b.width/2,y:f.top+b.top+b.height/2}};}})()")
            await rpc("Input.dispatchMouseEvent", {"type": "mousePressed", **point, "button": "left", "clickCount": 1}, session_id)
            await rpc("Input.dispatchMouseEvent", {"type": "mouseReleased", **point, "button": "left", "clickCount": 1}, session_id)
            await wait_for(f"{doc}.querySelector('#acc-modal').classList.contains('hidden')")
            assert await evaluate(f"{state} === null")
            await wait_for(f"{doc}.querySelector('#account-login-result').textContent.includes('已重授权并同步关联账号')")
            with sqlite3.connect(gateway_db) as database:
                row = database.execute("SELECT access_token,refresh_token,status,auth_error,disable_reason,rate_limit_reset_at,device_id FROM accounts WHERE id=?", (gateway_id,)).fetchone()
                assert row == ("new-access", "new-refresh", "active", "", "", "2099-01-01T00:00:00Z", device_id), "网关同步或策略保留失败"
                assert database.execute("SELECT count(*) FROM oauth_credential_imports WHERE account_id=?", (gateway_id,)).fetchone()[0] == 1
                assert database.execute("SELECT billing_mode,upstream_session_pool_enabled,upstream_session_pool_size,upstream_session_refresh_policy,concurrency,rpm_limit,upstream_session_ttl_minutes FROM accounts WHERE id=?", (gateway_id,)).fetchone() == policy_before
            with sqlite3.connect(bench_db) as database:
                assert database.execute("SELECT cc2api_account_id,enabled,warmup_enabled,warmup_quota_5h_limit_percent FROM accounts WHERE id=?", (account_id,)).fetchone() == (gateway_id, 0, 0, 30)
                assert database.execute("SELECT container_id FROM account_environments WHERE environment_id=?", (environment_id,)).fetchone()[0] == original_container
            assert json.loads((profile / ".credentials.json").read_text())["claudeAiOauth"]["refreshToken"] == "new-refresh"
            home_credentials = json.loads((home / ".claude/.credentials.json").read_text())["claudeAiOauth"]
            assert home_credentials["accessToken"] == "new-access" and "refreshToken" not in home_credentials
            assert json.loads((home / ".claude.json").read_text())["userID"] == device_id
            resolved = browser.post(base + f"/admin/accounts/{gateway_id}/oauth-credentials/resolve", headers=authorization,
                                    json={"min_validity_seconds": 600, "force_refresh": False}, timeout=10)
            assert resolved.status_code == 200
            assert (resolved.json()["access_token"], resolved.json()["refresh_token"]) == ("new-access", "new-refresh")
            assert not list((home / ".v3-login").glob("*/.claude/.credentials.json"))
            assert not (environment_root / "runtime/login-commit.json").exists()
            result = browser.post(base + f"/runtime/api/accounts/login/{sid}/commit", json={"name": name}, timeout=10)
            assert result.status_code == 200 and result.json()["credentials_synced"]
            assert browser.get(base + f"/admin/runtime/accounts/{gateway_id}/lease", headers=authorization, timeout=5).json()["lease"] is None
            print("通过：真实页面/WS/tmux 重授权、同 SID 自动和手动重连、新票据、复制降级、四种布局、原 ID 同步、AT-only HOME 与策略保留")

            # 在真实 start HTTP 尚未返回 SID 时关闭窗口，必须等取消收口再隐藏。
            await evaluate(f"{doc}.querySelector('[data-relogin=\"{account_id}\"]').click()")
            await evaluate(f"{doc}.querySelector('#acc-form').requestSubmit();{doc}.querySelector('#acc-modal-close').click()")
            assert await evaluate(f"Boolean({state}?.starting && {state}?.closeRequested)")
            await wait_for(f"{doc}.querySelector('#acc-modal').classList.contains('hidden')")
            assert await evaluate(f"{state} === null")
            assert browser.get(base + f"/admin/runtime/accounts/{gateway_id}/lease", headers=authorization, timeout=5).json()["lease"] is None
            assert not list((home / ".v3-login").glob("*/.claude/.credentials.json"))
            print("通过：启动响应返回前关闭窗口，取得 SID 后确认取消，无隐藏登录维护占用")

            # 通过正式 HTTP 再演练错登拒绝及取消，原凭据/回执数保持。
            control["account_uuid"] = "wrong-account"
            (home / ".synthetic-login.json").write_text(json.dumps(control))
            result = browser.post(base + "/runtime/api/accounts/login/start", json={"name": name, "force_reauth": True}, timeout=60)
            assert result.status_code == 200, result.status_code
            wrong_sid = result.json()["session_id"]
            container.exec_run(["tmux", "-S", f"/tmp/v3-login-{wrong_sid}.sock", "send-keys", "synthetic-code", "Enter"])
            deadline = time.monotonic() + 15
            while True:
                status = browser.get(base + f"/runtime/api/accounts/login/{wrong_sid}/status", timeout=5)
                if status.json().get("credentials_ready"):
                    break
                assert time.monotonic() < deadline
                await evaluate("new Promise(resolve=>setTimeout(resolve,100))")
            assert browser.post(base + f"/runtime/api/accounts/login/{wrong_sid}/commit", json={"name": name}, timeout=10).status_code == 409
            assert browser.delete(base + f"/runtime/api/accounts/login/{wrong_sid}", timeout=10).status_code == 200
            assert browser.get(base + f"/runtime/api/accounts/login/{wrong_sid}/status", timeout=5).status_code == 404
            with sqlite3.connect(gateway_db) as database:
                assert database.execute("SELECT access_token,refresh_token FROM accounts WHERE id=?", (gateway_id,)).fetchone() == ("new-access", "new-refresh")
                assert database.execute("SELECT count(*) FROM oauth_credential_imports WHERE account_id=?", (gateway_id,)).fetchone()[0] == 1
            print("通过：真实 Docker/HTTP 错登拒绝、取消后会话和暂存收口，原关联凭据保持")

            # 模拟输出组件缺失：授权码与认证轮询继续，不能启用不存在的重连方法。
            await evaluate(f"{win}.__codeVendor={{Terminal:{win}.Terminal,FitAddon:{win}.FitAddon}};{win}.Terminal=undefined;{win}.FitAddon=undefined")
            try:
                await evaluate(f"{doc}.querySelector('[data-relogin=\"{account_id}\"]').click();{doc}.querySelector('#acc-form').requestSubmit()")
                await wait_for(f"Boolean({state}?.sid)")
                await wait_for(f"Boolean({state}?.connection && {state}?.authorizationURL)")
                assert await evaluate(f"{doc}.querySelector('#acc-login-reconnect').disabled")
                assert not await evaluate(f"{doc}.querySelector('#acc-auth-code').disabled")
                await evaluate(f"{doc}.querySelector('#acc-auth-code').focus()")
                await rpc("Input.insertText", {"text": "synthetic-wrong"}, session_id)
                await rpc("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "text": "\r", "windowsVirtualKeyCode": 13}, session_id)
                await rpc("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, session_id)
                await wait_for(f"{state}.codeStatus === 'delivered' && !{state}.codeSending")
                await evaluate(f"{doc}.querySelector('#acc-login-cancel').click()")
                await wait_for(f"{state} === null")
                print("通过：输出组件加载失败时重连按钮禁用，原生输入、独立HTTP投递及取消仍正常")
            finally:
                await evaluate(f"{win}.Terminal={win}.__codeVendor.Terminal;{win}.FitAddon={win}.__codeVendor.FitAddon;delete {win}.__codeVendor")

            try:
                await verify_login_drafts(client, deployment, data, browser, base, address, rpc, evaluate, wait_for, session_id)
            except Exception:
                response = browser.get(base + '/runtime/api/accounts/login-drafts', timeout=10)
                print('草稿恢复诊断：', response.status_code, response.json(), flush=True)
                print('草稿页面诊断：', await evaluate(f"[Boolean({state}),{win}.__draftAlerts,{doc}.querySelector('#accounts-body').textContent,{doc}.querySelector('#acc-login-connection-status').textContent]"), flush=True)
                raise

        yield exercise
    finally:
        if environment_id:
            for container in client.containers.list(all=True, filters={"label": ["vibebench.deployment=" + deployment, "vibebench.environment=" + environment_id]}):
                container.remove(force=True)
        if account_id:
            with sqlite3.connect(bench_db) as database:
                database.execute("DELETE FROM account_environments WHERE account_id=?", (account_id,))
                database.execute("DELETE FROM accounts WHERE id=? AND name=?", (account_id, name))
        proxy.remove(force=True)
