"""中央草稿协调的实际Node管理协议、SQLite与原提交未知恢复。"""
from __future__ import annotations

import json
import threading
import time
import unittest
from uuid import uuid4
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from cluster_agent import create_node_app
from cluster_draft_login_runner import ClusterDraftLogins
from cluster_runtime_host import NodeRuntimeHost
from runtime_files import atomic_json
from test_cluster_draft_login import _DraftRuntime
import test_cluster_draft_login_store as root_fixture
import test_cluster_execution as node_fixture


class ClusterDraftLoginRunnerTests(unittest.TestCase):
    """两份实际SQLite、真实Node ASGI协议与Docker边界替身的完整协调。"""

    def setUp(self) -> None:
        """建立独立中央、Node和原部署活动门禁。:return: None。"""
        central=root_fixture.NodeLoginDraftStoreTests(methodName='runTest')
        central.setUp()
        self.addCleanup(central.doCleanups)
        node=node_fixture.NodeExecutionTests(methodName='runTest')
        node.setUp()
        self.addCleanup(node.doCleanups)
        self.central,self.node=central,node
        with central.connection:
            central.connection.execute('UPDATE cluster_nodes SET node_key=? WHERE id=?',(node.node_key,central.node_id))
        self.preparation=central.preparation.model_copy(update={'node_key':node.node_key})
        self.host=NodeRuntimeHost(node.executor,runtime_factory=_DraftRuntime)
        client=TestClient(create_node_app(node.executor,self.host,'b'*64,'synthetic-release'))
        client.__enter__()
        self.addCleanup(client.__exit__,None,None,None)
        self.loss=None
        self.calls=[]
        def execution(container,payload,operation):
            """消费真实Node HTTP/DTO并在已执行后注入响应丢失。:return: 原结果。"""
            self.calls.append(operation)
            result=client.post('/operations/'+operation,json=payload,headers={'x-v3-node-token':'b'*64}).json()
            if not result['ok']:
                raise ValueError('合成Node操作待核对：'+str(result))
            if self.loss==operation:
                self.loss=None
                raise ConnectionError('synthetic response lost after actual Node action')
            return result['result']
        self.peer=SimpleNamespace(execution_environment=execution,docker_socket=lambda:Path('/synthetic/docker.sock'))
        service=SimpleNamespace(store=central.store,connection=lambda node_id:self.peer,
            docker=lambda node_id:SimpleNamespace(api=SimpleNamespace(_version='1.45')))
        path=Path(central.connection.execute('PRAGMA database_list').fetchone()['file']).parent/'central-data'
        self.runtime=SimpleNamespace(data=path,deployment='synthetic')
        self.gate=SimpleNamespace(reserve=Mock(return_value='synthetic-activity'),
            restore_reserved=Mock(return_value='synthetic-restored-activity'),release_reserved=Mock())
        self.sessions=SimpleNamespace(service=service,runtime=self.runtime,activity_gate=self.gate,
            ledger=SimpleNamespace(release='synthetic-release'))
        self.owner_guard=threading.Lock()
        self.source=Mock()
        self.downloads=[]
        def download(environment_id,operation_id,filename,target,checksum,size):
            """仅替换Docker数据承载，保留真实文件与摘要验证。:return: None。"""
            self.downloads.append(filename)
            source=node.root/'node-draft-logins'/environment_id/operation_id/'authorization'/filename
            target.write_bytes(source.read_bytes())
            target.chmod(0o600)
        transport=patch('cluster_draft_login_runner.NodeArchiveTransfer',return_value=SimpleNamespace(download_login_document=download))
        transport.start()
        self.addCleanup(transport.stop)
        self.coordinator=self.new_coordinator()

    def mirror(self, name, documents):
        """写入真实中央管理副本并保留完整字段。:param name: 原名称。:param documents: 原文档。:return: None。"""
        for source,target in (('.claude.json','.claude.json'),('.claude/.credentials.json','.credentials.json'),
                ('.claude/settings.json','settings.json')):
            if source in documents:
                atomic_json(self.runtime.data/'profiles'/name/target,documents[source])

    def new_coordinator(self):
        """重建中央具体消费者，原私有文件与SQLite保持。:return: 草稿协调器。"""
        value=ClusterDraftLogins(self.sessions,lambda name:self.owner_guard,self.mirror,self.source,80,90)
        self.addCleanup(value.close)
        return value

    def ready(self):
        """启动后只查原执行回执，等待Node实际作业定位。:return: 原中央记录。"""
        row=self.coordinator.start(self.central.node_id,self.preparation)
        deadline=time.monotonic()+5
        while True:
            row=self.coordinator.ledger.get(row['operation_id'])
            receipt=self.coordinator._rpc(row,'get',row['record']['scope'])
            if receipt['phase']=='ready':
                return row
            self.assertLess(time.monotonic(),deadline,str(receipt))
            time.sleep(.01)

    def test_original_operation_starts_once_and_commits_complete_remote_account(self) -> None:
        """原配置/有限许可先持久，完整提交后仅原Node/真实ID启用一次。:return: None。"""
        row=self.ready()
        repeated=self.coordinator.start(self.central.node_id,self.preparation)
        self.assertEqual(row['operation_id'],repeated['operation_id'])
        self.assertEqual(row['record']['work'],repeated['record']['work'])
        self.assertEqual(1,self.host.runtime.begin_calls)
        delivered=self.coordinator.code(row['operation_id'],'f'*32,'synthetic-code')
        self.assertEqual('delivered',delivered['status'])
        self.assertEqual(delivered,self.coordinator.code(row['operation_id'],'f'*32,'synthetic-code'))
        self.host.runtime.send_login_code.assert_called_once()
        result=self.coordinator.commit(row['operation_id'])
        self.assertGreater(result['id'],0)
        self.assertEqual(result,self.coordinator.commit(row['operation_id']))
        self.assertEqual('committed',self.coordinator.status(row['operation_id'])['phase'])
        self.assertEqual({},self.coordinator.activities)
        self.source.assert_called_once_with(result['id'],self.preparation.work.version)
        account=self.central.connection.execute('SELECT * FROM accounts').fetchone()
        self.assertEqual(1,account['enabled'])
        self.assertEqual(self.central.node_id,self.central.store.assignment(result['id'])['node_id'])
        self.assertEqual(3,len(self.downloads))
        credentials=json.loads((self.runtime.data/'profiles'/account['name']/'.credentials.json').read_text())
        self.assertEqual({'preserved':True},credentials['unknown_credentials'])

    def test_recovery_does_not_restore_fresh_work_past_busy_owner_and_new_gate(self) -> None:
        """本进程新工作仍由原owner持有时，恢复轮询不能把它变为旧许可。:return: None。"""
        row=self.coordinator.ledger.begin(self.central.node_id,self.preparation)
        self.owner_guard.acquire()
        try:
            self.coordinator.recover_pending()
        finally:
            self.owner_guard.release()
        self.gate.restore_reserved.assert_not_called()
        self.assertEqual({},self.coordinator.activities)
        self.gate.reserve.side_effect=RuntimeError('synthetic deployment maintenance')
        self.coordinator.recover_pending()
        self.gate.restore_reserved.assert_not_called()
        self.assertEqual([],self.calls)
        self.assertEqual('reconcile',self.coordinator.ledger.get(row['operation_id'])['phase'])

    def test_actual_accept_response_lost_recovers_from_original_private_files_without_new_login(self) -> None:
        """Node实际接受后中央丢响应，重建只查原提交并读取原私有副本。:return: None。"""
        row=self.ready()
        self.loss='draft-login-accept'
        with self.assertRaises(ConnectionError):
            self.coordinator.commit(row['operation_id'])
        failed=self.coordinator.ledger.get(row['operation_id'])
        self.assertEqual('reconcile',failed['phase'])
        self.assertIsNone(failed['saved_account_id'])
        self.assertIsNotNone(failed['record']['files'])
        self.coordinator.close()
        restored=self.new_coordinator()
        restored.recover_pending()
        self.assertEqual('closed',restored.ledger.get(row['operation_id'])['phase'])
        self.assertEqual(1,self.host.runtime.begin_calls)
        self.assertEqual(3,len(self.downloads))
        self.assertEqual({},restored.activities)
        self.assertEqual(1,self.central.connection.execute('SELECT count(*) FROM accounts').fetchone()[0])

    def test_actual_activation_response_lost_keeps_disabled_real_id_until_recovery_finishes(self) -> None:
        """Node实际激活后丢响应，原正式ID保持disabled并沿同一操作完成来源收口。:return: None。"""
        row=self.ready()
        self.loss='draft-login-activate'
        with self.assertRaises(ConnectionError):
            self.coordinator.commit(row['operation_id'])
        failed=self.coordinator.ledger.get(row['operation_id'])
        self.assertGreater(failed['saved_account_id'],0)
        self.assertEqual(0,self.central.connection.execute('SELECT enabled FROM accounts').fetchone()[0])
        self.coordinator.close()
        restored=self.new_coordinator()
        restored.recover_pending()
        completed=restored.result(row['operation_id'])
        self.assertEqual(failed['saved_account_id'],completed['id'])
        self.assertEqual(1,self.central.connection.execute('SELECT enabled FROM accounts').fetchone()[0])
        self.assertEqual(1,self.host.runtime.begin_calls)
        self.assertEqual(1,self.host.runtime.stop_calls)

    def test_cancel_preserves_node_products_and_release_requires_actual_stop(self) -> None:
        """取消保留原Node授权产物，停止确认后释放原部署活动。:return: None。"""
        row=self.ready()
        self.host.runtime.cleanup_failure=True
        with self.assertRaises(ValueError):
            self.coordinator.cancel(row['operation_id'])
        self.assertIn(row['operation_id'],self.coordinator.activities)
        self.host.runtime.cleanup_failure=False
        self.coordinator.cancel(row['operation_id'])
        self.assertEqual('closed',self.coordinator.ledger.get(row['operation_id'])['phase'])
        product=self.node.root/'environments'/self.preparation.work.environment_id/'home/.v3-login'/self.preparation.work.sid/'.claude/.credentials.json'
        self.assertTrue(product.is_file())
        self.assertEqual({},self.coordinator.activities)

    def test_lost_prepare_recovers_scope_after_expiry_without_starting_authorization(self) -> None:
        """准备响应丢失且已过期时只恢复实际Scope并停止，原操作永久拒绝授权输入。:return: None。"""
        self.loss='draft-login-prepare'
        with self.assertRaises(ConnectionError):
            self.coordinator.start(self.central.node_id,self.preparation)
        row=self.coordinator.ledger.get(self.preparation.work.id)
        self.assertIsNone(row['record']['scope'])
        expired=self.preparation.work.expires_at+1
        with patch('cluster_draft_login.time.time',return_value=expired):
            self.coordinator.cancel(row['operation_id'])
        row=self.coordinator.ledger.get(row['operation_id'])
        self.assertEqual('closed',row['phase'])
        self.assertIsNotNone(row['record']['scope'])
        self.assertFalse(row['record']['start_intent'])
        self.assertEqual(0,self.host.runtime.begin_calls)
        self.assertEqual(0,self.host.runtime.recover_calls)
        self.assertEqual({},self.coordinator.activities)
        self.coordinator.delete(row['environment_id'],row['generation'])
        self.assertIsNone(self.coordinator.ledger.find(row['environment_id']))

    def test_prepare_never_reached_node_can_delete_without_creating_resources(self) -> None:
        """原准备尚未到Node时，清理只落外部墓碑并拒绝迟到准备，不创建角色。:return: None。"""
        original=self.peer.execution_environment
        def execution(container,payload,operation):
            """只丢弃原准备请求，其余仍使用真实Node协议。:return: 原结果。"""
            if operation=='draft-login-prepare':
                raise ConnectionError('synthetic prepare lost before Node')
            return original(container,payload,operation)
        with patch.object(self.peer,'execution_environment',side_effect=execution),self.assertRaises(ConnectionError):
            self.coordinator.start(self.central.node_id,self.preparation)
        self.assertIsNone(self.host.runtime)
        self.coordinator.delete(self.preparation.work.environment_id,self.preparation.work.draft_generation)
        self.assertEqual(0,self.host.runtime.begin_calls)
        self.assertEqual(0,self.host.runtime.recover_calls)
        receipt=self.coordinator.deletion(self.preparation.work.environment_id)
        self.assertEqual(0,receipt.scope.generation)
        with self.assertRaises(ValueError):
            original('synthetic-node',self.preparation.model_dump(),'draft-login-prepare')

    def test_new_preparation_missing_both_private_files_cleans_only_verified_closed_previous(self) -> None:
        """新代次私有文件尚未写入时，原已停止前代提供专属资源归属，清理不重启授权。:return: None。"""
        row=self.ready()
        self.coordinator.cancel(row['operation_id'])
        row=self.coordinator.ledger.get(row['operation_id'])
        sid=uuid4().hex[:12]
        work=self.preparation.work.model_copy(update={'id':uuid4().hex,'sid':sid,
            'draft_generation':uuid4().hex,'home':'/home/node/.v3-login/'+sid})
        preparation=type(self.preparation).model_validate({**self.preparation.model_dump(),'work':work.model_dump(),
            'previous':row['record']['scope']})
        current=self.coordinator.ledger.begin(row['node_id'],preparation,previous_revision=row['revision'])
        self.assertFalse(self.coordinator._preparation_path(current).exists())
        self.coordinator.delete(current['environment_id'],current['generation'])
        self.assertEqual(1,self.host.runtime.begin_calls)
        self.assertEqual(0,self.host.runtime.recover_calls)
        self.assertEqual('login-draft-preparation',self.coordinator.deletion(current['environment_id']).scope.role)
        self.assertEqual(0,self.central.connection.execute('SELECT count(*) FROM accounts').fetchone()[0])
