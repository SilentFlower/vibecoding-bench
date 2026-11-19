"""通过系统 OpenSSH 严格核对节点身份并维护受保护的本地隧道。"""
from __future__ import annotations

import json
import os
import re
import selectors
import shlex
import signal
import subprocess
import threading
import time
from pathlib import Path
from stat import S_ISREG, S_ISSOCK

from cluster_migration_errors import MigrationFailure, public_failure
from cluster_nodes import NodeAddress, NodeConfiguration, host_key_identity
from cluster_draft_login_operations import DRAFT_LOGIN_OPERATIONS, DRAFT_LOGIN_SHORT_OPERATIONS
from cluster_owner_operations import OWNER_OPERATIONS
from cluster_environment_operations import ENVIRONMENT_OPERATIONS, response_limit
from runtime_files import atomic_text, directory_fd


_OBSERVE_SCRIPT = '''import json, os, platform, shutil, subprocess, sys
memory = {}
with open('/proc/meminfo') as source:
    for line in source:
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
            memory[key] = int(value.split()[0]) * 1024
result = subprocess.run(['docker', 'info', '--format', '{{json .}}'], capture_output=True, timeout=10)
if result.returncode:
    raise SystemExit(2)
info = json.loads(result.stdout)
directory = sys.argv[1]
if os.path.realpath(directory) != directory:
    raise SystemExit(3)
while not os.path.exists(directory):
    directory = os.path.dirname(directory)
disk = shutil.disk_usage(directory)
print(json.dumps({'platform': platform.system(), 'architecture': platform.machine(),
    'host_cpus': os.cpu_count(), 'memory': memory, 'disk_available_bytes': disk.free,
    'docker_version': info.get('ServerVersion'), 'docker_os_type': info.get('OSType'),
    'docker_architecture': info.get('Architecture'), 'docker_cpus': info.get('NCPU'),
    'swap_limit': info.get('SwapLimit')}))
'''

_BOOTSTRAP_SCRIPT = '''import datetime, json, os, stat, sys, uuid
from pathlib import PurePosixPath
value = json.loads(sys.stdin.buffer.read(16385))
if set(value) != {'data_root','node_key','deployment_id'}:
    raise SystemExit(2)
root = PurePosixPath(value['data_root'])
if not root.is_absolute() or '..' in root.parts or len(root.parts) < 3:
    raise SystemExit(2)
directory = os.open('/', os.O_DIRECTORY)
try:
    for part in root.parts[1:]:
        try:
            os.mkdir(part, mode=0o700, dir_fd=directory)
        except FileExistsError:
            pass
        following = os.open(part, os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
        os.close(directory)
        directory = following
    owner = {'protocol':1,'node_key':value['node_key'],'deployment_id':value['deployment_id']}
    names = os.listdir(directory)
    if 'cluster-node.json' not in names and names:
        raise SystemExit(3)
    initialized = False
    try:
        descriptor = os.open('cluster-node.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    except FileExistsError:
        descriptor = os.open('cluster-node.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        with os.fdopen(descriptor) as source:
            if json.loads(source.read(16385)) != owner:
                raise SystemExit(3)
    else:
        initialized = True
        with os.fdopen(descriptor, 'w') as target:
            json.dump(owner, target)
            target.flush()
            os.fsync(target.fileno())
        os.fsync(directory)
    os.fchmod(directory, 0o700)
    if not initialized and 'system-update-gate' not in os.listdir(directory):
        raise SystemExit(3)
    try:
        os.mkdir('system-update-gate', mode=0o700, dir_fd=directory)
    except FileExistsError:
        # 控制容器已接管root私有门禁，SSH只核对目录；内容由原控制组件启动时核验。
        metadata = os.stat('system-update-gate', dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid not in (0, os.geteuid()) or metadata.st_mode & 0o077:
            raise SystemExit(3)
    else:
        gate = os.open('system-update-gate', os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            record = {'schema_version':1,'deployment':value['deployment_id'],'operation_id':None,
                'epoch':str(uuid.uuid4()),'phase':'idle','target_release':None,
                'revision':str(uuid.uuid4()),'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
            descriptor = os.open('admission.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=gate)
            with os.fdopen(descriptor, 'w') as target:
                json.dump(record, target)
                target.flush()
                os.fsync(target.fileno())
            os.fsync(gate)
            os.fsync(directory)
        finally:
            os.close(gate)
finally:
    os.close(directory)
print(json.dumps({'ok':True,'node_key':value['node_key']}))
'''

REMOVAL_FILES_SCRIPT = Path(__file__).with_name('cluster_removal_files.py').read_text(encoding='utf-8')


class NodeSshError(ValueError):
    """节点 SSH 的固定公开故障原因，不携带远端原始输出。

    :param reason: 本模块定义的故障代码。
    """

    def __init__(self, reason: str) -> None:
        """保存受控原因及中文说明。:param reason: 固定故障代码。:return: None。"""
        messages = {'client_unavailable': '管理中心缺少可用的 SSH 客户端',
            'timeout': 'SSH 检查超时，请核对节点网络',
            'host_key_mismatch': '节点主机指纹不匹配，请通过可信渠道核对服务器身份',
            'authentication_failed': 'SSH 认证失败，请核对用户名和所选认证材料',
            'connection_failed': 'SSH 连接失败，请核对地址、端口和网络',
            'remote_command_failed': '节点检查命令失败，请核对 Python 3、Docker 和对应权限',
            'response_too_large': '节点检查结果超出允许大小'}
        self.reason = reason if reason in messages else 'remote_command_failed'
        super().__init__(messages[self.reason])


def _run(arguments: list[str], *, data: bytes | None = None, timeout: float | None = 15,
        maximum_output: int = 256 * 1024, pass_fds: tuple[int, ...] = ()) -> bytes:
    process, failed = None, True
    output, errors = bytearray(), bytearray()
    try:
        process = subprocess.Popen(arguments, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, pass_fds=pass_fds,
            env={**os.environ, 'SSH_AUTH_SOCK': '', 'SSH_ASKPASS_REQUIRE': 'never'})
        deadline = None if timeout is None else time.monotonic() + timeout
        with selectors.DefaultSelector() as ready:
            for stream, name in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
                os.set_blocking(stream.fileno(), False)
                ready.register(stream, selectors.EVENT_READ, name)
            position = 0
            if process.stdin is not None:
                if data:
                    os.set_blocking(process.stdin.fileno(), False)
                    ready.register(process.stdin, selectors.EVENT_WRITE, 'stdin')
                else:
                    process.stdin.close()
            # 同时消费stderr和提交有界输入，避免远端横幅或大JSON导致管道互相等待。
            while ready.get_map():
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise NodeSshError('timeout')
                for key, _ in ready.select(remaining):
                    stream = key.fileobj
                    if key.data == 'stdin':
                        try:
                            position += os.write(stream.fileno(), memoryview(data)[position:position + 65536])
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            position = len(data)
                        if position == len(data):
                            ready.unregister(stream)
                            stream.close()
                    else:
                        try:
                            chunk = os.read(stream.fileno(), 32768)
                        except BlockingIOError:
                            continue
                        if not chunk:
                            ready.unregister(stream)
                            stream.close()
                            continue
                        target = output if key.data == 'stdout' else errors
                        target.extend(chunk)
                        if len(output) + len(errors) > maximum_output:
                            raise NodeSshError('response_too_large')
        code = process.wait(timeout=None if deadline is None else max(0.001, deadline - time.monotonic()))
        if code:
            # OpenSSH错误可能含远端横幅与命令内容，只返回固定脱敏说明。
            message = bytes(errors).lower()
            if arguments[0] == 'sshpass' and code in (5, 6, 7):
                raise NodeSshError('authentication_failed' if code == 5 else 'host_key_mismatch')
            if code == 255:
                if b'host key verification failed' in message or b'remote host identification has changed' in message:
                    raise NodeSshError('host_key_mismatch')
                if b'permission denied' in message:
                    raise NodeSshError('authentication_failed')
                raise NodeSshError('connection_failed')
            raise NodeSshError('remote_command_failed')
        failed = False
        return bytes(output)
    except OSError as error:
        raise NodeSshError('client_unavailable') from error
    except subprocess.TimeoutExpired as error:
        raise NodeSshError('timeout') from error
    finally:
        if process is not None:
            if failed:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def probe_host_keys(address: NodeAddress) -> list[dict[str, str]]:
    """在使用私钥之前读取主机公钥，供管理员独立核对。

    :param address: 已严格验证的单一 SSH 地址。
    :return: 不含凭据的候选公钥与 SHA256 指纹。
    """
    raw = _run(['ssh-keyscan', '-T', '5', '-p', str(address.port), '-t', 'ed25519,ecdsa,rsa', address.host], timeout=10)
    keys = {}
    for line in raw.decode('ascii', errors='replace').splitlines():
        parts = line.split()
        if len(parts) == 3 and not line.startswith('#'):
            key = host_key_identity(' '.join(parts[1:]))
            keys[key['sha256']] = key
    if not keys:
        raise ValueError('未取得节点主机公钥，请检查 SSH 地址和端口')
    return list(keys.values())


class SshNode:
    """单个节点的 SSH 身份与转发进程。

    :param node_key: 中央生成的稳定节点身份。
    :param config: 已确认主机公钥的节点配置。
    :param private_root: 中央私有凭据根目录。
    :param transport_root: 服务可访问的隧道 socket 根目录。
    """

    def __init__(self, node_key: str, config: NodeConfiguration, private_root: Path, transport_root: Path) -> None:
        """固定节点身份与目录，初始化不联网。

        :param node_key: 32 位小写十六进制身份。
        :param config: 节点配置。
        :param private_root: 私钥根。
        :param transport_root: socket 根。
        :return: None。
        """
        if not re.fullmatch('[a-f0-9]{32}', node_key):
            raise ValueError('SSH 节点身份无效')
        self.node_key, self.config = node_key, config
        self.private = private_root / node_key
        self.sockets = transport_root / node_key
        self.lock = threading.RLock()
        self.processes: dict[str, subprocess.Popen] = {}
        self.targets: dict[str, str] = {}

    def save_identity(self, private_key: str) -> None:
        """原子保存专用密钥并校验其可被无交互读取。

        :param private_key: 管理员提交的专用无口令私钥。
        :return: None。
        """
        if not 64 <= len(private_key) <= 32 * 1024 or '\x00' in private_key:
            raise ValueError('SSH 私钥格式无效')
        descriptor = directory_fd(self.private, create=True)
        try:
            os.fchmod(descriptor, 0o700)
        finally:
            os.close(descriptor)
        atomic_text(self.private / 'identity', private_key.rstrip() + '\n')
        try:
            _run(['ssh-keygen', '-y', '-P', '', '-f', str(self.private / 'identity')], timeout=5)
        except ValueError:
            (self.private / 'identity').unlink()
            raise ValueError('SSH 私钥不可读取，请提供专用的无口令私钥') from None
        atomic_text(self.private / 'known_hosts', 'node-' + self.node_key + ' ' + self.config.host_key + '\n')
        _run(['ssh-keygen', '-l', '-E', 'sha256', '-f', str(self.private / 'known_hosts')], timeout=5)

    def save_password(self, password: str) -> None:
        """原子保存节点密码及已确认的主机身份。

        :param password: 原值单行密码。
        :return: None。
        """
        if not isinstance(password, str) or not 1 <= len(password) <= 4096 or any(
                character in password for character in ('\x00', '\r', '\n')):
            raise ValueError('SSH 密码格式无效')
        descriptor = directory_fd(self.private, create=True)
        try:
            os.fchmod(descriptor, 0o700)
        finally:
            os.close(descriptor)
        atomic_text(self.private / 'password', password + '\n')
        atomic_text(self.private / 'known_hosts', 'node-' + self.node_key + ' ' + self.config.host_key + '\n')
        _run(['ssh-keygen', '-l', '-E', 'sha256', '-f', str(self.private / 'known_hosts')], timeout=5)

    def _password_descriptor(self) -> int | None:
        if self.config.auth_method != 'password':
            return None
        directory = directory_fd(self.private)
        descriptor = None
        try:
            metadata = os.fstat(directory)
            if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
                raise ValueError('SSH 身份目录权限或归属无效')
            descriptor = os.open('password', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            metadata = os.fstat(descriptor)
            if not S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_uid != os.geteuid():
                raise ValueError('SSH 密码文件权限或归属无效')
            return descriptor
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
            raise
        finally:
            os.close(directory)

    def _arguments(self, reuse_control: bool = True, password_descriptor: int | None = None) -> list[str]:
        for name in (('identity', 'known_hosts') if self.config.auth_method == 'private_key' else ('known_hosts',)):
            metadata = (self.private / name).lstat()
            if not S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_uid != os.geteuid():
                raise ValueError('SSH 身份文件权限或归属无效')
        if self.config.auth_method == 'password':
            if password_descriptor is None:
                raise ValueError('SSH 密码描述符尚未准备')
            prefix = ['sshpass', '-d', str(password_descriptor)]
            authentication = ['-o', 'BatchMode=no', '-o', 'PasswordAuthentication=yes',
                '-o', 'PreferredAuthentications=password', '-o', 'PubkeyAuthentication=no',
                '-o', 'NumberOfPasswordPrompts=1']
        else:
            prefix = []
            authentication = ['-i', str(self.private / 'identity'), '-o', 'BatchMode=yes',
                '-o', 'PasswordAuthentication=no']
        return prefix + ['ssh', '-F', '/dev/null', '-T', '-S', str(self.sockets / 'control.sock') if reuse_control else 'none',
            '-p', str(self.config.port), '-l', self.config.username,
            *authentication, '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none',
            '-o', 'KbdInteractiveAuthentication=no',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(self.private / 'known_hosts'),
            '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'HostKeyAlias=node-' + self.node_key,
            '-o', 'ProxyCommand=none', '-o', 'ProxyJump=none', '-o', 'ForwardAgent=no',
            '-o', 'ConnectTimeout=8', '-o', 'ConnectionAttempts=1', '-o', 'ServerAliveInterval=10',
            '-o', 'ServerAliveCountMax=3', '-o', 'LogLevel=ERROR']

    def _command(self, command: str, *, data: bytes | None = None, timeout: float | None = 15,
            maximum_output: int = 256 * 1024) -> bytes:
        descriptor = self._password_descriptor()
        try:
            return _run(self._arguments(password_descriptor=descriptor) + ['--', self.config.host, command],
                data=data, timeout=timeout, maximum_output=maximum_output,
                pass_fds=() if descriptor is None else (descriptor,))
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def observe(self) -> dict:
        """实际登录并读取无模型调用的宿主及 Docker 信息。

        :return: 带采样时刻的受限资源投影。
        """
        command = 'python3 -c ' + shlex.quote(_OBSERVE_SCRIPT) + ' ' + shlex.quote(self.config.data_root)
        raw = self._command(command, timeout=25)
        try:
            value = json.loads(raw)
            if (set(value) != {'platform', 'architecture', 'host_cpus', 'memory', 'disk_available_bytes',
                    'docker_version', 'docker_os_type', 'docker_architecture', 'docker_cpus', 'swap_limit'}
                    or value['platform'] != 'Linux' or value['architecture'] != 'x86_64'
                    or value['docker_os_type'] != 'linux' or not isinstance(value['docker_version'], str)
                    or len(value['docker_version']) > 80):
                raise ValueError('节点平台或 Docker 能力不符合要求')
            if set(value['memory']) != {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
                raise ValueError('节点资源观测不完整')
            numeric = [value['host_cpus'], value['disk_available_bytes'], value['docker_cpus'], *value['memory'].values()]
            if any(type(item) is not int or not 0 <= item < 2 ** 53 for item in numeric):
                raise ValueError('节点资源观测格式无效')
            if value['host_cpus'] < 1 or value['docker_cpus'] < 1 or type(value['swap_limit']) is not bool:
                raise ValueError('节点 CPU 或 swap 能力观测无效')
        except (TypeError, KeyError, json.JSONDecodeError) as error:
            raise ValueError('节点资源观测格式无效') from error
        return {**value, 'state': 'reachable', 'observed_at': time.time(), 'stale': False}

    def bootstrap(self, deployment: str) -> None:
        """初始化明确归属的节点数据根，拒绝已有未知资料。

        :param deployment: 当前平台部署身份。
        :return: None。
        """
        if not re.fullmatch('[a-z0-9][a-z0-9-]{0,35}', deployment):
            raise ValueError('部署身份无效')
        body = json.dumps({'data_root': self.config.data_root, 'node_key': self.node_key,
            'deployment_id': deployment}).encode()
        command = 'python3 -c ' + shlex.quote(_BOOTSTRAP_SCRIPT)
        result = json.loads(self._command(command, data=body))
        if result != {'ok': True, 'node_key': self.node_key}:
            raise ValueError('节点数据根归属初始化未确认')

    def removal_files(self, action: str, owner: dict, proof: dict | None = None) -> dict:
        """通过已固定身份的 SSH 核对或擦除原数据目录。:param action: 文件动作。:param owner: 安装归属。:param proof: 原目录身份。:return: 受限目录状态。"""
        body = json.dumps({'action': action, 'root': self.config.data_root, 'owner': owner, 'proof': proof}).encode()
        command = 'python3 -c ' + shlex.quote(REMOVAL_FILES_SCRIPT)
        return json.loads(self._command(command, data=body, timeout=None if action == 'erase' else 15,
            maximum_output=8192))

    def verify_removal_mounts(self, sources: list[str]) -> dict:
        """批量核对其他容器绑定源的实际宿主目录。:param sources: 原 Docker 绑定路径。:return: 确认或受控原因。"""
        body = json.dumps({'action': 'verify_mounts', 'root': self.config.data_root, 'sources': sources}).encode()
        command = 'python3 -c ' + shlex.quote(REMOVAL_FILES_SCRIPT)
        return json.loads(self._command(command, data=body, maximum_output=8192))

    def prepare_environment(self, container: str, payload: dict, *, inspect: bool = False) -> dict:
        """通过固定容器组件准备一个账号，不暴露任意远程命令。

        :param container: 中央按节点身份生成的控制容器名称。
        :param payload: 私有准备协议输入。
        :param inspect: 是否仅执行固定只读状态操作。
        :return: 受限执行组件返回的私有结果。
        """
        return self._execute_environment(container, payload, 'inspect' if inspect else 'prepare')

    def fence_environment(self, container: str, payload: dict) -> dict:
        """通过固定节点组件隔离原源环境。

        :param container: 精确节点控制容器。
        :param payload: 冻结的原分配与环境身份。
        :return: 真实停止及持久隔离收据。
        """
        return self._execute_environment(container, payload, 'fence')

    def agent_health(self, container: str) -> dict:
        """经固定SSH入口核对原长驻进程，保持账号执行状态。

        :param container: 精确节点控制容器。
        :return: 节点、部署、发布及进程就绪回执。
        """
        return self._execute_environment(container, {}, 'health')

    def execution_environment(self, container: str, payload: dict, operation: str) -> dict:
        """经原SSH身份调用固定执行证明和具体终端操作。

        :param container: 原节点精确控制容器。
        :param payload: 原冻结scope及有界操作输入。
        :param operation: 固定证明或终端动作。
        :return: 节点持久回执。
        """
        if operation not in ('account-quiesce','review-admission','grant-create', 'grant-renew', 'grant-get', 'grant-close', 'credential-refresh-start', 'credential-refresh-get', 'credential-status', 'credential-material', 'credential-identity', 'credential-usage-get', 'account-login-get', 'account-login-observe', 'account-login-code-receipt', 'account-login-snapshot', 'account-login-input', 'account-bound-identity', 'account-bound-login-start', 'account-bound-login-get', 'account-bound-login-stop', 'account-bound-login-observe', 'account-bound-login-code', 'account-bound-login-code-receipt', 'account-bound-login-commit', 'account-bound-login-snapshot', 'account-bound-login-accept', 'account-bound-login-discard', 'account-bound-login-input', 'account-bound-login-publish', 'account-bound-login-abort', 'credential-refresh-stop', 'account-login-start', 'account-login-stop', 'account-login-code', 'account-login-commit', 'account-login-accept', 'account-login-discard', 'credential-usage-start', 'credential-usage-stop', 'terminal-assets',
                'terminal-start', 'terminal-get', 'terminal-observe', 'terminal-send', 'terminal-input', 'terminal-control',
                'terminal-conversation', 'terminal-usage', 'terminal-passive', 'terminal-passive-ack', 'terminal-quota-state', 'terminal-quota-read', 'api-quota-read', 'project-history-capture', 'terminal-capture', 'terminal-maintenance', 'terminal-recover', 'terminal-reconcile', 'terminal-snapshot', 'terminal-snapshot-get', 'terminal-verification-start', 'terminal-verification-get', 'terminal-verification-cancel', 'run-verification-start', 'run-verification-get', 'run-verification-cancel', 'run-review-input-stage', 'run-review-input-commit', 'run-review-input-facts', 'run-scenario-input-stage', 'run-scenario-input-commit', 'run-scenario-input-facts', 'run-scenario-input-archive', 'run-project-prepare', 'run-project-configure', 'run-project-decision', 'run-project-facts', 'run-project-native', 'run-project-permit', 'run-snapshot', 'run-snapshot-get', 'run-start', 'run-get', 'run-poll', 'run-control', 'run-recover', 'run-quota-state', 'run-quota-read', 'run-artifact', 'run-files', 'run-file', 'run-stats', 'run-capture', 'run-session', 'run-refresh', 'run-refresh-get', 'run-owner-refresh-defer', 'continue-start', 'continue-get', 'continue-input', 'continue-control', 'continue-recover', 'continue-quota-state', 'continue-quota-read', 'continue-quota-control', 'continue-credentials') and operation not in DRAFT_LOGIN_OPERATIONS and operation not in OWNER_OPERATIONS and operation not in ENVIRONMENT_OPERATIONS:
            raise ValueError('节点具体执行操作无效')
        return self._execute_environment(container, payload, operation)

    def migration_environment(self, container: str, payload: dict, operation: str) -> dict:
        """调用固定的迁移文件操作，返回受限组件回执。

        :param container: 精确节点控制容器。
        :param payload: 已校验的原操作及包身份。
        :param operation: 固定导出、暂存、核验、准备或激活操作。
        :return: 固定协议回执。
        """
        if operation not in ('export', 'stage-import', 'verify-import', 'prepare-import', 'activate-import', 'restore-source', 'revoke-import', 'restart-preserved', 'stage-preparation-files', 'prepare-files'):
            raise ValueError('节点迁移文件操作无效')
        return self._execute_environment(container, payload, operation)

    def _execute_environment(self, container: str, payload: dict, operation: str) -> dict:
        if operation not in ('health', 'prepare', 'inspect', 'account-quiesce', 'review-admission', 'fence', 'export', 'stage-import', 'verify-import',
                'prepare-import', 'activate-import', 'restore-source', 'revoke-import', 'restart-preserved', 'stage-preparation-files', 'prepare-files', 'grant-create', 'grant-renew',
                'grant-get', 'grant-close', 'credential-refresh-start', 'credential-refresh-get', 'credential-status', 'credential-material', 'credential-identity', 'credential-usage-get', 'account-login-get', 'account-login-observe', 'account-login-code-receipt', 'account-login-snapshot', 'account-login-input', 'account-bound-identity', 'account-bound-login-start', 'account-bound-login-get', 'account-bound-login-stop', 'account-bound-login-observe', 'account-bound-login-code', 'account-bound-login-code-receipt', 'account-bound-login-commit', 'account-bound-login-snapshot', 'account-bound-login-accept', 'account-bound-login-discard', 'account-bound-login-input', 'account-bound-login-publish', 'account-bound-login-abort', 'credential-refresh-stop', 'account-login-start', 'account-login-stop', 'account-login-code', 'account-login-commit', 'account-login-accept', 'account-login-discard', 'credential-usage-start', 'credential-usage-stop', 'terminal-assets', 'terminal-start', 'terminal-get', 'terminal-observe',
                'terminal-send', 'terminal-input', 'terminal-control', 'terminal-conversation', 'terminal-usage',
                'terminal-passive', 'terminal-passive-ack', 'terminal-quota-state', 'terminal-quota-read', 'api-quota-read', 'project-history-capture', 'terminal-capture', 'terminal-maintenance', 'terminal-recover', 'terminal-reconcile', 'terminal-snapshot', 'terminal-snapshot-get', 'terminal-verification-start', 'terminal-verification-get', 'terminal-verification-cancel', 'run-verification-start', 'run-verification-get', 'run-verification-cancel', 'run-review-input-stage', 'run-review-input-commit', 'run-review-input-facts', 'run-scenario-input-stage', 'run-scenario-input-commit', 'run-scenario-input-facts', 'run-scenario-input-archive', 'run-project-prepare', 'run-project-configure', 'run-project-decision', 'run-project-facts', 'run-project-native', 'run-project-permit', 'run-snapshot', 'run-snapshot-get', 'run-start', 'run-get', 'run-poll', 'run-control', 'run-recover', 'run-quota-state', 'run-quota-read', 'run-artifact', 'run-files', 'run-file', 'run-stats', 'run-capture', 'run-session', 'run-refresh', 'run-refresh-get', 'run-owner-refresh-defer', 'continue-start', 'continue-get', 'continue-input', 'continue-control', 'continue-recover', 'continue-quota-state', 'continue-quota-read', 'continue-quota-control', 'continue-credentials') and operation not in DRAFT_LOGIN_OPERATIONS and operation not in OWNER_OPERATIONS and operation not in ENVIRONMENT_OPERATIONS:
            raise ValueError('节点执行操作无效')
        if not re.fullmatch('flower2api-node-[a-f0-9]{24}', container):
            raise ValueError('节点控制容器身份无效')
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        if len(body) > 2 * 1024 * 1024:
            raise ValueError('节点准备输入超过允许大小')
        arguments = ['docker', 'exec', '-i', container, 'python3', '/app/cluster_agent_client.py', operation]
        command = shlex.join(arguments)
        timeout = 20 if operation in DRAFT_LOGIN_SHORT_OPERATIONS else 605 if operation in ('export', 'verify-import', 'terminal-assets', 'terminal-snapshot', 'terminal-snapshot-get', 'run-snapshot', 'run-snapshot-get') else 20 if operation in (
            'health', 'inspect', 'review-admission', 'stage-import', 'grant-create', 'grant-renew', 'grant-get', 'grant-close', 'credential-refresh-get', 'credential-status', 'credential-material', 'credential-identity', 'credential-usage-get', 'account-login-get', 'account-login-observe', 'account-login-code-receipt', 'account-login-snapshot', 'account-login-input', 'account-bound-identity', 'account-bound-login-get', 'account-bound-login-observe', 'account-bound-login-code-receipt', 'account-bound-login-snapshot', 'account-bound-login-input',
            'terminal-get', 'terminal-observe', 'terminal-send', 'terminal-input', 'terminal-conversation',
            'terminal-usage', 'terminal-passive', 'terminal-passive-ack', 'terminal-quota-state', 'terminal-quota-read', 'api-quota-read', 'project-history-capture',
            'terminal-capture', 'terminal-reconcile', 'terminal-verification-get', 'run-verification-get', 'run-project-facts', 'run-project-native', 'run-get', 'run-poll', 'run-quota-state', 'run-quota-read', 'run-artifact', 'run-files', 'run-file', 'run-stats', 'run-capture', 'run-session', 'run-refresh', 'run-refresh-get', 'run-owner-refresh-defer', 'continue-get', 'continue-input', 'continue-quota-state', 'continue-quota-read', 'continue-quota-control', 'continue-credentials') else 120
        # 迁移本来由中央后台线程持有；SSH保活检测失联，不按环境规模限制总运行时间。
        if operation in ('export', 'verify-import', 'prepare-import', 'prepare-files'):
            timeout = None
        result = json.loads(self._command(command, data=body, timeout=timeout, maximum_output=response_limit(operation)))
        if not isinstance(result, dict) or result.get('ok') is not True or not isinstance(result.get('result'), dict):
            failure = public_failure(result.get('failure')) if isinstance(result, dict) else None
            if failure is not None:
                raise MigrationFailure(failure['code'], failure['stage'])
            raise ValueError('节点环境准备失败，请检查执行组件、环境归属与资源')
        value = result['result']
        if value.get('protocol') != 1 or value.get('node_key') != self.node_key:
            raise ValueError('节点准备回执身份不一致')
        return value

    def docker_socket(self) -> Path:
        """建立独立控制连接，将本机私有 socket 映射到远程 Docker。

        :return: 中央本地 Unix socket 路径。
        """
        return self._forward('docker', '/var/run/docker.sock')

    def sender_socket(self, environment_id: str, address: str, port: int = 8091) -> Path:
        """为受信 Docker 观测到的 sender 地址建立独立业务通道。

        :param environment_id: 环境身份。
        :param address: 本节点 Docker 网络中的 sender IP。
        :param port: 固定 sender 端口。
        :return: 私有本地 socket。
        """
        if not re.fullmatch('[a-f0-9]{32}', environment_id) or port != 8091:
            raise ValueError('账号传输归属无效')
        address = NodeAddress(host=address).host
        # SSH -L 的 IPv6 目标需要括号；地址由受信 Docker 观测提供，不来自浏览器。
        target = f'[{address}]' if ':' in address else address
        return self._forward(environment_id, f'{target}:{port}')

    def pty_socket(self) -> Path:
        """通过独立SSH连接转发本安装节点的固定私有UDS。

        :return: 中央私有socket；目标始终取管理员登记的数据根。
        """
        return self._forward('node-pty', self.config.data_root + '/node-agent/control.sock')

    def _forward(self, name: str, target: str) -> Path:
        with self.lock:
            descriptor = directory_fd(self.sockets, create=True)
            try:
                os.fchmod(descriptor, 0o700)
            finally:
                os.close(descriptor)
            path = self.sockets / (name + '.sock')
            if len(os.fsencode(path)) > 100:
                raise ValueError('节点隧道路径过长，请缩短共享目录')
            current = self.processes.get(name)
            if current and current.poll() is None and path.exists() and self.targets.get(name) == target:
                return path
            if current and current.poll() is None:
                self._stop(name)
            if path.exists() or path.is_symlink():
                metadata = path.lstat()
                if not S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.geteuid():
                    raise ValueError('节点隧道路径存在未知文件')
                path.unlink()
            descriptor = self._password_descriptor()
            try:
                arguments = self._arguments(False, descriptor)
                if name == 'docker':
                    arguments += ['-M', '-S', str(self.sockets / 'control.sock')]
                arguments += ['-N', '-o', 'ExitOnForwardFailure=yes',
                    '-o', 'StreamLocalBindMask=0177', '-L', str(path) + ':' + target, '--', self.config.host]
                process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True,
                    pass_fds=() if descriptor is None else (descriptor,),
                    env={**os.environ, 'SSH_AUTH_SOCK': '', 'SSH_ASKPASS_REQUIRE': 'never'})
            finally:
                if descriptor is not None:
                    os.close(descriptor)
            self.processes[name] = process
            self.targets[name] = target
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and process.poll() is None:
                if path.exists():
                    return path
                time.sleep(0.025)
            self._stop(name)
            raise ValueError('SSH 隧道建立失败，请检查主机指纹、认证和转发权限')

    def _stop(self, name: str) -> None:
        self.targets.pop(name, None)
        process = self.processes.pop(name, None)
        if process:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            finally:
                # sshpass 与 ssh 分属父子进程，父进程退出后仍收口整个原会话。
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
        path = self.sockets / (name + '.sock')
        try:
            if S_ISSOCK(path.lstat().st_mode):
                path.unlink()
        except FileNotFoundError:
            pass
        if name == 'docker':
            control = self.sockets / 'control.sock'
            try:
                if S_ISSOCK(control.lstat().st_mode) and control.lstat().st_uid == os.geteuid():
                    control.unlink()
            except FileNotFoundError:
                pass

    def close(self) -> None:
        """停止本对象持有的隧道，保留远程环境。:return: None。"""
        with self.lock:
            for name in list(self.processes):
                self._stop(name)

    def remove_identity(self) -> None:
        """收口未登记成功的精确身份文件。:return: None。"""
        self.close()
        for name in ('identity', 'password', 'known_hosts'):
            try:
                (self.private / name).unlink()
            except FileNotFoundError:
                pass
        try:
            self.private.rmdir()
        except FileNotFoundError:
            pass
