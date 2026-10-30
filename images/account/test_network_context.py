"""账号网络上下文进程收口测试。"""
import importlib.util
import io
import json
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_diagnostics import NETWORK_FAILURE_PREFIX


SPEC = importlib.util.spec_from_file_location("network_context", Path(__file__).with_name("network-context.py"))
network_context = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(network_context)


class NetworkContextTests(unittest.TestCase):
    """验证已知监听器可强制收口，未知 PID 不会被误杀。"""

    def test_process_exiting_after_proc_open_is_already_stopped(self) -> None:
        """真实进程在读取前退出时，ESRCH 与路径消失都表示原进程已结束。:return: None。"""
        original_open = Path.open
        for filename in ('cmdline', 'stat'):
            with self.subTest(proc_file=filename):
                process = subprocess.Popen(['sleep', '30'])
                try:
                    started = Path(f'/proc/{process.pid}/stat').read_text().split()[21]
                    target = Path(f'/proc/{process.pid}/{filename}')

                    def open_then_exit(path, *args, **kwargs):
                        """让内核返回已退出进程的真实读取错误，而非模拟异常。:return: 已打开文件。"""
                        stream = original_open(path, *args, **kwargs)
                        if path == target:
                            process.terminate()
                            process.wait(timeout=2)
                        return stream

                    with patch.object(Path, 'open', open_then_exit):
                        result = (network_context._listener_identity(process.pid) if filename == 'cmdline'
                            else network_context._owned_process_state(process.pid, started))
                    self.assertIsNone(result)
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=2)

    def test_listener_ignoring_term_is_killed(self) -> None:
        """已知 relay 忽略 SIGTERM 时升级为 SIGKILL。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            process = subprocess.Popen(["bash", "-c", "trap '' TERM; exec -a v3-passthrough-fixture sleep 30"])
            self.addCleanup(lambda: process.poll() is None and process.kill())
            deadline = time.monotonic() + 2
            while Path(f"/proc/{process.pid}/cmdline").read_bytes().split(b"\0", 1)[0] != b"v3-passthrough-fixture":
                if time.monotonic() >= deadline:
                    self.fail("合成 relay 未进入目标进程")
                time.sleep(0.01)
            pid_file = Path(temporary) / "network.pid"
            pid_file.write_text(str(process.pid))
            self.assertFalse(network_context._terminate_listener(pid_file))
            process.wait(timeout=2)
            self.assertEqual(-signal.SIGKILL, process.returncode)
            self.assertFalse(pid_file.exists())

    def test_unknown_pid_is_refused_without_killing_process(self) -> None:
        """PID 指向无关进程时失败关闭并保留该进程。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            process = subprocess.Popen(["sleep", "30"])
            self.addCleanup(lambda: process.poll() is None and process.kill())
            pid_file = Path(temporary) / "network.pid"
            pid_file.write_text(str(process.pid))
            with self.assertRaisesRegex(RuntimeError, "未知进程"):
                network_context._terminate_listener(pid_file)
            self.assertIsNone(process.poll())
            process.terminate()
            process.wait(timeout=2)

    def test_ca_failure_is_reported_before_cleanup_without_socket_retries(self) -> None:
        """CA 写盘错误不能被连接重试吞掉，私有记录保留 errno 且不含秘密。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'context.json').write_text(json.dumps({'NETWORK_INSPECTION_MODE': 'capture',
                'QUOTA_SOURCE': 'projects:fixture:2'}))
            stream = io.StringIO()
            process = type('ProcessFixture', (), {'pid': 42, 'poll': lambda self: None})()
            with patch.object(network_context, 'Path', side_effect=lambda value: root if value == '/run/v3' else Path(value)), \
                    patch.object(network_context, 'open', side_effect=lambda name, mode: (root / 'listener.log').open(mode), create=True), \
                    patch.object(network_context, '_restore_capture_ca'), \
                    patch.object(network_context.subprocess, 'Popen', return_value=process), \
                    patch.object(network_context.socket, 'create_connection') as connect, \
                    patch.object(network_context, '_publish_capture_ca', side_effect=OSError(28, 'synthetic-secret')) as publish, \
                    patch.object(sys, 'stderr', stream), patch.object(sys, 'argv', ['network-context.py']):
                with self.assertRaises(SystemExit) as raised:
                    network_context.main()
            self.assertEqual(1, raised.exception.code)
            self.assertEqual(1, publish.call_count)
            self.assertEqual(1, connect.call_count)
            record = json.loads(next((root / 'diagnostics').glob('*.json')).read_text())
            self.assertEqual('publish_ca', record['phase'])
            self.assertEqual(28, record['exceptions'][0]['errno'])
            self.assertNotIn('synthetic-secret', stream.getvalue())
            self.assertTrue(stream.getvalue().startswith(NETWORK_FAILURE_PREFIX))

    def test_capture_metadata_reaches_actual_child_environment_only_via_allowlist(self) -> None:
        """真实子进程收到冻结 JSON；不支持的上下文不能混入环境。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = json.dumps({'schema': 1, 'source': 'projects:fixture:2', 'namespace': 'projects',
                'work_id': 'fixture', 'claude_code_version': '2.1.303'})
            (root / 'context.json').write_text(json.dumps({'NETWORK_INSPECTION_MODE': 'capture',
                'QUOTA_SOURCE': 'projects:fixture:2', 'CAPTURE_CONTEXT': metadata,
                'CAPTURE_FULL_HTTP': '1', 'STATS_FILE': '/flows/fixture/stats.jsonl',
                'UNSUPPORTED_CAPTURE_KEY': 'private-test-only'}))
            output = root / 'child-environment.json'
            actual_popen = subprocess.Popen
            processes = []

            def spawn(command, **kwargs):
                """只替换监听程序，仍由操作系统传递生产组装的子进程环境。:return: 真实子进程。"""
                script = ('import json,os,sys,time; from pathlib import Path; '
                    'Path(sys.argv[1]).write_text(json.dumps({key:os.environ.get(key) for key in '
                    '["CAPTURE_CONTEXT","QUOTA_SOURCE","CAPTURE_FULL_HTTP","UNSUPPORTED_CAPTURE_KEY"]})); time.sleep(30)')
                process = actual_popen([sys.executable, '-c', script, str(output)], **kwargs)
                processes.append(process)
                return process

            try:
                with patch.object(network_context, 'Path', side_effect=lambda value: root if value == '/run/v3' else Path(value)), \
                        patch.object(network_context, 'open', side_effect=lambda name, mode: (root / 'listener.log').open(mode), create=True), \
                        patch.object(network_context.subprocess, 'Popen', side_effect=spawn), \
                        patch.object(network_context, '_restore_capture_ca'), patch.object(network_context, '_publish_capture_ca'), \
                        patch.object(network_context, '_listener_identity', return_value=('S', 'synthetic-start')), \
                        patch.object(network_context.socket, 'create_connection'), patch.object(sys, 'argv', ['network-context.py']):
                    network_context.main()
                deadline = time.monotonic() + 3
                while not output.is_file() and time.monotonic() < deadline:
                    time.sleep(0.01)
                captured = json.loads(output.read_text())
                self.assertEqual(metadata, captured['CAPTURE_CONTEXT'])
                self.assertEqual('projects:fixture:2', captured['QUOTA_SOURCE'])
                self.assertEqual('1', captured['CAPTURE_FULL_HTTP'])
                self.assertIsNone(captured['UNSUPPORTED_CAPTURE_KEY'])
                self.assertEqual('projects:fixture:2', json.loads((root / 'context-ack.json').read_text())['QUOTA_SOURCE'])
            finally:
                for process in processes:
                    process.terminate()
                    process.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
