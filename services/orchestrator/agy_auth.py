"""现有管理链路的 AGY 原生授权及凭据适配，所有模型提交数为零。"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import threading
import time
import uuid
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from stat import S_ISREG
from urllib.parse import parse_qs, urlsplit

from runtime_files import atomic_json, directory_fd

SOURCE_SHA256 = '39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'
SOURCE_BYTES = 265700040
BINARY = '/usr/local/bin/agy-1.5.9'
TOKEN_PATH = Path('.gemini/antigravity-cli/antigravity-oauth-token')
TTL_SECONDS = 1800


def auth_asset_identity(value: dict | None) -> dict | None:
    """核对构建清单中的授权制品身份。@param value 制品记录或历史缺省。@return 已核验身份；未提供制品返回空。"""
    if value is None:
        return None
    if not isinstance(value, dict) or type(value.get('available')) is not bool:
        raise ValueError('AGY 构建制品声明无效')
    expected = {'available', 'source_version', 'sha256'} | ({'bytes'} if value['available'] else set())
    if set(value) != expected or value.get('source_version') != '1.5.9':
        raise ValueError('AGY 构建制品字段或版本无效')
    if value['available']:
        if value['sha256'] != SOURCE_SHA256 or type(value['bytes']) is not int or value['bytes'] != SOURCE_BYTES:
            raise ValueError('AGY 构建制品身份不匹配')
        return dict(value)
    if value['sha256'] != '':
        raise ValueError('AGY 未提供制品的声明不一致')
    return None


def require_auth_asset(value: dict | None) -> dict:
    """要求正式交付具备固定AGY能力。@param value 构建制品声明。@return 已核验的完整能力身份。"""
    identity = auth_asset_identity(value)
    if identity is None:
        raise ValueError('正式交付缺少固定AGY处理产物')
    return identity


def stage_auth_asset(destination: Path, source: str | None = None) -> dict:
    """冻结可选原生授权制品。@param destination 本次快照目录。@param source 私有固定原版。@return 已核验能力记录。"""
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    source = source or os.environ.get('V3_AGY_AUTH_ASSET')
    if not source:
        (destination / 'agy-auth-unavailable').touch(mode=0o600)
        return {'available': False, 'source_version': '1.5.9', 'sha256': ''}
    target = destination / 'agy-1.5.9'
    shutil.copyfile(source, target)
    with target.open('rb') as stream:
        valid = target.stat().st_size == SOURCE_BYTES and hashlib.file_digest(stream, 'sha256').hexdigest() == SOURCE_SHA256
    if not valid:
        target.unlink()
        raise ValueError('AGY 原版授权制品身份不匹配')
    target.chmod(0o755)
    return {'available': True, 'source_version': '1.5.9', 'sha256': SOURCE_SHA256, 'bytes': SOURCE_BYTES}


def native_document(value: dict, *, require_refresh: bool = True) -> dict:
    """校验固定原版的私有凭据。@param value 原生对象。@param require_refresh 是否要求RT。@return 独立副本。"""
    token = value.get('token') if isinstance(value, dict) else None
    if (not isinstance(token, dict) or value.get('auth_method') != 'consumer'
            or not isinstance(token.get('access_token'), str) or not token['access_token'].strip()
            or len(token['access_token']) > 16384):
        raise ValueError('AGY 凭据结构无效')
    refresh = token.get('refresh_token')
    if (refresh is not None and (not isinstance(refresh, str) or len(refresh) > 16384)
            or require_refresh and not refresh):
        raise ValueError('AGY 刷新凭据无效')
    try:
        expiry = datetime.fromisoformat(token['expiry'].replace('Z', '+00:00'))
        if expiry.tzinfo is None:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError('AGY 有效期无效') from None
    return copy.deepcopy(value)


def authorization_url(screen: str) -> str | None:
    """读取原生 Google OOB 链接。@param screen 私有终端文本。@return 校验后的原始链接或空值。"""
    hyperlinks = re.findall(r'\x1b\]8;[^;]*;(https://accounts\.google\.com/[^\x07\x1b]+)', screen)
    plain = re.sub(r'\x1b(?:\][^\x07\x1b]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~])', '', screen)
    for candidate in [*hyperlinks, *re.findall(r'https://accounts\.google\.com/[^\s\x00-\x1f<>]+', plain)]:
        if len(candidate) > 8192:
            continue
        try:
            parsed = urlsplit(candidate)
            query = parse_qs(parsed.query, keep_blank_values=True)
            required = {'client_id', 'response_type', 'redirect_uri', 'scope', 'code_challenge', 'code_challenge_method', 'state'}
            if (parsed.scheme == 'https' and parsed.netloc == 'accounts.google.com' and not parsed.fragment
                    and required.issubset(query) and all(len(query[key]) == 1 and query[key][0] for key in required)
                    and query['response_type'] == ['code'] and query['code_challenge_method'] == ['S256']
                    and query['redirect_uri'] == ['https://antigravity.google/oauth-callback']
                    and re.fullmatch(r'[A-Za-z0-9_-]{43}', query['code_challenge'][0])):
                return candidate
        except ValueError:
            continue
    return None


class AgyOperationBusy(ValueError):
    """原操作仍在持锁执行。"""


class AgyAuthManager:
    """使用私有操作目录和固定账号镜像管理原生进程。@param client Docker客户端。@param data 私有数据根。@param host_data 宿主挂载根。@param image 账号镜像。@param network 部署网络。"""

    def __init__(self, client, data: Path, host_data: Path, image: str, network: str):
        """初始化授权适配。@param client Docker客户端。@param data 数据根。@param host_data 宿主根。@param image 镜像。@param network 网络。@return 无。"""
        self.client, self.data, self.host_data = client, data, host_data
        self.image, self.network = image, network
        self.root = data / 'agy-auth'
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.root.lstat()
        if self.root.is_symlink() or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('AGY 私有操作根权限无效')
        self.guard = threading.Lock()
        self._reap()

    def _read(self, path: Path) -> dict:
        """读取受限普通操作文件，拒绝链接及共享权限。"""
        directory = directory_fd(path.parent)
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            expected_uid = 1001 if path.name == TOKEN_PATH.name else os.geteuid()
            if not S_ISREG(info.st_mode) or info.st_uid != expected_uid or info.st_mode & 0o077 or info.st_size > 2 * 1024 * 1024:
                raise ValueError('AGY 私有材料权限或大小无效')
            value = json.loads(stream.read(2 * 1024 * 1024 + 1))
        if not isinstance(value, dict):
            raise ValueError('AGY 私有材料格式无效')
        return value

    @contextmanager
    def _locked(self, identity: str):
        """跨进程串行同一会话或账号的实际原生操作。"""
        if not re.fullmatch(r'[a-z0-9-]{1,80}', identity):
            raise ValueError('AGY 操作归属无效')
        descriptor = os.open(self.root / (identity + '.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if not S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError('AGY 操作锁权限无效')
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AgyOperationBusy('AGY 原操作仍在进行，请读取原会话') from None
            yield
        finally:
            os.close(descriptor)

    def _folder(self, identity: str) -> Path:
        """解析已验证的操作目录。"""
        if not re.fullmatch(r'[a-f0-9]{32}', identity):
            raise ValueError('AGY 操作身份无效')
        return self.root / identity

    def _reap(self):
        """恢复时停止过期的未完成授权，保留凭据操作对账材料。"""
        for path in self.root.glob('*/state.json'):
            identity = path.parent.name
            try:
                with self._locked(identity):
                    state = self._read(path)
                    if state.get('phase') in ('retired', 'not_started') or (
                            state.get('phase') == 'completed' and state.get('account_id') is not None):
                        continue
                    age = time.time() - state.get('created_at', 0)
                    if state.get('kind') == 'authorization' and age > TTL_SECONDS:
                        self._stop(state)
                        if state.get('account_id') is None:
                            shutil.rmtree(path.parent)
                            continue
                        if state.get('code_digest'):
                            state['phase'] = 'reconcile'
                        else:
                            state['phase'] = 'expired'
                        atomic_json(path, state)
                    elif state.get('kind') == 'verification' and age > 120:
                        self._stop(state)
                        shutil.rmtree(path.parent)
            except AgyOperationBusy:
                continue

    def cleanup(self) -> None:
        """周期回收到期的授权进程，保留关联账号的未知结果。@return 无。"""
        with self.guard, self._locked('start'):
            self._reap()

    def _stop(self, state: dict):
        """只回收记录中同代次的实验原生容器。"""
        name = state.get('container')
        if not name:
            return
        try:
            container = self.client.containers.get(name)
        except Exception as error:
            from docker.errors import NotFound
            if isinstance(error, NotFound):
                return
            raise ValueError('AGY 原生进程状态待核对') from None
        labels = container.labels or {}
        if labels.get('vibebench.agy-operation') != state['operation_id']:
            raise ValueError('AGY 原生进程归属不符')
        container.remove(force=True)

    def _launch(self, folder: Path, state: dict, *, interactive: bool, document: dict | None = None, native_args: list[str] | None = None):
        """启动固定身份的原生进程，镜像及完整执行体均核验。"""
        image = self.client.images.get(self.image)
        if image.labels.get('vibebench.agy-auth-source-sha256') != SOURCE_SHA256:
            raise ValueError('账号镜像尚未提供固定 AGY 授权能力')
        home, workspace = folder / 'home', folder / 'workspace'
        home.mkdir(mode=0o700, exist_ok=True)
        workspace.mkdir(mode=0o700, exist_ok=True)
        if document is not None:
            atomic_json(home / TOKEN_PATH, document)
        for path in [home, workspace, *home.rglob('*')]:
            if path.is_symlink():
                raise ValueError('AGY 私有目录包含链接')
            os.chown(path, 1001, 1001)
        name = 'bench-agy-auth-' + state['operation_id']
        environment = {'HOME': '/home/agy', 'USER': 'agy', 'LANG': 'C.UTF-8', 'TERM': 'xterm-256color',
            'AGY_CLI_DISABLE_AUTO_UPDATE': 'true', 'ANTIGRAVITY_REMOTE_OOB_AUTH': 'true',
            'SSH_CONNECTION': '127.0.0.1 1 127.0.0.1 2', 'ANTIGRAVITY_SERVER_CSRF_TOKEN': secrets.token_urlsafe(32),
            'NO_PROXY': '127.0.0.1,localhost'}
        if state.get('proxy_url'):
            environment.update(HTTP_PROXY=state['proxy_url'], HTTPS_PROXY=state['proxy_url'], ALL_PROXY=state['proxy_url'])
        state.update(container=name, phase='starting')
        atomic_json(folder / 'state.json', state)
        bootstrap = 'import hashlib,os,sys; p=sys.argv[1]; f=open(p,"rb"); h=hashlib.file_digest(f,"sha256").hexdigest(); f.close(); h==sys.argv[2] or sys.exit(2); os.execv(p,[p]+sys.argv[3:])'
        container = self.client.containers.run(self.image, native_args if native_args is not None else ([] if interactive else ['--input-format', 'stream-json', '--output-format', 'stream-json']),
            entrypoint=['python3', '-c', bootstrap, BINARY, SOURCE_SHA256], name=name,
            user='1001:1001', detach=True, stdin_open=True, tty=interactive, read_only=True,
            tmpfs={'/tmp': 'rw,nosuid,nodev,noexec,size=128m'}, cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
            network=self.network, mem_limit='512m', pids_limit=256, environment=environment,
            labels={'vibebench.agy-operation': state['operation_id']},
            volumes={str(self.host_data / home.relative_to(self.data)): {'bind': '/home/agy', 'mode': 'rw'},
                str(self.host_data / workspace.relative_to(self.data)): {'bind': '/workspace', 'mode': 'rw'}}, working_dir='/workspace')
        return container

    def _send(self, container, value: bytes):
        """向同一原生终端发送已冻结输入，socket 失败交给原操作对账。"""
        connection = container.attach_socket(params={'stdin': True, 'stream': True})
        try:
            connection._sock.settimeout(5)
            connection._sock.sendall(value)
        finally:
            connection.close()

    def start(self, proxy_url: str, account_id: int | None, generation: int | None,
              operation_id: str | None = None) -> dict:
        """生成原生 OOB 链接。@param proxy_url 授权线路。@param account_id 原账号。@param generation 原代次。@param operation_id 网关预占身份。@return 会话及链接。"""
        if (account_id is None) != (generation is None) or (account_id is not None and
                (type(account_id) is not int or account_id < 1 or type(generation) is not int or generation < 1)):
            raise ValueError('AGY 授权目标无效')
        if operation_id is not None and (account_id is None or not isinstance(operation_id, str)):
            raise ValueError('AGY 授权预占身份无效')
        identity = operation_id if operation_id is not None else uuid.uuid4().hex
        folder = self._folder(identity)
        with ExitStack() as operation:
            with self.guard, self._locked('start'):
                self._reap()
                if account_id is not None:
                    operation.enter_context(self._locked('account-' + str(account_id)))
                operation.enter_context(self._locked(identity))
                if folder.exists():
                    previous = self._read(folder / 'state.json')
                    if (previous.get('kind') == 'authorization' and previous.get('phase') == 'authorizing'
                            and previous.get('account_id') == account_id and previous.get('generation') == generation
                            and previous.get('proxy_url') == proxy_url):
                        return {'session_id': identity, 'auth_url': previous['auth_url']}
                    raise ValueError('AGY 原授权操作已结束或归属已变化')
                active = sum(self._read(path).get('phase') in ('starting', 'authorizing', 'code_pending')
                    for path in self.root.glob('*/state.json'))
                if active >= 8:
                    raise ValueError('AGY 授权会话已满')
                folder.mkdir(mode=0o700)
                state = {'kind': 'authorization', 'operation_id': identity, 'phase': 'starting',
                    'created_at': time.time(), 'proxy_url': proxy_url, 'account_id': account_id, 'generation': generation}
                atomic_json(folder / 'state.json', state)
            return self._start_authorization(folder, state)

    def _start_authorization(self, folder: Path, state: dict) -> dict:
        """启动同一预占会话，整个调用保持操作锁。"""
        selected = False
        try:
            container = self._launch(folder, state, interactive=True)
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                screen = container.logs(tail=160).decode(errors='replace')[-131072:]
                url = authorization_url(screen)
                if url:
                    state.update(phase='authorizing', auth_url=url)
                    atomic_json(folder / 'state.json', state)
                    return {'session_id': state['operation_id'], 'auth_url': url}
                if not selected and 'Select login method:' in screen and '1. Google OAuth' in screen:
                    self._send(container, b'\r')
                    selected = True
                time.sleep(.1)
            raise ValueError('AGY 原生授权链接尚未就绪')
        except Exception:
            self._stop(state)
            state['phase'] = 'failed'
            atomic_json(folder / 'state.json', state)
            raise

    def cancel(self, identity: str) -> dict:
        """结束原会话进程并保留必要的私有对账状态。@param identity 原会话。@return 取消状态。"""
        folder = self._folder(identity)
        with self._locked(identity):
            state = self._read(folder / 'state.json')
            if state.get('kind') == 'authorization':
                if state.get('phase') == 'completed':
                    state['exchange_closed'] = True
                    atomic_json(folder / 'state.json', state)
                    return {'cancelled': False, 'phase': 'reconcile'}
                self._stop(state)
                state['phase'] = 'reconcile' if state.get('code_digest') else 'cancelled'
                atomic_json(folder / 'state.json', state)
            else:
                raise ValueError('AGY 原授权操作归属无效')
        return {'cancelled': True, 'phase': state['phase']}

    def _retired_result(self, state: dict) -> dict:
        """返回不含凭据的同归属持久终止证明。"""
        return {key: state[key] for key in ('operation_id', 'account_id', 'generation', 'phase')} | {'retired': True}

    def _retire_locked(self, folder: Path, identity: str, account_id: int, generation: int) -> dict:
        """在账号与操作双锁内保存终止记录，阻止迟到请求消费RT。"""
        try:
            state = self._read(folder / 'state.json')
        except FileNotFoundError:
            folder.mkdir(mode=0o700, exist_ok=True)
            state = dict(kind='retired', operation_id=identity, account_id=account_id,
                generation=generation, phase='not_started', created_at=time.time())
        else:
            if state.get('account_id') != account_id or state.get('generation') != generation:
                raise ValueError('AGY 原终止操作归属不符')
            if state.get('phase') not in ('retired', 'not_started'):
                self._stop(state)
                state['phase'] = 'retired'
        atomic_json(folder / 'state.json', state)
        return self._retired_result(state)

    def retire(self, identity: str, account_id: int, generation: int) -> dict:
        """明确终止原操作并持久拒绝迟到重放。@param identity 操作。@param account_id 账号。@param generation 原代次。@return 脱敏终止证明。"""
        if type(account_id) is not int or account_id < 1 or type(generation) is not int or generation < 1:
            raise ValueError('AGY 终止归属无效')
        folder = self._folder(identity)
        with self._locked('account-' + str(account_id)), self._locked(identity):
            return self._retire_locked(folder, identity, account_id, generation)

    def exchange(self, identity: str, code: str) -> dict:
        """将授权码送回同一原生终端。@param identity 会话。@param code 用户提供的授权码。@return 完整原生凭据。"""
        if not isinstance(code, str) or not code.strip() or len(code) > 4096 or any(ord(value) <= 32 or ord(value) >= 127 for value in code.strip()):
            raise ValueError('AGY 授权码格式无效')
        folder = self._folder(identity)
        with self._locked(identity):
            state = self._read(folder / 'state.json')
            if (state.get('kind') != 'authorization' or state.get('exchange_closed')
                    or time.time() > state['created_at'] + TTL_SECONDS):
                raise ValueError('AGY 原授权会话已过期')
            digest = hashlib.sha256(code.strip().encode()).hexdigest()
            if state['phase'] == 'completed':
                if state.get('code_digest') != digest:
                    raise ValueError('AGY 原授权码回执不符')
                return self._read(folder / 'result.json')
            if state['phase'] not in ('authorizing', 'code_pending') or state.get('code_digest', digest) != digest:
                raise ValueError('AGY 原授权操作待核对')
            if state['phase'] == 'authorizing':
                state.update(phase='code_pending', code_digest=digest)
                atomic_json(folder / 'state.json', state)
                container = self.client.containers.get(state['container'])
                self._send(container, b'\x1b[200~' + code.strip().encode() + b'\x1b[201~\r')
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                path = folder / 'home' / TOKEN_PATH
                if path.exists():
                    document = native_document(self._read(path))
                    self._stop(state)
                    verified = self.verify(document, state['proxy_url'])
                    # 对账读取同一份核验回执，避免依赖重启后丢失的网关会话。
                    result = {'document': document, **verified, 'proxy_url': state['proxy_url']}
                    atomic_json(folder / 'result.json', result)
                    state['phase'] = 'completed'
                    atomic_json(folder / 'state.json', state)
                    return result
                time.sleep(.1)
            raise ValueError('AGY 原生认证仍待完成，请查询原会话')

    def verify(self, document: dict, proxy_url: str, *, include_quota: bool = False, identity_only: bool = False) -> dict:
        """使用 AT-only 原生进程读取账号状态。@param document 原生凭据。@param proxy_url 固定代理。@param include_quota 同时读取平台额度。@param identity_only 只核验认证身份。@return 真实身份及所请求的观测。"""
        document = native_document(document)
        expiry = datetime.fromisoformat(document['token']['expiry'].replace('Z', '+00:00')).timestamp()
        if expiry <= time.time() + 60:
            raise ValueError('AGY 访问凭据有效期不足')
        identity = uuid.uuid4().hex
        folder = self._folder(identity)
        folder.mkdir(mode=0o700)
        state = {'kind': 'verification', 'operation_id': identity, 'created_at': time.time(), 'proxy_url': proxy_url}
        access = copy.deepcopy(document)
        access['token'].pop('refresh_token', None)
        try:
            container = self._launch(folder, state, interactive=False, document=access)
            deadline = time.monotonic() + 20
            port = None
            while time.monotonic() < deadline:
                for path in (folder / 'home/.gemini/antigravity-cli/log').glob('*.log'):
                    hits = re.findall(r'Language server listening on random port at (\d+) for HTTP\b', path.read_text(errors='replace'))
                    if hits:
                        port = int(hits[-1])
                        break
                if port:
                    break
                time.sleep(.1)
            if not port:
                raise ValueError('AGY 账号状态服务未就绪')
            code = '''from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection, HTTPException
import json,os,sys

def read(method):
    connection = HTTPConnection('127.0.0.1',int(sys.argv[1]),timeout=15)
    try:
        connection.request('POST','/exa.language_server_pb.LanguageServerService/'+method,sys.argv[2].encode(),
            {'Content-Type':'application/json','x-codeium-csrf-token':os.environ['ANTIGRAVITY_SERVER_CSRF_TOKEN']})
        response = connection.getresponse()
        body = response.read(1048577)
        if response.status==200 and len(body)<=1048576:
            return json.loads(body)
    except (OSError,HTTPException,ValueError):
        pass
    finally:
        connection.close()
    return None

with ThreadPoolExecutor(max_workers=len(sys.argv[3:])) as pool:
    print(json.dumps(dict(zip(sys.argv[3:],pool.map(read,sys.argv[3:])))))
'''
            rpc = ['python3', '-c', code, str(port)]
            observed_at_ms = int(time.time() * 1000)
            result = container.exec_run([*rpc, '{}', 'GetUserStatus'], user='1001:1001')
            status_response = json.loads(result.output).get('GetUserStatus') if result.exit_code == 0 else None
            if not isinstance(status_response, dict) or not isinstance(status_response.get('userStatus'), dict):
                raise ValueError('AGY 已认证状态读取失败')
            status = status_response['userStatus']
            email = status.get('email')
            if not isinstance(email, str) or not email.strip() or len(email) > 320:
                raise ValueError('AGY 已认证身份缺失')
            if identity_only:
                return {'email_address': email.strip()}
            model_code = 'import subprocess,sys; r=subprocess.run([sys.argv[1],"models"],capture_output=True,timeout=25); sys.stdout.buffer.write((r.stdout+bytes([10])+r.stderr)[:1048576]); sys.exit(r.returncode)'
            models = container.exec_run(['python3', '-c', model_code, BINARY], user='1001:1001')
            if models.exit_code != 0:
                raise ValueError('AGY 原生模型目录读取失败')
            names = sorted(set(re.findall(r'\b(?:gemini|claude|gpt)-[A-Za-z0-9_.-]+', models.output.decode(errors='replace'))))
            # CLI名称和原生枚举分别观测，运行层只使用两者已核对的交集。
            methods = ['GetAvailableModels', 'RetrieveUserQuotaSummary'] if include_quota else ['GetAvailableModels']
            catalog = container.exec_run([*rpc, '{"forceRefresh":true}' if include_quota else '{}', *methods],
                user='1001:1001')
            mapping = {}
            media_inputs = {}
            responses = {}
            if catalog.exit_code == 0:
                try:
                    from agy_runtime.models import decode_catalog, decode_media_support
                    responses = json.loads(catalog.output)
                    raw_catalog = responses.get('GetAvailableModels')
                    observed = decode_catalog(raw_catalog)
                    mapping = {name: observed[name] for name in names if name in observed}
                    media_inputs = decode_media_support(raw_catalog, mapping)
                except (ValueError, TypeError, KeyError):
                    # 身份核验仍独立成立；未知模型映射保持未就绪，不猜测枚举发送业务。
                    mapping = {}
            verified = {'email_address': email.strip(), 'capabilities': {'source': 'agy:1.5.9:native',
                'observed_at_ms': observed_at_ms, 'models': names,
                'model_mappings': mapping, 'model_mapping_status': 'observed' if mapping else 'unavailable',
                'media_inputs': media_inputs, 'png_inputs': {name: formats['image/png']
                    for name, formats in media_inputs.items() if 'image/png' in formats},
                'provider': {key: status[key] for key in ('planStatus', 'userTier') if key in status}}}
            if include_quota:
                from agy_runtime.models import decode_quota
                verified['platform_quota'] = decode_quota(responses.get('RetrieveUserQuotaSummary'),
                    responses.get('GetAvailableModels'), status, observed_at_ms)
            return verified
        finally:
            self._stop(state)
            state['phase'] = 'stopped'
            shutil.rmtree(folder)

    def refresh(self, identity: str, account_id: int, generation: int, document: dict, proxy_url: str) -> dict:
        """在同账号锁内执行一次原生刷新并保存回执。@param identity 操作ID。@param account_id 账号。@param generation 原代次。@param document 权威凭据。@param proxy_url 代理。@return 私有刷新结果。"""
        # 固定宿主更新器也会导入本模块，Docker HTTP 依赖只在执行刷新时加载。
        from requests.exceptions import ReadTimeout

        document = native_document(document)
        if type(account_id) is not int or account_id < 1 or type(generation) is not int or generation < 1:
            raise ValueError('AGY 刷新归属无效')
        folder = self._folder(identity)
        with self._locked('account-' + str(account_id)):
            fingerprint = hashlib.sha256(json.dumps([account_id, generation, document, proxy_url], sort_keys=True).encode()).hexdigest()
            if folder.exists():
                state = self._read(folder / 'state.json')
                if state.get('request_digest') != fingerprint or state.get('kind') != 'refresh':
                    raise ValueError('AGY 原刷新操作归属不符')
                if state['phase'] == 'completed':
                    return self._read(folder / 'result.json')
                raise ValueError('AGY 原刷新结果待对账')
            folder.mkdir(mode=0o700)
            state = {'kind': 'refresh', 'operation_id': identity, 'account_id': account_id, 'generation': generation,
                'phase': 'pending', 'created_at': time.time(), 'proxy_url': proxy_url, 'request_digest': fingerprint}
            atomic_json(folder / 'state.json', state)
            # 只在唯一管理副本设置到期，强制原生刷新；权威数据库和在途 AT 保持原值。
            atomic_json(folder / 'input.json', document)
            pending = copy.deepcopy(document)
            pending['token']['expiry'] = '1970-01-01T00:00:00Z'
            stage, status = 'start_refresh', 'retrying'
            try:
                container = self._launch(folder, state, interactive=False, document=pending, native_args=['models'])
                stage = 'refresh'
                try:
                    models_completed = container.wait(timeout=45).get('StatusCode') == 0
                except (ReadTimeout, TimeoutError):
                    models_completed = False
                    state.setdefault('first_failure', stage)
                explicit_rejection = False
                if not models_completed:
                    # 只识别结构化的 OAuth 拒绝标记，原生输出可能含私有数据。
                    try:
                        output = container.logs(tail=80)
                        explicit_rejection = isinstance(output, bytes) and re.search(
                            rb'"error"\s*:\s*"invalid_grant"', output[-65536:]) is not None
                    except Exception:
                        pass
                # 原生可能已写入新凭据，随后才在模型目录卡住。确认唯一写者退出后再读取。
                stage = 'stop_refresh'
                self._stop(state)
                stage = 'credential_file'
                try:
                    updated = self._refresh_document(folder)
                except (OSError, ValueError):
                    if explicit_rejection:
                        stage, status = 'refresh', 'reauthorization_required'
                    raise
                if datetime.fromisoformat(updated['token']['expiry'].replace('Z', '+00:00')).timestamp() <= time.time() + 60:
                    stage, status = ('refresh', 'reauthorization_required') if explicit_rejection else (
                        'credential_expiry', 'needs_check')
                    raise ValueError('AGY 刷新后的有效期不足')
                stage = 'identity_check'
                verified = self.verify(updated, proxy_url, identity_only=True)
                stage = 'receipt'
                return self._save_refresh_result(folder, state, updated, verified)
            except Exception:
                state.setdefault('first_failure', stage)
                state.update(phase='reconcile', recovery_status=status)
                atomic_json(folder / 'state.json', state)
                self._stop(state)
                raise ValueError('AGY 原生刷新结果待对账') from None

    def _save_refresh_result(self, folder: Path, state: dict, document: dict, verified: dict) -> dict:
        """持久保存已核验的同操作凭据及首次失败摘要。"""
        outcome = {'document': document, **verified, 'proxy_url': state['proxy_url'],
            **{key: state[key] for key in ('operation_id', 'account_id', 'generation')}}
        if 'first_failure' in state:
            outcome['first_failure'] = state['first_failure']
        atomic_json(folder / 'result.json', outcome)
        state.update(phase='completed', recovery_status='ready')
        atomic_json(folder / 'state.json', state)
        return outcome

    def _recover_refresh(self, folder: Path, state: dict) -> dict:
        """只核对原刷新落盘的 AT，重启后保持首次失败。"""
        stage, status, expiry = 'stop_refresh', 'retrying', None
        try:
            self._stop(state)
            stage = 'credential_file'
            if state.get('recovery_status') == 'reauthorization_required':
                status = 'reauthorization_required'
                raise ValueError('AGY OAuth 明确拒绝原刷新')
            document = self._refresh_document(folder)
            expiry = datetime.fromisoformat(document['token']['expiry'].replace('Z', '+00:00')).timestamp()
            stage = 'credential_expiry'
            if expiry <= time.time() + 60:
                status = 'needs_check'
                raise ValueError('AGY 原刷新材料有效期不足')
            stage = 'identity_check'
            verified = self.verify(document, state['proxy_url'], identity_only=True)
            stage = 'receipt'
            return self._save_refresh_result(folder, state, document, verified)
        except Exception:
            if stage == 'credential_file' and status == 'retrying':
                status = 'needs_check'
            state.setdefault('first_failure', stage)
            state.update(phase='reconcile', recovery_status=status)
            atomic_json(folder / 'state.json', state)
            return {key: state[key] for key in ('operation_id', 'account_id', 'generation',
                'first_failure', 'recovery_status')} | {'expires_at': int(expiry) if expiry else None}

    def _refresh_document(self, folder: Path) -> dict:
        """优先保留已落盘的新 RT，原生省略时沿用原操作输入。"""
        value = self._read(folder / 'home' / TOKEN_PATH)
        if isinstance(value.get('token'), dict) and 'refresh_token' not in value['token']:
            value['token']['refresh_token'] = self._read(folder / 'input.json')['token']['refresh_token']
        return native_document(value)

    def prepare_import(self, identity: str, account_id: int, generation: int, document: dict, proxy_url: str) -> dict:
        """持久保存候选并按需刷新，再执行AT-only核验。@param identity 操作。@param account_id 账号。@param generation 原代次。@param document 候选。@param proxy_url 代理。@return 可恢复的私有回执。"""
        document = native_document(document)
        if type(account_id) is not int or account_id < 1 or type(generation) is not int or generation < 1:
            raise ValueError('AGY 导入归属无效')
        folder = self._folder(identity)
        with self._locked('account-' + str(account_id)):
            fingerprint = hashlib.sha256(json.dumps([account_id, generation, document, proxy_url], sort_keys=True).encode()).hexdigest()
            if folder.exists():
                state = self._read(folder / 'state.json')
                if state.get('kind') != 'import' or state.get('request_digest') != fingerprint or state.get('phase') != 'completed':
                    raise ValueError('AGY 原导入操作待核对')
                return self._read(folder / 'result.json')
            folder.mkdir(mode=0o700)
            state = dict(kind='import', operation_id=identity, account_id=account_id, generation=generation,
                phase='pending', created_at=time.time(), proxy_url=proxy_url, request_digest=fingerprint)
            atomic_json(folder / 'state.json', state)
            atomic_json(folder / 'input.json', document)
            try:
                expiry = datetime.fromisoformat(document['token']['expiry'].replace('Z', '+00:00')).timestamp()
                if expiry <= time.time() + 60:
                    # 旧AT到期时由同一操作持有RT，用候选线路刷新后再核验身份。
                    pending = copy.deepcopy(document)
                    pending['token']['expiry'] = '1970-01-01T00:00:00Z'
                    container = self._launch(folder, state, interactive=False, document=pending, native_args=['models'])
                    if container.wait(timeout=45).get('StatusCode') != 0:
                        raise ValueError('AGY 候选线路刷新未完成')
                    document = self._refresh_document(folder)
                    self._stop(state)
                outcome = {'document': document, **self.verify(document, proxy_url), 'proxy_url': proxy_url}
                atomic_json(folder / 'result.json', outcome)
                state['phase'] = 'completed'
                atomic_json(folder / 'state.json', state)
                return outcome
            except Exception:
                self._stop(state)
                state['phase'] = 'reconcile'
                atomic_json(folder / 'state.json', state)
                raise ValueError('AGY 原导入结果待核对') from None

    def recover(self, identity: str, account_id: int, generation: int, *, report_status: bool = False) -> dict:
        """恢复同操作当前私有材料。@param identity 操作。@param account_id 账号。@param generation 原代次。@param report_status 是否返回受控恢复状态。@return 私有回执。"""
        if type(account_id) is not int or account_id < 1 or type(generation) is not int or generation < 1:
            raise ValueError('AGY 对账归属无效')
        folder = self._folder(identity)
        with self._locked('account-' + str(account_id)), self._locked(identity):
            try:
                state = self._read(folder / 'state.json')
            except FileNotFoundError:
                return self._retire_locked(folder, identity, account_id, generation)
            if (state.get('account_id') != account_id or state.get('generation') != generation
                    or state.get('kind') not in ('refresh', 'authorization', 'import', 'retired')):
                raise ValueError('AGY 原操作归属不符')
            if state.get('phase') in ('retired', 'not_started'):
                return self._retired_result(state)
            if state.get('phase') == 'completed':
                result = self._read(folder / 'result.json')
                if state['kind'] == 'refresh':
                    expiry = datetime.fromisoformat(result['document']['token']['expiry'].replace('Z', '+00:00')).timestamp()
                    if expiry <= time.time() + 60:
                        if report_status:
                            return {'operation_id': identity, 'account_id': account_id, 'generation': generation,
                                'recovery_status': 'needs_check', 'first_failure': state.get('first_failure', 'credential_expiry')}
                        raise ValueError('AGY 原刷新材料有效期不足')
                if state['kind'] == 'authorization':
                    if result.get('proxy_url', state['proxy_url']) != state['proxy_url']:
                        raise ValueError('AGY 原授权回执线路不符')
                    result['proxy_url'] = state['proxy_url']
                return result | {'operation_id': identity, 'account_id': account_id, 'generation': generation}
            if state['kind'] == 'refresh':
                result = self._recover_refresh(folder, state)
                if 'document' not in result and not report_status:
                    raise ValueError('AGY 原生刷新结果待对账')
                return result
            if state.get('kind') == 'authorization' and not state.get('code_digest'):
                if report_status and state.get('phase') in ('starting', 'failed', 'expired', 'cancelled'):
                    return self._retire_locked(folder, identity, account_id, generation)
                if report_status:
                    return {'operation_id': identity, 'account_id': account_id, 'generation': generation,
                        'recovery_status': 'authorizing'}
                raise ValueError('AGY 原授权码尚待提交')
            if report_status and state.get('kind') == 'import':
                return {'operation_id': identity, 'account_id': account_id, 'generation': generation,
                    'recovery_status': 'needs_check'}
            # 先结束原唯一 RT 进程，再核对已原子保存的当前材料；恢复仅使用 AT。
            self._stop(state)
            if state['kind'] == 'import':
                document = self._refresh_document(folder) if (folder / 'home' / TOKEN_PATH).exists() else native_document(self._read(folder / 'input.json'))
            else:
                document = self._refresh_document(folder) if state['kind'] == 'refresh' else native_document(self._read(folder / 'home' / TOKEN_PATH))
            verified = self.verify(document, state['proxy_url'])
            outcome = {'document': document, **verified, 'proxy_url': state['proxy_url'], 'account_id': account_id,
                'generation': generation, 'operation_id': identity}
            atomic_json(folder / 'result.json', outcome)
            state['phase'] = 'completed'
            atomic_json(folder / 'state.json', state)
            return outcome

    def authorization_proxy_references(self, operations: list[str]) -> dict:
        """读取网关仍持有的授权线路。@param operations 原凭据操作。@return 内部目录引用。"""
        if not isinstance(operations, list) or any(not isinstance(item, str) for item in operations):
            raise ValueError('AGY 原授权操作无效')
        references = []
        for identity in operations:
            try:
                state = self._read(self._folder(identity) / 'state.json')
            except FileNotFoundError:
                # 授权驱动先保存状态再返回会话；未启动的刷新或导入没有已冻结的授权线路。
                continue
            if state.get('operation_id') != identity:
                raise ValueError('AGY 原操作归属不符')
            if state.get('kind') != 'authorization' or state.get('phase') not in (
                    'starting', 'authorizing', 'code_pending', 'completed', 'reconcile'):
                continue
            if state['proxy_url']:
                references.append([identity, state['proxy_url']])
        return {'references': references}

    def handle(self, action: str, value: dict) -> dict:
        """分派受信管理请求，严格限定每类输入。@param action 固定操作。@param value 私有请求。@return 原生结果。"""
        allowed = {'start': {'proxy_url', 'account_id', 'generation'}, 'exchange': {'session_id', 'code'}, 'cancel': {'session_id'},
            'verify': {'document', 'proxy_url'}, 'refresh': {'operation_id', 'account_id', 'generation', 'document', 'proxy_url'},
            'prepare': {'operation_id', 'account_id', 'generation', 'document', 'proxy_url'},
            'recover': {'operation_id', 'account_id', 'generation'},
            'recover-status': {'operation_id', 'account_id', 'generation'},
            'retire': {'operation_id', 'account_id', 'generation'},
            'proxy-references': {'operations'}}
        if not isinstance(value, dict) or action not in allowed:
            raise ValueError('AGY 管理输入无效')
        fields = allowed[action]
        if action == 'start' and value.get('replace_proxy') is True and value.get('account_id') is not None:
            fields = fields | {'replace_proxy'}
        if action == 'start' and 'operation_id' in value and value.get('account_id') is not None:
            fields = fields | {'operation_id'}
        if set(value) != fields:
            raise ValueError('AGY 管理输入无效')
        if 'proxy_url' in value and (not isinstance(value['proxy_url'], str) or len(value['proxy_url']) > 8192 or any(ord(c) < 32 for c in value['proxy_url'])):
            raise ValueError('AGY 代理配置无效')
        if action == 'start':
            return self.start(value['proxy_url'], value['account_id'], value['generation'], value.get('operation_id'))
        if action == 'exchange':
            return self.exchange(value['session_id'], value['code'])
        if action == 'cancel':
            return self.cancel(value['session_id'])
        if action == 'verify':
            return self.verify(value['document'], value['proxy_url'], include_quota=True)
        if action == 'refresh':
            return self.refresh(value['operation_id'], value['account_id'], value['generation'], value['document'], value['proxy_url'])
        if action == 'retire':
            return self.retire(value['operation_id'], value['account_id'], value['generation'])
        if action == 'prepare':
            return self.prepare_import(value['operation_id'], value['account_id'], value['generation'], value['document'], value['proxy_url'])
        if action == 'proxy-references':
            return self.authorization_proxy_references(value['operations'])
        try:
            return self.recover(value['operation_id'], value['account_id'], value['generation'],
                report_status=action == 'recover-status')
        except AgyOperationBusy:
            if action != 'recover-status':
                raise
            # 仍有实际写者持有文件锁。调用方只等待，并再次读取同范围的持久回执。
            return {**value, 'recovery_status': 'in_flight'}
