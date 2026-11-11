"""真实SQLite迁移登记、幂等、回填失败及旧程序兼容测试。"""
import copy
import sqlite3
import unittest

from database_migration_contract import load_registry, registry_contract, validate_registry
from database_migrations import apply_migrations, migration_plan, schema_checksum
from pathlib import Path


class DatabaseMigrationTests(unittest.TestCase):
    """使用合成数据验证真实事务和台账。"""

    def setUp(self) -> None:
        """创建独立内存库。@return None。"""
        self.database = sqlite3.connect(':memory:')
        self.database.row_factory = sqlite3.Row
        self.addCleanup(self.database.close)
        self.registry = load_registry(Path(__file__).with_name('database-migration-registry.json'), 'bench')

    def test_empty_database_baseline_and_repeat_preserve_records(self) -> None:
        """空库建立基线后重复执行保留账号与台账。@return None。"""
        first = apply_migrations(self.database)
        with self.database:
            self.database.execute("INSERT INTO accounts(name,profile_path) VALUES('synthetic','profiles/synthetic')")
        second = apply_migrations(self.database)
        self.assertEqual(first['contract'], second['contract'])
        self.assertEqual(second['current_version'], 1)
        self.assertEqual(self.database.execute('SELECT COUNT(*) FROM system_schema_migrations').fetchone()[0], 1)
        self.assertEqual(self.database.execute('SELECT profile_path FROM accounts').fetchone()[0], 'profiles/synthetic')

    def test_add_table_column_index_and_backfill_with_version_two(self) -> None:
        """新增登记可真实建表、补列、索引并回填，旧程序保留后来的数据。@return None。"""
        apply_migrations(self.database)
        with self.database:
            self.database.execute("INSERT INTO accounts(name,profile_path) VALUES('synthetic','profiles/synthetic')")
        registry = copy.deepcopy(self.registry)
        registry['steps'].append({'id': 'bench.synthetic.2', 'version': 2, 'predecessor': 1, 'checksum': 'a' * 64,
            'engine': 'sqlite', 'kind': 'schema', 'rollback_mode': 'compatible'})
        validate_registry(registry, 'bench')
        def increment(connection):
            connection.execute('CREATE TABLE synthetic_versions(id INTEGER PRIMARY KEY, value TEXT)')
            connection.execute('ALTER TABLE accounts ADD COLUMN synthetic_note TEXT')
            connection.execute('CREATE INDEX synthetic_note_index ON accounts(synthetic_note)')
            connection.execute("UPDATE accounts SET synthetic_note='retained'")
        from database_schema import initialize_bench_schema
        runners = {'bench.baseline.1': (initialize_bench_schema, schema_checksum), 'bench.synthetic.2': (increment, lambda: 'a' * 64)}
        result = apply_migrations(self.database, registry=registry, runners=runners)
        self.assertEqual(result['current_version'], 2)
        self.assertEqual(result['contract'], registry_contract(registry))
        self.assertEqual(apply_migrations(self.database, registry=registry, runners=runners)['current_version'], 2)
        self.assertEqual(apply_migrations(self.database)['state'], 'compatible_newer')
        self.assertEqual(self.database.execute('SELECT synthetic_note FROM accounts').fetchone()[0], 'retained')

    def test_failed_backfill_rolls_back_data_and_step_marker(self) -> None:
        """失败的数据回填事务保持原记录与原版本。@return None。"""
        apply_migrations(self.database)
        with self.database:
            self.database.execute("INSERT INTO accounts(name,profile_path) VALUES('synthetic','profiles/before')")
        registry = copy.deepcopy(self.registry)
        registry['steps'].append({'id': 'bench.synthetic.2', 'version': 2, 'predecessor': 1, 'checksum': 'b' * 64,
            'engine': 'sqlite', 'kind': 'data', 'rollback_mode': 'compatible'})
        def fail(connection):
            connection.execute('ALTER TABLE accounts ADD COLUMN synthetic_failed TEXT')
            connection.execute('CREATE TABLE synthetic_failed_table(id INTEGER)')
            connection.execute("UPDATE accounts SET profile_path='profiles/invalid'")
            raise RuntimeError('synthetic-failure')
        from database_schema import initialize_bench_schema
        runners = {'bench.baseline.1': (initialize_bench_schema, schema_checksum), 'bench.synthetic.2': (fail, lambda: 'b' * 64)}
        with self.assertRaisesRegex(RuntimeError, 'synthetic-failure'):
            apply_migrations(self.database, registry=registry, runners=runners)
        self.assertEqual(self.database.execute('SELECT profile_path FROM accounts').fetchone()[0], 'profiles/before')
        self.assertEqual(migration_plan(self.database)['current_version'], 1)
        self.assertNotIn('synthetic_failed', {row['name'] for row in self.database.execute('PRAGMA table_info(accounts)')})
        self.assertIsNone(self.database.execute("SELECT name FROM sqlite_master WHERE name='synthetic_failed_table'").fetchone())

    def test_modified_marker_or_definition_rejected(self) -> None:
        """历史登记与程序语义被改写时拒绝继续执行。@return None。"""
        apply_migrations(self.database)
        with self.database:
            self.database.execute("UPDATE system_schema_migrations SET checksum=?", ('c' * 64,))
        with self.assertRaisesRegex(ValueError, '摘要'):
            apply_migrations(self.database)

    def test_registry_chain_and_contract_are_explicit(self) -> None:
        """缺前驱、重复ID与破坏性模式不能进入登记。@return None。"""
        for field, value in (('predecessor', 2), ('rollback_mode', 'destructive'), ('checksum', 'not-a-digest')):
            registry = copy.deepcopy(self.registry)
            registry['steps'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_registry(registry, 'bench')

    def test_unknown_legacy_core_does_not_receive_a_ledger(self) -> None:
        """旧库缺少必要字段时在写入迁移台账前拒绝。@return None。"""
        self.database.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT,profile_path TEXT)')
        with self.assertRaisesRegex(ValueError, '迁移基线'):
            apply_migrations(self.database)
        self.assertIsNone(self.database.execute("SELECT 1 FROM sqlite_master WHERE name='system_schema_migrations'").fetchone())

    def test_registered_database_checks_actual_columns(self) -> None:
        """已登记数据库的缺列仍须明确拒绝。@return None。"""
        apply_migrations(self.database)
        self.database.execute('ALTER TABLE accounts DROP COLUMN enabled')
        with self.assertRaisesRegex(ValueError, 'accounts.enabled'):
            migration_plan(self.database)
        with self.assertRaises(ValueError):
            apply_migrations(self.database)

    def test_wrong_primary_key_or_column_affinity_is_rejected(self) -> None:
        """核心主键及字段类型异常保持失败状态。@return None。"""
        for identity in ('id TEXT PRIMARY KEY', 'id INTEGER'):
            with self.subTest(identity=identity):
                self.database.execute('DROP TABLE IF EXISTS accounts')
                self.database.execute('CREATE TABLE accounts(' + identity + ',name TEXT,profile_path TEXT,enabled INTEGER,upstream_socks5_host TEXT,upstream_socks5_port INTEGER)')
                with self.assertRaisesRegex(ValueError, '迁移基线'):
                    apply_migrations(self.database)


if __name__ == '__main__':
    unittest.main()
