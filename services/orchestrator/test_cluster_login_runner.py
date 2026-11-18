"""中央已有SSH账号登录的真实账本与故障恢复回归。"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
import unittest
from unittest.mock import Mock, patch

from cluster_credentials_contract import CredentialRefreshWork
from cluster_execution_grants import ExecutionGrant
from cluster_login_runner import ClusterAccountLogins
import test_cluster_credential_refresh as credential_fixture


class _LoginPeer(credential_fixture._CredentialPeer):
    """明确模拟Node原操作结果，调用顺序与一次启动均可观察。"""

    def __init__(self) -> None:
        """建立当前授权及可控响应丢失。:return: None。"""
        super().__init__()
        self.login=None
        self.codes={}
        self.lost=None
        self.material={'access_token':'synthetic-new-at','refresh_token':'synthetic-new-rt',
            'expires_at':int((time.time()+3600)*1000),'subscription_type':'synthetic-tier'}

    def execution_environment(self, container, payload, operation):
        """执行具体Node登录的固定协议。:param container: 原容器。:param payload: 原输入。:param operation: 固定动作。:return: 私有回执。"""
        if not operation.startswith('account-login-'):
            return super().execution_environment(container,payload,operation)
        self.calls.append(operation)
        scope=payload.get('scope',payload)
        if operation=='account-login-start':
            self.work=copy.deepcopy(payload['work'])
            self.login={'protocol':1,'scope':copy.deepcopy(scope),'phase':'ready',
                'result':{'token':'original-login-token','source':scope['source']}}
        elif operation=='account-login-commit':
            if 'commit' not in self.login:
                self.login['commit']={'stage':'saved','authorization_sha256':'a'*64,
                    'refresh_sha256':hashlib.sha256(self.material['refresh_token'].encode()).hexdigest(),
                    'files':['.claude.json','.claude/.credentials.json'],'cleanup_pending':True,'auth_method':'oauth'}
        elif operation=='account-login-accept':
            self.login['phase']='closed'
            self.login['commit'].update(stage='accepted',cleanup_pending=False)
        elif operation=='account-login-stop':
            if self.login is None:
                self.login={'protocol':1,'scope':copy.deepcopy(scope),'phase':'closed','result':None}
            self.login['phase']='closed'
        elif operation=='account-login-discard':
            self.login['discarded']=True
        elif operation=='account-login-get' and self.login is None:
            raise FileNotFoundError('合成原Node尚无本次登录记录')
        result=copy.deepcopy(self.login)
        if operation=='account-login-code':
            self.codes.setdefault(payload['request_id'],{'request_id':payload['request_id'],'status':'delivered','message':'已送到CLI，等待认证检查'})
            result=dict(self.codes[payload['request_id']])
        elif operation=='account-login-code-receipt':
            result=dict(self.codes[payload['request_id']])
        elif operation=='account-login-snapshot':
            result={'protocol':1,'scope':copy.deepcopy(scope),'authorization_sha256':'a'*64,
                'material':copy.deepcopy(self.material),'version':self.work['version'],'auth_method':'oauth',
                'identity':{'user_id':'b'*64,'email':'synthetic@example.invalid','account_uuid':'original-uuid',
                    'organization_uuid':None},'cli_identity':None}
        elif operation=='account-login-observe':
            result={'phase':'ready_to_submit','credentials_ready':True,'reconnectable':False,
                'expires_at':self.work['expires_at'],'authorization_url':None,'auth_method':'oauth'}
        if self.lost==operation:
            self.lost=None
            raise ConnectionError('合成操作已应用但响应丢失')
        return {'protocol':1,'node_key':scope['node_key'],'login':result}


class ClusterAccountLoginTests(unittest.TestCase):
    """真实中央SQLite及原NodeExecutions，Node传输为显式可观察替身。"""

    def setUp(self) -> None:
        """建立已有独立SSH账号与原所有者锁。:return: None。"""
        fixture=credential_fixture.RemoteCredentialRefreshTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.sessions,self.account=fixture,fixture.sessions,fixture.account
        self.sessions.service.prepare_remote_login=Mock()
        self.peer=_LoginPeer()
        self.sessions.service.connection=lambda node:self.peer
        self.owner=Mock()
        self.owner.state.return_value=None
        fixture.coordinator.ownership=self.owner
        fixture.coordinator.read_identity=Mock(return_value={'device_id':'b'*64})
        self.save=Mock()
        self.logins=ClusterAccountLogins(self.sessions,fixture.coordinator,lambda name:fixture.owner_lock,self.save)
        self.addCleanup(self.logins.close)
        # 单测主动调用续接与恢复，避免后台线程时钟竞争掩盖持久边界。
        self.logins._watch=Mock()

    def _start(self) -> dict:
        return self.logins.start(self.account,'a'*12,'2.1.293')

    def _parent(self) -> dict:
        scope=self.fixture.fixture.request.scope
        work=CredentialRefreshWork(id='c'*32,account_id=1,account_identity='original-account-identity',version='2.1.293')
        scope=scope.model_copy(update={'operation_id':work.id,'source':work.source,'role':'login','gateway_account_id':None})
        self.sessions.ledger.begin(scope,work)
        grant=ExecutionGrant(**scope.model_dump(),not_after=int(time.time())+30)
        self.sessions._save(work.id,'claimed',local_admission_intent=True,grant=grant.model_dump())
        self.peer.receipt={'protocol':1,'scope':scope.model_dump(),'phase':'closed',
            'result':{'token':'original-refresh-token','source':scope.source},'outcome':{'status':'uncertain'}}
        return self.sessions._save(work.id,'reconcile',node_receipt=self.peer.receipt)

    def test_commit_follows_original_save_accept_and_actual_release(self) -> None:
        """新授权保存成功后才接受并释放，普通回执保持无码无令牌。:return: None。"""
        row=self._start()
        operation=row['operation_id']
        self.assertEqual('running',row['phase'])
        self.assertIsNone(row['record']['quota_identity'])
        self.logins._renew(operation)
        self.assertEqual(2,self.sessions.ledger.get(operation)['record']['grant']['sequence'])
        self.assertEqual(operation,self.logins.find('a'*12)['operation_id'])
        self.assertTrue(self.logins.status(operation)['credentials_ready'])
        self.save.side_effect=lambda *args:self.assertEqual('ready',self.peer.login['phase'])
        result=self.logins.commit(operation)
        self.assertEqual({'id':1,'name':self.account['name'],'auth_method':'oauth',
            'cc2api_account_id':None,'credentials_synced':False},result)
        self.assertEqual('synthetic-new-rt',self.save.call_args.args[1]['material']['refresh_token'])
        self.assertEqual(result,self.logins.commit(operation))
        self.save.assert_called_once()
        self.assertEqual([],self.sessions.ledger.active(1))
        self.assertEqual([],self.fixture.fixture.gateway.calls)
        self.fixture.fixture.admit.assert_not_called()
        text=json.dumps(self.sessions.ledger.get(operation))
        self.assertNotIn('synthetic-new-at',text)
        self.assertNotIn('synthetic-new-rt',text)

    def test_unknown_start_recovery_only_stops_original_login(self) -> None:
        """启动响应丢失后的恢复只查询、实际停止并清理原登录。:return: None。"""
        self.peer.lost='account-login-start'
        with self.assertRaises(ConnectionError):
            self._start()
        row=self.logins.find('a'*12)
        self.assertEqual('reconcile',row['phase'])
        self.logins.recover_pending()
        self.assertEqual('closed',self.sessions.ledger.get(row['operation_id'])['phase'])
        self.assertEqual(1,self.peer.calls.count('account-login-start'))
        self.assertTrue(self.peer.login['discarded'])
        self.save.assert_not_called()

    def test_unknown_grant_creation_cancels_original_scope_without_start(self) -> None:
        """许可创建响应丢失时持久隔离，恢复只取消原具体登录。:return: None。"""
        original=self.sessions._call
        def call(row,operation,payload):
            """实际创建证明后注入响应丢失。:return: 原Node结果。"""
            result=original(row,operation,payload)
            if operation=='grant-create':
                raise ConnectionError('合成许可创建响应丢失')
            return result
        with patch.object(self.sessions,'_call',side_effect=call):
            with self.assertRaises(ConnectionError):
                self._start()
        row=self.logins.find('a'*12)
        self.assertEqual('reconcile',row['phase'])
        self.logins.recover_pending()
        self.assertEqual('closed',self.sessions.ledger.get(row['operation_id'])['phase'])
        self.assertNotIn('account-login-start',self.peer.calls)
        self.assertTrue(self.peer.login['discarded'])

    def test_save_failure_retains_original_material_then_recovers_same_commit(self) -> None:
        """中央证明保存失败继续隔离，恢复同一授权后才清理。:return: None。"""
        operation=self._start()['operation_id']
        self.save.side_effect=OSError('合成中央证明保存失败')
        with self.assertRaises(OSError):
            self.logins.commit(operation)
        self.assertEqual('reconcile',self.sessions.ledger.get(operation)['phase'])
        self.assertTrue(self.peer.login['commit']['cleanup_pending'])
        self.assertNotIn('account-login-accept',self.peer.calls)
        self.save.side_effect=None
        self.logins.recover_pending()
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual(1,self.peer.calls.count('account-login-start'))

    def test_unknown_accept_recovers_original_scope_without_new_authorization(self) -> None:
        """接受响应丢失保留中央隔离，原保存和清理阶段可重复对账。:return: None。"""
        operation=self._start()['operation_id']
        self.peer.lost='account-login-accept'
        with self.assertRaises(ConnectionError):
            self.logins.commit(operation)
        self.assertEqual('closed',self.peer.login['phase'])
        self.assertEqual('reconcile',self.sessions.ledger.get(operation)['phase'])
        self.logins.recover_pending()
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual(1,self.peer.calls.count('account-login-start'))

    def test_unknown_parent_stays_active_until_new_authorization_fully_closes(self) -> None:
        """原未知RT账本隔离保留到新授权完成，取消新登录保留原父来源。:return: None。"""
        parent=self._parent()
        row=self._start()
        self.assertEqual(parent['record']['scope'],row['record']['work']['refresh_scope'])
        self.assertEqual(2,len(self.sessions.ledger.active(1)))
        self.logins.cancel(row['operation_id'])
        self.assertEqual('reconcile',self.sessions.ledger.get(parent['operation_id'])['phase'])
        row=self.logins.start(self.account,'b'*12,'2.1.293')
        self.logins.commit(row['operation_id'])
        self.assertEqual([],self.sessions.ledger.active(1))
        closed=self.sessions.ledger.get(parent['operation_id'])
        self.assertEqual('uncertain',closed['record']['node_receipt']['outcome']['status'])
        self.assertEqual('superseded_by_new_authorization',closed['record']['failure'])

    def test_new_login_keeps_barrier_until_parent_closed_after_accept(self) -> None:
        """接受后关闭父记录失败时保留新登录屏障，恢复先关闭父再释放新登录。:return: None。"""
        parent=self._parent()
        row=self._start()
        original=self.sessions._save
        def save(operation,phase=None,**changes):
            """注入父记录终态持久化失败。:return: 原CAS记录。"""
            if operation==parent['operation_id'] and phase=='closed':
                raise OSError('合成原父来源关闭失败')
            return original(operation,phase,**changes)
        with patch.object(self.sessions,'_save',side_effect=save):
            with self.assertRaises(OSError):
                self.logins.commit(row['operation_id'])
        self.assertEqual(2,len(self.sessions.ledger.active(1)))
        self.logins.recover_pending()
        self.assertEqual([],self.sessions.ledger.active(1))

    def test_snapshot_failure_does_not_accept_and_never_exposes_secret(self) -> None:
        """受信快照错类型返回固定错误，中央隔离与Node材料继续保留。:return: None。"""
        operation=self._start()['operation_id']
        self.peer.material['access_token']='sensitive token with whitespace'
        with self.assertRaises(ValueError) as error:
            self.logins.commit(operation)
        self.assertNotIn('sensitive',str(error.exception))
        self.assertEqual('reconcile',self.sessions.ledger.get(operation)['phase'])
        self.assertNotIn('account-login-accept',self.peer.calls)
        self.save.assert_not_called()
