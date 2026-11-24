"""在已核验的账号请求上应用 V1 Messages 缓存策略，按需复制发生变化的协议字段。"""


def _prefix(body):
    count, short = 0, False
    # 提供方消费前缀的顺序固定为 tools、system，与 JSON 的键顺序无关。
    for field in ("tools", "system"):
        if field not in body or field == "system" and isinstance(body[field], str):
            continue
        for block in body[field]:
            if "cache_control" not in block:
                continue
            cache = block["cache_control"]
            if (
                not isinstance(cache, dict)
                or cache.keys() - {"type", "scope", "ttl"}
                or cache.get("type") != "ephemeral"
                or "scope" in cache
                and not isinstance(cache["scope"], str)
                or cache.get("ttl", "5m") not in ("5m", "1h")
                or short
                and cache.get("ttl") == "1h"
            ):
                return None
            short |= cache.get("ttl") != "1h"
            count += 1
    return max(0, 4 - count), "5m" if short else "1h"


def _nested_marker(messages):
    pending = [
        block["content"]
        for message in messages
        if isinstance(message["content"], list)
        for block in message["content"]
        if isinstance(block.get("content"), list)
    ]
    while pending:
        for block in pending.pop():
            if not isinstance(block, dict):
                continue
            if "cache_control" in block:
                return True
            # 工具参数和 schema 可有同名业务字段，只沿协议内容块下降。
            if isinstance(block.get("type"), str) and isinstance(
                block.get("content"), list
            ):
                pending.append(block["content"])
    return False


def _candidate(message):
    role, content = message["role"], message["content"]
    if role not in ("user", "assistant"):
        return None
    if isinstance(content, str):
        return 0 if content else None
    for i in reversed(range(len(content))):
        block = content[i]
        if (
            block["type"] == "text"
            and isinstance(block.get("text"), str)
            and block["text"]
            or role == "user"
            and block["type"] == "tool_result"
        ):
            return i
    return None


def _layout(body):
    messages = body["messages"]
    if "cache_control" in body or _nested_marker(messages):
        return body
    prefix = _prefix(body)
    if prefix is None:
        return body
    available, ttl = prefix
    candidates = [len(messages) - 1]
    if len(messages) >= 4:
        users = (
            i for i in reversed(range(len(messages))) if messages[i]["role"] == "user"
        )
        next(users, None)
        previous = next(users, None)
        if previous is not None:
            candidates.append(previous)
    selected = {}
    for i in candidates:
        pos = _candidate(messages[i])
        if pos is not None and len(selected) < available:
            selected[i] = pos
    mark = {"type": "ephemeral", "ttl": ttl}
    rows = messages
    for i, row in enumerate(messages):
        pos = selected.get(i)
        content = row["content"]
        if isinstance(content, str):
            blocks = (
                [{"type": "text", "text": content, "cache_control": mark}]
                if pos is not None
                else content
            )
        else:
            blocks = content
            for j, block in enumerate(content):
                if pos == j:
                    if block.get("cache_control") == mark:
                        continue
                    changed = {**block, "cache_control": mark}
                elif "cache_control" in block:
                    changed = {k: v for k, v in block.items() if k != "cache_control"}
                else:
                    continue
                if blocks is content:
                    blocks = content.copy()
                blocks[j] = changed
        if blocks is not content:
            if rows is messages:
                rows = messages.copy()
            rows[i] = {**row, "content": blocks}
    return body if rows is messages else {**body, "messages": rows}


def _map_changed(values, transform):
    if not isinstance(values, list):
        return values
    result = values
    for i, value in enumerate(values):
        replacement = transform(value)
        if replacement is not value:
            if result is values:
                result = values.copy()
            result[i] = replacement
    return result


def _ttl(body, ttl):
    def block(value):
        cache = value.get("cache_control")
        if (
            isinstance(cache, dict)
            and cache.get("type") == "ephemeral"
            and cache.get("ttl") != ttl
        ):
            return {**value, "cache_control": {**cache, "ttl": ttl}}
        return value

    def message(row):
        content = _map_changed(row["content"], block)
        return row if content is row["content"] else {**row, "content": content}

    result = block(body)
    for key, transform in (("tools", block), ("system", block), ("messages", message)):
        value = body.get(key)
        changed = _map_changed(value, transform)
        if changed is not value:
            result = {**result, key: changed}
    return result


def model_body(body, policy, *, native):
    """为模型生成本轮正文，历史和工具校验继续引用原输入。

    @param body 通过 Messages 校验的原始对象。@param policy 已鉴权的本轮策略。
    @param native 原生正文校验后的分类。
    @return 无语义变化时返回原对象，否则只复制需要改动的容器。
    """
    if not policy:
        return body
    result = _layout(body) if policy["sub2api"] else body
    if policy["ttl"] != "off":
        result = _ttl(result, policy["ttl"])
    if policy["adaptive"] and body.get("thinking", {}).get("type") == "disabled":
        thinking = {**body["thinking"], "type": "adaptive"}
        if "display" not in thinking and not native:
            thinking["display"] = "updates"
        result = {**result, "thinking": thinking}
    # 布局先算继承时长，后续显式 TTL 可能恰好还原同一布局。此时继续复用原始字节。
    return body if result is body or result == body else result
