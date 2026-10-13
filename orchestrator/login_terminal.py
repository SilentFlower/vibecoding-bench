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
        # CLI 的硬换行可能切开 query；只拼接连续 URL 字符行，不合成参数。
        remaining = text[match.end():].splitlines()
        for continuation in [None, *remaining[:12]]:
            if continuation is not None:
                part = continuation.strip()
                if not part:
                    continue
                if not fullmatch(r"[A-Za-z0-9_~.%&=+/?#:-]+", part):
                    break
                candidate += part
            if len(candidate) > 8192:
                break
            try:
                parsed = urlsplit(candidate)
                query = parse_qs(parsed.query, keep_blank_values=True)
                if parsed.scheme != "https" or parsed.netloc not in ("claude.ai", "platform.claude.com") or parsed.path != "/oauth/authorize" or parsed.fragment:
                    break
                if not required.issubset(query) or any(len(query[key]) != 1 or not query[key][0] for key in required):
                    continue
                if query["response_type"] != ["code"] or query["code_challenge_method"] != ["S256"]:
                    break
                if not fullmatch(r"[A-Za-z0-9_-]{43}", query["code_challenge"][0]) or not fullmatch(r"[A-Za-z0-9_-]{43}", query["state"][0]):
                    continue
                redirect = urlsplit(query["redirect_uri"][0])
                if redirect.scheme != "https" or redirect.netloc not in ("platform.claude.com", "console.anthropic.com"):
                    break
                return candidate
            except ValueError:
                break
    return None
