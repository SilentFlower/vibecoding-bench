"""从受认证维护入口复验历史停止证据和原准入边界。"""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, RLock
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4
import os
import sqlite3

from docker.errors import NotFound
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from account_isolation import ROLE_COLUMNS, ROLE_LABELS
from cluster_service import ClusterService
from cluster_store import ClusterStore
from database_migrations import apply_migrations
from runtime_files import atomic_json
from system_updates import system_updates_router
from system_update_stopped import HOST_READ_PATH


class StoppedMaintenanceTests(TestCase):
    """真实 SQLite 和维护路由使用合成的节点及宿主回执。"""

    def setUp(self) -> None:
        """冻结两个历史环境和同代门禁。@return None。"""
        area = self.enterContext(TemporaryDirectory())
        self.root = Path(area)
        self.local, self.remote = sorted((uuid4().hex, uuid4().hex))
        self.node = uuid4().hex
        self.ids = {role: str(number) * 64 for number, role in enumerate(ROLE_COLUMNS, 1)}
        self.remote_ids = {role: str(number) * 64 for number, role in enumerate(ROLE_COLUMNS, 4)}
        self.registry = 'sha256:' + 'a' * 64
        self.configuration = 'sha256:' + 'b' * 64
        self.gate = {'schema_version': 1, 'deployment': 'test', 'operation_id': str(uuid4()), 'epoch': str(uuid4()),
            'phase': 'blocked', 'target_release': 'system-ci-29-1', 'revision': str(uuid4()), 'created_at': '2026-11-28T09:00:00Z'}
        atomic_json(self.root / 'admission.json', self.gate)
        token = 'f' * 64
        key_file = self.root / 'token'
        key_file.write_text(token)
        key_file.chmod(0o600)
        self.headers = {'x-v3-update-token': token}
        self.enterContext(patch.dict(os.environ, {'V3_UPDATE_GATE_DIR': area, 'V3_UPDATE_SOCKET_DIR': area,
            'V3_DEPLOYMENT_ID': 'test'}))
        with closing(self.database()) as connection, connection:
            apply_migrations(connection)
            connection.execute("INSERT INTO cluster_nodes(node_key,name,kind,config_json,created_at) VALUES(?,'节点','ssh','{}',0)",
                (self.node,))
            for identifier, account, name, roles in ((self.local, 17, '原中央', self.ids), (self.remote, 18, '原节点', self.remote_ids)):
                fields = ','.join(ROLE_COLUMNS[role] for role in roles)
                connection.execute(f"INSERT INTO account_environments(environment_id,account_id,name,fingerprint_json,state,generation,{fields}) "
                    "VALUES(?,?,?,'{}','stopped',4,?,?,?)", (identifier, account, name, *roles.values()))
                (self.root / 'profiles' / name).mkdir(parents=True)
            connection.execute("INSERT INTO node_login_drafts(environment_id,node_id,operation_id,sid,generation,phase,revision,"
                "record_json,created_at,updated_at) VALUES(?,2,?,?,?,'closed',72,'{}',0,0)",
                (self.remote, uuid4().hex, uuid4().hex[:12], uuid4().hex))
        original = self.root / 'environments' / self.local
        (original / 'home').mkdir(parents=True)
        atomic_json(original / 'runtime/sender/sender.json', {'binding': {'environment_id': self.local, 'generation': 4}})
        self.central = Mock()
        self.central.info.return_value = {'ID': 'central-engine'}
        self.peer = Mock()
        self.peer.info.return_value = {'ID': 'peer-engine'}
        containers = {
            value: SimpleNamespace(id=value, labels={'vibebench.product': 'v3', 'vibebench.deployment': 'test',
                'vibebench.environment': self.local, 'vibebench.role': ROLE_LABELS[role],
                'vibebench.isolation-version': '2', 'vibebench.release': 'ci-18-1'},
                attrs={'Image': self.registry, 'State': {'Status': 'exited', 'Running': False, 'Restarting': False, 'Pid': 0}})
            for role, value in self.ids.items()}
        self.central.containers.list.side_effect = lambda **kw: list(containers.values()) if kw['filters']['label'] == [
            f'vibebench.environment={self.local}'] else []

        def get_container(identifier):
            if identifier not in containers:
                raise NotFound('fixture')
            return containers[identifier]

        self.central.containers.get.side_effect = get_container
        self.peer.containers.list.return_value = []
        self.peer.containers.get.side_effect = NotFound('fixture')
        self.store = ClusterStore(self.database, Lock())
        self.service = ClusterService(self.store, self.root, self.central, self.root / 'transport')
        self.addCleanup(self.service.close)
        self.enterContext(patch.object(self.service, 'docker', return_value=self.peer))
        self.gateway = Mock()
        self.gateway._request.return_value = {**self.gate, 'active': 0, 'tui_tool_pending': False}
        self.runtime = SimpleNamespace(database=self.database, locality=self.service.owns_local, data=self.root,
            cluster_service=self.service, deployment='test', client=self.central, gateway=self.gateway,
            environment_lock=lambda identifier: RLock(), environment_jobs=Mock(return_value=[]),
            _stop_environment=Mock())
        app = FastAPI()
        app.include_router(system_updates_router(lambda: self.runtime))
        self.client = self.enterContext(TestClient(app))
        self.read_host = self.enterContext(patch('system_updates.updater_request', side_effect=self.evidence))

    def database(self) -> sqlite3.Connection:
        """打开实际迁移过的独立数据库。@return 由调用方关闭的连接。"""
        connection = sqlite3.connect(self.root / 'bench.sqlite')
        connection.row_factory = sqlite3.Row
        return connection

    def evidence(self, method: str, path: str, scope: dict) -> dict:
        """给本次挑战投影同代节点与已选镜像。@param method HTTP 方法。@param path 私有路径。@param scope 原挑战。@return 隔离证据。"""
        self.assertEqual((method, path), ('POST', HOST_READ_PATH))
        environment = scope['environment_id']
        local = environment == self.local
        nodes = {}
        for key, engine in (('local', 'central-engine'), (self.node, 'peer-engine')):
            owner = (key == 'local') == local
            nodes[key] = {'engine_id': engine, 'operation_id': scope['operation_id'], 'epoch': scope['epoch'],
                'phase': 'blocked', 'directories': ['home', 'runtime', 'profile'] if owner else ['profile'] if key == 'local' else [],
                'binding': [environment, 4] if owner else None, 'jobs': 0, 'executions': 0, 'leases': 0, 'pending_receipts': 0}
        image = {'system_release': 'system-ci-18-1', 'manifest_sha256': 'a' * 64, 'account_release': 'ci-18-1',
            'registry_digest': self.registry, 'config_digest': self.configuration, 'engine_digest': 'registry_digest'}
        return {'scope': deepcopy(scope), 'nodes': nodes, 'image': image if local else None}

    def snapshot(self, **body) -> dict:
        """请求原维护快照。@param body 原范围参数。@return HTTP 成功响应。"""
        response = self.client.post('/internal/v3/system-updates/snapshot', json=body, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_full_and_central_read_original_without_granting_authority(self) -> None:
        """两个原形态读回；中央、快切及环境操作沿各自范围。@return None。"""
        with closing(self.database()) as connection:
            before = [dict(row) for row in connection.execute('SELECT * FROM account_environments ORDER BY account_id')]
        snapshot = self.snapshot()
        self.assertTrue(snapshot['ready'], snapshot)
        local, remote = snapshot['environments']
        self.assertEqual((local['node_kind'], remote['node_kind']), ('local', 'ssh'))
        self.assertEqual({role: value['id'] for role, value in local['roles'].items()}, self.ids)
        self.assertEqual(remote['roles'], {})
        self.assertTrue(all(item['state'] == 'stopped' and item['origin'] is None for item in (local, remote)))
        self.assertEqual([item['environment_id'] for item in self.snapshot(central_only=True)['environments']], [self.local])
        prior = self.read_host.call_count
        self.assertEqual(self.snapshot(control_only=True)['environments'], [])
        self.assertEqual(self.read_host.call_count, prior)
        self.assertFalse(any(self.service.owns_local(row) for row in before))
        with self.assertRaises(ValueError):
            self.service.admit_local({'id': 17})
        for action in ('stop', 'rebuild', 'restore', 'retire'):
            response = self.client.post('/internal/v3/system-updates/environment', headers=self.headers,
                json={**{key: self.gate[key] for key in ('operation_id', 'epoch')},
                    'environment_id': self.local, 'generation': 4, 'action': action})
            self.assertEqual(response.status_code, 409, response.text)
        self.runtime._stop_environment.assert_not_called()
        with closing(self.database()) as connection:
            self.assertEqual([dict(row) for row in connection.execute('SELECT * FROM account_environments ORDER BY account_id')], before)

    def test_host_legacy_and_unauthorized_calls_keep_barrier(self) -> None:
        """原宿主缺接口继续阻断，快切和内部鉴权沿原约束。@return None。"""
        self.read_host.side_effect = HTTPException(404, '原宿主没有该入口')
        response = self.client.post('/internal/v3/system-updates/snapshot', json={})
        self.assertEqual(response.status_code, 403)
        self.read_host.assert_not_called()
        snapshot = self.snapshot()
        self.assertFalse(snapshot['ready'])
        self.assertEqual(len(snapshot['blockers']), 2)
        self.assertTrue(all('宿主尚未提供历史停止证据读取' in value for value in snapshot['blockers']))
        self.assertTrue(self.snapshot(control_only=True)['ready'])

    def test_unverified_receipts_fail_closed(self) -> None:
        """查明回执变形、实际镜像、未知远程容器和复读门禁。@return None。"""
        cases = {
            '过期挑战': lambda proof: proof['scope'].update(challenge='0' * 32),
            '布尔替代节点修订': lambda proof: proof['scope']['nodes'][0].update(revision=True),
            '未知节点门禁': lambda proof: proof['nodes'][self.node].update(phase='idle'),
            '同一引擎冒充两个节点': lambda proof: proof['nodes'][self.node].update(engine_id='central-engine'),
            'SSH 引擎与实收不符': lambda proof: proof['nodes'][self.node].update(engine_id='wrong-peer'),
            '缺少节点': lambda proof: proof['nodes'].pop(self.node),
            '待回执': lambda proof: proof['nodes'][self.node].update(pending_receipts=1),
            'SSH 作业': lambda proof: proof['nodes'][self.node].update(jobs=1),
            '跨节点目录冲突': lambda proof: proof['nodes'][self.node].update(directories=['profile']),
            '代次类型不符': lambda proof: proof['nodes']['local'].update(binding=[self.local, '4']),
            '错误摘要类型': lambda proof: proof['image'].update(engine_digest='config_digest'),
        }
        for reason, mutate in cases.items():
            with self.subTest(reason=reason):
                def changed(method, path, scope):
                    response = self.evidence(method, path, scope)
                    if scope['environment_id'] == self.local:
                        mutate(response)
                    return response

                self.read_host.side_effect = changed
                self.assertFalse(self.snapshot()['ready'])
        self.read_host.side_effect = self.evidence
        with patch.object(self.peer.containers.get, 'side_effect', None):
            self.assertFalse(self.snapshot()['ready'])
        container = self.central.containers.get(self.ids['cli'])
        with patch.dict(container.attrs['State'], {'Running': True, 'Pid': 123}):
            self.assertFalse(self.snapshot()['ready'])
        self.gateway._request.return_value['tui_tool_pending'] = True
        self.assertFalse(self.snapshot()['ready'])

    def test_original_database_files_and_gate_are_live_requirements(self) -> None:
        """原登记复用、本机执行、二次读回变化与运行绑定均必须拒绝。@return None。"""
        with closing(self.database()) as connection, connection:
            connection.execute("INSERT INTO accounts(name,profile_path) VALUES('新账号','profiles/原中央')")
        self.assertFalse(self.snapshot()['ready'])
        with closing(self.database()) as connection, connection:
            connection.execute("DELETE FROM accounts WHERE name='新账号'")
        binding = self.root / 'environments' / self.local / 'runtime/sender/sender.json'
        atomic_json(binding, {'binding': {'environment_id': self.local, 'generation': 4.0}})
        self.assertFalse(self.snapshot()['ready'])
        atomic_json(binding, {'binding': {'environment_id': self.local, 'generation': 4}})
        executions = binding.parent.parent / 'executions'
        executions.mkdir()
        atomic_json(executions / 'pending.json', {})
        self.assertFalse(self.snapshot()['ready'])
        (executions / 'pending.json').unlink()

        def change_gate(method, path, scope):
            atomic_json(self.root / 'admission.json', {**self.gate, 'epoch': str(uuid4())})
            return self.evidence(method, path, scope)

        self.read_host.side_effect = change_gate
        self.assertFalse(self.snapshot()['ready'])
