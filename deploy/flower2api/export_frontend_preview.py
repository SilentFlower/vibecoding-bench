"""使用合成数据将实际前端导出为可离线浏览的静态设计预览。"""
import argparse
import asyncio
import base64
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from verify_management_ui import ManagementFixture
from verify_environment_ui import BASE, ROOT


class PreviewFixture(ManagementFixture):
    """补齐账号、令牌和静态入口，所有数据仅用于本地预览。"""

    def __init__(self):
        """准备独立示例数据。@return None。"""
        super().__init__(ROOT / 'apps/web/dist')
        self.accounts = [dict(id=i, name=name, email=f'account{i}@example.test', status='active', auth_type='oauth',
            setup_token='', access_token='', refresh_token='', proxy_url='', device_id='synthetic', billing_mode='strip',
            concurrency=3, priority=50, rpm_limit=20, five_hour_usage_limit_percent=90, seven_day_usage_limit_percent=90,
            auto_telemetry=False, auto_poll_usage=True, allow_1m_models='opus', allow_fast_mode=False,
            upstream_session_pool_enabled=False, upstream_session_pool_size=2, upstream_session_ttl_minutes=30,
            upstream_session_refresh_policy='mapped_request', telemetry_count=0, created_at='2026-11-14T00:00:00Z',
            updated_at='2026-11-14T00:00:00Z', current_concurrency=0, subscription_type='max',
            usage_data={'five_hour': {'utilization': i * 12}, 'seven_day': {'utilization': i * 8}})
            for i, name in enumerate(['日常开发', '工程任务', '备用账号'], 1)]
        self.tokens = [dict(id=1, name='开发客户端', token='sk-preview-example-only', allowed_accounts='', blocked_accounts='',
            status='active', created_at='2026-11-14T00:00:00Z', updated_at='2026-11-14T00:00:00Z')]

    async def route(self, route):
        """提供合成接口与真实构建资源。@param route 浏览器路由。@return None。"""
        path = urlsplit(route.request.url).path
        if path == '/admin/dashboard':
            return await self.respond(route, {'accounts': {'total': 3, 'active': 3, 'error': 0, 'disabled': 0}, 'tokens': 1})
        if path in ('/admin/accounts', '/admin/tokens'):
            rows = self.accounts if path.endswith('accounts') else self.tokens
            return await self.respond(route, {'data': rows, 'total': len(rows), 'page': 1, 'page_size': 20, 'total_pages': 1})
        if path == '/admin/prime-logs':
            return await self.respond(route, [])
        if path in ('/tokens', '/settings', '/login'):
            return await route.fulfill(path=str(self.gateway / 'index.html'), content_type='text/html')
        return await super().route(route)


async def snapshot(frame):
    """内嵌实际样式和图标，去除业务脚本。@param frame 页面或子文档。@return 离线HTML。"""
    data = await frame.evaluate("""() => {
      const root = document.documentElement.cloneNode(true);
      root.querySelectorAll('script, link, style').forEach(node => node.remove());
      const styles = [...document.styleSheets].map(sheet => {
        try { return [...sheet.cssRules].map(rule => rule.cssText).join('\\n'); } catch { return ''; }
      }).join('\\n');
      return { html: root.outerHTML, styles };
    }""")
    # 外部SVG符号表也内嵌，离线快照保留确认稿的同一组图标路径。
    symbols = set(re.findall(r'(?:href|xlink:href)="((?:/assets/approved-icons-[^"#]+|(?:/runtime/)?approved-icons)\.svg)#[^"]+"', data['html']))
    for symbol_path in symbols:
        directory = ROOT / ('apps/legacy-web' if symbol_path.endswith('approved-icons.svg') else 'apps/web/dist')
        resource = (directory / ('approved-icons.svg' if symbol_path.endswith('approved-icons.svg') else symbol_path.lstrip('/'))).resolve()
        if resource.is_relative_to(directory.resolve()) and resource.is_file():
            sprite = resource.read_text().replace('<svg ', '<svg style="display:none" ', 1)
            end = data['html'].find('>', data['html'].find('<body')) + 1
            data['html'] = data['html'][:end] + sprite + data['html'][end:]
            data['html'] = data['html'].replace(symbol_path + '#', '#')

    # 正式页面新增自托管字体；离线快照将同源字体一并内嵌。
    def embed_font(match):
        """替换构建字体路径为离线数据。@param match CSS URL。@return 字体URL。"""
        path = urlsplit(match.group(2)).path
        directory = ROOT / 'apps/web/dist'
        resource = (directory / path.lstrip('/')).resolve()
        if path in ('fonts/inter-variable.woff2','fonts/jetbrains-mono-variable.woff2','/runtime/fonts/inter-variable.woff2','/runtime/fonts/jetbrains-mono-variable.woff2'):
            directory = ROOT / 'apps/legacy-web'
            resource = directory / 'fonts' / Path(path).name
        if resource.is_relative_to(directory.resolve()) and resource.is_file():
            return 'url(data:font/woff2;base64,' + base64.b64encode(resource.read_bytes()).decode() + ')'
        return match.group(0)
    data['styles'] = re.sub(r"url\((['\"]?)([^)'\"]+\.woff2)\1\)", embed_font, data['styles'])
    text = data['html'].replace('</head>', '<style>' + data['styles'].replace('</style', '<\\/style') + '*{animation:none!important;transition:none!important}</style></head>')
    icon = base64.b64encode((ROOT / 'apps/web/public/favicon.svg').read_bytes()).decode()
    text = text.replace('/favicon.svg?v=flower2api-pink-04', 'data:image/svg+xml;base64,' + icon)
    return text


async def export(output):
    """导出页面快照和预览索引。@param output 输出目录。@return 验证结果。"""
    from playwright.async_api import async_playwright
    output.mkdir(parents=True, exist_ok=True)
    views = []
    errors = []
    routes = [('/', '账号'), ('/updates', '系统更新'), ('/requests', '请求记录'), ('/tokens', '令牌'),
        ('/settings', '设置'), ('/environments', '环境'), ('/tasks', '任务账号'), ('/tasks?tab=topics', '题库'),
        ('/tasks?tab=tasks', '普通任务'), ('/tasks?tab=runs', '运行记录'), ('/tasks?tab=projects', '工程迭代'),
        ('/tasks?tab=warmup', '养号迭代')]
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Shanghai')
        fixture = PreviewFixture()
        await context.route('**/*', fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only');localStorage.setItem('vibebench-theme','light');")
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        for path, label in routes:
            await page.goto(BASE + path)
            await page.locator('.console-workspace').wait_for()
            await page.wait_for_timeout(600)
            if path.startswith('/tasks'):
                await page.locator('.task-runtime[aria-busy=false] #view > *').first.wait_for()
            elif path=='/environments':
                await page.locator('.environment-rich').first.wait_for()
            await page.evaluate('scrollTo(0,0)')
            await page.screenshot(path=str(output / (label + '.png')), full_page=True)
            views.append({'path': path, 'label': label, 'html': await snapshot(page)})
        await context.close()
        # 登录使用独立无凭据上下文。
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        await context.route('**/*', fixture.route)
        page = await context.new_page()
        await page.goto(BASE + '/login')
        await page.locator('#admin-password').wait_for()
        views.append({'path': '/login', 'label': '登录', 'html': await snapshot(page)})
        await browser.close()
    assert not errors, errors
    payload = json.dumps(views, ensure_ascii=False).replace('<', '\\u003c')
    document = '''<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>flower2api · 静态设计预览</title>
<style>*{box-sizing:border-box}body{margin:0;font:13px system-ui,sans-serif;background:#e9eeec;color:#243d33}header{height:52px;display:flex;align-items:center;gap:12px;padding:8px 18px;border-bottom:1px solid #ccdcd3;background:#f0f7f2}select,button{font:inherit;padding:6px 10px;background:white;border:1px solid #cbdcd1;border-radius:6px;color:inherit}#stage{display:block;width:100%;height:calc(100dvh - 52px);margin:auto;border:0;background:white}small{color:#62796c}#notice{margin-left:auto} @media(max-width:650px){header{padding:8px;gap:6px}small,#notice{display:none}}</style>
<header><strong>静态设计预览</strong><small>示例数据</small><select id="pages" aria-label="预览页面"></select><button id="width">窄屏预览</button><span id="notice">点击侧栏或选择页面浏览</span></header><iframe id="stage" title="设计页面"></iframe>
<script>const views=PAYLOAD;const selector=document.querySelector('#pages'),stage=document.querySelector('#stage'),notice=document.querySelector('#notice');
views.forEach((view,i)=>selector.add(new Option(view.label,i)));
function show(index){selector.value=index;stage.srcdoc=views[index].html;}
selector.onchange=()=>show(Number(selector.value));
document.querySelector('#width').onclick=function(){const narrow=stage.style.maxWidth==='390px';stage.style.maxWidth=narrow?'':'390px';this.textContent=narrow?'窄屏预览':'桌面预览';};
function bind(doc){doc.addEventListener('submit',event=>event.preventDefault(),true);doc.addEventListener('click',event=>{const a=event.target.closest('a');const button=event.target.closest('button');if(a){const href=a.getAttribute('href')||'';let index=views.findIndex(view=>view.path===href);if(href.startsWith('#')&&['accounts','topics','tasks','runs','projects','warmup'].includes(href.slice(1))){index=views.findIndex(view=>view.path==='/tasks'+(href==='#accounts'?'':'?tab='+href.slice(1)));}if(index>=0){event.preventDefault();show(index);return;}if(!href.startsWith('#'))event.preventDefault();}if(button){event.preventDefault();if(button.getAttribute('aria-label')?.includes('侧边栏')){doc.querySelector('.console-shell')?.classList.toggle('sidebar-collapsed');return;}notice.textContent='静态预览：操作效果将在实际界面中体验';}},true);doc.querySelectorAll('iframe').forEach(frame=>{frame.onload=()=>bind(frame.contentDocument);if(frame.contentDocument)bind(frame.contentDocument);});}
stage.onload=()=>bind(stage.contentDocument);show(0);</script></html>'''.replace('PAYLOAD', payload)
    (output / 'index.html').write_text(document)
    return {'pages': len(views), 'errors': errors, 'output': str(output / 'index.html')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/frontend-sidebar-refresh/preview')
    print(json.dumps(asyncio.run(export(parser.parse_args().output)), ensure_ascii=False))
