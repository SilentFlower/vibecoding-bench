"""已有独立Node登录的原Scope、输入回执及实际停止回归。"""
from __future__ import annotations

import json
import time
import threading
import base64
import select
import socket
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
from docker.errors import NotFound

from account_runtime import AccountRuntime
from cluster_execution_grants import ExecutionGrant
from cluster_login import NodeAccountLogins
from cluster_login_contract import AccountLoginAccept, AccountLoginCode, AccountLoginCodeRead, AccountLoginStart, AccountLoginWork
from cluster_pty import PtyInput
from cluster_terminal import TerminalInputQuery
from runtime_files import atomic_json
import test_cluster_credentials as credential_fixture


class NodeAccountLoginTests(unittest.TestCase):
    """真实节点SQLite/私有文件/有限证明，原Docker与tmux使用可观察替身。"""

    def setUp(self) -> None:
        """借用原已存在独立Node及其实际HOME身份。:return: None。"""
        fixture=credential_fixture.NodeCredentialTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.runtime=fixture,fixture.runtime
        self.runtime.execution_token=AccountRuntime.execution_token
        row=self.runtime._row('synthetic',1)
        top={'userID':'a'*64,'oauthAccount':{'accountUuid':'original-uuid','organizationUuid':'original-org',
            'emailAddress':'synthetic@example.invalid'}}
        self.old_credentials={'claudeAiOauth':{'accessToken':'synthetic-old-at','refreshToken':'synthetic-old-rt',
            'expiresAt':int((time.time()+3600)*1000)}}
        atomic_json(self.runtime._root(row)/'home/.claude.json',top)
        atomic_json(self.runtime._root(row)/'home/.claude/.credentials.json',self.old_credentials)
        atomic_json(fixture.executor.data/'profiles/synthetic/.claude.json',top)
        atomic_json(fixture.executor.data/'profiles/synthetic/.credentials.json',self.old_credentials)
        self.runtime._publish_login_home=AccountRuntime._publish_login_home.__get__(self.runtime,type(self.runtime))
        self.runtime.read_cli_identity=Mock(return_value={'device_id':'a'*64,'account_uuid':'original-uuid',
            'source':'fixture:config.userID'})
        self.work=AccountLoginWork(id='f'*32,sid='a'*12,account_id=1,account_identity=fixture.work.account_identity,
            version='2.1.303',expires_at=int(time.time())+1800)
        self.scope=fixture.scope.model_copy(update={'operation_id':self.work.id,'source':self.work.source})
        fixture.scope=self.scope
        fixture.grants.create(ExecutionGrant(**self.scope.model_dump(),not_after=1020))
        self.request=AccountLoginStart(scope=self.scope,work=self.work)
        self.actor=NodeAccountLogins(fixture.executor,fixture.host,fixture.grants)
        self.addCleanup(self.actor.close)
        self.runtime.begin_login=Mock(side_effect=self._begin)
        self.runtime.exec_cli=Mock(return_value=SimpleNamespace(exit_code=0,output=b'{"loggedIn":false}'))
        self.runtime.login_terminal_alive=Mock(return_value=True)
        self.url=('https://claude.ai/oauth/authorize?client_id=synthetic&response_type=code&'
            'redirect_uri=https%3A%2F%2Fplatform.claude.com%2Foauth%2Fcallback&scope=user%3Ainference&code_challenge='
            +'a'*43+'&code_challenge_method=S256&state='+'b'*43)
        self.runtime.capture_login_pane=Mock(return_value=self.url)
        self.runtime.send_login_code=Mock()

    def _begin(self, sid, account, version, force):
        self.assertEqual(self.work.sid,sid)
        self.assertTrue(force)
        row=self.runtime._row(account['name'],account['id'])
        self.fixture.active=True
        self.fixture.job={'row':row,'account':account,'source':self.scope.source,'token':'original-refresh-token',
            'exclusive':True,'shared_cli':False,'version':version,'tmux':sid,'tmux_socket':'/tmp/v3-login-'+sid+'.sock'}
        self.runtime.job_for_container=Mock(return_value=self.fixture.job)
        profile=self.runtime._root(row)/'home/.v3-login'/sid/'.claude'
        self.profile=profile
        atomic_json(profile/'.credentials.json',{'claudeAiOauth':{'accessToken':'synthetic-new-at',
            'refreshToken':'synthetic-new-rt','expiresAt':int((time.time()+3600)*1000)}})
        atomic_json(profile.parent/'.claude.json',{'userID':'a'*64,'oauthAccount':{'accountUuid':'original-uuid',
            'organizationUuid':'original-org','emailAddress':'synthetic@example.invalid'}})
        return row,SimpleNamespace(id='original-cli'),profile,'/home/node/.v3-login/'+sid

    def _ready(self) -> dict:
        self.actor.start(self.request)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            receipt=self.actor.get(self.scope)
            if receipt['phase']=='ready':
                return receipt
            time.sleep(.01)
        self.fail('原Node登录准备等待超时：'+str(receipt))

    def test_disabled_independent_login_preserves_state_until_central_authorization_commit(self) -> None:
        """已有停用独立账号的Node明确登录保留enabled，普通刷新许可保持独立。:return: None。"""
        with self.fixture.executor.database() as connection:
            connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
        self._ready()
        self.runtime.exec_cli.return_value=SimpleNamespace(exit_code=0,output=b'{"loggedIn":true,"authMethod":"oauth"}')
        committed=self.actor.commit(self.scope)
        self.assertEqual('saved',committed['commit']['stage'])
        with self.fixture.executor.database() as connection:
            self.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=1').fetchone()[0])

    def test_original_login_starts_once_observes_actual_cli_and_strictly_stops(self) -> None:
        """原登录复用冻结版本、当前HOME与暂存路径，文件存在不替代CLI认证检查。:return: None。"""
        receipt=self._ready()
        self.assertEqual(receipt,self.actor.start(self.request))
        self.runtime.begin_login.assert_called_once()
        observed=self.actor.observe(self.scope)
        self.assertEqual('authorizing',observed['phase'])
        self.assertFalse(observed['credentials_ready'])
        self.assertEqual(self.url,observed['authorization_url'])
        self.runtime.exec_cli.return_value=SimpleNamespace(exit_code=0,output=b'{"loggedIn":true,"accessToken":"private-token"}')
        observed=self.actor.observe(self.scope)
        self.assertEqual('ready_to_submit',observed['phase'])
        self.assertTrue(observed['credentials_ready'])
        self.assertNotIn('private-token',json.dumps(observed))
        self.runtime.exec_cli.return_value=SimpleNamespace(exit_code=1,output=b'{"loggedIn":false}')
        self.assertEqual('ended',self.actor.observe(self.scope)['phase'])
        stopped=self.actor.stop(self.scope)
        self.assertEqual('closed',stopped['phase'])
        self.assertEqual(stopped,self.actor.stop(self.scope))
        self.runtime.cleanup.assert_called_once()
        self.assertTrue(self.runtime.restore_execution.call_args.kwargs['account_login'])
        self.assertEqual('closed',self.fixture.grants.get(self.scope)['phase'])

    def test_code_receipt_persists_without_secret_and_duplicate_never_replays(self) -> None:
        """已投递及未知回执都持久查询，同标识重试只读原记录。:return: None。"""
        self._ready()
        request=AccountLoginCode(scope=self.scope,request_id='b'*32,code='synthetic-auth-code')
        receipt=self.actor.code(request)
        self.assertEqual('delivered',receipt['status'])
        self.assertEqual(receipt,self.actor.code(request))
        self.runtime.send_login_code.assert_called_once()
        self.runtime.send_login_code.side_effect=RuntimeError('合成可能已粘贴')
        uncertain=request.model_copy(update={'request_id':'c'*32})
        receipt=self.actor.code(uncertain)
        self.assertEqual('uncertain',receipt['status'])
        self.assertEqual(receipt,self.actor.code(uncertain))
        self.assertEqual(2,self.runtime.send_login_code.call_count)
        restarted=NodeAccountLogins(self.fixture.executor,self.fixture.host,self.fixture.grants)
        self.addCleanup(restarted.close)
        self.assertEqual(receipt,restarted.code_receipt(AccountLoginCodeRead(scope=self.scope,request_id='c'*32)))
        self.assertEqual('reconcile',restarted.get(self.scope)['phase'])
        files=list(self.actor._directory(self.scope).rglob('*.json'))
        self.assertTrue(files)
        self.assertTrue(all('synthetic-auth-code' not in path.read_text() for path in files))
        self.assertEqual('closed',restarted.stop(self.scope)['phase'])
        self.runtime.begin_login.assert_called_once()

    def test_prepared_cancel_fences_late_start(self) -> None:
        """原prepared取消保留幂等墓碑，迟到启动只查询原结束状态。:return: None。"""
        cancelled=self.actor.stop(self.scope)
        self.assertEqual(cancelled,self.actor.stop(self.scope))
        self.assertEqual(cancelled,self.actor.start(self.request))
        self.assertEqual(cancelled,self.actor.get(self.scope))
        self.runtime.begin_login.assert_not_called()

    def test_cancel_before_grant_creation_fences_late_prepared_proof(self) -> None:
        """许可创建响应未知时保留具体取消门禁，迟到证明只允许查询原结束状态。:return: None。"""
        request=self.request.model_copy(update={'scope':self.scope.model_copy(update={'operation_id':'c'*32}),
            'work':self.work.model_copy(update={'id':'c'*32})})
        cancelled=self.actor.stop(request.scope)
        self.assertEqual(cancelled,self.actor.get(request.scope))
        self.fixture.grants.create(ExecutionGrant(**request.scope.model_dump(),not_after=1020))
        self.assertEqual(cancelled,self.actor.start(request))
        self.assertEqual(cancelled,self.actor.stop(request.scope))
        self.runtime.begin_login.assert_not_called()
        for changed in ({'account_id':2},{'environment_id':'b'*32},{'assignment_revision':2},{'generation':2}):
            with self.assertRaises((ValueError,FileNotFoundError)):
                self.actor.stop(request.scope.model_copy(update={**changed,'operation_id':'d'*32}))

    def test_active_grant_without_execution_record_stays_unresolved(self) -> None:
        """已激活许可且丢失执行记录时保留原核对门禁。:return: None。"""
        self.fixture.grants.activate(self.scope)
        with self.assertRaisesRegex(ValueError,'已认领'):
            self.actor.stop(self.scope)
        self.assertFalse((self.actor._directory(self.scope)/'unsubmitted.json').exists())

    def test_interrupted_sending_projects_uncertain_without_replaying_code(self) -> None:
        """发送后终态落盘失败与新Actor恢复都只读未知回执。:return: None。"""
        self._ready()
        request=AccountLoginCode(scope=self.scope,request_id='b'*32,code='synthetic-auth-code')
        original=atomic_json
        def write(path,value):
            """仅注入原授权码终态写入失败。:return: 原文件写入结果。"""
            if path.name==request.request_id+'.json' and value.get('status')=='delivered':
                raise OSError('合成回执落盘失败')
            return original(path,value)
        with patch('cluster_login.atomic_json',side_effect=write):
            with self.assertRaises(OSError):
                self.actor.code(request)
        self.assertEqual('uncertain',self.actor.code(request)['status'])
        restarted=NodeAccountLogins(self.fixture.executor,self.fixture.host,self.fixture.grants)
        self.addCleanup(restarted.close)
        self.assertEqual('uncertain',restarted.code(request)['status'])
        self.runtime.send_login_code.assert_called_once()
        restarted.stop(self.scope)

    def test_discard_requires_actual_stop_then_removes_staged_materials(self) -> None:
        """明确取消先停止原tmux，暂存清理失败时保留记录并可重复清理。:return: None。"""
        self._ready()
        with patch.object(self.actor,'_cleanup_materials',side_effect=OSError('合成清理失败')):
            with self.assertRaises(OSError):
                self.actor.discard(self.scope)
        self.assertEqual('closed',self.actor.get(self.scope)['phase'])
        self.assertTrue(self.profile.exists())
        self.assertTrue(self.actor.discard(self.scope)['discarded'])
        self.assertFalse(self.profile.parent.exists())
        self.assertTrue(self.actor.discard(self.scope)['discarded'])
        self.runtime.cleanup.assert_called_once()

    def test_accept_cleanup_failure_keeps_original_commit_for_recovery(self) -> None:
        """接受后清理失败保留原提交摘要，重启仅完成本次清理。:return: None。"""
        self._ready()
        self.runtime.exec_cli.return_value=SimpleNamespace(exit_code=0,output=b'{"loggedIn":true}')
        receipt=self.actor.commit(self.scope)
        accepted=AccountLoginAccept(scope=self.scope,authorization_sha256=receipt['commit']['authorization_sha256'])
        with patch.object(self.actor,'_cleanup_materials',side_effect=OSError('合成清理失败')):
            with self.assertRaises(OSError):
                self.actor.accept(accepted)
        receipt=self.actor.get(self.scope)
        self.assertEqual('closed',receipt['phase'])
        self.assertTrue(receipt['commit']['cleanup_pending'])
        restarted=NodeAccountLogins(self.fixture.executor,self.fixture.host,self.fixture.grants)
        self.addCleanup(restarted.close)
        self.assertFalse(restarted.accept(accepted)['commit']['cleanup_pending'])
        self.assertEqual('synthetic-new-rt',restarted.snapshot(self.scope)['material']['refresh_token'])
        self.runtime.cleanup.assert_called_once()

    def test_expired_login_ttl_refuses_new_code_but_keeps_original_stop(self) -> None:
        """实际授权TTL到期即关闭新输入，原Scope仍可严格收口。:return: None。"""
        self._ready()
        request=AccountLoginCode(scope=self.scope,request_id='b'*32,code='synthetic-auth-code')
        with patch('cluster_login.time.time',return_value=self.work.expires_at+1):
            with self.assertRaisesRegex(ValueError,'过期'):
                self.actor.code(request)
        self.runtime.send_login_code.assert_not_called()
        self.assertEqual('closed',self.actor.stop(self.scope)['phase'])

    def test_missing_actual_container_closes_original_login_after_restart(self) -> None:
        """原CLI容器实际缺失时，恢复收口原Scope并保留无进程事实。:return: None。"""
        self._ready()
        self.fixture.active=False
        self.runtime.restore_execution=Mock(return_value=None)
        self.runtime._container=Mock(side_effect=NotFound('合成原容器已经删除'))
        restarted=NodeAccountLogins(self.fixture.executor,self.fixture.host,self.fixture.grants)
        self.addCleanup(restarted.close)
        self.assertEqual('closed',restarted.stop(self.scope)['phase'])
        self.assertEqual('closed',self.fixture.grants.get(self.scope)['phase'])
        self.runtime.cleanup.assert_not_called()

    def test_auth_status_alone_does_not_replace_staged_oauth_artifacts(self) -> None:
        """API密钥或其它认证状态不能替代本次实际OAuth产物。:return: None。"""
        self._ready()
        (self.profile/'.credentials.json').unlink()
        self.runtime.exec_cli.return_value=SimpleNamespace(exit_code=0,output=b'{"loggedIn":true}')
        observed=self.actor.observe(self.scope)
        self.assertFalse(observed['credentials_ready'])
        self.assertEqual('authorizing',observed['phase'])
        self.runtime.exec_cli.assert_not_called()
        self.actor.stop(self.scope)

    def test_commit_keeps_rt_private_until_matching_central_accept_and_actual_cleanup(self) -> None:
        """新授权先保存同一Node，中央确认前保持占用，完成后清除本次私有副本。:return: None。"""
        self._ready()
        home=self.runtime._root(self.fixture.job['row'])/'home/.claude/.credentials.json'
        self.assertEqual(self.old_credentials,json.loads(home.read_text()))
        self.runtime.exec_cli.return_value=SimpleNamespace(exit_code=0,output=b'{"loggedIn":true,"authMethod":"oauth"}')
        receipt=self.actor.commit(self.scope)
        self.assertEqual('saved',receipt['commit']['stage'])
        self.assertEqual('ready',receipt['phase'])
        self.assertEqual(receipt,self.actor.commit(self.scope))
        self.assertEqual('synthetic-new-rt',json.loads(home.read_text())['claudeAiOauth']['refreshToken'])
        self.assertNotIn('synthetic-new-rt',json.dumps(receipt))
        self.assertNotIn('synthetic-new-at',json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'中央确认'):
            self.actor.stop(self.scope)
        snapshot=self.actor.snapshot(self.scope)
        self.assertEqual('synthetic-new-rt',snapshot['material']['refresh_token'])
        self.assertEqual('a'*64,snapshot['cli_identity']['device_id'])
        self.runtime.exec_cli.assert_called_once()
        with self.assertRaisesRegex(ValueError,'不一致'):
            self.actor.accept(AccountLoginAccept(scope=self.scope,authorization_sha256='0'*64))
        accepted=AccountLoginAccept(scope=self.scope,authorization_sha256=receipt['commit']['authorization_sha256'])
        closed=self.actor.accept(accepted)
        self.assertEqual('closed',closed['phase'])
        self.assertFalse(closed['commit']['cleanup_pending'])
        self.assertEqual(closed,self.actor.accept(accepted))
        self.assertEqual('committed',self.actor.observe(self.scope)['phase'])
        self.assertFalse(self.profile.parent.exists())
        self.assertFalse((self.actor._directory(self.scope)/'authorization').exists())
        self.assertEqual('synthetic-new-rt',json.loads(home.read_text())['claudeAiOauth']['refreshToken'])
        self.runtime.cleanup.assert_called_once()

    def test_partial_commit_recovers_frozen_authorization_without_new_cli_or_code(self) -> None:
        """HOME成功而profile失败时保留原冻结材料，重启只补原落盘阶段。:return: None。"""
        self._ready()
        self.runtime.exec_cli.return_value=SimpleNamespace(exit_code=0,output=b'{"loggedIn":true}')
        original=atomic_json
        path=self.fixture.executor.data/'profiles/synthetic/.credentials.json'
        def write(target,value):
            """仅注入本次profile写入失败。:return: 原原子写入结果。"""
            if target==path:
                raise OSError('合成profile写入失败')
            return original(target,value)
        with patch('cluster_login.atomic_json',side_effect=write):
            with self.assertRaises(OSError):
                self.actor.commit(self.scope)
        self.assertEqual('home_saved',self.actor.get(self.scope)['commit']['stage'])
        self.assertEqual('synthetic-old-rt',json.loads(path.read_text())['claudeAiOauth']['refreshToken'])
        restarted=NodeAccountLogins(self.fixture.executor,self.fixture.host,self.fixture.grants)
        self.addCleanup(restarted.close)
        receipt=restarted.commit(self.scope)
        self.assertEqual('saved',receipt['commit']['stage'])
        self.assertEqual('synthetic-new-rt',json.loads(path.read_text())['claudeAiOauth']['refreshToken'])
        self.runtime.begin_login.assert_called_once()
        self.runtime.exec_cli.assert_called_once()
        restarted.accept(AccountLoginAccept(scope=self.scope,authorization_sha256=receipt['commit']['authorization_sha256']))

    def test_refresh_parent_must_be_physically_closed_before_new_login(self) -> None:
        """RT父来源仍在实际执行时拒绝新登录，真实停止后仅放行同身份明确登录。:return: None。"""
        parent=self.fixture.request.scope
        self.fixture.scope=parent
        entered,release=threading.Event(),threading.Event()
        self.addCleanup(release.set)
        def read():
            """保持本次原探针响应，以观察原Scope实际阶段。:return: 固定结果。"""
            entered.set()
            release.wait(5)
            return b'{"refreshed":true,"submitted":true}'
        self.fixture.stream.read=read
        self.fixture.actor.start(self.fixture.request)
        self.assertTrue(entered.wait(5))
        request=AccountLoginStart(scope=self.scope,work=self.work.model_copy(update={'refresh_scope':parent}))
        self.actor.credentials=self.fixture.actor
        with self.assertRaisesRegex(ValueError,'尚未实际停止'):
            self.actor.start(request)
        self.runtime.begin_login.assert_not_called()
        self.assertEqual('prepared',self.fixture.grants.get(self.scope)['phase'])
        release.set()
        deadline=time.monotonic()+5
        while self.fixture.actor.get(parent)['phase']!='closed':
            self.assertLess(time.monotonic(),deadline,'原RT维护仍未实际关闭')
            time.sleep(.01)
        self.fixture.scope=self.scope
        self.work,self.request=request.work,request
        self._ready()
        self.assertEqual('closed',self.actor.stop(self.scope)['phase'])

    def test_login_pty_attaches_original_tmux_and_unknown_input_blocks_next_input(self) -> None:
        """原登录PTY重连只attach同一tmux；部分输入及落盘中断保持未知。:return: None。"""
        self._ready()
        raw,peer=socket.socketpair()
        peer.settimeout(2)
        self.addCleanup(peer.close)
        self.runtime.environment_lock=Mock(side_effect=lambda environment:nullcontext())
        self.runtime.authorize_input=Mock()
        self.runtime.client.api.exec_create=Mock(return_value={'Id':'original-attach-exec'})
        self.runtime.client.api.exec_start=Mock(return_value=raw)
        self.assertIs(raw,self.actor.open_pty(self.scope))
        argv=self.runtime.client.api.exec_create.call_args.args[1]
        self.assertEqual(['tmux','-S','/tmp/v3-login-'+self.work.sid+'.sock','attach-session','-d','-t',self.work.sid],argv)
        peer.sendall(b'original-output')
        self.assertEqual(b'original-output',raw.recv(4096))
        data='本次选择\r'.encode()
        request=PtyInput(operation_id='1'*32,data=base64.b64encode(data).decode())
        receipt=self.actor.send_input(self.scope,request)
        self.assertEqual('sent',receipt['status'])
        self.assertEqual(data,peer.recv(4096))
        self.assertEqual(receipt,self.actor.send_input(self.scope,request))
        self.assertFalse(select.select([peer],[],[],.05)[0])
        self.actor.close_pty(self.scope)
        second,other=socket.socketpair()
        self.addCleanup(other.close)
        self.runtime.client.api.exec_start.return_value=second
        self.actor.open_pty(self.scope)
        self.runtime.begin_login.assert_called_once()
        self.actor.ptys[self.scope.operation_id]['raw']=Mock(send=Mock(return_value=1))
        second.close()
        partial=request.model_copy(update={'operation_id':'2'*32})
        self.assertEqual('unknown',self.actor.send_input(self.scope,partial)['status'])
        self.assertEqual('reconcile',self.actor.get(self.scope)['phase'])
        with self.assertRaisesRegex(ValueError,'核对'):
            self.actor.send_input(self.scope,request.model_copy(update={'operation_id':'3'*32}))
        with self.assertRaisesRegex(ValueError,'核对'):
            self.actor.code(AccountLoginCode(scope=self.scope,request_id='b'*32,code='synthetic-code'))
        restarted=NodeAccountLogins(self.fixture.executor,self.fixture.host,self.fixture.grants)
        self.addCleanup(restarted.close)
        self.assertEqual('unknown',restarted.input_receipt(TerminalInputQuery(scope=self.scope,operation_id='2'*32))['status'])
        self.actor.stop(self.scope)
