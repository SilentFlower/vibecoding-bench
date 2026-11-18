"""无模型凭据维护的Scope与原中央账本合同回归。"""
from __future__ import annotations

import unittest

from cluster_credentials_contract import CredentialRefreshStart,CredentialRefreshWork
from cluster_execution_grants import ExecutionGrant
from cluster_execution_store import CentralExecutionRecord
import test_cluster_execution_store as store_fixture


class CredentialContractTests(unittest.TestCase):
    """使用真实原中央SQLite核对无模型许可和重放拒绝。"""

    def setUp(self) -> None:
        """建立独立账号的现有凭据操作族Scope。:return: None。"""
        fixture=store_fixture.NodeExecutionStoreTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.ledger=fixture,fixture.ledger
        with fixture.fixture.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
        self.work=CredentialRefreshWork(id=fixture.scope.operation_id,account_id=1,
            account_identity='original-account-identity',version='2.1.303')
        self.scope=fixture.scope.model_copy(update={'gateway_account_id':None,'role':'login','source':self.work.source})
        self.grant=ExecutionGrant(**self.scope.model_dump(),not_after=1020,sequence=1,lease=None)

    def test_credential_permission_uses_no_gateway_lease_or_model_quota(self) -> None:
        """原账本接受具体凭据维护，实际Node关闭前保持活动。:return: None。"""
        CredentialRefreshStart(scope=self.scope,work=self.work)
        self.ledger.begin(self.scope,self.work)
        def save(phase,**changes):
            """沿原CAS记录确定阶段。:return: 新原记录。"""
            row=self.ledger.get(self.scope.operation_id)
            return self.ledger.checkpoint(self.scope.operation_id,row['revision'],phase,**changes)
        save('claimed',local_admission_intent=True)
        save('starting',grant=self.grant)
        ready={'protocol':1,'scope':self.scope.model_dump(),'phase':'ready',
            'result':{'token':'credential-maintenance-token','source':self.work.source}}
        row=save('running',node_receipt=ready)
        self.assertIsNone(row['record']['quota_identity'])
        self.assertIsNone(row['record']['lease'])
        self.assertEqual(1,len(self.ledger.active(1)))
        save('stopping')
        with self.assertRaisesRegex(ValueError,'节点停止'):
            save('closed',local_admission_released=True)
        row=save('closed',node_receipt={**ready,'phase':'closed'},local_admission_released=True)
        self.assertEqual([],self.ledger.active(1))
        self.assertEqual(row,self.ledger.begin(self.scope,self.work))
        with self.assertRaisesRegex(ValueError,'禁止重放'):
            self.ledger.begin(self.scope.model_copy(update={'operation_id':'a'*32}),self.work)

    def test_other_role_binding_or_review_environment_cannot_authorize_refresh(self) -> None:
        """模型Scope、网关绑定及跨环境旧评审来源均被拒绝。:return: None。"""
        for changes in ({'role':'cli'},{'gateway_account_id':7},{'source':'run:'+'a'*12+':0'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                CredentialRefreshStart(scope=self.scope.model_copy(update=changes),work=self.work)
        original=self.scope.model_copy(update={'operation_id':'b'*32,'role':'cli','source':'run:'+'a'*12+':0'})
        work=self.work.model_copy(update={'force_refresh':True,'review_scope':original,'review_request_id':'e'*64})
        CredentialRefreshStart(scope=self.scope,work=work)
        changed=work.model_copy(update={'review_scope':original.model_copy(update={'generation':99})})
        with self.assertRaisesRegex(ValueError,'代次'):
            CredentialRefreshStart(scope=self.scope,work=changed)
        with self.assertRaises(ValueError):
            CredentialRefreshWork(**{**self.work.model_dump(),'refresh_token':'synthetic-private'})

    def test_model_execution_keeps_original_quota_requirement(self) -> None:
        """无额度许可仅限具体凭据工作，普通模型证明仍要求原认领。:return: None。"""
        scope=self.fixture.scope.model_copy(update={'gateway_account_id':None})
        grant=ExecutionGrant(**scope.model_dump(),not_after=1020,lease=None)
        with self.assertRaisesRegex(ValueError,'原中央许可'):
            CentralExecutionRecord(scope=scope,work=self.fixture.work,runtime_release='synthetic-release',
                node_config_sha256='f'*64,local_admission_intent=True,grant=grant)
