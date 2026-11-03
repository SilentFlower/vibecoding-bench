"""真实 HTTP、两侧 SQLite 和账号容器的合成交接演练。"""
import json
import re
import sqlite3
import subprocess
from contextlib import contextmanager

from verify_reauth_stack import reauth_fixture


@contextmanager
def ownership_fixture(client, deployment, data, manifest, browser, base, authorization):
    """复用隔离登录基础设施，只访问本次合成账号。

    :param client: 本地 Docker 客户端。
    :param deployment: 随机部署。
    :param data: 独立空数据根。
    :param manifest: 联合镜像清单。
    :param browser: 已鉴权 HTTP 会话。
    :param base: 真实网关地址。
    :param authorization: 本次管理鉴权。
    :return: Chrome 场景回调。
    """
    with reauth_fixture(client, deployment, data, manifest, browser, base, authorization):
        bench, gateway = data / 'bench/db.sqlite', data / 'gateway/gateway.sqlite'
        with sqlite3.connect(bench) as database:
            account_id, remote_id = database.execute("SELECT id,cc2api_account_id FROM accounts WHERE name='reauth-ui-fixture'").fetchone()
            environment_id, = database.execute('SELECT environment_id FROM account_environments WHERE account_id=?', (account_id,)).fetchone()
        environment = data / 'bench/environments' / environment_id
        home = environment / 'home'
        original_top = (home / '.claude.json').read_bytes()
        (home / '.claude/cache-preserved').write_bytes(b'synthetic cache unchanged')
        with sqlite3.connect(gateway) as database:
            database.execute("UPDATE accounts SET status='active',auth_error='',disable_reason='',rate_limited_at=NULL,rate_limit_reset_at=NULL WHERE id=?", (remote_id,))
        orchestrator = client.containers.list(filters={'label': [f'vibebench.deployment={deployment}', 'vibebench.role=orchestrator']})[0]

        def request(method, path, **kwargs):
            return browser.request(method, base + path, timeout=90, **kwargs)

        def native(code):
            # 独立控制进程执行生产协调器；退出后由在线 API 按持久回执恢复。
            setup = f"""import main,docker,json
from account_runtime import AccountRuntime
from credential_ownership import CredentialOwnership
main.runner=main.Runner()
r=AccountRuntime(main.runner.client,main.BENCH_DATA,main.HOST_BENCH_DATA,main.get_db,main.derive_v3_fingerprint,main.cc2api_client)
main.account_runtime=r
o=CredentialOwnership(r,main.cc2api_client,main.get_db,main._db_lock,read_profile=main._read_bench_profile_identity,mirror=main._sync_cc2api_credentials_to_profile,mirror_locked=main._sync_cc2api_credentials_to_profile_locked,profile_lock=main._profile_lock,identity=main._v3_cli_identity,read_identity=main._v3_cli_identity_readonly,validate=main._validate_cc2api_identity,find=main._find_cc2api_account_for_profile,idle=main._require_oauth_owner_transition_idle,available=main._require_cc2api_binding_available,creation_payload=main._cc2api_creation_payload,refresh=main.runner.refresh_account_oauth_token)
main.credential_ownership=o
r.credential_ownership=o
a=o._account({account_id})
try:
"""
            script = setup + ''.join('    ' + line + '\n' for line in code.splitlines()) + '\nfinally:\n    r.heartbeat_pool.shutdown()\n'
            result = orchestrator.exec_run(['python', '-c', script])
            if result.exit_code:
                text = result.output.decode(errors='replace')
                frames = re.findall(r'File "([^"]+)", line (\d+)', text)[-4:]
                errors = re.findall(r'^([A-Za-z][A-Za-z0-9]*Error):', text, re.MULTILINE)
                raise AssertionError(f'隔离控制进程未完成：{errors} {frames}；不打印凭据或响应正文')

        async def exercise(rpc, evaluate, wait_for, session_id):
            """核对解绑、真实 HTTPS 轮换、回交、回包丢失和可见状态。

            :param rpc: CDP 命令。
            :param evaluate: 浏览器表达式。
            :param wait_for: 有界页面等待。
            :param session_id: 本次 Chrome 会话。
            :return: None；失败时抛错。
            """
            doc, win = "document.querySelector('iframe').contentDocument", "document.querySelector('iframe').contentWindow"
            assert request('DELETE', f'/runtime/api/accounts/{account_id}/cc2api-binding').status_code == 200
            assert request('PUT', f'/admin/accounts/{remote_id}', headers=authorization,
                json={'rpm_limit': 23, 'concurrency': 3, 'priority': 71}).status_code == 200
            evidence = data / 'synthetic-network/tls.jsonl'
            before = evidence.read_bytes() if evidence.exists() else b''
            token = request('POST', '/admin/tokens', headers=authorization,
                json={'name': 'ownership-fixture', 'allowed_accounts': str(remote_id)}).json()
            api_headers = {'Authorization': 'Bearer ' + token['token'], 'User-Agent': 'claude-cli/2.1.293 (external, cli)'}
            for path in ('/v1/messages', '/v1/messages/count_tokens'):
                response = request('POST', path, headers=api_headers,
                    json={'model': 'claude-sonnet-5', 'max_tokens': 1, 'messages': [{'role': 'user', 'content': 'synthetic'}]})
                assert response.status_code == 503, (path, response.status_code)
            assert request('POST', f'/admin/accounts/{remote_id}/test', headers=authorization).status_code == 503
            response = request('POST', f'/admin/accounts/{remote_id}/usage', headers=authorization)
            assert response.status_code == 200 and response.json()['status'] == 'error'
            native(f"""try:
    main.cc2api_client.resolve_credentials({remote_id},60,True)
except (ValueError,ConnectionError) as error:
    assert getattr(error.__cause__,'code',None)==503
else:
    raise AssertionError('已解绑账号不应允许刷新')""")
            assert before == (evidence.read_bytes() if evidence.exists() else b''), '暂停入口建立了上游连接'
            await evaluate(f'{win}.location.hash="#accounts";{win}.renderAccounts()')
            await wait_for(f'{doc}.body.textContent.includes("本地管理，cc2api 已暂停")')
            print('通过：暂停后的模型、count_tokens、测试、额度、强制刷新零上游连接；普通配置仍可编辑')

            network = data / 'synthetic-network'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-keyout', str(network / 'native-usage.key'), '-out', str(network / 'native-usage.crt'),
                '-subj', '/CN=platform.claude.com', '-addext', 'subjectAltName=DNS:platform.claude.com,DNS:api.anthropic.com'],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            (network / 'usage-tls.enabled').touch()
            (network / 'ownership-oauth.json').write_text(json.dumps({'expected_refresh': 'old-refresh', 'number': 0}))
            proxy = client.containers.list(filters={'label': [f'vibebench.deployment={deployment}', 'vibebench.role=verification']})[0]
            proxy.restart(timeout=3)
            with sqlite3.connect(bench) as database:
                database.execute('UPDATE accounts SET enabled=1 WHERE id=?', (account_id,))
            native('r.ensure(a)')
            # CLI 根文件系统保持只读；只在本次 exec 的环境注入本地测试根，不关闭证书校验。
            certificate = home / '.ownership-fixture-ca.pem'
            certificate.write_bytes((network / 'native-usage.crt').read_bytes())
            certificate.chmod(0o444)
            for number in (1, 2, 3):
                native("""original_env=main._claude_exec_env
main._claude_exec_env=lambda *args,**kwargs: {**original_env(*args,**kwargs),'NODE_EXTRA_CA_CERTS':'/home/node/.ownership-fixture-ca.pem'}
assert main.runner.refresh_account_oauth_token(a,force_refresh=True)""")
                assert json.loads((home / '.claude/.credentials.json').read_text())['claudeAiOauth']['refreshToken'] == f'ownership-local-rt-{number}'
            assert all(value['accepted'] and value['tls'] for value in
                map(json.loads, (network / 'ownership-oauth-calls.jsonl').read_text().splitlines()))
            response = request('POST', f'/runtime/api/accounts/{account_id}/cc2api/bind', json={'cc2api_account_id': remote_id})
            assert response.status_code == 200, response.status_code
            with sqlite3.connect(gateway) as database:
                assert database.execute('SELECT refresh_token,rpm_limit,concurrency,priority FROM accounts WHERE id=?', (remote_id,)).fetchone() == ('ownership-local-rt-3', 23, 3, 71)
            assert 'refreshToken' not in json.loads((home / '.claude/.credentials.json').read_text())['claudeAiOauth']
            assert (home / '.claude.json').read_bytes() == original_top
            assert (home / '.claude/cache-preserved').read_bytes() == b'synthetic cache unchanged'
            print('通过：真实 Node HTTPS 连续轮换三次，重绑原 ID、最新 RT、AT-only HOME，配置/设备/缓存保留')

            with sqlite3.connect(bench) as database:
                database.execute('UPDATE accounts SET enabled=0 WHERE id=?', (account_id,))
            native("""original=main.cc2api_client._request
def request_lost(method,path,payload=None):
    value=original(method,path,payload)
    if path.endswith('/oauth-ownership') and method=='POST' and payload['action']=='commit':
        raise ConnectionError('合成提交回包丢失')
    return value
main.cc2api_client._request=request_lost
try:
    o.detach(a)
except ConnectionError:
    pass
else:
    raise AssertionError('未注入回包丢失')
assert o.state(a['id'])['phase']=='handoff'""")
            await evaluate(f'{win}.renderAccounts()')
            await wait_for(f'{doc}.body.textContent.includes("凭据交接中")')
            result = request('POST', f'/runtime/api/environments/{environment_id}/maintenance', json={'operation': 'reconcile'})
            assert result.status_code == 200, result.status_code
            with sqlite3.connect(bench) as database:
                state, = database.execute('SELECT record_json FROM account_credential_ownerships WHERE account_id=?', (account_id,)).fetchone()
                assert json.loads(state)['owner'] == 'local' and json.loads(state)['phase'] == 'ready'
                # 故障注入期间停用本地调度；对账后恢复原准入条件再显式关联。
                database.execute('UPDATE accounts SET enabled=1 WHERE id=?', (account_id,))
            response = request('POST', f'/runtime/api/accounts/{account_id}/cc2api/bind', json={'cc2api_account_id': remote_id})
            assert response.status_code == 200, response.status_code
            assert 'refreshToken' not in json.loads((home / '.claude/.credentials.json').read_text())['claudeAiOauth']
            print('通过：真实提交回包丢失后控制进程退出，在线 API 按持久回执恢复并重绑原账号')
            (data / 'bench/profiles/reauth-ui-fixture/.credentials.json').write_text('{}')
            result = request('DELETE', f'/runtime/api/accounts/{account_id}')
            assert result.status_code == 200 and result.json()['soft_deleted'], result.status_code
            with sqlite3.connect(bench) as database:
                assert database.execute('SELECT deleted_at IS NOT NULL FROM accounts WHERE id=?', (account_id,)).fetchone() == (1,)
            with sqlite3.connect(gateway) as database:
                state, = database.execute('SELECT record_json FROM oauth_account_ownerships WHERE account_id=?', (remote_id,)).fetchone()
                assert json.loads(state)['owner'] == 'local'
            assert (home / '.claude/cache-preserved').read_bytes() == b'synthetic cache unchanged'
            print('通过：凭据不完整仍可显式删除本地账号；远端暂停、原 ID 和 HOME 历史保留')
        yield exercise

