"""中央绑定登录的真实账本、同操作导入、长期门禁及响应未知恢复。"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from cluster_bound_login_runner import ClusterBoundAccountLogins
from cluster_credential_refresh import RemoteCredentialRefresh
import test_cluster_terminal_sessions as session_fixture


class _Peer(session_fixture._Peer):
    """固定Node操作替身，授权材料只留测试内存，接口收据保持无RT。"""

    def __init__(self, events) -> None:
        """登记可观察阶段。:param events: 共享调用顺序。:return: None。"""
        super().__init__()
        self.events,self.value,self.work,self.lost=events,None,None,None
        self.material={'access_token':'synthetic-new-at','refresh_token':'synthetic-new-rt','expires_at':int((time.time()+3600)*1000)}
        self.published=None

    def execution_environment(self, container, payload, operation):
        """模拟同一原Node登录，不自行执行Gateway导入。:param container: 原控制容器。:param payload: 原载荷。:param operation: 固定动作。:return: 私有回执。"""
        if not operation.startswith('account-bound-login-'):
            return super().execution_environment(container,payload,operation)
        self.calls.append(operation)
        action=operation.removeprefix('account-bound-login-')
        self.events.append('node:'+action)
        scope=payload.get('scope',payload)
        if action=='start':
            self.work=copy.deepcopy(payload['work'])
            self.value={'protocol':1,'scope':copy.deepcopy(scope),'phase':'ready',
                'result':{'token':'original-bound-login-token','source':scope['source']}}
        elif action=='get' and self.value is None:
            raise FileNotFoundError('合成Node尚无原登录记录')
        elif action=='commit' and 'commit' not in self.value:
            self.value['commit']={'stage':'frozen','authorization_sha256':'a'*64,
                'refresh_sha256':hashlib.sha256(self.material['refresh_token'].encode()).hexdigest(),
                'files':['.claude.json','.claude/.credentials.json'],'identity':copy.deepcopy(self.work['expected_identity']),
                'cleanup_pending':True,'auth_method':'oauth'}
        elif action=='publish':
            self.published=copy.deepcopy(payload)
            if self.value['commit']['stage']!='accepted':
                self.value['commit']['stage']='saved'
        elif action=='accept':
            self.value['phase']='closed'
            self.value['commit'].update(stage='accepted',cleanup_pending=False)
        elif action=='stop':
            if self.value is None:
                self.value={'protocol':1,'scope':copy.deepcopy(scope),'phase':'closed','result':None}
            self.value['phase']='closed'
        elif action=='discard':
            self.value.update(phase='closed',discarded=True)
        elif action=='abort':
            self.value['phase']='closed'
            self.value['commit'].update(aborted=True,cleanup_pending=False)
        result=copy.deepcopy(self.value)
        if action=='snapshot':
            if not self.value['commit']['cleanup_pending']:
                raise FileNotFoundError('合成原冻结授权已清理')
            result={'protocol':1,'scope':copy.deepcopy(scope),'authorization_sha256':'a'*64,
                'material':dict(self.material),'identity':{'user_id':'b'*64,**self.work['expected_identity']},
                'version':self.work['version'],'auth_method':'oauth','cli_identity':None}
        if self.lost==action:
            self.lost=None
            raise ConnectionError('合成Node动作已应用但响应丢失')
        return {'protocol':1,'node_key':scope['node_key'],'login':result}


class _Gateway:
    """明确模拟原真实排他lease及按操作ID幂等导入，非实际Rust网关。"""

    def __init__(self, peer, events) -> None:
        """建立原账号及导入回执。:param peer: 可观察Node。:param events: 原调用顺序。:return: None。"""
        self.peer,self.events,self.lease,self.owner=peer,events,None,None
        self.configuration={'account_id':7,'auth_type':'oauth','status':'active','email':'synthetic@example.invalid',
            'account_uuid':'original-uuid','organization_uuid':'original-org'}
        self.imports,self.payloads={},{}
        self.import_count=0
        self.drop_import,self.query_unknown=False,False

    def _request(self, method, path, payload=None):
        if path.endswith('/config'):
            return dict(self.configuration)
        if not path.endswith('/lease'):
            raise AssertionError('合成Gateway未知固定操作')
        if method=='POST':
            action=payload['operation']
            self.events.append('gateway:'+action)
            if action=='prepare':
                self.lease={'owner':payload['owner'],'generation':'original-bound-lease','expires_at':int(time.time())+30,
                    'exclusive':True,'shared_cli':False,'phase':'prepared'}
            else:
                if self.lease is None or any(payload[key]!=self.lease[key] for key in ('owner','generation')):
                    raise ValueError('合成原Gateway lease已经变化')
                if action=='claim':
                    self.lease['phase']='claimed'
                elif action=='heartbeat':
                    self.lease['expires_at']=int(time.time())+30
                elif action=='fence':
                    self.lease.update(phase='reconcile',expires_at=0)
                elif action=='release':
                    if self.peer.value is not None and self.peer.value['phase']!='closed':
                        raise AssertionError('Node实际停止前不能释放Gateway lease')
                    self.lease=None
                else:
                    raise AssertionError('合成Gateway lease动作无效')
        return {'lease':copy.deepcopy(self.lease),'holders':[copy.deepcopy(self.lease)] if self.lease else [],
            'active':0,'waiting':0,'importing':0}

    def import_status(self, account, operation):
        """查询同一导入结果，未知保持异常。:param account: 原账号。:param operation: 原操作。:return: 当前快照或None。"""
        self.events.append('gateway:import-status')
        if self.query_unknown:
            raise ConnectionError('合成导入仍在途')
        return copy.deepcopy(self.imports.get(operation))

    def import_credentials(self, account, payload):
        """同一原lease内导入一次。:param account: 原绑定。:param payload: 原冻结载荷。:return: 当前权威快照。"""
        if (self.lease is None or self.lease['phase']!='claimed' or self.lease['expires_at']<=time.time()
                or any(payload[key]!=self.lease[key] for key in ('owner','generation'))):
            raise ValueError('合成导入要求原有效排他lease')
        self.events.append('gateway:import')
        operation=payload['operation_id']
        if operation in self.payloads and self.payloads[operation]!=payload:
            raise ValueError('合成同操作导入载荷已经变化')
        if operation not in self.imports:
            self.payloads[operation]=copy.deepcopy(payload)
            self.import_count+=1
            self.imports[operation]={'account_id':account,**{key:payload[key] for key in ('access_token','refresh_token','expires_at')}}
            self.owner.receipt.update(stage='imported',import_operation_id=operation)
        if self.drop_import:
            self.drop_import=False
            raise ConnectionError('合成Gateway已导入但响应丢失')
        return copy.deepcopy(self.imports[operation])


class _Ownership:
    """原Owner接口的显式替身，实际协议由原所有权测试及真实Gateway纵向验证。"""

    def __init__(self, gateway, peer, events) -> None:
        """建立可观察长期门禁。:param gateway: 原Gateway。:param peer: Node。:param events: 原顺序。:return: None。"""
        self.gateway,self.peer,self.events=gateway,peer,events
        self.record,self.receipt=None,None
        self.original_reconcile,self.drop_finish=False,False

    def state(self, account):
        """读取原状态副本。:param account: 原账号。:return: 原记录或None。"""
        return copy.deepcopy(self.record)

    def guard(self, account, source=None):
        """保留原长期门禁。:param account: 原账号。:param source: 原来源。:return: None。"""
        if self.record and self.record['phase']!='ready':
            raise ValueError('合成长期开关仍需核对')

    def begin_reauth(self, account, sid):
        """冻结原长期来源。:param account: 原账号。:param sid: 原SID。:return: None。"""
        self.events.append('owner:prepare')
        self.record={'schema':1,'account_id':1,'remote_id':7,'original_binding':7,'owner':'gateway','phase':'reauth','stage':'prepared',
            'input':{'direction':'reauth','lease_owner':'login:'+sid,'identity':{'environment_id':'e'*32,'bench_account_id':1,
                'device_id':'b'*64,'email':'synthetic@example.invalid','account_uuid':'original-uuid','organization_uuid':'original-org'}}}
        self.receipt={'stage':'prepared'}

    def _rpc(self, record, action):
        """只查询原回执或重建同一暂停。:param record: 原记录。:param action: 固定动作。:return: 原回执。"""
        if action=='prepare' and self.receipt is None:
            self.receipt={'stage':'prepared'}
        return {'protocol':1,'receipt':copy.deepcopy(self.receipt)}

    def close_reauth(self, account, sid):
        """Node实际停止和lease释放后才结束长期门禁。:param account: 原账号。:param sid: 原SID。:return: None。"""
        if self.record['phase']=='ready':
            return
        if self.gateway.lease is not None or self.peer.value is not None and self.peer.value['phase']!='closed':
            raise AssertionError('长期门禁不能先于Node停止及lease释放')
        self.events.append('owner:finish' if self.receipt['stage']=='imported' else 'owner:cancel')
        imported=self.receipt['stage']=='imported'
        self.receipt['stage']='committed' if imported else 'cancelled'
        pending=self.original_reconcile and not imported
        self.record.update(phase='reconcile' if pending else 'ready',stage='ready',gateway_refresh_pending=pending)
        if self.drop_finish:
            self.drop_finish=False
            raise ConnectionError('合成长期finish已完成但响应丢失')


class ClusterBoundLoginTests(unittest.TestCase):
    """真实中央Scope/SQLite/活动，Node、Gateway与Owner使用明确故障替身。"""

    def setUp(self) -> None:
        """建立原绑定及唯一账号锁。:return: None。"""
        fixture=session_fixture.TerminalSessionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.sessions=fixture,fixture.sessions
        self.events=[]
        self.peer=_Peer(self.events)
        self.gateway=_Gateway(self.peer,self.events)
        self.owner=_Ownership(self.gateway,self.peer,self.events)
        self.gateway.owner=self.owner
        self.sessions.gateway=self.gateway
        self.sessions.service.connection=lambda node:self.peer
        self.sessions.service.prepare_remote_login=Mock()
        self.sessions.runtime._row=lambda *args:{'environment_id':'e'*32,'generation':4}
        with self.sessions.service.store.database() as connection:
            self.account=dict(connection.execute('SELECT * FROM accounts WHERE id=1').fetchone())
        self.owner_lock=threading.Lock()
        credentials=RemoteCredentialRefresh(self.sessions,self.owner,lambda name:self.owner_lock,
            lambda account:'unused',lambda account:'2.1.293')
        self.addCleanup(credentials.close)
        self.save=Mock(side_effect=lambda *args:self.events.append('central:mirror'))
        self.logins=ClusterBoundAccountLogins(self.sessions,credentials,lambda name:self.owner_lock,self.save)
        self.logins.identity_reader=SimpleNamespace(read=Mock(return_value={'device_id':'b'*64,'environment_id':'e'*32}))
        self.logins._watch=Mock()
        self.addCleanup(self.logins.close)

    def _start(self):
        return self.logins.start(self.account,'a'*12,'2.1.293')

    def test_original_gateway_import_and_long_gate_follow_actual_node_cleanup(self) -> None:
        """原真实模式、单次导入、Node清理、lease释放和长期finish按顺序完成。:return: None。"""
        row=self._start()
        operation=row['operation_id']
        self.assertTrue(row['record']['lease']['exclusive'])
        self.assertIsNone(row['record']['quota_identity'])
        self.logins._renew(operation)
        self.assertEqual(2,self.sessions.ledger.get(operation)['record']['grant']['sequence'])
        result=self.logins.commit(operation)
        self.assertEqual(7,result['cc2api_account_id'])
        self.assertTrue(result['credentials_synced'])
        self.assertEqual(1,self.gateway.import_count)
        self.assertLess(self.events.index('gateway:import'),self.events.index('node:publish'))
        self.assertLess(self.events.index('node:accept'),self.events.index('gateway:release'))
        self.assertLess(self.events.index('gateway:release'),self.events.index('owner:finish'))
        self.assertEqual([],self.sessions.ledger.pending())
        self.assertEqual({},self.sessions.activities)
        self.assertNotIn('synthetic-new-rt',json.dumps(self.sessions.ledger.get(operation)))
        self.assertEqual(result,self.logins.commit(operation))
        self.assertEqual(1,self.gateway.import_count)

    def test_unknown_gateway_import_recovers_original_status_without_resubmitting(self) -> None:
        """导入响应丢失保留长期暂停，恢复只读取同一回执并完成当前AT发布。:return: None。"""
        operation=self._start()['operation_id']
        self.gateway.drop_import=True
        with self.assertRaises(ConnectionError):
            self.logins.commit(operation)
        self.assertEqual('reauth',self.owner.record['phase'])
        self.assertTrue(self.peer.value['commit']['cleanup_pending'])
        self.logins.recover_pending()
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual(1,self.gateway.import_count)
        self.assertEqual(1,self.peer.calls.count('account-bound-login-start'))

    def test_unknown_node_accept_recovers_with_gateway_current_rotated_credentials(self) -> None:
        """Node清理响应丢失后使用Gateway当前快照，原已清理RT不会再次读取。:return: None。"""
        operation=self._start()['operation_id']
        self.peer.lost='accept'
        with self.assertRaises(ConnectionError):
            self.logins.commit(operation)
        self.gateway.imports[operation].update(access_token='gateway-later-at',refresh_token='gateway-later-rt')
        self.logins.recover_pending()
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual('gateway-later-at',self.peer.published['access_token'])
        self.assertEqual('gateway-later-rt',self.save.call_args.args[1]['material']['refresh_token'])
        self.assertEqual(1,self.gateway.import_count)
        self.assertEqual(1,self.peer.calls.count('account-bound-login-snapshot'))

    def test_unknown_long_finish_keeps_ledger_until_same_source_recovers(self) -> None:
        """长期finish响应丢失后中央账本保持占用，恢复只确认原完成阶段。:return: None。"""
        operation=self._start()['operation_id']
        self.owner.drop_finish=True
        with self.assertRaises(ConnectionError):
            self.logins.commit(operation)
        self.assertEqual('reconcile',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual('ready',self.owner.record['phase'])
        self.logins.recover_pending()
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual(1,self.gateway.import_count)

    def test_frozen_cancel_fences_then_checks_import_and_preserves_original_reconcile(self) -> None:
        """明确未导入才删除本次RT，取消原reconcile来源仍保持长期隔离。:return: None。"""
        operation=self._start()['operation_id']
        row,request=self.logins._row(operation)
        self.logins._call(row,'commit',request.scope.model_dump())
        self.owner.original_reconcile=True
        self.logins.cancel(operation)
        self.assertLess(self.events.index('gateway:fence'),self.events.index('node:abort'))
        self.assertTrue(self.peer.value['commit']['aborted'])
        self.assertEqual('reconcile',self.owner.record['phase'])
        self.assertTrue(self.owner.record['gateway_refresh_pending'])
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual(0,self.gateway.import_count)

    def test_cancel_import_query_unknown_keeps_original_rt_and_long_gate(self) -> None:
        """fence后回执仍未知时保持原RT暂存与长期暂停。:return: None。"""
        operation=self._start()['operation_id']
        row,request=self.logins._row(operation)
        self.logins._call(row,'commit',request.scope.model_dump())
        self.gateway.query_unknown=True
        with self.assertRaises(ConnectionError):
            self.logins.cancel(operation)
        self.assertTrue(self.peer.value['commit']['cleanup_pending'])
        self.assertNotIn('node:abort',self.events)
        self.assertEqual('reauth',self.owner.record['phase'])

    def test_cancel_of_known_import_finishes_original_scope_instead_of_aborting(self) -> None:
        """已导入回执确认后取消接完成分支，原授权不会被当成未提交销毁。:return: None。"""
        operation=self._start()['operation_id']
        self.gateway.drop_import=True
        with self.assertRaises(ConnectionError):
            self.logins.commit(operation)
        self.logins.cancel(operation)
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual('accepted',self.peer.value['commit']['stage'])
        self.assertNotIn('node:abort',self.events)
        self.assertEqual(1,self.gateway.import_count)

    def test_expired_unsubmitted_frozen_login_recovers_through_fence_and_abort(self) -> None:
        """原lease到期且明确未导入时，恢复只取消同一冻结授权。:return: None。"""
        operation=self._start()['operation_id']
        row,request=self.logins._row(operation)
        self.logins._call(row,'commit',request.scope.model_dump())
        self.sessions._isolate(operation,'synthetic_restart')
        self.gateway.lease['expires_at']=int(time.time())-1
        self.logins.recover_pending()
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertTrue(self.peer.value['commit']['aborted'])
        self.assertEqual(0,self.gateway.import_count)

    def test_published_node_without_original_gateway_receipt_stays_isolated(self) -> None:
        """Node已发布且原导入回执缺失时保持隔离，原RT不会作为新导入重放。:return: None。"""
        operation=self._start()['operation_id']
        self.peer.lost='publish'
        with self.assertRaises(ConnectionError):
            self.logins.commit(operation)
        self.gateway.imports.clear()
        self.logins.recover_pending()
        self.assertEqual('reconcile',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual(1,self.gateway.import_count)
        self.assertTrue(self.peer.value['commit']['cleanup_pending'])

    def test_wrong_long_ownership_import_link_keeps_gateway_paused_after_node_cleanup(self) -> None:
        """长期回执关联其它导入操作时保持暂停，原Node实际清理证据继续保留。:return: None。"""
        operation=self._start()['operation_id']
        self.peer.lost='publish'
        with self.assertRaises(ConnectionError):
            self.logins.commit(operation)
        self.owner.receipt['import_operation_id']='f'*32
        self.logins.recover_pending()
        self.assertEqual('reconcile',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual('reauth',self.owner.record['phase'])
        self.assertFalse(self.peer.value['commit']['cleanup_pending'])
        self.assertNotIn('owner:finish',self.events)

    def test_unknown_start_recovery_never_restarts_cli_or_imports(self) -> None:
        """启动响应未知恢复只停止原操作与取消长期暂停，原CLI只启动一次。:return: None。"""
        self.peer.lost='start'
        with self.assertRaises(ConnectionError):
            self._start()
        operation=self.logins.find('a'*12)['operation_id']
        self.logins.recover_pending()
        self.assertEqual('closed',self.sessions.ledger.get(operation)['phase'])
        self.assertEqual(1,self.peer.calls.count('account-bound-login-start'))
        self.assertEqual(0,self.gateway.import_count)

    def test_busy_original_owner_skips_background_recovery(self) -> None:
        """原不可重入owner锁占用时跳过该账号恢复。:return: None。"""
        self.peer.lost='start'
        with self.assertRaises(ConnectionError):
            self._start()
        calls=list(self.peer.calls)
        with self.owner_lock:
            self.logins.recover_pending()
        self.assertEqual(calls,self.peer.calls)
