"""中央NULL登录草稿的节点归属与当前操作增量定义。"""
from __future__ import annotations

import sqlite3


def initialize_node_login_draft_schema(connection: sqlite3.Connection) -> None:
    """在调用方同一事务内登记草稿节点、CAS与提交后的真实账号引用。

    :param connection: 持有独立增量迁移事务的中央连接。
    :return: None；正式账号由实际新授权完成后另行创建。
    """
    connection.execute("""CREATE TABLE node_login_drafts (
        environment_id TEXT PRIMARY KEY NOT NULL REFERENCES account_environments(environment_id),
        node_id INTEGER NOT NULL REFERENCES cluster_nodes(id),
        operation_id TEXT NOT NULL UNIQUE CHECK(length(operation_id)=32),
        sid TEXT NOT NULL UNIQUE CHECK(length(sid)=12),
        generation TEXT NOT NULL CHECK(length(generation)=32),
        phase TEXT NOT NULL CHECK(phase IN ('preparing','active','stopping','submitting','reconcile','deleting','closed')),
        saved_account_id INTEGER REFERENCES accounts(id),
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
        record_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""")
    connection.execute('CREATE INDEX idx_node_login_drafts_node ON node_login_drafts(node_id)')
    connection.execute('CREATE INDEX idx_node_login_drafts_saved_account ON node_login_drafts(saved_account_id) WHERE saved_account_id IS NOT NULL')
    connection.execute("CREATE INDEX idx_node_login_drafts_active ON node_login_drafts(phase) WHERE phase<>'closed'")
