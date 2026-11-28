"""验证冻结的 SSH 历史观察只接受原身份，读取真实文件与长驻运行时的工作。"""

from types import SimpleNamespace
from threading import RLock
from subprocess import Popen, DEVNULL
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from docker.errors import NotFound
from pydantic import ValidationError

from account_runtime import AccountRuntime
from cluster_draft_login_grants import DraftLoginGrants
from cluster_lease_mirror import NodeLeaseMirror
from cluster_stopped_observation import StoppedNodeRead, node_observation
from runtime_files import atomic_json
from system_update_gate import DeploymentGate
import test_cluster_execution_grants as grant_fixture


class StoppedNodeTests(TestCase):
    """沿现有执行许可夹具建立真实 SQLite、持久 grant 和节点门禁。"""

    def setUp(self):
        """准备同一维护代次及原角色。@return 无。"""
        f = grant_fixture.ExecutionGrantTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.f = f
        self.read = StoppedNodeRead(
            deployment='synthetic',
            operation_id=str(uuid4()),
            epoch=str(uuid4()),
            challenge=uuid4().hex,
            node_id=2,
            node_revision=1,
            node_key=f.node_key,
            environment_id=f.environment_id,
            generation=3,
            profile_name='11-23',
            role_ids={r: str(i) * 64 for i, r in enumerate(('cli', 'network', 'sender'), 1)},
        )
        self.gate_file = f.data / 'gate' / 'admission.json'
        self.gate = {
            'schema_version': 1,
            'deployment': 'synthetic',
            'operation_id': self.read.operation_id,
            'epoch': self.read.epoch,
            'phase': 'blocked',
            'target_release': 'system-ci-2-1',
            'revision': str(uuid4()),
            'created_at': '2026-01-01T00:00:00Z',
        }
        atomic_json(self.gate_file, self.gate, 0o600)
        self.gate_service = DeploymentGate(f.data / 'gate', 'synthetic')
        self.enterContext(patch('cluster_stopped_observation.UPDATE_GATE', self.gate_service))
        self.engine = Mock()
        self.engine.info.return_value = {'ID': 'synthetic-test-daemon'}
        self.engine.containers.list.return_value = []
        self.engine.containers.get.side_effect = NotFound('fixture')
        self.executor = SimpleNamespace(
            data=f.data, client=self.engine, node_key=f.node_key, deployment='synthetic'
        )
        self.mirror = NodeLeaseMirror(f.store)
        self.runtime = object.__new__(AccountRuntime)
        self.runtime.jobs, self.runtime.lock = {}, RLock()
        self.host = SimpleNamespace(
            closed=False,
            lock=f.store.lock,
            runtime=self.runtime,
            gateway=SimpleNamespace(lease_mirror=self.mirror),
        )
        self.drafts = DraftLoginGrants(f.data, f.node_key, 'synthetic', f.database)
        (f.root / 'home').mkdir()
        (f.data / 'profiles' / '11-23').mkdir(parents=True)
        atomic_json(
            f.root / 'runtime' / 'sender' / 'sender.json',
            {'binding': {'environment_id': f.environment_id, 'generation': 3}},
        )

    def observation(self):
        """执行真实节点读取函数。@return 节点公开观察。"""
        return node_observation(self.executor, self.host, self.f.store, self.drafts, self.read)

    def test_real_grant_and_execution_file_are_counted(self):
        """读取已有执行文件、真实 grant 以及内存作业；不续期、不关闭。@return 无。"""
        first = self.observation()
        self.assertEqual(first['binding'], (self.f.environment_id, 3))
        self.assertEqual((first['jobs'], first['executions'], first['leases']), (0, 0, 0))
        self.f.store.create(self.f.grant)
        proc = Popen(['sleep', '15'], stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.terminate)
        self.runtime.jobs[self.f.environment_id + ':fixture'] = {
            'row': {'environment_id': self.f.environment_id},
            'process': proc,
        }
        atomic_json(self.f.root / 'runtime/execution.json', {'operation': 'test'})
        observed = self.observation()
        self.assertEqual((observed['jobs'], observed['executions'], observed['leases']), (1, 1, 1))
        self.assertEqual(self.f.store.get(self.f.scope)['phase'], 'prepared')

    def test_idle_mismatched_gate_and_extra_role_fail(self):
        """旧节点空闲门禁、其他代次与未知额外角色均拒绝。@return 无。"""
        for updates in (
            {'phase': 'idle', 'operation_id': None, 'target_release': None},
            {'epoch': str(uuid4())},
        ):
            atomic_json(self.gate_file, {**self.gate, **updates}, 0o600)
            with self.assertRaises(ValueError):
                self.observation()
        atomic_json(self.gate_file, self.gate, 0o600)
        self.engine.containers.list.return_value = [object()]
        with self.assertRaises(ValueError):
            self.observation()

    def test_unknown_grant_or_sender_generation_remains_unconfirmed(self):
        """损坏的许可和类型错误的代次不会被计作零。@return 无。"""
        case = self.f
        malformed = case.store.directory / case.environment_id / (uuid4().hex + '.json')
        atomic_json(malformed, {}, 0o600)
        with self.assertRaises(ValueError):
            self.observation()
        malformed.unlink()
        atomic_json(
            case.root / 'runtime/sender/sender.json',
            {'binding': {'environment_id': case.environment_id, 'generation': 3.0}},
        )
        with self.assertRaises(ValueError):
            self.observation()

    def test_profile_is_one_component(self):
        """阻断含上级目录的路径。@return 无。"""
        with self.assertRaises(ValidationError):
            StoppedNodeRead.model_validate({**self.read.model_dump(), 'profile_name': '../other'})
