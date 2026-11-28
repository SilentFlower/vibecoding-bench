"""对照普通 Messages 与原版 PTY 的账号代理连接归属。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest
import json
from pathlib import Path
from shutil import which
from socket import if_nameindex
from subprocess import Popen
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import verify_tui_cold_history as fixture
import verify_tui_concurrency as pty
from fixtures.native_model_send.socket_owner import loopback_source_inode, owns_socket


CLI_SHA256 = "8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978"
ORIGIN = "https://api.anthropic.com"
QUESTION = "请直接返回这条隔离验证的合成答复。"
SENDER_CONFIG = Path("/run/v3/sender.json")


def _proc_ids(sender, session):
    sender_ids, cli_ids = [], []
    marker = ("--name=" + session).encode()
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            args = path.read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        pid = int(path.parent.name)
        if args[0].decode(errors="replace") == str(sender):
            sender_ids.append(pid)
        if marker in args:
            cli_ids.append(pid)
    return sender_ids, cli_ids


def _connection_owner(sender, session, peer, direct_pid):
    port = urlsplit(json.loads(SENDER_CONFIG.read_bytes())["proxy_url"]).port
    inode = loopback_source_inode(peer, port)
    sender_ids, cli_ids = _proc_ids(sender, session)
    if direct_pid is not None:
        cli_ids.append(direct_pid)
    sender_owners = [pid for pid in sender_ids if owns_socket(pid, inode)]
    cli_owners = [pid for pid in cli_ids if owns_socket(pid, inode)]
    assert len(sender_owners) + len(cli_owners) == 1, (session, sender_ids, cli_ids)
    owner, pid = ("interactive_cli", cli_owners[0]) if cli_owners else ("account_sender", sender_owners[0])
    return {"owner": owner, "pid": pid, "cli_pids": cli_ids, "sender_pids": sender_ids,
            "proxy_port": port, "socket_inode": inode}


def verify(gateway, sender, binary, folder, expected):
    """用正式网关入口与同一代理检验 HTTPS 的连接归属。@return 两条实收证据。"""
    evidence, current, observations = {}, {}, []
    events = fixture.startup_event
    model_credentials = []

    class ObserveModel(fixture.QuietHandler):
        """从一次性实验模型取下次正对照需要的合成认证。"""

        def parse_request(self):
            """检验本轮模型请求头。@return 原处理器结果。"""
            parsed = super().parse_request()
            if parsed and self.command == "POST" and urlsplit(self.path).path == "/v1/messages":
                presented = self.headers.get("Authorization")
                assert not model_credentials or presented == model_credentials[0]
                if not model_credentials:
                    model_credentials.append(presented)
                if current.get("direct_cli"):
                    # 对照允许官方客户端直接使用 Messages 的 beta 查询。公开基线保持原接收行为。
                    current["direct_model_path"] = self.path
                    if self.path == "/v1/messages?beta=true":
                        self.path = "/v1/messages"
            return parsed

    def observe(stage, **values):
        if stage == "proxy_connect_accepted":
            assert "proxy_connection" not in current
            peer = values["peer_port"]
            current["proxy_connection"] = {"source_port": peer}
            # 模型代理继续转发。读进程表的结果只在答复之后参加验收。
            observations.append(observer.submit(_connection_owner, sender, current["session"],
                                                peer, current.get("direct_cli")))
        if stage == "proxy_model_tcp_connected":
            current["proxy_connection"]["model_peer_port"] = values["peer_port"]
        if stage == "model_received":
            assert current["proxy_connection"]["model_peer_port"] == values["peer_port"]
            current["model_body_sha256"] = values["model_body_sha256"]
        events(stage, **values)

    def scenarios(manage, token, identifier, received, sender_status, restart, *, source_observer):
        assert not restart and not source_observer
        session = str(uuid4())
        current.update(session=session)
        payload = {"model": fixture.MODEL, "max_tokens": 128, "stream": False,
                   "messages": [{"role": "user", "content": QUESTION}]}
        status, raw, request_id = fixture.checked_messages(
            manage, token, payload, {"x-session-id": session, "User-Agent": "flower2api-egress-fixture/1"},
            received, "public_model_egress", expected_status=200, trace_startup=True, sender_status=sender_status,
        )
        assert json.loads(raw)["content"] == [{"type": "text", "text": fixture.FINAL}]

        def finished():
            detail = manage("GET", "request-diagnostics/" + request_id)
            return detail if detail["request"].get("finished_at") else None

        detail = fixture.wait_for(finished)
        (attempt,) = detail["attempts"]
        context = attempt["context"]
        reservation = detail["request"]["context"]["tui_reservation_id"]
        assert (attempt["request_id"], attempt["attempt_id"]) == (request_id, reservation)
        (model,) = received
        assert model[0] == current["model_body_sha256"]
        current["proxy_connection"].update(observations.pop().result())
        evidence["public"] = {**current, "http_status": status, "request_id": request_id, "reservation_id": reservation,
                              "body_source": context["tui_body_source"], "model_posts": 1, "tls_version": model[2],
                              "model_response_confirmed": detail["request"]["context"]["tui_confirmed_model_responses"]}

        # 同样的本地账号代理和 CA。原版 PTY 直接使用公开代理配置作为位置对照。
        previous = current["proxy_connection"]
        proxy = json.loads(SENDER_CONFIG.read_bytes())["proxy_url"]
        (authorization,) = model_credentials
        assert authorization and authorization.startswith("Bearer ")
        current.clear()
        current["session"] = str(uuid4())

        def launch(command, *, env, **options):
            process = Popen(command, env={**env, "HTTPS_PROXY": proxy, "NODE_EXTRA_CA_CERTS": str(folder / "ca.pem")},
                            **options)
            current["direct_cli"] = process.pid
            return process

        with patch.object(pty, "Popen", launch):
            terminal = pty.Terminal(binary, folder / "direct-pty", current["session"], ORIGIN,
                                    authorization.removeprefix("Bearer "), which("setsid"), model=fixture.MODEL)
        try:
            terminal.submit(QUESTION)
            pty.wait_for(lambda: terminal.completed() == 1, "原版 PTY 完成隔离模型答复")
            current["proxy_connection"].update(observations.pop().result())
        except (RuntimeError, TimeoutError):
            path = folder / "direct-pty" / "cli-debug.log"
            if path.exists():
                debug = path.read_text(errors="replace").replace(authorization.removeprefix("Bearer "), "[REDACTED]")
                print(debug[-2400:], file=sys.stderr)
            raise
        finally:
            terminal.cleanup()
        first, direct = received
        assert first[0] != direct[0] and direct[0] == current["model_body_sha256"]
        assert current["proxy_connection"]["proxy_port"] == previous["proxy_port"]
        assert current["proxy_connection"]["owner"] == "interactive_cli"
        evidence["direct_control"] = {**current, "model_posts": 1, "tls_version": direct[2], "stop_hook_count": 1}
        return evidence

    with ThreadPoolExecutor(max_workers=1) as observer, patch.multiple(
        fixture, QuietHandler=ObserveModel, startup_event=observe, verify_structured_tool_round=scenarios
    ):
        fixture.verify(gateway, sender, folder, installed_runtime=True, structured_output="live", trace_startup=True)
    return {**evidence, "expected_public_owner": expected,
            "matches_expected_public_owner": evidence["public"]["proxy_connection"]["owner"] == expected,
            "final_tls_write": "unavailable"}


def main():
    """执行仅回环的安装制品验证。@return CLI 退出码。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, default=Path("/usr/local/bin/account-sender"))
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--expected-public-owner", choices=("account_sender", "interactive_cli"), required=True)
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    with args.cli.open("rb") as executable:
        assert file_digest(executable, "sha256").hexdigest() == CLI_SHA256
    assert not Path("/opt/flower/tui/fixture_tui_source.py").exists()
    with TemporaryDirectory(prefix="verify-tui-egress-owner-") as folder:
        evidence = verify(args.gateway, args.sender, args.cli, Path(folder), args.expected_public_owner)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["matches_expected_public_owner"] else 1


if __name__ == "__main__":
    sys.exit(main())
