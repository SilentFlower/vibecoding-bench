"""固定账号三个 Docker 角色的配置与受控创建，不处理业务或凭据刷新。"""
import ipaddress
import json
import os
import secrets
import socket
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from docker.types import Mount

from resource_budget import isolated_account_limits
from system_profile import SYSTEM_PROFILE_DIRECTORY, SYSTEM_PROFILE_LABEL, SYSTEM_PROFILE_VERSION


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
        'vibebench.release': runtime.release_id, 'vibebench.isolation-version': str(ISOLATION_VERSION)}


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
    expected = role_labels(runtime, row, role)
    if allow_old_release:
        expected.pop('vibebench.release')
    if any(container.labels.get(key) != value for key, value in expected.items()):
        raise ValueError('账号隔离角色归属、代次或镜像批次不匹配')
    return container


def _directory(path: Path, uid: int = 0, gid: int = 0, mode: int = 0o700) -> None:
    if path.is_symlink():
        raise ValueError('账号运行目录不能是符号链接')
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    os.chown(path, uid, gid)
    path.chmod(mode)


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
    limits = isolated_account_limits(fingerprint['mem'], fingerprint.get('swap', '0'))
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
        if container.labels.get('vibebench.role') not in ('orchestrator', 'gateway'):
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
    binding = {'account_id': int(account.get('cc2api_account_id') or 0), 'environment_id': row['environment_id'],
        'generation': generation, 'endpoint': f'http://{name}:8091',
        'secret': secrets.token_hex(32), 'release_id': runtime.release_id}
    userinfo = parsed.netloc.rsplit('@', 1)[0] + '@' if '@' in parsed.netloc else ''
    resolved_proxy = urlunsplit((parsed.scheme, f'{userinfo}{address}:{parsed.port}', parsed.path, parsed.query, ''))
    sender_file = paths['sender'] / 'sender.json'
    write_json(sender_file, {'binding': binding, 'proxy_url': resolved_proxy, 'proxy_source': proxy,
        'allowed_origin': 'https://api.anthropic.com', 'evidence_file': '/flows/api/observations.jsonl', 'quota_identity': ''}, 0o640)
    os.chown(sender_file, 0, 1001)
    write_json(paths['network'] / 'context.json', {'NETWORK_INSPECTION_MODE': 'passthrough', 'QUOTA_SOURCE': ''})
    (paths['network'] / 'ready').unlink(missing_ok=True)
    host_root = runtime.host_data / root.relative_to(runtime.data)

    def mounts(entries):
        return {str(host_root / source): {'bind': destination, 'mode': mode} for source, destination, mode in entries}

    common_files = [('runtime/machine-id', '/etc/machine-id', 'ro'), ('runtime/resolv.conf', '/etc/resolv.conf', 'ro')]
    # 同一个宿主源不能在 dict 中重复作为键，machine-id 的第二个目标使用 Docker mounts。
    machine_mount = Mount('/var/lib/dbus/machine-id', str(host_root / 'runtime/machine-id'), type='bind', read_only=True)
    cpu = int(float(os.environ.get('V3_ACCOUNT_CPUS', '2')) * 1_000_000_000)
    created = []

    def launch(role, **options):
        memory, total = limits[role]
        options.update(name=name if role == 'network' else name + '-' + role,
            labels=role_labels(runtime, row, role), detach=True, auto_remove=False, read_only=True,
            mem_limit=memory, memswap_limit=total, nano_cpus=cpu * (6 if role == 'cli' else 1) // 8,
            pids_limit=512 if role == 'cli' else 128, security_opt=['no-new-privileges:true'],
            log_config={'type': 'json-file', 'config': {'max-size': '10m', 'max-file': '3'}}, mounts=[machine_mount])
        if role == 'cli':
            options['labels'][SYSTEM_PROFILE_LABEL] = str(SYSTEM_PROFILE_VERSION)
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
            tmpfs={'/tmp': 'rw,noexec,nosuid,nodev,size=128m,mode=1777'})
        runtime.check_system_profile(row, cli)
        sender_mounts = mounts([*common_files, ('runtime/sender', '/run/v3', 'ro'), ('flows/api', '/flows/api', 'rw')])
        verification = root / 'runtime/verification-ca.der'
        if verification.is_file():
            # 父目录按只读挂载，runc 不能在其中创建嵌套 bind 的目标文件。
            (paths['sender'] / 'verification-ca.der').touch(mode=0o444)
            sender_mounts[str(host_root / 'runtime/verification-ca.der')] = {'bind': '/run/v3/verification-ca.der', 'mode': 'ro'}
        launch('sender', **base, user='1001:1001', entrypoint=['/usr/local/bin/account-sender'],
            environment={'V3_SENDER_CONFIG': '/run/v3/sender.json', 'TOKIO_WORKER_THREADS': '2'},
            volumes=sender_mounts, tmpfs={'/tmp': 'rw,noexec,nosuid,nodev,size=16m,mode=1777'})
    except Exception:
        for container in reversed(created):
            try:
                container.stop(timeout=5)
            except Exception:
                # 保留实例和登记供后续显式对账，不能假报已回滚。
                pass
        runtime._update(row, state='reconcile')
        raise
