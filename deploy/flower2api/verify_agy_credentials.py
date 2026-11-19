"""独立验证 AGY 受管凭据合同；默认运行合成离线实验。"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import time
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from pathlib import Path
from secrets import compare_digest
from urllib.parse import urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/orchestrator'))
from runtime_files import atomic_json


SOURCE_SHA256 = '39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'
TOKEN_PATH = Path('.gemini/antigravity-cli/antigravity-oauth-token')
NATIVE_TEST_ROOT = Path('/opt/agy-runtime/oauth-test-1.5.9')


def private_json(path: Path, expected_uid: int | None = None) -> dict:
    """读取当前用户的受限普通 JSON 文件。

    :param path: 私有文件路径。
    :param expected_uid: 文件所有者；省略时使用当前用户。
    :return: JSON 对象；文件或内容异常时抛出受控错误。
    """
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != (os.geteuid() if expected_uid is None else expected_uid)
                or info.st_mode & 0o077 or info.st_size > 65536):
            raise ValueError('私有实验文件权限或大小不符合约定')
        try:
            value = json.loads(stream.read(65537))
        except (ValueError, UnicodeError):
            raise ValueError('私有实验文件内容无效') from None
    if not isinstance(value, dict):
        raise ValueError('私有实验文件应为 JSON 对象')
    return value


def native_document(value: dict, require_refresh: bool = False) -> dict:
    """校验已观察到的 consumer OAuth 文件结构，保留原有扩展字段。

    :param value: 原生凭据对象。
    :param require_refresh: 是否要求管理侧具有刷新令牌。
    :return: 已校验的独立副本；错误正文保持脱敏。
    """
    token = value.get('token') if isinstance(value, dict) else None
    if (not isinstance(value, dict) or value.get('auth_method') != 'consumer' or not isinstance(token, dict)
            or not isinstance(token.get('access_token'), str) or not token['access_token'].strip()
            or not isinstance(token.get('expiry'), str)):
        raise ValueError('原生凭据结构不完整')
    refresh = token.get('refresh_token')
    if refresh is not None and not isinstance(refresh, str):
        raise ValueError('原生刷新凭据类型无效')
    if require_refresh and (not isinstance(refresh, str) or not refresh.strip()):
        raise ValueError('管理侧缺少完整刷新凭据')
    try:
        expiry = datetime.fromisoformat(token['expiry'].replace('Z', '+00:00'))
        if expiry.tzinfo is None:
            raise ValueError
    except ValueError:
        raise ValueError('原生凭据有效期无效') from None
    return copy.deepcopy(value)


def access_document(value: dict, empty_refresh: bool = False) -> dict:
    """生成仅含访问凭据的工作副本。

    :param value: 已观察结构的原生凭据。
    :param empty_refresh: 使用显式空值覆盖刷新令牌。
    :return: 保留原身份及扩展字段的独立副本。
    """
    document = native_document(value)
    document['token'].pop('refresh_token', None)
    if empty_refresh:
        document['token']['refresh_token'] = ''
    return document


class CredentialLab:
    """使用真实文件锁与原子发布验证实验状态，作用域限合成夹具。

    :param root: 实验私有目录。
    :param document: 首次创建时的合成完整凭据；恢复时省略。
    """

    def __init__(self, root: Path, document: dict | None = None):
        """打开实验状态。

        :param root: 当前实验的私有目录。
        :param document: 首次创建材料。
        :return: 无。
        """
        self.root = root
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = root / 'authority.json'
        self.lock_path = root / 'authority.lock'
        with self._locked():
            if not self.path.exists():
                if document is None:
                    raise ValueError('实验权威状态缺失')
                atomic_json(self.path, {'generation': 1, 'phase': 'ready', 'operation_id': None,
                    'document': native_document(document, require_refresh=True)})
            self._read()

    @contextmanager
    def _locked(self):
        """每次打开独立文件描述符，使线程和进程共享同一排他门禁。"""
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _read(self) -> dict:
        """读取并校验权威状态，未知阶段保持隔离。"""
        state = private_json(self.path)
        if (type(state.get('generation')) is not int or state['generation'] < 1
                or state.get('phase') not in ('ready', 'pending', 'reconcile')):
            raise ValueError('实验权威状态损坏')
        native_document(state.get('document'), require_refresh=True)
        return state

    def snapshot(self) -> dict:
        """取得锁内当前权威快照。

        :return: 私有完整状态，调用方负责保持秘密。
        """
        with self._locked():
            return self._read()

    def refresh(self, expected_generation: int, endpoint: str) -> int:
        """向本地合成服务刷新一次，并按代次原子保存结果。

        :param expected_generation: 调用方观察到的原代次。
        :param endpoint: 仅允许回环 HTTP 合成刷新地址。
        :return: 当前已持久化代次；未知结果进入对账并抛出受控错误。
        """
        target = urlsplit(endpoint)
        if (target.scheme != 'http' or target.hostname != '127.0.0.1' or not target.port
                or target.username or target.password or target.query or target.fragment):
            raise ValueError('离线刷新只接受回环合成服务')
        with self._locked():
            state = self._read()
            if state['phase'] != 'ready':
                raise ValueError('实验刷新结果待对账')
            if expected_generation != state['generation']:
                return state['generation']
            # 待确认和权威材料共用一次持久提交，崩溃恢复不会重发未知的旧 RT。
            operation_id = uuid.uuid4().hex
            state.update(phase='pending', operation_id=operation_id)
            atomic_json(self.path, state)
            connection = HTTPConnection(target.hostname, target.port, timeout=2)
            try:
                body = urlencode({'grant_type': 'refresh_token',
                    'refresh_token': state['document']['token']['refresh_token']})
                connection.request('POST', target.path or '/', body,
                    {'Content-Type': 'application/x-www-form-urlencoded'})
                response = connection.getresponse()
                payload = response.read(65537)
                if response.status != 200 or len(payload) > 65536:
                    raise ValueError('合成刷新响应无效')
                result = json.loads(payload)
                if (not isinstance(result, dict) or not isinstance(result.get('access_token'), str)
                        or not result['access_token'].strip() or type(result.get('expires_in')) is not int
                        or not 0 < result['expires_in'] <= 7200):
                    raise ValueError('合成刷新响应缺少有效访问凭据')
                token = state['document']['token']
                token.update(access_token=result['access_token'], expires_in=result['expires_in'],
                    expiry=(datetime.now(timezone.utc) + timedelta(seconds=result['expires_in'])).isoformat())
                if 'refresh_token' in result:
                    if not isinstance(result['refresh_token'], str) or not result['refresh_token'].strip():
                        raise ValueError('合成刷新响应包含无效刷新凭据')
                    token['refresh_token'] = result['refresh_token']
                state.update(generation=state['generation'] + 1, phase='ready', operation_id=None)
                atomic_json(self.path, state)
                return state['generation']
            except Exception:
                # 重新读取已落盘状态，保留 rename 成功后的新 RT；未知提交结果沿原操作对账。
                pending = private_json(self.path)
                pending['phase'] = 'reconcile'
                pending['operation_id'] = operation_id
                atomic_json(self.path, pending)
                raise ValueError('合成刷新结果待对账') from None
            finally:
                connection.close()

    def publish(self, expected_generation: int, destination: Path) -> bool:
        """只发布匹配当前代次的 AT-only 工作副本。

        :param expected_generation: 本次发布的预期代次。
        :param destination: 隔离 HOME 的原生凭据路径。
        :return: 发布成功为真，旧回执或待对账状态为假。
        """
        with self._locked():
            state = self._read()
            if state['phase'] != 'ready' or state['generation'] != expected_generation:
                return False
            atomic_json(destination, access_document(state['document']))
            return True


def retry_allowed(attempt: dict, current: dict, *, authentication_failed: bool,
                  response_started: bool, tool_pending: bool, deadline: float) -> bool:
    """计算实验中的单次同账号认证恢复门槛。

    :param attempt: 冻结的账号、代次、原生凭据 document 及已发送次数。
    :param current: 当前账号、权威代次和原生凭据 document。
    :param authentication_failed: 已观察到真实认证失败分类。
    :param response_started: 已向调用方发送响应。
    :param tool_pending: 存在原生待回填工具轮。
    :param deadline: 原准入单调截止时间。
    :return: 是否允许进入一次恢复尝试；此函数仅属于离线参考模型。
    """
    try:
        token = native_document(current.get('document'))['token']
        failed = native_document(attempt.get('document'))['token']
        expiry = datetime.fromisoformat(token['expiry'].replace('Z', '+00:00')).timestamp()
        changed = not compare_digest(token['access_token'].encode(), failed['access_token'].encode())
    except (ValueError, UnicodeError):
        return False
    return (authentication_failed and not response_started and not tool_pending
        and time.monotonic() < deadline and attempt['attempts'] == 1
        and attempt['account'] == current['account'] and current['phase'] == 'ready'
        and current['generation'] > attempt['generation'] and changed and expiry > time.time())


def _native_models(root: Path, home: Path, workspace: Path, image: str, name: str, output: Path) -> dict:
    """在仅挂载本次 HOME 的原生容器中执行一次模型目录读取。"""
    command = ['docker', 'run', '--rm', '--name', name, '--pull', 'never',
        '--user', '1001:1001', '--network', 'bridge', '--read-only',
        '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=128m', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges:true', '--env', 'HOME=/home/agy',
        '--env', 'USER=agy', '--env', 'LANG=C.UTF-8', '--env', 'AGY_CLI_DISABLE_AUTO_UPDATE=true',
        '--mount', 'type=bind,src=' + str(root / 'native/agy') + ',dst=/opt/native/agy,readonly',
        '--mount', 'type=bind,src=' + str(home) + ',dst=/home/agy',
        '--mount', 'type=bind,src=' + str(workspace) + ',dst=/workspace',
        '--workdir', '/workspace', '--entrypoint', '/opt/native/agy', image, 'models']
    try:
        result = subprocess.run(command, capture_output=True, timeout=45)
    except subprocess.TimeoutExpired:
        return {'status': 'timeout', 'exit_code': None, 'model_names_present': False}
    finally:
        # docker 客户端退出并不保证容器退出；只清理本次明确命名的实验容器。
        subprocess.run(['docker', 'rm', '--force', name], capture_output=True, timeout=15)
    for label, data in (('stdout', result.stdout), ('stderr', result.stderr)):
        descriptor = os.open(output / label, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
    content = (result.stdout + result.stderr).lower()
    return {'status': 'completed', 'exit_code': result.returncode,
        'stdout_bytes': len(result.stdout), 'stderr_bytes': len(result.stderr),
        'model_names_present': b'gemini-' in content,
        'auth_error_present': any(marker in content for marker in
            (b'unauthenticated', b'failed to authenticate', b'not authenticated',
             b'invalid_token', b'401', b'no refresh token'))}


def native_probe(config: dict) -> dict:
    """在固定测试宿主执行原生目录的 RT 缺省、空值和无效 AT 对照。

    :param config: 只接受唯一 run_id 的私有实验配置。
    :return: 脱敏结果，模型生成阶段保持独立的待验证标记。
    """
    if (set(config) != {'run_id'} or not isinstance(config['run_id'], str)
            or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', config['run_id'])):
        raise ValueError('原生目录实验配置应只包含合法 run_id')
    root = NATIVE_TEST_ROOT
    descriptor = os.open(root / 'credential-contract.lock',
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('原生探针锁的所有者或权限无效')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('原生凭据探针正在接管，稍后重试') from None
        # 预检也在锁内；恢复和最终状态落盘完成后才释放同一账号的接管权。
        return _native_probe_locked(config, root)
    finally:
        os.close(descriptor)


def _native_probe_locked(config: dict, root: Path) -> dict:
    """在持有账号接管锁期间执行环境重检、管理刷新和恢复。"""
    with (root / 'native/agy').open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != SOURCE_SHA256:
            raise ValueError('固定原版执行体身份不匹配')
    original = json.loads(subprocess.check_output(['docker', 'inspect', 'agy-oauth-test-159']))[0]
    if not original['State']['Running'] or original['Config']['User'] != '1001:1001':
        raise ValueError('原生测试环境状态或身份不符合约定')
    rows = subprocess.check_output(['docker', 'top', 'agy-oauth-test-159',
        '-eo', 'pid,ppid,comm'], text=True).splitlines()[1:]
    if [row.split()[-1] for row in rows] != ['agy']:
        raise ValueError('测试账号存在额外原生进程，需先排空活动')
    experiment = root / 'credential-contract' / config['run_id']
    experiment.mkdir(mode=0o700, parents=True, exist_ok=False)
    summary = {'schema_version': 1, 'evidence': 'native_oauth', 'scope': 'model_directory',
        'source_sha256': SOURCE_SHA256, 'run_id': config['run_id'], 'model_submissions': 0, 'cases': [],
        'original_restored': False, 'phase': 'preparing', 'passed': False,
        'pending': ['原生模型文本与SSE', '常驻进程实际换代', '工具回填与遥测排空']}
    state = experiment / 'summary.json'
    atomic_json(state, summary)
    stopped = False
    authority_confirmed = False
    try:
        subprocess.run(['docker', 'stop', '--time', '20', 'agy-oauth-test-159'],
            check=True, capture_output=True, timeout=25)
        stopped = True
        summary['phase'] = 'manager_pending'
        atomic_json(state, summary)
        before = native_document(private_json(root / 'home' / TOKEN_PATH, 1001), require_refresh=True)
        manager = experiment / 'manager'
        manager.mkdir(mode=0o700)
        outcome = _native_models(root, root / 'home', root / 'workspace', original['Config']['Image'],
            'bench-agy-manager-' + uuid.uuid4().hex[:12], manager)
        after = native_document(private_json(root / 'home' / TOKEN_PATH, 1001), require_refresh=True)
        expiry = datetime.fromisoformat(after['token']['expiry'].replace('Z', '+00:00'))
        summary['manager'] = {**outcome, 'access_changed': not compare_digest(
            before['token']['access_token'], after['token']['access_token'])}
        if outcome['exit_code'] != 0 or expiry.timestamp() <= time.time() + 60:
            summary['phase'] = 'reconcile'
            return summary
        authority_confirmed = True
        summary['phase'] = 'probing'
        atomic_json(state, summary)
        for mode in ('missing', 'empty', 'invalid-access'):
            case_root = experiment / mode
            home, workspace = case_root / 'home', case_root / 'workspace'
            destination = home / TOKEN_PATH
            destination.parent.mkdir(mode=0o700, parents=True)
            workspace.mkdir(mode=0o700)
            document = access_document(after, empty_refresh=mode == 'empty')
            if mode == 'invalid-access':
                document['token']['access_token'] = 'synthetic-invalid-access'
            atomic_json(destination, document)
            settings = root / 'home/.gemini/antigravity-cli/settings.json'
            if settings.exists():
                # 仅沿用已有账号设置，避免首次交互设置成为认证实验的额外变量。
                atomic_json(destination.parent / 'settings.json', private_json(settings, 1001))
            for path in (home, workspace, *home.rglob('*')):
                os.chown(path, 1001, 1001)
            outcome = _native_models(root, home, workspace, original['Config']['Image'],
                'bench-agy-probe-' + uuid.uuid4().hex[:12], case_root)
            current = native_document(private_json(destination, 1001))
            outcome.update(mode=mode, refresh_present=bool(current['token'].get('refresh_token')),
                access_unchanged=compare_digest(current['token']['access_token'], document['token']['access_token']))
            expected = (outcome['exit_code'] != 0 and outcome.get('auth_error_present')
                if mode == 'invalid-access' else outcome['exit_code'] == 0 and outcome['model_names_present'])
            outcome['passed'] = bool(expected and not outcome['refresh_present'] and outcome['access_unchanged'])
            summary['cases'].append(outcome)
            atomic_json(state, summary)
        summary['passed'] = all(case['passed'] for case in summary['cases'])
        summary['phase'] = 'completed'
        return summary
    finally:
        # 管理刷新结果未知时保留停止状态与对账记录，避免重新使用可能已轮换的 RT。
        if stopped and authority_confirmed:
            restored = subprocess.run(['docker', 'start', 'agy-oauth-test-159'],
                capture_output=True, timeout=20)
            summary['original_restored'] = restored.returncode == 0
        if not summary['original_restored']:
            summary['passed'] = False
        atomic_json(state, summary)


def main() -> int:
    """执行默认离线实验或显式原生目录探针，并输出脱敏摘要。

    :return: 全部离线实验通过返回零。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='脱敏摘要保存路径')
    parser.add_argument('--native-config', type=Path, help='在固定测试宿主执行原生模型目录实验的私有配置')
    args = parser.parse_args()
    if args.native_config:
        try:
            summary = native_probe(private_json(args.native_config))
        except Exception as error:
            summary = {'schema_version': 1, 'evidence': 'native_oauth', 'passed': False,
                'error_type': type(error).__name__}
        if args.output:
            atomic_json(args.output, summary)
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary['passed'] else 1
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_agy_credentials.py')
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream).run(suite)
    summary = {'schema_version': 1, 'evidence': 'offline_fixture',
        'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped),
        'passed': result.testsRun > 0 and result.wasSuccessful() and not result.skipped,
        'native_verified': False}
    if args.output:
        atomic_json(args.output, summary)
    print(json.dumps(summary, ensure_ascii=False))
    if not summary['passed']:
        sys.stderr.write(stream.getvalue())
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
