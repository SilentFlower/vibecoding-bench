"""使用临时私有文件和原生驱动替身验证 AGY 管理操作，不提交模型请求。"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from requests.exceptions import ReadTimeout

from agy_auth import AgyAuthManager, TOKEN_PATH, authorization_url, native_document, stage_auth_asset
from runtime_files import atomic_json


def document(refresh='synthetic-rt1'):
    """生成合成有效凭据。@param refresh 合成RT。@return 原生结构。"""
    return {'auth_method': 'consumer', 'token': {'access_token': 'synthetic-at1',
        'refresh_token': refresh, 'expiry': '2099-01-01T00:00:00Z'}}


class AgyAuthTests(unittest.TestCase):
    """覆盖授权归属、私有文件、唯一刷新及恢复。"""

    def setUp(self):
        """建立每例独立目录。@return 无。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name)
        self.client = Mock()
        self.manager = AgyAuthManager(self.client, self.data, self.data, 'synthetic-image', 'bridge')
        self.manager._stop = Mock()
        self.manager.verify = Mock(return_value={'email_address': 'synthetic@example.test', 'capabilities': {}})

    def token_file(self, folder, value):
        """模拟原生用户的原子保存。@param folder 操作目录。@param value 原生对象。@return 无。"""
        path = folder / 'home' / TOKEN_PATH
        atomic_json(path, value)
        os.chown(path, 1001, 1001)

    def test_management_verify_reads_quota_on_native_loopback(self):
        """管理刷新复用原生进程与绑定出口，并区分已知零和缺失。@return 无。"""
        driver = Mock()
        driver.exec_run.side_effect = [
            SimpleNamespace(exit_code=0, output=json.dumps({'GetUserStatus': {'userStatus': {
                'email': 'synthetic@example.test', 'planStatus': {'planInfo': {'planName': 'Pro'}}}}})),
            SimpleNamespace(exit_code=0, output=b'gemini-synthetic'),
            SimpleNamespace(exit_code=0, output=json.dumps({
                'GetAvailableModels': {'response': json.dumps({'models': {
                    'gemini-synthetic': {'model': 36, 'quotaInfo': {'remainingFraction': 0.25}}}})},
                'RetrieveUserQuotaSummary': {'response': {'groups': [{'displayName': 'Gemini', 'buckets': [
                    {'bucketId': 'synthetic-5h', 'window': '5h', 'remainingFraction': 0,
                        'resetTime': '2030-01-01T00:00:00Z'},
                    {'bucketId': 'synthetic-week', 'window': 'weekly'},
                ]}]}}
            })),
        ]

        def launch(folder, state, *, interactive, document):
            """为本地语言服务提供合成监听记录。@param folder 当前私有目录。@return 驱动替身。"""
            self.assertEqual('socks5h://synthetic.test:1080', state['proxy_url'])
            self.assertNotIn('refresh_token', document['token'])
            logs = folder / 'home/.gemini/antigravity-cli/log'
            logs.mkdir(parents=True)
            (logs / 'synthetic.log').write_text('Language server listening on random port at 12345 for HTTP')
            return driver

        with patch.object(self.manager, '_launch', side_effect=launch), patch.object(
                self.manager, 'verify', wraps=AgyAuthManager.verify.__get__(self.manager)):
            result = self.manager.handle('verify', {'document': document(), 'proxy_url': 'socks5h://synthetic.test:1080'})
        self.assertEqual(['12345', '{"forceRefresh":true}', 'GetAvailableModels', 'RetrieveUserQuotaSummary'],
            driver.exec_run.call_args_list[-1].args[0][-4:])
        self.assertEqual({'gemini-synthetic': 36}, result['capabilities']['model_mappings'])
        snapshot = result['platform_quota']
        self.assertEqual(('ok', 'Pro'), (snapshot['status'], snapshot['plan']))
        self.assertEqual(0.25, snapshot['models']['items'][0]['remaining_fraction'])
        windows = snapshot['groups']['items'][0]['windows']
        self.assertEqual(0, windows[0]['remaining_fraction'])
        self.assertIsNone(windows[1]['remaining_fraction'])

    def test_identity_only_verification_uses_at_without_model_catalog(self):
        """续期收尾只核验来源身份，避免再等待目录。@return 无。"""
        driver = Mock()
        driver.exec_run.return_value = SimpleNamespace(exit_code=0, output=json.dumps({
            'GetUserStatus': {'userStatus': {'email': 'synthetic@example.test'}}}))

        def launch(folder, state, *, interactive, document):
            self.assertNotIn('refresh_token', document['token'])
            logs = folder / 'home/.gemini/antigravity-cli/log'
            logs.mkdir(parents=True)
            (logs / 'synthetic.log').write_text('Language server listening on random port at 12345 for HTTP')
            return driver

        with patch.object(self.manager, '_launch', side_effect=launch):
            result = AgyAuthManager.verify(self.manager, document(), '', identity_only=True)
        self.assertEqual(result, {'email_address': 'synthetic@example.test'})
        driver.exec_run.assert_called_once()
        self.assertEqual(driver.exec_run.call_args.args[0][-1], 'GetUserStatus')

    def test_pkce_url_rejects_origin_callback_duplicates_and_fragment(self):
        """只接纳固定 Google PKCE 合同。@return 无。"""
        query = dict(client_id='synthetic', response_type='code', redirect_uri='https://antigravity.google/oauth-callback',
            scope='synthetic', code_challenge='A'*43, code_challenge_method='S256', state='synthetic')
        url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(query)
        self.assertEqual(authorization_url('\x1b]8;;'+url+'\x07授权\x1b]8;;\x07'), url)
        for invalid in [url+'&state=other', url+'#fragment', url.replace('accounts.google.com', 'accounts.google.com.evil.test'),
                url.replace('S256', 'plain'), url.replace('antigravity.google', 'evil.test')]:
            self.assertIsNone(authorization_url(invalid))

    def test_native_document_requires_timezone_and_retains_copy(self):
        """有效期严格解析且独立复制。@return 无。"""
        value = document()
        duplicate = native_document(value)
        duplicate['token']['refresh_token'] = 'synthetic-new'
        self.assertEqual(value['token']['refresh_token'], 'synthetic-rt1')
        for expiry in ['2099-01-01T00:00:00', None, 1, 'invalid']:
            value['token']['expiry'] = expiry
            with self.assertRaises(ValueError):
                native_document(value)

    def test_private_read_rejects_shared_link_and_wrong_owner(self):
        """私有材料只接受正确所有者的普通文件。@return 无。"""
        path = self.manager.root / 'result.json'
        atomic_json(path, document())
        path.chmod(0o644)
        with self.assertRaises(ValueError): self.manager._read(path)
        path.chmod(0o600)
        link = self.manager.root / 'link.json'
        link.symlink_to(path)
        with self.assertRaises(OSError): self.manager._read(link)
        os.chown(path, 1001, 1001)
        with self.assertRaises(ValueError): self.manager._read(path)

    def test_file_lock_excludes_another_process_and_releases(self):
        """原生刷新跨进程互斥。@return 无。"""
        code = 'import fcntl,sys; f=open(sys.argv[1],"r+"); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)'
        with self.manager._locked('account-1'):
            result = subprocess.run([sys.executable, '-c', code, str(self.manager.root/'account-1.lock')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        result = subprocess.run([sys.executable, '-c', code, str(self.manager.root/'account-1.lock')], capture_output=True)
        self.assertEqual(result.returncode, 0)
        (self.manager.root/'account-1.lock').chmod(0o644)
        with self.assertRaises(ValueError):
            with self.manager._locked('account-1'): pass

    def test_refresh_is_once_and_recover_preserves_rotated_material(self):
        """响应丢失只读取同操作回执；未知确认保留新RT。@return 无。"""
        identity = 'a'*32
        updated = document('synthetic-rt2')
        updated['token']['access_token'] = 'synthetic-at2'
        def launch(folder, state, **kwargs):
            self.assertEqual(kwargs['native_args'], ['models'])
            self.assertEqual(kwargs['document']['token']['expiry'], '1970-01-01T00:00:00Z')
            self.token_file(folder, updated)
            return SimpleNamespace(wait=lambda timeout: {'StatusCode': 0})
        self.manager._launch = Mock(side_effect=launch)
        first = self.manager.refresh(identity, 1, 1, document(), '')
        self.assertEqual(self.manager.refresh(identity, 1, 1, document(), ''), first)
        self.assertEqual(self.manager._launch.call_count, 1)
        folder = self.manager._folder(identity)
        state = self.manager._read(folder/'state.json')
        state['phase'] = 'reconcile'
        atomic_json(folder/'state.json', state)
        (folder/'result.json').unlink()
        self.assertEqual(self.manager.recover(identity, 1, 1)['document']['token']['refresh_token'], 'synthetic-rt2')
        for account, generation in [(2, 1), (1, 2)]:
            with self.assertRaises(ValueError): self.manager.recover(identity, account, generation)
        self.assertEqual(self.manager._launch.call_count, 1)

    def test_recover_status_reports_the_existing_writer_without_retiring(self):
        """原生账号文件锁仍由刷新持有时只返回原操作范围。@return 无。"""
        scope = {'operation_id': 'd'*32, 'account_id': 1, 'generation': 3}
        with self.manager._locked('account-1'):
            self.assertEqual({**scope, 'recovery_status': 'in_flight'},
                self.manager.handle('recover-status', scope))
            with self.assertRaises(ValueError):
                self.manager.handle('recover', scope)
            self.assertFalse(self.manager._folder(scope['operation_id']).exists())
        result = self.manager.handle('recover-status', scope)
        self.assertEqual('not_started', result['phase'])

    def test_refresh_wait_timeout_completes_with_saved_token(self):
        """等待超时后核验已落盘的新 AT，省略 RT 时保留原值。@return 无。"""
        identity = 'b'*32
        updated = document()
        del updated['token']['refresh_token']
        updated['token']['access_token'] = 'synthetic-at2'
        def launch(folder, state, **kwargs):
            self.token_file(folder, updated)
            return SimpleNamespace(wait=Mock(side_effect=ReadTimeout))

        def verify(candidate, proxy_url, *, identity_only):
            self.manager._stop.assert_called_once()
            self.assertEqual(candidate['token']['access_token'], 'synthetic-at2')
            self.assertTrue(identity_only)
            return {'email_address': 'synthetic@example.test'}

        self.manager.verify.side_effect = verify
        self.manager._launch = Mock(side_effect=launch)
        result = self.manager.refresh(identity, 1, 1, document(), '')
        self.assertEqual(result['document']['token']['refresh_token'], 'synthetic-rt1')
        self.assertNotIn('capabilities', result)
        self.assertEqual(self.manager.refresh(identity, 1, 1, document(), ''), result)
        self.assertEqual(self.manager.recover(identity, 1, 1), result)
        self.manager._launch.assert_called_once()
        self.manager.verify.assert_called_once()

    def test_refresh_nonzero_native_exit_recovers_rotated_rt(self):
        """原生命令异常退出后，保留同操作已经保存的新 RT。@return 无。"""
        updated = document('synthetic-rt2')
        updated['token']['access_token'] = 'synthetic-at2'

        def launch(folder, state, **kwargs):
            self.token_file(folder, updated)
            return SimpleNamespace(wait=lambda timeout: {'StatusCode': 1})

        self.manager._launch = Mock(side_effect=launch)
        result = self.manager.refresh('b'*32, 1, 1, document(), '')
        self.assertEqual(result['document'], updated)
        self.manager.verify.assert_called_once_with(updated, '', identity_only=True)

    def test_refresh_without_valid_output_stays_in_reconcile(self):
        """临时副本仍处于强制到期状态时保留原操作。@return 无。"""
        identity = 'b'*32

        def launch(folder, state, **kwargs):
            self.token_file(folder, kwargs['document'])
            return SimpleNamespace(wait=Mock(side_effect=ReadTimeout))

        self.manager._launch = Mock(side_effect=launch)
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, '待对账'):
                self.manager.refresh(identity, 1, 1, document(), '')
        self.assertEqual(self.manager._read(self.manager._folder(identity) / 'state.json')['phase'], 'reconcile')
        self.manager.verify.assert_not_called()
        self.manager._launch.assert_called_once()

    def test_refresh_without_verified_identity_keeps_saved_credential_for_recovery(self):
        """身份核验失败时保留同操作的新凭据，供后续对账。@return 无。"""
        identity = 'b'*32
        updated = document('synthetic-rt2')
        updated['token']['access_token'] = 'synthetic-at2'

        def launch(folder, state, **kwargs):
            self.token_file(folder, updated)
            return SimpleNamespace(wait=Mock(side_effect=ReadTimeout))

        self.manager._launch = Mock(side_effect=launch)
        self.manager.verify.side_effect = ValueError('synthetic-unverified-identity')
        with self.assertRaisesRegex(ValueError, '待对账'):
            self.manager.refresh(identity, 1, 1, document(), '')
        folder = self.manager._folder(identity)
        self.assertEqual(self.manager._read(folder / 'state.json')['phase'], 'reconcile')
        self.assertFalse((folder / 'result.json').exists())
        self.manager.verify.side_effect = None
        self.assertEqual(self.manager.recover(identity, 1, 1)['document'], updated)
        self.manager._launch.assert_called_once()

    def test_refresh_recovers_after_manager_restart_with_first_failure_and_identity_only(self):
        """两次核验失败后沿原落盘材料恢复，重启保留首因且仅消费一次 RT。@return 无。"""
        identity = 'c'*32
        updated = document('synthetic-rt2')
        updated['token']['access_token'] = 'synthetic-at2'

        def launch(folder, state, **kwargs):
            self.token_file(folder, updated)
            return SimpleNamespace(wait=lambda timeout: {'StatusCode': 0})

        self.manager._launch = Mock(side_effect=launch)
        self.manager.verify.side_effect = ValueError('synthetic-identity-rpc-unavailable')
        with self.assertRaisesRegex(ValueError, '待对账'):
            self.manager.refresh(identity, 1, 1, document(), '')
        restarted = AgyAuthManager(self.client, self.data, self.data, 'synthetic-image', 'bridge')
        restarted._launch = Mock(side_effect=AssertionError('旧 RT 不应重放'))
        restarted.verify = Mock(side_effect=[OSError('synthetic-private'), {'email_address': 'synthetic@example.test'}])
        pending = restarted.recover(identity, 1, 1, report_status=True)
        self.assertEqual(('retrying', 'identity_check'), (pending['recovery_status'], pending['first_failure']))
        self.assertNotIn('synthetic-private', json.dumps(pending))
        final = restarted.recover(identity, 1, 1, report_status=True)
        self.assertEqual((updated, 'identity_check'), (final['document'], final['first_failure']))
        self.assertEqual(final, restarted.recover(identity, 1, 1, report_status=True))
        self.assertTrue(all(call.kwargs == {'identity_only': True} for call in restarted.verify.call_args_list))
        self.manager._launch.assert_called_once()
        restarted._launch.assert_not_called()

    def test_invalid_grant_and_expired_material_remain_scoped(self):
        """有明确 OAuth 拒绝的原操作单独分类，未知到期材料保留人工核对。@return 无。"""
        for number, output, expected in [(1, b'{"error":"invalid_grant","secret":"synthetic"}', 'reauthorization_required'),
                                         (2, b'temporarily unavailable', 'needs_check')]:
            identity = str(number)*32

            def launch(folder, state, **kwargs):
                self.token_file(folder, kwargs['document'])
                return SimpleNamespace(wait=lambda timeout: {'StatusCode': 1}, logs=lambda **_: output)

            self.manager._launch = Mock(side_effect=launch)
            with self.assertRaisesRegex(ValueError, '待对账'):
                self.manager.refresh(identity, number, 1, document(), '')
            result = self.manager.recover(identity, number, 1, report_status=True)
            self.assertEqual(expected, result['recovery_status'])
            self.assertNotIn('synthetic', json.dumps(result))
            self.manager._launch.assert_called_once()
        self.manager.verify.assert_not_called()

    def test_reserved_authorization_does_not_restart_or_revive_retired_id(self):
        """预占会话首开、重试与终止使用同一身份。@return 无。"""
        identity = 'c'*32
        self.manager._launch = Mock(return_value=SimpleNamespace(logs=lambda **_: b'synthetic'))
        with patch('agy_auth.authorization_url', return_value='https://accounts.google.com/synthetic'):
            first = self.manager.start('', 1, 1, identity)
            self.assertEqual(identity, first['session_id'])
            self.assertEqual(first, self.manager.start('', 1, 1, identity))
            with self.assertRaises(ValueError):
                self.manager.start('', 2, 1, identity)
            self.assertEqual('authorizing', self.manager.recover(identity, 1, 1, report_status=True)['recovery_status'])
            self.manager.retire(identity, 1, 1)
            with self.assertRaises(ValueError):
                self.manager.start('', 1, 1, identity)
        self.manager._launch.assert_called_once()

    def test_refresh_without_writer_shutdown_stays_in_reconcile(self):
        """原容器收口失败时不得核验或发布其凭据。@return 无。"""
        identity = 'b'*32

        def launch(folder, state, **kwargs):
            self.token_file(folder, document('synthetic-rt2'))
            return SimpleNamespace(wait=lambda timeout: {'StatusCode': 0})

        self.manager._launch = Mock(side_effect=launch)
        self.manager._stop.side_effect = ValueError('synthetic-stop-unconfirmed')
        with self.assertRaises(ValueError):
            self.manager.refresh(identity, 1, 1, document(), '')
        self.assertEqual(self.manager._read(self.manager._folder(identity) / 'state.json')['phase'], 'reconcile')
        self.manager.verify.assert_not_called()
        self.assertFalse((self.manager._folder(identity) / 'result.json').exists())

    def test_code_submission_is_once_and_wrong_replay_is_rejected(self):
        """重复码复用回执，其他码和取消后的回包隔离。@return 无。"""
        identity = 'c'*32
        folder = self.manager._folder(identity)
        folder.mkdir(mode=0o700)
        state = dict(kind='authorization', operation_id=identity, created_at=time.time(), phase='authorizing',
            proxy_url='socks5h://candidate.example.test:1080', container='synthetic', account_id=1, generation=1)
        atomic_json(folder/'state.json', state)
        self.assertEqual(self.manager.handle('proxy-references', {'operations': [identity]}),
                         {'references': [[identity, state['proxy_url']]]})
        self.manager._send = Mock(side_effect=lambda *_: self.token_file(folder, document()))
        result = self.manager.exchange(identity, 'synthetic-code')
        self.assertEqual(result['proxy_url'], state['proxy_url'])
        self.manager.verify.assert_called_once_with(document(), state['proxy_url'])
        self.assertEqual(self.manager.exchange(identity, 'synthetic-code'), result)
        self.assertEqual(self.manager._send.call_count, 1)
        with self.assertRaises(ValueError): self.manager.exchange(identity, 'other-code')
        self.manager.cancel(identity)
        with self.assertRaises(ValueError): self.manager.exchange(identity, 'synthetic-code')
        recovered = self.manager.recover(identity, 1, 1)
        self.assertEqual(recovered['document'], document())
        self.assertEqual(recovered['proxy_url'], state['proxy_url'])
        with self.assertRaises(ValueError):
            self.manager.recover(identity, 1, 2)

    def test_container_ownership_is_checked_before_stop(self):
        """错误归属容器保持原状态。@return 无。"""
        self.client.containers.get.return_value.labels = {'vibebench.agy-operation': 'other'}
        manager = AgyAuthManager(self.client, self.data, self.data, 'synthetic', 'bridge')
        with self.assertRaises(ValueError): manager._stop({'container': 'synthetic', 'operation_id': 'original'})
        self.client.containers.get.return_value.remove.assert_not_called()

    def test_staging_is_optional_and_rejects_wrong_binary(self):
        """CC构建可省略AGY制品；错误制品阻断构建。@return 无。"""
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(stage_auth_asset(self.data/'staging')['available'])
        source = self.data/'synthetic-binary'
        source.write_bytes(b'synthetic')
        with self.assertRaises(ValueError): stage_auth_asset(self.data/'bad-staging', str(source))
        self.assertFalse((self.data/'bad-staging/agy-1.5.9').exists())

    def test_expired_authorization_cleanup_keeps_bound_unknown_material(self):
        """到期新建会话回收；关联未知结果保留对账材料。@return 无。"""
        for identity, target in [('d'*32,None),('e'*32,1)]:
            folder=self.manager._folder(identity)
            folder.mkdir(mode=0o700)
            atomic_json(folder/'state.json',dict(kind='authorization',operation_id=identity,
                account_id=target,created_at=time.time()-1900,phase='code_pending',code_digest='synthetic'))
            self.token_file(folder,document())
        self.manager.cleanup()
        self.assertFalse(self.manager._folder('d'*32).exists())
        folder=self.manager._folder('e'*32)
        self.assertEqual(self.manager._read(folder/'state.json')['phase'],'reconcile')
        self.assertTrue((folder/'home'/TOKEN_PATH).exists())

    def test_pending_code_survives_retry_without_second_delivery(self):
        """超时保存pending，后续只读取原终端结果。@return 无。"""
        identity='f'*32
        folder=self.manager._folder(identity)
        folder.mkdir(mode=0o700)
        atomic_json(folder/'state.json',dict(kind='authorization',operation_id=identity,
            created_at=time.time(),phase='authorizing',proxy_url='',container='synthetic'))
        self.manager._send=Mock()
        with patch('agy_auth.time.monotonic',side_effect=[0,46]):
            with self.assertRaises(ValueError): self.manager.exchange(identity,'synthetic-code')
        self.assertEqual(self.manager._read(folder/'state.json')['phase'],'code_pending')
        self.token_file(folder,document())
        self.manager.exchange(identity,'synthetic-code')
        self.assertEqual(self.manager._send.call_count,1)

    def test_import_survives_lost_ack_without_refreshing_or_replaying_rt(self):
        """手工候选在确认丢失后可按原代次恢复。@return 无。"""
        identity='1'*32
        candidate=document('synthetic-manual-rt')
        result=self.manager.prepare_import(identity,1,2,candidate,'')
        self.assertEqual(self.manager.prepare_import(identity,1,2,candidate,''),result)
        folder=self.manager._folder(identity)
        state=self.manager._read(folder/'state.json')
        state['phase']='reconcile'
        atomic_json(folder/'state.json',state)
        recovered=self.manager.recover(identity,1,2)
        self.assertEqual(recovered['document'],candidate)
        self.assertEqual(self.manager.verify.call_count,2)
        with self.assertRaises(ValueError): self.manager.recover(identity,2,2)

    def test_launch_failure_releases_authorization_capacity(self):
        """镜像能力缺失后会话进入失败终态。@return 无。"""
        self.manager._launch=Mock(side_effect=ValueError('synthetic-failure'))
        with self.assertRaises(ValueError): self.manager.start('',None,None)
        records=list(self.manager.root.glob('*/state.json'))
        self.assertEqual(len(records),1)
        self.assertEqual(self.manager._read(records[0])['phase'],'failed')

    def test_missing_operation_recovery_records_tombstone_and_rejects_late_rt(self):
        """未开始证明跨重启保留，迟到刷新与导入均拒绝消费RT。@return 无。"""
        identity='2'*32
        result=self.manager.recover(identity,1,1)
        self.assertEqual(result,dict(operation_id=identity,account_id=1,generation=1,phase='not_started',retired=True))
        self.manager._launch=Mock()
        with self.assertRaises(ValueError): self.manager.refresh(identity,1,1,document(),'')
        with self.assertRaises(ValueError): self.manager.prepare_import(identity,1,1,document(),'')
        self.manager._launch.assert_not_called()
        restarted=AgyAuthManager(self.client,self.data,self.data,'synthetic-image','bridge')
        self.assertEqual(restarted.recover(identity,1,1),result)
        with self.assertRaises(ValueError): restarted.retire(identity,2,1)
        with self.assertRaises(ValueError): restarted.retire(identity,1,2)

    def test_retire_completed_operation_keeps_material_and_blocks_old_result(self):
        """终止回执阻止旧操作发布，私有已轮换材料保留。@return 无。"""
        identity='3'*32
        value=document('synthetic-new-rt')
        self.manager.prepare_import(identity,1,1,value,'')
        result=self.manager.retire(identity,1,1)
        self.assertEqual(result['phase'],'retired')
        self.assertEqual(self.manager.recover(identity,1,1),result)
        self.assertEqual(self.manager._read(self.manager._folder(identity)/'input.json'),value)
        with self.assertRaises(ValueError): self.manager.prepare_import(identity,1,1,value,'')

    def test_expired_candidate_proxy_refresh_is_once_and_rotation_survives_failure(self):
        """到期候选按新线路刷新；身份读取失败后恢复已落盘新RT。@return 无。"""
        identity='4'*32
        original=document()
        original['token']['expiry']='2000-01-01T00:00:00Z'
        updated=document('synthetic-proxy-rotated-rt')
        updated['token']['access_token']='synthetic-proxy-at'
        proxy='http://new-proxy.example.test:8080'
        def launch(folder,state,**kwargs):
            self.assertEqual(state['proxy_url'],proxy)
            self.assertEqual(kwargs['native_args'],['models'])
            self.token_file(folder,updated)
            return SimpleNamespace(wait=lambda timeout:{'StatusCode':0})
        self.manager._launch=Mock(side_effect=launch)
        self.manager.verify.side_effect=ValueError('synthetic-lost-observation')
        with self.assertRaises(ValueError): self.manager.prepare_import(identity,1,1,original,proxy)
        self.assertEqual(self.manager._read(self.manager._folder(identity)/'state.json')['phase'],'reconcile')
        with self.assertRaises(ValueError): self.manager.prepare_import(identity,1,1,original,proxy)
        self.manager.verify.side_effect=None
        recovered=self.manager.recover(identity,1,1)
        self.assertEqual(recovered['document'],updated)
        self.assertEqual(recovered['proxy_url'],proxy)
        self.manager.verify.assert_called_with(updated,proxy)
        self.assertEqual(self.manager._launch.call_count,1)


if __name__ == '__main__':
    unittest.main()
