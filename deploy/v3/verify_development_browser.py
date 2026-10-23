"""通过真实浏览器核对完整任务的页面、API 与数据库投影。"""
from __future__ import annotations

import asyncio
import base64
import json
import shutil
import socket
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from websockets.asyncio.client import connect


async def verify_browser(application, evidence: Path, pilots: list[dict], *, validate_configuration=None) -> dict:
    """仅在回环提供合成数据库，核对连续对话、最终成果和主备用量。

    :param application: 禁止启动生产 lifespan 的本机验证 ASGI 应用。
    :param evidence: 截图及公开 API 回执位置。
    :param pilots: 已通过 SQLite 独立核对的真实内容试点。
    :param validate_configuration: 配置保存后独立核对模型调用与持久化的可选回调。
    :return: 浏览器断言结果，失败抛出异常。
    """
    evidence.mkdir(parents=True, exist_ok=True)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    service = uvicorn.Server(uvicorn.Config(application, log_level='error', lifespan='off', loop='asyncio'))
    server_thread = threading.Thread(target=service.run, kwargs={'sockets': [listener]}, daemon=True)
    server_thread.start()
    chrome = shutil.which('google-chrome') or shutil.which('chromium')
    if not chrome:
        raise RuntimeError('缺少本机 Chrome／Chromium')
    process = None
    errors = []
    try:
        deadline = time.monotonic() + 10
        while not service.started and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        if not service.started:
            raise RuntimeError('本机隔离 API 未就绪')
        with tempfile.TemporaryDirectory(prefix='development-browser-') as profile:
            with socket.socket() as debug:
                debug.bind(('127.0.0.1', 0))
                debug_port = debug.getsockname()[1]
            process = await asyncio.create_subprocess_exec(chrome, '--headless=new', '--no-sandbox',
                '--disable-dev-shm-usage', '--disable-background-networking', '--no-first-run',
                '--proxy-server=http://127.0.0.1:9', '--proxy-bypass-list=127.0.0.1;localhost',
                f'--user-data-dir={profile}', f'--remote-debugging-port={debug_port}', 'about:blank',
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(60):
                try:
                    with opener.open(f'http://127.0.0.1:{debug_port}/json/version', timeout=1) as response:
                        version = json.load(response)
                    break
                except OSError:
                    await asyncio.sleep(0.1)
            else:
                raise RuntimeError('浏览器未在期限内启动')
            async with connect(version['webSocketDebuggerUrl'], proxy=None, max_size=8 * 1024 * 1024) as channel:
                command_id = 0

                async def rpc(method: str, parameters: dict | None = None, session: str | None = None) -> dict:
                    """调用有界 CDP，收集页面异常。

                    :param method: CDP 方法。
                    :param parameters: 结构化参数。
                    :param session: 页面会话。
                    :return: 实际响应。
                    """
                    nonlocal command_id
                    command_id += 1
                    payload = {'id': command_id, 'method': method, 'params': parameters or {}}
                    if session:
                        payload['sessionId'] = session
                    await channel.send(json.dumps(payload))
                    async with asyncio.timeout(15):
                        while True:
                            reply = json.loads(await channel.recv())
                            if reply.get('method') == 'Runtime.exceptionThrown':
                                errors.append(reply.get('params', {}).get('exceptionDetails', {}).get('text'))
                            if reply.get('method') == 'Page.javascriptDialogOpening':
                                errors.append(reply.get('params', {}).get('message'))
                            if reply.get('id') == command_id:
                                if 'error' in reply:
                                    raise RuntimeError('浏览器命令失败：' + method)
                                return reply.get('result', {})

                target = await rpc('Target.createTarget', {'url': 'about:blank'})
                attached = await rpc('Target.attachToTarget', {'targetId': target['targetId'], 'flatten': True})
                session = attached['sessionId']
                await rpc('Page.enable', session=session)
                await rpc('Runtime.enable', session=session)

                async def evaluate(expression: str):
                    """执行页面操作并直接返回值。

                    :param expression: 本工具固定的测试表达式。
                    :return: 实际页面值。
                    """
                    result = await rpc('Runtime.evaluate', {'expression': expression,
                        'awaitPromise': True, 'returnByValue': True}, session)
                    if 'exceptionDetails' in result:
                        raise RuntimeError('页面脚本失败：' + result['exceptionDetails'].get('text', 'unknown'))
                    return result['result'].get('value')

                async def wait_for(expression: str) -> None:
                    """等待实际 DOM 就绪，不跳过失败条件。

                    :param expression: 返回布尔值的固定表达式。
                    :return: None。
                    """
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        if await evaluate(expression):
                            return
                        await asyncio.sleep(0.1)
                    raise RuntimeError('页面等待超时：' + expression)

                await rpc('Page.navigate', {'url': f'http://127.0.0.1:{port}/#projects'}, session)
                await wait_for('document.querySelector("#project-library-count")?.textContent.includes("完整需求")')
                assert await evaluate('document.querySelectorAll("[data-project-preview]").length') == 2
                configuration_result = None
                if validate_configuration:
                    await wait_for('document.querySelector("#project-requester-status")?.textContent.includes("密钥已配置")')
                    initial = await evaluate('fetch("/api/settings/project-requester").then(r=>r.json())')
                    endpoint = urlsplit(initial['base_url'])
                    changed_url = f'{endpoint.scheme}://{endpoint.netloc}/updated/v1'
                    models = ['fixture-unavailable', 'gemini-3-flash-agent', 'deepseek-flash']
                    await evaluate('document.querySelector("#project-requester-form").closest("details").open=true')
                    await evaluate(f'document.querySelector("#project-requester-form").elements.base_url.value={json.dumps(changed_url)}')
                    await evaluate(f'document.querySelector("#project-requester-form").elements.models.value={json.dumps(chr(10).join(models))}')
                    await evaluate('document.querySelector("#project-requester-form").elements.api_key.value="isolated-updated-test-key"')
                    await evaluate('document.querySelector("#project-requester-form").requestSubmit()')
                    await wait_for('document.querySelector("#project-requester-status")?.textContent.includes("已保存")')
                    assert await evaluate('document.querySelector("#project-requester-form").elements.api_key.value') == ''
                    public = await evaluate('fetch("/api/settings/project-requester").then(r=>r.json())')
                    assert public['base_url'] == changed_url and public['models'] == models and public['api_key_configured']
                    assert 'api_key' not in public and 'isolated-updated-test-key' not in json.dumps(public)
                    configuration_result = validate_configuration(public)
                    await evaluate('document.querySelector("[data-requester-reset]").click()')
                    await wait_for('document.querySelector("#project-requester-status")?.textContent.includes("环境配置")')
                    restored = await evaluate('fetch("/api/settings/project-requester").then(r=>r.json())')
                    assert restored['base_url'] == initial['base_url'] and restored['models'] == initial['models']
                for pilot in pilots:
                    await evaluate(f'selectProjectBatch({pilot["batch_id"]})')
                    await wait_for(f'Boolean(document.querySelector("[data-project-instance=\\"{pilot["instance_id"]}\\"]"))')
                    await evaluate(f'document.querySelector("[data-project-instance=\\"{pilot["instance_id"]}\\"]").click()')
                    await wait_for('document.querySelector("#project-instance-detail")?.textContent.includes("交付已接受")')
                    assert await evaluate('document.querySelector("#project-instance-detail").textContent.includes("deepseek-flash")')
                    await evaluate('document.querySelector("details[data-scenario-id]").open=true')
                    await evaluate('document.querySelector("[data-scenario-conversation]").click()')
                    await wait_for('document.querySelector("#modal-content")?.textContent.includes("完整任务连续对话")')
                    count = await evaluate('document.querySelectorAll("#modal-content article").length')
                    assert count == len(pilot['conversation'])
                    await evaluate('document.querySelector("#modal-close").click()')
                    await evaluate('document.querySelector("[data-scenario-usage]").click()')
                    await wait_for('document.querySelector("#modal-content")?.textContent.includes("需求方（外接）")')
                    assert await evaluate('document.querySelector("#modal-content").textContent.includes("未知")')
                    await evaluate('document.querySelector("#modal-close").click()')
                    base = f'/api/project-instances/{pilot["instance_id"]}'
                    detail = await evaluate(f'fetch({json.dumps(base)}).then(r=>r.json())')
                    task = detail['scenarios'][0]['tasks'][0]
                    assert (task['status'], task['development_phase']) == ('passed', 'accepted')
                    assert task['requester']['model'] == 'deepseek-flash'
                    (evidence / (pilot['project'] + '-api.json')).write_text(json.dumps(detail, ensure_ascii=False, indent=2) + '\n')
                # 非可信对话只能作为文本展示，不能在弹窗或页面创建元素。
                await evaluate('window.__originalDevelopmentGoal=state.projectInstanceDetail.scenarios[0].tasks[0].goal;state.projectInstanceDetail.scenarios[0].tasks[0].goal="<img src=x onerror=window.__developmentXss=1>";paintProjectInstance()')
                assert not await evaluate('Boolean(window.__developmentXss)')
                assert await evaluate('document.querySelectorAll("#project-instance-detail img").length') == 0
                await evaluate('state.projectInstanceDetail.scenarios[0].tasks[0].goal=window.__originalDevelopmentGoal;paintProjectInstance()')
                await evaluate('document.querySelector("details[data-scenario-id]").open=true')
                for width, height in ((1280, 900), (390, 844)):
                    await rpc('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
                        'deviceScaleFactor': 1, 'mobile': width < 500}, session)
                    for theme in ('dark', 'light'):
                        if await evaluate('document.documentElement.dataset.theme') != theme:
                            await evaluate('document.querySelector("#theme-toggle").click()')
                        assert await evaluate(f'document.documentElement.scrollWidth <= window.innerWidth+2')
                        shot = await rpc('Page.captureScreenshot', {'format': 'png'}, session)
                        (evidence / f'{width}-{theme}.png').write_bytes(base64.b64decode(shot['data']))
                        if validate_configuration:
                            await evaluate('document.querySelector("#project-requester-form").scrollIntoView({block:"center"})')
                            assert await evaluate('Array.from(document.querySelectorAll("#project-requester-form input, #project-requester-form textarea")).every(node=>{const rect=node.getBoundingClientRect();return rect.left>=0 && rect.right<=window.innerWidth})')
                            shot = await rpc('Page.captureScreenshot', {'format': 'png'}, session)
                            (evidence / f'configuration-{width}-{theme}.png').write_bytes(base64.b64decode(shot['data']))
                assert not errors, errors
                return {'status': 'passed', 'projects': len(pilots), 'conversation_messages': sum(len(p['conversation']) for p in pilots),
                    'themes': ['dark', 'light'], 'widths': [1280, 390], 'javascript_errors': errors,
                    'dynamic_configuration': configuration_result}
    finally:
        (evidence / 'diagnostics.json').write_text(json.dumps({'javascript_errors': errors}, ensure_ascii=False, indent=2) + '\n')
        if process and process.returncode is None:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=10)
        service.should_exit = True
        server_thread.join(timeout=10)
        listener.close()
