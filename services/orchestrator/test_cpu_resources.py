"""CPU在线调整的归属、并发、失败恢复与私有持久策略验证。"""
import json
import tempfile
import unittest
from decimal import localcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from docker import APIClient

from cpu_resources import default_cpu_limits, read_policy, read_resources, set_resources, _update_cpu
from runtime_files import atomic_json


class CpuResourcesTests(unittest.TestCase):
    """使用实际角色归属校验和可注入未知结果的Docker边界。"""

    def test_independent_defaults_ignore_legacy_total_and_validate_overrides(self):
        """三角色缺省独立，非法覆盖在容器创建前拒绝。@return 无。"""
        defaults = {'cli': 1500000000, 'sender': 1500000000, 'network': 500000000}
        self.assertEqual(default_cpu_limits({'V3_ACCOUNT_CPUS': '2'}), defaults)
        self.assertEqual(default_cpu_limits({'V3_ACCOUNT_SENDER_CPUS': '2.25'}), {**defaults, 'sender': 2250000000})
        self.assertEqual(default_cpu_limits({'V3_ACCOUNT_SENDER_CPUS': ''}), defaults)
        for value in (False, None, 0, 'NaN', 'Infinity', '-1', '0.001', '1.0000000001', 'invalid'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                default_cpu_limits({'V3_ACCOUNT_SENDER_CPUS': value})

    def test_default_cpu_precision_is_exact_under_decimal_context_changes(self):
        """超长小数精确拒绝，合法纳核值不受Decimal上下文精度影响。@return 无。"""
        for precision in (3, 28):
            with self.subTest(precision=precision), localcontext() as context:
                context.prec = precision
                for value, expected in (('1.000000001', 1000000001),
                        ('1.0000000010000000000000000000', 1000000001), ('1e-2', 10000000)):
                    self.assertEqual(default_cpu_limits({'V3_ACCOUNT_SENDER_CPUS': value})['sender'], expected)
                for value in ('1.0000000000000000000000000001', '1.0000000009999999999999999999'):
                    with self.subTest(value=value), self.assertRaises(ValueError):
                        default_cpu_limits({'V3_ACCOUNT_SENDER_CPUS': value})

    def setUp(self):
        """建立固定三角色测试环境。@return None。"""
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.environment = {'environment_id': 'a' * 32, 'account_id': 7, 'generation': 14,
            'isolation_version': 2, 'state': 'ready', 'container_id': 'cli-id',
            'sender_container_id': 'sender-id', 'network_container_id': 'network-id'}
        self.containers = {}
        labels = {'vibebench.product': 'v3', 'vibebench.deployment': 'test',
            'vibebench.environment': self.environment['environment_id']}
        for role, label, cpu in [('cli', 'account', 1500000000), ('sender', 'account-sender', 250000000), ('network', 'account-network', 250000000)]:
            container = SimpleNamespace(id=role+'-id', labels={**labels, 'vibebench.role': label,
                'vibebench.isolation-version': '2', 'vibebench.release': 'test-release'}, calls=[], fail=False)
            container.attrs = {'Image': 'synthetic-image', 'HostConfig': {'NanoCpus': cpu, 'Memory': 100,
                'MemorySwap': 200, 'PidsLimit': 128}, 'State': {'StartedAt': 'synthetic-start'}, 'RestartCount': 0}
            container.reload = lambda: None
            def update(*, nano_cpus, current=container):
                current.calls.append(nano_cpus)
                current.attrs['HostConfig']['NanoCpus'] = nano_cpus
                if current.fail:
                    current.fail = False
                    raise RuntimeError('模拟Docker已生效但返回失败')
            container.update = update
            self.containers[role+'-id'] = container
        self.runtime = SimpleNamespace(release_id='test-release', _root=lambda row: self.root,
            reviews=SimpleNamespace(serial_state=lambda row: None),
            _labels=lambda row: labels, client=SimpleNamespace(info=lambda: {'NCPU': 4},
                containers=SimpleNamespace(get=self.containers.__getitem__)))
        self.runtime.client.api = SimpleNamespace(_url=lambda path, identifier: identifier,
            _post_json=lambda identifier, data: self.containers[identifier].update(nano_cpus=data['NanoCpus']),
            _result=lambda response, parsed: response)
        self.addCleanup(patch.stopall)
        patch.dict('os.environ', {'V3_UPDATE_GATE_DIR': ''}).start()
        patch('native_kernel_upgrade.status', return_value={'state': 'idle'}).start()

    def test_individual_quotas_can_exceed_three_in_total_and_persist(self):
        """合计超3核合法，实际额度与持久策略一致。@return None。"""
        before = read_resources(self.runtime, self.environment)
        after = set_resources(self.runtime, self.environment, 14, before['revision'], {'cli': 2, 'sender': 2, 'network': 2})
        self.assertEqual(after['cpus'], {'cli': 2, 'sender': 2, 'network': 2})
        self.assertEqual(after['persisted_cpus'], after['cpus'])
        self.assertNotEqual(after['revision'], before['revision'])
        self.assertEqual(read_policy(self.runtime, self.environment)['nano_cpus']['sender'], 2000000000)
        for container in self.containers.values():
            self.assertEqual(container.attrs['HostConfig']['Memory'], 100)
            self.assertEqual(container.attrs['State']['StartedAt'], 'synthetic-start')
        with self.assertRaisesRegex(ValueError, '已变化'):
            set_resources(self.runtime, self.environment, 14, before['revision'], before['cpus'])
        self.assertTrue(all(len(c.calls) == 1 for c in self.containers.values()))

    def test_unknown_update_result_restores_all_attempted_roles(self):
        """异常返回仍按可能生效恢复，保持原持久策略。@return None。"""
        before = read_resources(self.runtime, self.environment)
        self.containers['sender-id'].fail = True
        with self.assertRaisesRegex(RuntimeError, '已恢复'):
            set_resources(self.runtime, self.environment, 14, before['revision'], {'cli': 2, 'sender': 1, 'network': 0.5})
        self.assertEqual(read_resources(self.runtime, self.environment), before)
        self.assertIsNone(read_policy(self.runtime, self.environment))
        self.assertEqual(json.loads((self.root/'runtime/cpu-resources-operation.json').read_text())['state'], 'restored')

    def test_review_handoff_rejects_cpu_changes_before_docker_update(self):
        """交接期间保持已冻结的CLI及评审恢复额度。@return None。"""
        before = read_resources(self.runtime, self.environment)
        self.runtime.reviews.serial_state = lambda row: {'phase': 'review_running'}
        with self.assertRaisesRegex(ValueError, '评审资源正在交接'):
            set_resources(self.runtime, self.environment, 14, before['revision'], {'cli': 2, 'sender': 2, 'network': 2})
        self.assertEqual(read_resources(self.runtime, self.environment), before)
        self.assertTrue(all(not c.calls for c in self.containers.values()))

    def test_invalid_values_and_wrong_ownership_do_not_apply(self):
        """非法数值和错误归属在Docker更新前拒绝。@return None。"""
        before = read_resources(self.runtime, self.environment)
        for value in [True, float('nan'), float('inf'), -1, 0, 0.001, 5]:
            with self.assertRaises(ValueError):
                set_resources(self.runtime, self.environment, 14, before['revision'], {'cli': value, 'sender': 1, 'network': 0.5})
        self.assertTrue(all(not c.calls for c in self.containers.values()))
        self.containers['sender-id'].labels['vibebench.environment'] = 'other'
        with self.assertRaisesRegex(ValueError, '归属'):
            read_resources(self.runtime, self.environment)

    def test_real_docker_sdk_sends_only_the_supported_nano_cpu_json(self):
        """真实SDK的JSON边界包含NanoCpus，不依赖不存在的update参数。@return None。"""
        observed = []
        class Handler(BaseHTTPRequestHandler):
            """只在回环接收Docker JSON的合成接口。"""
            def do_POST(self):
                """读取合成Docker更新请求并返回受控结果。@return None。"""
                observed.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                raw = b'{"Warnings":[]}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def log_message(self, *arguments):
                """关闭回环服务的普通访问日志。@return None。"""
                return
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        api = APIClient(base_url=f'http://127.0.0.1:{server.server_port}', version='1.45')
        api.trust_env = False
        try:
            runtime = SimpleNamespace(client=SimpleNamespace(api=api))
            _update_cpu(runtime, self.containers['sender-id'], 1000000000)
            self.assertEqual(observed, [('/v1.45/containers/sender-id/update', {'NanoCpus': 1000000000})])
        finally:
            api.close()
            server.shutdown()
            thread.join()
            server.server_close()

    def test_corrupt_linked_and_wrong_environment_policy_are_rejected(self):
        """策略损坏、链接及跨环境文件均失败关闭。@return None。"""
        path = self.root/'runtime/cpu-resources.json'
        atomic_json(path, {'schema_version': 1})
        with self.assertRaises(ValueError):
            read_policy(self.runtime, self.environment)
        path.unlink()
        target = self.root/'other.json'
        atomic_json(target, {})
        path.symlink_to(target)
        with self.assertRaises(OSError):
            read_policy(self.runtime, self.environment)
