"""以同一合成账号代理对照官方 CLI、普通 HTTPS 客户端及受管交互 CLI。"""

import argparse
from contextlib import ExitStack, closing
from fcntl import ioctl
from hashlib import sha256
from http.client import HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from pty import openpty
import re
from select import select
from socket import if_nameindex
import ssl
from struct import pack
from subprocess import DEVNULL, Popen, run
from termios import TIOCSWINSZ
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic
import sys

from verify import stop, verify
from fixture_tunnel import HOST, connect_model

sys.path.insert(0, "/opt/flower/tui")
from tui_source import cli_owns_peer


CLI = Path("/cli/2.1.293/node_modules/.bin/claude")
ANSWER = "MODEL_PROXY_CONTROL_OK"


class LocalHandler(BaseHTTPRequestHandler):
    """两个本机监听器共用的 HTTP 基类。仅收集计数。"""

    def log_message(self, *_):
        """省略 HTTP 日志，避免记录本轮合成请求。@return 无。"""


class Proxy(LocalHandler):
    """标准 HTTP CONNECT 正对照，只能连到已经绑定的本机合成模型。"""

    def setup(self):
        """统计所有到达代理的 TCP 连接，包括没有形成 CONNECT 的连接。@return 无。"""
        super().setup()
        self.server.accepted.append(self.client_address[1])

    def do_CONNECT(self):
        """接通固定模型，分别统计连接和模型请求。@return 无。"""
        if self.path != HOST + ":443":
            self.server.other_targets += 1
            return self.send_error(403)

        def opened(port):
            if self.server.tui_pid and cli_owns_peer(
                self.connection, self.server.tui_pid
            ):
                self.server.tui_peers.append(port)
            self.server.connections.append(port)

        connect_model(self, self.server.origin.server_port, opened)


class Model(LocalHandler):
    """独立 TLS 服务。按 TCP 对端和 HTTP 请求分别计数。"""

    protocol_version = "HTTP/1.1"

    def do_POST(self):
        """给两个独立对照返回相同的可识别结果。@return 无。"""
        if self.path.partition("?")[0] != "/v1/messages":
            return self.send_error(404)
        body = self.rfile.read(int(self.headers["Content-Length"]))
        decoded = json.loads(body)
        last_user = next(
            (
                m
                for m in reversed(decoded.get("messages", []))
                if m.get("role") == "user"
            ),
            {},
        )
        content = last_user.get("content", "")
        texts = (
            [content]
            if isinstance(content, str)
            else [
                block.get("text", "")
                for block in content
                if block.get("type") == "text"
            ]
        )
        marker = next(
            (name for name in ("TUI_CASE_ONE", "TUI_CASE_TWO") if name in texts), None
        )
        answer = {
            "TUI_CASE_ONE": "MODEL_FIRST_OK",
            "TUI_CASE_TWO": "MODEL_SECOND_OK",
        }.get(marker, ANSWER)
        self.server.posts.append(
            {
                "peer_port": self.client_address[1],
                "tls": self.connection.version(),
                "case": marker,
                "body_sha256": sha256(body).hexdigest(),
                "session_wrapped": any(
                    s.startswith("<session>\n") and "\n</session>\n" in s for s in texts
                ),
            }
        )
        message = {
            "type": "message",
            "id": "msg_probe",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": answer}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        if decoded.get("stream"):
            frames = [
                {
                    "type": "message_start",
                    "message": {**message, "content": [], "stop_reason": None},
                },
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": answer},
                },
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 1},
                },
                {"type": "message_stop"},
            ]
            raw = "".join(
                f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in frames
            ).encode()
            mime = "text/event-stream"
        else:
            raw, mime = json.dumps(message).encode(), "application/json"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def interactive_control(home, environment, proxy, origin):
    """在正常交互模式的同一官方进程提交两轮，核对代理套接字和终端回复。
    @param home 合成工作区。@param environment 只含测试地址的环境。@param proxy 本机代理。
    @param origin TLS 接收端。@return 已确认的进程号、连接与回复数。
    """
    home.mkdir()
    (home / ".claude.json").write_text(
        json.dumps(
            {
                "hasCompletedOnboarding": True,
                "lastOnboardingVersion": "2.1.293",
                "projects": {str(home): {"hasTrustDialogAccepted": True}},
            }
        )
    )
    env = {
        **environment,
        "HOME": str(home),
        "TERM": "xterm-256color",
        "ANTHROPIC_AUTH_TOKEN": "fixture-only-token",
    }
    del env["ANTHROPIC_API_KEY"]
    master, slave = openpty()
    with ExitStack() as stack:
        stack.callback(os.close, master)
        ioctl(slave, TIOCSWINSZ, pack("HHHH", 36, 120, 0, 0))
        try:
            child = Popen(
                [
                    CLI,
                    "--model",
                    "claude-sonnet-4-6",
                    "--tools",
                    "",
                    "--strict-mcp-config",
                    "TUI_CASE_ONE",
                ],
                env=env,
                cwd=home,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                start_new_session=True,
            )
        finally:
            os.close(slave)
        stack.callback(stop, child)
        proxy.tui_pid = child.pid
        for expected in (b"MODEL_FIRST_OK", b"MODEL_SECOND_OK"):
            output = bytearray()
            deadline = monotonic() + 25
            while child.poll() is None and monotonic() < deadline:
                if select([master], [], [], 0.2)[0]:
                    output.extend(os.read(master, 65536))
                    plain = re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", output)
                    if expected in plain:
                        break
            else:
                raise AssertionError(
                    (
                        "交互正对照未收到合成答复",
                        expected,
                        child.poll(),
                        len(origin.posts),
                        bytes(output[-350:]),
                    )
                )
            if expected == b"MODEL_FIRST_OK":
                os.write(master, b"TUI_CASE_TWO")
                # 等终端渲染真实输入，再提交回车。
                typed = bytearray()
                until = monotonic() + 5
                while b"TUI_CASE_TWO" not in typed and monotonic() < until:
                    if select([master], [], [], 0.2)[0]:
                        typed.extend(os.read(master, 65536))
                os.write(master, b"\r")
        requests = [r for r in origin.posts if r["case"]]
        assert [r["case"] for r in requests] == ["TUI_CASE_ONE", "TUI_CASE_TWO"], (
            requests
        )
        traffic = [r for r in origin.posts if r["peer_port"] in proxy.tui_peers]
        assert all(r in traffic for r in requests)
        return {
            "cli_pid": child.pid,
            "verified_client_socket_owner": True,
            "connects_used": len({r["peer_port"] for r in traffic}),
            "model_posts": len(traffic),
            "foreground_posts": len(requests),
            "terminal_replies": 2,
            "received": traffic,
        }


def serve(stack, server):
    """监听器就绪后启用服务。@param stack 生命周期。@param server 已配置的服务。@return 无。"""
    Thread(target=server.serve_forever, daemon=True).start()
    stack.callback(server.shutdown)


def probe(gateway, sender, directory):
    """从同一代理和接收端独立读取三种对照结果。
    @param gateway 本机网关。@param sender 账号发送器。@param directory 一次性数据目录。@return 仅含计数和摘要的证据。
    """
    if not Path("/.dockerenv").exists() or [name for _, name in if_nameindex()] != [
        "lo"
    ]:
        raise RuntimeError("代理验证需要全新的 --network none 容器")
    cert, key = directory / "model.crt", directory / "model.key"
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=" + HOST,
            "-addext",
            "subjectAltName=DNS:" + HOST,
        ],
        stdout=DEVNULL,
        stderr=DEVNULL,
        check=True,
    )
    with ExitStack() as stack:
        origin = stack.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), Model))
        origin.posts = []
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        origin.socket = context.wrap_socket(origin.socket, server_side=True)
        serve(stack, origin)
        proxy = stack.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), Proxy))
        proxy.connections, proxy.origin, proxy.other_targets = [], origin, 0
        proxy.accepted, proxy.tui_peers, proxy.tui_pid = [], [], None
        serve(stack, proxy)
        proxy_url = f"http://127.0.0.1:{proxy.server_port}"

        # 除代理以外，此客户端没有接收端的地址。用保留域名验证 TLS 证书。
        home = directory / "control-cli"
        home.mkdir()
        environment = {
            "HOME": str(home),
            "PATH": os.defpath,
            "TERM": "dumb",
            "LANG": "C.UTF-8",
            "ANTHROPIC_BASE_URL": "https://" + HOST,
            "ANTHROPIC_API_KEY": "test-only-api-key",
            "HTTP_PROXY": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "NO_PROXY": "localhost,127.0.0.1",
            "NODE_EXTRA_CA_CERTS": str(cert),
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        result = run(
            [
                CLI,
                "-p",
                "--model",
                "claude-sonnet-4-6",
                "--tools",
                "",
                "--strict-mcp-config",
                "请回复代理连通验证结果。",
            ],
            cwd=home,
            env=environment,
            stdin=DEVNULL,
            capture_output=True,
            timeout=45,
        )
        if result.returncode or ANSWER.encode() not in result.stdout:
            raise AssertionError(
                (
                    "官方 CLI 正对照失败",
                    result.returncode,
                    len(proxy.connections),
                    len(origin.posts),
                    result.stdout[-200:],
                    result.stderr[-200:],
                )
            )
        cli_count = len(origin.posts)
        assert cli_count and all(
            r["peer_port"] in proxy.connections for r in origin.posts
        )
        control = {
            "cli_version": run(
                [CLI, "--version"],
                env=environment,
                cwd=home,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
            "connects": len(proxy.connections),
            "posts": cli_count,
            "reply_verified": True,
        }

        interactive = interactive_control(
            directory / "interactive", environment, proxy, origin
        )
        proxy.tui_pid = None
        start_connections, start_posts = len(proxy.connections), len(origin.posts)
        with closing(
            HTTPSConnection(
                *proxy.server_address,
                context=ssl.create_default_context(cafile=cert),
                timeout=10,
            )
        ) as client:
            client.set_tunnel(HOST, 443)
            for prompt in ("正常对照一", "正常对照二"):
                content = {
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": prompt}],
                }
                client.request(
                    "POST",
                    "/v1/messages",
                    json.dumps(content),
                    {"Content-Type": "application/json"},
                )
                reply = client.getresponse()
                assert (
                    reply.status == 200
                    and json.loads(reply.read())["content"][0]["text"] == ANSWER
                )
        pair = origin.posts[start_posts:]
        assert len(pair) == 2 and len(proxy.connections) - start_connections == 1
        assert pair[0]["peer_port"] == pair[1]["peer_port"] == proxy.connections[-1]
        assert pair[0]["body_sha256"] != pair[1]["body_sha256"]
        tunnel = {"connects": 1, "model_posts": len(pair), "same_tls_connection": True}

        before = (
            len(proxy.connections),
            len(origin.posts),
            proxy.other_targets,
            len(proxy.accepted),
        )
        managed = verify(gateway, sender, directory, probe_proxy=proxy_url)
        attempts = [r for r in managed["observations"] if "proxy_attempt" in r]
        rejected = [r for r in managed["observations"] if "session_proxy_status" in r]
        root_pid = next(
            r["cli_pid"] for r in managed["observations"] if "received" in r
        )
        assert len(attempts) == 3 and all(r["cli_peer"] for r in attempts)
        assert all(
            r["proxy_attempt"] == {"account": "EPERM", "session": "ERR_PROXY_TUNNEL"}
            for r in attempts
        )
        assert len(rejected) == len(attempts)
        assert [r["cli_pid"] for r in attempts[:2]] == [root_pid, root_pid]
        assert all(r["cli_peer"] and r["session_proxy_status"] == 403 for r in rejected)
        assert {r["cli_pid"] for r in rejected} == {r["cli_pid"] for r in attempts}
        counts = (
            len(proxy.connections),
            len(origin.posts),
            proxy.other_targets,
            len(proxy.accepted),
        )
        assert counts == before, ("受管探测到达了隔离代理或模型", before, counts)
        return {
            "official_cli_control": control,
            "interactive_cli_control": interactive,
            "ordinary_connect_control": tunnel,
            "managed_file_mode": {
                "proxy_attempts": attempts,
                "session_proxy_rejections": rejected,
                "account_proxy_connects": counts[0] - before[0],
                "account_proxy_other_targets": counts[2] - before[2],
                "account_proxy_tcp_accepts": counts[3] - before[3],
                "proxy_model_posts": counts[1] - before[1],
                "existing_loopback_posts": managed["model_posts"],
                "tool_reads": managed["tool_reads"],
                "cancel": managed["cancel_case"],
            },
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="native-proxy-") as root:
        print(
            json.dumps(
                probe(args.gateway.resolve(), args.sender.resolve(), Path(root)),
                ensure_ascii=False,
            )
        )
