"""使用隔离回环 sshd 验证真实认证、主机指纹和 Unix socket 隧道。"""
from __future__ import annotations

import os
import json
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from docker import DockerClient

from cluster_nodes import NodeAddress, NodeConfiguration
from cluster_ssh import NodeSshError, SshNode, _run, probe_host_keys
from system_update_gate import read_gate


class _Echo(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        while data := self.request.recv(65536):
            self.request.sendall(data)


class _DockerEndpoint(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        method, path, _ = self.rfile.readline().decode().split()
        while line := self.rfile.readline():
            if line in (b'\r\n', b'\n'):
                break
        if path == '/version':
            value = {'ApiVersion': '1.45', 'MinAPIVersion': '1.24', 'Version': 'synthetic'}
        else:
            value = {'Name': 'ssh-loopback-docker', 'ServerVersion': 'synthetic', 'NCPU': 2}
        body = json.dumps(value).encode()
        self.wfile.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: '
            + str(len(body)).encode() + b'\r\n\r\n' + body)


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('sshd') and shutil.which('ssh-keygen'),
    '真实 SSH 集成验证需要隔离开发环境的 sshd 和 root')
class ClusterSshTests(unittest.TestCase):
    """不读取用户密钥、不连接外部节点的本地真实 SSH 验证。"""

    def setUp(self) -> None:
        """启动使用临时密钥和配置的本地 sshd。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.host = self.root / 'host'
        self.identity = self.root / 'identity'
        for key in (self.host, self.identity):
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)],
                check=True, capture_output=True)
        self.authorized = self.root / 'authorized_keys'
        self.authorized.write_text(self.identity.with_suffix('.pub').read_text())
        self.authorized.chmod(0o600)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        privilege = Path('/run/sshd')
        if not privilege.exists():
            privilege.mkdir(mode=0o755)
            self.addCleanup(privilege.rmdir)
        configuration = self.root / 'sshd_config'
        configuration.write_text(f'''Port {self.port}
ListenAddress 127.0.0.1
HostKey {self.host}
PidFile {self.root / 'sshd.pid'}
AuthorizedKeysFile {self.authorized}
StrictModes no
PermitRootLogin yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
UsePAM yes
AllowUsers root
AllowTcpForwarding yes
AllowStreamLocalForwarding yes
LogLevel QUIET
''')
        self.server = subprocess.Popen([shutil.which('sshd'), '-D', '-e', '-f', str(configuration)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self._stop_server)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                self.fail('隔离 sshd 提前退出')
            try:
                with socket.create_connection(('127.0.0.1', self.port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.025)
        else:
            self.fail('隔离 sshd 未监听')
        self.config = NodeConfiguration(name='回环测试节点', host='127.0.0.1', port=self.port,
            username='root', host_key=' '.join(self.host.with_suffix('.pub').read_text().split()[:2]),
            data_root='/srv/synthetic-node')
        self.node = SshNode('a' * 32, self.config, self.root / 'private', self.root / 'transport')
        self.node.save_identity(self.identity.read_text())
        self.addCleanup(self.node.close)

    def _stop_server(self) -> None:
        self.server.terminate()
        try:
            self.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.server.kill()
            self.server.wait(timeout=5)

    def test_probe_and_key_authentication_use_the_expected_host(self) -> None:
        """候选主机公钥匹配，专用密钥能够完成真实命令执行。:return: None。"""
        keys = probe_host_keys(NodeAddress(host='127.0.0.1', port=self.port))
        self.assertIn(self.config.host_key, [key['key'] for key in keys])
        result = _run(self.node._arguments() + ['--', '127.0.0.1', 'printf ssh-verified'])
        self.assertEqual(b'ssh-verified', result)

    def test_mismatched_host_key_is_rejected_before_command_execution(self) -> None:
        """实际主机与已确认公钥不一致时拒绝远程命令。:return: None。"""
        wrong = NodeConfiguration(**{**self.config.model_dump(),
            'host_key': ' '.join(self.identity.with_suffix('.pub').read_text().split()[:2])})
        node = SshNode('b' * 32, wrong, self.root / 'private', self.root / 'transport')
        self.addCleanup(node.close)
        node.save_identity(self.identity.read_text())
        with self.assertRaises(NodeSshError) as failure:
            _run(node._arguments() + ['--', '127.0.0.1', 'printf should-not-run'])
        self.assertEqual('host_key_mismatch', failure.exception.reason)

    def test_unix_forwarding_preserves_bytes_and_closes_owned_processes(self) -> None:
        """跨真实 SSH 的Unix隧道双向逐字传输并按归属释放。:return: None。"""
        remote = self.root / 'remote.sock'
        server = socketserver.ThreadingUnixStreamServer(str(remote), _Echo)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        local = self.node._forward('docker', str(remote))
        self.assertEqual(0o600, local.stat().st_mode & 0o777)
        self.assertEqual(local, self.node._forward('docker', str(remote)))
        with socket.socket(socket.AF_UNIX) as stream:
            stream.settimeout(5)
            stream.connect(str(local))
            payload = ('跨节点\x00SSE\n' * 3000).encode()
            stream.sendall(payload)
            received = bytearray()
            while len(received) < len(payload):
                received.extend(stream.recv(len(payload) - len(received)))
            self.assertEqual(payload, received)
        process = self.node.processes['docker']
        self.node.close()
        self.assertIsNotNone(process.poll())
        self.assertFalse(local.exists())

    def test_real_docker_sdk_reads_remote_api_through_ssh(self) -> None:
        """真实 Docker SDK 经 SSH 隧道协商版本并读取独立模拟守护进程。:return: None。"""
        remote = self.root / 'docker-api.sock'
        server = socketserver.ThreadingUnixStreamServer(str(remote), _DockerEndpoint)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        local = self.node._forward('docker', str(remote))
        client = DockerClient(base_url='unix://' + str(local), version='auto', timeout=5)
        self.addCleanup(client.close)
        self.assertEqual('ssh-loopback-docker', client.info()['Name'])

    def test_bootstrap_is_idempotent_and_rejects_other_node_ownership(self) -> None:
        """真实 SSH 初始化仅接受空目录和同一持久节点身份。:return: None。"""
        data = self.root / 'node-data'
        config = NodeConfiguration(**{**self.config.model_dump(), 'data_root': str(data)})
        node = SshNode('a' * 32, config, self.root / 'private', self.root / 'transport')
        self.addCleanup(node.close)
        node.bootstrap('synthetic')
        node.bootstrap('synthetic')
        record = json.loads((data / 'cluster-node.json').read_text())
        self.assertEqual('a' * 32, record['node_key'])
        gate = read_gate(data / 'system-update-gate', 'synthetic')
        self.assertEqual('idle', gate['phase'])
        gate.update(phase='blocked', operation_id=gate['epoch'], target_release='synthetic-next')
        (data / 'system-update-gate' / 'admission.json').write_text(json.dumps(gate))
        node.bootstrap('synthetic')
        self.assertEqual('blocked', read_gate(data / 'system-update-gate', 'synthetic')['phase'])
        wrong = SshNode('c' * 32, config, self.root / 'private', self.root / 'transport')
        self.addCleanup(wrong.close)
        wrong.save_identity(self.identity.read_text())
        with self.assertRaises(NodeSshError):
            wrong.bootstrap('synthetic')
        self.assertEqual(record, json.loads((data / 'cluster-node.json').read_text()))


class BoundedNodeCommandTests(unittest.TestCase):
    """直接验证控制命令的总输出上限、双向管道及真实超时。"""

    def test_output_limit_stops_stdout_and_stderr_before_child_completion(self) -> None:
        """输出过大时立即收口，子进程长等待不会延迟中央拒绝。:return: None。"""
        for descriptor in (1, 2):
            script = f'import os,time; os.write({descriptor},b"x"*1048576); time.sleep(20)'
            started = time.monotonic()
            with self.subTest(descriptor=descriptor), self.assertRaises(NodeSshError) as failure:
                _run([sys.executable, '-c', script], timeout=10)
            self.assertEqual('response_too_large', failure.exception.reason)
            self.assertLess(time.monotonic() - started, 3)

    def test_large_input_and_stderr_do_not_block_each_other(self) -> None:
        """输入和stderr并行消费，完整JSON长度可由远端确认。:return: None。"""
        script = 'import os,sys; os.write(2,b"x"*100000); data=sys.stdin.buffer.read(); print(len(data))'
        self.assertEqual(b'2097152\n', _run([sys.executable, '-c', script], data=b'x' * 2097152, timeout=5))

    def test_deadline_and_error_mapping_keep_remote_output_private(self) -> None:
        """无输出超时与SSH错误分别映射，公开错误保持固定文本。:return: None。"""
        with self.assertRaises(NodeSshError) as timeout:
            _run([sys.executable, '-c', 'import time; time.sleep(20)'], timeout=0.1)
        self.assertEqual('timeout', timeout.exception.reason)
        with self.assertRaises(NodeSshError) as failure:
            _run([sys.executable, '-c', 'import sys; print("Permission denied secret-synthetic",file=sys.stderr);sys.exit(255)'])
        self.assertEqual('authentication_failed', failure.exception.reason)
        self.assertNotIn('secret-synthetic', str(failure.exception))


if __name__ == '__main__':
    unittest.main()
