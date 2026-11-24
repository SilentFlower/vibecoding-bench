"""原CredentialOwnership经实际Node HTTP、双SQLite和原发布器完成交接。"""
from __future__ import annotations

import json
import shutil
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from fastapi.testclient import TestClient

import main
import test_cluster_nodes as node_config_fixture
import test_cluster_owner_node as node_fixture
import test_credential_ownership as owner_fixture
from cluster_agent import create_node_app
from cluster_bound_identity import RemoteBoundIdentity
from cluster_credential_refresh import RemoteCredentialRefresh
from cluster_execution_store import NodeExecutions
from cluster_nodes import NodeConfiguration
from cluster_owner_runner import RemoteOwnerTransitions
from cluster_runtime_host import NodeRuntimeHost
from cluster_store import ClusterStore
from runtime_files import atomic_json


class RemoteOwnerTests(unittest.TestCase):
    """纯传输故障替身，原所有权协调、Node协议和文件发布保持真实。"""

    def setUp(self) -> None:
        """建立原正式账号及同身份Node实际布局。:return: None。"""
        root=owner_fixture.CredentialOwnershipTests(methodName='runTest')
        root.setUp()
        self.addCleanup(root.doCleanups)
        node=node_fixture.NodeOwnerTests(methodName='runTest')
        node.setUp()
        self.addCleanup(node.doCleanups)
        config=node_config_fixture.ClusterNodeTests(methodName='runTest')
        config.setUp()
        self.addCleanup(config.doCleanups)
        self.root,self.node=root,node
        store=ClusterStore(main.get_db,main._db_lock)
        registered=store.create(node.executor.node_key,NodeConfiguration.model_validate(config.config))
        self.node_id=registered['id']
        assigned=store.assign_unstarted(1,self.node_id,1)
        with main.get_db() as connection:
            connection.execute('UPDATE cluster_nodes SET preparation_json=? WHERE id=?',
                (json.dumps({'state':'prepared','release':'synthetic'}),self.node_id))
            connection.execute('UPDATE account_environments SET environment_id=?,generation=? WHERE account_id=1',
                (node.row['environment_id'],node.row['generation']))
        root.row.update(environment_id=node.row['environment_id'],generation=node.row['generation'])
        profile=node.executor.data/'profiles/fixture'
        node.profile.rename(profile)
        node.profile=profile
        with node.executor.database() as connection:
            connection.execute("UPDATE accounts SET name='fixture',profile_path='profiles/fixture' WHERE id=1")
            connection.execute("UPDATE account_environments SET name='fixture' WHERE account_id=1")
        node.row['name']='fixture'
        atomic_json(node.runtime._root(node.row)/'runtime/node-assignment.json',{'protocol':1,'node_key':node.executor.node_key,
            'account_id':1,'environment_id':node.row['environment_id'],'revision':assigned['revision'],'phase':'ready'})
        top=json.loads((root.root/'profiles/fixture/.claude.json').read_text())
        for path in (profile/'.claude.json',node.home/'.claude.json'):
            atomic_json(path,top)
        for path in (profile/'.credentials.json',node.home/'.claude/.credentials.json'):
            atomic_json(path,{'unknown':{'preserved':True},'claudeAiOauth':{'accessToken':root.tokens['access_token'],
                'expiresAt':root.tokens['expires_at']}})
        host=NodeRuntimeHost(node.executor)
        self.addCleanup(host.close)
        client=TestClient(create_node_app(node.executor,host,token='b'*64,release='synthetic'))
        self.addCleanup(client.close)
        node.executor._runtime=Mock(return_value=node.runtime)
        node.executor._release_runtime=Mock()
        self.loss=None
        self.calls=[]
        def execution(container,payload,operation):
            """只在实际Node操作完成之后注入响应丢失。:return: 原实际HTTP回执。"""
            self.calls.append(operation)
            response=client.post('/operations/'+operation,json=payload,headers={'x-v3-node-token':'b'*64})
            value=response.json()
            if not value['ok']:
                raise ValueError('合成Node交接失败：'+str(value))
            if self.loss==operation:
                self.loss=None
                raise ConnectionError('synthetic response lost after actual owner action')
            return value['result']
        self.gateway_lease=None
        original=root.gateway._request.side_effect
        def gateway(method,path,payload=None):
            """仅为原所有权夹具补真实短期lease字段。:return: 原长期回执或实际有限许可。"""
            if path.endswith('/config'):
                return {**original(method,path,payload),'account_id':7}
            if not path.endswith('/lease'):
                return original(method,path,payload)
            if method=='POST' and payload['operation']=='prepare':
                self.gateway_lease={'owner':payload['owner'],'generation':'synthetic-central-real-lease',
                    'expires_at':int(time.time())+30,'exclusive':True,'shared_cli':False}
            elif method=='POST' and payload['operation']=='release':
                self.gateway_lease=None
            return {'active':0,'waiting':0,'lease':self.gateway_lease}
        root.gateway._request.side_effect=gateway
        service=SimpleNamespace(store=store,connection=lambda node_id:SimpleNamespace(execution_environment=execution))
        self.sessions=SimpleNamespace(runtime=root.runtime,service=service,gateway=root.gateway,
            ledger=NodeExecutions(store,'synthetic'))
        root.runtime.release_id='synthetic'
        self.remote=RemoteOwnerTransitions(self.sessions,root.ownership,main._read_bench_profile_identity)
        root.ownership.transition=self.remote.transition
        root.ownership.read_bound_identity=RemoteBoundIdentity(self.sessions,lambda account:'2.1.293').read
        self.credentials=RemoteCredentialRefresh(self.sessions,root.ownership,main._oauth_owner_lock,
            main._quota_identity,lambda account:'2.1.293')
        root.ownership.read_material=self.credentials.read_material
        root.ownership.identity=main._v3_cli_identity
        root.ownership.read_identity=main._v3_cli_identity_readonly
        root.ownership.matched_identity=main._v3_matched_cli_identity
        for name,value in {'account_runtime':root.runtime,'cluster_service':service,
                'cluster_runner':SimpleNamespace(credentials=self.credentials,owners=self.remote),
                '_resolve_account_cli_version':lambda account,version=None:(version or '2.1.293','synthetic')}.items():
            guard=patch.object(main,name,value)
            guard.start()
            self.addCleanup(guard.stop)

    def test_original_detach_then_rotated_node_home_returns_to_same_gateway(self) -> None:
        """原HTTP协议消费Node权威HOME，完整解绑和回交保持原Gateway ID与AT-only。:return: None。"""
        with patch.object(self.root.runtime,'_root',side_effect=AssertionError('禁止中央HOME')):
            self.root.ownership.detach(self.root.account())
            self.assertIsNone(self.root.account()['cc2api_account_id'])
            path=self.node.home/'.claude/.credentials.json'
            value=json.loads(path.read_text())
            value['claudeAiOauth'].update(accessToken='node-rotated-at',refreshToken='node-rotated-rt')
            atomic_json(path,value)
            self.root.receipt=None
            self.root.ownership.associate(self.root.account(),'bind',7)
        self.assertEqual(7,self.root.account()['cc2api_account_id'])
        self.assertEqual('node-rotated-rt',self.root.tokens['refresh_token'])
        self.assertNotIn('refreshToken',json.loads(path.read_text())['claudeAiOauth'])
        self.assertEqual('gateway',self.root.ownership.state(1)['owner'])

    def test_prepare_and_publish_lost_responses_resume_same_original_operation(self) -> None:
        """准备或发布实际完成后响应丢失，原所有权回执接续同操作。:return: None。"""
        self.loss='credential-owner-prepare'
        with self.assertRaises(ConnectionError):
            self.root.ownership.detach(self.root.account())
        operation=self.root.ownership.state(1)['input']['operation_id']
        self.loss='credential-owner-publish'
        with self.assertRaises(ConnectionError):
            self.root.ownership.resume(self.root.account())
        self.assertIsNone(self.root.account()['cc2api_account_id'])
        self.root.ownership.resume(self.root.account())
        self.assertEqual(operation,self.root.ownership.state(1)['input']['operation_id'])
        self.assertEqual('ready',self.root.ownership.state(1)['phase'])
        self.assertIsNone(self.gateway_lease)

    def test_paused_node_allows_original_handoff_to_finish(self) -> None:
        """暂停接单保持原交接收尾入口可用。:return: None。"""
        self.loss='credential-owner-prepare'
        with self.assertRaises(ConnectionError):
            self.root.ownership.detach(self.root.account())
        with main.get_db() as connection:
            connection.execute('UPDATE cluster_nodes SET enabled=0 WHERE id=?',(self.node_id,))
        self.root.ownership.resume(self.root.account())
        self.assertEqual('ready',self.root.ownership.state(1)['phase'])

    def test_paused_node_allows_fresh_explicit_detach_without_starting_work(self) -> None:
        """暂停接单仍允许纯设备读取和显式解绑，Node保持停止。:return: None。"""
        with main.get_db() as connection:
            connection.execute('UPDATE cluster_nodes SET enabled=0 WHERE id=?',(self.node_id,))
        self.root.ownership.detach(self.root.account())
        self.assertEqual('ready',self.root.ownership.state(1)['phase'])
        self.assertFalse(any(call.endswith('-start') for call in self.calls))

    def test_retirement_confirms_node_before_central_account_deletion(self) -> None:
        """原退休先收口Node，随后中央级联删分配可正常完成。:return: None。"""
        self.root.ownership.retire(self.root.account())
        with self.remote.transition(self.root.account(),None,handoff_credentials=False):
            with main.get_db() as connection:
                connection.execute('DELETE FROM accounts WHERE id=1')
        with self.node.executor.database() as connection:
            self.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=1').fetchone()[0])

    def test_delete_independent_account_before_first_node_preparation(self) -> None:
        """正式账号尚无Node资料时，删除只建立停用退休投影。:return: None。"""
        environment=self.root.row['environment_id']
        with main.get_db() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
            connection.execute('DELETE FROM account_credential_ownerships WHERE account_id=1')
            connection.execute("UPDATE account_environments SET generation=0,container_id=NULL,network_container_id=NULL,sender_container_id=NULL,state='stopped' WHERE account_id=1")
        with self.node.executor.database() as connection:
            connection.execute('DELETE FROM account_environments WHERE account_id=1')
            connection.execute('DELETE FROM accounts WHERE id=1')
        shutil.rmtree(self.node.executor.data/'environments'/environment)
        shutil.rmtree(self.node.profile)
        with patch.object(main,'_require_oauth_owner_transition_idle'):
            result=main.delete_account(1)
        self.assertTrue(result['deleted'])
        with self.node.executor.database() as connection:
            self.assertEqual((None,0),tuple(connection.execute('SELECT cc2api_account_id,enabled FROM accounts WHERE id=1').fetchone()))
            self.assertEqual((0,'retired',None),tuple(connection.execute('SELECT generation,state,account_id FROM account_environments WHERE environment_id=?',(environment,)).fetchone()))
        self.assertFalse((self.node.executor.data/'environments'/environment/'home').exists())

    def test_manual_disabled_account_can_enter_idle_migration_guard_without_enabling(self) -> None:
        """管理迁移可读取停用账号，原普通准入继续按停用处理。:return: None。"""
        with main.get_db() as connection:
            connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
            self.assertIsNone(main._get_available_account(connection,1))
        with patch.object(main,'_require_oauth_owner_transition_idle'):
            with main._node_migration_guard(1) as (account,environment):
                self.assertEqual(0,account['enabled'])
                self.assertEqual(self.root.row['environment_id'],environment['environment_id'])
        with main.get_db() as connection:
            self.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=1').fetchone()[0])

    def test_full_identity_import_samples_node_and_keeps_central_home_closed(self) -> None:
        """创建所需完整环境来自Node原采样器，中央只接收原公开字段。:return: None。"""
        self.root.ownership.detach(self.root.account())
        service=self.sessions.service
        service.prepare_remote_cli=Mock()
        container=SimpleNamespace(status='running',reload=Mock(),exec_run=Mock(return_value=SimpleNamespace(
            exit_code=0,output=json.dumps({'platform_raw':'linux','arch':'x64','node_version':'v22.0.0',
                'linux_distro_id':'synthetic','linux_distro_version':'1','linux_kernel':'synthetic-node-kernel'}).encode())))
        with patch.object(self.node.runtime,'_container',return_value=container), \
                patch.object(self.node.runtime,'process_import',return_value={'synthetic_node_metrics':True}), \
                patch.object(self.root.runtime,'_root',side_effect=AssertionError('禁止中央HOME')):
            observed=main._v3_cli_identity(self.root.account())
        self.assertEqual('synthetic-node-kernel',observed['canonical_env']['linux_kernel'])
        self.assertEqual('d'*64,observed['device_id'])
        self.assertEqual({'synthetic_node_metrics':True},observed['canonical_process'])
        service.prepare_remote_cli.assert_called_once()

    def test_deleted_gateway_binding_uses_complete_missing_proof_and_original_node(self) -> None:
        """旧Gateway明确删除后，原完整缺失证明允许交接Node HOME。:return: None。"""
        original=self.root.gateway._request.side_effect
        def gateway(method,path,payload=None):
            """对原旧绑定返回明确404，完整账号集合另行核对。:return: 其它原回执。"""
            if path.endswith('/oauth-ownership') or path.endswith('/lease'):
                raise ValueError('原绑定已删除') from HTTPError(path,404,'原绑定不存在',{},None)
            return original(method,path,payload)
        self.root.gateway._request.side_effect=gateway
        self.root.gateway.list_accounts.side_effect=lambda **kwargs:[]
        self.root.ownership.detach(self.root.account())
        self.assertIsNone(self.root.account()['cc2api_account_id'])
        self.assertEqual('original-rt',json.loads((self.node.home/'.claude/.credentials.json').read_text())['claudeAiOauth']['refreshToken'])
        self.root.gateway.list_accounts.assert_called_with(require_complete=True)

    def test_unknown_gateway_lease_prepare_reuses_original_operation_owner(self) -> None:
        """真实短期prepare已生效而响应未知时，同操作可读取自己的许可。:return: None。"""
        original=self.root.gateway._request.side_effect
        lost=[True]
        def gateway(method,path,payload=None):
            """只丢原Gateway prepare之后的回包。:return: 原回执。"""
            value=original(method,path,payload)
            if path.endswith('/lease') and method=='POST' and payload['operation']=='prepare' and lost[0]:
                lost[0]=False
                raise ConnectionError('synthetic lease prepare response lost')
            return value
        self.root.gateway._request.side_effect=gateway
        with self.assertRaises(ConnectionError):
            self.root.ownership.detach(self.root.account())
        self.assertEqual('binding:'+self.root.ownership.state(1)['input']['operation_id'],self.gateway_lease['owner'])
        self.root.ownership.resume(self.root.account())
        self.assertIsNone(self.gateway_lease)
        self.assertEqual('ready',self.root.ownership.state(1)['phase'])
