"""使用真实SQLite验证AGY环境归属、预算、采集CAS与维护门禁。"""
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
from agy_environment import SOURCE_SHA256, capture, lookup, lookup_environment, maintenance, quiesce, register, sender_config, transport
from database_migrations import apply_migrations, migration_plan
from runtime_files import atomic_json


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
            self.assertEqual(migration_plan(connection)['current_version'],2)
        finally:
            connection.close()

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
        with patch('agy_environment.configured_release',return_value='synthetic-release'),patch('agy_environment.role_release',return_value='synthetic-release'), \
                patch('agy_environment.image_origin',return_value={'image_id':'synthetic-image'}),patch('agy_environment.role_container',return_value=SimpleNamespace(status='running',reload=lambda:None)):
            self.assertEqual(transport(self.runtime,17),binding)
            self.assertEqual(transport(self.runtime,17),binding)
            self.assertEqual(transport(self.runtime,17,wake=False),binding)
        self.runtime._make_room.assert_not_called()

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


if __name__=='__main__':
    unittest.main()
