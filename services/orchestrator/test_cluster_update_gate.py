"""节点真实私有入口的冻结、取消、错代及维护续接回归。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import cluster_update_gate as gates
import test_cluster_agent as fixture
from cluster_agent_client import node_agent_request
from runtime_files import atomic_json
from system_update_gate import DeploymentGate, UPDATE_GATE, read_gate


class NodeGateTests(unittest.TestCase):
    """两处私有目录独立持有门禁，节点使用实际 uvicorn UDS 和原工作入口。"""

    def setUp(self):
        """建立相互独立的中央、节点门禁及受信绑定。@return 无。"""
        self.actor = fixture.NodeAgentTests(methodName='runTest')
        self.actor.setUp()
        self.addCleanup(self.actor.doCleanups)
        self.node = self.actor.fixture.executor
        self.directory = self.actor.data / 'system-update-gate'
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.control = Path(self.enterContext(TemporaryDirectory()))
        self.central = DeploymentGate(self.control, self.node.deployment)
        self.origin = {'schema_version': 1, 'deployment': self.node.deployment, 'phase': 'idle',
            'operation_id': None, 'epoch': str(uuid4()), 'revision': str(uuid4()), 'created_at': '2026-11-28T00:00:00Z', 'target_release': None}
        self.operation = {**self.origin, 'phase': 'blocked', 'operation_id': str(uuid4()), 'epoch': str(uuid4()),
                          'revision': str(uuid4()), 'target_release': 'candidate'}
        atomic_json(self.directory/'admission.json', self.origin)
        atomic_json(self.control/'admission.json', self.operation)
        self.enterContext(patch.object(UPDATE_GATE, 'directory', self.directory))
        self.enterContext(patch.object(UPDATE_GATE, 'deployment', self.node.deployment))
        self.enterContext(patch.object(gates, 'UPDATE_GATE', self.central))
        self.peer = gates.GatePeer(id=2, node_key=self.node.node_key, config_sha256=sha256(b'{}').hexdigest())
        self.calls = []
        self.fail_after = None
        self.record = {'kind': 'ssh', 'node_key': self.node.node_key, 'config_json': '{}'}
        self.ssh = SimpleNamespace(execution_environment=self.forward)
        self.service = SimpleNamespace(private_root=self.control/'private', connection=lambda _: self.ssh,
                                       store=SimpleNamespace(get=lambda _:self.record))

    def forward(self, container, payload, operation):
        """经真实节点 UDS 转发固定操作。@param container 原节点控制角色。@param payload 命令。@param operation 动作。@return 回执。"""
        self.assertEqual(operation, 'platform-gate')
        self.calls.append(payload.copy())
        result = self.actor.call(operation, payload)
        if not result['ok']:
            raise ValueError('节点拒绝维护动作')
        if self.fail_after == payload['action']:
            raise TimeoutError('模拟远端实际提交后丢失应答')
        return result['result']

    def coordinate(self, action):
        """用原节点配置和宿主操作协调一项动作。@param action 动作。@return 完成状态。"""
        return gates.coordinate_gate(self.service, self.node, self.peer, action, self.operation)

    def state(self):
        """通过受信路径读真实节点文件。@return 持久节点门禁。"""
        return read_gate(self.directory, self.node.deployment)

    def test_active_work_waits_then_blocks_fresh_and_preserves_platform_scope(self):
        """在途认领先收口，新业务在冻结期间等待，旧平台任务限本次代次继续。@return 无。"""
        entered, finish = Event(), Event()
        original = self.node.prepare
        def held(request):
            entered.set()
            if not finish.wait(3):
                raise AssertionError('准备线程未放行')
            return original(request)
        with ThreadPoolExecutor(max_workers=1) as pool, patch.object(self.node, 'prepare', held):
            started = pool.submit(self.actor.call,'prepare',self.actor.fixture.request.model_dump())
            try:
                self.assertTrue(entered.wait(2))
                self.assertFalse(self.coordinate('freeze'))
                self.assertEqual(self.state()['phase'], 'idle')
            finally:
                finish.set()
            self.assertTrue(started.result()['ok'])
        self.assertTrue(self.coordinate('freeze'))
        blocked = self.state()
        self.assertEqual((blocked['epoch'],blocked['operation_id']), (self.operation['epoch'],self.operation['operation_id']))
        self.assertTrue(self.coordinate('freeze'))
        self.assertEqual(self.state(), blocked)
        raw = json.dumps(self.actor.fixture.request.model_dump()).encode()
        with self.assertRaises(ValueError):
            node_agent_request(self.actor.data,self.actor.token,'prepare',raw)
        with self.assertRaises(ValueError):
            node_agent_request(self.actor.data,self.actor.token,'prepare',raw,maintenance=(str(uuid4()),self.operation['epoch']))
        self.assertTrue(node_agent_request(self.actor.data,self.actor.token,'prepare',raw,
                       maintenance=(self.operation['operation_id'], self.operation['epoch']))['ok'])
        maintenance = UPDATE_GATE.reserve_maintenance('test', self.operation['operation_id'], self.operation['epoch'])
        try:
            self.assertFalse(self.coordinate('release'))
            self.assertEqual(self.state(), blocked)
        finally:
            UPDATE_GATE.release_reserved(maintenance)
        self.assertTrue(self.coordinate('release'))
        self.assertTrue(self.coordinate('release'))
        self.assertEqual(self.state()['phase'], 'idle')
        self.assertTrue(self.actor.call('prepare',self.actor.fixture.request.model_dump())['ok'])

    def test_async_job_keeps_admission_until_thread_exit(self):
        """节点请求返回后异步工作继续持位，实际退出才可冻结。@return 无。"""
        hold = Event()
        with patch.object(gates, 'UPDATE_GATE', UPDATE_GATE):
            job = gates.NodeJobThread(target=hold.wait, args=(3,))
            job.start()
            try:
                self.assertGreater(UPDATE_GATE.state()['active'], 0)
                command = gates.NodeGateCommand(action='freeze', node_key=self.node.node_key,
                    expected_revision=self.origin['revision'], **{k:self.operation[k] for k in
                    ('operation_id','epoch','deployment','created_at','target_release')})
                self.assertEqual(gates.node_gate(self.node, command)['phase'], 'idle')
            finally:
                hold.set()
                job.join(timeout=3)
        self.assertFalse(job.is_alive())
        self.assertEqual(UPDATE_GATE.state()['active'],0)
        self.assertTrue(self.coordinate('freeze'))
        self.assertTrue(self.coordinate('release'))

    def test_lost_write_reply_release_and_late_retry(self):
        """节点已经冻结但应答丢失时，重开协调器可沿原修订释放。@return 无。"""
        self.fail_after = 'freeze'
        with self.assertRaises(TimeoutError):
            self.coordinate('freeze')
        frozen_request=self.calls[-1]
        self.assertEqual(self.state()['phase'], 'blocked')
        self.fail_after = None
        self.assertTrue(self.coordinate('release'))
        self.assertFalse(self.actor.call('platform-gate', frozen_request)['ok'])
        with self.assertRaises(ValueError):
            self.coordinate('freeze')
        self.assertEqual(self.state()['phase'], 'idle')

    def test_cancel_before_remote_write_and_node_config_drift(self):
        """未发冻结的取消不访问节点；已有意图必须按原配置释放。@return 无。"""
        self.assertTrue(self.coordinate('release'))
        self.assertEqual(self.calls, [])
        with self.assertRaises(ValueError):
            self.coordinate('freeze')
        self.operation = {**self.operation,'operation_id':str(uuid4()), 'epoch':str(uuid4())}
        atomic_json(self.control/'admission.json',self.operation)
        self.assertTrue(self.coordinate('freeze'))
        self.record['config_json']='{"changed":true}'
        with self.assertRaises(ValueError):
            self.coordinate('release')
        self.assertEqual(self.state()['phase'], 'blocked')
        self.record['config_json']='{}'
        self.assertTrue(self.coordinate('release'))

    def test_release_rechecks_an_intended_node_after_backup_restore(self):
        """宿主仍封住中央时，节点恢复到先前快照，同一释放再核原节点。@return 无。"""
        self.assertTrue(self.coordinate('freeze'))
        saved = self.state()
        self.assertTrue(self.coordinate('release'))
        atomic_json(self.directory / 'admission.json', saved)
        self.assertTrue(self.coordinate('release'))
        self.assertEqual(self.state()['phase'], 'idle')
        self.assertEqual(self.state()['epoch'], self.operation['epoch'])

    def test_node_release_overtakes_delayed_freeze(self):
        """节点在实际冻结执行前收到释放，也消费原修订。@return 无。"""
        request={**{k:self.operation[k] for k in ('operation_id','epoch','deployment','created_at','target_release')},
                 'node_key':self.peer.node_key,'expected_revision':self.origin['revision']}
        cleared=self.actor.call('platform-gate',{**request,'action':'release'})
        self.assertTrue(cleared['ok'])
        self.assertEqual(cleared['result']['epoch'],self.operation['epoch'])
        self.assertFalse(self.actor.call('platform-gate',{**request,'action':'freeze'})['ok'])

    def test_authenticated_host_route_through_loopback_ssh_and_persistent_node(self):
        """宿主管理 HTTP、固定 SSH 命令、轻量客户端、真实 UDS 依次冻结和释放。@return 无。"""
        import os
        import shlex
        import shutil
        import sys
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from cluster_deployment import node_container_name
        from cluster_ssh import _run
        from system_updates import system_updates_router
        import test_cluster_ssh as ssh_fixture

        if os.geteuid() != 0 or not shutil.which('sshd'):
            self.skipTest('隔离 SSH 需 root 和本机 sshd')
        ssh = ssh_fixture.ClusterSshTests(methodName='runTest')
        ssh.setUp()
        self.addCleanup(ssh.doCleanups)
        self.service.private_root = ssh.node.private.parent
        self.service.connection = lambda _: ssh.node
        self.record['config_json'] = json.dumps(ssh.config.model_dump(), sort_keys=True)
        self.peer = self.peer.model_copy(update={'config_sha256': sha256(self.record['config_json'].encode()).hexdigest()})
        shim = ssh.root / 'docker'
        shim.write_text(f'#!{sys.executable}\nimport os,sys\nsys.path.insert(0,{str(Path(__file__).parent)!r})\n'
            f'os.environ["BENCH_DATA"]={str(self.actor.data)!r}\nos.environ["V3_INTERNAL_TOKEN"]={self.actor.token!r}\n'
            'os.environ["V3_ROLE"]="node-control"\nfrom cluster_agent_client import main\n'
            'sys.argv=sys.argv[sys.argv.index("/app/cluster_agent_client.py"):]\nmain()\n')
        shim.chmod(0o700)
        def transport(arguments, **kwargs):
            self.assertTrue(arguments[-1].startswith('docker exec '))
            return _run([*arguments[:-1], shlex.quote(str(shim)) + arguments[-1][6:]], **kwargs)
        app = FastAPI()
        runtime = SimpleNamespace(deployment=self.node.deployment, cluster_service=self.service)
        app.include_router(system_updates_router(lambda: runtime))
        self.enterContext(patch('cluster_ssh._run', side_effect=transport))
        self.enterContext(patch('system_updates.UPDATE_GATE', self.central))
        self.enterContext(patch('system_updates.update_token', return_value='e' * 40))
        client = self.enterContext(TestClient(app))
        route = '/internal/v3/system-updates/stopped-node-gate'
        request = {'peer': self.peer.model_dump(), 'action':'freeze', 'operation_id':self.operation['operation_id'],
                   'epoch': self.operation['epoch']}
        headers = {'x-v3-update-token':'e' * 40}
        self.assertEqual(client.post(route,json=request).status_code, 403)
        self.assertEqual(client.post(route,json={**request, 'epoch':str(uuid4())},headers=headers).status_code, 409)
        response=client.post(route,json=request,headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['done'])
        self.assertEqual(self.state()['phase'],'blocked')
        with gates.maintenance_scope(self.operation):
            value=ssh.node.prepare_environment(node_container_name(self.node.deployment,self.node.node_key),
                                               self.actor.fixture.request.model_dump())
        self.assertIn('environment',value)
        released=client.post(route,json={**request, 'action':'release'},headers=headers)
        self.assertEqual(released.status_code,200,released.text)
        self.assertTrue(released.json()['done'])
        self.assertEqual(self.state()['phase'],'idle')


class SnapshotGateScopeTests(unittest.TestCase):
    """真实历史环境进入不同范围时向宿主发布稳定的参与者清单。"""

    def test_candidates_do_not_depend_on_a_successful_historical_proof(self):
        """取证前 idle 与同一行 blocked 返回相同节点，control_only 省略。@return 无。"""
        import test_system_update_stopped as fixtures
        case = fixtures.StoppedMaintenanceTests(methodName='runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        states = []
        for phase in ('idle','blocked'):
            gate = {**case.gate,'phase':phase,'active':0,'central_active':0,'control_active':0}
            if phase == 'idle':
                gate.update(operation_id=None,target_release=None)
            with patch('system_updates.UPDATE_GATE.state', return_value=gate):
                full=case.snapshot()
                central=case.snapshot(central_only=True)
                control=case.snapshot(control_only=True)
            self.assertNotIn('stopped_gate_nodes', control)
            self.assertEqual(full['stopped_gate_nodes'],central['stopped_gate_nodes'])
            self.assertEqual([item['node_key'] for item in full['stopped_gate_nodes']],[case.node])
            states.append(full['stopped_gate_nodes'])
        self.assertEqual(*states)
        rows=[{'id':3,'node_key':'b'*32,'kind':'ssh'},{'id':1,'node_key':'local','kind':'local'},
              {'id':2,'node_key':'a'*32,'kind':'ssh'}]
        service=SimpleNamespace(store=SimpleNamespace(get=lambda _: {'config_json':'{}'}))
        self.assertEqual([p['id'] for p in gates.gate_peers(service,rows)],[2,3])
