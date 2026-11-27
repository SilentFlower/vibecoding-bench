"""在仅回环容器预装本地直发候选的固定运行文件。"""

from argparse import ArgumentParser
from hashlib import file_digest
from pathlib import Path
from shutil import copy2, copytree
from socket import if_nameindex

import verify_tui_cold_history as fixture
import verify_tui_core_http_hook as core
from verify_tui_direct_reuse import CANDIDATE_MODE, install_permit


def main():
    """导出供本地镜像构建的隔离 Mod 和账号事件源。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--policy-guard", type=Path, required=True)
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    runtime = args.output / "runtime"
    runtime.mkdir()
    for version, digest in core.PROGRAMS.items():
        path = Path(f"/cli/{version}/node_modules/.bin/claude")
        with path.open("rb") as program:
            assert file_digest(program, "sha256").hexdigest() == digest
        output = args.output / "cli" / path.relative_to("/cli")
        output.parent.mkdir(parents=True)
        copy2(path, output)
        copy2(path.parents[2] / ".ready", output.parents[2] / ".ready")

    version = "2.1.321"
    fixture.install_source()
    core.install(version, core.PROGRAMS[version], "tool", "managed")
    install_permit(CANDIDATE_MODE)
    account = Path("/opt/flower/tui")
    (account / "fixture-installed-direct").touch()
    mod = account / "tui-mod/hooks/session.js"
    mod_code = mod.read_text()
    register = "export function register(on) {\n"
    step = "    const stream = next(e)\n"
    position = "      const chunk = item.value\n"
    terminal = "        const response = item.value\n"
    result = "          answer: response.answer, usage: response.usage,\n"
    assert all(mod_code.count(marker) == 1 for marker in (register, step, position, terminal, result))
    mod.write_text(mod_code.replace(register, register + """  let responseStep = null
  on('session.append', { door: 'response' }, async ($, e, next) => {
    // 官方增量可读思考文字，完整签名和不透明内容来自同一步的助手追加事件。
    if (responseStep && !e.agentId && e.message.role === 'assistant') {
      const { turn, step, rows } = responseStep
      if (typeof e.uuid === 'string') rows.add(e.uuid)
      const blocks = e.message.content.filter(b => ['thinking', 'redacted_thinking'].includes(b.type))
      if (blocks.length) await post($, 'direct-chunk', { turn, step, chunk: { kind: 'signed', blocks } })
    }
    return next(e)
  })
""").replace(step, """    responseStep = { turn: e.turnId, step: e.index, rows: new Set() }
""" + step).replace(terminal, terminal + """        const responseRows = responseStep.rows
        responseStep = null
""")
        .replace(result, result + "          archive_rows: response.stopReason === 'refusal' ? [...responseRows] : [],\n")
        .replace(position, position + """      if (['text', 'tool', 'input'].includes(chunk.kind)) {
        await post($, 'direct-chunk', { turn: e.turnId, step: e.index, chunk })
      }
"""))
    marketplace = Path(f"/opt/{core.POLICY_MARKET}")
    hook = marketplace / core.POLICY_PLUGIN / "hooks/observe.js"
    code = hook.read_text()
    marker = "address.includes('/v1/messages')"
    assert code.count(marker) == 1
    # 外部原版客户端也在回环验证环境中，只有内层面向固定模型地址的请求接受受管许可。
    hook.write_text(code.replace(marker, """['https://api.anthropic.com/v1/messages',
      'https://api.anthropic.com/v1/messages?beta=true'].includes(address)"""))
    for directory in (account, marketplace, Path("/etc/claude-code")):
        copytree(directory, runtime / directory.relative_to("/"), ignore=lambda _, names: [
            name for name in names if name in {"__pycache__", "runtime"}
        ])
    copy2(args.policy_guard, runtime / account.relative_to("/") / "tui-guard")


if __name__ == "__main__":
    main()
