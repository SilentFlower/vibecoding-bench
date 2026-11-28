"""比较正式入口试接中官方交互 CLI 的核心 HTTP 钩子。"""

from argparse import ArgumentParser
from functools import partial
from hashlib import file_digest
import json
from pathlib import Path
from re import MULTILINE, subn
from socket import if_nameindex
from subprocess import check_output
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import verify_tui_cold_history as fixture
import verify_tui_guarded_egress as guarded
from verify_tui_egress_owner import CLI_SHA256


MARKER = "FLOWER-CORE-HTTP|"
POLICY_PLUGIN = "flower-http-policy"
POLICY_MARKET = "flower-http-test"
BUILTIN_GUARD = "sec-default@builtin"
PROGRAMS = {
    "2.1.293": CLI_SHA256,
    "2.1.321": "426c33815ca6645a772f722fbff10dbf2cbdb124a8aeab733c1365dbf8bbf61f",
}
JS = """
  on('http.fetch', async ($, e, next) => {
    const origin = next.origin?.plugin ?? 'unknown'
    const address = String(e.url ?? e.init?.url)
    const model = origin === 'engine' && address.includes('/v1/messages')
    const record = row => $.ui.log('FLOWER-CORE-HTTP|' + JSON.stringify({origin, model, ...row}) + '|END', {to: 'debug'})
    record({phase: 'offer', method: e.init?.method, bodyKind: typeof e.init?.body, keys: Object.keys(e)})
    if (model && __DENY__) return {deny: '隔离模型提交未获许可'}
    const reply = await next(e)
    if (model) {
      const value = reply?.value ?? {}
      const headers = value.headers
      const header = (Array.isArray(headers) ? headers.find(h => h[0].toLowerCase() === 'x-flower-fixture')?.[1]
        : headers?.['x-flower-fixture']) ?? null
      record({phase: 'reply', keys: Object.keys(value), status: value.status, header,
        isStreaming: value.isStreaming ?? null, sendIndex: value.sendIndex ?? null,
        textLength: value.text?.length ?? null,
        hasErrorBody: value.text?.includes('隔离模型明确拒绝合成请求') ?? false})
    }
    return reply
  })
"""
FAILURE_HOOK = """
  on('classic.StopFailure', async ($, e, next) => {
    const outcome = {phase: 'stop_failure', origin: 'engine', model: false,
      category: e.error, detailsType: typeof e.error_details,
      hasRenderedError: e.last_assistant_message?.includes('隔离模型明确拒绝合成请求') ?? false}
    $.ui.log('FLOWER-CORE-HTTP|' + JSON.stringify(outcome) + '|END', {to: 'debug'})
    return next(e)
  })
"""


def install_managed_settings(authority, hook):
    """通过本机管理策略部署隔离目录市场。@param authority 实验授权方式。
    @param hook 待注册的官方 HTTP 事件处理器。@return 无。
    """
    target = Path("/etc/claude-code/managed-settings.json")
    target.parent.mkdir(mode=0o755, exist_ok=True)
    settings = {"prependPlugins": [BUILTIN_GUARD]}
    if authority == "managed":
        marketplace = Path("/opt/flower-http-test")
        plugin = marketplace / POLICY_PLUGIN
        (plugin / ".claude-plugin").mkdir(mode=0o755, parents=True)
        (plugin / "hooks").mkdir(mode=0o755)
        (marketplace / ".claude-plugin").mkdir(mode=0o755)
        (marketplace / ".claude-plugin/marketplace.json").write_text(json.dumps({
            "name": POLICY_MARKET, "owner": {"name": "Flower 隔离验收"},
            "plugins": [{"name": POLICY_PLUGIN, "source": f"./{POLICY_PLUGIN}"}],
        }))
        (plugin / ".claude-plugin/plugin.json").write_text(json.dumps({"name": POLICY_PLUGIN, "version": "1.0.0"}))
        (plugin / "hooks/hooks.json").write_text(json.dumps({"modules": ["./observe.js"]}))
        (plugin / "hooks/observe.js").write_text("export function register(on) {\n" + hook + "\n}\n")
        plugin_id = f"{POLICY_PLUGIN}@{POLICY_MARKET}"
        settings["extraKnownMarketplaces"] = {POLICY_MARKET: {
            "source": {"source": "directory", "path": str(marketplace)},
        }}
        settings["enabledPlugins"] = {plugin_id: True}
        settings["prependPlugins"].insert(0, plugin_id)
    # 策略只写入一次性容器的空白系统目录。已存在的配置必须先由验收者核对。
    with target.open("x") as policy_file:
        json.dump(settings, policy_file)


def install(version, digest, mode, authority):
    """配置仅回环的试接。@param version 官方 CLI 版本。@param digest 固定制品摘要。
    @param mode 实验场景。@param authority 实验授权方式。@return 无。
    """
    # 仅替换此容器的实验版本与摘要。启动器仍校验原版文件及工作区归属。
    guarded.install(debug_file="core-http.log")
    root = Path("/opt/flower/tui")
    launcher = root / "tui_sender_launch.py"
    code, count = subn(r'^VERSION = "[0-9.]+"$', f'VERSION = "{version}"', launcher.read_text(), flags=MULTILINE)
    assert count == 1
    code, count = subn(r'^PROGRAM_SHA256 = "[0-9a-f]+"$', f'PROGRAM_SHA256 = "{digest}"', code, flags=MULTILINE)
    assert count == 1
    launcher.write_text(code)
    hook = JS.replace("__DENY__", json.dumps(mode == "deny"))
    if authority == "managed" and mode == "error":
        hook += FAILURE_HOOK
    if authority != "default":
        install_managed_settings(authority, hook)
    if authority == "managed":
        return
    mod = root / "tui-mod/hooks/session.js"
    register = "export function register(on) {"
    body = mod.read_text()
    assert body.count(register) == 1
    mod.write_text(body.replace(register, register + hook))


class ObservedModel(guarded.ModelPath):
    """对真实模型 HTTP 回包附加隔离标记。"""

    def send_response(self, code, message=None):
        """交付与状态对应的模型头。@param code HTTP 状态。@param message 状态说明。@return 无。"""
        super().send_response(code, message)
        self.send_header("x-flower-fixture", "model-http-" + str(code))


def collect(manage, token, identifier, received, sender_status, restart, *, source_observer, mode, authority):
    """读公开回包和其 CLI 钩子的事件。@param manage 管理入口。@param token 合成入口凭据。
    @param identifier 实验账号。@param received 模型实收。@param sender_status 失败时读取发送器。
    @param restart 重启能力。@param source_observer 是否启用额外事件源观测。
    @param mode 实验场景。@param authority 实验授权方式。@return 关联证据。
    """
    if mode in ("stream", "tool"):
        result = guarded.check(manage, token, identifier, received, sender_status, restart,
                               source_observer=source_observer, mode="text" if mode == "stream" else mode)
    else:
        session = str(uuid4())
        body = {"model": fixture.MODEL, "max_tokens": 128, "stream": False, "thinking": {"type": "disabled"},
                "messages": [{"role": "user", "content": fixture.REJECT_MODEL_REQUEST}]}
        headers = {"x-session-id": session, "User-Agent": "flower2api-guarded-http-hook/1"}
        started = fixture.datetime.now(fixture.timezone.utc).isoformat(timespec="milliseconds")
        status, raw, request_id = fixture.checked_messages(
            manage, token, body, headers, received, "direct_http_hook_" + mode, expected_status=None,
            trace_startup=True, sender_status=sender_status,
        )
        detail = fixture.report_request_diagnostics(manage, "direct_http_hook_" + mode, request_id, session, started)
        result = {"status": status, "request_id": request_id, "model_posts": len(received),
                  "public_error": json.loads(raw).get("error", {}).get("type"), "diagnostics": detail}
    (log,) = Path("/native/tui-sessions").glob("*/home/.claude/core-http.log")

    def read_events():
        lines = log.read_text(errors="replace").splitlines()
        events = [json.loads(line.split(MARKER, 1)[1].split("|END", 1)[0])
                  for line in lines if MARKER in line and "|END" in line]
        if authority == "managed" and mode == "error" and not any(
                event["phase"] == "stop_failure" for event in events):
            return None
        return lines, events

    lines, events = fixture.wait_for(read_events)
    assert any(row["origin"] == "flower-tui-session" for row in events), events
    plugins = [line for line in lines if "hooks module" in line and " loaded (" in line and any(
        name in line for name in (POLICY_PLUGIN, "cc-plugin-sec-default", "flower-tui-session")
    )]
    return {"mode": mode, "public": result, "events": events, "model_posts": len(received),
            "model_digests": [digest for digest, _, _ in received], "plugins": plugins, "wire_final": "unavailable"}


def verify_boundary(version, mode, authority, result):
    """核对逐请求许可及响应边界。@param version 官方 CLI 版本。@param mode 实验场景。
    @param authority 实验授权方式。@param result 实测结果。@return 无。
    """
    expected_posts = {"stream": 1, "tool": 2, "error": 1, "deny": 0}[mode]
    assert result["model_posts"] == expected_posts, result
    core = [event for event in result["events"] if event["origin"] == "engine" and event["model"]]
    if authority != "default":
        assert any("sec-default" in line for line in result["plugins"]), result["plugins"]
    if authority == "managed":
        assert any(f"{POLICY_PLUGIN}@{POLICY_MARKET}" in line and "tier prepend" in line
                   for line in result["plugins"]), result["plugins"]
    if authority == "guarded":
        assert any("flower-tui-session@inline" in line and "tier user" in line
                   for line in result["plugins"]), result["plugins"]
    if version == "2.1.293" or authority == "guarded":
        assert not core, core
        return
    offers = [event for event in core if event["phase"] == "offer"]
    assert len(offers) == (1 if mode == "deny" else expected_posts), offers
    assert all((event["method"], event["bodyKind"]) == ("POST", "string") for event in offers), offers
    replies = [event for event in core if event["phase"] == "reply"]
    upstream = 400 if mode == "error" else 200
    assert [(event["status"], event["header"]) for event in replies] == [
        (upstream, f"model-http-{upstream}")
    ] * expected_posts, replies
    assert all(event["isStreaming"] is True and event["textLength"] == 0 for event in replies), replies
    if mode in ("error", "deny"):
        assert result["public"]["status"] == 502, result["public"]
    if authority == "managed" and mode == "error":
        (failure,) = (event for event in result["events"] if event["phase"] == "stop_failure")
        assert (failure["category"], failure["detailsType"], failure["hasRenderedError"]) == (
            "unknown", "undefined", True,
        ), failure


def main():
    """在冻结内置账号和独立 CLI 制品上运行单个能力用例。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=tuple(PROGRAMS), required=True)
    parser.add_argument("--case", choices=("stream", "tool", "error", "deny"), required=True)
    parser.add_argument("--authority", choices=("default", "guarded", "managed"), default="default",
                        help="通过原版 guard 检查旁载或受管钩子的授权边界")
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    if args.version == "2.1.293" and args.case == "deny":
        parser.error("拒绝对照使用支持核心 HTTP 事件的版本")
    if args.authority != "default" and (args.version == "2.1.293" or (
            args.authority == "guarded" and args.case == "deny"
    )):
        parser.error("含管理策略的用例需要 2.1.321，拒绝对照需要受管钩子")
    executable = Path(f"/cli/{args.version}/node_modules/.bin/claude")
    digest = PROGRAMS[args.version]
    with executable.open("rb") as program:
        assert file_digest(program, "sha256").hexdigest() == digest
    with Path("/opt/flower/tui/tui-guard").open("rb") as guard:
        guard_digest = file_digest(guard, "sha256").hexdigest()
    assert check_output([executable, "--version"], text=True).split()[0] == args.version
    install(args.version, digest, args.case, args.authority)
    try:
        with patch.multiple(
            fixture, QuietHandler=ObservedModel,
            verify_structured_tool_round=partial(collect, mode=args.case, authority=args.authority),
        ), TemporaryDirectory() as folder:
            result = fixture.verify(
                Path("/verification/claude-code-gateway"), Path("/usr/local/bin/account-sender"), Path(folder),
                installed_runtime=True, structured_output="live", trace_startup=True,
                failure_boundaries=True, model_connection_contract="server-close",
            )
    except TimeoutError:
        # 保留未收到公开响应头时原版 CLI 报出的管理策略读取失败。
        for log in Path("/native/tui-sessions").glob("*/home/.claude/core-http.log"):
            for line in log.read_text(errors="replace").splitlines():
                if "settings file read failed at /etc/claude-code/managed-settings.json" in line:
                    print(line, file=sys.stderr)
        raise
    verify_boundary(args.version, args.case, args.authority, result)
    print(json.dumps({"version": args.version, "program_sha256": digest, "sandbox_guard_sha256": guard_digest,
                      "authority": args.authority, **result},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
