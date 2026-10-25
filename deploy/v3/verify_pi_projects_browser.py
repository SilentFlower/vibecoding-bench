"""使用回环 API、真实 Chrome 和 SQLite 验证新 Projects 页面，不调用真实账号。"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from websockets.asyncio.client import connect


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'orchestrator'))

from project_requester_settings import ProjectRequesterSettings
from project_library import materialize_snapshot, read_document
from projects_api import projects_router
from test_projects_agent import CatalogFixture, PiFixture, ProjectsAgentTests


class BrowserCatalog(CatalogFixture):
    """为浏览器提供含恶意 HTML 文本的研究材料。"""

    def project(self, key, detail=True):
        """返回不含可执行 HTML 的原始业务文本。:param key: 项目。:param detail: 详细标记。:return: 公开对象。"""
        value = super().project(key, detail)
        value.update(title=key + ' 项目研究', description='浏览器合成研究资料',
            research={'report': '<img src=x onerror="window.researchInjected=true">研究正文', 'roadmap': '保留原项目研究。'})
        return value


class BrowserPi(PiFixture):
    """为浏览器表单操作保留充足时间，不调用模型或真实账号。"""

    def __init__(self):
        """初始化可控的单轮到时信号和实际调用时限记录。:return: None。"""
        super().__init__()
        self.timeout_turn = threading.Event()
        self.turn_timeouts = []

    def run(self, configuration, tools, event, stop, timeout_sec):
        """持有合成控制者直到页面暂停，避免表单验证被短夹具超时打断。

        :param configuration: 控制端生成的启动配置。
        :param tools: 当前账号的工具回调。
        :param event: 公开事件回调。
        :param stop: 当前控制者停止信号。
        :param timeout_sec: 本轮工作预算。
        :return: 已停止状态。
        """
        self.entered.set()
        self.turn_timeouts.append(timeout_sec)
        deadline = time.monotonic() + min(60, timeout_sec)
        while not stop.wait(0.05):
            if self.timeout_turn.is_set():
                self.timeout_turn.clear()
                return 'timeout'
            if time.monotonic() >= deadline:
                break
        return 'stopped'


async def verify(evidence: Path) -> dict:
    """核对项目池选择、独立自动计划、Pi 生命周期、SSE 和手机布局。

    :param evidence: 截图与检查报告目录。
    :return: 实际检查结果。
    """
    evidence.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    source_paths = ('webui/projects.js', 'webui/index.html', 'webui/style.css',
        'orchestrator/projects.py', 'orchestrator/projects_api.py', 'deploy/v3/verify_pi_projects_browser.py')
    source_sha256 = {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() for relative in source_paths}
    fixture = ProjectsAgentTests('test_pause_rejects_old_generation_before_any_terminal_write')
    fixture.setUp()
    fixture.pi = BrowserPi()
    fixture.service.pi = fixture.pi
    fixture.service.catalog = BrowserCatalog(fixture.root)
    fixture.activate(); initial = fixture.start_work()
    work = fixture.service._one('SELECT * FROM projects_work WHERE id=?', (initial['work_id'],))
    (fixture.terminal.workspace(work) / 'library/app.py').write_text('VALUE = 2\n')
    fixture.verification = {'status': 'passed', 'feedback': ['合成工程独立验收通过']}
    submitted = fixture.tool('project_submit', {'summary': '浏览器成果夹具'})
    completed_at = time.time()
    # 墙钟跨两小时但实际只累计约七分钟，确认页面不会把暂停时间算进执行耗时。
    fixture.service._write('UPDATE projects_work SET work_sec=?,created_at=?,started_at=?,ended_at=? WHERE id=?',
        (418.9, completed_at - 7201, completed_at - 7200, completed_at, work['id']))
    work = fixture.service._one('SELECT * FROM projects_work WHERE id=?', (work['id'],))
    directory = fixture.root / 'projects/submissions' / submitted['submission_id']
    materialize_snapshot(read_document(directory / 'snapshot.json'), fixture.root / 'projects/objects', directory / 'candidate')
    fixture.service._write("UPDATE projects_agents SET status='off' WHERE account_id=1")
    fixture.service.configure(2, ['other'])

    def seed_history(identifier, created_at):
        """添加不属于当前项目池的已完成历史，不改变真实交付和运行进度。

        :param identifier: 合成历史工作 ID。
        :param created_at: 早于真实交付的创建时间。
        :return: 合成工作的完整记录。
        """
        historical = {**work, 'id': identifier, 'project_key': 'browser-history', 'status': 'passed',
            'session_id': 'session-' + identifier, 'created_at': created_at, 'ended_at': created_at + 1,
            'runtime_json': None, 'segment_started_at': None, 'work_sec': 0}
        columns, placeholders = ','.join(historical), ','.join('?' for _ in historical)
        fixture.service._write(f'INSERT INTO projects_work({columns}) VALUES({placeholders})', tuple(historical.values()))
        return historical

    historical_works = [seed_history(f'browser-history-{index:03}', work['created_at'] - 10 - index // 3)
        for index in range(36)]
    fixture.service._write('UPDATE projects_work SET work_sec=?,ended_at=? WHERE id=?',
        (3661.9, completed_at - 2, historical_works[0]['id']))
    for index in range(450):
        fixture.service._event(1, 'observation', {'screen': f'旧历史画面 {index}'}, historical_works[0]['id'])
    for index in range(65):
        fixture.service._event(1, 'pi', {'text': f'分页交互 {index:03}'}, work['id'])
    latest_screen = '当前真实交付的最新终端画面'
    fixture.service._event(1, 'observation', {'screen': latest_screen}, work['id'])
    initial_cursor = fixture.service.snapshot(1)['cursor']
    public_gate = {'allowed': True, 'reason': 'allowed', 'retryable': False, 'retry_at': None,
        'message': None, 'window': {'enabled': False, 'allowed': True, 'timezone': 'Asia/Shanghai',
            'next_open_at': None, 'next_close_at': None},
        'quota': {'known': False, 'source': 'passive', 'observed_at': None, 'windows': {},
            'limits': {'five_hour': 30, 'seven_day': 50}, 'hit': []}}
    fixture.service.admission = lambda *_: public_gate
    configuration = ProjectRequesterSettings(fixture.root / 'provider.json', {})
    configuration.save('https://example.invalid/v1', ['test-model'], 'browser-private-key')
    application = FastAPI()
    application.include_router(projects_router(lambda: fixture.service))
    requested_paths = []
    stream_requests = []
    start_response = threading.Event()
    drop_stream_once = threading.Event()

    @application.middleware('http')
    async def record_requests(request: Request, call_next):
        """记录请求路径，验证新页面不再读取旧项目接口。

        :param request: 本地浏览器请求。
        :param call_next: 当前请求的后续处理器。
        :return: 原请求响应。
        """
        requested_paths.append(request.url.path)
        if request.url.path == '/api/projects/stream':
            stream_requests.append({'query': dict(request.query_params), 'last_event_id': request.headers.get('last-event-id')})
        if request.method == 'POST' and request.url.path == '/api/projects/agents/1/start':
            await asyncio.to_thread(start_response.wait, 10)
        response = await call_next(request)
        if request.url.path == '/api/projects/stream':
            original_body = response.body_iterator

            async def observed_body():
                """只在隔离测试中结束一次已交付的更新，验证浏览器自动重连。:return: 原始 SSE 字节。"""
                try:
                    async for chunk in original_body:
                        yield chunk
                        if drop_stream_once.is_set() and b'event: update' in chunk:
                            drop_stream_once.clear()
                            return
                finally:
                    await original_body.aclose()

            response.body_iterator = observed_body()
        return response

    @application.get('/api/accounts')
    def accounts():
        """返回合成账号。:return: 无凭据账号列表。"""
        return [{'id': 1, 'name': '浏览器合成账号', 'enabled': True},
            {'id': 2, 'name': '浏览器第二账号', 'enabled': True}]

    @application.get('/api/auth/me')
    def auth():
        """只在隔离回环应用关闭登录。:return: 本地测试鉴权状态。"""
        return {'auth_required': False}

    @application.get('/api/settings/project-requester')
    def settings():
        """读取真实脱敏配置。:return: 公开配置。"""
        return configuration.public()

    @application.put('/api/settings/project-requester')
    def save_settings(body: dict):
        """保存测试配置。:param body: 页面表单。:return: 脱敏结果。"""
        configuration.save(body['base_url'], body['models'], body.get('api_key'))
        return configuration.public()

    @application.get('/api/topics')
    def topics():
        """供切页检查使用。:return: 空题库。"""
        return []

    application.mount('/', StaticFiles(directory=str(ROOT / 'webui'), html=True))
    listener = socket.socket(); listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(application, lifespan='off', log_level='error', loop='asyncio'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True); thread.start()
    process, errors = None, []
    try:
        with tempfile.TemporaryDirectory(prefix='pi-projects-chrome-') as profile:
            debug = socket.socket(); debug.bind(('127.0.0.1', 0)); debug_port = debug.getsockname()[1]; debug.close()
            chrome = shutil.which('google-chrome') or shutil.which('chromium')
            if not chrome:
                raise RuntimeError('缺少本机 Chrome')
            process = await asyncio.create_subprocess_exec(chrome, '--headless=new', '--no-sandbox',
                '--disable-dev-shm-usage', '--no-first-run', '--disable-background-networking',
                '--proxy-server=http://127.0.0.1:9', '--proxy-bypass-list=127.0.0.1;localhost',
                f'--user-data-dir={profile}', f'--remote-debugging-port={debug_port}', 'about:blank',
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            version = None
            for _ in range(80):
                try:
                    with opener.open(f'http://127.0.0.1:{debug_port}/json/version', timeout=1) as response:
                        version = json.load(response)
                    break
                except OSError:
                    await asyncio.sleep(0.1)
            if not version:
                raise RuntimeError('Chrome 未能启动')
            async with connect(version['webSocketDebuggerUrl'], proxy=None, max_size=8 * 1024 * 1024) as channel:
                command_id = 0

                async def rpc(method, parameters=None, session=None):
                    nonlocal command_id
                    command_id += 1
                    payload = {'id': command_id, 'method': method, 'params': parameters or {}}
                    if session: payload['sessionId'] = session
                    await channel.send(json.dumps(payload))
                    async with asyncio.timeout(15):
                        while True:
                            value = json.loads(await channel.recv())
                            if value.get('method') == 'Runtime.exceptionThrown':
                                errors.append(value['params']['exceptionDetails'])
                            if value.get('id') == command_id:
                                if 'error' in value: raise RuntimeError(str(value['error']))
                                return value.get('result', {})

                target = await rpc('Target.createTarget', {'url': 'about:blank'})
                session = (await rpc('Target.attachToTarget', {'targetId': target['targetId'], 'flatten': True}))['sessionId']
                await rpc('Page.enable', session=session); await rpc('Runtime.enable', session=session)

                async def evaluate(expression):
                    value = await rpc('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True}, session)
                    if 'exceptionDetails' in value: raise RuntimeError(str(value['exceptionDetails']))
                    return value.get('result', {}).get('value')

                async def until(expression):
                    for _ in range(100):
                        if await evaluate(expression): return
                        await asyncio.sleep(0.1)
                    diagnostic = await evaluate('Object.fromEntries(["state","message","feedback","budget"].map(key=>[key,document.querySelector("#projects-"+key)?.textContent]))')
                    raise AssertionError('浏览器等待失败：' + expression + '；页面状态：' + json.dumps(diagnostic, ensure_ascii=False))

                async def reload():
                    """等待新文档真正替换旧页面，避免重载回显断言读到原 DOM。

                    :return: None。
                    """
                    await evaluate('window.browserReloadMarker=true')
                    await rpc('Page.reload', session=session)
                    await until('window.browserReloadMarker !== true && document.readyState === "complete"')

                await rpc('Page.addScriptToEvaluateOnNewDocument', {'source': '''window.projectStreams=[];
                    const Original=window.EventSource;window.EventSource=class extends Original{
                    constructor(...args){super(...args);window.projectStreams.push(this)}
                    close(){this.wasClosed=true;super.close()}};
                    window.projectScreens=[];addEventListener('DOMContentLoaded',()=>{
                        const screen=document.querySelector('#projects-screen');
                        if(screen)new MutationObserver(()=>window.projectScreens.push(screen.textContent)).observe(screen,{childList:true,subtree:true});
                    });'''}, session)
                await rpc('Page.navigate', {'url': f'http://127.0.0.1:{port}/#projects'}, session)
                await until('document.querySelectorAll("[name=project_key]").length === 2')
                await until('document.querySelector("#projects-progress-text").textContent.includes("1 / 1")')
                await until('document.querySelector("#projects-screen").textContent === ' + json.dumps(latest_screen))
                await until('window.projectStreams.some(value=>value.readyState===EventSource.OPEN)')
                assert not await evaluate('window.projectScreens.some(text=>text.includes("旧历史画面"))')
                assert stream_requests and stream_requests[0]['query'] == {'account_id': '1', 'after': str(initial_cursor)}
                assert await evaluate('document.querySelectorAll("#projects-events li[data-event-id]").length === 20 && document.querySelectorAll("#projects-history [data-work]").length === 10')
                assert await evaluate('(()=>{const ids=Array.from(document.querySelectorAll("#projects-events [data-event-id]"),value=>Number(value.dataset.eventId));return ids.every((id,index)=>!index || id<ids[index-1])})()')
                assert await evaluate('document.querySelector("#projects-history [data-work]").dataset.work === ' + json.dumps(work['id']))
                assert await evaluate('document.querySelector(' + json.dumps('[data-work-duration="' + work['id'] + '"]') + ').textContent === "完成耗时 6 分 58 秒"')
                assert await evaluate('document.querySelector("[data-work-duration=browser-history-000]").textContent === "完成耗时 1 小时 1 分 1 秒"')

                # 迟到的旧工程观察只属于历史，不能把当前终端换成其他会话。
                before_operations = (len(fixture.terminal.started), len(fixture.terminal.sent), len(fixture.terminal.controls))
                fixture.service._event(1, 'observation', {'screen': '迟到的旧工程终端'}, historical_works[0]['id'])
                fixture.service._event(1, 'pi', {'text': '迟到观察已核对'}, work['id'])
                await until('document.querySelector("#projects-events").textContent.includes("迟到观察已核对")')
                assert await evaluate('document.querySelector("#projects-screen").textContent === ' + json.dumps(latest_screen))
                await evaluate('window.firstEventPage=Array.from(document.querySelectorAll("#projects-events [data-event-id]"),value=>value.dataset.eventId);window.firstWorkPage=Array.from(document.querySelectorAll("#projects-history [data-work]"),value=>value.dataset.work);document.querySelector("#projects-tab-events").click();document.querySelector("#projects-events-next").click();document.querySelector("#projects-history-next").click();')
                await until('document.querySelector("#projects-events-page").textContent.includes("第 2 页") && document.querySelector("#projects-history-page").textContent.includes("第 2 页")')
                assert await evaluate('document.querySelectorAll("#projects-events [data-event-id]").length === 20 && document.querySelectorAll("#projects-history [data-work]").length === 10')
                assert await evaluate('Array.from(document.querySelectorAll("#projects-events [data-event-id]")).every(value=>!window.firstEventPage.includes(value.dataset.eventId)) && Array.from(document.querySelectorAll("#projects-history [data-work]")).every(value=>!window.firstWorkPage.includes(value.dataset.work))')
                await evaluate('window.oldEventPage=Array.from(document.querySelectorAll("#projects-events [data-event-id]"),value=>value.dataset.eventId);window.oldWorkPage=Array.from(document.querySelectorAll("#projects-history [data-work]"),value=>value.dataset.work);')
                fixture.service._event(1, 'pi', {'text': '浏览旧页时的新交互'}, work['id'])
                newer_work = seed_history('browser-newer-work', work['created_at'] - 0.5)
                fixture.service._write('UPDATE projects_agents SET current_work_id=? WHERE account_id=1', (newer_work['id'],))
                fixture.service._event(1, 'started', {'session_id': newer_work['session_id']}, newer_work['id'])
                await until('!document.querySelector("#projects-events-new").classList.contains("hidden") && !document.querySelector("#projects-history-new").classList.contains("hidden")')
                assert await evaluate('document.querySelector("#projects-events-page").textContent.includes("第 2 页") && document.querySelector("#projects-history-page").textContent.includes("第 2 页")')
                assert await evaluate('JSON.stringify(Array.from(document.querySelectorAll("#projects-events [data-event-id]"),value=>value.dataset.eventId))===JSON.stringify(window.oldEventPage) && JSON.stringify(Array.from(document.querySelectorAll("#projects-history [data-work]"),value=>value.dataset.work))===JSON.stringify(window.oldWorkPage)')
                assert await evaluate('document.querySelector("#projects-screen").textContent.includes("等待当前目标")')
                await evaluate('document.querySelector("#projects-events-new").click();document.querySelector("#projects-history-new").click();')
                await until('document.querySelector("#projects-events-page").textContent.includes("第 1 页") && document.querySelector("#projects-history-page").textContent.includes("第 1 页") && document.querySelector("#projects-events").textContent.includes("浏览旧页时的新交互")')
                assert await evaluate('document.querySelector("#projects-events-new").classList.contains("hidden") && document.querySelector("#projects-history-new").classList.contains("hidden") && document.querySelector("#projects-events-previous").disabled && document.querySelector("#projects-history-previous").disabled')
                assert await evaluate('Array.from(document.querySelectorAll("#projects-history [data-work]")).some(value=>value.dataset.work===' + json.dumps(newer_work['id']) + ')')
                fixture.service._write('UPDATE projects_agents SET current_work_id=? WHERE account_id=1', (work['id'],))
                fixture.service._event(1, 'observation', {'screen': latest_screen}, work['id'])
                await until('document.querySelector("#projects-screen").textContent === ' + json.dumps(latest_screen))

                # 原生 EventSource 收到服务端断开后必须用 Last-Event-ID 续接，而非从零回放。
                stream_count = len(stream_requests)
                drop_stream_once.set()
                fixture.service._event(1, 'pi', {'text': '断线前最后一条交互'}, work['id'])
                disconnect_id = fixture.service.event_page(1, limit=1)['items'][0]['id']
                await until('document.querySelector("#projects-events").textContent.includes("断线前最后一条交互")')
                for _ in range(100):
                    if len(stream_requests) > stream_count:
                        break
                    await asyncio.sleep(0.1)
                assert len(stream_requests) > stream_count, '浏览器没有自动重连 SSE'
                assert stream_requests[-1]['last_event_id'] == str(disconnect_id)
                fixture.service._event(1, 'pi', {'text': '重连后的最新交互'}, work['id'])
                await until('document.querySelector("#projects-events").textContent.includes("重连后的最新交互")')
                assert await evaluate('Array.from(document.querySelectorAll("#projects-events [data-event-id]")).filter(value=>value.dataset.eventId===' + json.dumps(str(disconnect_id)) + ').length === 1')
                assert not await evaluate('window.projectScreens.some(text=>text.includes("旧历史画面") || text.includes("迟到的旧工程终端"))')
                assert before_operations == (len(fixture.terminal.started), len(fixture.terminal.sent), len(fixture.terminal.controls))
                assert not fixture.pi.entered.is_set(), '读取历史意外启动了 Pi'
                await evaluate('document.querySelector("#projects-tab-terminal").click()')
                assert await evaluate('document.querySelector("#projects-progress-bar").value === 100 && document.querySelector("#projects-budget").textContent === "完成耗时 6 分 58 秒"')
                assert await evaluate('document.querySelector("#projects-account").getAttribute("form") === "projects-agent-form" && document.querySelector("#projects-account").closest("header") !== null')
                assert await evaluate('Array.from(document.querySelectorAll(".projects-settings > details")).every(value => !value.open)')
                assert await evaluate('document.querySelector("#projects-overview").getBoundingClientRect().top < document.querySelector("#projects-workspace").getBoundingClientRect().top')
                assert await evaluate('document.querySelector("#projects-current").textContent.includes("上一目标已验收通过") && !document.querySelector("#projects-state").textContent.includes("指挥中")')
                assert await evaluate('Array.from(document.querySelectorAll("[data-quota-value]")).every(value => value.textContent === "未采集") && Array.from(document.querySelectorAll("[data-quota-fill]")).every(value => value.classList.contains("hidden") && !value.hasAttribute("aria-valuenow"))')
                await evaluate('document.dispatchEvent(new KeyboardEvent("keydown",{key:"/",bubbles:true,cancelable:true}))')
                assert await evaluate('document.querySelector("#projects-agent-settings").open && document.activeElement.id === "projects-filter"')
                await evaluate('document.querySelector("#projects-account").value="1";document.querySelector("#projects-account").dispatchEvent(new Event("change"));')
                await evaluate('document.querySelector("#projects-filter").value="example";document.querySelector("#projects-filter").dispatchEvent(new Event("input"));')
                assert await evaluate('document.querySelectorAll(".projects-choice:not(.hidden)").length === 1 && document.querySelector("[name=project_key][value=other]").closest(".projects-choice").classList.contains("hidden")')
                await evaluate('document.querySelector("#projects-select-all").click()')
                await until('document.querySelectorAll("[name=project_key]:checked").length === 2 && document.querySelector("#projects-selected-count").textContent.includes("已选 2 个")')
                assert await evaluate('document.querySelector("[name=project_key][value=other]").checked && document.querySelector("[name=project_key][value=other]").closest(".projects-choice").classList.contains("hidden")')
                await evaluate('document.querySelector("#projects-agent-form").requestSubmit()')
                await until('document.querySelector("#projects-feedback").textContent.includes("已保存")')
                assert json.loads(fixture.service._one('SELECT project_keys_json FROM projects_agents WHERE account_id=1')['project_keys_json']) == ['example', 'other']
                await until('document.querySelector("#projects-progress-text").textContent.includes("1 / 2")')
                assert await evaluate('document.querySelector("#projects-progress-bar").value === 50')
                await reload()
                await until('document.querySelectorAll("[name=project_key]:checked").length === 2 && document.querySelector("#projects-selected-count").textContent.includes("已选 2 个")')
                await evaluate('document.querySelector("#projects-filter").value="example";document.querySelector("#projects-filter").dispatchEvent(new Event("input"));document.querySelector("#projects-clear-all").click();')
                await until('document.querySelectorAll("[name=project_key]:checked").length === 0 && document.querySelector("#projects-selected-count").textContent.includes("已选 0 个")')
                assert await evaluate('document.querySelectorAll(".projects-choice:not(.hidden)").length === 1 && !document.querySelector("[name=project_key][value=other]").checked')
                await evaluate('document.querySelector("[name=project_key][value=example]").click()')
                await until('document.querySelector("#projects-selected-count").textContent.includes("已选 1 个")')
                await evaluate('document.querySelector("#projects-filter").value="";document.querySelector("#projects-filter").dispatchEvent(new Event("input"));document.querySelector("[name=project_key][value=other]").click();')
                await until('document.querySelector("#projects-selected-count").textContent.includes("已选 2 个")')
                await evaluate('document.querySelector("[name=project_key][value=other]").click()')
                await until('document.querySelector("#projects-selected-count").textContent.includes("已选 1 个")')
                await evaluate('document.querySelector("[name=instructions]").value="按实际交互完整指挥";document.querySelector("#projects-agent-form").requestSubmit();')
                await until('document.querySelector("#projects-feedback").textContent.includes("已保存")')
                record = fixture.service._one('SELECT * FROM projects_agents WHERE account_id=1')
                assert json.loads(record['project_keys_json']) == ['example']
                assert record['instructions'] == '按实际交互完整指挥'
                await reload()
                await until('document.querySelectorAll("[name=project_key]:checked").length === 1 && document.querySelector("[name=project_key][value=example]").checked && document.querySelector("#projects-selected-count").textContent.includes("已选 1 个")')
                assert await evaluate('document.querySelector("[name=instructions]").value === "按实际交互完整指挥" && !document.querySelector("[name=project_key][value=other]").checked')
                await until('document.querySelector("#projects-schedule-form")?.elements.interval_minutes.disabled === false')
                await evaluate('document.querySelector("#projects-schedule-settings").open=true;document.querySelector("#projects-agent-settings").open=true;')
                assert await evaluate('(()=>{const form=document.querySelector("#projects-schedule-form");return !form.elements.schedule_enabled.checked && form.elements.interval_minutes.value === "60"})()')
                assert await evaluate('(()=>{const input=document.querySelector("#projects-schedule-form").elements.interval_minutes;input.value="0";const low=!input.checkValidity();input.value="1441";const high=!input.checkValidity();input.value="60";return low && high && input.checkValidity()})()')
                original_schedule = fixture.service.state(1)['agents'][0]['schedule']
                rejected_schedule = await evaluate('Promise.all([{enabled:false,interval_minutes:0},{enabled:false,interval_minutes:1441},{enabled:false,interval_minutes:1.5},{enabled:"true",interval_minutes:60}].map(body=>fetch("/api/projects/agents/1/schedule",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(response=>response.status)))')
                assert rejected_schedule == [422, 422, 422, 422]
                assert fixture.service.state(1)['agents'][0]['schedule'] == original_schedule
                await until('document.querySelector("[data-work]") !== null')
                await evaluate('document.querySelector("[data-work]").click()')
                await until('document.querySelector("[data-submission]") !== null')
                assert await evaluate('document.querySelector("#projects-delivery-duration").textContent === "完成耗时 6 分 58 秒"')
                await evaluate('document.querySelector("[data-submission]").click()')
                await until('document.querySelector("[data-candidate-path]") !== null')
                await evaluate('document.querySelector("[data-candidate-path]").click()')
                await until('document.querySelector("#projects-delivery-preview").textContent === "VALUE = 2\\n"')
                # example 的交付已通过；加入未完成的 other，避免计划验证被“项目池已完成”门禁提前结束。
                await evaluate('document.querySelector("[name=project_key][value=other]").click();document.querySelector("#projects-agent-form").requestSubmit();')
                await until('document.querySelector("#projects-feedback").textContent.includes("已保存")')
                public_gate['quota'].update(known=True, observed_at=time.time(),
                    windows={'five_hour': {'utilization': 25.0, 'reset_at': time.time() + 3600},
                        'seven_day': {'utilization': 10.0, 'reset_at': time.time() + 86400}}, hit=[])
                fixture.service._event(1, 'pi', {'text': '额度视图已更新'})
                await until('document.querySelector("#projects-quota-five_hour [data-quota-value]").textContent === "25%"')
                assert await evaluate('document.querySelector("#projects-quota-seven_day [data-quota-value]").textContent === "10%" && document.querySelector("#projects-quota-five_hour [data-quota-description]").textContent.includes("30%")')
                await evaluate('window.quotaFlash=false;window.quotaObserver=new MutationObserver(()=>{if(document.querySelector("#projects-quota-five_hour [data-quota-value]").textContent!=="25%")window.quotaFlash=true});window.quotaObserver.observe(document.querySelector("#projects-quota-five_hour"),{childList:true,subtree:true});')
                await evaluate('document.querySelector("[data-pi-action=start]").click()')
                await until('document.querySelector("#projects-state").textContent.includes("正在启动") && document.querySelector("[data-pi-action=start]").disabled')
                await evaluate('document.querySelector("[data-pi-action=start]").click();new Promise(resolve=>setTimeout(resolve,100))')
                assert requested_paths.count('/api/projects/agents/1/start') == 1
                start_response.set()
                await until('document.querySelector("#projects-state").textContent.includes("指挥中")')
                assert not await evaluate('window.quotaFlash')
                await evaluate('window.quotaObserver.disconnect();document.querySelector("#projects-tab-events").click()')
                assert await evaluate('document.querySelector("#projects-tab-events").getAttribute("aria-selected")==="true" && document.querySelector("#projects-terminal-panel").classList.contains("hidden")')
                fixture.service._event(1, 'pi', {'text': '<img src=x onerror="window.eventInjected=true">实际交互'})
                await until('document.querySelector("#projects-events").textContent.includes("实际交互")')
                assert not await evaluate('!!window.eventInjected || !!document.querySelector("#projects-events img")')
                running_generation = fixture.service.state(1)['agents'][0]['generation']
                assert fixture.service.state(1)['agents'][0]['controller_active']
                await evaluate('(()=>{const form=document.querySelector("#projects-schedule-form");form.elements.schedule_enabled.click();form.elements.interval_minutes.value="15";form.requestSubmit()})()')
                await until('document.querySelector("#projects-feedback").textContent.includes("自动计划已保存")')
                running = fixture.service.state(1)['agents'][0]
                assert running['controller_active'] and running['generation'] == running_generation
                assert running['schedule']['enabled'] and running['schedule']['interval_minutes'] == 15
                await until('document.querySelector("#projects-schedule-status").textContent.includes("间隔 15 分钟") && document.querySelector("#projects-schedule-next").textContent.length > 0')
                await evaluate('(()=>{const form=document.querySelector("#projects-schedule-form");form.elements.schedule_enabled.click();form.elements.interval_minutes.value="37"})()')
                await evaluate('document.querySelector("#projects-agent-form").elements.instructions.value="尚未保存的业务指南";document.querySelector("#projects-model-form").elements.models.value="unsaved-model";document.querySelector("[name=project_key][value=other]").click();')
                fixture.service._event(1, 'pi', {'text': '定时表单保留检查'})
                await until('document.querySelector("#projects-events").textContent.includes("定时表单保留检查")')
                assert await evaluate('(()=>{const form=document.querySelector("#projects-schedule-form");return !form.elements.schedule_enabled.checked && form.elements.interval_minutes.value === "37"})()')
                assert await evaluate('document.querySelector("#projects-agent-form").elements.instructions.value === "尚未保存的业务指南" && document.querySelector("#projects-model-form").elements.models.value === "unsaved-model" && !document.querySelector("[name=project_key][value=other]").checked')
                assert fixture.service.state(1)['agents'][0]['schedule']['interval_minutes'] == 15
                await evaluate('document.querySelector("#projects-schedule-form").requestSubmit()')
                await until('document.querySelector("#projects-feedback").textContent.includes("自动计划已关闭")')
                running = fixture.service.state(1)['agents'][0]
                assert running['controller_active'] and running['generation'] == running_generation
                assert not running['schedule']['enabled'] and running['schedule']['interval_minutes'] == 37
                await evaluate('document.querySelector("#projects-account").value="2";document.querySelector("#projects-account").dispatchEvent(new Event("change"));')
                await until('document.querySelector("#projects-schedule-form").elements.interval_minutes.value === "60"')
                assert not await evaluate('document.querySelector("#projects-schedule-form").elements.schedule_enabled.checked')
                await evaluate('document.querySelector("#projects-schedule-form").elements.interval_minutes.value="22";document.querySelector("#projects-schedule-form").requestSubmit();')
                await until('document.querySelector("#projects-feedback").textContent.includes("自动计划已关闭")')
                assert fixture.service.state(2)['agents'][0]['schedule']['interval_minutes'] == 22
                await evaluate('document.querySelector("#projects-account").value="1";document.querySelector("#projects-account").dispatchEvent(new Event("change"));')
                await until('document.querySelector("#projects-schedule-form").elements.interval_minutes.value === "37"')
                await evaluate('document.querySelector("#projects-schedule-form").elements.interval_minutes.value="41";document.querySelector("#projects-account").value="2";document.querySelector("#projects-account").dispatchEvent(new Event("change"));')
                await until('document.querySelector("#projects-schedule-form").elements.interval_minutes.value === "22"')
                await evaluate('document.querySelector("#projects-account").value="1";document.querySelector("#projects-account").dispatchEvent(new Event("change"));')
                await until('document.querySelector("#projects-schedule-form").elements.interval_minutes.value === "37"')
                await reload()
                await until('document.querySelector("#projects-schedule-form")?.elements.interval_minutes.value === "37" && document.querySelector("#projects-account").value === "1"')
                await evaluate('document.querySelector("#projects-schedule-settings").open=true;document.querySelector("#projects-agent-settings").open=true;')
                assert not await evaluate('document.querySelector("#projects-schedule-form").elements.schedule_enabled.checked')
                assert fixture.service.state(1)['agents'][0]['controller_active']
                assert fixture.service.state(1)['agents'][0]['generation'] == running_generation
                await evaluate('(()=>{const form=document.querySelector("#projects-schedule-form");form.elements.schedule_enabled.click();form.elements.interval_minutes.value="19";form.requestSubmit()})()')
                await until('document.querySelector("#projects-feedback").textContent.includes("自动计划已保存")')
                await evaluate('document.querySelector("[data-pi-action=pause]").click()')
                await until('document.querySelector("#projects-state").textContent.includes("已暂停")')
                assert not fixture.service.state(1)['agents'][0]['schedule']['enabled']
                await until('document.querySelector("#projects-schedule-status").textContent.includes("定时已关闭")')
                await evaluate('document.querySelector("#projects-account").value="2";document.querySelector("#projects-account").dispatchEvent(new Event("change"));document.querySelector("#projects-account").value="1";document.querySelector("#projects-account").dispatchEvent(new Event("change"));')
                await until('!document.querySelector("#projects-schedule-form").elements.schedule_enabled.checked && document.querySelector("#projects-schedule-form").elements.interval_minutes.value === "19"')
                fixture.service.configure_schedule(1, True, 19)
                fixture.service._write('UPDATE projects_agents SET schedule_next_at=? WHERE account_id=1', (time.time() + 90,))
                fixture.service._event(1, 'pi', {'text': '待机时间视图已更新'})
                await until('document.querySelector("#projects-state").textContent.includes("待机") && document.querySelector("#projects-schedule-next").textContent.includes("后检查")')
                fixture.service.configure_schedule(1, False, 19)
                await until('document.querySelector("#projects-schedule-status").textContent.includes("定时已关闭")')
                public_gate.update(allowed=False, reason='window', retryable=True, retry_at=time.time() + 600,
                    message='休息中，等待上海当地运行时段')
                fixture.service._event(1, 'pi', {'text': '等待原因视图已更新'})
                await until('document.querySelector("#projects-admission").textContent.includes("等待上海当地运行时段")')
                assert await evaluate('document.querySelector("#projects-next-action").textContent.includes("手动启动或恢复")')
                public_gate.update(allowed=True, reason='allowed', retryable=False, retry_at=None, message=None)
                fixture.service._event(1, 'pi', {'text': '运行条件恢复'})
                await evaluate('document.querySelector("[data-research=example]").click()')
                await until('document.querySelector("#projects-research").open')
                assert not await evaluate('!!window.researchInjected || !!document.querySelector("#projects-research-body img")')
                await evaluate('document.querySelector("#projects-model-form").closest("details").open=true;document.querySelector("#projects-model-form [name=models]").value="updated-model";document.querySelector("#projects-model-form").requestSubmit();')
                await until('document.querySelector("#projects-feedback").textContent.includes("模型配置已保存")')
                assert configuration.agent_configuration()['api_key'] == 'browser-private-key'
                assert 'api_key' not in configuration.public()
                assert not await evaluate('!!document.querySelector("[id^=projects-legacy], [data-legacy]") || document.querySelector("#projects-agent-form").closest("section.view").textContent.includes("旧 Projects 只读历史")')
                # 具体计划阻塞原因优先展示，避免重启后的通用文案掩盖真正需要处理的条件。
                fixture.service._write('UPDATE projects_agents SET message=?,schedule_state=?,schedule_message=? WHERE account_id=1',
                    ('服务已重启，保留原目标和会话', 'blocked', '合成模型配置需要处理'))
                fixture.service._event(1, 'pi', {'text': '计划具体阻塞说明已更新'})
                await until('document.querySelector("#projects-message").textContent === "合成模型配置需要处理"')
                # 累计已跨过单轮时长，下一轮仍应恢复同一目标，并取得完整的单轮时限。
                fixture.service._write('UPDATE projects_work SET status=?,work_sec=?,segment_started_at=NULL,ended_at=NULL WHERE id=?',
                    ('paused', 1804.6653017997742, work['id']))
                fixture.service.configure_schedule(1, True, 19)
                fixture.service._write('UPDATE projects_agents SET status=?,budget_sec=?,schedule_enabled=1,schedule_state=?,schedule_message=?,schedule_next_at=? WHERE account_id=1',
                    ('paused', 1800, 'scheduled', '原目标等待下一轮接续', time.time() + 90))
                fixture.service._event(1, 'pi', {'text': '原目标跨轮接续视图已更新'})
                await until('document.querySelector("#projects-message").textContent === "原目标等待下一轮接续"')
                assert await evaluate('document.querySelector("#projects-budget").textContent === "目标累计耗时 30 分 4 秒 · 下轮可用时长 30 分 0 秒" && document.querySelector("#projects-state").textContent.includes("待机")')
                assert await evaluate('document.querySelector("[name=budget_minutes]").closest("label").textContent.includes("单轮指挥时长") && !document.querySelector("#projects-agent-form").textContent.includes("累计预算耗尽")')
                await evaluate('document.querySelector("[data-pi-action=start]").click()')
                await until('document.querySelector("#projects-state").textContent.includes("指挥中") && document.querySelector("#projects-budget").textContent.includes("本轮剩余")')
                resumed_turn = fixture.service.view(1)['agents'][0]
                assert 1700 < fixture.pi.turn_timeouts[-1] <= 1800
                assert resumed_turn['controller_active'] and resumed_turn['work']['id'] == work['id']
                assert resumed_turn['work']['session_id'] == work['session_id']
                assert resumed_turn['progress']['elapsed_work_sec'] == 1804.6653017997742
                assert resumed_turn['progress']['turn_active'] and resumed_turn['progress']['turn_budget_sec'] == 1800
                assert 1700 < resumed_turn['progress']['remaining_work_sec'] <= 1800
                # 用隔离 Pi 返回真实 timeout 结果，经真实收口与计划分支驱动界面，不等待实际三十分钟。
                fixture.pi.timeout_turn.set()
                await until('document.querySelector("#projects-message").textContent.includes("本轮指挥时限已到") && document.querySelector("#projects-state").textContent.includes("待机") && document.querySelector("#projects-budget").textContent.includes("下轮可用时长")')
                ended_turn = fixture.service.view(1)['agents'][0]
                assert not ended_turn['controller_active'] and ended_turn['status'] == 'paused'
                assert ended_turn['schedule']['enabled'] and ended_turn['schedule']['state'] == 'scheduled'
                assert ended_turn['schedule']['next_run_at'] > time.time()
                assert ended_turn['progress']['elapsed_work_sec'] == 1804.6653017997742
                assert not ended_turn['progress']['turn_active'] and ended_turn['progress']['remaining_work_sec'] == 1800
                assert await evaluate('document.querySelector("#projects-budget").textContent === "目标累计耗时 30 分 4 秒 · 下轮可用时长 30 分 0 秒" && document.querySelector("#projects-next-action").textContent === "到达下次时间后自动检查，接续未完成目标。" && !document.querySelector("#projects-overview").textContent.includes("累计预算已用尽")')
                turn_evidence = await evaluate('Object.fromEntries(["state","message","budget","next-action","schedule-next"].map(key=>[key,document.querySelector("#projects-"+key).textContent]))')
                await evaluate('document.querySelector("#projects-account").value="2";document.querySelector("#projects-account").dispatchEvent(new Event("change"))')
                await until('document.querySelector("#projects-account").value === "2" && document.querySelector("#projects-current").textContent.includes("尚未开始工程目标")')
                assert not await evaluate('document.querySelector("#projects-message").textContent.includes("本轮指挥时限已到") || document.querySelector("#projects-budget").textContent.includes("30 分 4 秒")')
                await evaluate('document.querySelector("#projects-account").value="1";document.querySelector("#projects-account").dispatchEvent(new Event("change"))')
                await until('document.querySelector("#projects-message").textContent.includes("本轮指挥时限已到")')
                await evaluate('document.querySelectorAll(".projects-settings > details").forEach(value=>value.open=false);document.querySelector("#projects-tab-terminal").click();window.scrollTo(0,0);')
                for width, height, theme, name in ((1280, 900, 'dark', 'desktop'), (390, 844, 'light', 'mobile')):
                    await rpc('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False}, session)
                    await evaluate(f'document.documentElement.dataset.theme="{theme}"')
                    await asyncio.sleep(0.2)
                    image = await rpc('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False}, session)
                    (evidence / (name + '.png')).write_bytes(base64.b64decode(image['data']))
                    overflow = await evaluate('document.documentElement.scrollWidth <= window.innerWidth ? [] : Array.from(document.querySelectorAll("body *")).filter(value => value.getBoundingClientRect().right > innerWidth + 1).slice(0,16).map(value => ({tag:value.tagName,id:value.id,class:value.className,width:value.getBoundingClientRect().width,right:value.getBoundingClientRect().right}))')
                    assert not overflow, {'width': width, 'overflow': overflow}
                await evaluate('location.hash="#topics"')
                await until('window.projectStreams.length > 0 && window.projectStreams.every(value => value.wasClosed)')
                assert before_operations == (len(fixture.terminal.started), len(fixture.terminal.sent), len(fixture.terminal.controls)), '切账号或翻页意外操作了原生终端'
                assert not errors, errors
                legacy_paths = ('/api/project-catalog', '/api/project-iteration-batches', '/api/project-instances',
                    '/api/project-step-attempts', '/api/project-iterations-stream')
                assert not any(path.startswith(legacy_paths) for path in requested_paths), '新页面仍请求旧项目接口'
        assert source_sha256 == {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in source_paths}, '受测源码在验证期间发生变化，请重新验证'
        result = {'status': 'passed', 'started_at': started_at, 'finished_at': time.time(), 'source_sha256': source_sha256,
            'turn_time_limit': {'elapsed_work_sec': 1804.6653017997742, 'budget_sec': 1800,
                'pi_timeout_sec': fixture.pi.turn_timeouts[-1],
                'active_remaining_work_sec': resumed_turn['progress']['remaining_work_sec'],
                'synthetic_pi_timeout': True, 'display': turn_evidence},
            'feed_fixture': {'historical_observations': 450, 'historical_works': len(historical_works),
                'initial_cursor': initial_cursor, 'reconnected_last_event_id': str(disconnect_id)},
            'checks': ['真实表单与SQLite保存', 'Pi启动暂停', 'SSE事件及切页关闭',
            '450条旧终端观察不回放', '首次SSE从快照高水位订阅', '迟到旧工程画面不覆盖当前目标',
            '交互20条最新倒序分页', '工程10条稳定分页及同时间排序', '浏览旧页新增记录不跳页且有提示',
            '新记录提示返回最新页', '目标切换立即清除旧画面', 'SSE服务端断开后原生Last-Event-ID重连',
            '页面读取及翻页不启动Pi或操作Claude终端', '切账号及快速重选不操作原生终端',
            '筛选时全选覆盖全部项目', '筛选时清空全部项目', '单选实时更新已选数量', '项目池保存重载回显',
            '自动计划默认关闭与间隔范围', '运行中启停自动计划不重建Pi', 'SSE保留未保存的计划输入',
            '计划切账号及重载回填', '人工暂停关闭自动计划',
            '顶部账号与总览及默认收起配置', '真实目标进度与已完成状态', '完成目标总览与工程列表及交付详情显示耗时',
            '累计耗时排除暂停等待及小时格式保留秒数', '未知额度不冒充零',
            '具体计划阻塞原因优先于重启通用文案', '目标累计跨越单轮时限仍恢复原目标原会话',
            '活动轮剩余与下轮可用时长明确区分', '单轮到时真实收口并按原计划等待接续', '单轮接续状态切换账号不串',
            '额度阈值与操作回执缓存', '启动即时反馈及禁止重复点击', '终端交互标签与明确等待原因',
            '待机倒计时及全部配置编辑保护', '折叠配置搜索快捷键',
            '模型密钥不回显', '研究与事件XSS', '冻结交付与源码预览', '无旧历史入口及请求', '1280暗色与390亮色布局']}
        (evidence / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        return result
    finally:
        start_response.set()
        if process and process.returncode is None:
            process.terminate(); await process.wait()
        server.should_exit = True; thread.join(timeout=5)
        fixture.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='验证 Pi Projects 浏览器界面')
    parser.add_argument('--evidence', type=Path, default=ROOT / '.deploy/pi-projects/verification/browser')
    print(json.dumps(asyncio.run(verify(parser.parse_args().evidence)), ensure_ascii=False))
