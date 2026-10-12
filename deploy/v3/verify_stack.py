#!/usr/bin/env python3
"""用空数据库和随机部署验证整套管理桥；只删除本次测试资源。"""
import argparse
import asyncio
import hashlib
import json
import socket
import sqlite3
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import docker
import requests
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from manage import REPO


async def verify_websocket(base: str, cookie: str, ticket: str) -> None:
    """核对终端桥拒绝未授权连接，并转发有效票据对应的后端消息。

    :param base: 本地网关地址
    :param cookie: 合成管理会话
    :param ticket: 绑定指定终端路径的短期票据
    :return: None；契约不符时失败
    """
    uri = base.replace("http://", "ws://") + "/runtime/api/accounts/login/ws/abcdef123456"
    try:
        async with connect(uri, proxy=None):
            raise AssertionError("未鉴权终端被接受")
    except InvalidStatus as error:
        assert error.response.status_code == 401
    try:
        async with connect(uri, proxy=None, additional_headers={"Cookie": cookie}) as channel:
            await channel.recv()
            raise AssertionError("没有票据的终端被接受")
    except ConnectionClosed:
        pass
    async with connect(uri + "?ticket=" + ticket, proxy=None,
            additional_headers={"Cookie": cookie}, origin=base) as channel:
        payload = json.loads(await asyncio.wait_for(channel.recv(), timeout=5))
        assert payload == {"type": "error", "msg": "session not found"}
    print("通过：WS 会话/票据鉴权和管理端到调度器的消息桥")


def main() -> None:
    """启动并停止本地独立 v3，核对 HTTP/SSE/WS 与旧哨兵保护。

    :return: None；失败时非零退出
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    client = docker.from_env()
    deployment = "stack-verify-" + uuid.uuid4().hex[:10]
    filters = {"label": ["vibebench.product=v3", "vibebench.deployment=" + deployment]}
    with tempfile.TemporaryDirectory(prefix="v3-stack-verify-") as temporary:
        root = Path(temporary)
        data = root / "v3-data"
        legacy = root / "legacy-data"
        legacy.mkdir()
        sentinel_file = legacy / "legacy.sqlite"
        sentinel_file.write_bytes(b"synthetic legacy database unchanged")
        sentinel_hash = hashlib.sha256(sentinel_file.read_bytes()).digest()
        sentinel = client.containers.run(manifest["images"]["control"]["reference"],
            ["-c", "import time; time.sleep(600)"], entrypoint="python", detach=True,
            network_mode="none", labels={"vibebench.verification": deployment},
            volumes={str(legacy): {"bind": "/synthetic-legacy", "mode": "rw"}})
        sentinel.reload()
        sentinel_start = sentinel.attrs["State"]["StartedAt"]
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        values = {"V3_DEPLOYMENT_ID": deployment, "V3_DATA_ROOT": str(data),
            "V3_HOST_PORT": str(port), "V3_BIND_ADDRESS": "127.0.0.1",
            "V3_CONTROL_IMAGE": manifest["images"]["control"]["reference"],
            "V3_ACCOUNT_IMAGE": manifest["images"]["account"]["reference"],
            "V3_RELEASE_MANIFEST": str(args.manifest.resolve()),
            "V3_ADMIN_PASSWORD": uuid.uuid4().hex + uuid.uuid4().hex,
            "V3_INTERNAL_TOKEN": uuid.uuid4().hex + uuid.uuid4().hex,
            "V3_SESSION_SECRET": uuid.uuid4().hex + uuid.uuid4().hex}
        configuration = root / "v3.env"
        configuration.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
        configuration.chmod(0o600)
        manager = ["python3", str(REPO / "deploy/v3/manage.py")]
        try:
            for action in ("check", "up"):
                subprocess.run(manager + [action, "--env", str(configuration)], check=True, cwd=REPO)
            base = f"http://127.0.0.1:{port}"
            browser = requests.Session()
            browser.trust_env = False
            authorization = {"Authorization": "Bearer " + values["V3_ADMIN_PASSWORD"]}
            deadline = time.monotonic() + 60
            while True:
                response = browser.post(base + "/admin/runtime/session", headers=authorization, timeout=5)
                if response.status_code == 200:
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("调度器未就绪")
                time.sleep(0.5)
            assert "HttpOnly" in response.headers["Set-Cookie"]
            assert "Path=/runtime" in response.headers["Set-Cookie"]
            assert requests.get(base + "/runtime/api/environments", timeout=5).status_code == 401
            assert browser.get(base + "/runtime/api/environments", headers={"Origin": "http://untrusted.invalid"}, timeout=5).status_code == 401
            assert browser.get(base + "/runtime/api/auth/me", timeout=5).json()["authenticated"]
            assert browser.get(base + "/runtime/api/environments", timeout=5).status_code == 200
            assert browser.get(base + "/runtime/api/topics", timeout=5).status_code == 200
            for path in ("/runtime/", "/runtime/app.js", "/runtime/vendor/xterm.js", "/environments"):
                assert browser.get(base + path, timeout=5).status_code == 200, path
            assert browser.post(base + "/runtime/api/auth/login", json={"user": "v3", "pwd": "synthetic"}, timeout=5).status_code == 404
            for path in ("/runtime/internal/v3/session/verify", "/runtime/internal/v3/transport/1", "/runtime/api/%252e%252e/internal/v3/session"):
                assert browser.get(base + path, timeout=5).status_code == 404
            assert browser.post(base + "/runtime/internal/v3/session", timeout=5).status_code == 404
            assert browser.get(base + "/runtime/api/runs/nonexistent/transcript", timeout=5).status_code == 404
            with browser.get(base + "/runtime/api/runs-stream", stream=True, timeout=5) as stream:
                assert stream.status_code == 200
                assert next(stream.iter_lines(chunk_size=1)) == b"event: runs"
            print("通过：整套 Compose 启动、统一会话、静态资源、API 和 SSE 桥")
            cookie = "; ".join(f"{item.name}={item.value}" for item in browser.cookies)
            ticket = browser.post(base + "/runtime/api/terminal-ticket",
                json={"path": "/api/accounts/login/ws/abcdef123456"}, timeout=5).json()["ticket"]
            asyncio.run(verify_websocket(base, cookie, ticket))
            if args.browser:
                from verify_browser import verify_visible_logout
                asyncio.run(verify_visible_logout(base, values["V3_ADMIN_PASSWORD"]))
            assert browser.post(base + "/runtime/logout", headers=authorization, timeout=5).status_code == 200
            assert browser.get(base + "/runtime/api/environments", timeout=5).status_code == 401
            assert requests.get(base + "/runtime/api/environments", headers={"Cookie": cookie}, timeout=5).status_code == 401
            assert requests.post(base + "/runtime/api/terminal-ticket", headers={"Cookie": cookie},
                json={"path": "/api/accounts/login/ws/abcdef123456"}, timeout=5).status_code == 401
            subprocess.run(manager + ["status", "--env", str(configuration)], check=True, cwd=REPO)
            subprocess.run(manager + ["stop", "--env", str(configuration)], check=True, cwd=REPO)
            offline = manager + ["import-offline", "--env", str(configuration), "--source", str(REPO / "deploy/v3/fixtures/offline_metadata.json")]
            subprocess.run(offline, check=True, cwd=REPO)
            subprocess.run(offline + ["--apply"], check=True, cwd=REPO)
            subprocess.run(offline + ["--apply"], check=True, cwd=REPO)
            with sqlite3.connect(data / "bench/db.sqlite") as database:
                assert database.execute("SELECT enabled,warmup_enabled,cc2api_account_id FROM accounts").fetchone() == (0, 0, None)
            owned = client.containers.list(all=True, filters=filters)
            assert len(owned) == 2 and all(item.status != "running" for item in owned)
            assert (data / "gateway/gateway.sqlite").exists()
            subprocess.run(manager + ["backup", "--env", str(configuration),
                "--backup-dir", str(root / "v3-backup")], check=True, cwd=REPO)
            assert (root / "v3-backup/data/bench/db.sqlite").exists()
            sentinel.reload()
            assert sentinel.status == "running" and sentinel.attrs["State"]["StartedAt"] == sentinel_start
            assert hashlib.sha256(sentinel_file.read_bytes()).digest() == sentinel_hash
            print("通过：stop 保留 v3 数据；旧哨兵容器、进程和数据库内容不变")
        except Exception:
            for container in client.containers.list(all=True, filters=filters):
                print(container.logs(tail=30).decode(), flush=True)
            raise
        finally:
            for container in client.containers.list(all=True, filters=filters):
                container.remove(force=True)
            for network in client.networks.list(filters=filters):
                network.remove()
            sentinel.remove(force=True)


if __name__ == "__main__":
    main()
