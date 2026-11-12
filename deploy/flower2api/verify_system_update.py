#!/usr/bin/env python3
"""使用独立 Docker 部署、合成签名和真实私有管理桥验证平台更新。"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import io
import ipaddress
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import traceback
from contextlib import closing
from pathlib import Path
from source_layout import source_path
from urllib.error import HTTPError

import docker
import requests

from install_system_updater import finalize_installation, prepare_installation
from manage import REPO, _image_config_digest
from runtime_files import atomic_json, atomic_text
from system_release import create_index, create_release, sign_file
from system_update_contract import safe_read, strict_json
from system_update_gate import read_gate
from system_update_host import HostDeployment
from system_updater import SystemUpdater, UpdateHTTPHandler, UpdateServer
from verify_forwarding import certificates
from verify_database_compatibility import verify as verify_database_compatibility
from upgrade_system_updater import upgrade


def wait_for(read, description: str, timeout: int = 240):
    """等待真实事实满足条件。:param read: 有界读取。:param description: 超时原因。:param timeout: 秒。@return 事实。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = read()
            if result:
                return result
        except (requests.RequestException, OSError, ValueError, KeyError):
            pass
        time.sleep(0.3)
    raise AssertionError(description)


def verify_retention(output: Path) -> dict:
    """用真实 Docker 引用定向验证保留集合和最后一个 tag 的删除行为。

    :param output: 独立脱敏证据目录。
    :return: 实际回收结果。
    """
    output.mkdir(parents=True, exist_ok=True)
    client, references, pin = docker.from_env(), [], None
    installations = []
    counter = int(uuid.uuid4().hex[:12], 16)
    with tempfile.TemporaryDirectory(prefix='v3-update-retention-') as temporary:
        root = Path(temporary)
        try:
            for index in range(4):
                release, selection = f'ci-{counter + index}-1', {}
                for role in ('control', 'account'):
                    reference = f'ghcr.io/silentflower/vibebench-v3-{role}:v3-{release}'
                    references.append(reference)
                    (root / 'Dockerfile').write_text('FROM scratch\n'
                        f'LABEL vibebench.product="v3" vibebench.role="{role}" vibebench.release="{release}" vibebench.verification="retention"\n')
                    subprocess.run(['docker', 'build', '-t', reference, str(root)], check=True, capture_output=True)
                    image = client.images.get(reference)
                    selection[role] = {'reference': reference, 'release': release, 'registry_digest': image.id,
                        'config_digest': _image_config_digest(reference)}
                installations.append({'selection': selection})
            current, history = installations[3], list(reversed(installations[:3]))
            old = installations[0]['selection']['control']['reference']
            pin = client.containers.create(old, ['/synthetic-never-start'], network_mode='none',
                labels={'vibebench.verification': 'system-update-retention'})
            host = HostDeployment({'state_root': str(root / 'updates'), 'data_root': str(root), 'env_file': str(root / 'v3.env')})
            first = host.cleanup(current, history, [])
            assert old in first['retained'], first
            assert installations[0]['selection']['account']['reference'] in first['removed'], first
            pin.remove()
            pin = None
            second = host.cleanup(current, history, [])
            assert old in second['removed'], second
            for installation in [current, *history[:2]]:
                for entry in installation['selection'].values():
                    client.images.get(entry['reference'])
            report = {'passed': True, 'scene': '真实容器引用保护、当前及最近两个完整组合保留、精确旧镜像回收',
                'with_container_reference': first, 'after_container_removed': second, 'real_model_calls': 0}
            atomic_json(output / 'results.json', report)
            return report
        finally:
            if pin is not None:
                pin.remove()
            for reference in references:
                try:
                    client.images.remove(reference)
                except docker.errors.ImageNotFound:
                    pass
            client.close()


def worker(policy_path: Path, fault: str | None) -> None:
    """在独立进程执行正式状态机，以明确测试入口注入一次故障。

    :param policy_path: 仅本次隔离策略。
    :param fault: health 或 switched-crash。
    :return: 运行至进程停止。
    """
    policy = strict_json(safe_read(policy_path, private=True))
    root = Path(policy['state_root'])
    descriptor = os.open(root / 'service.lock', os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    class FaultHost(HostDeployment):
        """正式宿主动作之后注入故障，保留真实持久现场。"""

        def request(self, service, path, body=None, timeout=15):
            """保留隔离夹具的 HTTP 失败证据。:param service: 服务。:param path: 路径。:param body: 载荷。:param timeout: 秒。@return 实际响应。"""
            try:
                return super().request(service, path, body, timeout)
            except HTTPError as error:
                logs = {}
                for role, container in self.controls(require_both=False).items():
                    captured = subprocess.run(['docker', 'logs', '--tail', '80', container['Id']], capture_output=True, timeout=10)
                    logs[role] = (captured.stdout + captured.stderr).decode(errors='replace')[-16000:]
                atomic_json(root / 'worker-error.json', {'service': service, 'path': path, 'status': error.code,
                    'detail': error.read(4096).decode(errors='replace'), 'traceback': traceback.format_exc()[-6000:], 'logs': logs})
                raise

        def switch(self, operation, selected) -> None:
            """实际切换后模拟进程掉电。:param operation: 原操作。:param selected: 候选。@return None。"""
            super().switch(operation, selected)
            if fault == 'switched-crash':
                os._exit(92)

        def migrate_databases(self, operation, plan, save) -> None:
            """真实迁移后注入进程掉电。:param operation: 操作。:param plan: 计划。:param save: 持久回调。@return None。"""
            if fault == 'first-database-crash':
                first = {'databases': {'bench': plan['databases']['bench']}}
                super().migrate_databases(operation, first, save)
                os._exit(93)
            super().migrate_databases(operation, plan, save)

        def health(self, operation, selected, *, restoring=False) -> None:
            """真实验收后注入候选失败。:param operation: 原操作。:param selected: 候选。:param restoring: 恢复。@return None。"""
            super().health(operation, selected, restoring=restoring)
            if fault == 'health' and not restoring:
                raise ValueError('隔离夹具候选验收故障')
            if fault == 'restoring-crash':
                if restoring:
                    os._exit(94)
                raise ValueError('隔离夹具候选验收故障')

        def update_environments(self, operation, selected, save) -> None:
            """真实重建后移除一个空闲角色，模拟账号重建的部分失败。

            :param operation: 本次操作。
            :param selected: 候选。
            :param save: 持久回调。
            :return: None。
            """
            super().update_environments(operation, selected, save)
            if fault == 'partial-account':
                client = docker.from_env()
                try:
                    for row in operation['before']['environments']:
                        if row['environment_id'] not in operation.get('environment_intents', {}):
                            continue
                        containers = client.containers.list(filters={'label': ['vibebench.deployment=' + policy['deployment'],
                            'vibebench.environment=' + row['environment_id'], 'vibebench.role=account']})
                        assert len(containers) == 1
                        containers[0].remove(force=True)
                        raise ValueError('隔离夹具账号部分角色故障')
                finally:
                    client.close()
    engine = SystemUpdater(policy, FaultHost(policy))
    path = root / 'socket/updater.sock'
    path.unlink(missing_ok=True)
    server = UpdateServer(str(path), UpdateHTTPHandler)
    path.chmod(0o600)
    server.token = safe_read(root / 'socket/token', 128, private=True).decode().strip()
    server.engine = engine
    engine.resume()
    server.serve_forever(poll_interval=0.2)


def verify(output: Path, gateway_binary: Path, sender_binary: Path, migration_manifest: Path | None = None) -> dict:
    """运行实际底座、控制复用、账号重建、回退及进程恢复并清理专属资源。

    :param output: 脱敏证据目录。
    :param gateway_binary: 当前已编译测试网关。
    :param sender_binary: 当前已编译发送器。
    :param migration_manifest: 可选真实迁移候选镜像清单，开启 v1→v2 接入验收。
    :return: 场景结果。
    """
    output.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex[:10]
    deployment = 'verify-update-' + identifier
    client = docker.from_env()
    session = requests.Session()
    session.trust_env = False
    results, references = [], []
    child = None
    with tempfile.TemporaryDirectory(prefix='v3-update-', dir='/tmp') as temporary:
        root = Path(temporary)
        data, update_root = root / 'v3-data', root / 'updates'
        context = root / 'context'
        context.mkdir()
        (context / 'orchestrator').mkdir()
        for path in (source_path(REPO, 'orchestrator')).glob('*.py'):
            shutil.copy2(path, context / 'orchestrator' / path.name)
        shutil.copy2(source_path(REPO, 'orchestrator/database-migration-registry.json'), context / 'orchestrator/database-migration-registry.json')
        shutil.copy2(gateway_binary, context / 'gateway')
        shutil.copy2(sender_binary, context / 'sender')
        shutil.copytree(source_path(REPO, 'cc2api/web/dist'), context / 'dist')
        # 使用现有隔离测试底座提供系统依赖，实际业务程序均由本次源码替换。
        (context / 'Dockerfile').write_text('''FROM vibebench-v3-control:v3-verify-kernel-online-final AS control
COPY orchestrator/ /app/
COPY gateway /app/claude-code-gateway
COPY dist /app/web/dist
# 生命周期夹具使用空项目库，避免历史底座中的大型示例库影响启动期限。
ENV PROJECT_LIBRARY_DIR=/isolated-empty-library
ARG RELEASE
ARG REVISION
LABEL vibebench.release=$RELEASE vibebench.parent-revision=$REVISION vibebench.system-update-protocol="1" vibebench.verification="platform-update"
FROM vibebench-v3-account:v3-verify-kernel-online-final AS account
COPY sender /usr/local/bin/account-sender
ARG RELEASE
ARG REVISION
ARG CONTENT
LABEL vibebench.release=$RELEASE vibebench.parent-revision=$REVISION vibebench.system-update-protocol="1" vibebench.account-runtime-protocol="1" vibebench.verification="platform-update" vibebench.test-content=$CONTENT
''')
        candidate = strict_json(migration_manifest.read_bytes()) if migration_manifest else None
        if candidate:
            (context / 'Dockerfile').write_text('''ARG CONTROL_BASE
ARG ACCOUNT_BASE
FROM ${CONTROL_BASE} AS control
ENV PROJECT_LIBRARY_DIR=/isolated-empty-library
ARG RELEASE
ARG REVISION
LABEL vibebench.release=$RELEASE vibebench.parent-revision=$REVISION vibebench.verification="platform-migration-update"
FROM ${ACCOUNT_BASE} AS account
ARG RELEASE
ARG REVISION
ARG CONTENT
LABEL vibebench.release=$RELEASE vibebench.parent-revision=$REVISION vibebench.verification="platform-migration-update" vibebench.test-content=$CONTENT
''')
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
        key = root / 'private.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(key)], check=True, capture_output=True)
        public = subprocess.check_output(['openssl', 'pkey', '-in', str(key), '-pubout', '-outform', 'DER'])[-32:].hex()
        counter = int(uuid.uuid4().hex[:12], 16)
        releases, folders = [], []
        env = root / 'v3.env'
        compose = REPO / 'deploy/flower2api/compose.yml'
        override = REPO / 'deploy/flower2api/compose-updates.yml'
        values = {}
        business_token = None

        def passed(scene, **facts):
            """保存通过事实。:param scene: 场景。:param facts: 脱敏结果。@return None。"""
            results.append({'scene': scene, 'passed': True, **facts})
            print('通过：' + scene, flush=True)

        def controls():
            """读取精确部署容器。@return 角色映射。"""
            return {item.labels['vibebench.role']: item for item in client.containers.list(all=True,
                filters={'label': ['vibebench.product=v3', 'vibebench.deployment=' + deployment]})}

        def request(method, path, **options):
            """通过真实统一后台访问。:param method: 方法。:param path: 固定路径。:param options: 正文。@return 响应。"""
            return session.request(method, f'http://127.0.0.1:{values["V3_HOST_PORT"]}' + path,
                headers=options.pop('headers', {'Authorization': 'Bearer ' + values['V3_ADMIN_PASSWORD']}), timeout=30, **options)

        def runtime_ready():
            """取得真实管理会话。@return 是否就绪。"""
            return request('POST', '/admin/runtime/session').status_code == 200

        def status():
            """读取跨网关、调度器、Unix socket 的实际状态。@return 状态。"""
            response = request('GET', '/runtime/api/system-updates/status')
            response.raise_for_status()
            return response.json()

        def start_worker(fault=None):
            """重启独立测试执行器。:param fault: 一次故障。@return None。"""
            nonlocal child
            if child is not None and child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
            arguments = [sys.executable, str(Path(__file__).resolve()), '--worker', '--policy', str(update_root / 'policy.json')]
            if fault:
                arguments += ['--fault', fault]
            child = subprocess.Popen(arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            wait_for(lambda: status().get('installed'), '独立更新服务未就绪')

        def submit(index, action='install'):
            """冻结实际 revision 和签名摘要提交。:param index: 夹具版本。:param action: 操作。@return 冻结请求。"""
            body = {'operation_id': str(uuid.uuid4()), 'expected_revision': status()['revision'],
                'target_release': releases[index]['release'],
                'target_manifest_sha256': hashlib.sha256((folders[index] / 'system-release.json').read_bytes()).hexdigest(),
                'drain_timeout_seconds': 60}
            response = request('POST', '/runtime/api/system-updates/' + action, json=body)
            assert response.status_code == 202, response.text[:512]
            return body

        def finished():
            """等候原持久操作结束。@return 实际操作。"""
            state = status()
            return state['operation'] if not state['busy'] else None

        def account_rows():
            """读取实际环境身份、代次及角色。@return 持久记录。"""
            with closing(sqlite3.connect(data / 'bench/db.sqlite')) as database, database:
                database.row_factory = sqlite3.Row
                return [dict(row) for row in database.execute('SELECT * FROM account_environments ORDER BY name')]

        def seed_accounts():
            """用合成账号创建真实三角色，并保留一个原本停止的环境。@return None。"""
            nonlocal business_token
            runtime = controls()['orchestrator']
            proxy_data = root / 'proxy'
            proxy_data.mkdir()
            certificates(proxy_data)
            gateway = controls()['gateway']
            gateway.exec_run(['mkdir', '-p', '/run/v3'])
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode='w') as bundle:
                payload = (proxy_data / 'ca.der').read_bytes()
                entry = tarfile.TarInfo('verification-ca.der')
                entry.size, entry.mode = len(payload), 0o600
                bundle.addfile(entry, io.BytesIO(payload))
            gateway.put_archive('/run/v3', archive.getvalue())
            proxy = client.containers.run(values['V3_CONTROL_IMAGE'], ['/fixtures/forwarding_network.py'], entrypoint='python',
                detach=True, network='vibebench-v3-' + deployment,
                labels={'vibebench.product': 'v3', 'vibebench.deployment': deployment, 'vibebench.role': 'verification'},
                volumes={str(REPO / 'deploy/flower2api/fixtures'): {'bind': '/fixtures', 'mode': 'ro'},
                    str(proxy_data): {'bind': '/fixtures-data', 'mode': 'rw'}})
            wait_for(lambda: proxy.exec_run(['python', '-c', "import socket;socket.create_connection(('127.0.0.1',1081),timeout=1).close()"]).exit_code == 0,
                '本地 DNS 与代理夹具未就绪')
            proxy.reload()
            address = proxy.attrs['NetworkSettings']['Networks']['vibebench-v3-' + deployment]['IPAddress']
            # 合成代理自己终止 DNS 和隧道，全部账号流量只在本次网络内处理。
            response = request('POST', '/admin/accounts', json={'name': 'synthetic-running', 'email': 'update@example.invalid',
                'auth_type': 'oauth', 'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh',
                'expires_at': int((time.time() + 7200) * 1000), 'proxy_url': f'http://{address}:1081',
                'auto_poll_usage': False, 'auto_telemetry': False})
            assert response.status_code == 201, response.text[:512]
            gateway_account_id = response.json()['id']
            response = request('POST', '/admin/tokens', json={'name': 'synthetic-update', 'allowed_accounts': str(gateway_account_id)})
            assert response.status_code == 201, response.text[:512]
            business_token = response.json()['token']
            code = '''import main,docker
from account_runtime import AccountRuntime
r=AccountRuntime(docker.from_env(),main.BENCH_DATA,main.HOST_BENCH_DATA,main.get_db,main.derive_v3_fingerprint,main.cc2api_client)
try:
 for name in ('synthetic-running','synthetic-stopped'):
  with main.get_db() as db:
   aid=db.execute('INSERT INTO accounts(name,profile_path,timezone,upstream_proxy_scheme,upstream_socks5_host,upstream_socks5_port,enabled,warmup_enabled) VALUES(?,?,?,?,?,?,0,0)',(name,'profiles/'+name,'Asia/Tokyo','http',PROXY,1081)).lastrowid
   account=dict(db.execute('SELECT * FROM accounts WHERE id=?',(aid,)).fetchone())
  if name.endswith('running'):
   with main.get_db() as db:db.execute('UPDATE accounts SET cc2api_account_id=?,enabled=1 WHERE id=?',(REMOTE,aid))
   account.update(cc2api_account_id=REMOTE,enabled=1)
   row=r._row(name,aid,'Asia/Tokyo')
   import pathlib,base64
   ca=r._root(row)/'runtime/verification-ca.der';ca.parent.mkdir(parents=True,exist_ok=True);ca.write_bytes(base64.b64decode(CERTIFICATE))
   r.ensure(account)
  else:
   row=r._row(name,aid,'Asia/Tokyo');r._update(row,state='stopped')
finally:r.heartbeat_pool.shutdown()
'''.replace('PROXY', repr(address)).replace('REMOTE', str(gateway_account_id)).replace('CERTIFICATE', repr(base64.b64encode((proxy_data / 'ca.der').read_bytes()).decode()))
            result = runtime.exec_run(['python', '-c', code])
            assert result.exit_code == 0, result.output.decode(errors='replace')[-2000:]
            rows = account_rows()
            assert rows[0]['state'] == 'ready' and rows[1]['state'] == 'stopped'
            assert all(rows[0][key] for key in ('container_id', 'sender_container_id', 'network_container_id'))

        try:
            for index in range(4):
                release = f'ci-{counter + index}-1'
                images = {}
                extra_arguments = []
                if candidate:
                    bases = ({'control': 'vibebench-v3-control:v3-verify-native-warm-20261112',
                        'account': 'vibebench-v3-account:v3-verify-native-warm-20261112'} if index == 0
                        else {role: candidate['images'][role]['reference'] for role in ('control', 'account')})
                    extra_arguments = ['--build-arg', 'CONTROL_BASE=' + bases['control'], '--build-arg', 'ACCOUNT_BASE=' + bases['account']]
                for role in ('control', 'account'):
                    reference = f'ghcr.io/silentflower/vibebench-v3-{role}:v3-{release}'
                    references.append(reference)
                    build_metadata = root / f'build-{index}-{role}.json'
                    subprocess.run(['docker', 'build', '--pull=false', '--target', role, '--metadata-file', str(build_metadata), '--build-arg', 'RELEASE=' + release,
                        '--build-arg', 'REVISION=' + revision, '--build-arg', 'CONTENT=' + ('new' if index >= 2 else 'old'),
                        *extra_arguments, '-t', reference, str(context)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    image = client.images.get(reference)
                    # BuildKit 输出原始配置摘要；旧 builder 保留 archive 核验入口。
                    config_digest = strict_json(build_metadata.read_bytes()).get('containerimage.config.digest')
                    images[role] = {'reference': reference, 'platform': 'linux/amd64', 'registry_digest': image.id,
                        'config_digest': config_digest or _image_config_digest(reference), 'unpacked_bytes': image.attrs['Size']}
                manifest = root / ('v3-' + str(index) + '.json')
                atomic_json(manifest, {'schema': 3, 'release': release, 'dirty_worktree': False, 'layout_version': 2,
                    'credential_ownership_protocol': 1, 'system_update_protocol': 1,
                    'parent_revision': revision, 'gateway_revision': revision, 'images': images,
                    'bundle': {'name': 'v3-images.tar.gz', 'size': 1, 'sha256': 'a' * 64}})
                folder = root / ('release-' + str(index))
                evidence_path = None
                if candidate and index:
                    evidence_path = root / ('evidence-' + str(index) + '.json')
                    verify_database_compatibility(manifest, public, evidence_path, history_root=root / 'history')
                value = create_release(manifest, REPO / 'deploy/flower2api/system-update-policy.json', folder, key,
                    [counter + index, 1], '隔离平台更新验证', migration_evidence=evidence_path)
                if candidate and index == 0:
                    # 合成历史发行绑定真实旧镜像，旧合同取自已归档的预热版本。
                    for name, digest in {'bench': 'e7232926f126ec2a3ad60b3f346c4a7ad473d66497617acc6773c0c05117674b',
                            'gateway': '9b28f95cf540f10d2651026d95af6d8e7c9ece44f4c4939c62a2cbc775ddbcd1'}.items():
                        value['data_compatibility'][name] = {'contract': digest, 'rollback_compatible': [digest]}
                    atomic_json(folder / 'system-release.json', value)
                    (folder / 'system-release.sig').unlink()
                    sign_file(folder / 'system-release.json', key)
                    history = root / 'history'
                    history.mkdir()
                    shutil.copytree(folder, history / value['release'])
                    create_index(folder / 'system-release.json', None, history / 'index.json', key)
                if index >= 2:
                    value['account']['content_sha256'] = hashlib.sha256(b'isolated-account-new-content').hexdigest()
                    atomic_json(folder / 'system-release.json', value)
                    (folder / 'system-release.sig').unlink()
                    sign_file(folder / 'system-release.json', key)
                releases.append(value)
                folders.append(folder)
                if candidate:
                    shutil.copytree(folder, output / value['release'])
                    if evidence_path:
                        shutil.copy2(evidence_path, output / ('compatibility-' + str(index) + '.json'))
            if candidate:
                atomic_json(output / 'provenance.json', {'verification_only': True, 'public_key': public, 'candidate': candidate})
            passed('真实镜像、独立签名和原始构建清单准备', releases=[item['release'] for item in releases])
            with socket.socket() as port:
                port.bind(('127.0.0.1', 0))
                host_port = port.getsockname()[1]
            values = {'V3_DEPLOYMENT_ID': deployment, 'V3_DATA_ROOT': str(data), 'V3_HOST_PORT': str(host_port),
                'V3_RELEASE': releases[0]['control']['release'],
                'V3_CONTROL_IMAGE': releases[0]['control']['reference'], 'V3_ACCOUNT_IMAGE': releases[0]['account']['reference'],
                'V3_ADMIN_PASSWORD': uuid.uuid4().hex * 2, 'V3_INTERNAL_TOKEN': uuid.uuid4().hex * 2,
                'V3_SESSION_SECRET': uuid.uuid4().hex * 2, 'V3_ACCOUNT_MEMORY': '1536m', 'V3_MAX_ACTIVE_ACCOUNTS': '2'}
            atomic_text(env, ''.join(key + '=' + value + '\n' for key, value in values.items()))
            for directory in (data, data / 'gateway', data / 'bench'):
                directory.mkdir(mode=0o700, exist_ok=True)
            atomic_json(data / '.v3-deployment.json', {'deployment': deployment})
            # 本机历史测试已用尽 Docker 默认地址池；显式选取和现有网络、宿主路由均不重叠的测试网段。
            occupied = [ipaddress.ip_network(item['Subnet']) for network in client.networks.list()
                for item in network.attrs.get('IPAM', {}).get('Config') or [] if item.get('Subnet')]
            routes = json.loads(subprocess.check_output(['ip', '-j', 'route', 'show']))
            occupied.extend(ipaddress.ip_network(item['dst']) for item in routes if item.get('dst') not in (None, 'default'))
            subnet = next(ipaddress.ip_network(f'10.233.{index}.0/24') for index in range(200, 250)
                if not any(ipaddress.ip_network(f'10.233.{index}.0/24').overlaps(item) for item in occupied if item.version == 4))
            client.networks.create('vibebench-v3-' + deployment, driver='bridge',
                ipam=docker.types.IPAMConfig(pool_configs=[docker.types.IPAMPool(subnet=str(subnet))]),
                labels={'vibebench.product': 'v3', 'vibebench.deployment': deployment,
                    'com.docker.compose.project': 'vibebench-v3-' + deployment, 'com.docker.compose.network': 'v3'})
            subprocess.run(['docker', 'compose', '--env-file', str(env), '-f', str(compose), 'up', '-d'], check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            wait_for(runtime_ready, '初始隔离控制服务未就绪')
            assert prepare_installation(env, folders[0], update_root, public)['status'] == 'planned'
            prepare_installation(env, folders[0], update_root, public, apply=True)
            subprocess.run(['docker', 'compose', '--env-file', str(update_root / 'bootstrap.env'), '-f', str(compose),
                '-f', str(override), 'up', '-d'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            wait_for(runtime_ready, '底座控制服务未就绪')
            finalize_installation(update_root / 'policy.json', apply=True)
            seed_accounts()
            catalog_path = None
            for index, folder in enumerate(folders):
                destination = update_root / 'releases' / releases[index]['release']
                if not destination.exists():
                    shutil.copytree(folder, destination)
                next_path = root / ('index-' + str(index) + '.json')
                create_index(folder / 'system-release.json', catalog_path, next_path, key)
                catalog_path = next_path
            state = strict_json(safe_read(update_root / 'state.json'))
            state['catalog'] = strict_json(catalog_path.read_bytes())
            atomic_json(update_root / 'state.json', state)
            start_worker()
            if candidate:
                def control(*arguments):
                    """将底座服务控制限定为本次独立进程。:param arguments: 固定动作。@return 状态。"""
                    if arguments[0] == 'show':
                        return str(update_root / 'vibebench-updater.service')
                    if arguments[0] == 'stop':
                        if child.poll() is None:
                            child.terminate()
                            child.wait(timeout=10)
                        return ''
                    if arguments[0] == 'start':
                        start_worker()
                        return ''
                    if arguments[0] == 'is-active':
                        return 'active' if child.poll() is None else 'inactive'
                    raise AssertionError('测试服务动作超出范围')
                upgraded = upgrade(update_root / 'policy.json', REPO, 'isolated-updater.service', apply=True, control=control)
                assert upgraded['status'] == 'upgraded'
                assert status()['migration_capability'] is True
                passed('真实独立进程、Unix接口和安装历史的v2底座接入')
                control('stop', 'isolated-updater.service')
                installed = strict_json(safe_read(update_root / 'state.json'))
                # 接入会清空旧通道；隔离演练直接装入本次签名目录，模拟完成新通道检查。
                atomic_json(update_root / 'state.json', {**installed, 'catalog': strict_json(catalog_path.read_bytes())})
                start_worker()
                probe_source = '''import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'source/deploy/v3'),str(root/'source/orchestrator')]
import system_updater
assert Path(system_updater.__file__).is_relative_to(root/'source')
engine=system_updater.SystemUpdater(json.loads((root/'policy.json').read_text()))
assert engine.status()['migration_capability'] is True
'''
                subprocess.run([sys.executable, '-I', '-c', probe_source, str(update_root)], check=True, capture_output=True)
                passed('已复制底座源码在独立解释器中完成导入及状态核验')
            assert request('POST', '/runtime/api/system-updates/install', json={}).status_code == 422
            passed('真实首次底座接入和三层管理桥', installed=status()['current_release'])
            before_accounts = account_rows()
            old_controls = {role: item.id for role, item in controls().items() if role in ('gateway', 'orchestrator')}
            # 真实未知 CLI 子进程必须阻塞切换，取消后保持原进程自然完成。
            cli = controls()['account']
            assert cli.exec_run(['sleep', '8'], detach=True).exit_code is None
            cancellation = submit(1)
            wait_for(lambda: status()['operation']['phase'] == 'draining', '未观察到实际进程排空阶段', timeout=30)
            assert request('POST', '/v1/messages', json={'model': 'synthetic'}).status_code == 503
            response = request('POST', '/runtime/api/system-updates/operations/' + cancellation['operation_id'] + '/cancel',
                json={'expected_revision': status()['revision']})
            assert response.status_code == 202, response.text[:512]
            result = wait_for(finished, '取消等待未收口')
            assert result['phase'] == 'cancelled', result
            assert all(controls()[role].id == identity for role, identity in old_controls.items())
            passed('未知实际 CLI 活动阻断切换、新请求拒绝及取消等待', operation=result)
            if candidate:
                submit(1)
            else:
                with request('POST', '/api/v3-verification', headers={'Authorization': 'Bearer ' + business_token,
                        'User-Agent': 'python-httpx/0.28.1'}, json={'marker': 'slow-kernel', 'stream': True}, stream=True) as stream:
                    assert stream.status_code == 200, stream.text[:512] if stream.status_code != 200 else ''
                    submit(1)
                    wait_for(lambda: status()['operation']['phase'] == 'draining', '长 API 响应未保持排空等待', timeout=30)
                    assert all(controls()[role].id == identity for role, identity in old_controls.items())
                    assert request('POST', '/api/v3-verification', headers={'Authorization': 'Bearer ' + business_token}, json={}).status_code == 503
                    (root / 'proxy/release-kernel').touch()
                    assert b'message_stop' in stream.content
            result = wait_for(finished, '控制更新未结束')
            assert result['phase'] == 'succeeded', result
            assert status()['current_release'] == releases[1]['release']
            assert status()['components']['account']['release'] == releases[0]['account']['release']
            assert all(controls()[role].id != identity for role, identity in old_controls.items())
            assert account_rows() == before_accounts
            passed('真实迁移后切换并保留三角色ID、代次、画像和账号来源' if candidate else
                '真实 TLS 长 API 完整收口后切换，保留三角色 ID、代次、画像和账号来源', operation=result)
            submit(2)
            result = wait_for(finished, '账号组件重建未结束')
            assert result['phase'] == 'succeeded', result
            after_accounts = account_rows()
            assert after_accounts[0]['generation'] > before_accounts[0]['generation']
            assert all(after_accounts[0][key] != before_accounts[0][key]
                for key in ('container_id', 'sender_container_id', 'network_container_id'))
            assert after_accounts[0]['fingerprint_json'] == before_accounts[0]['fingerprint_json']
            assert after_accounts[1] == before_accounts[1]
            passed('真实账号组件按需重建与停止环境保留', operation=result)
            if candidate:
                with closing(sqlite3.connect(data / 'bench/db.sqlite')) as database, database:
                    database.execute("INSERT INTO topics(no,title) VALUES(-91212,'migration-later-business')")
            submit(0, 'rollback')
            result = wait_for(finished, '显式回退未结束')
            assert result['phase'] == 'succeeded', result
            assert status()['current_release'] == releases[0]['release']
            if candidate:
                with closing(sqlite3.connect(data / 'bench/db.sqlite')) as database, database:
                    assert database.execute("SELECT 1 FROM topics WHERE no=-91212 AND title='migration-later-business'").fetchone()
            passed('真实显式回退和历史来源恢复', operation=result)
            if candidate:
                # 在独立旧程序夹具中恢复“从未登记迁移”的旧库形态，实际制造只迁移一侧的状态。
                for name, filename in (('bench', 'db.sqlite'), ('gateway', 'gateway.sqlite')):
                    with closing(sqlite3.connect(data / name / filename)) as database, database:
                        database.execute('DROP TABLE IF EXISTS system_schema_migrations')
                start_worker('first-database-crash')
                submit(2)
                wait_for(lambda: child.poll() == 93, '第一库迁移后故障进程未退出')
                assert read_gate(update_root / 'gate', deployment)['phase'] == 'blocked'
                versions = []
                for name, filename in (('bench', 'db.sqlite'), ('gateway', 'gateway.sqlite')):
                    with closing(sqlite3.connect(data / name / filename)) as database:
                        exists = database.execute("SELECT 1 FROM sqlite_master WHERE name='system_schema_migrations'").fetchone()
                        versions.append(database.execute('SELECT MAX(version) FROM system_schema_migrations').fetchone()[0] if exists else 0)
                assert versions == [1, 0], versions
                start_worker()
                result = wait_for(finished, '双库部分迁移恢复未结束')
                assert result['phase'] == 'restored', result
                for name, filename in (('bench', 'db.sqlite'), ('gateway', 'gateway.sqlite')):
                    with closing(sqlite3.connect(data / name / filename)) as database:
                        assert database.execute("SELECT 1 FROM sqlite_master WHERE name='system_schema_migrations'").fetchone() is None
                passed('真实第一库迁移完成后进程中断及双库恢复', operation=result, versions_before_recovery=versions)
            start_worker('health')
            submit(2)
            result = wait_for(finished, '候选失败恢复未结束')
            assert result['phase'] == 'restored', result
            assert status()['current_release'] == releases[0]['release']
            assert read_gate(update_root / 'gate', deployment)['phase'] == 'idle'
            passed('候选验收失败后真实控制服务恢复', operation=result)
            if candidate:
                start_worker('restoring-crash')
                submit(2)
                wait_for(lambda: child.poll() == 94, '原程序恢复启动后故障进程未退出')
                assert read_gate(update_root / 'gate', deployment)['phase'] == 'blocked'
                start_worker()
                result = wait_for(finished, '原程序恢复启动后重启续接未结束')
                assert result['phase'] == 'restored', result
                passed('双库恢复完成且原程序启动后掉电，重启继续同一恢复', operation=result)
            start_worker('partial-account')
            submit(2)
            result = wait_for(finished, '账号部分重建失败恢复未结束')
            assert result['phase'] == 'restored', result
            assert account_rows()[0]['state'] == 'ready'
            assert account_rows()[1]['state'] == 'stopped'
            assert status()['current_release'] == releases[0]['release']
            passed('真实账号缺失部分角色后恢复原镜像和身份', operation=result)
            start_worker('switched-crash')
            submit(3)
            wait_for(lambda: child.poll() == 92, '切换后故障进程未退出')
            assert read_gate(update_root / 'gate', deployment)['phase'] == 'blocked'
            start_worker()
            result = wait_for(finished, '独立执行器重启恢复未结束')
            assert result['phase'] == 'restored', result
            assert status()['current_release'] == releases[0]['release']
            passed('实际切换后进程中断与持久恢复', operation=result)
            retained = client.containers.create(releases[1]['control']['reference'], ['-c', 'pass'], entrypoint='python',
                network_mode='none', labels={'vibebench.product': 'v3', 'vibebench.deployment': deployment,
                    'vibebench.role': 'retention-proof'})
            submit(3)
            result = wait_for(finished, '保留策略验证的最终安装未结束')
            assert result['phase'] == 'succeeded', result
            if candidate:
                snapshots = result['cleanup']['database_snapshots']
                assert snapshots['retained_groups'] == 2 and snapshots['preserved_unverified_groups'] == 0, snapshots
            assert releases[1]['control']['reference'] in result['cleanup']['retained']
            retained.remove()
            installed = strict_json(safe_read(update_root / 'state.json'))
            policy = strict_json(safe_read(update_root / 'policy.json'))
            cleaned = HostDeployment(policy).cleanup(installed['current'], installed['history'], [])
            assert releases[1]['control']['reference'] in cleaned['removed'], cleaned
            for installation in [installed['current'], *installed['history'][:2]]:
                for entry in installation['selection'].values():
                    client.images.get(entry['reference'])
            passed('真实容器引用保护、最近两个完整组合保留和精确旧镜像回收', cleanup=cleaned)
            report = {'deployment': deployment, 'scenes': results, 'real_model_calls': 0}
            atomic_json(output / 'results.json', report)
            return report
        except BaseException:
            facts = []
            for role, container in controls().items():
                logs = container.logs(tail=70).decode(errors='replace')
                for key_name in ('V3_ADMIN_PASSWORD', 'V3_INTERNAL_TOKEN', 'V3_SESSION_SECRET'):
                    if values.get(key_name):
                        logs = logs.replace(values[key_name], '[已脱敏]')
                facts.append({'role': role, 'logs': logs})
            diagnostic = root / 'updates/worker-error.json'
            atomic_json(output / 'failure.json', {'scenes': results, 'containers': facts,
                'worker_error': strict_json(diagnostic.read_bytes()) if diagnostic.exists() else None})
            raise
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
            # 清理对象逐个来自本次随机部署标签及本次唯一精确镜像引用。
            for container in controls().values():
                container.remove(force=True)
            for network in client.networks.list(filters={'label': 'vibebench.deployment=' + deployment}):
                network.remove()
            for reference in references:
                try:
                    client.images.remove(reference)
                except docker.errors.ImageNotFound:
                    pass
            client.close()
            session.close()


def main() -> None:
    """提供隔离验收入口与内部子进程入口。@return None。"""
    parser = argparse.ArgumentParser(description='隔离 Docker 验证平台在线安装、回退和进程恢复')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--retention-only', action='store_true', help='只执行独立真实镜像保留与回收场景')
    parser.add_argument('--gateway-binary', type=Path, default=source_path(REPO, 'cc2api/target/release/claude-code-gateway'))
    parser.add_argument('--sender-binary', type=Path, default=source_path(REPO, 'cc2api/target/release/account-sender'))
    parser.add_argument('--migration-manifest', type=Path, help='使用真实旧/新镜像验收迁移底座接入及故障恢复')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--policy', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--fault', choices=('health', 'switched-crash', 'partial-account', 'first-database-crash', 'restoring-crash'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args.policy, args.fault)
        return
    if not args.output:
        parser.error('需要 --output 脱敏证据目录')
    if args.retention_only:
        report = verify_retention(args.output)
        print(json.dumps({'passed': report['passed'], 'real_model_calls': 0}, ensure_ascii=False))
        return
    report = verify(args.output, args.gateway_binary, args.sender_binary, args.migration_manifest)
    print(json.dumps({'passed': len(report['scenes']), 'real_model_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
