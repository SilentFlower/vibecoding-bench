"""合成环境验证恢复策略、观测归属及维护失败恢复。"""
import copy
import json
import tempfile
import time
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import main

from native_criu_policy import account_enabled, restore_policy
from native_criu_settings import ENTRY, read_settings, set_settings
from native_sender import criu_enabled, sender_config
from runtime_files import atomic_json


class CriuPolicyTests(unittest.TestCase):
    """普通进程与恢复进程分别校验资源。"""

    def test_default_explicit_disable_and_independent_memory_budget(self):
        """缺省开启，有限旧额度保持普通可用，无限额度通过恢复。@return 无。"""
        with patch.dict('os.environ', {'V3_NATIVE_CRIU': ''}):
            self.assertTrue(criu_enabled())
            normal = sender_config({'request_backend': 'native293', 'concurrency': 3}, '4g', budget='1536m')
            self.assertEqual(restore_policy(normal, {}, True)['required_memory_mib'], 2056)
            self.assertEqual(restore_policy(normal, {}, True)['reason'], 'memory_budget')
            self.assertTrue(restore_policy({**normal, 'memory_mib': 0}, {}, True)['eligible'])
            self.assertTrue(restore_policy({**normal, 'memory_mib': 2056}, {}, True)['eligible'])
            self.assertEqual(restore_policy(normal, {'native_criu_enabled': False}, True)['reason'], 'account_disabled')
        with patch.dict('os.environ', {'V3_NATIVE_CRIU': '0'}):
            self.assertEqual(restore_policy(normal, {}, True)['reason'], 'platform_disabled')
        for value in (0, 1, None, 'true'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                account_enabled({'native_criu_enabled': value})


class CriuSettingsTests(unittest.TestCase):
    """真实配置文件与合成Docker/租约，保持零模型调用。"""

    def setUp(self):
        """建立受控单账号夹具。@return 无。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / 'runtime/sender.json'
        self.row = {'environment_id': 'a' * 32, 'account_id': 7, 'gateway_account_id': 12, 'generation': 10,
            'state': 'ready', 'fingerprint_json': json.dumps({'mem': 'unlimited', 'native_criu_enabled': False, 'hostname': 'fixture'})}
        self.account = {'id': 7, 'cc2api_account_id': 12, 'name': '合成账号'}
        self.config = {'native': {'memory_mib': 0, 'max_workers': 8, 'kernel_generation': 'synthetic'},
            'binding': {'account_id': 12, 'environment_id': 'a' * 32, 'generation': 10}, 'native_criu_enabled': False}
        atomic_json(self.path, self.config)
        self.sender = SimpleNamespace(id='synthetic-sender', attrs={'Config': {
            'Labels': {'vibebench.native-criu': '1'}, 'Entrypoint': ['/usr/local/bin/account-sender']}}, reload=Mock())
        self.patch = patch('native_criu_settings.role_container', return_value=self.sender)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.env = patch.dict('os.environ', {'V3_NATIVE_CRIU': '1'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.lease, self.failures, self.operations = None, 0, []
        self.runtime = SimpleNamespace(_root=lambda row: self.root, _sender_config=lambda row: self.path,
            _stop_environment=Mock(), credential_ownership=None, environment_jobs=Mock(return_value=[]),
            reviews=SimpleNamespace(serial_state=lambda row: None), _running_sender_active=Mock(return_value=0))

        def gateway(method, path, body=None):
            """模拟独占维护租约。@param method 动作。@param path 固定路径。@param body 合成命令。@return 状态。"""
            if method == 'POST':
                self.operations.append(body['operation'])
                self.lease = None if body['operation'] == 'release' else {'owner': body['owner'], 'generation': 'fixture'}
            return {'lease': self.lease, 'active': 0, 'waiting': 0}
        self.runtime.gateway = SimpleNamespace(_request=Mock(side_effect=gateway))
        self.runtime._owned_lease = lambda value, owner: value.get('lease') if (value.get('lease') or {}).get('owner') == owner else None
        self.runtime._update = lambda row, **values: row.update(values)

        def ensure(account, preserve_proxy):
            """按目标选择重建合成入口。@param account 账号。@param preserve_proxy 保持代理。@return 新代次。"""
            if self.failures:
                self.failures -= 1
                raise RuntimeError('合成失败')
            current = copy.deepcopy(self.config)
            policy = restore_policy(current['native'], json.loads(self.row['fingerprint_json']), True)
            self.row.update(generation=self.row['generation'] + 1, state='ready')
            current['binding']['generation'] = self.row['generation']
            current['native_criu_enabled'] = policy['eligible']
            self.sender.attrs['Config']['Entrypoint'] = ENTRY if policy['eligible'] else ['/usr/local/bin/account-sender']
            atomic_json(self.path, current)
            return dict(self.row), None
        self.runtime.ensure = Mock(side_effect=ensure)

    def apply(self, enabled):
        """按当前CAS提交。@param enabled 目标选择。@return 实际结果。"""
        before = read_settings(self.runtime, self.row)
        return set_settings(self.runtime, self.row, self.account, enabled, before['generation'], before['revision'])

    def test_apply_persists_and_preserves_kernel_and_identity(self):
        """切换经过独占租约并核对实际入口。@return 无。"""
        result = self.apply(True)
        self.assertTrue(result['enabled'] and result['applied'])
        self.assertEqual(self.operations, ['prepare', 'claim', 'release'])
        self.assertEqual(json.loads(self.path.read_text())['native'], self.config['native'])
        self.assertEqual(json.loads(self.row['fingerprint_json'])['hostname'], 'fixture')
        self.assertFalse(self.apply(False)['enabled'])
        self.assertIsNone(self.lease)

    def test_same_desired_choice_rebuilds_old_entry(self):
        """历史缺字段默认为开启，旧入口需要显式应用。@return 无。"""
        self.row['fingerprint_json'] = json.dumps({'mem': 'unlimited'})
        self.assertEqual(read_settings(self.runtime, self.row)['state'], 'requires_rebuild')
        self.assertTrue(self.apply(True)['applied'])
        self.runtime.ensure.assert_called_once()

    def test_stale_busy_and_failed_rebuild_keep_ownership(self):
        """过期或忙碌拒绝，失败重建恢复原指纹。@return 无。"""
        before = read_settings(self.runtime, self.row)
        with self.assertRaisesRegex(ValueError, '已变化'):
            set_settings(self.runtime, self.row, self.account, True, 9, before['revision'])
        self.runtime.environment_jobs.return_value = ['synthetic-job']
        with self.assertRaisesRegex(ValueError, '正在工作'):
            self.apply(True)
        self.runtime._stop_environment.assert_not_called()
        self.runtime.environment_jobs.return_value = []
        original = self.row['fingerprint_json']
        self.failures = 1
        with self.assertRaisesRegex(RuntimeError, '原策略已恢复'):
            self.apply(True)
        self.assertEqual(self.row['fingerprint_json'], original)
        self.assertEqual(self.row['state'], 'ready')
        self.assertIsNone(self.lease)

    def test_only_fresh_owned_boolean_telemetry_can_claim_ready(self):
        """跨代、陈旧、畸形与任意错误内容不能声明模板就绪。@return 无。"""
        self.apply(True)
        observation = {'environment_id': self.row['environment_id'], 'generation': self.row['generation'],
            'kernel_generation': 'synthetic', 'checked_at_ms': int(time.time() * 1000),
            'restore': {'schema_version': 1, 'state': 'ready', 'reason': None, 'template_ready': True, 'last_start_source': 'criu_restore'}}
        result = read_settings(self.runtime, self.row, observation)
        self.assertEqual((result['state'], result['last_start_source']), ('ready', 'criu_restore'))
        for changed in ({**observation, 'generation': 9}, {**observation, 'checked_at_ms': 0},
                {**observation, 'restore': {**observation['restore'], 'template_ready': 1}},
                {**observation, 'restore': {**observation['restore'], 'state': 'unavailable'}},
                {**observation, 'restore': {**observation['restore'], 'reason': {'secret': 'synthetic-secret'}}}):
            result = read_settings(self.runtime, self.row, changed)
            self.assertNotEqual(result['state'], 'ready')
            self.assertNotIn('synthetic-secret', json.dumps(result))

    def test_real_http_authentication_strict_dto_cas_and_discovery(self):
        """真实ASGI路由执行鉴权、严格DTO、CAS及只读发现。@return 无。"""
        self.runtime.environment_lock = lambda identifier: threading.RLock()
        self.runtime.native_preparation_snapshots = lambda: ({}, None)

        def binding(identifier):
            """只返回当前夹具归属。@param identifier 环境。@return 唯一账号。"""
            if identifier != self.row['environment_id']:
                raise main.HTTPException(404)
            return self.row, self.account

        with patch.multiple(main, account_runtime=self.runtime, V3_ENABLED=False, _AUTH_ENABLED=True,
                WEBUI_USER='fixture', WEBUI_PASS='fixture'), patch('main._content_capture_account', side_effect=binding), \
                patch('main.native_kernel_status', return_value={'state': 'idle'}), \
                patch('main.discover_releases', return_value={'state': 'ready', 'versions': []}) as discover, \
                patch.dict('os.environ', {'V3_UPDATE_GATE_DIR': ''}):
            client = TestClient(main.app)
            path = '/api/environments/' + self.row['environment_id']
            self.assertEqual(client.get(path + '/criu').status_code, 401)
            self.assertEqual(client.get(path + '/native-kernel/releases').status_code, 401)
            client.cookies.set(main._SESSION_COOKIE, main._make_session_token('fixture'))
            before = client.get(path + '/criu').json()
            self.assertEqual(client.get('/api/environments/' + 'b' * 32 + '/criu').status_code, 404)
            command = {'enabled': True, 'expected_generation': before['generation'], 'expected_revision': before['revision']}
            for invalid in ({**command, 'enabled': 1}, {**command, 'expected_generation': True}, {**command, 'extra': True}):
                self.assertEqual(client.post(path + '/criu', json=invalid).status_code, 422)
            result = client.post(path + '/criu', json=command)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertTrue(result.json()['applied'])
            self.assertEqual(client.post(path + '/criu', json=command).status_code, 409)
            self.assertEqual(client.get(path + '/native-kernel/releases?refresh=true').status_code, 200)
            discover.assert_called_once_with(True)
            self.assertEqual(self.runtime.ensure.call_count, 1)
