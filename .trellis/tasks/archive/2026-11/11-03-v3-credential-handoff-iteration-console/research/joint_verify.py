"""在原隔离交接流程前，补充同账号双工程视图的真实维护状态验证。"""
import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / 'deploy/v3'))
import verify_credential_ownership
import verify_stack


@contextmanager
def joint_fixture(client, deployment, data, manifest, browser, base, authorization):
    """组合既有真实账号/网关/CLI 夹具，不修改产品或原验证器。

    :param client: 隔离 Docker 客户端。
    :param deployment: 随机部署。
    :param data: 隔离数据根。
    :param manifest: 联合清单。
    :param browser: 鉴权 HTTP 会话。
    :param base: 本地网关入口。
    :param authorization: 合成管理鉴权。
    :return: 先联合维护、再执行完整交接的 Chrome 场景。
    """
    with original_fixture(client, deployment, data, manifest, browser, base, authorization) as original:
        database = data / 'bench/db.sqlite'
        with sqlite3.connect(database) as connection:
            aid, binding, enabled = connection.execute("SELECT id,cc2api_account_id,enabled FROM accounts WHERE name='reauth-ui-fixture'").fetchone()
            # 原认证夹具停用账号以隔离后台调度；页面联合场景需要有效选择，结束后恢复原条件。
            connection.execute('UPDATE accounts SET enabled=1 WHERE id=?', (aid,))
        catalog = browser.get(base + '/runtime/api/projects/catalog', timeout=10)
        catalog.raise_for_status()
        key = catalog.json()['projects'][0]['project_key']
        for endpoint in ('/projects', '/accounts/warmup/pi'):
            response = browser.put(base + f'/runtime/api{endpoint}/agents/{aid}',
                json={'project_keys': [key], 'instructions': '联合维护只读验证', 'budget_sec': 3600}, timeout=10)
            response.raise_for_status()

        def facts():
            """仅比较导航涉及的业务事实，不收集令牌。@return 两空间配置/工作/输入行。"""
            with sqlite3.connect(database) as connection:
                return {table: connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
                    for prefix in ('', 'warmup_') for name in ('agents', 'work', 'actions', 'submissions')
                    for table in [prefix + 'projects_' + name]}

        async def exercise(rpc, evaluate, wait_for, session_id):
            """真实重授权维护期切换视图并核对拒绝事实，取消后继续原交接套件。

            :param rpc: Chrome CDP。
            :param evaluate: 页面执行器。
            :param wait_for: 有界条件等待。
            :param session_id: 当前浏览器会话。
            :return: None；失败即停止。
            """
            response = browser.post(base + '/runtime/api/accounts/login/start',
                json={'name': 'reauth-ui-fixture', 'force_reauth': True}, timeout=90)
            response.raise_for_status()
            sid = response.json()['session_id']
            doc = "document.querySelector('iframe').contentDocument"
            win = doc + '.defaultView'
            baseline = facts()
            try:
                for mode, endpoint in (('projects', '/projects'), ('warmup', '/accounts/warmup/pi')):
                    response = browser.get(base + '/runtime/api' + endpoint, timeout=10)
                    response.raise_for_status()
                    agent = next(item for item in response.json()['agents'] if item['account_id'] == aid)
                    assert agent['admission']['allowed'] is False
                    assert agent['admission']['reason'] == 'credential_ownership'
                    await evaluate(f'{win}.location.hash="#{mode}?account={aid}"')
                    await wait_for(f'{doc}.querySelector("#projects-account")?.value==="{aid}" && '
                        f'{doc}.querySelector("#projects-admission")?.textContent.includes("账号凭据正在交接")')
                    assert await evaluate(f'{doc}.querySelector("[data-iteration-mode={mode}]").getAttribute("aria-current")') == 'page'
                assert facts() == baseline, '维护期间切换改写了工程事实'
            finally:
                response = browser.delete(base + f'/runtime/api/accounts/login/{sid}', timeout=30)
                assert response.status_code == 200
            accounts = browser.get(base + '/runtime/api/accounts', timeout=10).json()
            account = next(item for item in accounts if item['id'] == aid)
            assert account['cc2api_account_id'] == binding
            assert account['credential_ownership']['phase'] == 'ready'
            assert facts() == baseline
            with sqlite3.connect(database) as connection:
                connection.execute('UPDATE accounts SET enabled=? WHERE id=?', (enabled, aid))
            print('通过：同账号真实关联重授权维护中，两个工程视图/HTTP一致拒绝执行；切换不写业务事实；取消保留原绑定并恢复ready', flush=True)
            await original(rpc, evaluate, wait_for, session_id)
        yield exercise


if __name__ == '__main__':
    original_fixture = verify_credential_ownership.ownership_fixture
    verify_credential_ownership.ownership_fixture = joint_fixture
    try:
        verify_stack.main()
    finally:
        verify_credential_ownership.ownership_fixture = original_fixture
