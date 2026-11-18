"""具体独立账号登录的无模型中央许可及严格输入合同。"""
import time
import unittest

from pydantic import ValidationError

from cluster_execution_grants import ExecutionGrant
from cluster_login_contract import AccountLoginCode, AccountLoginStart, AccountLoginWork
import test_cluster_credentials_contract as credential_fixture


class AccountLoginContractTests(unittest.TestCase):
    """复用真实中央SQLite核对已存在账号的明确重授权范围。"""

    def setUp(self) -> None:
        """借用独立账号的原中央账本。:return: None。"""
        fixture=credential_fixture.CredentialContractTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.ledger=fixture,fixture.ledger
        self.work=AccountLoginWork(id=fixture.scope.operation_id,sid='a'*12,account_id=1,
            account_identity='original-identity',version='2.1.303',expires_at=int(time.time())+1800)
        self.scope=fixture.scope.model_copy(update={'source':self.work.source})

    def test_original_login_uses_only_independent_permission_and_never_replays_closed_sid(self) -> None:
        """具体login工作无模型额度和网关租约，真实停止确认前保持活动。:return: None。"""
        AccountLoginStart(scope=self.scope,work=self.work)
        row=self.ledger.begin(self.scope,self.work)
        row=self.ledger.checkpoint(self.scope.operation_id,row['revision'],'claimed',local_admission_intent=True)
        grant=ExecutionGrant(**self.scope.model_dump(),not_after=1020)
        row=self.ledger.checkpoint(self.scope.operation_id,row['revision'],'starting',grant=grant)
        self.assertIsNone(row['record']['quota_identity'])
        self.assertIsNone(row['record']['lease'])
        self.assertEqual(1,len(self.ledger.active(1)))
        receipt={'protocol':1,'scope':self.scope.model_dump(),'phase':'closed','result':None}
        row=self.ledger.checkpoint(self.scope.operation_id,row['revision'],'stopping',node_receipt=receipt)
        row=self.ledger.checkpoint(self.scope.operation_id,row['revision'],'closed',local_admission_released=True)
        self.assertEqual([],self.ledger.active(1))
        with self.assertRaisesRegex(ValueError,'禁止重放'):
            self.ledger.begin(self.scope.model_copy(update={'operation_id':'b'*32}),self.work.model_copy(update={'id':'b'*32}))

    def test_scope_force_and_code_are_strict(self) -> None:
        """普通登录、错误SID或绑定账号拒绝进入本次独立重授权。:return: None。"""
        for change in ({'force_reauth':False},{'force_reauth':1},{'account_id':None}):
            with self.assertRaises(ValidationError):
                AccountLoginWork.model_validate({**self.work.model_dump(),**change})
        for change in ({'source':'login:'+'b'*12},{'gateway_account_id':7},{'role':'cli'}):
            with self.assertRaises(ValidationError):
                AccountLoginStart(scope=self.scope.model_copy(update=change),work=self.work)
        for code in ('',' ','secret\nvalue','secret\x7fvalue'):
            with self.assertRaises(ValidationError):
                AccountLoginCode(scope=self.scope,request_id='c'*32,code=code)

    def test_unknown_refresh_parent_keeps_same_owner_and_monotonic_environment_generation(self) -> None:
        """明确登录只能关联同Node原已停止RT维护，受控唤醒可提高环境代次。:return: None。"""
        parent=self.scope.model_copy(update={'operation_id':'d'*32,'source':'oauth-refresh:'+'d'*32})
        work=self.work.model_copy(update={'refresh_scope':parent})
        AccountLoginStart(scope=self.scope,work=work)
        AccountLoginStart(scope=self.scope.model_copy(update={'generation':self.scope.generation+1}),work=work)
        for change in ({'node_key':'e'*32},{'environment_id':'f'*32},{'assignment_revision':self.scope.assignment_revision+1}):
            with self.subTest(change=change),self.assertRaises(ValidationError):
                AccountLoginStart(scope=self.scope.model_copy(update=change),work=work)
        for change in ({'source':'quota:'+'d'*32},{'account_id':2},{'gateway_account_id':7}):
            with self.assertRaises(ValidationError):
                AccountLoginWork.model_validate({**self.work.model_dump(),'refresh_scope':parent.model_copy(update=change).model_dump()})
