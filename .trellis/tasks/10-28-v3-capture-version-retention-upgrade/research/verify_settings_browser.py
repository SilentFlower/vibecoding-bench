"""使用实际静态页面与合成 API 回执验证配置、切页及抓包查看。"""
import asyncio
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[4]


class Handler(SimpleHTTPRequestHandler):
    """仅提供本地静态 WebUI。"""

    def __init__(self, *args, **kwargs):
        """固定静态目录。:param args: 请求参数。:param kwargs: 附加参数。:return: None。"""
        super().__init__(*args, directory=str(ROOT / 'webui'), **kwargs)

    def log_message(self, *args):
        """省略静态访问日志。:param args: 日志参数。:return: None。"""


async def verify() -> dict:
    """检查真实 DOM 和延迟响应，不发起模型或账号请求。:return: 浏览器验证证据。"""
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    settings = {aid: {'account_id': aid, 'claude_code_version': None,
        'projects_capture_enabled': False, 'warmup_capture_enabled': False} for aid in (1, 2)}
    requests, errors, themes, dialogs, captures = [], [], {}, [], []
    global_version = {'configured_version': None, 'env_default_version': '2.1.293', 'effective_version': '2.1.293'}
    delay = {'get': False, 'put': False}
    release = asyncio.Event()
    work_id = 'a' * 32

    async def respond(route):
        """提供与后端契约相同的公开测试数据。:param route: 请求。:return: None。"""
        path, method = route.request.url.split('/api', 1)[1], route.request.method
        path = path.split('?', 1)[0]
        requests.append((method, path))
        if path.endswith('/cli-settings'):
            aid = int(path.split('/')[2])
            if method == 'PUT':
                settings[aid].update(route.request.post_data_json)
            value = {**settings[aid], 'effective_claude_code_version': settings[aid]['claude_code_version'] or '2.1.293',
                'claude_code_version_source': 'account' if settings[aid]['claude_code_version'] else 'global'}
            if aid == 1 and delay[method.lower()]:
                await release.wait()
        elif path == '/auth/me':
            value = {'auth_required': False}
        elif path == '/accounts':
            value = [{'id': aid, 'name': f'fixture-{aid}', 'enabled': True, 'profile_path': 'synthetic'} for aid in (1, 2)]
        elif path == '/accounts/login-drafts':
            value = []
        elif path == '/topics':
            value = [{'id': 1, 'no': 1, 'title': '合成题目'}]
        elif path == '/tasks':
            value = []
        elif path == '/settings/runtime-model':
            value = {'configured_model': None, 'env_default_model': None, 'effective_model': None}
        elif path == '/settings/runtime-effort':
            value = {'configured_effort': None, 'env_default_effort': 'high', 'effective_effort': 'high', 'allowed_efforts': ['high', 'low']}
        elif path == '/settings/claude-code-version':
            value = global_version
        elif path == '/captures/run' and method == 'POST':
            payload = route.request.post_data_json
            version = payload.get('claude_code_version') or settings[payload['account_id']]['claude_code_version'] or global_version['effective_version']
            run_id = f'capture-{len(captures) + 1}'
            captures.append({'payload': payload, 'id': run_id, 'task_id': len(captures) + 1,
                'account_id': payload['account_id'], 'status': 'stopped', 'run_kind': 'capture',
                'claude_code_version': version, 'claude_effort_level': payload['effort_level'] or 'high',
                'capture_permission_mode': payload['permission_mode'], 'created_at': 1})
            value = {'run_id': run_id, 'claude_code_version': version}
        elif path == '/runs':
            value = [{key: item for key, item in run.items() if key != 'payload'} for run in captures]
        elif path.startswith('/runs/') and path.endswith('/files'):
            value = []
        elif path.startswith('/runs/') and path.endswith('/stats'):
            value = {'available': False}
        elif path.startswith('/runs/') and path.endswith('/transcript'):
            await route.fulfill(status=200, content_type='text/plain', body='合成抓包提交成功')
            return
        elif path.startswith('/runs/') and path.endswith('/capture'):
            run = next(item for item in captures if item['id'] == path.split('/')[2])
            value = {'available': False, 'status': 'empty', 'message': '尚未采到目标流量',
                'claude_code_version': run['claude_code_version'], 'files': [], 'index': {'entries': []}}
        elif path.startswith('/runs/'):
            run = next(item for item in captures if item['id'] == path.split('/')[2])
            value = {key: item for key, item in run.items() if key != 'payload'}
        elif path == '/settings/project-requester':
            value = {'base_url': '', 'models': [], 'ready': False, 'error': '合成环境，不启动模型'}
        elif path.endswith('/catalog'):
            value = {'projects': []}
        elif path.endswith('/snapshot'):
            value = {'state': {'agents': []}, 'cursor': 0, 'events': {'items': [], 'has_more': False}}
        elif path.endswith('/work/page'):
            value = {'items': [{'id': work_id, 'project_key': 'fixture', 'goal': '合成目标', 'status': 'stopped',
                'work_sec': 12, 'created_at': 1, 'ended_at': 2}], 'has_more': False}
        elif path.endswith('/actions'):
            value = []
        elif path.endswith('/capture'):
            value = {'available': True, 'status': 'partial', 'message': '已有部分数据，响应中断',
                'claude_code_version': '2.1.303', 'index': {'entries': [{'flow_id': 'fixture', 'capture_state': 'interrupted',
                    'request': {'path': '<img src=x onerror=alert(1)>', 'method': 'POST'}, 'response': {}}]},
                'files': [{'path': 'executions/1/http_capture.jsonl', 'size': 23}]}
        elif path.endswith('/stream') or path == '/runs-stream':
            await route.fulfill(status=200, content_type='text/event-stream', body=': 合成只读连接\n\n')
            return
        else:
            value = {'agents': [], 'pi_available': False}
        await route.fulfill(status=200, content_type='application/json', body=json.dumps(value, ensure_ascii=False))

    async with async_playwright() as browser_api:
        browser = await browser_api.chromium.launch(executable_path='/root/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome',
            headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1280, 'height': 900})
        page.on('pageerror', lambda error: errors.append(str(error)))

        async def handle_dialog(dialog):
            """保存错误弹窗供断言，自动关闭以免验证挂起。:param dialog: 浏览器弹窗。:return: None。"""
            dialogs.append(dialog.message)
            await dialog.dismiss()

        page.on('dialog', handle_dialog)
        await page.route('**/api/**', respond)
        await page.route('https://**', lambda route: route.abort())
        base = f'http://127.0.0.1:{server.server_port}/index.html'
        try:
            await page.goto(base + '#projects')
            await page.locator('#projects-account option[value="1"]').wait_for(state='attached')
            await page.select_option('#projects-account', '1')
            await page.click('#projects-cli-settings')
            await page.wait_for_function("!document.querySelector('#cli-settings-form [type=submit]').disabled")
            assert not await page.locator('#cli-settings-form [name=capture_enabled]').is_checked()
            await page.fill('#cli-settings-form [name=claude_code_version]', '2.1.303')
            await page.check('#cli-settings-form [name=capture_enabled]')
            await page.click('#cli-settings-form [type=submit]')
            await page.wait_for_function("document.querySelector('#cli-settings-feedback').textContent.includes('已保存')")
            assert settings[1]['projects_capture_enabled'] and not settings[1]['warmup_capture_enabled']
            await page.click('#cli-settings-modal [data-close]')
            await page.evaluate("location.hash = '#warmup'")
            await page.locator('#projects-overview[data-namespace=warmup]').wait_for()
            await page.locator('#projects-account option[value="1"]').wait_for(state='attached')
            await page.select_option('#projects-account', '1')
            await page.click('#projects-cli-settings')
            await page.wait_for_function("!document.querySelector('#cli-settings-form [type=submit]').disabled")
            assert await page.input_value('#cli-settings-form [name=claude_code_version]') == '2.1.303'
            assert not await page.locator('#cli-settings-form [name=capture_enabled]').is_checked()
            for theme in ('dark', 'light'):
                await page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                await page.wait_for_timeout(250)
                themes[theme] = await page.locator('#cli-settings-modal .modal-card').evaluate('(node) => getComputedStyle(node).backgroundColor')
                await page.screenshot(path=str(Path(__file__).with_name(f'settings-{theme}.png')))
            assert themes['dark'] != themes['light']
            await page.click('#cli-settings-modal [data-close]')
            delay['get'] = True
            await page.click('#projects-cli-settings')
            await page.wait_for_function("document.querySelector('#cli-settings-feedback').textContent.includes('正在读取')")
            await page.click('#cli-settings-modal [data-close]')
            await page.select_option('#projects-account', '2')
            await page.click('#projects-cli-settings')
            await page.wait_for_function("!document.querySelector('#cli-settings-form [type=submit]').disabled")
            release.set()
            await page.wait_for_timeout(150)
            assert '账号 #2' in await page.locator('#cli-settings-title').inner_text()
            assert await page.input_value('#cli-settings-form [name=claude_code_version]') == ''
            await page.click('#cli-settings-modal [data-close]')
            delay['get'] = False
            release.clear()
            await page.select_option('#projects-account', '1')
            await page.click('#projects-cli-settings')
            await page.wait_for_function("!document.querySelector('#cli-settings-form [type=submit]').disabled")
            await page.check('#cli-settings-form [name=capture_enabled]')
            delay['put'] = True
            await page.click('#cli-settings-form [type=submit]')
            await page.wait_for_function("document.querySelector('#cli-settings-form [type=submit]').disabled")
            await page.click('#cli-settings-modal [data-close]')
            await page.select_option('#projects-account', '2')
            await page.click('#projects-cli-settings')
            await page.wait_for_function("!document.querySelector('#cli-settings-form [type=submit]').disabled")
            release.set()
            await page.wait_for_timeout(150)
            assert '账号 #2' in await page.locator('#cli-settings-title').inner_text()
            assert await page.input_value('#cli-settings-form [name=claude_code_version]') == ''
            assert settings[1]['projects_capture_enabled'] and settings[1]['warmup_capture_enabled']
            await page.set_viewport_size({'width': 720, 'height': 900})
            bounds = await page.locator('#cli-settings-modal .modal-card').bounding_box()
            assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 720
            await page.click('#cli-settings-modal [data-close]')
            await page.locator('[data-work-capture]').first.click()
            await page.wait_for_function("document.querySelector('#work-capture-content').textContent.includes('已有部分数据')")
            assert await page.locator('#work-capture-content img').count() == 0
            await page.keyboard.press('Escape')
            assert await page.locator('#work-capture-modal').evaluate("node => node.classList.contains('hidden')")
            assert not errors, errors
            assert not any(method == 'POST' for method, path in requests)
            await page.evaluate("location.hash = '#runs'")
            await page.locator('#capture-form [name=account_id] option[value="1"]').wait_for(state='attached')
            assert await page.locator('#capture-form [name=claude_code_version]').count() == 1, '单次版本输入必须属于抓包表单'
            assert await page.evaluate("document.querySelector('#tpl-tasks').content.querySelectorAll('#batch-form [name=claude_code_version]').length") == 0
            submitted_versions = []
            for explicit, configured, effective in [('2.1.293', '2.1.303', '2.1.293'), ('', '2.1.303', '2.1.303'), ('', None, '2.1.293')]:
                settings[1]['claude_code_version'] = configured
                saved_settings = json.dumps(settings, sort_keys=True)
                saved_global = dict(global_version)
                writes = [(method, path) for method, path in requests if method == 'PUT']
                await page.fill('#capture-form [name=claude_code_version]', explicit)
                await page.fill('#capture-form [name=prompt]', '合成抓包输入')
                await page.fill('#capture-form [name=model_override]', 'synthetic-model')
                await page.select_option('#capture-form [name=effort_level]', 'low')
                await page.select_option('#capture-form [name=permission_mode]', 'auto')
                async with page.expect_response(lambda response: response.url.endswith('/api/captures/run') and response.request.method == 'POST'):
                    await page.click('#capture-form [type=submit]')
                await page.wait_for_function("document.querySelector('#run-detail-capture') && document.querySelector('#run-detail-capture').textContent.includes('尚未采到目标流量')")
                assert captures[-1]['payload']['claude_code_version'] == (explicit or None)
                assert await page.locator('#run-detail-capture').inner_text() and effective in await page.locator('#run-detail-capture').inner_text()
                for field in ['claude_code_version', 'prompt', 'model_override', 'effort_level']:
                    assert await page.input_value(f'#capture-form [name={field}]') == ''
                assert await page.input_value('#capture-form [name=permission_mode]') == 'bypassPermissions'
                assert await page.locator('#capture-form [type=submit]').is_enabled()
                assert saved_settings == json.dumps(settings, sort_keys=True)
                assert saved_global == global_version
                assert writes == [(method, path) for method, path in requests if method == 'PUT']
                assert not dialogs, dialogs
                submitted_versions.append({'explicit': explicit or None, 'account': configured, 'effective': effective})
                await page.click('#modal-close')
            assert not errors, errors
            return {'result': 'passed', 'api_mode': '合成回执；后端契约另由 SQLite/API 测试验证',
                'account_and_namespace_isolation': True, 'old_get_response_ignored': True,
                'old_put_response_ignored': True, 'two_capture_switches_saved_independently': True,
                'history_capture_and_escape': True, 'escaped_index': True, 'themes': themes,
                'viewport_720_fits': True, 'page_errors': errors, 'model_start_requests': 0,
                'capture_form_submission': submitted_versions, 'capture_form_reset_and_details': True,
                'capture_submit_preserves_settings': True, 'capture_error_dialogs': dialogs,
                'synthetic_capture_posts': len(captures)}
        finally:
            release.set()
            await browser.close()
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    result = asyncio.run(verify())
    Path(__file__).with_name('browser-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
