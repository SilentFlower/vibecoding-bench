"""绑定SSH登录的真实管理HTTP、原Owner与SQLite集成；传输采用合成替身。"""
from __future__ import annotations

import copy
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import main
from credential_ownership import CredentialOwnership
from runtime_files import atomic_json
import test_cluster_bound_login_runner as bound_fixture


class _Gateway(bound_fixture._Gateway):
    """原所有权协议与导入的显式替身；实际Rust协议另做纵向验证。"""

    def __init__(self, peer, events) -> None:
        """建立可观察的原长期门禁。:param peer: Node替身。:param events: 顺序。:return: None。"""
        super().__init__(peer,events)
        self.ownership,self.receipt=None,None
        self.drop_prepare,self.drop_finish=False,False

    def _request(self, method, path, payload=None):
        if not path.endswith('/oauth-ownership'):
            return super()._request(method,path,payload)
        if method=='GET':
            return {'protocol':1,'ownership':copy.deepcopy(self.ownership)}
        action=payload['action']
        self.events.append('owner:'+action)
        if action=='prepare' and self.receipt is None:
            self.ownership={'identity':copy.deepcopy(payload['identity']),'operation_id':payload['operation_id'],
                'generation':payload['operation_id'],'owner':'gateway','phase':'reauth'}
            self.receipt={'operation_id':payload['operation_id'],'account_id':7,'identity':copy.deepcopy(payload['identity']),
                'generation':payload['operation_id'],'stage':'prepared'}
            self.owner=SimpleNamespace(receipt=self.receipt)
        if self.receipt and self.receipt['operation_id']!=payload['operation_id']:
            raise ValueError('合成原所有权操作已经变化')
        if action in ('finish','cancel'):
            if self.lease is not None or self.peer.value is not None and self.peer.value['phase']!='closed':
                raise AssertionError('原实际停止与lease释放应先于长期收口')
            self.receipt['stage']='committed' if action=='finish' else 'cancelled'
            self.ownership['phase']='ready'
        if action=='prepare' and self.drop_prepare or action=='finish' and self.drop_finish:
            self.drop_prepare=self.drop_finish=False
            raise ConnectionError('合成原长期动作已应用但响应丢失')
        operation=(self.receipt or {}).get('import_operation_id')
        return copy.deepcopy({'protocol':1,'ownership':self.ownership,'receipt':self.receipt,
            'credentials':self.imports.get(operation)})


class _Peer(bound_fixture._Peer):
    """补齐原HTTP状态与单次码回执，实际tmux由SSH用例验证。"""

    def __init__(self, events) -> None:
        """建立单次输入记录。:param events: 顺序。:return: None。"""
        super().__init__(events)
        self.codes={}

    def execution_environment(self, container, payload, operation):
        if operation not in ('account-bound-login-observe','account-bound-login-code','account-bound-login-code-receipt'):
            return super().execution_environment(container,payload,operation)
        self.calls.append(operation)
        if operation.endswith('-observe'):
            result={'phase':'ready_to_submit','credentials_ready':True,'reconnectable':True,
                'authorization_url':None,'expires_at':self.work['expires_at']}
        else:
            request_id=payload['request_id']
            if operation.endswith('-code'):
                self.codes.setdefault(request_id,{'request_id':request_id,'status':'delivered','message':'合成原终端已接收'})
            result=dict(self.codes[request_id])
        if self.lost==operation:
            self.lost=None
            raise ConnectionError('合成码已接收但响应丢失')
        return {'protocol':1,'node_key':self.work and self.value['scope']['node_key'],'login':result}


class ClusterBoundLoginApiTests(unittest.TestCase):
    """原管理入口与真实Owner一起覆盖绑定提交及未知恢复。"""

    def setUp(self) -> None:
        """建立临时真实DB与profile，实际Node/Gateway采用明确替身。:return: None。"""
        fixture=bound_fixture.ClusterBoundLoginTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.sessions,self.logins=fixture,fixture.sessions,fixture.logins
        self.peer=_Peer(fixture.events)
        self.gateway=_Gateway(self.peer,fixture.events)
        self.sessions.service.connection=lambda node:self.peer
        self.sessions.gateway=self.gateway
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.manager=main.LoginManager(Mock())
        for key,value in {'get_db':self.sessions.service.store.database,'account_runtime':self.sessions.runtime,
                'BENCH_DATA':self.root,'PROFILES_DIR':self.root/'profiles','cluster_logins':None,'cluster_bound_logins':self.logins,
                'cluster_service':self.sessions.service,'cluster_runner':SimpleNamespace(credentials=None,project_io=None),
                'login_manager':self.manager,'continue_manager':None,'pi_owners':None,'V3_ENABLED':False,
                '_resolve_account_cli_version':lambda account,version=None:(version or '2.1.293','fixture')}.items():
            guard=patch.object(main,key,value)
            guard.start()
            self.addCleanup(guard.stop)
        self.owner=CredentialOwnership(self.sessions.runtime,self.gateway,main.get_db,threading.Lock(),
            read_profile=main._read_bench_profile_identity,mirror=main._sync_cc2api_credentials_to_profile,
            mirror_locked=main._sync_cc2api_credentials_to_profile_locked,profile_lock=main._profile_lock,
            identity=Mock(),read_identity=Mock(),validate=Mock(),find=Mock(),idle=Mock(),available=Mock(),
            creation_payload=Mock(),refresh=Mock(),read_bound_identity=main._read_remote_bound_identity,
            reauth_idle=main._remote_reauth_idle,reauth_publish=main._remote_reauth_publish)
        guard=patch.object(main,'credential_ownership',self.owner)
        guard.start()
        self.addCleanup(guard.stop)
        self.logins.ownership=self.owner
        self.logins.credentials.ownership=self.owner
        self.logins.owner_lock=main._oauth_owner_lock
        self.logins.save_authorization=main._save_remote_bound_login_authorization
        self.logins.admission=main._remote_login_admission
        self.profile=main.PROFILES_DIR/fixture.account['name']
        atomic_json(self.profile/'.claude.json',{'userID':'b'*64,'unknown_config':{'keep':True},
            'oauthAccount':{'emailAddress':'synthetic@example.invalid','accountUuid':'original-uuid',
                'organizationUuid':'original-org','unknown_identity':'keep'}})
        atomic_json(self.profile/'.credentials.json',{'unknown_credentials':'keep','claudeAiOauth':
            {'accessToken':'synthetic-old-at','refreshToken':'synthetic-old-rt','expiresAt':1,'subscriptionType':'keep'}})
        with main.get_db() as connection:
            connection.execute("UPDATE accounts SET warmup_enabled=1,warmup_last_status='keep' WHERE id=1")
            connection.execute("INSERT INTO account_quota_states(account_id,identity,state_json,updated_at) VALUES(1,'original','{\"blocked\":true}',1)")
        self.client=TestClient(main.app)
        self.addCleanup(self.client.close)

    def _start(self):
        response=self.client.post('/api/accounts/login/start',json={'name':self.fixture.account['name'],'force_reauth':True})
        self.assertEqual(200,response.status_code,response.text)
        sid=response.json()['session_id']
        self.assertEqual(7,response.json()['cc2api_account_id'])
        return sid,self.manager.get(sid).remote_operation

    def _commit(self, sid):
        return self.client.post('/api/accounts/login/'+sid+'/commit',json={'name':self.fixture.account['name']})

    def test_public_bound_commit_preserves_original_device_policies_and_quota(self) -> None:
        """原HTTP登录、码回执与提交沿Node及Gateway，设备/策略/额度保留。:return: None。"""
        sid,operation=self._start()
        status=self.client.get('/api/accounts/login/'+sid+'/status')
        self.assertEqual(200,status.status_code,status.text)
        self.assertTrue(status.json()['credentials_ready'])
        self.assertEqual('no-store',status.headers['cache-control'])
        self.peer.lost='account-bound-login-code'
        response=self.client.post('/api/accounts/login/'+sid+'/code',json={'request_id':'c'*32,'code':'synthetic-auth-code'})
        self.assertEqual('delivered',response.json()['status'])
        self.assertEqual(response.json(),self.client.get('/api/accounts/login/'+sid+'/code/'+'c'*32).json())
        self.assertEqual(1,self.peer.calls.count('account-bound-login-code'))
        response=self._commit(sid)
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(7,response.json()['cc2api_account_id'])
        self.assertNotIn('synthetic-new-rt',response.text)
        self.assertEqual('ready',self.owner.state(1)['phase'])
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        oauth=json.loads((self.profile/'.credentials.json').read_text())['claudeAiOauth']
        top=json.loads((self.profile/'.claude.json').read_text())
        self.assertEqual('synthetic-new-rt',oauth['refreshToken'])
        self.assertEqual('keep',oauth['subscriptionType'])
        self.assertEqual('keep',top['oauthAccount']['unknown_identity'])
        self.assertEqual('b'*64,top['userID'])
        with main.get_db() as connection:
            account=connection.execute('SELECT * FROM accounts WHERE id=1').fetchone()
            self.assertEqual((1,1,'keep'),(account['enabled'],account['warmup_enabled'],account['warmup_last_status']))
            self.assertEqual(1,connection.execute('SELECT count(*) FROM account_quota_states WHERE account_id=1').fetchone()[0])
            self.assertEqual(0,connection.execute('SELECT count(*) FROM local_credential_authorizations').fetchone()[0])
        self.assertEqual(response.json(),self._commit(sid).json())

    def test_manually_disabled_bound_account_keeps_disabled_after_explicit_authorization(self) -> None:
        """人工停用账号可明确重新授权，原enabled和额度状态保持。:return: None。"""
        with main.get_db() as connection:
            connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
        sid,operation=self._start()
        response=self._commit(sid)
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        with main.get_db() as connection:
            self.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=1').fetchone()[0])
            self.assertEqual(1,connection.execute('SELECT count(*) FROM account_quota_states WHERE account_id=1').fetchone()[0])

    def test_import_and_accept_unknown_recover_with_original_owner_and_current_gateway_snapshot(self) -> None:
        """导入及Node清理响应未知均沿原操作恢复，当前Gateway RT只镜像中央。:return: None。"""
        sid,operation=self._start()
        self.gateway.drop_import=True
        self.assertEqual(503,self._commit(sid).status_code)
        self.assertEqual('reauth',self.owner.state(1)['phase'])
        self.gateway.imports[operation].update(access_token='gateway-current-at',refresh_token='gateway-current-rt')
        self.peer.lost='accept'
        self.logins.recover_pending()
        self.assertEqual('reconcile',self.sessions.ledger.get(operation)['phase'])
        self.assertFalse(self.peer.value['commit']['cleanup_pending'])
        self.assertEqual('submitting',self.client.get('/api/accounts/login/'+sid+'/status').json()['phase'])
        self.manager=main.LoginManager(Mock())
        with patch.object(main,'login_manager',self.manager):
            self.assertEqual(operation,self.manager.get(sid).remote_operation)
            self.logins.recover_pending()
            self.assertEqual(200,self._commit(sid).status_code)
        self.assertEqual('ready',self.owner.state(1)['phase'])
        self.assertEqual('gateway-current-at',self.peer.published['access_token'])
        self.assertNotIn('refresh_token',self.peer.published)
        self.assertEqual(1,self.gateway.import_count)
        self.assertEqual(1,self.peer.calls.count('account-bound-login-start'))

    def test_background_completed_login_releases_only_stale_in_memory_name(self) -> None:
        """后台原提交已完整关闭时，旧浏览器名称缓存应允许后续账号管理。:return: None。"""
        sid,operation=self._start()
        self.gateway.drop_import=True
        self.assertEqual(503,self._commit(sid).status_code)
        self.assertTrue(self.manager.has_active_name(self.fixture.account['name']))
        self.logins.recover_pending()
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        calls=list(self.peer.calls)
        self.assertFalse(self.manager.has_active_name(self.fixture.account['name']))
        self.assertEqual(calls,self.peer.calls)

    def test_background_unknown_cleanup_keeps_name_reserved(self) -> None:
        """实际清理回包仍未知时，后台维护保留名称占用。:return: None。"""
        sid,operation=self._start()
        self.gateway.drop_import=True
        self.assertEqual(503,self._commit(sid).status_code)
        self.peer.lost='accept'
        self.logins.recover_pending()
        self.assertNotEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertTrue(self.manager.has_active_name(self.fixture.account['name']))

    def test_cancel_frozen_unsubmitted_authorization_closes_real_owner_and_hides_aborted_session(self) -> None:
        """明确未导入的冻结授权由原fence取消，重建管理器不复活已销毁草稿。:return: None。"""
        sid,operation=self._start()
        row,request=self.logins._row(operation)
        self.logins._call(row,'commit',request.scope.model_dump())
        response=self.client.delete('/api/accounts/login/'+sid)
        self.assertEqual(200,response.status_code,response.text)
        self.assertTrue(self.peer.value['commit']['aborted'])
        self.assertEqual('ready',self.owner.state(1)['phase'])
        with patch.object(main,'login_manager',main.LoginManager(Mock())):
            self.assertEqual(404,self.client.get('/api/accounts/login/'+sid+'/status').status_code)

    def test_cancel_import_query_unknown_keeps_original_owner_and_material(self) -> None:
        """取消中的导入查询未知保持原长期门禁与冻结材料。:return: None。"""
        sid,operation=self._start()
        row,request=self.logins._row(operation)
        self.logins._call(row,'commit',request.scope.model_dump())
        self.gateway.query_unknown=True
        response=self.client.delete('/api/accounts/login/'+sid)
        self.assertEqual(503,response.status_code,response.text)
        self.assertEqual('reauth',self.owner.state(1)['phase'])
        self.assertTrue(self.peer.value['commit']['cleanup_pending'])

    def test_prepare_unknown_recovers_without_starting_node_or_reading_central_home(self) -> None:
        """长期prepare响应丢失保留原账本，恢复核对后取消原门禁。:return: None。"""
        self.gateway.drop_prepare=True
        response=self.client.post('/api/accounts/login/start',json={'name':self.fixture.account['name'],'force_reauth':True})
        self.assertEqual(500,response.status_code)
        self.logins.recover_pending()
        self.assertEqual([],self.sessions.ledger.pending())
        self.assertEqual('ready',self.owner.state(1)['phase'])
        self.assertNotIn('account-bound-login-start',self.peer.calls)

    def test_completed_frozen_binding_result_survives_later_detach_and_manager_restart(self) -> None:
        """后续解绑后原SID重复提交仍返回原绑定完成结果。:return: None。"""
        sid,_=self._start()
        result=self._commit(sid)
        self.assertEqual(200,result.status_code,result.text)
        with main.get_db() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
        with patch.object(main,'login_manager',main.LoginManager(Mock())):
            response=self._commit(sid)
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(result.json(),response.json())

    def test_management_websocket_uses_original_bound_coordinator(self) -> None:
        """原管理WS桥选择冻结绑定协调器并清理实际attach socket。:return: None。"""
        sid,operation=self._start()
        raw,peer=socket.socketpair()
        raw.setblocking(False)
        self.addCleanup(raw.close)
        self.addCleanup(peer.close)
        with patch.object(self.logins,'open',return_value=raw) as opening:
            with self.client.websocket_connect('/api/accounts/login/ws/'+sid) as websocket:
                websocket.send_json({'type':'ping'})
                self.assertEqual({'type':'pong'},websocket.receive_json())
            deadline=time.monotonic()+2
            while raw.fileno()!=-1 and time.monotonic()<deadline:
                time.sleep(.01)
        opening.assert_called_once_with(operation)
        self.assertEqual(-1,raw.fileno())
