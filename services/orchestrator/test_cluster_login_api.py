"""已有SSH账号重授权的真实ASGI、原所有权证明与故障恢复。"""
from __future__ import annotations

import hashlib
import asyncio
import json
import tempfile
import socket
import time
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

import main
from credential_ownership import CredentialOwnership
from runtime_files import atomic_json
import test_cluster_login_runner as login_fixture


class ClusterLoginApiTests(unittest.TestCase):
    """真实中央数据库、管理镜像与HTTP入口，节点传输采用显式替身。"""

    def setUp(self) -> None:
        """接入原公开登录入口及真实CredentialOwnership。:return: None。"""
        fixture=login_fixture.ClusterAccountLoginTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.logins,self.sessions=fixture,fixture.logins,fixture.sessions
        self.account,self.peer=fixture.account,fixture.peer
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        credentials=fixture.fixture.coordinator
        credentials.read_identity.return_value={'device_id':'b'*64,'account_uuid':'original-uuid',
            'environment_id':fixture.fixture.fixture.request.scope.environment_id,'source':'cli:2.1.293:config.userID'}
        credentials.read_material=Mock(side_effect=lambda account:{key:self.peer.material[key] for key in
            ('access_token','refresh_token','expires_at')})
        self.manager=main.LoginManager(Mock())
        for key,value in {'get_db':self.sessions.service.store.database,'account_runtime':self.sessions.runtime,
                'BENCH_DATA':self.root,'PROFILES_DIR':self.root/'profiles','cluster_logins':self.logins,
                'cluster_service':self.sessions.service,'cluster_runner':SimpleNamespace(credentials=credentials,project_io=None),
                'login_manager':self.manager,'continue_manager':None,'pi_owners':None,'V3_ENABLED':False,
                '_resolve_account_cli_version':lambda account,version=None:(version or '2.1.293','fixture')}.items():
            guard=patch.object(main,key,value)
            guard.start()
            self.addCleanup(guard.stop)
        self.owner=CredentialOwnership(self.sessions.runtime,Mock(),main.get_db,threading.Lock(),
            read_profile=main._read_bench_profile_identity,mirror=main._sync_cc2api_credentials_to_profile,
            mirror_locked=main._sync_cc2api_credentials_to_profile_locked,profile_lock=main._profile_lock,
            identity=Mock(),read_identity=main._v3_cli_identity_readonly,validate=Mock(),find=Mock(),idle=Mock(),
            available=Mock(),creation_payload=Mock(),refresh=Mock(),read_material=main._read_current_owner_material)
        guard=patch.object(main,'credential_ownership',self.owner)
        guard.start()
        self.addCleanup(guard.stop)
        credentials.ownership=self.owner
        self.logins.save_authorization=main._save_remote_login_authorization
        self.logins.admission=main._remote_login_admission
        self.profile=main.PROFILES_DIR/self.account['name']
        atomic_json(self.profile/'.claude.json',{'userID':'b'*64,'unknown_config':{'keep':True},
            'oauthAccount':{'emailAddress':'synthetic@example.invalid','accountUuid':'original-uuid'}})
        atomic_json(self.profile/'.credentials.json',{'unknown_credentials':{'keep':True},
            'claudeAiOauth':{'accessToken':'synthetic-old-at','refreshToken':'synthetic-old-rt','expiresAt':1}})
        self.client=TestClient(main.app)
        self.addCleanup(self.client.close)

    def _start(self) -> tuple[str,str]:
        response=self.client.post('/api/accounts/login/start',json={'name':self.account['name'],'force_reauth':True})
        self.assertEqual(200,response.status_code,response.text)
        sid=response.json()['session_id']
        session=self.manager.get(sid)
        self.assertIsNotNone(session.remote_operation)
        self.assertFalse(session.profile_dir.exists())
        return sid,session.remote_operation

    def _pending_owner(self, parent: dict) -> None:
        identity={'deployment_id':self.sessions.runtime.deployment,'environment_id':parent['environment_id'],
            'bench_account_id':1,'device_id':'b'*64,'email':'synthetic@example.invalid','account_uuid':'original-uuid',
            'organization_uuid':None}
        self.owner._save({'schema':1,'account_id':1,'remote_id':7,'owner':'local','phase':'reconcile','stage':'ready',
            'generation':'c'*32,'refresh_pending':True,'refresh_source':parent['source'],
            'input':{'protocol':1,'operation_id':'d'*32,'action':'prepare','direction':'return','identity':identity}})

    def test_public_code_receipt_and_commit_use_original_node_without_local_docker(self) -> None:
        """原HTTP入口读取Node认证并保存新证明，授权码回包丢失只查原收据。:return: None。"""
        sid,operation=self._start()
        status=self.client.get('/api/accounts/login/'+sid+'/status')
        self.assertEqual(200,status.status_code,status.text)
        self.assertTrue(status.json()['credentials_ready'])
        self.assertEqual('no-store',status.headers['cache-control'])
        self.peer.lost='account-login-code'
        response=self.client.post('/api/accounts/login/'+sid+'/code',json={'request_id':'a'*32,'code':'synthetic-auth-code'})
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual('delivered',response.json()['status'])
        self.assertNotIn('synthetic-auth-code',response.text)
        receipt=self.client.get('/api/accounts/login/'+sid+'/code/'+'a'*32)
        self.assertEqual(response.json(),receipt.json())
        self.assertEqual(1,self.peer.calls.count('account-login-code'))
        response=self.client.post('/api/accounts/login/'+sid+'/commit',json={'name':self.account['name']})
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(1,response.json()['id'])
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual('synthetic-new-rt',json.loads((self.profile/'.credentials.json').read_text())['claudeAiOauth']['refreshToken'])
        self.assertEqual('synthetic-tier',json.loads((self.profile/'.credentials.json').read_text())['claudeAiOauth']['subscriptionType'])
        self.assertTrue(json.loads((self.profile/'.claude.json').read_text())['unknown_config']['keep'])
        self.assertTrue(json.loads((self.profile/'.credentials.json').read_text())['unknown_credentials']['keep'])
        self.manager.client.containers.run.assert_not_called()
        self.assertEqual(response.json(),self.client.post('/api/accounts/login/'+sid+'/commit',json={'name':self.account['name']}).json())
        with main.get_db() as connection:
            proof=json.loads(connection.execute('SELECT record_json FROM local_credential_authorizations WHERE account_id=1').fetchone()[0])
        self.assertEqual('2.1.293',proof['cli_version'])
        self.assertEqual(hashlib.sha256(b'synthetic-new-rt').hexdigest(),proof['refresh_sha256'])
        self.assertNotIn('synthetic-new-rt',json.dumps(proof))

    def test_unknown_rt_is_replaced_only_by_same_operation_completed_authorization(self) -> None:
        """原未知RT父隔离及原所有权pending由完整新授权恢复，旧结果保留历史。:return: None。"""
        parent=self.fixture._parent()
        self._pending_owner(parent)
        sid,operation=self._start()
        self.assertTrue(self.owner.state(1)['refresh_pending'])
        self.peer.lost='account-login-accept'
        response=self.client.post('/api/accounts/login/'+sid+'/commit',json={'name':self.account['name']})
        self.assertEqual(503,response.status_code)
        self.assertEqual(2,len(self.sessions.ledger.active(1)))
        self.assertEqual('reconcile',self.sessions.ledger.get(operation)['phase'])
        self.assertFalse(self.owner.state(1)['refresh_pending'])
        self.manager=main.LoginManager(Mock())
        with patch.object(main,'login_manager',self.manager):
            self.assertEqual(operation,self.manager.get(sid).remote_operation)
            self.logins.recover_pending()
            response=self.client.post('/api/accounts/login/'+sid+'/commit',json={'name':self.account['name']})
            self.assertEqual(200,response.status_code,response.text)
        self.assertEqual([],self.sessions.ledger.active(1))
        self.assertEqual(1,self.peer.calls.count('account-login-start'))
        self.assertEqual('uncertain',self.sessions.ledger.get(parent['operation_id'])['record']['node_receipt']['outcome']['status'])

    def test_disabled_retired_independent_account_recovers_only_after_verified_new_authorization(self) -> None:
        """原退休独立账号先保持停用，完整新授权证明后恢复本地所有者与enabled。:return: None。"""
        with main.get_db() as connection:
            connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
            environment=connection.execute('SELECT environment_id FROM account_environments WHERE account_id=1').fetchone()[0]
        identity={'deployment_id':self.sessions.runtime.deployment,'environment_id':environment,'bench_account_id':1,
            'device_id':'b'*64,'email':'synthetic@example.invalid','account_uuid':'original-uuid','organization_uuid':None}
        self.owner._save({'schema':1,'account_id':1,'remote_id':7,'owner':'local','phase':'ready','stage':'ready',
            'generation':'c'*32,'retired':True,'input':{'protocol':1,'operation_id':'d'*32,'action':'prepare',
                'direction':'retire','identity':identity}})
        sid,operation=self._start()
        self.assertTrue(self.owner.state(1)['retired'])
        with main.get_db() as connection:
            self.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=1').fetchone()[0])
        response=self.client.post('/api/accounts/login/'+sid+'/commit',json={'name':self.account['name']})
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertFalse(self.owner.state(1)['retired'])
        self.assertEqual('ready',self.owner.state(1)['phase'])
        with main.get_db() as connection:
            self.assertEqual(1,connection.execute('SELECT enabled FROM accounts WHERE id=1').fetchone()[0])
            proof=json.loads(connection.execute('SELECT record_json FROM local_credential_authorizations WHERE account_id=1').fetchone()[0])
        self.assertEqual('2.1.293',proof['cli_version'])
        self.assertEqual(hashlib.sha256(b'synthetic-new-rt').hexdigest(),proof['refresh_sha256'])

    def test_original_business_admission_blocks_other_work_before_remote_prepare(self) -> None:
        """原业务活动拒绝明确登录，实际节点准备和启动仍保持零次。:return: None。"""
        with patch.object(main,'_oauth_owner_transition_blocker',return_value='原业务仍有活动工作'):
            response=self.client.post('/api/accounts/login/start',json={'name':self.account['name'],'force_reauth':True})
        self.assertEqual(400,response.status_code,response.text)
        self.sessions.service.prepare_remote_cli.assert_not_called()
        self.assertNotIn('account-login-start',self.peer.calls)

    def test_remote_cancel_keeps_unknown_parent_and_owner_pending(self) -> None:
        """取消尚无提交意图的新登录只清本次暂存，原未知RT保持隔离。:return: None。"""
        parent=self.fixture._parent()
        self._pending_owner(parent)
        sid,operation=self._start()
        response=self.client.delete('/api/accounts/login/'+sid)
        self.assertEqual(200,response.status_code,response.text)
        self.assertTrue(self.owner.state(1)['refresh_pending'])
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual('reconcile',self.sessions.ledger.get(parent['operation_id'])['phase'])

    def test_browser_disconnect_while_opening_closes_late_original_pty(self) -> None:
        """浏览器在SSH开连接途中取消时，迟到的原连接由开连接线程严格关闭。:return: None。"""
        sid,_=self._start()
        session=self.manager.get(sid)
        entered,release,closed=threading.Event(),threading.Event(),threading.Event()
        self.addCleanup(release.set)
        def open_original(operation):
            """暂停实际连接结果，模拟浏览器先关闭。:return: 可观察的原句柄。"""
            entered.set()
            release.wait(5)
            return SimpleNamespace(close=closed.set)
        async def exercise():
            with patch.object(self.logins,'open',side_effect=open_original):
                task=asyncio.create_task(main._remote_login_ws(AsyncMock(),session))
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                release.set()
                self.assertTrue(await asyncio.to_thread(closed.wait,2))
        asyncio.run(exercise())

    def test_actual_asgi_disconnect_always_closes_attached_output_socket(self) -> None:
        """真实ASGI取消发生在pump收口期间时，原输出socket仍严格关闭。:return: None。"""
        sid,_=self._start()
        raw,peer=socket.socketpair()
        raw.setblocking(False)
        self.addCleanup(raw.close)
        self.addCleanup(peer.close)
        with patch.object(self.logins,'open',return_value=raw):
            with self.client.websocket_connect('/api/accounts/login/ws/'+sid) as websocket:
                websocket.send_json({'type':'ping'})
                self.assertEqual({'type':'pong'},websocket.receive_json())
            deadline=time.monotonic()+2
            while raw.fileno()!=-1 and time.monotonic()<deadline:
                time.sleep(.01)
        self.assertEqual(-1,raw.fileno())
