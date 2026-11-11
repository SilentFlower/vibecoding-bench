"""固定部署的宿主动作适配器：实际镜像核验、维护切换及恢复。"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import quote
from urllib.request import ProxyHandler, Request, build_opener

from manage import _check_local_reference, _local_image_matches, _container_image_matches, load_bundle, load_environment
from runtime_files import atomic_json, atomic_text
from system_update_contract import DOWNLOAD_ROOT, ROLES, ReleaseRedirect, fetch_bytes, safe_read, strict_json, validate_migration_plan
from system_update_gate import read_gate
from system_update_database import assert_quiescent, create_snapshot, restore_snapshot, rotate_snapshots

SOFTWARE_FIELDS = ('version', 'version_base', 'build_time', 'node_version')
ENVIRONMENT_IDENTITY = ('environment_id', 'name', 'account_id', 'fingerprint_json')
ENVIRONMENT_BINDINGS = ('generation', 'container_id', 'network_container_id', 'sender_container_id', 'state', 'isolation_version')


def docker(*arguments: str, timeout: int = 120) -> str:
    """执行固定 argv 的 Docker 命令，公开错误不包含原输出。

    :param arguments: 经合同核验的 Docker 参数。
    :param timeout: 执行期限。
    :return: 完整标准输出。
    """
    result = subprocess.run(['docker', *arguments], capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError('Docker 部署动作失败，请核对私有运行记录')
    return result.stdout


class HostDeployment:
    """只操作首次接入固化的单一部署，所有路径来自宿主策略。"""

    def __init__(self, policy: dict) -> None:
        """绑定部署策略。

        :param policy: 已校验的宿主策略。
        :return: None。
        """
        self.policy = policy
        self.root = Path(policy['state_root'])
        self.data = Path(policy['data_root'])
        self.env = Path(policy['env_file'])
        self.gate = self.root / 'gate'
        self.opener = build_opener(ProxyHandler({}))

    def values(self) -> dict:
        """核对当前部署文件与数据根归属。

        :return: 私有环境值。
        """
        values = load_environment(self.env)
        marker = strict_json(safe_read(self.data / '.v3-deployment.json'))
        if (values.get('V3_DEPLOYMENT_ID') != self.policy['deployment']
                or values.get('V3_DATA_ROOT') != str(self.data)
                or marker.get('deployment') != self.policy['deployment']):
            raise ValueError('更新目标部署或数据目录归属已变化')
        if self.data != self.data.resolve() or not self.data.is_absolute():
            raise ValueError('更新数据目录必须为固化真实路径')
        return values

    def controls(self, require_both: bool = True) -> dict:
        """按精确标签和挂载读取两项控制服务。

        :param require_both: 普通操作要求双端完整，恢复允许部分创建。
        :return: gateway/orchestrator 的实际 inspect 对象。
        """
        ids = docker('ps', '-aq', '--filter', 'label=vibebench.product=v3',
            '--filter', 'label=vibebench.deployment=' + self.policy['deployment']).split()
        objects = json.loads(docker('inspect', *ids)) if ids else []
        result = {}
        for item in objects:
            labels = item['Config'].get('Labels') or {}
            role = labels.get('vibebench.role')
            if role not in ('gateway', 'orchestrator'):
                continue
            if role in result:
                raise ValueError('部署控制服务角色不唯一')
            expected = self.data / ('gateway' if role == 'gateway' else 'bench')
            if not any(mount.get('Source') == str(expected) and mount.get('Destination') == '/data' for mount in item.get('Mounts', [])):
                raise ValueError('部署控制服务数据挂载不匹配')
            result[role] = item
        if require_both and set(result) != {'gateway', 'orchestrator'}:
            raise ValueError('部署控制服务缺失')
        return result

    def request(self, service: str, path: str, body: dict | None = None, timeout: int = 15) -> dict:
        """向本部署的实际控制服务发送受证管理请求。

        :param service: gateway 或 orchestrator。
        :param path: 固定内部路径。
        :param body: 有界协议载荷。
        :param timeout: 单次期限。
        :return: 有界 JSON 对象。
        """
        values = self.values()
        if service == 'gateway':
            base = f'http://127.0.0.1:{int(values.get("V3_HOST_PORT", "18080"))}'
            token = values['V3_ADMIN_PASSWORD']
        else:
            control = self.controls()['orchestrator']
            network = 'vibebench-v3-' + self.policy['deployment']
            address = str(ipaddress.IPv4Address(control['NetworkSettings']['Networks'][network]['IPAddress']))
            base = 'http://' + address + ':8000'
            token = values['V3_INTERNAL_TOKEN']
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
            'X-V3-Update-Token': safe_read(self.root / 'socket/token', 128, private=True).decode().strip()}
        request = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with self.opener.open(request, timeout=timeout) as response:
            return strict_json(response.read(131073))

    def metadata(self) -> dict:
        """只保存身份摘要和明确可逆的软件字段，不复制数据库或凭据。

        :return: 受保护身份摘要与软件字段前值。
        """
        with closing(sqlite3.connect('file:' + quote(str(self.data / 'bench/db.sqlite'), safe='/') + '?mode=ro', uri=True)) as connection, connection:
            rows = connection.execute('SELECT environment_id,name,account_id,fingerprint_json FROM account_environments ORDER BY environment_id').fetchall()
            bench_accounts = connection.execute('SELECT id,name,profile_path,cc2api_account_id FROM accounts ORDER BY id').fetchall()
            ownership = {'bench': connection.execute('SELECT account_id,record_json FROM account_credential_ownerships ORDER BY account_id').fetchall(),
                'local': connection.execute('SELECT account_id,record_json FROM local_credential_authorizations ORDER BY account_id').fetchall()}
            bench_schema = connection.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name").fetchall()
        gateway = []
        software = {}
        with closing(sqlite3.connect('file:' + quote(str(self.data / 'gateway/gateway.sqlite'), safe='/') + '?mode=ro', uri=True)) as connection, connection:
            gateway_schema = connection.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name").fetchall()
            gateway_accounts = connection.execute('SELECT id,email,device_id,account_uuid,organization_uuid FROM accounts ORDER BY id').fetchall()
            ownership['gateway'] = connection.execute('SELECT account_id,record_json FROM oauth_account_ownerships ORDER BY account_id').fetchall()
            for account_id, raw in connection.execute('SELECT id,canonical_env FROM accounts ORDER BY id'):
                environment = json.loads(raw) if raw else None
                if isinstance(environment, dict):
                    software[str(account_id)] = {key: {'present': key in environment, 'value': environment.get(key)} for key in SOFTWARE_FIELDS}
                    environment = {key: value for key, value in environment.items() if key not in SOFTWARE_FIELDS}
                gateway.append((account_id, environment))
        digest = hashlib.sha256(json.dumps({'bench': rows, 'gateway': gateway, 'bench_accounts': bench_accounts,
            'gateway_accounts': gateway_accounts, 'ownership': ownership}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return {'identity_sha256': digest, 'software': software, 'database_schema': {
            name: hashlib.sha256(json.dumps(schema, separators=(',', ':')).encode()).hexdigest()
            for name, schema in (('bench', bench_schema), ('gateway', gateway_schema))}}

    def restore_software(self, before: dict, observed: dict) -> None:
        """仅在明确前后值一致时恢复四项软件字段，保留所有其他字段。

        :param before: 明确原软件字段。
        :param observed: 本次启动后已观察的软件字段。
        :return: None；并发漂移立即拒绝。
        """
        with closing(sqlite3.connect(self.data / 'gateway/gateway.sqlite')) as connection, connection:
            for identity, fields in before.items():
                row = connection.execute('SELECT canonical_env FROM accounts WHERE id=?', (int(identity),)).fetchone()
                if not row or not row[0]:
                    raise ValueError('账号软件字段恢复来源缺失')
                value = json.loads(row[0])
                current = {key: {'present': key in value, 'value': value.get(key)} for key in SOFTWARE_FIELDS}
                if current != observed.get(identity):
                    raise ValueError('账号软件字段恢复遇到并发变化')
                for key, previous in fields.items():
                    if previous['present']:
                        value[key] = previous['value']
                    else:
                        value.pop(key, None)
                changed = connection.execute('UPDATE accounts SET canonical_env=? WHERE id=? AND canonical_env=?',
                    (json.dumps(value, ensure_ascii=False, separators=(',', ':')), int(identity), row[0]))
                if changed.rowcount != 1:
                    raise ValueError('账号软件字段恢复条件已变化')

    def verify_images(self, selection: dict, require_local: bool = True) -> dict:
        """逐组件核对真实镜像身份及来源标签，允许声明过的混合组合。

        :param selection: 精确组件选择。
        :param require_local: 是否要求本地镜像存在。
        :return: 实际镜像 inspect。
        """
        result = {}
        for role in ROLES:
            entry = selection[role]
            try:
                image = json.loads(docker('image', 'inspect', entry['reference']))[0]
            except RuntimeError:
                if require_local:
                    raise
                continue
            labels = image['Config'].get('Labels') or {}
            if (not _local_image_matches(entry['reference'], image, {**entry, 'digest': entry['config_digest']})
                    or image.get('Os') + '/' + image.get('Architecture') != 'linux/amd64'
                    or labels.get('vibebench.product') != 'v3' or labels.get('vibebench.role') != role
                    or labels.get('vibebench.release') != entry['release']
                    or labels.get('vibebench.parent-revision') != entry['revision']
                    or labels.get('vibebench.system-update-protocol') != '1'
                    or labels.get('vibebench.credential-ownership-protocol') != '1'
                    or labels.get('vibebench.isolation-version') != '2'
                    or (role == 'account' and (labels.get('vibebench.account-runtime-protocol') != '1'
                        or labels.get('vibebench.cli-install-version') != '2'))):
                raise ValueError('更新镜像的真实内容或来源不符')
            result[role] = image
        return result

    def prepare(self, release: dict, selection: dict, folder: Path) -> None:
        """按签名固定来源拉取组件，原版持续运行。

        :param release: 已验签完整发行。
        :param selection: 实际拟使用组合。
        :param folder: 受控发行缓存目录。
        :return: None。
        """
        needed = sum(entry['unpacked_bytes'] for entry in selection.values()) + release['bundle']['size'] + 512 * 1024 ** 2
        if shutil.disk_usage(self.data).free < needed:
            raise ValueError('磁盘空间不足以保留当前及恢复制品')
        # 原始联合清单也逐字节核对，外层签名不能替代构建来源证据。
        for role in ROLES:
            asset = release['build_manifests'][role]
            path = folder / asset['name']
            if not path.exists():
                raw = fetch_bytes(f'{DOWNLOAD_ROOT}/{release["release"]}/{asset["name"]}', asset['size'])
                if len(raw) != asset['size'] or hashlib.sha256(raw).hexdigest() != asset['sha256']:
                    raise ValueError('原始构建清单摘要不符')
                atomic_text(path, raw.decode())
            raw = safe_read(path)
            if len(raw) != asset['size'] or hashlib.sha256(raw).hexdigest() != asset['sha256']:
                raise ValueError('缓存构建清单摘要不符')
            source = strict_json(raw)
            entry = release[role]
            if (source.get('schema') != 3 or source.get('release') != entry['release']
                    or source.get('parent_revision') != entry['revision']
                    or any(source['images'][role].get(key) != entry[key] for key in ('reference', 'registry_digest', 'config_digest'))):
                raise ValueError('平台组件与原始构建清单不一致')
        existing = self.verify_images(selection, require_local=False)
        for role in ROLES:
            if role in existing:
                continue
            entry = selection[role]
            expected = {**entry, 'digest': entry['config_digest']}
            _check_local_reference(entry['reference'], expected)
            pinned = entry['reference'].rsplit(':', 1)[0] + '@' + entry['registry_digest']
            try:
                docker('pull', pinned, timeout=1800)
            except RuntimeError:
                self._load_release_bundle(release, folder)
                break
            image = json.loads(docker('image', 'inspect', pinned))[0]
            if not _local_image_matches(pinned, image, expected):
                raise ValueError('拉取镜像内容不匹配')
            docker('tag', pinned, entry['reference'])
        self.verify_images(selection)

    def _load_release_bundle(self, release: dict, folder: Path) -> None:
        if release['build_manifests']['control'] != release['build_manifests']['account']:
            raise ValueError('混合来源需按各自镜像摘要获取')
        bundle = release['bundle']
        destination = folder / bundle['name']
        if not destination.exists():
            temporary = folder / (bundle['name'] + '.partial')
            temporary.unlink(missing_ok=True)
            opener = build_opener(ProxyHandler({}), ReleaseRedirect())
            request = Request(f'{DOWNLOAD_ROOT}/{release["release"]}/{bundle["name"]}', headers={'User-Agent': 'vibebench-system-updater/1'})
            digest, total, deadline = hashlib.sha256(), 0, time.monotonic() + 1800
            try:
                with opener.open(request, timeout=15) as response, temporary.open('xb') as output:
                    os.fchmod(output.fileno(), 0o600)
                    while chunk := response.read1(1024 * 1024):
                        total += len(chunk)
                        if total > bundle['size'] or time.monotonic() > deadline:
                            raise ValueError('镜像包下载超过大小或时间限制')
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if total != bundle['size'] or digest.hexdigest() != bundle['sha256']:
                    raise ValueError('镜像包下载摘要不符')
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        load_bundle(folder / release['build_manifests']['control']['name'], destination)

    def capture(self, current: dict) -> dict:
        """冻结当前实际部署及身份，后续动作逐项对照。

        :param current: 当前安装记录。
        :return: 私有维护前证据。
        """
        self.values()
        images = self.verify_images(current['selection'])
        controls = self.controls()
        for item in controls.values():
            if not _container_image_matches(item['Image'], images['control']['Id'],
                    {**current['selection']['control'], 'digest': current['selection']['control']['config_digest']}):
                raise ValueError('实际控制服务与当前安装记录不符')
        evidence = self.request('orchestrator', '/internal/v3/system-updates/snapshot', {})
        return {'controls': {role: {'id': item['Id'], 'image_id': item['Image']} for role, item in controls.items()},
            'env_sha256': hashlib.sha256(safe_read(self.env, private=True)).hexdigest(),
            'metadata': self.metadata(), 'environments': evidence['environments']}

    def block(self, operation: dict) -> None:
        """原子发布本次维护门禁。

        :param operation: 已持久化的原操作及 epoch。
        :return: None。
        """
        current = read_gate(self.gate, self.policy['deployment'])
        if current['phase'] != 'idle' and (current['operation_id'] != operation['operation_id'] or current['epoch'] != operation['epoch']):
            raise ValueError('已有其他维护操作占有部署')
        atomic_json(self.gate / 'admission.json', {'schema_version': 1, 'deployment': self.policy['deployment'],
            'operation_id': operation['operation_id'], 'epoch': operation['epoch'], 'phase': 'blocked',
            'target_release': operation['target']['release'], 'revision': operation['revision'], 'created_at': operation['created_at']})

    def drained(self, operation: dict) -> dict:
        """取得同一 epoch 的双端接管和真实排空证明。

        :param operation: 本次冻结操作。
        :return: ready、阻塞项及环境快照。
        """
        runtime = self.request('orchestrator', '/internal/v3/system-updates/snapshot', {})
        gateway = self.request('gateway', '/admin/runtime/system-update/status')
        if any(value.get('phase') != 'blocked' or value.get('epoch') != operation['epoch'] for value in (gateway, runtime)):
            raise ValueError('部署维护接管代次不一致')
        return {'ready': gateway.get('active') == 0 and runtime.get('ready') is True,
            'blockers': (['网关仍有在途活动'] if gateway.get('active') else []) + runtime.get('blockers', []),
            'environments': runtime['environments']}

    def _compose(self, *arguments: str) -> None:
        for name in ('compose_file', 'override_file'):
            path = Path(self.policy[name])
            if hashlib.sha256(safe_read(path)).hexdigest() != self.policy[name + '_sha256']:
                raise ValueError('受信 Compose 模板已经变化')
        docker('compose', '--env-file', str(self.env), '-f', self.policy['compose_file'],
            '-f', self.policy['override_file'], *arguments, timeout=240)

    def _stage_selection(self, operation: dict, selected: dict) -> None:
        """仅切换两个控制服务，所有账号操作继续由目标运行时执行。

        :param operation: 已持久操作。
        :param selected: 目标安装记录。
        :return: None。
        """
        folder = self.root / 'operations' / operation['operation_id']
        folder.mkdir(mode=0o700, exist_ok=True)
        original = safe_read(self.env, private=True)
        if hashlib.sha256(original).hexdigest() != operation['before']['env_sha256']:
            raise ValueError('维护期间部署配置已经变化')
        actual = self.controls()
        if any(actual[role]['Id'] != old['id'] or actual[role]['Image'] != old['image_id']
                for role, old in operation['before']['controls'].items()):
            raise ValueError('维护期间控制容器身份已经变化')
        if not (folder / 'before.env').exists():
            atomic_text(folder / 'before.env', original.decode())
        updates = {'V3_RELEASE': selected['selection']['control']['release'],
            'V3_CONTROL_IMAGE': selected['selection']['control']['reference'],
            'V3_ACCOUNT_IMAGE': selected['selection']['account']['reference'],
            'V3_ACCOUNT_RELEASE': selected['selection']['account']['release'],
            'V3_SYSTEM_RELEASE': selected['release']['release'], 'V3_UPDATE_ROOT': str(self.root),
            'V3_RELEASE_MANIFEST': str(self.root / 'releases' / selected['release']['release'] / selected['release']['build_manifests']['control']['name'])}
        lines = []
        for line in original.decode().splitlines():
            key = line.partition('=')[0].strip()
            if key in updates:
                lines.append(key + '=' + shlex.quote(updates.pop(key)))
            else:
                lines.append(line)
        lines.extend(key + '=' + shlex.quote(value) for key, value in updates.items())
        candidate = '\n'.join(lines) + '\n'
        atomic_text(folder / 'candidate.env', candidate)
    def switch(self, operation: dict, selected: dict) -> None:
        """按冻结来源切换两个控制服务。:param operation: 持久操作。:param selected: 目标组合。:return: None。"""
        self._stage_selection(operation, selected)
        folder = self.root / 'operations' / operation['operation_id']
        candidate = safe_read(folder / 'candidate.env', private=True).decode()
        # 原门禁和排空证明仍被持有；通用 stop 会影响账号容器，所以仅指定控制服务。
        self._compose('stop', '-t', '30', 'orchestrator', 'gateway')
        atomic_text(self.env, candidate)
        self._compose('up', '-d', '--no-deps', 'gateway', 'orchestrator')

    def wait_controls(self, deadline: float) -> None:
        """等待实际双端服务可读，保留总截止期限。

        :param deadline: 单调截止。
        :return: None。
        """
        while time.monotonic() < deadline:
            try:
                self.request('gateway', '/admin/runtime/system-update/status', timeout=5)
                self.request('orchestrator', '/internal/v3/system-updates/snapshot', {}, timeout=5)
                return
            except (OSError, ValueError, RuntimeError, KeyError):
                time.sleep(0.5)
        raise TimeoutError('候选控制服务健康验收超时')

    def snapshot_databases(self, operation: dict, selected: dict, save) -> None:
        """停止写入服务后保存同组双库快照。

        :param operation: 持久维护操作。
        :param selected: 已验证目标组合。
        :param save: 原子持久回调。
        :return: None。
        """
        self._stage_selection(operation, selected)
        self._compose('stop', '-t', '30', 'orchestrator', 'gateway')
        if any(item['State']['Running'] for item in self.controls().values()):
            raise ValueError('数据库快照前控制服务仍在运行')
        gate = read_gate(self.gate, self.policy['deployment'])
        if gate['phase'] != 'blocked' or gate['epoch'] != operation['epoch'] or gate['operation_id'] != operation['operation_id']:
            raise ValueError('数据库快照维护归属失效')
        assert_quiescent(self.data)
        folder = self.root / 'operations' / operation['operation_id'] / 'database-snapshot'
        snapshot = create_snapshot(self.data, folder, self.policy['deployment'], operation)
        operation['database_snapshot'] = {'state': 'verified', 'completed_at': snapshot['completed_at'],
            'bytes': sum(item['size'] for item in snapshot['databases'].values())}
        save()

    def migrate_databases(self, operation: dict, plan: dict, save) -> None:
        """在精确候选镜像内离线执行固定维护入口。

        :param operation: 持久维护操作。
        :param plan: 已验签资产中的完整迁移计划。
        :param save: 每库执行前后的持久回调。
        :return: None。
        """
        image = self.verify_images(operation['selected']['selection'])['control']['Id']
        for name, entry in plan['databases'].items():
            gate = read_gate(self.gate, self.policy['deployment'])
            if gate['phase'] != 'blocked' or gate['epoch'] != operation['epoch'] or gate['operation_id'] != operation['operation_id']:
                raise ValueError('数据库迁移维护归属失效')
            status = operation.setdefault('database_migrations', {})
            status[name] = {'state': 'running', 'target_version': entry['version']}
            save()
            if name == 'bench':
                command = ['python3', '-m', 'database_migrations', 'apply']
                environment = []
                directory = self.data / 'bench'
            else:
                command = ['/app/claude-code-gateway', 'database-migrations', 'apply']
                environment = ['--env', 'DATABASE_DRIVER=sqlite', '--env', 'DATABASE_DSN=/data/gateway.sqlite']
                directory = self.data / 'gateway'
            # 参数和入口均由宿主固定；发行只提供已校验版本，不能改变命令或挂载。
            container_name = 'bench-database-' + operation['operation_id'] + '-' + name
            operation.setdefault('database_containers', {})[name] = container_name
            save()
            identifier = docker('create', '--name', container_name, '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
                '--security-opt', 'no-new-privileges', '--pids-limit', '64', '--memory', '512m',
                '--label', 'vibebench.product=v3', '--label', 'vibebench.deployment=' + self.policy['deployment'],
                '--label', 'vibebench.role=database-migration', '--label', 'vibebench.operation=' + operation['operation_id'], '--mount', f'type=bind,source={directory},target=/data',
                '--entrypoint', command[0], *environment, image, *command[1:],
                '--operation-id', operation['operation_id'], '--target-version', str(entry['version'])).strip()
            try:
                output = docker('start', '--attach', identifier, timeout=300)
                actual = json.loads(docker('inspect', identifier))[0]
                if actual['State']['Running'] or actual['State']['ExitCode'] != 0:
                    raise ValueError('离线数据库迁移进程执行失败')
            finally:
                self.stop_database_jobs(operation)
            result = strict_json(output.encode())
            if (result.get('database') != name or type(result.get('current_version')) is not int or result['current_version'] < entry['version']
                    or result.get('target_version') != entry['version']
                    or [(step.get('id'), step.get('checksum'), step.get('state')) for step in result.get('steps', [])]
                    != [(step['id'], step['checksum'], 'completed') for step in entry['steps']]):
                raise ValueError('数据库迁移实际回执与目标不符')
            status[name] = {'state': 'completed', 'target_version': entry['version']}
            save()

    def cleanup_database_snapshots(self, protected: set[str]) -> dict:
        """轮换当前部署的完成快照并保护活动操作。

        :param protected: 所有仍需恢复的操作 ID。
        :return: 脱敏轮换结果。
        """
        return rotate_snapshots(self.root / 'operations', self.policy['deployment'], protected)

    def capture_restore_bindings(self, operation: dict, folder: Path, save) -> None:
        """冻结本操作已重建角色的登记，避免数据快照恢复丢失其收口归属。

        :param operation: 具有精确环境维护意图的原操作。
        :param folder: 本操作双库快照目录。
        :param save: 副作用前的持久回调。
        :return: None；身份或代次异常保持维护阻断。
        """
        if 'environment_restore_bindings' in operation:
            return
        bindings = {}
        if operation.get('environment_intents'):
            with closing(sqlite3.connect((self.data / 'bench/db.sqlite').as_uri() + '?mode=ro', uri=True)) as current, closing(sqlite3.connect((folder / 'bench.sqlite').as_uri() + '?mode=ro&immutable=1', uri=True)) as original:
                current.row_factory = original.row_factory = sqlite3.Row
                for identifier, intent in operation['environment_intents'].items():
                    before = original.execute('SELECT * FROM account_environments WHERE environment_id=?', (identifier,)).fetchone()
                    after = current.execute('SELECT * FROM account_environments WHERE environment_id=?', (identifier,)).fetchone()
                    if (before is None or after is None or any(before[key] != after[key] for key in ENVIRONMENT_IDENTITY)
                            or type(after['generation']) is not int or not intent['generation'] <= after['generation'] <= intent['generation'] + 1
                            or before['generation'] != intent['generation']):
                        raise ValueError('数据库恢复的环境身份或角色代次出现外来变化')
                    bindings[identifier] = {'identity': {key: before[key] for key in ENVIRONMENT_IDENTITY},
                        'before': {key: before[key] for key in ENVIRONMENT_BINDINGS},
                        'current': {key: after[key] for key in ENVIRONMENT_BINDINGS}}
        operation['environment_restore_bindings'] = bindings
        save()

    def restore_environment_bindings(self, operation: dict, save) -> None:
        """在业务数据恢复后续接已登记角色，重复执行按精确前后值收口。

        :param operation: 已恢复双库且仍关闭准入的原操作。
        :param save: 完成回执的持久回调。
        :return: None；未知数据变化拒绝覆盖。
        """
        if operation.get('environment_restore_bindings_applied') or not operation.get('environment_restore_bindings'):
            return
        with closing(sqlite3.connect(self.data / 'bench/db.sqlite')) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN IMMEDIATE')
            for identifier, binding in operation['environment_restore_bindings'].items():
                actual = connection.execute('SELECT * FROM account_environments WHERE environment_id=?', (identifier,)).fetchone()
                if (actual is None or any(actual[key] != value for key, value in binding['identity'].items())
                        or {key: actual[key] for key in ENVIRONMENT_BINDINGS} not in (binding['before'], binding['current'])):
                    raise ValueError('恢复角色登记发现后来或外来的环境变化')
                # 业务字段保留快照值；仅续接原维护意图的角色，交由原运行时安全停止和重建。
                connection.execute('UPDATE account_environments SET generation=?,container_id=?,network_container_id=?,sender_container_id=?,state=?,isolation_version=? WHERE environment_id=?',
                    (*[binding['current'][key] for key in ENVIRONMENT_BINDINGS], identifier))
        operation['environment_restore_bindings_applied'] = True
        save()

    def stop_database_jobs(self, operation: dict) -> None:
        """收口本操作的离线进程，超时或重启后也不得遗留数据库写入者。

        :param operation: 已冻结的维护操作。
        :return: None；外来角色或归属不明立即阻断恢复。
        """
        identifiers = docker('ps', '-aq', '--filter', 'label=vibebench.product=v3',
            '--filter', 'label=vibebench.deployment=' + self.policy['deployment'],
            '--filter', 'label=vibebench.operation=' + operation['operation_id']).split()
        if not identifiers:
            return
        image = self.verify_images(operation['selected']['selection'])['control']['Id']
        for item in json.loads(docker('inspect', *identifiers)):
            labels = item['Config'].get('Labels') or {}
            name = item['Name'].lstrip('/')
            database = next((key for key in ('bench', 'gateway') if name == 'bench-database-' + operation['operation_id'] + '-' + key), None)
            if (database is None or labels.get('vibebench.role') != 'database-migration' or item['Image'] != image
                    or not any(mount.get('Source') == str(self.data / database) and mount.get('Destination') == '/data' for mount in item.get('Mounts', []))):
                raise ValueError('数据库维护进程归属或挂载不符')
            if item['State']['Running']:
                docker('stop', '-t', '5', item['Id'])
            docker('rm', item['Id'])

    def update_environments(self, operation: dict, selected: dict, save) -> None:
        """按原运行状态逐项维护需要变化的账号环境。

        :param operation: 具有逐项日志的操作。
        :param selected: 目标安装记录。
        :param save: 每一步副作用后的持久回调。
        :return: None。
        """
        if operation['original']['selection']['account']['content_sha256'] == selected['selection']['account']['content_sha256']:
            return
        for original in operation['before']['environments']:
            if not any(item['state'] == 'running' for item in original.get('roles', {}).values()):
                continue
            evidence = self.drained(operation)
            current = next(item for item in evidence['environments'] if item['environment_id'] == original['environment_id'])
            if current.get('origin', {}).get('release') == selected['selection']['account']['release']:
                continue
            if not evidence['ready']:
                raise ValueError('账号更新期间出现新的阻塞活动')
            operation.setdefault('environment_intents', {})[current['environment_id']] = {
                'generation': current['generation'], 'allowed_image_ids': list({
                    *[item['image_id'] for item in original.get('roles', {}).values()],
                    self.verify_images(selected['selection'])['account']['Id']})}
            save()
            result = self.request('orchestrator', '/internal/v3/system-updates/environment',
                {'operation_id': operation['operation_id'], 'epoch': operation['epoch'],
                    'environment_id': current['environment_id'], 'generation': current['generation'], 'action': 'rebuild'}, timeout=180)
            operation.setdefault('environment_results', {})[current['environment_id']] = result
            save()

    def health(self, operation: dict, selected: dict, *, restoring: bool = False) -> None:
        """核对镜像、身份、环境及明确允许的软件字段变化。

        :param operation: 维护前证据。
        :param selected: 应当实际运行的组合。
        :param restoring: 是否正在恢复原版。
        :return: None。
        """
        images = self.verify_images(selected['selection'])
        for control in self.controls().values():
            if control['State']['Status'] != 'running' or not _container_image_matches(control['Image'], images['control']['Id'],
                    {**selected['selection']['control'], 'digest': selected['selection']['control']['config_digest']}):
                raise ValueError('真实控制服务镜像或状态验收失败')
        after = self.metadata()
        before = operation['before']['metadata']
        if selected['release']['schema_version'] == 2:
            asset = selected['release']['migrations']['plan']
            raw = safe_read(self.root / 'releases' / selected['release']['release'] / asset['name'])
            if len(raw) != asset['size'] or hashlib.sha256(raw).hexdigest() != asset['sha256']:
                raise ValueError('健康验收的迁移计划摘要不符')
            plan = validate_migration_plan(strict_json(raw), selected['release'])
            for name, filename in (('bench', 'db.sqlite'), ('gateway', 'gateway.sqlite')):
                try:
                    with closing(sqlite3.connect('file:' + quote(str(self.data / name / filename), safe='/') + '?mode=ro', uri=True)) as connection, connection:
                        rows = connection.execute('SELECT migration_id,version,checksum FROM system_schema_migrations ORDER BY version').fetchall()
                except sqlite3.Error as error:
                    raise ValueError('候选数据库迁移台账未完成') from error
                expected = [(step['id'], step['version'], step['checksum']) for step in plan['databases'][name]['steps']]
                if rows[:len(expected)] != expected:
                    raise ValueError('候选数据库台账与受信计划不符')
        if after['identity_sha256'] != before['identity_sha256']:
            raise ValueError('更新改变了受保护账号身份或资源')
        for name in ('bench', 'gateway'):
            if (operation['original']['release']['data_compatibility'][name]['contract']
                    == selected['release']['data_compatibility'][name]['contract']
                    and before['database_schema'][name] != after['database_schema'][name]):
                raise ValueError('未声明数据迁移改变了数据库结构')
        operation['after'] = {'database_schema': after['database_schema'], 'identity_sha256': after['identity_sha256'],
            'data_contracts': {name: selected['release']['data_compatibility'][name]['contract'] for name in ('bench', 'gateway')}}
        same_contract = (operation['original']['release']['data_compatibility']['gateway']['contract']
            == selected['release']['data_compatibility']['gateway']['contract'])
        if (restoring or same_contract) and after['software'] != before['software']:
            self.restore_software(before['software'], after['software'])
        evidence = self.drained(operation)
        if not evidence['ready']:
            raise ValueError('更新验收存在未收口工作或未知证据')
        if operation['original']['selection']['account']['content_sha256'] == operation['selected']['selection']['account']['content_sha256']:
            for original in operation['before']['environments']:
                current = next(item for item in evidence['environments'] if item['environment_id'] == original['environment_id'])
                if current['generation'] != original['generation'] or current.get('roles') != original.get('roles'):
                    raise ValueError('兼容更新意外改变了账号容器或环境代次')

    def release(self, operation: dict) -> None:
        """只释放本操作持有的维护门禁。

        :param operation: 原操作身份。
        :return: None。
        """
        current = read_gate(self.gate, self.policy['deployment'])
        if current['phase'] != 'blocked' or current['operation_id'] != operation['operation_id'] or current['epoch'] != operation['epoch']:
            raise ValueError('维护门禁归属已经变化')
        atomic_json(self.gate / 'admission.json', {**current, 'phase': 'idle', 'operation_id': None, 'target_release': None})

    def abandon(self, operation: dict) -> None:
        """切换前取消或超时只核对原控制服务，允许原在途工作继续完成。

        :param operation: 持有原版环境摘要的操作。
        :return: None。
        """
        if hashlib.sha256(safe_read(self.env, private=True)).hexdigest() != operation['before']['env_sha256']:
            raise ValueError('取消维护时原配置已经变化')
        controls = self.controls()
        for role, original in operation['before']['controls'].items():
            actual = controls[role]
            if actual['Id'] != original['id'] or actual['Image'] != original['image_id'] or actual['State']['Status'] != 'running':
                raise ValueError('取消维护时原控制服务状态已经变化')
        self.release(operation)

    def committed(self, operation: dict) -> bool:
        """重启后核对已经提交的目标组合，按持久门禁收尾。

        :param operation: committing 阶段的操作。
        :return: 已提交版本可保持时为 True。
        """
        current = read_gate(self.gate, self.policy['deployment'])
        if current['epoch'] != operation['epoch']:
            return False
        images = self.verify_images(operation['selected']['selection'])
        if any(not _container_image_matches(item['Image'], images['control']['Id'],
                {**operation['selected']['selection']['control'], 'digest': operation['selected']['selection']['control']['config_digest']})
                for item in self.controls().values()):
            return False
        if current['phase'] == 'blocked':
            self.health(operation, operation['selected'])
            self.release(operation)
        return True

    def restore(self, operation: dict, save) -> None:
        """在持久门禁下恢复原控制组合及原运行账号环境。

        :param operation: 已冻结的原版及副作用。
        :param save: 逐项收口持久回调。
        :return: None。
        """
        folder = self.root / 'operations' / operation['operation_id']
        original = operation['original']
        # 释放门禁后的持久化故障也可能进入恢复；先重新接管并复核新接单，避免中断后来活动。
        released = read_gate(self.gate, self.policy['deployment'])['phase'] == 'idle'
        if released and not operation.get('release_started'):
            operation['release_started'] = True
            save()
        self.block(operation)
        if released:
            runtime = self.request('orchestrator', '/internal/v3/system-updates/snapshot', {})
            gateway = self.request('gateway', '/admin/runtime/system-update/status')
            if (runtime.get('active') != 0 or gateway.get('active') != 0
                    or any(item['blockers'] for item in runtime['environments']
                        if item['environment_id'] not in operation.get('environment_intents', {}))):
                raise ValueError('恢复前仍有在途工作或未知环境，门禁保持等待')
        self.verify_images(original['selection'])
        controls = self.controls(require_both=False)
        allowed = {selection['control']['config_digest'] for selection in (original['selection'], operation['selected']['selection'])}
        allowed.update(self.verify_images(selection)['control']['Id']
            for selection in (original['selection'], operation['selected']['selection']))
        if any(item['Image'] not in allowed for item in controls.values()):
            raise ValueError('恢复发现不属于本操作的控制服务')
        before = safe_read(folder / 'before.env', private=True)
        actual = safe_read(self.env, private=True)
        candidate = safe_read(folder / 'candidate.env', private=True)
        if actual not in (before, candidate):
            raise ValueError('恢复发现外部修改的部署配置')
        self.stop_database_jobs(operation)
        self._compose('stop', '-t', '30', 'orchestrator', 'gateway')
        if operation.get('database_snapshot') and not operation.get('release_started') and not operation.get('database_restored'):
            assert_quiescent(self.data)
            self.capture_restore_bindings(operation, folder / 'database-snapshot', save)
            operation['phase'] = 'restoring_data'
            save()
            restore_snapshot(self.data, folder / 'database-snapshot', self.policy['deployment'], operation, save)
            # 原程序启动后会合法写库；持久完成边界让恢复重启继续程序验收。
            operation['database_restored'] = True
            operation['phase'] = 'restoring'
            save()
        if operation.get('database_restored') and not operation.get('release_started'):
            self.restore_environment_bindings(operation, save)
        atomic_text(self.env, before.decode())
        self._compose('up', '-d', '--no-deps', 'gateway', 'orchestrator')
        self.wait_controls(time.monotonic() + 180)
        if original['selection']['account']['content_sha256'] != operation['selected']['selection']['account']['content_sha256']:
            # 已持久登记的重建意图允许收口本操作造成的部分角色，未知活动仍拒绝。
            for environment_id, intent in operation.get('environment_intents', {}).items():
                evidence = self.request('orchestrator', '/internal/v3/system-updates/snapshot', {})
                current = next(item for item in evidence['environments'] if item['environment_id'] == environment_id)
                result = self.request('orchestrator', '/internal/v3/system-updates/environment',
                    {'operation_id': operation['operation_id'], 'epoch': operation['epoch'],
                        'environment_id': environment_id, 'generation': current['generation'],
                        'action': 'restore', 'allowed_image_ids': intent['allowed_image_ids']}, timeout=180)
                operation.setdefault('environment_restored', {})[environment_id] = result
                save()
        self.health(operation, original, restoring=True)
        self.release(operation)

    def cleanup(self, current: dict, history: list[dict], active: list[dict]) -> dict:
        """按精确历史来源和所有容器引用定向清理，保留完整恢复集合。

        :param current: 当前实际安装。
        :param history: 最近在前的完整历史安装。
        :param active: 仍被恢复操作引用的安装。
        :return: 脱敏回收结果。
        """
        before = shutil.disk_usage(self.data).free
        protected = [current, *history[:2], *active]
        protected_refs = {item['reference'] for installation in protected for item in installation['selection'].values()}
        ids = docker('ps', '-aq').split()
        referenced = {item['Image'] for item in json.loads(docker('inspect', *ids))} if ids else set()
        removed, retained = [], []
        for installation in history[2:]:
            for role, entry in installation['selection'].items():
                reference = entry['reference']
                if reference in protected_refs or reference in removed:
                    continue
                try:
                    image = json.loads(docker('image', 'inspect', reference))[0]
                except RuntimeError:
                    continue
                labels = image['Config'].get('Labels') or {}
                if (image['Id'] in referenced or not _local_image_matches(reference, image, {**entry, 'digest': entry['config_digest']})
                        or labels.get('vibebench.product') != 'v3' or labels.get('vibebench.role') != role
                        or labels.get('vibebench.release') != entry['release']):
                    retained.append(reference)
                    continue
                expected_repository = reference.rsplit(':', 1)[0]
                references = [*(image.get('RepoTags') or []), *(image.get('RepoDigests') or [])]
                if any(value != reference and value != expected_repository + '@' + entry['registry_digest'] for value in references):
                    retained.append(reference)
                    continue
                # 最后一次引用复核紧邻删除；Docker 的引用保护继续生效。
                if docker('ps', '-aq', '--filter', 'ancestor=' + reference).strip():
                    retained.append(reference)
                    continue
                # Docker 删除最后一个 tag 时会同步移除对应 digest，重复删 digest 会将成功回收误报为失败。
                docker('image', 'rm', reference)
                removed.append(reference)
        return {'status': 'passed', 'removed': removed, 'retained': retained,
            'before_free_bytes': before, 'after_free_bytes': shutil.disk_usage(self.data).free}
