"""在账号 sender 容器中，向其父进程交付原版交互会话的事件。"""

from contextlib import closing, contextmanager
import fcntl
import hashlib
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import select
import signal
import socket
import socketserver
import stat
import struct
import sys
from threading import Lock
import time
from uuid import UUID

# sender 以 -I 启动，解释器会跳过脚本目录；只加载同一只读安装目录内的应用模块。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_input_policy import InputRejection
from tui_message_json import MessageJSON
from tui_messages import (
    MODEL_PROTOCOL_HEADERS,
    MODEL_VERSION_HEADERS,
    ModelResponseError,
    OAUTH_FILE_LIMIT,
    SubagentAmbiguousError,
    SubagentBindingError,
    SubagentCapacityError,
    encode as json_bytes,
    valid_model_header_value,
    wire_events,
)


# 与 tui_sender.rs 的私有控制帧、Messages 正文和数据分片上限对应。
CONTROL_LIMIT = 4096
BODY_LIMIT = 10 * 1024 * 1024
CHUNK_LIMIT = 64 * 1024
IO_TIMEOUT = 120
SOCKET = Path("/run/v3/tui-v2/events.sock")
BINDING_FIELDS = ("account_id", "environment_id", "generation", "release_id")


def _oauth_file(reader, size):
    if type(size) is not int or not 0 < size <= OAUTH_FILE_LIMIT:
        raise ValueError("V2 凭据帧长度无效")
    data = reader.read(size)
    if len(data) != size:
        raise EOFError
    document = json.loads(data)
    expected = {"access_token", "refresh_token", "expires_at"}
    optional = {"subscription_type", "rate_limit_tier"}
    if (not isinstance(document, dict) or not expected <= document.keys()
            or document.keys() - (expected | optional | {"profile"})
            or type(document["expires_at"]) is not int or document["expires_at"] <= 0
            or any(not isinstance(document[key], str) for key in document.keys() & optional)):
        raise ValueError("V2 凭据文件结构无效")
    if "profile" in document:
        profile = document["profile"]
        if (not isinstance(profile, dict) or profile.keys() & {"accessToken", "refreshToken", "expiresAt"}
                or "scopes" in profile and (not isinstance(profile["scopes"], list)
                                            or any(not isinstance(scope, str) or not scope for scope in profile["scopes"]))):
            raise ValueError("V2 OAuth 画像结构无效")
    for key in ("access_token", "refresh_token"):
        token = document[key]
        if (not isinstance(token, str) or not 0 < len(token) <= 2048
                or not token.isascii() or not all(c.isalnum() or c in "-._~+/=" for c in token)):
            raise ValueError("V2 凭据令牌无效")
    return document


def _control(stream):
    data = stream.readline(CONTROL_LIMIT + 1)
    if not data:
        raise EOFError
    if len(data) > CONTROL_LIMIT or not data.endswith(b"\n"):
        raise ValueError("控制帧长度无效")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("控制帧须为对象")
    return value


def _reply(stream, fields, *, quota_headers=None):
    data = json_bytes(fields)
    if quota_headers:
        selected = {}
        candidate = {**fields, "quota_headers": selected}
        # 沿用原控制帧上限。优先放入短字段，避免异常长值挤掉其他窗口。
        for name in sorted(quota_headers, key=lambda name: len(quota_headers[name])):
            selected[name] = quota_headers[name]
            encoded = json_bytes(candidate)
            if len(encoded) < CONTROL_LIMIT:
                data = encoded
            else:
                del selected[name]
    stream.write(data + b"\n")


def _model_head(handle, status, content_type):
    fields = {"status": status, "content_type": content_type, "message_id_mode": "gateway"}
    if attempt_id := getattr(handle, "repair_attempt_id", None):
        fields["repair_attempt_id"] = attempt_id
    # 只在收到模型帧后随成功响应发布正文归属。预留成功或选定候选正文不足以记录此事实。
    if status == 200:
        if body_source := getattr(handle, "body_source", None):
            fields["body_source"] = body_source
        if session_origin := getattr(handle, "session_origin", None):
            fields["session_origin"] = session_origin
        if instruction_location := getattr(handle, "instruction_location", None):
            fields["instruction_location"] = instruction_location
        if content_type == "text/event-stream" and getattr(handle, "opening_usage_placeholder", False) is True:
            fields["opening_usage_placeholder"] = True
    return fields


class _Disconnected:
    """供本轮进程准入直接查询取消信号，排队时无需另开监视线程。"""

    def __init__(self, connection):
        self.poll = select.poll()
        self.poll.register(connection, select.POLLRDHUP | select.POLLHUP | select.POLLERR)

    def is_set(self):
        """读取私有 socket 对端是否已放弃预留。@return 是否取消。"""
        return bool(self.poll.poll(0))


class AccountSource:
    """管理当前绑定的会话驱动。@param path sender 配置。@param factory 交互驱动构造器。"""

    def __init__(self, path, factory):
        self.path = path
        self.factory = factory
        self.lock = Lock()
        self.driver = None
        self.epoch = None
        self.maximum = 0
        self.connections = 0

    def _config(self):
        # 配置由编排原子替换。只将公开的绑定字段和容量传入交互驱动。
        doc = json.loads(self.path.read_bytes())
        binding = {key: doc["binding"][key] for key in BINDING_FIELDS}
        maximum = doc["tui_v2"]["max_reservations"]
        if type(maximum) is not int or not 1 <= maximum <= 64:
            raise ValueError("账号预留配置无效")
        epoch = (tuple(binding.values()), hashlib.sha256(doc["binding"]["secret"].encode()).digest())
        return binding, maximum, epoch

    @contextmanager
    def _driver_for(self, epoch, maximum):
        with self.lock:
            resize = (self.maximum != maximum and not self.connections and self.driver is not None
                      and self.driver.idle())
            if self.driver is None or self.epoch != epoch or resize:
                if self.driver is not None:
                    # 原上下文中在等工具的进程仍属于原绑定；拒绝沿用到新配置。
                    self.driver.close()
                    self.driver = None
                self.driver = self.factory({"max_reservations": maximum})
                self.epoch = epoch
                self.maximum = maximum
            self.connections += 1
            driver = self.driver
        try:
            yield driver
        finally:
            with self.lock:
                self.connections -= 1

    def exchange(self, reader, writer, connection):
        """处理一次父进程的绑定探测或提交。@param reader 输入。@param writer 输出。@param connection 连接。@return 无。"""
        hello = _control(reader)
        binding, maximum, epoch = self._config()
        proof = {"protocol": 1, **binding, "nonce": hello["nonce"]}
        if str(UUID(proof["nonce"])) != proof["nonce"] or hello.get("action") not in ("status", "bind"):
            return
        if any(hello.get(key) != value for key, value in proof.items()):
            return
        with self._driver_for(epoch, maximum) as driver:
            self._exchange_bound(reader, writer, connection, proof, hello, driver, epoch)

    def _exchange_bound(self, reader, writer, connection, proof, hello, driver, epoch):
        action = hello["action"]
        ready = driver.ready()
        managed_oauth = getattr(driver, "managed_oauth", False)
        state = {
            **proof,
            "ready": ready,
            "idle": ready and driver.idle(),
            "model_headers_protocol": 1,
            "model_header_policy_protocol": 1,
            "body_policy_protocol": 1,
            "input_policy_protocol": 1,
            "agent_scope_protocol": 1,
            "agent_summary_protocol": 1,
            "upstream_session_protocol": 1,
            "title_session_mapping_protocol": 1,
            "prompt_suggestion_protocol": 1,
            "capture_http_protocol": 1,
            "signature_repair_protocol": 1,
        }
        receipt = hello.get("receipt") if action == "status" else None
        inspect = getattr(driver, "receipt_idle", None)
        if ready and inspect is not None and isinstance(receipt, dict):
            principal = receipt.get("principal_id")
            session = receipt.get("session_id")
            if type(principal) is int and principal >= 0 and isinstance(session, str) and session:
                state["receipt_idle"] = inspect((
                    proof["account_id"], proof["environment_id"], proof["generation"], principal, session,
                ))
        if managed_oauth:
            state["managed_oauth_protocol"] = 1
            state["client_system_prompt_policy_protocol"] = 1
        file_available = managed_oauth and getattr(driver, "oauth_file_available", False)
        if file_available:
            state["oauth_file_protocol"] = 1
        _reply(writer, state)
        if not ready or action == "status":
            return
        prepared = _control(reader)
        if prepared.get("action") != "prepare" or any(
            prepared.get(key) != value for key, value in proof.items()
        ):
            return
        file_offer = prepared.get("oauth_file_protocol")
        if file_offer is not None and (not file_available or type(file_offer) is not int or file_offer != 1):
            return
        reservation = prepared["reservation"]
        if any(
            reservation[key] != proof[key]
            for key in ("account_id", "environment_id", "generation")
        ):
            return
        if "input_format" in prepared:
            if prepared["input_format"] not in ("claude_code", "claude_code_280"):
                return
            reservation = {**reservation, "input_format": prepared["input_format"]}
        model_header_policy = prepared.get("model_header_policy")
        if model_header_policy is not None:
            if type(model_header_policy) is not int or model_header_policy != 1:
                return
            reservation = {**reservation, "model_header_policy": 1}
        if "body_policy" in prepared:
            policy = prepared["body_policy"]
            if (
                not isinstance(policy, dict)
                or policy.keys() != {"sub2api", "ttl", "adaptive"}
                or type(policy["sub2api"]) is not bool
                or type(policy["adaptive"]) is not bool
                or policy["ttl"] not in ("off", "5m", "1h")
            ):
                return
            reservation = {**reservation, "body_policy": policy}
        if "native_cold_history_protocol" in prepared:
            if (type(prepared["native_cold_history_protocol"]) is not int
                    or prepared["native_cold_history_protocol"] != 1 or not managed_oauth):
                return
            reservation = {**reservation, "native_cold_history": True}
        if "client_system_prompt_policy" in prepared:
            policy = prepared["client_system_prompt_policy"]
            if reservation.get("native_cold_history") is not True or policy not in ("replace", "user_reminder"):
                return
            reservation = {**reservation, "client_system_prompt_policy": policy}
        size = prepared["body_len"]
        if type(size) is not int or not 0 < size <= BODY_LIMIT:
            return
        body = reader.read(size)
        if (
            len(body) != size
            or hashlib.sha256(body).hexdigest() != prepared["body_sha256"]
        ):
            return
        header_size = prepared.get("model_headers_len", 0)
        if type(header_size) is not int or not 0 <= header_size <= BODY_LIMIT:
            return
        if header_size:
            raw_headers = reader.read(header_size)
            if len(raw_headers) != header_size:
                return
            headers = json.loads(raw_headers)
            allowed = MODEL_PROTOCOL_HEADERS if model_header_policy else MODEL_VERSION_HEADERS
            if (
                not isinstance(headers, dict)
                or headers.keys() - allowed
                or any(not valid_model_header_value(value) for value in headers.values())
                or not model_header_policy
                and any(not all(" " <= char <= "~" for char in value) for value in headers.values())
            ):
                return
            reservation = {**reservation, "model_headers": headers}
        deadline = reservation["deadline_unix_ms"] / 1000
        if time.time() >= deadline:
            return
        try:
            handle = driver.prepare(
                reservation, body, cancel_event=_Disconnected(connection)
            )
        except ModelResponseError as exc:
            if exc.source == "local_provider_backoff" and exc.status == 429 and exc.retry_after is not None:
                _reply(writer, {**state, "error": exc.source, "retry_after": exc.retry_after})
            return
        except SubagentCapacityError:
            _reply(writer, {**state, "error": "subagent_capacity"})
            return
        except SubagentAmbiguousError:
            _reply(writer, {**state, "error": "subagent_ambiguous"})
            return
        except SubagentBindingError:
            _reply(writer, {**state, "error": "subagent_binding"})
            return
        except InputRejection as exc:
            _reply(writer, {**state, "error": "input_rejected", "code": exc.code})
            return
        except ValueError:
            _reply(writer, {**state, "error": "unsupported_input"})
            return
        except TimeoutError:
            _reply(writer, {**state, "error": "capacity"})
            return
        with closing(handle):
            existing_file = bool(getattr(getattr(handle, "actor", None), "oauth_file", False))
            if handle.kind == "continuation" and existing_file and file_offer != 1:
                # 旧网关须先沿当前文件模式收口原轮，不能用旧 AT 令牌接管活动进程。
                _reply(writer, {**state, "error": "oauth_file_required"})
                return
            oauth_file = file_offer == 1 and (handle.kind != "continuation" or existing_file)
            reply = {
                **state,
                "kind": handle.kind,
                "workspace_protocol": 1,
                "workspace_resume": getattr(handle, "workspace_resume", False),
            }
            if "client_system_prompt_policy" in reservation:
                reply["client_system_prompt_policy"] = reservation["client_system_prompt_policy"]
            cold = bool(getattr(getattr(handle, "actor", None), "cold_history", None))
            if cold:
                if reservation.get("native_cold_history") is not True:
                    return
                reply["native_cold_history_protocol"] = 1
                reply.pop("capture_http_protocol", None)
                reply.pop("signature_repair_protocol", None)
                reply["capture_cli_submission_protocol"] = 1
            if not oauth_file:
                reply.pop("oauth_file_protocol", None)
            if reservation.get("agent_hint") is not None:
                reply["agent_session"] = handle.actor.reservation["session_id"]
            if handle.kind not in ("new", "continuation", "recovered") or (
                reservation["continuation_only"] and handle.kind == "new"
            ):
                return
            _reply(writer, reply)
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            connection.settimeout(remaining)
            command = _control(reader)
            if (command.get("action") != "send" or command.get("reservation_id") != reservation["reservation_id"]
                    or not isinstance(command.get("workspace"), dict)
                    or time.time() >= deadline or self._config()[2] != epoch):
                return
            if "oauth_file" in command:
                return
            if cold and (
                "signature_repair" in command or command.get("capture_http") is True
            ):
                return
            if cold and "capture_assembly" in command:
                return
            if "capture_cli_submission" in command and (
                command["capture_cli_submission"] is not True or "capture_cli_submission_protocol" not in reply
                or "capture_http" in command or "capture_assembly" in command
            ):
                return
            token = command.get("account_token")
            size = command.pop("oauth_file_len", None)
            if oauth_file:
                if "account_token" in command:
                    return
                command["oauth_file"] = _oauth_file(reader, size)
                if time.time() >= deadline or self._config()[2] != epoch:
                    return
            elif size is not None:
                return
            elif managed_oauth:
                if not isinstance(token, str) or not 0 < len(token) <= 2048 or any(not 33 <= ord(c) <= 126 for c in token):
                    return
            elif "account_token" in command:
                return
            connection.settimeout(IO_TIMEOUT)
            if "signature_repair" in command:
                if type(command["signature_repair"]) is not bool:
                    return
                handle.signature_known = command["signature_repair"]
                send_deadline = time.monotonic() + max(0, deadline - time.time())
                handle.signature_exchange = lambda raw, error=None: self._signature_exchange(
                    reader, writer, connection, handle, send_deadline, epoch, raw, error
                )
            capturing = command.get("capture_http") is True or command.get("capture_cli_submission") is True
            if capturing:
                handle.capture = []
            try:
                self._send_handle(writer, connection, handle, command)
                if capturing:
                    # 正常客户端流已发出结束符，私有尾帧由 sender 后台收取。
                    pairs, raw = handle.capture[0] if handle.capture else ([], b"")
                    headers = json_bytes(pairs)
                    writer.write(struct.pack("!II", len(headers), len(raw)))
                    writer.write(headers)
                    writer.write(raw)
            finally:
                if capturing:
                    # 等待工具的进程可继续存活，本轮采集的正文随本次发送释放。
                    handle.capture = None
                if "signature_repair" in command:
                    handle.signature_exchange = None

    def _signature_exchange(self, reader, writer, connection, handle, deadline, epoch, raw, error):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        fields = {"signature_repair": "known", "body_len": len(raw)}
        if error is not None:
            capture = getattr(handle, "capture", None)
            pairs = json_bytes(capture[0][0]) if capture and capture[0][1] == raw else b""
            fields.update(signature_repair="rejected", error_len=len(error.signature_evidence),
                          error_source=error.source, capture_headers_len=len(pairs))
        try:
            # 该交互发生在首个业务事件发布前，发送循环此时只等待原进程的事件。
            connection.settimeout(remaining)
            _reply(writer, fields)
            writer.write(raw)
            if error is not None:
                writer.write(error.signature_evidence)
                writer.write(pairs)
            decision = _control(reader)
            if decision == {"body_len": 0}:
                return None
            size = decision["body_len"]
            attempt_id = decision.get("attempt_id")
            if (type(size) is not int or not 0 < size <= BODY_LIMIT
                    or (error is None and attempt_id is not None)
                    or (error is not None and (
                        not isinstance(attempt_id, str) or str(UUID(attempt_id)) != attempt_id
                        or attempt_id == handle.reservation["reservation_id"]))):
                raise ValueError("V2 签名修复决定无效")
            repaired = reader.read(size)
            if len(repaired) != size or self._config()[2] != epoch or time.monotonic() >= deadline:
                raise EOFError("V2 签名修复的原轮已失效")
            if error is not None and capture is not None:
                capture.clear()
            return repaired, attempt_id
        except (EOFError, OSError):
            if error is not None:
                return None
            raise
        finally:
            connection.settimeout(IO_TIMEOUT)

    def _send_handle(self, writer, connection, handle, command):
        handle.disconnected = _Disconnected(connection)
        try:
            events = iter(handle.send(command))
        except ModelResponseError as exc:
            self._json_end(writer, handle, exc.status, exc.private_body, error=exc)
            return
        with closing(events):
            if not handle.stream:
                self._message_json(writer, events, connection, handle)
                return
            # 第一帧之前发生的启动失败不能被发布为成功响应。
            try:
                first = next(events, None)
            except ModelResponseError as exc:
                self._json_end(writer, handle, exc.status, exc.private_body, error=exc)
                return
            if not first:
                return
            _reply(writer, _model_head(handle, 200, "text/event-stream"),
                   quota_headers=handle.quota_headers)
            self._chunks(writer, first)
            for event in events:
                self._chunks(writer, event)
            writer.write(struct.pack("!I", 0))

    def _message_json(self, writer, events, connection, handle):
        # 只聚合最终模型流。与下游网关已有的 JSON 正常化容量一致。
        output = MessageJSON(BODY_LIMIT)
        sent = False
        error = None
        last = time.monotonic()
        disconnect = _Disconnected(connection)
        try:
            for frame in events:
                if disconnect.is_set():
                    raise EOFError
                for _, data in wire_events(BytesIO(frame)):
                    if data is not None:
                        output.add(data)
                if not sent and (output.message is not None or time.monotonic() - last >= IO_TIMEOUT / 2):
                    _reply(writer, _model_head(handle, 200, "application/json"),
                           quota_headers=handle.quota_headers)
                    sent = True
                if sent and time.monotonic() - last >= IO_TIMEOUT / 2:
                    # 长回答已持续产生模型事件，私有 JSON 流用合法空白维持分块空闲期限。
                    self._chunks(writer, b" ")
                    last = time.monotonic()
            payload = output.finish()
            status = 200
        except ModelResponseError as exc:
            status, payload = exc.status, exc.private_body
            error = exc
        except TimeoutError:
            status = 504
            payload = json_bytes({"type": "error", "error": {"type": "timeout_error", "message": "V2 模型响应超时"}})
        except (ValueError, KeyError, TypeError, RuntimeError, OverflowError):
            status = 502
            payload = json_bytes({"type": "error", "error": {"type": "api_error", "message": "V2 模型响应无效或提前终止"}})
        self._json_end(writer, handle, status, payload, sent=sent, error=error)

    def _json_end(self, writer, handle, status, payload, *, sent=False, error=None):
        if not sent:
            head = _model_head(handle, status, "application/json")
            if error and error.source is not None:
                head["error_source"] = error.source
                if error.retry_after is not None:
                    head["retry_after"] = error.retry_after
            _reply(writer, head, quota_headers=error.quota_headers if error else None)
        self._chunks(writer, payload)
        writer.write(struct.pack("!I", 0))

    @staticmethod
    def _chunks(stream, data):
        if not isinstance(data, bytes) or not data:
            raise ValueError("会话事件不是有效字节")
        for offset in range(0, len(data), CHUNK_LIMIT):
            piece = data[offset:offset + CHUNK_LIMIT]
            stream.write(struct.pack("!I", len(piece)) + piece)

    def close(self):
        """收回该进程持有的会话资源。@return 无。"""
        with self.lock:
            if self.driver is not None:
                self.driver.close()
                self.driver = None
                self.epoch = None


class SourceHandler(socketserver.StreamRequestHandler):
    """仅接收父 sender 在私有 socket 上建立的连接。"""

    def handle(self):
        """验证内核报告的对端身份后执行握手。@return 无。"""
        fmt = "3i"
        peer = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize(fmt))
        pid, uid, _ = struct.unpack(fmt, peer)
        if (pid, uid) != (self.server.sender_pid, os.geteuid()):
            return
        self.request.settimeout(IO_TIMEOUT)
        try:
            self.server.source.exchange(self.rfile, self.wfile, self.request)
        except (EOFError, BrokenPipeError, ConnectionResetError):
            # 准备后断开是 sender 的取消协议。
            pass
        except Exception as exc:
            # 正文、路径、鉴权和工具回执均不能进入容器日志。
            logging.warning("V2 会话连接结束，错误类型 %s", type(exc).__name__)


class SourceServer(socketserver.ThreadingUnixStreamServer):
    """每个已预留的轮独立传递事件，慢客户端只对本轮形成背压。"""

    daemon_threads = True


@contextmanager
def listen(path, source, sender_pid):
    """独占监听目录，安全回收上一次异常退出的 socket。

    @param path 账号私有 socket。@param source 账号驱动。@param sender_pid 父进程。
    @return 已绑定的 Unix 服务。
    """
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise PermissionError("V2 socket 目录权限无效")
        fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            info = path.lstat()
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
                raise PermissionError("V2 socket 文件归属无效")
            # 旧协议来源也可能仍在运行；锁只能互斥支持新协议的监听者。
            with socket.socket(socket.AF_UNIX) as probe:
                try:
                    probe.connect(str(path))
                except ConnectionRefusedError:
                    path.unlink()
                else:
                    raise FileExistsError("V2 socket 已被活动来源占用")
        with SourceServer(str(path), SourceHandler) as server:
            try:
                server.source = source
                server.sender_pid = sender_pid
                yield server
            finally:
                path.unlink(missing_ok=True)
    finally:
        os.close(directory)


def main(driver_factory=None):
    """在受管账号内启动内置事件源。@param driver_factory 镜像内部选定的会话驱动工厂。@return 无。"""
    # 解释器以 -I 运行，只在安装目录加载随镜像交付的会话驱动。
    from tui_session import SessionDriver
    from tui_sender_launch import purge_oauth_files

    os.umask(0o077)
    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    with closing(AccountSource(Path(sys.argv[1]), driver_factory or SessionDriver)) as source:
        with listen(SOCKET, source, os.getppid()) as server:
            purge_oauth_files()
            # sender 意外退出时也收回原会话；Linux 会将孤儿重挂给其他父进程。
            server.timeout = 1.0
            while os.getppid() == server.sender_pid:
                server.handle_request()


if __name__ == "__main__":
    main()
