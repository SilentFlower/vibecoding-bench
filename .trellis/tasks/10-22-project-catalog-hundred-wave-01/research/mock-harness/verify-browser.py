"""只读检查本地模拟试跑的真实页面；模拟用量不代表真实模型成本。"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import traceback
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path.cwd()
BUNDLE = Path(os.environ['HUNDRED_MOCK_BUNDLE']).resolve()
OUTPUT = BUNDLE / 'browser'
BROWSER_ROOT = OUTPUT
DIAGNOSTICS = OUTPUT / 'diagnostics'
KINDS = {'understand': '理解', 'consult': '咨询', 'diagnose': '诊断', 'plan': '方案', 'modify': '修改'}
CHINESE = re.compile(r'[\u4e00-\u9fff]')
PROJECT_KEYS = tuple(json.loads((BUNDLE / 'fixtures/catalog-identity.json').read_text())['project_keys'])
FIXTURES = BUNDLE / 'fixtures'


def write_json(path, value):
    """保存无身份秘密的本地核验结果。

    :param path: 输出文件。
    :param value: 可序列化的核验结果。
    :return: 无。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def api(context, base, path):
    """访问指定本地服务的只读 JSON 接口。

    :param context: 带本地服务鉴权的浏览器上下文。
    :param base: 已校验的回环服务地址。
    :param path: API 资源路径。
    :return: HTTP 200 的 JSON 内容。
    """
    response = context.request.get(base + '/api' + path, timeout=30000)
    assert response.status == 200, f'只读接口异常：{path}，HTTP {response.status}'
    return response.json()


def check(result, condition, text):
    """累计业务核验，保留失败项以便仍能截取实际页面。

    :param result: 不含身份秘密的核验结果。
    :param condition: 实际核验条件。
    :param text: 中文核验说明。
    :return: 实际条件的布尔值。
    """
    result['checks'].append({'passed': bool(condition), 'description': text})
    return bool(condition)


def screenshot(page, selector, name, result):
    """保存真实 DOM 的截图，不向页面插入模拟数据或标识。

    :param page: 当前浏览器页面。
    :param selector: 截取的真实组件。
    :param name: 明确标记 mock 的文件名。
    :param result: 接收截图清单的核验结果。
    :return: 无。
    """
    target = page.locator(selector)
    target.scroll_into_view_if_needed()
    path = OUTPUT / name
    target.screenshot(path=str(path), style='.topbar, .hintbar { visibility: hidden !important; }')
    result['screenshots'].append(str(path.relative_to(ROOT)))


def close_modal(page):
    """通过真实页面按钮关闭模态框。

    :param page: 当前浏览器页面。
    :return: 无。
    """
    page.locator('#modal-close').click()
    expect(page.locator('#modal')).to_be_hidden()


def assert_public(value):
    """确认公开目录不包含候选不应获得的评审内容。

    :param value: 公开目录内容。
    :return: 无；字段泄漏时抛出断言。
    """
    if isinstance(value, dict):
        assert not ({'prompt', 'rubric', 'evaluation', 'verification'} & set(value))
        for child in value.values():
            assert_public(child)
    elif isinstance(value, list):
        for child in value:
            assert_public(child)


def verify_usage_coverage(task_key, role, value, executions, result):
    """按实际来源边界核对完整性，保留中断前缺失用量的未知状态。

    :param task_key: 正式任务标识。
    :param role: 候选或评审角色。
    :param value: API 返回的已有来源汇总。
    :param executions: 当前角色的实际执行记录。
    :param result: 接收覆盖证据与核验结果的对象。
    :return: 无。
    """
    fields = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')
    interrupted = [entry['execution_status'] for entry in executions if entry['execution_status'] != 'success']
    sources, known_sources, requests = value['sources'], value['known_sources'], value['requests']
    known_fields = value['known_fields']
    result['usage_coverage'].append({'task_key': task_key, 'role': role,
        'sources': sources, 'known_sources': known_sources, 'unknown_sources': sources - known_sources,
        'requests': requests, 'known_fields': known_fields, 'complete': value['complete'],
        'interrupted_execution_statuses': interrupted,
        'interpretation': '部分已知小计，缺失来源未补零' if interrupted and not value['complete'] else
            '已有响应完整' if value['complete'] else '尚无已知响应'})
    check(result, type(sources) is int and type(known_sources) is int and 0 <= known_sources <= sources,
        f'{task_key} 的 {role} 已知来源数量不超过实际来源数量')
    responses_known = type(requests) is int and requests > 0
    field_counts_valid = all(type(known_fields[field]) is int and 0 <= known_fields[field] <= (requests or 0)
        for field in fields)
    unknowns_preserved = all((value[field] is None if known_fields[field] == 0 else
        type(value[field]) is int and value[field] >= 0) for field in fields)
    expected_complete = bool(sources) and known_sources == sources and responses_known and all(
        known_fields[field] == requests for field in fields)
    check(result, field_counts_valid and unknowns_preserved and value['complete'] == expected_complete,
        f'{task_key} 的 {role} 完整性与来源／字段覆盖一致，未知字段保持 null')
    if executions:
        check(result, responses_known and sources >= len(executions),
            f'{task_key} 的 {role} 已知响应小计及实际执行来源均有记录')
        if interrupted:
            # 真超时可能只落盘 user 消息；恢复后的已知响应不能补成整段完整统计。
            check(result, False, f'{task_key} 的 {role} 出现本批未计划的中断：{interrupted}')
            if not value['complete']:
                check(result, known_sources < sources or any(known_fields[field] < requests for field in fields),
                    f'{task_key} 的 {role} 部分小计明确保留缺失来源或字段覆盖')
        else:
            check(result, value['complete'], f'{task_key} 的 {role} 无中断响应覆盖完整')
    else:
        check(result, sources == 0 and requests is None and all(value[field] is None for field in fields)
            and not value['complete'], f'{task_key} 的 {role} 未执行时保持未知用量')


def verify_usage(page, instance, usage, result):
    """核对页面按任务分列的候选与评审用量来自实际 API。

    :param page: 当前浏览器页面。
    :param instance: 当前实例公开详情。
    :param usage: 当前实例真实用量接口内容，数值来自模拟原生日志。
    :param result: 接收角色和截图证据的核验结果。
    :return: 无。
    """
    usage_path = f"/api/project-instances/{instance['id']}/usage"
    # 相同任务数量的项目会留下同标题、同行数的隐藏旧表，必须等待本实例响应和重新显示。
    with page.expect_response(lambda response: urlsplit(response.url).path == usage_path
            and response.request.method == 'GET') as pending:
        page.locator('#project-instance-detail [data-scenario-usage]').click()
    response = pending.value
    assert response.status == 200 and response.json()['instance_id'] == instance['id']
    expect(page.locator('#modal')).to_be_visible()
    expect(page.locator('#modal-content > h3')).to_have_text('任务与评审用量')
    expected = []
    task_lookup = {task['task_key']: task for scene in instance['scenarios'] for task in scene['tasks']}
    for task in usage['tasks']:
        for role, value in task['roles'].items():
            display = lambda key: str(value[key]) if value.get(key) is not None else '未知'
            expected.append([task['task_key'] + ' · ' + ('评审' if role == 'review' else '任务'),
                display('input_tokens'), display('output_tokens'),
                display('cache_read_input_tokens') + ' / ' + display('cache_creation_input_tokens'),
                display('requests'), '完整' if value['complete'] else '不完整'])
            executed = [entry for entry in task_lookup[task['task_key']]['executions'] if entry['role'] == role]
            verify_usage_coverage(task['task_key'], role, value, executed, result)
            result['usage'].append({'project_key': instance['project_key'], 'task_key': task['task_key'],
                'role': role, 'mock': True, **value})
    rows = page.locator('#modal-content table tbody tr')
    expect(rows).to_have_count(len(expected))
    actual = [rows.nth(index).locator('td').all_text_contents() for index in range(len(expected))]
    check(result, actual == expected, f"{instance['project_key']} 的页面候选／评审分列用量逐格匹配 API")
    page.set_viewport_size({'width': 1280, 'height': 1000})
    page.evaluate('document.documentElement.dataset.theme = "dark"')
    screenshot(page, '#modal .modal-card', f"mock-usage-{instance['id']}-{instance['project_key']}-1280-dark.png", result)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.evaluate('document.documentElement.dataset.theme = "light"')
    screenshot(page, '#modal .modal-card', f"mock-usage-{instance['id']}-{instance['project_key']}-390-light.png", result)
    close_modal(page)


def prompt_snapshot(page, run_id):
    """只读记录实际Run收口与首问可见性。@param page 真实页面。@param run_id 精确Run。@return 无秘密状态及正文SHA。"""
    detail = page.locator('#run-detail-followups details').first
    prompt = detail.locator('pre')
    text = prompt.text_content() or ''
    state = page.evaluate('() => ({rid:state.runDetail?.rid, seq:state.runDetail?.seq, '
        'timer_is_null:state.runDetail?.timer === null, final_files_pending:state.runDetail?.finalFilesPending, '
        'file_count:Array.isArray(state.runDetail?.files) ? state.runDetail.files.length : null, '
        'displayed_file_count:document.querySelector("#run-detail-file-count")?.textContent})')
    return {**state, 'rid_matches':state['rid'] == run_id, 'details_open':detail.evaluate('(node) => node.open'),
        'pre_visible':prompt.is_visible(), 'prompt_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'prompt_characters':len(text)}


def verify_visible_prompt(page, run, target, result):
    """等待真实最终文件补刷后展开，并在截图两侧核全文可见。@param page 页面。@param run 真实API记录。@param target 精确实例。@param result 证据对象。@return None。"""
    run_id = run['id']
    assert run['status'] == 'success'
    # 完成Run仍有一次最终文件补刷；只等待页面自身状态，不写DOM或改运行计划。
    page.wait_for_function('(rid) => state.runDetail && state.runDetail.rid === rid '
        '&& state.runDetail.rendered && state.runDetail.seq >= 2 && state.runDetail.timer === null '
        '&& state.runDetail.finalFilesPending === false && Array.isArray(state.runDetail.files)', arg=run_id)
    detail = page.locator('#run-detail-followups details').first
    expect(detail.locator('summary')).to_have_text('初始需求')
    if not detail.evaluate('(node) => node.open'):
        detail.locator('summary').click()
    prompt = detail.locator('pre')
    expect(prompt).to_be_visible()
    expect(prompt).to_have_text(run['prompt'])
    assert prompt.text_content() == run['prompt']
    expected_sha = hashlib.sha256(run['prompt'].encode()).hexdigest()
    before = prompt_snapshot(page, run_id)
    record = {'run_id':run_id,**target,'api_prompt_sha256':expected_sha,
        'before_screenshot':before,'private_rubric_exposed':False,'read_only_replay':False,'live_run_verification':True}
    result['english_first_prompt'] = record
    valid_before = (before['rid_matches'] and before['details_open'] and before['pre_visible']
        and before['prompt_sha256'] == expected_sha and before['timer_is_null']
        and before['final_files_pending'] is False and str(before['file_count']) == before['displayed_file_count'])
    check(result, valid_before, '英文首问截图前：真实Run最终文件已收口，details展开、pre可见、全文SHA匹配')
    assert valid_before
    name = f'mock-live-english-first-prompt-instance-{target["instance_id"]}-run-{run_id}-1280-dark.png'
    path = OUTPUT / name
    prompt.scroll_into_view_if_needed()
    page.locator('#modal .modal-card').screenshot(path=str(path), animations='disabled')
    result['screenshots'].append(str(path.relative_to(ROOT)))
    record['screenshot'] = str(path.relative_to(ROOT))
    after = prompt_snapshot(page, run_id)
    record['after_screenshot'] = after
    valid_after = (after['rid_matches'] and after['details_open'] and after['pre_visible']
        and after['prompt_sha256'] == expected_sha and after['seq'] == before['seq']
        and after['timer_is_null'] and after['final_files_pending'] is False)
    check(result, valid_after, '英文首问截图后：同一Run与补刷序号、details仍展开、pre仍可见、全文SHA仍匹配')
    # 如果真实应用再次折叠，保留刚拍到的原现场及失败事实，不替换图或伪造DOM。
    assert valid_after


def main():
    """核验模拟批次；可选在失败后保留 runner 原等待窗口供只读排查。

    :return: 成功返回 0，任一核验失败返回 1。
    """
    global OUTPUT, DIAGNOSTICS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='本browser目录内的独立证据子目录；默认取连接文件父目录名')
    parser.add_argument('--connection-file', required=True, type=Path)
    parser.add_argument('--defer-done', action='store_true',
        help='即使通过也不写browser-done，只留pending结果，等待root核审计快照后明确释放')
    parser.add_argument('--hold-on-failure', action='store_true', default=True,
        help='核验失败时仅保存诊断，保留 runner 现有等待窗口供只读排查')
    args = parser.parse_args()
    OUTPUT = (args.output_dir or BROWSER_ROOT / args.connection_file.parent.name).resolve()
    if not OUTPUT.is_relative_to(BROWSER_ROOT.resolve()) or OUTPUT == BROWSER_ROOT.resolve():
        raise ValueError('浏览器证据必须写入本browser目录内的独立子目录')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS = OUTPUT / 'diagnostics'
    if (DIAGNOSTICS / 'result.json').exists():
        raise ValueError('此浏览器证据目录已有结果，拒绝覆盖；请选新的output-dir')
    configuration = None
    result = {'status': 'running', 'simulation': True,
        'gate_hold_requested': args.hold_on_failure, 'done_deferred': args.defer_done,
        'read_only_replay': False, 'live_run_verification': True,
        'notice': '本地真实调度器与页面的模拟试跑；回答、评审和用量来自 mock CLI，不能据此判断真实模型质量或成本。',
        'business_write_requests': 0, 'production_model_requests': 0,
        'checks': [], 'screenshots': [], 'instances': [], 'tasks': [], 'runs': [], 'usage': [], 'usage_coverage': [],
        'blocked_external_requests': [], 'blocked_write_requests': [], 'external_requests_finished': [], 'page_errors': [], 'dialogs': []}
    browser = None
    try:
        configuration = json.loads(args.connection_file.read_text())
        base = configuration['base_url'].rstrip('/')
        parsed = urlsplit(base)
        assert parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
        assert not parsed.username and not parsed.password and parsed.path in ('', '/')
        assert Path(configuration['browser_ready_file']).is_file(), 'runner 尚未完成全部模拟任务'
        secret = Path(configuration['service_token_file']).read_text().strip()
        assert len(secret) >= 32
        batch_ids = configuration['batch_ids']
        stages = json.loads((FIXTURES / 'stages.json').read_text())
        identity = json.loads((FIXTURES / 'catalog-identity.json').read_text())
        assert len(batch_ids) == len(stages) == 3
        expected_counts = configuration['expected_selected_task_counts']
        assert expected_counts == [stage['count'] for stage in stages]
        result['expected_stage_counts'] = expected_counts
        result['expected_catalog_digest'] = identity['digest']
        result['batch_ids'] = batch_ids
        expected_kinds = {task['kind'] for key in PROJECT_KEYS
            for scene in json.loads((BUNDLE / 'library/projects' / key / 'project.json').read_text())['scenarios']
            for task in scene['tasks']}
        assert expected_kinds and expected_kinds <= set(KINDS)
        result['expected_task_kinds'] = sorted(expected_kinds)
        with sync_playwright() as engine:
            browser = engine.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = browser.new_context(viewport={'width': 1280, 'height': 1000}, reduced_motion='reduce',
                extra_http_headers={'Authorization': 'Bearer ' + secret}, service_workers='block')

            def enforce_read_only(route):
                """隔离真实页面的所有写请求与外网请求。@param route 请求路由。@return 无。"""
                request = route.request
                request_url = urlsplit(request.url)
                if request_url.scheme in ('http', 'https') and request_url.netloc != parsed.netloc:
                    # 字体和终端 CDN 不是本轮项目页所需；禁止外发服务令牌。
                    result['blocked_external_requests'].append({'host': request_url.hostname, 'path': request_url.path})
                    route.abort('blockedbyclient')
                elif request.method not in ('GET', 'HEAD'):
                    result['blocked_write_requests'].append({'method': request.method, 'path': request_url.path})
                    route.abort('blockedbyclient')
                else:
                    route.continue_()

            context.route('**/*', enforce_read_only)
            context.on('requestfinished', lambda request: result['external_requests_finished'].append(
                {'host':urlsplit(request.url).hostname,'path':urlsplit(request.url).path})
                if urlsplit(request.url).scheme in ('http','https') and urlsplit(request.url).netloc != parsed.netloc else None)
            page = context.new_page()
            page.set_default_timeout(20000)
            page.on('pageerror', lambda error: result['page_errors'].append(type(error).__name__))
            page.on('dialog', lambda dialog: (result['dialogs'].append(dialog.type), dialog.dismiss()))
            catalog = api(context, base, '/project-catalog')
            assert_public(catalog)
            check(result, catalog['version'] == identity['version'] and catalog['digest'] == identity['digest'], '实际目录使用本批冻结版本与摘要')
            page.goto(base + '/#projects', wait_until='domcontentloaded', timeout=60000)
            expect(page.locator('#project-library-count')).to_have_text(f"{identity['projects']} 个项目 · {identity['scenarios']} 个场景 · {identity['tasks']} 个任务")
            catalog_panel = page.locator('details.project-panel').filter(has=page.locator('#project-catalog-list'))
            if not catalog_panel.evaluate('(node) => node.open'):
                catalog_panel.locator(':scope > summary').click()
            for key in PROJECT_KEYS:
                public = api(context, base, '/project-catalog/' + key)
                assert_public(public)
                page.locator(f'[data-project-preview="{key}"]').click()
                expect(page.locator('#modal')).to_be_visible()
                expected = [task['goal'] for scene in public['scenarios'] for task in scene['tasks']]
                for goal in expected:
                    check(result, goal in page.locator('#modal-content').inner_text() and bool(CHINESE.search(goal)),
                        key + ' 浏览路线的真实任务目标为中文')
                for width, height, theme in ((1280, 1000, 'dark'), (390, 844, 'light')):
                    page.set_viewport_size({'width': width, 'height': height})
                    page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                    screenshot(page, '#modal .modal-card', f'mock-route-{key}-{width}-{theme}.png', result)
                close_modal(page)
            english_run = None
            english_target = None
            all_kinds = set()
            for batch_id, expected_count, stage in zip(batch_ids, expected_counts, stages):
                batch = api(context, base, f'/project-iteration-batches/{batch_id}')
                check(result, '模拟' in batch['name'], f'批次 {batch_id} 的来源明确标记模拟')
                check(result, batch['status'] == 'completed', f'批次 {batch_id} 的真实调度器已运行结束')
                button = page.locator(f'[data-project-batch="{batch_id}"]')
                expect(button).to_be_visible()
                if button.is_enabled():
                    button.click()
                expect(page.locator('#project-batch-detail > header h3')).to_have_text(batch['name'])
                count = 0
                stage_task_keys = []
                metadata_rows = 0
                for item in batch['instances']:
                    instance = api(context, base, f"/project-instances/{item['id']}")
                    tasks = [task for scene in instance['scenarios'] for task in scene['tasks'] if task['selected']]
                    count += len(tasks)
                    stage_task_keys.extend(task['task_key'] for task in tasks)
                    metadata_rows += sum(len(scene['tasks']) for scene in instance['scenarios'])
                    check(result, all(task['status'] == 'passed' for task in tasks),
                        f"{instance['project_key']} 的 {len(tasks)} 项所选模拟任务全部通过")
                    with page.expect_response(lambda response: urlsplit(response.url).path ==
                            '/api/project-instances/' + str(item['id']) and response.request.method == 'GET') as loaded:
                        page.locator(f"[data-project-instance=\"{item['id']}\"]").click()
                    assert loaded.value.status == 200 and loaded.value.json()['id'] == item['id']
                    host = page.locator('#project-instance-detail')
                    expect(host.locator(f"details[data-scenario-id=\"{instance['scenarios'][0]['id']}\"]")).to_be_visible()
                    expect(host.locator(':scope > header h3')).to_have_text(instance['title'])
                    for scene in instance['scenarios']:
                        detail = host.locator(f"details[data-scenario-id=\"{scene['id']}\"]")
                        if not detail.evaluate('(node) => node.open'):
                            detail.locator(':scope > summary').click()
                        for task in scene['tasks']:
                            if not task['selected']:
                                continue
                            all_kinds.add(task['kind'])
                            article = host.locator('article.project-scenario-task').filter(has_text=task['task_key'] + ' ·')
                            expect(article.locator(':scope > header strong')).to_have_text(task['task_key'] + ' · ' + KINDS[task['kind']])
                            expect(article.locator(':scope > p').first).to_have_text(task['goal'])
                            check(result, bool(CHINESE.search(task['goal'])), f"{task['task_key']} 的任务目标保持中文")
                            expect(article.locator(':scope > header span.pill')).to_have_text('任务通过')
                            budget_text = (f"业务尝试 {task['attempt_count']}/3 · 第 {task['turn_no']} 轮 · 工作剩余 "
                                f"{max(0, math.floor(task['candidate_budget']['remaining_sec']))} 秒 · 评审剩余 "
                                f"{max(0, math.floor(task['review_budget']['remaining_sec']))} 秒")
                            check(result, budget_text in article.inner_text(), f"{task['task_key']} 的页面业务尝试与候选／评审预算匹配API")
                            outcome = (task.get('result') or {}).get('outcome')
                            if outcome:
                                check(result, '业务结果：' + outcome in article.inner_text(), f"{task['task_key']} 页面展示真实合法业务结果")
                            checkpoint = task['accepted_checkpoint_digest']
                            checkpoint_text = '代码已接受：' + checkpoint[:16] if checkpoint else '代码未产生新的已接受检查点'
                            check(result, checkpoint_text in article.inner_text() and bool(checkpoint) == (task['kind']=='modify'),
                                f"{task['task_key']} 页面代码检查点与任务类型及API一致")
                            for execution in task['executions']:
                                actual_run = api(context, base, '/runs/' + execution['run_id'])
                                run_kind = 'project_iteration' if execution['role']=='candidate' else 'project_review'
                                check(result, actual_run['id'] == execution['run_id'] and actual_run['status'] == execution['execution_status']
                                    and actual_run['run_kind'] == run_kind, f"{task['task_key']} 的 {execution['role']} Run身份、状态与类型匹配API")
                                expect(article.locator(f'[data-project-run="{execution["run_id"]}"]')).to_be_visible()
                                result['runs'].append({'instance_id':item['id'],'task_key':task['task_key'],'role':execution['role'],
                                    'run_id':actual_run['id'],'status':actual_run['status'],'run_kind':actual_run['run_kind']})

                            history = api(context, base,
                                f"/project-instances/{item['id']}/scenario-tasks/{task['id']}/attempts")
                            record = {'project_key': instance['project_key'], 'task_key': task['task_key'],
                                'kind': task['kind'], 'status': task['status'], 'attempt_count': task['attempt_count'],
                                'executions': task['executions'], 'attempts': history['attempts']}
                            result['tasks'].append(record)
                            if task['task_key'] == identity['prompt_task'] and english_run is None:
                                english_run = next(entry['run_id'] for entry in task['executions'] if entry['role'] == 'candidate')
                                english_target = {'batch_id':batch_id, 'instance_id':item['id'], 'scene_id':scene['id'],
                                    'task_key': task['task_key']}
                    usage = api(context, base, f"/project-instances/{item['id']}/usage")
                    verify_usage(page, instance, usage, result)
                    for width, height, theme in ((1280, 1000, 'dark'), (390, 844, 'light')):
                        page.set_viewport_size({'width': width, 'height': height})
                        page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                        check(result, page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),
                            f"{instance['project_key']} 在 {width}px 页面无横向溢出")
                        screenshot(page, '#project-instance-detail', f"mock-instance-{item['id']}-batch-{batch_id}-{instance['project_key']}-{width}-{theme}.png", result)
                    result['instances'].append({'instance_id': item['id'], 'project_key': instance['project_key'], 'selected_tasks': len(tasks)})
                check(result, sorted(stage_task_keys) == sorted(stage['selected_task_keys']) and metadata_rows == stage['complete_metadata_rows'],
                    f'批次 {batch_id} 所选task集合及完整metadata行数匹配冻结stage')
                check(result, count == expected_count, f'批次 {batch_id} 实际选择 {expected_count} 项任务')
                page.set_viewport_size({'width': 1280, 'height': 1000})
                page.evaluate('document.documentElement.dataset.theme = "dark"')
                screenshot(page, '#project-batch-panel', f'mock-batch-{batch_id}-1280.png', result)

            check(result, len(result['tasks']) == sum(expected_counts) and len({task['task_key'] for task in result['tasks']}) == identity['tasks'],
                '默认与入口分支覆盖本批全部唯一任务，额外路径执行单独计数')
            check(result, all_kinds == expected_kinds, '真实页面与 API 覆盖冻结内容包中的全部实际任务类型')
            check(result, all(task['attempt_count'] == 1 for task in result['tasks']),
                '所有任务及正常披露均保持一次业务尝试')
            assert english_run and english_target, '未找到本批首问候选Run'
            run = api(context, base, '/runs/' + english_run)
            manifest = json.loads((BUNDLE / 'library/projects' / identity['prompt_project'] / 'project.json').read_text())
            definition = next(task for scene in manifest['scenarios'] for task in scene['tasks'] if task['id'] == identity['prompt_task'])
            rubric = json.loads((BUNDLE / 'library/projects' / identity['prompt_project'] / definition['evaluation']['rubric']).read_text())
            expected_prompt = definition['prompt']
            check(result, expected_prompt in (run['prompt'] or '') and not CHINESE.search(expected_prompt), '实际候选首问包含本批冻结英文任务提示词')
            private_requirements = [criterion['requirement'] for criterion in rubric['criteria']]
            check(result, not any(requirement in run['prompt'] for requirement in private_requirements), '候选首问没有泄漏私有评分标准')
            page.set_viewport_size({'width':1280,'height':1000})
            page.evaluate('document.documentElement.dataset.theme = "dark"')
            batch_button = page.locator(f'[data-project-batch="{english_target["batch_id"]}"]')
            if batch_button.is_enabled():
                batch_button.click()
            with page.expect_response(lambda response: urlsplit(response.url).path ==
                    '/api/project-instances/' + str(english_target['instance_id']) and response.request.method == 'GET') as loaded:
                page.locator(f'[data-project-instance="{english_target["instance_id"]}"]').click()
            assert loaded.value.status == 200 and loaded.value.json()['id'] == english_target['instance_id']
            scene = page.locator(f'#project-instance-detail details[data-scenario-id="{english_target["scene_id"]}"]')
            expect(scene).to_be_visible()
            if not scene.evaluate('(node) => node.open'):
                scene.locator(':scope > summary').click()
            scene.locator(f'[data-project-run="{english_run}"]').click()
            verify_visible_prompt(page, run, english_target, result)
            close_modal(page)
            check(result, not result['page_errors'] and not result['dialogs'], '真实页面没有脚本异常或意外弹窗')
            check(result, not result['blocked_write_requests'], '浏览器没有发起业务写请求')
            check(result, not result['external_requests_finished'], '外网请求全部在发送前拦截，没有携带本地令牌完成外发')
            browser.close()
            browser = None
        result['status'] = 'passed' if all(entry['passed'] for entry in result['checks']) else 'failed'
    except Exception as error:
        result['status'] = 'failed'
        # 不输出异常参数或浏览器调用日志，避免身份头进入证据。
        result['exception_type'] = type(error).__name__
        result['traceback_locations'] = [{'file': frame.filename, 'line': frame.lineno, 'function': frame.name}
            for frame in traceback.extract_tb(error.__traceback__)]
    finally:
        if browser:
            try:
                browser.close()
            except Exception as cleanup_error:
                # 上下文已退出时关闭可能失败，不能覆盖原始核验诊断或阻止保存证据。
                result['browser_cleanup_error_type'] = type(cleanup_error).__name__
        result['business_write_requests'] = len(result['blocked_write_requests'])
        write_json(DIAGNOSTICS / 'result.json', result)
        # 保留原有有限等待窗口，不把选择器或截图异常伪装成通过。
        if configuration and not args.defer_done and not (args.hold_on_failure and result['status'] == 'failed'):
            write_json(Path(configuration['browser_done_file']), {'status': result['status'],
                'result_file': str(DIAGNOSTICS / 'result.json'), 'simulation': True})
        if configuration and args.defer_done:
            write_json(DIAGNOSTICS / 'gate-pending.json', {'status':result['status'], 'browser_done_written':False,
                'requires':'root确认独立机制审计快照完成后释放；本脚本未释放gate', 'simulation':True})
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']),
        'failed_checks': sum(not entry['passed'] for entry in result['checks']),
        'screenshots': len(result['screenshots']), 'result_file': str(DIAGNOSTICS / 'result.json')}, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
