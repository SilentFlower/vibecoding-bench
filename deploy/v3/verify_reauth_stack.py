"""隔离部署的关联重授权演练；合成 CLI/代理不访问真实 OAuth 或模型。"""

import base64
import json
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from manage import REPO


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
        response = browser.post(base + "/admin/accounts", headers=authorization, timeout=10,
            json={"name": name, "email": "synthetic@example.invalid", "auth_type": "oauth",
                  "access_token": "old-access", "refresh_token": "old-refresh", "expires_at": int(time.time()) + 3600,
                  "account_uuid": "synthetic-account", "organization_uuid": "synthetic-org",
                  "proxy_url": f"socks5h://{address}:1080", "auto_poll_usage": False, "auto_telemetry": False})
        assert response.status_code == 201, response.status_code
        gateway_id = response.json()["id"]
        device_id = response.json()["device_id"]
        assert browser.get(base + f"/admin/accounts/{gateway_id}/oauth-credentials/import/" + "a" * 32,
                           headers=authorization, timeout=5).status_code == 401, "管理密码不能代替内部凭据导入证明"
        with sqlite3.connect(gateway_db) as database:
            database.execute("UPDATE accounts SET status='disabled',auth_error=?,disable_reason=?,rate_limited_at=?,rate_limit_reset_at=? WHERE id=?",
                             ("401 OAuth 认证恢复失败", "401 OAuth 认证恢复失败", "2026-01-01T00:00:00Z", "2099-01-01T00:00:00Z", gateway_id))
        with sqlite3.connect(bench_db) as database:
            cursor = database.execute("INSERT INTO accounts(name,profile_path,timezone,cc2api_account_id,enabled,warmup_enabled,warmup_quota_5h_limit_percent) VALUES(?,?,?,?,0,0,30)",
                                      (name, "profiles/" + name, "Asia/Tokyo", gateway_id))
            account_id = cursor.lastrowid
        orchestrator = client.containers.list(filters={"label": ["vibebench.deployment=" + deployment, "vibebench.role=orchestrator"]})[0]
        # 使用真实模型/迁移创建环境行，避免演练脚本复制固定环境的数据结构。
        code = "import main,docker;from account_runtime import AccountRuntime;" \
            "r=AccountRuntime(docker.from_env(),main.BENCH_DATA,main.HOST_BENCH_DATA,main.get_db,main.derive_fingerprint,main.cc2api_client);" \
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
        top = {"userID": device_id, "preserved": True, "oauthAccount": {"emailAddress": "synthetic@example.invalid",
               "accountUuid": "synthetic-account", "organizationUuid": "synthetic-org"}}
        credentials = {"claudeAiOauth": {"accessToken": "old-access", "refreshToken": "old-refresh", "expiresAt": int(time.time() * 1000) + 3600000}}
        (profile / ".credentials.json").write_text(json.dumps(credentials))
        (profile / ".claude.json").write_text(json.dumps(top))
        (home / ".claude.json").write_text(json.dumps(top))
        binary = environment_root / "cli/9.9.9/node_modules/.bin/claude"
        binary.parent.mkdir(parents=True)
        shutil.copy2(REPO / "deploy/v3/fixtures/mock_cli.py", binary)
        binary.chmod(0o755)
        (environment_root / "cli/9.9.9/.ready").touch()
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
            await wait_for(f"Boolean({state}?.sid && {state}?.connection && {state}?.authorizationURL)")
            sid = await evaluate(f"{state}.sid")
            url = await evaluate(f"{doc}.querySelector('#acc-auth-url').value")
            assert url.startswith("https://claude.ai/oauth/authorize?")
            await evaluate(f"{win}.open=(...args)=>{{{win}.__syntheticOpened=args;return null}};{doc}.querySelector('#acc-login-open').click()")
            assert await evaluate(f"{win}.__syntheticOpened") == [url, "_blank", "noopener,noreferrer"]
            container = client.containers.list(filters={"label": ["vibebench.deployment=" + deployment, "vibebench.environment=" + environment_id]})[0]
            original_container = container.id
            pane = container.exec_run(["tmux", "-S", f"/tmp/v3-login-{sid}.sock", "list-sessions"])
            assert pane.exit_code == 0
            lease = browser.get(base + f"/admin/runtime/accounts/{gateway_id}/lease", headers=authorization, timeout=5).json()
            assert lease["lease"]["exclusive"] and lease["lease"]["owner"] == "login:" + sid
            # 真正断开当前 WebSocket，检查自动重连取得新票据而 SID/tmux 保持。
            old_ticket_url = await evaluate(f"{state}.ws.url")
            await evaluate(f"{state}.ws.close();{state}.term.paste('not-replay-code\\r')")
            await wait_for(f"{state}?.ws?.readyState === 1 && {state}.ws.url !== " + json.dumps(old_ticket_url))
            assert await evaluate(f"{state}.sid") == sid
            assert await evaluate(f"{doc}.querySelector('#acc-auth-url').value") == url
            pane = container.exec_run(["tmux", "-S", f"/tmp/v3-login-{sid}.sock", "capture-pane", "-p", "-J"])
            assert "合成授权码不匹配" not in pane.output.decode(), "离线输入被重放"
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
            # 输入通过当前真实 WS 到原 tmux；没有调用替身的文件写入接口。
            await evaluate(f"{state}.ws.send(JSON.stringify({{type:'input',data:'synthetic-code\\r'}}))")
            await wait_for(f"{doc}.querySelector('#acc-login-link-status').textContent.includes('可以提交保存')")
            await evaluate(f"{doc}.querySelector('#acc-login-commit').scrollIntoView({{block:'center'}})")
            point = await evaluate(f"(() => {{const f=document.querySelector('iframe').getBoundingClientRect(),b={doc}.querySelector('#acc-login-commit').getBoundingClientRect();return {{x:f.left+b.left+b.width/2,y:f.top+b.top+b.height/2}};}})()")
            await rpc("Input.dispatchMouseEvent", {"type": "mousePressed", **point, "button": "left", "clickCount": 1}, session_id)
            await rpc("Input.dispatchMouseEvent", {"type": "mouseReleased", **point, "button": "left", "clickCount": 1}, session_id)
            await wait_for(f"{doc}.querySelector('#acc-modal').classList.contains('hidden')")
            assert await evaluate(f"{state} === null")
            with sqlite3.connect(gateway_db) as database:
                row = database.execute("SELECT access_token,refresh_token,status,auth_error,disable_reason,rate_limit_reset_at,device_id FROM accounts WHERE id=?", (gateway_id,)).fetchone()
                assert row == ("new-access", "new-refresh", "active", "", "", "2099-01-01T00:00:00Z", device_id), "网关同步或策略保留失败"
                assert database.execute("SELECT count(*) FROM oauth_credential_imports WHERE account_id=?", (gateway_id,)).fetchone()[0] == 1
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
