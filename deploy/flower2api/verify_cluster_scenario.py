"""合成账号的真实SSH场景候选、原driver计时及中央完整候选封存验证。"""
from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import patch

from docker.errors import NotFound

import main
from cluster_deployment import node_container_name
from cluster_legacy_project_io import ClusterLegacyProjectIO
from cluster_run_programs import RemoteRunPrograms
from cluster_credential_refresh import RemoteCredentialRefresh
from project_iteration import ProjectIterationManager
from project_library import ProjectLibrary, digest_json, read_document, snapshot_tree, write_document
from project_verifier import ProjectVerifier
from runtime_files import atomic_json
from verify_project_scenarios import create_scenario_fixture


def _cleanup_scope(local, token: str) -> None:
    """沿原Scope严格停止，等待尚在退出的原续约线程完成收口。

    :param local: 原Runner。
    :param token: 本次唯一原Scope定位。
    :return: None；超时保留实际失败。
    """
    deadline=time.monotonic()+60
    while True:
        try:
            local.cleanup(token,token)
            return
        except (ValueError,sqlite3.OperationalError) as error:
            if (('原远程租约续接仍在收口' not in str(error) and 'database is locked' not in str(error))
                    or time.monotonic()>=deadline):
                raise
            # 只继续原停止与账本核对；不再启动CLI或重复业务输入。
            time.sleep(0.3)


def verify_cluster_scenario(testcase, service, runtime, node, account, local, remote) -> None:
    """运行原场景候选至实际释放，按开关验证节点独立程序与私有评审。

    :param testcase: 本次隔离断言。
    :param service: 原中央SSH节点服务。
    :param runtime: 原中央账号环境登记。
    :param node: 本次随机合成节点。
    :param account: 本次合成账号。
    :param local: 原Runner入口。
    :param remote: 原远程Run协调器。
    :return: None；所有源码、模型响应和程序输入来自本次固定合成夹具。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('场景验证需要本次随机隔离部署')
    testcase.addCleanup(_cleanup_scenario_programs,service,node)
    row=runtime._row(account['name'],account['id'])
    container=service.docker(node['id']).containers.get(row['container_id'])
    observed=container.exec_run(['python3','-c','import platform;print(platform.python_version())'])
    testcase.assertEqual(0,observed.exit_code)
    library=create_scenario_fixture(service.data/'cluster-scenario-fixture',observed.output.decode().strip())
    project=library.root/'projects/fixture-one'
    definition=read_document(project/'project.json')
    definition['scenarios'][0]['entries'][0]['setup']=[{'source':'disclosure/context.txt','target':'app/entry-context.txt'}]
    materials=project/'materials'
    materials.mkdir()
    (materials/'task.txt').write_text('本轮独立任务材料')
    definition['scenarios'][0]['tasks'][0]['setup']=[{'source':'materials/task.txt','target':'app/task-context.txt'}]
    if os.environ.get('CLUSTER_TEST_SCENARIO_PROGRAM')=='1':
        definition['scenarios'][0]['tasks'][0]['evaluation']['native']='verification/native-understand.json'
        specification=read_document(project/'verification/native.json')
        write_document(project/'verification/native-understand.json',{**specification,'expected':{'value':1}})
        if os.environ.get('CLUSTER_TEST_PROGRAM_RECOVERY')=='1':
            script=project/'verification/native.py'
            script.write_text('import time\ntime.sleep(5)\n'+script.read_text())
    write_document(project/'project.json',definition)
    library=ProjectLibrary(library.root)
    installed=Path(node['data_root'])/'project-library/releases'/library.digest
    installed.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(library.root,installed)
    submitted=[]
    def stop(rid):
        with service.store.database() as connection:
            connection.execute("UPDATE runs SET status='stopped',stop_requested_at=1 WHERE id=?",(rid,))
    manager=ProjectIterationManager(service.data,library,service.store.database,service.store.lock,
        lambda rid,current,task:submitted.append((rid,current,task)),
        lambda current:{'claude_code_version':'2.1.303','claude_code_version_source':'synthetic-scenario',
            'claude_effort_level':'high','execution_model':'offline-fixture'},remote.identity,stop,
        ProjectVerifier(local.client,service.data,runtime.host_data,runtime.image),lambda _rid,_attempt:False,
        admission=main._project_admission,execution_control=main._project_execution_control)
    remote.project_io=ClusterLegacyProjectIO(remote,manager)
    remote.project_io.programs=RemoteRunPrograms(remote.project_io,main._oauth_owner_lock)
    manager.execution_io=remote.project_io
    remote.sessions.run_prepare=remote.project_io.prepare
    runtime.set_project_iterations(manager)
    manager.review_admission=main._project_review_admission
    if os.environ.get('CLUSTER_TEST_REVIEW_REFRESH')=='1':
        testcase.assertIsNone(account.get('cc2api_account_id'))
        remote.credentials=RemoteCredentialRefresh(remote.sessions,None,main._oauth_owner_lock,remote.identity,lambda _:'2.1.303')
        manager.review_refresh=main._project_review_refresh
        testcase.addCleanup(remote.credentials.close)
    token=None
    with patch.object(main,'project_iterations',manager):
        try:
            batch=manager.create_batch(account['id'],'合成SSH场景候选',['fixture-one'],
                policy={'concurrency':1,'active_projects':1,'steps_per_plan':1})
            manager.transition(batch['id'],'start')
            manager.tick()
            testcase.assertEqual(1,len(submitted))
            rid,current,task=submitted[0]
            task.update(capture_permission_mode='bypassPermissions',capture_full_http=False)
            context=manager.run_context(rid)
            root=Path(node['data_root'])/'environments'/row['environment_id']
            directory=root/'home/.synthetic-scenarios'
            directory.mkdir(mode=0o755)
            atomic_json(directory/(context['session_id']+'.json'),{'task_key':context['task_key'],
                'session':context['session_id'],'quota_samples':[{'five_hour':25,'seven_day':9}]},0o644)
            with service.store.database() as connection:
                connection.execute("UPDATE runs SET status='running',started_at=?,capture_permission_mode='bypassPermissions' WHERE id=?",
                    (time.time(),rid))
            with main._oauth_owner_lock(account['name']):
                _,token=local.start_run(rid,current,task)
            deadline=time.monotonic()+150
            execution=manager._one('SELECT * FROM project_task_executions WHERE run_id=?',(rid,))
            source=manager._one('SELECT * FROM project_execution_sources WHERE execution_id=?',(execution['id'],))
            while remote.poll(token)['running']:
                testcase.assertLess(time.monotonic(),deadline,'真实场景候选尚未收口')
                manager.scenarios.capture_submission(execution,source)
                time.sleep(0.25)
            testcase.assertEqual(0,remote.poll(token)['exit_code'])
            manager.scenarios.capture_submission(execution,source)
            job=manager._one('SELECT * FROM project_evaluation_jobs WHERE source_id=?',(source['id'],))
            testcase.assertIsNotNone(job)
            candidate=service.data/job['candidate_relative']
            testcase.assertEqual('本轮独立任务材料',(candidate/'app/task-context.txt').read_text())
            testcase.assertEqual(snapshot_tree(candidate)['digest'],job['candidate_digest'])
            testcase.assertFalse((candidate/'verification').exists())
            testcase.assertIsNone(manager.scenarios.task(execution['task_id'])['accepted_checkpoint_digest'])
            operation=remote._row(token)
            prepared=read_document(root.parent.parent/'node-runs'/row['environment_id']/operation['operation_id']/'scenario-inputs/prepared.json')
            segment=manager._one('SELECT * FROM project_work_segments WHERE source_id=?',(source['id'],))
            testcase.assertEqual(prepared['clock']['boot_id'],segment['boot_id'])
            testcase.assertEqual(prepared['clock']['start_mono'],segment['start_mono'])
            testcase.assertFalse((service.data/prepared['workspace_relative']).exists())
            with service.store.database() as connection:
                connection.execute("UPDATE runs SET status='success',ended_at=? WHERE id=?",(time.time(),rid))
            _cleanup_scope(local,token)
            manager.execution_released(rid,0)
            source=manager._one('SELECT * FROM project_execution_sources WHERE id=?',(source['id'],))
            testcase.assertIsNotNone(source['released_at'])
            testcase.assertIsNone(source['execution_error'])
            segment=manager._one('SELECT * FROM project_work_segments WHERE id=?',(segment['id'],))
            testcase.assertEqual('settled',segment['status'])
            testcase.assertGreater(segment['confirmed_sec'],0)
            testcase.assertEqual('closed',remote._row(token)['phase'])
            testcase.assertEqual([],remote.sessions.ledger.active(account['id']))
            if os.environ.get('CLUSTER_TEST_SCENARIO_REVIEW')=='1':
                _verify_private_review(testcase,service,runtime,node,account,local,remote,manager,submitted,batch,execution,source,job,root)
        finally:
            if token is not None:
                _cleanup_scope(local,token)
            manager.stop()
            remote.project_io.programs.close()


def _verify_private_review(testcase, service, runtime, node, account, local, remote, manager, submitted,
                           batch, candidate, candidate_source, job, root) -> None:
    """复用原验收作业运行实际私有评审，严格释放后由中央接受原业务回答。

    :param testcase: 本次断言。
    :param service: 原中央SSH服务。
    :param runtime: 原中央环境登记。
    :param node: 本次合成节点。
    :param account: 原合成账号。
    :param local: 原Runner。
    :param remote: 原节点协调器。
    :param manager: 原中央项目管理器。
    :param submitted: 原调度提交记录。
    :param batch: 原批次公开记录。
    :param candidate: 原候选执行。
    :param candidate_source: 已严格释放的原来源。
    :param job: 原候选封存作业。
    :param root: 实际Node账号根。
    :return: None；测试响应由固定离线CLI生成。
    """
    parent=manager._one('SELECT * FROM project_iteration_batches WHERE id=?',(batch['id'],))
    execution=manager._one('SELECT e.*,r.status AS run_status,r.error AS run_error FROM project_task_executions e '
        'JOIN runs r ON r.id=e.run_id WHERE e.id=?',(candidate['id'],))
    manager.scenarios._settle_execution(parent,execution,candidate_source)
    if os.environ.get('CLUSTER_TEST_PROGRAM_RECOVERY')=='1':
        _recover_program(testcase,service,runtime,remote,manager,account,candidate_source,job)
    else:
        manager.scenarios._mechanical_job(job['id'])
    job=manager._one('SELECT * FROM project_evaluation_jobs WHERE id=?',(job['id'],))
    testcase.assertEqual('review_ready',job['status'],job['native_result_json'] or job['error'])
    if os.environ.get('CLUSTER_TEST_SCENARIO_PROGRAM')=='1':
        testcase.assertEqual([],remote.project_io.programs.active(account['id']))
        testcase.assertTrue(list((service.data/'cluster-run-programs').glob('*/report.json')))
    testcase.assertTrue(manager.scenarios._reserve_review(parent,account,job))
    rid,current,task=submitted[-1]
    task.update(capture_permission_mode='bypassPermissions',capture_full_http=False)
    if os.environ.get('CLUSTER_TEST_REVIEW_REFRESH')=='1':
        rid,current,task=_verify_review_refresh(testcase,service,runtime,node,account,local,remote,manager,submitted,parent,job,root,rid,current,task)
    context=manager.run_context(rid)
    testcase.assertEqual('review',context['role'])
    with service.store.database() as connection:
        connection.execute("UPDATE runs SET status='running',started_at=?,capture_permission_mode='bypassPermissions' WHERE id=?",
            (time.time(),rid))
    token=None
    try:
        with main._oauth_owner_lock(account['name']):
            _,token=local.start_run(rid,current,task)
        operation=remote._row(token)
        testcase.assertIsNotNone(operation['record']['work']['project']['scenario']['review'])
        if operation['record']['grant']['lease'] is not None:
            testcase.assertFalse(operation['record']['grant']['lease']['shared_cli'])
        serial=read_document(root/'runtime/project-review-serial.json')
        docker=service.docker(node['id'])
        cli=docker.containers.get(serial['container_id'])
        cli.reload()
        testcase.assertIn(cli.status,('exited','dead','created'))
        private=docker.containers.get(serial['review_container_id'])
        private.reload()
        testcase.assertEqual('running',private.status)
        testcase.assertTrue(private.attrs['HostConfig']['ReadonlyRootfs'])
        testcase.assertEqual(128,private.attrs['HostConfig']['PidsLimit'])
        testcase.assertEqual('1000:1000',private.attrs['Config']['User'])
        mounts={item['Destination']:item for item in private.attrs['Mounts']}
        private_root=Path(node['data_root'])/'project-review-private'/context['session_id']
        testcase.assertEqual(str(private_root/'home'),mounts['/home/node']['Source'])
        testcase.assertFalse(mounts['/input']['RW'])
        testcase.assertFalse(mounts['/cli']['RW'])
        testcase.assertNotIn('/home/node/projects',mounts)
        testcase.assertNotIn('/var/run/docker.sock',mounts)
        environment=runtime._row(account['name'],account['id'])
        network=docker.containers.get(environment['network_container_id'])
        sender=docker.containers.get(environment['sender_container_id'])
        for role in (network,sender):
            role.reload()
            testcase.assertEqual('running',role.status)
        testcase.assertEqual('container:'+network.id,private.attrs['HostConfig']['NetworkMode'])
        credentials=read_document(private_root/'access/.credentials.json')['claudeAiOauth']
        testcase.assertNotIn('refreshToken',credentials)
        package=read_document(manager.scenarios._package_path(job['id']))
        testcase.assertEqual(package,read_document(private_root/'input/package.json'))
        source=manager._one('SELECT x.* FROM project_execution_sources x JOIN project_task_executions e ON e.id=x.execution_id WHERE e.run_id=?',(rid,))
        execution=manager._one('SELECT * FROM project_task_executions WHERE run_id=?',(rid,))
        deadline=time.monotonic()+150
        while remote.poll(token)['running']:
            testcase.assertLess(time.monotonic(),deadline,'真实私有评审尚未收口')
            manager.scenarios._capture_review(execution,source)
            time.sleep(0.25)
        testcase.assertEqual(0,remote.poll(token)['exit_code'])
        manager.scenarios._capture_review(execution,source)
        updated=manager._one('SELECT * FROM project_evaluation_jobs WHERE id=?',(job['id'],))
        testcase.assertEqual('waiting_review_release',updated['status'])
        testcase.assertNotEqual('passed',manager.scenarios.task(execution['task_id'])['status'])
        if os.environ.get('CLUSTER_TEST_REVIEW_RECOVERY')=='1':
            _restart_review_node(testcase,service,runtime,remote,operation,private,cli)
        with service.store.database() as connection:
            connection.execute("UPDATE runs SET status='success',ended_at=? WHERE id=?",(time.time(),rid))
        _cleanup_scope(local,token)
        manager.execution_released(rid,0)
        source=manager._one('SELECT * FROM project_execution_sources WHERE id=?',(source['id'],))
        testcase.assertIsNone(source['execution_error'])
        testcase.assertIsNotNone(source['released_at'],source['execution_error'])
        execution=manager._one('SELECT e.*,r.status AS run_status,r.error AS run_error FROM project_task_executions e '
            'JOIN runs r ON r.id=e.run_id WHERE e.run_id=?',(rid,))
        manager.scenarios._settle_execution(parent,execution,source)
        testcase.assertEqual('passed',manager.scenarios.task(execution['task_id'])['status'])
        testcase.assertEqual('passed',manager._one('SELECT status FROM project_evaluation_jobs WHERE id=?',(job['id'],))['status'])
        segment=manager._one('SELECT * FROM project_work_segments WHERE source_id=?',(source['id'],))
        testcase.assertEqual('settled',segment['status'])
        testcase.assertGreater(segment['confirmed_sec'],0)
        cli.reload()
        testcase.assertEqual('running',cli.status)
        testcase.assertEqual(serial['cli_limits'],{key:cli.attrs['HostConfig'][key] for key in serial['cli_limits']})
        try:
            private.reload()
        except NotFound:
            pass
        else:
            testcase.assertIn(private.status,('exited','dead','created'))
        testcase.assertFalse((root/'runtime/project-review-serial.json').exists())
        testcase.assertEqual([],remote.sessions.ledger.active(account['id']))
    finally:
        if token is not None:
            _cleanup_scope(local,token)


def _verify_review_refresh(testcase,service,runtime,node,account,local,remote,manager,submitted,parent,job,root,rid,current,task):
    """实际私有评审401后释放原Scope，经Node真实TLS刷新并恢复同一逻辑会话。

    :param testcase: 当前隔离断言。
    :param service: 原SSH服务。
    :param runtime: 原中央运行时。
    :param node: 本次合成节点。
    :param account: 原独立账号。
    :param local: 原Runner。
    :param remote: 原节点协调器。
    :param manager: 原场景管理器。
    :param submitted: 原调度提交记录。
    :param parent: 原批次。
    :param job: 原冻结评测作业。
    :param root: 原实际Node环境。
    :param rid: 首次评审Run。
    :param current: 原账号行。
    :param task: 原冻结评审任务。
    :return: 同一评测作业的原基础设施恢复Run、账号和任务。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('评审401验证仅用于当前隔离部署')
    authority=root/'public-ca/cluster-test-ca.pem'
    shutil.copyfile(service.data.parent/'upstream/ca.crt',authority)
    authority.chmod(0o644)
    authority.parent.chmod(0o755)
    credentials=root/'home/.claude/.credentials.json'
    value=read_document(credentials)
    value['claudeAiOauth']['accessToken']='synthetic-review-refresh-required'
    atomic_json(credentials,value)
    os.chown(credentials,1000,1000)
    original_context=manager.run_context(rid)
    original_package=read_document(manager.scenarios._package_path(job['id']))
    with service.store.database() as connection:
        connection.execute("UPDATE runs SET status='running',started_at=?,capture_permission_mode='bypassPermissions' WHERE id=?",(time.time(),rid))
    token=None
    stop=threading.Event()
    watcher=None
    try:
        with main._oauth_owner_lock(account['name']):
            _,token=local.start_run(rid,current,task)
        operation=remote._row(token)
        watcher=threading.Thread(target=local.watch_managed_oauth_refresh,args=(rid,current,stop,token),daemon=True)
        watcher.start()
        deadline=time.monotonic()+150
        while remote.sessions.ledger.get(operation['operation_id'])['phase']!='closed':
            testcase.assertLess(time.monotonic(),deadline,'原私有评审401尚未实际释放')
            time.sleep(.2)
        while remote.sessions.ledger.active(account['id']):
            testcase.assertLess(time.monotonic(),deadline,'原Node凭据维护尚未确定收口')
            time.sleep(.2)
        pending=Path(node['data_root'])/'project-review-owner-refresh'/(str(account['id'])+'.json')
        testcase.assertEqual('complete',read_document(pending)['status'])
        testcase.assertTrue(read_document(credentials)['claudeAiOauth']['accessToken'].startswith('synthetic-refreshed-'))
        testcase.assertEqual(value['claudeAiOauth']['refreshToken'],read_document(credentials)['claudeAiOauth']['refreshToken'])
        testcase.assertTrue((Path(node['data_root'])/'node-runs'/operation['environment_id']/operation['operation_id']/'owner-refresh-defer.json').is_file())
        _cleanup_scope(local,token)
        with service.store.database() as connection:
            connection.execute("UPDATE runs SET status='failed',error='合成401后的原私有评审已实际释放',ended_at=? WHERE id=?",(time.time(),rid))
        manager.execution_released(rid,0)
        source=manager._one('SELECT x.* FROM project_execution_sources x JOIN project_task_executions e ON e.id=x.execution_id WHERE e.run_id=?',(rid,))
        execution=manager._one('SELECT e.*,r.status AS run_status,r.error AS run_error FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE e.run_id=?',(rid,))
        testcase.assertIsNotNone(source['released_at'],source['execution_error'])
        testcase.assertIsNone(source['execution_error'])
        testcase.assertIsNone(execution['result_json'])
        manager.scenarios._settle_execution(parent,execution,source)
        updated=manager._one('SELECT * FROM project_evaluation_jobs WHERE id=?',(job['id'],))
        testcase.assertEqual(('review_ready',1,1),(updated['status'],updated['review_resume'],updated['infra_recoveries']))
        segment=manager._one('SELECT * FROM project_work_segments WHERE source_id=?',(source['id'],))
        testcase.assertEqual('settled',segment['status'])
        testcase.assertGreater(segment['confirmed_sec'],0)
        testcase.assertTrue(manager.scenarios._reserve_review(parent,account,updated))
        next_id,next_account,next_task=submitted[-1]
        next_task.update(capture_permission_mode='bypassPermissions',capture_full_http=False)
        next_context=manager.run_context(next_id)
        testcase.assertEqual(original_context['session_id'],next_context['session_id'])
        testcase.assertEqual(original_package,read_document(manager.scenarios._package_path(job['id'])))
        next_execution=manager._one('SELECT * FROM project_task_executions WHERE run_id=?',(next_id,))
        testcase.assertEqual(execution['review_attempt'],next_execution['review_attempt'])
        return next_id,next_account,next_task
    finally:
        stop.set()
        if watcher is not None:
            watcher.join(timeout=25)
            testcase.assertFalse(watcher.is_alive(),'原401 watcher尚未退出')
        if token is not None:
            _cleanup_scope(local,token)


def _restart_review_node(testcase,service,runtime,remote,operation,private,cli) -> None:
    """在原完整评审结果待释放时强杀节点，保留原私有实例并核对恢复边界。

    :param testcase: 本次隔离断言。
    :param service: 原SSH服务。
    :param runtime: 原中央发布身份。
    :param remote: 原Run协调器。
    :param operation: 原冻结Scope记录。
    :param private: 原实际私有容器。
    :param cli: 原已交接的固定CLI。
    :return: None；后续沿原Scope收口并接受原封存结果。
    """
    private.reload()
    testcase.assertEqual('running',private.status)
    _restart_node_control(testcase,service,runtime,operation)
    observed=remote.sessions.node_state(operation['operation_id'])
    testcase.assertEqual(('reconcile','NodeRestart'),(observed['phase'],observed['error_type']))
    testcase.assertEqual(operation['operation_id'],remote.sessions.ledger.active(operation['account_id'])[0]['operation_id'])
    private.reload()
    cli.reload()
    testcase.assertEqual('running',private.status)
    testcase.assertIn(cli.status,('exited','dead','created'))


def _restart_node_control(testcase,service,runtime,operation) -> None:
    """强杀并恢复本次合成节点控制进程。参数为本次断言、原服务、运行时和操作。:return: None。"""
    name=node_container_name(runtime.deployment,operation['record']['scope']['node_key'])
    control=service.docker(operation['node_id']).containers.get(name)
    testcase.assertEqual('node-control',control.labels['vibebench.role'])
    control.kill(signal='SIGKILL')
    control.start()
    deadline=time.monotonic()+30
    while True:
        try:
            if service.connection(operation['node_id']).agent_health(name).get('state')=='ready':
                break
        except ValueError:
            pass
        testcase.assertLess(time.monotonic(),deadline,'原节点控制进程尚未恢复')
        time.sleep(0.2)


def _recover_program(testcase,service,runtime,remote,manager,account,source,job) -> None:
    """实际隔离程序运行中重启Node，沿原一次环境复验完成同一冻结候选。

    :param testcase: 本次隔离断言。
    :param service: 原SSH服务。
    :param runtime: 原中央运行时。
    :param remote: 原Run协调器。
    :param manager: 原场景管理器。
    :param account: 原合成账号。
    :param source: 已实际释放的原候选来源。
    :param job: 原冻结评测作业。
    :return: None；候选CLI保持已释放，后续评审沿原流程启动。
    """
    operation=remote.sessions.ledger.by_source(account['id'],source['source'],active_only=False)
    testcase.assertEqual('closed',operation['phase'])
    worker=threading.Thread(target=manager.scenarios._mechanical_job,args=(job['id'],),daemon=True)
    worker.start()
    docker=service.docker(operation['node_id'])
    labels=['vibebench.project-verifier=native','vibebench.execution-id='+operation['operation_id'],
        'vibebench.node-key='+operation['record']['scope']['node_key']]
    deadline=time.monotonic()+60
    while True:
        containers=docker.containers.list(filters={'label':labels})
        if containers:
            testcase.assertEqual(1,len(containers))
            original=containers[0]
            break
        testcase.assertTrue(worker.is_alive(),'程序在故障注入前已退出')
        testcase.assertLess(time.monotonic(),deadline,'原Node隔离程序尚未实际启动')
        time.sleep(0.1)
    _restart_node_control(testcase,service,runtime,operation)
    worker.join(timeout=150)
    testcase.assertFalse(worker.is_alive(),'程序重启后的原有限复验尚未收口')
    updated=manager._one('SELECT * FROM project_evaluation_jobs WHERE id=?',(job['id'],))
    testcase.assertEqual('review_ready',updated['status'],updated['native_result_json'] or updated['error'])
    records=[read_document(path) for path in (manager.data/'cluster-run-programs').glob('*/record.json')]
    testcase.assertEqual(2,len(records))
    testcase.assertCountEqual(['complete','cancelled'],[item['phase'] for item in records])
    testcase.assertTrue(any(item['error_reason']=='node_restart' for item in records))
    testcase.assertTrue(all(item['request']['candidate_digest']==job['candidate_digest'] for item in records))
    try:
        original.reload()
    except NotFound:
        pass
    else:
        testcase.assertIn(original.status,('exited','dead','created'))
    testcase.assertEqual([],remote.project_io.programs.active(account['id']))
    testcase.assertEqual([],remote.sessions.ledger.active(account['id']))


def _cleanup_scenario_programs(service,node) -> None:
    """清理本次随机节点的隔离验收容器，覆盖控制进程失联的夹具失败路径。

    :param service: 本次测试SSH服务。
    :param node: 本次随机节点及唯一私有数据根。
    :return: None；只处理精确原Node及verifier-root标签。
    """
    labels={'vibebench.node-key':node['node_key'],'vibebench.project-verifier':'native',
        'vibebench.verifier-root':digest_json(str(node['data_root']))}
    docker=service.docker(node['id'])
    for container in docker.containers.list(all=True,filters={'label':[key+'='+value for key,value in labels.items()]}):
        if any(container.labels.get(key)!=value for key,value in labels.items()):
            raise ValueError('本次场景验收清理标签需要核对')
        container.remove(force=True)
