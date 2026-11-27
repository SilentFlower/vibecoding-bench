"""把同一真实模型主轮的 Messages 事件聚合为非流式响应。"""

import json

from tui_messages import ModelResponseError, encode as json_bytes


class ModelError(ModelResponseError):
    """带有 Messages 信封的确定错误。@param error 给调用方的标准错误类型和消息。"""

    def __init__(self, error, *, source=None):
        """保留可交付的错误字段。@param error 模型错误对象。@param source 已核验的来源。@return 无。"""
        if not isinstance(error, dict):
            raise ValueError("模型错误信封无效")
        kind = error.get("type")
        # 残缺的事件保留原有 502。单有类型不能将它认定为 HTTP 鉴权或限流错误。
        if not isinstance(kind, str) or not isinstance(error.get("message"), str):
            kind = ""
        status = {
            "invalid_request_error": 400,
            "authentication_error": 401,
            "billing_error": 402,
            "permission_error": 403,
            "not_found_error": 404,
            "request_too_large": 413,
            "rate_limit_error": 429,
            "timeout_error": 504,
            "overloaded_error": 529,
        }.get(kind, 502)
        super().__init__(status, json_bytes({"error": error}), source=source)


class MessageJSON:
    """聚合一轮有序 Messages 内容。@param limit 网关对单个正常化 JSON 的字节预算。"""

    def __init__(self, limit: int):
        """初始化单轮内存预算。@param limit 字节上限。@return 无。"""
        self.limit = limit
        self.size = 0
        self.message = None
        self.open = {}
        self.stopped = False

    def _charge(self, amount):
        self.size += amount
        if self.size > self.limit:
            raise ModelError(
                {
                    "type": "api_error",
                    "message": "V2 的非流式响应超过网关 JSON 正常化容量",
                }
            )

    def _replace(self, target, key, value):
        before = (
            len(json_bytes(target[key]))
            if key in target
            else -(len(json_bytes(key)) + 1)
        )
        self._charge(len(json_bytes(value)) - before)
        target[key] = value

    def add(self, event: dict) -> None:
        """并入真实事件。@param event 单条已解码 Messages 事件。@return 无。"""
        kind = event["type"]
        if kind == "ping":
            return
        if self.stopped:
            raise ValueError("模型终态之后出现额外事件")
        if kind == "error":
            raise ModelError(event["error"], source="local_provider_event")
        if kind == "message_start":
            msg = event["message"]
            if (
                self.message is not None
                or not isinstance(msg, dict)
                or msg.get("type") != "message"
                or msg.get("role") != "assistant"
                or not isinstance(msg.get("content"), list)
                or not isinstance(msg.get("usage"), dict)
            ):
                raise ValueError("模型开场信封无效")
            self._charge(len(json_bytes(msg)))
            msg["content"] = [json_bytes(block) for block in msg["content"]]
            self.message = msg
            return
        if self.message is None:
            raise ValueError("缺少模型开场信封")
        if kind == "message_delta":
            delta, usage = event["delta"], event.get("usage", {})
            if (
                not isinstance(usage, dict)
                or not isinstance(delta, dict)
                or delta.keys() & {"role", "model", "id", "type", "content", "usage"}
            ):
                raise ValueError("模型结束增量无效")
            for key, value in delta.items():
                self._replace(self.message, key, value)
            # 上下文编辑报告在流式增量的顶层，非流式消息也从该位置取实际报告。
            if "context_management" in event:
                self._replace(self.message, "context_management", event["context_management"])
            # 用量是当前步骤的累计值，后到的字段覆盖同名旧值；缺省的缓存读数仍来自开场。
            for key, value in usage.items():
                existing = self.message["usage"].get(key)
                if isinstance(existing, dict) and isinstance(value, dict):
                    for name, count in value.items():
                        self._replace(existing, name, count)
                else:
                    self._replace(self.message["usage"], key, value)
            return
        if kind == "message_stop":
            if self.open or not isinstance(self.message.get("stop_reason"), str):
                raise ValueError("模型结束时仍缺内容块或停止原因")
            self.stopped = True
            return
        idx = event["index"]
        if type(idx) is not int or idx < 0:
            raise ValueError("模型内容块索引无效")
        if kind == "content_block_start":
            block = event["content_block"]
            if (
                idx != len(self.message["content"])
                or not isinstance(block, dict)
                or not isinstance(block.get("type"), str)
            ):
                raise ValueError("模型内容块开场顺序无效")
            self._charge(len(json_bytes(block)))
            self.message["content"].append(block)
            self.open[idx] = (block, {})
            return
        block, buffers = self.open[idx]
        if kind == "content_block_stop":
            for field, buffer in buffers.items():
                if field == "input":
                    value = json.loads(buffer)
                    if not isinstance(value, dict):
                        raise ValueError("工具输入必须为 JSON 对象")
                    block[field] = value
                else:
                    block[field] = buffer.decode()
            # 完成的块按原索引以紧凑字节保留，长回复不持续持有各工具参数的 Python 对象树。
            self.message["content"][idx] = json_bytes(block)
            del self.open[idx]
            return
        if kind != "content_block_delta":
            raise ValueError("不支持的模型状态变化")
        delta = event["delta"]
        change = delta["type"]
        if change == "citations_delta" and block["type"] == "text":
            citation = delta["citation"]
            if not isinstance(citation, dict) or not isinstance(
                block.get("citations"), (list, type(None))
            ):
                raise ValueError("文本引用增量无效")
            self._charge(len(json_bytes(citation)))
            if block.get("citations") is None:
                block["citations"] = []
            block["citations"].append(citation)
            return
        if change == "signature_delta" and block["type"] == "thinking":
            field, piece = "signature", delta["signature"]
        elif change == "input_json_delta" and isinstance(block.get("input"), dict):
            field, piece = "input", delta["partial_json"]
        elif change == "text_delta" and block["type"] == "text":
            field, piece = "text", delta["text"]
        elif change == "thinking_delta" and block["type"] == "thinking":
            field, piece = "thinking", delta["thinking"]
        else:
            raise ValueError("模型增量与内容块不符")
        if not isinstance(piece, str):
            raise ValueError("模型增量内容不是字符串")
        if not piece:
            return
        data = piece.encode()
        self._charge(len(data))
        if field not in buffers:
            initial = "" if field == "input" else block.get(field, "")
            if not isinstance(initial, str):
                raise ValueError("模型内容块缺少文本起点")
            buffers[field] = bytearray(initial.encode())
        buffers[field].extend(data)

    def finish(self) -> bytes:
        """仅完成的消息可交付。@return 完整 JSON 字节。"""
        if not self.stopped:
            raise ValueError("模型流提前结束")
        envelope = dict(self.message)
        parts = envelope.pop("content")
        body = b"".join(
            (json_bytes(envelope)[:-1], b',"content":[', b",".join(parts), b"]}")
        )
        if len(body) > self.limit:
            raise ModelError(
                {
                    "type": "api_error",
                    "message": "V2 的非流式响应超过网关 JSON 正常化容量",
                }
            )
        return body
