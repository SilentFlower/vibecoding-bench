"""在独立管理栈验证题库编辑和运行补充详情，全部数据为合成资料。"""
import base64
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def followup_browser_fixture(data: Path):
    """准备已完成的合成运行，不创建账号容器或真实任务。

    :param data: 本次验证专属数据根目录。
    :return: 复用已登录 Chrome 的页面场景。
    """
    database = data/'bench/db.sqlite'
    rid = 'f0110b000001'
    messages = ['Compare date windows. <img src=x onerror="window.__followupXss=1">','Export comparisons.']
    with sqlite3.connect(database) as connection:
        aid = connection.execute("INSERT INTO accounts(name,profile_path) VALUES('followup-ui','profiles/followup-ui')").lastrowid
        tid = connection.execute("INSERT INTO topics(no,title,description,category,followups_json) VALUES(601,'Followup UI fixture','Build a local table.','Examples',?)",(json.dumps(messages),)).lastrowid
        task = connection.execute("INSERT INTO tasks(topic_no,title,prompt,account_id,topic_id) VALUES(601,'Followup UI','Initial local requirement.',?,?)",(aid,tid)).lastrowid
        connection.execute("INSERT INTO runs(id,task_id,account_id,topic_id,status,followup_plan_json,environment_id) VALUES(?,?,?,?,'done',?,'followup-ui')",(rid,task,aid,tid,json.dumps(messages)))
    phase = data/f'bench/environments/followup-ui/runtime/runs/{rid}/followups.json'
    phase.parent.mkdir(parents=True)
    digest = hashlib.sha256(json.dumps({'run_id':rid,'followups':messages},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    phase.write_text(json.dumps({'schema':1,'run_id':rid,'plan_digest':digest,'completed_stages':3,'phase':'complete'}))
    phase.chmod(0o600)

    async def exercise(rpc,evaluate,wait_for,session_id):
        """通过真实 DOM 操作保存题目，并核对 API 和 SQLite。

        :param rpc: CDP 命令。
        :param evaluate: 页面执行器。
        :param wait_for: 有界条件等待。
        :param session_id: 私有浏览器会话。
        :return: None；失败抛出断言。
        """
        doc = "document.querySelector('iframe').contentDocument"
        await wait_for(f'Boolean({doc}?.querySelector(".tabs"))')
        await evaluate(f'{doc}.defaultView.location.hash="#topics"')
        await wait_for(f'Boolean({doc}.querySelector(".topic-card[data-id=\\"{tid}\\"]"))')
        await evaluate(f'{doc}.querySelector(".topic-card[data-id=\\"{tid}\\"]").click()')
        await wait_for(f'!{doc}.querySelector("#topic-modal").classList.contains("hidden")')
        assert await evaluate(f'{doc}.querySelector("#topic-form").elements.followup_1.value')==messages[0]
        replacement='Compare monthly date windows.'
        await evaluate(f'{doc}.querySelector("#topic-form").elements.followup_1.value={json.dumps(replacement)}')
        await evaluate(f'{doc}.querySelector("#topic-form").requestSubmit()')
        await wait_for(f'{doc}.querySelector("#topic-modal").classList.contains("hidden")')
        topics=await evaluate('fetch("/runtime/api/topics").then(r=>r.json())')
        assert next(t for t in topics if t['id']==tid)['followups']==[replacement,messages[1]]
        with sqlite3.connect(database) as connection:
            assert json.loads(connection.execute('SELECT followups_json FROM topics WHERE id=?',(tid,)).fetchone()[0])==[replacement,messages[1]]
        await evaluate(f'{doc}.defaultView.openRunDetail("{rid}")')
        await wait_for(f'{doc}.querySelector("#run-detail-followups")?.textContent.includes("全部轮次完成")')
        assert await evaluate(f'{doc}.querySelector("#run-detail-followups").textContent.includes("2/2")')
        assert await evaluate(f'{doc}.querySelector("#run-detail-followups").textContent.includes({json.dumps(messages[0])})')
        assert not await evaluate(f'Boolean({doc}.defaultView.__followupXss)')
        assert await evaluate(f'{doc}.querySelectorAll("#run-detail-followups img").length')==0
        timing = {'schema':2,'offsets_sec':[90,540],'timeout_sec':1800,'wrapup_sec':600}
        with sqlite3.connect(database) as connection:
            connection.execute('UPDATE runs SET followup_timing_json=?,status=\'running\' WHERE id=?',(json.dumps(timing),rid))
        state = {'schema':2,'run_id':rid,'plan_digest':digest,'completed_stages':0,'phase':'awaiting',
            'timing_digest':hashlib.sha256(json.dumps(timing,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'started_at':1792210000,'items':[{'status':'queued','queue_entry':'session.jsonl:1'},
                {'status':'consumed','input_entry':'session.jsonl:2'}]}
        phase.write_text(json.dumps(state))
        await evaluate(f'{doc}.defaultView.openRunDetail("{rid}")')
        await wait_for(f'{doc}.querySelector("#run-detail-followups")?.textContent.includes("已入队，等待消费")')
        content = await evaluate(f'{doc}.querySelector("#run-detail-followups").textContent')
        assert all(text in content for text in ('已投递 2/2','已消费 1/2','已完成补充 0/2','启动后 1分30秒','启动后 9分0秒')),content
        state.update(phase='complete',completed_stages=3)
        for index,item in enumerate(state['items']):
            item.update(status='completed',input_entry=f'session.jsonl:{index+3}',reply_entry='session.jsonl:5')
        phase.write_text(json.dumps(state))
        await evaluate(f'{doc}.defaultView.openRunDetail("{rid}")')
        await wait_for(f'{doc}.querySelector("#run-detail-followups")?.textContent.includes("已完成补充 2/2")')
        valid_state = json.dumps(state)
        phase.unlink()
        await evaluate(f'{doc}.defaultView.openRunDetail("{rid}")')
        await wait_for(f'{doc}.querySelector("#run-detail-followups")?.textContent.includes("阶段状态待核对")')
        content = await evaluate(f'{doc}.querySelector("#run-detail-followups").textContent')
        assert '已投递 待确认/2' in content and '等待到点' not in content,content
        for item in state['items']:
            item.update(input_entry='',reply_entry='')
        phase.write_text(json.dumps(state))
        phase.chmod(0o600)
        await evaluate(f'{doc}.defaultView.openRunDetail("{rid}")')
        await wait_for(f'{doc}.querySelector("#run-detail-followups")?.textContent.includes("阶段证据无效")')
        content = await evaluate(f'{doc}.querySelector("#run-detail-followups").textContent')
        assert '已完成补充 2/2' not in content and '已消费 待确认/2' in content,content
        phase.unlink()
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,))
        await evaluate(f'{doc}.defaultView.openRunDetail("{rid}")')
        await wait_for(f'{doc}.querySelector("#run-detail-followups")?.textContent.includes("等待到点")')
        content = await evaluate(f'{doc}.querySelector("#run-detail-followups").textContent')
        assert '已投递 0/2' in content and '阶段状态待核对' not in content,content
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE runs SET status='running' WHERE id=?",(rid,))
        phase.write_text(valid_state)
        phase.chmod(0o600)
        await evaluate(f'{doc}.defaultView.openRunDetail("{rid}")')
        await wait_for(f'{doc}.querySelector("#run-detail-followups")?.textContent.includes("已完成补充 2/2")')
        for width in (1280,390):
            await rpc('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False},session_id)
            for theme in ('dark','light'):
                await evaluate(f'(() => {{const d={doc};if(d.documentElement.dataset.theme!=="{theme}")d.querySelector("#theme-toggle").click();}})()')
                await evaluate('new Promise(r=>setTimeout(r,250))')
                bounds=await evaluate(f'(() => {{const r={doc}.querySelector("#modal .modal-card").getBoundingClientRect();return {{left:r.left,right:r.right,width:{doc}.defaultView.innerWidth}};}})()')
                assert bounds['left']>=-1 and bounds['right']<=bounds['width']+1,bounds
                screenshot=await rpc('Page.captureScreenshot',{'format':'png'},session_id)
                Path(f'/tmp/topic-followups-{width}-{theme}.png').write_bytes(base64.b64decode(screenshot['data']))
        print('通过：真实浏览器编辑/API/SQLite，旧阶段与定时进度，缺失/空证据提示及正常未启动，XSS转义，1280/390px明暗主题',flush=True)
    try:
        yield exercise
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute('DELETE FROM runs WHERE id=?',(rid,))
            connection.execute('DELETE FROM tasks WHERE id=?',(task,))
            connection.execute('DELETE FROM topics WHERE id=?',(tid,))
            connection.execute('DELETE FROM accounts WHERE id=?',(aid,))
