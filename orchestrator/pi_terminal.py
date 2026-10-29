"""Pi 共用的原生 Claude Code 终端监督、输入与被动观察，不编排业务阶段。"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from math import isfinite
from pathlib import Path
from socket import SHUT_WR
from stat import S_ISREG
from threading import RLock
from uuid import uuid4

from account_runtime import AccountRuntime, atomic_json
from project_library import read_document, safe_relative
from project_scenario_usage import aggregate_usage, source_usage


KEYS = {'Enter', 'Escape', 'Up', 'Down', 'Left', 'Right', 'Tab', 'BTab', 'Space',
    'BSpace', 'Delete', 'Home', 'End', 'PPage', 'NPage'} | {
    'C-' + character for character in 'abcdefghijklmnopqrstuvwxyz'} | {'F' + str(index) for index in range(1, 13)}


class PiTerminal:
    """只操作服务端绑定账号、来源和代次的原生终端。

    :param runtime: 固定账号运行环境。
    :param settings: CLI 设置回调。
    :param quota_context: 当前执行的被动额度上下文回调。
    """

    def __init__(self, runtime: AccountRuntime, settings, quota_context, quota_release=None, credentials=None,
                 driver: Path | None = None, *, quota_observation=None, namespace: str, scenario_resources: bool = False) -> None:
        """绑定可信服务命名空间，不启动终端或模型。

        :param runtime: 固定账号运行环境。
        :param settings: CLI 设置回调。
        :param quota_context: 被动额度登记回调。
        :param quota_release: 精确收口后归还额度许可的回调。
        :param credentials: 从唯一凭据所有者同步的回调。
        :param driver: 只读终端监督脚本。
        :param quota_observation: 结构化限额或认证补证回调。
        :param namespace: 服务端固定的 projects 或 warmup，不能来自模型参数。
        :param scenario_resources: 是否准备工程所需的运行资源。
        :return: None。
        """
        if namespace not in ('projects', 'warmup'):
            raise ValueError('Pi 终端服务命名空间不合法')
        self.runtime, self.settings = runtime, settings
        self.quota_context, self.quota_release, self.credentials = quota_context, quota_release, credentials
        self.quota_observation, self.namespace = quota_observation, namespace
        self.scenario_resources = scenario_resources
        self._passive_lock = RLock()
        local = Path(__file__).resolve().parents[1] / 'images/account/projects_cli.py'
        self.driver = driver or (local if local.is_file() else Path('/opt/v3/projects-cli.py'))

    def _prepare_execution(self, root: Path, row: dict, account: dict, work: dict) -> tuple[Path, dict]:
        """由业务适配器准备持久工作区和可信进程环境。:param root: 账号目录。:param row: 环境。:param account: 账号。:param work: 原工作。:return: 工作区及附加环境。"""
        raise NotImplementedError

    def start(self, account: dict, work: dict) -> dict:
        """领取账号租约，在持久项目目录启动没有自动输入逻辑的 CLI。

        :param account: 已通过公共门禁的账号。
        :param work: 新架构的工作记录。
        :return: 可持久化的执行定位信息，不包含凭据。
        """
        runtime = self.runtime
        settings = json.loads(work['settings_json'])
        version = settings['claude_code_version']
        capture = bool(account.get(self.namespace + '_capture_enabled', 0))
        source = f"{self.namespace}:{work['id']}:{work['generation']}"
        if self.credentials:
            self.credentials(account)
        with runtime._cli_setup(account, source, version, idle_only=True, shared_cli=not capture,
                scenario_resources=self.scenario_resources) as (row, container, job):
            quota_admitted, launched = False, False
            try:
                if not capture and not job.get('shared_cli'):
                    raise ValueError('Pi 终端需要支持逐作业监督的 v3 账号环境')
                if capture:
                    # 监督能力独立于租约类型，不能把独占捕获伪装成共享作业。
                    job['execution_role'] = 'pi-capture'
                runtime.sync_credentials(row, account)
                root = runtime._root(row)
                workspace, prepared_environment = self._prepare_execution(root, row, account, work)
                alias = workspace.name
                cwd = '/home/node/projects/' + alias
                # 同一工作同代次可以多次恢复；本次握手必须独占目录，不能读取旧 PID 的证明或许可。
                handle = uuid4().hex[:20]
                runtime_job = root / 'runtime/jobs' / handle
                controls = root / 'controls' / handle
                for path in (runtime_job, controls):
                    path.mkdir(parents=True, exist_ok=False, mode=0o750)
                    os.chown(path, 1000 if path == runtime_job else 0, 1000, follow_symlinks=False)
                    path.chmod(0o750)
                os.chown(root / 'controls', 0, 1000, follow_symlinks=False)
                (root / 'controls').chmod(0o750)
                session = self.namespace + '-' + work['id']
                socket = '/run/v3/jobs/' + handle + '/tmux.sock'
                override = runtime_job / 'settings.json'
                original = root / 'home/.claude/settings.json'
                atomic_json(override, read_document(original) if original.is_file() else {})
                os.chown(override, 1000, 1000, follow_symlinks=False)
                job.update(run_id=work['id'], handle=handle, cwd=cwd, version=version,
                    tmux=session, tmux_socket=socket, settings_override=str(override.relative_to(root)),
                    network_inspection_mode='capture' if capture else 'passthrough')
                runtime._save_execution(job)
                flows = runtime.execution_flows(account, source,
                    runtime.data / 'flows' / account['name'] / self.namespace / work['id'])
                context = self.quota_context(account, source, flows, controls)
                quota_admitted = True
                runtime._install_cli_quota(job, cwd, flows, context.get('QUOTA_IDENTITY'))
                context_path = runtime._network_runtime(row) / 'context.json'
                if capture:
                    flow_path = '/flows/' + str(flows.relative_to(root / 'flows'))
                    context.update(NETWORK_INSPECTION_MODE='capture', QUOTA_SOURCE=source,
                        STATS_FILE=flow_path + '/stats.jsonl', CAPTURE_FILE=flow_path + '/http_capture.jsonl',
                        CAPTURE_INDEX_FILE=flow_path + '/capture_index.json', CAPTURE_FULL_HTTP='1', SAVE_FULL_FLOWS='1',
                        QUOTA_STATE_FILE=f"/quota-accounts/{account['id']}/state.json",
                        QUOTA_SIGNAL_FILE=f'/controls/{handle}/pause.json',
                        QUOTA_OBSERVATIONS_FILE=flow_path + '/passive-quota.jsonl',
                        QUOTA_CREDENTIALS_FILE='/run/v3/access/.credentials.json')
                    job['capture_flows'] = str(flows.relative_to(root / 'flows'))
                    runtime._save_execution(job)
                    atomic_json(context_path, context)
                    runtime._configure_network_context(container, context)
                else:
                    context = {'NETWORK_INSPECTION_MODE': 'passthrough', 'QUOTA_SOURCE': ''}
                    atomic_json(context_path, context)
                    runtime._configure_network_context(container, context, reuse_passthrough=True,
                        require_reuse=len(runtime.environment_jobs(row['environment_id'])) > 1)
                signal = f'/controls/{handle}/pause.json'
                native = root / 'home/.claude/projects' / cwd.replace('/', '-') / (work['session_id'] + '.jsonl')
                if work.get('resume_required') and not native.is_file():
                    raise ValueError('原 Claude 会话缺失，不能用新会话替代已有输入')
                # 额度补证仍按逻辑 source 读取，不能随本次握手目录变化而重放旧会话错误。
                cursor = root / 'runtime' / (self.namespace + '-quota') / (hashlib.sha256(source.encode()).hexdigest()[:20] + '.json')
                # 恢复沿用原 JSONL，但旧错误不属于新执行；从启动前的精确字节边界开始。
                observed = native.stat() if native.is_file() else None
                atomic_json(cursor, {'source': source, 'session_id': work['session_id'],
                    'file_identity': f'{observed.st_dev}:{observed.st_ino}' if observed else None,
                    'offset': observed.st_size if observed else 0, 'discarding': False, 'seen': []})
                configuration = {'session': session, 'socket': socket, 'session_id': work['session_id'],
                    'resume': native.is_file(), 'settings': f'/run/v3/jobs/{handle}/settings.json',
                    'model': settings.get('execution_model'), 'timeout_sec': work['remaining_sec'],
                    'exit_file': f'/run/v3/jobs/{handle}/exit-code', 'quota_signal': signal,
                    'source': source, 'interaction_signal': f'/run/v3/jobs/{handle}/interaction.json'}
                atomic_json(runtime_job / (self.namespace + '.json'), configuration)
                os.chown(runtime_job / (self.namespace + '.json'), 1000, 1000, follow_symlinks=False)
                script = root / 'runtime/drivers' / (self.namespace + '-' + handle + '.py')
                script.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
                os.chown(script.parent, 0, 1000, follow_symlinks=False)
                script.parent.chmod(0o750)
                script.write_bytes(self.driver.read_bytes())
                os.chown(script, 0, 1000, follow_symlinks=False)
                script.chmod(0o750)
                environment = {**runtime.execution_environment(row), 'HOME': '/home/node',
                    'PATH': f'/cli/{version}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin',
                    'CLAUDE_CODE_VERSION': version,
                    'CLAUDE_CODE_EFFORT_LEVEL': settings['claude_effort_level'],
                    'DISABLE_AUTOUPDATER': '1', 'CC2API_MANAGED_OAUTH': '1' if account.get('cc2api_account_id') is not None else '0',
                    **prepared_environment}
                if capture:
                    ca = '/etc/mitm/mitmproxy-ca-cert.pem'
                    environment.update(NODE_EXTRA_CA_CERTS=ca, SSL_CERT_FILE=ca,
                        REQUESTS_CA_BUNDLE=ca, CURL_CA_BUNDLE=ca, GIT_SSL_CAINFO=ca)
                execution = runtime.client.api.exec_create(container.id,
                    ['python3', '-I', '/usr/local/bin/v3-cli-control', 'supervise', '--source', source,
                        '--proof', f'/run/v3/jobs/{handle}/process.json', '--ready', f'/controls/{handle}/start.json',
                        '--result', f'/run/v3/jobs/{handle}/process-result.json', '--',
                        'python3', '-I', '/run/v3/drivers/' + script.name, '--config', f'/run/v3/jobs/{handle}/{self.namespace}.json'],
                    environment=environment, workdir=cwd)
                job['exec'] = execution['Id']
                runtime._save_execution(job)
                runtime.client.api.exec_start(execution['Id'], detach=True)
                launched = True
                runtime._attach_process(job, runtime_job / 'process.json')
                atomic_json(controls / 'start.json', job['process'], 0o640)
                os.chown(controls / 'start.json', 0, 1000, follow_symlinks=False)
                return {'token': job['token'], 'source': source, 'workspace': str(workspace.relative_to(runtime.data)),
                    'capture_enabled': capture,
                    'capture_flows': str(flows.relative_to(runtime.data)),
                    'native': str((root / 'home/.claude/projects' / cwd.replace('/', '-')).relative_to(runtime.data)),
                    'interaction_signal': str((runtime_job / 'interaction.json').relative_to(runtime.data)),
                    'quota_signal': str((controls / 'pause.json').relative_to(runtime.data))}
            except Exception:
                runtime.cleanup(job['token'])
                if quota_admitted and self.quota_release:
                    self.quota_release(account, source, not launched)
                raise

    def passive_status(self, work: dict) -> dict:
        """消费本代原生会话中的结构化错误，不解释普通正文或发起额度请求。

        :param work: 含当前账号、控制代次、原生会话及已登记执行定位的工作。
        :return: 新补证的认证错误、限额窗口、可信重置时间与去重键；没有新事实时返回空摘要。
        """
        empty = {'account_error': None, 'quota_limited': False, 'window': None, 'retry_at': None,
            'observed_at': None, 'evidence_key': None, 'native_error': None}
        if not work.get('runtime_json'):
            return empty
        info = json.loads(work['runtime_json'])
        with self._passive_lock:
            job = self.runtime.job_for_container(info['token'])
            expected_source = f"{self.namespace}:{work['id']}:{work['generation']}"
            if (job['account']['id'] != work['account_id'] or job['row']['account_id'] != work['account_id']
                    or job['source'] != expected_source or info.get('source') != expected_source
                    or job.get('heartbeat_failed')):
                raise ValueError('原生额度补证与账号或执行代次不符')
            root = self.runtime._root(job['row'])
            directory = self.runtime.data / safe_relative(info['native'])
            expected = root / 'home/.claude/projects' / job['cwd'].replace('/', '-')
            path = directory / (work['session_id'] + '.jsonl')
            if directory != expected or directory.is_symlink() or path.is_symlink():
                raise ValueError('原生额度补证的会话目录归属不符')
            if not path.exists():
                return empty
            if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('原生额度补证必须属于当前固定账号')
            marker = root / 'runtime' / (self.namespace + '-quota') / (hashlib.sha256(expected_source.encode()).hexdigest()[:20] + '.json')
            state = read_document(marker) if marker.is_file() else {'source': expected_source,
                'session_id': work['session_id'], 'offset': 0, 'file_identity': None, 'discarding': False, 'seen': []}
            if state.get('source') != expected_source or state.get('session_id') != work['session_id']:
                raise ValueError('原生额度补证游标与当前执行不符')
            observed = path.stat()
            identity = f'{observed.st_dev}:{observed.st_ino}'
            if state['file_identity'] not in (None, identity) or state['offset'] > observed.st_size:
                state.update(offset=0, discarding=False)
            state['file_identity'] = identity
            initial = state['offset']
            with path.open('rb') as source:
                source.seek(initial)
                while source.tell() - initial < 256 * 1024:
                    offset = source.tell()
                    line = source.readline(2 * 1024 * 1024)
                    if not line:
                        break
                    complete = line.endswith(b'\n')
                    if state['discarding']:
                        state.update(offset=source.tell(), discarding=not complete)
                        continue
                    if not complete:
                        if len(line) == 2 * 1024 * 1024:
                            # 超长普通消息分片跳过，不能把后半段误当独立错误事件。
                            state.update(offset=source.tell(), discarding=True)
                        else:
                            source.seek(offset)
                        break
                    try:
                        value = json.loads(line)
                    except (ValueError, UnicodeError):
                        state['offset'] = source.tell()
                        continue
                    facts = self._passive_error(value, work, expected_source, time.time())
                    if facts and facts['evidence_key'] not in state['seen']:
                        if self.quota_observation:
                            # 补证提交失败不能推进游标；同一事实可由回调按时间和键幂等重试。
                            self.quota_observation(job['account'], expected_source, facts)
                        state['seen'] = [*state['seen'], facts['evidence_key']][-128:]
                        state['offset'] = source.tell()
                        atomic_json(marker, state)
                        return facts
                    state['offset'] = source.tell()
            atomic_json(marker, state)
            return empty

    @staticmethod
    def _passive_error(value: object, work: dict, source: str, now: float) -> dict | None:
        """只信任官方错误标志及结构化字段，模型普通回答不能形成门禁事实。"""
        if (not isinstance(value, dict) or value.get('type') != 'assistant'
                or value.get('isApiErrorMessage') is not True or value.get('isSidechain') is True
                or value.get('sessionId') != work['session_id']):
            return None
        message = value.get('message')
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            return None
        error, identifier = value.get('error'), value.get('uuid')
        if (error not in ('rate_limit', 'account_on_hold', 'invalid_grant', 'authentication_failed')
                or not isinstance(identifier, str) or not 1 <= len(identifier) <= 200):
            return None
        try:
            timestamp = datetime.fromisoformat(str(value.get('timestamp') or '').replace('Z', '+00:00'))
            observed = timestamp.timestamp()
        except (ValueError, OverflowError, OSError):
            return None
        started = work.get('segment_started_at') or work.get('started_at') or work.get('created_at')
        if timestamp.tzinfo is None or not started or not float(started) <= observed <= now + 5:
            return None
        if error == 'rate_limit' and value.get('apiErrorIsTransient') is True:
            return None
        facts = {'account_error': ('invalid_grant' if error == 'authentication_failed' else error)
            if error != 'rate_limit' else None, 'quota_limited': error == 'rate_limit',
            'window': 'unknown' if error == 'rate_limit' else None, 'retry_at': None,
            'observed_at': observed, 'native_error': error,
            'evidence_key': hashlib.sha256(f'{source}:{identifier}:{error}'.encode()).hexdigest()}
        if error != 'rate_limit':
            return facts
        parameters = value.get('apiErrorParams')
        details = value.get('quotaLimits')
        if not isinstance(details, dict) and isinstance(parameters, dict):
            details = parameters.get('rate_limit_info')
        if isinstance(details, dict) and details.get('status') == 'rejected':
            kind = details.get('rateLimitType')
            if kind in ('five_hour', 'seven_day'):
                facts['window'] = kind
            reset = details.get('resetsAt')
            horizon = 6 * 3600 if kind == 'five_hour' else 8 * 86400
            if type(reset) in (int, float) and isfinite(reset) and observed < reset <= observed + horizon:
                facts['retry_at'] = float(reset)
        return facts

    def _interaction(self, work: dict, info: dict, job: dict) -> dict | None:
        """读取当前作业的有界唤醒提示，不把可写提示当授权证明。

        :param work: 当前工作。
        :param info: 已持久化的执行定位。
        :param job: 已核对容器的作业。
        :return: 合法提示；旧配置、陈旧或无效提示返回 None。
        """
        if not info.get('interaction_signal'):
            return None
        expected_source = f"{self.namespace}:{work['id']}:{work['generation']}"
        path = self.runtime.data / safe_relative(info['interaction_signal'])
        expected = self.runtime._root(job['row']) / 'runtime/jobs' / job['handle'] / 'interaction.json'
        if path != expected or info.get('source') != expected_source or job['source'] != expected_source:
            raise ValueError('交互通知与原执行归属不符')
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as stream:
                metadata = os.fstat(stream.fileno())
                if not S_ISREG(metadata.st_mode) or metadata.st_size > 4096:
                    return None
                raw = stream.read(4097)
            if len(raw) > 4096:
                return None
            value = json.loads(raw)
            if (not isinstance(value, dict) or set(value) != {'schema', 'source', 'session_id', 'id', 'event', 'tool', 'observed_at'}
                    or type(value['schema']) is not int or value['schema'] != 1
                    or value['source'] != expected_source or value['session_id'] != work['session_id']
                    or not isinstance(value['id'], str) or len(value['id']) != 32
                    or any(letter not in '0123456789abcdef' for letter in value['id'])
                    or value['event'] not in ('PermissionRequest', 'PreToolUse', 'Stop')
                    or value['tool'] is not None and (not isinstance(value['tool'], str) or len(value['tool']) > 200)
                    or value['event'] == 'PreToolUse' and value['tool'] not in ('AskUserQuestion', 'ExitPlanMode')
                    or type(value['observed_at']) not in (int, float) or not isfinite(value['observed_at'])
                    or not 0 < value['observed_at'] <= time.time() + 60):
                return None
            return value
        except (OSError, ValueError, TypeError):
            return None

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
        events, interactions = [], []
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
                    if message.get('role') == 'assistant' and isinstance(content, list):
                        for block in content:
                            if (block.get('type') == 'tool_use' and block.get('name') in ('AskUserQuestion', 'ExitPlanMode')
                                    and isinstance(block.get('id'), str)):
                                interactions.append({'id': block['id'][:200], 'tool': block['name']})
                cursor = source.tell()
        process = runtime.client.api.exec_inspect(job['exec'])
        running = bool(process.get('Running'))
        return {'screen': screen, 'events': events, 'cursor': cursor, 'running': running, 'terminal_ready': not result.exit_code,
            'interactions': interactions, 'interaction': self._interaction(work, info, job),
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
