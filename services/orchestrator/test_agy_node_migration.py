"""AGY 分配、归档边界和原发送器排空回归。"""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from agy_environment import SOURCE_SHA256, lookup
from agy_node import AgyNode
from agy_placement import AgyPlacement
from cluster_archive import AgyArchiveIdentity, restore_environment_archive
from cluster_migration_files import MigrationFiles
from cluster_migrations import NodeMigrations
from cluster_store import ClusterStore
from cluster_transport import NodeTransport, NodeTransports
from database_migrations import apply_migrations
from system_updates import runtime_snapshot


class AgyMigrationTests(unittest.TestCase):
    """使用同号正式账号和 AGY 网关账号落实独立归属。"""

    def setUp(self) -> None:
        """建立隔离的共享账本。@return 无。"""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.store = ClusterStore(self.database, threading.Lock())
        self.ledger = NodeMigrations(self.store, agy=True)
        connection = self.database()
        try:
            apply_migrations(connection)
            with connection:
                connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(7,'cc-fixture','profiles/cc-fixture')")
                connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json) "
                    "VALUES(?,'cc-fixture',7,'{}')", ('c' * 32,))
                connection.execute("INSERT INTO account_environments(environment_id,name,fingerprint_json,generation,isolation_version,state) "
                    "VALUES(?,'agy:7','{}',4,2,'ready')", ('a' * 32,))
                connection.execute("INSERT INTO platform_api_environments(gateway_account_id,environment_id,platform) "
                    "VALUES(7,?,'antigravity')", ('a' * 32,))
                connection.execute("INSERT INTO cluster_nodes(id,node_key,name,kind,config_json,created_at,preparation_json) "
                    "VALUES(2,?,'合成 SSH 节点','ssh','{}',0,?)", ('b' * 32, json.dumps({'state': 'prepared'})))
        finally:
            connection.close()

    def database(self):
        """读取本次隔离数据库。@return 调用方关闭的连接。"""
        connection = sqlite3.connect(self.root / 'bench.sqlite')
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def test_platform_and_generation_cas_keep_cc_assignment(self):
        """分配和环境更新都核对独立平台及冻结代次。@return 无。"""
        operation = 'e' * 32
        self.ledger.begin(operation, 7, 2, 1)
        with self.assertRaisesRegex(ValueError, '其他平台'):
            NodeMigrations(self.store).begin(operation, 7, 2, 1)
        with self.database() as connection:
            connection.execute("UPDATE account_environments SET generation=5 WHERE name='agy:7'")
        result = self.ledger.advance(operation, 'draining', {})
        self.assertEqual(result['record']['source_generation'], 5)
        for phase in ('source_fenced', 'exporting', 'importing', 'verified'):
            self.ledger.advance(operation, phase, {})
        actual = {**lookup(self.store, 7), 'generation': 6, 'state': 'ready',
            'container_id': 'cli', 'network_container_id': 'network', 'sender_container_id': 'sender'}
        with self.assertRaises(ValueError):
            self.ledger.commit(operation, {**actual, 'gateway_account_id': 8})
        committed = self.ledger.commit(operation, actual)
        self.assertEqual(committed['phase'], 'committed')
        self.assertEqual(self.store.agy_assignment(7)['phase'], 'maintenance')
        self.assertEqual(self.store.assignment(7)['node_id'], 1)
        self.ledger.isolate(operation, 'migration_step_unconfirmed')
        self.assertEqual(self.ledger.resume(operation)['phase'], 'committed')
        self.ledger.finish(operation, {'operation_id': operation, 'node_id': 2, 'account_id': 7,
            'environment_id': 'a' * 32, 'revision': 2, 'generation': 6, 'phase': 'activated'})
        self.assertEqual(self.store.agy_assignment(7)['phase'], 'ready')
        self.assertEqual(self.store.agy_assignment(7)['node_id'], 2)

    def test_drain_cancel_preserves_running_source(self):
        """取消尚未隔离的迁移保留原进程代次与运行状态。@return 无。"""
        operation = 'd' * 32
        self.ledger.begin(operation, 7, 2, 1)
        self.ledger.request_drain_cancel(operation)
        self.assertEqual(self.ledger.advance(operation, 'draining', {})['phase'], 'requested')
        self.assertEqual(self.ledger.finish_drain_cancel(operation)['phase'], 'cancelled')
        self.assertEqual(self.store.agy_assignment(7)['revision'], 1)
        row = lookup(self.store, 7)
        self.assertEqual((row['generation'], row['state']), (4, 'ready'))

    def test_original_node_binding_is_accepted_through_drain_only(self):
        """相同数字的 CC 流与 AGY 流分别计数，隔离前冻结原路径。@return 无。"""
        with self.database() as connection:
            for table in ('agy_node_assignments', 'account_node_assignments'):
                connection.execute(f'UPDATE {table} SET node_id=2 WHERE account_id=7')
        transports = NodeTransports(self.store)
        agy = NodeTransport(2, 'b' * 32, 7, 'a' * 32, 1, 4, self.root / 'agy.sock', 'd' * 64, agy=True)
        cc = NodeTransport(2, 'b' * 32, 7, 'c' * 32, 1, 0, self.root / 'cc.sock', 'e' * 64)
        transports.register(agy)
        transports.register(cc)
        operation = 'd' * 32
        self.ledger.begin(operation, 7, 1, 1)
        entry = transports.acquire(agy.node_key, agy.environment_id, 1, 'Bearer ' + agy.secret)
        self.assertEqual(transports.account_streams(7, agy=True), 1)
        self.assertEqual(transports.account_streams(7), 0)
        transports.end(entry)
        self.ledger.advance(operation, 'draining', {})
        with self.assertRaises(ValueError):
            transports.authorize(agy.node_key, agy.environment_id, 1, 'Bearer ' + agy.secret)
        self.assertIs(transports.authorize(cc.node_key, cc.environment_id, 1, 'Bearer ' + cc.secret), cc)

    def test_remote_quiesce_uses_exact_drained_gateway_configuration_lease(self):
        """配置许可覆盖零活动排空期，原代次和活动检查继续生效。@return 无。"""
        placement = AgyPlacement.__new__(AgyPlacement)
        lease = {'owner': 'gateway-config:' + 'e' * 32, 'generation': 'f' * 32, 'exclusive': True, 'phase': 'draining'}
        snapshot = {'lease': lease, 'active': 0}
        placement.runtime = SimpleNamespace(gateway=Mock())
        placement.runtime.gateway._request.return_value = snapshot
        proof = {key: lease[key] for key in ('owner', 'generation')}
        with placement._maintenance(7, proof):
            pass
        with self.assertRaisesRegex(ValueError, '配置许可已变化'), placement._maintenance(7, {**proof, 'generation': '1'}):
            self.fail('过期配置许可不应获准')
        snapshot['active'] = 1
        with self.assertRaisesRegex(ValueError, '配置许可已变化'), placement._maintenance(7, proof):
            self.fail('有原请求时不应静默')

    def test_remote_archive_requires_gateway_deletion_and_same_stopped_generation(self):
        """只有网关确认删除且最新投影已静默时，原分配才从节点工作中归档。@return 无。"""
        with self.database() as connection:
            connection.execute('UPDATE agy_node_assignments SET node_id=2 WHERE account_id=7')
            connection.execute("UPDATE account_environments SET state='stopped' WHERE name='agy:7'")
        placement = AgyPlacement.__new__(AgyPlacement)
        placement.store = self.store
        gateway = Mock()
        placement.runtime = SimpleNamespace(gateway=gateway)
        gateway.list_accounts.return_value = []
        gateway._request.return_value = {'account_id': 7, 'platform': 'antigravity', 'auth_type': 'oauth'}
        placement.reconcile_retired()
        self.assertEqual(self.store.agy_assignment(7)['phase'], 'ready')

        original, = self.store.agy_retirement_candidates()
        self.store.retire_agy_assignment({**original, 'generation': original['generation'] - 1})
        self.assertEqual(self.store.agy_assignment(7)['phase'], 'ready')

        failure = ValueError('原账号已删除')
        failure.__cause__ = HTTPError('http://fixture.invalid', 404, 'not found', None, None)
        gateway._request.side_effect = failure
        placement.reconcile_retired()
        archived = self.store.agy_assignment(7)
        self.assertEqual((archived['phase'], archived['revision'], archived['node_id']), ('retired', 1, 2))
        self.assertEqual(self.store.agy_assignments(), [])
        with self.database() as connection:
            self.store._require_removable(connection, 2)
        self.assertEqual(lookup(self.store, 7)['generation'], original['generation'])

    def test_platform_snapshot_guards_remote_ownership_in_each_update_mode(self):
        """平台换批按实际归属拦截，零角色归档和活跃迁移分别核对。@return 无。"""
        def unexpected_local_access(row):
            if row['environment_id'] == 'a' * 32:
                raise AssertionError('远程 AGY 环境不应打开本机资料')
            return True

        runtime = SimpleNamespace(database=self.database, locality=unexpected_local_access,
            environment_lock=lambda _: threading.RLock(), environment_jobs=lambda _: [],
            _execution_records=lambda _: [], _root=lambda _: self.root, gateway=Mock())
        with self.database() as connection:
            connection.execute('UPDATE agy_node_assignments SET node_id=2 WHERE account_id=7')
            connection.execute("UPDATE account_environments SET state='stopped' WHERE name='agy:7'")
        with patch('system_updates.UPDATE_GATE.state', return_value={'phase': 'blocked', 'active': 0}):
            for central, control in ((False, False), (True, False), (True, True)):
                snapshot = runtime_snapshot(runtime, central, control)
                self.assertFalse(snapshot['ready'])
                self.assertIn('请迁回本机后更新或回退平台', snapshot['agy_update_blockers'][0])
                item = next(row for row in snapshot['environments'] if row['environment_id'] == 'a' * 32)
                self.assertEqual((item['node_kind'], item['gateway_account_id']), ('ssh', 7))

            candidate, = self.store.agy_retirement_candidates()
            self.store.retire_agy_assignment(candidate)
            snapshot = runtime_snapshot(runtime, True, True)
            self.assertEqual(snapshot['agy_update_blockers'], [])
            self.assertEqual(next(row for row in snapshot['environments'] if row['environment_id'] == 'a' * 32)['blockers'], [])

            with self.database() as connection:
                connection.execute("UPDATE agy_node_assignments SET node_id=1,phase='ready' WHERE account_id=7")
            self.ledger.begin('e' * 32, 7, 2, 1)
            runtime.locality = None
            self.assertIn('请先完成或取消原 AGY 节点迁移', runtime_snapshot(runtime)['agy_update_blockers'][0])

    def test_archive_transfers_eligible_data_and_rebuilds_host_state(self):
        """归档与解包共同校验 AGY 白名单。@return 无。"""
        source = self.root / 'environment'
        allowed = ['projects/work.txt', 'runtime/cpu-resources.json',
            'flows/api/agy-prepared/ingress/snapshots/11111111-1111-4111-8111-111111111111.json']
        blocked = ['home/.agy/user_settings.json', 'runtime/sender/sender.json', 'runtime/native/agy/session',
            'runtime/native-criu/image', 'runtime/agy-capacity.json',
            'flows/api/agy-prepared/' + '1' * 32 + '/config.json']
        for path in allowed + blocked:
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(path)
        identity = AgyArchiveIdentity(platform='antigravity', operation_id='d' * 32, deployment_id='agy-test',
            source_node_key='local', account_id=7, environment_id='a' * 32, assignment_revision=1)
        files = MigrationFiles(self.root, 'local', 'agy-test')
        archive = files.export(source, identity, 'f' * 32, environment_generation=4)
        bundle = self.root / 'node-migrations' / identity.operation_id / 'exports' / (archive.attempt_id + '.tar')
        target = self.root / 'restored'
        restore_environment_archive(bundle, target, identity, archive.sha256, archive.data_bytes)
        self.assertEqual({path.relative_to(target).as_posix() for path in target.rglob('*') if path.is_file()}, set(allowed))

    def test_preflight_keeps_an_empty_target_projection_uninitialized(self):
        """目标预检只读制品和容量，首次导入初始化完整账本。@return 无。"""
        client = Mock()
        client.containers.list.return_value = []
        labels = {
            'vibebench.product': 'v3', 'vibebench.role': 'account', 'vibebench.release': 'fixture',
            'vibebench.isolation-version': '2', 'vibebench.agy-runtime-protocol': '1',
            'vibebench.agy-runtime-source-sha256': SOURCE_SHA256}
        client.images.get.return_value.attrs = {'Config': {'Labels': labels}}
        executor = SimpleNamespace(node_key='b' * 32, deployment='agy-test', data=self.root,
            local_runtime=None, client=client, _runtime=Mock(side_effect=AssertionError('预检提前创建投影')))
        row = lookup(self.store, 7)
        row['fingerprint_json'] = json.dumps({'mem': 'unlimited', 'swap': '0'})
        scope = {'node_key': executor.node_key, 'account_id': 7, 'environment_id': row['environment_id'],
            'assignment_revision': 2, 'generation': row['generation'], 'environment': row,
            'configuration': {'account_id': 7, 'platform': 'antigravity', 'auth_type': 'oauth',
                'status': 'active', 'credential_state': {'phase': 'ready'}, 'concurrency': 3,
                'proxy_url': 'socks5://proxy.example.test:1080'}}
        with patch.dict(os.environ, {'V3_ACCOUNT_IMAGE': 'fixture', 'V3_ACCOUNT_RELEASE': 'fixture',
                'V3_RELEASE': 'fixture', 'V3_MAX_ACTIVE_ACCOUNTS': '1'}):
            node = AgyNode(executor)
            self.assertEqual(node.call('agy-preflight', scope)['phase'], 'compatible')
            labels['vibebench.release'] = 'other-release'
            with self.assertRaisesRegex(ValueError, '镜像批次或能力不一致'):
                node.call('agy-preflight', scope)
            labels['vibebench.release'] = 'fixture'
            client.containers.list.return_value = [SimpleNamespace(labels={
                'vibebench.environment': 'c' * 32, 'vibebench.role': 'account',
                'vibebench.cluster-node': executor.node_key})]
            with self.assertRaisesRegex(ValueError, '无空余环境容量'):
                node.call('agy-preflight', scope)
        executor._runtime.assert_not_called()
        self.assertEqual(self.store.agy_assignment(7)['phase'], 'ready')
