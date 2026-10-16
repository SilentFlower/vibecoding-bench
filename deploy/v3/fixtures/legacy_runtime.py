"""只在隔离夹具里调用旧镜像自带的运行时，验证真实布局转换。"""
import json
import os
import sqlite3
from pathlib import Path

import docker
from account_runtime import AccountRuntime


def main() -> None:
    """读取合成账号，在旧镜像中恢复原环境，输出无凭据身份摘要。

    :return: None；失败使用非零退出码。
    """
    root = Path('/verify/data')

    def database():
        """创建夹具数据库连接。@return SQLite 连接。"""
        connection = sqlite3.connect(root / 'test.sqlite')
        connection.row_factory = sqlite3.Row
        return connection

    account = json.loads(Path('/verify/legacy-account.json').read_text())
    runtime = AccountRuntime(docker.from_env(), root, Path(os.environ['VERIFY_HOST_ROOT']) / 'data', database, lambda timezone: {}, None)
    try:
        row, container = runtime.ensure(account, '9.9.9')
        value = container.exec_run(['cat', '/etc/machine-id'])
        assert value.exit_code == 0
        print(json.dumps({'environment_id': row['environment_id'], 'machine_id': value.output.decode().strip()}))
    finally:
        runtime.heartbeat_pool.shutdown()
        runtime.client.close()


if __name__ == '__main__':
    main()
