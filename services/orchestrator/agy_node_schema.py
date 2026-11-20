"""反重力网关环境的节点分配与持久迁移增量。"""


def initialize_agy_node_schema(connection) -> None:
    """回填已有 AGY 环境并登记接下来的首次本机归属。@param connection 迁移事务。@return 无。"""
    connection.execute("""CREATE TABLE agy_node_assignments (
        account_id INTEGER PRIMARY KEY REFERENCES platform_api_environments(gateway_account_id),
        node_id INTEGER NOT NULL REFERENCES cluster_nodes(id),
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
        phase TEXT NOT NULL DEFAULT 'ready' CHECK(phase IN ('ready','maintenance','reconcile','retired'))
    )""")
    connection.execute("CREATE INDEX idx_agy_node_assignments_node ON agy_node_assignments(node_id)")
    connection.execute("""CREATE TABLE agy_node_migrations (
        operation_id TEXT PRIMARY KEY,
        account_id INTEGER NOT NULL REFERENCES platform_api_environments(gateway_account_id),
        source_node_id INTEGER NOT NULL REFERENCES cluster_nodes(id),
        target_node_id INTEGER NOT NULL REFERENCES cluster_nodes(id),
        phase TEXT NOT NULL,
        record_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""")
    connection.execute("""CREATE UNIQUE INDEX idx_agy_node_migrations_active ON agy_node_migrations(account_id)
        WHERE phase NOT IN ('completed','cancelled')""")
    connection.execute("""CREATE TRIGGER cluster_assign_new_agy_environment AFTER INSERT ON platform_api_environments BEGIN
        INSERT INTO agy_node_assignments(account_id,node_id)
            SELECT NEW.gateway_account_id,id FROM cluster_nodes WHERE node_key='local';
    END""")
    connection.execute("""INSERT INTO agy_node_assignments(account_id,node_id)
        SELECT p.gateway_account_id,n.id FROM platform_api_environments p
        CROSS JOIN cluster_nodes n WHERE n.node_key='local'""")
    verify_agy_node_schema(connection)


def verify_agy_node_schema(connection) -> None:
    """核对节点分配和迁移的最低结构。@param connection 结构校验连接。@return 无。"""
    columns = {
        'agy_node_assignments': {'account_id', 'node_id', 'revision', 'phase'},
        'agy_node_migrations': {'operation_id', 'account_id', 'source_node_id', 'target_node_id',
            'phase', 'record_json', 'created_at', 'updated_at'},
    }
    for table, required in columns.items():
        if not required <= {row[1] for row in connection.execute('SELECT * FROM pragma_table_info(?)', (table,))}:
            raise ValueError('AGY 节点归属增量缺少必要列')
        if ('platform_api_environments', 'account_id', 'gateway_account_id') not in {
                (row[2], row[3], row[4]) for row in connection.execute('SELECT * FROM pragma_foreign_key_list(?)', (table,))}:
            raise ValueError('AGY 节点归属增量缺少网关环境外键')
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='cluster_assign_new_agy_environment'").fetchone():
        raise ValueError('AGY 节点归属增量缺少首次登记触发器')
