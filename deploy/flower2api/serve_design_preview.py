"""运行真实构建的本地交互预览，全部管理接口使用合成数据。"""
import argparse
import atexit
import re
import signal
import sys
import asyncio
import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from verify_capture_workspace_design import CaptureFixture
from verify_environment_ui import BASE, ROOT


class PreviewWorkspaceFixture(CaptureFixture):
    """展示真实本地冻结成果，所有配置与目录修改限合成夹具。"""
    def __init__(self):
        """准备可编辑的示例CPU与代理同步状态。@return 无。"""
        super().__init__()
        self.task_accounts[0]['warmup_engine'] = 'projects'
        self.rows[0]['isolation_version'] = 2
        self.preview_cpu = {'generation': self.rows[0]['generation'], 'revision': 'preview-cpu-1',
            'host_cpus': 8, 'cpus': {'cli': 2, 'sender': 1, 'network': .5}}
        self.preview_sync = {}

    async def route(self,route):
        """本地配置保存仍走隔离SQLite；执行动作返回明确预览说明。@param route 请求。@return 无。"""
        path=urlsplit(route.request.url).path
        settings=re.fullmatch(r'/runtime/api/accounts/(\d+)/cli-settings',path)
        if settings:
            account=next((item for item in self.task_accounts if item['id']==int(settings[1])),None)
            if not account:return await self.respond(route,{'detail':'示例账号不存在'},404)
            if route.request.method=='PUT':
                body=route.request.post_data_json or {}
                account.update({key:value for key,value in body.items() if key in (
                    'display_name','claude_code_version','projects_capture_enabled','warmup_capture_enabled')})
            version=account.get('claude_code_version')
            return await self.respond(route,{'account_id':account['id'],
                'display_name':account.get('display_name') or account['name'],
                'claude_code_version':version,'effective_claude_code_version':version or '2.1.293',
                'claude_code_version_source':'account' if version else 'global',
                'projects_capture_enabled':bool(account.get('projects_capture_enabled')),
                'warmup_capture_enabled':bool(account.get('warmup_capture_enabled'))})
        if path.endswith('/cpu-resources'):
            if route.request.method == 'POST':
                body = route.request.post_data_json or {}
                if body.get('expected_generation') != self.preview_cpu['generation'] or body.get('expected_revision') != self.preview_cpu['revision']:
                    return await self.respond(route, {'detail': '示例资源配置已变化，请重新读取'}, 409)
                self.preview_cpu.update(cpus=body['cpus'], revision=self.preview_cpu['revision'] + 'x')
            return await self.respond(route, self.preview_cpu)
        if path == '/admin/proxies' and route.request.method == 'GET':
            for row in self.proxies:
                if row.get('sync_pending') and time.monotonic() >= self.preview_sync.get(row['id'], float('inf')):
                    row['sync_pending'] = False
        match=re.fullmatch(r'/runtime/api/projects/agents/(\d+)(?:/(schedule|start|pause|stop))?',path)
        if match and route.request.method in ('PUT','POST'):
            account=int(match[1]);action=match[2];body=route.request.post_data_json or {};service=self.fixture.service
            try:
                if action is None:return await self.respond(route,service.configure(account,body['project_keys'],body.get('instructions',''),body.get('budget_sec',3600)))
                if action=='schedule':return await self.respond(route,service.configure_schedule(account,body['enabled'],body.get('interval_minutes',60),body.get('interval_max_minutes')))
                return await self.respond(route,{'detail':'本地预览展示配置、交付与观测；执行控制请在实际运行服务中操作。'},409)
            except (ValueError,KeyError):return await self.respond(route,{'detail':'请检查本地预览配置'},400)
        if path=='/runtime/api/accounts/login/start':return await self.respond(route,{'detail':'本地预览展示授权配置；连接实际运行服务后可启动登录终端。'},409)
        result = await super().route(route)
        if path.startswith('/admin/proxies/') and route.request.method == 'PUT':
            self.preview_sync[path.rsplit('/', 1)[1]] = time.monotonic() + 2
        return result


class PreviewRoute:
    """将本地HTTP请求适配到现有合成夹具。"""

    def __init__(self, handler):
        """准备请求上下文。@param handler HTTP处理器。@return 无。"""
        self.handler = handler
        length = int(handler.headers.get('Content-Length', '0'))
        if length > 1024 * 1024:
            raise ValueError('预览请求过大')
        body = handler.rfile.read(length).decode() if length else None
        self.request = SimpleNamespace(url=BASE+handler.path, method=handler.command, post_data=body, post_data_json=json.loads(body) if body else None)

    async def fulfill(self, status=200, content_type='text/plain', body='', path=None):
        """回传夹具内容，HTML附加清晰的本地示例标识。@param status 状态码。@param content_type 类型。@param body 响应体。@param path 静态资源路径。@return 无。"""
        payload = Path(path).read_bytes() if path else body.encode() if isinstance(body, str) else body
        if content_type == 'text/html' and '/runtime/' not in self.handler.path:
            injection = '''<script>localStorage.setItem('claude-code-gateway_auth','synthetic-only')</script><style>body{padding-top:24px}.console-sidebar{top:24px;height:calc(100dvh - 24px)}.console-embedded .console-workspace{height:calc(100dvh - 24px)}.design-preview-note{position:fixed;inset:0 0 auto;height:24px;z-index:45;background:#ece8f3;color:#74618e;font:11px/24px system-ui;padding:0 16px;pointer-events:none}</style>'''
            payload = payload.replace(b'</head>', injection.encode()+b'</head>').replace(b'<body>', '<body><div class="design-preview-note">本地交互预览 · 示例数据</div>'.encode())
        self.handler.send_response(status)
        self.handler.send_header('Content-Type', content_type)
        self.handler.send_header('Content-Length', str(len(payload)))
        self.handler.send_header('Cache-Control', 'no-store')
        self.handler.end_headers()
        self.handler.wfile.write(payload)


class PreviewHandler(BaseHTTPRequestHandler):
    """只在回环地址提供合成数据，不连接真实模型与管理服务。"""
    fixture = PreviewWorkspaceFixture()
    lock = threading.Lock()
    # 服务启动时冻结已验证构建，避免迭代构建删除旧chunk导致当前预览丢入口。
    bundle = ROOT / 'apps/web/dist'
    archived_assets = ROOT / '.deploy/frontend-sidebar-refresh/preview-assets'
    assets = {'/assets/' + str(path.relative_to(ROOT / '.deploy/frontend-sidebar-refresh/preview-assets')): path.read_bytes() for path in archived_assets.rglob('*') if path.is_file()}
    assets.update({'/' + str(path.relative_to(ROOT / 'apps/web/dist')): path.read_bytes() for path in bundle.rglob('*') if path.is_file()})
    comparison = ROOT / '.deploy/frontend-sidebar-refresh/exact'
    assets.update({'/design-review/' + path.name: path.read_bytes() for path in (ROOT / '.deploy/frontend-sidebar-refresh/exact').iterdir() if path.suffix in ('.html', '.png', '.json')})
    pages = {'/', '/login', '/proxies', '/requests', '/tokens', '/settings', '/updates', '/environments', '/tasks'}

    def handle_preview(self):
        """执行当前夹具请求。@return 无。"""
        try:
            path=urlsplit(self.path).path
            if self.command=='GET' and (path in ('/runtime/api/projects/stream','/runtime/api/accounts/warmup/pi/stream','/runtime/api/runs-stream')):
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-store');self.end_headers()
                # 预览保持真实长连接生命周期，避免合成回执关闭连接后出现多余断线横幅。
                while True:
                    self.wfile.write(': 本地预览心跳\n\n'.encode());self.wfile.flush();time.sleep(15)
            with self.lock:
                route = PreviewRoute(self)
                path = urlsplit(self.path).path
                if self.command == 'GET' and path in self.pages:
                    asyncio.run(route.fulfill(content_type='text/html', body=self.assets['/index.html']))
                elif self.command == 'GET' and path in self.assets:
                    asyncio.run(route.fulfill(content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream', body=self.assets[path]))
                else:
                    asyncio.run(self.fixture.route(route))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send_error(500, 'Local preview request failed')

    def do_GET(self):
        """读取预览页面或合成数据。@return 无。"""
        self.handle_preview()

    def do_POST(self):
        """执行本地示例动作。@return 无。"""
        self.handle_preview()

    def do_PUT(self):
        """保存本地示例配置。@return 无。"""
        self.handle_preview()

    def do_DELETE(self):
        """删除本地示例记录。@return 无。"""
        self.handle_preview()

    def log_message(self, format, *args):
        """省略包含查询内容的访问日志。@param format 格式。@param args 参数。@return 无。"""
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=4188)
    options = parser.parse_args()
    atexit.register(PreviewHandler.fixture.fixture.doCleanups)
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
    server = ThreadingHTTPServer(('127.0.0.1', options.port), PreviewHandler)
    print(f'本地交互预览：http://localhost:{options.port}/', flush=True)
    server.serve_forever()
