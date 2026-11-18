"""校验数据库定义所有权及业务查询变化的合同稳定性。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from source_layout import source_path

from system_release import BENCH_SCHEMA_SOURCES, GATEWAY_SCHEMA_SOURCES, REPO, data_contracts
from verify_database_definitions import source_ownership, verify


class DatabaseDefinitionTests(unittest.TestCase):
    """用最小源码夹具检测漏登记和普通代码变更。"""

    def setUp(self) -> None:
        """复制固定迁移定义。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in (*BENCH_SCHEMA_SOURCES.values(), 'orchestrator/database-migration-registry.json',
                'cc2api/src/store/database-migration-registry.json', *GATEWAY_SCHEMA_SOURCES.values()):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path(REPO, name), target)

    def test_current_repository_has_complete_registered_definitions(self) -> None:
        """真实仓库必须通过CI入口，避免最小夹具遗漏新增定义。@return None。"""
        self.assertEqual('passed', verify(REPO)['status'])

    def test_incremental_definitions_require_unchanged_checksums(self) -> None:
        """目录及同步定义均绑定登记摘要，签发入口也拒绝漂移。@return None。"""
        for name in ('proxy_schema.rs', 'proxy_sync_schema.rs', 'session_policy_block_schema.rs'):
            with self.subTest(name=name):
                path = self.root / 'cc2api/src/store' / name
                original = path.read_text()
                path.write_text(original + '\nconst EXTRA: &str = "CREATE TABLE unexpected(id INT)";\n')
                with self.assertRaisesRegex(ValueError, '版本登记'):
                    verify(self.root)
                with self.assertRaisesRegex(ValueError, '版本登记'):
                    data_contracts(self.root)
                path.write_text(original)

    def test_incremental_owners_are_exact_paths_and_pure_definitions(self) -> None:
        """同名业务文件不能冒充所有者，增量定义不能依赖业务模块。@return None。"""
        path = self.root / 'cc2api/src/proxy_schema.rs'
        path.write_text('const Q: &str = "CREATE TABLE unexpected(id INT)";\n')
        self.assertEqual(['cc2api/src/proxy_schema.rs:1'], source_ownership(self.root))
        path.unlink()
        path = self.root / 'cc2api/src/store/proxy_schema.rs'
        path.write_text(path.read_text() + '\nuse crate::business::mutable_defaults;\n')
        self.assertEqual(['cc2api/src/store/proxy_schema.rs:1'], source_ownership(self.root))

    def test_unknown_registered_step_and_missing_source_are_rejected(self) -> None:
        """未知步骤与缺失定义都在发布材料生成前拒绝。@return None。"""
        registry = self.root / 'cc2api/src/store/database-migration-registry.json'
        original = registry.read_text()
        value = json.loads(original)
        latest = value['steps'][-1]['version']
        value['steps'].append({**value['steps'][-1], 'id': f'gateway.future.{latest + 1}', 'version': latest + 1, 'predecessor': latest})
        registry.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, '定义来源'):
            verify(self.root)
        registry.write_text(original)
        (self.root / 'cc2api/src/store/proxy_sync_schema.rs').unlink()
        with self.assertRaisesRegex(ValueError, '来源缺失'):
            verify(self.root)

    def test_business_queries_and_comments_preserve_contract(self) -> None:
        """普通查询、说明及测试代码保持合同稳定。@return None。"""
        before = data_contracts(self.root)
        (self.root / 'orchestrator/business.py').write_text('"""CREATE TABLE 文档示例"""\nQUERY="SELECT 1"\n')
        (self.root / 'cc2api/src/business.rs').write_text('// CREATE TABLE 示例\nconst Q: &str = "SELECT 1";\n#[cfg(test)]\nconst TEST: &str = "CREATE TABLE fixture(id INT)";\n')
        (self.root / 'cc2api/src/store/settings_store.rs').write_text('const DEFAULT_ALLOW_SYSTEM_ROLE_MODELS: &str = "synthetic-new-default";\n')
        self.assertEqual(verify(self.root)['status'], 'passed')
        self.assertEqual(data_contracts(self.root), before)

    def test_unregistered_ddl_and_modified_schema_are_rejected(self) -> None:
        """新增业务 DDL 和覆盖登记定义均阻断。@return None。"""
        python = self.root / 'orchestrator/business.py'
        rust = self.root / 'cc2api/src/business.rs'
        python.write_text('QUERY="CREATE TABLE foreign_table(id INT)"\n')
        rust.write_text('const Q: &str = r#"ALTER TABLE accounts ADD COLUMN foreign_field INT"#;\n')
        self.assertEqual(len(source_ownership(self.root)), 2)
        with self.assertRaisesRegex(ValueError, '未登记'):
            verify(self.root)
        python.unlink()
        rust.unlink()
        schema = self.root / 'orchestrator/database_schema.py'
        schema.write_text(schema.read_text() + '\nEXTRA_SCHEMA="CREATE TABLE later(id INT)"\n')
        with self.assertRaisesRegex(ValueError, '版本登记'):
            verify(self.root)

    def test_baseline_rejects_mutable_business_dependencies(self) -> None:
        """登记基线禁止间接引用后来会变更的业务默认值。@return None。"""
        schema = self.root / 'orchestrator/database_schema.py'
        schema.write_text(schema.read_text() + '\nfrom business_defaults import mutable_default\n')
        self.assertEqual(len(source_ownership(self.root)), 1)

    def test_views_triggers_and_chained_statements_require_registration(self) -> None:
        """视图、触发器和同一行后续结构语句属于迁移所有者。@return None。"""
        for statement in ('CREATE VIEW synthetic AS SELECT 1',
                'CREATE TRIGGER synthetic AFTER INSERT ON accounts BEGIN SELECT 1; END',
                'SELECT 1; CREATE TABLE synthetic(id INT)'):
            (self.root / 'orchestrator/business.py').write_text('QUERY=' + repr(statement) + '\n')
            self.assertEqual(len(source_ownership(self.root)), 1)


if __name__ == '__main__':
    unittest.main()
