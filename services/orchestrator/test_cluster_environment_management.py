"""原管理HTTP经真实Node Actor、双SQLite和原快照读取器的路由回归。"""
import json
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import main
import test_cluster_owner_runner as owner_fixture
from cluster_environment_control import RemoteEnvironmentControl
from cluster_environment_management import EnvironmentReference, _ConfigurationLease, environment_management
from cluster_execution_grants import ExecutionLeaseProof
from runtime_files import atomic_json


class RemoteEnvironmentTests(unittest.TestCase):
    """中央仅登记归属，实际资源与文件操作留在所属Node。"""

    def setUp(self) -> None:
        """复用已归属账号、真实Actor及原Gateway门禁夹具。:return: None。"""
        self.fixture = owner_fixture.RemoteOwnerTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.node = self.fixture.root, self.fixture.node
        with self.node.executor.database() as connection:
            connection.execute('UPDATE account_environments SET isolation_version=2 WHERE account_id=1')
        original = self.root.gateway._request.side_effect
        def gateway(method, path, payload=None):
            """原所有权夹具补齐停止预热的管理响应。:return: 原管理结果。"""
            if path.endswith('/native-preparation?cancel=true'):
                return {'ok': True}
            value = original(method, path, payload)
            if path.endswith('/lease') and method == 'POST' and payload['operation'] in ('prepare', 'claim'):
                self.fixture.gateway_lease['phase'] = 'claimed' if payload['operation'] == 'claim' else 'prepared'
                if payload['operation'] == 'claim':
                    self.fixture.gateway_lease['expires_at'] += 1
            return value
        self.root.gateway._request.side_effect = gateway
        self.control = RemoteEnvironmentControl(self.fixture.sessions.service, self.root.runtime,
            self.root.gateway, main._quota_identity)

    def test_original_http_cpu_uses_node_and_paused_admin_remains_available(self) -> None:
        """原HTTP读取和修改送到暂停Node，中央HOME保持独立。:return: None。"""
        with main.get_db() as connection:
            connection.execute('UPDATE cluster_nodes SET enabled=0 WHERE id=?', (self.fixture.node_id,))
        expected = {'generation': self.node.row['generation'], 'revision': 'a' * 64, 'roles': []}
        with patch.object(self.root.runtime, '_root', side_effect=AssertionError('禁止中央HOME')), \
                patch('cluster_environment_management.read_resources', return_value=expected) as reader, \
                patch('cluster_environment_management.set_resources', return_value=expected) as setter:
            self.assertEqual(expected, main.v3_cpu_resources(self.node.row['environment_id']))
            self.assertIs(self.node.runtime, reader.call_args.args[0])
            body = main.CpuResourceOperation(expected_generation=self.node.row['generation'],
                expected_revision='a' * 64, cpus={'cli': 1.5})
            self.assertEqual(expected, main.v3_set_cpu_resources(self.node.row['environment_id'], body))
            self.assertIs(self.node.runtime, setter.call_args.args[0])
        self.assertIn('environment-cpu-read', self.fixture.calls)
        self.assertIn('environment-cpu-set', self.fixture.calls)

    def test_original_private_capture_preserves_large_snapshot_and_missing_state(self) -> None:
        """原文件读取器返回超过旧256KiB预算的同账号快照。:return: None。"""
        attempt = str(uuid4())
        value = {'schema_version': 1, 'stage': 'cc_prepared', 'account_id': 7, 'attempt_id': attempt,
            'captured_at_ms': int(time.time() * 1000), 'headers': [], 'body': 'x' * (300 * 1024)}
        path = self.node.runtime._root(self.node.row) / 'flows/api/cc-prepared' / (attempt + '.json')
        atomic_json(path, value)
        with patch.object(self.root.runtime, '_root', side_effect=AssertionError('禁止中央HOME')):
            result = self.control.call(self.root.row, 'environment-capture-read', {'attempt_id': attempt})
            self.assertEqual(value, result['snapshot'])
            result = self.control.call(self.root.row, 'environment-capture-read', {'attempt_id': str(uuid4())})
            self.assertEqual({'state': 'missing'}, result)

    def test_original_settings_receive_node_runtime_and_owned_lease(self) -> None:
        """实际配置动作使用同一中央真实门禁，回执镜像Node指纹。:return: None。"""
        original_gateway = self.node.runtime.gateway
        def apply(runtime, row, account, enabled, generation, revision, **keywords):
            self.assertIs(self.node.runtime, runtime)
            self.assertEqual(7, account['cc2api_account_id'])
            facade = keywords['lease_gateway']
            self.assertIsInstance(facade, _ConfigurationLease)
            path = '/admin/runtime/accounts/7/lease'
            prepared = facade._request('POST', path, {'operation': 'prepare', 'owner': keywords['lease_owner']})
            self.assertEqual({key: value for key, value in self.fixture.gateway_lease.items() if key != 'phase'}, prepared['lease'])
            fingerprint = json.loads(row['fingerprint_json'])
            runtime._update(row, fingerprint_json=json.dumps({**fingerprint, 'native_capture_enabled': enabled}))
            return {'enabled': enabled}
        with patch('cluster_environment_management.set_capture_settings', side_effect=apply):
            result = self.control.call(self.root.row, 'environment-capture-set',
                {'expected_generation': self.node.row['generation'], 'expected_revision': 'a' * 64, 'enabled': False})
        self.assertEqual({'enabled': False}, result)
        self.assertIs(original_gateway, self.node.runtime.gateway)
        self.assertIsNone(self.fixture.gateway_lease)
        with main.get_db() as connection:
            row = connection.execute('SELECT fingerprint_json FROM account_environments WHERE account_id=1').fetchone()
        self.assertFalse(json.loads(row[0])['native_capture_enabled'])

    def test_unknown_response_preserves_gate_until_actual_stop_reconciliation(self) -> None:
        """Node停止后响应丢失，实际重读及显式停止对账后才释放原门禁。:return: None。"""
        self.fixture.loss = 'environment-maintenance'
        with self.assertRaises(ConnectionError):
            self.control.call(self.root.row, 'environment-maintenance', {'operation': 'stop'})
        self.assertIsNotNone(self.fixture.gateway_lease)
        with patch('cluster_environment_management.read_resources', return_value={'ok': True}):
            self.control.call(self.root.row, 'environment-cpu-read')
        with main.get_db() as connection:
            self.assertEqual('stopped', connection.execute('SELECT state FROM account_environments WHERE account_id=1').fetchone()[0])
        self.fixture.gateway_lease['expires_at'] = int(time.time()) - 1
        self.control.call(self.root.row, 'environment-maintenance', {'operation': 'reconcile'})
        self.assertIsNone(self.fixture.gateway_lease)

    def test_stale_generation_rejected_before_node_mutation(self) -> None:
        """实际代次变化后旧页面修改保持冲突。:return: None。"""
        with patch('cluster_environment_management.set_resources') as setter:
            with self.assertRaisesRegex(ValueError, '代次已变化'):
                self.control.call(self.root.row, 'environment-cpu-set',
                    {'expected_generation': self.node.row['generation'] - 1, 'expected_revision': 'a' * 64, 'cpus': {'cli': 1}})
            setter.assert_not_called()

    def test_wrong_binding_rejected_before_node_read(self) -> None:
        """实际Node的绑定变化使原位置请求失效。:return: None。"""
        context = self.control._context(1, self.node.row['environment_id'])
        request = EnvironmentReference(**context[0].model_dump(), generation=self.node.row['generation'])
        with self.node.executor.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
        with patch('cluster_environment_management.read_resources') as reader:
            with self.assertRaisesRegex(ValueError, '绑定已变化'):
                environment_management(self.node.executor, request, 'environment-cpu-read')
            reader.assert_not_called()

    def test_malformed_result_does_not_advance_central_generation(self) -> None:
        """Node回执正文损坏时，较新代次也不能先写进中央镜像。:return: None。"""
        context = self.control._context(1, self.node.row['environment_id'])
        with self.node.executor.database() as connection:
            actual = dict(connection.execute('SELECT * FROM account_environments WHERE account_id=1').fetchone())
        actual['generation'] += 1
        value = {'protocol': 1, 'node_key': context[0].node_key,
            'location': context[0].model_dump(exclude={'gateway_account_id'}), 'environment': actual, 'result': []}
        remote = Mock()
        remote.execution_environment.return_value = value
        with patch.object(self.fixture.sessions.service, 'connection', return_value=remote):
            with self.assertRaisesRegex(ValueError, '结果需要核对'):
                self.control._rpc(context, context[0], 'environment-state')
        with main.get_db() as connection:
            generation = connection.execute('SELECT generation FROM account_environments WHERE account_id=1').fetchone()[0]
        self.assertEqual(context[2]['generation'], generation)

    def test_expired_recovery_keeps_lease_until_real_stop_confirmed(self) -> None:
        """过期门禁只在实际停止确认之后收口，Node失败仍保持原门禁。:return: None。"""
        proof = {'owner': 'maintenance:' + 'a' * 32, 'generation': 'original-expired',
            'expires_at': int(time.time()) - 1, 'exclusive': True, 'shared_cli': False}
        self.fixture.gateway_lease = proof
        with patch.object(self.node.runtime, '_stop_environment', side_effect=ValueError('合成停止失败')):
            with self.assertRaises(ValueError):
                self.control.call(self.root.row, 'environment-maintenance', {'operation': 'reconcile'})
        self.assertEqual(proof, self.fixture.gateway_lease)
        self.control.call(self.root.row, 'environment-maintenance', {'operation': 'reconcile'})
        self.assertIsNone(self.fixture.gateway_lease)

    def test_prepare_response_loss_recovers_exact_owner(self) -> None:
        """中央门禁准备成功后响应丢失，按本次来源回查并释放。:return: None。"""
        original = self.root.gateway._request.side_effect
        def gateway(method, path, payload=None):
            value = original(method, path, payload)
            if path.endswith('/lease') and method == 'POST' and payload['operation'] == 'prepare':
                raise ConnectionError('合成准备响应丢失')
            return value
        self.root.gateway._request.side_effect = gateway
        with self.assertRaises(ConnectionError):
            self.control.call(self.root.row, 'environment-maintenance', {'operation': 'rebuild'})
        self.assertIsNone(self.fixture.gateway_lease)

    def test_expired_configuration_claim_rejected_and_cleanup_remains_available(self) -> None:
        """到期许可拒绝开始配置，原来源仍能释放本次借用。:return: None。"""
        proof = ExecutionLeaseProof(owner='capture:' + 'a' * 32, generation='original',
            expires_at=int(time.time()) - 1, exclusive=True, shared_cli=False)
        facade = _ConfigurationLease(7, proof)
        with self.assertRaisesRegex(ValueError, '到期'):
            facade._request('POST', '/admin/runtime/accounts/7/lease', {'operation': 'prepare', 'owner': proof.owner})
        self.assertEqual({'ok': True}, facade._request('POST', '/admin/runtime/accounts/7/lease',
            {'operation': 'release', 'owner': proof.owner, 'generation': proof.generation}))
