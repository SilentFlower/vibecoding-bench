"""绑定Node登录的授权冻结、Gateway当前AT发布及原tmux严格收口。"""
from __future__ import annotations

import json
import time
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from account_runtime import AccountRuntime

from cluster_bound_login import NodeBoundAccountLogins
from cluster_bound_login_contract import BoundLoginAbort, BoundLoginIdentity, BoundLoginPublish, BoundLoginStart, BoundLoginWork
from cluster_execution_grants import ExecutionGrant, ExecutionLeaseProof
from cluster_login_contract import AccountLoginAccept
from runtime_files import atomic_json
import test_cluster_login as login_fixture


class NodeBoundLoginTests(unittest.TestCase):
    """真实Node SQLite、证明和私有文件，Docker/tmux及Gateway回执为显式替身。"""

    def setUp(self) -> None:
        """复用原登录文件与一次输入夹具，补真实绑定范围及原排他lease镜像。:return: None。"""
        fixture=login_fixture.NodeAccountLoginTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.runtime=fixture,fixture.runtime
        credential_lock=threading.RLock()
        self.runtime._credential_lock=lambda name:credential_lock
        self.runtime.sync_credentials=AccountRuntime.sync_credentials.__get__(self.runtime,type(self.runtime))
        with fixture.fixture.executor.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=7 WHERE id=1')
            connection.execute('UPDATE account_environments SET isolation_version=2 WHERE account_id=1')
        identity=BoundLoginIdentity(email='synthetic@example.invalid',account_uuid='original-uuid',organization_uuid='original-org')
        work=BoundLoginWork(id='e'*32,sid='b'*12,account_id=1,gateway_account_id=7,device_id='a'*64,
            expected_identity=identity,version='2.1.303',expires_at=int(time.time())+1800,
            account_identity=json.dumps({'account_id':1,'binding':7,'uuid':identity.account_uuid,'org':identity.organization_uuid},sort_keys=True))
        scope=fixture.scope.model_copy(update={'operation_id':work.id,'source':work.source,'gateway_account_id':7})
        fixture.work,fixture.scope=work,scope
        fixture.fixture.scope=scope
        fixture.request=BoundLoginStart(scope=scope,work=work)
        self.scope,self.request=scope,fixture.request
        self.lease=ExecutionLeaseProof(owner=scope.source,generation='original-bound-lease',expires_at=1020,exclusive=True)
        fixture.fixture.grants.create(ExecutionGrant(**scope.model_dump(),not_after=1020,lease=self.lease))
        self.actor=NodeBoundAccountLogins(fixture.fixture.executor,fixture.fixture.host,fixture.fixture.grants)
        self.addCleanup(self.actor.close)
        fixture.actor=self.actor
        row=self.runtime._row('synthetic',1)
        self.home=self.runtime._root(row)/'home'
        self.profile=fixture.fixture.executor.data/'profiles/synthetic'
        for root,relative in ((self.home,'.claude/.credentials.json'),(self.profile,'.credentials.json')):
            atomic_json(root/relative,{'unknown_credentials':True,'claudeAiOauth':{
                'accessToken':'synthetic-old-at','expiresAt':int((time.time()+3600)*1000)}})
            top=json.loads((root/'.claude.json').read_text())
            top['unknown_config']=True
            atomic_json(root/'.claude.json',top)
        self.previous=(self.home/'.claude/.credentials.json').read_bytes()

    def _frozen(self) -> dict:
        self.fixture._ready()
        self.fixture.fixture.job['lease']=self.lease.model_dump()
        self.runtime.exec_cli.return_value=SimpleNamespace(exit_code=0,output=b'{"loggedIn":true,"authMethod":"oauth"}')
        return self.actor.commit(self.scope)

    def test_original_disabled_account_can_authorize_without_reenabling_it(self) -> None:
        """原绑定停用账号的明确授权保持enabled原值及AT-only。:return: None。"""
        with self.fixture.fixture.executor.database() as connection:
            connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
        frozen=self._frozen()
        self.assertEqual('frozen',frozen['commit']['stage'])
        self.assertEqual(self.previous,(self.home/'.claude/.credentials.json').read_bytes())
        with self.fixture.fixture.executor.database() as connection:
            self.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=1').fetchone()[0])

    def test_freeze_keeps_rt_private_then_publishes_gateway_current_at_and_strictly_cleans(self) -> None:
        """Node只冻结本次RT，HOME发布Gateway当前AT，中央确认后实际停止并删除私有副本。:return: None。"""
        frozen=self._frozen()
        self.assertEqual('frozen',frozen['commit']['stage'])
        self.assertEqual(self.previous,(self.home/'.claude/.credentials.json').read_bytes())
        self.assertEqual(frozen,self.actor.commit(self.scope))
        self.assertNotIn('synthetic-new-rt',json.dumps(frozen))
        snapshot=self.actor.snapshot(self.scope)
        self.assertEqual('synthetic-new-rt',snapshot['material']['refresh_token'])
        with self.assertRaisesRegex(ValueError,'中央确认'):
            self.actor.stop(self.scope)
        published=self.actor.publish(BoundLoginPublish(scope=self.scope,
            authorization_sha256=frozen['commit']['authorization_sha256'],access_token='gateway-current-at',expires_at=9999999999999))
        self.assertEqual('saved',published['commit']['stage'])
        for root,relative in ((self.home,'.claude/.credentials.json'),(self.profile,'.credentials.json')):
            document=json.loads((root/relative).read_text())
            self.assertEqual('gateway-current-at',document['claudeAiOauth']['accessToken'])
            self.assertNotIn('refreshToken',document['claudeAiOauth'])
            self.assertTrue(document['unknown_credentials'])
            self.assertTrue(json.loads((root/'.claude.json').read_text())['unknown_config'])
        for relative in ('runtime/access/.credentials.json','runtime/network/access/.credentials.json'):
            credentials=json.loads((self.home.parent/relative).read_text())['claudeAiOauth']
            self.assertEqual('gateway-current-at',credentials['accessToken'])
            self.assertNotIn('refreshToken',credentials)
        accepted=AccountLoginAccept(scope=self.scope,authorization_sha256=frozen['commit']['authorization_sha256'])
        closed=self.actor.accept(accepted)
        self.assertEqual('closed',closed['phase'])
        self.assertFalse(closed['commit']['cleanup_pending'])
        self.assertFalse(self.fixture.profile.parent.exists())
        self.assertFalse((self.actor._directory(self.scope)/'authorization').exists())
        self.runtime.cleanup.assert_called_once()
        self.assertEqual(self.lease.model_dump(),self.runtime.restore_execution.call_args.args[3])
        self.assertEqual({},self.fixture.fixture.host.gateway.lease_mirror.scopes)
        # 原Gateway可能已进一步轮换；原Scope收口中的恢复仍只发布当前AT。
        self.actor.publish(BoundLoginPublish(scope=self.scope,
            authorization_sha256=frozen['commit']['authorization_sha256'],access_token='gateway-later-at',expires_at=9999999999999))
        self.assertEqual('gateway-later-at',json.loads((self.home/'.claude/.credentials.json').read_text())['claudeAiOauth']['accessToken'])
        self.assertEqual('committed',self.actor.observe(self.scope)['phase'])

    def test_wrong_new_identity_is_rejected_before_freeze_intent(self) -> None:
        """新授权换号时保持原HOME，明确拒绝本次冻结提交。:return: None。"""
        self.fixture._ready()
        top=json.loads((self.fixture.profile.parent/'.claude.json').read_text())
        top['oauthAccount']['accountUuid']='other-uuid'
        atomic_json(self.fixture.profile.parent/'.claude.json',top)
        self.runtime.exec_cli.return_value=SimpleNamespace(exit_code=0,output=b'{"loggedIn":true}')
        with self.assertRaisesRegex(ValueError,'原绑定身份'):
            self.actor.commit(self.scope)
        self.assertNotIn('commit',self.actor.get(self.scope))
        self.assertEqual(self.previous,(self.home/'.claude/.credentials.json').read_bytes())
        self.actor.discard(self.scope)

    def test_partial_at_only_publication_recovers_same_frozen_authorization(self) -> None:
        """HOME已更新而profile失败时保留原冻结RT，重启只补当前Gateway AT发布。:return: None。"""
        frozen=self._frozen()
        publish=BoundLoginPublish(scope=self.scope,authorization_sha256=frozen['commit']['authorization_sha256'],
            access_token='gateway-current-at',expires_at=9999999999999)
        original=atomic_json
        def write(path,value):
            """只注入Node管理profile发布失败。:return: 原文件写入结果。"""
            if path==self.profile/'.credentials.json':
                raise OSError('合成AT-only profile发布失败')
            return original(path,value)
        with patch('cluster_bound_login.atomic_json',side_effect=write):
            with self.assertRaises(OSError):
                self.actor.publish(publish)
        self.assertEqual('frozen',self.actor.get(self.scope)['commit']['stage'])
        restarted=NodeBoundAccountLogins(self.fixture.fixture.executor,self.fixture.fixture.host,self.fixture.fixture.grants)
        self.addCleanup(restarted.close)
        self.assertEqual('saved',restarted.publish(publish)['commit']['stage'])
        restarted.accept(AccountLoginAccept(scope=self.scope,authorization_sha256=publish.authorization_sha256))
        self.runtime.begin_login.assert_called_once()
        self.runtime.exec_cli.assert_called_once()

    def test_nonexclusive_proof_cannot_start_bound_login(self) -> None:
        """普通CLI证明不能取得绑定账号原独占登录能力。:return: None。"""
        work=self.request.work.model_copy(update={'id':'c'*32,'sid':'c'*12})
        scope=self.scope.model_copy(update={'operation_id':work.id,'source':work.source})
        lease=self.lease.model_copy(update={'owner':scope.source,'exclusive':False})
        self.fixture.fixture.grants.create(ExecutionGrant(**scope.model_dump(),not_after=1020,lease=lease))
        with self.assertRaisesRegex(ValueError,'排他lease'):
            self.actor.start(BoundLoginStart(scope=scope,work=work))
        self.runtime.begin_login.assert_not_called()
        self.assertEqual('prepared',self.fixture.fixture.grants.get(scope)['phase'])

    def test_published_authorization_keeps_original_accept_path_and_rejects_abort(self) -> None:
        """AT发布后已进入导入完成分支，禁止通过未导入声明丢弃原提交。:return: None。"""
        frozen=self._frozen()
        publish=BoundLoginPublish(scope=self.scope,authorization_sha256=frozen['commit']['authorization_sha256'],
            access_token='gateway-current-at',expires_at=9999999999999)
        self.actor.publish(publish)
        with self.assertRaisesRegex(ValueError,'导入阶段'):
            self.actor.abort(BoundLoginAbort(scope=self.scope,authorization_sha256=publish.authorization_sha256,
                lease_generation=self.lease.generation,import_not_submitted=True))
        self.assertTrue((self.actor._directory(self.scope)/'authorization').exists())
        self.actor.accept(AccountLoginAccept(scope=self.scope,authorization_sha256=publish.authorization_sha256))

    def test_abort_requires_original_lease_and_never_cancels_already_published_authorization(self) -> None:
        """冻结取消须保留原lease代次，发布后继续原提交收口。:return: None。"""
        frozen=self._frozen()
        abort=BoundLoginAbort(scope=self.scope,authorization_sha256=frozen['commit']['authorization_sha256'],
            lease_generation='other-lease',import_not_submitted=True)
        with self.assertRaisesRegex(ValueError,'lease代次'):
            self.actor.abort(abort)
        abort=abort.model_copy(update={'lease_generation':self.lease.generation})
        closed=self.actor.abort(abort)
        self.assertEqual('closed',closed['phase'])
        self.assertTrue(closed['commit']['aborted'])
        self.assertFalse(closed['commit']['cleanup_pending'])
        self.assertEqual(closed,self.actor.abort(abort))
        self.assertEqual(self.previous,(self.home/'.claude/.credentials.json').read_bytes())
        self.assertEqual('ended',self.actor.observe(self.scope)['phase'])
        with self.assertRaisesRegex(ValueError,'原冻结授权'):
            self.actor.publish(BoundLoginPublish(scope=self.scope,authorization_sha256=abort.authorization_sha256,
                access_token='gateway-current-at',expires_at=9999999999999))
