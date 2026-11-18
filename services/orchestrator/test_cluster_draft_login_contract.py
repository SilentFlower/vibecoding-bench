"""NULL草稿范围与正式执行隔离、准备摘要及原恢复来源的严格合同。"""
from __future__ import annotations

import unittest

from pydantic import ValidationError

from cluster_draft_login_contract import DraftLoginGrant, DraftLoginPreparation, DraftLoginReceipt, DraftLoginScope, DraftLoginSettings, DraftLoginStart, DraftLoginWork, draft_preparation_sha256
from cluster_execution_grants import ExecutionScope


class DraftLoginContractTests(unittest.TestCase):
    """草稿用真实独立身份，原正式账号Scope继续要求正ID。"""

    def setUp(self) -> None:
        """建立单个未绑定账号的冻结配置。:return: None。"""
        self.settings=DraftLoginSettings(name='synthetic_draft',timezone='UTC',upstream_socks5_host='proxy.invalid',
            upstream_socks5_user='synthetic-user',upstream_socks5_pass='synthetic-private-proxy')
        self.fingerprint='{"tz":"UTC","mem":"4g","swap":"0"}'
        self.files={'.claude.json':'{}','settings.json':'{"permissions":{"defaultMode":"bypassPermissions"}}'}
        self.work=DraftLoginWork(id='a'*32,sid='b'*12,environment_id='e'*32,name=self.settings.name,
            draft_generation='d'*32,version='2.1.293',home='/home/node/.v3-login/'+'b'*12,
            preparation_sha256=draft_preparation_sha256(self.settings,self.fingerprint,self.files),expires_at=2000)
        self.scope=DraftLoginScope(operation_id=self.work.id,node_key='c'*32,environment_id=self.work.environment_id,
            name=self.work.name,draft_generation=self.work.draft_generation,generation=1,source=self.work.source)

    def test_null_scope_and_grant_round_trip_without_account_or_gateway_identity(self) -> None:
        """草稿范围与有限证明只携带真实草稿定位，序列化不会产生占位账号。:return: None。"""
        request=DraftLoginStart(scope=self.scope,work=self.work)
        self.assertEqual(request,DraftLoginStart.model_validate_json(request.model_dump_json()))
        grant=DraftLoginGrant(**self.scope.model_dump(),not_after=1020)
        self.assertEqual(self.scope,grant.scope())
        for value in (self.scope.model_dump(),grant.model_dump(),self.work.model_dump()):
            self.assertNotIn('account_id',value)
            self.assertNotIn('gateway_account_id',value)
            self.assertNotIn('lease',value)
        with self.assertRaises(ValidationError):
            ExecutionScope.model_validate(self.scope.model_dump())

    def test_account_surrogates_gateway_lease_and_zero_actual_generation_are_rejected(self) -> None:
        """NULL草稿不接受正ID、零ID、NULL账号字段或伪造Gateway租约。:return: None。"""
        for extra in ({'account_id':1},{'account_id':0},{'account_id':None},{'gateway_account_id':7},
                {'gateway_account_id':None},{'lease':None},{'generation':0},{'generation':True},{'role':'login'}):
            with self.subTest(extra=extra),self.assertRaises(ValidationError):
                DraftLoginGrant.model_validate({**self.scope.model_dump(),'not_after':1020,**extra})
        for extra in ({'id':1},{'cc2api_account_id':7},{'account_id':None}):
            with self.subTest(extra=extra),self.assertRaises(ValidationError):
                DraftLoginSettings.model_validate({**self.settings.model_dump(),**extra})

    def test_wrong_name_environment_operation_sid_or_logical_generation_cannot_replace_work(self) -> None:
        """具体启动范围同时核对原工作、名称和两类代次。:return: None。"""
        for changes in ({'operation_id':'f'*32},{'environment_id':'f'*32},{'name':'another'},
                {'draft_generation':'f'*32},{'source':'login:'+'f'*12}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                DraftLoginStart(scope=self.scope.model_copy(update=changes),work=self.work)

    def test_private_prepare_digest_preserves_proxy_and_initial_json_content(self) -> None:
        """准备内容规范摘要稳定，公开工作与证明只保存摘要。:return: None。"""
        request=DraftLoginPreparation(node_key=self.scope.node_key,work=self.work,settings=self.settings,
            fingerprint_json=self.fingerprint,profile_files=self.files)
        self.assertEqual(self.work.preparation_sha256,draft_preparation_sha256(self.settings,
            '{"swap":"0", "mem":"4g", "tz":"UTC"}',self.files))
        self.assertNotIn('synthetic-private-proxy',self.work.model_dump_json())
        for changes in ({'settings':self.settings.model_copy(update={'upstream_socks5_pass':'changed'})},
                {'profile_files':{'.claude.json':'{"changed":true}'}},
                {'fingerprint_json':'{"tz":"Europe/Paris"}'},
                {'profile_files':{'.credentials.json':'{}'}},
                {'profile_files':{'../outside':'{}'}}):
            value=request.model_dump()
            value.update(changes)
            with self.subTest(changes=changes),self.assertRaises((ValidationError,ValueError)):
                DraftLoginPreparation.model_validate(value)

    def test_duplicate_private_json_fields_are_rejected_before_digest(self) -> None:
        """准备配置中的重复JSON键不能在摘要与实际消费之间改变含义。:return: None。"""
        with self.assertRaises(ValueError):
            draft_preparation_sha256(self.settings,'{"tz":"UTC","tz":"Europe/Paris"}',self.files)
        with self.assertRaises(ValueError):
            draft_preparation_sha256(self.settings,self.fingerprint,{'settings.json':'{"env":{},"env":{}}'})

    def test_recover_requires_same_environment_previous_scope_and_new_sid_generation(self) -> None:
        """恢复保留原HOME，同时要求原Node范围、新操作/SID和新逻辑代次。:return: None。"""
        work=self.work.model_copy(update={'id':'f'*32,'sid':'f'*12,'draft_generation':'f'*32,'mode':'recover'})
        request={'node_key':self.scope.node_key,'work':work,'settings':self.settings,
            'fingerprint_json':self.fingerprint,'profile_files':self.files,'previous':self.scope}
        self.assertEqual(self.work.home,DraftLoginPreparation.model_validate(request).work.home)
        for previous in (None,self.scope.model_copy(update={'node_key':'f'*32}),
                self.scope.model_copy(update={'source':work.source}),
                self.scope.model_copy(update={'draft_generation':work.draft_generation}),
                self.scope.model_copy(update={'environment_id':'f'*32})):
            with self.subTest(previous=previous),self.assertRaises(ValidationError):
                DraftLoginPreparation.model_validate({**request,'previous':previous})

    def test_authorize_and_recover_home_are_fixed_safe_paths(self) -> None:
        """新授权只能用本SID暂存，恢复路径保持原固定HOME集合。:return: None。"""
        for home in ('/tmp/unavailable','/home/node/../outside','/home/node','/home/node/.v3-login/'+'f'*12):
            with self.subTest(home=home),self.assertRaises(ValidationError):
                DraftLoginWork.model_validate({**self.work.model_dump(),'home':home})
        for home in ('/home/node',self.work.home):
            value={**self.work.model_dump(),'mode':'recover','home':home}
            self.assertEqual(home,DraftLoginWork.model_validate(value).home)

    def test_receipt_requires_actual_scope_result_and_fixed_private_commit_fields(self) -> None:
        """回执只保存无令牌事实，实际启动与提交范围同时严格校验。:return: None。"""
        result={'token':'synthetic-draft-job','source':self.work.source}
        commit={'stage':'accepted','authorization_sha256':'a'*64,'refresh_sha256':'b'*64,
            'files':['.claude.json','.claude/.credentials.json'],'cleanup_pending':False}
        receipt={'protocol':1,'scope':self.scope.model_dump(),'phase':'closed','result':result,'commit':commit}
        self.assertEqual(receipt['commit'],DraftLoginReceipt.model_validate(receipt).commit.model_dump(exclude={'auth_method'}))
        for extra in ({'phase':'ready','result':None,'commit':None},{'phase':'ready'},
                {'result':{**result,'source':'login:'+'f'*12}}, {'protocol':True},
                {'commit':{**commit,'refresh_token':'synthetic-secret'}},
                {'commit':{**commit,'files':['.claude.json','.claude.json']}},
                {'commit':{**commit,'files':['.claude.json','../outside']}},
                {'commit':{**commit,'cleanup_pending':0}}):
            with self.subTest(extra=extra),self.assertRaises(ValidationError):
                DraftLoginReceipt.model_validate({**receipt,**extra})
