"""校验数据库定义所有权及业务查询变化的合同稳定性。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from system_release import REPO, data_contracts
from verify_database_definitions import source_ownership, verify


class DatabaseDefinitionTests(unittest.TestCase):
    """用最小源码夹具检测漏登记和普通代码变更。"""

    def setUp(self) -> None:
        """复制固定迁移定义。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ('orchestrator/database_schema.py', 'orchestrator/database-migration-registry.json',
                'cc2api/src/store/database_schema.rs', 'cc2api/src/store/database-migration-registry.json'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, target)

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
