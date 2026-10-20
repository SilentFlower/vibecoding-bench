"""在独立管理栈核对本轮完成提示及历史 stopped 原因，不使用真实账号。"""
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def quota_completion_browser_fixture(data: Path):
    """创建已停止的合成记录，供真实页面、API 和 SQLite 交叉核对。

    :param data: 本次随机验证部署的数据根。
    :return: 使用已登录 Chrome 的异步页面场景，退出时清理本次合成记录。
    """
    database = data/'bench/db.sqlite'
    rid = 'c070ffb00001'
    reason = '额度阈值强制中断：5h 已用 68% ≥ 60%（观测 2026-10-18T12:00:00+00:00） <img src=x onerror="window.__quotaXss=1">'
    now = time.time()
    with sqlite3.connect(database) as connection:
        aid = connection.execute("INSERT INTO accounts(name,profile_path,warmup_quota_5h_limit_percent,"
            "warmup_quota_7d_limit_percent) VALUES('hard-stop-ui','profiles/hard-stop-ui',60,80)").lastrowid
        tid = connection.execute("INSERT INTO tasks(topic_no,title,prompt,account_id) "
            "VALUES(1,'合成额度中断','Local fixture.',?)",(aid,)).lastrowid
        connection.execute("INSERT INTO runs(id,task_id,account_id,status,exit_code,error,started_at,ended_at,"
            "stop_requested_at) VALUES(?,?,?,'stopped',143,?,?,?,?)",(rid,tid,aid,reason,now-30,now,now))

    async def exercise(rpc, evaluate, wait_for, session_id: str) -> None:
        """操作真实额度表单和运行详情，核对公开状态和转义。@return None。"""
        doc = "document.querySelector('iframe').contentDocument"
        await evaluate(f'{doc}.defaultView.location.hash="#accounts"')
        await wait_for(f'Boolean({doc}.querySelector("[data-warmup-config]"))')
        await evaluate(f'{doc}.querySelector("[data-warmup-config]").click()')
        await wait_for(f'!{doc}.querySelector("#warmup-modal").classList.contains("hidden")')
        content = await evaluate(f'{doc}.querySelector("#warmup-modal").textContent')
        assert all(text in content for text in ['完成本轮','包括补充与收尾','下一轮等待','被动更新']),content
        assert '自动查询额度' not in content and '强制结束当前' not in content,content
        assert await evaluate(f'{doc}.querySelector("#warmup-quota-5h-hint").textContent.includes("达到 60%")')
        await evaluate(f'{doc}.querySelector("#warmup-form").requestSubmit()')
        await wait_for(f'{doc}.querySelector("#warmup-modal").classList.contains("hidden")')
        result = await evaluate(f'fetch("/runtime/api/runs/{rid}").then(response=>response.json())')
        assert result['status']=='stopped' and result['exit_code']==143 and result['error']==reason,result
        await evaluate(f'{doc}.defaultView.openRunDetail("{rid}")')
        await wait_for(f'{doc}.body.textContent.includes("5h 已用 68%")')
        assert await evaluate(f'{doc}.querySelectorAll("img[src=x]").length')==0
        assert await evaluate(f'{doc}.defaultView.__quotaXss||0')==0
        for width in (1280,390):
            await rpc('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,
                'deviceScaleFactor':1,'mobile':False},session_id)
            for theme in ('dark','light'):
                await evaluate(f'(() => {{const doc={doc};if(doc.documentElement.dataset.theme!=="{theme}")'
                               'doc.querySelector("#theme-toggle").click();})()')
                bounds = await evaluate(f'(() => {{const doc={doc};const card=doc.querySelector('
                    '\'.modal:not(.hidden) .modal-card\').getBoundingClientRect();'
                    'return {left:card.left,right:card.right,width:doc.defaultView.innerWidth};})()')
                assert bounds['left']>=-1 and bounds['right']<=bounds['width']+1,bounds
        await rpc('Emulation.setDeviceMetricsOverride',{'width':1280,'height':900,
            'deviceScaleFactor':1,'mobile':False},session_id)
        with sqlite3.connect(database) as connection:
            saved = connection.execute('SELECT status,error,stop_requested_at FROM runs WHERE id=?',(rid,)).fetchone()
            limits = connection.execute('SELECT warmup_quota_5h_limit_percent,warmup_quota_7d_limit_percent '
                                       'FROM accounts WHERE id=?',(aid,)).fetchone()
        assert saved==('stopped',reason,now) and limits==(60,80)
        print('通过：本轮完成说明、保存重读、历史 stopped API／SQLite 原因、XSS、1280／390px 明暗主题',flush=True)

    try:
        yield exercise
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute('DELETE FROM runs WHERE id=?',(rid,))
            connection.execute('DELETE FROM tasks WHERE id=?',(tid,))
            connection.execute('DELETE FROM account_quota_states WHERE account_id=?',(aid,))
            connection.execute('DELETE FROM warmup_quota_admissions WHERE account_id=?',(aid,))
            connection.execute('DELETE FROM accounts WHERE id=?',(aid,))
