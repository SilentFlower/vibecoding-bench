"""使用真实页面与合成接口验证分阶段诊断和CPU表单，全部浏览器流量在进程内拦截。"""
import argparse
import asyncio
import copy
import json
from pathlib import Path
from source_layout import source_path
from urllib.parse import urlsplit

from verify_environment_ui import Fixture, BASE, ENVIRONMENT, ROOT

REQUEST = '11111111-1111-4111-8111-111111111111'
ATTEMPT = '22222222-2222-4222-8222-222222222222'


class DiagnosticsCpuFixture(Fixture):
    """复用原环境夹具并追加两项新管理合同。"""

    def __init__(self, gateway: Path, source_version: str = '2.1.293'):
        """建立独立资源状态。@param gateway 真实网关产物。@param source_version 诊断的实际官方源版本。@return None。"""
        super().__init__(gateway)
        assert source_version in ('2.1.280', '2.1.293')
        self.source_version = source_version
        self.rows[0]['isolation_version'] = 2
        self.cpus = {'cli': 1.5, 'sender': 1, 'network': 0.5}
        self.cpu_revision = 'a'*64
        self.cpu_writes = []
        self.cpu_read_gate = None
        self.cpu_read_started = asyncio.Event()

    async def route(self, route):
        """仅接管新增接口，其余流量沿原夹具。@param route 浏览器请求。@return None。"""
        request = route.request
        parsed = urlsplit(request.url)
        if parsed.netloc != 'environment-ui.test':
            return await super().route(route)
        if parsed.path.endswith('/cpu-resources'):
            status = 200
            payload = {'generation': 10, 'revision': self.cpu_revision, 'host_cpus': 4,
                'cpus': copy.deepcopy(self.cpus), 'persisted_cpus': copy.deepcopy(self.cpus)}
            if request.method == 'POST':
                body = json.loads(request.post_data)
                self.cpu_writes.append(body)
                if body['expected_revision'] != self.cpu_revision or body['expected_generation'] != 10:
                    status, payload = 409, {'detail': 'CPU额度已变化，请重新读取'}
                else:
                    self.cpus = body['cpus']
                    self.cpu_revision = 'b'*64
                    payload.update(cpus=self.cpus, persisted_cpus=self.cpus, revision=self.cpu_revision)
            elif self.cpu_read_gate:
                gate, self.cpu_read_gate = self.cpu_read_gate, None
                payload['cpus']['cli'] = 0.5
                self.cpu_read_started.set()
                await gate.wait()
            await route.fulfill(status=status, content_type='application/json', body=json.dumps(payload))
            return
        if parsed.path.startswith('/admin/request-diagnostics'):
            root = {'request_id': REQUEST, 'started_at': '2026-11-12T00:00:00Z', 'status_code': 200,
                'account_id': 1, 'outcome': 'success', 'attempt_count': 2, 'log_mode': 'debug'}
            attempt = {'attempt_id': ATTEMPT, 'account_id': 1, 'ordinal': 1, 'profile_selection': 'native' + self.source_version.rsplit('.', 1)[1] + '_cc_prepared',
                'status_code': 200, 'outcome': 'success', 'log_mode': 'debug', 'capture_status': 'saved'}
            if '/captures/' in parsed.path:
                snapshot = {'stage': 'cc_prepared', 'headers': [['accept', 'application/json']], 'body': '{"model":"synthetic"}',
                    'body_truncated': False, 'headers_truncated': False, 'original_body_bytes': 100, 'original_body_sha256': 'a'*64}
                if parsed.path.endswith(ATTEMPT):
                    snapshot.update(ingress={'source': 'gateway_http_ingress', 'representation': 'http_logical_bytes', 'status': 'complete',
                        'headers': [['x-unregistered', 'synthetic']], 'body': '{"settings":"[REDACTED]"}', 'body_truncated': False,
                        'headers_truncated': False, 'original_body_bytes': 100, 'original_body_sha256': 'b'*64},
                        header_policy={'source': 'native_header_policy', 'status': 'complete', 'observed_count': 3, 'stored_count': 3,
                            'decisions': [{'name': 'x-unregistered', 'action': 'drop', 'reason': '未登记到协议白名单'},
                                {'name': 'accept', 'action': 'keep', 'reason': '合法协议'},
                                {'name': 'authorization', 'action': 'runtime', 'reason': '<img src=x onerror="window.stageInjected=1">'}]},
                        body_changes={'source': 'observed_diff', 'status': 'complete', 'items': [{'path': '/settings', 'action': 'removed', 'reason': '本机设置由账号运行时管理'}]})
                payload = {'state': 'available', 'snapshot': snapshot}
            elif parsed.path == '/admin/request-diagnostics':
                payload = {'items': [root], 'total': 1, 'health': {}}
            else:
                payload = {'request': root, 'attempts': [attempt, dict(attempt, ordinal=2, attempt_id='33333333-3333-4333-8333-333333333333')]}
            await route.fulfill(content_type='application/json', body=json.dumps(payload))
            return
        await super().route(route)


async def run(output: Path, gateway: Path) -> dict:
    """验证输入保留、并发冲突、迟到响应及移动端详情。@param output 证据目录。@param gateway 网关产物。@return 报告。"""
    from playwright.async_api import async_playwright, expect
    fixture = DiagnosticsCpuFixture(gateway)
    scenes, errors = [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1280, 'height': 1000}, service_workers='block')
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            await page.goto(BASE+'/environments')
            target=page.locator('.environment-rich').first
            await target.get_by_role('button',name='资源与采集',exact=True).click()
            workspace=page.locator('.runtime-environment-dialog');form=workspace.locator('.environment-resource-editor form')
            for name in ['CLI CPU','发送器 CPU','网络 CPU']:await form.get_by_role('spinbutton',name=name,exact=True).fill('2')
            await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            await expect(form.get_by_role('spinbutton',name='发送器 CPU',exact=True)).to_have_value('2')
            await form.get_by_role('button',name='保存并应用',exact=True).click()
            await expect(workspace.get_by_text('CPU 额度已应用，重建配置已保存。',exact=True)).to_be_visible()
            assert fixture.cpus==dict.fromkeys(('cli','sender','network'),2)
            assert sum(fixture.cpu_writes[0]['cpus'].values())==6
            scenes.append('三角色独立额度、轮询输入保留和冻结版本保存')
            fixture.cpu_revision='c'*64
            await form.get_by_role('button',name='保存并应用',exact=True).click()
            await expect(form.get_by_role('alert')).to_contain_text('已变化')
            await workspace.get_by_role('button',name='关闭环境详情').click()
            gate=asyncio.Event();fixture.cpu_read_gate=gate
            await target.get_by_role('button',name='资源与采集',exact=True).click();await fixture.cpu_read_started.wait()
            await workspace.get_by_role('button',name='关闭环境详情').click()
            await target.get_by_role('button',name='资源与采集',exact=True).click()
            await expect(form.get_by_role('spinbutton',name='CLI CPU',exact=True)).to_have_value('2');gate.set()
            await page.wait_for_timeout(50);await expect(form.get_by_role('spinbutton',name='CLI CPU',exact=True)).to_have_value('2')
            await page.set_viewport_size({'width':390,'height':844});assert await workspace.evaluate('e=>e.scrollWidth<=e.clientWidth')
            await page.screenshot(path=str(output/'cpu-390.png'),full_page=True)
            await workspace.get_by_role('button',name='关闭环境详情').click()
            scenes.append('资源CAS冲突、关闭后旧回执失效及390px布局')
            await page.goto(BASE+'/requests')
            await page.get_by_role('button', name='详情', exact=True).click()
            await page.get_by_role('button', name='阶段证据', exact=True).first.click()
            stages = page.locator('[data-native-stages]')
            await expect(stages.locator('.request-stages article')).to_have_count(4)
            for name in ['头部处理', '正文变化']:
                await expect(stages.get_by_role('heading', name=name, exact=True)).to_be_visible()
            await expect(stages.get_by_text('/settings', exact=True)).to_be_visible()
            await stages.get_by_role('combobox',name='筛选头部处理动作').click()
            await page.get_by_role('option',name='只看删除',exact=True).click()
            await expect(stages.get_by_text('x-unregistered', exact=True)).to_be_visible()
            await expect(stages.get_by_text('authorization', exact=True)).to_have_count(0)
            await stages.get_by_role('button',name='入口原文',exact=True).click()
            await expect(stages.locator('.request-code-block pre').last).to_contain_text('[REDACTED]')
            assert await page.evaluate('window.stageInjected===undefined')
            assert await page.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
            await page.screenshot(path=str(output/'diagnostics-390.png'), full_page=True)
            scenes.append('390px 三块诊断、真实动作筛选、正文路径及阶段原文可用，HTML按文本展示')
            await page.get_by_role('combobox',name='当前尝试',exact=True).click()
            await page.get_by_role('option',name='尝试 2',exact=False).click()
            await page.get_by_role('button',name='读取阶段证据',exact=True).click()
            await expect(stages.get_by_text('历史记录未保存逐字段处理明细。', exact=True)).to_be_visible()
            await expect(stages.get_by_text('本次未采集独立最终TLS写出', exact=True)).to_be_visible()
            scenes.append('历史快照缺失明细及最终TLS未采集保持明确')
            assert not errors, errors
            assert not fixture.unexpected, fixture.unexpected
            return {'status': 'passed', 'scenes': scenes, 'script_errors': errors,
                'cpu_writes': len(fixture.cpu_writes), 'real_model_requests': 0, 'synthetic_only': True}
        except Exception:
            await page.screenshot(path=str(output/'failure.png'), full_page=True)
            raise
        finally:
            await browser.close()


def main():
    """执行本地离线页面验证。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'.deploy/native-diagnostics-cpu-browser')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run(args.output.resolve(), source_path(ROOT, 'cc2api/web/dist')))
    (args.output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
