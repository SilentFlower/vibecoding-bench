"""隔离账号镜像的测试代理及标题回执。只接通测试容器里的合成模型。"""

from hashlib import sha256
import hmac
import json
from pathlib import Path
from secrets import token_hex
from shutil import copyfile
from subprocess import run
from threading import Thread
from time import time_ns

from fixture_tunnel import HOST, connect_account_fixture


def is_title(body):
    """使用固定版运行时分类器核对真实标题请求。@param body 解码的 Messages。@return 是否为标题。"""
    # 普通主轮不必启动分类器；会话包装只是预筛选，最终以仓库完整的标题特征校验为准。
    rows = body.get("messages", [])
    if len(rows) != 1 or not isinstance(rows[0].get("content"), list):
        return False
    if not any(
        isinstance(b.get("text"), str) and b["text"].startswith("<session>\n")
        for b in rows[0]["content"]
        if isinstance(b, dict)
    ):
        return False
    js = (
        "const b=JSON.parse(require('node:fs').readFileSync(0));"
        "const c=require('/verify-native/native-classifier.ts').readNativeClassification(b);"
        "process.stdout.write(c?.purpose || 'unknown');"
    )
    answer = run(
        ["/usr/local/bin/node", "-e", js],
        input=json.dumps(body).encode(),
        check=True,
        capture_output=True,
        timeout=10,
    )
    return answer.stdout == b"session_title"


def semantic_digest(body):
    """得到可跨 HTTP 压缩和 JSON 编码比较的摘要。@param body 解码对象。@return SHA-256。"""
    return sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ManagedRoute:
    """绑定测试账号、唯一会话监听器和唯一合成模型。"""

    def __init__(self, fixture, owns_peer, record):
        """@param fixture 受信夹具目录。@param owns_peer 连接属主核对。@param record 脱敏观测写入器。@return 无。"""
        self.fixture = fixture
        self.config = json.loads((fixture / "managed-proxy.json").read_bytes())
        self.owns_peer = owns_peer
        self.record = record
        self.grants = {}
        self.token_hash = (fixture / "synthetic-at.sha256").read_text()
        configured = json.loads(Path("/run/v3/sender.json").read_bytes())["proxy_url"]
        if configured != f"http://127.0.0.1:{self.config['proxy_port']}":
            raise ValueError("测试代理必须与账号发送器配置一致")

    def _owns_request(self, actor, http):
        with actor.changed:
            token = actor.model_authorization()
            handle = actor.claim
            return (
                actor.oauth_file
                and token
                and actor.process
                and not actor.dead.is_set()
                and handle
                and handle.expires_at
                and handle.expires_at > time_ns() // 1_000_000
                and hmac.compare_digest(
                    sha256(token.encode()).hexdigest(), self.token_hash
                )
                and self.owns_peer(http.connection, actor.process.pid)
            )

    def install(self, session, callback):
        """安装仅回环容器的代理和回执入口。@param session 会话模块。@param callback 原测试回调。@return 无。"""
        route = self
        original = session._Actor.serve_model

        class AccountCallback(callback):
            """单会话测试账号接受固定模型目标，私有 Mod 回调沿用原入口。"""

            def do_CONNECT(self):
                """核对目标、当前凭据与进程后接通本机模型。@return 无。"""
                actor = self.server.actor
                if self.path != HOST + ":443" or not route._owns_request(actor, self):
                    return self.send_error(403)
                connect_account_fixture(
                    self,
                    route.config["proxy_port"],
                    lambda port: route.record(
                        account_peer_port=port,
                        cli_pid=actor.process.pid,
                        session_port=self.server.server_port,
                    ),
                )

            def do_POST(self):
                """区分标题用量回执与原有主轮回调。@return 无。"""
                if not self.path.startswith("/native-title/"):
                    return super().do_POST()
                actor = self.server.actor
                if (
                    self.headers.get("Authorization") != "Bearer " + actor.bearer
                    or not actor.process
                    or not route.owns_peer(self.connection, actor.process.pid)
                ):
                    return self.send_error(403)
                size = int(self.headers.get("Content-Length", "0"))
                # 回执只有消息 ID 和两个 token 计数，沿用既有控制帧的上限。
                from tui_source_impl import CONTROL_LIMIT

                if not 0 < size <= CONTROL_LIMIT:
                    return self.send_error(400)
                data = json.loads(self.rfile.read(size))
                if (
                    set(data) != {"message_id", "input_tokens", "output_tokens"}
                    or not isinstance(data["message_id"], str)
                    or any(
                        type(data[k]) is not int or data[k] < 0
                        for k in ("input_tokens", "output_tokens")
                    )
                ):
                    return self.send_error(400)
                key = self.path.removeprefix("/native-title/")
                with actor.changed:
                    if route.grants.get(key) != actor.process.pid:
                        return self.send_error(409)
                    del route.grants[key]
                route.record(title_receipt=key, cli_pid=actor.process.pid, **data)
                self.send_response(204)
                self.end_headers()

        def dispatch(actor, http, body):
            if not is_title(body):
                return original(actor, http, body)
            if not route._owns_request(actor, http):
                return http.send_error(403)
            key = token_hex(16)
            with actor.changed:
                route.grants[key] = actor.process.pid
            route.record(
                title_grant=key,
                semantic_sha256=semantic_digest(body),
                cli_pid=actor.process.pid,
            )
            raw = json.dumps(
                {
                    "id": key,
                    "kind": "session_title",
                    "proxy": f"http://127.0.0.1:{actor.port}",
                }
            ).encode()
            http.send_response(200)
            http.send_header("Content-Type", "application/vnd.flower.native-lab+json")
            http.send_header("Content-Length", str(len(raw)))
            http.end_headers()
            http.wfile.write(raw)

        session._Callback = AccountCallback
        session._Actor.serve_model = dispatch

    def prepare_main(self, trial, grant):
        """将已认领主轮交给账号代理，之后独立比对回复。@param trial 主轮。@param grant 交付数据。@return 无。"""
        digest = sha256(trial.submission.body).hexdigest()
        trial.independent_model = True
        trial.used = True
        grant.update(kind="main", proxy=f"http://127.0.0.1:{trial.actor.port}")
        self.record(
            main_grant=trial.id,
            attempt_id=trial.submission.handle.reservation["reservation_id"],
            sha256=digest,
            cli_pid=trial.actor.process.pid,
            private_port=trial.actor.port,
        )
        Thread(target=trial.consume, daemon=True).start()

    def prepare_cli(self, kwargs, mod, session_id):
        """按验收分组选择会话 ID 或原生自动命名。@param kwargs 启动参数。@param mod 会话插件目录。
        @param session_id 账号预留的会话 ID。@return 无。
        """
        copyfile(self.fixture / "title-usage.mjs", mod / "hooks/title-usage.mjs")
        args = list(kwargs["arguments"])
        (name,) = [
            arg.removeprefix("--name=") for arg in args if arg.startswith("--name=")
        ]
        if name != session_id:
            raise ValueError("CLI 名称与预留会话不匹配")
        if self.config["automatic_name"]:
            args.remove("--name=" + name)
            kwargs["arguments"] = args
        self.record(
            reserved_session_id=session_id,
            cli_name=None if self.config["automatic_name"] else name,
        )
