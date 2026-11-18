"""真实双SQLite及私有文件的集群离线备份与组合恢复校验。"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import manage
from cluster_backup import backup_node
from database_migrations import apply_migrations
from runtime_files import atomic_json
from storage_backup import verify_cluster_backup


class ClusterBackupTests(unittest.TestCase):
    """保留当前Node RT、冻结归属、原维护状态与完成范围。"""

    def setUp(self) -> None:
        """准备同部署中央和Node，Docker只读停机检查使用明确替身。:return: None。"""
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.central,self.node=self.root/'central',self.root/'node'
        self.central.mkdir(mode=0o700)
        self.node.mkdir(mode=0o700)
        self.epoch='b'*32
        self.environment='e'*32
        self.key='a'*32
        atomic_json(self.central/'.v3-deployment.json',{'deployment':'synthetic'})
        atomic_json(self.node/'cluster-node.json',{'protocol':1,'deployment_id':'synthetic','node_key':self.key})
        (self.central/'bench').mkdir()
        self.central_db=self.central/'bench/db.sqlite'
        self.node_db=self.node/'node-execution.sqlite'
        for path in (self.central_db,self.node_db):
            with sqlite3.connect(path) as connection:
                connection.row_factory=sqlite3.Row
                apply_migrations(connection)
                connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(1,'fixture','profiles/fixture')")
                connection.execute('INSERT INTO account_environments(environment_id,name,account_id,generation,state,fingerprint_json) VALUES(?,?,?,?,?,?)',
                    (self.environment,'fixture',1,3,'ready','{}'))
        with sqlite3.connect(self.central_db) as connection:
            cursor=connection.execute("INSERT INTO cluster_nodes(node_key,name,kind,config_json,created_at) VALUES(?,'Node','ssh','{}',1)",(self.key,))
            connection.execute('UPDATE account_node_assignments SET node_id=?,revision=2 WHERE account_id=1',(cursor.lastrowid,))
        atomic_json(self.node/'environments'/self.environment/'runtime/node-assignment.json',{'protocol':1,'node_key':self.key,
            'account_id':1,'environment_id':self.environment,'revision':2,'phase':'ready'})
        self.credentials=self.node/'environments'/self.environment/'home/.claude/.credentials.json'
        atomic_json(self.credentials,{'claudeAiOauth':{'accessToken':'node-at','refreshToken':'node-current-rt','expiresAt':9999999999999},
            'unknown':{'preserved':True}})
        atomic_json(self.central/'bench/profiles/fixture/.credentials.json',{'claudeAiOauth':{'refreshToken':'central-stale-rt'}})
        self.client=SimpleNamespace(containers=SimpleNamespace(list=Mock(return_value=[])))
        self.node_target,self.central_target=self.root/'node-backup',self.root/'central-backup'

    def backup(self) -> None:
        """生成实际Node及中央离线完成快照。:return: None。"""
        backup_node(self.node,self.node_target,self.epoch,client=self.client)
        with patch.object(manage,'command',return_value=''),patch.object(manage,'inspect_images',return_value={
                'layout_version':2,'bridge_protocol':1,'release':'synthetic'}):
            manage.backup({'V3_DEPLOYMENT_ID':'synthetic','V3_DATA_ROOT':str(self.central)},self.central_target,
                full=True,cluster_epoch=self.epoch)

    def test_complete_cluster_restores_current_node_home_and_both_databases(self) -> None:
        """原Node当前RT及未知字段保留，组合恢复对应中央实际分配。:return: None。"""
        self.backup()
        result=verify_cluster_backup(self.central_target,[self.node_target])
        self.assertEqual(('passed',1,1,0),(result['status'],result['nodes'],result['environments'],result['reconcile_required']))
        copied=self.node_target/'data/environments'/self.environment/'home/.claude/.credentials.json'
        self.assertEqual('node-current-rt',json.loads(copied.read_text())['claudeAiOauth']['refreshToken'])
        self.assertTrue(json.loads(copied.read_text())['unknown']['preserved'])
        document=json.loads((self.node_target/'backup-files.json').read_text())
        self.assertIn('node-execution.sqlite',document['databases'])
        self.assertEqual('node-current-rt',json.loads(self.credentials.read_text())['claudeAiOauth']['refreshToken'])

    def test_central_only_snapshot_remains_valid_but_global_collection_requires_nodes(self) -> None:
        """中央快照可独立核验，集群范围必须收齐对应Node资料。:return: None。"""
        self.backup()
        self.assertEqual('passed',manage.verify_backup_data(self.central_target)['status'])
        with self.assertRaisesRegex(ValueError,'缺少'):
            verify_cluster_backup(self.central_target,[])

    def test_different_batch_and_incomplete_node_do_not_form_complete_cluster(self) -> None:
        """旧批次或缺完成标记的Node资料保持原备份，组合校验拒绝。:return: None。"""
        self.backup()
        other=self.root/'other-batch'
        backup_node(self.node,other,'c'*32,client=self.client)
        with self.assertRaisesRegex(ValueError,'批次'):
            verify_cluster_backup(self.central_target,[other])
        (self.node_target/'.v3-node-backup.json').unlink()
        with self.assertRaises(FileNotFoundError):
            verify_cluster_backup(self.central_target,[self.node_target])

    def test_pending_environment_is_preserved_and_reported_for_original_recovery(self) -> None:
        """原维护状态仍可保存完整快照，组合检查显式要求继续对账。:return: None。"""
        with sqlite3.connect(self.central_db) as connection:
            connection.execute("UPDATE account_node_assignments SET phase='reconcile' WHERE account_id=1")
        self.backup()
        result=verify_cluster_backup(self.central_target,[self.node_target])
        self.assertEqual(1,result['reconcile_required'])
        with sqlite3.connect(self.central_target/'data/bench/db.sqlite') as connection:
            self.assertEqual('reconcile',connection.execute('SELECT phase FROM account_node_assignments WHERE account_id=1').fetchone()[0])

    def test_running_node_refuses_backup_before_copying_data(self) -> None:
        """Node实际角色仍活动时，停止前检查保护原资料。:return: None。"""
        self.client.containers.list.return_value=[object()]
        with self.assertRaisesRegex(ValueError,'停机'):
            backup_node(self.node,self.node_target,self.epoch,client=self.client)
        self.assertFalse(self.node_target.exists())

    def test_running_independent_program_alone_refuses_backup(self) -> None:
        """控制与账号角色已停，独立验收仍运行时继续要求实际停机。:return: None。"""
        self.client.containers.list.side_effect=[[],[object()]]
        with self.assertRaisesRegex(ValueError,'独立验收'):
            backup_node(self.node,self.node_target,self.epoch,client=self.client)
        self.assertFalse(self.node_target.exists())
