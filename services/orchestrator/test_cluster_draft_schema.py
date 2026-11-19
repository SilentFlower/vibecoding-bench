"""NULL草稿节点增量的真实迁移事务、约束与历史引用保护。"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from cluster_store import ClusterStore
from database_migration_contract import load_registry
from database_migrations import apply_migrations, migration_plan
from node_login_draft_schema import initialize_node_login_draft_schema


class NodeLoginDraftSchemaTests(unittest.TestCase):
    """保留前三步台账，草稿期间保持NULL账号并保护实际节点引用。"""

    def setUp(self) -> None:
        """建立独立v3库，显式开启外键检查。:return: None。"""
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/'drafts.sqlite'
        self.connection=self.database()
        self.addCleanup(self.connection.close)
        self.registry=load_registry(Path(__file__).with_name('database-migration-registry.json'),'bench')
        self.previous={**self.registry,'steps':self.registry['steps'][:3]}
        apply_migrations(self.connection,registry=self.previous)
        self.markers=[tuple(row) for row in self.connection.execute('SELECT * FROM system_schema_migrations ORDER BY version')]
        with self.connection:
            self.node_id=self.connection.execute("INSERT INTO cluster_nodes(node_key,name,kind,config_json,created_at) "
                "VALUES(?,'草稿节点','ssh','{}',0)",('b'*32,)).lastrowid
            self.connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json) "
                "VALUES(?,'draft_only',NULL,'{}')",('e'*32,))
        self.store=ClusterStore(self.database,threading.Lock())

    def database(self):
        """打开仅本次合成库的连接。:return: 由调用方关闭的连接。"""
        connection=sqlite3.connect(self.path)
        connection.row_factory=sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def _insert(self, **changes):
        values={'environment_id':'e'*32,'node_id':self.node_id,'operation_id':'a'*32,'sid':'c'*12,
            'generation':'d'*32,'phase':'preparing','saved_account_id':None,'revision':1,
            'record_json':json.dumps({'fixture':'opaque-schema-only'}),'created_at':0,'updated_at':0,**changes}
        with self.connection:
            self.connection.execute('INSERT INTO node_login_drafts('+','.join(values)+') VALUES('
                +','.join('?' for _ in values)+')',tuple(values.values()))

    def test_version_four_preserves_old_markers_null_environment_and_old_program_writes(self) -> None:
        """追加第四步后原NULL环境和前三步身份保持，旧程序继续兼容账号写入。:return: None。"""
        result=apply_migrations(self.connection,target=4)
        self.assertEqual(4,result['current_version'])
        self.assertEqual(self.markers,[tuple(row) for row in self.connection.execute(
            'SELECT * FROM system_schema_migrations WHERE version<=3 ORDER BY version')])
        self.assertIsNone(self.connection.execute('SELECT account_id FROM account_environments').fetchone()[0])
        self.assertEqual(0,self.connection.execute('SELECT count(*) FROM accounts').fetchone()[0])
        self._insert()
        self.assertEqual('compatible_newer',apply_migrations(self.connection,registry=self.previous)['state'])
        with self.connection:
            self.connection.execute("INSERT INTO accounts(name,profile_path) VALUES('old_program','profiles/old_program')")
        self.assertEqual('local',self.connection.execute('SELECT n.node_key FROM account_node_assignments b '
            'JOIN cluster_nodes n ON n.id=b.node_id').fetchone()[0])
        current=[tuple(row) for row in self.connection.execute('SELECT * FROM system_schema_migrations ORDER BY version')]
        apply_migrations(self.connection,target=4)
        self.assertEqual(current,[tuple(row) for row in self.connection.execute('SELECT * FROM system_schema_migrations ORDER BY version')])

    def test_null_draft_scope_unique_operations_and_real_saved_account_reference(self) -> None:
        """草稿无需正式账号，原操作/SID唯一；保存后的引用只接受真实账号。:return: None。"""
        apply_migrations(self.connection)
        self._insert()
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert(operation_id='f'*32,sid='a'*12)
        with self.assertRaises(sqlite3.IntegrityError),self.connection:
            self.connection.execute("UPDATE node_login_drafts SET phase='invalid'")
        with self.assertRaises(sqlite3.IntegrityError),self.connection:
            self.connection.execute('UPDATE node_login_drafts SET saved_account_id=99')
        with self.connection:
            self.connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json) "
                "VALUES(?,'second_draft',NULL,'{}')",('f'*32,))
        for changes in ({'sid':'a'*12},{'operation_id':'f'*32}):
            with self.subTest(changes=changes),self.assertRaises(sqlite3.IntegrityError):
                self._insert(environment_id='f'*32,**changes)
        with self.connection:
            account_id=self.connection.execute("INSERT INTO accounts(name,profile_path,enabled) "
                "VALUES('saved','profiles/saved',0)").lastrowid
            self.connection.execute("UPDATE node_login_drafts SET saved_account_id=?,phase='submitting'",(account_id,))
        self.assertEqual(account_id,self.connection.execute('SELECT saved_account_id FROM node_login_drafts').fetchone()[0])
        self.assertIsNone(self.connection.execute("SELECT account_id FROM account_environments WHERE name='draft_only'").fetchone()[0])

    def test_node_and_environment_references_survive_closed_state_until_explicit_cleanup(self) -> None:
        """活动草稿阻止移除，关闭草稿在节点归档后仍可引用原环境和节点。:return: None。"""
        apply_migrations(self.connection)
        self._insert(phase='active')
        with self.assertRaisesRegex(ValueError,'登录草稿'):
            self.store.begin_removal(self.node_id,1)
        with self.connection:
            self.connection.execute("UPDATE node_login_drafts SET phase='closed'")
        _, removal = self.store.begin_removal(self.node_id,1)
        removal.update(phase='clearing_data', proof={'synthetic': True})
        self.store.save_removal(self.node_id, removal)
        self.store.save_removal(self.node_id, {**removal, 'state': 'completed', 'phase': 'completed'})
        with self.assertRaises(sqlite3.IntegrityError),self.connection:
            self.connection.execute('DELETE FROM account_environments WHERE environment_id=?',('e'*32,))
        self.assertEqual(self.node_id,self.connection.execute('SELECT node_id FROM node_login_drafts').fetchone()[0])
        self.assertIsNotNone(self.connection.execute('SELECT deleted_at FROM cluster_nodes WHERE id=?',(self.node_id,)).fetchone()[0])
        self.assertEqual({'e' * 32}, self.store.removed_draft_environments())

    def test_partial_ddl_failure_rolls_back_new_table_and_preserves_version_three(self) -> None:
        """第四步DDL中断不会留下半表或成功台账。:return: None。"""
        runners={step['id']:(Mock(side_effect=AssertionError('已完成的旧迁移不应重跑')),
            lambda checksum=step['checksum']:checksum) for step in self.previous['steps']}
        def fail(connection):
            """建立新结构后注入同一事务故障。:param connection: 本次连接。:return: 抛出合成故障。"""
            initialize_node_login_draft_schema(connection)
            raise RuntimeError('合成第四步DDL中断')
        runners['bench.node-login-drafts.4']=(fail,lambda:self.registry['steps'][3]['checksum'])
        with self.assertRaisesRegex(RuntimeError,'DDL中断'):
            apply_migrations(self.connection,target=4,runners=runners)
        self.assertIsNone(self.connection.execute("SELECT name FROM sqlite_master WHERE name='node_login_drafts'").fetchone())
        self.assertEqual(self.markers,[tuple(row) for row in self.connection.execute('SELECT * FROM system_schema_migrations ORDER BY version')])
        self.assertEqual(3,migration_plan(self.connection)['current_version'])

    def test_registered_draft_index_damage_is_rejected(self) -> None:
        """已登记库继续核对草稿恢复索引，损坏结构拒绝报告成功。:return: None。"""
        apply_migrations(self.connection)
        with self.connection:
            self.connection.execute('DROP INDEX idx_node_login_drafts_active')
        with self.assertRaisesRegex(ValueError,'登录草稿'):
            migration_plan(self.connection)

    def test_registered_draft_foreign_key_damage_is_rejected(self) -> None:
        """同列结构缺少原Node外键仍属于坏结构。:return: None。"""
        apply_migrations(self.connection)
        definition=self.connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='node_login_drafts'").fetchone()[0]
        indexes=[row[0] for row in self.connection.execute("SELECT sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name='node_login_drafts' AND sql IS NOT NULL")]
        with self.connection:
            self.connection.execute('DROP TABLE node_login_drafts')
            self.connection.execute(definition.replace('REFERENCES cluster_nodes(id)',''))
            for definition in indexes:
                self.connection.execute(definition)
        with self.assertRaisesRegex(ValueError,'外键'):
            migration_plan(self.connection)
