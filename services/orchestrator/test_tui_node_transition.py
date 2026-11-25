"""核对节点独立提供方和休眠账号的可信更新回执。"""
from contextlib import closing
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from threading import Lock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from account_isolation import tui_node_provider
from cluster_service import ClusterService
from cluster_store import ClusterStore
from cluster_transport import NodeTransports
from database_migrations import apply_migrations
from runtime_files import atomic_json
from runtime_names import account_container_prefix
from system_update_host import HostDeployment
from system_update_rollout import read_rollout
from tui_node_source import inspect_tui_node_source


class TuiNodeTransitionTests(unittest.TestCase):
    """以私有配置文件和真实归属数据库覆盖节点更新的比较边界。"""

    def test_stopped_sender_keeps_source_proof_without_background_start(self) -> None:
        """休眠项只授权首轮换代，错误镜像及网关账号无法生成有效前驱。@return 无。"""
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'V3_UPDATE_GATE_DIR': directory}):
            root = Path(directory)
            old_release, target_release = 'ci-100-1', 'ci-101-1'
            environment = 'a' * 32

            def selection(release):
                return {'control': {'release': release}, 'account': {'release': release,
                    'reference': 'ghcr.io/silentflower/flower2api-account:v3-' + release}}

            old = selection(old_release)
            target = selection(target_release)
            old_id, new_id = 'sha256:' + '1' * 64, 'sha256:' + '2' * 64
            host = object.__new__(HostDeployment)
            host.gate = root
            host.policy = {'deployment': 'test'}
            host.verify_images = lambda chosen: {'account': {'Id': old_id if chosen == old else new_id}}
            original = {'image_id': old_id, 'release': old_release, 'environment_id': environment,
                'protocol': 1, 'reference': old['account']['reference']}
            dormant = {'account_id': 1, 'gateway_account_id': 17, 'environment_id': environment,
                'generation': 2, 'state': 'stopped', 'roles': {}, 'origin': original}
            operation = {'operation_id': 'operation', 'epoch': 'epoch', 'original': {'selection': old},
                'before': {'environments': [dormant, {**dormant, 'environment_id': 'b' * 32}]}}
            self.assertEqual({}, host.stage_local_rollout(operation, {'selection': target}))
            record = read_rollout(root, 'test', target_release, target_release)
            self.assertEqual({}, record['environments'])
            self.assertEqual({environment}, set(record['stopped_environments']))

            def database():
                connection = sqlite3.connect(root / 'test.db')
                connection.row_factory = sqlite3.Row
                return connection

            with closing(database()) as connection:
                apply_migrations(connection)
                with connection:
                    connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(1,'synthetic','profiles/synthetic')")
            service = object.__new__(ClusterService)
            service.store = ClusterStore(database, Lock())
            runtime = SimpleNamespace(deployment='test', release_id=target_release)
            binding = {'environment_id': environment, 'generation': 3, 'release_id': target_release}
            account = {'id': 1, 'cc2api_account_id': 17}
            proof = service.tui_transport_predecessors(account, runtime, binding)
            self.assertEqual(2, len(proof))
            self.assertEqual({(17, 2, old_release)}, {(p['account_id'], p['generation'], p['release_id']) for p in proof})
            self.assertEqual([], service.tui_transport_predecessors({**account, 'cc2api_account_id': 18}, runtime, binding))
            self.assertEqual([], service.tui_transport_predecessors(account, runtime, {**binding, 'generation': 2}))

            # 全量回退重建后的回执只授权旧键推进；后台旧实例继续运行的授权列表保持为空。
            roles = {role: {'id': role, 'state': 'running', 'image_id': old_id} for role in ('cli', 'network', 'sender')}
            running = {**dormant, 'state': 'ready', 'roles': roles}
            operation['before']['environments'] = [running]
            rebuilt = {**running, 'generation': 3, 'origin': {**original, 'release': target_release, 'image_id': new_id}}
            self.assertEqual({}, host.stage_local_rollout(operation, {'selection': target}, rebuilt=[rebuilt]))
            record = read_rollout(root, 'test', target_release, target_release)
            self.assertEqual({}, record['environments'])
            self.assertEqual({environment}, set(record['rebuilt_environments']))
            self.assertEqual(proof, service.tui_transport_predecessors(account, runtime, binding))
            host.stage_local_rollout(operation, {'selection': target}, rebuilt=[{**rebuilt, 'generation': 2}])
            self.assertEqual([], service.tui_transport_predecessors(account, runtime, binding))

    @unittest.skipUnless(os.geteuid() == 0, '节点私有提供方检查使用实际 root 归属')
    def test_target_provider_keeps_loopback_and_path_ownership(self) -> None:
        """目标私有提供方只接纳固定环境及回环地址。@return 无。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / 'tui-local-providers'
            vault.mkdir(mode=0o700)
            environment = 'a' * 32
            config = vault / (environment + '.json')
            allowed = {'base_url': 'http://127.0.0.1:18193', 'local_bearer': 'synthetic'}
            atomic_json(config, allowed)
            self.assertEqual(allowed, tui_node_provider(root, environment))
            self.assertIsNone(tui_node_provider(root, 'b' * 32))
            for address in ('https://127.0.0.1:18193', 'http://192.0.2.1:18193', 'http://127.0.0.1:18193/extra'):
                atomic_json(config, {**allowed, 'base_url': address})
                with self.subTest(address=address), self.assertRaises(ValueError):
                    tui_node_provider(root, environment)
            config.chmod(0o644)
            with self.assertRaisesRegex(ValueError, '归属'):
                tui_node_provider(root, environment)

    def test_remote_upgrade_journal_requires_fixed_node_revision_and_release(self) -> None:
        """远端旧绑定只从同一 SSH 分配的已完成维护导出。@return 无。"""
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            environment, node_key = 'a' * 32, 'b' * 32
            node = {'config_json': '{}'}
            assignment = {'phase': 'ready', 'enabled': True, 'kind': 'ssh',
                'node_id': 2, 'node_key': node_key, 'revision': 4}
            service = object.__new__(ClusterService)
            service.store = SimpleNamespace(database=lambda: sqlite3.connect(private / 'test.db'),
                assignment=lambda _: assignment, get=lambda _: node)
            service.connection = lambda _: SimpleNamespace(private=private)
            with closing(service.store.database()) as connection, connection:
                connection.execute('CREATE TABLE node_migrations (account_id,phase,updated_at,operation_id)')
            runtime = SimpleNamespace(deployment='synthetic', release_id='ci-101-1')
            account = {'id': 1, 'cc2api_account_id': 17}
            binding = {'environment_id': environment, 'generation': 9, 'release_id': 'ci-101-1'}
            journal = {'phase': 'completed', 'node_id': 2, 'node_key': node_key,
                'config_sha256': sha256(node['config_json'].encode()).hexdigest(),
                'target_account_release': 'ci-101-1', 'old_account_release': 'ci-100-1',
                'accounts': [{'account': account}],
                'fences': {'1': {'environment_id': environment, 'assignment_revision': 4, 'generation': 8}}}
            path = private / 'maintenance/current.json'
            atomic_json(path, journal)
            [proof] = service.tui_transport_predecessors(account, runtime, binding)
            self.assertTrue(proof['endpoint'].endswith(f'/{node_key}/{environment}/4'))
            self.assertEqual((17, 8, 'ci-100-1'), (proof['account_id'], proof['generation'], proof['release_id']))
            for change in ({'node_id': 3}, {'phase': 'restoring'}, {'config_sha256': 'different'},
                           {'target_account_release': 'ci-102-1'}, {'fences': {'1': {'environment_id': environment,
                            'assignment_revision': 3, 'generation': 8}}}):
                atomic_json(path, {**journal, **change})
                with self.subTest(change=change):
                    self.assertEqual([], service.tui_transport_predecessors(account, runtime, binding))

            # 真实旧同步日志只有控制镜像版本。账号版本必须取自同一节点安装回执。
            legacy = {k: v for k, v in journal.items() if k != 'target_account_release'}
            legacy.update(target_release='ci-102-1', revision=7)
            runtime.release_id = legacy['target_release']
            runtime.account_release_id = binding['release_id']
            prepared = {'state': 'prepared', 'node_id': 2, 'node_key': node_key, 'revision': 7,
                        'release': legacy['target_release'], 'account_release': binding['release_id']}
            node.update(revision=7, preparation_json=json.dumps(prepared))
            with patch.dict(os.environ, {'V3_UPDATE_GATE_DIR': str(private)}):
                atomic_json(path, legacy)
                self.assertEqual([proof], service.tui_transport_predecessors(account, runtime, binding))
                for change in ({'state': 'preparing'}, {'node_key': 'c' * 32}, {'node_id': 9}, {'revision': 8},
                               {'release': 'ci-103-1'}, {'account_release': 'ci-104-1'}, {'account_release': None}):
                    node['preparation_json'] = json.dumps({**prepared, **change})
                    with self.subTest(preparation=change):
                        self.assertEqual([], service.tui_transport_predecessors(account, runtime, binding))
                node['preparation_json'] = json.dumps(prepared)
                for change in ({'revision': 8}, {'target_account_release': ''}, {'target_account_release': 'ci-104-1'}):
                    atomic_json(path, {**legacy, **change})
                    with self.subTest(journal=change):
                        self.assertEqual([], service.tui_transport_predecessors(account, runtime, binding))

    def test_readonly_original_remote_binding_survives_control_upgrade(self) -> None:
        """旧远端只对原轮查询开放，常规查询与后续代次保持原校验。@return 无。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment, node_key = 'a' * 32, 'b' * 32
            release, target = 'ci-100-1', 'ci-101-1'
            assignment = {'phase': 'ready', 'enabled': True, 'kind': 'ssh',
                'node_id': 2, 'node_key': node_key, 'revision': 4}

            def database():
                connection = sqlite3.connect(root / 'test.db')
                connection.row_factory = sqlite3.Row
                return connection

            with closing(database()) as connection, connection:
                connection.execute('CREATE TABLE account_environments (account_id,environment_id,generation,state)')
                connection.execute('INSERT INTO account_environments VALUES (1,?,9,?)', (environment, 'ready'))
            store = SimpleNamespace(database=database, assignment=lambda _: assignment, lock=Lock())
            service = object.__new__(ClusterService)
            service.store = store
            service.transports = NodeTransports(store)
            binding = {'account_id': 17, 'environment_id': environment, 'generation': 9,
                'release_id': release, 'secret': 'synthetic-original-sender-secret-0123456789'}
            node = SimpleNamespace(prepare_environment=Mock(return_value={'binding': binding, 'protocol': 1,
                'node_key': node_key, 'assignment_revision': 4, 'sender_address': '127.0.0.1'}),
                sender_socket=Mock(return_value=root / 'sender.sock'))
            service.connection = lambda _: node
            runtime = SimpleNamespace(deployment='synthetic', release_id=target)
            account = {'id': 1, 'cc2api_account_id': 17}
            with self.assertRaisesRegex(ValueError, '没有通过'):
                service.existing_remote_transport(account, runtime)
            result = service.existing_remote_transport(account, runtime, allow_previous_release=True)
            self.assertEqual(binding, {key: result[key] for key in binding})
            self.assertTrue(result['endpoint'].endswith(f'/{node_key}/{environment}/4'))
            node.sender_socket.assert_called_once_with(environment, '127.0.0.1')
            with self.assertRaisesRegex(ValueError, '仍在原发行'):
                service.existing_remote_transport(account, runtime)
            assignment['revision'] = 5
            with self.assertRaisesRegex(ValueError, '归属不一致'):
                service.existing_remote_transport(account, runtime, allow_previous_release=True)

    def test_formal_preflight_requires_only_installation_and_verifies_actual_sender_after_preparation(self) -> None:
        """空目标预检只看安装能力，准备后逐项验证同操作 sender。@return 无。"""
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            environment = 'a' * 32
            scope = {'action': 'target', 'mode': 'formal', 'account_id': 1, 'gateway_account_id': 17,
                'environment_id': environment, 'generation': 2, 'release_id': 'ci-101-1', 'node_key': 'local',
                'deployment': 'test', 'operation_id': 'b' * 32, 'target_revision': 4}
            image = SimpleNamespace(attrs={'Config': {'Labels': {'vibebench.tui-sender-protocol': '1',
                'vibebench.tui-session-host': '1', 'vibebench.release': 'ci-101-1'}}})
            client = SimpleNamespace(images=SimpleNamespace(get=lambda _: image))
            root = data / 'environments' / environment
            marker = root / 'runtime/node-migration-target.json'
            document = root / 'runtime/sender/sender.json'
            staged = {key: scope[key] for key in ('operation_id', 'node_key', 'environment_id', 'account_id')}
            staged.update(revision=4, phase='prepared', generation=3)
            endpoint = 'http://' + account_container_prefix('test') + environment + ':8091'
            secret = 'synthetic-sender-secret-' * 2
            config = {'tui_v2': {'max_reservations': 2}, 'binding': {'account_id': 17,
                'environment_id': environment, 'generation': 3, 'release_id': 'ci-101-1',
                'endpoint': endpoint, 'secret': secret}}
            status = {'environment_id': environment, 'generation': 3, 'active': 0, 'tui_v2': {'protocol': 1,
                'account_id': 17, 'release_id': 'ci-101-1', 'event_source': 'local_unix', 'ready': True, 'idle': True}}
            response = Mock(side_effect=lambda *_a, **_kw: BytesIO(json.dumps(status).encode()))
            with patch('account_isolation.tui_node_provider', side_effect=AssertionError('正式模式不可读本机配置')), \
                    patch('tui_node_source.build_opener', return_value=SimpleNamespace(open=response)):
                self.assertEqual({'supported': True}, inspect_tui_node_source(data, client, 'image', scope))
                self.assertEqual({'supported': False}, inspect_tui_node_source(data, client, 'image',
                    {**scope, 'release_id': 'ci-102-1'}))
                self.assertFalse(root.exists())
                response.assert_not_called()
                prepared = {**scope, 'action': 'prepared', 'generation': 3}
                with self.assertRaises(FileNotFoundError):
                    inspect_tui_node_source(data, client, 'image', prepared)
                atomic_json(marker, staged)
                atomic_json(document, config)
                self.assertEqual({'ready': True}, inspect_tui_node_source(data, client, 'image', prepared))
                outbound = response.call_args.args[0]
                self.assertEqual(endpoint + '/internal/status', outbound.full_url)
                self.assertEqual('GET', outbound.get_method())
                self.assertEqual('Bearer ' + secret, outbound.get_header('Authorization'))
                self.assertIsNone(outbound.data)
                status['tui_v2']['account_id'] = 18
                self.assertEqual({'ready': False}, inspect_tui_node_source(data, client, 'image', prepared))
                status['tui_v2']['account_id'] = 17
                status['generation'] = 2
                self.assertEqual({'ready': False}, inspect_tui_node_source(data, client, 'image', prepared))
                status['generation'] = 3
                status['tui_v2']['release_id'] = 'ci-102-1'
                self.assertEqual({'ready': False}, inspect_tui_node_source(data, client, 'image', prepared))
                status['tui_v2']['release_id'] = 'ci-101-1'
                status['active'] = 1
                self.assertEqual({'ready': False}, inspect_tui_node_source(data, client, 'image', prepared))
                status['active'] = 0
                atomic_json(marker, {**staged, 'operation_id': 'c' * 32})
                self.assertEqual({'ready': False}, inspect_tui_node_source(data, client, 'image', prepared))
                self.assertEqual({'mode': 'formal'}, inspect_tui_node_source(data, client, 'image',
                    {**scope, 'action': 'source', 'generation': 3}))
                atomic_json(marker, staged)
                self.assertEqual({'ready': True}, inspect_tui_node_source(data, client, 'image', prepared))

    @unittest.skipUnless(os.geteuid() == 0, '本机模式检查用实际 root 归属')
    def test_managed_source_requires_target_provider_only_in_local_mode(self) -> None:
        """内置本机源按实际发送器配置分类，只在此模式检查目标本机配置。@return 无。"""
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            environment = 'a' * 32
            binding = {'account_id': 17, 'environment_id': environment, 'generation': 2, 'release_id': 'ci-101-1'}
            scope = {**binding, 'action': 'source', 'node_key': 'local', 'gateway_account_id': 17}
            atomic_json(data / 'environments' / environment / 'runtime/sender/sender.json',
                {'tui_v2': {'max_reservations': 2}, 'tui_host_memory': '1g', 'binding': binding})
            image = SimpleNamespace(attrs={'Config': {'Labels': {'vibebench.tui-sender-protocol': '1',
                'vibebench.tui-session-host': '1', 'vibebench.release': 'ci-101-1'}}})
            client = SimpleNamespace(images=SimpleNamespace(get=lambda _: image))
            self.assertEqual({'mode': 'local_provider'}, inspect_tui_node_source(data, client, 'image', scope))
            target = {**scope, 'action': 'target', 'mode': 'local_provider'}
            self.assertEqual({'supported': False}, inspect_tui_node_source(data, client, 'image', target))
            vault = data / 'tui-local-providers'
            vault.mkdir(mode=0o700)
            atomic_json(vault / (environment + '.json'), {'base_url': 'http://127.0.0.1:18193', 'local_bearer': 'synthetic'})
            self.assertEqual({'supported': True}, inspect_tui_node_source(data, client, 'image', target))
            self.assertEqual({'supported': True}, inspect_tui_node_source(data, client, 'image', {**target, 'mode': 'formal'}))
