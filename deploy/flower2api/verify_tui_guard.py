"""用合成会话核对实际 TUI 文件规则和隔离初始化。"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from ctypes import CDLL, c_int, c_ushort
import errno
import os
from pathlib import Path
from shlex import split
import socket
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase, main


HERE = Path(__file__).resolve().parent
GUARD_SOURCE = HERE.parents[1] / "images/account/tui_guard.c"
CONNECT_SOURCE = GUARD_SOURCE.with_name("tui_connect.c")
SESSION_PROGRAM = Path("/usr/bin/python3")
SAVE = """
import errno
import os
from pathlib import Path
import sys

own, peer, runtime = map(Path, sys.argv[1:4])
session = own.name
config = own / 'config'
temporary = own / 'config.tmp'
temporary.write_bytes(b'saved-config')
if os.environ.get('TUI_GUARD_TEST_ABI') == '2':
    try:
        os.truncate(temporary, 1)
    except PermissionError:
        assert temporary.read_bytes() == b'saved-config'
    else:
        sys.exit('兼容分支意外开放路径截短')
with temporary.open('r+b') as stream:
    stream.truncate(5)
temporary.replace(config)
(own / 'history').write_text(f'{session}-history', encoding='utf-8')
assert Path('shared.txt').read_text(encoding='utf-8') == 'shared-project'
Path(f'{session}.txt').write_text(f'{session}-project', encoding='utf-8')
for private_path in (peer / 'config', peer / 'history', runtime):
    for access in (os.O_RDONLY, os.O_WRONLY):
        try:
            descriptor = os.open(private_path, access)
        except PermissionError:
            continue
        os.close(descriptor)
        sys.exit(f'私有文件意外开放 {private_path.name}')
try:
    os.fstat(int(sys.argv[4]))
except OSError as error:
    if error.errno != errno.EBADF:
        raise
else:
    sys.exit('继承的文件描述符意外保留')
print('保存完成')
"""
NETWORK = """
import ctypes
import errno
import os
import socket
import struct
import sys

port = int(sys.argv[1])
target = ('127.0.0.1', port)
def denied(operation):
    try:
        operation()
    except OSError as error:
        assert error.errno == errno.EPERM, error
    else:
        raise AssertionError('未授权的套接字操作成功')

denied(lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
denied(lambda: socket.socket(socket.AF_INET6, socket.SOCK_STREAM))
denied(lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
with socket.socket() as tcp:
    address = struct.pack('=H', socket.AF_INET) + struct.pack('!H', port) + socket.inet_aton(target[0]) + bytes(8)
    connect_syscalls = {'x86_64': 42, 'aarch64': 203}
    libc = ctypes.CDLL(None, use_errno=True)
    assert libc.syscall(connect_syscalls[os.uname().machine], tcp.fileno(), address, len(address)) == -1
    assert ctypes.get_errno() == errno.EPERM
    denied(lambda: tcp.connect(('127.0.0.2', port)))
    denied(lambda: tcp.connect(('127.0.0.1', int(sys.argv[2]))))
    tcp.settimeout(2)
    tcp.connect(target)
    tcp.sendall(b'ok')
    assert tcp.recv(2) == b'ok'
print('回环隔离完成')
"""


class GuardTests(TestCase):
    """编译真实隔离程序，另用独立测试产物选择兼容分支。"""

    @classmethod
    def setUpClass(cls):
        """编译原版和带探测桩的产物。@return 无。"""
        root = Path(cls.enterClassContext(TemporaryDirectory(prefix="flower-tui-guard-")))
        cls.native = root / "tui-guard"
        cls.probe = root / "tui-guard-probe"
        cls.shim = root / "tui-connect.so"
        compiler = split(os.environ.get("CC", "cc"))
        compiler += split(os.environ.get("CPPFLAGS", ""))
        compiler += ["-O2", "-Wall", "-Wextra", "-Werror", "-Wl,-z,relro,-z,now"]
        subprocess.run([*compiler, "-fPIC", "-shared", CONNECT_SOURCE, "-o", cls.shim], check=True)
        compiler += [f'-DCONNECT_SHIM="{cls.shim}"', str(GUARD_SOURCE)]
        libraries = split(os.environ.get("LDLIBS", "-lseccomp"))
        subprocess.run([*compiler, "-o", cls.native, *libraries], check=True)
        subprocess.run(
            [
                *compiler, HERE / "tui_guard_test_probe.c", "-Wl,--wrap=syscall,--wrap=seccomp_load",
                "-o", cls.probe, *libraries,
            ],
            check=True,
        )

    def setUp(self):
        """建立共用工作区、两个私有 HOME 和独立的合成运行时文件。@return 无。"""
        self.root = Path(self.enterContext(TemporaryDirectory(prefix="flower-tui-private-")))
        self.work, self.mod, self.first, self.second = (
            self.root / name for name in ("project", "mod", "first", "second")
        )
        for directory in (self.work, self.mod, self.first, self.second):
            directory.mkdir()
        for home in (self.first, self.second):
            (home / "config").write_bytes(home.name.encode())
            (home / "history").write_bytes(home.name.encode())
        self.runtime = self.root / "sender-state"
        self.runtime.write_bytes(b"synthetic-sender-state")

    def _ready(self, guard, environment=None):
        return subprocess.run(
            [guard, "--check"], cwd=self.work, env=environment, capture_output=True, timeout=5,
        )

    def _save(self, guard, home, peer, environment, expected=0):
        with ExitStack() as stack:
            master, terminal = os.openpty()
            stack.callback(os.close, master)
            with ExitStack() as launch:
                launch.callback(os.close, terminal)
                inherited = launch.enter_context(self.runtime.open("rb"))
                program = launch.enter_context(SESSION_PROGRAM.open("rb"))
                child = subprocess.run(
                    [guard, home, self.mod, f"/proc/self/fd/{program.fileno()}", "-I", "-S", "-B", "-c", SAVE,
                     home, peer, self.runtime, str(inherited.fileno())],
                    cwd=self.work, env=environment, stdin=terminal, stdout=terminal, stderr=terminal,
                    pass_fds=(program.fileno(), inherited.fileno()), timeout=5,
                )
            try:
                output = os.read(master, 4096).decode(errors="replace")
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                output = ""
        self.assertEqual(child.returncode, expected, output)
        if expected == 0:
            self.assertIn("保存完成", output)

    def _verify_sessions(self, guard, environment=None):
        (self.work / "shared.txt").write_text("shared-project")
        ready = self._ready(guard, environment)
        self.assertEqual(ready.returncode, 0, ready.stderr)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self._save, guard, self.first, self.second, environment)
            second = pool.submit(self._save, guard, self.second, self.first, environment)
            first.result()
            second.result()
        for home in (self.first, self.second):
            self.assertEqual((home / "config").read_bytes(), b"saved")
            self.assertEqual((home / "history").read_text(), f"{home.name}-history")
            self.assertEqual((self.work / f"{home.name}.txt").read_text(), f"{home.name}-project")
        self.assertEqual(self.runtime.read_bytes(), b"synthetic-sender-state")

    def test_native(self):
        """在当前真实内核核验就绪、保存与会话隔离。@return 无。"""
        self._verify_sessions(self.native)

    def test_abi2_selection(self):
        """选择兼容分支，在当前内核执行其规则并保存会话。@return 无。"""
        self._verify_sessions(self.probe, {**os.environ, "TUI_GUARD_TEST_ABI": "2"})

    def test_abi1_and_failed_load_close(self):
        """在能力不足或策略安装失败时拒绝就绪和执行。@return 无。"""
        for options in ({"TUI_GUARD_TEST_ABI": "1"},
                        {"TUI_GUARD_TEST_ABI": "2", "TUI_GUARD_TEST_LOAD_FAILURE": "1"}):
            with self.subTest(options=options):
                environment = {**os.environ, **options}
                self.assertEqual(self._ready(self.probe, environment).returncode, 125)
                self._save(self.probe, self.first, self.second, environment, expected=125)
                self.assertEqual((self.first / "config").read_bytes(), b"first")
                self.assertEqual(list(self.work.iterdir()), [])

    def test_abi2_requires_terminal(self):
        """禁止把普通文件继承为 ABI 2 会话的标准输出。@return 无。"""
        with ExitStack() as stack:
            master, terminal = os.openpty()
            stack.callback(os.close, master)
            stack.callback(os.close, terminal)
            output = stack.enter_context(self.runtime.open("r+b"))
            child = subprocess.run(
                [self.probe, self.first, self.mod, SESSION_PROGRAM, "-c", "raise SystemExit(1)"],
                cwd=self.work, env={**os.environ, "TUI_GUARD_TEST_ABI": "2"},
                stdin=terminal, stdout=output, stderr=terminal, timeout=5,
            )
            self.assertEqual(child.returncode, 125)
        self.assertEqual(self.runtime.read_bytes(), b"synthetic-sender-state")

    def test_oauth_connections_stay_on_the_session_loopback(self):
        """用真实连接和直接系统调用核验当前与 ABI 2 兼容分支。@return 无。"""
        serve = CDLL(str(self.shim)).tui_run_loopback_broker
        serve.argtypes = [c_int, c_ushort]
        serve.restype = c_int
        for guard, environment in ((self.native, os.environ),
                                   (self.probe, {**os.environ, "TUI_GUARD_TEST_ABI": "2"})):
            with self.subTest(guard=guard), ExitStack() as stack:
                allowed = stack.enter_context(socket.socket())
                peer = stack.enter_context(socket.socket())
                for listener in (allowed, peer):
                    listener.bind(("127.0.0.1", 0))
                    listener.listen()
                    listener.settimeout(5)
                def echo():
                    client, _ = allowed.accept()
                    with client:
                        client.settimeout(2)
                        client.sendall(client.recv(2))
                port = allowed.getsockname()[1]
                client, broker = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                stack.callback(broker.close)
                pool = stack.enter_context(ThreadPoolExecutor(max_workers=2))
                answering = pool.submit(echo)
                running = pool.submit(serve, broker.fileno(), port)
                master, terminal = os.openpty()
                stack.callback(os.close, master)
                try:
                    child = subprocess.run(
                        [guard, "--oauth-loopback", str(port), str(client.fileno()), self.first,
                         self.mod, SESSION_PROGRAM, "-I", "-S", "-B", "-c", NETWORK,
                         str(port), str(peer.getsockname()[1])],
                        cwd=self.work, env=environment, stdin=terminal, stdout=terminal,
                        stderr=terminal, pass_fds=(client.fileno(),), timeout=5,
                    )
                finally:
                    os.close(terminal)
                    client.close()
                output = os.read(master, 4096).decode(errors="replace")
                self.assertEqual(child.returncode, 0, output)
                answering.result()
                self.assertEqual(running.result(timeout=3), 0)
                self.assertIn("回环隔离完成", output)


if __name__ == "__main__":
    main()
