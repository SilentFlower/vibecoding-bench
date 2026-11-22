"""真实SQLite迁移登记、幂等、回填失败及旧程序兼容测试。"""
import copy
import sqlite3
import unittest

from database_migration_contract import load_registry, registry_contract, validate_registry
from database_migrations import apply_migrations, migration_plan, schema_checksum
from pathlib import Path
from agy_environment_schema import initialize_agy_environment_schema
from database_schema import initialize_bench_schema


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
        self.assertEqual(second['current_version'], len(self.registry['steps']))
        self.assertEqual(self.database.execute('SELECT COUNT(*) FROM system_schema_migrations').fetchone()[0], len(self.registry['steps']))
        self.assertEqual(self.database.execute('SELECT profile_path FROM accounts').fetchone()[0], 'profiles/synthetic')

    def test_node_execution_increment_preserves_previous_ledger_and_old_program_writes(self) -> None:
        """节点增量独立追加，前两步台账及旧程序账号读写继续保留。:return: None。"""
        previous = {**self.registry, 'steps': self.registry['steps'][:2]}
        apply_migrations(self.database, registry=previous)
        markers = [tuple(row) for row in self.database.execute('SELECT * FROM system_schema_migrations ORDER BY version')]
        with self.database:
            self.database.execute("INSERT INTO accounts(name,profile_path) VALUES('old-node','profiles/old-node')")
        result = apply_migrations(self.database)
        self.assertEqual(len(self.registry['steps']), result['current_version'])
        self.assertEqual(markers, [tuple(row) for row in self.database.execute('SELECT * FROM system_schema_migrations WHERE version<=2 ORDER BY version')])
        current = [tuple(row) for row in self.database.execute('SELECT * FROM system_schema_migrations ORDER BY version')]
        apply_migrations(self.database)
        self.assertEqual(current, [tuple(row) for row in self.database.execute('SELECT * FROM system_schema_migrations ORDER BY version')])
        self.assertEqual('compatible_newer', apply_migrations(self.database, registry=previous)['state'])
        with self.database:
            self.database.execute("UPDATE accounts SET timezone='Europe/Paris' WHERE name='old-node'")
        self.assertEqual('Europe/Paris', self.database.execute("SELECT timezone FROM accounts WHERE name='old-node'").fetchone()[0])

    def test_registered_node_execution_index_damage_is_rejected(self) -> None:
        """迁移台账存在时仍检查会话活动索引，结构损坏阻止成功。:return: None。"""
        apply_migrations(self.database)
        self.database.execute('DROP INDEX idx_node_executions_active')
        with self.assertRaisesRegex(ValueError, '执行会话'):
            migration_plan(self.database)

    def test_add_table_column_index_and_backfill_with_version_two(self) -> None:
        """新增登记可真实建表、补列、索引并回填，旧程序保留后来的数据。@return None。"""
        baseline = {**self.registry, 'steps': self.registry['steps'][:1]}
        apply_migrations(self.database, registry=baseline)
        with self.database:
            self.database.execute("INSERT INTO accounts(name,profile_path) VALUES('synthetic','profiles/synthetic')")
        registry = copy.deepcopy(baseline)
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
        self.assertEqual(apply_migrations(self.database, registry=baseline)['state'], 'compatible_newer')
        self.assertEqual(self.database.execute('SELECT synthetic_note FROM accounts').fetchone()[0], 'retained')

    def test_failed_backfill_rolls_back_data_and_step_marker(self) -> None:
        """失败的数据回填事务保持原记录与原版本。@return None。"""
        baseline = {**self.registry, 'steps': self.registry['steps'][:1]}
        apply_migrations(self.database, registry=baseline)
        with self.database:
            self.database.execute("INSERT INTO accounts(name,profile_path) VALUES('synthetic','profiles/before')")
        registry = copy.deepcopy(baseline)
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
        self.assertEqual(migration_plan(self.database, registry=baseline)['current_version'], 1)
        self.assertNotIn('synthetic_failed', {row['name'] for row in self.database.execute('PRAGMA table_info(accounts)')})
        self.assertIsNone(self.database.execute("SELECT name FROM sqlite_master WHERE name='synthetic_failed_table'").fetchone())

    def test_modified_marker_or_definition_rejected(self) -> None:
        """历史登记与程序语义被改写时拒绝继续执行。@return None。"""
        apply_migrations(self.database)
        with self.database:
            self.database.execute("UPDATE system_schema_migrations SET checksum=?", ('c' * 64,))
        with self.assertRaisesRegex(ValueError, '摘要'):
            apply_migrations(self.database)

    def test_cluster_four_upgrade_keeps_assignments_and_adds_independent_agy_environment(self) -> None:
        """集群正式库追加 AGY 后保持原账号归属与旧程序兼容。@return 无。"""
        previous = {**self.registry, 'steps': self.registry['steps'][:4]}
        apply_migrations(self.database, registry=previous)
        with self.database:
            self.database.execute("INSERT INTO accounts(id,name,profile_path) VALUES(7,'cluster-old','profiles/old')")
            self.database.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json) "
                "VALUES('cluster-environment','cluster-old',7,'{}')")
        markers = [tuple(row) for row in self.database.execute('SELECT * FROM system_schema_migrations ORDER BY version')]
        assignments = [tuple(row) for row in self.database.execute('SELECT * FROM account_node_assignments')]
        self.assertEqual(5, apply_migrations(self.database, target=5)['current_version'])
        with self.database:
            self.database.execute("INSERT INTO account_environments(environment_id,name,fingerprint_json) "
                "VALUES('agy-environment','agy:7','{}')")
            self.database.execute("INSERT INTO platform_api_environments(gateway_account_id,environment_id,platform) "
                "VALUES(7,'agy-environment','antigravity')")
        self.assertEqual(markers, [tuple(row) for row in self.database.execute(
            'SELECT * FROM system_schema_migrations WHERE version<=4 ORDER BY version')])
        self.assertEqual(assignments, [tuple(row) for row in self.database.execute('SELECT * FROM account_node_assignments')])
        self.assertEqual('compatible_newer', apply_migrations(self.database, registry=previous)['state'])
        self.database.execute("UPDATE accounts SET timezone='Europe/Paris' WHERE id=7")
        self.database.commit()
        self.assertEqual(6, apply_migrations(self.database)['current_version'])
        self.assertEqual([(7, 1, 1, 'ready')], [tuple(row) for row in self.database.execute(
            'SELECT account_id,node_id,revision,phase FROM agy_node_assignments')])
        self.assertEqual('Europe/Paris', self.database.execute('SELECT timezone FROM accounts WHERE id=7').fetchone()[0])
        self.assertIsNone(self.database.execute("SELECT account_id FROM account_environments WHERE environment_id='agy-environment'").fetchone()[0])

    def test_divergent_agy_two_ledger_is_rejected_without_rewriting_data(self) -> None:
        """旧开发分支同号异身份台账保持失败关闭及完整原始数据。@return 无。"""
        legacy_step = {**self.registry['steps'][4], 'id': 'bench.agy-environments.2', 'version': 2, 'predecessor': 1}
        legacy = {**self.registry, 'steps': [self.registry['steps'][0], legacy_step]}
        runners = {'bench.baseline.1': (initialize_bench_schema, schema_checksum),
            'bench.agy-environments.2': (initialize_agy_environment_schema,
                lambda: schema_checksum(Path(__file__).with_name('agy_environment_schema.py')))}
        apply_migrations(self.database, registry=legacy, runners=runners)
        self.database.execute("INSERT INTO accounts(name,profile_path) VALUES('retained','profiles/retained')")
        self.database.commit()
        before = tuple(self.database.iterdump())
        with self.assertRaisesRegex(ValueError, '台账版本或摘要'):
            apply_migrations(self.database)
        self.assertEqual(before, tuple(self.database.iterdump()))

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
