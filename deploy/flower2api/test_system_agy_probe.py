"""验证合成探针失败证据的隐私、边界与首错清理。"""
import io
import json
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from source_layout import source_path

# sudo宿主验证会清除外部PYTHONPATH，先沿统一布局解析编排源码。
sys.path.insert(0, str(source_path(Path(__file__).resolve().parents[2], 'orchestrator')))
from agy_auth import SOURCE_BYTES, SOURCE_SHA256
from agy_runtime.supervisor import validate_submission
import verify_agy_runtime as probe


class ProbeFailureTests(unittest.TestCase):
    """失败诊断仅公开白名单分类与计数。"""

    def test_projects_private_fields_to_bounded_classifications(self) -> None:
        """未知字段及任意错误正文均被排除。@return 无。"""
        secret = 'synthetic-private-credential'
        container = Mock()
        container.attrs = {'State': {'Running': True, 'OOMKilled': False, 'ExitCode': 0, 'Error': secret}}
        container.logs.return_value = b'not-json\n' + json.dumps({'type': 'error',
            'code': 'worker_start_failed', 'access_token': secret}).encode() + b'\n' + json.dumps(
                {'type': secret, 'code': secret, 'body': secret}).encode()
        container.exec_run.return_value = SimpleNamespace(exit_code=0, output=json.dumps({
            'processes': {'kernel': 1, 'native': 1, secret: 1, 'observer': True},
            'stages': {'kernel_lock': 1, 'worker_config': -1, 'input_pipe': 2**80},
            'memory_events': {'oom_kill': 2, secret: secret},
            'startup_errors': {'PermissionError': 1, secret: 1}, 'private': secret}).encode())
        value = probe._failure_evidence(container, 'prepared', 1)
        self.assertNotIn(secret, json.dumps(value))
        self.assertEqual({'error': 1, 'other': 1}, value['event_counts'])
        self.assertEqual({'worker_start_failed': 1}, value['error_codes'])
        self.assertEqual({'kernel': 1, 'native': 1}, value['runtime']['processes'])
        self.assertEqual({'kernel_lock': 1}, value['runtime']['stages'])
        self.assertEqual({'oom_kill': 2}, value['runtime']['memory_events'])
        self.assertEqual({'PermissionError': 1}, value['runtime']['startup_errors'])
        self.assertLess(len(json.dumps(value)), 2048)
        arguments = container.exec_run.call_args.args[0]
        compile(arguments[-1], '<固定诊断子进程>', 'exec')
        self.assertEqual('1001:1001', container.exec_run.call_args.kwargs['user'])

    def test_capture_failures_are_separate_and_do_not_export_exception_text(self) -> None:
        """采集失败分类有界且保持脱敏。@return 无。"""
        container = Mock()
        container.reload.side_effect = OSError('synthetic-private-path')
        container.logs.side_effect = OSError('synthetic-private-token')
        container.exec_run.return_value = SimpleNamespace(exit_code=0, output=b'x' * 8193)
        value = probe._failure_evidence(container, 'prepared', 1)
        self.assertEqual(['state', 'events', 'runtime'], value['capture_failed'])
        self.assertNotIn('synthetic-private', json.dumps(value))

    def test_original_failure_and_container_cleanup_survive_diagnostic_failure(self) -> None:
        """诊断故障不能覆盖原始异常或跳过容器清理。@return 无。"""
        import docker
        client, container = Mock(), Mock()
        client.containers.run.return_value = container
        original = ValueError('合成原始验证错误')
        container.attach_socket.side_effect = original
        with patch.object(docker, 'from_env', return_value=client), \
                patch.object(probe, '_failure_evidence', side_effect=OSError('合成采集失败')), \
                patch.object(probe.os, 'chown'), patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaises(ValueError) as caught:
                probe.native_probe('synthetic-image', image_package=True)
        self.assertIs(original, caught.exception)
        container.remove.assert_called_once_with(force=True)

    def test_logs_and_runtime_output_have_independent_budgets(self) -> None:
        """超量日志和损坏子进程输出保持有界摘要。@return 无。"""
        container = Mock()
        container.attrs = {'State': {}}
        container.logs.return_value = b'x' * 65536 + b'\n{"type":"supervisor_ready"}\n'
        container.exec_run.return_value = SimpleNamespace(exit_code=1, output=b'private-output')
        value = probe._failure_evidence(container, 'prepared', 1)
        self.assertEqual({'supervisor_ready': 1}, value['event_counts'])
        self.assertEqual(['runtime'], value['capture_failed'])
        self.assertLess(len(json.dumps(value)), 2048)

    def test_cleanup_failures_preserve_original_and_attempt_remaining_resources(self) -> None:
        """连接及容器清理异常后，临时状态和客户端仍收口。@return 无。"""
        import docker
        client, container, connection = Mock(), Mock(), Mock()
        client.containers.run.return_value = container
        container.attach_socket.return_value = connection
        original = ValueError('合成首错')
        connection._sock.settimeout.side_effect = original
        connection.close.side_effect = OSError('合成关闭失败')
        container.remove.side_effect = OSError('合成回收失败')
        with patch.object(docker, 'from_env', return_value=client), \
                patch.object(probe, '_failure_evidence', return_value={'event': 'agy-probe-failure'}), \
                patch.object(probe.os, 'chown'), \
                patch.object(probe.shutil, 'rmtree', wraps=probe.shutil.rmtree) as cleanup, \
                patch('sys.stderr', new_callable=io.StringIO) as output:
            with self.assertRaises(ValueError) as caught:
                probe.native_probe('synthetic-image', image_package=True)
        self.assertIs(original, caught.exception)
        cleanup.assert_called_once()
        client.close.assert_called_once()
        self.assertFalse(cleanup.call_args.args[0].exists())
        last = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(['connection', 'container'], last['steps'])

    def test_client_connection_failure_still_removes_temporary_state(self) -> None:
        """Docker客户端建立失败时也回收已创建状态目录。@return 无。"""
        import docker
        original = OSError('合成客户端失败')
        with patch.object(docker, 'from_env', side_effect=original), \
                patch.object(probe.shutil, 'rmtree', wraps=probe.shutil.rmtree) as cleanup:
            with self.assertRaises(OSError) as caught:
                probe.native_probe('synthetic-image', image_package=True)
        self.assertIs(original, caught.exception)
        cleanup.assert_called_once()
        self.assertFalse(cleanup.call_args.args[0].exists())

    def test_prepare_envelopes_fit_runtime_deadline_and_startup_budget(self) -> None:
        """实际探针信封通过真实运行时校验，预算覆盖既有启动窗口。@return 无。"""
        import docker
        client, container, connection = Mock(), Mock(), Mock()
        client.containers.run.return_value = container
        container.attach_socket.return_value = connection
        events = [{'type': 'supervisor_ready'}]
        submissions = []

        def transmit(raw):
            """模拟版本化响应并以真实合同核对准备输入。@param raw 原始探针信封。@return 无。"""
            value = json.loads(raw)
            if value['type'] == 'prepare':
                validate_submission(value, {'account_id': 17, 'environment_id': 'synthetic-env', 'environment_generation': 2})
                remaining = value['deadline_unix_ms'] / 1000 - time.time()
                self.assertGreater(remaining, 90)
                self.assertLessEqual(remaining, 120)
                submissions.append(value)
                events.extend([{'type': 'prepared', 'request_id': value['request_id'], 'native': {
                    'observer_pid': 4, 'native_pid': 5, 'source_sha256': SOURCE_SHA256}},
                    {'type': 'job_finalized', 'request_id': value['request_id']}])
            elif value['type'] == 'status':
                events.append({'type': 'status', 'request_id': value['request_id'], 'status': {
                    'image_decode_calls': 1, 'workers': 1, 'active': 0,
                    'controller': {'pid': 2}, 'processes': [{'controller': {'pid': 3}}],
                    'image_scope': 'account_workers', 'image_bytes': SOURCE_BYTES, 'cgroup_memory': {}}})

        connection._sock.sendall.side_effect = transmit
        container.logs.side_effect = lambda **kwargs: b'\n'.join(json.dumps(event).encode() for event in events)
        container.exec_run.return_value = SimpleNamespace(exit_code=0, output=b'{"terminated":true}')
        with patch.object(docker, 'from_env', return_value=client), patch.object(probe.os, 'chown'):
            result = probe.native_probe('synthetic-image', image_package=True)
        self.assertEqual([1, 2], [value['credential_snapshot']['credential_generation'] for value in submissions])
        self.assertEqual(2, len(result['prepare_seconds']))
        self.assertTrue(result['passed'])
        self.assertTrue(result['terminated'])
