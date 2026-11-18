"""实际SSH完整开发周期与中央独立HTTPS需求方的合成纵向验证。"""
from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import compare_digest
from typing import cast
from urllib.request import HTTPSHandler, ProxyHandler, build_opener
from unittest.mock import Mock, patch

import main
from cluster_legacy_project_io import ClusterLegacyProjectIO
from cluster_run_programs import RemoteRunPrograms
from project_dialogue import ProjectDialogueClient, _NoRedirect
from project_iteration import ProjectIterationManager
from project_library import ProjectLibrary, read_document, write_document
from project_verifier import ProjectVerifier
from runtime_files import atomic_json, private_directory
from verify_cluster_scenario import _cleanup_scope, _cleanup_scenario_programs, _verify_private_review
from verify_project_scenarios import create_scenario_fixture


class _RequesterServer(ThreadingHTTPServer):
    """本地真实TLS服务，固定业务动作且不输出凭据日志。"""

    daemon_threads=True

    def __init__(self) -> None:
        """登记三个独立业务回复与有限合成认证。:return: None。"""
        self.api_key='synthetic-cluster-requester-private-key'
        self.records=[]
        self.actions=[('reply','请说明当前VALUE与现有调用方的关系。'),
            ('implement','方案确认：仅将library/example.py中的VALUE调整为2，保持原接口。'),
            ('verify','请对本次交付执行独立验收。')]
        self.record_lock=threading.Lock()
        super().__init__(('127.0.0.1',0),_RequesterHandler)


class _RequesterHandler(BaseHTTPRequestHandler):
    """按原chat/completions协议返回有限业务动作。"""

    def do_POST(self) -> None:
        """校验本次管理认证并保留公开业务上下文。:return: None。"""
        server=cast(_RequesterServer,self.server)
        length=int(self.headers.get('content-length','0'))
        if (self.path!='/v1/chat/completions' or not 0<length<1024*1024
                or not compare_digest(self.headers.get('authorization',''),'Bearer '+server.api_key)):
            self.send_error(400)
            return
        body=json.loads(self.rfile.read(length))
        context=json.loads(body['messages'][1]['content'])
        with server.record_lock:
            index=len(server.records)
            if index>=len(server.actions) or body['model']!='requester-fixture' or body['stream'] is not False:
                self.send_error(400)
                return
            server.records.append({'context':context,'peer':self.client_address[0],'tls':isinstance(self.connection,ssl.SSLSocket)})
            action,message=server.actions[index]
        response=json.dumps({'model':'requester-fixture','choices':[{'finish_reason':'stop',
            'message':{'role':'assistant','content':json.dumps({'action':action,'message':message},ensure_ascii=False)}}],
            'usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}},ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('content-type','application/json')
        self.send_header('content-length',str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self,*args) -> None:
        """关闭默认HTTP正文与认证相关日志。:param args: 原日志参数。:return: None。"""


def _requester(testcase, root: Path) -> tuple[ProjectDialogueClient,_RequesterServer]:
    private_directory(root)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost',
        '-addext','subjectAltName=IP:127.0.0.1,DNS:localhost','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem')],
        check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    server=_RequesterServer()
    server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(root/'cert.pem',root/'key.pem')
    server.socket=server_context.wrap_socket(server.socket,server_side=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    def close() -> None:
        """释放本次本地HTTPS监听及服务线程。:return: None。"""
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    testcase.addCleanup(close)
    client_context=ssl.create_default_context(cafile=root/'cert.pem')
    opener=build_opener(ProxyHandler({}),HTTPSHandler(context=client_context),_NoRedirect())
    client=ProjectDialogueClient('https://127.0.0.1:'+str(server.server_port)+'/v1',server.api_key,
        'requester-fixture',opener=opener,revision='cluster-development-fixture')
    return client,server


def verify_cluster_development(testcase, service, runtime, node, account, local, remote) -> None:
    """经原Node候选、中央真实HTTPS、原Node程序和私有评审完成一项完整开发。

    :param testcase: 当前随机部署断言。
    :param service: 原SSH服务。
    :param runtime: 原中央运行时。
    :param node: 本次合成执行节点。
    :param account: 原合成账号。
    :param local: 原Runner入口。
    :param remote: 原实际Node协调器。
    :return: None；不访问真实模型或外部供应商。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('完整开发验证仅用于本次随机隔离部署')
    testcase.addCleanup(_cleanup_scenario_programs,service,node)
    actual=runtime._row(account['name'],account['id'])
    root=Path(node['data_root'])/'environments'/actual['environment_id']
    container=service.docker(node['id']).containers.get(actual['container_id'])
    observed=container.exec_run(['python3','-c','import platform;print(platform.python_version())'])
    testcase.assertEqual(0,observed.exit_code)
    library=create_scenario_fixture(service.data/'cluster-development-fixture',observed.output.decode().strip())
    project=library.root/'projects/fixture-one'
    definition=read_document(project/'project.json')
    task=definition['scenarios'][0]['tasks'][-1]
    task.update(requires=[],development_cycle='feature',owner_materials=['disclosure/context.txt'])
    definition['schema']=3
    definition['scenarios'][0]['tasks']=[task]
    definition['scenarios'][0]['entries'][0]['task_ids']=[task['id']]
    write_document(project/'project.json',definition)
    (project/'verification/private-secret.txt').write_text('PRIVATE_CLUSTER_EVALUATION_SENTINEL')
    write_document(library.root/'catalog.json',{'schema':3,'version':'test-only-development','projects':['fixture-one']})
    library=ProjectLibrary(library.root)
    installed=Path(node['data_root'])/'project-library/releases'/library.digest
    installed.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(library.root,installed)
    requester,server=_requester(testcase,service.data/'cluster-development-requester')
    submitted=[]
    verifier=ProjectVerifier(local.client,service.data,runtime.host_data,runtime.image)
    verifier.verify_native=Mock(side_effect=AssertionError('远程完整任务误用中央Docker验收'))
    manager=ProjectIterationManager(service.data,library,service.store.database,service.store.lock,
        lambda rid,current,payload:submitted.append((rid,current,payload)),
        lambda current:{'claude_code_version':'2.1.303','claude_code_version_source':'synthetic-development',
            'claude_effort_level':'high','execution_model':'offline-fixture'},remote.identity,lambda rid:None,
        verifier,lambda rid,attempt:False,admission=main._project_admission,
        execution_control=main._project_execution_control,dialogue=requester)
    remote.project_io=ClusterLegacyProjectIO(remote,manager)
    remote.project_io.programs=RemoteRunPrograms(remote.project_io,main._oauth_owner_lock)
    manager.execution_io=remote.project_io
    remote.sessions.run_prepare=remote.project_io.prepare
    runtime.set_project_iterations(manager)
    manager.review_admission=main._project_review_admission
    token=None
    with patch.object(main,'project_iterations',manager):
        try:
            batch=manager.create_batch(account['id'],'合成SSH完整开发',['fixture-one'],policy={'concurrency':1,'active_projects':1})
            manager.transition(batch['id'],'start')
            scenario=manager._one('SELECT * FROM project_scenario_instances ORDER BY id LIMIT 1')
            task_id=manager._one('SELECT id FROM project_scenario_tasks ORDER BY id LIMIT 1')['id']
            sessions,workspaces=set(),set()
            for turn in range(3):
                parent=manager._one('SELECT * FROM project_iteration_batches WHERE id=?',(batch['id'],))
                manager.scenarios.refresh_readiness(scenario['id'])
                testcase.assertTrue(manager.scenarios._reserve_candidate(parent,account,task_id))
                rid,current,payload=submitted[-1]
                payload.update(capture_permission_mode='bypassPermissions',capture_full_http=False)
                context=manager.run_context(rid)
                sessions.add(context['session_id'])
                directory=root/'home/.synthetic-scenarios'
                directory.mkdir(exist_ok=True,mode=0o755)
                atomic_json(directory/(context['session_id']+'.json'),{'task_key':task['id'],'session':context['session_id'],
                    'development':True,'implement':turn==2,'answer':('当前源码VALUE为1。','方案是只将VALUE改为2。','已按确认方案实现并提交验收。')[turn]},0o644)
                with service.store.database() as connection:
                    connection.execute("UPDATE runs SET status='running',started_at=?,capture_permission_mode='bypassPermissions' WHERE id=?",(time.time(),rid))
                with main._oauth_owner_lock(account['name']):
                    _,token=local.start_run(rid,current,payload)
                operation=remote._row(token)
                prepared=read_document(Path(node['data_root'])/'node-runs'/actual['environment_id']/operation['operation_id']/'scenario-inputs/prepared.json')
                workspaces.add(prepared['workspace_relative'])
                testcase.assertNotIn(server.api_key,json.dumps(operation['record']['work']))
                execution=manager._one('SELECT * FROM project_task_executions WHERE run_id=?',(rid,))
                source=manager._one('SELECT * FROM project_execution_sources WHERE execution_id=?',(execution['id'],))
                deadline=time.monotonic()+150
                while remote.poll(token)['running']:
                    testcase.assertLess(time.monotonic(),deadline,'完整开发候选尚未封存')
                    manager.scenarios.capture_submission(execution,source)
                    time.sleep(.25)
                testcase.assertEqual(0,remote.poll(token)['exit_code'])
                manager.scenarios.capture_submission(execution,source)
                job=manager._one('SELECT * FROM project_evaluation_jobs WHERE source_id=?',(source['id'],))
                testcase.assertIsNotNone(job)
                candidate=service.data/job['candidate_relative']
                testcase.assertEqual('VALUE = '+('2' if turn==2 else '1')+'\n',(candidate/'library/example.py').read_text())
                with service.store.database() as connection:
                    connection.execute("UPDATE runs SET status='success',ended_at=? WHERE id=?",(time.time(),rid))
                _cleanup_scope(local,token)
                manager.execution_released(rid,0)
                source=manager._one('SELECT * FROM project_execution_sources WHERE id=?',(source['id'],))
                testcase.assertIsNotNone(source['released_at'],source['execution_error'])
                execution=manager._one('SELECT e.*,r.status AS run_status,r.error AS run_error FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE e.run_id=?',(rid,))
                manager.scenarios._settle_execution(parent,execution,source)
                manager.scenarios._mechanical_job(job['id'])
                testcase.assertEqual(turn+1,len(server.records))
                manager.scenarios._mechanical_job(job['id'])
                testcase.assertEqual(turn+1,len(server.records))
                if turn<2:
                    testcase.assertEqual('dialogue_done',manager._one('SELECT status FROM project_evaluation_jobs WHERE id=?',(job['id'],))['status'])
                    testcase.assertEqual([],manager._rows("SELECT id FROM project_task_executions WHERE role='review'"))
                    testcase.assertFalse(list((service.data/'cluster-run-programs').glob('*/record.json')))
            testcase.assertEqual(1,len(sessions))
            testcase.assertEqual(1,len(workspaces))
            testcase.assertEqual(['investigating','investigating','implementing'],[item['context']['phase'] for item in server.records])
            testcase.assertTrue(all(item['tls'] and item['peer']=='127.0.0.1' for item in server.records))
            testcase.assertNotIn('PRIVATE_CLUSTER_EVALUATION_SENTINEL',json.dumps(server.records))
            testcase.assertNotIn(server.api_key,json.dumps(server.records))
            testcase.assertEqual('review_ready',manager._one('SELECT status FROM project_evaluation_jobs WHERE id=?',(job['id'],))['status'])
            testcase.assertEqual(1,len(list((service.data/'cluster-run-programs').glob('*/report.json'))))
            _verify_private_review(testcase,service,runtime,node,account,local,remote,manager,submitted,batch,execution,source,job,root)
            testcase.assertEqual(1,manager.scenarios.task(task_id)['attempt_count'])
            summary=manager.scenarios.development.summary(task_id)
            testcase.assertEqual((3,30,12),(summary['requests'],summary['input_tokens'],summary['output_tokens']))
            testcase.assertEqual(['requester-fixture'],summary['models'])
            testcase.assertEqual([],remote.sessions.ledger.active(account['id']))
            verifier.verify_native.assert_not_called()
        finally:
            if token is not None:
                _cleanup_scope(local,token)
            manager.stop()
            remote.project_io.programs.close()
