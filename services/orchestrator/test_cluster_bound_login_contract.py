"""绑定登录的具体工作、AT-only私有发布及原真实排他租约账本。"""
from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from cluster_bound_login_contract import BoundLoginAbort, BoundLoginIdentity, BoundLoginPublish, BoundLoginStart, BoundLoginWork
from cluster_execution_grants import ExecutionGrant, ExecutionLeaseProof
from cluster_execution_store import CentralExecutionRecord
import test_cluster_execution_store as store_fixture


class BoundLoginContractTests(unittest.TestCase):
    """真实中央SQLite及Scope，Gateway租约作为明确外部回执输入。"""

    def setUp(self) -> None:
        """建立原绑定账号、Node及冻结登录范围。:return: None。"""
        fixture=store_fixture.NodeExecutionStoreTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.ledger=fixture,fixture.ledger
        expected=BoundLoginIdentity(email='synthetic@example.invalid',account_uuid='synthetic-uuid',organization_uuid='synthetic-org')
        identity=json.dumps({'account_id':1,'binding':7,'uuid':expected.account_uuid,'org':expected.organization_uuid},sort_keys=True)
        self.work=BoundLoginWork(id='f'*32,sid='a'*12,account_id=1,gateway_account_id=7,account_identity=identity,
            device_id='b'*64,expected_identity=expected,version='2.1.293',expires_at=2000)
        self.scope=fixture.scope.model_copy(update={'operation_id':self.work.id,'source':self.work.source,'role':'login'})
        self.request=BoundLoginStart(scope=self.scope,work=self.work)

    def _save(self, phase: str, **changes) -> dict:
        row=self.ledger.get(self.scope.operation_id)
        return self.ledger.checkpoint(self.scope.operation_id,row['revision'],phase,**changes)

    def test_disabled_bound_login_is_explicit_while_normal_work_and_deleted_account_stay_blocked(self) -> None:
        """原停用账号可落账明确重授权，普通工作及删除账号保持原门禁。:return: None。"""
        with self.ledger.store.database() as connection:
            connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
        with self.assertRaises(ValueError):
            self.ledger.begin(self.fixture.scope,self.fixture.work)
        row=self.ledger.begin(self.scope,self.work)
        self.assertEqual(row,self.ledger.admit(self.work.id))
        with self.ledger.store.database() as connection:
            connection.execute('UPDATE accounts SET deleted_at=1 WHERE id=1')
        with self.assertRaises(ValueError):
            self.ledger.admit(self.work.id)

    def test_original_bound_scope_requires_real_exclusive_login_lease_without_model_quota(self) -> None:
        """原Scope落账后先保留网关认领意图，真实排他lease确认后才认领Node证明。:return: None。"""
        row=self.ledger.begin(self.scope,self.work)
        self.assertEqual('account-bound-login',row['record']['work']['kind'])
        self.assertIsInstance(CentralExecutionRecord.model_validate(row['record']).work,BoundLoginWork)
        self._save('preparing',gateway_prepare_intent=True)
        lease=ExecutionLeaseProof(owner=self.work.source,generation='original-gateway-login',expires_at=1020,exclusive=True)
        grant=ExecutionGrant(**self.scope.model_dump(),not_after=1020,lease=lease)
        self._save('claimed',lease=lease.model_dump(),grant=grant.model_dump())
        self._save('starting')
        ready={'protocol':1,'scope':self.scope.model_dump(),'phase':'ready','result':{'token':'original-login-token','source':self.work.source}}
        row=self._save('running',node_receipt=ready)
        self.assertIsNone(row['record']['quota_identity'])
        self.assertFalse(row['record']['local_admission_intent'])
        with self.assertRaises(ValueError):
            self._save('closed')
        self._save('stopping',node_receipt={**ready,'phase':'closed'})
        row=self._save('closed',lease_released={'owner':lease.owner,'generation':lease.generation,'released':True})
        self.assertEqual('closed',row['phase'])
        with self.assertRaisesRegex(ValueError,'禁止重放'):
            self.ledger.begin(self.scope.model_copy(update={'operation_id':'e'*32}),self.work.model_copy(update={'id':'e'*32}))

    def test_shared_or_nonexclusive_gateway_lease_cannot_be_used_for_reauthorization(self) -> None:
        """共享CLI许可与普通CLI许可均不能升级为绑定重授权门禁。:return: None。"""
        self.ledger.begin(self.scope,self.work)
        self._save('preparing',gateway_prepare_intent=True)
        for shared in (False,True):
            lease=ExecutionLeaseProof(owner=self.work.source,generation='wrong-mode',expires_at=1020,exclusive=False,shared_cli=shared)
            with self.subTest(shared=shared),self.assertRaisesRegex(ValueError,'排他'):
                self._save('claimed',lease=lease.model_dump())

    def test_frozen_binding_identity_and_scope_reject_other_accounts_and_independent_parent(self) -> None:
        """绑定、设备、角色及独立RT父来源都不能替换本次冻结范围。:return: None。"""
        for changes in ({'gateway_account_id':None},{'gateway_account_id':8},{'account_id':2},{'source':'login:'+'b'*12},{'role':'cli'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                BoundLoginStart(scope=self.scope.model_copy(update=changes),work=self.work)
        value=self.work.model_dump()
        for changes in ({'gateway_account_id':8},{'device_id':'bad-device'},{'refresh_scope':self.scope.model_dump()},{'force_reauth':False}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                BoundLoginWork.model_validate({**value,**changes})

    def test_at_only_publish_rejects_rt_and_abort_requires_original_scope_and_known_unsubmitted(self) -> None:
        """私有发布只接受AT与到期，取消必须保留原租约代次和明确未导入结论。:return: None。"""
        value={'scope':self.scope.model_dump(),'authorization_sha256':'a'*64,'access_token':'synthetic-at','expires_at':9999999}
        self.assertEqual('synthetic-at',BoundLoginPublish.model_validate(value).access_token)
        for changes in ({'refresh_token':'synthetic-rt'},{'access_token':'invalid token'},{'expires_at':True}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                BoundLoginPublish.model_validate({**value,**changes})
        cancel={'scope':self.scope,'authorization_sha256':'a'*64,'lease_generation':'original-gateway-login','import_not_submitted':True}
        self.assertTrue(BoundLoginAbort.model_validate(cancel).import_not_submitted)
        for known in (False,1,'true'):
            with self.subTest(known=known),self.assertRaises(ValidationError):
                BoundLoginAbort.model_validate({**cancel,'import_not_submitted':known})
