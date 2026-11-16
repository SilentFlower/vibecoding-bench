"""用真实前端和合成接口验证环境卡片的 CPU 配额读取。"""
import asyncio
import copy
import json
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_environment_ui import BASE, ROOT
from verify_native_diagnostics_cpu import DiagnosticsCpuFixture


class CpuSummaryFixture(DiagnosticsCpuFixture):
    """提供独立失败、迟到快照及环境换代的 CPU 接口。"""

    def __init__(self):
        """初始化四个可独立读取的环境。@return None。"""
        super().__init__(ROOT / 'apps/web/dist')
        for row in self.rows:
            row['isolation_version'] = 2
        self.failed_id = self.rows[1]['environment_id']
        self.gate = None
        self.gated = asyncio.Event()
        self.active = 0
        self.maximum = 0
        self.cpu_reads = 0
        self.forced_generation = None

    async def route(self, route):
        """拦截只读配额，写入继续复用原合同。@param route 浏览器请求。@return None。"""
        path = urlsplit(route.request.url).path
        if path.endswith('/cpu-resources') and route.request.method == 'GET':
            environment_id = path.split('/')[-2]
            row = next(row for row in self.rows if row['environment_id'] == environment_id)
            self.cpu_reads += 1
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                if environment_id == self.failed_id:
                    return await route.fulfill(status=503, content_type='application/json',
                        body=json.dumps({'detail': '合成 CPU 读取失败'}))
                payload = {'generation': self.forced_generation or row['generation'],
                    'revision': self.cpu_revision, 'host_cpus': 4, 'cpus': copy.deepcopy(self.cpus)}
                if environment_id == self.rows[0]['environment_id'] and self.gate:
                    gate, self.gate = self.gate, None
                    self.gated.set()
                    await gate.wait()
                return await route.fulfill(content_type='application/json', body=json.dumps(payload))
            finally:
                self.active -= 1
        return await super().route(route)


async def main():
    """覆盖首屏、失败恢复、编辑回填、换代、迟到响应和离页。@return None。"""
    fixture = CpuSummaryFixture()
    gate = asyncio.Event()
    fixture.gate = gate
    errors = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(error.message))
        await page.goto(BASE + '/environments')
        cards = page.locator('.environment-rich')
        await expect(cards).to_have_count(4)
        first = cards.first.locator('.environment-resources-grid')
        await asyncio.wait_for(fixture.gated.wait(), timeout=5)
        await expect(first).to_contain_text('读取中')
        await expect(cards.nth(1).locator('.environment-resources-grid')).to_contain_text('读取失败')
        await expect(cards.nth(2).locator('.environment-resources-grid')).to_contain_text('1.5 核')
        gate.set()
        await expect(first).to_contain_text('1.5 核')
        await expect(first).to_contain_text('0.5 核')
        assert fixture.maximum <= 3
        assert not fixture.cpu_writes

        fixture.failed_id = None
        refresh = page.get_by_role('button', name='刷新', exact=True)
        await refresh.click()
        await expect(cards.nth(1).locator('.environment-resources-grid')).to_contain_text('1.5 核')

        gate = asyncio.Event()
        fixture.gate = gate
        fixture.gated.clear()
        await refresh.click()
        await asyncio.wait_for(fixture.gated.wait(), timeout=5)
        fixture.cpus['cli'] = 2.25
        await cards.first.get_by_role('button', name='资源与采集', exact=True).click()
        workspace = page.locator('.runtime-environment-dialog')
        cpu_input = workspace.get_by_role('spinbutton', name='CLI CPU', exact=True)
        await expect(cpu_input).to_have_value('2.25')
        await expect(first).to_contain_text('2.25 核')
        gate.set()
        await page.wait_for_timeout(100)
        await expect(first).to_contain_text('2.25 核')
        await cpu_input.fill('3')
        await workspace.get_by_role('button', name='保存并应用', exact=True).click()
        await expect(first).to_contain_text('3 核')
        await workspace.get_by_role('button', name='关闭环境详情', exact=True).click()

        fixture.rows[0]['generation'] = 11
        fixture.cpus['cli'] = 1.75
        gate = asyncio.Event()
        fixture.gate = gate
        fixture.gated.clear()
        await refresh.click()
        await asyncio.wait_for(fixture.gated.wait(), timeout=5)
        await expect(first).to_contain_text('读取中')
        await expect(first).not_to_contain_text('3 核')
        fixture.rows[0]['generation'] = 12
        fixture.cpus['cli'] = 2
        await refresh.click()
        await expect(first).to_contain_text('2 核')
        gate.set()
        await page.wait_for_timeout(100)
        await expect(first).to_contain_text('2 核')

        fixture.forced_generation = 13
        await refresh.click()
        await expect(first).to_contain_text('读取失败')
        fixture.forced_generation = None
        fixture.rows[0]['isolation_version'] = 1
        await refresh.click()
        await expect(first).to_contain_text('未提供')
        await page.get_by_role('link', name='请求记录', exact=True).first.click()
        await expect(page).to_have_url(BASE + '/requests')
        reads = fixture.cpu_reads
        await page.wait_for_timeout(2300)
        assert fixture.cpu_reads == reads
        assert not errors, errors
        assert not fixture.unexpected, fixture.unexpected
        await browser.close()
    print(json.dumps({'passed': True, 'checks': ['首屏自动读取与并发上限', '单环境失败及重试',
        '编辑器新回执优先', '保存同步卡片', '换代清理与迟到响应', '代次不符拒绝', '历史布局', '离页停止'],
        'real_model_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
