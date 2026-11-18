"""中央草稿真实SQLite的CAS、启动意图及首次保存中断窗口。"""
from __future__ import annotations

import json
import sqlite3
import time
import unittest
from pathlib import Path

from cluster_draft_login_contract import DraftLoginActivated, DraftLoginActivation, DraftLoginGrant, DraftLoginPreparation, DraftLoginScope, DraftLoginSettings, DraftLoginWork, draft_preparation_sha256
from cluster_draft_login_store import NodeLoginDrafts
from cluster_execution_grants import ExecutionScope
from cluster_execution_store import NodeExecutions
from cluster_login_contract import AccountLoginWork
from database_migrations import apply_migrations
import test_cluster_draft_schema as draft_schema_fixture


class NodeLoginDraftStoreTests(unittest.TestCase):
    """合成NULL环境按原操作持久恢复，正式账号只在完整Node收口后创建。"""

    def setUp(self) -> None:
        """建立真实中央临时库和同批SSH节点。:return: None。"""
        fixture=draft_schema_fixture.NodeLoginDraftSchemaTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.connection,self.store,self.database,self.node_id=fixture.connection,fixture.store,fixture.database,fixture.node_id
        apply_migrations(self.connection)
        self.settings=DraftLoginSettings(name='draft_only',timezone='UTC',upstream_socks5_host='synthetic.proxy.invalid',
            upstream_socks5_user='synthetic-user',upstream_socks5_pass='synthetic-secret')
        self.fingerprint='{"tz":"UTC","mem":"4g","swap":"0"}'
        self.files={'.claude.json':'{"synthetic_device":"original"}','settings.json':'{}'}
        self.work=DraftLoginWork(id='a'*32,sid='c'*12,environment_id='e'*32,name=self.settings.name,
            draft_generation='d'*32,version='2.1.293',home='/home/node/.v3-login/'+'c'*12,
            preparation_sha256=draft_preparation_sha256(self.settings,self.fingerprint,self.files),expires_at=int(time.time())+900)
        self.preparation=DraftLoginPreparation(node_key='b'*32,work=self.work,settings=self.settings,
            fingerprint_json=self.fingerprint,profile_files=self.files)
        self.scope=DraftLoginScope(operation_id=self.work.id,node_key=self.preparation.node_key,
            environment_id=self.work.environment_id,name=self.work.name,draft_generation=self.work.draft_generation,
            generation=2,source=self.work.source)
        self.grant=DraftLoginGrant(**self.scope.model_dump(),sequence=1,not_after=int(time.time())+25)
        with self.connection:
            self.connection.execute('UPDATE cluster_nodes SET preparation_json=? WHERE id=?',
                (json.dumps({'state':'prepared','release':'synthetic-release'}),self.node_id))
            self.connection.execute('UPDATE account_environments SET fingerprint_json=?',(self.fingerprint,))
        self.ledger=NodeLoginDrafts(self.store,'synthetic-release',Path('/synthetic/data'))

    def checkpoint(self, phase: str, **changes) -> dict:
        """以当前CAS版本保存原操作。:param phase: 新阶段。:param changes: 原事实。:return: 最新记录。"""
        row=self.ledger.get(self.work.id)
        return self.ledger.checkpoint(self.work.id,row['revision'],phase,**changes)

    def running(self) -> dict:
        """依次保存实际代次、有限证明和启动意图，再认领原Node回执。:return: 活动记录。"""
        self.ledger.begin(self.node_id,self.preparation)
        self.checkpoint('preparing',scope=self.scope)
        self.checkpoint('preparing',grant=self.grant,start_intent=True)
        return self.checkpoint('active',node_receipt=self.receipt('ready'))

    def receipt(self, phase: str, **changes) -> dict:
        """构造合成Node回执。:param phase: 原实际阶段。:param changes: 额外事实。:return: 回执。"""
        return {'protocol':1,'scope':self.scope.model_dump(),'phase':phase,
            'result':{'token':'synthetic-original-tmux','source':self.work.source},**changes}

    def accepted(self) -> dict:
        """合成原Node已保存授权并实际停止、清理暂存的完整事实。:return: 提交中记录。"""
        self.running()
        commit={'stage':'frozen','authorization_sha256':'1'*64,'refresh_sha256':'2'*64,
            'files':['.claude.json','.claude/.credentials.json'],'cleanup_pending':True,'auth_method':'oauth'}
        self.checkpoint('submitting',node_receipt=self.receipt('ready',commit=commit))
        return self.checkpoint('submitting',node_receipt=self.receipt('closed',commit={**commit,'stage':'accepted','cleanup_pending':False}))

    def test_initial_record_keeps_account_null_and_private_settings_outside_ledger(self) -> None:
        """初次登记冻结节点、配置摘要和逻辑代次，重建存储复用原记录。:return: None。"""
        row=self.ledger.begin(self.node_id,self.preparation)
        self.assertIsNone(row['record']['scope'])
        self.assertIsNone(self.connection.execute('SELECT account_id FROM account_environments').fetchone()[0])
        self.assertEqual(0,self.connection.execute('SELECT count(*) FROM accounts').fetchone()[0])
        restored=NodeLoginDrafts(self.store,'synthetic-release',self.ledger.data)
        self.assertEqual(row,restored.get(self.work.id))
        self.assertEqual(row,restored.by_sid(self.work.sid))
        self.assertEqual(row,restored.find(self.work.environment_id))
        self.assertEqual([row],restored.pending())
        self.assertEqual(row,self.ledger.begin(self.node_id,self.preparation))
        self.assertNotIn('synthetic-secret',json.dumps(row))
        self.assertNotIn('synthetic.proxy.invalid',json.dumps(row))

    def test_actual_scope_observation_and_start_intent_are_durable_before_node_start(self) -> None:
        """资源实际代次与证明先落库，活动状态须有原Node进程确认。:return: None。"""
        self.ledger.begin(self.node_id,self.preparation)
        for changes in ({'start_intent':True},{'grant':self.grant}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.checkpoint('preparing',**changes)
        row=self.checkpoint('preparing',scope=self.scope)
        self.assertEqual(2,self.connection.execute('SELECT generation FROM account_environments').fetchone()[0])
        with self.assertRaises(ValueError):
            self.checkpoint('active',grant=self.grant,start_intent=True)
        started=self.checkpoint('preparing',grant=self.grant,start_intent=True)
        self.assertTrue(started['record']['start_intent'])
        self.assertGreater(started['revision'],row['revision'])
        with self.assertRaises(ValueError):
            self.checkpoint('closed')

    def test_wrong_node_release_image_or_formal_profile_is_rejected_before_begin(self) -> None:
        """准入核对受信节点、同批发布、中央画像以及正式/软删除profile引用。:return: None。"""
        with self.assertRaises(ValueError):
            NodeLoginDrafts(self.store,'another-release',self.ledger.data).begin(self.node_id,self.preparation)
        for field,value in (('node_key','f'*32),('fingerprint_json','{"tz":"UTC","changed":true}')):
            request=self.preparation.model_dump()
            if field=='fingerprint_json':
                request[field]=value
                request['work']['preparation_sha256']=draft_preparation_sha256(self.settings,value,self.files)
            else:
                request[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.ledger.begin(self.node_id,DraftLoginPreparation.model_validate(request))
        for name,profile,deleted in (('draft_only','profiles/other',None),('other','profiles/draft_only',1)):
            with self.subTest(name=name):
                with self.connection:
                    account=self.connection.execute('INSERT INTO accounts(name,profile_path,deleted_at) VALUES(?,?,?)',
                        (name,profile,deleted)).lastrowid
                with self.assertRaisesRegex(ValueError,'正式或软删除'):
                    self.ledger.begin(self.node_id,self.preparation)
                with self.connection:
                    self.connection.execute('DELETE FROM accounts WHERE id=?',(account,))

    def test_scope_cas_and_grant_renewal_reject_stale_or_replaced_evidence(self) -> None:
        """旧CAS、跨环境Scope、回退截止和跳号证明保持拒绝。:return: None。"""
        row=self.running()
        for change in ({'scope':self.scope.model_copy(update={'generation':3})},{'start_intent':False},
                {'grant':self.grant.model_copy(update={'sequence':3})},
                {'grant':self.grant.model_copy(update={'sequence':2,'not_after':self.grant.not_after-1})}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.checkpoint('active',**change)
        new=self.grant.model_copy(update={'sequence':2,'not_after':self.grant.not_after+1})
        updated=self.checkpoint('active',grant=new)
        with self.assertRaisesRegex(ValueError,'版本已变化'):
            self.ledger.checkpoint(self.work.id,row['revision'],'active')
        self.assertEqual(updated,self.ledger.get(self.work.id))

    def test_changed_configuration_blocks_admission_but_keeps_original_stop_history(self) -> None:
        """停用节点后停止回执仍可保存，新输入准入等待原节点核对。:return: None。"""
        row=self.running()
        self.assertEqual(row,self.ledger.admit(self.work.id))
        with self.connection:
            self.connection.execute('UPDATE cluster_nodes SET enabled=0 WHERE id=?',(self.node_id,))
        with self.assertRaises(ValueError):
            self.ledger.admit(self.work.id)
        self.checkpoint('stopping')
        closed=self.checkpoint('closed',node_receipt=self.receipt('closed'))
        self.assertEqual(closed,self.ledger.get(self.work.id))
        self.assertEqual([],self.ledger.pending())
        with self.assertRaises(ValueError):
            self.checkpoint('closed',node_receipt=self.receipt('ready'))

    def test_restart_requires_closed_previous_scope_new_sid_generation_and_frozen_settings(self) -> None:
        """恢复保持原节点、原版本、代理与画像，只更换明确的新操作来源。:return: None。"""
        self.running()
        work=self.work.model_copy(update={'id':'f'*32,'sid':'f'*12,'draft_generation':'f'*32,'mode':'recover'})
        request=DraftLoginPreparation(**{**self.preparation.model_dump(),'work':work,'previous':self.scope})
        with self.assertRaisesRegex(ValueError,'停止回执'):
            self.ledger.begin(self.node_id,request,previous_revision=self.ledger.get(self.work.id)['revision'])
        self.checkpoint('stopping')
        old=self.checkpoint('closed',node_receipt=self.receipt('closed'))
        with self.assertRaises(ValueError):
            self.ledger.begin(self.node_id,request,previous_revision=old['revision']-1)
        changed=self.settings.model_copy(update={'upstream_socks5_pass':'different-private'})
        changed_work=work.model_copy(update={'preparation_sha256':draft_preparation_sha256(changed,self.fingerprint,self.files)})
        altered=DraftLoginPreparation(**{**request.model_dump(),'work':changed_work,'settings':changed})
        with self.assertRaises(ValueError):
            self.ledger.begin(self.node_id,altered,previous_revision=old['revision'])
        row=self.ledger.begin(self.node_id,request,previous_revision=old['revision'])
        self.assertEqual(work.id,row['operation_id'])
        self.assertEqual(self.scope.model_dump(),row['record']['previous'])
        self.assertEqual(work.home,row['record']['work']['home'])
        self.assertIsNone(self.ledger.by_sid(self.work.sid))

    def test_frozen_authorization_is_monotonic_and_cannot_be_cancelled_or_replaced(self) -> None:
        """开始提交后授权摘要及实际定位固定，取消和删除保持拒绝。:return: None。"""
        row=self.accepted()
        for phase in ('active','stopping','deleting','closed'):
            with self.subTest(phase=phase),self.assertRaises(ValueError):
                self.checkpoint(phase)
        receipt=row['record']['node_receipt']
        for change in ({'authorization_sha256':'f'*64},{'stage':'saved'},{'cleanup_pending':True}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.checkpoint('submitting',node_receipt={**receipt,'commit':{**receipt['commit'],**change}})

    def test_save_account_atomically_claims_environment_and_remote_assignment_disabled(self) -> None:
        """完整原Node事实后首次创建真实ID，账号/环境/远程归属/草稿记录同次发布。:return: None。"""
        row=self.accepted()
        saved=self.ledger.save_account(self.work.id,row['revision'],self.preparation,80,90)
        account_id=saved['saved_account_id']
        self.assertGreater(account_id,0)
        self.assertEqual(account_id,saved['record']['saved_account_id'])
        account=dict(self.connection.execute('SELECT * FROM accounts').fetchone())
        self.assertEqual((self.settings.name,0,None,self.settings.upstream_socks5_pass,80,90),
            (account['name'],account['enabled'],account['cc2api_account_id'],account['upstream_socks5_pass'],
            account['warmup_quota_5h_limit_percent'],account['warmup_quota_7d_limit_percent']))
        self.assertEqual(account_id,self.connection.execute('SELECT account_id FROM account_environments').fetchone()[0])
        assignment=dict(self.connection.execute('SELECT * FROM account_node_assignments').fetchone())
        self.assertEqual((self.node_id,1,'ready'),(assignment['node_id'],assignment['revision'],assignment['phase']))
        self.assertEqual('submitting',saved['phase'])
        restored=NodeLoginDrafts(self.store,'synthetic-release',self.ledger.data)
        self.assertEqual(saved,restored.save_account(self.work.id,row['revision'],self.preparation,80,90))
        self.assertEqual(1,self.connection.execute('SELECT count(*) FROM accounts').fetchone()[0])
        work=AccountLoginWork(id='f'*32,sid='f'*12,account_id=account_id,account_identity='synthetic-original',
            version=self.work.version,expires_at=self.work.expires_at)
        scope=ExecutionScope(operation_id=work.id,node_key=self.scope.node_key,account_id=account_id,
            environment_id=self.scope.environment_id,assignment_revision=1,generation=self.scope.generation,source=work.source,role='login')
        with self.assertRaisesRegex(ValueError,'中央账号'):
            NodeExecutions(self.store,'synthetic-release').begin(scope,work)
        with self.assertRaises(ValueError):
            self.checkpoint('closed')

    def test_failed_last_write_rolls_back_account_assignment_and_environment_claim(self) -> None:
        """真实SQLite最后一步失败使整个首次保存回滚，原操作可按同一授权恢复。:return: None。"""
        row=self.accepted()
        with self.connection:
            self.connection.execute("CREATE TRIGGER synthetic_fail_saved_draft BEFORE UPDATE ON node_login_drafts "
                "WHEN NEW.saved_account_id IS NOT NULL BEGIN SELECT RAISE(ABORT,'synthetic draft interruption'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'synthetic draft interruption'):
            self.ledger.save_account(self.work.id,row['revision'],self.preparation,80,90)
        self.assertEqual(0,self.connection.execute('SELECT count(*) FROM accounts').fetchone()[0])
        self.assertEqual(0,self.connection.execute('SELECT count(*) FROM account_node_assignments').fetchone()[0])
        self.assertIsNone(self.connection.execute('SELECT account_id FROM account_environments').fetchone()[0])
        self.assertEqual(row,self.ledger.get(self.work.id))
        with self.connection:
            self.connection.execute('DROP TRIGGER synthetic_fail_saved_draft')
        self.assertIsNotNone(self.ledger.save_account(self.work.id,row['revision'],self.preparation,80,90)['saved_account_id'])

    def test_finish_enables_once_after_same_node_activation_and_keeps_later_manual_disabled_state(self) -> None:
        """首次独立账号沿原可选设备证明语义收口，重复完成保留后续人工状态。:return: None。"""
        row=self.accepted()
        saved=self.ledger.save_account(self.work.id,row['revision'],self.preparation,80,90)
        request=DraftLoginActivation(scope=self.scope,account_id=saved['saved_account_id'],authorization_sha256='1'*64)
        activation=DraftLoginActivated(request=request,refresh_sha256='2'*64)
        with self.assertRaises(ValueError):
            self.ledger.finish(self.work.id,saved['revision'],activation.model_copy(update={'refresh_sha256':'f'*64}),'synthetic')
        closed=self.ledger.finish(self.work.id,saved['revision'],activation,'synthetic')
        self.assertEqual('closed',closed['phase'])
        self.assertEqual(1,self.connection.execute('SELECT enabled FROM accounts').fetchone()[0])
        with self.connection:
            self.connection.execute('UPDATE accounts SET enabled=0')
        self.assertEqual(closed,self.ledger.finish(self.work.id,saved['revision'],activation,'synthetic'))
        self.assertEqual(0,self.connection.execute('SELECT enabled FROM accounts').fetchone()[0])

    def test_existing_source_proof_must_match_frozen_authorization_and_enable_is_atomic(self) -> None:
        """已有来源证明错RT保持隔离，最终关闭失败也回滚账号启用。:return: None。"""
        row=self.accepted()
        saved=self.ledger.save_account(self.work.id,row['revision'],self.preparation,80,90)
        request=DraftLoginActivation(scope=self.scope,account_id=saved['saved_account_id'],authorization_sha256='1'*64)
        activation=DraftLoginActivated(request=request,refresh_sha256='2'*64)
        proof={'schema':1,'account_id':saved['saved_account_id'],'deployment_id':'synthetic','cli_version':self.work.version,
            'environment_id':self.work.environment_id,'device_id':'synthetic-device','email':'draft@example.invalid',
            'account_uuid':'synthetic-uuid','organization_uuid':None,'refresh_sha256':'f'*64}
        with self.connection:
            self.connection.execute('INSERT INTO local_credential_authorizations VALUES(?,?)',(saved['saved_account_id'],json.dumps(proof)))
        with self.assertRaisesRegex(ValueError,'来源证明'):
            self.ledger.finish(self.work.id,saved['revision'],activation,'synthetic')
        self.assertEqual(0,self.connection.execute('SELECT enabled FROM accounts').fetchone()[0])
        with self.connection:
            proof['refresh_sha256']='2'*64
            self.connection.execute('UPDATE local_credential_authorizations SET record_json=?',(json.dumps(proof),))
            self.connection.execute("CREATE TRIGGER synthetic_fail_finish BEFORE UPDATE ON node_login_drafts WHEN NEW.phase='closed' "
                "BEGIN SELECT RAISE(ABORT,'synthetic finish interruption'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'synthetic finish interruption'):
            self.ledger.finish(self.work.id,saved['revision'],activation,'synthetic')
        self.assertEqual(saved,self.ledger.get(self.work.id))
        self.assertEqual(0,self.connection.execute('SELECT enabled FROM accounts').fetchone()[0])
        with self.connection:
            self.connection.execute('DROP TRIGGER synthetic_fail_finish')
        self.assertEqual('closed',self.ledger.finish(self.work.id,saved['revision'],activation,'synthetic')['phase'])

    def test_premature_or_changed_submission_cannot_create_account(self) -> None:
        """实际停止、完整清理、原配置与CAS任一缺失时首次保存保持NULL。:return: None。"""
        row=self.running()
        with self.assertRaises(ValueError):
            self.ledger.save_account(self.work.id,row['revision'],self.preparation,80,90)
        self.checkpoint('stopping')
        self.checkpoint('closed',node_receipt=self.receipt('closed'))
        self.assertEqual(0,self.connection.execute('SELECT count(*) FROM accounts').fetchone()[0])

    def test_stale_cas_and_changed_private_configuration_are_rejected_before_first_save(self) -> None:
        """相同名字不能掩盖代理变更，提交CAS与原私有准备摘要一同核验。:return: None。"""
        row=self.accepted()
        with self.assertRaises(ValueError):
            self.ledger.save_account(self.work.id,row['revision']-1,self.preparation,80,90)
        settings=self.settings.model_copy(update={'upstream_socks5_pass':'another-private'})
        altered=self.preparation.model_copy(update={'settings':settings})
        with self.assertRaises(ValueError):
            self.ledger.save_account(self.work.id,row['revision'],altered,80,90)
        self.assertEqual(0,self.connection.execute('SELECT count(*) FROM accounts').fetchone()[0])

    def test_row_corruption_and_unknown_evidence_are_not_adopted_as_original_operation(self) -> None:
        """坏行保留为明确错误，额外正式账号字段不能混入NULL记录。:return: None。"""
        row=self.ledger.begin(self.node_id,self.preparation)
        with self.assertRaises(ValueError):
            self.checkpoint('preparing',saved_account_id=17)
        with self.connection:
            self.connection.execute('UPDATE node_login_drafts SET generation=?',('f'*32,))
        with self.assertRaisesRegex(ValueError,'冻结记录'):
            self.ledger.get(row['operation_id'])
