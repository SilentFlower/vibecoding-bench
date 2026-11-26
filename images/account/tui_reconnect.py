"""保存账号事件源亲自观察到的工具续轮依据。"""

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import Lock
import time
from uuid import uuid4

from runtime_files import private_directory
from tui_input_policy import InputRejection


def digest(value):
    """计算有序 JSON 的摘要。@param value 私有比较对象。@return 十六进制摘要。"""
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return sha256(raw.encode()).hexdigest()


class ReceiptCheckpoints:
    """按账号内的实际进程身份保存恢复依据。"""

    def __init__(self, storage):
        """选择账号私有目录。@param storage 账号卷，测试可使用内存。@return 无。"""
        self.directory = Path(storage) / "tui-reconnect" if storage is not None else None
        self.db = None
        self.lock = Lock()

    def _connect(self):
        if self.db is None:
            if self.directory is not None:
                private_directory(self.directory)
            path = self.directory / "receipts.db" if self.directory is not None else ":memory:"
            db = sqlite3.connect(path, check_same_thread=False)
            db.execute("""CREATE TABLE IF NOT EXISTS receipts (
                actor TEXT PRIMARY KEY, session TEXT NOT NULL, history TEXT NOT NULL,
                blocks TEXT NOT NULL, expires REAL NOT NULL, request TEXT, state TEXT NOT NULL, revision TEXT NOT NULL)""")
            self.db = db
        return self.db

    def offer(self, key, session, history, blocks, lifetime):
        """记录已完成的新工具组。@param key 完整身份。@param session 私有工作区。
        @param history 原历史摘要。@param blocks 声明摘要。@param lifetime 有效秒数。@return 此次声明的独有修订。
        """
        now = time.time()
        revision = uuid4().hex
        with self.lock, self._connect() as db:
            db.execute("DELETE FROM receipts WHERE expires <= ?", (now,))
            db.execute("INSERT OR REPLACE INTO receipts VALUES (?,?,?,?,?,NULL,'open',?)",
                       (digest(key), session, history, json.dumps(blocks), now + lifetime, revision))
        return revision

    def find(self, key):
        """读取未过期且可恢复的声明。@param key 完整身份。@return 私有会话、历史及声明摘要。"""
        with self.lock:
            row = self._connect().execute(
                "SELECT session,history,blocks,request,state,revision FROM receipts WHERE actor=? AND expires>?",
                (digest(key), time.time())).fetchone()
        if row:
            if row[4] == "tool_started":
                raise InputRejection("outstanding_tool")
            if row[4] == "recovered":
                raise InputRejection("recovery_used")
            return row[0], row[1], json.loads(row[2]), row[3], row[5]
        return None

    def submit(self, key, revision, request, recovered):
        """冻结实际回执参数并消费单次恢复许可。@param key 身份。@param revision 原声明修订。@param request 参数摘要。
        @param recovered 是否已确认原进程退出。@return 条件写入是否成功。
        """
        with self.lock, self._connect() as db:
            return db.execute("""UPDATE receipts SET request=?, state=?
                WHERE actor=? AND revision=? AND expires>? AND state='open' AND (request IS NULL OR request=?)""",
                (request, "recovered" if recovered else "open", digest(key), revision, time.time(), request)).rowcount == 1

    def new_tool(self, key, revision):
        """登记新工具已开始输出。@param key 身份。@param revision 原声明修订。@return 无。"""
        with self.lock, self._connect() as db:
            db.execute("UPDATE receipts SET state='tool_started' WHERE actor=? AND revision=?", (digest(key), revision))

    def discard(self, key):
        """撤销已推进或已开始输出新工具的恢复依据。@param key 身份。@return 无。"""
        with self.lock, self._connect() as db:
            db.execute("DELETE FROM receipts WHERE actor=?", (digest(key),))

    def close(self):
        """释放本地连接。@return 无。"""
        with self.lock:
            if self.db is not None:
                self.db.close()
                self.db = None
