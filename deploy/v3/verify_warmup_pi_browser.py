"""用真实 Chrome 和隔离工程服务验证两个独立入口，不接触生产账号或模型。"""
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
from projects import ProjectsService
from projects_api import projects_router
from test_projects_agent import ProjectsAgentTests


async def verify(evidence: Path) -> dict:
    """验证独立指南、池、计划、记录、周期和只读导航。:param evidence: 私有证据目录。:return: 实际检查报告。"""
    evidence.mkdir(parents=True, exist_ok=True)
    sources = ('webui/app.js', 'webui/projects.js', 'webui/index.html', 'webui/style.css',
        'orchestrator/projects.py', 'orchestrator/projects_store.py', 'orchestrator/projects_api.py', 'deploy/v3/verify_warmup_pi_browser.py')
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    projects = ProjectsAgentTests('test_pause_rejects_old_generation_before_any_terminal_write')
    warmup = ProjectsAgentTests('test_pause_rejects_old_generation_before_any_terminal_write')
    projects.setUp(); warmup.setUp()
    original = warmup.service
    original.close()
    warmup.service = ProjectsService(warmup.root, warmup.database, threading.Lock(), warmup.catalog,
        warmup.terminal, original.account, original.admission, original.provider, original.verifier,
        warmup.pi, namespace='warmup', auto_cycle=True)
    warmup.addCleanup(warmup.service.close)
    original_start = warmup.terminal.start

    def start(account, record):
        """隔离终端使用真实养号命名空间。:param account: 合成账号。:param record: 工作。:return: 原生定位。"""
        reference = original_start(account, record)
        return reference | {'source': f"warmup:{record['id']}:{record['generation']}"}

    warmup.terminal.start = start
    projects.service.configure(1, ['other'], '项目空间独立指南', 3600)
    projects.service.configure_schedule(1, True, 30)
    projects.service._write('UPDATE projects_agents SET schedule_next_at=? WHERE account_id=1', (time.time() + 1800,))
    warmup.service.configure(1, ['other'], '养号第一账号指南', 1800)
    warmup.activate(2, ['example', 'other'])
    warmup.service.configure(2, ['example', 'other'], '养号第二账号独立指南', 1800)
    initial = warmup.start_work(2)
    work = warmup.service._one('SELECT * FROM projects_work WHERE id=?', (initial['work_id'],))
    (warmup.terminal.workspace(work) / 'library/app.py').write_text('VALUE = 2\n')
    warmup.verification = {'status': 'passed', 'feedback': ['隔离工程验收通过']}
    warmup.tool('project_submit', {'summary': '浏览器工程交付'}, account_id=2)
    warmup.service._write('UPDATE projects_work SET work_sec=? WHERE id=?', (418.9, work['id']))
    warmup.service._write("UPDATE projects_agents SET status='paused' WHERE account_id=2")
    warmup.service.configure_schedule(2, True, 180, 300)
    warmup.service._write('UPDATE projects_agents SET schedule_next_at=? WHERE account_id=2', (time.time() + 10800,))
    warmup.service._event(2, 'observation', {'screen': '养号工程当前最新画面'}, work['id'])
    cycle = {'number': 2, 'completed': 1, 'total': 2}
    original_view, original_work = warmup.service.view, warmup.service._public_work

    def public_work(row):
        """给真实工程记录附加待验证的周期展示合同。:param row: 真实工作行。:return: 公开工作。"""
        value = original_work(row)
        if value: value['cycle_no'] = 2
        return value

    def view(account_id=None):
        """通过真实服务视图提供独立的周期合同夹具。:param account_id: 可选账号。:return: 公开视图。"""
        value = original_view(account_id)
        for agent in value['agents']:
            agent['cycle'] = dict(cycle)
            if cycle['number'] == 3:
                agent['progress'].update(completed=0, remaining=2, total=2, ready=2, waiting=0)
                agent['passed'] = []
        return value

    warmup.service._public_work = public_work
    warmup.service.view = view
    provider = ProjectRequesterSettings(warmup.root / 'provider.json', {})
    provider.save('https://example.invalid/v1', ['browser-test-model'], 'local-private-key')
    application = FastAPI()
    application.include_router(projects_router(lambda: projects.service))
    application.include_router(projects_router(lambda: warmup.service, prefix='/api/accounts/warmup/pi'))
    requests, quota_saves = [], []
    delay_save, save_entered, release_save, save_returned = (threading.Event() for _ in range(4))

    @application.middleware('http')
    async def record(request: Request, call_next):
        """仅记录隔离请求方法和路径，不采集凭据或指南正文。:param request: 请求。:param call_next: 后继。:return: 原响应。"""
        requests.append((request.method, request.url.path))
        delayed = delay_save.is_set() and request.method == 'PUT' and request.url.path == '/api/accounts/warmup/pi/agents/2'
        if delayed:
            delay_save.clear(); save_entered.set()
            await asyncio.to_thread(release_save.wait, 10)
        response = await call_next(request)
        if delayed: save_returned.set()
        return response

    @application.get('/api/auth/me')
    def auth():
        """隔离回环服务无需认证。:return: 本地状态。"""
        return {'auth_required': False}

    @application.get('/api/accounts/login-drafts')
    def drafts():
        """本地没有登录草稿。:return: 空列表。"""
        return []

    @application.get('/api/accounts')
    def accounts():
        """账号摘要仅引用养号空间，故意保留关闭的旧开关。:return: 合成账号。"""
        result = []
        for aid in (1, 2):
            agent = warmup.service.view(aid)['agents'][0]
            result.append({'id': aid, 'name': f'合成账号 {aid}', 'profile_path': 'isolated', 'enabled': True,
                'warmup_engine': 'projects', 'warmup_enabled': 0, 'warmup_interval_min_hours': 3,
                'warmup_interval_max_hours': 5, 'warmup_quota_5h_limit_percent': 55,
                'warmup_quota_7d_limit_percent': 55,
                'project_pi': {key: agent[key] for key in ('status', 'message', 'controller_active', 'schedule', 'work')}})
        result.append({'id': 3, 'name': '旧 worker 合成账号', 'profile_path': 'isolated', 'enabled': True,
            'warmup_engine': 'worker', 'cc2api_account_id': 99, 'warmup_enabled': 0,
            'warmup_interval_min_hours': 3, 'warmup_interval_max_hours': 5})
        return result

    @application.put('/api/accounts/{aid}/warmup')
    def quota(aid: int, body: dict):
        """核对实际额度表单不会偷带旧计划字段。:param aid: 合成账号。:param body: 表单。:return: 已保存。"""
        quota_saves.append({'account_id': aid, 'payload': body})
        if aid != 3:
            assert set(body) == {'warmup_quota_5h_limit_percent', 'warmup_quota_7d_limit_percent'}
        return {'ok': True}

    @application.get('/api/settings/project-requester')
    def settings():
        """读取共用脱敏模型设置。:return: 公开配置。"""
        return provider.public()

    application.mount('/', StaticFiles(directory=str(ROOT / 'webui'), html=True))
    listener = socket.socket(); listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(application, lifespan='off', log_level='error', loop='asyncio'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True); thread.start()
    process, errors, checks = None, [], []
    before_project = projects.service._one('SELECT * FROM projects_agents WHERE account_id=1')
    before_warmup = warmup.service._one('SELECT * FROM projects_agents WHERE account_id=2')
    operations = (len(projects.terminal.started), len(projects.terminal.sent), len(warmup.terminal.started), len(warmup.terminal.sent))
    try:
        with tempfile.TemporaryDirectory(prefix='separate-pi-chrome-', ignore_cleanup_errors=True) as profile:
            debug = socket.socket(); debug.bind(('127.0.0.1', 0)); debug_port = debug.getsockname()[1]; debug.close()
            chrome = shutil.which('google-chrome') or shutil.which('chromium')
            assert chrome, '缺少 Chrome'
            process = await asyncio.create_subprocess_exec(chrome, '--headless=new', '--no-sandbox',
                '--disable-dev-shm-usage', '--no-first-run', '--disable-background-networking',
                '--proxy-server=http://127.0.0.1:9', '--proxy-bypass-list=127.0.0.1;localhost',
                f'--user-data-dir={profile}', f'--remote-debugging-port={debug_port}', 'about:blank',
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            connection = None
            for _ in range(80):
                try:
                    with opener.open(f'http://127.0.0.1:{debug_port}/json/version', timeout=1) as response:
                        connection = json.load(response)
                    break
                except OSError: await asyncio.sleep(0.1)
            assert connection, 'Chrome 调试入口未就绪'
            async with connect(connection['webSocketDebuggerUrl'], proxy=None, max_size=8 * 1024 * 1024) as channel:
                command = 0

                async def rpc(method, params=None, session=None):
                    """执行 CDP 命令并捕获真实页面异常。:param method: 方法。:param params: 参数。:param session: 页面。:return: 原响应。"""
                    nonlocal command
                    command += 1
                    payload = {'id': command, 'method': method, 'params': params or {}}
                    if session: payload['sessionId'] = session
                    await channel.send(json.dumps(payload))
                    async with asyncio.timeout(15):
                        while True:
                            value = json.loads(await channel.recv())
                            if value.get('method') == 'Runtime.exceptionThrown': errors.append(value['params']['exceptionDetails'])
                            if value.get('method') == 'Page.javascriptDialogOpening':
                                raise AssertionError('隔离页面出现未预期原生弹窗：' + value['params']['type'])
                            if value.get('id') == command:
                                assert 'error' not in value, value
                                return value.get('result', {})

                target = await rpc('Target.createTarget', {'url': 'about:blank'})
                session = (await rpc('Target.attachToTarget', {'targetId': target['targetId'], 'flatten': True}))['sessionId']
                await rpc('Page.enable', session=session); await rpc('Runtime.enable', session=session)

                async def evaluate(expression):
                    """在真实 DOM 执行断言或交互。:param expression: 表达式。:return: JSON 值。"""
                    value = await rpc('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True}, session)
                    assert 'exceptionDetails' not in value, value
                    return value.get('result', {}).get('value')

                async def until(expression):
                    """等待真实界面条件，不用固定延迟冒充通过。:param expression: 成功条件。:return: None。"""
                    for _ in range(120):
                        if await evaluate(expression): return
                        await asyncio.sleep(0.1)
                    raise AssertionError('界面等待失败：' + expression)

                await rpc('Page.addScriptToEvaluateOnNewDocument', {'source': 'window.testStreams=[];const OriginalSource=window.EventSource;window.EventSource=class extends OriginalSource{constructor(...args){super(...args);window.testStreams.push(this)}close(){this.closedForTest=true;super.close()}};window.scheduleBodies=[];const originalFetch=window.fetch;window.fetch=(path,settings)=>{if(settings?.method==="PUT"&&String(path).endsWith("/schedule"))window.scheduleBodies.push({path,body:JSON.parse(settings.body)});return originalFetch(path,settings)};'}, session)
                await rpc('Page.navigate', {'url': f'http://127.0.0.1:{port}/#accounts'}, session)
                await until('document.querySelector("[data-warmup-console=\\"2\\"]") !== null')
                assert await evaluate('JSON.stringify(Array.from(document.querySelectorAll(".tabs a"),link=>[link.dataset.tab,link.querySelector(".tab-cn").textContent])) === JSON.stringify([["accounts","账号"],["environments","环境"],["topics","题库"],["tasks","普通任务"],["runs","运行记录"],["projects","项目迭代"],["warmup","养号迭代"]])')
                assert await evaluate('document.querySelector("[data-warmup-console=\\"2\\"]").closest("tr").textContent.includes("180～300 分钟随机")')
                assert not await evaluate('document.querySelector("[data-warmup-console=\\"2\\"]").closest("tr").textContent.includes("Pi 养号未开启")')
                assert await evaluate('document.querySelector("[data-warmup-console=\\"2\\"]").closest("tr").querySelector("[data-warmup-now],[data-warmup-resume]") === null')
                checks.append('账号状态来自独立养号工程计划而非旧开关')
                await evaluate('document.querySelector("[data-warmup-console=\\"2\\"]").click()')
                await until('document.querySelector("#projects-account")?.value === "2" && document.querySelector("#projects-screen")?.textContent === "养号工程当前最新画面"')
                assert await evaluate('location.hash === "#warmup" && document.querySelector("#projects-title").textContent === "养号迭代" && document.querySelector("#projects-overview").dataset.namespace === "warmup"')
                assert await evaluate('document.querySelector("#projects-agent-form").elements.instructions.value === "养号第二账号独立指南" && document.querySelector("#projects-agent-form").elements.budget_minutes.value === "30"')
                assert await evaluate('document.querySelector("#projects-cycle").textContent === "第 2 轮 · 完成 1 / 2" && !document.querySelector("#projects-cycle").classList.contains("hidden")')
                assert await evaluate('document.querySelector("#projects-history").textContent.includes("第 2 轮") && document.querySelector("#projects-history").textContent.includes("完成耗时 6 分 58 秒")')
                assert all(method == 'GET' for method, _ in requests), requests
                checks.extend(['账号入口准确预选并只读加载', '养号真实工程历史与耗时', '本轮进度与周期标识'])
                await evaluate('document.querySelector("#projects-agent-form").elements.instructions.value="尚未保存的养号编辑";location.hash="#projects"')
                await until('document.querySelector("#projects-title")?.textContent === "项目迭代" && document.querySelector("#projects-account")?.value === "1"')
                assert await evaluate('document.querySelector("#projects-agent-form").elements.instructions.value === "项目空间独立指南" && document.querySelector("#projects-cycle").classList.contains("hidden") && document.querySelector("#projects-interval-max").classList.contains("hidden")')
                assert await evaluate('window.testStreams.filter(stream=>stream.url.includes("/accounts/warmup/pi/")).every(stream=>stream.closedForTest)')
                await evaluate('location.hash="#warmup"')
                await until('document.querySelector("#projects-title")?.textContent === "养号迭代" && document.querySelector("#projects-account")?.value === "1"')
                assert await evaluate('document.querySelector("#projects-agent-form").elements.instructions.value === "养号第一账号指南"')
                checks.extend(['两个入口独立指南池与预算', '切页关闭原订阅并清除未保存表单缓存'])
                await evaluate('location.hash="#accounts"')
                await until('document.querySelector("[data-warmup-config=\\"2\\"]") !== null')
                await evaluate('document.querySelector("[data-warmup-config=\\"2\\"]").click()')
                assert await evaluate('document.querySelector("#warmup-legacy-interval").classList.contains("hidden") && document.querySelector("#warmup-legacy-enabled").classList.contains("hidden") && document.querySelector("#warmup-form").elements.interval_min_hours.disabled')
                await evaluate('document.querySelector("#warmup-form").requestSubmit()')
                await until('document.querySelector("#warmup-modal").classList.contains("hidden")')
                assert quota_saves[-1]['account_id'] == 2 and quota_saves[-1]['payload'] == {'warmup_quota_5h_limit_percent': 55, 'warmup_quota_7d_limit_percent': 55}
                assert projects.service._one('SELECT * FROM projects_agents WHERE account_id=1') == before_project
                assert warmup.service._one('SELECT * FROM projects_agents WHERE account_id=2') == before_warmup
                checks.append('工程额度保存不提交旧开关间隔且保护两个空间计划指南预算')
                await evaluate('document.querySelector("[data-warmup-config=\\"3\\"]").click()')
                assert await evaluate('!document.querySelector("#warmup-legacy-interval").classList.contains("hidden") && !document.querySelector("#warmup-form").elements.interval_min_hours.disabled')
                await evaluate('document.querySelector("#warmup-form").elements.enabled.checked=true;document.querySelector("#warmup-form").requestSubmit()')
                await until('document.querySelector("#warmup-modal").classList.contains("hidden")')
                assert quota_saves[-1]['payload']['enabled'] is True and quota_saves[-1]['payload']['interval_min_hours'] == 3 and quota_saves[-1]['payload']['interval_max_hours'] == 5
                checks.append('旧 worker 账号保留原配置表单行为')
                await evaluate('document.querySelector("[data-warmup-config=\\"2\\"]").click();document.querySelector("#warmup-projects-link").click()')
                await until('document.querySelector("#projects-account")?.value === "2"')
                assert await evaluate('document.querySelector("#projects-schedule-form").elements.interval_minutes.value === "180" && document.querySelector("#projects-schedule-form").elements.interval_max_minutes.value === "300" && !document.querySelector("#projects-interval-max").classList.contains("hidden")')
                checks.append('额度弹窗引导对应账号的独立养号计划')
                await evaluate('document.querySelector("#projects-agent-form").elements.instructions.value="养号更新后的独立指南";document.querySelector("#projects-agent-form").requestSubmit()')
                await until('document.querySelector("#projects-feedback").textContent.includes("项目池和指南已保存")')
                assert warmup.service._one('SELECT instructions FROM projects_agents WHERE account_id=2')['instructions'] == '养号更新后的独立指南'
                assert projects.service._one('SELECT * FROM projects_agents WHERE account_id=1') == before_project
                await evaluate('document.querySelector("#projects-schedule-form").elements.interval_max_minutes.value="240";document.querySelector("#projects-schedule-form").requestSubmit()')
                await until('document.querySelector("#projects-feedback").textContent.includes("自动计划已保存")')
                assert warmup.service._one('SELECT schedule_interval_max_sec FROM projects_agents WHERE account_id=2')['schedule_interval_max_sec'] == 14400
                assert await evaluate('window.scheduleBodies.at(-1).path === "/api/accounts/warmup/pi/agents/2/schedule" && window.scheduleBodies.at(-1).body.interval_max_minutes === 240')
                assert projects.service._one('SELECT * FROM projects_agents WHERE account_id=1') == before_project
                checks.extend(['养号指南写入独立工程服务不覆盖项目空间', '随机间隔真实提交并保存且项目计划原样'])
                await evaluate('location.hash="#projects"')
                await until('document.querySelector("#projects-title")?.textContent === "项目迭代" && document.querySelector("#projects-account")?.value === "1"')
                await evaluate('document.querySelector("#projects-schedule-form").requestSubmit()')
                await until('document.querySelector("#projects-feedback").textContent.includes("自动计划已保存")')
                assert await evaluate('window.scheduleBodies.at(-1).path === "/api/projects/agents/1/schedule" && JSON.stringify(Object.keys(window.scheduleBodies.at(-1).body).sort()) === JSON.stringify(["enabled","interval_minutes"])')
                checks.append('项目迭代仍仅提交原固定间隔合同')
                await evaluate('location.hash="#accounts"')
                await until('document.querySelector("[data-warmup-console=\\"2\\"]") !== null')
                await evaluate('document.querySelector("[data-warmup-console=\\"2\\"]").click()')
                await until('document.querySelector("#projects-account")?.value === "2" && document.querySelector("#projects-screen")?.textContent === "养号工程当前最新画面"')
                # 人为延迟隔离服务回执，证明旧空间的保存不能把新空间未配置账号变成可启动。
                delay_save.set()
                await evaluate('document.querySelector("#projects-agent-form").elements.instructions.value="迟到回执的养号指南";document.querySelector("#projects-agent-form").requestSubmit()')
                for _ in range(100):
                    if save_entered.is_set(): break
                    await asyncio.sleep(0.05)
                assert save_entered.is_set(), '迟到保存夹具未进入'
                await evaluate('location.hash="#projects"')
                await until('document.querySelector("#projects-title")?.textContent === "项目迭代" && document.querySelector("#projects-account")?.value === "1"')
                await evaluate('document.querySelector("#projects-account").value="2";document.querySelector("#projects-account").dispatchEvent(new Event("change"))')
                await until('document.querySelector("#projects-account").value === "2" && document.querySelector("[data-pi-action=start]").disabled')
                release_save.set()
                for _ in range(100):
                    if save_returned.is_set(): break
                    await asyncio.sleep(0.05)
                assert save_returned.is_set(), '迟到保存夹具未返回'
                await evaluate('new Promise(resolve=>setTimeout(resolve,100))')
                assert await evaluate('document.querySelector("#projects-agent-form").elements.instructions.value === "" && document.querySelector("[data-pi-action=start]").disabled && document.querySelector("#projects-current").textContent.includes("尚未开始工程目标")')
                assert warmup.service._one('SELECT instructions FROM projects_agents WHERE account_id=2')['instructions'] == '迟到回执的养号指南'
                assert projects.service._one('SELECT * FROM projects_agents WHERE account_id=2') is None
                checks.append('迟到保存回执不能污染另一空间未配置账号或启用控制按钮')
                await evaluate('location.hash="#accounts"')
                await until('document.querySelector("[data-warmup-console=\\"2\\"]") !== null')
                await evaluate('document.querySelector("[data-warmup-console=\\"2\\"]").click()')
                await until('document.querySelector("#projects-account")?.value === "2" && document.querySelector("#projects-screen")?.textContent === "养号工程当前最新画面"')
                # 新一轮由服务端事实驱动；浏览器只更新显示，不能自行清零或发控制请求。
                cycle.update(number=3, completed=0)
                warmup.service._write('UPDATE projects_agents SET current_work_id=NULL WHERE account_id=2')
                warmup.service._event(2, 'cycle_started', {'cycle_no': 3})
                await until('document.querySelector("#projects-cycle").textContent === "第 3 轮 · 完成 0 / 2" && document.querySelector("#projects-screen").textContent === "尚无工程目标。"')
                assert await evaluate('document.querySelector("#projects-history").textContent.includes("第 2 轮") && document.querySelector("#projects-progress-text").textContent.includes("0 / 2")')
                checks.append('新周期清空当前画面并保留原交付耗时历史')
                for name, width, height, theme in (('desktop-dark', 1280, 900, 'dark'), ('desktop-light', 1280, 900, 'light'), ('mobile-dark', 390, 844, 'dark'), ('mobile-light', 390, 844, 'light')):
                    await rpc('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': width < 600}, session)
                    await evaluate('document.documentElement.dataset.theme=' + json.dumps(theme))
                    assert await evaluate('document.documentElement.scrollWidth <= innerWidth'), name
                    image = await rpc('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False}, session)
                    (evidence / (name + '.png')).write_bytes(base64.b64decode(image['data']))
                checks.append('桌面手机明暗四布局无横向溢出')
                # 此处只核导航目标；两个工程页面真实挂载已在前面验证，不引入无关页面的后端夹具。
                await evaluate('window.removeEventListener("hashchange",navigate)')
                for index, tab in enumerate(('accounts', 'environments', 'topics', 'tasks', 'runs', 'projects', 'warmup'), 1):
                    await evaluate('document.querySelector(' + json.dumps('.tabs [data-tab="' + tab + '"]') + ').click()')
                    await until('location.hash === ' + json.dumps('#' + tab))
                    await evaluate('location.hash="#shortcut-origin"')
                    await until('location.hash === "#shortcut-origin"')
                    await evaluate('document.dispatchEvent(new KeyboardEvent("keydown",{key:' + json.dumps(str(index)) + ',bubbles:true,cancelable:true}))')
                    assert await evaluate('location.hash === ' + json.dumps('#' + tab))
                assert await evaluate('JSON.stringify(Array.from(document.querySelectorAll(".tabs [data-nav-group]"),link=>link.dataset.navGroup)) === JSON.stringify(["基础配置","普通任务","工程迭代"]) && Array.from(document.querySelectorAll(".tabs .nav-group-start")).every(link=>getComputedStyle(link).borderLeftStyle==="solid" && getComputedStyle(link).borderLeftWidth==="1px")')
                checks.append('三功能分组七项导航及1到7快捷键目标一致')
                assert await evaluate('document.querySelectorAll("#tpl-warmup,#warmup-guide-form,#warmup-rounds").length === 0 && document.querySelectorAll(".tabs [data-tab=warmup]").length === 1')
                assert all(method == 'GET' or path in ('/api/accounts/2/warmup', '/api/accounts/3/warmup', '/api/accounts/warmup/pi/agents/2', '/api/accounts/warmup/pi/agents/2/schedule', '/api/projects/agents/1/schedule') for method, path in requests)
                assert not any('/rounds/' in path or '/topics' in path for _, path in requests)
                assert operations == (len(projects.terminal.started), len(projects.terminal.sent), len(warmup.terminal.started), len(warmup.terminal.sent))
                assert not projects.pi.entered.is_set() and not warmup.pi.entered.is_set()
                assert not errors, errors
                checks.extend(['无旧题库轮次接口或模板', '导航额度操作无Pi启动原生输入模型请求', '真实Chrome无JS异常'])
                await rpc('Target.closeTarget', {'targetId': target['targetId']})
        assert hashes == {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}, '验证期间源码改变，结果不能复用'
        result = {'status': 'passed', 'checks': checks, 'source_sha256': hashes, 'javascript_errors': errors,
            'model_requests': 0, 'request_count': len(requests), 'cycle_evidence': '服务端DTO夹具驱动真实DOM；循环执行与清理由独立后端测试验证'}
        (evidence / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        return result
    finally:
        release_save.set()
        if process and process.returncode is None:
            process.terminate()
            await process.wait()
        server.should_exit = True
        thread.join(timeout=5)
        warmup.doCleanups(); projects.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='验证独立养号工程与项目迭代入口')
    parser.add_argument('--evidence', type=Path, default=ROOT / '.deploy/pi-projects/warmup-engine-20261025/browser')
    print(json.dumps(asyncio.run(verify(parser.parse_args().evidence)), ensure_ascii=False))
