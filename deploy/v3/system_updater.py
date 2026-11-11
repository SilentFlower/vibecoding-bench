#!/usr/bin/env python3
"""独立平台更新执行器：持久操作、签名发现、单例切换与故障恢复。"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import secrets
import socketserver
import struct
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socket import SOL_SOCKET, SO_PEERCRED
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'orchestrator'))
from runtime_files import atomic_json, atomic_text, directory_fd
from storage_maintenance import acquire_storage_lock
from system_update_contract import (DEPLOYMENT_RE, DOWNLOAD_ROOT, INDEX_LIMIT, MANIFEST_LIMIT,
    RELEASE_RE, REPOSITORY, SHA_RE, TERMINAL, compatible_data, fetch_bytes, fetch_repository_file, safe_read, strict_json,
    utc_now, validate_index, validate_operation, validate_release, verify_signed)
from system_update_host import HostDeployment

DONE = TERMINAL | {'prepared'}
STATE_LIMIT = 8 * 1024 * 1024


class UpdateConflict(ValueError):
    """冻结的现场或操作身份发生变化，对外返回 409。"""


def validate_policy(value: dict) -> dict:
    """核对首次接入固化的单一部署策略。

    :param value: root 私有策略。
    :return: 原策略。
    """
    fields = {'schema_version', 'deployment', 'data_root', 'env_file', 'state_root', 'public_key',
        'compose_file', 'compose_file_sha256', 'override_file', 'override_file_sha256'}
    if set(value) != fields or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('更新服务策略格式无效')
    if not isinstance(value['deployment'], str) or not DEPLOYMENT_RE.fullmatch(value['deployment']):
        raise ValueError('更新服务部署身份无效')
    for key in ('public_key', 'compose_file_sha256', 'override_file_sha256'):
        if not isinstance(value[key], str) or not SHA_RE.fullmatch(value[key]):
            raise ValueError('更新服务策略摘要无效')
    for key in ('data_root', 'env_file', 'state_root', 'compose_file', 'override_file'):
        path = Path(value[key])
        if not path.is_absolute() or path != path.resolve() or '..' in path.parts:
            raise ValueError('更新服务策略路径必须为固化真实绝对路径')
    if Path(value['state_root']).is_relative_to(Path(value['data_root'])):
        raise ValueError('更新状态根需要独立于业务数据根')
    return value


class SystemUpdater:
    """负责一个部署的独占更新，操作日志先于副作用落盘。"""

    def __init__(self, policy: dict, backend=None) -> None:
        """读取已有安装状态，未知状态保持维护恢复路径。

        :param policy: 已校验固定策略。
        :param backend: 测试可注入受控宿主边界。
        :return: None。
        """
        self.policy = validate_policy(policy)
        self.root = Path(policy['state_root'])
        self.backend = backend or HostDeployment(policy)
        self.lock = threading.RLock()
        self.worker = None
        self.checking = False
        self._verified = {}
        self.state = strict_json(safe_read(self.root / 'state.json', STATE_LIMIT, private=True), STATE_LIMIT)
        if (self.state.get('schema_version') != 1 or self.state.get('deployment') != policy['deployment']
                or not isinstance(self.state.get('revision'), str) or not isinstance(self.state.get('history'), list)):
            raise ValueError('系统更新安装状态损坏，需要恢复')
        validate_release(self.state['current']['release'])
        # 当前安装和回退来源均必须能由首次接入的信任根重新复核。
        for installation in [self.state['current'], *self.state['history']]:
            signed = self.load_release(installation['release']['release'])
            if installation['release'] != signed or set(installation['selection']) != {'control', 'account'}:
                raise ValueError('安装记录与受信发行来源不符')
            for role, selected in installation['selection'].items():
                source = self.load_release('system-' + selected['release'])
                if selected != source[role]:
                    raise ValueError('已选组件与其签名来源不符')
            if installation['selection']['control'] != signed['control']:
                raise ValueError('控制服务来源与安装发行不符')

    def _persist(self) -> None:
        atomic_json(self.root / 'state.json', self.state)

    def _record(self, operation: dict) -> None:
        with self.lock:
            path = self.root / 'operations' / operation['operation_id'] / 'operation.json'
            # 控制线程单独读取并保存取消意图，执行线程的旧快照必须保留该单向标记。
            if path.exists() and self._operation(operation['operation_id']).get('cancel_requested') is True:
                operation['cancel_requested'] = True
            atomic_json(path, operation)
            self._persist()

    def _operation(self, identifier: str) -> dict:
        if not isinstance(identifier, str) or str(uuid.UUID(identifier)) != identifier:
            raise ValueError('操作身份无效')
        return strict_json(safe_read(self.root / 'operations' / identifier / 'operation.json', STATE_LIMIT, private=True), STATE_LIMIT)

    def load_release(self, release: str, expected: str | None = None) -> dict:
        """按精确标签和签名复核缓存发行。

        :param release: 精确标签。
        :param expected: 可选冻结清单 SHA256。
        :return: 已验证合同。
        """
        if not isinstance(release, str) or not RELEASE_RE.fullmatch(release):
            raise ValueError('发行标签无效')
        folder = self.root / 'releases' / release
        raw = safe_read(folder / 'system-release.json')
        if expected and hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('发行清单与冻结摘要不符')
        signature = safe_read(folder / 'system-release.sig', 64)
        identity = hashlib.sha256(raw + signature).hexdigest()
        cached = self._verified.get(release)
        if cached and cached[0] == identity:
            return copy.deepcopy(cached[1])
        value = validate_release(verify_signed(raw, signature, self.policy['public_key']))
        if value['release'] != release:
            raise ValueError('缓存发行标签与清单不符')
        self._verified[release] = (identity, copy.deepcopy(value))
        return value

    def releases(self) -> dict:
        """返回脱敏的已验证版本缓存及最近检查状态。

        :return: 版本目录。
        """
        with self.lock:
            fresh = True
            try:
                validate_index(self.state.get('catalog', {}))
            except ValueError:
                fresh = False
            rows = []
            for entry in sorted(self.state.get('catalog', {}).get('releases', []), key=lambda item: item['sequence'], reverse=True)[:8]:
                try:
                    value = self.load_release(entry['release'], entry['manifest']['sha256'])
                    rows.append({'release': value['release'], 'sequence': value['sequence'],
                        'published_at': value['published_at'], 'changes': value['changes'],
                        'manifest_sha256': entry['manifest']['sha256'],
                        'data_compatible': compatible_data(self.state['current']['release']['data_compatibility'], value['data_compatibility']),
                        'account_changed': self.state['current']['selection']['account']['content_sha256'] != value['account']['content_sha256']})
                except (ValueError, OSError):
                    continue
            return {'releases': rows, 'fresh': fresh, 'checking': self.checking, 'checked_at': self.state.get('checked_at'),
                'check_error': self.state.get('check_error') or (None if fresh else '版本目录待重新检查，已安装版本继续保留')}

    def status(self) -> dict:
        """读取安装和操作状态，重启后仍能继续展示。

        :return: 公开管理状态。
        """
        with self.lock:
            operation = self._operation(self.state['last_operation']) if self.state.get('last_operation') else None
            current = self.state['current']
            history = [{'release': item['release']['release'],
                'manifest_sha256': hashlib.sha256(safe_read(self.root / 'releases' / item['release']['release'] / 'system-release.json')).hexdigest(),
                'installed_at': item.get('installed_at'),
                'rollback_available': compatible_data(item['release']['data_compatibility'], current['release']['data_compatibility'])}
                for item in self.state['history'][:8]]
            return {'installed': True, 'revision': self.state['revision'],
                'deployment': self.policy['deployment'], 'current_release': current['release']['release'],
                'components': {role: {key: value for key, value in entry.items() if key in ('release', 'reference', 'content_sha256')}
                    for role, entry in current['selection'].items()},
                'operation': self._public_operation(operation) if operation else None,
                'busy': bool(self.state.get('active_operation')), 'history': history,
                'checked_at': self.state.get('checked_at'), 'check_error': self.state.get('check_error')}

    def _public_operation(self, operation: dict) -> dict:
        return {key: copy.deepcopy(operation.get(key)) for key in ('operation_id', 'action', 'phase', 'created_at',
            'updated_at', 'target_release', 'error', 'blockers', 'cancel_requested', 'cleanup', 'environment_results')}

    def operation(self, identifier: str) -> dict:
        """读取指定操作的脱敏进度。

        :param identifier: 原操作 UUID。
        :return: 原操作公开状态。
        """
        with self.lock:
            return self._public_operation(self._operation(identifier))

    def _download_release(self, entry: dict) -> None:
        folder = self.root / 'releases' / entry['release']
        if folder.exists():
            self.load_release(entry['release'], entry['manifest']['sha256'])
            return
        raw = fetch_bytes(f'{DOWNLOAD_ROOT}/{entry["release"]}/system-release.json', MANIFEST_LIMIT)
        signature = fetch_bytes(f'{DOWNLOAD_ROOT}/{entry["release"]}/system-release.sig', 64)
        if len(raw) != entry['manifest']['size'] or hashlib.sha256(raw).hexdigest() != entry['manifest']['sha256']:
            raise ValueError('版本目录与发行清单摘要不符')
        value = validate_release(verify_signed(raw, signature, self.policy['public_key']))
        if value['release'] != entry['release'] or value['sequence'] != entry['sequence']:
            raise ValueError('版本目录与发行清单身份不符')
        temporary = folder.with_name('.' + folder.name + '-' + uuid.uuid4().hex)
        temporary.mkdir(mode=0o700)
        atomic_text(temporary / 'system-release.json', raw.decode())
        descriptor = os.open(temporary / 'system-release.sig', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(signature)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, folder)
        directory = directory_fd(folder.parent)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def check(self) -> dict:
        """后台获取同一 commit 的签名目录，安装版本保持原状。

        :return: 检查已登记状态。
        """
        with self.lock:
            if self.checking:
                return {'checking': True}
            self.checking = True
        def worker():
            try:
                reference = strict_json(fetch_bytes(f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/updates/v3', 65536))
                commit = reference.get('object', {}).get('sha', '')
                if not re.fullmatch(r'[a-f0-9]{40}', commit):
                    raise ValueError('版本目录提交身份无效')
                raw = fetch_repository_file('index.json', commit, INDEX_LIMIT)
                signature = fetch_repository_file('index.sig', commit, 64)
                with self.lock:
                    highest = self.state.get('catalog', {}).get('sequence')
                value = validate_index(verify_signed(raw, signature, self.policy['public_key'], INDEX_LIMIT), highest)
                # 新目录只在所有列出清单验签完成后提交，半批失败沿用旧目录。
                for entry in value['releases']:
                    self._download_release(entry)
                with self.lock:
                    self.state.update(catalog=value, check_error=None, checked_at=utc_now())
                    self._persist()
            except Exception:
                with self.lock:
                    self.state.update(check_error='版本检查失败，保留上次已验证结果', checked_at=utc_now())
                    self._persist()
            finally:
                with self.lock:
                    self.checking = False
        threading.Thread(target=worker, daemon=True, name='v3-update-check').start()
        return {'checking': True}

    def submit(self, action: str, body: dict) -> dict:
        """原子登记冻结操作，后续异步执行实际副作用。

        :param action: prepare、install 或 rollback。
        :param body: 严格冻结请求。
        :return: 操作公开状态。
        """
        if action not in ('prepare', 'install', 'rollback'):
            raise ValueError('更新动作无效')
        validate_operation(body)
        with self.lock:
            path = self.root / 'operations' / body['operation_id'] / 'operation.json'
            if path.exists():
                previous = self._operation(body['operation_id'])
                if previous['request'] != body or previous['action'] != action:
                    raise UpdateConflict('同一操作身份已经绑定其他参数')
                if previous.get('completion_revision') and previous['completion_revision'] != self.state['revision']:
                    raise UpdateConflict('旧操作后现场版本已经变化')
                return self._public_operation(previous)
            if self.state.get('active_operation') or body['expected_revision'] != self.state['revision']:
                raise UpdateConflict('平台现场版本已经变化，请刷新后确认')
            if action != 'rollback':
                catalog = validate_index(self.state.get('catalog', {}))
                if not any(entry['release'] == body['target_release'] and entry['manifest']['sha256'] == body['target_manifest_sha256']
                        for entry in catalog['releases']):
                    raise ValueError('目标版本不在当前受信目录中，请重新检查版本')
            target = self.load_release(body['target_release'], body['target_manifest_sha256'])
            original = copy.deepcopy(self.state['current'])
            selected = {'release': target, 'selection': {role: copy.deepcopy(target[role]) for role in ('control', 'account')}}
            if action == 'rollback':
                stored = next((item for item in self.state['history'] if item['release']['release'] == target['release']), None)
                if not stored or not compatible_data(target['data_compatibility'], original['release']['data_compatibility']):
                    raise ValueError('当前数据合同不允许回退到所选版本')
                selected = copy.deepcopy(stored)
            elif not compatible_data(original['release']['data_compatibility'], target['data_compatibility']):
                raise ValueError('本版本涉及不兼容数据迁移，需要专项维护')
            elif original['selection']['account']['content_sha256'] == target['account']['content_sha256']:
                selected['selection']['account'] = copy.deepcopy(original['selection']['account'])
            if (action != 'prepare' and selected['release']['release'] == original['release']['release']
                    and selected['selection'] == original['selection']):
                raise UpdateConflict('目标组合已经安装')
            revision = str(uuid.uuid4())
            operation = {'schema_version': 1, 'operation_id': body['operation_id'], 'action': action,
                'request': copy.deepcopy(body), 'target_release': target['release'], 'target': target,
                'original': original, 'selected': selected, 'revision': revision,
                'epoch': str(uuid.uuid4()), 'phase': 'preparing', 'created_at': utc_now(), 'updated_at': utc_now(),
                'error': None, 'blockers': [], 'cancel_requested': False}
            folder = path.parent
            folder.mkdir(mode=0o700)
            self.state.update(revision=revision, active_operation=body['operation_id'], last_operation=body['operation_id'])
            self._record(operation)
            self.worker = threading.Thread(target=self._execute, args=(operation,), daemon=True, name='v3-system-install')
            self.worker.start()
            return self._public_operation(operation)

    def _phase(self, operation: dict, phase: str, **fields) -> None:
        with self.lock:
            operation.update(phase=phase, updated_at=utc_now(), **fields)
            self._record(operation)

    def _cancelled(self, operation: dict) -> bool:
        with self.lock:
            return self._operation(operation['operation_id']).get('cancel_requested') is True

    def _finish(self, operation: dict, phase: str, **fields) -> None:
        with self.lock:
            self.state['active_operation'] = None
            operation['completion_revision'] = self.state['revision']
            self._phase(operation, phase, **fields)

    def _execute(self, operation: dict) -> None:
        descriptor = None
        try:
            selected = operation['selected']
            self.backend.prepare(operation['target'], selected['selection'], self.root / 'releases' / operation['target_release'])
            if self._cancelled(operation):
                self._finish(operation, 'cancelled')
                return
            if operation['action'] == 'prepare':
                self._finish(operation, 'prepared')
                return
            descriptor = acquire_storage_lock(Path(self.policy['data_root']))
            operation['before'] = self.backend.capture(operation['original'])
            self._phase(operation, 'draining')
            self.backend.block(operation)
            deadline = time.monotonic() + operation['request']['drain_timeout_seconds']
            while True:
                evidence = self.backend.drained(operation)
                if self._cancelled(operation):
                    self.backend.abandon(operation)
                    self._finish(operation, 'cancelled')
                    return
                if evidence['ready']:
                    break
                self._phase(operation, 'draining', blockers=evidence['blockers'])
                if time.monotonic() >= deadline:
                    raise TimeoutError('在途工作排空超时')
                time.sleep(0.5)
            # 以在途自然结束后的身份和环境为切换基线，接纳原工作合法完成的变化。
            operation['before'] = self.backend.capture(operation['original'])
            # 与取消接口共用锁，使最后一次取消核对和进入切换成为同一个边界。
            with self.lock:
                cancelled = self._cancelled(operation)
                if not cancelled:
                    self._phase(operation, 'switching', blockers=[])
            if cancelled:
                self.backend.abandon(operation)
                self._finish(operation, 'cancelled')
                return
            self.backend.switch(operation, selected)
            self._phase(operation, 'verifying')
            self.backend.wait_controls(time.monotonic() + 180)
            self.backend.update_environments(operation, selected, lambda: self._record(operation))
            self.backend.health(operation, selected)
            self._phase(operation, 'committing')
            with self.lock:
                selected['installed_at'] = utc_now()
                if operation.get('after'):
                    selected['data_versions'] = operation['after']
                self.state['history'] = [operation['original'], *[item for item in self.state['history']
                    if item['release']['release'] != selected['release']['release']]][:64]
                self.state['current'] = selected
                self._record(operation)
            self.backend.release(operation)
            self._phase(operation, 'cleaning')
            self._clean(operation)
        except Exception as error:
            phase = operation['phase']
            reason = str(error) if isinstance(error, (ValueError, TimeoutError)) else '更新执行失败，需要核对运行状态'
            reason = reason[:300]
            if phase == 'preparing':
                self._finish(operation, 'failed', error=reason)
            elif phase == 'draining':
                try:
                    self.backend.abandon(operation)
                    self._finish(operation, 'failed', error=reason)
                except Exception:
                    self._phase(operation, 'reconcile', error='排空失败，维护门禁及原版状态需要对账')
            elif phase == 'cleaning':
                self._finish(operation, 'succeeded_cleanup_pending', error='新版本已生效，旧制品回收需要重试')
            else:
                try:
                    self._phase(operation, 'restoring', error=reason)
                    self.backend.restore(operation, lambda: self._record(operation))
                    with self.lock:
                        self.state['current'] = operation['original']
                        self.state['history'] = [item for item in self.state['history'] if item['release']['release'] != operation['original']['release']['release']]
                    self._finish(operation, 'restored', error=reason)
                except Exception:
                    self._phase(operation, 'reconcile', error='切换恢复尚未完成，维护门禁保持关闭')
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _clean(self, operation: dict) -> None:
        try:
            result = self.backend.cleanup(self.state['current'], self.state['history'], [operation['original']])
            self._finish(operation, 'succeeded', cleanup=result, error=None)
        except Exception:
            self._finish(operation, 'succeeded_cleanup_pending', error='服务已验收，旧制品回收需要重试')

    def control(self, identifier: str, action: str, body: dict) -> dict:
        """基于当前 revision 取消等待或恢复原操作。

        :param identifier: 原操作。
        :param action: cancel 或 recover。
        :param body: 仅含 expected_revision。
        :return: 已登记的操作状态。
        """
        if set(body) != {'expected_revision'} or action not in ('cancel', 'recover'):
            raise ValueError('更新控制参数无效')
        with self.lock:
            if body['expected_revision'] != self.state['revision']:
                raise UpdateConflict('平台现场版本已经变化')
            operation = self._operation(identifier)
            if action == 'cancel':
                if operation['phase'] not in ('preparing', 'draining') or self.state.get('active_operation') != identifier:
                    raise UpdateConflict('操作已经进入切换或结束阶段')
                operation['cancel_requested'] = True
                self._record(operation)
            else:
                if self.worker and self.worker.is_alive():
                    raise UpdateConflict('原更新动作仍在收口')
                if self.state.get('active_operation') not in (None, identifier):
                    raise UpdateConflict('其他操作仍持有部署恢复权')
                if operation['phase'] not in ('reconcile', 'succeeded_cleanup_pending'):
                    raise UpdateConflict('本操作无需恢复')
                self.state.update(active_operation=identifier, last_operation=identifier, revision=str(uuid.uuid4()))
                self._record(operation)
                self.worker = threading.Thread(target=self._recover, args=(operation,), daemon=True, name='v3-system-recover')
                self.worker.start()
            return self._public_operation(operation)

    def _recover(self, operation: dict) -> None:
        descriptor = None
        try:
            descriptor = acquire_storage_lock(Path(self.policy['data_root']))
            if operation['phase'] in ('cleaning', 'succeeded_cleanup_pending'):
                self._phase(operation, 'cleaning')
                self._clean(operation)
                return
            self.load_release(operation['original']['release']['release'])
            self.load_release(operation['target_release'], operation['request']['target_manifest_sha256'])
            folder = self.root / 'operations' / operation['operation_id']
            if 'before' not in operation:
                self._finish(operation, 'failed', error='执行在准备阶段中断')
                return
            if (operation['phase'] == 'committing' and self.state['current']['release']['release'] == operation['target_release']
                    and self.backend.committed(operation)):
                self._phase(operation, 'cleaning')
                self._clean(operation)
                return
            self.backend.block(operation)
            if (folder / 'before.env').exists():
                self._phase(operation, 'restoring')
                self.backend.restore(operation, lambda: self._record(operation))
                with self.lock:
                    self.state['current'] = operation['original']
                    self.state['history'] = [item for item in self.state['history'] if item['release']['release'] != operation['original']['release']['release']]
                self._finish(operation, 'restored', error='已按实际部署恢复原版本')
            elif 'before' in operation:
                self.backend.abandon(operation)
                self._finish(operation, 'failed', error='执行在切换前中断，原版本保持')
        except Exception:
            self._phase(operation, 'reconcile', error='更新恢复证据仍不完整，需要继续对账')
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def resume(self) -> None:
        """重启后依持久阶段续接恢复，未知结果保留门禁。

        :return: None。
        """
        with self.lock:
            identifier = self.state.get('active_operation')
            if not identifier:
                return
            operation = self._operation(identifier)
            if operation['phase'] in DONE:
                self.state['active_operation'] = None
                self._persist()
                return
            self.worker = threading.Thread(target=self._recover, args=(operation,), daemon=True, name='v3-update-startup-recovery')
            self.worker.start()


class UpdateHTTPHandler(BaseHTTPRequestHandler):
    """仅在私有 Unix socket 上提供有界管理协议。"""

    def log_message(self, format, *args) -> None:
        """禁止默认日志打印内部 HTTP 内容。

        :param format: 原日志格式。
        :param args: 原参数。
        :return: None。
        """

    def _dispatch(self) -> None:
        server = self.server
        credentials = self.connection.getsockopt(SOL_SOCKET, SO_PEERCRED, struct.calcsize('3i'))
        _, uid, _ = struct.unpack('3i', credentials)
        if uid != os.geteuid() or not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + server.token):
            self._reply(403, {'detail': '更新服务证明无效'})
            return
        try:
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('更新接口不接受流式请求体')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 8192:
                raise ValueError('更新请求超过大小限制')
            body = strict_json(self.rfile.read(length), 8192) if length else {}
            engine = server.engine
            if self.command == 'GET' and self.path == '/status':
                result = engine.status()
            elif self.command == 'GET' and self.path == '/releases':
                result = engine.releases()
            elif self.command == 'POST' and self.path == '/check' and not body:
                result = engine.check()
            elif self.command == 'POST' and self.path in ('/prepare', '/install', '/rollback'):
                result = engine.submit(self.path[1:], body)
            elif re.fullmatch(r'/operations/[a-f0-9-]{36}', self.path) and self.command == 'GET':
                result = engine.operation(self.path.split('/')[2])
            elif re.fullmatch(r'/operations/[a-f0-9-]{36}/(cancel|recover)', self.path) and self.command == 'POST':
                _, _, identifier, action = self.path.split('/')
                result = engine.control(identifier, action, body)
            else:
                self._reply(404, {'detail': '更新接口不存在'})
                return
            self._reply(202 if self.command == 'POST' else 200, result)
        except UpdateConflict as error:
            self._reply(409, {'detail': str(error)[:300]})
        except (ValueError, FileNotFoundError) as error:
            self._reply(400, {'detail': str(error)[:300] if isinstance(error, ValueError) else '更新材料缺失'})
        except Exception:
            self._reply(503, {'detail': '更新服务执行失败，持久状态仍可查询'})

    def _reply(self, status: int, value: dict) -> None:
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        """处理固定 GET。@return None。"""
        self.connection.settimeout(10)
        self._dispatch()

    def do_POST(self) -> None:
        """处理固定 POST。@return None。"""
        self.connection.settimeout(10)
        self._dispatch()


class UpdateServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """线程化私有 socket 服务，长更新在独立工作线程执行。"""
    daemon_threads = True


def main() -> None:
    """启动已接入部署的独立执行器。

    :return: None。
    """
    parser = argparse.ArgumentParser(description='v3 独立系统更新服务')
    parser.add_argument('--policy', type=Path, required=True)
    args = parser.parse_args()
    policy = validate_policy(strict_json(safe_read(args.policy, private=True)))
    root = Path(policy['state_root'])
    descriptor = os.open(root / 'service.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    engine = SystemUpdater(policy)
    if engine.state.get('bootstrap_pending'):
        raise ValueError('首次底座尚未完成 finalize，请先按接入操作单核验')
    token = safe_read(root / 'socket/token', 128, private=True).decode().strip()
    if not re.fullmatch(r'[a-f0-9]{64}', token):
        raise ValueError('更新服务令牌无效')
    socket_path = root / 'socket/updater.sock'
    if socket_path.exists():
        socket_path.unlink()
    server = UpdateServer(str(socket_path), UpdateHTTPHandler)
    os.chmod(socket_path, 0o600)
    server.token, server.engine = token, engine
    engine.resume()
    def periodic():
        # 检查只更新提示；重启后的随机抖动避免多实例同步请求公开目录。
        while True:
            time.sleep(60 + secrets.randbelow(120))
            engine.check()
            time.sleep(6 * 3600)
    threading.Thread(target=periodic, daemon=True, name='v3-update-periodic').start()
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        os.close(descriptor)


if __name__ == '__main__':
    main()
