"""为同一工程服务提供固定 SQL 命名空间，业务参数与共享账号表保持原样。"""
from __future__ import annotations

import re


SQL_TOKEN = re.compile(r"'(?:(?:'')|[^'])*'|\"(?:(?:\"\")|[^\"])*\"|`(?:(?:``)|[^`])*`|\[[^\]]*\]|--[^\n]*(?:\n|$)|/\*[\s\S]*?\*/|[:@$][A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*")
PROJECTS_IDENTIFIER = re.compile(r'projects_[A-Za-z0-9_]+\Z', re.IGNORECASE)


def _warmup_sql(sql: str) -> str:
    """只映射 SQL 标识，跳过字符串常量及注释。:param sql: 服务端固定SQL。:return: 养号物理表SQL。"""
    def replace(match):
        token = match.group()
        if token.startswith(('\'', '--', '/*', ':', '@', '$')):
            return token
        if token[0] in ('"', '`', '['):
            inner = token[1:-1]
            return token[0] + 'warmup_' + inner + token[-1] if PROJECTS_IDENTIFIER.fullmatch(inner) else token
        return 'warmup_' + token if PROJECTS_IDENTIFIER.fullmatch(token) else token
    return SQL_TOKEN.sub(replace, sql)


class _ProjectsConnection:
    """转发真实 SQLite 连接，仅固定改写服务自身的工程表和索引名称。"""

    def __init__(self, connection):
        """保留原连接的行工厂与事务行为。:param connection: 已建立连接。:return: None。"""
        self.connection = connection

    def execute(self, sql, parameters=()):
        """执行映射后的SQL，绑定值不作转换。:param sql: 受信SQL。:param parameters: 原参数。:return: 原SQLite游标。"""
        return self.connection.execute(_warmup_sql(sql), parameters)

    def executescript(self, sql):
        """初始化隔离表和索引，保留SQLite脚本事务语义。:param sql: 受信schema脚本。:return: 原SQLite游标。"""
        return self.connection.executescript(_warmup_sql(sql))

    def __enter__(self):
        """进入原连接事务上下文。:return: 映射连接自身。"""
        self.connection.__enter__()
        return self

    def __exit__(self, kind, value, traceback):
        """沿用原连接的提交或回滚。:param kind: 异常类型。:param value: 异常值。:param traceback: 栈。:return: 原连接处理结果。"""
        return self.connection.__exit__(kind, value, traceback)

    def close(self):
        """关闭原连接。:return: None。"""
        return self.connection.close()


class ProjectsDatabase:
    """把独立工程空间接入同一SQLite连接工厂，不复制工程服务。

    :param database: 返回真实SQLite连接的工厂。
    :param namespace: 服务端固定的 projects 或 warmup。
    """

    def __init__(self, database, namespace: str = 'projects') -> None:
        """校验固定空间，初始化不访问数据库。:param database: 连接工厂。:param namespace: 固定空间。:return: None。"""
        if namespace not in ('projects', 'warmup'):
            raise ValueError('工程数据库空间不合法')
        self.database, self.namespace = database, namespace

    def __call__(self):
        """建立连接；原空间返回原对象以保留全部旧行为。:return: 原连接或养号SQL隔离连接。"""
        connection = self.database()
        return connection if self.namespace == 'projects' else _ProjectsConnection(connection)
