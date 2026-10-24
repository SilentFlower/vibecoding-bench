"""使用真实 Chrome、SQLite 和回环服务核验 Pi 养号现场，不调用真实模型。"""
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
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'orchestrator'))

from project_requester_settings import ProjectRequesterSettings
from test_warmup_pi import PiFixture, WarmupPiTests
from warmup_pi_api import warmup_pi_router


class BrowserPi(PiFixture):
    """为真实表单验证持有隔离控制者，不向外部服务发请求。"""

    def run(self, config, tools, event, stop, timeout_sec):
        """持有当前账号直到页面暂停。:param config: 冻结配置。:param tools: 受控工具。:param event: 事件。:param stop: 停止信号。:param timeout_sec: 预算。:return: 已停止。"""
        self.calls.append((config, timeout_sec))
        self.entered.set()
        stop.wait(min(timeout_sec, 120))
        return 'stopped'


async def verify(evidence: Path) -> dict:
    """验证原账号配置、Pi现场、分页、追加指南和移动布局。:param evidence: 证据目录。:return: 实际检查报告。"""
    evidence.mkdir(parents=True, exist_ok=True)
    sources = ('webui/app.js', 'webui/index.html', 'webui/style.css', 'orchestrator/warmup_pi.py',
        'orchestrator/warmup_pi_api.py', 'deploy/v3/verify_warmup_pi_browser.py')
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    fixture = WarmupPiTests('test_off_accounts_initialization_configuration_reads_and_recovery_never_enable')
    fixture.setUp()
    service = fixture.service
    fixture.enable()
    fixture.pi.mode = 'complete'
    service.start(1); fixture.join()
    agent = service._one('SELECT * FROM warmup_pi_agents WHERE account_id=1')
    completed = service._round(agent)
    assert completed['status'] == 'completed', fixture.pi.results
    frozen_topic = json.loads(completed['topic_json'])
    service._write('UPDATE warmup_pi_rounds SET work_sec=? WHERE id=?', (411.888, completed['id']))
    service._write("UPDATE accounts SET warmup_enabled=0,warmup_next_run_at=NULL,warmup_last_status='off' WHERE id=1")
    history = []
    for index in range(24):
        row = {**completed, 'id': f'{index + 1:032x}', 'created_at': completed['created_at'] - 10 - index,
            'session_id': f'historical-session-{index}', 'runtime_json': None, 'status': 'completed', 'work_sec': 90 + index}
        service._write('INSERT INTO warmup_pi_rounds(' + ','.join(row) + ') VALUES(' + ','.join('?' for _ in row) + ')', tuple(row.values()))
        history.append(row)
    for index in range(450):
        service._event(1, 'observation', {'screen': f'禁止回放的旧画面 {index}'}, history[0]['id'])
    for index in range(45):
        service._event(1, 'pi', {'text': f'历史交互 {index}'}, completed['id'])
    service._event(1, 'observation', {'screen': '本轮最新终端画面'}, completed['id'])
    service._event(1, 'observation', {'screen': '其他轮迟到的旧画面'}, history[0]['id'])
    current_cursor = service.snapshot(1)['cursor']
    fixture.pi = BrowserPi(); service.pi = fixture.pi
    fixture.gate.update(quota={'known': False, 'source': 'passive', 'windows': {},
        'limits': {'five_hour': 55, 'seven_day': 55}, 'hit': []})
    provider = ProjectRequesterSettings(fixture.root / 'provider.json', {})
    provider.save('https://example.invalid/v1', ['test-model'], 'browser-secret-key')
    application = FastAPI()
    application.include_router(warmup_pi_router(lambda: service))

    @application.get('/api/accounts')
    def accounts():
        """返回真实SQLite账号配置及安全展示名称。:return: 无凭据账号列表。"""
        return [{**fixture.account(aid), 'name': f'养号合成账号 {aid}', 'warmup_engine': 'pi',
            'warmup_quota_5h_limit_percent': 55, 'warmup_quota_7d_limit_percent': 55} for aid in (1, 2)]

    @application.get('/api/auth/me')
    def auth():
        """只对隔离测试取消登录。:return: 本地鉴权状态。"""
        return {'auth_required': False}

    @application.get('/api/accounts/login-drafts')
    def drafts():
        """隔离账号列表不含登录草稿。:return: 空草稿列表。"""
        return []

    @application.put('/api/accounts/{aid}/warmup')
    def settings(aid: int, body: dict):
        """保存页面实际提交的原间隔与开关。:param aid: 账号。:param body: 配置。:return: 保存状态。"""
        service._write('UPDATE accounts SET warmup_enabled=?,warmup_interval_min_hours=?,warmup_interval_max_hours=?,warmup_next_run_at=? WHERE id=?',
            (int(body['enabled']), body['interval_min_hours'], body['interval_max_hours'], time.time() + 10800 if body['enabled'] else None, aid))
        return {'ok': True}

    @application.get('/api/settings/project-requester')
    def model():
        """返回真实脱敏共享配置。:return: 模型状态。"""
        return provider.public()

    @application.put('/api/settings/project-requester')
    def save_model(body: dict):
        """保存隔离配置，留空密钥沿用。:param body: 表单。:return: 脱敏配置。"""
        provider.save(body['base_url'], body['models'], body.get('api_key'))
        return provider.public()

    application.mount('/', StaticFiles(directory=str(ROOT / 'webui'), html=True))
    listener = socket.socket(); listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(application, lifespan='off', log_level='error', loop='asyncio'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True); thread.start()
    process, errors, checks = None, [], []
    try:
        with tempfile.TemporaryDirectory(prefix='warmup-chrome-', ignore_cleanup_errors=True) as profile:
            debug = socket.socket(); debug.bind(('127.0.0.1', 0)); debug_port = debug.getsockname()[1]; debug.close()
            chrome = shutil.which('google-chrome') or shutil.which('chromium')
            assert chrome, '缺少Chrome'
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
                except OSError:
                    await asyncio.sleep(0.1)
            assert connection, 'Chrome调试入口未就绪'
            async with connect(connection['webSocketDebuggerUrl'], proxy=None, max_size=8 * 1024 * 1024) as channel:
                command_id = 0

                async def rpc(method, parameters=None, session=None):
                    """执行一次受控CDP命令并收集真实JS异常。:param method: 命令。:param parameters: 参数。:param session: 页面。:return: 原结果。"""
                    nonlocal command_id
                    command_id += 1
                    payload = {'id': command_id, 'method': method, 'params': parameters or {}}
                    if session: payload['sessionId'] = session
                    await channel.send(json.dumps(payload))
                    async with asyncio.timeout(15):
                        while True:
                            result = json.loads(await channel.recv())
                            if result.get('method') == 'Runtime.exceptionThrown': errors.append(result['params']['exceptionDetails'])
                            if result.get('id') == command_id:
                                if 'error' in result: raise RuntimeError(str(result['error']))
                                return result.get('result', {})

                target = await rpc('Target.createTarget', {'url': 'about:blank'})
                session = (await rpc('Target.attachToTarget', {'targetId': target['targetId'], 'flatten': True}))['sessionId']
                await rpc('Page.enable', session=session); await rpc('Runtime.enable', session=session)

                async def evaluate(expression):
                    """在实际页面执行表达式，JS错误明确失败。:param expression: 表达式。:return: JSON结果。"""
                    value = await rpc('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True}, session)
                    if 'exceptionDetails' in value: raise RuntimeError(str(value['exceptionDetails']))
                    return value.get('result', {}).get('value')

                async def until(expression):
                    """有界等待界面真实状态。:param expression: 成功条件。:return: None。"""
                    for _ in range(120):
                        if await evaluate(expression): return
                        await asyncio.sleep(0.1)
                    raise AssertionError('浏览器等待失败：' + expression)

                await rpc('Page.addScriptToEvaluateOnNewDocument', {'source': '''window.warmupStreams=[];
                    const Source=window.EventSource;window.EventSource=class extends Source{
                    constructor(...args){super(...args);window.warmupStreams.push(this)}
                    close(){this.wasClosed=true;super.close()}};'''}, session)
                await rpc('Page.navigate', {'url': f'http://127.0.0.1:{port}/#warmup'}, session)
                await until('document.querySelector("#warmup-screen")?.textContent === "本轮最新终端画面"')
                assert await evaluate('document.querySelector("#warmup-state").textContent.includes("已关闭") && document.querySelector("#warmup-duration").textContent.includes("6 分 51 秒")')
                assert await evaluate('document.querySelector("#warmup-quota-five_hour [data-quota-value]").textContent === "未采集"')
                assert not await evaluate('document.querySelector("#warmup-screen").textContent.includes("旧画面")')
                assert await evaluate('window.warmupStreams.some(value=>new URL(value.url).searchParams.get("after")===' + json.dumps(str(current_cursor)) + ')')
                assert not fixture.pi.calls
                checks.extend(['关闭配置保持关闭且不启动模型', '最新快照及高水位不回放450旧画面', '完成耗时与未知额度'])
                await evaluate('document.querySelector("[data-warmup-action=start]").click()')
                await until('document.querySelector("#warmup-feedback").textContent.includes("请先")')
                assert not fixture.pi.calls
                assert await evaluate('document.querySelectorAll("#warmup-events [data-warmup-event]").length === 20 && document.querySelectorAll("#warmup-rounds [data-warmup-round]").length === 10')
                await evaluate('document.querySelector("#warmup-tab-events").click();document.querySelector("#warmup-events-next").click();document.querySelector("#warmup-rounds-next").click()')
                await until('document.querySelector("#warmup-events-page").textContent.includes("第 2 页") && document.querySelector("#warmup-rounds-page").textContent.includes("第 2 页")')
                await evaluate('window.oldEvents=document.querySelector("#warmup-events").textContent;window.oldRounds=document.querySelector("#warmup-rounds").textContent')
                service._event(1, 'pi', {'text': '<img src=x onerror="window.injected=true">新的真实交互'}, completed['id'])
                await until('!document.querySelector("#warmup-events-new").classList.contains("hidden")')
                assert await evaluate('document.querySelector("#warmup-events").textContent===window.oldEvents && document.querySelector("#warmup-rounds").textContent===window.oldRounds')
                await evaluate('document.querySelector("#warmup-events-new").click();document.querySelector("#warmup-rounds-latest").click()')
                await until('document.querySelector("#warmup-events-page").textContent.includes("第 1 页") && document.querySelector("#warmup-rounds-page").textContent.includes("第 1 页")')
                await until('document.querySelector("#warmup-events").textContent.includes("新的真实交互")')
                assert not await evaluate('!!window.injected || !!document.querySelector("#warmup-events img")')
                checks.extend(['交互20条和轮次10条倒序分页', '旧页位置保留与新记录通知', '返回最新与事件XSS防护'])
                await evaluate('document.querySelector("#warmup-rounds [data-warmup-round]").click()')
                await until('document.querySelector("#warmup-round-detail").open')
                assert await evaluate('document.querySelector("#warmup-round-body").textContent') == '\n\n'.join(
                    [frozen_topic['prompt'], *[f'补充需求 {index + 1}\n{text}' for index, text in enumerate(frozen_topic['followups'])]])
                checks.append('轮次详情展示实际冻结需求与全部补充')
                await evaluate('document.querySelector("#warmup-guide-form").closest("details").open=true;document.querySelector("#warmup-guide-form").elements.instructions.value="新增养号指南：英文交流，先确认方案";document.querySelector("#warmup-guide-form").requestSubmit()')
                await until('document.querySelector("#warmup-feedback").textContent.includes("已保存")')
                assert fixture.account(1)['warmup_enabled'] == 0
                assert service._one('SELECT instructions FROM warmup_pi_agents WHERE account_id=1')['instructions'] == '新增养号指南：英文交流，先确认方案'
                await evaluate('document.querySelector("#warmup-account").value="2";document.querySelector("#warmup-account").dispatchEvent(new Event("change"))')
                await until('document.querySelector("#warmup-screen").textContent.includes("尚未开始")')
                assert await evaluate('document.querySelector("#warmup-guide-form").elements.instructions.value === ""')
                await evaluate('document.querySelector("#warmup-account").value="1";document.querySelector("#warmup-account").dispatchEvent(new Event("change"))')
                await until('document.querySelector("#warmup-guide-form").elements.instructions.value.includes("新增养号指南")')
                await evaluate('document.querySelector("#warmup-config").click()')
                await until('!document.querySelector("#warmup-modal").classList.contains("hidden")')
                assert await evaluate('(()=>{const form=document.querySelector("#warmup-form");return !form.enabled.checked && form.interval_min_hours.value==="3" && form.interval_max_hours.value==="5"})()')
                await evaluate('(()=>{const form=document.querySelector("#warmup-form");form.enabled.click();form.interval_min_hours.value="2";form.interval_max_hours.value="4";form.requestSubmit()})()')
                await until('document.querySelector("#warmup-schedule").textContent.includes("2～4")')
                assert await evaluate('location.hash==="#warmup" && document.querySelector("#warmup-guide-form").elements.instructions.value.includes("新增养号指南")')
                assert not fixture.pi.calls
                checks.extend(['追加指南原文保存且不启用养号', '切账号原指南回显及隔离', '旧间隔额度弹窗保存后留在现场且不覆盖指南'])
                await evaluate('document.querySelector("[data-warmup-action=start]").click()')
                await until('document.querySelector("#warmup-state").textContent.includes("指挥中")')
                assert len(fixture.pi.calls) == 1
                await evaluate('document.querySelector("[data-warmup-action=start]").click()')
                assert len(fixture.pi.calls) == 1
                assert fixture.pi.calls[0][0]['instructions'].endswith('新增养号指南：英文交流，先确认方案')
                await evaluate('document.querySelector("[data-warmup-action=pause]").click()')
                await until('document.querySelector("#warmup-state").textContent.includes("已关闭")')
                fixture.join()
                assert fixture.account(1)['warmup_enabled'] == 0
                checks.append('启动回执及禁止重复点击、暂停关闭后续并保留原轮')
                await evaluate('document.querySelector("#warmup-model-form").closest("details").open=true;document.querySelector("#warmup-model-form").elements.models.value="updated-model";document.querySelector("#warmup-model-form").requestSubmit()')
                await until('document.querySelector("#warmup-feedback").textContent.includes("模型配置已保存")')
                assert provider.agent_configuration()['api_key'] == 'browser-secret-key'
                assert not await evaluate('document.querySelector("#warmup-model-form").elements.api_key.value')
                checks.append('共享模型配置不回显或覆盖原密钥')
                await evaluate('document.querySelectorAll("#view details").forEach(value=>value.open=false);document.querySelector("#warmup-tab-terminal").click();scrollTo(0,0)')
                for width, height, theme, name in ((1280, 900, 'dark', 'desktop'), (390, 844, 'light', 'mobile')):
                    await rpc('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False}, session)
                    await evaluate(f'document.documentElement.dataset.theme="{theme}"')
                    await asyncio.sleep(0.2)
                    assert await evaluate('document.documentElement.scrollWidth<=innerWidth'), '页面产生横向溢出'
                    shot = await rpc('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False}, session)
                    (evidence / (name + '.png')).write_bytes(base64.b64decode(shot['data']))
                checks.append('1280暗色和390亮色布局')
                await evaluate('location.hash="#accounts"')
                await until('window.warmupStreams.every(value=>value.wasClosed)')
                await until('!!document.querySelector("[data-warmup-console=\\"2\\"]")')
                call_count = len(fixture.pi.calls)
                await evaluate('document.querySelector("[data-warmup-console=\\"2\\"]").click()')
                await until('document.querySelector("#warmup-account")?.value === "2" && document.querySelector("#warmup-screen").textContent.includes("尚未开始")')
                assert len(fixture.pi.calls) == call_count
                checks.append('账号页直达所选Pi现场且不启动模型')
                await evaluate('location.hash="#projects"')
                await until('window.warmupStreams.every(value=>value.wasClosed)')
                checks.append('离开养号现场关闭所有SSE')
                assert not errors, errors
        assert hashes == {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}, '受测源码在运行期间变化'
        report = {'status': 'passed', 'checks': checks, 'source_sha256': hashes, 'model_calls': 0}
        (evidence / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        return report
    finally:
        if process and process.returncode is None:
            process.terminate(); await process.wait()
        server.should_exit = True; thread.join(timeout=5)
        fixture.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=ROOT / '.deploy/pi-projects/warmup-pi-20261025/browser')
    print(json.dumps(asyncio.run(verify(parser.parse_args().evidence)), ensure_ascii=False))
