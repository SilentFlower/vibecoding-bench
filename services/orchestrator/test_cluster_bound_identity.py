"""绑定账号当前Node设备纯读取与原中央所有权消费者的范围回归。"""
from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cluster_bound_identity import BoundIdentityRead, RemoteBoundIdentity, read_bound_identity, read_bound_process
from cluster_service import ClusterService
from runtime_files import atomic_json
import test_cluster_execution as execution_fixture
import test_cluster_terminal_sessions as session_fixture
import test_credential_ownership as owner_fixture


class NodeBoundIdentityTests(unittest.TestCase):
    """真实Node SQLite、HOME及分配文件，Docker准备为显式替身。"""

    def setUp(self) -> None:
        """建立原绑定身份及已经准备的当前Node HOME。:return: None。"""
        fixture=execution_fixture.NodeExecutionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.executor=fixture,fixture.executor
        self.executor.prepare(fixture.request)
        self.home=fixture.root/'environments'/('e'*32)/'home/.claude.json'
        self.profile=fixture.root/'profiles/synthetic/.claude.json'
        self.top={'userID':'b'*64,'oauthAccount':{'accountUuid':'synthetic-uuid','organizationUuid':'synthetic-org',
            'emailAddress':'synthetic@example.invalid'},'accessToken':'synthetic-secret'}
        for path in (self.home,self.profile):
            atomic_json(path,self.top)
        self.request=BoundIdentityRead(node_key=fixture.node_key,account_id=1,gateway_account_id=7,
            environment_id='e'*32,assignment_revision=1,generation=1,version='2.1.293',
            account_identity=json.dumps({'account_id':1,'binding':7,'uuid':'synthetic-uuid','org':'synthetic-org'},sort_keys=True))

    def test_current_home_device_is_pure_and_never_returns_extra_material(self) -> None:
        """读取原HOME设备且保持无Docker、无运行时唤醒及无凭据返回。:return: None。"""
        with patch.object(self.executor,'_runtime',side_effect=AssertionError('纯读取不能创建运行时')):
            receipt=read_bound_identity(self.executor,self.request)
        self.assertEqual({'protocol':1,'request':self.request.model_dump(),'device_id':'b'*64},receipt)
        self.assertNotIn('synthetic-secret',json.dumps(receipt))
        self.assertEqual(self.top,json.loads(self.home.read_text()))

    def test_process_import_uses_current_node_runtime_and_original_identity(self) -> None:
        """实际Node账号和HOME核对后复用原采样器，纯设备读取保持独立。:return: None。"""
        runtime=Mock()
        payload={'device_id':'b'*64,'account_uuid':'synthetic-uuid','email':'synthetic@example.invalid',
            'environment_id':'e'*32,'cli_version':'2.1.293','canonical_process':{'node_sample':True}}
        runtime.process_identity_import_current.return_value=payload
        container=SimpleNamespace(status='running',reload=Mock())
        def acquire(snapshot):
            """只借用原运行时，保留已有Gateway配置。:return: 原运行时。"""
            self.assertEqual(0,snapshot.account_id)
            return runtime
        with patch.object(self.executor,'_runtime',side_effect=acquire), \
                patch.object(self.executor,'_release_runtime'), \
                patch('cluster_bound_identity.role_container',return_value=container):
            result=read_bound_process(self.executor,self.request)
        self.assertEqual(payload,result['process'])
        self.assertEqual('b'*64,result['device_id'])
        self.assertEqual('e'*32,runtime.process_identity_import_current.call_args.args[0]['environment_id'])
        self.assertEqual((container,'2.1.293'),runtime.process_identity_import_current.call_args.args[1:])

    def test_wrong_binding_generation_assignment_and_current_home_identity_are_rejected(self) -> None:
        """所有身份维度及当前HOME换号分别在读取前拒绝。:return: None。"""
        for changes in ({'gateway_account_id':8},{'generation':2},{'assignment_revision':2},{'node_key':'c'*32}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                read_bound_identity(self.executor,self.request.model_copy(update=changes))
        changed=json.loads(self.home.read_text())
        changed['oauthAccount']['accountUuid']='other-uuid'
        atomic_json(self.home,changed)
        with self.assertRaisesRegex(ValueError,'身份不一致'):
            read_bound_identity(self.executor,self.request)
        atomic_json(self.home,{**self.top,'userID':'c'*64})
        with self.assertRaisesRegex(ValueError,'设备身份'):
            read_bound_identity(self.executor,self.request)

    def test_gateway_identity_preserves_existing_case_and_optional_organization_rules(self) -> None:
        """原网关UUID忽略大小写并允许未登记组织，Node两份原身份保持一致。:return: None。"""
        identity=json.dumps({'account_id':1,'binding':7,'uuid':'  SYNTHETIC-UUID  ','org':None},sort_keys=True)
        receipt=read_bound_identity(self.executor,self.request.model_copy(update={'account_identity':identity}))
        self.assertEqual('b'*64,receipt['device_id'])
        changed=json.loads(self.profile.read_text())
        changed['oauthAccount']['organizationUuid']='other-org'
        atomic_json(self.profile,changed)
        with self.assertRaisesRegex(ValueError,'身份不一致'):
            read_bound_identity(self.executor,self.request.model_copy(update={'account_identity':identity}))


class CentralBoundIdentityTests(unittest.TestCase):
    """真实中央账号/分配与原所有者，Node传输采用白名单协议替身。"""

    def setUp(self) -> None:
        """建立真实中央绑定及固定配置。:return: None。"""
        fixture=session_fixture.TerminalSessionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.sessions=fixture,fixture.sessions
        self.remote=RemoteBoundIdentity(self.sessions,lambda account:'2.1.293')
        with self.sessions.service.store.database() as connection:
            self.account=dict(connection.execute('SELECT * FROM accounts WHERE id=1').fetchone())
        self.configuration={'account_id':7,'email':'synthetic@example.invalid','account_uuid':'synthetic-uuid','organization_uuid':'synthetic-org'}
        self.peer=Mock()
        self.sessions.service.connection=lambda node:self.peer
        self.peer.execution_environment.side_effect=lambda container,payload,operation:{'protocol':1,'node_key':payload['node_key'],
            'identity':{'protocol':1,'request':payload,'device_id':'b'*64}}

    def test_read_uses_original_binding_and_rechecks_central_assignment(self) -> None:
        """当前Node响应必须属于原绑定且读取前后归属一致。:return: None。"""
        result=self.remote.read(self.account,self.configuration)
        self.assertEqual({'device_id':'b'*64,'environment_id':'e'*32},result)
        self.assertEqual('account-bound-identity',self.peer.execution_environment.call_args.args[2])
        original=self.peer.execution_environment.side_effect
        def change(container,payload,operation):
            """在Node响应期间修改中央绑定。:return: 原响应。"""
            with self.sessions.service.store.database() as connection:
                connection.execute('UPDATE accounts SET cc2api_account_id=8 WHERE id=1')
            return original(container,payload,operation)
        self.peer.execution_environment.side_effect=change
        with self.assertRaisesRegex(ValueError,'中央账号已经变化'):
            self.remote.read(self.account,self.configuration)

    def test_wrong_node_and_malformed_device_keep_fixed_failure(self) -> None:
        """错误Node与含秘密的伪造设备回执都返回固定说明。:return: None。"""
        self.peer.execution_environment.return_value={'protocol':1,'node_key':'other'}
        self.peer.execution_environment.side_effect=None
        with self.assertRaisesRegex(ValueError,'其他Node'):
            self.remote.read(self.account,self.configuration)
        request,_,_=self.remote._request(self.account,self.configuration)
        self.peer.execution_environment.return_value={'protocol':1,'node_key':request.node_key,
            'identity':{'protocol':1,'request':request.model_dump(),'device_id':'synthetic-secret-device'}}
        with self.assertRaises(ValueError) as error:
            self.remote.read(self.account,self.configuration)
        self.assertNotIn('synthetic-secret',str(error.exception))

    def test_original_owner_uses_optional_node_device_without_local_home_fallback(self) -> None:
        """原长期重授权设备读取使用注入来源，节点失败保持原失败。:return: None。"""
        fixture=owner_fixture.CredentialOwnershipTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        account=fixture.account()
        fixture.ownership.read_bound_identity=Mock(return_value={'device_id':'b'*64,'environment_id':fixture.row['environment_id']})
        fixture.ownership.runtime._root=Mock(side_effect=AssertionError('原Node读取不能回退中央HOME'))
        profile,observed=fixture.ownership._bound_identity(account)
        self.assertEqual(fixture.remote['email'],profile['email'])
        self.assertEqual('b'*64,observed['device_id'])
        fixture.ownership.read_bound_identity.side_effect=ConnectionError('合成节点断连')
        with self.assertRaises(ConnectionError):
            fixture.ownership._bound_identity(account)

    def test_bound_login_preparation_preserves_binding_and_uses_cli_only_projection(self) -> None:
        """原中央准备固定CLI布局，Gateway原绑定和代理配置保留，Node投影始终无RT。:return: None。"""
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root=Path(temporary.name)
        service=ClusterService(self.sessions.service.store,root,Mock(),root/'sockets')
        self.addCleanup(service.close)
        with service.store.database() as connection:
            actual=dict(connection.execute('SELECT * FROM account_environments WHERE account_id=1').fetchone())
        actual.update(state='ready',isolation_version=2)
        runtime=SimpleNamespace(data=root,deployment='synthetic',release_id='synthetic-release',
            _row=lambda *args:actual,environment_lock=lambda environment:nullcontext())
        account={**self.account,'profile_path':'profiles/'+self.account['name']}
        atomic_json(root/account['profile_path']/'.credentials.json',{'claudeAiOauth':{
            'accessToken':'synthetic-central-at','refreshToken':'synthetic-central-rt','expiresAt':9999999999999}})
        peer=Mock()
        peer.prepare_environment.return_value={'environment':actual,'binding':None,'assignment_revision':1,
            'sender_address':'172.28.0.3'}
        service.connection=lambda node:peer
        gateway=Mock()
        gateway._request.return_value={**self.configuration,'auth_type':'oauth','status':'disabled','proxy_url':'socks5://fixture:1080'}
        receipt=service.prepare_remote_login(account,runtime,gateway,'original-identity','a'*12)
        self.assertEqual(actual,receipt['environment'])
        payload=peer.prepare_environment.call_args.args[1]
        self.assertEqual(7,payload['account']['cc2api_account_id'])
        self.assertEqual('a'*12,payload['login_sid'])
        self.assertTrue(payload['cli_only'])
        self.assertEqual('disabled',payload['gateway_config']['status'])
        self.assertNotIn('refreshToken',json.loads(payload['profile_files']['.credentials.json'])['claudeAiOauth'])
        gateway._request.assert_called_once_with('GET','/admin/runtime/accounts/7/config')
