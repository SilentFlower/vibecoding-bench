"""实际 SQLite 元数据与软件字段恢复的边界验证。"""
import copy
import json
import sqlite3
import tempfile
import unittest
import uuid
import gc
import io
from contextlib import closing
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import Mock, patch

from system_update_host import HostDeployment
from runtime_files import atomic_json, atomic_text
from system_update_gate import read_gate
from system_update_database import assert_quiescent, create_snapshot, restore_snapshot
from runtime_names import account_container_prefix


class HostNetworkNamesTests(unittest.TestCase):
    """宿主控制连接在单部署迁移前后使用真实受控网络。"""

    def test_capture_retries_blocked_partial_snapshot_before_freezing_role_sources(self) -> None:
        """只读竞争后的完整证明才进入冻结记录，持续未知时拒绝冻结。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host = HostDeployment({'state_root': str(root), 'data_root': str(root / 'data'),
                'env_file': str(root / 'v3.env'), 'deployment': 'test'})
            atomic_text(host.env, 'synthetic=1\n')
            controls = {role: {'Id': role, 'Image': 'trusted-image'} for role in ('gateway', 'orchestrator')}
            partial = {'phase': 'blocked', 'ready': False, 'environments': [{'environment_id': 'synthetic'}]}
            complete = {'phase': 'blocked', 'ready': True, 'environments': [{'environment_id': 'synthetic',
                'roles': {'network': {'image_id': 'original-image'}}}]}
            current = {'selection': {'control': {'config_digest': 'trusted-image'}}}
            with patch.object(host, 'values'), patch.object(host, 'controls', return_value=controls), \
                    patch.object(host, 'verify_images', return_value={'control': {'Id': 'trusted-image'}}), \
                    patch('system_update_host._container_image_matches', return_value=True), \
                    patch.object(host, 'metadata', return_value={'protected': True}) as metadata, \
                    patch.object(host, 'request', side_effect=[partial, complete]) as request, \
                    patch('system_update_host.time.sleep'):
                frozen = host.capture(current)
                self.assertEqual(frozen['environments'][0]['roles']['network']['image_id'], 'original-image')
                self.assertEqual(request.call_count, 2)
                metadata.assert_called_once()
            with patch.object(host, 'values'), patch.object(host, 'controls', return_value=controls), \
                    patch.object(host, 'verify_images', return_value={'control': {'Id': 'trusted-image'}}), \
                    patch('system_update_host._container_image_matches', return_value=True), \
                    patch.object(host, 'metadata') as metadata, patch.object(host, 'request', return_value=partial), \
                    patch('system_update_host.time.monotonic', side_effect=[0, 6]):
                with self.assertRaisesRegex(ValueError, '冻结快照'):
                    host.capture(current)
                metadata.assert_not_called()

    def test_environment_retry_only_replays_pre_action_quiescence_conflicts(self) -> None:
        """仅两种前置排空冲突可沿原请求重试，代次冲突与提交未知直接上抛。@return None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        body = {'generation': 7, 'operation_id': 'synthetic-operation'}
        for message in ('平台在途工作尚未排空', '其他环境仍有在途工作或未知证据', '环境身份或代次已经变化'):
            error = HTTPError('http://synthetic.invalid', 409, 'conflict', {},
                io.BytesIO(json.dumps({'detail': message}).encode()))
            with self.subTest(message=message), patch.object(host, 'request', side_effect=[error, {'state': 'ready'}]) as request, \
                    patch('system_update_host.time.sleep'):
                if message == '环境身份或代次已经变化':
                    with self.assertRaises(HTTPError):
                        host._environment_request(body)
                    self.assertEqual(request.call_count, 1)
                else:
                    self.assertEqual(host._environment_request(body), {'state': 'ready'})
                    self.assertEqual(request.call_count, 2)
                    self.assertTrue(all(call.args[2] is body for call in request.call_args_list))
        with patch.object(host, 'request', side_effect=TimeoutError('合成提交未知')) as request:
            with self.assertRaises(TimeoutError):
                host._environment_request(body)
            self.assertEqual(request.call_count, 1)

    def test_settled_requires_fresh_ready_proof_and_preserves_persistent_blocker(self) -> None:
        """短暂读取竞争后重验，持续阻塞到期限仍返回原阻塞证明。@return None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        blocked, ready = {'ready': False, 'blockers': ['合成占锁']}, {'ready': True, 'blockers': []}
        with patch.object(host, 'drained', side_effect=[blocked, ready]), patch('system_update_host.time.sleep'):
            self.assertIs(host._settled({}), ready)
        with patch.object(host, 'drained', return_value=blocked), patch('system_update_host.time.monotonic', side_effect=[0, 6]):
            self.assertIs(host._settled({}), blocked)

    def test_failed_new_package_recovery_retires_only_persisted_environment_intents(self) -> None:
        """失败恢复先由候选程序收口已登记环境，完成回执阻止重复重建。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host = HostDeployment({'state_root': str(root), 'data_root': str(root / 'data'),
                'env_file': str(root / 'v3.env'), 'deployment': 'test'})
            operation = {'operation_id': 'synthetic-operation', 'epoch': 'synthetic-epoch',
                'original': {'selection': {'account': {'release': 'ci-1-1',
                    'reference': 'ghcr.io/silentflower/vibebench-v3-account:v3-ci-1-1'}}},
                'selected': {'selection': {'account': {'release': 'ci-2-1',
                    'reference': 'ghcr.io/silentflower/flower2api-account:v3-ci-2-1'}}},
                'environment_intents': {'synthetic': {'generation': 7, 'allowed_image_ids': ['old-image', 'new-image']}}}
            atomic_text(root / 'operations/synthetic-operation/candidate.env', 'synthetic=1\n')
            evidence = {'environments': [{'environment_id': 'synthetic', 'generation': 8},
                {'environment_id': 'unrelated', 'generation': 10}]}
            with patch.object(host, '_stop_controls'), patch.object(host, '_retire_legacy_controls'), \
                    patch.object(host, '_compose'), patch.object(host, '_connect_legacy_environments'), \
                    patch.object(host, 'wait_controls'), patch.object(host, 'request',
                        side_effect=[evidence, {'state': 'stopped'}]) as request:
                save = Mock()
                host._retire_restore_environments(operation, save)
                self.assertEqual(request.call_count, 2)
                body = request.call_args.args[2]
                self.assertEqual(body['action'], 'retire')
                self.assertEqual(body['environment_id'], 'synthetic')
                self.assertEqual(body['allowed_image_ids'], ['old-image', 'new-image'])
                self.assertIn('synthetic', operation['environment_restore_retired'])
                save.assert_called_once()
                host._retire_restore_environments(operation, save)
                self.assertEqual(request.call_count, 2)
                self.assertEqual(host.env.read_text(), 'synthetic=1\n')

    def test_historical_retirement_persists_proof_before_owner_removes_roles(self) -> None:
        """新到旧回退先持久意图，再由原所有者收口；重复及在途分别受控。@return None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        selected = {'selection': {'account': {'release': 'ci-1-1',
            'reference': 'ghcr.io/silentflower/vibebench-v3-account:v3-ci-1-1'}}}
        environment = {'environment_id': 'synthetic', 'generation': 7,
            'roles': {role: {'state': 'running', 'image_id': 'new-image'} for role in ('cli', 'sender', 'network')}}
        operation = {'operation_id': 'synthetic-operation', 'epoch': 'synthetic-epoch',
            'original': {'selection': {'account': {'release': 'ci-2-1',
                'reference': 'ghcr.io/silentflower/flower2api-account:v3-ci-2-1'}}},
            'before': {'environments': [environment]}}
        evidence = {'ready': True, 'environments': [environment]}
        saved = []

        def save():
            """记录每次持久意图。@return None。"""
            saved.append(copy.deepcopy(operation))

        def retire(service, path, body, timeout):
            """验证副作用之前已经登记来源及资源。:param service: 服务。:param path: 路径。:param body: 维护请求。:param timeout: 秒。@return 收口回执。"""
            self.assertEqual(body['action'], 'retire')
            self.assertEqual(saved[-1]['environment_intents']['synthetic']['generation'], 7)
            self.assertEqual(set(saved[-1]['environment_intents']['synthetic']['allowed_image_ids']), {'old-image', 'new-image'})
            self.assertEqual(saved[-1]['environment_cpu_before']['synthetic']['cli'], 1500000000)
            return {'state': 'stopped', 'generation': 7}

        with patch.object(host, 'drained', return_value=evidence), \
                patch.object(host, 'environment_cpu', return_value={'cli': 1500000000, 'sender': 1000000000, 'network': 500000000}), \
                patch.object(host, 'verify_images', return_value={'account': {'Id': 'old-image'}}), \
                patch.object(host, 'request', side_effect=retire) as request:
            host._retire_rollback_environments(operation, selected, save)
            self.assertEqual(len(saved), 2)
            self.assertIn('synthetic', operation['environment_retired'])
            host._retire_rollback_environments(operation, selected, save)
            self.assertEqual(request.call_count, 1)
            operation.pop('environment_retired')
            evidence['ready'] = False
            with self.assertRaisesRegex(ValueError, '在途'):
                host._retire_rollback_environments(operation, selected, save)
            self.assertEqual(request.call_count, 1)

    def test_old_and_new_networks_and_ambiguous_rejection(self) -> None:
        """分别接纳新旧网络，缺失或同时存在时拒绝发送。@return None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        for names in [('vibebench-v3-test',), ('flower2api-test',), (), ('vibebench-v3-test', 'flower2api-test')]:
            controls = {'orchestrator': {'NetworkSettings': {'Networks': {name: {'IPAddress': '10.0.0.2'} for name in names}}}}
            host.opener = Mock()
            host.opener.open.return_value = io.BytesIO(b'{}')
            with self.subTest(networks=names), patch.object(host, 'values', return_value={'V3_INTERNAL_TOKEN': 'synthetic'}), \
                    patch.object(host, 'controls', return_value=controls), patch('system_update_host.safe_read', return_value=b'synthetic'):
                if len(names) == 1:
                    self.assertEqual(host.request('orchestrator', '/health'), {})
                    self.assertEqual(host.opener.open.call_args.args[0].full_url, 'http://10.0.0.2:8000/health')
                else:
                    with self.assertRaisesRegex(ValueError, '网络'):
                        host.request('orchestrator', '/health')
                    host.opener.open.assert_not_called()

    def test_project_retirement_requires_frozen_stopped_controls(self) -> None:
        """改名只移除本操作的原控制角色；外来来源和运行状态拒绝删除。@return None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        gate = {'phase': 'blocked', 'epoch': 'synthetic-epoch', 'operation_id': 'synthetic-operation'}
        operation = {'epoch': gate['epoch'], 'operation_id': gate['operation_id'],
            'before': {'controls': {'gateway': {'id': 'original', 'image_id': 'old-image'}}}}
        original = {'Id': 'original', 'Image': 'old-image', 'State': {'Running': False},
            'Config': {'Labels': {'com.docker.compose.project': 'vibebench-v3-test'}}}
        for item, valid in [(original, True), ({**original, 'Id': 'foreign'}, False),
                ({**original, 'State': {'Running': True}}, False),
                ({**original, 'Config': {'Labels': {'com.docker.compose.project': 'other'}}}, False)]:
            with self.subTest(item=item), patch.object(host, 'controls', return_value={'gateway': item}), \
                    patch('system_update_host.read_gate', return_value=gate), patch('system_update_host.docker') as docker:
                if valid:
                    host._retire_legacy_controls(operation)
                    docker.assert_called_once_with('rm', 'original')
                else:
                    with self.assertRaises(ValueError):
                        host._retire_legacy_controls(operation)
                    docker.assert_not_called()

    def test_network_handoff_requires_registered_owned_role(self) -> None:
        """真实数据库登记绑定原网络角色，保留旧别名并拒绝未知来源。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'bench').mkdir()
            environment = 'a' * 32
            with sqlite3.connect(root / 'bench/db.sqlite') as db:
                db.execute('CREATE TABLE account_environments(environment_id TEXT,network_container_id TEXT)')
                db.execute('INSERT INTO account_environments VALUES(?,?)', (environment, 'original-network'))
            host = HostDeployment({'state_root': str(root / 'updates'), 'data_root': str(root),
                'env_file': str(root / 'v3.env'), 'deployment': 'test'})
            labels = {'vibebench.product': 'v3', 'vibebench.deployment': 'test',
                'vibebench.environment': environment, 'vibebench.role': 'account-network'}
            item = {'Id': 'original-network', 'Image': 'old-image', 'Config': {'Labels': labels},
                'State': {'Running': True},
                'Name': '/' + account_container_prefix('test', legacy=True) + environment,
                'NetworkSettings': {'Networks': {'vibebench-v3-test': {'IPAddress': '10.0.0.2'}}}}
            operation = {'before': {'environments': [{'environment_id': environment,
                'roles': {'network': {'image_id': 'old-image'}}}]}, 'selected': {'selection': {}}}
            controls = {role: {'State': {'Running': True}, 'NetworkSettings': {'Networks': {
                'flower2api-test': {'IPAddress': address}}}} for role, address in
                (('gateway', '10.1.0.2'), ('orchestrator', '10.1.0.3'))}
            for mode in ('running', 'foreign', 'stopped', 'connected'):
                observed = copy.deepcopy(item)
                if mode == 'foreign':
                    observed['Config']['Labels']['vibebench.environment'] = 'b' * 32
                elif mode == 'stopped':
                    observed['State']['Running'] = False
                elif mode == 'connected':
                    observed['NetworkSettings']['Networks']['flower2api-test'] = {'IPAddress': '10.1.0.2'}
                with self.subTest(mode=mode), patch.object(host, 'verify_images', return_value={'account': {'Id': 'new-image'}}), \
                        patch.object(host, 'controls', return_value=controls), \
                        patch('system_update_host.docker', side_effect=[json.dumps([{'Labels': labels,
                            'IPAM': {'Config': [{'Gateway': '10.1.0.1'}]}}]),
                            'original-network', json.dumps([observed]), '', '']) as docker:
                    if mode == 'foreign':
                        with self.assertRaisesRegex(ValueError, '来源或名称'):
                            host._connect_legacy_environments(operation)
                        self.assertEqual(docker.call_count, 3)
                    elif mode == 'stopped':
                        host._connect_legacy_environments(operation)
                        self.assertEqual(docker.call_count, 3)
                    else:
                        host._connect_legacy_environments(operation)
                        if mode == 'running':
                            self.assertEqual(docker.call_args_list[-2].args, ('network', 'connect', '--gw-priority=-1', '--alias',
                                item['Name'].lstrip('/'), 'flower2api-test', 'original-network'))
                        else:
                            self.assertEqual(docker.call_count, 4)
                        self.assertEqual(docker.call_args.args, ('exec', '--env',
                            'V3_MANAGEMENT_ADDRESSES=["10.1.0.1", "10.1.0.2", "10.1.0.3"]',
                            'original-network', 'python3', '/usr/local/bin/v3-network-guard'))


class HostMetadataTests(unittest.TestCase):
    """核对软件字段、账号身份及结构证据的真实持久效果。"""

    def setUp(self) -> None:
        """建立独立双库和合成画像。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ('bench', 'gateway'):
            (self.root / name).mkdir()
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('CREATE TABLE account_environments(environment_id TEXT,name TEXT,account_id INTEGER,fingerprint_json TEXT)')
            database.execute('INSERT INTO account_environments VALUES(?,?,?,?)', ('synthetic', 'synthetic', 1, '{"memory":"1536m","device":"synthetic"}'))
            database.execute('CREATE TABLE accounts(id INTEGER,name TEXT,profile_path TEXT,cc2api_account_id INTEGER)')
            database.execute('INSERT INTO accounts VALUES(1,"synthetic","profiles/synthetic",1)')
            for name in ('account_credential_ownerships', 'local_credential_authorizations'):
                database.execute('CREATE TABLE ' + name + '(account_id INTEGER,record_json TEXT)')
        self.environment = {'version': 'old', 'node_version': 'old-node', 'device_id': 'synthetic-private-device',
            'unknown': {'keep': True}, 'timezone': 'Asia/Tokyo'}
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            database.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY,canonical_env TEXT,email TEXT,device_id TEXT,account_uuid TEXT,organization_uuid TEXT)')
            database.execute('CREATE TABLE oauth_account_ownerships(account_id INTEGER,record_json TEXT)')
            database.execute('INSERT INTO accounts(id,canonical_env) VALUES(?,?)', (1, json.dumps(self.environment)))
        self.host = HostDeployment({'state_root': str(self.root / 'updates'), 'data_root': str(self.root),
            'env_file': str(self.root / 'v3.env')})

    def change(self, value: dict) -> None:
        """更新合成画像。:param value: 新值。@return None。"""
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            database.execute('UPDATE accounts SET canonical_env=? WHERE id=1', (json.dumps(value),))

    def test_software_compensation_preserves_identity_unknown_and_absent_fields(self) -> None:
        """仅补偿声明的四个字段，缺失和存在 null 保持区别。@return None。"""
        before = self.host.metadata()
        value = {**self.environment, 'version': 'new', 'version_base': None, 'build_time': 'new-time'}
        self.change(value)
        after = self.host.metadata()
        self.assertEqual(before['identity_sha256'], after['identity_sha256'])
        self.host.restore_software(before['software'], after['software'])
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            restored = json.loads(database.execute('SELECT canonical_env FROM accounts').fetchone()[0])
        self.assertEqual(restored, self.environment)
        self.assertEqual(self.host.metadata(), before)

    def test_software_conflict_rolls_back_transaction(self) -> None:
        """迟到的软件恢复遇到并发变化时事务保持原数据。@return None。"""
        before = self.host.metadata()
        self.change({**self.environment, 'version': 'observed'})
        observed = self.host.metadata()
        self.change({**self.environment, 'version': 'concurrent'})
        with self.assertRaisesRegex(ValueError, '并发变化'):
            self.host.restore_software(before['software'], observed['software'])
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            self.assertEqual(json.loads(database.execute('SELECT canonical_env FROM accounts').fetchone()[0])['version'], 'concurrent')

    def test_identity_and_schema_changes_are_visible(self) -> None:
        """设备、资源和数据库结构变化均能被独立证据识别。@return None。"""
        before = self.host.metadata()
        changed = copy.deepcopy(self.environment)
        changed['device_id'] = 'different'
        self.change(changed)
        self.assertNotEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])
        self.change(self.environment)
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('ALTER TABLE account_environments ADD COLUMN changed TEXT')
        after = self.host.metadata()
        self.assertEqual(after['identity_sha256'], before['identity_sha256'])
        self.assertNotEqual(after['database_schema']['bench'], before['database_schema']['bench'])

    def test_metadata_closes_database_descriptors_before_snapshot(self) -> None:
        """元数据读取结束后释放持库句柄，明确识别仍在运行的读取者。@return None。"""
        gc.collect()
        self.host.metadata()
        assert_quiescent(self.root)
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database:
            database.execute('SELECT * FROM accounts').fetchall()
            with self.assertRaisesRegex(ValueError, '仍有本机进程'):
                assert_quiescent(self.root)
        assert_quiescent(self.root)

    def test_snapshot_restore_retains_registered_role_recovery_and_generation(self) -> None:
        """双库恢复后保留候选角色收口登记，事务回执中断可幂等续接。@return None。"""
        gc.collect()
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database, database:
            for name, kind in [('generation', 'INTEGER DEFAULT 4'), ('container_id', 'TEXT'),
                    ('network_container_id', 'TEXT'), ('sender_container_id', 'TEXT'),
                    ('state', "TEXT DEFAULT 'ready'"), ('isolation_version', 'INTEGER DEFAULT 2')]:
                database.execute('ALTER TABLE account_environments ADD COLUMN ' + name + ' ' + kind)
        operation = {'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()),
            'original': {'release': {'release': 'system-ci-1-1'}}, 'environment_intents': {'synthetic': {'generation': 4}}}
        folder = self.root / 'snapshot'
        create_snapshot(self.root, folder, 'test', operation)
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database, database:
            database.execute("UPDATE account_environments SET generation=5,container_id='candidate-cli',network_container_id='candidate-network',sender_container_id='candidate-sender'")
        self.host.capture_restore_bindings(operation, folder, lambda: None)
        restore_snapshot(self.root, folder, 'test', operation, lambda: None)
        before_receipt = copy.deepcopy(operation)
        with self.assertRaisesRegex(RuntimeError, '合成回执中断'):
            self.host.restore_environment_bindings(operation, Mock(side_effect=RuntimeError('合成回执中断')))
        operation = before_receipt
        self.host.restore_environment_bindings(operation, lambda: None)
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database:
            self.assertEqual(database.execute('SELECT generation,container_id FROM account_environments').fetchone(), (5, 'candidate-cli'))
        operation['environment_restore_bindings_applied'] = False
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database, database:
            database.execute('UPDATE account_environments SET generation=6')
        with self.assertRaisesRegex(ValueError, '后来或外来'):
            self.host.restore_environment_bindings(operation, lambda: None)

    def test_binding_and_credential_ownership_changes_are_visible(self) -> None:
        """账号绑定和单一凭据所有权属于受保护身份。@return None。"""
        before = self.host.metadata()
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('UPDATE accounts SET cc2api_account_id=2 WHERE id=1')
        self.assertNotEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('UPDATE accounts SET cc2api_account_id=1 WHERE id=1')
        self.assertEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            database.execute('INSERT INTO oauth_account_ownerships VALUES(1,?)', ('{"owner":"changed"}',))
        self.assertNotEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])

    def test_restore_reacquires_released_gate_before_observing_new_work(self) -> None:
        """提交后恢复先重新关门，后来活动保持且切换尚未开始。@return None。"""
        operation = self.prepare_restore_gate('idle')
        self.host.request = Mock(side_effect=[{'active': 0, 'environments': []}, {'active': 1}])
        self.host.verify_images = Mock()
        with self.assertRaisesRegex(ValueError, '恢复前仍有在途'):
            self.host.restore(operation, lambda: None)
        self.assertEqual(read_gate(self.host.gate, 'test')['phase'], 'blocked')
        self.host.verify_images.assert_not_called()

    def test_fenced_restore_can_reach_images_when_candidate_api_is_down(self) -> None:
        """原门禁持续关闭时，可恢复尚未启动的候选控制服务。@return None。"""
        operation = self.prepare_restore_gate('blocked')
        self.host.request = Mock(side_effect=RuntimeError('候选 API 尚未启动'))
        self.host.verify_images = Mock(side_effect=ValueError('到达原版镜像核验'))
        with self.assertRaisesRegex(ValueError, '到达原版镜像核验'):
            self.host.restore(operation, lambda: None)
        self.host.request.assert_not_called()

    def prepare_restore_gate(self, phase: str) -> dict:
        """建立同操作的实际持久门禁。:param phase: 原阶段。@return 恢复输入。"""
        self.host.policy['deployment'] = 'test'
        self.host.gate.mkdir(parents=True)
        operation = {'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()), 'revision': str(uuid.uuid4()),
            'target': {'release': 'system-ci-1-1'}, 'created_at': '2026-11-11T00:00:00Z', 'original': {'selection': {}}}
        atomic_json(self.host.gate / 'admission.json', {'schema_version': 1, 'deployment': 'test',
            'operation_id': operation['operation_id'] if phase == 'blocked' else None, 'epoch': operation['epoch'],
            'revision': operation['revision'], 'phase': phase, 'target_release': 'system-ci-1-1' if phase == 'blocked' else None,
            'created_at': operation['created_at']})
        return operation


if __name__ == '__main__':
    unittest.main()
