"""草稿有限证明的真实私有文件、NULL投影、过期与正式身份隔离。"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from cluster_draft_login_contract import DraftLoginGrant
from cluster_draft_login_grants import DraftLoginGrants
from cluster_execution_grants import ExecutionGrants
from database_migrations import apply_migrations
from runtime_files import atomic_json


class DraftLoginGrantTests(unittest.TestCase):
    """草稿使用原有限证明状态机，所有输入继续依赖真实NULL环境与原逻辑代次。"""

    def setUp(self) -> None:
        """建立单个未绑定草稿和私有节点安装。:return: None。"""
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data=Path(temporary.name)
        self.path=self.data/'node.sqlite'
        self.node_key='b'*32
        atomic_json(self.data/'cluster-node.json',{'protocol':1,'node_key':self.node_key,'deployment_id':'synthetic'})
        connection=self.database()
        try:
            apply_migrations(connection)
            with connection:
                connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json,generation,state) "
                    "VALUES(?,'draft_only',NULL,'{}',2,'ready')",('e'*32,))
        finally:
            connection.close()
        self.now=1000
        self.grant=DraftLoginGrant(operation_id='a'*32,node_key=self.node_key,environment_id='e'*32,name='draft_only',
            draft_generation='d'*32,generation=2,source='login:'+'c'*12,not_after=1020)
        self.scope=self.grant.scope()
        self.marker={'protocol':1,'scope':self.scope.model_dump(),'phase':'ready'}
        self.root=self.data/'environments'/self.scope.environment_id
        atomic_json(self.root/'runtime/node-draft-login.json',self.marker)
        self.grants=DraftLoginGrants(self.data,self.node_key,'synthetic',self.database,lambda:self.now)

    def database(self):
        """打开本次合成Node库。:return: 由调用方关闭的连接。"""
        connection=sqlite3.connect(self.path)
        connection.row_factory=sqlite3.Row
        return connection

    def test_prepared_and_single_start_are_durable_and_formal_proofs_keep_separate_directory(self) -> None:
        """草稿证明不产生正式ID，重复认领必须查询原工作。:return: None。"""
        original=self.grants.create(self.grant)
        self.assertEqual(original,self.grants.create(self.grant))
        self.assertEqual('active',self.grants.activate(self.scope)['phase'])
        with self.assertRaises(ValueError):
            self.grants.activate(self.scope)
        restored=DraftLoginGrants(self.data,self.node_key,'synthetic',self.database,lambda:self.now)
        self.assertEqual(self.grant,restored.authorize(self.scope))
        self.assertTrue((self.data/'node-draft-login-grants'/self.scope.environment_id/(self.scope.operation_id+'.json')).is_file())
        self.assertFalse((self.data/'node-execution-grants').exists())
        with self.assertRaises((ValueError,FileNotFoundError)):
            ExecutionGrants(self.data,self.node_key,'synthetic',self.database).create(self.grant)

    def test_only_monotonic_renewal_within_original_35_seconds_is_accepted(self) -> None:
        """序号与截止只允许单调续接，同次响应丢失可以查询或重读原证明。:return: None。"""
        self.grants.create(self.grant)
        self.grants.activate(self.scope)
        newer=self.grant.model_copy(update={'sequence':2,'not_after':1030})
        renewed=self.grants.renew(newer)
        self.assertEqual(renewed,self.grants.renew(newer))
        for candidate in (self.grant,newer.model_copy(update={'sequence':4}),
                newer.model_copy(update={'sequence':3,'not_after':1029}),
                newer.model_copy(update={'sequence':3,'not_after':1036})):
            with self.subTest(candidate=candidate),self.assertRaises(ValueError):
                self.grants.renew(candidate)
        self.assertEqual(newer,self.grants.authorize(self.scope))

    def test_expiry_and_closed_proof_keep_stop_history_without_new_input(self) -> None:
        """过期只关闭新输入，实际停止由具体Actor核对，关闭墓碑保持持久。:return: None。"""
        self.grants.create(self.grant)
        self.grants.activate(self.scope)
        self.now=1021
        with self.assertRaises(ValueError):
            self.grants.authorize(self.scope)
        with self.assertRaisesRegex(ValueError,'实际作业'):
            self.grants.renew(self.grant.model_copy(update={'sequence':2,'not_after':1040}))
        closed=self.grants.close(self.scope,'node_execution_closed')
        self.assertEqual('closed',closed['phase'])
        self.assertEqual(closed,self.grants.get(self.scope))
        self.now=1000
        with self.assertRaises(ValueError):
            self.grants.create(self.grant)

    def test_changed_marker_sid_generation_or_node_cannot_authorize_original_proof(self) -> None:
        """逻辑范围与真实代次均冻结，新SID或跨节点不继承原授权。:return: None。"""
        self.grants.create(self.grant)
        self.grants.activate(self.scope)
        for change in ({'generation':3},{'source':'login:'+'f'*12},{'node_key':'f'*32},{'draft_generation':'f'*32}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.grants.authorize(self.scope.model_copy(update=change))
        atomic_json(self.root/'runtime/node-draft-login.json',{**self.marker,'protocol':True})
        with self.assertRaises(ValueError):
            self.grants.authorize(self.scope)
        self.assertEqual('active',self.grants.get(self.scope)['phase'])

    def test_formal_or_soft_deleted_profile_reference_rejects_new_input(self) -> None:
        """独立NULL身份只在无正式/软删除profile引用时有效。:return: None。"""
        self.grants.create(self.grant)
        self.grants.activate(self.scope)
        connection=self.database()
        try:
            with connection:
                connection.execute("INSERT INTO accounts(name,profile_path,enabled,deleted_at) VALUES('other','profiles/draft_only',0,1)")
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError,'正式或软删除'):
            self.grants.authorize(self.scope)
        self.assertEqual('closed',self.grants.close(self.scope,'node_execution_closed')['phase'])

    def test_actual_environment_id_claim_or_generation_change_rejects_proof(self) -> None:
        """正式认领与实际代次变化均使原草稿证明失效。:return: None。"""
        self.grants.create(self.grant)
        self.grants.activate(self.scope)
        connection=self.database()
        try:
            for sql in ('UPDATE account_environments SET generation=3','UPDATE account_environments SET generation=2,account_id=17'):
                with self.subTest(sql=sql):
                    with connection:
                        connection.execute(sql)
                    with self.assertRaises(ValueError):
                        self.grants.authorize(self.scope)
        finally:
            connection.close()
        self.assertEqual('active',self.grants.get(self.scope)['phase'])

    def test_formal_assignment_or_migration_fence_blocks_nullable_scope(self) -> None:
        """新增正式归属和迁移隔离标记不会被草稿许可绕过。:return: None。"""
        self.grants.create(self.grant)
        self.grants.activate(self.scope)
        for name in ('node-assignment.json','node-fence.json'):
            path=self.root/'runtime'/name
            atomic_json(path,{'synthetic':'conflict'})
            try:
                with self.subTest(name=name),self.assertRaises(ValueError):
                    self.grants.authorize(self.scope)
            finally:
                path.unlink()
