"""平台内置内核迁移、归属和历史维护门禁回归。"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import native_kernel_upgrade as kernel
from native_sender import builtin_config
from runtime_files import atomic_json


class PlatformKernelTests(unittest.TestCase):
    """以独立文件和SQLite核对历史数据生命周期。"""

    def setUp(self):
        """准备唯一账号、旧选择和双版目标镜像。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.row = {'environment_id': 'a' * 32, 'generation': 3, 'state': 'ready', 'sender_container_id': 'sender'}
        self.account = {'id': 1, 'name': 'synthetic', 'cc2api_account_id': 7}
        self.config = {'binding': {'environment_id': self.row['environment_id'], 'generation': 3, 'account_id': 7,
            'release_id': 'synthetic-platform'}, 'native': {'binary_path': '/usr/local/bin/ccrb-runtime',
            'memory_mib': 0, 'max_workers': 6, 'work_root': '/native',
            'release': {'release': 'v0.1.0-beta.6', 'launcher_sha256': 'a' * 64}, 'kernel_generation': 'old'}}
        atomic_json(self.root / 'runtime/sender.json', self.config)
        self.database = self.root / 'accounts.sqlite'
        with sqlite3.connect(self.database) as connection:
            connection.execute('CREATE TABLE accounts(cc2api_account_id INTEGER, deleted_at REAL)')
            connection.execute('INSERT INTO accounts VALUES(7,NULL)')
        self.runtime = SimpleNamespace(_root=lambda row: self.root,
            _sender_config=lambda row: self.root / 'runtime/sender.json',
            database=lambda: sqlite3.connect(self.database), environment_jobs=Mock(return_value=[]),
            _execution_records=Mock(return_value=[]), _running_sender_active=Mock(return_value=0),
            _stop_environment=Mock(), _write_sender_config=lambda row, config: atomic_json(self.root / 'runtime/sender.json', config),
            _update=lambda row, **changes: row.update(changes), ensure=Mock(return_value=(self.row, None)),
            gateway=SimpleNamespace(_request=Mock()), client=Mock(), image='synthetic-image')
        self.runtime.client.images.get.return_value.attrs = {'Config': {'Labels': {
            'vibebench.native-runtime-versions': '2.1.280,2.1.293'}}}
        self.lease = {'owner': 'kernel:synthetic-operation', 'generation': 'original-lease', 'phase': 'claimed', 'exclusive': True}
        self.runtime.gateway._request.return_value = {'active': 0, 'waiting': 0, 'lease': self.lease}
        self.runtime.gateway._request.side_effect = lambda method, path, body=None: (
            {'lease': None} if method == 'POST' and body.get('operation') == 'release' else self.runtime.gateway._request.return_value)

    def save(self, state='active', version='2.1.293', **fields):
        """写入合成历史记录。@param state 原阶段。@param version 源版本。@param fields 覆盖字段。@return 原始记录。"""
        value = {'state': state, 'account_id': 7, 'binding_generation': 3,
            'operation_id': 'synthetic-operation', 'lease_generation': 'original-lease',
            'current': self.config['native']['release'], **fields}
        atomic_json(kernel._record(self.root, version), value)
        return value

    def test_completed_choices_migrate_both_versions_and_are_old_platform_readable(self):
        """两份选择原子收口为内置，重复迁移保持字节一致。@return None。"""
        for version in kernel.HISTORICAL_VERSIONS:
            self.save(version=version, preparing_release='v0.1.0-beta.7', prepared={'release': 'candidate'})
        kernel.migrate_records(self.root, 7)
        before = [kernel._record(self.root, version).read_bytes() for version in kernel.HISTORICAL_VERSIONS]
        for version in kernel.HISTORICAL_VERSIONS:
            value = kernel._load(self.root, version)
            self.assertEqual(value['state'], 'restored')
            self.assertIsNone(value['current'])
            self.assertIsNone(value['kernel_generation'])
            self.assertFalse(value['previous_available'])
            self.assertIsNone(value['prepared'])
            self.assertIsNone(value['preparing_release'])
            self.assertEqual(value['migrated_from']['current'], self.config['native']['release'])
        kernel.migrate_records(self.root, 7)
        self.assertEqual(before, [kernel._record(self.root, version).read_bytes() for version in kernel.HISTORICAL_VERSIONS])
        self.assertFalse(kernel.pending_upgrade(self.root, include_preparing=True))

    def test_old_platform_can_change_previously_migrated_record_and_next_upgrade_normalizes_it(self):
        """旧平台保留迁移标记并恢复独立选择后，新升级仍再次清除选择。@return None。"""
        self.save(state='restored', management='platform', prepared={'release':'v0.1.0-beta.7'})
        kernel.migrate_records(self.root, 7)
        value = kernel._load(self.root)
        self.assertIsNone(value['current'])
        self.assertIsNone(value['prepared'])
        self.assertEqual(value['migrated_from']['current'], self.config['native']['release'])

    def test_foreign_record_or_unknown_phase_rejects_before_any_write(self):
        """全部记录先核对，第二份异常保留第一份选择。@return None。"""
        self.save(version='2.1.280')
        original = kernel._record(self.root, '2.1.280').read_bytes()
        for fields in ({'account_id': 8}, {'state': 'unexpected'}, {'state': 'switching'}):
            self.save(**fields)
            with self.assertRaises(ValueError):
                kernel.migrate_records(self.root, 7)
            self.assertEqual(original, kernel._record(self.root, '2.1.280').read_bytes())

    def test_readonly_status_survives_missing_release_key_and_uses_no_old_pid(self):
        """只读信息脱离独立发行公钥，旧预热PID保持在历史摘要中。@return None。"""
        self.save(pid=1234, image_sha256='b' * 64)
        value = kernel.status(self.runtime, self.row)
        self.assertEqual(value['management'], 'platform')
        self.assertEqual(value['state'], 'migration_required')
        self.assertEqual(value['builtin']['launcher_sha256'], kernel.SHA256)
        self.assertNotIn('pid', value)
        self.assertIsNone(kernel.status(self.runtime, self.row, '2.1.280'))
        self.runtime.gateway._request.assert_not_called()

    def test_binding_archive_preserves_both_records_and_admits_new_owner(self):
        """旧绑定终态归档后，新账号通过同一归属校验；原审计保留。@return None。"""
        originals = {version: self.save(version=version) for version in kernel.HISTORICAL_VERSIONS}
        kernel.archive_binding_records(self.root, 7)
        kernel.validate_records(self.root, 8)
        kernel.archive_binding_records(self.root, 7)
        for version, original in originals.items():
            path = kernel._record(self.root, version)
            self.assertFalse(path.exists())
            self.assertEqual(json.loads(path.with_name(f'{path.stem}.account-7.json').read_text()), original)

    def test_binding_archive_rejects_foreign_pending_and_migration_before_writes(self):
        """两版统一预检，跨账号、迁移和无归属记录保持原文件。@return None。"""
        self.save(version='2.1.280')
        original = kernel._record(self.root, '2.1.280').read_bytes()
        for fields in ({'account_id': 8}, {'state': 'switching'}, {'state': 'unexpected'}):
            self.save(**fields)
            with self.assertRaises(ValueError):
                kernel.archive_binding_records(self.root, 7)
            self.assertEqual(kernel._record(self.root, '2.1.280').read_bytes(), original)
        self.save()
        atomic_json(kernel._migration(self.root), {})
        with self.assertRaises(ValueError):
            kernel.archive_binding_records(self.root, 7)
        kernel._migration(self.root).unlink()
        with self.assertRaises(ValueError):
            kernel.archive_binding_records(self.root, None)
        self.assertEqual(list((self.root / 'runtime').glob('*.account-*.json')), [])

    def test_archive_write_interruption_preserves_record_and_retry(self):
        """归档持久化失败保留活动记录，恢复后重复交接仍采用内置。@return None。"""
        original = self.save()
        with patch.object(kernel, 'atomic_json', side_effect=OSError('合成持久化失败')):
            with self.assertRaises(OSError):
                kernel.archive_binding_records(self.root, 7)
        self.assertEqual(kernel._load(self.root), original)
        kernel.archive_binding_records(self.root, 7)
        self.assertFalse(kernel._record(self.root).exists())

    def test_retired_preparing_marker_is_audited_and_real_maintenance_stays_blocked(self):
        """旧下载标记退出门禁，真实未完成操作和迁移日志继续保护。@return None。"""
        for version in kernel.HISTORICAL_VERSIONS:
            self.save(version=version, preparing_release='v0.1.0-beta.7')
        self.assertFalse(kernel.pending_upgrade(self.root, include_preparing=True))
        self.assertFalse(kernel.recover_interrupted(self.root))
        for version in kernel.HISTORICAL_VERSIONS:
            record = kernel._load(self.root, version)
            self.assertIsNone(record['preparing_release'])
            self.assertEqual(record['cancelled_preparing_release'], 'v0.1.0-beta.7')
        self.save(state='switching', preparing_release='v0.1.0-beta.7')
        self.assertTrue(kernel.recover_interrupted(self.root))
        self.assertEqual(kernel._load(self.root)['state'], 'reconcile')
        self.save()
        atomic_json(kernel._migration(self.root), {})
        self.assertTrue(kernel.pending_upgrade(self.root, include_preparing=True))

    def test_foreign_or_corrupt_record_is_shown_as_environment_reconciliation(self):
        """读取接口明确投影未知归属和损坏迁移日志。@return None。"""
        self.save(account_id=8)
        value = kernel.status(self.runtime, self.row)
        self.assertEqual(value['state'], 'reconcile')
        self.assertIn('环境对账', value['error'])
        self.assertNotIn('account_id', value)
        self.runtime.gateway._request.assert_not_called()
        kernel._migration(self.root).write_text('{invalid')
        self.assertEqual(kernel.status(self.runtime,self.row)['state'],'reconcile')

    def test_owned_interrupted_maintenance_rebuilds_before_lease_release(self):
        """原租约保护重建，发送器就绪后释放同一代次。@return None。"""
        self.save(state='switching')
        kernel.recover_interrupted(self.root)
        events = []
        def ensure(account, prepare_sender, native_migration):
            """模拟发送器实际就绪回执。@return 环境结果。"""
            self.assertFalse(prepare_sender)
            self.assertIsNone(kernel._load(self.root)['current'])
            self.assertNotIn('runtimes', json.loads((self.root / 'runtime/sender.json').read_text())['native'])
            self.assertTrue(native_migration)
            events.append('ready')
            return self.row, None
        self.runtime.ensure.side_effect = ensure
        self.runtime.gateway._request.side_effect = lambda method, path, body=None: (
            {'active': 0, 'waiting': 0, 'lease': self.lease} if method == 'GET' else (events.append(body) or {'lease': None}))
        kernel.reconcile_legacy(self.runtime, self.row, self.account)
        self.assertEqual(events, ['ready', {'operation': 'release', 'owner': self.lease['owner'], 'generation': self.lease['generation']}])
        self.assertFalse(kernel.pending_upgrade(self.root))

    def test_active_or_foreign_maintenance_preserves_original_roles_and_lease(self):
        """活动、外来owner或租约代次漂移均保护原现场。@return None。"""
        self.save(state='reconcile', reconcile_from='switching')
        for snapshot in ({'active': 0, 'holders': [{'owner':'foreign-cli'}], 'lease': self.lease}, {'active': 1, 'lease': self.lease}, {'active': 0, 'waiting': 1, 'lease': self.lease},
                {'active': 0, 'lease': {**self.lease, 'owner': 'other'}},
                {'active': 0, 'lease': {**self.lease, 'generation': 'other'}}, {'active': 0, 'lease': None}):
            self.runtime.gateway._request.return_value = snapshot
            with self.assertRaises(ValueError):
                kernel.reconcile_legacy(self.runtime, self.row, self.account)
            self.runtime._stop_environment.assert_not_called()
            self.runtime.ensure.assert_not_called()
            self.assertEqual(self.runtime.gateway._request.call_args.args[0], 'GET')

    def test_wrong_binding_and_account_or_operation_generation_preserve_gate(self):
        """跨账号和旧代次异常保持维护状态。@return None。"""
        for fields in ({'account_id': 8}, {'binding_generation': 2}, {'operation_id': None}, {'reconcile_from': 'unknown'}):
            self.save(state='reconcile', reconcile_from='switching', **{k:v for k,v in fields.items() if k != 'reconcile_from'})
            if 'reconcile_from' in fields:
                self.save(state='reconcile', **fields)
            with self.assertRaises(ValueError):
                kernel.reconcile_legacy(self.runtime, self.row, self.account)
            self.runtime._stop_environment.assert_not_called()

    def test_stopped_environment_migrates_without_waking(self):
        """停止环境完成文件迁移，保持停止状态。@return None。"""
        self.row['state'] = 'stopped'
        self.save(state='reconcile', reconcile_from='draining')
        kernel.reconcile_legacy(self.runtime, self.row, self.account)
        self.assertEqual(self.row['state'], 'stopped')
        self.runtime.ensure.assert_not_called()
        self.assertFalse(kernel.pending_upgrade(self.root))

    def test_failed_rebuild_keeps_same_lease_and_reconcile_identity(self):
        """就绪失败保留旧租约和操作归属。@return None。"""
        self.save(state='reconcile', reconcile_from='restoring')
        self.runtime.ensure.side_effect = ValueError('synthetic unavailable')
        with self.assertRaises(ValueError):
            kernel.reconcile_legacy(self.runtime, self.row, self.account)
        self.assertEqual(self.row['state'], 'reconcile')
        self.assertTrue(kernel.pending_upgrade(self.root))
        self.assertEqual(kernel._read(kernel._migration(self.root))['records']['2.1.293']['lease_generation'], 'original-lease')
        self.assertEqual(self.runtime.gateway._request.call_count, 1)

    def test_process_interruption_keeps_journal_and_recovers_after_generation_changes(self):
        """清除旧选择后掉电，持久日志继续绑定原门禁及受控新代次。@return None。"""
        self.save(state='reconcile', reconcile_from='switching')
        def interrupted(account, **options):
            """模拟创建新代发送器之后进程退出。@return 抛出掉电信号。"""
            self.row['generation'] += 1
            config = json.loads(self.runtime._sender_config(self.row).read_text())
            config['binding']['generation'] = self.row['generation']
            atomic_json(self.runtime._sender_config(self.row), config)
            raise KeyboardInterrupt('synthetic restart')
        self.runtime.ensure.side_effect = interrupted
        with self.assertRaises(KeyboardInterrupt):
            kernel.reconcile_legacy(self.runtime, self.row, self.account)
        self.assertIsNone(kernel._load(self.root)['current'])
        self.assertTrue(kernel.recover_interrupted(self.root))
        self.assertTrue(kernel.migration_context(self.root, self.row, 7))
        self.runtime.ensure.side_effect = None
        self.runtime.ensure.return_value = (self.row, None)
        kernel.reconcile_legacy(self.runtime, self.row, self.account)
        self.assertFalse(kernel.pending_upgrade(self.root))
        self.assertEqual(self.runtime.ensure.call_count, 2)

    def test_missing_draining_lease_is_reacquired_before_any_destructive_step(self):
        """原租约消失时重新关门，有新在途请求则保留日志等待再次对账。@return None。"""
        self.save(state='reconcile', reconcile_from='draining')
        self.runtime.gateway._request.side_effect = [
            {'active': 0, 'waiting': 0, 'lease': None},
            {'active': 1, 'waiting': 0, 'lease': {**self.lease, 'generation': 'new-lease', 'phase': 'draining', 'exclusive': True}}]
        with self.assertRaisesRegex(ValueError, '等待原请求结束'):
            kernel.reconcile_legacy(self.runtime, self.row, self.account)
        self.runtime._stop_environment.assert_not_called()
        self.assertTrue(kernel.pending_upgrade(self.root))
        journal = kernel._read(kernel._migration(self.root))
        self.assertEqual(journal['records']['2.1.293']['lease_generation'], 'new-lease')

    def test_lost_release_response_resumes_finishing_with_a_new_owned_gate(self):
        """释放已发生且回执丢失时，重试仍核对实际活动并重新持有门禁。@return None。"""
        self.save(state='reconcile', reconcile_from='switching')
        lease, lost = dict(self.lease), False
        actions = []
        def request(method, path, body=None):
            """模拟实际释放成功与回执失联。@return 门禁快照。"""
            nonlocal lease, lost
            if method == 'GET':
                return {'active': 0, 'waiting': 0, 'lease': lease}
            actions.append(body)
            if body['operation'] == 'prepare':
                lease = {'owner': body['owner'], 'generation': 'new-lease', 'phase': 'draining', 'exclusive': True}
            elif body['operation'] == 'claim':
                lease['phase'] = 'claimed'
            else:
                lease = None
                if not lost:
                    lost = True
                    raise OSError('synthetic lost acknowledgement')
            return {'active': 0, 'waiting': 0, 'lease': lease}
        self.runtime.gateway._request.side_effect = request
        with self.assertRaises(OSError):
            kernel.reconcile_legacy(self.runtime, self.row, self.account)
        self.assertTrue(kernel.pending_upgrade(self.root))
        self.assertEqual(kernel._read(kernel._migration(self.root))['phase'], 'finishing')
        kernel.reconcile_legacy(self.runtime, self.row, self.account)
        self.assertFalse(kernel.pending_upgrade(self.root))
        self.assertEqual([action['operation'] for action in actions], ['release','prepare','claim','release'])
        self.assertEqual(actions[-1]['generation'], 'new-lease')

    def test_empty_migration_journal_remains_explicitly_blocked(self):
        """空日志保持未知维护门禁，归属不足时拒绝任何副作用。@return None。"""
        atomic_json(kernel._migration(self.root), {})
        self.assertTrue(kernel.pending_upgrade(self.root))
        with self.assertRaisesRegex(ValueError, '缺少归属信息'):
            kernel.reconcile_legacy(self.runtime, self.row, self.account)
        self.runtime.gateway._request.assert_not_called()
        self.runtime._stop_environment.assert_not_called()

    def test_builtin_layout_target_versions_preserve_frozen_resources(self):
        """双版历史账号归一到 293 后保留预算，重复迁移得到相同配置。@return None。"""
        original = {**self.config['native'], 'runtimes': {'2.1.280': {'binary_path': '/usr/local/bin/ccrb-runtime-280'}}}
        single = builtin_config(original, ('2.1.293',))
        self.assertEqual({k: single[k] for k in ('memory_mib','max_workers','work_root')},
            {k: original[k] for k in ('memory_mib','max_workers','work_root')})
        self.assertNotIn('release', single)
        self.assertNotIn('runtimes', single)
        self.assertEqual(builtin_config(single, ('2.1.293',)), single)
