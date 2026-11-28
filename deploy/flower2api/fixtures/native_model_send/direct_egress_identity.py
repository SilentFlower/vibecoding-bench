"""隔离直发验收使用的正文身份，仅规范化实测晚写入的计费校验。"""

from hashlib import sha256
import json
from re import search


def model_body_identity(body):
    """保留请求字段及次序，单列计费校验。@param body CLI 钩子或模型实收所见请求。
    @return 仅略过计费校验值的正文摘要和原计费校验。
    """
    first, *rest = body["system"]
    text = first["text"]
    assert text.startswith("x-anthropic-billing-header:")
    check = search(r"\bcch=([^; ]+);", text)
    if check is not None:
        normalized = {**first, "text": text[:check.start(1)] + "cch-value" + text[check.end(1):]}
        body = {**body, "system": [normalized, *rest]}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {"sha256": sha256(raw).hexdigest(), "billing_cch": check.group(1) if check else None}
