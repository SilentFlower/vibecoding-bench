"""账号 sender 的原生 Messages 分类与普通 API 请求约定，对照 native293 的 parseInput。"""

import json
import re


_API_FIELDS = {
    "model",
    "messages",
    "system",
    "tools",
    "tool_choice",
    "max_tokens",
    "thinking",
    "temperature",
    "output_config",
    "stream",
    "context_management",
    "metadata",
}
_IDENTITIES = {
    "You are Claude Code, Anthropic's official CLI for Claude.",
    "You are a Claude agent, built on Anthropic's Claude Agent SDK.",
}
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I | re.ASCII)
_BILLING = "x-anthropic-billing-header:"
CONTEXT_BETA = "context-management-2025-06-27"
SYSTEM_CLEAR_AT_BETA = "mid-conversation-system-clear-at-2026-08-21"


class InputRejection(ValueError):
    """携带固定公开错误码的入站拒绝，私有准备协议只转交登记码。"""

    def __init__(self, code):
        """记录拒绝类型。@param code 固定错误码。@return 无。"""
        super().__init__(code)
        self.code = code


def _uuid(value):
    return isinstance(value, str) and _UUID.fullmatch(value) is not None


def native_input(body, cli):
    """区分普通 API 与原生正文，并核验声明的原生结构。

    @param body 解码后尚未裁剪的业务正文。@param cli 网关核过的固定 CLI 来源信息。
    @return 正文是否走原生扩展合同。
    """
    system = body.get("system")
    blocks = (
        [{"text": system}]
        if isinstance(system, str)
        else system
        if isinstance(system, list)
        else []
    )
    marked = [
        i
        for i, b in enumerate(blocks)
        if isinstance(b, dict)
        and isinstance(b.get("text"), str)
        and b["text"].lstrip().startswith(_BILLING)
    ]
    if not marked:
        first = blocks[0] if blocks else None
        if not (
            cli
            and isinstance(system, list)
            and isinstance(first, dict)
            and first.get("type") == "text"
            and isinstance(first.get("text"), str)
            and first["text"] in _IDENTITIES
        ):
            return False
        if cli == "claude_code_280":
            raise InputRejection("invalid_native_request")
    else:
        if (
            marked != [0]
            or not isinstance(system, list)
            or blocks[0].get("type") != "text"
            or "cache_control" in blocks[0]
        ):
            raise InputRejection("invalid_native_request")
        # 账单块只是格式声明；缺损或重复的声明不能替代普通 API 的字段校验。
        text = blocks[0]["text"].lstrip()[len(_BILLING) :]
        fields = {}
        for field in filter(None, (v.strip() for v in text.split(";"))):
            match = re.fullmatch(r"([a-z_][a-z0-9_]*)=([^\r\n;]+)", field)
            if not match or match[1] in fields:
                raise InputRejection("invalid_native_request")
            fields[match[1]] = match[2]
        if (
            not re.fullmatch(r"2\.1\.293\.[0-9a-f]{3}", fields.get("cc_version", ""))
            or fields.get("cc_entrypoint") not in ("cli", "sdk-cli", "claude-vscode")
            or len(re.findall(r"\bcch=", text, re.ASCII)) != int("cch" in fields)
            or ("cch" in fields and not re.fullmatch(r"[0-9a-f]{5}", fields["cch"]))
            or (
                "cc_is_subagent" in fields
                and fields["cc_is_subagent"] not in ("true", "false")
            )
            or ("cc_prompt_id" in fields and not _uuid(fields["cc_prompt_id"]))
            or any(
                k in fields and not re.fullmatch(r"[0-9]+", fields[k])
                for k in ("cc_prompt_index", "cc_turn_index")
            )
        ):
            raise InputRejection("invalid_native_request")
    metadata = body.get("metadata")
    try:
        user = (
            json.loads(metadata["user_id"])
            if isinstance(metadata, dict) and isinstance(metadata.get("user_id"), str)
            else None
        )
    except ValueError:
        user = None
    if not (
        isinstance(user, dict)
        and isinstance(user.get("device_id"), str)
        and re.fullmatch(r"[0-9a-fA-F]{64}", user["device_id"])
        and _uuid(user.get("session_id"))
        and (user.get("account_uuid") == "" or _uuid(user.get("account_uuid")))
    ):
        raise InputRejection("invalid_native_request")
    return True


def _keys(obj, allowed):
    if obj.keys() - allowed:
        raise InputRejection("unsupported_parameter")


def _count(obj, kinds, minimum=0):
    if not (
        isinstance(obj, dict)
        and obj.keys() == {"type", "value"}
        and obj["type"] in kinds
        and type(obj["value"]) in (int, float)
        and minimum <= obj["value"] <= 2**53 - 1
        and obj["value"] == int(obj["value"])
    ):
        raise InputRejection("invalid_context_management")


def _context(value):
    if not isinstance(value, dict):
        raise InputRejection("invalid_context_management")
    _keys(value, {"edits"})
    edits = value.get("edits", [])
    if not isinstance(edits, list):
        raise InputRejection("invalid_context_management")
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise InputRejection("invalid_context_management")
        if edit.get("type") == "clear_thinking_20251015":
            _keys(edit, {"type", "keep"})
            if index != 0:
                raise InputRejection("invalid_context_management")
            if "keep" in edit and edit["keep"] != "all":
                _count(edit["keep"], ("thinking_turns",), 1)
        elif edit.get("type") == "clear_tool_uses_20250919":
            _keys(
                edit,
                {
                    "type",
                    "trigger",
                    "keep",
                    "clear_at_least",
                    "exclude_tools",
                    "clear_tool_inputs",
                },
            )
            for key, kinds in (
                ("trigger", ("input_tokens", "tool_uses")),
                ("keep", ("tool_uses",)),
                ("clear_at_least", ("input_tokens",)),
            ):
                if key in edit:
                    _count(edit[key], kinds)
            if "exclude_tools" in edit and not (
                isinstance(edit["exclude_tools"], list)
                and all(
                    isinstance(item, str) and item for item in edit["exclude_tools"]
                )
            ):
                raise InputRejection("invalid_context_management")
            if (
                "clear_tool_inputs" in edit
                and type(edit["clear_tool_inputs"]) is not bool
            ):
                raise InputRejection("invalid_context_management")
        else:
            raise InputRejection("unsupported_parameter")


def validate_api(body, session_id):
    """核验普通 API 根字段、会话关联及历史管理指令。

    @param body 已解码的普通 API 正文。@param session_id 网关从本次原文解析的预留会话。
    @return 无。
    """
    if "metadata" in body:
        meta = body["metadata"]
        if not isinstance(meta, dict) or (
            "user_id" in meta and not isinstance(meta["user_id"], str)
        ):
            raise InputRejection("invalid_metadata")
        user_id = meta.get("user_id")
        if user_id is not None:
            try:
                obj = json.loads(user_id)
            except ValueError:
                old = re.fullmatch(r"user_.*_session_(.+)", user_id)
                obj = {"session_id": old[1]} if old else None
            if isinstance(obj, dict) and "session_id" in obj:
                value = obj["session_id"]
                if not isinstance(value, str):
                    raise InputRejection("invalid_metadata")
                if session_id is not None and session_id != value:
                    raise InputRejection("context_conflict")
    _keys(body, _API_FIELDS)
    if "context_management" in body:
        _context(body["context_management"])


def validate_api_row(row):
    """核对普通 API 消息自己的扩展键。@param row 已确认角色的消息。@return 无。"""
    _keys(
        row,
        {"role", "content", "output_config", "clear_at"}
        if row["role"] == "system"
        else {"role", "content"},
    )
    if row.get("output_config") is not None and not isinstance(
        row["output_config"], dict
    ):
        raise InputRejection("invalid_parameter")
    if row.get("clear_at") not in (None, "next_user_message", "never"):
        raise InputRejection("invalid_parameter")
