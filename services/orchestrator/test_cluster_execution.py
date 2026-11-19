"""验证私有节点准备的账号范围、持久投影及旧分配拒绝。"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from account_runtime import read_cli_identity_at
from cluster_archive import ArchiveIdentity
from cluster_execution import ImportActivation, ImportPreparation, ImportRevocation, NodeExecution, NodeInspection, NodePreparation
from cluster_migration_files import ImportStage, MigrationFiles
from cluster_deployment import node_network_name
from runtime_files import atomic_json
from database_migrations import apply_migrations


class _Runtime:
    """原运行时接口的受限执行替身，记录实际投影及通知。"""

    def __init__(self, client, data, host_data, database, fingerprint, gateway, quota_identity) -> None:
        """保存与原类签名一致的依赖。:param client: Docker替身。:param data: 数据根。:param host_data: 宿主根。:param database: 连接工厂。:param fingerprint: 画像回调。:param gateway: 受限网关。:param quota_identity: 额度回调。:return: None。"""
        self.data, self.database, self.gateway = data, database, gateway
        if (data / 'cluster-node.json').exists():
            owner = json.loads((data / 'cluster-node.json').read_text())
            self.node_key, self.deployment = owner['node_key'], owner['deployment_id']
            self.network = node_network_name(self.deployment, self.node_key)
        else:
            self.node_key, self.deployment, self.network = None, 'synthetic', 'local-test'
        self.heartbeat_pool = Mock()

    def _row(self, name, account_id):
        connection = self.database()
        try:
            return dict(connection.execute('SELECT * FROM account_environments WHERE account_id=?', (account_id,)).fetchone())
        finally:
            connection.close()

    def _root(self, row):
        return self.data / 'environments' / row['environment_id']

    def sync_credentials(self, row, account):
        """模拟原独立准备的文件发布。:param row: 原环境。:param account: 原账号。:return: None。"""
        path=self.data/'profiles'/account['name']/'.credentials.json'
        if path.exists():
            atomic_json(self._root(row)/'home/.claude/.credentials.json',json.loads(path.read_text()))

    def transport(self, account, version):
        """模拟原准备的状态变化和原生通知。:param account: 账号。:param version: 兼容版本。:return: 绑定。"""
        self.gateway._request('GET', '/admin/runtime/accounts/7/config')
        self.gateway._request('POST', '/admin/accounts/7/native-preparation', {})
        connection = self.database()
        try:
            with connection:
                connection.execute("UPDATE account_environments SET state='ready',generation=generation+1,network_container_id='network'")
        finally:
            connection.close()
        return {'account_id': 7, 'environment_id': 'e' * 32, 'generation': 1, 'secret': 'synthetic'}


class NodeExecutionTests(unittest.TestCase):
    """使用临时节点库验证真实投影和文件归属。"""

    def setUp(self) -> None:
        """建立已归属的隔离节点根。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.node_key = 'a' * 32
        atomic_json(self.root / 'cluster-node.json', {'protocol': 1, 'node_key': self.node_key, 'deployment_id': 'synthetic'})
        client = Mock()
        client.containers.list.return_value = []
        client.containers.get.return_value = SimpleNamespace(reload=Mock(), attrs={
            'NetworkSettings': {'Networks': {node_network_name('synthetic', self.node_key): {'IPAddress': '172.28.0.3'}}}})
        self.executor = NodeExecution(self.root, Path('/srv/node-data'), self.node_key, 'synthetic', client, _Runtime)
        self.request = NodePreparation(node_key=self.node_key, assignment_revision=1,
            account={'id': 1, 'name': 'synthetic', 'profile_path': 'profiles/synthetic', 'cc2api_account_id': 7},
            environment={'environment_id': 'e' * 32, 'account_id': 1, 'name': 'synthetic',
                'fingerprint_json': '{}', 'generation': 0, 'state': 'stopped'}, gateway_config={'auth_type': 'oauth'},
            quota_identity='synthetic-quota', profile_files={'.credentials.json': json.dumps({
                'claudeAiOauth': {'accessToken': 'synthetic-access', 'refreshToken': 'synthetic-refresh'}})})

    def test_prepare_persists_actual_node_state_and_omits_refresh_token(self) -> None:
        """节点实际代次回传，远程profile保持AT-only。:return: None。"""
        result = self.executor.prepare(self.request)
        self.assertEqual('172.28.0.3', result['sender_address'])
        self.assertEqual(1, result['environment']['generation'])
        self.assertEqual([7], result['native_notifications'])
        profile = json.loads((self.root / 'profiles/synthetic/.credentials.json').read_text())
        self.assertNotIn('refreshToken', profile['claudeAiOauth'])
        self.assertEqual('synthetic-access', profile['claudeAiOauth']['accessToken'])
        self.assertEqual(2, self.executor.prepare(self.request)['environment']['generation'])

    def test_independent_cli_projection_keeps_original_full_credentials_and_no_binding(self) -> None:
        """独立准备保留完整本地凭据，原运行时只进入CLI准备合同。:return: None。"""
        account = {**self.request.account, 'cc2api_account_id': None}
        request = self.request.model_copy(update={'account': account, 'gateway_config': {}, 'cli_only': True})

        def ensure(runtime, current, *, prepare_sender):
            self.assertFalse(prepare_sender)
            connection = runtime.database()
            try:
                with connection:
                    connection.execute("UPDATE account_environments SET state='ready',generation=1,network_container_id='network'")
            finally:
                connection.close()

        with patch.object(_Runtime, 'ensure', ensure, create=True):
            result = self.executor.prepare(request)
        self.assertIsNone(result['binding'])
        self.assertEqual(1, result['environment']['generation'])
        profile = json.loads((self.root / 'profiles/synthetic/.credentials.json').read_text())
        self.assertEqual('synthetic-refresh', profile['claudeAiOauth']['refreshToken'])
        self.assertEqual('synthetic-refresh',json.loads((self.root/'environments'/('e'*32)/'home/.claude/.credentials.json').read_text())['claudeAiOauth']['refreshToken'])
        with self.assertRaises(ValueError):
            self.executor.prepare(request.model_copy(update={'cli_only': False}))

    def test_assignment_revision_and_node_identity_are_fenced(self) -> None:
        """旧/错分配不能覆盖既有节点环境。:return: None。"""
        self.executor.prepare(self.request)
        for change in ({'assignment_revision': 2}, {'node_key': 'b' * 32}):
            request = self.request.model_copy(update=change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.executor.prepare(request)

    def test_failed_import_preparation_recovers_only_its_stopped_roles(self) -> None:
        """目标创建失败后保留原资料，重试核对并收口同次已停止角色。:return: None。"""
        request = self.migration_input()
        def fail(runtime, account, version):
            """模拟网络角色建立后的画像校验失败。:return: None。"""
            with runtime.database() as connection:
                connection.execute("UPDATE account_environments SET state='reconcile',network_container_id='network'")
            raise ValueError('系统画像与实际 CPU 代际冲突，需要核对迁移')
        with patch.object(_Runtime, 'transport', fail), self.assertRaisesRegex(ValueError, 'CPU'):
            self.executor.prepare_import(request)
        root = self.root / 'environments' / ('e' * 32)
        sentinel = (root / 'projects/sentinel.txt').read_bytes()
        identity = read_cli_identity_at(root, self.root / 'profiles/synthetic', '2.1.293')
        stopped = SimpleNamespace(id='network', labels={'vibebench.role': 'account-network'}, reload=lambda: None,
            attrs={'State': {'Running': False, 'Pid': 0}})
        def remove(runtime, row, *, remove):
            """只模拟同代停止角色的删除。:return: None。"""
            self.assertTrue(remove)
            with runtime.database() as connection:
                connection.execute('UPDATE account_environments SET network_container_id=NULL')
        def update(runtime, row, *, state):
            """保留原代次并更新已核对状态。:return: None。"""
            with runtime.database() as connection:
                connection.execute('UPDATE account_environments SET state=?', (state,))
        with patch.object(self.executor, '_scoped_containers', return_value=[stopped]), \
                patch.object(_Runtime, 'environment_jobs', return_value=[], create=True), \
                patch.object(_Runtime, '_stop_environment', remove, create=True), \
                patch.object(_Runtime, '_update', update, create=True):
            stopped.attrs['State'] = {'Running': True, 'Pid': 123}
            with self.assertRaisesRegex(ValueError, '实际角色'):
                self.executor.prepare_import(request)
            stopped.attrs['State'] = {'Running': False, 'Pid': 0}
            self.assertEqual('prepared', self.executor.prepare_import(request)['phase'])
        self.assertEqual(sentinel, (root / 'projects/sentinel.txt').read_bytes())
        self.assertEqual(identity, read_cli_identity_at(root, self.root / 'profiles/synthetic', '2.1.293'))

    def test_explicit_bound_login_only_prepares_original_cli_with_inactive_exception(self) -> None:
        """绑定账号显式登录准备保持原绑定及AT-only，仅将原SID交给CLI准备例外。:return: None。"""
        request=self.request.model_copy(update={'cli_only':True,'login_sid':'a'*12,
            'gateway_config':{'auth_type':'oauth','status':'disabled'}})
        calls=[]
        def ensure(runtime,account,**options):
            """只模拟原固定CLI准备，记录显式例外参数。:return: None。"""
            calls.append((account,options))
            with runtime.database() as connection:
                connection.execute("UPDATE account_environments SET state='ready',generation=1,network_container_id='network'")
        with patch.object(_Runtime,'ensure',ensure,create=True), \
                patch.object(_Runtime,'transport',side_effect=AssertionError('登录准备不发布发送绑定')):
            receipt=self.executor.prepare(request)
        self.assertIsNone(receipt['binding'])
        self.assertEqual(7,calls[0][0]['cc2api_account_id'])
        self.assertEqual({'prepare_sender':False,'allow_inactive_login':True,'ownership_source':'login:'+'a'*12},calls[0][1])
        profile=json.loads((self.root/'profiles/synthetic/.credentials.json').read_text())
        self.assertNotIn('refreshToken',profile['claudeAiOauth'])

    def test_login_preparation_exception_rejects_api_and_null_draft_identity(self) -> None:
        """显式登录例外保持已有正账号身份，API与NULL草稿继续拒绝。:return: None。"""
        draft=self.request.model_copy(update={'cli_only':True,'login_sid':'a'*12,
            'account':{**self.request.account,'id':None,'cc2api_account_id':None},'gateway_config':{}})
        api=self.request.model_copy(update={'login_sid':'a'*12})
        with patch.object(self.executor,'_runtime',side_effect=AssertionError('错误范围不能构造运行时')):
            for request in (draft,api):
                with self.subTest(independent=request.account['cc2api_account_id'] is None),self.assertRaises(ValueError):
                    self.executor.prepare(request)

    def test_inactive_independent_login_preparation_keeps_existing_account_and_complete_credentials(self) -> None:
        """已有停用独立账号明确准备CLI，完整RT与enabled保持原值。:return: None。"""
        request=self.request.model_copy(update={'cli_only':True,'login_sid':'a'*12,
            'account':{**self.request.account,'enabled':0,'cc2api_account_id':None},'gateway_config':{}})
        calls=[]
        def ensure(runtime,account,**options):
            """记录具体登录来源并模拟原布局。:param runtime: 原接口。:param account: 原账号。:param options: 原例外。:return: None。"""
            calls.append(options)
            with runtime.database() as connection:
                connection.execute("UPDATE account_environments SET state='ready',generation=1,network_container_id='network'")
        with patch.object(_Runtime,'ensure',ensure,create=True):
            result=self.executor.prepare(request)
        self.assertIsNone(result['binding'])
        self.assertEqual('login:'+'a'*12,calls[0]['ownership_source'])
        self.assertTrue(calls[0]['allow_inactive_login'])
        profile=json.loads((self.root/'profiles/synthetic/.credentials.json').read_text())
        self.assertEqual('synthetic-refresh',profile['claudeAiOauth']['refreshToken'])
        with self.executor.database() as connection:
            row=connection.execute('SELECT enabled,cc2api_account_id FROM accounts WHERE id=1').fetchone()
        self.assertEqual((0,None),tuple(row))

    def test_wrong_installation_owner_is_rejected(self) -> None:
        """数据根属于其他部署时拒绝使用。:return: None。"""
        with self.assertRaisesRegex(ValueError, '安装归属'):
            NodeExecution(self.root, Path('/srv/node-data'), 'b' * 32, 'synthetic', Mock(), _Runtime)

    def test_unowned_files_and_cross_account_paths_are_rejected(self) -> None:
        """未知目录和越界profile无法进入准备。:return: None。"""
        request = self.request.model_copy(update={'profile_files': {'../other': '{}'}})
        with self.assertRaisesRegex(ValueError, '文件超出'):
            self.executor.prepare(request)
        path = self.root / 'environments' / ('e' * 32)
        path.mkdir(parents=True)
        (path / 'unknown').write_text('保留的未知文件')
        with self.assertRaisesRegex(ValueError, '未核对归属'):
            self.executor.prepare(self.request)
        self.assertEqual('保留的未知文件', (path / 'unknown').read_text())

    def test_persisted_execution_cannot_be_treated_as_an_idle_process(self) -> None:
        """跨进程准备发现执行记录时保持保护。:return: None。"""
        self.executor.prepare(self.request)
        atomic_json(self.root / 'environments' / ('e' * 32) / 'runtime/execution.json', {'source': 'synthetic'})
        with self.assertRaisesRegex(ValueError, '执行记录'):
            self.executor.prepare(self.request)

    def test_inspection_reads_real_node_generation_and_execution_record(self) -> None:
        """只读摘要使用节点代次与持久执行事实，拒绝旧分配。:return: None。"""
        self.executor.prepare(self.request)
        root = self.root / 'environments' / ('e' * 32)
        atomic_json(root / 'runtime/execution.json', {'source': 'synthetic'})
        request = NodeInspection(node_key=self.node_key, account_id=1, environment_id='e' * 32,
            assignment_revision=1, version='2.1.293')
        with patch.object(_Runtime, 'read_cli_identity', return_value={'source': 'cli:2.1.293:config.userID'}, create=True), \
                patch.object(_Runtime, 'role_status', return_value={'cli': 'running'}, create=True), \
                patch('cluster_execution.native_kernel_status', return_value=None), \
                patch('cluster_execution.read_capture_settings', return_value={'enabled': False}), \
                patch('cluster_execution.read_criu_settings', return_value={'enabled': False}), \
                patch('cluster_execution.role_release', return_value='synthetic-release'):
            result = self.executor.inspect(request)
        self.assertEqual(1, result['generation'])
        self.assertTrue(result['busy'])
        self.assertEqual({'cli': 'running'}, result['role_status'])
        self.assertEqual({'enabled': False}, result['content_capture'])
        self.assertEqual({'enabled': False}, result['criu'])
        self.assertEqual(7, result['gateway_account_id'])
        self.assertNotIn('synthetic-access', json.dumps(result))
        with self.assertRaisesRegex(ValueError, '检查版本'):
            self.executor.inspect(request.model_copy(update={'assignment_revision': 2}))
        self.assertTrue((root / 'runtime/execution.json').exists())

    def migration_input(self) -> ImportPreparation:
        """从真实源资料建立核验后的私有目标树。:return: 带冻结CLI身份和代次的发布输入。"""
        source_data = self.root / 'source'
        source_root = source_data / 'environments' / ('e' * 32)
        identity = {'userID': 'b' * 64, 'oauthAccount': {'accountUuid': 'synthetic-account'}}
        atomic_json(source_root / 'home/.claude.json', identity)
        (source_root / 'projects').mkdir()
        (source_root / 'projects/sentinel.txt').write_text('已核对的工程资料')
        archive_identity = ArchiveIdentity(operation_id='c' * 32, deployment_id='synthetic',
            source_node_key='local' if self.node_key != 'local' else 'b' * 32,
            account_id=1, environment_id='e' * 32, assignment_revision=1)
        files = MigrationFiles(source_data, archive_identity.source_node_key, 'synthetic')
        cli_identity = {'device_id': 'b' * 64, 'account_uuid': 'synthetic-account', 'source': 'cli:2.1.293:config.userID'}
        archive = files.export(source_root, archive_identity, 'd' * 32, cli_version='2.1.293',
            cli_identity=cli_identity, environment_generation=4)
        stage = ImportStage(node_key=self.node_key, transfer_id='f' * 32, target_revision=2, archive=archive)
        target = MigrationFiles(self.root, self.node_key, 'synthetic')
        target.stage(stage)
        private = self.root / 'node-migrations' / ('c' * 32) / 'imports' / ('f' * 32)
        shutil.copyfile(source_data / 'node-migrations' / ('c' * 32) / 'exports' / ('d' * 32 + '.tar'), private / 'environment.tar')
        target.restore(stage)
        preparation = self.request.model_copy(update={'assignment_revision': 2,
            'environment': {**self.request.environment, 'generation': 4, 'state': 'ready'},
            'profile_files': {**self.request.profile_files, '.claude.json': json.dumps(identity)}})
        return ImportPreparation(stage=stage, preparation=preparation)

    def test_import_publication_preserves_identity_and_rebuilds_actual_generation(self) -> None:
        """目标从核验树准备新代次，激活范围和当前角色逐项核对。:return: None。"""
        request = self.migration_input()
        result = self.executor.prepare_import(request)
        self.assertEqual(('prepared', 5), (result['phase'], result['environment']['generation']))
        root = self.root / 'environments' / ('e' * 32)
        self.assertEqual('已核对的工程资料', (root / 'projects/sentinel.txt').read_text())
        self.assertEqual('b' * 64, json.loads((root / 'home/.claude.json').read_text())['userID'])
        activation = ImportActivation(node_key=self.node_key, operation_id='c' * 32, transfer_id='f' * 32,
            account_id=1, environment_id='e' * 32, revision=2, generation=5)
        def read_identity(runtime, row, version):
            return read_cli_identity_at(runtime._root(row), runtime.data / 'profiles/synthetic', version)
        with patch.object(_Runtime, 'read_cli_identity', read_identity, create=True), \
                patch.object(_Runtime, 'environment_jobs', return_value=[], create=True), \
                patch.object(_Runtime, '_execution_records', return_value=[], create=True), \
                patch.object(_Runtime, 'role_status', return_value=dict.fromkeys(('cli', 'sender', 'network'), 'running'), create=True):
            self.assertEqual('activated', self.executor.activate_import(activation)['phase'])
            self.assertEqual('activated', self.executor.activate_import(activation)['phase'])
            with self.assertRaisesRegex(ValueError, '发布范围'):
                self.executor.activate_import(activation.model_copy(update={'generation': 4}))

    def test_import_refuses_missing_source_proof_changed_identity_and_unknown_existing_home(self) -> None:
        """冻结证明、私有HOME和既有目录分别保护，错误发布保持原资料。:return: None。"""
        request = self.migration_input()
        for changes in ({'cli_identity': None}, {'environment_generation': 2}):
            changed = request.model_copy(update={'stage': request.stage.model_copy(update={
                'archive': request.stage.archive.model_copy(update=changes)})})
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, '身份或代次'):
                self.executor.prepare_import(changed)
        private = self.root / 'node-migrations' / ('c' * 32) / 'imports' / ('f' * 32)
        home = private / 'environment/home/.claude.json'
        original = home.read_bytes()
        atomic_json(home, {'userID': '0' * 64, 'oauthAccount': {'accountUuid': 'synthetic-account'}})
        with self.assertRaisesRegex(ValueError, 'CLI设备'):
            self.executor.prepare_import(request)
        home.write_bytes(original)
        target = self.root / 'environments' / ('e' * 32)
        target.mkdir(parents=True)
        (target / 'sentinel').write_text('原有资料')
        with self.assertRaisesRegex(ValueError, '其他操作'):
            self.executor.prepare_import(request)
        self.assertEqual('原有资料', (target / 'sentinel').read_text())

    def test_unpublished_target_revocation_blocks_all_late_publication(self) -> None:
        """撤销保留私有副本，重复撤销可核对，旧上传和发布被墓碑拒绝。:return: None。"""
        request = self.migration_input()
        revocation = ImportRevocation(node_key=self.node_key, target_revision=2, identity=request.stage.archive.identity)
        first = self.executor.revoke_import(revocation)
        self.assertEqual('revoked', first['phase'])
        self.assertEqual(first, self.executor.revoke_import(revocation))
        for operation in (lambda: self.executor.stage_import(request.stage),
                lambda: self.executor.verify_import(request.stage), lambda: self.executor.prepare_import(request)):
            with self.assertRaisesRegex(ValueError, '已撤销'):
                operation()
        private = self.root / 'node-migrations' / ('c' * 32) / 'imports' / ('f' * 32)
        self.assertEqual('已核对的工程资料', (private / 'environment/projects/sentinel.txt').read_text())

    def test_returning_target_preserves_old_fenced_home_and_uses_new_source_generation(self) -> None:
        """迁回已停机旧副本时保留原HOME，独立投影从新源代次准备。:return: None。"""
        self.executor.prepare(self.request)
        connection = self.executor.database()
        try:
            with connection:
                connection.execute('UPDATE account_environments SET generation=6')
        finally:
            connection.close()
        root = self.root / 'environments' / ('e' * 32)
        atomic_json(root / 'home/sentinel.json', {'value': '旧副本资料'})
        atomic_json(root / 'runtime/node-fence.json', {'protocol': 1, 'operation_id': '0' * 32,
            'node_key': self.node_key, 'account_id': 1, 'environment_id': 'e' * 32,
            'assignment_revision': 1, 'generation': 6, 'phase': 'fenced', 'stopped_containers': []})
        atomic_json(root / 'runtime/node-assignment.json', {'protocol': 1, 'node_key': self.node_key,
            'account_id': 1, 'environment_id': 'e' * 32, 'revision': 1, 'phase': 'fenced', 'operation_id': '0' * 32})
        self.executor.client.containers.list.return_value = []
        request = self.migration_input()
        result = self.executor.prepare_import(request)
        self.assertEqual(7, result['environment']['generation'])
        previous = self.root / 'node-migrations' / ('c' * 32) / 'imports' / ('f' * 32) / 'previous-environment'
        self.assertEqual({'value': '旧副本资料'}, json.loads((previous / 'home/sentinel.json').read_text()))
        self.assertEqual('已核对的工程资料', (root / 'projects/sentinel.txt').read_text())

    def test_local_target_keeps_central_authority_and_management_refresh_token(self) -> None:
        """本机目标准备使用独立投影，管理profile及中央环境行保持权威。:return: None。"""
        self.root = self.root / 'central'
        self.root.mkdir()
        self.node_key = 'local'
        self.request = self.request.model_copy(update={'node_key': 'local', 'profile_files': {
            '.credentials.json': json.dumps({'claudeAiOauth': {'accessToken': 'synthetic-access'}})}})
        database_path = self.root / 'central.sqlite'
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        try:
            apply_migrations(connection)
            with connection:
                connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(1,'synthetic','profiles/synthetic')")
                connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json,generation) VALUES(?,'synthetic',1,'{}',4)", ('e' * 32,))
        finally:
            connection.close()
        central_runtime = SimpleNamespace(node_key=None, deployment='synthetic', data=self.root,
            host_data=Path('/srv/central'), network='local-test', jobs={}, lock=threading.RLock(),
            capacity_lock=threading.RLock(), environment_locks={}, database=lambda: sqlite3.connect(database_path))
        client = Mock()
        client.containers.get.return_value = SimpleNamespace(reload=Mock(), attrs={
            'NetworkSettings': {'Networks': {'local-test': {'IPAddress': '172.28.0.4'}}}})
        self.executor = NodeExecution(self.root, central_runtime.host_data, 'local', 'synthetic', client,
            _Runtime, local_runtime=central_runtime)
        request = self.migration_input()
        credentials = {'claudeAiOauth': {'accessToken': 'synthetic-access', 'refreshToken': 'central-owner-refresh'}}
        atomic_json(self.root / 'profiles/synthetic/.credentials.json', credentials)
        atomic_json(self.root / 'profiles/synthetic/.claude.json', json.loads(request.preparation.profile_files['.claude.json']))
        self.assertEqual(5, self.executor.prepare_import(request)['environment']['generation'])
        self.assertEqual(credentials, json.loads((self.root / 'profiles/synthetic/.credentials.json').read_text()))
        connection = central_runtime.database()
        try:
            self.assertEqual(4, connection.execute('SELECT generation FROM account_environments').fetchone()[0])
        finally:
            connection.close()

    def test_revocation_preserves_previous_fenced_copy_before_current_publication(self) -> None:
        """本次尚未发布时取消，只核对原停止副本并保持其资料。:return: None。"""
        request = self.migration_input()
        root = self.root / 'environments' / ('e' * 32)
        previous = {'protocol': 1, 'operation_id': '0' * 32, 'node_key': self.node_key, 'account_id': 1,
            'environment_id': 'e' * 32, 'assignment_revision': 1, 'generation': 1, 'phase': 'fenced', 'stopped_containers': []}
        atomic_json(root / 'runtime/node-fence.json', previous)
        atomic_json(root / 'runtime/node-assignment.json', {'protocol': 1, 'node_key': self.node_key,
            'account_id': 1, 'environment_id': 'e' * 32, 'revision': 1, 'phase': 'fenced', 'operation_id': '0' * 32})
        atomic_json(root / 'home/sentinel.json', {'value': '原停止资料'})
        revoked = self.executor.revoke_import(ImportRevocation(node_key=self.node_key, target_revision=2,
            identity=request.stage.archive.identity))
        self.assertEqual('revoked', revoked['phase'])
        self.assertEqual(previous, json.loads((root / 'runtime/node-fence.json').read_text()))
        self.assertEqual({'value': '原停止资料'}, json.loads((root / 'home/sentinel.json').read_text()))

    def test_revocation_refuses_actual_roles_when_target_root_is_missing(self) -> None:
        """目录缺失时实际角色仍须核对，未知进程阻止源重新开放。:return: None。"""
        request = self.migration_input()
        self.executor.client.containers.list.return_value = [SimpleNamespace(labels={'vibebench.cluster-node': self.node_key})]
        with self.assertRaisesRegex(ValueError, '缺少运行目录'):
            self.executor.revoke_import(ImportRevocation(node_key=self.node_key, target_revision=2,
                identity=request.stage.archive.identity))
        self.assertFalse((self.root / 'node-migrations' / ('c' * 32) / 'revoked.json').exists())


    def test_borrowed_runtime_keeps_shared_pool_and_unknown_records_stay_closed(self) -> None:
        """持久运行时释放只归还借用，执行记录须与本进程实际job逐项一致。:return: None。"""
        release = Mock()
        self.executor.runtime_release, self.executor.shared_runtime = release, True
        runtime = self.executor._runtime(Mock())
        self.executor._release_runtime(runtime)
        release.assert_called_once_with(runtime)
        runtime.heartbeat_pool.shutdown.assert_not_called()
        row = {'environment_id': 'e' * 32, 'generation': 3, 'container_id': 'synthetic-cli'}
        root = self.root / 'environments' / row['environment_id']
        path = root / 'runtime/executions/known.json'
        job = {'source': 'projects:synthetic:1', 'row': row, 'account': {'cc2api_account_id': 7}}
        atomic_json(path, {'source': job['source'], 'generation': 3, 'container_id': row['container_id'], 'account_id': 7})
        current = SimpleNamespace(_root=lambda current: root, _execution_records=lambda current: [path],
            _execution_path=lambda current: path, environment_jobs=lambda environment: [job])
        self.executor._check_execution_records(current, row)
        atomic_json(path, {'source': job['source'], 'generation': 2, 'container_id': row['container_id'], 'account_id': 7})
        with self.assertRaisesRegex(ValueError, '代次不匹配'):
            self.executor._check_execution_records(current, row)


if __name__ == '__main__':
    unittest.main()
