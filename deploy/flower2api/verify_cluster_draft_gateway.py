"""为隔离草稿验证接入真实Rust管理桥和原编排HTTP/WS服务。"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
from uvicorn import Config, Server
from websockets.sync.client import connect

import main


class DraftGatewayClient:
    """提供原测试客户端形状，所有管理请求经过实际Rust统一入口。

    :param testcase: 本次隔离部署的清理所有者。
    :param runtime: 随机部署的中央运行时。
    :param binary: 已构建的宿主Rust网关。
    """

    def __init__(self, testcase, runtime, binary: Path) -> None:
        """仅监听回环地址并使用独立SQLite及随机管理口令。

        :param testcase: 隔离验证与清理登记器。
        :param runtime: 原随机部署。
        :param binary: 本次Rust执行文件。
        :return: None。
        """
        if not runtime.deployment.startswith('cluster-test-') or os.environ.get('CLUSTER_DOCKER_TEST')!='1':
            raise ValueError('真实管理桥仅用于随机隔离验证')
        listener=socket.socket()
        listener.bind(('127.0.0.1',0))
        runtime_base='http://127.0.0.1:'+str(listener.getsockname()[1])
        self.last_runtime_error=None
        async def application(scope,receive,send):
            """为本次合成启动保留Root失败分类，成功响应和授权码内容不采集。:return: None。"""
            status=200
            async def observe(message):
                """只收集原启动失败的有限回执。:param message: ASGI消息。:return: None。"""
                nonlocal status
                if message['type']=='http.response.start':
                    status=message['status']
                if (scope.get('path')=='/api/accounts/login/start' and status>=400
                        and message['type']=='http.response.body' and message.get('body')):
                    self.last_runtime_error={'status':status,'body':message.get('body',b'').decode(errors='replace')[:512]}
                await send(message)
            await main.app(scope,receive,observe)
        server=Server(Config(application,log_level='error',lifespan='off'))
        thread=threading.Thread(target=lambda:asyncio.run(server.serve(sockets=[listener])),daemon=True)
        thread.start()
        def stop_server():
            """先退出原HTTP线程，再关闭本次监听。:return: None。"""
            server.should_exit=True
            thread.join(timeout=5)
            listener.close()
        testcase.addCleanup(stop_server)
        deadline=time.monotonic()+10
        while not server.started:
            testcase.assertLess(time.monotonic(),deadline,'原草稿编排HTTP服务启动超时')
            time.sleep(.01)
        probe=socket.socket()
        probe.bind(('127.0.0.1',0))
        port=probe.getsockname()[1]
        probe.close()
        root=runtime.data/'draft-management-gateway'
        root.mkdir(mode=0o700)
        password=os.urandom(32).hex()
        log=(root/'gateway.log').open('wb')
        testcase.addCleanup(log.close)
        process=subprocess.Popen([str(binary.resolve())],cwd=root,stdout=log,stderr=subprocess.STDOUT,
            env={'PATH':os.environ.get('PATH',''),'SERVER_HOST':'127.0.0.1','SERVER_PORT':str(port),
                'DATABASE_DRIVER':'sqlite','DATABASE_DSN':str(root/'gateway.sqlite'),'ADMIN_PASSWORD':password,
                'LOG_LEVEL':'error','V3_DEPLOYMENT_ID':runtime.deployment,'V3_RELEASE':runtime.release_id,
                'V3_RUNTIME_URL':runtime_base,'V3_INTERNAL_TOKEN':os.environ['V3_INTERNAL_TOKEN']})
        def stop_gateway():
            """收口本次宿主网关进程。:return: None。"""
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        testcase.addCleanup(stop_gateway)
        self.base='http://127.0.0.1:'+str(port)
        self.http=httpx.Client(base_url=self.base,trust_env=False,timeout=120)
        self.cookies=self.http.cookies
        testcase.addCleanup(self.close)
        deadline=time.monotonic()+15
        while True:
            try:
                if self.http.get('/admin/accounts',headers={'authorization':'Bearer '+password}).status_code==200:
                    break
            except httpx.TransportError:
                pass
            testcase.assertIsNone(process.poll(),'实际Rust管理桥提前退出')
            testcase.assertLess(time.monotonic(),deadline,'实际Rust管理桥启动超时')
            time.sleep(.05)
        admin={'authorization':'Bearer '+password}
        created=self.http.post('/admin/proxies',headers=admin,json={'name':'合成节点登录代理',
            'protocol':'socks5','host':'cluster-test-proxy','port':1080,
            'username':'synthetic-directory-user','password':'synthetic-directory-password'})
        testcase.assertEqual(200,created.status_code,created.text)
        listing=self.http.get('/admin/proxies',headers=admin,params={'usage':'false'})
        testcase.assertEqual(200,listing.status_code,listing.text)
        proxy=next(item for item in listing.json()['data'] if item['id']==created.json()['id'])
        self.proxy_selection={'proxy_id':proxy['id'],'proxy_revision':proxy['revision']}

    def get(self, path: str, **kwargs):
        """读取统一管理路径。:param path: 原浏览器路径。:param kwargs: 原请求参数。:return: HTTP响应。"""
        return self.http.get('/runtime'+path,**kwargs)

    def post(self, path: str, **kwargs):
        """提交统一管理路径。:param path: 原浏览器路径。:param kwargs: 原请求参数。:return: HTTP响应。"""
        return self.http.post('/runtime'+path,**kwargs)

    def delete(self, path: str, **kwargs):
        """删除统一管理路径。:param path: 原浏览器路径。:param kwargs: 原请求参数。:return: HTTP响应。"""
        return self.http.delete('/runtime'+path,**kwargs)

    @contextmanager
    def websocket_connect(self, path: str):
        """沿原会话Cookie及票据连接实际Rust WS转发。

        :param path: 原精确WS路径与单次票据。
        :return: 与原测试客户端等价的有界连接。
        """
        cookie=self.http.build_request('GET','/runtime'+path).headers.get('cookie','')
        with connect(self.base.replace('http:','ws:',1)+'/runtime'+path,
                additional_headers={'cookie':cookie},proxy=None,compression=None,open_timeout=15,close_timeout=2) as socket_client:
            class Socket:
                """将真实WS映射为原测试消息形状。"""

                def send_json(self, value):
                    """发送JSON控制帧。:param value: 原控制消息。:return: None。"""
                    socket_client.send(json.dumps(value))

                def receive(self):
                    """有界等待原消息。:return: 文本或二进制消息。"""
                    value=socket_client.recv(timeout=20)
                    return {'type':'websocket.send','text' if isinstance(value,str) else 'bytes':value}
            yield Socket()

    def close(self) -> None:
        """关闭本次HTTP连接池。:return: None。"""
        self.http.close()
