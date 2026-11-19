"""真实私有UDS验证节点认证、长驻运行时、有限证明及生命周期边界。"""
from __future__ import annotations

import io
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from httpx import Client, HTTPTransport
from uvicorn import Config, Server

from cluster_agent import _node_socket, create_node_app
from cluster_agent_client import node_agent_request
from cluster_environment_operations import ENVIRONMENT_OPERATIONS
from cluster_execution import main as execution_main
from cluster_draft_login_contract import DraftLoginScope, DraftLoginSettings, DraftLoginWork, draft_preparation_sha256
from cluster_runtime_host import NodeRuntimeHost
from cluster_deployment import node_container_name
from cluster_ssh import _run as run_ssh_command
from test_cluster_runtime_host import _HostedRuntime
from test_cluster_draft_login import _DraftRuntime
import test_cluster_execution as execution_fixture
import test_cluster_ssh as ssh_fixture


class NodeAgentTests(unittest.TestCase):
    """仅连接隔离临时UDS，Docker使用原运行时接口替身。"""

    def setUp(self) -> None:
        """启动真实uvicorn私有socket，保留原节点准备夹具。:return: None。"""
        fixture = execution_fixture.NodeExecutionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.data, self.token = fixture, fixture.root, 'b' * 64
        self.host = NodeRuntimeHost(fixture.executor, runtime_factory=_HostedRuntime)
        self.socket_context = _node_socket(self.data)
        listener = self.socket_context.__enter__()
        self.addCleanup(self.socket_context.__exit__, None, None, None)
        app = create_node_app(fixture.executor, self.host, self.token, 'synthetic')
        self.server = Server(Config(app, log_level='critical', access_log=False, loop='asyncio'))
        self.thread = threading.Thread(target=self.server.run, kwargs={'sockets': [listener]}, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)
        deadline = time.monotonic() + 5
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                self.fail('隔离节点服务启动超时')
            time.sleep(0.01)

    def _stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())

    def call(self, operation: str, value: dict) -> dict:
        """使用实际容器内客户端提交原固定操作。:param operation: 操作。:param value: 输入。:return: 私有回执。"""
        return node_agent_request(self.data, self.token, operation, json.dumps(value).encode())

    def test_private_socket_and_repeated_prepare_share_actual_runtime(self) -> None:
        """多次SSH等价请求共享同一pool，服务关闭时收口一次。:return: None。"""
        self.assertEqual(0o600, (self.data / 'node-agent/control.sock').stat().st_mode & 0o777)
        self.assertEqual({'protocol': 1, 'node_key': 'a' * 32, 'deployment': 'synthetic',
            'release': 'synthetic', 'state': 'ready'}, self.call('health', {})['result'])
        request = self.fixture.request.model_dump()
        first = self.call('prepare', request)
        runtime = self.host.runtime
        second = self.call('prepare', request)
        self.assertTrue(first['ok'])
        self.assertTrue(second['ok'])
        self.assertEqual(2, second['result']['environment']['generation'])
        self.assertIs(runtime, self.host.runtime)
        runtime.start.assert_called_once()
        runtime.heartbeat_pool.shutdown.assert_not_called()
        self._stop()
        runtime.stop.assert_called_once()

    def test_light_cli_uses_original_uds_without_loading_execution_models(self) -> None:
        """真实子进程经原认证UDS读取状态，执行模型保持由长驻服务装载。:return: None。"""
        program='import sys;from cluster_agent_client import main;main();assert "cluster_execution" not in sys.modules'
        environment={**os.environ,'V3_ROLE':'node-control','BENCH_DATA':str(self.data),'V3_INTERNAL_TOKEN':self.token}
        completed=subprocess.run([sys.executable,'-c',program,'health'],input=b'{}',capture_output=True,
            env=environment,timeout=5,check=True)
        value=json.loads(completed.stdout)
        self.assertTrue(value['ok'])
        self.assertEqual('ready',value['result']['state'])
        self.assertEqual(self.fixture.node_key,value['result']['node_key'])

    def test_history_capture_through_real_ssh_light_client_and_actor(self) -> None:
        """真实SSH经容器命令替身和轻量客户端读取Actor原文件。:return: None。"""
        if os.geteuid() != 0 or not shutil.which('sshd'):
            self.skipTest('隔离SSH链路需要root和sshd')
        ssh = ssh_fixture.ClusterSshTests(methodName='runTest')
        ssh.setUp()
        self.addCleanup(ssh.doCleanups)
        prepared = self.call('prepare', self.fixture.request.model_dump())['result']['environment']
        work_id = 'c' * 32
        group = hashlib.sha256(f'warmup/{work_id}'.encode()).hexdigest()[:20]
        base = self.data / 'environments' / prepared['environment_id'] / 'flows' / ('group-' + group)
        base.mkdir(parents=True)
        (base / 'capture-status.json').write_text(json.dumps({'state': 'complete', 'message': '真实链路'}))
        shim = ssh.root / 'docker'
        shim.write_text(f'#!{sys.executable}\nimport os,sys\nsys.path.insert(0,{str(Path(__file__).parent)!r})\n'
            f'os.environ["BENCH_DATA"]={str(self.data)!r}\nos.environ["V3_INTERNAL_TOKEN"]={self.token!r}\n'
            'os.environ["V3_ROLE"]="node-control"\n'
            'from cluster_agent_client import main\nsys.argv=[sys.argv[0],sys.argv[-1]]\nmain()\n')
        shim.chmod(0o700)

        def transport(arguments, **kwargs):
            self.assertTrue(arguments[-1].startswith('docker exec '))
            return run_ssh_command([*arguments[:-1], shlex.quote(str(shim)) + arguments[-1][6:]], **kwargs)

        payload = {'node_key': self.fixture.node_key, 'account_id': 1, 'environment_id': prepared['environment_id'],
            'assignment_revision': 1, 'generation': prepared['generation'], 'namespace': 'warmup', 'work_id': work_id,
            'relative': 'capture-status.json'}
        with patch('cluster_ssh._run', side_effect=transport):
            result = ssh.node.execution_environment(node_container_name('synthetic', self.fixture.node_key),
                payload, 'project-history-capture')
        self.assertEqual('真实链路', result['history']['capture']['message'])
        self.assertEqual(payload, result['history']['reference'])
        self.host.runtime.start.assert_called_once()

    def test_owner_operations_reach_real_uds_and_typed_actor(self) -> None:
        """原轻量客户端必须把交接及完整身份操作送到实际Actor校验。:return: None。"""
        for operation in ('credential-owner-get','credential-owner-prepare','credential-owner-publish','credential-identity-import','account-bound-process'):
            with self.subTest(operation=operation):
                result=self.call(operation,{})
                self.assertFalse(result['ok'])
                self.assertEqual('ValidationError',result['error_type'])

    def test_environment_operations_reach_real_uds_and_typed_actor(self) -> None:
        """原轻量入口把每个环境管理操作送到Actor DTO校验。:return: None。"""
        for operation in ENVIRONMENT_OPERATIONS:
            with self.subTest(operation=operation):
                result = self.call(operation, {})
                self.assertFalse(result['ok'])
                self.assertEqual('ValidationError', result['error_type'])

    def test_private_response_budget_preserves_original_large_capture(self) -> None:
        """真实UDS保留超过旧256KiB限制的原请求快照。:return: None。"""
        value = {'body': 'x' * (300 * 1024)}
        with patch('cluster_agent.environment_management', return_value=value):
            payload = {key: self.fixture.request.environment[key] for key in ('environment_id',)}
            payload.update(node_key=self.fixture.node_key, account_id=1, assignment_revision=1,
                gateway_account_id=7, generation=1, attempt_id='a'*8+'-'+ 'b'*4+'-'+ 'c'*4+'-'+ 'd'*4+'-'+ 'e'*12)
            self.assertEqual(value, self.call('environment-capture-read', payload)['result'])

    def test_private_login_rpc_validates_scope_and_redacts_code_errors(self) -> None:
        """真实UDS接收具体登录动作，非法输入和缺失原操作只返回固定错误。:return: None。"""
        secret='synthetic-private-authorization-code'
        result=self.call('account-login-code',{'scope':{},'request_id':'a'*32,'code':secret})
        self.assertFalse(result['ok'])
        self.assertEqual('ValidationError',result['error_type'])
        self.assertNotIn(secret,json.dumps(result))
        scope={'operation_id':'b'*32,'node_key':self.fixture.node_key,'account_id':1,'gateway_account_id':None,
            'environment_id':'e'*32,'assignment_revision':1,'generation':1,'source':'login:'+'c'*12,'role':'login'}
        result=self.call('account-login-get',scope)
        self.assertFalse(result['ok'])
        self.assertEqual('FileNotFoundError',result['error_type'])
        # UTF-8上限输入沿原64KiB合同读取，错误正文继续只公开固定类型。
        result=self.call('account-login-code',{'scope':scope,'request_id':'a'*32,'code':'汉'*8192})
        self.assertFalse(result['ok'])
        self.assertEqual('FileNotFoundError',result['error_type'])
        self.assertNotIn('汉',json.dumps(result,ensure_ascii=False))

    def test_private_null_draft_rpc_prepares_starts_commits_and_stops_original_operation(self) -> None:
        """真实认证UDS逐层消费草稿DTO，NULL账号保持至中央正式保存。:return: None。"""
        self.host.runtime_factory=_DraftRuntime
        settings=DraftLoginSettings(name='draft_only',timezone='UTC',upstream_socks5_pass='synthetic-draft-private')
        fingerprint='{"tz":"UTC"}'
        files={'.claude.json':'{"userID":"original-device"}','settings.json':'{}'}
        work=DraftLoginWork(id='a'*32,sid='c'*12,environment_id='e'*32,name=settings.name,draft_generation='d'*32,
            version='2.1.293',home='/home/node/.v3-login/'+'c'*12,
            preparation_sha256=draft_preparation_sha256(settings,fingerprint,files),expires_at=int(time.time())+900)
        prepared=self.call('draft-login-prepare',{'node_key':self.fixture.node_key,'work':work.model_dump(),
            'settings':settings.model_dump(),'fingerprint_json':fingerprint,'profile_files':files})
        self.assertTrue(prepared['ok'],prepared)
        scope=DraftLoginScope.model_validate(prepared['result']['login']['scope'])
        self.assertNotIn('synthetic-draft-private',json.dumps(prepared))
        grant=self.call('draft-login-grant-create',{**scope.model_dump(),'not_after':int(time.time())+30})
        self.assertTrue(grant['ok'],grant)
        request={'scope':scope.model_dump(),'work':work.model_dump()}
        response=self.call('draft-login-start',request)
        deadline=time.monotonic()+5
        while response['ok'] and response['result']['login']['phase']=='starting':
            self.assertLess(time.monotonic(),deadline)
            time.sleep(.01)
            response=self.call('draft-login-get',scope.model_dump())
        self.assertTrue(response['ok'],response)
        self.assertEqual('ready',response['result']['login']['phase'])
        code={'scope':scope.model_dump(),'request_id':'f'*32,'code':'synthetic-code'}
        original=self.call('draft-login-code',code)
        self.assertEqual('delivered',original['result']['login']['status'])
        self.assertEqual(original,self.call('draft-login-code',code))
        self.host.runtime.send_login_code.assert_called_once()
        committed=self.call('draft-login-commit',scope.model_dump())
        self.assertTrue(committed['ok'],committed)
        snapshot=self.call('draft-login-snapshot',scope.model_dump())
        self.assertTrue(snapshot['ok'],snapshot)
        self.assertEqual('synthetic-rt',snapshot['result']['login']['material']['refresh_token'])
        accepted=self.call('draft-login-accept',{'scope':scope.model_dump(),
            'authorization_sha256':committed['result']['login']['commit']['authorization_sha256']})
        self.assertTrue(accepted['ok'],accepted)
        self.assertEqual('closed',accepted['result']['login']['phase'])
        self.assertFalse(accepted['result']['login']['commit']['cleanup_pending'])
        bad=self.call('draft-login-get',{**scope.model_dump(),'account_id':17})
        self.assertFalse(bad['ok'])
        self.assertEqual('ValidationError',bad['error_type'])
        connection=self.fixture.executor.database()
        try:
            self.assertIsNone(connection.execute('SELECT account_id FROM account_environments').fetchone()[0])
            self.assertEqual(0,connection.execute('SELECT count(*) FROM accounts').fetchone()[0])
        finally:
            connection.close()

    def test_bound_login_rpc_never_accepts_rt_publication_or_echoes_private_material(self) -> None:
        """真实UDS的绑定发布仅接AT，非法RT与码正文只返回固定错误。:return: None。"""
        scope={'operation_id':'e'*32,'node_key':self.fixture.node_key,'account_id':1,'gateway_account_id':7,
            'environment_id':'e'*32,'assignment_revision':1,'generation':1,'source':'login:'+'c'*12,'role':'login'}
        payload={'scope':scope,'authorization_sha256':'a'*64,'access_token':'synthetic-private-at',
            'refresh_token':'synthetic-private-rt','expires_at':9999999999999}
        result=self.call('account-bound-login-publish',payload)
        self.assertFalse(result['ok'])
        self.assertEqual('ValidationError',result['error_type'])
        self.assertNotIn('synthetic-private',json.dumps(result))
        result=self.call('account-bound-login-code',{'scope':scope,'request_id':'a'*32,'code':'synthetic-private-code\n'})
        self.assertFalse(result['ok'])
        self.assertEqual('ValidationError',result['error_type'])
        self.assertNotIn('synthetic-private',json.dumps(result))
        result=self.call('account-bound-login-get',scope)
        self.assertFalse(result['ok'])
        self.assertEqual('FileNotFoundError',result['error_type'])

    def test_light_cli_rejects_wrong_role_and_oversize_input_with_redacted_result(self) -> None:
        """轻量入口拒绝错误角色及超限输入，原请求正文保持私有。:return: None。"""
        program='from cluster_agent_client import main;main()'
        for role,raw in (('account-cli',b'{"secret":"synthetic-private"}'),('node-control',b'x'*(2*1024*1024+1))):
            with self.subTest(role=role):
                environment={**os.environ,'V3_ROLE':role,'BENCH_DATA':str(self.data),'V3_INTERNAL_TOKEN':self.token}
                completed=subprocess.run([sys.executable,'-c',program,'health'],input=raw,capture_output=True,
                    env=environment,timeout=5,check=True)
                self.assertEqual({'ok':False,'reason':'node_preparation_failed','error_type':'ValueError'},json.loads(completed.stdout))
                self.assertNotIn(b'synthetic-private',completed.stdout)

    def test_api_quota_rpc_checks_exact_environment_and_returns_bounded_original_bytes(self) -> None:
        """实际UDS操作只读精确环境的API文件，旧分配拒绝。:return: None。"""
        prepared = self.call('prepare', self.fixture.request.model_dump())['result']
        scope = {'node_key': self.fixture.node_key, 'account_id': 1, 'environment_id': 'e' * 32,
            'assignment_revision': 1, 'generation': prepared['environment']['generation']}
        path = self.data / 'environments' / scope['environment_id'] / 'flows/api/observations.jsonl'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"source":"synthetic"}\n')
        response = self.call('api-quota-read', {'scope': scope, 'offset': 0})
        self.assertTrue(response['ok'])
        self.assertEqual(scope, response['result']['quota']['scope'])
        self.assertEqual(path.stat().st_size, response['result']['quota']['size'])
        self.assertFalse(self.call('api-quota-read', {'scope': {**scope, 'assignment_revision': 2}})['ok'])

    def test_authentication_schema_and_operation_rejection_are_redacted(self) -> None:
        """认证和合同失败均拒绝执行，公开错误保持固定字段。:return: None。"""
        transport = HTTPTransport(uds=str(self.data / 'node-agent/control.sock'))
        with Client(transport=transport, trust_env=False, timeout=5) as client:
            unauthorized = client.post('http://node.internal/operations/prepare',
                content=b'{"profile":"synthetic-secret"}', headers={'x-v3-node-token': 'c' * 64})
            self.assertEqual(401, unauthorized.status_code)
            self.assertEqual({'ok': False, 'reason': 'node_authentication_failed'}, unauthorized.json())
            for path, raw in (('arbitrary-command', b'{}'), ('health', b'{"x":1,"x":2}'),
                    ('prepare', b'{"profile_files":{"bad":"synthetic-secret"}}')):
                response = client.post('http://node.internal/operations/' + path,
                    content=raw, headers={'x-v3-node-token': self.token})
                self.assertEqual(200, response.status_code)
                self.assertFalse(response.json()['ok'])
                self.assertNotIn('synthetic-secret', response.text)
            oversized = client.post('http://node.internal/operations/health',
                content=b'x' * (2 * 1024 * 1024 + 1), headers={'x-v3-node-token': self.token})
            self.assertEqual(413, oversized.status_code)
        self.assertIsNone(self.host.runtime)

    def test_grant_rpc_persists_original_scope_and_closed_tombstone(self) -> None:
        """证明经真实UDS写入，关闭后保留原记录并拒绝重开。:return: None。"""
        self.assertTrue(self.call('prepare', self.fixture.request.model_dump())['ok'])
        scope = {'operation_id': 'd' * 32, 'node_key': 'a' * 32, 'account_id': 1,
            'gateway_account_id': 7, 'environment_id': 'e' * 32, 'assignment_revision': 1,
            'generation': 1, 'source': 'cli:synthetic', 'role': 'cli'}
        deadline = int(time.time()) + 25
        grant = {**scope, 'not_after': deadline, 'sequence': 1, 'lease': {'owner': scope['source'],
            'generation': 'synthetic-lease', 'expires_at': deadline, 'exclusive': False, 'shared_cli': True}}
        created = self.call('grant-create', grant)
        self.assertTrue(created['ok'], created)
        self.assertEqual('prepared', self.call('grant-get', scope)['result']['record']['phase'])
        grant['not_after'] += 1
        grant['lease']['expires_at'] += 1
        grant['sequence'] = 2
        entered, finish = threading.Event(), threading.Event()

        def slow_environment():
            with self.fixture.executor._locked(environment_id='e' * 32):
                entered.set()
                finish.wait(3)

        thread = threading.Thread(target=slow_environment, daemon=True)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            before = time.monotonic()
            self.assertTrue(self.call('grant-renew', grant)['ok'])
            self.assertLess(time.monotonic() - before, 1)
        finally:
            finish.set()
            thread.join(3)
        closed = self.call('grant-close', {**scope, 'reason': 'central_closed'})
        self.assertEqual('closed', closed['result']['record']['phase'])
        self.assertFalse(self.call('grant-renew', grant)['ok'])
        self.assertEqual('central_closed', self.call('grant-get', scope)['result']['record']['closed_reason'])
        self.assertFalse(self.call('grant-get', {**scope, 'account_id': 2})['ok'])

    def test_saturated_long_operations_keep_independent_control_capacity(self) -> None:
        """长操作占满八个槽位时，原健康/续接通道继续保留独立容量。:return: None。"""
        entered, finish = threading.Event(), threading.Event()
        lock, count = threading.Lock(), [0]

        def slow_prepare(request):
            with lock:
                count[0] += 1
                if count[0] == 8:
                    entered.set()
            finish.wait(5)
            return {'protocol': 1, 'node_key': 'a' * 32}

        with patch.object(self.fixture.executor, 'prepare', side_effect=slow_prepare), ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(self.call, 'prepare', self.fixture.request.model_dump()) for _ in range(8)]
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual('ready', self.call('health', {})['result']['state'])
                with self.assertRaises(ValueError):
                    self.call('prepare', self.fixture.request.model_dump())
            finally:
                finish.set()
            self.assertTrue(all(future.result(timeout=3)['ok'] for future in futures))


class NodeSocketBoundaryTests(unittest.TestCase):
    """独立文件锁和入口失联边界。"""

    def test_only_one_process_owns_socket_and_unknown_file_is_preserved(self) -> None:
        """独占锁防止第二服务替换socket，未知文件阻止新服务。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            with _node_socket(data):
                original = (data / 'node-agent/control.sock').stat().st_ino
                with self.assertRaises(BlockingIOError):
                    with _node_socket(data):
                        self.fail('同一节点不能启动两个控制服务')
                self.assertEqual(original, (data / 'node-agent/control.sock').stat().st_ino)
            target = data / 'node-agent/control.sock'
            target.write_bytes(b'unknown-original')
            with self.assertRaises(ValueError):
                with _node_socket(data):
                    self.fail('未知文件不能被服务覆盖')
            self.assertEqual(b'unknown-original', target.read_bytes())

    def test_exec_entry_refuses_missing_agent_before_opening_docker(self) -> None:
        """服务失联返回固定未知结果，Docker与临时运行时准入保持关闭。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            output = io.StringIO()
            incoming = type('Input', (), {'buffer': io.BytesIO(b'{}')})()
            with patch.dict(os.environ, {'V3_ROLE': 'node-control', 'BENCH_DATA': temporary, 'V3_INTERNAL_TOKEN': 'b' * 64}), \
                    patch('cluster_execution.sys.stdin', incoming), patch('cluster_execution.sys.stdout', output), \
                    patch('cluster_execution.sys.argv', ['cluster_execution.py', 'health']), \
                    patch('cluster_execution.DockerClient.from_env') as factory:
                execution_main()
            self.assertFalse(json.loads(output.getvalue())['ok'])
            factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
