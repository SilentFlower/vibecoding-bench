"""隔离验证历史迁移、旧程序读写及真实UI/API/SQLite诊断链路。"""
import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from source_layout import source_path
from verify_management_ui import BASE, ManagementFixture

ROOT=Path(__file__).resolve().parents[2] if len(Path(__file__).resolve().parents)>2 else Path('/opt')
SECRET='synthetic-private-request-records-proof'
QUERY_CODE="""import json,sys
from urllib.request import Request,urlopen
from urllib.error import HTTPError
path,method,body,headers=json.loads(sys.argv[1])
try:r=urlopen(Request('http://127.0.0.1:5674'+path,data=body.encode() if body is not None else None,headers=headers,method=method),timeout=10)
except HTTPError as error:r=error
print(json.dumps({'status':r.code,'headers':dict(r.headers),'body':r.read().decode()}))
"""


def inside():
    """启动受限管理读取桥与真实网关，网络仅限容器回环。@return 无。"""
    from agy_runtime.capture import read_snapshot

    class Binding(BaseHTTPRequestHandler):
        """模拟受信映射边界，快照由产品读取器校验。"""

        def log_message(self,*args):
            """屏蔽合成鉴权日志。@param args 日志参数。@return 无。"""

        def do_GET(self):
            """按固定账号目录返回实际脱敏快照。@return 无。"""
            parsed=urlsplit(self.path);parts=parsed.path.split('/')
            if self.headers.get('authorization')!='Bearer '+SECRET:
                self.send_error(401);return
            if len(parts)!=6 or parts[1:4]!=['internal','v3','native-captures'] or parse_qs(parsed.query)!={'platform':['antigravity']}:
                self.send_error(404);return
            try:value=read_snapshot(Path('/state'),int(parts[4]),parts[5])
            except FileNotFoundError:self.send_error(404);return
            except TimeoutError:self.send_error(410);return
            except (ValueError,OSError):self.send_error(503);return
            body=json.dumps(value).encode();self.send_response(200);self.send_header('content-type','application/json')
            self.send_header('content-length',str(len(body)));self.end_headers();self.wfile.write(body)

    server=ThreadingHTTPServer(('127.0.0.1',8765),Binding)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    command=['/opt/verify-lib/ld-linux-x86-64.so.2','--library-path','/opt/verify-lib','/opt/gateway']
    with open('/state/gateway-verification.log','ab') as output:
        subprocess.run(command,stdout=output,stderr=subprocess.STDOUT,check=True)


def request(container,path,method='GET',body=None,headers=None):
    """通过容器内真实HTTP调用网关，保持断网隔离。@param container 独立容器。@param path API路径。@param method 方法。@param body 正文。@param headers 实际头。@return 响应。"""
    result=container.exec_run(['python3','-c',QUERY_CODE,json.dumps([path,method,body,headers or {'x-api-key':'synthetic-admin','content-type':'application/json'}])])
    assert result.exit_code==0,result.output.decode()
    return json.loads(result.output)


def launch(client,image,binary,folder):
    """创建固定产物、只读根及断网管理验证容器。@param client Docker客户端。@param image 固定镜像。@param binary 真实网关。@param folder 隔离数据。@return 就绪容器。"""
    volumes={str(binary):{'bind':'/opt/gateway','mode':'ro'},str(Path(__file__).resolve()):{'bind':'/opt/probe.py','mode':'ro'},
        str(ROOT/'deploy/flower2api'):{'bind':'/opt/deploy','mode':'ro'},str(ROOT/'services/orchestrator'):{'bind':'/opt/orchestrator','mode':'ro'},str(folder):{'bind':'/state','mode':'rw'}}
    for name in ['ld-linux-x86-64.so.2','libc.so.6','libm.so.6','libgcc_s.so.1']:
        volumes[str((Path('/lib/x86_64-linux-gnu')/name).resolve())]={'bind':'/opt/verify-lib/'+name,'mode':'ro'}
    container=client.containers.run(image,['/opt/probe.py','--inside'],entrypoint=['python3'],detach=True,network_mode='none',read_only=True,
        cap_drop=['ALL'],security_opt=['no-new-privileges:true'],mem_limit='768m',pids_limit=128,tmpfs={'/tmp':'rw,nosuid,nodev,size=64m'},volumes=volumes,
        environment={'PYTHONPATH':'/opt/deploy:/opt/orchestrator','DATABASE_DRIVER':'sqlite','DATABASE_DSN':'/state/gateway.sqlite',
            'ADMIN_PASSWORD':'synthetic-admin','V3_RUNTIME_URL':'http://127.0.0.1:8765','V3_INTERNAL_TOKEN':SECRET,'LOG_LEVEL':'warn','TOKIO_WORKER_THREADS':'2'},
        labels={'vibebench.test-task':'agy-request-records'})
    try:
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            container.reload()
            assert container.status=='running',container.logs().decode()
            try:
                if request(container,'/api/hello')['status']==200:return container
            except (AssertionError,ValueError):pass
            time.sleep(.1)
        raise AssertionError('隔离网关启动未就绪')
    except BaseException:
        container.remove(force=True);raise


def migration(binary,database,action,target):
    """执行真实离线维护子命令。@param binary 真实产物。@param database 隔离库。@param action 操作。@param target 目标版本。@return 迁移计划。"""
    result=subprocess.run([str(binary),'database-migrations',action,'--operation-id',str(uuid.uuid4()),'--target-version',str(target)],
        env={**os.environ,'DATABASE_DRIVER':'sqlite','DATABASE_DSN':str(database)},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


async def browser_check(container,folder,report):
    """真实前端经真实管理HTTP核对SQLite事实与有界快照。@param container 隔离网关。@param folder 证据目录。@param report 聚合报告。@return 无。"""
    from playwright.async_api import async_playwright,expect

    class Fixture(ManagementFixture):
        """静态资源复用既有探针，诊断与账号直接调用真实API。"""

        async def route(self,route):
            """转发实际浏览器鉴权、筛选与详情请求。@param route 浏览器请求。@return 无。"""
            parsed=urlsplit(route.request.url)
            if parsed.path.startswith(('/admin/request-diagnostics','/admin/accounts','/admin/settings')):
                headers={key:value for key,value in route.request.headers.items() if key in ['authorization','x-api-key','content-type']}
                result=await asyncio.to_thread(request,container,parsed.path+('?' + parsed.query if parsed.query else ''),route.request.method,route.request.post_data,headers)
                return await route.fulfill(status=result['status'],headers={'content-type':'application/json',**({'cache-control':'no-store'} if '/captures/' in parsed.path else {})},body=result['body'])
            return await super().route(route)

    page_data=json.loads(request(container,'/admin/request-diagnostics?platform=antigravity&page_size=200')['body'])
    with sqlite3.connect(folder/'gateway.sqlite') as connection:
        count=connection.execute("SELECT COUNT(*) FROM request_diagnostics WHERE platform='antigravity'").fetchone()[0]
        assert page_data['total']==count and count>=19
    chosen=None
    for row in page_data['items']:
        detail=json.loads(request(container,'/admin/request-diagnostics/'+row['request_id'])['body'])
        if any(a.get('capture_status')=='saved' and a.get('context',{}).get('system_prompt_policy',{}).get('changed') for a in detail['attempts']):
            chosen=detail;break
    assert chosen,'未找到实际策略转换快照'
    root=chosen['request'];attempt=chosen['attempts'][0]
    report['diagnostic_requests']=count
    async with async_playwright() as playwright:
        browser=await playwright.chromium.launch()
        context=await browser.new_context(viewport={'width':1280,'height':1000})
        fixture=Fixture(source_path(ROOT,'cc2api/web/dist'));await context.route('**/*',fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-admin')")
        page=await context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(BASE+'/requests')
        await expect(page.locator('tbody')).to_contain_text('Antigravity')
        await page.get_by_role('button',name='筛选',exact=True).click()
        await page.get_by_role('combobox',name='账号平台',exact=True).click()
        await page.get_by_role('option',name='Antigravity',exact=True).click()
        await page.get_by_label('请求模型',exact=True).fill(root['context']['requested_model'])
        await page.get_by_role('button',name='查询',exact=True).click()
        await expect(page.locator('tbody')).to_contain_text('Antigravity')
        correlation=page.get_by_label('请求关联 ID',exact=True)
        await correlation.fill(root['request_id']);await page.get_by_role('button',name='查询',exact=True).click()
        await expect(page.locator('tbody tr')).to_have_count(1)
        await page.get_by_role('button',name='详情',exact=True).click()
        await expect(page.get_by_role('dialog')).to_contain_text('Antigravity')
        await page.get_by_role('tab',name='性能',exact=True).click()
        await expect(page.locator('[data-gemini-usage]')).to_contain_text('Gemini usageMetadata')
        await expect(page.locator('[data-gemini-usage]')).to_contain_text(str(attempt['context']['usage']['total_tokens']))
        await page.get_by_role('tab',name='原始数据',exact=True).click()
        await page.get_by_role('button',name='读取阶段证据',exact=True).click()
        await expect(page.locator('.request-stages')).to_contain_text('native_cascade_prompt_sections')
        await expect(page.locator('.request-stages')).to_contain_text('decoded_gemini_input')
        for width in [1280,390]:
            await page.set_viewport_size({'width':width,'height':1000})
            await expect(page.get_by_role('dialog')).to_have_css('width',f'{min(1020,width-28)}px')
            bounds=await page.get_by_role('dialog').bounding_box()
            assert bounds and bounds['x']>=0 and bounds['x']+bounds['width']<=width, bounds
            assert await page.locator('html').evaluate('node=>node.scrollWidth<=innerWidth')
            await page.screenshot(path=str(folder/f'agy-records-{width}.png'))
        assert not errors,errors
        await browser.close()
    capture=request(container,f"/admin/request-diagnostics/{root['request_id']}/captures/{attempt['attempt_id']}")
    assert capture['status']==200 and capture['headers']['cache-control']=='no-store'
    assert json.loads(capture['body'])['snapshot']['stage']=='agy_prepared'
    report['ui_api_db_passed']=True


def main():
    """执行历史升级、真实旧程序写入及浏览器验证。@return 无。"""
    parser=argparse.ArgumentParser();parser.add_argument('--inside',action='store_true');parser.add_argument('--image');parser.add_argument('--baseline',type=Path)
    args=parser.parse_args()
    if args.inside:inside();return
    assert args.image and args.baseline
    import docker
    current=ROOT/'services/gateway/target/debug/claude-code-gateway';baseline=args.baseline.resolve()
    report={'real_model_submissions':0,'network':'none','scenarios':['5→6及重复迁移','旧程序compatible_newer读写','持久平台/协议/模型筛选',
        '列表API与SQLite计数一致','真实请求关联查询','源用量详情','解码与原生提交阶段来源','390px弹窗边界','管理采集no-store']}
    output=ROOT/'.trellis/.runtime/agy-records-full-chain';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='agy-records-') as temporary:
        folder=Path(temporary);database=folder/'upgrade.sqlite'
        assert migration(baseline,database,'apply',5)['current_version']==5
        with sqlite3.connect(database) as connection:connection.execute("INSERT INTO settings VALUES('synthetic_compatibility_marker','before')")
        assert migration(current,database,'apply',6)['current_version']==6
        assert migration(current,database,'apply',6)['current_version']==6
        assert migration(baseline,database,'plan',5)['state']=='compatible_newer'
        with sqlite3.connect(database) as connection:assert connection.execute("SELECT value FROM settings WHERE key='synthetic_compatibility_marker'").fetchone()[0]=='before'
        report['migration_5_to_6_repeat_old_plan']=True
        source=ROOT/'.trellis/.runtime/agy-homoglyph-loopback-private'
        with sqlite3.connect(source/'gateway.sqlite') as original,sqlite3.connect(folder/'gateway.sqlite') as target:original.backup(target)
        shutil.copytree(source/'capture/api/agy-prepared',folder/'flows/api/agy-prepared')
        client=docker.from_env(timeout=20);container=None
        try:
            container=launch(client,args.image,baseline,folder)
            assert request(container,'/admin/request-diagnostics')['status']==200
            assert request(container,'/admin/settings','PUT',json.dumps({'request_diagnostics_log_mode':'debug'}))['status']==200
            response=request(container,'/v1/messages','POST','{}',{'x-api-key':'synthetic-key','content-type':'application/json'})
            assert response['status'] in [400,403,404,422,503],response
            time.sleep(.2);container.remove(force=True);container=None
            container=launch(client,args.image,current,folder)
            unknown=json.loads(request(container,'/admin/request-diagnostics?platform=history_unknown')['body'])
            assert unknown['total']>=1
            report['old_program_read_write_preserved']=True
            with sqlite3.connect(folder/'gateway.sqlite') as original,sqlite3.connect(output/'gateway.sqlite') as target:original.backup(target)
            asyncio.run(browser_check(container,folder,report))
            for path in folder.glob('agy-records-*.png'):shutil.copy2(path,output/path.name)
        finally:
            if container:container.remove(force=True)
        report['isolated_data_removed']=True
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
