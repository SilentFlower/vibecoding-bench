"""回环验证真实Rust管理桥、Python选线函数与两份SQLite；运行环境使用本地替身。"""
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'services/orchestrator'))
from task_proxy import TaskProxyActivity, ProxySelectionConflict, read_account, snapshot, save_selection
from proxy_references import collect_references

SECRET = 'synthetic-internal-service-token-for-test'
ADMIN = 'synthetic-admin-for-proxy-test'


def request(base, path, method='GET', body=None, headers=None):
    """只访问指定回环服务。@param base 回环URL。@param path 路径。@param method 方法。@param body JSON。@param headers 合成认证。@return 状态及JSON。"""
    value=Request(base+path,data=None if body is None else json.dumps(body).encode(),method=method,
        headers={'Content-Type':'application/json',**(headers or {})})
    try:
        with build_opener(ProxyHandler({})).open(value,timeout=65) as response:return response.status,json.load(response)
    except HTTPError as error:
        raw=error.read()
        try:return error.code,json.loads(raw)
        except ValueError:return error.code,{}


def main():
    """验证真实请求载荷、公开投影、单列写入及冲突恢复。@return None。"""
    with tempfile.TemporaryDirectory(prefix='flower-task-proxy-') as folder:
        folder=Path(folder);db=folder/'tasks.sqlite'
        def database():
            connection=sqlite3.connect(db);connection.row_factory=sqlite3.Row;return connection
        with database() as connection:
            connection.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT,enabled INTEGER,upstream_proxy_scheme TEXT,upstream_socks5_host TEXT,upstream_socks5_port INTEGER,upstream_socks5_user TEXT,upstream_socks5_pass TEXT,cc2api_account_id INTEGER,deleted_at TEXT)')
            connection.execute("INSERT INTO accounts VALUES(1,'独立任务',1,'http','old.invalid',8080,'fixture-user','fixture-secret',NULL,NULL)")
            connection.execute("INSERT INTO accounts VALUES(2,'关联任务',1,'http','old.invalid',8080,'fixture-user','fixture-secret',1,NULL)")
            connection.execute('CREATE TABLE account_environments(environment_id TEXT,account_id INTEGER,name TEXT)')
            connection.execute("INSERT INTO account_environments VALUES('independent',1,'独立任务')")
        owner,profile,environment,write_lock=threading.Lock(),threading.Lock(),threading.RLock(),threading.Lock()
        runtime=Mock(lock=threading.Lock());runtime.environment_lock.return_value=environment
        runtime.environment_jobs.return_value=[];runtime._running_sender_active.return_value=False
        activity=TaskProxyActivity();received=[]
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
        base=f'http://127.0.0.1:{port}';private_headers={'Authorization':'Bearer '+ADMIN,'x-v3-service-token':SECRET}
        def gateway(method,path,body=None):
            status,value=request(base,path,method,body,private_headers)
            if status!=200:raise ConnectionError('合成管理调用失败')
            return value
        class Handler(BaseHTTPRequestHandler):
            """运行时替身只替代容器活动，保存使用产品函数。"""
            def log_message(self,*args):
                """保持测试输出只含公开汇总。@param args 标准日志参数。@return None。"""
            def reply(self,status,value):
                """发送JSON。@param status 状态。@param value 数据。@return None。"""
                raw=json.dumps(value).encode()
                try:
                    self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    # 故障场景故意关闭等待者，事务结果仍由两库回读核对。
                    pass
            def dispatch(self):
                """验证内部证明后分派确定的测试路由。@return None。"""
                if self.headers.get('Authorization')!='Bearer '+SECRET:return self.reply(401,{})
                if self.path=='/internal/v3/session/verify':return self.reply(200 if self.headers.get('Cookie')=='fixture-session=yes' else 401,{'ok':True})
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or '{}')
                if self.path=='/internal/v3/proxy-references':
                    result=activity.references(lambda:collect_references(database,None))
                    return self.reply(200,result)
                if self.path=='/internal/v3/quiesce/1':
                    lease=gateway('GET','/admin/runtime/accounts/1/lease')['lease']
                    assert lease['owner']==body['owner'] and lease['generation']==body['generation']
                    return self.reply(200,{'ok':True})
                if self.path=='/api/accounts':
                    with database() as connection:rows=[dict(row) for row in connection.execute('SELECT * FROM accounts')]
                    return self.reply(200,rows)
                match=re.fullmatch(r'/api/accounts/(1|2)/proxy-selection',self.path)
                if not match:return self.reply(404,{})
                identity=int(match[1])
                try:
                    if self.command=='GET':value=snapshot(read_account(database,identity),gateway,SECRET)
                    else:
                        received.append(dict(body));operation=body['operation_id']
                        def authorize(account):
                            result=gateway('POST',f'/admin/runtime/task-proxy-operations/{operation}/claim',
                                dict(account_id=identity,gateway_account_id=account.get('cc2api_account_id'),selection_revision=body['selection_revision'],connection=body['connection']))
                            assert result['claimed'] is True
                            return operation
                        with activity.track(operation):
                            value=save_selection(identity,{key:value for key,value in body.items() if key!='operation_id'},database,write_lock,runtime,lambda _:owner,lambda _:profile,lambda _:False,gateway,SECRET,authorize=authorize)
                    return self.reply(200,value)
                except ProxySelectionConflict as error:return self.reply(409,{'detail':{'code':error.code}})
                except ConnectionError:return self.reply(409,{'detail':'内部操作未完成'})
            do_GET=dispatch
            do_PUT=dispatch
            do_POST=dispatch
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        binary=ROOT/'services/gateway/target/debug/claude-code-gateway'
        log=(folder/'gateway.log').open('w')
        process=subprocess.Popen([str(binary)],cwd=folder,stdout=log,stderr=subprocess.STDOUT,env={
            'PATH':os.environ['PATH'],'SERVER_HOST':'127.0.0.1','SERVER_PORT':str(port),'DATABASE_DRIVER':'sqlite',
            'DATABASE_DSN':str(folder/'gateway.sqlite'),'ADMIN_PASSWORD':ADMIN,'RUST_LOG':'warn',
            'V3_RUNTIME_URL':f'http://127.0.0.1:{server.server_port}','V3_INTERNAL_TOKEN':SECRET})
        headers={'Cookie':'fixture-session=yes','Origin':base};admin={'Authorization':'Bearer '+ADMIN}
        try:
            for _ in range(150):
                try:
                    if request(base,'/admin/dashboard',headers=admin)[0]==200:break
                except OSError:pass
                if process.poll() is not None:raise RuntimeError('隔离网关启动失败')
                time.sleep(.1)
            else:raise RuntimeError('隔离网关启动超时')
            with sqlite3.connect(folder/'gateway.sqlite') as connection:
                connection.execute("INSERT INTO accounts(id,name,email,token,device_id,status,auth_type,proxy_url,priority,rpm_limit,auto_telemetry,auto_poll_usage) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (1,'合成网关','fixture@example.invalid','','d'*64,'disabled','setup_token','http://fixture-user:fixture-secret@old.invalid:8080',17,123,0,0))
            status,created=request(base,'/admin/proxies','POST',dict(name='新目录线路',protocol='http',host='new.invalid',port=80,username='new@user',password='private:password'),admin)
            assert status==200,(status,created)
            status,routes=request(base,'/admin/proxies?usage=false',headers=admin);assert status==200
            route=routes['data'][0]
            assert request(base,'/runtime/api/accounts/1/proxy-selection')[0]==401
            assert request(base,'/runtime/api/accounts/1/proxy-selection',headers={**headers,'Origin':'http://other.invalid'})[0]==401
            assert request(base,'/admin/runtime/accounts/1/proxy-selection','POST',{'operation_id':'a'*32,'connection':'','expected_connection':''},admin)[0]==401
            for identity in [1,2]:
                path=f'/runtime/api/accounts/{identity}/proxy-selection';status,original=request(base,path,headers=headers);assert status==200,(status,original)
                assert 'connection' not in original and 'fixture-secret' not in json.dumps(original)
                assert original['current']['kind']=='custom'
                payload=dict(selection_revision=original['selection_revision'],proxy_id=route['id'],proxy_revision=route['revision'])
                assert request(base,path,'PUT',{**payload,'connection':'http://malicious.invalid'},headers)[0]==400
                assert request(base,path,'PUT',{**payload,'proxy_revision':'stale'},headers)[0]==400
                if identity==1:
                    runtime.environment_jobs.return_value=['busy'];assert request(base,path,'PUT',payload,headers)[0]==409
                    runtime.environment_jobs.return_value=[]
                status,saved=request(base,path,'PUT',payload,headers);assert status==200,(status,saved)
                assert saved['current']['name']=='新目录线路' and saved['current']['kind']=='directory'
                assert 'private:password' not in json.dumps(saved) and 'new@user' not in json.dumps(saved)
                assert request(base,path,'PUT',{**payload,'proxy_id':None,'proxy_revision':None},headers)[0]==409
                status,direct=request(base,path,'PUT',dict(selection_revision=saved['selection_revision'],proxy_id=None),headers)
                assert status==200 and direct['current']['kind']=='direct',(status,direct)
                assert read_account(database,identity)['upstream_socks5_host']==''
            status,rows=request(base,'/runtime/api/accounts',headers=headers);assert status==200
            assert all(row['proxy_selection']['kind']=='direct' for row in rows)
            with sqlite3.connect(folder/'gateway.sqlite') as connection:
                account=connection.execute('SELECT proxy_url,priority,rpm_limit,status FROM accounts WHERE id=1').fetchone()
                assert account==('',17,123,'disabled'),account
            paused=threading.Event();entered=threading.Event()
            def slow_stop(row,remove=False):
                entered.set();assert paused.wait(60)
            runtime._stop_environment.side_effect=slow_stop
            path='/runtime/api/accounts/1/proxy-selection';_,original=request(base,path,headers=headers)
            try:
                status,_=request(base,path,'PUT',dict(selection_revision=original['selection_revision'],proxy_id=route['id'],proxy_revision=route['revision']),headers)
                assert status==503 and entered.is_set() and activity.active()
                delayed_body=dict(received[-1])
                assert request(base,'/admin/proxies/'+route['id'],'DELETE',dict(revision=route['revision']),admin)[0]==503
                assert request(base,'/admin/proxies/'+route['id'],'PUT',dict(name='改写线路',protocol='http',host='changed.invalid',port=80,revision=route['revision']),admin)[0]==503
            finally:
                paused.set()
            for _ in range(100):
                if not activity.active():break
                time.sleep(.05)
            assert not activity.active()
            status,saved=request(base,path,headers=headers);assert status==200 and saved['current']['id']==route['id']
            runtime._stop_environment.side_effect=None
            status,_=request(base,path,'PUT',dict(selection_revision=saved['selection_revision'],proxy_id=None),headers);assert status==200
            assert request(base,'/admin/proxies/'+route['id'],'DELETE',dict(revision=route['revision']),admin)[0]==200
            # 目录已释放后重新送达旧私有请求，领取已过期票据必须在停止和写入前失败。
            status,_=request(f'http://127.0.0.1:{server.server_port}','/api/accounts/1/proxy-selection','PUT',delayed_body,{'Authorization':'Bearer '+SECRET})
            assert status==409 and read_account(database,1)['upstream_socks5_host']==''
            print(json.dumps({'passed':True,'tasks':2,'verified':['原会话与来源保护','内部服务证明','私有字段隔离','目录版本冲突','独立任务忙碌拒绝','关联与独立任务真实HTTP保存','两库回读和单字段保留','45秒超时仍保护目标删改','后台提交后正常恢复','失效票据拒绝迟到写入']},ensure_ascii=False))
        finally:
            process.terminate()
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            log.close();server.shutdown();server.server_close();thread.join(timeout=3)


if __name__=='__main__':main()
