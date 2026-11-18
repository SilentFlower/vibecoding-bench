"""迁移私有临时目录中的磁盘清单定义，操作结束随索引一起删除。"""

SCHEMA = 'CREATE TABLE entries(path TEXT PRIMARY KEY, item TEXT NOT NULL, depth INTEGER NOT NULL, seen INTEGER NOT NULL DEFAULT 0)'
