"""使用真实SQLite验证AGY环境归属、预算、采集CAS与维护门禁。"""
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from account_runtime import AccountRuntime, derive_v3_fingerprint
from agy_environment import SOURCE_SHA256, capture, lookup, lookup_environment, maintenance, quiesce, register, sender_config, summary, transport
from agy_kernel import activate, catalog, module_root, selection, stage, work_root
from agy_tool_continuation import configured_binding, read_policy, save_policy
from cluster_service import ClusterService
from cluster_store import ClusterStore
from database_migrations import apply_migrations, migration_plan
from runtime_files import atomic_json
from system_updates import runtime_snapshot


class AgyEnvironmentTests(unittest.TestCase):
    """验证API环境复用现有持久生命周期而独立绑定网关身份。"""

    def setUp(self):
        """建立合成临时库与原运行时。@return 无。"""
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        def database():
            connection=sqlite3.connect(self.root/'db.sqlite')
            connection.row_factory=sqlite3.Row
            return connection
        self.database=database
        connection=database()
        try:
            apply_migrations(connection)
            connection.execute("INSERT INTO accounts(name,profile_path) VALUES('agy_17','synthetic')")
            connection.commit()
        finally:
            connection.close()
        self.environment=patch.dict(os.environ,{'V3_DEPLOYMENT_ID':'synthetic','V3_ACCOUNT_IMAGE':'synthetic',
            'V3_NETWORK':'synthetic','V3_ACCOUNT_MEMORY':'4g','V3_ACCOUNT_SWAP':'0'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.runtime=AccountRuntime(Mock(),self.root,self.root,database,derive_v3_fingerprint,Mock())
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)

    def test_platform_mapping_survives_repeat_without_engineering_account(self):
        """同号工程账号和AGY账号保持独立归属，读取零初始化。@return 无。"""
        self.assertIsNone(lookup(self.runtime,17))
        row=register(self.runtime,17)
        self.assertIsNone(row['account_id'])
        self.assertEqual(row['name'],'agy:17')
        self.assertEqual(register(self.runtime,17)['environment_id'],row['environment_id'])
        self.assertEqual(lookup_environment(self.runtime,row['environment_id'])['gateway_account_id'],17)
        connection=self.database()
        try:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM accounts').fetchone()[0],1)
            self.assertEqual(migration_plan(connection)['current_version'],6)
        finally:
            connection.close()

    def test_tool_continuation_is_frozen_per_environment_and_checked_on_save(self):
        """核对默认值、旧版本写入拒绝、历史能力以及已派发的绑定。@return 无。"""
        first=register(self.runtime,17)['environment_id']
        second=register(self.runtime,18)['environment_id']
        binding={'environment_id':first,'agy_tool_continuation_protocol':1}
        original=configured_binding(self.root,binding)
        self.assertEqual(read_policy(self.root,first),{'mode':'claim','revision':0})
        with self.assertRaisesRegex(ValueError,'暂不支持'):
            save_policy(self.root,first,0,'history',supported=False)
        saved=save_policy(self.root,first,0,'history',supported=True)
        self.assertEqual(saved,{'mode':'history','revision':1})
        self.assertNotIn('agy_tool_continuation_mode',original)
        self.assertEqual(configured_binding(self.root,binding)['agy_tool_continuation_mode'],'history')
        self.assertEqual(read_policy(self.root,second),{'mode':'claim','revision':0})
        with self.assertRaisesRegex(ValueError,'已变化'):
            save_policy(self.root,first,0,'claim_with_history',supported=True)
        self.assertEqual(save_policy(self.root,first,1,'claim_with_history',supported=True)['revision'],2)
        self.assertEqual(configured_binding(self.root,binding)['agy_tool_continuation_mode'],'claim_with_history')

    def test_stopped_environment_shows_configured_local_node(self):
        """停止的环境也显示本机归属，实际进程状态沿原取值。@return 无。"""
        row = register(self.runtime, 17)
        connection = self.database()
        try:
            connection.execute("UPDATE cluster_nodes SET name=? WHERE node_key='local'", ('合成中央节点',))
            node_id = connection.execute("SELECT id FROM cluster_nodes WHERE node_key='local'").fetchone()['id']
            connection.commit()
        finally:
            connection.close()
        with patch.object(self.runtime, 'role_status', return_value={'sender': 'stopped'}):
            result = summary(self.runtime, row)
        self.assertEqual(result['node'], {'node_id': node_id, 'node_key': 'local',
            'node_name': '合成中央节点', 'kind': 'local', 'enabled': True})
        self.assertEqual(result['agy_runtime']['state'], 'sleeping')

    def test_finite_resources_stay_inside_original_total(self):
        """AGY物理进程上限沿账号并发，有限RAM不足在创建前拒绝。@return 无。"""
        labels={'vibebench.agy-runtime-protocol':'1','vibebench.agy-runtime-source-sha256':SOURCE_SHA256}
        self.assertEqual(sender_config({'concurrency':1},{'mem':'4g'},labels)['max_workers'],1)
        self.assertEqual(sender_config({'concurrency':2},{'mem':'unlimited'},labels)['memory_mib'],0)
        with self.assertRaises(ValueError):
            sender_config({'concurrency':2},{'mem':'1g'},labels)
        with self.assertRaises(ValueError):
            sender_config({'concurrency':1},{'mem':'4g'},{})

    def test_capture_cas_binds_original_environment_generation(self):
        """采集配置仅作用于后续请求，过时代次和版本在写入前拒绝。@return 无。"""
        row=register(self.runtime,17)
        folder=self.runtime._root(row)/'runtime/sender'
        folder.mkdir(parents=True)
        atomic_json(folder/'sender.json',{'native_capture_dir':'/flows/api/agy-prepared'})
        before=capture(self.runtime,row)
        after=capture(self.runtime,row,{'enabled':False,'expected_generation':row['generation'],'expected_revision':before['revision']})
        self.assertFalse(after['enabled'])
        self.assertTrue(after['applied'])
        with self.assertRaises(ValueError):
            capture(self.runtime,row,{'enabled':False,'expected_generation':row['generation'],'expected_revision':before['revision']})

    def test_busy_native_tool_turn_blocks_environment_stop(self):
        """实际工具轮计数参与既有维护门禁，许可最终释放。@return 无。"""
        row=register(self.runtime,17)
        self.runtime.gateway._request.side_effect=lambda method,path,body:{'lease':{'owner':body['owner'],'generation':'synthetic'},'active':0}
        self.runtime._running_sender_active=Mock(return_value=1)
        self.runtime._stop_environment=Mock()
        with self.assertRaises(ValueError):
            maintenance(self.runtime,row,'stop')
        self.runtime._stop_environment.assert_not_called()
        self.assertEqual(self.runtime.gateway._request.call_args.args[2]['operation'],'release')

    def test_existing_binding_reuses_current_environment_and_read_does_not_wake(self):
        """重复API请求复用已运行环境，只读查询保持当前代次。@return 无。"""
        row=register(self.runtime,17)
        self.runtime._update(row,state='ready',generation=1,container_id='cli',network_container_id='network',sender_container_id='sender')
        config={'account_id':17,'platform':'antigravity','auth_type':'oauth','status':'active','concurrency':1,
            'proxy_url':'http://127.0.0.1:8888','credential_state':{'phase':'ready'}}
        labels={'vibebench.product':'v3','vibebench.role':'account','vibebench.release':'synthetic-release','vibebench.isolation-version':'2',
            'vibebench.agy-runtime-protocol':'1','vibebench.agy-runtime-source-sha256':SOURCE_SHA256}
        self.runtime.gateway._request.return_value=config
        self.runtime.client.images.get.return_value=SimpleNamespace(attrs={'Id':'synthetic-image','Config':{'Labels':labels}})
        binding={'account_id':17,'environment_id':row['environment_id'],'generation':1,'release_id':'synthetic-release',
            'endpoint':'http://synthetic:8091','secret':'synthetic-secret-at-least-32-bytes'}
        folder=self.runtime._root(row)/'runtime/sender';folder.mkdir(parents=True)
        atomic_json(folder/'sender.json',{'binding':binding,'agy':sender_config(config,json.loads(row['fingerprint_json']),labels),'proxy_source':config['proxy_url']})
        self.runtime._make_room=Mock();self.runtime._wait_network=Mock();self.runtime._sender_active=Mock(return_value=0)
        container = SimpleNamespace(status='running', attrs={'Image': 'synthetic-image'}, reload=lambda:None)
        with patch('agy_environment.configured_release',return_value='synthetic-release'),patch('agy_environment.role_release',return_value='synthetic-release'), \
                patch('agy_environment.role_container',return_value=container):
            self.assertEqual(transport(self.runtime,17),binding)
            self.assertEqual(transport(self.runtime,17),binding)
            self.assertEqual(transport(self.runtime,17,wake=False),binding)
        self.runtime._make_room.assert_not_called()

    def test_kernel_stage_activation_and_rollback_are_bound_to_one_environment(self):
        """验证另一环境隔离、旧代次、活动工具及失败探测均保持原选择。@return 无。"""
        first = register(self.runtime, 17)
        second = register(self.runtime, 18)
        self.runtime._update(first, generation=3)
        folders = {}
        for row in (first, second):
            folder = self.runtime._root(row) / 'runtime/sender'
            folder.mkdir(parents=True)
            folders[row['environment_id']] = folder
            atomic_json(folder / 'sender.json', {'binding': {
                'account_id': row['gateway_account_id'], 'environment_id': row['environment_id'],
                'generation': row['generation'], 'release_id': 'original'},
                'agy': {'module_root': module_root(None), 'work_root': work_root(None)}})
        source = self.root / 'candidate'
        resources = source / 'resources'
        resources.mkdir(parents=True)
        for name in ('__init__.py', 'kernel.py', 'supervisor.py', 'storage.py'):
            (source / name).write_text('# 合成候选\n')
        hashes = {}
        for name in ('observer-c', 'relocation_reclaim.so'):
            (resources / name).write_bytes(b'synthetic')
            hashes['resources/' + name] = hashlib.sha256(b'synthetic').hexdigest()
        atomic_json(resources / 'admission.json', {'source_sha256': SOURCE_SHA256, 'resource_hashes': hashes})
        folder = folders[first['environment_id']]
        candidate = stage(source, folder)
        self.assertEqual(stage(source, folder), candidate)
        self.assertEqual(catalog(self.runtime, first)['candidates'], [candidate])
        self.assertEqual(catalog(self.runtime, second)['candidates'], [])
        self.assertIsNone(selection(self.runtime, first))
        change = {'expected_generation': 3, 'expected_kernel': None, 'kernel': candidate}
        with self.assertRaisesRegex(ValueError, '代次'):
            activate(self.runtime, first, {**change, 'expected_generation': 2}, None)
        with self.assertRaisesRegex(ValueError, '不存在'):
            activate(self.runtime, second, {**change, 'expected_generation': second['generation']}, None)
        self.runtime.gateway._request.assert_not_called()

        def lease(method, path, body):
            self.assertEqual((method, path), ('POST', '/admin/runtime/accounts/17/lease'))
            return {'lease': {'owner': body['owner'], 'generation': 'lease-3',
                'phase': 'claimed' if body['operation'] == 'claim' else 'preparing'}, 'active': 0, 'waiting': 0}

        self.runtime.gateway._request.side_effect = lease
        self.runtime._running_sender_active = Mock(return_value=1)
        self.runtime._write_sender_config = Mock(side_effect=lambda row, config: atomic_json(
            folders[row['environment_id']] / 'sender.json', config))
        sender = Mock()
        with self.assertRaisesRegex(ValueError, '工具'):
            activate(self.runtime, first, change, sender)
        sender.exec_run.assert_not_called()
        self.assertEqual(self.runtime.gateway._request.call_args.args[2]['operation'], 'release')
        self.runtime._running_sender_active.return_value = 0
        sender.exec_run.return_value.exit_code = 1
        with self.assertRaisesRegex(ValueError, '启动检查'):
            activate(self.runtime, first, change, sender)
        self.runtime._write_sender_config.assert_not_called()
        self.assertEqual(self.runtime.gateway._request.call_args.args[2]['operation'], 'release')

        sender.exec_run.return_value.exit_code = 0
        self.assertEqual(activate(self.runtime, first, change, sender)['kernel'], candidate)
        self.assertEqual(sender.exec_run.call_args.kwargs['user'], '1001:1001')
        self.assertEqual(self.runtime.read_sender_configuration(first)['agy']['work_root'], work_root(candidate))
        self.assertEqual(selection(self.runtime, first, release='original'), candidate)
        self.assertIsNone(selection(self.runtime, first, release='new-platform'))
        self.assertIsNone(selection(self.runtime, second))
        with self.assertRaisesRegex(ValueError, '内核已变化'):
            activate(self.runtime, first, change, sender)
        self.assertIsNone(activate(self.runtime, first, {**change, 'expected_kernel': candidate, 'kernel': None}, sender)['kernel'])
        self.assertEqual(self.runtime.read_sender_configuration(first)['agy']['work_root'], work_root(None))

        target = folder / 'agy-kernels' / candidate / 'agy_runtime/kernel.py'
        target.chmod(0o644)
        target.write_text('# 已变更\n')
        with self.assertRaisesRegex(ValueError, '校验失败'):
            activate(self.runtime, first, change, sender)
        self.assertIsNone(selection(self.runtime, first))

    def test_configuration_quiesce_checks_native_activity_before_stopping(self):
        """配置事务沿原网关门禁，并用物理活动补充重启后计数。@return 无。"""
        row=register(self.runtime,17)
        proof={'owner':'gateway-config:synthetic','generation':'lease-generation'}
        self.runtime.gateway._request.return_value={'lease':{**proof,'exclusive':True},'active':0}
        self.runtime._running_sender_active=Mock(return_value=1)
        self.runtime._stop_environment=Mock()
        with self.assertRaises(ValueError):quiesce(self.runtime,row,proof)
        self.runtime._stop_environment.assert_not_called()

    def test_late_maintenance_generation_is_rejected_before_docker(self):
        """页面的旧代维护动作在真实生命周期锁内拒绝。@return 无。"""
        row=register(self.runtime,17)
        self.runtime._stop_environment=Mock()
        with self.assertRaisesRegex(ValueError,'代次'):
            self.runtime.maintenance(row['environment_id'],'stop',row['generation']+1)
        self.runtime._stop_environment.assert_not_called()

    def test_cluster_update_snapshot_keeps_agy_local_and_waits_for_activity(self):
        """集群归属判定保留AGY本机路径，更新排空核对实际许可及凭据。@return 无。"""
        row=register(self.runtime,17)
        cluster=ClusterService(ClusterStore(self.database,threading.RLock()),self.root,self.runtime.client,self.root/'transport')
        self.addCleanup(cluster.close)
        self.runtime.locality=cluster.owns_local
        self.runtime.cluster_service=cluster
        self.assertTrue(cluster.owns_local(row))
        lease={'active':0,'waiting':0,'lease':None}
        configuration={'credential_state':{'phase':'ready'}}
        self.runtime.gateway._request.side_effect=lambda method,path:lease if path.endswith('/lease') else configuration
        gate=SimpleNamespace(state=lambda:{'phase':'blocked','active':0})
        with patch('system_updates.UPDATE_GATE',gate):
            snapshot=runtime_snapshot(self.runtime)
            self.assertTrue(snapshot['ready'],snapshot['blockers'])
            self.assertEqual(snapshot['environments'][0]['platform'],'antigravity')
            self.assertEqual(snapshot['environments'][0]['gateway_account_id'],17)
            for busy in [{'active':1},{'waiting':1},{'lease':{'owner':'synthetic'}}]:
                with self.subTest(busy=busy),patch.dict(lease,busy):
                    snapshot=runtime_snapshot(self.runtime)
                    self.assertFalse(snapshot['ready'])
                    self.assertIn('AGY账号许可或凭据操作尚未收口',snapshot['blockers'][0])
            configuration['credential_state']['phase']='reconcile'
            self.assertFalse(runtime_snapshot(self.runtime)['ready'])


if __name__=='__main__':
    unittest.main()
