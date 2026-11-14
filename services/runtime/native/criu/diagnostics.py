"""恢复失败的白名单证据；私有摘要独立于实例和模板清理。"""
import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from uuid import UUID, uuid4

RECORD_LIMIT = 8192
RECORD_COUNT = 32
LOG_LIMIT = 16384
SIDECAR = 'failure.json'
STAGES = frozenset(('unknown', 'template_admission', 'template_directory', 'seed_identity',
    'seed_environment', 'seed_image', 'seed_pipes', 'template_dump', 'template_files',
    'template_manifest', 'template_publish', 'template_wait', 'restore_admission',
    'template_verify', 'instance_directory', 'instance_files', 'instance_config',
    'image_open', 'pipes', 'namespace_launch', 'namespace_identity', 'namespace_handoff',
    'start_ack', 'report_read', 'report_decode', 'worker_identity', 'image_verify',
    'worker_handoff', 'worker_wait', 'supervisor_input', 'namespace_mount', 'pid_setup',
    'criu_restore', 'worker_pid', 'entropy_verify', 'report_write', 'worker_resume'))
EXCEPTIONS = frozenset(('OSError', 'PermissionError', 'FileNotFoundError', 'FileExistsError',
    'ProcessLookupError', 'BrokenPipeError', 'ConnectionResetError', 'ConnectionAbortedError',
    'TimeoutError', 'ValueError', 'JSONDecodeError', 'KeyError', 'TypeError', 'RuntimeError',
    'CalledProcessError', 'TimeoutExpired', 'SystemExit', 'UnknownError'))
REASONS = frozenset(('RESTORE_OPERATION_FAILED', 'RESTORE_TEMPLATE_BUSY', 'RESTORE_SEED_OWNERSHIP',
    'RESTORE_SEED_BINDING', 'RESTORE_IMAGE_IDENTITY', 'RESTORE_IMAGE_MAPPING', 'RESTORE_SEED_PIPES',
    'RESTORE_CRIU_FAILED', 'RESTORE_SEED_EXITED', 'RESTORE_TEMPLATE_UNAVAILABLE',
    'RESTORE_NAMESPACE_OWNERSHIP', 'RESTORE_START_ACK', 'RESTORE_TEMPLATE_EXPIRED',
    'RESTORE_CONNECTION_CLOSED', 'RESTORE_WORKER_OWNERSHIP', 'RESTORE_TEMPLATE_CHANGED',
    'RESTORE_PEER_INVALID', 'RESTORE_COMMAND_INVALID', 'RESTORE_COMMAND_LIMIT',
    'RESTORE_FD_HANDOFF', 'RESTORE_DIRECTORY_OWNER', 'RESTORE_DIRECTORY_LIMIT',
    'RESTORE_DIRECTORY_CHANGED', 'RESTORE_DIRECTORY_TYPE', 'CRIU_EXIT_NONZERO'))
PYTHON_MODULES = frozenset(('controller.py', 'supervisor.py', 'protocol.py', 'shared_image.py', 'entropy.py'))
CRIU_MODULES = frozenset(('memfd.c', 'mem.c', 'files.c', 'files-reg.c', 'cr-restore.c',
    'cr-dump.c', 'pstree.c', 'namespaces.c', 'cgroup.c', 'util.c', 'proc_parse.c',
    'kerndat.c', 'image.c', 'protobuf.c', 'crtools.c', 'parasite-syscall.c', 'restorer.c',
    'sk-inet.c', 'sk-unix.c', 'cpu.c'))
CATEGORIES = {'permission_denied': 'permission denied', 'operation_denied': 'operation not permitted',
    'file_missing': 'no such file', 'file_exists': 'file exists', 'bad_fd': 'bad file descriptor',
    'no_memory': 'cannot allocate memory', 'resource_busy': 'device or resource busy',
    'not_supported': 'not supported', 'unexpected_eof': 'unexpected eof',
    'image_identity': 'shared executable memfd identity mismatch'}
FIELDS = frozenset(('schema_version', 'at_ms', 'operation', 'stage', 'exception_type', 'errno',
    'reason', 'template', 'worker', 'instance', 'criu_returncode', 'process_returncode',
    'source', 'log_status', 'log_evidence', 'upstream_status', 'upstream'))


def _uuid(value: object) -> str | None:
    try:
        return value if isinstance(value, str) and str(UUID(value)) == value else None
    except ValueError:
        return None


def _integer(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _directory(path: Path) -> int:
    # 每级拒绝链接，避免仅检查末级时越过被替换的父目录。
    path = path.absolute()
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            opened = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=descriptor)
            os.close(descriptor)
            descriptor = opened
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('DIAGNOSTIC_DIRECTORY_UNSAFE')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read(directory: int, name: str, limit: int, tail: bool = False) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=directory)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or not tail and info.st_size > limit):
            raise ValueError('DIAGNOSTIC_FILE_UNSAFE')
        if tail:
            os.lseek(descriptor, max(0, info.st_size - limit), os.SEEK_SET)
        raw = os.read(descriptor, limit + (not tail))
        if len(raw) > limit:
            raise ValueError('DIAGNOSTIC_FILE_LIMIT')
        return raw
    finally:
        os.close(descriptor)


def _validate(value: object, nested: bool = False) -> dict:
    if (not isinstance(value, dict) or set(value) != FIELDS or type(value['schema_version']) is not int
            or value['schema_version'] != 1 or not _integer(value['at_ms'], 0, 2**63 - 1)
            or value['operation'] not in ('template', 'restore') or value['stage'] not in STAGES
            or value['exception_type'] not in EXCEPTIONS or value['reason'] not in REASONS
            or value['log_status'] not in ('not_applicable', 'available_tail', 'missing', 'invalid')
            or value['upstream_status'] not in ('not_applicable', 'available', 'missing', 'invalid')):
        raise ValueError('DIAGNOSTIC_RECORD_INVALID')
    for name in ('template', 'worker', 'instance'):
        if value[name] is not None and _uuid(value[name]) is None:
            raise ValueError('DIAGNOSTIC_RECORD_INVALID')
    for name, low, high in (('errno', 1, 4095), ('criu_returncode', -255, 255), ('process_returncode', -255, 255)):
        if value[name] is not None and not _integer(value[name], low, high):
            raise ValueError('DIAGNOSTIC_RECORD_INVALID')
    source = value['source']
    if source is not None and (not isinstance(source, dict) or set(source) != {'module', 'line'}
            or source['module'] not in PYTHON_MODULES or not _integer(source['line'], 1, 10**7)):
        raise ValueError('DIAGNOSTIC_RECORD_INVALID')
    evidence = value['log_evidence']
    if not isinstance(evidence, list) or len(evidence) > 8:
        raise ValueError('DIAGNOSTIC_RECORD_INVALID')
    for entry in evidence:
        if (not isinstance(entry, dict) or set(entry) != {'level', 'category', 'module', 'line'}
                or entry['level'] not in ('error', 'warning')
                or entry['category'] not in (*CATEGORIES, 'unknown')
                or entry['module'] not in (*CRIU_MODULES, None)
                or entry['line'] is not None and not _integer(entry['line'], 1, 10**7)):
            raise ValueError('DIAGNOSTIC_RECORD_INVALID')
    if value['upstream'] is not None:
        if nested or value['upstream_status'] != 'available':
            raise ValueError('DIAGNOSTIC_RECORD_INVALID')
        _validate(value['upstream'], nested=True)
        if (value['upstream']['operation'] != 'restore' or value['upstream']['instance'] != value['instance']
                or value['upstream']['upstream_status'] != 'not_applicable'):
            raise ValueError('DIAGNOSTIC_RECORD_INVALID')
    elif value['upstream_status'] == 'available':
        raise ValueError('DIAGNOSTIC_RECORD_INVALID')
    return value


def _json(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DIAGNOSTIC_RECORD_INVALID')
            result[key] = value
        return result

    return _validate(json.loads(raw, object_pairs_hook=pairs))


def _publish(directory: int, name: str, raw: bytes) -> None:
    if len(raw) > RECORD_LIMIT:
        raise ValueError('DIAGNOSTIC_RECORD_LIMIT')
    temporary = '.' + str(uuid4()) + '.tmp'
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=directory)
    try:
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(descriptor, raw[offset:])
                if written <= 0:
                    raise OSError('DIAGNOSTIC_WRITE_FAILED')
                offset += written
        finally:
            os.close(descriptor)
        # 排他发布保留已有证据；父进程在监督进程退出后读取完整副摘要。
        os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
    finally:
        os.unlink(temporary, dir_fd=directory)


def _store(root: Path, raw: bytes) -> None:
    parent = _directory(root)
    directory = None
    try:
        try:
            os.mkdir('failures', 0o700, dir_fd=parent)
        except FileExistsError:
            pass
        directory = os.open('failures', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=parent)
        info = os.fstat(directory)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('DIAGNOSTIC_DIRECTORY_UNSAFE')
        existing = []
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(existing) >= RECORD_COUNT or not entry.name.endswith('.json') or _uuid(entry.name[:-5]) is None:
                    raise ValueError('DIAGNOSTIC_STORE_UNSAFE')
                record = _json(_read(directory, entry.name, RECORD_LIMIT))
                existing.append((record['at_ms'], entry.name))
        # 先预留一个受控槽，磁盘失败时也不会突破记录数量上限。
        if len(existing) == RECORD_COUNT:
            os.unlink(min(existing)[1], dir_fd=directory)
        _publish(directory, str(uuid4()) + '.json', raw)
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def _log_evidence(path: Path) -> list[dict]:
    directory = _directory(path.parent)
    try:
        text = _read(directory, path.name, LOG_LIMIT, tail=True).decode('utf-8', errors='replace')
    finally:
        os.close(directory)
    entries = []
    for line in text.splitlines():
        level = re.search(r'\b(Error|Warn(?:ing)?)\s*\(', line, re.IGNORECASE)
        if not level:
            continue
        location = re.search(r'\bcriu/(?:[a-z_-]+/)*([a-z_-]+\.c):(\d{1,7})\)', line)
        module = location[1] if location and location[1] in CRIU_MODULES else None
        category = next((key for key, phrase in CATEGORIES.items() if phrase in line.lower()), 'unknown')
        entry = {'level': 'error' if level[1].lower() == 'error' else 'warning', 'category': category,
                 'module': module, 'line': int(location[2]) if module else None}
        if entry not in entries:
            entries.append(entry)
    # 真正错误优先于警告；分类仅表示日志证据，不推断根因。
    return sorted(entries, key=lambda item: item['level'] != 'error')[:8]


@dataclass
class FailureDiagnostic:
    """跟踪内部操作的受控证据。

    @param root 原恢复私有根。
    @param operation 模板或恢复。
    @param template 模板UUID。
    @param worker 新workerUUID。
    @param instance 当前实例目录。
    @param stage 实际操作阶段。
    @param criu_returncode 已观测CRIU退出码。
    @param log 当前操作的固定CRIU日志。
    """
    root: Path
    operation: str
    template: str | None = None
    worker: str | None = None
    instance: Path | None = None
    stage: str = 'unknown'
    criu_returncode: int | None = None
    log: Path | None = None

    def report(self, error: BaseException, *, supervisor: bool = False) -> None:
        """尽力保存白名单首错。@param error 原异常。@param supervisor 是否仅写实例副摘要。@return 无，诊断故障保持原流程。"""
        if isinstance(error, asyncio.CancelledError) or type(error) is ValueError and str(error) == 'RESTORE_CONNECTION_CLOSED':
            return
        try:
            exception = type(error).__name__
            reason = str(error) if type(error) is ValueError and str(error) in REASONS else 'RESTORE_OPERATION_FAILED'
            source = None
            trace = error.__traceback__
            while trace:
                module = Path(trace.tb_frame.f_code.co_filename).name
                if module in PYTHON_MODULES:
                    source = {'module': module, 'line': trace.tb_lineno}
                trace = trace.tb_next
            value = {'schema_version': 1, 'at_ms': int(time.time() * 1000),
                'operation': self.operation, 'stage': self.stage if self.stage in STAGES else 'unknown',
                'exception_type': exception if exception in EXCEPTIONS else 'UnknownError',
                'errno': error.errno if isinstance(error, OSError) and _integer(error.errno, 1, 4095) else None,
                'reason': 'CRIU_EXIT_NONZERO' if self.stage == 'criu_restore' and self.criu_returncode else reason,
                'template': _uuid(self.template), 'worker': _uuid(self.worker),
                'instance': _uuid(self.instance.name) if self.instance else None,
                'criu_returncode': self.criu_returncode, 'process_returncode': None, 'source': source,
                'log_status': 'not_applicable', 'log_evidence': [],
                'upstream_status': 'not_applicable', 'upstream': None}
            code = error.returncode if isinstance(error, subprocess.CalledProcessError) else error.code if isinstance(error, SystemExit) else None
            value['process_returncode'] = code if _integer(code, -255, 255) else None
            if self.log:
                try:
                    value['log_evidence'] = _log_evidence(self.log)
                    value['log_status'] = 'available_tail'
                except FileNotFoundError:
                    value['log_status'] = 'missing'
                except (OSError, ValueError):
                    value['log_status'] = 'invalid'
            if not supervisor and self.instance:
                directory = None
                try:
                    directory = _directory(self.instance)
                    upstream = _json(_read(directory, SIDECAR, RECORD_LIMIT))
                    value['upstream_status'], value['upstream'] = 'available', upstream
                    _validate(value)
                except FileNotFoundError:
                    value['upstream_status'], value['upstream'] = 'missing', None
                except (OSError, ValueError, TypeError, RecursionError):
                    value['upstream_status'], value['upstream'] = 'invalid', None
                finally:
                    if directory is not None:
                        os.close(directory)
            _validate(value)
            raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
            if len(raw) > RECORD_LIMIT:
                raise ValueError('DIAGNOSTIC_RECORD_LIMIT')
            if supervisor:
                directory = _directory(self.instance)
                try:
                    _publish(directory, SIDECAR, raw)
                finally:
                    os.close(directory)
                return
            persistence = 'saved'
            try:
                _store(self.root, raw)
            except Exception:
                persistence = 'DIAGNOSTIC_STORE_FAILED'
            print(json.dumps({'layer': 'criu_failure', 'persistence': persistence, 'diagnostic': value}), flush=True)
        except Exception:
            try:
                print(json.dumps({'layer': 'criu_failure', 'reason': 'DIAGNOSTIC_CAPTURE_FAILED'}), flush=True)
            except Exception:
                pass
