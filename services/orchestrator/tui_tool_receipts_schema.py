"""账号私有 V2 工具回执库的第一版结构与旧候选数据收编。"""

import sqlite3


_TABLES = (
    ("turns", """CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, principal_id TEXT NOT NULL,
                    session_id TEXT NOT NULL, turn_id TEXT NOT NULL, backend TEXT NOT NULL,
                    generation TEXT NOT NULL, closed INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(account_id, principal_id, session_id, turn_id)
                )"""),
    ("calls", """CREATE TABLE IF NOT EXISTS calls (
                    turn_key INTEGER NOT NULL REFERENCES turns(id), tool_use_id TEXT NOT NULL,
                    internal_id TEXT NOT NULL, name TEXT NOT NULL, arguments_hash TEXT,
                    state TEXT NOT NULL, result_hash TEXT, result_json TEXT,
                    PRIMARY KEY(turn_key, tool_use_id), UNIQUE(turn_key, internal_id)
                )"""),
)
VERSION = 1


def initialize_receipts_schema(connection: sqlite3.Connection) -> None:
    """在调用方写事务内建立回执库，或验证已有候选库后登记版本。

    :param connection: 仅属于当前账号的 SQLite 连接。
    :return: 结构与版本一致时返回。
    """
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, VERSION):
        raise ValueError("账号工具回执库版本不受支持")
    for table, statement in _TABLES:
        if version == 0:
            connection.execute(statement)
        row = connection.execute("SELECT sql FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone()
        # SQLite 保存建表定义时会省略 IF NOT EXISTS。比较已发布的完整定义可保留唯一键及外键语义。
        expected = statement.replace(" IF NOT EXISTS", "", 1).split()
        if row is None or row[0].split() != expected:
            raise ValueError(f"账号工具回执结构与登记不符：{table}")
    if version == 0:
        connection.execute(f"PRAGMA user_version={VERSION}")
