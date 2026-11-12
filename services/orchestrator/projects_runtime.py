"""Projects 的工程资产准备；原生终端操作由共享 PiTerminal 承担。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from contextlib import ExitStack
from pathlib import Path
from stat import S_ISREG
from tempfile import TemporaryDirectory

from account_isolation import ISOLATION_VERSION, role_container
from account_runtime import AccountRuntime, atomic_json
from pi_terminal import KEYS, PiTerminal
from project_library import PROJECT_KEY, digest_json, materialize_snapshot, read_document, safe_relative, snapshot_tree
from project_runtime_policy import ProjectRuntimeError, check_python_runtime


class ProjectsTerminal(PiTerminal):
    """保留工程工作区、公开材料及离线依赖准备，复用账号原生终端。

    :param runtime: 固定账号环境。
    :param catalog: 冻结工程资产目录。
    :param settings: CLI 设置回调。
    :param quota_context: 被动额度登记回调。
    """

    def __init__(self, runtime: AccountRuntime, catalog, settings, quota_context, quota_release=None, credentials=None,
                 driver: Path | None = None, *, quota_observation=None, namespace: str = 'projects') -> None:
        """登记工程资产与原有终端依赖，不启动模型。

        :param runtime: 固定账号运行环境。
        :param catalog: 工程资产目录。
        :param settings: CLI 配置回调。
        :param quota_context: 被动额度登记回调。
        :param quota_release: 收口后归还许可回调。
        :param credentials: 唯一凭据所有者同步回调。
        :param driver: 只读终端监督脚本。
        :param quota_observation: 原生结构化门禁补证回调。
        :param namespace: 服务端固定的工程迭代或养号工程空间。
        :return: None。
        """
        super().__init__(runtime, settings, quota_context, quota_release, credentials, driver,
            quota_observation=quota_observation, namespace=namespace, scenario_resources=True)
        self.catalog = catalog

    def startup_recovery_ready(self, account: dict, work: dict) -> bool:
        """只读证明未启动原工作的环境、源码和输入现场已具备人工恢复条件。

        :param account: 当前可用账号。
        :param work: 尚未成功启动的原工作。
        :return: 全部证据明确且原会话不存在时为 True，未知或读取失败时为 False。
        """
        try:
            runtime = self.runtime
            connection = runtime.database()
            try:
                saved = connection.execute('SELECT * FROM account_environments WHERE account_id=? AND name=?',
                    (account['id'], account['name'])).fetchone()
            finally:
                connection.close()
            if not saved:
                return False
            with runtime.environment_lock(saved['environment_id']):
                connection = runtime.database()
                try:
                    current = connection.execute('SELECT * FROM account_environments WHERE environment_id=? AND account_id=? AND name=?',
                        (saved['environment_id'], account['id'], account['name'])).fetchone()
                finally:
                    connection.close()
                if not current:
                    return False
                row = dict(current)
                if (row['state'] != 'ready' or row.get('isolation_version') != ISOLATION_VERSION
                        or runtime.environment_jobs(row['environment_id']) or runtime.reviews.serial_state(row)
                        or runtime.role_status(row) != {'cli': 'running', 'sender': 'running', 'network': 'running'}):
                    return False
                root = runtime._root(row)
                for relative in ('', 'runtime', 'projects', 'home', 'home/.claude', 'home/.claude/projects'):
                    path = root / relative
                    if path.is_symlink() or not path.is_dir():
                        return False
                execution, shared = root / 'runtime/execution.json', root / 'runtime/executions'
                if execution.exists() or execution.is_symlink() or shared.is_symlink():
                    return False
                if shared.exists() and (not shared.is_dir() or any(shared.iterdir())):
                    return False
                assets = self.catalog.for_work(work)
                project, _ = assets.objective(work['project_key'], work['objective_id'])
                registered = self._workspace_registrations(root, account, row, self.namespace)
                matches = [alias for alias, (cycle, identity, _) in registered.items()
                    if cycle == work.get('cycle_no', 1) and identity['project_key'] == work['project_key']
                    and identity['seed_digest'] == project.manifest['seed_digest']]
                if len(matches) != 1:
                    return False
                workspace = root / 'projects' / matches[0]
                if workspace.is_symlink() or not workspace.is_dir():
                    return False
                for directory in (root / 'home/.claude/projects').iterdir():
                    if directory.is_symlink() or not directory.is_dir():
                        return False
                    native = directory / (work['session_id'] + '.jsonl')
                    if native.exists() or native.is_symlink():
                        return False
                container = role_container(runtime, row, 'cli')
                observed = container.exec_run(['python3', '-I', '/usr/local/bin/v3-cli-control', 'orphans'])
                if observed.exit_code or len(observed.output) > 64 * 1024:
                    return False
                # 私有登记为空仍须核对实际进程，不能把一次清理回执当作无遗留的证明。
                return json.loads(observed.output).get('orphans') == []
        except Exception:
            return False

    def _workspace_identity(self, account: dict, row: dict, project_key: str, seed_digest: str, cycle_no: int,
                            *, naming_version: int = 2, namespace: str | None = None) -> tuple[str, dict]:
        """派生自然目录或历史别名，完整身份仍由私有注册证明。

        :param account: 原账号。
        :param row: 固定环境。
        :param project_key: 已校验的实际项目标识。
        :param seed_digest: 冻结初始源码摘要。
        :param cycle_no: 正整数工程轮次。
        :param naming_version: 1 读取历史格式，2 创建自然名称。
        :param namespace: 核对兄弟注册时指定的服务端固定空间。
        :return: 安全目录别名及其完整注册身份。
        """
        if type(cycle_no) is not int or cycle_no < 1:
            raise ValueError('工程轮次必须为正整数')
        namespace = self.namespace if namespace is None else namespace
        if (type(naming_version) is not int or naming_version not in (1, 2)
                or namespace not in ('projects', 'warmup')):
            raise ValueError('工程目录命名版本或空间不合法')
        if (not isinstance(project_key, str) or not PROJECT_KEY.fullmatch(project_key)
                or not isinstance(seed_digest, str) or not re.fullmatch('[a-f0-9]{64}', seed_digest)):
            raise ValueError('工程项目标识或初始版本不合法')
        identity = {'account_id': account['id'], 'environment_id': row['environment_id'],
            'project_key': project_key, 'seed_digest': seed_digest}
        if naming_version == 2:
            suffix = hashlib.sha256(f"{namespace}:{account['id']}:{project_key}:{seed_digest}:{cycle_no}".encode()).hexdigest()[:8]
            alias = project_key + '-' + suffix
            identity.update(namespace=namespace, cycle_no=cycle_no, workspace='projects/' + alias, naming_version=2)
        elif namespace == 'projects' and cycle_no == 1:
            alias = 'workspace-' + hashlib.sha256(f"{account['id']}:{project_key}:{seed_digest}".encode()).hexdigest()[:16]
        else:
            alias = namespace + '-workspace-' + hashlib.sha256(
                f"{namespace}:{account['id']}:{project_key}:{seed_digest}:{cycle_no}".encode()).hexdigest()[:16]
            identity.update(namespace=namespace, cycle_no=cycle_no, workspace='projects/' + alias)
        return alias, identity

    def _prepare_execution(self, root: Path, row: dict, account: dict, work: dict) -> tuple[Path, dict]:
        """准备同一项目累计源码与其冻结离线 Python 依赖。:param root: 账号目录。:param row: 环境。:param account: 账号。:param work: 原工程。:return: 工作区和原有工程环境。"""
        assets = self.catalog.for_work(work)
        project, definition = assets.objective(work['project_key'], work['objective_id'])
        try:
            workspace = self._prepare_workspace(root, row, account, work, project, definition)
        except ValueError as error:
            raise ProjectRuntimeError('workspace_conflict', str(error)[:400]) from None
        python = self._prepare_python(row, project, assets.library)
        version = json.loads(work['settings_json'])['claude_code_version']
        cwd = '/home/node/projects/' + workspace.name
        return workspace, {'PATH': python['bin'] + f':/cli/{version}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin',
            'PYTHONPATH': cwd + '/library:' + cwd + '/app:' + python['site']}

    def _prepare_workspace(self, root: Path, row: dict, account: dict, work: dict,
                           project, definition: dict) -> Path:
        """复用项目累计成果，并在新目标开始前一次性补齐其公开输入。

        :param root: 已领取租约的账号持久目录。
        :param row: 已核对的账号环境。
        :param account: 当前账号。
        :param work: 冻结目标及原工作基线。
        :param project: 已校验的固定项目定义。
        :param definition: 当前完整工程目标。
        :return: 保留此前修改的累计项目目录。
        """
        markers = root / 'runtime' / (self.namespace + '-workspaces')
        if any(path.is_symlink() or path.exists() and not path.is_dir()
                for path in (root, root / 'projects', root / 'runtime', markers)):
            raise ValueError('工程工作区或注册目录不能为链接或未知文件')
        candidates, existing = [], []
        for version in (1, 2):
            alias, identity = self._workspace_identity(account, row, work['project_key'],
                project.manifest['seed_digest'], work.get('cycle_no', 1), naming_version=version)
            candidates.append((alias, identity))
            workspace, marker = root / 'projects' / alias, markers / (alias + '.json')
            if marker.is_symlink() or workspace.is_symlink():
                raise ValueError('工程工作区或注册目录不能为链接')
            if marker.exists():
                if (not marker.is_file() or marker.stat().st_nlink != 1 or read_document(marker) != identity
                        or not workspace.is_dir()):
                    raise ValueError('项目工作区的账号或初始版本证明不符')
                existing.append((alias, identity))
            elif workspace.exists():
                raise ValueError('未登记的项目工作区需要先核对，不能覆盖')
        if len(existing) > 1:
            raise ValueError('同一工程有多份工作区注册，请先核对')
        if not existing and (work.get('baseline_json') or work.get('resume_required')):
            raise ValueError('原工程工作区证明缺失，不能用新目录重建原源码')
        # 旧目录承载原 Claude 会话与输入凭据，接续时不能因升级静默换名。
        alias, identity = existing[0] if existing else candidates[-1]
        workspace = root / 'projects' / alias
        marker = markers / (alias + '.json')
        if not existing:
            objects = self.runtime.data / 'projects/objects'
            materialize_snapshot(snapshot_tree(project.root / 'seed', objects), objects, workspace)
            for current, directories, files in os.walk(workspace):
                os.chown(current, 1000, 1000, follow_symlinks=False)
                for name in files:
                    os.chown(Path(current) / name, 1000, 1000, follow_symlinks=False)
            atomic_json(marker, identity)
        sources = [(relative, relative) for relative in dict.fromkeys(
            [*definition['materials'], *definition.get('owner_materials', [])])]
        sources.extend((item['source'], item['target']) for item in definition.get('setup', []))
        inputs = {}
        for source, target in sources:
            source, target = safe_relative(source), safe_relative(target)
            content = (project.root / source).read_bytes()
            if target in inputs and inputs[target] != content:
                raise ValueError('工程目标向同一路径声明了不同输入')
            inputs[target] = content
        receipt = {**identity, 'objective_id': work['objective_id'], 'library_digest': work['library_digest'],
            'inputs': {name: hashlib.sha256(content).hexdigest() for name, content in sorted(inputs.items())}}
        input_marker = root / 'runtime' / (self.namespace + '-inputs') / (digest_json(receipt) + '.json')
        if input_marker.parent.is_symlink() or input_marker.is_symlink():
            raise ValueError('工程输入注册目录不能为链接')
        if input_marker.exists():
            saved = read_document(input_marker)
            if {key: value for key, value in saved.items() if key != 'legacy_existing_work'} != receipt:
                raise ValueError('原工程目标输入凭据不符')
            return workspace
        if work.get('baseline_json'):
            # 已开始的旧工作沿用原冻结基线；恢复时补文件会把控制端输入误记为候选改动。
            atomic_json(input_marker, {**receipt, 'legacy_existing_work': True})
            return workspace
        with ExitStack() as opened:
            descriptor = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            opened.callback(os.close, descriptor)
            planned = []
            for relative, content in inputs.items():
                parent = descriptor
                parts = relative.split('/')
                for name in parts[:-1]:
                    try:
                        os.mkdir(name, mode=0o755, dir_fd=parent)
                        os.chown(name, 1000, 1000, dir_fd=parent, follow_symlinks=False)
                    except FileExistsError:
                        pass
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                    opened.callback(os.close, child)
                    parent = child
                try:
                    existing = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                except FileNotFoundError:
                    planned.append((parent, parts[-1], content))
                    continue
                with os.fdopen(existing, 'rb') as current:
                    if not S_ISREG(os.fstat(current.fileno()).st_mode):
                        raise ValueError('工程目标输入位置不是普通文件：' + relative)
                    if current.read(len(content) + 1) != content:
                        raise ValueError('新目标输入与已有工作文件冲突，保留原文件：' + relative)
            # 先核对全部目标再写入，后续任务不能借 setup 覆盖上一轮成果或经链接越出项目。
            for parent, name, content in planned:
                target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
                with os.fdopen(target, 'wb') as output:
                    os.fchown(output.fileno(), 1000, 1000)
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
        atomic_json(input_marker, receipt)
        return workspace

    def _registered_identity(self, saved: dict, account: dict, row: dict, *, namespace: str | None = None):
        """核对完整注册身份。:param saved: 已读取凭据。:param account: 当前账号。:param row: 固定环境。:param namespace: 待核对的固定空间。:return: 轮次、别名和规范身份。"""
        namespace = self.namespace if namespace is None else namespace
        if (not isinstance(saved, dict) or saved.get('account_id') != account['id']
                or saved.get('environment_id') != row['environment_id']
                or saved.get('namespace', 'projects') != namespace
                or not isinstance(saved.get('project_key'), str) or not saved['project_key']
                or not isinstance(saved.get('seed_digest'), str) or not re.fullmatch('[a-f0-9]{64}', saved['seed_digest'])):
            raise ValueError('工程清理注册的账号、空间或初始版本不符')
        cycle = saved.get('cycle_no', 1)
        alias, identity = self._workspace_identity(account, row, saved['project_key'], saved['seed_digest'], cycle,
            naming_version=saved.get('naming_version', 1), namespace=namespace)
        if any(saved.get(key) != value for key, value in identity.items()):
            raise ValueError('工程清理注册的真实路径或轮次不符')
        return cycle, alias, identity

    def _workspace_registrations(self, root: Path, account: dict, row: dict, namespace: str) -> dict:
        """读取一个空间的新旧注册，用完整身份识别自然目录的归属。

        :param root: 已加锁的账号环境根。
        :param account: 当前账号。
        :param row: 当前环境。
        :param namespace: 服务端固定的工程空间。
        :return: 别名到轮次、身份和注册文件的映射。
        """
        markers = root / 'runtime' / (namespace + '-workspaces')
        if markers.is_symlink() or markers.exists() and not markers.is_dir():
            raise ValueError('工程工作区注册目录不能为链接或未知文件')
        registered, identities = {}, set()
        for path in sorted(markers.iterdir()) if markers.exists() else []:
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                raise ValueError('工程工作区注册目录包含链接或未知文件')
            # 早期题库轮次不属于工程注册，不能因新目录不再带前缀而误删。
            if namespace == 'warmup' and re.fullmatch(r'[a-f0-9]{32}\.json', path.name):
                continue
            saved = read_document(path)
            cycle, alias, identity = self._registered_identity(saved, account, row, namespace=namespace)
            if path.name != alias + '.json' or saved != identity:
                raise ValueError('工程工作区凭据路径或内容不符')
            key = (identity['project_key'], identity['seed_digest'], cycle)
            if key in identities:
                raise ValueError('同一工程有多份工作区注册，请先核对')
            identities.add(key)
            registered[alias] = (cycle, identity, path)
        return registered

    def cleanup_cycle(self, account: dict, cycle_no: int) -> None:
        """只清理指定账号、当前空间及已登记轮次的累计源码和输入凭据。

        :param account: 仍属于固定环境的正式账号，包含 id/name。
        :param cycle_no: 已由业务服务确认全量通过的正整数轮次。
        :return: None；缺失的已登记文件可重入，未知目录或链接拒绝删除。
        """
        if type(cycle_no) is not int or cycle_no < 1 or type(account.get('id')) is not int or account['id'] < 1:
            raise ValueError('工程清理账号或轮次不合法')
        runtime = self.runtime
        connection = runtime.database()
        try:
            saved = connection.execute('SELECT * FROM account_environments WHERE account_id=?', (account['id'],)).fetchone()
        finally:
            connection.close()
        if not saved:
            return
        with runtime.environment_lock(saved['environment_id']):
            connection = runtime.database()
            try:
                current = connection.execute('SELECT * FROM account_environments WHERE account_id=?', (account['id'],)).fetchone()
            finally:
                connection.close()
            if (not current or current['environment_id'] != saved['environment_id'] or current['name'] != account['name']):
                raise ValueError('工程清理期间账号环境已变化')
            row = dict(current)
            root = runtime._root(row)
            markers = root / 'runtime' / (self.namespace + '-workspaces')
            inputs = root / 'runtime' / (self.namespace + '-inputs')
            projects = root / 'projects'
            for path in (root, root / 'runtime', projects, markers, inputs):
                if path.is_symlink() or path.exists() and not path.is_dir():
                    raise ValueError('工程清理路径不能是链接或未知文件')
            executions = root / 'runtime/executions'
            legacy = root / 'runtime/execution.json'
            if (row['state'] not in ('ready', 'stopped') or runtime.environment_jobs(row['environment_id'])
                    or legacy.exists() or legacy.is_symlink() or executions.is_symlink()
                    or executions.exists() and (not executions.is_dir() or any(executions.iterdir()))):
                raise ValueError('账号仍有原生作业或未确认登记，不能清理工程轮次')
            registrations = {namespace: self._workspace_registrations(root, account, row, namespace)
                for namespace in ('projects', 'warmup')}
            if registrations['projects'].keys() & registrations['warmup'].keys():
                raise ValueError('多个工程空间有相同目录注册，请先核对')
            registered = {alias: identity for alias, (_, identity, _) in registrations[self.namespace].items()}
            selected = [(projects / alias, path) for alias, (cycle, _, path) in registrations[self.namespace].items()
                if cycle == cycle_no]
            known = registrations['projects'].keys() | registrations['warmup'].keys()
            prefix = 'workspace-' if self.namespace == 'projects' else self.namespace + '-workspace-'
            # 同空间出现无注册目录时不能猜其所属轮次，也不能靠目录名前缀直接清空。
            for path in projects.iterdir() if projects.exists() else []:
                project_key, _, suffix = path.name.rpartition('-')
                natural = PROJECT_KEY.fullmatch(project_key) and re.fullmatch('[a-f0-9]{8}', suffix)
                owned = natural or path.name.startswith(prefix) or self.namespace == 'projects' and path.name.startswith('projects-workspace-')
                if owned and path.name not in known:
                    raise ValueError('存在未登记的同空间工程目录，请先核对')
            selected_inputs = []
            for path in sorted(inputs.iterdir()) if inputs.exists() else []:
                if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                    raise ValueError('工程输入注册目录包含链接或未知文件')
                receipt = read_document(path)
                cycle, alias, identity = self._registered_identity(receipt, account, row)
                canonical = {key: value for key, value in receipt.items() if key != 'legacy_existing_work'}
                if (path.name != digest_json(canonical) + '.json' or registered.get(alias) != identity
                        or not isinstance(receipt.get('inputs'), dict) or not isinstance(receipt.get('objective_id'), str)
                        or not isinstance(receipt.get('library_digest'), str)):
                    raise ValueError('工程输入凭据与已登记工作区不符')
                for name, digest in receipt['inputs'].items():
                    safe_relative(name)
                    if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
                        raise ValueError('工程输入凭据摘要不符')
                if cycle == cycle_no:
                    selected_inputs.append(path)
            for workspace, _ in selected:
                if workspace.is_symlink() or workspace.exists() and not workspace.is_dir():
                    raise ValueError('工程清理工作区被替换为链接或未知文件')
                if workspace.exists():
                    for directory, folders, files in os.walk(workspace, followlinks=False):
                        for name in [*folders, *files]:
                            path = Path(directory) / name
                            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                                raise ValueError('工程清理内容包含链接或特殊文件')
            # 先验证全部身份和路径，再删除源码、输入凭据，最后删注册凭据；中断后仍有原证明可重入。
            for workspace, _ in selected:
                if workspace.exists():
                    shutil.rmtree(workspace)
            for path in selected_inputs:
                path.unlink(missing_ok=True)
            for _, path in selected:
                path.unlink(missing_ok=True)

    def _prepare_python(self, row: dict, project, library) -> dict:
        runtime = self.runtime
        profile = library.environments[project.manifest['environment']]
        checksum = digest_json(profile)
        root = runtime._root(row)
        base = root / 'cli/projects-python' / checksum
        marker = root / 'runtime/projects-python' / (checksum + '.json')
        container_root = '/cli/projects-python/' + checksum
        network = role_container(runtime, row, 'network')
        observed = network.exec_run(['python3', '-c', 'import platform;print(platform.python_version())'])
        if observed.exit_code:
            raise ProjectRuntimeError('python_probe_failed', '无法读取运行环境的 Python 版本', retryable=True)
        proof = check_python_runtime(profile, observed.output.decode().strip())
        if marker.exists():
            if read_document(marker).get('profile_digest') != checksum or not (base / 'site-packages').is_dir():
                raise ProjectRuntimeError('python_cache_invalid', '已准备的离线 Python 依赖证明不符')
        else:
            artifacts = base / 'artifacts'
            artifacts.mkdir(parents=True, exist_ok=True)
            for artifact in profile['artifacts']:
                original = library.root / 'environments' / project.manifest['environment'] / artifact['path']
                if original.is_symlink() or library._artifact_digest(original) != artifact['digest']:
                    raise ProjectRuntimeError('artifact_invalid', '离线依赖制品摘要不符')
                shutil.copyfile(original, artifacts / Path(artifact['path']).name)
                (artifacts / Path(artifact['path']).name).chmod(0o644)
            for path in (base.parent, base, artifacts):
                path.chmod(0o755)
            # 安装到私有暂存后再发布，避免失败的半成品缓存及 network 的 64MiB 临时盘限制。
            with TemporaryDirectory(prefix='.install-', dir=base) as temporary:
                relative = container_root + '/' + Path(temporary).name
                result = network.exec_run(['python3', '-m', 'pip', 'install', '--disable-pip-version-check',
                    '--no-cache-dir', '--no-index', '--no-deps', '--no-compile', '--target', relative + '/site-packages',
                    '--find-links', container_root + '/artifacts', *profile['requirements']], environment={'TMPDIR': relative})
                if result.exit_code:
                    raise ProjectRuntimeError('offline_install_failed', '项目离线依赖准备失败，请核对冻结依赖与当前环境', details=proof)
                installed = Path(temporary) / 'site-packages'
                for current, directories, files in os.walk(installed):
                    Path(current).chmod(0o755)
                    if any((Path(current) / name).is_symlink() for name in directories):
                        raise ValueError('离线 Python 依赖目录不能是符号链接')
                    for name in files:
                        path = Path(current) / name
                        if path.is_symlink():
                            raise ValueError('离线 Python 依赖不能包含符号链接')
                        path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
                target = base / 'site-packages'
                if target.is_symlink():
                    raise ValueError('离线 Python 缓存不能是符号链接')
                if target.exists():
                    shutil.rmtree(target)
                installed.rename(target)
        # 即使命中旧缓存也先核对实际解释器，升级不会靠旧凭据绕过兼容规则。
        atomic_json(marker, {'profile_digest': checksum, **proof})
        return {'bin': container_root + '/site-packages/bin', 'site': container_root + '/site-packages'}
