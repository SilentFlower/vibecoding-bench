"""登记、核验并切换单个反重力环境的请求内核。"""
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
from pathlib import Path

from agy_runtime.storage import SOURCE_SHA, digest
from runtime_files import atomic_json, directory_fd

PLATFORM_ROOT = '/opt/v3/python'
KERNEL_FOLDER = 'agy-kernels'
MOUNT_PREFIX = '/run/v3/' + KERNEL_FOLDER + '/'
IDENTIFIER = re.compile(r'[0-9a-f]{64}')
FILE_NAME = re.compile(r'[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,95}')
REQUIRED_MODULES = ('__init__.py', 'kernel.py', 'supervisor.py', 'storage.py')
EXECUTABLES = ('observer-c', 'relocation_reclaim.so')
EXECUTABLE_PATHS = tuple('resources/' + name for name in EXECUTABLES)
MAX_BUNDLE_BYTES = 64 * 1024 ** 2


def _ordinary(path, *, deployed=False, directory=False):
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or (deployed and (info.st_uid != os.geteuid() or info.st_mode & 0o022)):
        raise ValueError('候选内核文件类型或权限无效')
    return info


def _inventory(package, *, deployed=False):
    resources = package / 'resources'
    for directory in (package, resources):
        _ordinary(directory, deployed=deployed, directory=True)
    modules = sorted(package.glob('*.py'))
    entries = modules + sorted(resources.iterdir())
    if not set(REQUIRED_MODULES) <= {path.name for path in modules}:
        raise ValueError('候选内核缺少启动模块')
    files = {}
    total = 0
    for path in entries:
        info = _ordinary(path, deployed=deployed)
        total += info.st_size
        if total > MAX_BUNDLE_BYTES or not FILE_NAME.fullmatch(path.name):
            raise ValueError('候选内核超过制品范围或文件名无效')
        if path.suffix == '.py':
            try:
                compile(path.read_bytes(), str(path.relative_to(package)), 'exec')
            except SyntaxError:
                raise ValueError('候选内核模块语法无效：' + path.name) from None
        if deployed and path.parent == resources and path.name in EXECUTABLES and not info.st_mode & 0o111:
            raise ValueError('候选内核缺少执行权限')
        files[path.relative_to(package).as_posix()] = digest(path)
    admission = json.loads((resources / 'admission.json').read_bytes())
    expected = admission.get('resource_hashes', {}) if isinstance(admission, dict) else {}
    if (not isinstance(admission, dict) or admission.get('source_sha256') != SOURCE_SHA
            or not isinstance(expected, dict) or not all(name in expected for name in EXECUTABLE_PATHS)
            or any(name not in files or files[name] != value for name, value in expected.items())):
        raise ValueError('候选内核与固定 AGY 执行体或配套资源不匹配')
    return {'protocol_version': 1, 'source_sha256': SOURCE_SHA, 'files': files}


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _receipt(folder, *, verify=False):
    _ordinary(folder.parent, deployed=True, directory=True)
    _ordinary(folder, deployed=True, directory=True)
    path = folder / 'kernel.json'
    if _ordinary(path, deployed=True).st_size > MAX_BUNDLE_BYTES:
        raise ValueError('候选内核清单过大')
    value = json.loads(path.read_bytes())
    if (not isinstance(value, dict) or value.get('protocol_version') != 1 or value.get('source_sha256') != SOURCE_SHA
            or _identity(value) != folder.name or (verify and _inventory(folder / 'agy_runtime', deployed=True) != value)):
        raise ValueError('候选内核摘要失配，请重新准备制品')
    return value


def stage(source: Path, sender: Path) -> str:
    """把已构建的包原子放入目标发送器的只读配置目录。@param source AGY 包。@param sender 目标发送器配置目录。@return 候选包摘要。"""
    metadata = _inventory(source)
    identifier = _identity(metadata)
    parent = sender / KERNEL_FOLDER
    os.close(directory_fd(sender))
    parent.mkdir(exist_ok=True, mode=0o755)
    _ordinary(parent, deployed=True, directory=True)
    parent.chmod(0o755)
    target = parent / identifier
    if target.exists() or target.is_symlink():
        _receipt(target, verify=True)
        return identifier
    with tempfile.TemporaryDirectory(prefix='.stage-', dir=parent) as temporary:
        folder = Path(temporary) / identifier
        package = folder / 'agy_runtime'
        (package / 'resources').mkdir(parents=True, mode=0o755)
        for directory in (folder, package, package / 'resources'):
            directory.chmod(0o755)
        for name in metadata['files']:
            path = package / name
            shutil.copyfile(source / name, path)
            path.chmod(0o555 if name in EXECUTABLE_PATHS else 0o444)
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
        atomic_json(folder / 'kernel.json', metadata, 0o444)
        _receipt(folder, verify=True)
        for directory in (package / 'resources', package, folder):
            descriptor = directory_fd(directory)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        try:
            folder.rename(target)
        except OSError:
            if not target.is_dir():
                raise
            _receipt(target, verify=True)
        descriptor = directory_fd(parent)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return identifier


def kernel_id(path: str) -> str | None:
    """解出固定目录代表的候选身份。@param path 发送器配置路径。@return 摘要或内置版标志。"""
    if path == PLATFORM_ROOT:
        return None
    if isinstance(path, str) and path.startswith(MOUNT_PREFIX) and IDENTIFIER.fullmatch(path[len(MOUNT_PREFIX):]):
        return path[len(MOUNT_PREFIX):]
    raise ValueError('环境的反重力内核位置无效')


def module_root(identifier: str | None) -> str:
    """把候选身份映射为发送器内的固定路径。@param identifier 候选摘要。@return 模块根。"""
    return MOUNT_PREFIX + identifier if identifier else PLATFORM_ROOT


def work_root(identifier: str | None) -> str:
    """隔离候选的启动残留，允许恢复已就绪的内置内核。@param identifier 候选摘要。@return 该版本工作根。"""
    return '/native/agy/kernels/' + identifier if identifier else '/native/agy'


def selection(runtime, row: dict, *, release: str | None = None) -> str | None:
    """读取持久配置，更新到另一平台批次时采用内置版本。@param runtime 运行时。@param row 环境记录。@param release 目标镜像批次。@return 所选候选摘要。"""
    try:
        config = runtime.read_sender_configuration(row)
    except FileNotFoundError:
        return None
    if release is not None and config.get('binding', {}).get('release_id') != release:
        return None
    options = config.get('agy')
    if not isinstance(options, dict):
        raise ValueError('发送器的反重力内核配置缺失')
    return kernel_id(options.get('module_root', PLATFORM_ROOT))


def catalog(runtime, row: dict) -> dict:
    """列出已准备到此环境的候选。@param runtime 运行时。@param row 环境记录。@return 选择、代次和候选摘要。"""
    parent = runtime._root(row) / 'runtime/sender' / KERNEL_FOLDER
    current = selection(runtime, row)
    candidates = []
    if parent.exists() or parent.is_symlink():
        _ordinary(parent, deployed=True, directory=True)
        for folder in sorted(parent.iterdir()):
            if IDENTIFIER.fullmatch(folder.name):
                try:
                    _receipt(folder)
                except (ValueError, OSError):
                    continue
                candidates.append(folder.name)
    return {'generation': row['generation'], 'kernel': current, 'candidates': candidates}


def activate(runtime, row: dict, change: dict, running_sender) -> dict:
    """在环境锁和网关排空许可内热切换。@param runtime 运行时。@param row 最新环境记录。@param change 前端冻结选择。@param running_sender 当前发送器或空。@return 更新后的选择。"""
    if (set(change) != {'expected_generation', 'expected_kernel', 'kernel'}
            or type(change['expected_generation']) is not int or change['expected_generation'] != row['generation']):
        raise ValueError('环境代次已变化，请刷新后重试')
    current = selection(runtime, row)
    if change['expected_kernel'] != current:
        raise ValueError('内核已变化，请刷新后重试')
    target = change['kernel']
    if target is not None and (type(target) is not str or not IDENTIFIER.fullmatch(target)):
        raise ValueError('候选内核摘要无效')
    if target == current:
        return catalog(runtime, row)
    path = module_root(target)
    if target is not None:
        try:
            _receipt(runtime._root(row) / 'runtime/sender' / KERNEL_FOLDER / target, verify=True)
        except (ValueError, OSError):
            raise ValueError('当前环境的候选内核不存在或校验失败') from None
    owner = 'maintenance:' + uuid.uuid4().hex
    lease_path = f"/admin/runtime/accounts/{row['gateway_account_id']}/lease"
    lease = runtime.gateway._request('POST', lease_path, {'operation': 'prepare', 'owner': owner})
    proof = lease.get('lease')
    if not isinstance(proof, dict) or proof.get('owner') != owner or not proof.get('generation'):
        raise ValueError('当前环境维护许可未就绪')
    control = {'owner': owner, 'generation': proof['generation']}
    try:
        if lease.get('active') or lease.get('waiting') or runtime._running_sender_active(row):
            raise ValueError('当前环境仍有请求或工具结果待处理')
        claimed = runtime.gateway._request('POST', lease_path, {'operation': 'claim', **control}).get('lease')
        if not isinstance(claimed, dict) or claimed.get('phase') != 'claimed' or any(claimed.get(key) != value for key, value in control.items()):
            raise ValueError('当前环境维护许可未取得')
        if target is not None and running_sender is not None:
            probe = ('import sys; from pathlib import Path; from agy_runtime import kernel, supervisor, storage; '
                     'from PIL import Image; assert Path(storage.__file__).parent == Path(sys.argv[1]) / "agy_runtime"; '
                     'storage.verify_resources()')
            result = running_sender.exec_run(['timeout', '20s', 'env', 'PYTHONPATH=' + path + ':' + PLATFORM_ROOT
                + ':/usr/local/bin', 'python3', '-P', '-c', probe, path], user='1001:1001')
            if result.exit_code:
                raise ValueError('候选包未通过目标发送器的启动检查，保留当前内核')
            runtime.gateway._request('POST', lease_path, {'operation': 'heartbeat', **control})
        config = runtime.read_sender_configuration(row)
        binding = config['binding']
        if (binding['environment_id'] != row['environment_id'] or binding['account_id'] != row['gateway_account_id']
                or binding['generation'] != row['generation'] or kernel_id(config['agy']['module_root']) != current):
            raise ValueError('发送器归属或当前内核已变化，请刷新')
        config['agy']['module_root'] = path
        config['agy']['work_root'] = work_root(target)
        runtime._write_sender_config(row, config)
    finally:
        runtime.gateway._request('POST', lease_path, {'operation': 'release', **control})
    return catalog(runtime, row)
