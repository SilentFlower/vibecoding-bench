"""保留工程 SQL 命名空间的原入口，定义归属不可变迁移基线。"""
from database_schema import (PROJECTS_IDENTIFIER, SQL_TOKEN, ProjectsDatabase,
    _ProjectsConnection, _warmup_sql)
