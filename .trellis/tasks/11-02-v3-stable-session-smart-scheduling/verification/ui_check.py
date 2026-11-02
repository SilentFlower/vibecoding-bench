"""使用本地预览和合成管理响应验证界面；不连接真实网关或模型。"""
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:4177'


def main():
    """验证可视化、只读刷新和字符串设置保存，输出可复核结果。"""
    calls = Counter()
    state = {'fail': False, 'saved': None, 'reason': 'pacing'}
    errors = []
    blocked = []
    keys = [hashlib.sha256(f'fixture-{i}'.encode()).hexdigest() for i in range(21)]
    settings = {'score_weight_7d': '0.5', 'score_weight_5h': '0.3', 'score_weight_concurrency': '0.2'}

    def phases(index=2):
        """构造一个会话可包含多个请求的合成阶段计数。"""
        return {'waiting_concurrency': 0, 'preparing': 0, 'waiting_send': int(index == 0), 'running': int(index < 2), 'backoff': 0}

    def summary():
        """返回与后端 DTO 一致的容量和会话摘要。"""
        now = int(time.time() * 1000)
        return {'config': {'mode': 'smart', 'wait_seconds': 120, 'weights': [1, .8, 1, .5]}, 'factors': {'load': .5, 'quota': .6, 'health': .5, 'latency': .5, 'score': .53}, 'capacity': {'immediate': False, 'can_queue': state['reason'] != 'wait_budget', 'reason': state['reason'], 'earliest_submit_at_ms': now + 2000}, 'observed_at_ms': now, 'bound_sessions': 21, 'active_sessions': 2, 'unbound_requests': 0, 'phases': {'waiting_concurrency': 0, 'preparing': 0, 'waiting_send': 1, 'running': 2, 'backoff': 0}, 'next_send_at_ms': now + 800, 'submissions_last_60s': 32, 'history_available_from_ms': now - 300000, 'history_truncated': False}

    def dispatch(route):
        """拦截所有管理与外部请求；只允许本地静态资源直通。"""
        parsed = urlparse(route.request.url)
        path = parsed.path
        if parsed.hostname == 'fonts.googleapis.com' and route.request.resource_type == 'stylesheet':
            return route.fulfill(content_type='text/css', body='')
        if parsed.netloc != '127.0.0.1:4177':
            blocked.append(route.request.url)
            return route.abort()
        if not path.startswith('/admin/'):
            if path.startswith(('/v1/', '/api/')):
                blocked.append(path)
                return route.abort()
            return route.continue_()
        calls[path] += 1
        value = None
        status = 200
        now = int(time.time() * 1000)
        if path == '/admin/dashboard':
            value = {'accounts': {'total': 1, 'active': 1, 'error': 0, 'disabled': 0}, 'tokens': 1}
        elif path == '/admin/accounts':
            account = {'id': 1, 'name': '合成验收账号', 'email': 'fixture@example.invalid', 'status': 'active', 'auth_type': 'setup_token', 'setup_token': 'synthetic', 'access_token': '', 'refresh_token': '', 'proxy_url': '', 'device_id': '', 'canonical_env': {'platform': 'linux', 'arch': 'x64', 'version': '2.1.293'}, 'canonical_prompt_env': {}, 'billing_mode': 'strip', 'concurrency': 4, 'priority': 50, 'rpm_limit': 50, 'five_hour_usage_limit_percent': 0, 'seven_day_usage_limit_percent': 0, 'auto_telemetry': False, 'auto_poll_usage': False, 'allow_fast_mode': False, 'allow_1m_models': 'opus', 'upstream_session_pool_enabled': True, 'upstream_session_pool_size': 4, 'upstream_session_ttl_minutes': 60, 'upstream_session_refresh_policy': 'owner_only', 'upstream_session_pool_active_count': 2, 'upstream_session_pool_capacity': 4, 'telemetry_count': 0, 'usage_data': {}, 'current_concurrency': 3, 'current_concurrency_units': 6, 'max_concurrency_units': 8, 'active_requests': 3, 'queued_requests': 0, 'transient_backoff_waiting': 0, 'transient_backoff_remaining_ms': 0, 'scheduling_score': 40, 'created_at': '2026-11-02T00:00:00Z', 'updated_at': '2026-11-02T00:00:00Z', 'v3_scheduling': summary()}
            value = {'data': [account], 'total': 1, 'total_pages': 1, 'page': 1, 'page_size': 12, 'claude_code_profile_selection_mode': 'client_version', 'claude_code_version_profile': '2.1.293'}
        elif path == '/admin/accounts/1/scheduling':
            if state['fail']:
                status, value = 503, {'error': '合成观测失败'}
            else:
                value = {'summary': summary(), 'snapshot': {'observed_at_ms': now, 'history_available_from_ms': now - 300000, 'history_truncated': False, 'dropped_events': 0, 'submissions_last_60s': 32, 'requests': [], 'events': [{'request_id': '00000000-0000-4000-8000-000000000001', 'account_id': 1, 'submitted_at_ms': now - i * 1200} for i in range(40)]}}
        elif path == '/admin/accounts/1/scheduling/sessions':
            query = parse_qs(parsed.query)
            page = int(query.get('page', ['1'])[0])
            selected = query.get('state', ['all'])[0]
            prefix = query.get('prefix', [''])[0]
            rows = [{'session_key': key, 'account_id': 1, 'created_at_ms': now - 3600000, 'last_seen_at_ms': now - i * 60000, 'expires_at_ms': now + 3600000, 'phases': phases(i)} for i, key in enumerate(keys) if key.startswith(prefix) and (selected == 'all' or (selected == 'active') == (i < 2))]
            value = {'items': rows[(page-1)*20:page*20], 'total': len(rows), 'page': page, 'page_size': 20, 'observed_at_ms': now}
        elif path == '/admin/settings':
            if route.request.method == 'PUT':
                payload = route.request.post_data_json
                assert all(isinstance(v, str) for v in payload.values())
                state['saved'] = payload
                settings.update(payload)
                value = {'ok': True}
            else:
                value = settings
        elif path == '/admin/prime-logs':
            value = []
        else:
            blocked.append(path)
            return route.abort()
        route.fulfill(status=status, content_type='application/json', body=json.dumps(value))

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        page.route('**/*', dispatch)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script("localStorage.setItem('claude-code-gateway_auth', 'synthetic-admin')")
        page.clock.install()
        page.goto(BASE)
        expect(page.get_by_role('button', name='调度详情', exact=True)).to_be_visible()
        page.get_by_role('button', name='调度详情', exact=True).click()
        dialog = page.get_by_role('dialog')
        expect(dialog.get_by_role('heading', name='真实提交时间轴')).to_be_visible()
        expect(dialog.locator('tbody tr')).to_have_count(20)
        expect(dialog.get_by_text('21 / 2', exact=True)).to_be_visible()
        page.screenshot(path=str(ROOT / 'ui-account-scheduling.png'), full_page=True)
        dialog.get_by_role('button', name='下一页', exact=True).click()
        expect(dialog.locator('tbody tr')).to_have_count(1)
        expect(dialog.locator('tbody tr td').first).to_have_text(keys[20][:12])
        dialog.get_by_label('会话摘要前缀').fill(keys[0][:6])
        dialog.get_by_role('button', name='筛选', exact=True).click()
        expect(dialog.locator('tbody tr')).to_have_count(1)
        expect(dialog.locator('tbody tr td').first).to_have_text(keys[0][:12])
        all_keys = keys.copy()
        keys.extend(hashlib.sha256(f'fixture-{i}'.encode()).hexdigest() for i in range(21, 61))
        dialog.get_by_label('会话摘要前缀').fill('')
        dialog.get_by_role('button', name='筛选', exact=True).click()
        expect(dialog.locator('tbody tr')).to_have_count(20)
        dialog.get_by_role('button', name='下一页', exact=True).click()
        expect(dialog.locator('tbody tr td').first).to_have_text(keys[20][:12])
        dialog.get_by_role('button', name='下一页', exact=True).click()
        expect(dialog.locator('tbody tr td').first).to_have_text(keys[40][:12])
        del keys[1:]
        before = calls['/admin/accounts/1/scheduling/sessions']
        page.clock.fast_forward(6000)
        expect(dialog.locator('tbody tr td').first).to_have_text(keys[0][:12])
        expect(dialog.get_by_role('button', name='上一页', exact=True)).to_be_disabled()
        expect(dialog.get_by_role('button', name='下一页', exact=True)).to_be_disabled()
        assert calls['/admin/accounts/1/scheduling/sessions'] - before == 2
        keys.clear()
        page.clock.fast_forward(6000)
        expect(dialog.get_by_text('当前筛选没有有效绑定', exact=True)).to_be_visible()
        expect(dialog.get_by_role('button', name='上一页', exact=True)).to_be_disabled()
        keys[:] = all_keys
        state['reason'] = 'wait_budget'
        page.clock.fast_forward(6000)
        expect(dialog.get_by_text('预计等待超过准入期限', exact=False)).to_be_visible()
        state['reason'] = 'pending_submissions'
        page.clock.fast_forward(6000)
        expect(dialog.get_by_text('前方请求准备或等待提交', exact=False)).to_be_visible()
        state['reason'] = 'pacing'
        state['fail'] = True
        page.clock.fast_forward(6000)
        expect(dialog.get_by_role('alert')).to_contain_text('数据已陈旧')
        expect(dialog.get_by_text('21 / 2', exact=True)).to_be_visible()
        before = calls['/admin/accounts/1/scheduling']
        page.evaluate("Object.defineProperty(document, 'hidden', {value: true, configurable: true}); document.dispatchEvent(new Event('visibilitychange'))")
        page.clock.fast_forward(11000)
        assert calls['/admin/accounts/1/scheduling'] == before
        state['fail'] = False
        page.evaluate("Object.defineProperty(document, 'hidden', {value: false, configurable: true}); document.dispatchEvent(new Event('visibilitychange'))")
        expect(dialog.get_by_role('alert')).to_have_count(0)
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).to_have_count(0)
        before = calls['/admin/accounts/1/scheduling']
        page.clock.fast_forward(11000)
        assert calls['/admin/accounts/1/scheduling'] == before
        page.goto(BASE + '/settings')
        expect(page.get_by_label('v3 新会话排序')).to_be_visible()
        page.get_by_label('v3 新会话排序').select_option('legacy_score')
        page.locator('#v3-wait-seconds').fill('30')
        page.locator('#v3-weight-0').fill('1.5')
        page.get_by_role('button', name='保存', exact=True).click()
        page.wait_for_timeout(100)
        assert state['saved'] is not None
        assert state['saved']['v3_admission_wait_seconds'] == '30'
        assert state['saved']['v3_smart_weight_load'] == '1.5'
        assert state['saved']['v3_scheduling_mode'] == 'legacy_score'
        assert not errors, errors
        assert not blocked, blocked
        result = {'passed': ['总览与详情渲染', '会话与请求分开', '分页与摘要筛选', '分页从三页缩至一页及归零', '容量超期及前方请求原因', '失败保留陈旧快照', '页面隐藏暂停详情刷新', '关闭详情停止刷新', '数字设置全部以字符串保存'], 'page_errors': errors, 'unexpected_or_model_requests': blocked}
        (ROOT / 'ui-check-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps(result, ensure_ascii=False))
        browser.close()


if __name__ == '__main__':
    main()
