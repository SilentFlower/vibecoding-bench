"""固定的节点登记、账号归属和迁移增量定义。"""
from __future__ import annotations

import sqlite3


def initialize_cluster_schema(connection: sqlite3.Connection) -> None:
    """在调用方事务内建立节点元数据并回填本地归属。

    :param connection: 持有增量迁移事务的数据库连接。
    :return: None。
    """
    statements = (
        """CREATE TABLE cluster_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('local','ssh')),
            endpoint_key TEXT UNIQUE,
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
            config_json TEXT NOT NULL,
            observation_json TEXT,
            preparation_json TEXT,
            created_at REAL NOT NULL,
            deleted_at REAL
        )""",
        """CREATE TABLE account_node_assignments (
            account_id INTEGER PRIMARY KEY REFERENCES accounts(id),
            node_id INTEGER NOT NULL REFERENCES cluster_nodes(id),
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
            phase TEXT NOT NULL DEFAULT 'ready' CHECK(phase IN ('ready','maintenance','reconcile'))
        )""",
        """CREATE INDEX idx_account_node_assignments_node ON account_node_assignments(node_id)""",
        """CREATE TABLE node_migrations (
            operation_id TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            source_node_id INTEGER NOT NULL REFERENCES cluster_nodes(id),
            target_node_id INTEGER NOT NULL REFERENCES cluster_nodes(id),
            phase TEXT NOT NULL,
            record_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )""",
        """CREATE UNIQUE INDEX idx_node_migrations_active ON node_migrations(account_id)
            WHERE phase NOT IN ('completed','cancelled')""",
        """CREATE TRIGGER cluster_assign_new_account AFTER INSERT ON accounts BEGIN
            INSERT INTO account_node_assignments(account_id,node_id)
                SELECT NEW.id,id FROM cluster_nodes WHERE node_key='local';
        END""",
        """CREATE TRIGGER cluster_remove_deleted_account AFTER DELETE ON accounts BEGIN
            DELETE FROM account_node_assignments WHERE account_id=OLD.id;
        END""",
    )
    for statement in statements:
        connection.execute(statement)
    connection.execute("INSERT INTO cluster_nodes(node_key,name,kind,config_json,created_at) "
        "VALUES('local','本机','local','{}',0)")
    connection.execute("INSERT INTO account_node_assignments(account_id,node_id) "
        "SELECT accounts.id,cluster_nodes.id FROM accounts CROSS JOIN cluster_nodes WHERE node_key='local'")
