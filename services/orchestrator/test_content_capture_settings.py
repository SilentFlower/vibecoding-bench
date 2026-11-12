"""采集开关的并发、失败恢复及实际配置核对回归，全部使用合成环境。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from content_capture_settings import read_settings, set_settings
from native_capture_policy import capture_enabled
from native_kernel_upgrade import pending_upgrade
from runtime_files import atomic_json


class ContentCaptureTests(unittest.TestCase):
    """验证策略发布和独占维护收口。"""

    def setUp(self):
        """建立两个独立的合成账号。@return None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.row = {'environment_id': 'a' * 32, 'account_id': 7, 'gateway_account_id': 12, 'generation': 10, 'state': 'ready',
            'fingerprint_json': json.dumps({'mem': 'unlimited', 'tz': 'Asia/Shanghai', 'hostname': 'demo', 'native_capture_enabled': False})}
        self.account = {'id': 7, 'cc2api_account_id': 12, 'name': '演示账号'}
        self.path = self.root / 'runtime/sender.json'
        self.config = {'native': {'release': {'release': 'v0.1.0-beta.5', 'launcher_sha256': 'a' * 64}},
            'binding': {'account_id': 12, 'environment_id': 'a' * 32, 'generation': 10}, 'memory': 'unlimited', 'proxy_url': 'synthetic', 'native_tls_observer_protocol': 1}
        atomic_json(self.path, self.config)
        self.path.chmod(0o640)
        self.lease = None
        self.lease_calls = []
        self.runtime = SimpleNamespace(_root=lambda row: self.root, _sender_config=lambda row: self.path,
            _stop_environment=Mock(), credential_ownership=None, environment_jobs=Mock(return_value=[]),
            reviews=SimpleNamespace(serial_state=lambda row: None), _running_sender_active=Mock(return_value=0))
        def gateway(method, path, body=None):
            self.lease_calls.append((method, body))
            if method == 'POST':
                self.lease = None if body['operation'] == 'release' else {'owner': body['owner'], 'generation': 'synthetic-generation'}
            return {'lease': self.lease, 'active': 0, 'waiting': 0}
        self.runtime.gateway = SimpleNamespace(_request=Mock(side_effect=gateway))
        self.runtime._owned_lease = lambda value, owner: value.get('lease') if (value.get('lease') or {}).get('owner') == owner else None
        self.runtime._update = lambda row, **fields: row.update(fields)
        self.failures = 0
        def ensure(account, preserve_proxy):
            if self.failures:
                self.failures -= 1
                raise RuntimeError('合成准备故障')
            current = copy.deepcopy(self.config)
            if capture_enabled(json.loads(self.row['fingerprint_json'])):
                current['native_capture_dir'] = '/flows/api/cc-prepared'
            else:
                current.pop('native_capture_dir', None)
            self.row['generation'] += 1
            self.row['state'] = 'ready'
            current['binding']['generation'] = self.row['generation']
            atomic_json(self.path, current)
            return dict(self.row), None
        self.runtime.ensure = Mock(side_effect=ensure)

    def apply(self, enabled):
        """提交当前冻结版本。@param enabled 目标状态。@return 实际回执。"""
        before = read_settings(self.runtime, self.row)
        return set_settings(self.runtime, self.row, self.account, enabled, before['generation'], before['revision'])

    def test_enable_disable_verifies_sender_and_preserves_other_fields(self):
        """配置实际写入，身份及内核字段沿用，租约一次释放。@return None。"""
        result = self.apply(True)
        self.assertTrue(result['enabled'] and result['applied'])
        self.assertEqual([body['operation'] for method, body in self.lease_calls if method == 'POST'], ['prepare', 'claim', 'release'])
        self.assertEqual(json.loads(self.path.read_text())['native'], self.config['native'])
        self.assertEqual(json.loads(self.row['fingerprint_json'])['hostname'], 'demo')
        self.assertIsNone(self.lease)
        self.assertFalse(self.apply(False)['enabled'])
        self.assertNotIn('native_capture_dir', json.loads(self.path.read_text()))

    def test_stale_and_busy_reject_before_policy_write(self):
        """旧版本与活动账号拒绝修改配置。@return None。"""
        before = read_settings(self.runtime, self.row)
        self.row['generation'] += 1
        with self.assertRaisesRegex(ValueError, '已变化'):
            set_settings(self.runtime, self.row, self.account, True, before['generation'], before['revision'])
        self.runtime.gateway._request.assert_not_called()
        self.row['generation'] = before['generation']
        original = dict(self.row)
        self.runtime.environment_jobs.return_value = ['合成活动作业']
        with self.assertRaisesRegex(ValueError, '正在工作'):
            self.apply(True)
        self.assertEqual(self.row, original)
        self.runtime.ensure.assert_not_called()

    def test_failure_recovers_original_strategy_and_stopped_lifecycle(self):
        """一次准备失败后恢复原配置，原停止环境保持停止。@return None。"""
        self.row['state'] = 'stopped'
        self.failures = 1
        with self.assertRaisesRegex(RuntimeError, '原策略已恢复'):
            self.apply(True)
        self.assertEqual(self.row['state'], 'stopped')
        self.assertFalse(read_settings(self.runtime, self.row)['enabled'])
        self.assertEqual(json.loads((self.root / 'runtime/content-capture-operation.json').read_text())['state'], 'restored')
        self.assertIsNone(self.lease)

    def test_failed_recovery_is_visible_and_lease_release_failure_isolates(self):
        """恢复及门禁故障保持可见待对账状态。@return None。"""
        self.failures = 2
        with self.assertRaisesRegex(RuntimeError, '需要对账'):
            self.apply(True)
        self.assertEqual(self.row['state'], 'reconcile')
        self.row['state'] = 'ready'
        atomic_json(self.path, self.config)
        self.row['fingerprint_json'] = '{"native_capture_enabled":false}'
        original_gateway = self.runtime.gateway._request.side_effect
        def fail_release(method, path, body=None):
            if method == 'POST' and body['operation'] == 'release':
                raise RuntimeError('合成门禁释放失败')
            return original_gateway(method, path, body)
        self.runtime.gateway._request.side_effect = fail_release
        with self.assertRaisesRegex(RuntimeError, '门禁尚未释放'):
            self.apply(True)
        self.assertEqual(self.row['state'], 'reconcile')
        self.assertIsNotNone(self.lease)

    def test_separate_accounts_and_actual_config_drift(self):
        """账号配置独立；持久策略与实际配置偏离时拒绝写入。@return None。"""
        other = dict(self.row, environment_id='b' * 32, account_id=8)
        second = self.root / 'other/sender.json'
        atomic_json(second, self.config)
        self.runtime._sender_config = lambda row: second if row['account_id'] == 8 else self.path
        before = read_settings(self.runtime, other)
        self.apply(True)
        self.assertEqual(read_settings(self.runtime, other), before)
        configuration = json.loads(self.path.read_text())
        configuration.pop('native_capture_dir')
        atomic_json(self.path, configuration)
        with self.assertRaisesRegex(ValueError, '需要对账'):
            self.apply(False)

    def test_busy_gateway_and_lost_prepare_response_keep_original_policy(self):
        """活动 API 拒绝切换；准备回执丢失时仅释放本次租约。@return None。"""
        original_gateway = self.runtime.gateway._request.side_effect
        self.runtime.gateway._request.side_effect = lambda *arguments: {'lease': None, 'active': 1}
        with self.assertRaisesRegex(ValueError, '正在工作'):
            self.apply(True)
        self.runtime.ensure.assert_not_called()
        def lost_prepare(method, path, body=None):
            result = original_gateway(method, path, body)
            if method == 'POST' and body['operation'] == 'prepare':
                raise ConnectionError('合成准备响应丢失')
            return result
        self.runtime.gateway._request.side_effect = lost_prepare
        with self.assertRaises(ConnectionError):
            self.apply(True)
        self.runtime.ensure.assert_not_called()
        self.assertIsNone(self.lease)
        self.assertFalse(read_settings(self.runtime, self.row)['enabled'])

    def test_kernel_download_blocks_capture_before_lease_and_rebuild(self):
        """真实下载标记保持原代次；采集维护零租约写入、零重建。@return None。"""
        original = dict(self.row)
        atomic_json(self.root / 'runtime/native-kernel-upgrade.json',
            {'state': 'active', 'preparing_release': 'v0.1.0-beta.6'})
        self.assertFalse(pending_upgrade(self.root))
        self.assertTrue(pending_upgrade(self.root, include_preparing=True))
        with self.assertRaisesRegex(ValueError, '内核正在维护'):
            self.apply(True)
        self.assertEqual(self.row, original)
        self.runtime.gateway._request.assert_not_called()
        self.runtime._stop_environment.assert_not_called()
        self.runtime.ensure.assert_not_called()

    def test_default_enabled_explicit_disabled_and_invalid_policy(self):
        """缺省开启、显式关闭及非法类型共用同一解释。@return None。"""
        self.assertTrue(capture_enabled({}))
        self.assertTrue(capture_enabled({'native_capture_enabled': True}))
        self.assertFalse(capture_enabled({'native_capture_enabled': False}))
        for value in (None, 0, 1, 'false'):
            with self.assertRaises(ValueError):
                capture_enabled({'native_capture_enabled': value})
        self.row['fingerprint_json'] = '{}'
        self.config['native_capture_dir'] = '/flows/api/cc-prepared'
        atomic_json(self.path, self.config)
        result = read_settings(self.runtime, self.row)
        self.assertTrue(result['enabled'] and result['applied'])
        self.apply(False)
        self.assertFalse(capture_enabled(json.loads(self.row['fingerprint_json'])))

    def test_tls_status_requires_fresh_same_generation_observation(self):
        """标签只代表安装，实际ready需要同代次新鲜观测。@return None。"""
        import time
        self.row['fingerprint_json'] = '{}'
        self.config['native_capture_dir'] = '/flows/api/cc-prepared'
        atomic_json(self.path, self.config)
        observation = {'environment_id': self.row['environment_id'], 'generation': 10,
            'checked_at_ms': int(time.time()*1000), 'tls_observer': {'state': 'ready', 'reason': None, 'image_admitted': True, 'protocol_version': 1}}
        self.assertEqual(read_settings(self.runtime, self.row)['tls_observer']['state'], 'unavailable')
        self.assertEqual(read_settings(self.runtime, self.row, observation)['tls_observer']['state'], 'ready')
        for changed in ({'generation': 9}, {'checked_at_ms': 1}, {'kernel_generation': 'old'}):
            self.assertEqual(read_settings(self.runtime, self.row, {**observation, **changed})['tls_observer']['state'], 'unavailable')
        for changed in ({'image_admitted': False}, {'protocol_version': 2}):
            self.assertEqual(read_settings(self.runtime, self.row, {**observation,
                'tls_observer': {**observation['tls_observer'], **changed}})['tls_observer']['state'], 'unavailable')
        self.config.pop('native_tls_observer_protocol')
        atomic_json(self.path, self.config)
        self.assertEqual(read_settings(self.runtime, self.row, observation)['tls_observer']['state'], 'not_installed')

    def test_disabled_old_image_rejects_enable_before_maintenance(self):
        """关闭态独立核对制品能力，拒绝无效重建。@return None。"""
        self.config.pop('native_tls_observer_protocol')
        atomic_json(self.path, self.config)
        before = dict(self.row)
        self.assertEqual(read_settings(self.runtime, self.row)['tls_observer']['state'], 'disabled')
        with self.assertRaisesRegex(ValueError, '系统更新'):
            self.apply(True)
        self.assertEqual(self.row, before)
        self.runtime.gateway._request.assert_not_called()
        self.runtime.ensure.assert_not_called()
        self.runtime._stop_environment.assert_not_called()


class ContentCaptureContractTests(unittest.TestCase):
    """验证实际 DTO 和唯一绑定 SQL，覆盖跨层准入。"""

    def test_model_and_unique_binding(self):
        """拒绝布尔代次、额外字段、重复绑定及已删除账号。@return None。"""
        import sqlite3
        from unittest.mock import patch
        from pydantic import ValidationError
        import main

        value = {'enabled': True, 'expected_generation': 10, 'expected_revision': 'a' * 64}
        self.assertTrue(main.ContentCaptureOperation(**value).enabled)
        for invalid in [dict(value, enabled=1), dict(value, expected_generation=True), dict(value, unknown=True)]:
            with self.assertRaises(ValidationError):
                main.ContentCaptureOperation(**invalid)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.sqlite'
            with sqlite3.connect(path) as connection:
                connection.executescript("CREATE TABLE accounts(id INTEGER,name TEXT,cc2api_account_id INTEGER,deleted_at TEXT);"
                    "CREATE TABLE account_environments(environment_id TEXT,account_id INTEGER,generation INTEGER);"
                    "INSERT INTO accounts VALUES(7,'演示',12,NULL);"
                    "INSERT INTO account_environments VALUES('synthetic',7,10);")
            def connect():
                connection = sqlite3.connect(path)
                connection.row_factory = sqlite3.Row
                return connection
            with patch('main.get_db', side_effect=connect):
                row, account = main._content_capture_account('synthetic')
                self.assertEqual((row['generation'], account['cc2api_account_id']), (10, 12))
                with sqlite3.connect(path) as connection:
                    connection.execute("INSERT INTO accounts VALUES(8,'重复',12,NULL)")
                with self.assertRaises(main.HTTPException):
                    main._content_capture_account('synthetic')
                with sqlite3.connect(path) as connection:
                    connection.execute("UPDATE accounts SET deleted_at='已删除' WHERE id=8")
                self.assertEqual(main._content_capture_account('synthetic')[1]['id'], 7)


if __name__ == '__main__':
    unittest.main()
