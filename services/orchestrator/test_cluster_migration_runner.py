"""中央迁移协调器的真实SQLite、原租约合同和阶段故障恢复测试。"""
from __future__ import annotations

import json
import threading
import time
import unittest
from contextlib import nullcontext, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cluster_archive import ArchiveIdentity
from cluster_execution import NodePreparation
from cluster_migration_files import ImportStage, MigrationFiles
from cluster_migration_io import MigrationIO, MigrationUploadIncomplete
from cluster_migration_lease import MigrationLease
from cluster_migration_runner import MigrationCoordinator, MigrationStart
from cluster_transport import NodeTransports
from runtime_files import atomic_json
import test_cluster_migrations as migration_fixture


class _Gateway:
    """仿照网关原排他租约和过期保护合同的合成客户端。"""

    def __init__(self) -> None:
        """建立空闲网关状态。:return: None。"""
        self.holders, self.requests, self.counter = [], [], 0
        self.fail_heartbeat = False

    def _request(self, method, path, payload=None):
        self.requests.append((method, path, payload))
        if method == 'POST':
            operation = payload['operation']
            if operation == 'prepare':
                if not self.holders:
                    self.counter += 1
                    self.holders = [{'owner': payload['owner'], 'generation': str(self.counter), 'exclusive': True,
                        'expires_at': time.time() + 30, 'phase': 'draining', 'shared_cli': False}]
                elif self.holders[0]['owner'] != payload['owner']:
                    raise ValueError('合成其他租约占用')
            else:
                if not self.holders or any(self.holders[0][key] != payload[key] for key in ('owner', 'generation')):
                    raise ValueError('合成租约代次已变化')
                if operation == 'release':
                    self.holders = []
                elif operation == 'heartbeat' and self.fail_heartbeat:
                    raise ValueError('合成续约连接中断')
                elif operation == 'claim':
                    self.holders[0]['phase'] = 'claimed'
        return {'holders': [dict(item) for item in self.holders], 'lease': dict(self.holders[0]) if self.holders else None,
            'active': 0, 'waiting': 0, 'importing': 0}


class MigrationCoordinatorTests(unittest.TestCase):
    """跨节点承载由固定命令替身记录，实际权威事务和恢复游标参与验证。"""

    def setUp(self) -> None:
        """建立原环境、已准备目标和中央互斥回调。:return: None。"""
        fixture = migration_fixture.NodeMigrationTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.store = fixture, fixture.store
        self.operation = fixture.operation
        self.root = Path(fixture.path).parent
        connection = fixture.database()
        try:
            with connection:
                connection.execute('UPDATE accounts SET cc2api_account_id=7 WHERE id=1')
                connection.execute('UPDATE cluster_nodes SET preparation_json=? WHERE id=?',
                    (json.dumps({'state': 'prepared', 'release': 'synthetic-release'}), fixture.target))
        finally:
            connection.close()
        self.owner_lock = threading.RLock()
        service = SimpleNamespace(store=self.store, data=self.root, local_client=Mock(), transports=NodeTransports(self.store),
            migration_nodes=lambda migration: nullcontext())
        service.connection = Mock(return_value=SimpleNamespace(agent_health=Mock(return_value={
            'release': 'synthetic-release', 'deployment': 'synthetic'})))
        service.build_preparation = lambda account, row, node_key, revision, runtime, gateway, quota, profile_sink=None, **options: NodePreparation(
            account=account, environment=row, node_key=node_key, assignment_revision=revision,
            gateway_config={}, quota_identity=quota, profile_files={},**options)
        runtime = SimpleNamespace(deployment='synthetic', release_id='synthetic-release', environment_lock=lambda identity: threading.RLock(),
            _root=lambda row: self.root / 'environments' / row['environment_id'])
        self.gateway = _Gateway()
        self.coordinator = MigrationCoordinator(service, runtime, self.gateway, lambda account: 'synthetic-quota', self.guard)
        self.request = MigrationStart(operation_id=self.operation, node_id=fixture.target, revision=1, version='2.1.293')
        self.commands = []
        self.target_account_release = 'synthetic-release'
        self.fail_operation = None
        self.coordinator.io = Mock()
        self.coordinator.io.command.side_effect = self.command

    @contextmanager
    def guard(self, account_id):
        """在原账号互斥中读取当前中央记录。:param account_id: 原账号。:return: 当前账号与环境。"""
        with self.owner_lock:
            connection = self.fixture.database()
            try:
                account = dict(connection.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone())
                row = dict(connection.execute('SELECT * FROM account_environments WHERE account_id=?', (account_id,)).fetchone())
            finally:
                connection.close()
            yield account, row

    def command(self, node_id, operation, payload):
        """记录固定节点动作，在已声明阶段注入一次未知结果。

        :param node_id: 原节点。
        :param operation: 固定动作。
        :param payload: 私有输入。
        :return: 与真实组件合同一致的无真实凭据收据。
        """
        self.commands.append((node_id, operation, payload))
        self.assertEqual('maintenance', self.store.assignment(1)['phase'])
        if self.fail_operation == operation:
            self.fail_operation = None
            raise ValueError('合成动作响应丢失')
        if operation in ('fence', 'restore-source'):
            return {'protocol': 1, **payload, 'phase': 'fenced' if operation == 'fence' else 'restored', 'stopped_containers': []}
        if operation == 'export':
            identity = ArchiveIdentity(operation_id=self.operation, deployment_id='synthetic', source_node_key='local',
                account_id=1, environment_id='e' * 32, assignment_revision=1)
            root = self.root / 'environment'
            atomic_json(root / 'home/.claude.json', {'userID': 'a' * 64})
            archive = MigrationFiles(self.root, 'local', 'synthetic').export(root, identity, payload['attempt_id'],
                cli_version='2.1.293', cli_identity={'device_id': 'a' * 64, 'account_uuid': 'synthetic',
                    'source': 'cli:2.1.293:config.userID'}, environment_generation=4)
            return {'protocol': 1, 'node_key': 'local', 'archive': archive.model_dump()}
        if operation == 'verify-import':
            return {'protocol': 1, 'node_key': payload['node_key'], 'operation_id': self.operation,
                'transfer_id': payload['transfer_id'], 'phase': 'verified', 'sha256': payload['archive']['sha256']}
        if operation == 'prepare-import':
            stage = payload['stage']
            if payload['preparation']['account']['cc2api_account_id'] is None:
                self.assertTrue(payload['preparation']['cli_only'])
                return {'protocol':1,'node_key':stage['node_key'],'operation_id':self.operation,
                    'transfer_id':stage['transfer_id'],'phase':'prepared','assignment_revision':2,
                    'environment':self.fixture.target_environment,'binding':None}
            return {'protocol': 1, 'node_key': stage['node_key'], 'operation_id': self.operation,
                'transfer_id': stage['transfer_id'], 'phase': 'prepared', 'assignment_revision': 2,
                'environment': self.fixture.target_environment, 'sender_address': '172.28.0.4',
                'binding': {'account_id': 7, 'environment_id': 'e' * 32, 'generation': 5,
                    'secret': 's' * 64, 'release_id': self.target_account_release}}
        if operation == 'activate-import':
            published = next(item[2]['stage'] for item in reversed(self.commands) if item[1] == 'prepare-import')
            self.assertEqual(published['transfer_id'], payload['transfer_id'])
            return {'protocol': 1, **payload, 'phase': 'activated'}
        if operation == 'revoke-import':
            identity = payload['identity']
            return {'protocol': 1, 'node_key': payload['node_key'], 'operation_id': identity['operation_id'],
                'account_id': identity['account_id'], 'environment_id': identity['environment_id'],
                'revision': payload['target_revision'], 'phase': 'revoked'}
        raise AssertionError('测试收到未定义节点动作')

    def test_complete_migration_keeps_maintenance_until_activation_and_releases_lease(self) -> None:
        """实际中央事务按完整阶段推进，释放排他租约后开放新分配。:return: None。"""
        self.coordinator.begin(1, self.request)
        result = self.coordinator.run(self.operation)
        self.assertEqual('completed', result['phase'])
        self.assertEqual((self.fixture.target, 2, 'ready'),
            (self.store.assignment(1)['node_id'], self.store.assignment(1)['revision'], self.store.assignment(1)['phase']))
        self.assertEqual([], self.gateway.holders)
        self.assertEqual(['fence', 'export', 'verify-import', 'prepare-import', 'activate-import'], [item[1] for item in self.commands])
        self.assertEqual(result, self.coordinator.run(self.operation))

    def test_outdated_target_is_synchronized_before_source_fence(self) -> None:
        """原后台迁移先自动同步目标，源隔离发生在准备完成之后。:return: None。"""
        with self.fixture.database() as connection:
            connection.execute('UPDATE cluster_nodes SET preparation_json=? WHERE id=?',
                (json.dumps({'state': 'prepared', 'release': 'old'}), self.fixture.target))
        self.coordinator.service.synchronization = object()
        def prepare(node_id, revision, **options):
            """模拟后台同步完成时的真实中央登记。:return: None。"""
            self.assertEqual([], self.commands)
            self.store.save_preparation(node_id, revision, {'state': 'prepared', 'release': 'synthetic-release'})
        self.coordinator.service.prepare_node = Mock(side_effect=prepare)
        self.coordinator.begin(1, self.request)
        self.assertEqual('completed', self.coordinator.run(self.operation)['phase'])
        self.coordinator.service.prepare_node.assert_called_once_with(self.fixture.target, 1, automatic=True)

    def test_reused_account_image_can_complete_migration_under_new_control(self) -> None:
        """控制组件换批而账号镜像复用时，按账号来源核对并完成激活。:return: None。"""
        self.coordinator.runtime.account_release_id = 'synthetic-account'
        self.target_account_release = 'synthetic-account'
        with patch.dict('os.environ', {'V3_UPDATE_GATE_DIR': str(self.root / 'gate')}):
            self.coordinator.begin(1, self.request)
            result = self.coordinator.run(self.operation)
        self.assertEqual('completed', result['phase'])
        self.assertEqual((self.fixture.target, 2, 'ready'),
            (self.store.assignment(1)['node_id'], self.store.assignment(1)['revision'], self.store.assignment(1)['phase']))
        self.assertEqual([], self.gateway.holders)
        self.assertEqual(['fence', 'export', 'verify-import', 'prepare-import', 'activate-import'], [item[1] for item in self.commands])

    def test_reused_account_image_resumes_old_rejected_receipt_without_reexport(self) -> None:
        """旧校验留下待核对操作时，修复后沿原尝试完成迁移并释放原租约。:return: None。"""
        self.coordinator.runtime.account_release_id = 'synthetic-account'
        self.target_account_release = 'synthetic-account'
        with patch.dict('os.environ', {'V3_UPDATE_GATE_DIR': str(self.root / 'gate')}):
            self.coordinator.begin(1, self.request)
            with patch.object(self.coordinator, '_prepared', side_effect=ValueError('合成旧控制端批次校验失败')):
                with self.assertRaises(ValueError):
                    self.coordinator.run(self.operation)
            self.assertEqual('importing', self.coordinator.ledger.get(self.operation)['record']['last_confirmed_phase'])
            self.assertEqual((1, 'reconcile'), (self.store.assignment(1)['node_id'], self.store.assignment(1)['phase']))
            self.assertTrue(self.gateway.holders)
            self.assertEqual('completed', self.coordinator.run(self.operation)['phase'])
        for operation in ('fence', 'export', 'activate-import'):
            self.assertEqual(1, [item[1] for item in self.commands].count(operation))
        stages = [item[2]['stage'] for item in self.commands if item[1] == 'prepare-import']
        self.assertEqual(stages[0], stages[1])
        self.assertEqual([], self.gateway.holders)

    def test_control_batch_cannot_replace_expected_account_batch(self) -> None:
        """账号镜像复用时，仅与控制批次一致的绑定继续拒绝并保留源归属。:return: None。"""
        self.coordinator.runtime.account_release_id = 'synthetic-account'
        with patch.dict('os.environ', {'V3_UPDATE_GATE_DIR': str(self.root / 'gate')}):
            self.coordinator.begin(1, self.request)
            with self.assertRaisesRegex(ValueError, '发送器身份'):
                self.coordinator.run(self.operation)
        self.assertEqual((1, 'reconcile'), (self.store.assignment(1)['node_id'], self.store.assignment(1)['phase']))
        self.assertTrue(self.gateway.holders)
        self.assertNotIn('activate-import', [item[1] for item in self.commands])

    def test_node_display_and_authentication_changes_keep_original_data_location(self) -> None:
        """显示名和认证方式变化继续原操作，实际数据根变化仍须核对。:return: None。"""
        self.coordinator.begin(1, self.request)
        with self.fixture.database() as connection:
            connection.execute('UPDATE cluster_nodes SET config_json=? WHERE id=?',
                (json.dumps({'name': '新显示名', 'auth_method': 'password', 'username': 'operator'}), self.fixture.target))
        with self.guard(1) as (account, row):
            self.coordinator._context(self.operation, account)
        with self.fixture.database() as connection:
            connection.execute('UPDATE cluster_nodes SET config_json=? WHERE id=?',
                (json.dumps({'data_root': '/srv/other'}), self.fixture.target))
        with self.guard(1) as (account, row), self.assertRaisesRegex(ValueError, '节点配置'):
            self.coordinator._context(self.operation, account)

    def test_independent_migration_preserves_null_gateway_and_uses_no_gateway_lease(self) -> None:
        """独立账号沿原完整迁移切换，目标保持无Gateway绑定及发送器。:return: None。"""
        with self.fixture.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
        self.coordinator.begin(1,self.request)
        result=self.coordinator.run(self.operation)
        self.assertEqual('completed',result['phase'])
        self.assertEqual([],self.gateway.requests)
        self.assertEqual(self.fixture.target,self.store.assignment(1)['node_id'])
        self.assertNotIn('gateway_lease',result['record']['checkpoints'])

    def test_independent_unknown_activation_and_cancellation_keep_original_flow(self) -> None:
        """独立迁移提交前可取消，激活回包未知继续原目标。:return: None。"""
        with self.fixture.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
        self.coordinator.begin(1,self.request)
        self.fail_operation='activate-import'
        with self.assertRaises(ValueError):
            self.coordinator.run(self.operation)
        self.assertEqual('completed',self.coordinator.run(self.operation)['phase'])
        self.assertEqual([],self.gateway.requests)

    def test_target_preparation_failure_resumes_same_export_and_transfer(self) -> None:
        """目标响应未知后保留源维护，继续原尝试并保持源只停止和导出一次。:return: None。"""
        self.coordinator.begin(1, self.request)
        self.fail_operation = 'prepare-import'
        with self.assertRaisesRegex(ValueError, '响应丢失'):
            self.coordinator.run(self.operation)
        self.assertEqual('importing', self.coordinator.ledger.get(self.operation)['record']['last_confirmed_phase'])
        self.assertEqual('reconcile', self.store.assignment(1)['phase'])
        self.assertTrue(self.gateway.holders)
        self.assertEqual('completed', self.coordinator.run(self.operation)['phase'])
        self.assertEqual(1, [item[1] for item in self.commands].count('export'))
        preparations = [item[2]['stage']['transfer_id'] for item in self.commands if item[1] == 'prepare-import']
        self.assertEqual(preparations[0], preparations[1])

    def test_partial_upload_resumes_original_migration_with_new_persisted_transfer(self) -> None:
        """真实部分文件保留，继续原操作登记新尝试后上传完成。:return: None。"""
        target = self.root / 'upload-target'
        uploader = MigrationIO(SimpleNamespace(store=SimpleNamespace(get=lambda _: {'kind': 'local'})),
            SimpleNamespace(data=target))
        uploader.command = lambda node, operation, payload: MigrationFiles(target, payload['node_key'], 'synthetic').stage(
            ImportStage.model_validate(payload))
        attempts, partial, lost_response = [], [], []

        def upload(node, stage, bundle):
            attempts.append(stage.transfer_id)
            if not partial:
                uploader.command(node, 'stage-import', stage.model_dump())
                path = target / 'node-migrations' / self.operation / 'imports' / stage.transfer_id / 'environment.tar'
                path.write_bytes(b'partial')
                path.chmod(0o600)
                partial.append(path)
                raise ConnectionError('合成上传中断')
            result = uploader.upload(node, stage, bundle)
            if stage.transfer_id != attempts[0] and not lost_response:
                lost_response.append(True)
                raise ConnectionError('合成完整上传回包丢失')
            return result

        self.coordinator.io.upload.side_effect = upload
        self.coordinator.io.download.side_effect = lambda node, archive: (
            self.root / 'node-migrations' / self.operation / 'exports' / (archive.attempt_id + '.tar'))
        self.coordinator.begin(1, self.request)
        with self.assertRaises(ConnectionError):
            self.coordinator.run(self.operation)
        with self.assertRaisesRegex(ConnectionError, '回包丢失'):
            self.coordinator.run(self.operation)
        restored = MigrationCoordinator(self.coordinator.service, self.coordinator.runtime,
            self.gateway, self.coordinator.quota_identity, self.guard)
        restored.io = self.coordinator.io
        result = restored.run(self.operation)
        self.assertEqual('completed', result['phase'])
        self.assertEqual(2, len(set(attempts)))
        self.assertEqual(b'partial', partial[0].read_bytes())
        current = result['record']['checkpoints']['transfer']
        self.assertEqual(attempts[-1], current['transfer_id'])
        self.assertEqual([attempts[0]], current['previous_transfer_ids'])

    def test_renewed_transfer_activation_resumes_after_committed_response_loss(self) -> None:
        """新尝试提交后激活回包丢失，重建协调器继续读取持久的新尝试。:return: None。"""
        self.coordinator.begin(1, self.request)
        self.coordinator.io.upload.side_effect = [MigrationUploadIncomplete('合成部分上传'), None]
        self.fail_operation = 'activate-import'
        with self.assertRaisesRegex(ValueError, '响应丢失'):
            self.coordinator.run(self.operation)
        migration = self.coordinator.ledger.get(self.operation)
        checkpoints = migration['record']['checkpoints']
        current = checkpoints['transfer']['transfer_id']
        self.assertEqual('committed', migration['record']['last_confirmed_phase'])
        self.assertNotEqual(checkpoints['execution']['transfer_id'], current)
        restored = MigrationCoordinator(self.coordinator.service, self.coordinator.runtime,
            self.gateway, self.coordinator.quota_identity, self.guard)
        restored.io = self.coordinator.io
        self.assertEqual('completed', restored.run(self.operation)['phase'])
        activations = [item[2]['transfer_id'] for item in self.commands if item[1] == 'activate-import']
        self.assertEqual([current, current], activations)
        self.assertEqual(1, [item[1] for item in self.commands].count('prepare-import'))

    def test_transfer_cas_rejects_stale_attempt_and_cancelled_operation(self) -> None:
        """新尝试只在原上传阶段认领，迟到及取消后的换源均被拒绝。:return: None。"""
        migration = self.coordinator.begin(1, self.request)
        initial = migration['record']['checkpoints']['execution']['transfer_id']
        self.coordinator.io.upload.side_effect = ConnectionError('合成上传未确认')
        with self.assertRaises(ConnectionError):
            self.coordinator.run(self.operation)
        self.coordinator.ledger.resume(self.operation)
        self.coordinator.ledger.renew_transfer(self.operation, initial, '1' * 32)
        with self.assertRaises(ValueError):
            self.coordinator.ledger.renew_transfer(self.operation, initial, '2' * 32)
        self.coordinator.cancel(self.operation)
        with self.assertRaises(ValueError):
            self.coordinator.ledger.renew_transfer(self.operation, '1' * 32, '3' * 32)

    def test_activation_unknown_keeps_target_and_recovers_original_operation_after_gateway_restart(self) -> None:
        """提交后断线保留新归属，旧网关占用对账后只重试目标激活。:return: None。"""
        self.coordinator.begin(1, self.request)
        self.fail_operation = 'activate-import'
        with self.assertRaises(ValueError):
            self.coordinator.run(self.operation)
        self.assertEqual((self.fixture.target, 'reconcile'), (self.store.assignment(1)['node_id'], self.store.assignment(1)['phase']))
        self.gateway.holders[0].update(phase='reconcile', expires_at=0)
        self.assertEqual('completed', self.coordinator.run(self.operation)['phase'])
        self.assertEqual(1, [item[1] for item in self.commands].count('prepare-import'))
        self.assertEqual('2', self.coordinator.ledger.get(self.operation)['record']['checkpoints']['gateway_lease']['generation'])

    def test_cancel_before_export_requires_target_revocation_then_source_restore(self) -> None:
        """排空初期取消也取得双端收据，后续run保持取消结果。:return: None。"""
        self.coordinator.begin(1, self.request)
        self.assertEqual('cancelled', self.coordinator.cancel(self.operation)['phase'])
        self.assertEqual(['revoke-import', 'restore-source'], [item[1] for item in self.commands])
        self.assertEqual((1, 1, 'ready'), (self.store.assignment(1)['node_id'], self.store.assignment(1)['revision'], self.store.assignment(1)['phase']))
        self.assertEqual('cancelled', self.coordinator.run(self.operation)['phase'])

    def test_foreign_gateway_holder_blocks_node_io_and_keeps_reconcile(self) -> None:
        """其他作业租约不能被迁移撤销，节点现场保持。:return: None。"""
        self.coordinator.begin(1, self.request)
        self.gateway.holders = [{'owner': 'run:synthetic', 'generation': 'foreign', 'exclusive': False}]
        with self.assertRaisesRegex(ValueError, '其他作业'):
            self.coordinator.run(self.operation)
        self.assertEqual([], self.commands)
        self.assertEqual('reconcile', self.store.assignment(1)['phase'])

    def test_heartbeat_failure_closes_later_steps_and_retains_lease(self) -> None:
        """原租约心跳失败后新节点步骤被拒绝，租约持续保留排他占用。:return: None。"""
        self.coordinator.begin(1, self.request)
        with MigrationLease(self.gateway, self.coordinator.ledger, self.operation, 7,
                self.coordinator.service.transports, 1) as lease:
            self.gateway.fail_heartbeat = True
            with patch.object(lease.stopping, 'wait', return_value=False):
                lease._heartbeat()
            with self.assertRaisesRegex(ValueError, '续约失效'):
                lease.check()
        self.assertTrue(self.gateway.holders)

    def test_api_drain_precedes_environment_lock_and_node_mutations_hold_it(self) -> None:
        """排空不占用原transport需要的环境锁，实际停止与切换保留互斥。:return: None。"""
        held = threading.Event()
        @contextmanager
        def environment_lock(environment_id):
            held.set()
            try:
                yield
            finally:
                held.clear()
        self.coordinator.runtime.environment_lock = environment_lock
        request = self.gateway._request
        def gateway_request(method, path, payload=None):
            if payload and payload.get('operation') in ('prepare', 'claim'):
                self.assertFalse(held.is_set())
            return request(method, path, payload)
        self.gateway._request = gateway_request
        command = self.command
        def execute(node_id, operation, payload):
            self.assertTrue(held.is_set())
            return command(node_id, operation, payload)
        self.coordinator.io.command.side_effect = execute
        self.coordinator.begin(1, self.request)
        self.assertEqual('completed', self.coordinator.run(self.operation)['phase'])

    def test_unstarted_account_uses_initial_placement_without_closing_admission(self) -> None:
        """尚未运行的账号使用首次分配，迁移拒绝后原账号保持ready。:return: None。"""
        connection = self.fixture.database()
        try:
            with connection:
                connection.execute('UPDATE account_environments SET generation=0,container_id=NULL,network_container_id=NULL,sender_container_id=NULL')
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, '首次执行节点'):
            self.coordinator.begin(1, self.request)
        self.assertEqual('ready', self.store.assignment(1)['phase'])

    def test_post_commit_node_pause_preserves_recovery_and_paused_admission(self) -> None:
        """暂停节点仅关闭新工作，提交后同连接配置仍可收口原激活。:return: None。"""
        self.coordinator.begin(1, self.request)
        self.fail_operation = 'activate-import'
        with self.assertRaises(ValueError):
            self.coordinator.run(self.operation)
        self.store.set_enabled(self.fixture.target, 1, False)
        self.assertEqual('completed', self.coordinator.run(self.operation)['phase'])
        self.assertFalse(self.store.assignment(1)['enabled'])
        self.assertEqual(self.fixture.target, self.store.assignment(1)['node_id'])
