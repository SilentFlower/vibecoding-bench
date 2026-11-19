"""节点统一同步的真实中央SQLite与固定Docker归属恢复验证。"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from docker.errors import NotFound

from cluster_deployment import node_container_name
from cluster_nodes import NodeCreate
from cluster_synchronization import NodeSynchronization, NodeSynchronizationWait
from runtime_files import atomic_json
import test_cluster_nodes


class NodeSynchronizationTests(unittest.TestCase):
    """核对同批幂等、真实旧组件换批和失败时的原容器恢复。"""

    def setUp(self) -> None:
        """建立真实节点记录和可观察的容器生命周期。:return: None。"""
        self.fixture = test_cluster_nodes.ClusterNodeTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = self.fixture.service
        self.row = self.service.register(NodeCreate(**self.fixture.config, private_key=self.fixture.key.read_text()))
        self.node = self.service.connection(self.row['id'])
        self.runtime = SimpleNamespace(release_id='new', deployment='synthetic', credential_ownership=None)
        self.sync = NodeSynchronization(self.service, self.runtime, Mock(), lambda account: 'synthetic')
        self.addCleanup(self.sync.close)
        self.name = node_container_name('synthetic', self.row['node_key'])
        labels = {'vibebench.product':'v3','vibebench.deployment':'synthetic','vibebench.cluster-node':self.row['node_key'],
            'vibebench.role':'node-control','vibebench.release':'old'}
        self.old = Mock(id='old-container', labels=labels, status='running')
        self.old.name = self.name
        self.old.attrs = {'Image':'old-image','Mounts':[{'Destination':'/data','Source':self.fixture.config['data_root'],'RW':True}],
            'State':{'Running':True,'Pid':100}}
        self.events = []
        def stop(**kwargs):
            self.events.append('stop')
            self.old.status='exited';self.old.attrs['State']={'Running':False,'Pid':0}
        def start():
            self.events.append('start')
            self.old.status='running';self.old.attrs['State']={'Running':True,'Pid':100}
        def rename(name):
            self.events.append('rename');self.old.name=name
        self.old.stop.side_effect=stop;self.old.start.side_effect=start;self.old.rename.side_effect=rename
        self.remote=Mock()
        def lookup(name):
            if name==self.old.id or name==self.old.name:
                return self.old
            raise NotFound('synthetic')
        self.remote.containers.get.side_effect=lookup
        self.remote.containers.list.side_effect=lambda **options: [self.old] if options.get('all') else []
        helper=Mock()
        helper.wait.return_value={'StatusCode':0}
        self.remote.containers.run.side_effect=lambda *args,**kwargs:self.events.append('backup') or helper
        self.service.docker=Mock(return_value=self.remote)
        self.installer=Mock(release='new')
        self.installer.prepare.side_effect=lambda *args: self.events.append('install') or {'state':'prepared','release':'new','protocol':1}
        context=patch('cluster_synchronization.DockerClient',return_value=self.remote)
        context.start();self.addCleanup(context.stop)
        self.node.docker_socket=Mock(return_value=self.fixture.root/'docker.sock')
        self.node.agent_health=Mock(return_value={'release':'old','node_key':self.row['node_key']})

    def test_old_running_control_is_stopped_and_replaced_in_place(self) -> None:
        """旧控制原地停止并换批，保留数据与接单偏好。:return: None。"""
        result=self.sync.install(self.installer,self.row['id'],1)
        self.assertEqual('prepared',result['state'])
        self.assertEqual(['stop','rename','install'],self.events)
        self.old.remove.assert_called_once()
        job=json.loads((self.node.private/'maintenance/current.json').read_text())
        self.assertEqual('completed',job['phase'])
        self.assertEqual('old',job['old_release'])
        self.assertEqual('new',job['target_release'])
        self.assertEqual('in_place', job['data_policy'])
        self.assertNotIn('backup', job)
        self.remote.containers.run.assert_not_called()
        self.assertTrue(self.service.store.get(self.row['id'])['enabled'])

    def test_in_place_platform_restore_keeps_later_data_and_uses_no_copy_helper(self) -> None:
        """原地恢复旧组件时保留后来文件及同一目录，不建立复制或恢复进程。:return: None。"""
        self.sync.install(self.installer, self.row['id'], 1)
        journal = self.node.private / 'maintenance/current.json'
        job = json.loads(journal.read_text())
        job.update(platform_operation='a' * 32, platform_epoch='b' * 32)
        atomic_json(journal, job)
        project = self.fixture.root / 'data/projects/current.txt'
        project.parent.mkdir(parents=True)
        project.write_text('当前工程资料')
        inode = project.stat().st_ino
        self.node.observe = Mock()
        gate = {'operation_id': job['platform_operation'], 'epoch': job['platform_epoch'], 'phase': 'blocked', 'active': 0}
        self.sync.gateway._request.return_value = gate
        with patch('cluster_synchronization.UPDATE_GATE.state', return_value=gate), \
                patch('cluster_synchronization.DockerClient') as client:
            result = self.sync.restore_platform_snapshot(self.row['id'])
        self.assertEqual('old', result['release'])
        self.assertEqual('当前工程资料', project.read_text())
        self.assertEqual(inode, project.stat().st_ino)
        self.assertEqual(self.name, self.old.name)
        self.assertEqual('running', self.old.status)
        self.assertEqual('platform_restored', json.loads(journal.read_text())['phase'])
        client.assert_not_called()
        self.remote.containers.run.assert_not_called()

    def test_legacy_backup_worker_is_stopped_before_in_place_switch(self) -> None:
        """历史在途复制仅在原作业和镜像匹配后停止，沿同一日志切换。:return: None。"""
        maintenance = {'operation_id': 'a' * 32, 'epoch': 'b' * 32}
        gate = {**maintenance, 'phase': 'blocked', 'active': 0}
        self.sync.gateway._request.return_value = gate
        with patch('cluster_synchronization.UPDATE_GATE.state', return_value=gate):
            self.sync.install(self.installer, self.row['id'], 1, maintenance=maintenance, stage_only=True)
            journal = self.node.private / 'maintenance/current.json'
            job = json.loads(journal.read_text())
            job['phase'] = 'fenced'
            job.pop('data_policy')
            atomic_json(journal, job)
            helper = Mock(labels={'flower.maintenance.job': job['job_id']})
            helper.attrs = {'Image': job['old_image'], 'State': {'Running': True, 'Pid': 1}}
            helper.stop.side_effect = lambda **options: helper.attrs.update(State={'Running': False, 'Pid': 0})
            lookup = self.remote.containers.get.side_effect
            self.remote.containers.get.side_effect = lambda name: helper if name.startswith('flower-node-backup-') else lookup(name)
            self.sync.install(self.installer, self.row['id'], 1, maintenance=maintenance)
        helper.stop.assert_called_once_with(timeout=5)
        helper.remove.assert_called_once()
        self.assertEqual('in_place', json.loads(journal.read_text())['data_policy'])
        self.remote.containers.run.assert_not_called()

    def test_failed_new_control_returns_original_named_running_control(self) -> None:
        """新控制启动失败时原地恢复原容器名和原运行状态。:return: None。"""
        self.installer.prepare.side_effect=RuntimeError('PRIVATE_SYNC_CANARY')
        with self.assertRaises(RuntimeError):
            self.sync.install(self.installer,self.row['id'],1)
        self.assertEqual(self.name,self.old.name)
        self.assertEqual('running',self.old.status)
        self.old.remove.assert_not_called()
        job=json.loads((self.node.private/'maintenance/current.json').read_text())
        self.assertEqual('rolled_back',job['phase'])
        self.assertEqual('in_place',job['data_policy'])
        self.assertNotIn('backup',job)
        self.remote.containers.run.assert_not_called()
        self.assertNotIn('PRIVATE_SYNC_CANARY',str(self.service.store.list()))

    def test_same_batch_uses_original_idempotent_installer(self) -> None:
        """同批只复核原组件，避免无意义停机和备份。:return: None。"""
        self.old.labels['vibebench.release']='new'
        self.sync.install(self.installer,self.row['id'],1)
        self.assertEqual(['install'],self.events)
        self.old.stop.assert_not_called()
        self.old.rename.assert_not_called()

    def test_unknown_role_is_blocked_before_stopping_control(self) -> None:
        """中央零账号不代表真实Node空闲，未知角色保持现场。:return: None。"""
        unknown=Mock(id='unknown',labels={'vibebench.environment':'unregistered'})
        self.remote.containers.list.side_effect=lambda **options: [self.old,unknown] if options.get('all') else []
        with self.assertRaises(NodeSynchronizationWait):
            self.sync.install(self.installer,self.row['id'],1)
        self.old.stop.assert_not_called()
        self.installer.prepare.assert_not_called()

    def _cancelled_target(self) -> dict:
        """建立与线上取消现场相同的停止目标及撤销收据。:return: 测试标记路径与角色。"""
        operation, environment = 'e' * 32, 'f' * 32
        receipt = {'operation_id': operation, 'account_id': 1, 'environment_id': environment,
            'revision': 2, 'phase': 'revoked'}
        record = {'environment_id': environment, 'source_revision': 1, 'source_generation': 61,
            'last_confirmed_phase': 'cancelled', 'receipts': {'target_revoked': {**receipt, 'node_id': self.row['id']}}}
        with self.fixture.database() as connection:
            connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(1,'synthetic','profiles/synthetic')")
            connection.execute("INSERT INTO node_migrations(operation_id,account_id,source_node_id,target_node_id,phase,record_json,created_at,updated_at) "
                "VALUES(?,1,1,?,'cancelled',?,0,0)", (operation, self.row['id'], json.dumps(record)))
        data = self.fixture.root / 'cancelled-target'
        root = data / 'environments' / environment
        expected = {**receipt, 'protocol': 1, 'node_key': self.row['node_key']}
        target = root / 'runtime/node-migration-target.json'
        revoked = data / 'node-migrations' / operation / 'revoked.json'
        fence = root / 'runtime/node-fence.json'
        atomic_json(target, {**expected, 'source_generation': 61})
        atomic_json(revoked, expected)
        atomic_json(fence, {'protocol': 1, 'operation_id': operation, 'node_key': self.row['node_key'],
            'account_id': 1, 'environment_id': environment, 'assignment_revision': 2, 'generation': 62,
            'phase': 'fenced', 'stopped_containers': ['cancelled-network']})
        atomic_json(root / 'home/project.json', {'data': '保留原资料'})
        role = Mock(id='cancelled-network', labels={'vibebench.environment': environment, 'vibebench.role': 'account-network'})
        role.attrs = {'State': {'Running': False, 'Pid': 0}}
        self.remote.containers.list.side_effect = lambda **options: (
            [role] if 'vibebench.environment=' + environment in options.get('filters', {}).get('label', [])
            else [self.old, role]) if options.get('all') else []

        def read(command, *, data, **options):
            value = json.loads(data)
            value['root'] = str(root.parent.parent)
            result = subprocess.run([sys.executable, '-c', shlex.split(command)[-1]],
                input=json.dumps(value).encode(), capture_output=True)
            if result.returncode:
                raise ValueError('节点只读标记核对失败')
            return result.stdout

        self.node._command = Mock(side_effect=read)
        return {'environment': environment, 'operation': operation, 'root': root,
            'target': target, 'revoked': revoked, 'fence': fence, 'role': role}

    def test_cancelled_target_is_preserved_and_component_upgrade_resumes(self) -> None:
        """取消目标残留网络角色时，自动核对后原地完成同步并保留全部资料。:return: None。"""
        target = self._cancelled_target()
        original = {path: path.read_bytes() for path in target['root'].rglob('*') if path.is_file()}
        revoked = target['revoked'].read_bytes()
        target['revoked'].unlink()
        with self.assertRaises(NodeSynchronizationWait):
            self.sync.install(self.installer, self.row['id'], 1)
        pending = json.loads((self.node.private / 'maintenance/current.json').read_text())
        target['revoked'].write_bytes(revoked)
        result = self.sync.install(self.installer, self.row['id'], 1)
        self.assertEqual('prepared', result['state'])
        self.assertEqual(['stop', 'rename', 'install'], self.events)
        job = json.loads((self.node.private / 'maintenance/current.json').read_text())
        self.assertEqual(pending['job_id'], job['job_id'])
        self.assertEqual('completed', job['phase'])
        self.assertEqual([target['environment']], job['historical_environments'])
        self.assertEqual(original, {path: path.read_bytes() for path in original})
        target['role'].remove.assert_not_called()
        with self.fixture.database() as connection:
            self.assertEqual('cancelled', connection.execute('SELECT phase FROM node_migrations').fetchone()[0])
            self.assertEqual(1, connection.execute('SELECT node_id FROM account_node_assignments').fetchone()[0])

    def test_cancelled_target_requires_matching_terminal_receipts_and_markers(self) -> None:
        """外来操作、节点、代次或缺失撤销证明保持原控制运行。:return: None。"""
        target = self._cancelled_target()
        for name, key, value in (
                ('target', 'operation_id', 'a' * 32), ('target', 'source_generation', 99),
                ('target', 'phase', 'published'), ('revoked', 'node_key', 'b' * 32),
                ('fence', 'assignment_revision', 3), ('fence', 'account_id', 2)):
            with self.subTest(file=name, key=key):
                path = target[name]
                original = path.read_bytes()
                atomic_json(path, {**json.loads(original), key: value})
                try:
                    with self.assertRaises(NodeSynchronizationWait):
                        self.sync.install(self.installer, self.row['id'], 1)
                finally:
                    path.write_bytes(original)
        target['revoked'].unlink()
        with self.assertRaises(NodeSynchronizationWait):
            self.sync.install(self.installer, self.row['id'], 1)
        self.old.stop.assert_not_called()

    def test_completed_source_keeps_original_generation_proof(self) -> None:
        """已完成迁移的旧源继续按原代次识别，与取消目标分别核对。:return: None。"""
        target = self._cancelled_target()
        with self.fixture.database() as connection:
            record = json.loads(connection.execute('SELECT record_json FROM node_migrations').fetchone()[0])
            record.update(source_generation=62, source_revision=2, last_confirmed_phase='completed')
            connection.execute("UPDATE node_migrations SET phase='completed',source_node_id=?,target_node_id=1,record_json=?",
                (self.row['id'], json.dumps(record)))
        self.assertTrue(self.sync._historical_environment(self.node, self.name, self.row['id'], target['environment']))
        marker = json.loads(target['fence'].read_text())
        atomic_json(target['fence'], {**marker, 'generation': 99})
        self.assertFalse(self.sync._historical_environment(self.node, self.name, self.row['id'], target['environment']))
        self.installer.prepare.assert_not_called()

    def test_cancelled_target_requires_actual_stopped_registered_roles(self) -> None:
        """撤销证明齐全时仍逐个核对实际角色、PID及停止登记。:return: None。"""
        target = self._cancelled_target()
        role = target['role']
        for state in ({'Running': True, 'Pid': 99}, {'Running': False, 'Pid': 99}):
            with self.subTest(state=state):
                role.attrs['State'] = state
                with self.assertRaises(NodeSynchronizationWait):
                    self.sync.install(self.installer, self.row['id'], 1)
        role.attrs['State'] = {'Running': False, 'Pid': 0}
        role.id = 'foreign-network'
        with self.assertRaises(NodeSynchronizationWait):
            self.sync.install(self.installer, self.row['id'], 1)
        role.id = 'cancelled-network'
        role.labels['vibebench.role'] = 'unknown'
        with self.assertRaises(NodeSynchronizationWait):
            self.sync.install(self.installer, self.row['id'], 1)
        self.old.stop.assert_not_called()
        self.installer.prepare.assert_not_called()

    def test_cancelled_target_requires_central_cancellation_receipt(self) -> None:
        """节点自报撤销不能代替中央原操作完成收据。:return: None。"""
        self._cancelled_target()
        with self.fixture.database() as connection:
            record = json.loads(connection.execute('SELECT record_json FROM node_migrations').fetchone()[0])
            record['receipts']['target_revoked']['node_id'] = 1
            connection.execute('UPDATE node_migrations SET record_json=?', (json.dumps(record),))
        with self.assertRaises(NodeSynchronizationWait):
            self.sync.install(self.installer, self.row['id'], 1)
        self.old.stop.assert_not_called()

    def test_source_or_target_pending_migration_blocks_empty_node(self) -> None:
        """目标尚无归属账号时，未完成迁移仍阻止组件切换。:return: None。"""
        with self.fixture.database() as connection:
            connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(1,'synthetic','profiles/synthetic')")
            connection.execute("INSERT INTO node_migrations(operation_id,account_id,source_node_id,target_node_id,phase,record_json,created_at,updated_at) VALUES(?,1,1,?,'reconcile','{}',0,0)",('a'*32,self.row['id']))
        with self.assertRaisesRegex(NodeSynchronizationWait,'迁移'):
            self.sync.install(self.installer,self.row['id'],1)
        self.old.stop.assert_not_called()
        self.installer.prepare.assert_not_called()

    def test_automatic_sync_only_enrolls_managed_outdated_nodes(self) -> None:
        """自动扫描保留首次登记确认，显式统一同步可提交首次节点。:return: None。"""
        self.service.prepare_node=Mock()
        self.sync.synchronize()
        self.service.prepare_node.assert_not_called()
        self.service.store.save_preparation(self.row['id'],1,{'state':'prepared','release':'old'})
        self.sync.synchronize()
        self.service.prepare_node.assert_called_once_with(self.row['id'],1,automatic=True)

    def test_initially_assigned_node_is_prepared_without_an_extra_button_click(self) -> None:
        """已保存首次归属的节点自动纳管，空白未使用节点保持按需准备。:return: None。"""
        with self.fixture.database() as connection:
            connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(1,'synthetic','profiles/synthetic')")
            connection.execute('UPDATE account_node_assignments SET node_id=? WHERE account_id=1', (self.row['id'],))
        self.service.prepare_node = Mock()
        self.sync.synchronize()
        self.service.prepare_node.assert_called_once_with(self.row['id'], 1, automatic=True)

    def test_platform_preparation_only_stops_then_resumes_original_journal(self) -> None:
        """平台切换前仅冻结停止，新中央沿同一操作原地恢复。:return: None。"""
        maintenance = {'operation_id': 'a' * 32, 'epoch': 'b' * 32}
        gate = {**maintenance, 'phase': 'blocked', 'active': 0}
        self.sync.gateway._request.return_value = gate
        with patch('cluster_synchronization.UPDATE_GATE.state', return_value=gate):
            prepared = self.sync.install(self.installer, self.row['id'], 1, maintenance=maintenance, stage_only=True)
            self.assertEqual('waiting_for_platform', prepared['phase'])
            self.installer.prepare.assert_not_called()
            job = json.loads((self.node.private / 'maintenance/current.json').read_text())
            self.assertEqual('backed_up', job['phase'])
            self.assertEqual('b' * 32, job['backup_epoch'])
            self.sync.install(self.installer, self.row['id'], 1, maintenance=maintenance)
        self.assertEqual(0, self.events.count('backup'))
        self.remote.containers.run.assert_not_called()
        self.assertEqual(1, self.events.count('install'))

    def test_platform_restart_requires_original_host_resume_for_current_boot(self) -> None:
        """重启核对保留已冻结备份，宿主明确恢复后才换批。:return: None。"""
        self.service.store.save_preparation(self.row['id'], 1, {'state': 'preparing', 'target_release': 'new'})
        directory = self.node.private / 'maintenance'
        directory.mkdir(parents=True)
        job = {'phase': 'backed_up', 'platform_operation': 'original', 'platform_epoch': 'epoch',
            'target_release': 'new', 'resume_boot_id': 'previous-boot'}
        (directory / 'current.json').write_text(json.dumps(job))
        self.service.prepare_node = Mock()
        gate = {'phase': 'blocked', 'operation_id': 'original', 'epoch': 'epoch'}
        with patch('cluster_synchronization.UPDATE_GATE.state', return_value=gate):
            self.sync.synchronize()
            self.service.prepare_node.assert_not_called()
            job['resume_boot_id'] = self.sync.boot_id
            (directory / 'current.json').write_text(json.dumps(job))
            self.sync.synchronize()
            self.service.prepare_node.assert_called_once_with(self.row['id'], 1, automatic=True,
                maintenance={'operation_id': 'original', 'epoch': 'epoch'})

    def test_paused_export_can_update_pristine_target_and_keep_original_migration(self) -> None:
        """源已隔离且目标尚无副本时，先更新空目标以恢复原迁移。:return: None。"""
        operation = 'c' * 32
        record = {'last_confirmed_phase': 'source_fenced', 'receipts': {'source_fenced': {}}, 'checkpoints': {}}
        with self.fixture.database() as connection:
            connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(1,'synthetic','profiles/synthetic')")
            connection.execute("INSERT INTO node_migrations(operation_id,account_id,source_node_id,target_node_id,phase,record_json,created_at,updated_at) VALUES(?,1,1,?,'reconcile',?,0,0)",
                (operation, self.row['id'], json.dumps(record)))
        self.node._command = Mock(return_value=b'{"pristine":true}')
        self.assertEqual('prepared', self.sync.install(self.installer, self.row['id'], 1)['state'])
        with self.fixture.database() as connection:
            migration = connection.execute('SELECT phase,record_json FROM node_migrations WHERE operation_id=?', (operation,)).fetchone()
        self.assertEqual('reconcile', migration['phase'])
        self.assertEqual(record, json.loads(migration['record_json']))

    def test_component_lock_and_migration_lock_exclude_each_other(self) -> None:
        """两端迁移实际占锁时，组件安装复用原状态并等待；释放后可继续。:return: None。"""
        migration = {'source_node_id': 1, 'target_node_id': self.row['id']}
        with self.service.migration_nodes(migration):
            self.assertTrue(self.service.operation_locks[self.row['id']].locked())
            with self.assertRaisesRegex(ValueError, '同步'):
                with self.service.migration_nodes(migration):
                    self.fail('相同节点的第二项操作必须等待')
        self.assertFalse(self.service.operation_locks[self.row['id']].locked())

    def test_bound_restore_uses_actual_account_release_for_transport_receipt(self) -> None:
        """控制镜像独立更新时，发送绑定仍按实际账号镜像批次核验。:return: None。"""
        self.old.attrs['Config'] = {'Env': ['V3_RELEASE=new-control', 'V3_ACCOUNT_RELEASE=original-account']}
        account = {'id': 1, 'name': 'synthetic', 'cc2api_account_id': 7, 'assignment_revision': 2, 'assignment_phase': 'ready'}
        environment = {'state': 'ready'}
        job = {'job_id': 'd' * 32, 'node_id': self.row['id'], 'node_key': self.row['node_key'], 'fences': {},
            'accounts': [{'account': account, 'environment': environment}], 'target_release': 'new-control', 'phase': 'restoring'}
        self.service.build_preparation = Mock(return_value='synthetic-request')
        self.service.deliver_preparation = Mock(return_value={'binding': {'release_id': 'original-account'}})
        self.service._adopt_remote = Mock()
        assignment = {'node_id': self.row['id'], 'revision': 2}
        with patch.object(self.service.store, 'assignment', return_value=assignment):
            self.sync._restore_accounts(self.node, self.name, job, preserve=False)
        self.assertEqual('original-account', self.service._adopt_remote.call_args.kwargs['expected_release'])
        projected = self.service.build_preparation.call_args.args[0]
        self.assertNotIn('assignment_phase', projected)
        self.assertNotIn('assignment_revision', projected)
