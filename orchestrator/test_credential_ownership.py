"""真实 SQLite、HOME 和运行时的交接恢复测试；远端回执为可注入故障的合成替身。"""
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

import main
from account_runtime import AccountRuntime, atomic_json
from credential_ownership import CredentialOwnership


class CredentialOwnershipTests(unittest.TestCase):
    """验证本地持久化边界，实际网关 HTTP 另由容器场景验证。"""

    def setUp(self) -> None:
        """准备原 ID、完整镜像、AT-only HOME 与可恢复回执。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, value in [('DB_PATH', self.root / 'db.sqlite'), ('BENCH_DATA', self.root),
                ('PROFILES_DIR', self.root / 'profiles'), ('TOPICS_FILE', self.root / 'missing'),
                ('login_manager', None), ('continue_manager', None), ('warmup_scheduler', None)]:
            guard = patch.object(main, name, value)
            guard.start()
            self.addCleanup(guard.stop)
        guard = patch.dict(os.environ, {'V3_DEPLOYMENT_ID': 'ownership-unit', 'V3_ACCOUNT_IMAGE': 'synthetic',
            'V3_NETWORK': 'synthetic', 'V3_RELEASE': 'synthetic'})
        guard.start()
        self.addCleanup(guard.stop)
        main.init_db()
        with closing(main.get_db()) as database, database:
            database.execute("INSERT INTO accounts(id,name,profile_path,cc2api_account_id) VALUES(1,'fixture','profiles/fixture',7)")
        self.remote = {'id': 7, 'auth_type': 'oauth', 'status': 'active', 'device_id': 'd' * 64,
            'email': 'fixture@example.invalid', 'account_uuid': 'fixture-uuid', 'organization_uuid': 'fixture-org'}
        self.tokens = {'account_id': 7, 'access_token': 'original-at', 'refresh_token': 'original-rt',
            'expires_at': int(time.time() * 1000) + 3600000}
        self.remote_owner, self.receipt, self.fail = None, None, None
        self.calls = []
        self.gateway = Mock()
        self.gateway._request.side_effect = self._request
        self.gateway.list_accounts.side_effect = lambda **kwargs: [dict(self.remote)]
        self.runtime = AccountRuntime(Mock(), self.root, self.root, main.get_db,
            lambda timezone: {'profile_version': 2, 'mem': '4g', 'swap': '0'}, self.gateway)
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)
        self.row = self.runtime._row('fixture', 1)
        self.runtime._stop_environment = Mock()
        self.runtime._running_sender_active = Mock(return_value=0)
        self.home = self.runtime._root(self.row) / 'home'
        profile = self.root / 'profiles/fixture'
        top = {'userID': self.remote['device_id'], 'oauthAccount': {'emailAddress': self.remote['email'],
            'accountUuid': self.remote['account_uuid'], 'organizationUuid': self.remote['organization_uuid']}}
        for path in (profile / '.claude.json', self.home / '.claude.json'):
            atomic_json(path, top)
        atomic_json(profile / '.credentials.json', {'claudeAiOauth': {'accessToken': self.tokens['access_token'],
            'refreshToken': self.tokens['refresh_token'], 'expiresAt': self.tokens['expires_at']}})
        self.runtime.sync_credentials(self.row, self.account())
        self.ownership = self.coordinator()
        self.runtime.credential_ownership = self.ownership

    def account(self) -> dict:
        """读取真实当前绑定。@return 账号行。"""
        with closing(main.get_db()) as database:
            return dict(database.execute('SELECT * FROM accounts WHERE id=1').fetchone())

    def coordinator(self) -> CredentialOwnership:
        """重建协调器，模拟进程恢复。@return 使用同一数据库的新实例。"""
        identity = lambda account, version=None: {**self.runtime.read_cli_identity(self.row, version or '2.1.293'),
            'environment_id': self.row['environment_id']}
        return CredentialOwnership(self.runtime, self.gateway, main.get_db, threading.Lock(),
            read_profile=main._read_bench_profile_identity, mirror=main._sync_cc2api_credentials_to_profile,
            mirror_locked=main._sync_cc2api_credentials_to_profile_locked, profile_lock=main._profile_lock,
            identity=identity, read_identity=identity, validate=main._validate_cc2api_identity,
            find=main._find_cc2api_account_for_profile, idle=lambda account: None,
            available=lambda account, remote: None, creation_payload=Mock(), refresh=Mock())

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, (payload or {}).get('action')))
        if path.endswith('/config'):
            return dict(self.remote)
        if path.endswith('/lease'):
            return {'active': 0, 'waiting': 0, 'lease': {'owner': 'binding:fixture', 'generation': 'fixture'}
                if method == 'POST' and payload['operation'] == 'prepare' else None}
        if method == 'GET':
            return {'protocol': 1, 'ownership': self.remote_owner}
        action = payload['action']
        if action == 'prepare' and self.receipt is None:
            if payload['direction'] == 'attach' and payload['source_refresh_sha256'] != hashlib.sha256(self.tokens['refresh_token'].encode()).hexdigest():
                raise ValueError('来源不能确认，请先核对或重新授权')
            self.remote_owner = {'identity': payload['identity'], 'operation_id': payload['operation_id'],
                'generation': payload['operation_id'], 'owner': 'local' if payload['direction'] == 'return' else 'gateway', 'phase': 'handoff'}
            self.receipt = {'operation_id': payload['operation_id'], 'identity': payload['identity'],
                'account_id': 7, 'generation': payload['operation_id'], 'stage': 'prepared'}
        if action == 'commit':
            if payload['direction'] in ('detach', 'retire'):
                self.receipt['stage'] = 'committed'
                self.remote_owner.update(owner='local', phase='ready')
            else:
                self.receipt['stage'] = 'imported'
                if payload.get('credentials'):
                    self.tokens = {'account_id': 7, **payload['credentials']}
        if action == 'finish':
            self.receipt['stage'] = 'committed'
            self.remote_owner.update(owner='gateway', phase='ready')
        if action == 'cancel':
            self.receipt['stage'] = 'cancelled'
            self.remote_owner.update(owner='local', phase='ready')
        if self.fail == action:
            self.fail = None
            raise ConnectionError('合成响应丢失')
        return json.loads(json.dumps({'protocol': 1, 'ownership': self.remote_owner, 'receipt': self.receipt,
            'credentials': self.tokens if self.receipt and self.receipt['stage'] in ('prepared', 'imported') else None}))

    def test_detach_rotate_and_return_original_id(self) -> None:
        """本地连续轮换后回交当前 HOME，保留 ID 并恢复 AT-only。@return None。"""
        self.ownership.detach(self.account())
        self.assertIsNone(self.account()['cc2api_account_id'])
        self.assertEqual('local', self.ownership.state(1)['owner'])
        for number in range(3):
            atomic_json(self.home / '.claude/.credentials.json', {'claudeAiOauth': {
                'accessToken': f'local-at-{number}', 'refreshToken': f'local-rt-{number}', 'expiresAt': self.tokens['expires_at']}})
        self.receipt = None
        result = self.ownership.associate(self.account(), 'bind', 7)
        self.assertEqual(7, result['cc2api_account']['id'])
        self.assertEqual('local-rt-2', self.tokens['refresh_token'])
        self.assertNotIn('refreshToken', json.loads((self.home / '.claude/.credentials.json').read_text())['claudeAiOauth'])
        self.assertEqual('gateway', self.ownership.state(1)['owner'])

    def test_lost_detach_reply_and_restart_do_not_publish_stale_remote_credentials(self) -> None:
        """远端提交回包丢失时本地保持关闭，重启查询回执完成。@return None。"""
        self.fail = 'commit'
        with self.assertRaises(ConnectionError):
            self.ownership.detach(self.account())
        with self.assertRaisesRegex(ValueError, '交接'):
            self.ownership.guard(self.account())
        recovered = self.coordinator()
        recovered.resume(self.account())
        self.assertEqual('ready', recovered.state(1)['phase'])
        self.assertEqual('local', recovered.state(1)['owner'])
        self.assertEqual(1, sum(action == 'commit' for _, _, action in self.calls))
        stored = json.dumps(recovered.state(1))
        self.assertNotIn('original-rt', stored)
        self.assertNotIn('original-at', stored)

    def test_lost_return_import_reply_resumes_without_second_import(self) -> None:
        """导入已提交时使用权威快照，重试不覆盖或重复导入旧 RT。@return None。"""
        self.ownership.detach(self.account())
        self.receipt = None
        self.fail = 'commit'
        with self.assertRaises(ConnectionError):
            self.ownership.associate(self.account(), 'bind', 7)
        count = sum(action == 'commit' for _, _, action in self.calls)
        self.ownership.resume(self.account())
        self.assertEqual(count, sum(action == 'commit' for _, _, action in self.calls))
        self.assertEqual(7, self.account()['cc2api_account_id'])
        self.assertEqual('gateway', self.ownership.state(1)['owner'])

    def test_retire_does_not_require_refresh_token_and_blocks_local_execution(self) -> None:
        """删除停用不依赖失效凭据，恢复需明确重新授权。@return None。"""
        (self.root / 'profiles/fixture/.credentials.json').unlink()
        self.ownership.retire(self.account())
        self.assertIsNone(self.account()['cc2api_account_id'])
        self.assertTrue(self.ownership.state(1)['retired'])
        with self.assertRaisesRegex(ValueError, '重新授权'):
            self.ownership.guard(self.account())
        self.ownership.guard(self.account(), 'login:fixture')

    def test_unknown_legacy_profile_requires_explicit_new_authorization(self) -> None:
        """来源冲突先拒绝；只有成功授权证明才能选择 authorize 交接。@return None。"""
        self.ownership.detach(self.account())
        self.remote_owner, self.receipt = None, None
        with closing(main.get_db()) as database, database:
            database.execute('DELETE FROM account_credential_ownerships')
        self.tokens['refresh_token'] = 'unrelated-remote-rt'
        with self.assertRaisesRegex(ValueError, '来源不能确认'):
            self.ownership.associate(self.account(), 'bind', 7)
        self.ownership.cancel_return(self.account())
        self.ownership.record_local_authorization(1)
        self.ownership.associate(self.account(), 'bind', 7)
        self.assertEqual('authorize', self.ownership.state(1)['input']['direction'])
        self.assertEqual('original-rt', self.tokens['refresh_token'])

    def test_unknown_local_refresh_survives_restart_and_requires_new_authorization(self) -> None:
        """刷新发送前的意图跨重启保持关闭，不能靠旧交接回执解除。@return None。"""
        self.ownership.detach(self.account())
        self.assertTrue(self.ownership.begin_local_refresh(1, 'oauth-refresh:fixture'))
        recovered = self.coordinator()
        with self.assertRaisesRegex(ValueError, '交接'):
            recovered.guard(self.account())
        with self.assertRaises(ValueError):
            recovered.finish_local_refresh(1, 'oauth-refresh:other')
        recovered.guard(self.account(), 'login:reauth')
        recovered.record_local_authorization(1)
        recovered.guard(self.account())
        self.assertFalse(recovered.state(1)['refresh_pending'])

    def test_independent_login_with_unknown_cli_clears_proof_without_blocking_save(self) -> None:
        """独立登录无需同步设备证明，旧证明不能用于后续关联。@return None。"""
        self.ownership.detach(self.account())
        with closing(main.get_db()) as database, database:
            database.execute('DELETE FROM account_credential_ownerships')
        self.ownership.record_local_authorization(1, '2.1.293')
        self.ownership.record_local_authorization(1, '9.9.9')
        profile = main._read_bench_profile_identity('fixture')
        self.assertIsNone(self.ownership._authorized_profile(self.account(), profile))
        self.assertEqual(set(), self.ownership.authorized_targets([self.remote]))
        self.ownership.guard(self.account())

    def test_unknown_cli_does_not_clear_managed_refresh_pending(self) -> None:
        """受管恢复仍需核验身份，不能用独立登录兼容分支解除维护。@return None。"""
        self.ownership.detach(self.account())
        self.ownership.begin_local_refresh(1, 'oauth-refresh:fixture')
        with self.assertRaisesRegex(ValueError, '尚未验证'):
            self.ownership.record_local_authorization(1, '9.9.9')
        self.assertTrue(self.ownership.state(1)['refresh_pending'])
        with self.assertRaises(ValueError):
            self.ownership.guard(self.account())

    def test_local_authorization_and_binding_use_frozen_login_version(self) -> None:
        """默认版本变化后仍按本次登录版本验证原设备和授权。@return None。"""
        self.ownership.detach(self.account())
        self.remote_owner, self.receipt = None, None
        with closing(main.get_db()) as database, database:
            database.execute('DELETE FROM account_credential_ownerships')
        self.tokens['refresh_token'] = 'unrelated-remote-rt'
        identity = self.ownership.read_identity
        self.ownership.read_identity = Mock(side_effect=lambda account, version=None: identity(account, version or '9.9.9'))
        self.ownership.record_local_authorization(1, '2.1.293')
        self.ownership.identity = Mock(side_effect=AssertionError('不能重新读取默认版本'))
        self.ownership.associate(self.account(), 'bind', 7)
        self.assertEqual('authorize', self.ownership.state(1)['input']['direction'])
        self.assertTrue(all(call.args[1] == '2.1.293' for call in self.ownership.read_identity.call_args_list))

    def test_detach_persistence_boundaries_resume_without_rollback(self) -> None:
        """各持久化边界写后失败均按实际回执恢复，不回滚 RT。@return None。"""
        for boundary in ('prepare', 'mirror', 'binding', 'publish', 'commit', 'ready'):
            with self.subTest(boundary=boundary):
                fixture = CredentialOwnershipTests()
                fixture.setUp()
                try:
                    owner, runtime = fixture.ownership, fixture.runtime
                    if boundary in ('prepare', 'commit'):
                        fixture.fail = boundary
                    else:
                        target = runtime if boundary == 'publish' else owner
                        method = {'mirror': 'mirror', 'binding': '_save_binding', 'publish': 'sync_credentials', 'ready': '_save'}[boundary]
                        original = getattr(target, method)
                        fired = False

                        def fail_after(*args, **kwargs):
                            nonlocal fired
                            result = original(*args, **kwargs)
                            if not fired and (boundary != 'ready' or args[0].get('phase') == 'ready'):
                                fired = True
                                raise OSError('合成写后失败')
                            return result

                        setattr(target, method, fail_after)
                    with self.assertRaises((OSError, ConnectionError)):
                        owner.detach(fixture.account())
                    if owner.state(1)['phase'] != 'ready':
                        with self.assertRaises(ValueError):
                            owner.guard(fixture.account())
                        fixture.coordinator().resume(fixture.account())
                    self.assertIsNone(fixture.account()['cc2api_account_id'])
                    self.assertEqual('local', owner.state(1)['owner'])
                    self.assertEqual('original-rt', json.loads((fixture.home / '.claude/.credentials.json').read_text())['claudeAiOauth']['refreshToken'])
                finally:
                    fixture.doCleanups()

    def test_corrupt_ownership_is_visible_and_blocks_only_its_account(self) -> None:
        """坏归属不能降级为本地管理，列表仍可显示其他账号。@return None。"""
        self.ownership.detach(self.account())
        with closing(main.get_db()) as database, database:
            database.execute("UPDATE account_credential_ownerships SET record_json='{}' WHERE account_id=1")
        with self.assertRaisesRegex(ValueError, '记录损坏'):
            self.ownership.guard(self.account())
        self.assertEqual('unknown', self.ownership.summaries()[1]['owner'])
        self.ownership.guard({'id': 2, 'cc2api_account_id': None})

    def test_legacy_attach_never_uses_stale_profile_as_source_proof(self) -> None:
        """HOME 已轮换而 profile 尚旧时，不能拿旧 RT 与远端匹配并回滚 HOME。@return None。"""
        self.ownership.detach(self.account())
        with closing(main.get_db()) as database, database:
            database.execute('DELETE FROM account_credential_ownerships')
        self.remote_owner, self.receipt = None, None
        atomic_json(self.home / '.claude/.credentials.json', {'claudeAiOauth': {
            'accessToken': 'home-current-at', 'refreshToken': 'home-current-rt', 'expiresAt': self.tokens['expires_at']}})
        with self.assertRaisesRegex(ValueError, '来源不能确认'):
            self.ownership.associate(self.account(), 'bind', 7)
        self.assertEqual('original-rt', self.tokens['refresh_token'])
        self.assertEqual('home-current-rt', json.loads((self.home / '.claude/.credentials.json').read_text())['claudeAiOauth']['refreshToken'])
        self.assertIsNone(self.account()['cc2api_account_id'])

    def test_committed_return_followed_by_unknown_gateway_refresh_keeps_reauthorization_reachable(self) -> None:
        """确认迟到时保留已提交绑定，将新刷新未知转成可重新授权的维护。@return None。"""
        self.ownership.detach(self.account())
        self.receipt = None
        self.ownership.associate(self.account(), 'bind', 7)
        record = self.ownership.state(1)
        record.update(phase='handoff', stage='mirrored')
        self.ownership._save(record)
        self.remote_owner['phase'] = 'reconcile'
        self.ownership.resume(self.account())
        self.assertEqual(7, self.account()['cc2api_account_id'])
        self.assertTrue(self.ownership.state(1)['gateway_refresh_pending'])
        with self.assertRaises(ValueError):
            self.ownership.guard(self.account())
        self.receipt = None
        self.ownership.begin_reauth(self.account(), 'recovery')
        self.assertEqual('reauth', self.ownership.state(1)['phase'])


if __name__ == '__main__':
    unittest.main()
