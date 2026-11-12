"""用真实 Chrome、HTTP、SQLite 与 SSE 验证两个独立工程空间的导航。"""
import asyncio
import base64
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def project_browser_fixture(client, deployment: str, data: Path, browser, base: str, *, library_root: Path):
    """准备独立配置及持久工作，导航验证不启动模型或改写业务事实。

    :param client: 本次 Docker 客户端。
    :param deployment: 随机部署标识。
    :param data: 隔离数据根。
    :param browser: 已登录 HTTP 会话。
    :param base: 本地网关地址。
    :param library_root: 本次小型合成工程库。
    :return: 实际浏览器场景函数。
    """
    database = data / 'bench/db.sqlite'
    with sqlite3.connect(database) as connection:
        ids = [connection.execute('INSERT INTO accounts(name,profile_path,enabled) VALUES(?,?,?)',
            (name, 'profiles/iteration-' + str(index), enabled)).lastrowid
            for index, (name, enabled) in enumerate((('iteration-a', 1),
                ('iteration-b <img src=x onerror="window.__iterationXss=1">', 1), ('iteration-disabled', 0)))]
    aid, bid, disabled = ids
    endpoints = {'projects': '/projects', 'warmup': '/accounts/warmup/pi'}
    catalog = browser.get(base + '/runtime/api/projects/catalog', timeout=10)
    catalog.raise_for_status()
    keys = [item['project_key'] for item in catalog.json()['projects'][:2]]
    assert len(keys) == 2 and library_root.is_dir()
    for index, (mode, endpoint) in enumerate(endpoints.items()):
        for account in (aid, bid):
            response = browser.put(base + f'/runtime/api{endpoint}/agents/{account}',
                json={'project_keys': [keys[index]], 'instructions': mode + '-guide', 'budget_sec': 3600}, timeout=10)
            response.raise_for_status()
            response = browser.put(base + f'/runtime/api{endpoint}/agents/{account}/schedule',
                json={'enabled': False, 'interval_minutes': 11 + index * 11}, timeout=10)
            response.raise_for_status()
        prefix = '' if mode == 'projects' else 'warmup_'
        with sqlite3.connect(database) as connection:
            for account in (aid, bid):
                for number in range(12):
                    wid = f'{mode}-{account}-{number:02}'
                    connection.execute(f'INSERT INTO {prefix}projects_work(id,account_id,project_key,objective_id,goal,'
                        'definition_json,library_root,library_digest,settings_json,generation,status,session_id,created_at) '
                        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (wid, account, keys[index], 'fixture-objective',
                        f'{mode}-goal-{number:02}', '{}', str(library_root), 'synthetic', '{}', 1,
                        'stopped', wid + '-session', time.time() + number))
                connection.execute(f'UPDATE {prefix}projects_agents SET current_work_id=? WHERE account_id=?', (wid, account))
                for number in range(25):
                    connection.execute(f'INSERT INTO {prefix}projects_events(account_id,work_id,kind,payload_json,created_at) '
                        'VALUES(?,?,?,?,?)', (account, wid, 'pi', json.dumps({'text': f'{mode}-event-{number:02}'}), time.time()))
                connection.execute(f'INSERT INTO {prefix}projects_events(account_id,work_id,kind,payload_json,created_at) '
                    'VALUES(?,?,?,?,?)', (account, wid, 'observation', json.dumps({'screen': mode + '-terminal'}), time.time()))

    def facts():
        """取得两个空间的完整持久事实，排除账号配置测试自身的写入。@return 可比较的表内容。"""
        with sqlite3.connect(database) as connection:
            return {table: connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
                for prefix in ('', 'warmup_') for name in ('agents', 'work', 'events', 'actions', 'submissions')
                for table in [prefix + 'projects_' + name]}

    baseline = facts()
    probe = r'''(() => {
      if (window.__iterationProbe) return;
      const p = window.__iterationProbe = {requests: [], sources: new Set(), timers: new Set(), releases: [], hold: '', maxSources: 0};
      const fetch = window.fetch.bind(window), EventSource = window.EventSource;
      const setInterval = window.setInterval.bind(window), clearInterval = window.clearInterval.bind(window);
      window.fetch = async (input, options = {}) => {
        const url = new URL(typeof input === 'string' ? input : input.url, location.href);
        p.requests.push({path: url.pathname, method: options.method || input.method || 'GET'});
        const response = await fetch(input, options);
        if (p.hold && url.pathname === p.hold) await new Promise(resolve => p.releases.push(resolve));
        return response;
      };
      window.EventSource = class extends EventSource {
        constructor(...args) { super(...args); p.sources.add(this); p.maxSources = Math.max(p.maxSources, p.sources.size); }
        close() { p.sources.delete(this); super.close(); }
      };
      window.setInterval = (...args) => { const id = setInterval(...args); p.timers.add(id); return id; };
      window.clearInterval = id => { p.timers.delete(id); clearInterval(id); };
    })();'''

    async def exercise(rpc, evaluate, wait_for, session_id):
        """操作实际视图并核对请求、资源及持久事实，不以页面状态代替真实模型执行。

        :param rpc: CDP 命令。
        :param evaluate: 页面执行器。
        :param wait_for: 有界条件等待。
        :param session_id: 浏览器会话。
        :return: None；断言失败即停止。
        """
        doc = "document.querySelector('iframe').contentDocument"
        win = doc + '.defaultView'
        await wait_for(f'Boolean({doc}?.querySelector(".tabs"))')
        await rpc('Page.addScriptToEvaluateOnNewDocument', {'source': probe}, session_id)
        await evaluate(f'{win}.eval({json.dumps(probe)})')

        async def ready(mode, account=aid):
            """等真实选择、配置、终端及 SSE 完成。@param mode 空间。@param account 账号。@return None。"""
            try:
                await wait_for(f'{doc}.querySelector("#projects-overview")?.dataset.namespace==="{mode}" && '
                    f'{doc}.querySelector("#projects-account")?.value==="{account}" && '
                    f'{doc}.querySelector("#projects-agent-form")?.elements.instructions.value==="{mode}-guide" && '
                    f'{doc}.querySelector("#projects-screen")?.textContent==="{mode}-terminal"')
            except TimeoutError:
                details = await evaluate(f'({{hash:{win}.location.hash,namespace:{doc}.querySelector("#projects-overview")?.dataset.namespace,'
                    f'account:{doc}.querySelector("#projects-account")?.value,guide:{doc}.querySelector("#projects-agent-form")?.elements.instructions.value,'
                    f'screen:{doc}.querySelector("#projects-screen")?.textContent,feedback:{doc}.querySelector("#projects-feedback")?.textContent}})')
                raise AssertionError('合成迭代页未就绪：' + json.dumps(details, ensure_ascii=False)) from None
            await wait_for(f'{win}.__iterationProbe.sources.size===1 && '
                f'Array.from({win}.__iterationProbe.sources)[0].readyState===1')

        async def go(mode, account=aid):
            """通过现有 hash 路由进入空间。@param mode 空间。@param account 账号。@return None。"""
            await evaluate(f'{win}.location.hash={json.dumps("#" + mode + "?account=" + str(account))}')
            await ready(mode, account)

        await go('projects')
        assert await evaluate(f'{doc}.querySelectorAll(".tabs [data-tab=projects]").length') == 1
        assert await evaluate(f'{doc}.querySelectorAll(".tabs [data-tab=warmup]").length') == 0
        assert await evaluate(f'{doc}.querySelector(".tabs .active .tab-cn").textContent') == '工程迭代'
        timers = await evaluate(f'{win}.__iterationProbe.timers.size')
        assert await evaluate(f'{doc}.querySelector("[data-iteration-mode=projects]").getAttribute("aria-current")') == 'page'
        # 真正键盘激活链接，不能靠直接调用渲染器掩盖可访问性问题。
        await evaluate(f'{doc}.querySelector("[data-iteration-mode=warmup]").focus()')
        for kind in ('keyDown', 'keyUp'):
            await rpc('Input.dispatchKeyEvent', {'type': kind, 'key': 'Enter', 'code': 'Enter'}, session_id)
        await ready('warmup')
        assert await evaluate(f'{doc}.querySelector("#projects-schedule-form").elements.interval_minutes.value') == '22'
        assert keys[1] == await evaluate(f'{doc}.querySelector("[name=project_key]:checked").value')
        await evaluate(f'{doc}.querySelector("[data-iteration-mode=projects]").click()')
        await ready('projects')
        await evaluate(f'{win}.history.back()')
        await ready('warmup')
        await evaluate(f'{win}.history.forward()')
        await ready('projects')
        await evaluate(f'{doc}.querySelector("#projects-account").value="{bid}"; '
            f'{doc}.querySelector("#projects-account").dispatchEvent(new ({win}.Event)("change"))')
        await ready('projects', bid)
        await evaluate(f'{doc}.querySelector("[data-iteration-mode=warmup]").click()')
        await ready('warmup', bid)
        await evaluate(f'window.__iterationPreviousDocument={doc}; {win}.location.reload()')
        # reload 返回时旧页面仍可读取，必须等新 Document 才能检验真正的刷新恢复。
        await wait_for(f'{doc}!==window.__iterationPreviousDocument && {doc}?.readyState==="complete"')
        await ready('warmup', bid)
        assert await evaluate(f'{win}.location.hash') == f'#warmup?account={bid}'
        assert not await evaluate(f'Boolean({win}.__iterationXss)')
        print('通过：统一顶层入口、键盘切换、账号保留、刷新及前进后退，账号名转义', flush=True)

        for mode in ('projects', 'warmup'):
            await go(mode)
            assert await evaluate(f'{doc}.querySelector("#projects-history").textContent.includes("{mode}-goal")')
            await evaluate(f'{doc}.querySelector("#projects-events-next").click()')
            await wait_for(f'{doc}.querySelector("#projects-events-page").textContent.includes("第 2 页")')
            await evaluate(f'{doc}.querySelector("#projects-history-next").click()')
            await wait_for(f'{doc}.querySelector("#projects-history-page").textContent.includes("第 2 页")')
            await evaluate(f'{doc}.querySelector("#projects-agent-form").elements.instructions.value="未保存输入"')
        assert facts() == baseline

        await go('projects')
        await evaluate(f'{win}.__iterationProbe.requests=[]; '
            f'{win}.__iterationProbe.hold="/runtime/api/projects/agents/{aid}/snapshot"')
        await go('warmup')
        await evaluate(f'{doc}.querySelector("[data-iteration-mode=projects]").click()')
        await wait_for(f'{win}.__iterationProbe.releases.length>0')
        await evaluate(f'{doc}.querySelector("[data-iteration-mode=warmup]").click()')
        await ready('warmup')
        await evaluate(f'{win}.__iterationProbe.hold=""; {win}.__iterationProbe.releases.splice(0).forEach(resolve=>resolve())')
        await asyncio.sleep(0.2)
        assert await evaluate(f'{doc}.querySelector("#projects-screen").textContent') == 'warmup-terminal'
        timers = await evaluate(f'{win}.__iterationProbe.timers.size')
        for index in range(20):
            mode = 'projects' if index % 2 == 0 else 'warmup'
            await evaluate(f'{doc}.querySelector("[data-iteration-mode={mode}]").click()')
            await wait_for(f'{doc}.querySelector("#projects-overview")?.dataset.namespace==="{mode}"')
        await ready('warmup')
        assert await evaluate(f'{win}.__iterationProbe.sources.size') == 1
        assert await evaluate(f'{win}.__iterationProbe.maxSources') == 1
        assert await evaluate(f'{win}.__iterationProbe.timers.size') == timers
        assert await evaluate(f'{win}.__iterationProbe.requests.every(item=>item.method==="GET")')
        assert facts() == baseline
        print('通过：不同项目池/计划/终端/记录与分页；未保存表单不写入；慢响应及20次切换无串空间、额外SSE或定时器', flush=True)

        for invalid in ('-1', 'abc', f'{aid}?unexpected', '9007199254740992', f'{aid}&account={bid}', str(disabled), '999999'):
            await evaluate(f'{win}.location.hash={json.dumps("#projects?account=" + invalid)}')
            await wait_for(f'{doc}.querySelector("#projects-feedback")?.textContent.includes("账号当前不可用")')
            assert await evaluate(f'{doc}.querySelector("#projects-account").value') == ''
            assert await evaluate(f'{win}.__iterationProbe.sources.size') == 0
        with sqlite3.connect(database) as connection:
            connection.execute('UPDATE accounts SET deleted_at=? WHERE id=?', (time.time(), bid))
        await evaluate(f'{win}.location.hash="#warmup?account={bid}"')
        await wait_for(f'{doc}.querySelector("#projects-feedback")?.textContent.includes("账号当前不可用")')
        assert await evaluate(f'{doc}.querySelector("#projects-account").value') == ''
        for mode in ('projects', 'warmup'):
            await evaluate(f'{win}.location.hash="#{mode}"')
            await ready(mode)
        await evaluate(f'{win}.location.hash="#accounts"')
        await wait_for(f'Boolean({doc}.querySelector("[data-warmup-console=\\"{aid}\\"]"))')
        await evaluate(f'{doc}.querySelector("[data-warmup-console=\\"{aid}\\"]").click()')
        await ready('warmup')
        print('通过：旧链接、账号页直达；非法/重复/失效/已删除账号不默认操作其他账号', flush=True)

        for mode in ('projects', 'warmup'):
            await go(mode)
            await evaluate(f'{doc}.querySelector("#projects-cli-settings").click()')
            await wait_for(f'{doc}.querySelector("#cli-settings-title").textContent.includes("'
                + ('项目迭代配置' if mode == 'projects' else '养号迭代配置') + '")')
            await wait_for(f'!{doc}.querySelector("#cli-settings-form button[type=submit]").disabled')
            await evaluate(f'{doc}.querySelector("#cli-settings-form").elements.capture_enabled.checked=true; '
                f'{doc}.querySelector("#cli-settings-form").requestSubmit()')
            await wait_for(f'{doc}.querySelector("#cli-settings-feedback").textContent.includes("配置已保存")')
            other = 'warmup' if mode == 'projects' else 'projects'
            await evaluate(f'{doc}.querySelector("[data-iteration-mode={other}]").click()')
            await ready(other)
            assert await evaluate(f'{doc}.querySelector("#cli-settings-modal").classList.contains("hidden")')
            await evaluate(f'{doc}.querySelector("#projects-capture").click()')
            await wait_for(f'{doc}.querySelector("#work-capture-content").textContent!=="正在读取抓包…"')
            assert await evaluate(f'{win}.__iterationProbe.requests.some(item=>item.path.includes("'
                + endpoints[other] + '/work/' + other + f'-{aid}-11/capture"))')
            await evaluate(f'{doc}.querySelector("[data-iteration-mode={mode}]").click()')
            await ready(mode)
            assert await evaluate(f'{doc}.querySelector("#work-capture-modal").classList.contains("hidden")')
        with sqlite3.connect(database) as connection:
            assert connection.execute('SELECT projects_capture_enabled,warmup_capture_enabled FROM accounts WHERE id=?', (aid,)).fetchone() == (1, 1)
        assert facts() == baseline
        for width, height in ((1280, 900), (720, 900), (390, 844)):
            await rpc('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
                'deviceScaleFactor': 1, 'mobile': width < 500}, session_id)
            for theme in ('dark', 'light'):
                if await evaluate(f'{doc}.documentElement.dataset.theme') != theme:
                    await evaluate(f'{doc}.querySelector("#theme-toggle").click()')
                await wait_for(f'{doc}.documentElement.dataset.theme==="{theme}"')
                assert await evaluate(f'{doc}.documentElement.scrollWidth <= {win}.innerWidth+2')
                shot = await rpc('Page.captureScreenshot', {'format': 'png'}, session_id)
                Path(f'/tmp/v3-iteration-console-{width}-{theme}.png').write_bytes(base64.b64decode(shot['data']))
        before_leave = await evaluate(f'{win}.__iterationProbe.timers.size')
        await evaluate(f'{win}.location.hash="#accounts"')
        await wait_for(f'{win}.__iterationProbe.sources.size===0 && {win}.__iterationProbe.timers.size==={before_leave - 1}')
        assert facts() == baseline
        print('通过：两空间配置/抓包正确，切换关闭弹窗；1280/720/390px明暗主题；卸载释放SSE/时钟且持久工作/计划不变；未调用真实模型', flush=True)

    try:
        yield exercise
    finally:
        with sqlite3.connect(database) as connection:
            connection.executemany('UPDATE accounts SET enabled=0,warmup_enabled=0 WHERE id=?', [(account,) for account in ids])
