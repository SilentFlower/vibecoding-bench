"""交互选线的真实SQLite比较保存及维护失败边界。"""
import threading
import unittest
import os
from contextlib import nullcontext
from unittest.mock import Mock, patch

from task_proxy import TaskProxyActivity, ProxySelectionConflict, read_account, snapshot, save_selection
import test_proxy_sync as proxy_sync_fixtures


class TaskProxyTests(unittest.TestCase):
    """复用同步测试的合成数据库，测试交互保存与后台同步的区别。"""

    def setUp(self):
        """准备真实库和受控环境。@return None。"""
        proxy_sync_fixtures.ProxySyncTests.setUp(self)
        self.secret = 'synthetic-selection-secret-' * 2
        self.gateway = Mock()
        self.write_lock = threading.Lock()

    def current(self):
        """取得当前私有快照。@return 内部数据。"""
        return snapshot(read_account(self.database, 1), self.gateway, self.secret)

    def test_activity_and_expired_authorization_fail_before_environment_changes(self):
        """重复活动及失效票据均关闭写入，异常退出清理登记。@return None。"""
        activity = TaskProxyActivity()
        before = self.current()
        def rejected(account):
            self.assertTrue(activity.active())
            raise ProxySelectionConflict('授权已失效')
        with self.assertRaises(ProxySelectionConflict):
            with activity.track('a' * 32):
                with self.assertRaises(ProxySelectionConflict):
                    with activity.track('a' * 32):
                        self.fail('重复操作不能再次进入')
                self.assertTrue(activity.active())
                save_selection(1, {'connection': '', 'selection_revision': before['selection_revision']},
                    self.database, self.write_lock, self.runtime, lambda _: self.owner, lambda _: self.profile,
                    self.active, self.gateway, self.secret, authorize=rejected)
        self.assertFalse(activity.active())
        self.runtime._stop_environment.assert_not_called()
        self.assertEqual(self.current(), before)

    def test_api_registers_activity_before_claim_and_references_guard_pending_target(self):
        """实际入口把票据领取与引用保护接入同一次保存。@return None。"""
        import main
        activity = TaskProxyActivity()
        calls = []
        def gateway(method, path, body=None):
            self.assertTrue(activity.active())
            self.assertFalse(main.v3_proxy_references()['complete'])
            calls.append((method, path, body))
            return {'claimed': True}
        body = main.TaskProxySelectionIn(selection_revision=self.current()['selection_revision'], connection='', operation_id='a' * 32)
        with patch.multiple(main, V3_ENABLED=True, account_runtime=self.runtime, login_manager=Mock(has_active_name=self.active),
                task_proxy_activity=activity, get_db=self.database, _db_lock=self.write_lock,
                _oauth_owner_lock=lambda _:self.owner, _profile_lock=lambda _:self.profile,
                credential_ownership=None, cc2api_client=Mock(_request=gateway), _login_drafts=lambda:None), \
                patch.dict(os.environ, {'V3_INTERNAL_TOKEN':self.secret}), \
                patch.object(main.UPDATE_GATE, 'admission', return_value=nullcontext()):
            result = main.put_task_proxy_selection(1, body)
            self.assertEqual(result['connection'], '')
            self.assertTrue(main.v3_proxy_references()['complete'])
        self.assertFalse(activity.active())
        self.assertEqual(calls, [('POST', '/admin/runtime/task-proxy-operations/' + 'a' * 32 + '/claim',
            {'account_id':1, 'gateway_account_id':None, 'selection_revision':body.selection_revision, 'connection':''})])

    def test_reference_snapshot_is_incomplete_if_selection_finishes_during_read(self):
        """读取结束时空闲仍须拒绝跨越提交的旧引用快照。@return None。"""
        activity = TaskProxyActivity()
        def old_snapshot():
            with activity.track('b' * 32):
                pass
            return {'references': [], 'complete': True}
        self.assertFalse(activity.references(old_snapshot)['complete'])
        self.assertTrue(activity.references(lambda:{'references': [], 'complete': True})['complete'])

    def save(self, connection, revision=None):
        """调用真实交互保存。@param connection 合成目标。@param revision 可选原版本。@return 快照。"""
        return save_selection(1, {'connection': connection, 'selection_revision': revision or self.current()['selection_revision']},
            self.database, self.write_lock, self.runtime, lambda _: self.owner, lambda _: self.profile,
            self.active, self.gateway, self.secret)

    def test_independent_switch_direct_and_noop(self):
        """空闲选线、直连和同配置保存保持业务字段。@return None。"""
        before = self.current()
        self.save(before['connection'])
        self.runtime._stop_environment.assert_not_called()
        saved = self.save('http://new%40user:p%3Ass@new.test')
        self.assertNotEqual(saved['selection_revision'], before['selection_revision'])
        row = read_account(self.database, 1)
        self.assertEqual((row['upstream_socks5_user'], row['upstream_socks5_pass'], row['upstream_socks5_port']), ('new@user', 'p:ss', 80))
        self.assertEqual(row['enabled'], 1)
        self.assertEqual(self.save('')['connection'], '')
        self.assertIsNone(read_account(self.database, 1)['upstream_socks5_port'])

    def test_stale_binding_source_and_deleted_rejected(self):
        """原配置和关联变化不作为后台同步的跳过成功。@return None。"""
        version = self.current()['selection_revision']
        self.save('socks5://new.test:1080')
        with self.assertRaises(ProxySelectionConflict):
            self.save('http://other.test:8080', version)
        with self.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=9')
        self.gateway.return_value = {'proxy_url':'http://bound.test:8080'}
        with self.assertRaises(ProxySelectionConflict):
            self.save('', version)
        with self.database() as connection:
            connection.execute("UPDATE accounts SET deleted_at='removed'")
        with self.assertRaises(LookupError):
            self.save('', version)

    def test_busy_login_lock_and_stop_failure_preserve_source(self):
        """未知或繁忙不会写新配置；失败后锁可再次取得。@return None。"""
        before = self.current()
        for reason in ['owner','login','jobs','sender','stop']:
            with self.subTest(reason=reason):
                self.active.return_value = reason == 'login'
                self.runtime.environment_jobs.return_value = ['job'] if reason == 'jobs' else []
                self.runtime._running_sender_active.return_value = reason == 'sender'
                self.runtime._stop_environment.side_effect = RuntimeError('停止失败') if reason == 'stop' else None
                if reason == 'owner': self.owner.acquire()
                try:
                    with self.assertRaises((ProxySelectionConflict, RuntimeError)):
                        self.save('', before['selection_revision'])
                finally:
                    if reason == 'owner': self.owner.release()
                self.assertEqual(self.current()['connection'], before['connection'])
                self.assertTrue(self.owner.acquire(blocking=False));self.owner.release()
                self.assertTrue(self.profile.acquire(blocking=False));self.profile.release()

    def test_bound_uses_authority_and_private_compare_callback(self):
        """关联网关时以网关真实连接生成版本，并在身份锁内调用受控写入。@return None。"""
        with self.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=9')
        authority = {'proxy_url':'http://actual.test:8080'}
        calls = []
        def gateway(method, path, body=None):
            if method == 'GET': return dict(authority)
            self.assertTrue(self.owner.locked());self.assertTrue(self.profile.locked())
            self.assertEqual(path, '/admin/runtime/accounts/9/proxy-selection')
            self.assertEqual(body['expected_connection'], authority['proxy_url'])
            calls.append(body);authority['proxy_url']=body['connection'];return {'ok':True}
        self.gateway = gateway
        self.assertEqual(self.current()['connection'], authority['proxy_url'])
        self.save('socks5h://bound:private@new.test:1080')
        self.assertEqual(len(calls), 1)
        self.assertEqual(read_account(self.database, 1)['upstream_socks5_host'], 'new.test')
        self.runtime._stop_environment.assert_not_called()

    def test_gateway_failure_and_invalid_payload_preserve_local(self):
        """内部写入失败保留配置；未知字段与错误版本拒绝。@return None。"""
        version = self.current()['selection_revision']
        self.assertNotIn('old.test', version)
        with self.assertRaises(ProxySelectionConflict): self.save('', '0'*64)
        with self.database() as connection: connection.execute('UPDATE accounts SET cc2api_account_id=9')
        def failed(method, path, body=None):
            if method == 'GET':return {'proxy_url':'http://actual.test:8080'}
            raise ConnectionError('合成内部故障')
        self.gateway=failed
        with self.assertRaises(ConnectionError):self.save('')
        self.assertEqual(read_account(self.database, 1)['upstream_socks5_host'], 'old.test')


if __name__ == '__main__':
    unittest.main()
