#!/usr/bin/env python3
"""新场景真实页面验证草案，仅用于独立合成部署，不写业务数据库。

本脚本要求 inner 已启动 main.app 的真实 HTTP 服务及场景调度 tick，且等待页面
创建／启动批次。它复用已有合成 CLI、私有评审与真实 Scheduler，不生成任务结果。
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import signal
import socket
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from websockets.asyncio.client import connect


_OBSERVATION_SCRIPT = """(() => {
  window.__scenarioBrowserProbe = {fetches: [], sources: [], messages: 0};
  const originalFetch = window.fetch.bind(window);
  window.fetch = (...args) => {
    const input = args[0];
    const url = typeof input === 'string' ? input : input.url;
    window.__scenarioBrowserProbe.fetches.push(new URL(url, location.href).pathname);
    return originalFetch(...args);
  };
  const OriginalEventSource = window.EventSource;
  window.EventSource = class extends OriginalEventSource {
    constructor(...args) {
      super(...args);
      window.__scenarioBrowserProbe.sources.push(this);
      this.addEventListener('project-state', () => window.__scenarioBrowserProbe.messages++);
    }
  };
})()"""


async def verify_scenario_browser(
    base: str,
    service_token: str,
    evidence_dir: Path,
    *,
    timeout_sec: int = 600,
    expected_capacity: int = 1,
    catalog_fault_request: Path | None = None,
) -> dict:
    """从真实页面创建并运行新场景，核对 DOM 与原 API 的执行结果。

    :param base: 仅当前随机合成部署的回环 HTTP 地址。
    :param service_token: 当前合成进程的 V3_INTERNAL_TOKEN，不写日志或进程参数。
    :param evidence_dir: 截图、公开 API 快照和浏览器诊断保存位置。
    :param timeout_sec: 等待真实任务完成的整体截止秒数。
    :param expected_capacity: 本次页面要提交的真实共享容量，草案默认容量一。
    :param catalog_fault_request: 可选的共享文件；inner 收到后将当前 catalog 置为不可用。
    :return: 公开任务和成本快照，供 inner 以真实 SQLite 独立对账。
    """
    parsed = urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('草案仅允许当前本机合成验证地址')
    if len(service_token) < 32 or expected_capacity not in (1, 2):
        raise ValueError('本次内部认证或容量参数不合法')
    chrome = shutil.which('google-chrome') or shutil.which('chromium')
    if not chrome:
        raise RuntimeError('本机缺少 Chrome／Chromium')
    evidence_dir.mkdir(parents=True, exist_ok=True)
    errors: list[dict] = []
    network_failures: list[dict] = []
    request_urls: dict[str, str] = {}
    dialogs: list[dict] = []
    summary: dict = {'status': 'running', 'real_model_calls': 0, 'validated': [], 'not_run': []}
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='scenario-browser-') as profile:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            debug_port = listener.getsockname()[1]
        process = await asyncio.create_subprocess_exec(
            chrome, '--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
            '--disable-background-networking', '--no-first-run',
            '--proxy-server=http://127.0.0.1:9', '--proxy-bypass-list=127.0.0.1;localhost',
            '--remote-debugging-address=127.0.0.1', f'--remote-debugging-port={debug_port}',
            f'--user-data-dir={profile}', 'about:blank', start_new_session=True,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(60):
                try:
                    with opener.open(f'http://127.0.0.1:{debug_port}/json/version', timeout=1) as response:
                        version = json.load(response)
                    break
                except OSError:
                    await asyncio.sleep(0.1)
            else:
                raise RuntimeError('本机 Chrome 未能在截止时间内启动')
            summary['browser'] = version.get('Browser')
            async with connect(version['webSocketDebuggerUrl'], proxy=None, max_size=8 * 1024 * 1024) as channel:
                command_id = 0

                async def rpc(method: str, parameters: dict | None = None, session: str | None = None) -> dict:
                    """顺序调用 CDP 并保留诊断事件，认证参数不进入输出。"""
                    nonlocal command_id
                    command_id += 1
                    payload = {'id': command_id, 'method': method, 'params': parameters or {}}
                    if session:
                        payload['sessionId'] = session
                    await channel.send(json.dumps(payload))
                    async with asyncio.timeout(15):
                        while True:
                            reply = json.loads(await channel.recv())
                            event = reply.get('method')
                            if event == 'Runtime.exceptionThrown':
                                detail = reply.get('params', {}).get('exceptionDetails', {})
                                errors.append({'text': detail.get('text'), 'url': detail.get('url'),
                                    'line': detail.get('lineNumber'), 'exception': detail.get('exception', {}).get('description')})
                            elif event == 'Network.requestWillBeSent':
                                detail = reply.get('params', {})
                                request_urls[detail.get('requestId', '')] = detail.get('request', {}).get('url', '')
                            elif event == 'Network.loadingFailed':
                                detail = reply.get('params', {})
                                network_failures.append({'url': request_urls.get(detail.get('requestId', '')),
                                    **{key: detail.get(key) for key in ('errorText', 'type', 'blockedReason')}})
                            elif event == 'Network.responseReceived':
                                detail = reply.get('params', {}).get('response', {})
                                if detail.get('status', 0) >= 400:
                                    network_failures.append({'url': detail.get('url'), 'status': detail.get('status')})
                            elif event == 'Page.javascriptDialogOpening':
                                detail = reply.get('params', {})
                                dialogs.append({'type': detail.get('type'), 'message': detail.get('message')})
                            if reply.get('id') == command_id:
                                if 'error' in reply:
                                    raise RuntimeError('CDP 命令失败：' + method)
                                return reply.get('result', {})

                target = await rpc('Target.createTarget', {'url': 'about:blank'})
                attached = await rpc('Target.attachToTarget', {'targetId': target['targetId'], 'flatten': True})
                session_id = attached['sessionId']
                await rpc('Page.enable', session=session_id)
                await rpc('Runtime.enable', session=session_id)
                await rpc('Network.enable', session=session_id)
                # 使用产品已存在的内部 Bearer 门禁；不新增认证入口、不改中间件。
                await rpc('Network.setExtraHTTPHeaders', {'headers': {'Authorization': 'Bearer ' + service_token}}, session_id)
                await rpc('Page.addScriptToEvaluateOnNewDocument', {'source': _OBSERVATION_SCRIPT}, session_id)

                async def evaluate(expression: str):
                    """执行真实页面操作和只读检查，不修改业务结果或页面业务状态。"""
                    reply = await rpc('Runtime.evaluate', {'expression': expression, 'awaitPromise': True,
                        'returnByValue': True}, session_id)
                    if 'exceptionDetails' in reply:
                        raise RuntimeError('浏览器页面脚本执行失败')
                    return reply['result'].get('value')

                async def wait_for(expression: str, *, timeout: float = 30) -> None:
                    """等待页面或真实 API 条件，在整体和局部截止时间内轮询。"""
                    async with asyncio.timeout(timeout):
                        while not await evaluate(expression):
                            if time.monotonic() - started > timeout_sec:
                                raise TimeoutError('真实场景浏览器链路达到整体截止')
                            if dialogs:
                                raise AssertionError('页面出现业务错误弹窗：' + dialogs[-1]['message'])
                            await asyncio.sleep(0.2)

                async def api(path: str, *, status: int = 200):
                    """读取浏览器实际同源 API，不创建替代结果或替换响应。"""
                    result = await evaluate(f"fetch({json.dumps(path)}).then(async r=>({{status:r.status,body:await r.json()}}))")
                    if result['status'] != status:
                        raise AssertionError('API 状态不符：' + path + '，实际 ' + str(result['status']))
                    return result['body']

                async def screenshot(name: str) -> None:
                    """保存当前真实页面，不修改渲染结果。"""
                    picture = await rpc('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False}, session_id)
                    (evidence_dir / name).write_bytes(base64.b64decode(picture['data']))

                async def capture_themes(prefix: str) -> None:
                    """核对宽窄屏和明暗主题，保存页面及真实横向溢出指标。"""
                    for width, height in ((1280, 900), (390, 844)):
                        await rpc('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
                            'deviceScaleFactor': 1, 'mobile': width < 500}, session_id)
                        for theme in ('dark', 'light'):
                            if await evaluate('document.documentElement.dataset.theme') != theme:
                                await evaluate('document.querySelector("#theme-toggle").click()')
                            await wait_for(f'document.documentElement.dataset.theme==={json.dumps(theme)}')
                            dimensions = await evaluate('({scroll:document.documentElement.scrollWidth,width:innerWidth})')
                            if dimensions['scroll'] > dimensions['width'] + 2:
                                raise AssertionError(f'{width}px {theme} 出现页面横向溢出：{dimensions}')
                            await screenshot(f'{prefix}-{width}-{theme}.png')

                await rpc('Page.navigate', {'url': base.rstrip('/') + '/#projects'}, session_id)
                await wait_for('Boolean(document.querySelector("#project-batch-form")?.elements.account_id.options.length)')
                await wait_for('document.querySelectorAll("#project-choice-list input[name=project_keys]").length===2')
                catalog = await api('/api/project-catalog')
                assert catalog['content_schema'] == 2 and len(catalog['projects']) == 2
                assert sum(item['scenario_count'] for item in catalog['projects']) == 2
                assert sum(item['task_count'] for item in catalog['projects']) == 6
                assert await evaluate('document.querySelector("#project-library-count").textContent.includes("6 个任务")')
                assert await evaluate('Number(document.querySelector("#project-batch-form").elements.timeout_sec.value)') == 600
                accounts = await api('/api/accounts')
                assert len(accounts) == 1, '浏览器验证必须只面对本次合成账号'
                assert await api('/api/project-iteration-batches') == [], 'inner 必须等待页面创建批次'
                await capture_themes('scenario-form')
                unsafe_name = '场景页面验证 <img src=x onerror="window.__scenarioXss=1">'
                fields = {'account_id': accounts[0]['id'], 'name': unsafe_name, 'concurrency': expected_capacity,
                    'timeout_sec': 60, 'task_budget_sec': 180, 'review_timeout_sec': 60, 'review_budget_sec': 240}
                await evaluate(f'''(() => {{
                  const form=document.querySelector('#project-batch-form');
                  for(const [key,value] of Object.entries({json.dumps(fields, ensure_ascii=False)})) {{
                    const input=form.elements[key]; input.value=String(value);
                    input.dispatchEvent(new Event('input',{{bubbles:true}}));
                    input.dispatchEvent(new Event('change',{{bubbles:true}}));
                  }}
                  if(!form.checkValidity()) throw new Error('页面表单存在非法字段');
                  form.requestSubmit();
                }})()''')
                await wait_for('document.querySelectorAll("[data-project-instance]").length===2')
                batches = await api('/api/project-iteration-batches')
                assert len(batches) == 1
                batch_id = batches[0]['id']
                batch = await api(f'/api/project-iteration-batches/{batch_id}')
                assert batch['status'] == 'paused' and batch['policy']['schema'] == 3
                for key in ('concurrency', 'timeout_sec', 'task_budget_sec', 'review_timeout_sec', 'review_budget_sec'):
                    assert batch['policy'][key] == fields[key], (key, batch['policy'])
                assert not await evaluate('Boolean(window.__scenarioXss)')
                assert await evaluate('document.querySelectorAll("#project-batch-detail img").length') == 0
                summary.update(batch_id=batch_id, initial_batch=batch, catalog=catalog)
                summary['validated'].extend(['真实页面创建policy3', '默认600与显式预算', '批次名称转义'])
                await evaluate('document.querySelector("[data-project-action=start]").click()')
                await wait_for('Boolean(document.querySelector("[data-project-action=pause]"))')
                first = next(item for item in batch['instances'] if item['project_key'] == 'fixture-one')
                await evaluate(f'document.querySelector("[data-project-instance=\\"{first["id"]}\\"]").click()')
                await wait_for('document.querySelectorAll("details[data-scenario-id]").length===1')
                await evaluate('document.querySelector("details[data-scenario-id]").open=true')
                await wait_for('document.querySelectorAll(".project-scenario-task").length===4')
                assert await evaluate('document.querySelector("#project-instance-detail").textContent.includes("同模型独立会话评审")')
                assert await evaluate('window.__scenarioBrowserProbe.fetches.filter(x=>/scenario-tasks.*\\/artifacts$/.test(x)).length') == 0
                await evaluate('scrollTo(0,Math.min(200,(document.documentElement.scrollHeight-innerHeight)/2))')
                scroll = await evaluate('scrollY')
                before_messages = await evaluate('window.__scenarioBrowserProbe.messages')
                await wait_for(f'window.__scenarioBrowserProbe.messages>={before_messages + 2}', timeout=20)
                assert await evaluate('document.querySelector("details[data-scenario-id]").open')
                assert abs(await evaluate('scrollY') - scroll) <= 4, '场景 SSE 重绘改变了页面滚动位置'
                summary['validated'].extend(['真实SSE更新', '场景展开与页面滚动保持', '回答按需读取'])
                await wait_for(f'''fetch('/api/project-iteration-batches/{batch_id}').then(r=>r.json()).then(b=>{{
                  if(b.status==='blocked')throw new Error('真实场景执行受阻'); return b.status==='completed';
                }})''', timeout=timeout_sec)
                final_batch = await api(f'/api/project-iteration-batches/{batch_id}')
                details = [await api(f'/api/project-instances/{item["id"]}') for item in final_batch['instances']]
                selected = [(item, task) for item in details for scene in item['scenarios'] for task in scene['tasks'] if task['selected']]
                assert len(selected) == 6 and all(task['status'] == 'passed' for _, task in selected)
                assert sum(bool(task['accepted_checkpoint_digest']) for _, task in selected) == 1
                assert all(task['attempt_count'] == (2 if task['task_key'] == 'Q3' else 1) for _, task in selected)
                assert any(execution['execution_status'] == 'timeout' for _, task in selected if task['task_key'] == 'Q3'
                    for execution in task['executions'])
                assert any(execution['role'] == 'review' for _, task in selected for execution in task['executions'])
                exposed = json.dumps(details, ensure_ascii=False)
                assert 'session_id' not in exposed and 'native_relative' not in exposed and 'rubric' not in exposed
                await wait_for('document.querySelector("#project-batch-detail").textContent.includes("本轮已收口")')
                await wait_for('document.querySelector("#project-instance-detail").textContent.includes("4 个通过")')
                assert await evaluate('document.querySelector("#project-instance-detail").textContent.includes("1 个代码检查点已接受")')
                await capture_themes('scenario-completed')
                attempts = []
                artifacts = []
                for item, task in selected:
                    attempts.append(await api(f'/api/project-instances/{item["id"]}/scenario-tasks/{task["id"]}/attempts'))
                    if task['task_key'] not in ('Q1', 'Q4') or item['project_key'] != 'fixture-one':
                        continue
                    await evaluate(f'document.querySelector("[data-scenario-artifact=\\"{task["id"]}\\"]").click()')
                    await wait_for('!document.querySelector("#modal").classList.contains("hidden") && document.querySelector("#modal-content").textContent.includes("回答与验收证据")')
                    artifact = await api(f'/api/project-instances/{item["id"]}/scenario-tasks/{task["id"]}/artifacts')
                    assert artifact['answer'] and artifact['code_accepted'] == (task['task_key'] == 'Q4')
                    assert await evaluate(f'document.querySelector("#modal-content").textContent.includes({json.dumps(artifact["answer"], ensure_ascii=False)})')
                    if task['task_key'] == 'Q4':
                        await evaluate('document.querySelector("#modal-content details:last-of-type").open=true')
                        await evaluate('document.querySelector("[data-scenario-file=\\"library/example.py\\"]").click()')
                        await wait_for('document.querySelector("#project-file-preview").textContent.includes("VALUE = 2")')
                    artifacts.append(artifact)
                    await evaluate('document.querySelector("#modal-close").click()')
                    await wait_for('document.querySelector("#modal").classList.contains("hidden")')
                usage = [await api(f'/api/project-instances/{item["id"]}/usage') for item in details]
                await evaluate('document.querySelector("[data-scenario-usage]").click()')
                await wait_for('!document.querySelector("#modal").classList.contains("hidden") && document.querySelector("#modal-content").textContent.includes("任务与评审用量")')
                assert await evaluate('document.querySelector("#modal-content").textContent.includes("缓存读 / 写")')
                assert await evaluate('document.querySelector("#modal-content").textContent.includes("评审")')
                await evaluate('document.querySelector("#modal-close").click()')
                await evaluate('location.hash="#topics"')
                await wait_for('window.eval("state.projectEventSource===null")')
                assert await evaluate('window.__scenarioBrowserProbe.sources.filter(s=>s.url.includes("project-iterations-stream")).every(s=>s.readyState===EventSource.CLOSED)')
                summary['validated'].extend(['真实API六任务通过', '仅修改任务接受代码', '真实timeout保留与接续',
                    '候选与评审角色分列', '固定回答与文件按需读取', '分类累计用量', '切页关闭SSE', '1280/390明暗主题'])
                summary.update(final_batch=final_batch, details=details, attempts=attempts, artifacts=artifacts, usage=usage)
                if catalog_fault_request is not None:
                    # 故障请求只通过本次共享证据文件交给 inner；没有额外产品 API。
                    catalog_fault_request.parent.mkdir(parents=True, exist_ok=True)
                    catalog_fault_request.write_text(json.dumps({'schema': 1, 'action': 'disable_current_catalog', 'batch_id': batch_id}) + '\n')
                    await wait_for('fetch("/api/project-catalog").then(r=>r.status===503)', timeout=30)
                    await evaluate('location.hash="#projects"')
                    await wait_for('document.querySelector("#project-feedback")?.textContent.includes("已有批次和成果仍可查看")')
                    assert len(await api('/api/project-iteration-batches')) == 1
                    assert (await api(f'/api/project-instances/{first["id"]}'))['content_schema'] == 2
                    assert (await api(f'/api/project-instances/{first["id"]}/usage'))['instance_id'] == first['id']
                    await evaluate(f'document.querySelector("[data-project-instance=\\"{first["id"]}\\"]").click()')
                    await wait_for('document.querySelectorAll("details[data-scenario-id]").length===1')
                    assert await evaluate('document.querySelector("#project-batch-form button[type=submit]").disabled')
                    await screenshot('scenario-catalog-unavailable-history.png')
                    summary['validated'].append('当前catalog503时历史API与页面仍可读')
                else:
                    summary['not_run'].append('catalog503故障注入：调用方未提供本次共享请求文件')
                await evaluate('location.hash="#topics"')
                await wait_for('window.eval("state.projectEventSource===null")')
                assert not errors, errors
                assert not dialogs, dialogs
                summary.update(status='passed', elapsed_sec=round(time.monotonic() - started, 3),
                    javascript_errors=errors, network_failures=network_failures, dialogs=dialogs)
        except BaseException as failure:
            summary.update(status='failed', error=type(failure).__name__ + ': ' + str(failure),
                elapsed_sec=round(time.monotonic() - started, 3), javascript_errors=errors,
                network_failures=network_failures, dialogs=dialogs)
            raise
        finally:
            (evidence_dir / 'scenario-browser.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    os.killpg(process.pid, signal.SIGKILL)
                    await process.wait()
    return summary


def main() -> None:
    """读取本次合成部署连接信息，运行真实页面验证草案。

    :return: None；断言或真实执行失败时非零退出。
    """
    parser = argparse.ArgumentParser(description='仅本机合成数据的新场景浏览器草案')
    parser.add_argument('--base', required=True)
    parser.add_argument('--service-token-file', required=True, type=Path)
    parser.add_argument('--evidence-dir', required=True, type=Path)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--capacity', type=int, choices=(1, 2), default=1)
    parser.add_argument('--catalog-fault-request', type=Path)
    args = parser.parse_args()
    result = asyncio.run(verify_scenario_browser(args.base, args.service_token_file.read_text().strip(), args.evidence_dir,
        timeout_sec=args.timeout, expected_capacity=args.capacity, catalog_fault_request=args.catalog_fault_request))
    print(json.dumps({'status': result['status'], 'batch_id': result['batch_id'],
        'validated': result['validated'], 'not_run': result['not_run']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
