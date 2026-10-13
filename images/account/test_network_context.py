"""账号网络上下文进程收口测试。"""
import importlib.util
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("network_context", Path(__file__).with_name("network-context.py"))
network_context = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(network_context)


class NetworkContextTests(unittest.TestCase):
    """验证已知监听器可强制收口，未知 PID 不会被误杀。"""

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
            network_context._terminate_listener(pid_file)
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


if __name__ == "__main__":
    unittest.main()
