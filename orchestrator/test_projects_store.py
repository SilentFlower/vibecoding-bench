"""用真实SQLite验证两套工程空间共享账号、隔离事实、保留参数和事务。"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from projects import PROJECTS_SCHEMA
from projects_store import ProjectsDatabase


class ProjectsStoreTests(unittest.TestCase):
    """隔离工程表和索引，不把用户文本或共享账号名当作SQL替换目标。"""

    def setUp(self):
        """建立只含合成账号的临时数据库。:return: None。"""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'store.sqlite'
        connection = self.database()
        with connection:
            connection.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY)')
            connection.execute('INSERT INTO accounts(id) VALUES(7)')
        connection.close()

    def database(self):
        """创建行工厂和外键均真实启用的连接。:return: SQLite连接。"""
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def test_default_returns_original_connection_and_warmup_initializes_distinct_schema(self):
        """默认对象不变；完整schema的表、索引和外键都落入独立养号空间。:return: None。"""
        original = self.database()
        self.assertIs(original, ProjectsDatabase(lambda: original)())
        original.executescript(PROJECTS_SCHEMA)
        connection = ProjectsDatabase(self.database, 'warmup')()
        connection.executescript(PROJECTS_SCHEMA)
        with original:
            original.execute('INSERT INTO projects_agents(account_id,updated_at,instructions) VALUES(7,1,?)', ('original-guide',))
        with connection:
            connection.execute('INSERT INTO projects_agents(account_id,updated_at,instructions) VALUES(7,1,?)', ('warmup-guide',))
        self.assertEqual('warmup-guide', connection.execute('SELECT instructions FROM projects_agents').fetchone()['instructions'])
        self.assertEqual('original-guide', original.execute('SELECT instructions FROM projects_agents').fetchone()['instructions'])
        names = {row['name'] for row in original.execute("SELECT name FROM sqlite_master WHERE type IN ('table','index')")}
        for table in ('agents', 'work', 'actions', 'events', 'submissions'):
            self.assertIn('projects_' + table, names)
            self.assertIn('warmup_projects_' + table, names)
        self.assertIn('warmup_projects_one_work_per_account', names)
        links = {row['table'] for row in connection.execute('PRAGMA foreign_key_list(projects_work)')}
        self.assertEqual({'warmup_projects_agents'}, links)
        account_link = connection.execute('PRAGMA foreign_key_list(projects_agents)').fetchone()['table']
        self.assertEqual('accounts', account_link)
        with self.assertRaises(sqlite3.IntegrityError), connection:
            connection.execute('INSERT INTO projects_agents(account_id,updated_at) VALUES(99,1)')
        connection.close()
        original.close()

    def test_literals_comments_named_parameters_and_quoted_identifiers_keep_their_meaning(self):
        """只改表和索引标识，JSON/指南/绑定参数/SQL注释保持原值。:return: None。"""
        connection = ProjectsDatabase(self.database, 'warmup')()
        connection.executescript('''-- projects_comments 不应成为工程表
            CREATE TABLE [projects_probe](name TEXT DEFAULT 'projects_literal');
            CREATE INDEX `projects_probe_index` ON "projects_probe"(name);
            /* projects_ignored */''')
        with connection:
            connection.execute('INSERT INTO "projects_probe"(name) VALUES(:projects_value)',
                {'projects_value': 'projects_user_text'})
            connection.execute('INSERT INTO `projects_probe` DEFAULT VALUES')
        rows = [row[0] for row in connection.execute('SELECT name FROM [projects_probe] ORDER BY rowid')]
        self.assertEqual(['projects_user_text', 'projects_literal'], rows)
        self.assertEqual('projects_agents', connection.execute("SELECT 'projects_agents'").fetchone()[0])
        raw = self.database()
        self.assertEqual(2, raw.execute('SELECT COUNT(*) FROM warmup_projects_probe').fetchone()[0])
        self.assertIsNone(raw.execute("SELECT name FROM sqlite_master WHERE name='projects_probe'").fetchone())
        raw.close()
        connection.close()

    def test_context_rolls_back_only_this_space_and_close_keeps_sqlite_semantics(self):
        """真实with事务遇异常回滚，原工程空间不受影响。:return: None。"""
        raw = self.database()
        raw.execute('CREATE TABLE projects_probe(value TEXT)')
        raw.commit()
        connection = ProjectsDatabase(self.database, 'warmup')()
        connection.execute('CREATE TABLE projects_probe(value TEXT)')
        with self.assertRaises(ValueError):
            with connection as entered:
                self.assertIs(connection, entered)
                connection.execute('INSERT INTO projects_probe VALUES(?)', ('not-committed',))
                raise ValueError('合成业务失败')
        self.assertEqual(0, connection.execute('SELECT COUNT(*) FROM projects_probe').fetchone()[0])
        self.assertEqual(0, raw.execute('SELECT COUNT(*) FROM projects_probe').fetchone()[0])
        connection.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')
        raw.close()

    def test_invalid_namespace_does_not_open_database(self):
        """空间只接受服务端固定枚举，不接受模型提供的表名前缀。:return: None。"""
        def forbidden():
            raise AssertionError('无效空间不能访问数据库')
        with self.assertRaises(ValueError):
            ProjectsDatabase(forbidden, 'other')


if __name__ == '__main__':
    unittest.main()
