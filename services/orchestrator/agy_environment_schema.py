"""AGY API环境归属的独立增量定义，既有工程账号基线保持冻结。"""


def initialize_agy_environment_schema(connection) -> None:
    """追加网关账号到现有环境的唯一归属。@param connection 迁移事务。@return 无。"""
    connection.execute("""CREATE TABLE IF NOT EXISTS platform_api_environments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        gateway_account_id INTEGER NOT NULL UNIQUE CHECK(gateway_account_id > 0),
        environment_id TEXT NOT NULL UNIQUE,
        platform TEXT NOT NULL CHECK(platform = 'antigravity'),
        FOREIGN KEY(environment_id) REFERENCES account_environments(environment_id))""")
    verify_agy_environment_schema(connection)


def verify_agy_environment_schema(connection) -> None:
    """核对已登记增量的最低列及唯一归属约束。@param connection 只读结构连接。@return 无。"""
    rows={row['name']:row for row in connection.execute('PRAGMA table_info(platform_api_environments)')}
    for name,kind in [('id','INTEGER'),('gateway_account_id','INTEGER'),('environment_id','TEXT'),('platform','TEXT')]:
        if name not in rows or rows[name]['type'].upper()!=kind or (name=='id' and rows[name]['pk']!=1):
            raise ValueError('AGY环境迁移的最低结构不符')
    unique=[]
    for index in connection.execute('PRAGMA index_list(platform_api_environments)'):
        if index['unique']:
            unique.append([row['name'] for row in connection.execute('SELECT name FROM pragma_index_info(?)',(index['name'],))])
    if ['gateway_account_id'] not in unique or ['environment_id'] not in unique:
        raise ValueError('AGY环境迁移缺少唯一归属约束')
