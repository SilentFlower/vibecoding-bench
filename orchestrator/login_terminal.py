"""从真实 CLI 终端输出提取授权链接，不生成或记录 OAuth 数据。"""
from re import finditer, fullmatch, sub
from urllib.parse import parse_qs, urlsplit


def authorization_url(pane: str) -> str | None:
    """提取有界屏幕中的完整官方 PKCE 授权链接。

    :param pane: tmux 合并软换行后的屏幕文本
    :return: 校验通过的原始链接；未完整输出时返回 None
    """
    text = sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))", "", pane[-65536:])
    required = {"client_id", "response_type", "redirect_uri", "scope", "code_challenge", "code_challenge_method", "state"}
    for match in finditer(r"https://[^\s<>\"'\x00-\x1f]+", text):
        candidate = match.group().rstrip("),.;")
        # 先拼完整连续行再校验，避免在换行的重复参数之前提前接受候选。
        remaining = text[match.end():].splitlines()
        if remaining and not remaining[0].strip():
            remaining = remaining[1:]
        else:
            remaining = []
        for part in remaining[:13]:
            part = part.strip()
            if not part or part.startswith("https://") or not fullmatch(r"[A-Za-z0-9_~.%&=+/?#:-]+", part):
                break
            candidate += part
        else:
            # 达到拼接上限时不能把仍在续行的有效前缀当完整链接。
            tail = remaining[13].strip() if len(remaining) > 13 else ""
            if tail and not tail.startswith("https://") and fullmatch(r"[A-Za-z0-9_~.%&=+/?#:-]+", tail):
                continue
        if len(candidate) > 8192:
            continue
        try:
            parsed = urlsplit(candidate)
            query = parse_qs(parsed.query, keep_blank_values=True)
            if parsed.scheme != "https" or (parsed.netloc, parsed.path) not in (
                ("claude.com", "/cai/oauth/authorize"),
                ("claude.ai", "/oauth/authorize"),
                ("platform.claude.com", "/oauth/authorize"),
            ) or parsed.fragment:
                continue
            if not required.issubset(query) or any(len(query[key]) != 1 or not query[key][0] for key in required):
                continue
            if query["response_type"] != ["code"] or query["code_challenge_method"] != ["S256"]:
                continue
            if not fullmatch(r"[A-Za-z0-9_-]{43}", query["code_challenge"][0]) or not fullmatch(r"[A-Za-z0-9_-]{43}", query["state"][0]):
                continue
            redirect = urlsplit(query["redirect_uri"][0])
            if redirect.scheme != "https" or redirect.netloc not in ("platform.claude.com", "console.anthropic.com"):
                continue
            return candidate
        except ValueError:
            continue
    return None
