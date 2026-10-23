"""新 Projects 到固定账号环境的终端适配，不使用旧项目执行状态机。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from socket import SHUT_WR
from tempfile import TemporaryDirectory

from account_isolation import role_container
from account_runtime import AccountRuntime, atomic_json
from project_library import digest_json, materialize_snapshot, read_document, safe_relative, snapshot_tree
from project_scenario_usage import aggregate_usage, source_usage


KEYS = {'Enter', 'Escape', 'Up', 'Down', 'Left', 'Right', 'Tab', 'BTab', 'Space',
    'BSpace', 'Delete', 'Home', 'End', 'PPage', 'NPage'} | {
    'C-' + character for character in 'abcdefghijklmnopqrstuvwxyz'} | {'F' + str(index) for index in range(1, 13)}


class ProjectsTerminal:
    """只操作当前账号和执行代次已登记的 Claude Code 终端。

    :param runtime: 固定账号运行环境。
    :param catalog: 只读工程资产目录。
    :param settings: 返回已规范化 CLI 设置的回调。
    :param quota_context: 为当前来源登记被动额度采集的回调。
    """

    def __init__(self, runtime: AccountRuntime, catalog, settings, quota_context, quota_release=None, credentials=None,
                 driver: Path | None = None) -> None:
        """登记运行依赖，不启动账号或模型。

        :param runtime: 账号运行环境。
        :param catalog: 工程资产目录。
        :param settings: CLI 配置回调。
        :param quota_context: 被动额度登记回调。
        :param quota_release: 执行收口后归还额度恢复认领的回调。
        :param credentials: 启动前向权威凭据所有者同步的回调。
        :param driver: 本批控制镜像提供的只读终端监督脚本。
        :return: None。
        """
        self.runtime, self.catalog = runtime, catalog
        self.settings, self.quota_context = settings, quota_context
        self.quota_release, self.credentials = quota_release, credentials
        local = Path(__file__).resolve().parents[1] / 'images/account/projects_cli.py'
        self.driver = driver or (local if local.is_file() else Path('/opt/v3/projects-cli.py'))

    def start(self, account: dict, work: dict) -> dict:
        """领取账号租约，在持久项目目录启动没有自动输入逻辑的 CLI。

        :param account: 已通过公共门禁的账号。
        :param work: 新架构的工作记录。
        :return: 可持久化的执行定位信息，不包含凭据。
        """
        runtime = self.runtime
        assets = self.catalog.for_work(work)
        project, definition = assets.objective(work['project_key'], work['objective_id'])
        settings = json.loads(work['settings_json'])
        version = settings['claude_code_version']
        source = f"projects:{work['id']}:{work['generation']}"
        if self.credentials:
            self.credentials(account)
        with runtime._cli_setup(account, source, version, idle_only=True, shared_cli=True,
                scenario_resources=True) as (row, container, job):
            quota_admitted, launched = False, False
            try:
                if not job.get('shared_cli'):
                    raise ValueError('Pi 终端需要支持逐作业监督的 v3 账号环境')
                runtime.sync_credentials(row, account)
                root = runtime._root(row)
                alias = 'workspace-' + hashlib.sha256(
                    f"{account['id']}:{work['project_key']}:{project.manifest['seed_digest']}".encode()).hexdigest()[:16]
                workspace = root / 'projects' / alias
                marker = root / 'runtime/projects-workspaces' / (alias + '.json')
                identity = {'account_id': account['id'], 'environment_id': row['environment_id'],
                    'project_key': work['project_key'], 'seed_digest': project.manifest['seed_digest']}
                if marker.exists():
                    if read_document(marker) != identity or workspace.is_symlink() or not workspace.is_dir():
                        raise ValueError('项目工作区的账号或初始版本证明不符')
                else:
                    if workspace.exists() or workspace.is_symlink():
                        raise ValueError('未登记的项目工作区需要先核对，不能覆盖')
                    objects = runtime.data / 'projects/objects'
                    initial = snapshot_tree(project.root / 'seed', objects)
                    materialize_snapshot(initial, objects, workspace)
                    for relative in dict.fromkeys([*definition['materials'], *definition.get('owner_materials', [])]):
                        destination = workspace / safe_relative(relative)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(project.root / safe_relative(relative), destination)
                    for current, directories, files in os.walk(workspace):
                        os.chown(current, 1000, 1000, follow_symlinks=False)
                        for name in files:
                            os.chown(Path(current) / name, 1000, 1000, follow_symlinks=False)
                    atomic_json(marker, identity)
                cwd = '/home/node/projects/' + alias
                handle = hashlib.sha256(source.encode()).hexdigest()[:20]
                runtime_job = root / 'runtime/jobs' / handle
                controls = root / 'controls' / handle
                for path in (runtime_job, controls):
                    path.mkdir(parents=True, exist_ok=True, mode=0o750)
                    os.chown(path, 1000 if path == runtime_job else 0, 1000, follow_symlinks=False)
                    path.chmod(0o750)
                os.chown(root / 'controls', 0, 1000, follow_symlinks=False)
                (root / 'controls').chmod(0o750)
                session = 'projects-' + work['id']
                socket = '/run/v3/jobs/' + handle + '/tmux.sock'
                override = runtime_job / 'settings.json'
                original = root / 'home/.claude/settings.json'
                atomic_json(override, read_document(original) if original.is_file() else {})
                os.chown(override, 1000, 1000, follow_symlinks=False)
                job.update(run_id=work['id'], handle=handle, cwd=cwd, version=version,
                    tmux=session, tmux_socket=socket, settings_override=str(override.relative_to(root)),
                    network_inspection_mode='passthrough')
                runtime._save_execution(job)
                flows = runtime.execution_flows(account, source,
                    runtime.data / 'flows' / account['name'] / 'projects' / work['id'])
                context = self.quota_context(account, source, flows, controls)
                quota_admitted = True
                runtime._install_cli_quota(job, cwd, flows, context.get('QUOTA_IDENTITY'))
                context_path = runtime._network_runtime(row) / 'context.json'
                atomic_json(context_path, {'NETWORK_INSPECTION_MODE': 'passthrough', 'QUOTA_SOURCE': ''})
                runtime._configure_network_context(container, {'NETWORK_INSPECTION_MODE': 'passthrough', 'QUOTA_SOURCE': ''},
                    reuse_passthrough=True)
                signal = f'/controls/{handle}/pause.json'
                native = root / 'home/.claude/projects' / cwd.replace('/', '-') / (work['session_id'] + '.jsonl')
                if work.get('resume_required') and not native.is_file():
                    raise ValueError('原 Claude 会话缺失，不能用新会话替代已有输入')
                configuration = {'session': session, 'socket': socket, 'session_id': work['session_id'],
                    'resume': native.is_file(), 'settings': f'/run/v3/jobs/{handle}/settings.json',
                    'model': settings.get('execution_model'), 'timeout_sec': work['remaining_sec'],
                    'exit_file': f'/run/v3/jobs/{handle}/exit-code', 'quota_signal': signal}
                atomic_json(runtime_job / 'projects.json', configuration)
                os.chown(runtime_job / 'projects.json', 1000, 1000, follow_symlinks=False)
                script = root / 'runtime/drivers' / ('projects-' + handle + '.py')
                script.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
                os.chown(script.parent, 0, 1000, follow_symlinks=False)
                script.parent.chmod(0o750)
                script.write_bytes(self.driver.read_bytes())
                os.chown(script, 0, 1000, follow_symlinks=False)
                script.chmod(0o750)
                python = self._prepare_python(row, project, assets.library)
                environment = {**runtime.execution_environment(row), 'HOME': '/home/node',
                    'PATH': python['bin'] + f':/cli/{version}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin',
                    'PYTHONPATH': cwd + '/library:' + cwd + '/app:' + python['site'],
                    'CLAUDE_CODE_EFFORT_LEVEL': settings['claude_effort_level'],
                    'DISABLE_AUTOUPDATER': '1', 'CC2API_MANAGED_OAUTH': '1' if account.get('cc2api_account_id') is not None else '0'}
                execution = runtime.client.api.exec_create(container.id,
                    ['python3', '-I', '/usr/local/bin/v3-cli-control', 'supervise', '--source', source,
                        '--proof', f'/run/v3/jobs/{handle}/process.json', '--ready', f'/controls/{handle}/start.json',
                        '--result', f'/run/v3/jobs/{handle}/process-result.json', '--',
                        'python3', '-I', '/run/v3/drivers/' + script.name, '--config', f'/run/v3/jobs/{handle}/projects.json'],
                    environment=environment, workdir=cwd)
                job['exec'] = execution['Id']
                runtime._save_execution(job)
                runtime.client.api.exec_start(execution['Id'], detach=True)
                launched = True
                runtime._attach_process(job, runtime_job / 'process.json')
                atomic_json(controls / 'start.json', job['process'], 0o640)
                os.chown(controls / 'start.json', 0, 1000, follow_symlinks=False)
                return {'token': job['token'], 'source': source, 'workspace': str(workspace.relative_to(runtime.data)),
                    'native': str((root / 'home/.claude/projects' / cwd.replace('/', '-')).relative_to(runtime.data)),
                    'quota_signal': str((controls / 'pause.json').relative_to(runtime.data))}
            except Exception:
                runtime.cleanup(job['token'])
                if quota_admitted and self.quota_release:
                    self.quota_release(account, source, not launched)
                raise

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

    def observe(self, work: dict, cursor: int = 0) -> dict:
        """取得有界终端画面及原生会话增量，不推断应当发送的回复。

        :param work: 当前账号的工作记录。
        :param cursor: 已读原生会话字节位置。
        :return: 画面、原生文本事件、游标和进程状态。
        """
        info = json.loads(work['runtime_json'])
        runtime = self.runtime
        job = runtime.job_for_container(info['token'])
        if job.get('heartbeat_failed'):
            raise ValueError('账号执行租约已失效')
        container = runtime._container(job['row'])
        result = container.exec_run(['tmux', '-S', job['tmux_socket'], 'capture-pane', '-p', '-S', '-120', '-t', job['tmux']])
        screen = result.output.decode('utf-8', errors='replace')[-32000:] if not result.exit_code else ''
        events = []
        path = runtime.data / safe_relative(info['native']) / (work['session_id'] + '.jsonl')
        if path.exists():
            if path.is_symlink() or not path.is_file() or cursor > path.stat().st_size:
                raise ValueError('原生会话归属或读取边界异常')
            with path.open('rb') as source:
                source.seek(cursor)
                while source.tell() - cursor < 65536:
                    offset = source.tell()
                    line = source.readline(1024 * 1024)
                    if not line.endswith(b'\n'):
                        source.seek(offset)
                        break
                    value = json.loads(line)
                    message = value.get('message') or {}
                    content = message.get('content', '')
                    text = content if isinstance(content, str) else '\n'.join(
                        block.get('text', '') for block in content if block.get('type') == 'text') if isinstance(content, list) else ''
                    if message.get('role') in ('user', 'assistant') and text:
                        events.append({'id': value.get('uuid'), 'role': message['role'], 'text': text[-24000:]})
                cursor = source.tell()
        process = runtime.client.api.exec_inspect(job['exec'])
        running = bool(process.get('Running'))
        return {'screen': screen, 'events': events, 'cursor': cursor, 'running': running, 'terminal_ready': not result.exit_code,
            'exit_code': process.get('ExitCode') if not running else None,
            'quota_paused': (runtime.data / safe_relative(info['quota_signal'])).is_file()}

    def send(self, work: dict, operation_id: str, text: str, keys: list[str], submit: bool) -> None:
        """经 stdin 缓冲发送文本或有限按键，失败时不得自动重放。

        :param work: 当前已核对的工作。
        :param operation_id: 控制端预先登记的操作标识。
        :param text: 原样投递的业务文本。
        :param keys: 已验证的终端按键。
        :param submit: 是否在文本后发送 Enter。
        :return: None；任何不确定投递抛出 RuntimeError。
        """
        if len(text.encode()) > 48000 or len(keys) > 16 or any(key not in KEYS for key in keys):
            raise ValueError('终端文本或按键不符合限制')
        runtime = self.runtime
        info = json.loads(work['runtime_json'])
        job = runtime.job_for_container(info['token'])
        with runtime.environment_lock(job['row']['environment_id']):
            if job.get('heartbeat_failed') or runtime.job_for_container(info['token']) is not job:
                raise ValueError('账号执行归属已改变')
            container = runtime._container(job['row'])
            command = ['tmux', '-S', job['tmux_socket']]
            stream = None
            try:
                if text:
                    execution = runtime.client.api.exec_create(container.id,
                        [*command, 'load-buffer', '-b', operation_id, '-'], stdin=True, tty=False)
                    stream = runtime.client.api.exec_start(execution['Id'], socket=True, tty=False)
                    raw = getattr(stream, '_sock', None) or stream
                    raw.settimeout(5)
                    raw.sendall(text.encode())
                    raw.shutdown(SHUT_WR)
                    while raw.recv(4096):
                        pass
                    if runtime.client.api.exec_inspect(execution['Id']).get('ExitCode') != 0:
                        raise RuntimeError('终端缓冲未确认')
                    result = container.exec_run([*command, 'paste-buffer', '-p', '-b', operation_id, '-t', job['tmux']])
                    if result.exit_code:
                        raise RuntimeError('终端文本投递未确认')
                sequence = [*keys, *(['Enter'] if submit else [])]
                if sequence and container.exec_run([*command, 'send-keys', '-t', job['tmux'], *sequence]).exit_code:
                    raise RuntimeError('终端按键投递未确认')
            except Exception:
                raise RuntimeError('终端输入结果未知，已保留意图，禁止自动重复发送') from None
            finally:
                if stream:
                    stream.close()
                if text:
                    container.exec_run([*command, 'delete-buffer', '-b', operation_id])

    def control(self, work: dict, operation: str) -> dict:
        """暂停、恢复或收口精确的执行树。

        :param work: 当前工作。
        :param operation: freeze、resume 或 stop。
        :return: 实际进程控制结果。
        """
        token = json.loads(work['runtime_json'])['token']
        if operation == 'stop':
            job = self.runtime.job_for_container(token)
            self.runtime.cleanup(token)
            if self.quota_release:
                self.quota_release(job['account'], job['source'], False)
            return {'stopped': True}
        return self.runtime.control_execution(token, operation)

    def workspace(self, work: dict) -> Path:
        """返回当前工作受控的真实源码目录。

        :param work: 已登记的工作。
        :return: 项目物理目录。
        """
        info = json.loads(work['runtime_json'])
        path = self.runtime.data / safe_relative(info['workspace'])
        if path.is_symlink() or not path.is_dir():
            raise ValueError('工作区缺失或已被替换')
        return path

    def conversation(self, work: dict) -> list[dict]:
        """读取原生实际交流，作为独立验收依据，超限时明确拒绝截断评分。

        :param work: 当前工作。
        :return: 原生用户和开发者文本，不含思考或工具调用块。
        """
        info = json.loads(work['runtime_json'])
        path = self.runtime.data / safe_relative(info['native']) / (work['session_id'] + '.jsonl')
        if path.is_symlink() or not path.is_file():
            raise ValueError('独立验收缺少原生会话')
        messages, size = [], 0
        with path.open('rb') as stream:
            for line in stream:
                value = json.loads(line)
                message = value.get('message') or {}
                if message.get('role') not in ('user', 'assistant'):
                    continue
                content = message.get('content', '')
                text = content if isinstance(content, str) else '\n'.join(
                    item.get('text', '') for item in content if item.get('type') == 'text') if isinstance(content, list) else ''
                if not text:
                    continue
                size += len(text.encode())
                if size > 256 * 1024:
                    raise ValueError('完整业务交流超出验收输入上限，不能静默截断')
                messages.append({'role': message['role'], 'content': text})
        return messages

    def usage(self, work: dict) -> dict:
        """按当前目标独立的原会话汇总真实用量，缺失字段保持未知。

        :param work: 当前工作。
        :return: 去重的输入、输出、缓存及证据覆盖。
        """
        info = json.loads(work['runtime_json'])
        directory = self.runtime.data / safe_relative(info['native'])
        name = work['session_id'] + '.jsonl'
        path = directory / name
        if not path.is_file() or path.is_symlink():
            return aggregate_usage([])
        return aggregate_usage([source_usage(directory, {name: 0}, {name: path.stat().st_size}, work['session_id'])])
