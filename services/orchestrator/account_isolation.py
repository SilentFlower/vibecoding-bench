"""固定账号三个 Docker 角色的配置与受控创建，不处理业务或凭据刷新。"""
import ipaddress
import json
import os
import secrets
import re
import socket
import stat
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from docker.types import Mount
from cpu_resources import default_cpu_limits, read_policy as read_cpu_policy

from account_update_identity import configured_release, image_origin, role_release, save_image_origin
from cli_scratchpad import SCRATCHPAD_STORE, prepare_scratchpad_mount, restore_cli_scratchpad

from native_kernel_upgrade import migrate_records
from native_capture_policy import capture_enabled
from native_criu_policy import restore_policy
from resource_budget import account_limits, isolated_account_limits, memory_bytes, scenario_account_limits, sender_pid_limit
from runtime_files import atomic_json, directory_fd
from system_profile import (COMPUTER_PROFILE_LABEL, COMPUTER_PROFILE_VERSION, SYSTEM_PROFILE_DIRECTORY,
    SYSTEM_PROFILE_LABEL, SYSTEM_PROFILE_VERSION)
from tui_managed_policy import DIRECT_ACCOUNT_PATH, DIRECT_DIRECTORY, MANAGED_MARKETPLACE_PATH, MANAGED_SETTINGS_PATH, POLICY_DIRECTORY


ISOLATION_VERSION = 2
ROLE_COLUMNS = {'cli': 'container_id', 'sender': 'sender_container_id', 'network': 'network_container_id'}
ROLE_LABELS = {'cli': 'account', 'sender': 'account-sender', 'network': 'account-network'}


def role_labels(runtime, row: dict, role: str) -> dict:
    """构造角色精确归属标签。

    :param runtime: 已初始化的 AccountRuntime。
    :param row: 持久环境行。
    :param role: 网络、CLI 或发送器角色。
    :return: Docker 标签。
    """
    return {**runtime._labels(row), 'vibebench.role': ROLE_LABELS[role],
        'vibebench.release': role_release(runtime, row), 'vibebench.isolation-version': str(ISOLATION_VERSION)}


def role_container(runtime, row: dict, role: str, allow_old_release: bool = False):
    """读取并严格核验本环境角色，拒绝误操作其他容器。

    :param runtime: AccountRuntime。
    :param row: 持久环境行。
    :param role: 角色名。
    :param allow_old_release: 仅显式停机/重建允许收口本部署旧批次实例。
    :return: 已核验 Docker 容器。
    """
    identifier = row.get(ROLE_COLUMNS[role])
    if not identifier:
        raise ValueError('账号隔离角色尚未登记，需要先对账')
    container = runtime.client.containers.get(identifier)
    if container.labels.get('vibebench.cluster-node') != getattr(runtime, 'node_key', None):
        raise ValueError('账号角色属于其他执行节点')
    expected = {**runtime._labels(row), 'vibebench.role': ROLE_LABELS[role],
        'vibebench.isolation-version': str(ISOLATION_VERSION)}
    if not allow_old_release:
        expected['vibebench.release'] = role_release(runtime, row)
        origin = image_origin(runtime, row)
        if origin and container.attrs.get('Image') != origin['image_id']:
            raise ValueError('账号角色实际镜像与原始来源不符')
    if any(container.labels.get(key) != value for key, value in expected.items()):
        raise ValueError('账号隔离角色归属、代次或镜像批次不匹配')
    return container


def _directory(path: Path, uid: int = 0, gid: int = 0, mode: int = 0o700) -> None:
    if path.is_symlink():
        raise ValueError('账号运行目录不能是符号链接')
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    os.chown(path, uid, gid)
    path.chmod(mode)


def tui_reservations(configuration: dict) -> dict | None:
    """计算已绑定账号的传输预留上限。@param configuration 网关的账号配置。@return 私有配置或空值。"""
    concurrency = configuration.get('concurrency')
    if type(concurrency) is not int or concurrency < 1:
        return None
    # 活跃响应和等候发送的预留均计数。每个 HTTP 槽允许再准备一轮，协议最多支持 64 项。
    return {'max_reservations': min(64, 2 * concurrency)}


def tui_host_memory(root: Path, fingerprint: dict, transport: dict | None, native: dict | None,
                    *, managed_oauth: bool = False) -> str | None:
    """核对部署者对本账号的本机 V2 授权并选择物理空间。@param root 账号根。@param fingerprint 冻结总预算。
    @param transport 当前预留配置。@param native 可并存的 V1 配置。
    @param managed_oauth 是否具备正式账号凭据模式。@return sender 的实际预算或关闭。
    """
    if not transport:
        return None
    provider = root / 'runtime/sender/tui-local-provider.json'
    try:
        entry = provider.lstat()
    except FileNotFoundError:
        data = root.parent.parent
        config = tui_node_provider(data, root.name)
        if config is None and not managed_oauth:
            return None
        entry = None
        if config is not None:
            provider.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(provider, config)
            os.chown(provider, 0, 1001, follow_symlinks=False)
            provider.chmod(0o640)
            entry = provider.lstat()
    if entry is not None and not (stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1 and entry.st_uid == 0
            and entry.st_gid == 1001 and stat.S_IMODE(entry.st_mode) in (0o440, 0o640)):
        raise ValueError('本机交互提供方配置必须由部署者所有且仅允许 sender 读取')
    if fingerprint['mem'] == 'unlimited':
        return 'unlimited'
    total, _ = account_limits(fingerprint['mem'])
    # 网络保留 256 MiB、CLI 保留 512 MiB。sender 的固定开销及每个 TUI 各规划 256 MiB。
    available_blocks = (total // (256 * 1024 ** 2)) - 3
    # 只有等待 Agent 的原轮能借一个额外驻留位，账号模型并发维持原值。
    blocks = min(available_blocks, 2 + transport['max_reservations'] // 2)
    if blocks < 2 and entry is None:
        # 已有 V1 配额可继续运行。V2 只有在账号剩余额度可启动交互进程时就绪。
        return None
    if native:
        # 切换后 sender 仍可沿用原有角色额度，V1 内核的独立配置保持生效。
        native_mib = native['memory_mib']
        target = max(native_mib, blocks * 256) if blocks >= 2 else native_mib
        return f'{target}m'
    previous = fingerprint.get('native_sender_memory')
    if previous and memory_bytes(previous) >= 512 * 1024 ** 2:
        return previous
    if blocks < 2:
        raise ValueError('账号内存不足以同时容纳原版交互进程、固定 CLI 和网络角色')
    return f'{blocks * 256}m'


def tui_node_provider(data: Path, environment_id: str) -> dict | None:
    """读取目标节点独立配置。@param data 私有数据根。@param environment_id 原环境。@return 本机提供方配置或空。"""
    if not re.fullmatch(r'[a-f0-9]{32}', environment_id):
        return None
    try:
        directory = directory_fd(data / 'tui-local-providers')
    except FileNotFoundError:
        return None
    try:
        status = os.fstat(directory)
        if status.st_uid != 0 or stat.S_IMODE(status.st_mode) != 0o700:
            raise ValueError('节点 V2 提供方目录权限无效')
        try:
            fd = os.open(environment_id + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, 'rb') as stream:
            status = os.fstat(stream.fileno())
            if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1 or status.st_uid != 0 or stat.S_IMODE(status.st_mode) != 0o600:
                raise ValueError('节点 V2 提供方配置归属无效')
            raw = stream.read(4097)
            if len(raw) > 4096:
                raise ValueError('节点 V2 提供方配置大小无效')
            value = json.loads(raw)
        if not isinstance(value, dict) or set(value) != {'base_url', 'local_bearer'}:
            raise ValueError('节点 V2 提供方格式无效')
        if not isinstance(value['base_url'], str):
            raise ValueError('节点 V2 提供方地址无效')
        target = urlsplit(value['base_url'])
        bearer = value['local_bearer']
        if (target.scheme != 'http' or not target.hostname or not ipaddress.ip_address(target.hostname).is_loopback
                or target.username is not None or target.password is not None or target.path not in ('', '/')
                or target.query or target.fragment or not target.port or not isinstance(bearer, str)
                or not bearer or any(not 33 <= ord(char) <= 126 for char in bearer)):
            raise ValueError('节点 V2 提供方必须是带独立口令的本机回环地址')
        return value
    finally:
        os.close(directory)


def create_environment(runtime, row: dict, account: dict, name: str, write_json) -> None:
    """按网络就绪、业务启动的顺序创建三个角色，逐个登记以便中断恢复。

    :param runtime: 已持有环境和容量锁的 AccountRuntime。
    :param row: 原环境行；本函数只更新实例及代次。
    :param account: 账号与原上游代理配置。
    :param name: 与原发送桥一致的受控 DNS 名。
    :param write_json: 原子 JSON 发布函数。
    :return: None；失败保留登记并停止本代已创建实例。
    """
    root = runtime._root(row)
    fingerprint = json.loads(row['fingerprint_json'])
    native = account.get('native_sender')
    agy = account.get('agy_sender')
    if native and agy:
        raise ValueError('同一账号环境只能采用一个平台内核')
    if native:
        migrate_records(root, int(account.get('cc2api_account_id') or 0), reconciled=account.get('native_migration') is True)
    execution = agy or native
    tui_budget = account.get('tui_host_memory')
    tui_policy = account.get('tui_managed_policy')
    execution_budget = (('unlimited' if execution['memory_mib'] == 0 else str(execution['memory_mib']) + 'm')
                        if execution else None)
    limits = isolated_account_limits(fingerprint['mem'], fingerprint.get('swap', '0'), tui_budget or execution_budget)
    layout_path = root / 'runtime/project-review-layout.json'
    review_layout = json.loads(layout_path.read_text()) if layout_path.is_file() else None
    if review_layout:
        expected_limits = scenario_account_limits(fingerprint['mem'], fingerprint.get('swap', '0'), fingerprint.get('native_sender_memory'))
        if review_layout.get('limits') != {key: list(value) for key, value in expected_limits.items()}:
            raise ValueError('冻结评审资源布局与原账号预算不符')
        limits = expected_limits
    proxy = runtime._proxy(account)
    parsed = urlsplit(proxy)
    if not parsed.hostname:
        raise ValueError('隔离账号必须配置上游代理')
    try:
        address = str(ipaddress.IPv4Address(parsed.hostname))
    except ipaddress.AddressValueError:
        address = socket.getaddrinfo(parsed.hostname, parsed.port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    managers = []
    network_info = runtime.client.networks.get(runtime.network).attrs
    for configuration in network_info.get('IPAM', {}).get('Config') or []:
        if configuration.get('Gateway'):
            managers.append(str(ipaddress.IPv4Address(configuration['Gateway'])))
    for container in runtime.client.containers.list(filters={'label': [
            'vibebench.product=v3', f'vibebench.deployment={runtime.deployment}']}):
        if container.labels.get('vibebench.role') not in ('orchestrator', 'gateway', 'node-control'):
            continue
        manager = container.attrs.get('NetworkSettings', {}).get('Networks', {}).get(runtime.network, {}).get('IPAddress')
        if manager:
            managers.append(str(ipaddress.IPv4Address(manager)))
    if not managers:
        raise ValueError('无法核验管理端网络来源，拒绝启动账号')
    paths = {role: root / 'runtime' / role for role in ROLE_COLUMNS}
    for role, path in paths.items():
        _directory(path, 0, 1000 if role == 'cli' else 0, 0o750 if role == 'cli' else 0o700)
    _directory(paths['sender'], 0, 1001, 0o750)
    for relative in ('runtime/drivers', 'runtime/runs', 'runtime/jobs'):
        _directory(root / relative, 0, 1000, 0o750)
    _directory(root / 'public-ca', 0, 0, 0o755)
    runtime._adopt_sender_evidence(row)
    _directory(root / 'runtime/access', 0, 1000, 0o750)
    _directory(root / 'runtime/empty', 0, 0, 0o555)
    machine = root / 'runtime' / 'machine-id'
    machine.write_text(fingerprint['machine_id'] + '\n')
    machine.chmod(0o444)
    resolver = root / 'runtime' / 'resolv.conf'
    resolver.write_text('nameserver 127.0.0.1\noptions timeout:2 attempts:2\n')
    resolver.chmod(0o444)
    generation = int(row['generation']) + 1
    runtime._update(row, generation=generation, state='starting', isolation_version=ISOLATION_VERSION)
    save_image_origin(runtime, row)
    binding = {'account_id': int(account.get('cc2api_account_id') or 0), 'environment_id': row['environment_id'],
        'generation': generation, 'endpoint': f'http://{name}:8091',
        'secret': secrets.token_hex(32), 'release_id': configured_release(runtime)}
    userinfo = parsed.netloc.rsplit('@', 1)[0] + '@' if '@' in parsed.netloc else ''
    resolved_proxy = urlunsplit((parsed.scheme, f'{userinfo}{address}:{parsed.port}', parsed.path, parsed.query, ''))
    image_labels = runtime.client.images.get(runtime.image).attrs['Config'].get('Labels') or {}
    tui_socket = not agy and image_labels.get('vibebench.tui-sender-protocol') == '1'
    if tui_socket:
        _directory(paths['sender'] / 'tui-v2', 1001, 1001, 0o700)
    observer_protocol = 1 if native and image_labels.get('vibebench.native-tls-observer') == '1' else None
    restore_label = 'vibebench.agy-criu' if agy else 'vibebench.native-criu'
    restore_installed = image_labels.get(restore_label) == '1'
    restore = restore_policy(execution, fingerprint, restore_installed)
    sender_file = paths['sender'] / 'sender.json'
    write_json(sender_file, {'binding': binding, 'proxy_url': resolved_proxy, 'proxy_source': proxy,
        **({'tui_v2': account['tui_transport']} if tui_socket and account.get('tui_transport') else {}),
        **({'tui_host_memory': tui_budget} if tui_budget else {}),
        **({'tui_managed_oauth': True} if account.get('tui_managed_oauth') else {}),
        **({'tui_managed_policy': tui_policy} if tui_policy else {}),
        **({'tui_direct': True} if account.get('tui_direct') else {}),
        'native': native, 'agy': agy, 'native_capture_dir': ('/flows/api/agy-prepared' if agy else '/flows/api/cc-prepared') if (execution or tui_budget) and capture_enabled(fingerprint) else None,
        'native_tls_observer_protocol': observer_protocol,
        'native_criu_enabled': restore['eligible'], 'native_criu_reason': restore['reason'],
        'native_criu_protocol': 1 if execution and restore_installed else None,
        'allowed_origin': 'https://cloudcode-pa.googleapis.com' if agy else 'https://api.anthropic.com', 'evidence_file': '/flows/api/observations.jsonl', 'quota_identity': ''}, 0o640)
    os.chown(sender_file, 0, 1001)
    write_json(paths['network'] / 'context.json', {'NETWORK_INSPECTION_MODE': 'passthrough', 'QUOTA_SOURCE': ''})
    (paths['network'] / 'ready').unlink(missing_ok=True)
    host_root = runtime.host_data / root.relative_to(runtime.data)

    def mounts(entries):
        return {str(host_root / source): {'bind': destination, 'mode': mode} for source, destination, mode in entries}

    common_files = [('runtime/machine-id', '/etc/machine-id', 'ro'), ('runtime/resolv.conf', '/etc/resolv.conf', 'ro')]
    # 同一个宿主源不能在 dict 中重复作为键，machine-id 的第二个目标使用 Docker mounts。
    machine_mount = Mount('/var/lib/dbus/machine-id', str(host_root / 'runtime/machine-id'), type='bind', read_only=True)
    default_cpus = default_cpu_limits()
    cpu_policy = read_cpu_policy(runtime, row)
    created = []

    def launch(role, **options):
        memory, total = limits[role]
        role_pids = sender_pid_limit(execution['max_workers'], agy=bool(agy)) if role == 'sender' and execution else 512 if role == 'cli' else 128
        if role == 'sender' and tui_budget:
            physical = max(1, account['tui_transport']['max_reservations'] // 2)
            if memory:
                physical = min(physical + 1, max(0, memory // (256 * 1024 ** 2) - 1))
            role_pids = max(role_pids, sender_pid_limit(physical))
        options.update(name=name if role == 'network' else name + '-' + role,
            labels=role_labels(runtime, row, role), detach=True, auto_remove=False, read_only=True,
            mem_limit=memory, memswap_limit=total, nano_cpus=default_cpus[role],
            pids_limit=role_pids, security_opt=options.pop('security_opt', ['no-new-privileges:true']),
            log_config={'type': 'json-file', 'config': {'max-size': '10m', 'max-file': '3'}},
            mounts=[machine_mount, *options.pop('mounts', [])])
        if role == 'cli' and review_layout:
            options.update(nano_cpus=review_layout['cli_nano_cpus'], pids_limit=384)
            options['labels']['vibebench.review-layout'] = '1'
            options['tmpfs']['/tmp'] = 'rw,noexec,nosuid,nodev,size=64m,mode=1777'
        if cpu_policy:
            options['nano_cpus'] = cpu_policy['nano_cpus'][role]
        if role == 'cli':
            options['labels'][SYSTEM_PROFILE_LABEL] = str(SYSTEM_PROFILE_VERSION)
            options['labels'][COMPUTER_PROFILE_LABEL] = str(COMPUTER_PROFILE_VERSION)
        container = runtime.client.containers.run(runtime.image, **options)
        created.append(container)
        runtime._update(row, **{ROLE_COLUMNS[role]: container.id})
        return container

    environment = {'V3_ACCOUNT_ROLE': 'network', 'V3_ISOLATION_VERSION': str(ISOLATION_VERSION),
        'V3_MACHINE_ID': fingerprint['machine_id'], 'HOME': '/root', 'TZ': fingerprint['tz'],
        'LANG': fingerprint['lang'], 'LC_ALL': fingerprint['lang'],
        'V3_MANAGEMENT_ADDRESSES': json.dumps(sorted(set(managers))),
        'PROXYCHAINS_CONF_FILE': '/run/v3/proxychains.conf', 'V3_HEV_CONFIG': '/run/v3/hev.yml',
        'V3_UNBOUND_CONFIG': '/run/v3/unbound.conf', 'DNS_READY_HOST': os.environ.get('DNS_READY_HOST', 'example.com'),
        'UPSTREAM_PROXY_SCHEME': account.get('upstream_proxy_scheme') or 'socks5',
        'UPSTREAM_SOCKS5_HOST': address, 'UPSTREAM_SOCKS5_PORT': str(parsed.port),
        'UPSTREAM_SOCKS5_USER': account.get('upstream_socks5_user') or '',
        'UPSTREAM_SOCKS5_PASS': account.get('upstream_socks5_pass') or ''}
    try:
        image_labels = runtime.client.images.get(runtime.image).attrs['Config'].get('Labels') or {}
        if image_labels.get(SYSTEM_PROFILE_LABEL) != str(SYSTEM_PROFILE_VERSION):
            raise ValueError('账号镜像缺少系统画像支持，请使用同批新镜像')
        if image_labels.get(COMPUTER_PROFILE_LABEL) != str(COMPUTER_PROFILE_VERSION):
            raise ValueError('账号镜像缺少计算机画像支持，请使用同批新镜像')
        network_mounts = mounts([*common_files, ('runtime/network', '/run/v3', 'rw'),
            ('public-ca', '/etc/mitm', 'rw'), ('ca', '/ca', 'rw'), ('cli', '/cli', 'rw'),
            ('flows', '/flows', 'rw'), ('runtime/empty', '/flows/api', 'ro'), ('controls', '/controls', 'rw')])
        if account.get('id') is not None:
            quota = runtime.data / 'quota' / str(int(account['id']))
            _directory(quota)
            network_mounts[str(runtime.host_data / quota.relative_to(runtime.data))] = {
                'bind': '/quota-accounts/' + str(account['id']), 'mode': 'ro'}
        # Docker 29 已忽略容器顶层 MAC，必须在实际网络端点上指定才能保持原画像。
        network = launch('network', network=runtime.network, hostname=fingerprint['hostname'],
            networking_config={runtime.network: runtime.client.api.create_endpoint_config(mac_address=fingerprint['mac'])},
            cap_add=['NET_ADMIN'], devices=['/dev/net/tun:/dev/net/tun'], environment=environment,
            volumes=network_mounts,
            tmpfs={'/tmp': 'rw,nosuid,nodev,size=64m', '/root': 'rw,nosuid,nodev,size=64m', '/var/log': 'rw,nosuid,nodev,size=32m'})
        deadline = time.monotonic() + 120
        while network.exec_run(['test', '-f', '/run/v3/ready']).exit_code:
            network.reload()
            if network.status != 'running' or time.monotonic() > deadline:
                raise ValueError('账号隔离网络未就绪，业务未启动')
            time.sleep(0.25)
        runtime.prepare_system_profile(row, network)
        base = {'network_mode': 'container:' + network.id, 'cap_drop': ['ALL']}
        scratchpad = []
        if (image_labels.get('vibebench.cli-scratchpad-protocol') == '1'
                or (root / SCRATCHPAD_STORE).exists() or (root / SCRATCHPAD_STORE).is_symlink()):
            scratchpad_mount = prepare_scratchpad_mount(runtime, row)
            if scratchpad_mount is not None:
                scratchpad.append(scratchpad_mount)
        cli = launch('cli', **base, user='1000:1000', entrypoint=['python3', '-I', '/usr/local/bin/v3-cli-control'], command=['idle'],
            environment={'HOME': '/home/node', 'TZ': fingerprint['tz'],
                'LANG': fingerprint['lang'], 'LC_ALL': fingerprint['lang'], 'SHELL': '/bin/bash'},
            volumes=mounts([*common_files,
                ('runtime/system-profile', SYSTEM_PROFILE_DIRECTORY, 'ro'),
                ('runtime/system-profile/cpuinfo', '/proc/cpuinfo', 'ro'),
                ('runtime/system-profile/ld.so.preload', '/etc/ld.so.preload', 'ro'),
                ('home', '/home/node', 'rw'), ('projects', '/home/node/projects', 'rw'),
                ('cli', '/cli', 'ro'), ('public-ca', '/etc/mitm', 'ro'), ('runtime/cli', '/run/v3', 'rw'),
                ('runtime/drivers', '/run/v3/drivers', 'ro'), ('runtime/runs', '/run/v3/runs', 'rw'),
                ('runtime/jobs', '/run/v3/jobs', 'rw'), ('runtime/access', '/run/v3/access', 'ro'),
                ('flows', '/flows', 'rw'), ('runtime/empty', '/flows/api', 'ro'), ('controls', '/controls', 'ro')]),
            tmpfs={'/tmp': 'rw,noexec,nosuid,nodev,size=128m,mode=1777'}, mounts=scratchpad)
        restore_cli_scratchpad(runtime, row, cli, fresh=True)
        runtime.check_system_profile(row, cli)
        _directory(root / 'runtime/native', 1001, 1001, 0o700)
        sender_mounts = mounts([*common_files, ('runtime/sender', '/run/v3', 'ro'), ('flows/api', '/flows/api', 'rw'), ('runtime/native', '/native', 'rw')])
        if tui_socket:
            # 只将事件 socket 子目录挂成可写，配置与绑定仍由控制端发布。
            sender_mounts[str(host_root / 'runtime/sender/tui-v2')] = {'bind': '/run/v3/tui-v2', 'mode': 'rw'}
        sender_env = {'V3_SENDER_CONFIG': '/run/v3/sender.json', 'TOKIO_WORKER_THREADS': '2'}
        if tui_budget:
            # 安装器原子替换版本子目录，挂其父级才能在运行中看到已验收的新 inode。
            # sender 不挂 CLI HOME、项目卷或登录凭据目录；运行准备由原生会话单独核对。
            sender_mounts[str(host_root / 'cli')] = {'bind': '/cli', 'mode': 'ro'}
            sender_env['V3_TUI_SESSION_HOST'] = '1'
            if account.get('tui_managed_oauth'):
                sender_env['V3_TUI_MANAGED_OAUTH'] = '1'
                if tui_policy:
                    policy_root = runtime.host_data / POLICY_DIRECTORY / row['environment_id']
                    sender_mounts[str(policy_root / 'managed-settings.json')] = {'bind': MANAGED_SETTINGS_PATH, 'mode': 'ro'}
                    sender_mounts[str(policy_root / 'marketplace')] = {'bind': MANAGED_MARKETPLACE_PATH, 'mode': 'ro'}
                    sender_env['V3_TUI_MANAGED_POLICY'] = '1'
                    if account.get('tui_direct'):
                        sender_env['V3_TUI_DIRECT'] = '1'
                        sender_mounts[str(runtime.host_data / DIRECT_DIRECTORY)] = {'bind': DIRECT_ACCOUNT_PATH, 'mode': 'ro'}
            else:
                sender_env['V3_TUI_LOCAL_PROVIDER_CONFIG'] = '/run/v3/tui-local-provider.json'
        sender_env['CCRB_CRIU_REASON'] = restore['reason'] or ''
        verification = root / 'runtime/verification-ca.der'
        if verification.is_file():
            # 父目录按只读挂载，runc 不能在其中创建嵌套 bind 的目标文件。
            (paths['sender'] / 'verification-ca.der').touch(mode=0o444)
            sender_mounts[str(host_root / 'runtime/verification-ca.der')] = {'bind': '/run/v3/verification-ca.der', 'mode': 'ro'}
        sender_options = {'user': '1001:1001', 'entrypoint': ['/usr/local/bin/account-sender'],
            'tmpfs': {'/tmp': 'rw,noexec,nosuid,nodev,size=16m,mode=1777'}}
        if native and capture_enabled(fingerprint) and image_labels.get('vibebench.native-tls-observer') == '1':
            # 可信入口持有加载权限；业务子进程由固定启动器清零能力后降权。
            profile = json.loads(Path(__file__).with_name('native_tls_seccomp.json').read_text())
            sender_env['CCRB_TLS_OBSERVER'] = '/opt/ccrb-tls-observer/client.py'
            sender_options.update(user='0:0', entrypoint=['/usr/local/bin/python3', '-E', '-s', '/opt/ccrb-tls-observer/broker.py'],
                cap_add=['SYS_ADMIN', 'SETUID', 'SETGID'],
                security_opt=['no-new-privileges:true', 'seccomp=' + json.dumps(profile, separators=(',', ':'))])
            sender_options['tmpfs']['/run/ccrb-observer'] = 'rw,noexec,nosuid,nodev,size=1m,mode=0750'
        if restore['eligible']:
            # 控制器单独持有恢复权限；固定C入口为sender安装原业务过滤器并清零能力。
            _directory(root / 'runtime/native-criu', 0, 0, 0o700)
            sender_mounts[str(host_root / 'runtime/native-criu')] = {'bind': '/var/lib/ccrb-criu', 'mode': 'rw'}
            sender_options.update(user='0:0', entrypoint=['/usr/local/bin/python3', '-E', '-s', '/opt/ccrb-criu/entry.py'],
                cap_add=['CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'KILL', 'SETUID', 'SETGID', 'SETPCAP', 'NET_ADMIN', 'SYS_CHROOT', 'SYS_PTRACE', 'SYS_ADMIN', 'SYS_RESOURCE', 'SYS_TIME'],
                security_opt=['no-new-privileges:true', 'seccomp=unconfined'])
            sender_options['tmpfs']['/run/ccrb-criu'] = 'rw,noexec,nosuid,nodev,size=1m,mode=0750'
        launch('sender', **base, **sender_options, environment=sender_env, volumes=sender_mounts)
    except Exception:
        for container in reversed(created):
            try:
                container.stop(timeout=5)
            except Exception:
                # 保留实例和登记供后续显式对账，不能假报已回滚。
                pass
        runtime._update(row, state='reconcile')
        raise
