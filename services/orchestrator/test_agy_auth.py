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

    def test_refresh_omitted_rt_keeps_original_and_uncertainty_does_not_replay(self):
        """省略RT沿用原操作；断连后只允许对账。@return 无。"""
        identity = 'b'*32
        updated = document()
        del updated['token']['refresh_token']
        updated['token']['access_token'] = 'synthetic-at2'
        def launch(folder, state, **kwargs):
            self.token_file(folder, updated)
            return SimpleNamespace(wait=Mock(side_effect=TimeoutError))
        self.manager._launch = Mock(side_effect=launch)
        with self.assertRaises(ValueError): self.manager.refresh(identity, 1, 1, document(), '')
        with self.assertRaises(ValueError): self.manager.refresh(identity, 1, 1, document(), '')
        recovered = self.manager.recover(identity, 1, 1)
        self.assertEqual(recovered['document']['token']['refresh_token'], 'synthetic-rt1')
        self.assertEqual(self.manager._launch.call_count, 1)

    def test_code_submission_is_once_and_wrong_replay_is_rejected(self):
        """重复码复用回执，其他码和取消后的回包隔离。@return 无。"""
        identity = 'c'*32
        folder = self.manager._folder(identity)
        folder.mkdir(mode=0o700)
        state = dict(kind='authorization', operation_id=identity, created_at=time.time(), phase='authorizing',
            proxy_url='', container='synthetic', account_id=1, generation=1)
        atomic_json(folder/'state.json', state)
        self.manager._send = Mock(side_effect=lambda *_: self.token_file(folder, document()))
        result = self.manager.exchange(identity, 'synthetic-code')
        self.assertEqual(self.manager.exchange(identity, 'synthetic-code'), result)
        self.assertEqual(self.manager._send.call_count, 1)
        with self.assertRaises(ValueError): self.manager.exchange(identity, 'other-code')
        self.manager.cancel(identity)
        with self.assertRaises(ValueError): self.manager.exchange(identity, 'synthetic-code')
        self.assertEqual(self.manager.recover(identity, 1, 1)['document'], document())

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
