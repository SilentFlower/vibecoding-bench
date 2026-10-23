"""使用回环 API、真实 Chrome 和 SQLite 验证新 Projects 页面，不调用真实账号。"""
from __future__ import annotations

import argparse
import asyncio
import base64
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
from project_library import materialize_snapshot, read_document
from projects_api import projects_router
from test_projects_agent import CatalogFixture, ProjectsAgentTests


class BrowserCatalog(CatalogFixture):
    """为浏览器提供含恶意 HTML 文本的研究材料。"""

    def project(self, key, detail=True):
        """返回不含可执行 HTML 的原始业务文本。:param key: 项目。:param detail: 详细标记。:return: 公开对象。"""
        value = super().project(key, detail)
        value.update(title=key + ' 项目研究', description='浏览器合成研究资料',
            research={'report': '<img src=x onerror="window.researchInjected=true">研究正文', 'roadmap': '保留原项目研究。'})
        return value


async def verify(evidence: Path) -> dict:
    """核对配置保存、Pi 生命周期、SSE、只读历史和手机布局。

    :param evidence: 截图与检查报告目录。
    :return: 实际检查结果。
    """
    evidence.mkdir(parents=True, exist_ok=True)
    fixture = ProjectsAgentTests('test_pause_rejects_old_generation_before_any_terminal_write')
    fixture.setUp()
    fixture.service.catalog = BrowserCatalog(fixture.root)
    fixture.activate(); initial = fixture.start_work()
    work = fixture.service._one('SELECT * FROM projects_work WHERE id=?', (initial['work_id'],))
    (fixture.terminal.workspace(work) / 'library/app.py').write_text('VALUE = 2\n')
    fixture.verification = {'status': 'passed', 'feedback': ['合成工程独立验收通过']}
    submitted = fixture.tool('project_submit', {'summary': '浏览器成果夹具'})
    directory = fixture.root / 'projects/submissions' / submitted['submission_id']
    materialize_snapshot(read_document(directory / 'snapshot.json'), fixture.root / 'projects/objects', directory / 'candidate')
    fixture.service._write("UPDATE projects_agents SET status='off' WHERE account_id=1")
    configuration = ProjectRequesterSettings(fixture.root / 'provider.json', {})
    configuration.save('https://example.invalid/v1', ['test-model'], 'browser-private-key')
    application = FastAPI()
    application.include_router(projects_router(lambda: fixture.service))

    @application.get('/api/accounts')
    def accounts():
        """返回合成账号。:return: 无凭据账号列表。"""
        return [{'id': 1, 'name': '浏览器合成账号', 'enabled': True}]

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

    @application.get('/api/project-iteration-batches')
    def legacy():
        """保留旧批次只读入口。:return: 合成旧记录。"""
        return [{'id': 19, 'name': '历史批次'}]

    @application.get('/api/project-iteration-batches/{batch_id}')
    def legacy_detail(batch_id: int):
        """读取旧状态。:param batch_id: 旧 ID。:return: 保留记录。"""
        return {'id': batch_id, 'name': '历史批次', 'status': 'active', 'instances': []}

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
                    raise AssertionError('浏览器等待失败：' + expression)

                await rpc('Page.addScriptToEvaluateOnNewDocument', {'source': '''window.projectStreams=[];
                    const Original=window.EventSource;window.EventSource=class extends Original{
                    constructor(...args){super(...args);window.projectStreams.push(this)}
                    close(){this.wasClosed=true;super.close()}};'''}, session)
                await rpc('Page.navigate', {'url': f'http://127.0.0.1:{port}/#projects'}, session)
                await until('document.querySelectorAll("[name=project_key]").length === 2')
                await evaluate('document.querySelector("#projects-account").value="1";document.querySelector("#projects-account").dispatchEvent(new Event("change"));')
                await evaluate('document.querySelector("[name=project_key][value=example]").checked=true;document.querySelector("[name=instructions]").value="按实际交互完整指挥";document.querySelector("#projects-agent-form").requestSubmit();')
                await until('document.querySelector("#projects-feedback").textContent.includes("已保存")')
                record = fixture.service._one('SELECT * FROM projects_agents WHERE account_id=1')
                assert json.loads(record['project_keys_json']) == ['example']
                assert record['instructions'] == '按实际交互完整指挥'
                await until('document.querySelector("[data-work]") !== null')
                await evaluate('document.querySelector("[data-work]").click()')
                await until('document.querySelector("[data-submission]") !== null')
                await evaluate('document.querySelector("[data-submission]").click()')
                await until('document.querySelector("[data-candidate-path]") !== null')
                await evaluate('document.querySelector("[data-candidate-path]").click()')
                await until('document.querySelector("#projects-delivery-preview").textContent === "VALUE = 2\\n"')
                await evaluate('document.querySelector("[data-pi-action=start]").click()')
                await until('document.querySelector("#projects-state").textContent.includes("指挥中")')
                fixture.service._event(1, 'pi', {'text': '<img src=x onerror="window.eventInjected=true">实际交互'})
                await until('document.querySelector("#projects-events").textContent.includes("实际交互")')
                assert not await evaluate('!!window.eventInjected || !!document.querySelector("#projects-events img")')
                await evaluate('document.querySelector("[data-pi-action=pause]").click()')
                await until('document.querySelector("#projects-state").textContent.includes("已暂停")')
                await evaluate('document.querySelector("[data-research=example]").click()')
                await until('document.querySelector("#projects-research").open')
                assert not await evaluate('!!window.researchInjected || !!document.querySelector("#projects-research-body img")')
                await evaluate('document.querySelector("#projects-model-form").closest("details").open=true;document.querySelector("#projects-model-form [name=models]").value="updated-model";document.querySelector("#projects-model-form").requestSubmit();')
                await until('document.querySelector("#projects-feedback").textContent.includes("模型配置已保存")')
                assert configuration.agent_configuration()['api_key'] == 'browser-private-key'
                assert 'api_key' not in configuration.public()
                await evaluate('document.querySelector("#projects-legacy-load").closest("details").open=true;document.querySelector("#projects-legacy-load").click()')
                await until('document.querySelector("[data-legacy]") !== null')
                await evaluate('document.querySelector("[data-legacy]").click()')
                await until('document.querySelector("#projects-legacy-detail").textContent.includes("历史批次")')
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
                assert not errors, errors
        result = {'status': 'passed', 'checks': ['真实表单与SQLite保存', 'Pi启动暂停', 'SSE事件及切页关闭',
            '模型密钥不回显', '研究与事件XSS', '冻结交付与源码预览', '旧历史只读', '1280暗色与390亮色布局']}
        (evidence / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        return result
    finally:
        if process and process.returncode is None:
            process.terminate(); await process.wait()
        server.should_exit = True; thread.join(timeout=5)
        fixture.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='验证 Pi Projects 浏览器界面')
    parser.add_argument('--evidence', type=Path, default=ROOT / '.deploy/pi-projects/verification/browser')
    print(json.dumps(asyncio.run(verify(parser.parse_args().evidence)), ensure_ascii=False))
