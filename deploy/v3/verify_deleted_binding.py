"""真实堆栈验证远端删除后页面解绑，仅使用独立合成资料。"""
import json
import shutil
import sqlite3
import time
from contextlib import contextmanager

from manage import REPO


@contextmanager
def deleted_binding_fixture(client, deployment, data, manifest, browser, base, authorization):
    """准备合成账号并提供删除、解绑与数据库交叉核对场景。

    :param client: Docker 客户端。
    :param deployment: 本次随机部署。
    :param data: 本次独立数据根。
    :param manifest: 同批正式镜像清单。
    :param browser: 已登录的本次 HTTP 客户端。
    :param base: 本次回环管理地址。
    :param authorization: 合成管理员请求头。
    :return: 真实浏览器操作回调；结束清理本次合成记录。
    """
    name = 'deleted-binding-fixture'
    network_data = data / 'synthetic-unbind-network'
    network_data.mkdir()
    proxy = client.containers.run(manifest['images']['control']['reference'], ['/fixtures/mock_network.py'],
        entrypoint='python', detach=True, network='vibebench-v3-' + deployment,
        labels={'vibebench.product': 'v3', 'vibebench.deployment': deployment, 'vibebench.role': 'verification'},
        volumes={str(REPO / 'deploy/v3/fixtures'): {'bind': '/fixtures', 'mode': 'ro'},
                 str(network_data): {'bind': '/fixtures-data', 'mode': 'rw'}})
    aid = None
    gid = None
    eid = None
    try:
        proxy.reload()
        address = next(iter(proxy.attrs['NetworkSettings']['Networks'].values()))['IPAddress']
        with sqlite3.connect(data / 'bench/db.sqlite') as database:
            aid = database.execute('INSERT INTO accounts(name,profile_path,upstream_proxy_scheme,'
                'upstream_socks5_host,upstream_socks5_port,enabled,warmup_enabled) VALUES(?,?,?,?,?,1,0)',
                (name, 'profiles/' + name, 'socks5h', address, 1080)).lastrowid
        orchestrator = client.containers.list(filters={'label': ['vibebench.deployment=' + deployment,
            'vibebench.role=orchestrator']})[0]
        # exec 进程不经过 lifespan；复用真实运行时构造环境行，不手写表结构。
        code = "import main,docker;from account_runtime import AccountRuntime;r=AccountRuntime(docker.from_env(),main.BENCH_DATA,main.HOST_BENCH_DATA,main.get_db,main.derive_v3_fingerprint,main.cc2api_client);print(r._row(" + repr(name) + ',' + str(aid) + ")[\"environment_id\"]);r.heartbeat_pool.shutdown()"
        result = orchestrator.exec_run(['python', '-c', code])
        assert result.exit_code == 0, '合成环境创建失败'
        eid = result.output.decode().strip().splitlines()[-1]
        assert len(eid) == 32
        env_root = data / 'bench/environments' / eid
        home = env_root / 'home'
        profile = data / 'bench/profiles' / name
        top = {'userID': 'd' * 64, 'oauthAccount': {'emailAddress': 'unbind@example.invalid',
            'accountUuid': 'synthetic-unbind-account', 'organizationUuid': 'synthetic-unbind-org'}}
        credentials = {'claudeAiOauth': {'accessToken': 'synthetic-unbind-access',
            'refreshToken': 'synthetic-unbind-refresh', 'expiresAt': int(time.time() * 1000) + 3600000}}
        for folder in (home, profile):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / '.claude.json').write_text(json.dumps(top))
        (profile / '.credentials.json').write_text(json.dumps(credentials))
        cached = env_root / 'cli/2.1.293/node_modules/.bin/claude'
        cached.parent.mkdir(parents=True)
        shutil.copy2(REPO / 'deploy/v3/fixtures/mock_cli.py', cached)
        cached.chmod(0o755)
        (cached.parents[2] / '.ready').touch()
        response = browser.post(base + f'/runtime/api/accounts/{aid}/cc2api/create', timeout=90)
        assert response.status_code == 200, response.status_code
        gid = response.json()['cc2api_account']['id']
        protected = [profile / '.credentials.json', profile / '.claude.json',
            home / '.claude/.credentials.json', home / '.claude.json']
        original_files = {str(path): json.loads(path.read_text()) for path in protected}
        with sqlite3.connect(data / 'bench/db.sqlite') as database:
            original_environment = database.execute('SELECT environment_id,fingerprint_json FROM account_environments WHERE account_id=?', (aid,)).fetchone()

        async def exercise(rpc, evaluate, wait_for, session_id):
            """点击正式解绑按钮，并核对 HTTP 结果、两库与持久身份。

            :param rpc: 本次 CDP 调用器。
            :param evaluate: 页面求值函数。
            :param wait_for: 有界等待函数。
            :param session_id: 本次浏览器页面。
            :return: None；不满足验收时立即失败。
            """
            doc = "document.querySelector('iframe').contentDocument"
            win = "document.querySelector('iframe').contentWindow"
            await wait_for(f"Boolean({doc}?.querySelector('[data-cc2-unbind=\"{aid}\"]') && {doc}.querySelector('#accounts-body').onclick)")
            await evaluate(f"{{const w={win},original=w.fetch;w.__unbindResponses=[];w.__unbindAlerts=[];w.confirm=()=>true;w.alert=m=>w.__unbindAlerts.push(m);w.fetch=async(...args)=>{{const r=await original(...args);if(String(args[0]).includes('/cc2api-binding'))w.__unbindResponses.push(r.status);return r}}}}")
            # 通过正式删除 API 产生悬空绑定；不直接删远端数据库绕过配置门禁。
            response = browser.delete(base + f'/admin/accounts/{gid}', headers=authorization, timeout=30)
            assert response.status_code == 200, response.status_code
            with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                assert database.execute('SELECT count(*) FROM accounts WHERE id=?', (gid,)).fetchone()[0] == 0
            with sqlite3.connect(data / 'bench/db.sqlite') as database:
                assert database.execute('SELECT cc2api_account_id FROM accounts WHERE id=?', (aid,)).fetchone()[0] == gid
            # 发布会重启调度器；即使旧绑定进入待对账状态，显式解绑也应完成安全收口。
            orchestrator.restart(timeout=5)
            deadline = time.monotonic() + 30
            while True:
                try:
                    response = browser.get(base + '/runtime/api/environments', timeout=5)
                    if response.status_code == 200:
                        break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise AssertionError('合成调度器重启后未就绪')
                time.sleep(0.2)
            await evaluate(f"{doc}.querySelector('[data-cc2-unbind=\"{aid}\"]').click()")
            await wait_for(f"Boolean({doc}.querySelector('[data-cc2-create=\"{aid}\"]'))")
            assert await evaluate(f"{win}.__unbindResponses") == [200]
            assert not await evaluate(f"{win}.__unbindAlerts")
            assert await evaluate(f"Boolean({doc}.querySelector('[data-cc2-bind=\"{aid}\"]'))")
            with sqlite3.connect(data / 'bench/db.sqlite') as database:
                assert database.execute('SELECT cc2api_account_id,warmup_enabled,warmup_next_run_at,warmup_last_status FROM accounts WHERE id=?', (aid,)).fetchone() == (None, 0, None, 'off')
                assert database.execute('SELECT environment_id,fingerprint_json FROM account_environments WHERE account_id=?', (aid,)).fetchone() == original_environment
                assert database.execute('SELECT state FROM account_environments WHERE account_id=?', (aid,)).fetchone()[0] == 'stopped'
            assert browser.delete(base + f'/runtime/api/accounts/{aid}/cc2api-binding', timeout=30).status_code == 200
            assert all(json.loads(path.read_text()) == original_files[str(path)] for path in protected)
            assert not (network_data / 'usage-calls.jsonl').exists(), '解绑不应查询上游额度'
            print('通过：正式远端删除→调度器重启→真实页面解绑 HTTP 200→SQLite 清空绑定/关闭养号→创建/关联按钮恢复；重复解绑及 HOME/凭据/设备保留')

        yield exercise
    finally:
        # 测试删除不可恢复，只清理本次随机部署的数据与实例，不操作生产。
        proxy.remove(force=True)
        if eid is not None:
            for container in client.containers.list(all=True, filters={'label': [
                    'vibebench.deployment=' + deployment, 'vibebench.environment=' + eid]}):
                container.remove(force=True)
        if aid is not None:
            with sqlite3.connect(data / 'bench/db.sqlite') as database:
                database.execute('DELETE FROM account_environments WHERE account_id=?', (aid,))
                database.execute('DELETE FROM accounts WHERE id=?', (aid,))
        if gid is not None:
            with sqlite3.connect(data / 'gateway/gateway.sqlite') as database:
                database.execute('DELETE FROM accounts WHERE id=?', (gid,))
