#!/usr/bin/env python3
"""用真实调度器、账号容器和隔离 HTTPS 上游验证正式 API 完整往返。"""
import argparse
import asyncio
import base64
import copy
import hashlib
import io
import ipaddress
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import tarfile
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import docker
import requests

import manage
from manage import REPO
from verify_browser import ACCOUNT_STARTUP_TIMEOUT, verify_visible_logout
from verify_isolation import verify_official_tools, verify_roles


def wait_until(predicate, message, seconds=30):
    """有界等待真实可观察条件。

    :param predicate: 无副作用的状态读取。
    :param message: 超时原因。
    :param seconds: 最长秒数。
    :return: 首个真值。
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError(message)


def build_verification(release, destination):
    """复用正式入口的源码冻结及联合清单，只替换显式测试目标。

    :param release: 唯一测试批次。
    :param destination: 全新清单路径。
    :return: None。
    """
    original = manage.command

    def command(*arguments, **options):
        """保持所有构建参数，仅将最终目标限定为测试阶段。

        :param arguments: 正式构建命令。
        :param options: 原调用选项。
        :return: 正式命令输出。
        """
        arguments = list(arguments)
        if arguments[:2] == ['docker', 'build']:
            index = arguments.index('--target') + 1
            arguments[index] = 'verification-' + arguments[index]
        return original(*arguments, **options)

    with patch.object(manage, 'command', command):
        manage.build(release, destination)
    manifest = json.loads(destination.read_text())
    manifest['verification_only'] = 'v3-verification: extra CA; never publish or deploy to production'
    destination.write_text(json.dumps(manifest, indent=2) + '\n')


def certificates(root):
    """为三种证书校验场景生成临时密钥，默认静默执行。

    :param root: 专属夹具目录。
    :return: None。
    """
    def openssl(*arguments):
        """执行本地证书工具，不输出私钥。

        :param arguments: OpenSSL 参数。
        :return: None。
        """
        subprocess.run(['openssl', *arguments], cwd=root, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for authority in ('ca', 'other'):
        openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=V3 isolated verification',
            '-keyout', authority + '.key', '-out', authority + '.crt')
    openssl('x509', '-in', 'ca.crt', '-outform', 'DER', '-out', 'ca.der')
    for mode in ('valid', 'untrusted', 'hostname'):
        hostname = 'wrong.invalid' if mode == 'hostname' else 'api.anthropic.com'
        openssl('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=' + hostname,
            '-keyout', mode + '.key', '-out', mode + '.csr')
        names = hostname + (',DNS:platform.claude.com' if mode != 'hostname' else '')
        (root / (mode + '.ext')).write_text('subjectAltName=DNS:' + names + '\n')
        authority = 'other' if mode == 'untrusted' else 'ca'
        openssl('x509', '-req', '-in', mode + '.csr', '-CA', authority + '.crt', '-CAkey', authority + '.key',
            '-CAcreateserial', '-days', '1', '-extfile', mode + '.ext', '-out', mode + '.crt')


def verify(manifest_path, output, binary):
    """运行全链路和浏览器场景，最终仅清理本次标签资源。

    :param manifest_path: 测试专用联合镜像清单。
    :param output: 脱敏结果目录，不保存令牌或代理密码。
    :param binary: 已安装的官方 CLI 原生二进制。
    :return: None；任一场景不符即失败。
    """
    manifest = json.loads(manifest_path.read_text())
    assert manifest.get('verification_only'), '只能使用明确标注的隔离测试镜像'
    client = docker.from_env()
    deployment = 'forward-' + uuid.uuid4().hex[:10]
    labels = {'vibebench.product': 'v3', 'vibebench.deployment': deployment}
    filters = {'label': [key + '=' + value for key, value in labels.items()]}
    output.mkdir(parents=True, exist_ok=False)
    results = []
    with tempfile.TemporaryDirectory(prefix='v3-forwarding-') as temporary:
        root = Path(temporary)
        data = root / 'v3-data'
        fixture = root / 'fixture'
        fixture.mkdir()
        certificates(fixture)
        used = [ipaddress.ip_network(item['Subnet']) for network in client.networks.list()
            for item in network.attrs.get('IPAM', {}).get('Config') or [] if item.get('Subnet')]
        routes = json.loads(subprocess.check_output(['ip', '-j', 'route', 'show']))
        used.extend(ipaddress.ip_network(item['dst']) for item in routes if item.get('dst') not in (None, 'default'))
        subnet = next(ipaddress.ip_network(f'10.231.{index}.0/24') for index in range(200, 250)
            if not any(ipaddress.ip_network(f'10.231.{index}.0/24').overlaps(item) for item in used if item.version == 4))
        compose = root / 'compose.yml'
        compose.write_text(manage.COMPOSE.read_text() + f'    ipam:\n      config:\n        - subnet: {subnet}\n')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        values = {'V3_DEPLOYMENT_ID': deployment, 'V3_DATA_ROOT': str(data), 'V3_HOST_PORT': str(port),
            'V3_BIND_ADDRESS': '127.0.0.1', 'V3_CONTROL_IMAGE': manifest['images']['control']['reference'],
            'V3_ACCOUNT_IMAGE': manifest['images']['account']['reference'], 'V3_RELEASE_MANIFEST': str(manifest_path.resolve()),
            'V3_ADMIN_PASSWORD': uuid.uuid4().hex + uuid.uuid4().hex,
            'V3_INTERNAL_TOKEN': uuid.uuid4().hex + uuid.uuid4().hex,
            'V3_SESSION_SECRET': uuid.uuid4().hex + uuid.uuid4().hex,
            'V3_CLI_VERSION': '2.1.293', 'V3_MAX_ACTIVE_ACCOUNTS': '2', 'V3_ACCOUNT_MEMORY': '1536m', 'V3_ACCOUNT_SWAP': '0'}
        environment_file = root / 'v3.env'
        environment_file.write_text(''.join(key + '=' + value + '\n' for key, value in values.items()))
        environment_file.chmod(0o600)
        wrapper = root / 'manage.py'
        wrapper.write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0,{str(REPO / "deploy/v3")!r})\n'
            f'import manage\nmanage.COMPOSE=Path({str(compose)!r})\nmanage.main()\n')
        manager = ['python3', str(wrapper)]
        session = requests.Session()
        session.trust_env = False
        base = f'http://127.0.0.1:{port}'
        admin = {'Authorization': 'Bearer ' + values['V3_ADMIN_PASSWORD']}
        proxies = []
        accounts = []

        def request(method, path, **options):
            """使用本次私有会话调用真实 API。

            :param method: HTTP 方法。
            :param path: 相对路由。
            :param options: 正文与其他请求选项。
            :return: 原始响应；不打印认证头。
            """
            return session.request(method, base + path, timeout=90, **options)

        def evidence(directory):
            """读取专用代理/上游证据。

            :param directory: 当前代理数据目录。
            :return: 脱敏 JSON 行列表。
            """
            path = directory / 'evidence.jsonl'
            return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

        def passed(scene, **facts):
            """场景全部断言完成后记录结果。

            :param scene: 场景名称。
            :param facts: 可复核摘要。
            :return: None。
            """
            results.append({'scene': scene, 'passed': True, **facts})
            print('通过：' + scene, flush=True)

        def wake(account):
            """经真实调度器的内部传输入口唤醒原关联环境。

            :param account: 当前合成账号。
            :return: 当前账号容器。
            """
            code = "import os,urllib.request;r=urllib.request.Request('http://127.0.0.1:8000/internal/v3/transport/" + str(account['gid']) + "',headers={'Authorization':'Bearer '+os.environ['V3_INTERNAL_TOKEN']});print(urllib.request.urlopen(r,timeout=90).status)"
            result = orchestrator.exec_run(['python', '-c', code])
            assert result.exit_code == 0 and result.output.strip() == b'200', '实际调度器传输绑定未就绪'
            roles = {item.labels['vibebench.role']: item for item in client.containers.list(filters={'label': [*filters['label'], 'vibebench.environment=' + account['eid']]})}
            container = roles['account']
            account['sender_container'], account['network_container'] = roles['account-sender'], roles['account-network']
            container.reload()
            version = container.exec_run(['/cli/2.1.293/node_modules/.bin/claude', '--version'], user='1000:1000')
            assert version.exit_code == 0 and version.output.decode().strip().startswith('2.1.293 '), '夹具官方 CLI 版本不符'
            account['container'] = container
            account['peer'] = next(iter(roles['account-network'].attrs['NetworkSettings']['Networks'].values()))['IPAddress']
            return container

        try:
            subprocess.run(manager + ['up', '--env', str(environment_file)], cwd=REPO, check=True)
            wait_until(lambda: request('POST', '/admin/runtime/session', headers=admin).status_code == 200, '管理桥未就绪')
            containers = client.containers.list(filters=filters)
            gateway = next(item for item in containers if item.labels['vibebench.role'] == 'gateway')
            orchestrator = next(item for item in containers if item.labels['vibebench.role'] == 'orchestrator')
            # 只在本次网关的网络命名空间阻断公网，保留宿主发布端口与原 Compose 结构。
            isolation = "import subprocess;" + ';'.join('subprocess.run(' + repr(command) + ',check=True)' for command in (
                ['iptables', '-N', 'V3VERIFY'], ['iptables', '-A', 'OUTPUT', '-o', 'eth0', '-j', 'V3VERIFY'],
                ['iptables', '-A', 'V3VERIFY', '!', '-d', str(subnet), '-j', 'REJECT']))
            client.containers.run(values['V3_ACCOUNT_IMAGE'], ['-c', isolation], entrypoint='python3',
                network_mode='container:' + gateway.id, cap_add=['NET_ADMIN'], remove=True,
                labels={**labels, 'vibebench.role': 'verification'})
            # 空代理回归即使失败，也只会尝试保留测试地址并被本次命名空间防火墙拦截。
            assert gateway.exec_run(['python', '-c',
                "open('/etc/hosts','a').write('\\n203.0.113.254 platform.claude.com\\n')"]).exit_code == 0
            gateway.exec_run(['mkdir', '-p', '/run/v3'])
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode='w') as bundle:
                content = (fixture / 'ca.der').read_bytes()
                item = tarfile.TarInfo('verification-ca.der')
                item.size, item.mode = len(content), 0o600
                bundle.addfile(item, io.BytesIO(content))
            gateway.put_archive('/run/v3', archive.getvalue())
            accounts = []
            for index, scheme in enumerate(('http', 'socks5h')):
                network_data = root / ('proxy-' + str(index))
                shutil.copytree(fixture, network_data)
                proxy = client.containers.run(values['V3_CONTROL_IMAGE'], ['/fixtures/forwarding_network.py'],
                    entrypoint='python', detach=True, network='vibebench-v3-' + deployment,
                    labels={**labels, 'vibebench.role': 'verification'},
                    volumes={str(REPO / 'deploy/v3/fixtures'): {'bind': '/fixtures', 'mode': 'ro'},
                        str(network_data): {'bind': '/fixtures-data', 'mode': 'rw'}})
                proxies.append(proxy)
                wait_until(lambda: (network_data / 'ready').exists(), '隔离代理未就绪')
                proxy.reload()
                address = next(iter(proxy.attrs['NetworkSettings']['Networks'].values()))['IPAddress']
                name = 'forwarding-' + str(index)
                with sqlite3.connect(data / 'bench/db.sqlite') as database:
                    aid = database.execute('INSERT INTO accounts(name,profile_path,timezone,upstream_proxy_scheme,upstream_socks5_host,upstream_socks5_port,enabled,warmup_enabled) VALUES(?,?,?,?,?,?,1,0)',
                        (name, 'profiles/' + name, 'Asia/Tokyo', scheme, address, 1081 if index == 0 else 1080)).lastrowid
                code = 'import main,docker;from account_runtime import AccountRuntime;' \
                    'r=AccountRuntime(docker.from_env(),main.BENCH_DATA,main.HOST_BENCH_DATA,main.get_db,main.derive_v3_fingerprint,main.cc2api_client);' \
                    'print(r._row(' + repr(name) + ',' + str(aid) + ')["environment_id"]);r.heartbeat_pool.shutdown()'
                result = orchestrator.exec_run(['python', '-c', code])
                assert result.exit_code == 0, '创建环境行失败'
                eid = result.output.decode().strip().splitlines()[-1]
                env_root = data / 'bench/environments' / eid
                for directory in ('home/.claude', 'runtime'):
                    (env_root / directory).mkdir(parents=True, exist_ok=True)
                shutil.copy2(fixture / 'ca.der', env_root / 'runtime/verification-ca.der')
                profile = data / 'bench/profiles' / name
                profile.mkdir(parents=True)
                top = {'userID': ('d' if index == 0 else 'e') * 64, 'hasCompletedOnboarding': True,
                    'hasSeenAutoDefaultNudge': True, 'bypassPermissionsModeAccepted': True,
                    'oauthAccount': {'emailAddress': name + '@example.invalid', 'accountUuid': name, 'organizationUuid': 'synthetic-org'}}
                credentials = {'claudeAiOauth': {'accessToken': 'synthetic-access-' + str(index),
                    'refreshToken': 'synthetic-refresh-' + str(index), 'expiresAt': int(time.time() * 1000) + 3600000}}
                for destination in (profile, env_root / 'home'):
                    (destination / '.claude.json').write_text(json.dumps(top))
                    (destination / '.credentials.json').write_text(json.dumps(credentials))
                cached = env_root / 'cli/2.1.293/node_modules/@anthropic-ai/claude-code/bin/claude.exe'
                cached.parent.mkdir(parents=True)
                shutil.copy2(binary, cached)
                cached.chmod(0o755)
                links = env_root / 'cli/2.1.293/node_modules/.bin'
                links.mkdir()
                (links / 'claude').symlink_to('../@anthropic-ai/claude-code/bin/claude.exe')
                (env_root / 'cli/2.1.293/.ready').touch()
                accounts.append({'aid': aid, 'name': name, 'eid': eid, 'root': env_root, 'network': network_data,
                    'top': top, 'profile': profile, 'scheme': scheme})

            async def exercise(rpc, evaluate, wait_for, session_id):
                """真实点击创建、关联和指标入口，并核对 API 与两侧数据库。

                :param rpc: CDP 命令。
                :param evaluate: 页面脚本执行器。
                :param wait_for: 浏览器条件等待。
                :param session_id: 当前私有浏览器会话。
                :return: None。
                """
                doc = "document.querySelector('iframe').contentDocument"
                win = "document.querySelector('iframe').contentWindow"
                await wait_for(f"Boolean({doc}?.querySelector('[data-cc2-create]'))")
                for width in (1440, 720):
                    await rpc('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False}, session_id)
                    for theme in ('dark', 'light'):
                        await evaluate(f"{doc}.documentElement.dataset.theme={json.dumps(theme)};{doc}.querySelector('[data-cc2-create]').scrollIntoView({{block:'center',inline:'end'}})")
                        shot = await rpc('Page.captureScreenshot', {'format': 'png'}, session_id)
                        (output / f'unbound-actions-{width}-{theme}.png').write_bytes(base64.b64decode(shot['data']))
                # 在点击前记录有限 fetch 路径与结果，避免错过短暂成功状态。
                await evaluate(f"{{const w={win};const original=w.fetch;w.__actions=[];w.__alerts=[];w.alert=message=>w.__alerts.push(message);w.fetch=async(...args)=>{{const r=await original(...args);if(String(args[0]).includes('/cc2api/'))w.__actions.push({{path:String(args[0]),status:r.status}});return r}};}}")
                for account in accounts:
                    aid = account['aid']
                    await evaluate(f"{doc}.querySelector('[data-cc2-create=\"{aid}\"]').click()")
                    await wait_for(f"Boolean({doc}.querySelector('[data-cc2-process=\"{aid}\"]'))", timeout=ACCOUNT_STARTUP_TIMEOUT)
                    with sqlite3.connect(data / 'bench/db.sqlite') as database:
                        gid = database.execute('SELECT cc2api_account_id FROM accounts WHERE id=?', (aid,)).fetchone()[0]
                    account['gid'] = gid
                    with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                        row = database.execute('SELECT billing_mode,upstream_session_pool_enabled,upstream_session_pool_size,upstream_session_refresh_policy,concurrency,rpm_limit,upstream_session_ttl_minutes,canonical_process FROM accounts WHERE id=?', (gid,)).fetchone()
                    assert row[:7] == ('rewrite', 1, 4, 'owner_only', 4, 50, 60), row[:7]
                    metrics = json.loads(row[7])
                    assert metrics['constrained_memory'] == 1207959552 and metrics['observation']['rss_bytes'] is None
                    wake(account)
                passed('V1/V2/V5 实际三角色权限、秘密隔离与本地构建', facts=verify_roles(account['container'],account['sender_container'],account['network_container']))
                passed('V5 官方 CLI 本地 SSE 工具构建', facts=verify_official_tools(account['container'], account['root'], account['network'], fixture / 'ca.crt'))
                passed('S1 创建按钮/API/SQLite：六项配置、TTL 与无样本状态')
                account = accounts[0]
                custom = {'billing_mode': 'strip', 'upstream_session_pool_enabled': False, 'upstream_session_pool_size': 2,
                    'upstream_session_refresh_policy': 'mapped_request', 'concurrency': 2, 'rpm_limit': 17}
                assert request('PUT', f"/admin/accounts/{account['gid']}", headers=admin, json=custom).status_code == 200
                # 复用正式解绑门禁构造“本地未关联、远端已存在”，不直接改数据库绕过生命周期。
                assert request('DELETE', f"/runtime/api/accounts/{account['aid']}/cc2api-binding").status_code == 200
                with sqlite3.connect(data / 'bench/db.sqlite') as database:
                    warmup_before = database.execute('SELECT warmup_enabled,warmup_next_run_at,warmup_last_status FROM accounts WHERE id=?', (account['aid'],)).fetchone()
                with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                    remote_before = database.execute('SELECT count(*) FROM accounts').fetchone()[0]
                await evaluate(f"{win}.eval('renderAccounts()')")
                await evaluate(f"{doc}.querySelector('[data-cc2-create=\"{account['aid']}\"]').click()")
                await wait_for(f"{win}.__alerts.some(value=>value.includes('关联已有账号'))")
                assert request('POST', f"/runtime/api/accounts/{account['aid']}/cc2api/process").status_code == 409
                with sqlite3.connect(data / 'bench/db.sqlite') as database:
                    assert database.execute('SELECT cc2api_account_id FROM accounts WHERE id=?', (account['aid'],)).fetchone() == (None,)
                await evaluate(f"{doc}.querySelector('[data-cc2-bind=\"{account['aid']}\"]').click()")
                await wait_for(f"!{doc}.querySelector('#cc2api-binding-modal').classList.contains('hidden')")
                await evaluate(f"{doc}.querySelector('#cc2api-binding-form').elements.cc2api_account_id.value='{account['gid']}';{doc}.querySelector('#cc2api-binding-form').requestSubmit()")
                await wait_for(f"Boolean({doc}.querySelector('[data-cc2-process=\"{account['aid']}\"]'))", timeout=ACCOUNT_STARTUP_TIMEOUT)
                with sqlite3.connect(data / 'bench/db.sqlite') as database:
                    assert database.execute('SELECT warmup_enabled,warmup_next_run_at,warmup_last_status FROM accounts WHERE id=?', (account['aid'],)).fetchone() == warmup_before
                    assert database.execute('SELECT cc2api_account_id FROM accounts WHERE id=?', (account['aid'],)).fetchone() == (account['gid'],)
                with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                    assert database.execute('SELECT count(*) FROM accounts').fetchone()[0] == remote_before
                    assert database.execute('SELECT billing_mode,upstream_session_pool_enabled,upstream_session_pool_size,upstream_session_refresh_policy,concurrency,rpm_limit FROM accounts WHERE id=?', (account['gid'],)).fetchone() == ('strip', 0, 2, 'mapped_request', 2, 17)
                defaults = {'billing_mode': 'rewrite', 'upstream_session_pool_enabled': True, 'upstream_session_pool_size': 4,
                    'upstream_session_refresh_policy': 'owner_only', 'concurrency': 4, 'rpm_limit': 50}
                assert request('PUT', f"/admin/accounts/{account['gid']}", headers=admin, json=defaults).status_code == 200
                wake(account)
                passed('S1 创建冲突不自动关联；关联保留自定义策略和养号；未关联指标动作拒绝')
                # 仅运行无提示输入的官方交互界面；所有外发仍只能到隔离代理，模型不发请求。
                launched = account['container'].exec_run(['tmux', '-L', 'process-verification', 'new-session', '-d', '-s', 'metrics',
                    'env', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1', 'ANTHROPIC_BASE_URL=http://127.0.0.1:9',
                    '/cli/2.1.293/node_modules/.bin/claude', '--dangerously-skip-permissions'], user='1000:1000')
                assert launched.exit_code == 0, '官方 CLI 夹具启动失败'
                metrics_path = account['root'] / 'runtime/process-metrics.json'
                wait_until(lambda: b'2.1.293' in account['container'].exec_run(['python3','-I','/usr/local/bin/v3-cli-control','sample']).output, '未观察到官方 CLI RSS')
                with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                    database.row_factory = sqlite3.Row
                    before = dict(database.execute('SELECT * FROM accounts WHERE id=?', (account['gid'],)).fetchone())
                before_files = [(path, hashlib.sha256(path.read_bytes()).hexdigest()) for path in (
                    account['profile'] / '.credentials.json', account['root'] / 'home/.claude/.credentials.json')]
                await evaluate(f"{doc}.querySelector('[data-cc2-process=\"{account['aid']}\"]').click()")
                await wait_for(f"{win}.eval('state.accountLoginMessage').includes('进程指标')", timeout=ACCOUNT_STARTUP_TIMEOUT)
                with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                    database.row_factory = sqlite3.Row
                    after = dict(database.execute('SELECT * FROM accounts WHERE id=?', (account['gid'],)).fetchone())
                assert all(value == after[key] for key, value in before.items() if key not in ('canonical_process', 'updated_at'))
                assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in before_files)
                observed = json.loads(after['canonical_process'])['observation']
                assert observed['rss_bytes'] > 0 and observed['source'] == 'v3:procfs:cli' and observed['sample_count'] > 0
                passed('S2 官方 CLI 容器 RSS → 按钮/API/SQLite，凭据与配置不变', rss_bytes=observed['rss_bytes'], samples=observed['sample_count'])
                account['container'].exec_run(['tmux', '-L', 'process-verification', 'kill-server'], user='1000:1000')
                for width in (1440, 720):
                    await rpc('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False}, session_id)
                    for theme in ('dark', 'light'):
                        await evaluate(f"{doc}.documentElement.dataset.theme={json.dumps(theme)};{doc}.querySelector('[data-cc2-process]').scrollIntoView({{block:'center',inline:'end'}})")
                        shot = await rpc('Page.captureScreenshot', {'format': 'png'}, session_id)
                        (output / f'actions-{width}-{theme}.png').write_bytes(base64.b64decode(shot['data']))
                actions = await evaluate(f'{win}.__actions')
                assert sum(item['path'].endswith('/cc2api/create') and item['status'] == 200 for item in actions) == 2
                assert any(item['path'].endswith('/cc2api/process') and item['status'] == 200 for item in actions)
                await evaluate("Array.from(document.querySelectorAll('a')).find(item=>item.textContent.trim()==='账号').click()")
                await wait_for("document.body.textContent.includes('官方 CLI 进程采样') && document.body.textContent.includes('CLI RSS 未采集')")
                assert await evaluate("Array.from(document.querySelectorAll('p')).filter(item=>item.textContent.includes('容器内存上限')).length") == 2
                await evaluate("Array.from(document.querySelectorAll('p')).find(item=>item.textContent.includes('容器内存上限')).scrollIntoView({block:'center'})")
                shot = await rpc('Page.captureScreenshot', {'format': 'png'}, session_id)
                (output / 'account-metrics.png').write_bytes(base64.b64decode(shot['data']))
                passed('S2 网关卡片区分容器上限、实测 RSS/时间与未采集状态')

            asyncio.run(verify_visible_logout(base, values['V3_ADMIN_PASSWORD'], exercise=exercise))
            # 浏览器退出撤销了共享管理会话，HTTP 场景重新获取本次会话。
            assert request('POST', '/admin/runtime/session', headers=admin).status_code == 200
            for account in accounts:
                response = request('POST', '/admin/tokens', headers=admin,
                    json={'name': 'synthetic-forwarding', 'allowed_accounts': str(account['gid'])})
                assert response.status_code == 201
                account['headers'] = {'Authorization': 'Bearer ' + response.json()['token'], 'User-Agent': 'python-httpx/0.28.1'}
                refreshed = request('POST', f"/admin/accounts/{account['gid']}/oauth-credentials/resolve",
                    headers=admin, json={'min_validity_seconds':60, 'force_refresh':True})
                assert refreshed.status_code == 200, '服务端 OAuth 本地刷新失败'
                assert refreshed.json()['access_token'].startswith('synthetic-refreshed-')
                refreshed.close()
                oauth = [item for item in evidence(account['network']) if item['kind'] == 'oauth-refresh']
                assert len(oauth) == 1
                assert any(item['kind'] == 'proxy' and item['target'] == 'platform.claude.com' and item['port'] == 443
                    for item in evidence(account['network']))
                passed('V3 服务端 OAuth 经本账号配置代理的实际 TLS 刷新：' + account['scheme'], count=len(oauth))
                marker = 'json-' + account['scheme']
                response = request('POST', '/api/v3-verification', headers=account['headers'], json={'marker': marker})
                assert response.status_code == 200, (response.status_code, response.text[:160])
                assert response.content == json.dumps({'marker': marker, 'ok': True}, separators=(',', ':')).encode()
                seen = evidence(account['network'])
                assert len([item for item in seen if item['kind'] == 'upstream' and item['marker'] == marker]) == 1
                assert any(item['kind'] == 'proxy' and item['peer'] == account['peer'] and item['port'] == 443 for item in seen)
                assert not any(item['kind'] == 'upstream' and item['marker'] == marker for item in evidence(accounts[1 if account is accounts[0] else 0]['network']))
                sender_records = [json.loads(line) for line in (account['root'] / 'flows/api/observations.jsonl').read_text().splitlines()]
                correlated = [item for item in sender_records if item['headers'].get('anthropic-ratelimit-unified-verify-marker') == marker]
                assert len(correlated) == 1 and correlated[0]['account_id'] == account['gid'] and correlated[0]['environment_id'] == account['eid']
                assert uuid.UUID(correlated[0]['request_id'])
                passed('S4/S5/S6 JSON 完整往返及账号隔离：' + account['scheme'], status=response.status_code,
                    response_sha256=hashlib.sha256(response.content).hexdigest(), account_id=account['gid'])
            account = accounts[0]
            with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                original = database.execute('SELECT proxy_url,access_token,refresh_token,oauth_expires_at,status FROM accounts WHERE id=?',
                    (account['gid'],)).fetchone()
            try:
                for empty_proxy in ('', ' \t'):
                    assert request('PUT', f"/admin/accounts/{account['gid']}", headers=admin,
                        json={'proxy_url': empty_proxy}).status_code == 200
                    rejected = request('POST', f"/admin/accounts/{account['gid']}/oauth-credentials/resolve",
                        headers=admin, json={'min_validity_seconds':60, 'force_refresh':True})
                    assert rejected.status_code == 503, 'v3 缺少代理必须在请求前拒绝 OAuth 刷新'
                    with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                        current = database.execute('SELECT access_token,refresh_token,oauth_expires_at,status FROM accounts WHERE id=?',
                            (account['gid'],)).fetchone()
                    assert current == original[1:], '代理配置错误不能修改合法凭据或停用账号'
            finally:
                assert request('PUT', f"/admin/accounts/{account['gid']}", headers=admin,
                    json={'proxy_url': original[0]}).status_code == 200
            passed('V3 OAuth 空白代理在请求前拒绝，凭据与账号状态保持，直连由最终内核计数核验')
            metrics_payload = {'device_id': account['top']['userID'], 'account_uuid': account['name'],
                'email': account['top']['oauthAccount']['emailAddress'], 'environment_id': account['eid'], 'cli_version': '2.1.293',
                'canonical_process': json.loads((account['root'] / 'runtime/process-metrics.json').read_text())}
            saved_process = request('GET', '/admin/accounts', headers=admin).json()['data']
            # 复用已持久化的有效载荷，避免仅测到 JSON 校验而漏测内部服务证明。
            metrics_payload['canonical_process'] = next(item for item in saved_process if item['id'] == account['gid'])['canonical_process']
            for proof in ({}, {'x-v3-service-token': 'incorrect'}):
                response = request('POST', f"/admin/accounts/{account['gid']}/cli-process/import", headers={**admin, **proof}, json=metrics_payload)
                assert response.status_code == 401
            passed('S3 指标导入拒绝缺失或伪造内部服务证明')
            response = request('POST', '/api/v3-verification', headers=account['headers'], json={'marker': 'sse-complete', 'stream': True})
            assert response.status_code == 200 and b'event: message_stop\n' in response.content
            end = wait_until(lambda: next((item for item in evidence(account['network']) if item['kind'] == 'stream-end' and item['marker'] == 'sse-complete'), None), '上游未完成 SSE')
            assert end['completed'] and end['response_sha256'] == hashlib.sha256(response.content).hexdigest()
            passed('S4 完整 SSE 字节哈希与结束标记', response_sha256=end['response_sha256'])
            # 此请求真正经过 Claude Code 改写和启用的 session 池，不能用通用路径代替。
            session_id = str(uuid.uuid4())
            payload = {'model': 'claude-sonnet-4-5', 'max_tokens': 32, 'stream': True,
                'messages': [{'role': 'user', 'content': 'claude-code-rewrite'}],
                'metadata': {'user_id': json.dumps({'device_id': 'client-device', 'account_uuid': 'client-account', 'session_id': session_id})},
                'system': [{'type': 'text', 'text': 'x-anthropic-billing-header: cc_version=0.0.1.abc; cc_entrypoint=cli; cch=00000;'}]}
            response = request('POST', '/v1/messages', headers={**account['headers'], 'User-Agent': 'claude-cli/2.1.293 (external, cli)'}, json=payload)
            assert response.status_code == 200 and b'message_stop' in response.content, response.status_code
            entry = next(item for item in evidence(account['network']) if item['kind'] == 'upstream' and item['marker'] == 'claude-code-rewrite')
            upstream_identity = json.loads(entry['metadata']['user_id'])
            assert upstream_identity['device_id'] == account['top']['userID'] and upstream_identity['account_uuid'] == account['name'], 'Claude Code 设备或账号身份未改写'
            assert entry['billing_rewritten'], 'Billing 头未按正式格式改写'
            sessions = [upstream_identity['session_id']]
            for index in range(1, 5):
                incoming = str(uuid.uuid4())
                payload['metadata']['user_id'] = json.dumps({'device_id': 'client-device', 'account_uuid': 'client-account', 'session_id': incoming})
                marker = 'claude-code-rewrite-' + str(index)
                payload['messages'][0]['content'] = marker
                response = request('POST', '/v1/messages', headers={**account['headers'], 'User-Agent': 'claude-cli/2.1.293 (external, cli)'}, json=payload)
                assert response.status_code == 200 and b'message_stop' in response.content
                entry = next(item for item in evidence(account['network']) if item['kind'] == 'upstream' and item['marker'] == marker)
                sessions.append(json.loads(entry['metadata']['user_id'])['session_id'])
                assert entry['billing_rewritten']
                if index == 4:
                    assert sessions[-1] != incoming and sessions[-1] in sessions[:-1]
            assert len(set(sessions)) == 4
            passed('S4 Claude Code 消息：Billing 重写，5 个会话被限制在 4 个池成员')
            payload['stream'] = False
            payload['messages'][0]['content'] = 'json-message-complete'
            response = request('POST', '/v1/messages', headers={**account['headers'], 'User-Agent': 'claude-cli/2.1.293 (external, cli)'}, json=payload)
            assert response.status_code == 200 and response.json()['type'] == 'message'
            assert response.json()['content'] == [{'type': 'text', 'text': 'json-message-complete'}]
            assert response.json()['stop_reason'] == 'end_turn'
            end = next(item for item in evidence(account['network']) if item['kind'] == 'json-response' and item['marker'] == 'json-message-complete')
            assert end['response_sha256'] == hashlib.sha256(response.content).hexdigest(), '非流式消息响应字节发生意外变化'
            passed('S4 非流式 /v1/messages：完整消息 JSON 与上游字节哈希一致', response_sha256=end['response_sha256'])
            lease_path = f"/admin/runtime/accounts/{account['gid']}/lease"
            lease = request('POST', lease_path, headers=admin, json={'operation': 'prepare-cli', 'owner': 'run:forwarding-shared'}).json()['lease']
            assert request('POST', lease_path, headers=admin, json={'operation': 'claim', 'owner': lease['owner'], 'generation': lease['generation']}).status_code == 200
            try:
                launched = account['container'].exec_run(['tmux', '-L', 'shared-verification', 'new-session', '-d', '-s', 'shared',
                    'env', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1', 'ANTHROPIC_BASE_URL=http://127.0.0.1:9',
                    '/cli/2.1.293/node_modules/.bin/claude', '--dangerously-skip-permissions'], user='1000:1000')
                assert launched.exit_code == 0
                probe = "import sys;sys.path.insert(0,'/usr/local/bin');from process_metrics import cli_processes;print(any(version=='2.1.293' for version,rss in cli_processes()))"
                wait_until(lambda: account['container'].exec_run(['python3', '-c', probe]).output.strip() == b'True', '共享场景没有实际官方 CLI 进程')
                assert request('POST', '/api/v3-verification', headers=account['headers'], json={'marker': 'shared-cli'}).status_code == 200
                assert account['container'].exec_run(['python3', '-c', probe]).output.strip() == b'True', 'API 响应前 CLI 已退出'
            finally:
                account['container'].exec_run(['tmux', '-L', 'shared-verification', 'kill-server'], user='1000:1000')
                request('POST', lease_path, headers=admin, json={'operation': 'release', 'owner': lease['owner'], 'generation': lease['generation']})
            passed('S6 共享租约与实际官方 CLI 进程存活期间，正式 API 可转发')
            response = request('POST', '/api/v3-verification', headers=account['headers'], json={'marker': 'slow-complete', 'stream': True})
            assert response.status_code == 200 and b'event: message_stop\n' in response.content
            end = wait_until(lambda: next((item for item in evidence(account['network']) if item['kind'] == 'stream-end' and item['marker'] == 'slow-complete'), None), '慢流未完整收口')
            assert end['completed'] and end['response_sha256'] == hashlib.sha256(response.content).hexdigest()
            with request('POST', '/api/v3-verification', headers=account['headers'], json={'marker': 'slow-cancel', 'stream': True}, stream=True) as response:
                assert response.status_code == 200
                # urllib3 的分块读取器被回收时会关闭连接；保留它才能真的验证在途拒绝。
                chunks = response.iter_content(chunk_size=1)
                next(chunks)
                assert request('GET', lease_path, headers=admin).json()['active'] > 0, '慢流未保持在途占用'
                with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                    process_before = database.execute('SELECT canonical_process FROM accounts WHERE id=?', (account['gid'],)).fetchone()
                rejected = request('POST', f"/runtime/api/accounts/{account['aid']}/cc2api/process")
                assert rejected.status_code in (409, 502), ('在途指标更新应拒绝', rejected.status_code)
                with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                    assert database.execute('SELECT canonical_process FROM accounts WHERE id=?', (account['gid'],)).fetchone() == process_before
            wait_until(lambda: request('GET', lease_path, headers=admin).json()['active'] == 0, '取消后网关活动计数未归零')
            status_code = "import json,urllib.request;c=json.load(open('/run/v3/sender.json'));r=urllib.request.Request('http://127.0.0.1:8091/internal/status',headers={'Authorization':'Bearer '+c['binding']['secret']});print(json.load(urllib.request.urlopen(r))['active'])"
            wait_until(lambda: account['sender_container'].exec_run(['python3', '-c', status_code]).output.strip() == b'0', '取消后发送器活动计数未归零')
            assert len([item for item in evidence(account['network']) if item['kind'] == 'upstream' and item['marker'] == 'slow-cancel']) == 1
            cancelled = wait_until(lambda: next((item for item in evidence(account['network']) if item['kind'] == 'stream-end' and item['marker'] == 'slow-cancel'), None), '取消未传播到隔离上游')
            assert not cancelled['completed'], '已取消的流被当成正常结束'
            passed('S7 慢流完整结束/取消：两端 active 归零，取消传播到上游，无重放')
            cached_sender_started = account['sender_container'].attrs['State']['StartedAt']
            with request('POST', '/api/v3-verification', headers=account['headers'], json={'marker':'slow-restart','stream':True}, stream=True) as response:
                assert response.status_code == 200
                chunks = response.iter_content(chunk_size=1)
                received = next(chunks)
                # 绑定维护可能早已停止/唤醒同一实例；以本次流已入场后的实际状态作比较基线。
                account['sender_container'].reload()
                sender_started = account['sender_container'].attrs['State']['StartedAt']
                if cached_sender_started != sender_started:
                    print('重启场景实时基线：' + json.dumps({'cached_started_at':cached_sender_started,
                        'stream_started_at':sender_started}), flush=True)
                orchestrator.restart(timeout=5)
                wait_until(lambda: request('GET','/runtime/api/environments').status_code == 200, '实际调度器重启未恢复', seconds=60)
                assert request('GET', lease_path, headers=admin).json()['active'] > 0, '重启结束前 API 长流已丢失'
                received += b''.join(chunks)
                assert b'event: message_stop\n' in received
            account['sender_container'].reload()
            assert account['sender_container'].attrs['State']['StartedAt'] == sender_started
            completed = wait_until(lambda: next((item for item in evidence(account['network']) if item['kind']=='stream-end' and item['marker']=='slow-restart'),None), '重启场景长流未收口')
            assert completed['completed'] and completed['response_sha256'] == hashlib.sha256(received).hexdigest()
            passed('V6 实际重启 orchestrator，健康 sender 与 API 长流保留且字节哈希一致')
            before = len([item for item in evidence(account['network']) if item['kind'] == 'upstream'])
            rule = ['INPUT', '-p', 'tcp', '--dport', '8091', '-m', 'string', '--algo', 'bm',
                '--string', 'POST /internal/send', '-j', 'REJECT', '--reject-with', 'tcp-reset']
            assert account['network_container'].exec_run(['iptables', '-I', *rule]).exit_code == 0
            try:
                response = request('POST', '/api/v3-verification', headers=account['headers'], json={'marker': 'reject-sender-unreachable'})
                assert response.status_code == 502
                assert len([item for item in evidence(account['network']) if item['kind'] == 'upstream']) == before
            finally:
                assert account['network_container'].exec_run(['iptables', '-D', *rule]).exit_code == 0
            passed('S8 真实发送路径不可达：正式 API 明确失败，无管理端直连回退')
            # 每个故障先关闭连接池中的旧连接，确保新 TLS/代理连接确实命中故障夹具。
            for mode in ('untrusted', 'hostname', 'proxy', 'unreachable'):
                before = len([item for item in evidence(account['network']) if item['kind'] == 'upstream'])
                account['sender_container'].restart(timeout=5)
                wait_until(lambda: account['sender_container'].exec_run(['python3', '-c', status_code]).output.strip() == b'0', '故障场景发送器未就绪')
                proxy_rule = ['INPUT', '-p', 'tcp', '--dport', '1081', '-j', 'REJECT', '--reject-with', 'tcp-reset']
                if mode == 'unreachable':
                    code = 'import subprocess;subprocess.run(' + repr(['iptables', '-I', *proxy_rule]) + ',check=True)'
                    client.containers.run(values['V3_ACCOUNT_IMAGE'], ['-c', code], entrypoint='python3',
                        network_mode='container:' + proxies[0].id, cap_add=['NET_ADMIN'], remove=True,
                        labels={**labels, 'vibebench.role': 'verification'})
                elif mode == 'proxy':
                    (account['network'] / 'proxy-fail').touch()
                else:
                    (account['network'] / 'tls-mode').write_text(mode)
                try:
                    response = request('POST', '/api/v3-verification', headers=account['headers'], json={'marker': 'reject-' + mode})
                    assert response.status_code in (502, 503), (mode, response.status_code)
                    assert len([item for item in evidence(account['network']) if item['kind'] == 'upstream']) == before
                finally:
                    (account['network'] / 'proxy-fail').unlink(missing_ok=True)
                    (account['network'] / 'tls-mode').unlink(missing_ok=True)
                    if mode == 'unreachable':
                        code = 'import subprocess;subprocess.run(' + repr(['iptables', '-D', *proxy_rule]) + ',check=True)'
                        client.containers.run(values['V3_ACCOUNT_IMAGE'], ['-c', code], entrypoint='python3',
                            network_mode='container:' + proxies[0].id, cap_add=['NET_ADMIN'], remove=True,
                            labels={**labels, 'vibebench.role': 'verification'})
                passed('S5/S8 拒绝错误证书/代理且无上游重放：' + mode, status=response.status_code)
            before = len([item for item in evidence(account['network']) if item['kind'] == 'upstream'])
            # 直接请求仍由真实发送器校验，不用 Python 重写校验逻辑来冒充服务端拒绝。
            for fault in ('account', 'generation', 'target', 'secret'):
                code = """import base64,json,time,uuid,urllib.request,urllib.error
c=json.load(open('/run/v3/sender.json'));b=c['binding']
p={'account_id':b['account_id'],'environment_id':b['environment_id'],'generation':b['generation'],
'request_id':str(uuid.uuid4()),'deadline_unix_ms':int(time.time()*1000)+10000,'method':'POST',
'target_url':'https://api.anthropic.com/api/v3-verification','headers':[['content-type','application/json']],'preserve_header_casing':True}
fault=FAULT
if fault=='account':p['account_id']+=1
if fault=='generation':p['generation']+=1
if fault=='target':p['target_url']='https://wrong.invalid/api/v3-verification'
r=urllib.request.Request('http://127.0.0.1:8091/internal/send',data=b'{}',headers={'Authorization':'Bearer '+('incorrect' if fault=='secret' else b['secret']),'x-v3-request':base64.b64encode(json.dumps(p).encode()).decode()})
try:urllib.request.urlopen(r);raise AssertionError('错误发送被接受')
except urllib.error.HTTPError as error:print(json.dumps({'status':error.code,'phase':error.headers.get('x-v3-transport-error')}))
""".replace('FAULT', repr(fault))
                result = account['sender_container'].exec_run(['python3', '-c', code])
                assert result.exit_code == 0, '发送器拒绝场景执行失败'
                rejected = json.loads(result.output)
                assert rejected['phase'] == 'before-send' and rejected['status'] in (400, 401)
            assert len([item for item in evidence(account['network']) if item['kind'] == 'upstream']) == before
            configuration_path = account['root'] / 'runtime/sender/sender.json'
            original = json.loads(configuration_path.read_text())
            changed = copy.deepcopy(original)
            changed['binding']['generation'] += 1
            manage_file = configuration_path.with_suffix('.verification')
            manage_file.write_text(json.dumps(changed))
            manage_file.chmod(0o640)
            os.chown(manage_file,0,1001)
            manage_file.replace(configuration_path)
            try:
                response = request('POST', '/api/v3-verification', headers=account['headers'], json={'marker': 'reject-binding'})
                assert response.status_code == 503
                assert len([item for item in evidence(account['network']) if item['kind'] == 'upstream']) == before
            finally:
                manage_file.write_text(json.dumps(original))
                manage_file.chmod(0o640)
                os.chown(manage_file,0,1001)
                manage_file.replace(configuration_path)
            passed('S8 错误身份/代次/目标/秘密在发送前拒绝；正式 API 绑定故障无直连回退')
            code = "import subprocess;v=subprocess.check_output(['iptables','-nvxL','V3VERIFY'],text=True);print(sum(int(line.split()[0]) for line in v.splitlines() if line.split() and line.split()[0].isdigit()))"
            attempts = client.containers.run(values['V3_ACCOUNT_IMAGE'], ['-c', code], entrypoint='python3',
                network_mode='container:' + gateway.id, cap_add=['NET_ADMIN'], remove=True,
                labels={**labels, 'vibebench.role': 'verification'}).decode().strip()
            assert attempts == '0', '网关尝试了容器链路之外的公网连接'
            passed('S8 管理端公网被阻断，全部场景中直连尝试计数为零', external_attempts=0)
            (output / 'results.json').write_text(json.dumps({'release': manifest['release'], 'test_build_difference': manifest['verification_only'],
                'scenes': results, 'real_anthropic_inference': '未验证：需要可用账号，隔离上游成功不代表真实推理'}, ensure_ascii=False, indent=2) + '\n')
            for index, account in enumerate(accounts):
                (output / f'network-{index}.json').write_text(json.dumps(evidence(account['network']), ensure_ascii=False, indent=2))
                shutil.copy2(account['root'] / 'runtime/process-metrics.json', output / f'process-{index}.json')
                shutil.copy2(account['root'] / 'flows/api/observations.jsonl', output / f'sender-{index}.jsonl')
        finally:
            (output / 'partial-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
            # 失败场景也保留脱敏证据，先定位偏差再清理本次隔离资源。
            for index, account in enumerate(accounts):
                (output / f'network-{index}.json').write_text(json.dumps(evidence(account['network']), ensure_ascii=False, indent=2))
                for relative, name in (('runtime/process-metrics.json', f'process-{index}.json'), ('flows/api/observations.jsonl', f'sender-{index}.jsonl')):
                    source = account['root'] / relative
                    if source.exists():
                        shutil.copy2(source, output / name)
            for container in client.containers.list(all=True, filters=filters):
                container.remove(force=True)
            for network in client.networks.list(filters=filters):
                network.remove()
            session.close()
            assert not client.containers.list(all=True, filters=filters), '本次测试容器未清理'


def main():
    """解析显式测试构建和验收参数。

    :return: None。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--release')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--cli-binary', type=Path)
    args = parser.parse_args()
    if args.build:
        build_verification(args.release or 'verify-' + uuid.uuid4().hex[:16], args.manifest)
    else:
        if not args.output or not args.cli_binary:
            parser.error('验收需要 --output 和 --cli-binary')
        verify(args.manifest, args.output, args.cli_binary)


if __name__ == '__main__':
    main()
