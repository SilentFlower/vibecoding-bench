"""冻结的中央远程执行会话增量定义，保留原节点与环境历史引用。"""
from __future__ import annotations

import sqlite3


def initialize_node_execution_schema(connection: sqlite3.Connection) -> None:
    """在调用方同一事务内建立原执行登记及活动恢复索引。

    :param connection: 持有增量迁移事务的中央连接。
    :return: None。
    """
    connection.execute("""CREATE TABLE node_executions (
        operation_id TEXT PRIMARY KEY,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        node_id INTEGER NOT NULL REFERENCES cluster_nodes(id),
        environment_id TEXT NOT NULL REFERENCES account_environments(environment_id),
        assignment_revision INTEGER NOT NULL CHECK(assignment_revision > 0),
        environment_generation INTEGER NOT NULL CHECK(environment_generation >= 0),
        source TEXT NOT NULL CHECK(length(source) BETWEEN 1 AND 160),
        role TEXT NOT NULL CHECK(role IN ('cli','projects','warmup','login','review')),
        phase TEXT NOT NULL CHECK(phase IN ('preparing','claimed','starting','running','stopping','reconcile','closed')),
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
        record_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""")
    connection.execute("CREATE UNIQUE INDEX idx_node_executions_source_active ON node_executions(account_id,source) WHERE phase<>'closed'")
    connection.execute("CREATE INDEX idx_node_executions_active ON node_executions(phase) WHERE phase<>'closed'")
