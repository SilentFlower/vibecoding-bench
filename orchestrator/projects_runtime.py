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

from account_isolation import role_container
from account_runtime import AccountRuntime, atomic_json
from pi_terminal import KEYS, PiTerminal
from project_library import digest_json, materialize_snapshot, read_document, safe_relative, snapshot_tree


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

    def _workspace_identity(self, account: dict, row: dict, project_key: str, seed_digest: str, cycle_no: int):
        """从固定身份计算工作区，保留原工程首轮的全部历史路径。:param account: 账号。:param row: 环境。:param project_key: 项目。:param seed_digest: 冻结seed。:param cycle_no: 正整数轮次。:return: 别名及注册凭据。"""
        if type(cycle_no) is not int or cycle_no < 1:
            raise ValueError('工程轮次必须为正整数')
        identity = {'account_id': account['id'], 'environment_id': row['environment_id'],
            'project_key': project_key, 'seed_digest': seed_digest}
        if self.namespace == 'projects' and cycle_no == 1:
            alias = 'workspace-' + hashlib.sha256(f"{account['id']}:{project_key}:{seed_digest}".encode()).hexdigest()[:16]
        else:
            alias = self.namespace + '-workspace-' + hashlib.sha256(
                f"{self.namespace}:{account['id']}:{project_key}:{seed_digest}:{cycle_no}".encode()).hexdigest()[:16]
            identity.update(namespace=self.namespace, cycle_no=cycle_no, workspace='projects/' + alias)
        return alias, identity

    def _prepare_execution(self, root: Path, row: dict, account: dict, work: dict) -> tuple[Path, dict]:
        """准备同一项目累计源码与其冻结离线 Python 依赖。:param root: 账号目录。:param row: 环境。:param account: 账号。:param work: 原工程。:return: 工作区和原有工程环境。"""
        assets = self.catalog.for_work(work)
        project, definition = assets.objective(work['project_key'], work['objective_id'])
        workspace = self._prepare_workspace(root, row, account, work, project, definition)
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
        alias, identity = self._workspace_identity(account, row, work['project_key'],
            project.manifest['seed_digest'], work.get('cycle_no', 1))
        workspace = root / 'projects' / alias
        marker = root / 'runtime' / (self.namespace + '-workspaces') / (alias + '.json')
        if any(path.is_symlink() for path in (root, root / 'projects', root / 'runtime', marker.parent, marker)):
            raise ValueError('工程工作区或注册目录不能为链接')
        if marker.exists():
            if read_document(marker) != identity or workspace.is_symlink() or not workspace.is_dir():
                raise ValueError('项目工作区的账号或初始版本证明不符')
        else:
            if workspace.exists() or workspace.is_symlink():
                raise ValueError('未登记的项目工作区需要先核对，不能覆盖')
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

    def _registered_identity(self, saved: dict, account: dict, row: dict):
        """核对不可伪装成其它账号或轮次的注册身份。:param saved: 已读取凭据。:param account: 当前账号。:param row: 固定环境。:return: 轮次、别名和规范身份。"""
        if (not isinstance(saved, dict) or saved.get('account_id') != account['id']
                or saved.get('environment_id') != row['environment_id']
                or saved.get('namespace', 'projects') != self.namespace
                or not isinstance(saved.get('project_key'), str) or not saved['project_key']
                or not isinstance(saved.get('seed_digest'), str) or not re.fullmatch('[a-f0-9]{64}', saved['seed_digest'])):
            raise ValueError('工程清理注册的账号、空间或初始版本不符')
        cycle = saved.get('cycle_no', 1)
        alias, identity = self._workspace_identity(account, row, saved['project_key'], saved['seed_digest'], cycle)
        if any(saved.get(key) != value for key, value in identity.items()):
            raise ValueError('工程清理注册的真实路径或轮次不符')
        return cycle, alias, identity

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
            registered, selected = {}, []
            prefix = 'workspace-' if self.namespace == 'projects' else self.namespace + '-workspace-'
            for path in sorted(markers.iterdir()) if markers.exists() else []:
                if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                    raise ValueError('工程工作区注册目录包含链接或未知文件')
                # 兼容早期题库养号的独立 round marker；其文件名不属于工程别名空间。
                if self.namespace == 'warmup' and not path.name.startswith(prefix):
                    if re.fullmatch('[a-f0-9]{32}\\.json', path.name):
                        continue
                    raise ValueError('工程工作区注册目录包含未知文件')
                saved_marker = read_document(path)
                cycle, alias, identity = self._registered_identity(saved_marker, account, row)
                if path.name != alias + '.json' or saved_marker != identity:
                    raise ValueError('工程工作区凭据路径或内容不符')
                registered[alias] = identity
                if cycle == cycle_no:
                    selected.append((projects / alias, path))
            # 同空间出现无注册目录时不能猜其所属轮次，也不能靠目录名前缀直接清空。
            for path in projects.iterdir() if projects.exists() else []:
                owned = path.name.startswith(prefix) or self.namespace == 'projects' and path.name.startswith('projects-workspace-')
                if owned and path.name not in registered:
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
        if marker.exists():
            if read_document(marker).get('profile_digest') != checksum or not (base / 'site-packages').is_dir():
                raise ValueError('已准备的离线 Python 依赖证明不符')
        else:
            artifacts = base / 'artifacts'
            artifacts.mkdir(parents=True, exist_ok=True)
            for artifact in profile['artifacts']:
                original = library.root / 'environments' / project.manifest['environment'] / artifact['path']
                if original.is_symlink() or library._artifact_digest(original) != artifact['digest']:
                    raise ValueError('离线依赖制品摘要不符')
                shutil.copyfile(original, artifacts / Path(artifact['path']).name)
                (artifacts / Path(artifact['path']).name).chmod(0o644)
            for path in (base.parent, base, artifacts):
                path.chmod(0o755)
            network = role_container(runtime, row, 'network')
            observed = network.exec_run(['python3', '-c', 'import platform;print(platform.python_version())'])
            if observed.exit_code or observed.output.decode().strip() != profile['python']:
                raise ValueError('离线 Python 版本与冻结环境不符')
            # 安装到私有暂存后再发布，避免失败的半成品缓存及 network 的 64MiB 临时盘限制。
            with TemporaryDirectory(prefix='.install-', dir=base) as temporary:
                relative = container_root + '/' + Path(temporary).name
                result = network.exec_run(['python3', '-m', 'pip', 'install', '--disable-pip-version-check',
                    '--no-cache-dir', '--no-index', '--no-deps', '--no-compile', '--target', relative + '/site-packages',
                    '--find-links', container_root + '/artifacts', *profile['requirements']], environment={'TMPDIR': relative})
                if result.exit_code:
                    raise ValueError('项目离线依赖准备失败')
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
            atomic_json(marker, {'profile_digest': checksum})
        return {'bin': container_root + '/site-packages/bin', 'site': container_root + '/site-packages'}
