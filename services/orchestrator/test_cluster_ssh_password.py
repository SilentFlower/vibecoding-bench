"""隔离 Docker sshd 的真实密码认证、独立隧道与进程清理验证。"""
from __future__ import annotations

import json
import os
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from docker import DockerClient, from_env

from cluster_nodes import NodeConfiguration
from cluster_ssh import NodeSshError, SshNode
import test_cluster_ssh as ssh_fixture


@unittest.skipUnless(os.environ.get('CLUSTER_SSH_PASSWORD_TEST') == '1',
    '真实密码 SSH 验证需显式开启隔离 Docker sshd')
class ClusterSshPasswordTests(unittest.TestCase):
    """只修改本次容器内的合成密码，开发宿主账号保持原状。"""

    @classmethod
    def setUpClass(cls) -> None:
        """启动仅映射回环端口的隔离 sshd。:return: None。"""
        temporary = tempfile.TemporaryDirectory(prefix='sp-')
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        unrelated_key = cls.root / 'unrelated'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(unrelated_key)],
            check=True, capture_output=True)
        cls.unrelated_host_key = ' '.join(unrelated_key.with_suffix('.pub').read_text().split()[:2])
        cls.password = ' 合成密碼 $`!;\\" 密码尾空格 '
        cls.client = from_env()
        cls.addClassCleanup(cls.client.close)
        cls.container = cls.client.containers.run(
            os.environ.get('CLUSTER_SSH_PASSWORD_IMAGE', 'flower2api-ssh-password-test:local'),
            ['sleep', 'infinity'], detach=True, entrypoint=[], user='root',
            name='flower2api-ssh-test-' + uuid.uuid4().hex[:12],
            ports={'22/tcp': ('127.0.0.1', None)}, volumes={str(cls.root): {'bind': '/test', 'mode': 'rw'}},
            labels={'flower2api.test': 'ssh-password'})
        cls.addClassCleanup(cls.container.remove, force=True)
        script = ('import pathlib,subprocess; pathlib.Path("/run/sshd").mkdir(exist_ok=True); '
            'subprocess.run(["ssh-keygen","-A"],check=True,capture_output=True); '
            'subprocess.run(["chpasswd"],input=' + repr('root:' + cls.password + '\n') + '.encode(),check=True); '
            'pathlib.Path("/var/run/docker.sock").symlink_to("/test/docker.sock")')
        result = cls.container.exec_run(['python3', '-c', script])
        if result.exit_code:
            raise RuntimeError('隔离 sshd 初始化失败')
        cls.container.exec_run(['/usr/sbin/sshd', '-D', '-e', '-o', 'PasswordAuthentication=yes',
            '-o', 'KbdInteractiveAuthentication=no', '-o', 'PubkeyAuthentication=no',
            '-o', 'UsePAM=no', '-o', 'PermitRootLogin=yes', '-o', 'AllowTcpForwarding=yes',
            '-o', 'AllowStreamLocalForwarding=yes', '-o', 'LogLevel=QUIET'], detach=True)
        cls.container.reload()
        cls.port = int(cls.container.attrs['NetworkSettings']['Ports']['22/tcp'][0]['HostPort'])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(('127.0.0.1', cls.port), timeout=0.3):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError('隔离 sshd 监听超时')
        key = cls.container.exec_run(['cat', '/etc/ssh/ssh_host_ed25519_key.pub'])
        cls.host_key = ' '.join(key.output.decode().split()[:2])

    def setUp(self) -> None:
        """每个场景创建独立凭据及隧道对象。:return: None。"""
        self.config = NodeConfiguration(name='密码回环节点', host='127.0.0.1', port=self.port,
            username='root', host_key=self.host_key, data_root='/test/node-data', auth_method='password')
        self.node = self.new_node(self.config, self.password)

    def new_node(self, config: NodeConfiguration, password: str) -> SshNode:
        """创建场景专属认证对象。:param config: 节点配置。:param password: 合成密码。:return: 节点连接。"""
        node = SshNode(uuid.uuid4().hex, config, self.root / 'private', self.root / 't')
        node.save_password(password)
        self.addCleanup(node.close)
        return node

    def test_password_preserves_special_characters_and_business_stdin(self) -> None:
        """密码与命令标准输入独立，包含 Shell 特殊字符和中文也可认证。:return: None。"""
        payload = ('命令输入\x00$`!;\\"\n' * 20000).encode()
        self.assertEqual(payload, self.node._command('cat', data=payload, maximum_output=len(payload) + 1024))
        reloaded = SshNode(self.node.node_key, self.config, self.root / 'private', self.root / 't')
        self.addCleanup(reloaded.close)
        self.assertEqual(b'reloaded', reloaded._command('printf reloaded'))

    def test_bad_password_and_bad_host_key_are_classified_without_secret(self) -> None:
        """认证与主机身份错误均保持固定原因和秘密保护。:return: None。"""
        wrong = self.new_node(self.config, 'synthetic-wrong-password')
        with self.assertRaises(NodeSshError) as failure:
            wrong._command('printf forbidden')
        self.assertEqual('authentication_failed', failure.exception.reason)
        self.assertNotIn('synthetic-wrong-password', str(failure.exception))
        config = NodeConfiguration(**{**self.config.model_dump(), 'host_key': self.unrelated_host_key})
        mismatch = self.new_node(config, self.password)
        with self.assertRaises(NodeSshError) as failure:
            mismatch._command('printf forbidden')
        self.assertEqual('host_key_mismatch', failure.exception.reason)

    def test_independent_docker_business_and_pty_tunnels_reconnect_and_close(self) -> None:
        """三路真实连接逐字转发，重连及关闭收口整个进程组。:return: None。"""
        (self.root / 'node-data/node-agent').mkdir(parents=True, exist_ok=True)
        servers = []
        for path, handler in ((self.root / 'docker.sock', ssh_fixture._DockerEndpoint),
                (self.root / 'node-data/node-agent/control.sock', ssh_fixture._Echo)):
            server = socketserver.ThreadingUnixStreamServer(str(path), handler)
            server.daemon_threads = True
            servers.append(server)
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        script = 'import socket; s=socket.socket(); s.bind(("127.0.0.1",8091)); s.listen();\nwhile True:\n c,_=s.accept()\n with c:\n  while data:=c.recv(65536): c.sendall(data)'
        self.container.exec_run(['python3', '-c', script], detach=True)
        paths = [self.node.docker_socket(), self.node.pty_socket(), self.node.sender_socket('e' * 32, '127.0.0.1')]
        client = DockerClient(base_url='unix://' + str(paths[0]), version='auto', timeout=5)
        self.addCleanup(client.close)
        self.assertEqual('ssh-loopback-docker', client.info()['Name'])
        for path in paths[1:]:
            with socket.socket(socket.AF_UNIX) as stream:
                stream.settimeout(5)
                stream.connect(str(path))
                stream.sendall('密码隧道\x00SSE\n'.encode())
                self.assertEqual('密码隧道\x00SSE\n'.encode(), stream.recv(1024))
        processes = list(self.node.processes.values())
        children = []
        for process in processes:
            children.extend(int(pid) for pid in Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split())
            self.assertNotIn(self.password.encode(), Path(f'/proc/{process.pid}/cmdline').read_bytes())
            self.assertNotIn(self.password.encode(), Path(f'/proc/{process.pid}/environ').read_bytes())
        self.node.close()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and any(Path(f'/proc/{pid}').exists() for pid in children):
            time.sleep(0.025)
        for pid in children:
            if Path(f'/proc/{pid}/stat').exists():
                self.assertEqual('Z', Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[0])
        for process in processes:
            self.assertIsNotNone(process.poll())
            with self.assertRaises(ProcessLookupError):
                os.killpg(process.pid, 0)
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertEqual(paths[1], self.node.pty_socket())

    def test_command_timeout_reaps_sshpass_and_ssh(self) -> None:
        """真实远程长命令超时后本次 SSH 会话整体退出。:return: None。"""
        with self.assertRaises(NodeSshError) as failure:
            self.node._command('sleep 30', timeout=0.5)
        self.assertEqual('timeout', failure.exception.reason)
        self.assertEqual(b'alive', self.node._command('printf alive'))


if __name__ == '__main__':
    unittest.main()
