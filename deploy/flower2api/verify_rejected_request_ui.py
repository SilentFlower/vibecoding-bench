"""用合成接口验证零上游尝试的拒绝原因及脱敏入口读取。"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from verify_management_ui import ManagementFixture
from verify_environment_ui import BASE, ROOT
from source_layout import source_path


class RejectedRequestFixture(ManagementFixture):
    """复用真实静态页面，隔离拒绝诊断及内容采集接口。"""

    def __init__(self, gateway):
        """建立独立拒绝样本。@param gateway 静态目录。@return None。"""
        super().__init__(gateway)
        self.status = 400
        self.reason = 'invalid_message_role'
        self.tui_submission_outcome = None

    async def route(self, route):
        """返回零尝试诊断和入口证据。@param route 浏览器请求。@return None。"""
        path = urlsplit(route.request.url).path
        if not path.startswith('/admin/request-diagnostics'):
            return await super().route(route)
        request_id = '11111111-1111-4111-8111-111111111111'
        legacy_unknown = self.tui_submission_outcome == 'local_rejected'
        capture_id = request_id if legacy_unknown else '33333333-3333-4333-8333-333333333333'
        if '/captures/' in path:
            assert path.endswith('/' + capture_id)
            self.capture_reads += 1
            body = '{"messages":[{"role":"system","content":[]}],"api_key":"[REDACTED]"}'
            return await self.respond(route, {'state': 'saved', 'snapshot': {
                'stage': 'ingress_rejected', 'body': '', 'headers': [],
                'body_truncated': False, 'headers_truncated': False,
                'original_body_bytes': None, 'original_body_sha256': None,
                'ingress': {'body': body, 'headers': [['authorization', '[REDACTED]']],
                    'body_truncated': False, 'headers_truncated': False,
                    'original_body_bytes': len(body), 'original_body_sha256': hashlib.sha256(body.encode()).hexdigest()},
                'stages': [{'stage': name, 'status': 'complete' if name == 'ingress' else 'unavailable',
                    'source': 'gateway_http_ingress' if name == 'ingress' else 'unavailable',
                    'representation': 'http_logical_bytes' if name == 'ingress' else 'unavailable'}
                    for name in ['ingress', 'header_policy', 'cc_prepared', 'wire_final']]}})
        row = {'request_id': request_id,
            'started_at': '2026-11-17T07:23:40.892Z', 'finished_at': '2026-11-17T07:23:41.146Z',
            'account_id': 11, 'account_name': '合成拒绝账号', 'status_code': self.status,
            'attempt_count': 0, 'log_mode': 'debug', 'outcome': 'local_rejected', 'error_stage': 'native_prepare',
            'native_rejection': {'reason': 'tui_send_http' if legacy_unknown else self.reason,
                                 'capture_id': capture_id, 'capture_status': 'queued'}}
        if self.tui_submission_outcome:
            row.update(status_code=502, outcome=self.tui_submission_outcome, error_stage='tui_send_http',
                       context={'tui_reservation_id': '22222222-2222-4222-8222-222222222222'})
            if self.tui_submission_outcome == 'transport_error':
                row.pop('native_rejection')
        value = {'items': [row], 'total': 1, 'health': {}} if path == '/admin/request-diagnostics' else {'request': row, 'attempts': []}
        return await self.respond(route, value)


async def run(output):
    """验证宽窄屏下的拒绝证据与提交状态未知。@param output 截图目录。@return 安全聚合报告。"""
    from playwright.async_api import async_playwright, expect
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    scenes = []
    capture_requests = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1280, 'height': 1000})
        fixture = RejectedRequestFixture(source_path(ROOT, 'cc2api/web/dist'))
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: capture_requests.append(request.url)
                if '/captures/' in urlsplit(request.url).path else None)
        for status, reason, label in [(400, 'invalid_message_role', '消息角色不符合当前接入格式'),
                (422, 'native_entrypoint_unsupported', '调用入口不支持')]:
            fixture.status, fixture.reason = status, reason
            for width in [1280, 390]:
                await page.set_viewport_size({'width': 1280, 'height': 1000})
                await page.goto(BASE + '/requests')
                await page.get_by_role('button', name='详情', exact=True).click()
                await page.set_viewport_size({'width': width, 'height': 1000})
                panel = page.get_by_role('tabpanel')
                await expect(panel).to_contain_text(label)
                await expect(panel).to_contain_text('本次在上游发送前拒绝')
                before = fixture.capture_reads
                requests_before = len(capture_requests)
                if width == 390:
                    await page.get_by_role('tab', name='原始数据', exact=True).click()
                    await panel.get_by_role('button', name='读取拒绝请求的入站证据', exact=True).click()
                else:
                    await panel.get_by_role('button', name='查看入站请求', exact=True).click()
                await expect(panel).to_contain_text('[REDACTED]')
                await expect(panel.locator('[data-native-stages]')).to_be_visible()
                assert fixture.capture_reads == before + 1
                assert len(capture_requests) == requests_before + 1
                await page.get_by_role('button', name='原生组装后', exact=True).click()
                await expect(panel).to_contain_text('本次未保存所选阶段的原文')
                await page.get_by_role('button', name='入口原文', exact=True).click()
                await page.screenshot(path=str(output / f'rejected-{status}-{width}.png'), full_page=True)
                scenes.append({'status': status, 'width': width, 'capture_reads': 1, 'passed': True})
                await page.keyboard.press('Escape')
        for width, outcome in [(390, 'local_rejected'), (1280, 'transport_error')]:
            fixture.tui_submission_outcome = outcome
            await page.set_viewport_size({'width': width, 'height': 1000})
            await page.goto(BASE + '/requests')
            await expect(page.locator('.request-result-button')).to_contain_text('提交状态未知')
            before = fixture.capture_reads
            requests_before = len(capture_requests)
            await page.get_by_role('button', name='详情', exact=True).click()
            panel = page.get_by_role('tabpanel')
            await expect(panel).to_contain_text('模型可能已收到请求')
            await expect(panel).to_contain_text('22222222-2222-4222-8222-222222222222')
            await expect(panel).to_contain_text('已记录尝试次数')
            await expect(panel).not_to_contain_text('本次在上游发送前拒绝')
            await expect(panel).not_to_contain_text('无执行尝试')
            await expect(panel.get_by_role('button', name='查看入站请求', exact=True)).to_have_count(0)
            await page.get_by_role('tab', name='原始数据', exact=True).click()
            await expect(panel.get_by_role('button', name='读取拒绝请求的入站证据', exact=True)).to_have_count(0)
            await expect(panel).to_contain_text('提交状态未知')
            await expect(panel).to_contain_text('没有已记录的上游尝试')
            await page.screenshot(path=str(output / f'unknown-raw-{width}.png'), full_page=True)
            assert fixture.capture_reads == before
            assert len(capture_requests) == requests_before
            scenes.append({'status': 502, 'stored_outcome': outcome, 'width': width, 'capture_reads': 0, 'passed': True})
            await page.keyboard.press('Escape')
        assert not errors, errors
        assert not fixture.external, fixture.external
        await browser.close()
    return {'passed': True, 'scenes': scenes, 'page_errors': errors, 'real_model_requests': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/rejected-request-ui')
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.output)), ensure_ascii=False))
