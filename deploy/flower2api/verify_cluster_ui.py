"""使用真实构建页面验证节点迁移确认、未知结果核对、恢复和窄屏布局。"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_environment_ui import BASE, ROOT, Fixture


class ClusterUiFixture(Fixture):
    """所有节点和迁移接口使用合成数据，页面资源来自实际构建。"""

    def __init__(self, gateway: Path) -> None:
        """建立双节点、双账号和可控制的响应。:param gateway: 实际构建目录。:return: None。"""
        super().__init__(gateway)
        self.assignments = {number: {'account_id': number, 'node_id': 1, 'node_key': 'local', 'node_name': '默认节点',
            'kind': 'local', 'enabled': True, 'revision': 1, 'phase': 'ready'} for number in (1, 2)}
        self.histories = {1: [], 2: []}
        self.nodes = [{'id': number, 'node_key': 'local' if number == 1 else 'a' * 32,
            'name': '默认节点' if number == 1 else '上海执行节点', 'kind': 'local' if number == 1 else 'ssh',
            'revision': 1, 'enabled': True, 'account_count': 1, 'host': None if number == 1 else 'node.example.invalid',
            'port': 22, 'username': 'synthetic', 'data_root': '/srv/synthetic', 'host_key_sha256': 'SHA256:synthetic',
            'observation': None, 'preparation': None if number == 1 else {'state': 'prepared', 'updated_at': time.time()}}
            for number in (1, 2)]
        self.start_gate = None
        self.start_entered = asyncio.Event()
        self.fail_start = False
        self.operation_reads = 0
        self.install_posts = 0
        self.synchronize_posts = 0
        self.install_complete = False
        self.fail_install_response = False

    async def route(self, route) -> None:
        """截获当前节点管理的全部业务路径。:param route: 浏览器请求。:return: None。"""
        request, path = route.request, urlsplit(route.request.url).path
        if path == '/nodes':
            await route.fulfill(path=str(self.gateway / 'index.html'), content_type='text/html')
            return
        if path == '/runtime/api/nodes':
            if self.install_complete:
                self.nodes[1]['preparation'] = {'state': 'prepared', 'updated_at': time.time()}
            payload = {'items': self.nodes}
        elif path == '/runtime/api/nodes/synchronize' and request.method == 'POST':
            self.synchronize_posts += 1
            self.nodes[1]['preparation'] = {'state': 'preparing', 'phase': 'backing_up', 'current_release': 'old', 'target_release': 'new'}
            payload = {'items': self.nodes}
        elif path == '/runtime/api/nodes/2/prepare' and request.method == 'POST':
            assert json.loads(request.post_data)['revision'] == self.nodes[1]['revision']
            self.install_posts += 1
            self.nodes[1]['preparation'] = {'state': 'preparing', 'updated_at': time.time()}
            if self.fail_install_response:
                self.fail_install_response = False
                await route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': '安装提交响应中断'}))
                return
            await route.fulfill(status=202, content_type='application/json', body=json.dumps(self.nodes[1]))
            return
        elif path == '/runtime/api/accounts':
            payload = [{'id': number, 'name': '合成账号 ' + str(number), 'enabled': 1 if number == 1 else 0,
                'cc2api_account_id': 7 if number == 1 else None, 'effective_claude_code_version': '2.1.293'} for number in (1, 2)]
        elif match := re.fullmatch(r'/runtime/api/accounts/([12])/node', path):
            payload = self.assignments[int(match[1])]
        elif match := re.fullmatch(r'/runtime/api/accounts/([12])/node-migrations(?:/([a-f0-9]{32})(?:/(resume|cancel))?)?', path):
            account_id = int(match[1])
            history = self.histories[account_id]
            if request.method == 'GET':
                if match[2]:
                    self.operation_reads += 1
                    payload = next(row for row in history if row['operation_id'] == match[2])
                else:
                    payload = {'items': history}
            else:
                body = json.loads(request.post_data or '{}')
                self.writes.append({'path': path, 'body': body})
                if not match[2]:
                    assert re.fullmatch('[a-f0-9]{32}', body['operation_id'])
                    assert body['revision'] == self.assignments[account_id]['revision']
                    target = next(row for row in self.nodes if row['id'] == body['node_id'])
                    source = next(row for row in self.nodes if row['id'] == self.assignments[account_id]['node_id'])
                    payload = {'operation_id': body['operation_id'], 'account_id': account_id,
                        'source': {'id': source['id'], 'name': source['name']}, 'target': {'id': target['id'], 'name': target['name']},
                        'phase': 'reconcile', 'last_confirmed_phase': 'importing', 'message': '迁移需要核对',
                        'failure': {'code': 'disk_space', 'stage': 'transfer', 'message': '迁移暂存磁盘空间不足', 'action': '释放对应节点空间后继续原迁移'},
                        'running': False, 'can_resume': True, 'can_cancel': True, 'source_revision': body['revision'],
                        'target_revision': None, 'cancelling': False, 'created_at': time.time(), 'updated_at': time.time()}
                    history.insert(0, payload)
                    self.assignments[account_id]['phase'] = 'maintenance'
                    self.start_entered.set()
                    if self.start_gate is not None:
                        await self.start_gate.wait()
                    if self.fail_start:
                        self.fail_start = False
                        await route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': '合成提交响应中断'}))
                        return
                else:
                    payload = next(row for row in history if row['operation_id'] == match[2])
                    if match[3] == 'cancel':
                        assert payload['can_cancel']
                        payload.update(phase='cancelled', last_confirmed_phase='cancelled', message='迁移已取消',
                            can_resume=False, can_cancel=False, cancelling=True)
                        self.assignments[account_id]['phase'] = 'ready'
                    elif payload['phase'] == 'reconcile':
                        payload.update(failure=None, phase='committed', last_confirmed_phase='committed', message='归属已切换，正在激活目标', can_cancel=False)
                        self.assignments[account_id].update(node_id=payload['target']['id'], node_name=payload['target']['name'],
                            revision=payload['source_revision'] + 1, node_key='a' * 32, kind='ssh')
                    else:
                        payload.update(failure=None, phase='completed', last_confirmed_phase='completed', message='迁移完成', can_resume=False)
                        self.assignments[account_id]['phase'] = 'ready'
        else:
            await super().route(route)
            return
        await route.fulfill(content_type='application/json', body=json.dumps(copy.deepcopy(payload)))


async def select(page, label: str, value: str) -> None:
    """通过真实复用选择器选择可见项。:param page: 当前页面。:param label: 控件名。:param value: 选项名。:return: None。"""
    await page.get_by_role('combobox', name=label, exact=True).click()
    await page.get_by_role('option', name=value, exact=True).click()


async def run(output: Path, gateway: Path) -> dict:
    """运行合成节点迁移交互并保存真实页面截图。

    :param output: 证据目录。
    :param gateway: 已构建页面目录。
    :return: 场景和异常摘要。
    """
    fixture, errors = ClusterUiFixture(gateway), []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(BASE + '/nodes')
        node_card = page.locator('.node-card').filter(has=page.get_by_role('heading', name='上海执行节点', exact=True))
        await node_card.get_by_role('button', name='检查并同步组件', exact=True).click()
        installation = page.get_by_role('dialog', name='准备节点运行组件', exact=True)
        await installation.get_by_role('button', name='开始准备', exact=True).click()
        await expect(installation).to_have_count(0)
        await expect(node_card.get_by_role('button', name='后台同步中…', exact=True)).to_be_disabled()
        assert fixture.install_posts == 1
        await page.reload()
        await expect(node_card.get_by_role('button', name='后台同步中…', exact=True)).to_be_disabled()
        fixture.install_complete = True
        await expect(node_card.get_by_role('button', name='检查并同步组件', exact=True)).to_be_enabled(timeout=10000)
        assert fixture.install_posts == 1
        fixture.install_complete = False
        fixture.fail_install_response = True
        await node_card.get_by_role('button', name='检查并同步组件', exact=True).click()
        await installation.get_by_role('button', name='开始准备', exact=True).click()
        await expect(installation.get_by_role('alert')).to_contain_text('安装提交响应中断')
        await installation.get_by_role('button', name='取消', exact=True).click()
        await expect(node_card.get_by_role('button', name='后台同步中…', exact=True)).to_be_disabled()
        fixture.install_complete = True
        await expect(node_card.get_by_role('button', name='检查并同步组件', exact=True)).to_be_enabled(timeout=10000)
        assert fixture.install_posts == 2
        fixture.install_complete = False
        fixture.nodes[1]['preparation'] = None
        await page.reload()
        await select(page, '任务账号', '合成账号 1')
        await select(page, '执行节点', '上海执行节点')
        start = page.get_by_role('button', name='迁移到所选节点', exact=True)
        await expect(start).to_be_enabled()
        await start.click()
        confirmation = page.get_by_role('dialog', name='迁移账号环境', exact=True)
        await confirmation.get_by_role('button', name='取消', exact=True).click()
        assert not fixture.writes
        await start.click()
        fixture.start_gate, fixture.fail_start = asyncio.Event(), True
        await confirmation.get_by_role('button', name='开始迁移', exact=True).click()
        await asyncio.wait_for(fixture.start_entered.wait(), timeout=3)
        await expect(page.locator('.account-node-selector [role="combobox"]').first).to_be_disabled()
        fixture.start_gate.set()
        await expect(confirmation.get_by_role('alert')).to_contain_text('合成提交响应中断')
        await confirmation.get_by_role('button', name='核对原操作', exact=True).click()
        await expect(confirmation).to_have_count(0)
        assert len(fixture.writes) == 1 and fixture.operation_reads == 1
        await expect(page.locator('.migration-status')).to_contain_text('释放对应节点空间后继续原迁移')
        await expect(page.locator('.migration-status')).to_contain_text('传输资料')
        await page.get_by_role('button', name='继续原迁移', exact=True).click()
        await expect(page.locator('.migration-status')).to_contain_text('归属已切换')
        await expect(page.get_by_role('button', name='取消迁移', exact=True)).to_have_count(0)
        await page.get_by_role('button', name='继续原迁移', exact=True).click()
        await expect(page.locator('.migration-status')).to_contain_text('迁移完成')
        operation = fixture.histories[1][0]['operation_id']
        assert [row['path'].split('/')[-1] for row in fixture.writes[1:]] == ['resume', 'resume']
        assert all(operation in row['path'] for row in fixture.writes[1:])
        await page.screenshot(path=str(output / 'migration-1440.png'), full_page=True)
        await page.set_viewport_size({'width': 390, 'height': 900})
        await page.screenshot(path=str(output / 'migration-390.png'), full_page=True)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        previous = copy.deepcopy(fixture.histories[1][0])
        previous.update(operation_id='b' * 32, phase='reconcile', last_confirmed_phase='importing', message='迁移需要核对',
            can_resume=True, can_cancel=True, source=previous['target'], target={'id': 1, 'name': '默认节点'}, source_revision=2)
        fixture.histories[1].insert(0, previous)
        fixture.assignments[1]['phase'] = 'reconcile'
        await page.reload()
        await select(page, '任务账号', '合成账号 1')
        await page.get_by_role('button', name='取消迁移', exact=True).click()
        cancel = page.get_by_role('dialog', name='取消原迁移', exact=True)
        before = len(fixture.writes)
        await cancel.get_by_role('button', name='取消', exact=True).click()
        assert len(fixture.writes) == before
        await page.get_by_role('button', name='取消迁移', exact=True).click()
        await cancel.get_by_role('button', name='确认取消迁移', exact=True).click()
        await expect(page.locator('.migration-status')).to_contain_text('迁移已取消')
        assert fixture.assignments[1]['node_id'] == 2 and fixture.assignments[1]['revision'] == 2
        await select(page, '任务账号', '合成账号 2（已停用）')
        await expect(page.locator('.node-migration')).to_contain_text('当前账号还没有迁移记录')
        await select(page, '执行节点', '上海执行节点')
        await expect(start).to_be_enabled()
        await start.click()
        await expect(confirmation).to_contain_text('合成账号 2')
        await confirmation.get_by_role('button', name='取消', exact=True).click()
        fixture.install_complete = False
        await page.get_by_role('button', name='同步全部节点', exact=True).click()
        await expect(node_card).to_contain_text('备份节点资料')
        await expect(node_card).to_contain_text('old → new')
        assert fixture.synchronize_posts == 1
        await page.screenshot(path=str(output / 'node-synchronization-390.png'), full_page=True)
        assert not errors and not fixture.unexpected and not fixture.external, (errors, fixture.unexpected, fixture.external)
        await browser.close()
    return {'passed': True, 'scenes': ['后台安装提交后关闭弹窗', '刷新页面恢复安装状态及轮询完成', '安装提交响应中断后只读核对', '冻结确认与取消零写入', '提交未知只核对原操作', '提交后继续目标激活',
        '提交前取消保持源分配版本', '账号切换隔离', '停用独立账号迁移入口', '1440和390视口', '统一同步后台受理与阶段显示', '迁移固定原因与恢复动作', '未准备节点可选择并直接提交迁移'], 'errors': errors, 'real_model_requests': 0}


def main() -> None:
    """读取实际产物路径并写出浏览器证据。:return: None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/cluster-ui')
    parser.add_argument('--gateway-dist', type=Path, default=ROOT / 'apps/web/dist')
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run(arguments.output.resolve(), arguments.gateway_dist.resolve()))
    (arguments.output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
