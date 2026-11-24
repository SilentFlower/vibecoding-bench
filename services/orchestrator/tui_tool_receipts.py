"""在账号私有目录中持久交接客户端工具调用和结果。"""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import astuple, dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat
from threading import Lock

from runtime_files import private_directory
from tui_tool_receipts_schema import initialize_receipts_schema


_TURN_KEY = "account_id=? AND principal_id=? AND session_id=? AND turn_id=?"
_SCHEMA_LOCK = Lock()


class UnknownToolCall(LookupError):
    """在本次认证归属和工具映射下找不到已登记的调用。"""


class ReceiptConflict(ValueError):
    """登记与既有事实冲突，或调用的交接状态与请求不符。"""


def _identity(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("工具交接身份字段须为非空字符串")
    return value


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(encoded: str) -> str:
    return sha256(encoded.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class ToolTurn:
    """标识授权入口已经核验的真实轮次。

    :param account_id: 账号标识。
    :param principal_id: 认证主体标识，使用稳定标识，不传入口令牌。
    :param session_id: 入口核验的真实会话标识。
    :param turn_id: 会话内的真实轮次标识。
    """

    account_id: str
    principal_id: str
    session_id: str
    turn_id: str

    def __post_init__(self):
        for value in astuple(self):
            _identity(value)


@dataclass(frozen=True)
class ToolReceipt:
    """返回原归属的工具登记和交接状态。

    :param internal_id: 原 worker 内的调用标识。
    :param name: 对客户端公开的工具名。
    :param backend: 原内核。
    :param generation: 原 worker 代次。
    :param state: 持久交接状态。
    :param result: 客户端原始结果块，关闭轮次后清除。
    """

    internal_id: str
    name: str
    backend: str
    generation: str
    state: str
    result: dict | None = field(repr=False)


class ToolReceiptStore:
    """为一个账号私有目录中的轮次保管工具结果和投递事实。"""

    def __init__(self, private_dir: Path):
        """打开或建立私有回执库。

        :param private_dir: 服务独占的受控目录。
        :return: 无。
        """
        private_dir = Path(private_dir).absolute()
        private_directory(private_dir)
        self._path = private_dir / "tui-tool-receipts.sqlite"
        self._write_lock = Lock()
        with _SCHEMA_LOCK:
            # SQLite 自行建库会继承服务 umask，先独占创建保证结果正文从首次落盘起私有。
            try:
                descriptor = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
            with self._connection(write=True) as db:
                initialize_receipts_schema(db)

    @contextmanager
    def _connection(self, *, write=False):
        metadata = self._path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077):
            raise ValueError("回执库文件权限或归属无效")
        with closing(sqlite3.connect(self._path.as_uri() + "?mode=rw", uri=True, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                # 另一个进程也可能先收到结果，读原状态和条件写入必须处于同一写事务。
                with self._write_lock, db:
                    db.execute("PRAGMA secure_delete=ON")
                    db.execute("BEGIN IMMEDIATE")
                    yield db
            else:
                with db:
                    db.execute("BEGIN")
                    yield db

    @staticmethod
    def _turn(db, turn):
        row = db.execute(f"SELECT * FROM turns WHERE {_TURN_KEY}", astuple(turn)).fetchone()
        if row is None:
            raise UnknownToolCall("当前归属下无此工具调用")
        return row

    @staticmethod
    def _call(db, turn_key, tool_use_id):
        row = db.execute("SELECT * FROM calls WHERE turn_key=? AND tool_use_id=?",
                         (turn_key, _identity(tool_use_id))).fetchone()
        if row is None:
            raise UnknownToolCall("当前归属下无此工具调用")
        return row

    def register(self, turn: ToolTurn, tool_use_id: str, *, internal_id: str, name: str,
                 arguments: dict | None, backend: str, generation: str) -> bool:
        """在首次公开调用前绑定内外标识、参数摘要和原 worker。

        :param turn: 已认证轮次。
        :param tool_use_id: 对客户端公开的调用标识。
        :param internal_id: 原 worker 内的调用标识。
        :param name: 客户端工具名。
        :param arguments: 工具块开始时传 None，在发出块结束前用同一登记封存完整参数。
        :param backend: 处理原轮的内核。
        :param generation: 原 worker 代次。
        :return: 新登记返回真，相同登记重试返回假。
        """
        for value in (tool_use_id, internal_id, name, backend, generation):
            _identity(value)
        if arguments is not None and not isinstance(arguments, dict):
            raise ValueError("工具参数须为对象")
        arguments_hash = None if arguments is None else _digest(_json(arguments))
        with self._connection(write=True) as db:
            db.execute("""INSERT INTO turns(account_id, principal_id, session_id, turn_id, backend, generation)
                VALUES(?,?,?,?,?,?) ON CONFLICT(account_id, principal_id, session_id, turn_id) DO NOTHING""",
                (*astuple(turn), backend, generation))
            owner = self._turn(db, turn)
            if (owner["backend"], owner["generation"]) != (backend, generation):
                raise ReceiptConflict("轮次已绑定其他 worker")
            existing = db.execute("SELECT internal_id, name, arguments_hash FROM calls WHERE turn_key=? AND tool_use_id=?",
                                  (owner["id"], tool_use_id)).fetchone()
            if existing is not None:
                if (existing["internal_id"], existing["name"]) != (internal_id, name):
                    raise ReceiptConflict("工具调用标识已绑定其他登记")
                if arguments_hash is not None:
                    if existing["arguments_hash"] is None:
                        db.execute("UPDATE calls SET arguments_hash=? WHERE turn_key=? AND tool_use_id=?",
                                   (arguments_hash, owner["id"], tool_use_id))
                    elif existing["arguments_hash"] != arguments_hash:
                        raise ReceiptConflict("工具参数与已封存的内容冲突")
                return False
            if owner["closed"]:
                raise ReceiptConflict("已关闭的轮次不能登记新工具")
            try:
                db.execute("""INSERT INTO calls(turn_key, tool_use_id, internal_id, name, arguments_hash, state)
                    VALUES(?,?,?,?,?,'registered')""", (owner["id"], tool_use_id, internal_id, name, arguments_hash))
            except sqlite3.IntegrityError as exc:
                raise ReceiptConflict("内部调用标识已被使用") from exc
            return True

    def claim_delivery(self, turn: ToolTurn, tool_use_id: str) -> bool:
        """在对客户端写入调用前原子认领唯一投递机会。

        :param turn: 已认证轮次。
        :param tool_use_id: 已登记的外部调用标识。
        :return: 仅首次认领返回真；重启后已认领的调用需按原标识核对客户端结果。
        """
        with self._connection(write=True) as db:
            owner = self._turn(db, turn)
            call = self._call(db, owner["id"], tool_use_id)
            if call["state"] != "registered":
                return False
            db.execute("UPDATE calls SET state='delivery_unknown' WHERE turn_key=? AND tool_use_id=?",
                       (owner["id"], tool_use_id))
            return True

    def submit(self, turn: ToolTurn, result_block: dict) -> bool:
        """持久保存首份已登记的客户端结果，等待原 worker 稍后认领。

        :param turn: 已认证轮次。
        :param result_block: 含外部 tool_use_id 的原始 tool_result 块。
        :return: 首次保存返回真，相同结果重放返回假，冲突抛出 ReceiptConflict。
        """
        return self.submit_many(turn, [result_block])[0]

    def submit_many(self, turn: ToolTurn, blocks: list[dict]) -> list[bool]:
        """以一个事务接收 Messages 中的多个工具结果。冲突或未知调用会回滚整批。

        :param turn: 已认证轮次。
        :param blocks: 按请求顺序提交的非空 tool_result 块列表。
        :return: 每块是否首次保存，顺序与输入相同。
        """
        if not isinstance(blocks, list) or not blocks:
            raise ValueError("需要非空的工具结果块列表")
        prepared = []
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                raise ValueError("需要客户端的工具结果块")
            tool_use_id = _identity(block.get("tool_use_id"))
            if "content" in block and not isinstance(block["content"], (str, list)):
                raise ValueError("工具结果内容须为文本或内容块数组")
            if "is_error" in block and type(block["is_error"]) is not bool:
                raise ValueError("工具结果错误标志须为布尔值")
            encoded = _json(block)
            prepared.append((tool_use_id, _digest(encoded), encoded))
        with self._connection(write=True) as db:
            turn_key = self._turn(db, turn)["id"]
            inserted = []
            for tool_use_id, result_hash, encoded in prepared:
                call = self._call(db, turn_key, tool_use_id)
                if call["arguments_hash"] is None:
                    raise ReceiptConflict("工具参数尚未封存")
                if call["result_hash"] is None:
                    if call["state"] != "delivery_unknown":
                        raise ReceiptConflict("工具调用尚未认领对外投递")
                    db.execute("UPDATE calls SET state='received', result_hash=?, result_json=? "
                               "WHERE turn_key=? AND tool_use_id=?", (result_hash, encoded, turn_key, tool_use_id))
                    inserted.append(True)
                elif call["result_hash"] == result_hash:
                    inserted.append(False)
                else:
                    raise ReceiptConflict("原调用已登记不同的工具结果")
            return inserted

    def read(self, turn: ToolTurn, tool_use_id: str) -> ToolReceipt:
        """只读核对原调用，读取不会取得任何投递权。

        :param turn: 已认证轮次。
        :param tool_use_id: 已登记的外部调用标识。
        :return: 原 worker 映射、当前持久状态及仍保留的结果。
        """
        with self._connection() as db:
            owner = self._turn(db, turn)
            call = self._call(db, owner["id"], tool_use_id)
            result = json.loads(call["result_json"]) if call["result_json"] is not None else None
            return ToolReceipt(call["internal_id"], call["name"], owner["backend"], owner["generation"],
                               "closed" if owner["closed"] else call["state"], result)

    def _worker_call(self, db, turn, tool_use_id, internal_id, backend, generation):
        owner = self._turn(db, turn)
        call = self._call(db, owner["id"], tool_use_id)
        if (owner["backend"], owner["generation"], call["internal_id"]) != (backend, generation, internal_id):
            raise UnknownToolCall("当前 worker 归属下无此工具调用")
        return call

    def take_result(self, turn: ToolTurn, tool_use_id: str, *, internal_id: str,
                    backend: str, generation: str) -> dict | None:
        """以原 worker 身份原子认领一次结果投递。

        :param turn: 已认证轮次。
        :param tool_use_id: 外部调用标识。
        :param internal_id: 原 worker 内的调用标识。
        :param backend: 原内核。
        :param generation: 原 worker 代次。
        :return: 只有待投递的结果能返回原始块；认领后崩溃需与原 worker 核对。
        """
        with self._connection(write=True) as db:
            call = self._worker_call(db, turn, tool_use_id, internal_id, backend, generation)
            if call["state"] != "received":
                return None
            db.execute("UPDATE calls SET state='result_delivery_unknown' WHERE turn_key=? AND tool_use_id=?",
                       (call["turn_key"], tool_use_id))
            return json.loads(call["result_json"])

    def confirm_result(self, turn: ToolTurn, tool_use_id: str, *, internal_id: str,
                       backend: str, generation: str) -> bool:
        """收到原 worker 接收确认或取得同等对账证据后标记已投递。

        :param turn: 已认证轮次。
        :param tool_use_id: 外部调用标识。
        :param internal_id: 原 worker 内的调用标识。
        :param backend: 原内核。
        :param generation: 原 worker 代次。
        :return: 首次确认返回真，重复确认返回假。
        """
        with self._connection(write=True) as db:
            call = self._worker_call(db, turn, tool_use_id, internal_id, backend, generation)
            if call["state"] == "confirmed":
                return False
            if call["state"] != "result_delivery_unknown":
                raise ReceiptConflict("当前结果尚未认领投递")
            db.execute("UPDATE calls SET state='confirmed' WHERE turn_key=? AND tool_use_id=?",
                       (call["turn_key"], tool_use_id))
            return True

    def close_turn(self, turn: ToolTurn) -> None:
        """在原轮完成续传后清理所有已确认结果的正文，保留防重发登记。

        :param turn: 已认证且业务已结束的原轮次。
        :return: 无，尚有未确认工具时抛出 ReceiptConflict。
        """
        with self._connection(write=True) as db:
            owner = self._turn(db, turn)
            if owner["closed"]:
                return
            if db.execute("SELECT 1 FROM calls WHERE turn_key=? AND state<>'confirmed' LIMIT 1",
                          (owner["id"],)).fetchone():
                raise ReceiptConflict("轮次还有待核对的工具调用")
            db.execute("UPDATE calls SET result_json=NULL WHERE turn_key=?", (owner["id"],))
            db.execute("UPDATE turns SET closed=1 WHERE id=?", (owner["id"],))
