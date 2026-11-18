"""真实SSH经典实例两步接续、原生区间和中央独立验收的隔离夹具。"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import main
from cluster_deployment import node_container_name
from cluster_legacy_project_io import ClusterLegacyProjectIO
from project_iteration import ProjectIterationManager
from project_library import snapshot_tree
from project_test_content import create_project_fixture
from project_verifier import ProjectVerifier
from runtime_files import atomic_json


def verify_legacy_project(testcase,service,runtime,node,account,local,remote,configuration) -> None:
    """在随机合成部署运行原worker，再经原候选包和实际隔离程序验收两步。

    :param testcase: 隔离断言。
    :param service: 原中央节点服务。
    :param runtime: 原中央环境登记。
    :param node: 原SSH节点。
    :param account: 原合成账号。
    :param local: 原Runner入口。
    :param remote: 原节点协调器。
    :param configuration: 本次合成CLI配置。
    :return: None；所有输入及候选均为测试作者提供的固定夹具。
    """
    if not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('经典项目验证需要本次隔离部署')
    library=create_project_fixture(service.data/'legacy-project-fixture')
    installed=Path(node['data_root'])/'project-library/releases'/library.digest
    installed.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(library.root,installed)
    submitted=[]
    def stop(run_id):
        with service.store.database() as connection:
            connection.execute("UPDATE runs SET status='stopped',stop_requested_at=1 WHERE id=?",(run_id,))
    manager=ProjectIterationManager(service.data,library,service.store.database,service.store.lock,
        lambda rid,current,task:submitted.append((rid,current,task)),
        lambda current:{'claude_code_version':'2.1.303','claude_code_version_source':'synthetic-legacy',
            'claude_effort_level':'high','execution_model':'offline-model'},lambda _:'synthetic-quota',stop,
        ProjectVerifier(local.client,service.data,runtime.host_data,runtime.image),lambda _rid,_attempt:False,
        admission=main._project_admission,execution_control=main._project_execution_control)
    remote.project_io=ClusterLegacyProjectIO(remote,manager)
    manager.execution_io=remote.project_io
    remote.sessions.run_prepare=remote.project_io.prepare
    row=runtime._row(account['name'],account['id'])
    root=Path(node['data_root'])/'environments'/row['environment_id']
    with patch.object(main,'project_iterations',manager):
        try:
            if os.environ.get('CLUSTER_TEST_RUN_PLAN')=='1':
                _verify_plan(testcase,service,account,local,remote,manager,library,submitted,root)
                return
            batch=manager.create_batch(account['id'],'合成经典项目',['project-001'])
            manager.transition(batch['id'],'start')
            manager.tick()
            original_workspace=None
            for expected_step in (1,2):
                rid,current,task=submitted[-1]
                task.update(capture_permission_mode='bypassPermissions',capture_full_http=False)
                atomic_json(configuration,{'session':str(uuid4()),'busy_seconds':0.2,
                    'reply_usage':{'input_tokens':3,'output_tokens':7}},0o644)
                with service.store.database() as connection:
                    connection.execute("UPDATE runs SET status='running',started_at=? WHERE id=?",(time.time(),rid))
                token=None
                try:
                    with main._oauth_owner_lock(account['name']):
                        _,token=local.start_run(rid,current,task)
                    context=manager.run_context(rid)
                    workspace=Path(node['data_root'])/context['workspace_relative']
                    testcase.assertEqual(original_workspace or workspace,workspace)
                    original_workspace=workspace
                    testcase.assertFalse((service.data/'environments'/row['environment_id']).exists())
                    deadline=time.monotonic()+100
                    while remote.poll(token)['running']:
                        testcase.assertLess(time.monotonic(),deadline,'原经典项目worker尚未结束')
                        time.sleep(0.4)
                    testcase.assertEqual(0,remote.poll(token)['exit_code'])
                    turns=[json.loads(line) for line in (workspace/'.synthetic-turns.jsonl').read_text().splitlines()]
                    testcase.assertEqual(expected_step,len(turns))
                    testcase.assertEqual(task['prompt'],turns[-1]['text'])
                    # 候选由测试作者写入，验证远程封存与原中央验收，避免调用真实模型。
                    project=library.projects[context['project_key']]
                    reference=json.loads((project.root/'verification/reference.json').read_text())
                    manifest=json.loads(context['manifest_json'])
                    actions={step['checks'][0]['input']['action']:reference['actions'][step['checks'][0]['input']['action']]
                        for step in manifest['steps'][:expected_step]}
                    shutil.copy2(library.root/'reference_runtime.py',workspace/'fixture_behaviors.py')
                    source=(project.root/'seed/app.py').read_text().replace('def handle(request):','def original_handle(request):')
                    addition='\nfrom fixture_behaviors import evaluate\nACTIONS = '+repr(actions)+'\ndef handle(request):\n    action=request.get("action","overview")\n    if action in ACTIONS:\n        return evaluate(ACTIONS[action],request,FIELDS)\n    return original_handle(request)\n\n'
                    (workspace/'app.py').write_text(source.replace("if __name__ == '__main__':",addition+"if __name__ == '__main__':"))
                    with (workspace/'accumulated.txt').open('a') as output:
                        output.write(f'step-{expected_step:02}\n')
                    with service.store.database() as connection:
                        connection.execute("UPDATE runs SET status='success',ended_at=? WHERE id=?",(time.time(),rid))
                finally:
                    if token is not None:
                        local.cleanup(token,token)
                        testcase.assertEqual('closed',remote._row(token)['phase'])
                manager.record_native_end(rid,service.data/'missing-native')
                manager.execution_released(rid,0)
                usage=main._aggregate_claude_session_usage(rid)
                testcase.assertEqual((3,7,1),(usage['tokens_in'],usage['tokens_out'],usage['requests']))
                testcase.assertEqual(7,remote.stats(rid)['tokens_out'])
                manager.tick()
                instance=manager.instance(context['id'])
                testcase.assertEqual(expected_step,instance['next_step_index'])
                testcase.assertEqual('passed',manager._one('SELECT validation_status FROM project_step_attempts WHERE run_id=?',(rid,))['validation_status'])
                testcase.assertEqual(snapshot_tree(workspace)['digest'],instance['checkpoint_digest'])
            testcase.assertEqual('step-01\nstep-02\n',(original_workspace/'accumulated.txt').read_text())
            testcase.assertEqual([],remote.sessions.ledger.active(account['id']))
        finally:
            manager.stop()


def _verify_plan(testcase,service,account,local,remote,manager,library,submitted,root) -> None:
    """通过原worker同会话完成两步，实际节点程序和原中央验收往返。

    :param testcase: 原隔离断言。
    :param service: 原中央服务。
    :param account: 原合成账号。
    :param local: 原Runner。
    :param remote: 原节点执行器。
    :param manager: 原中央计划管理器。
    :param library: 原合成固定内容。
    :param submitted: 原调度提交记录。
    :param root: 原实际环境根。
    :return: None；仅使用合成CLI实现固定夹具动作。
    """
    batch=manager.create_batch(account['id'],'合成同会话计划',['project-001'],
        policy={'concurrency':1,'active_projects':1,'steps_per_plan':2})
    manager.transition(batch['id'],'start')
    manager.tick()
    rid,current,task=submitted[-1]
    task.update(capture_permission_mode='bypassPermissions',capture_full_http=False)
    context=manager.run_context(rid)
    definition=library.projects[context['project_key']]
    manifest=json.loads(context['manifest_json'])
    reference=json.loads((definition.root/'verification/reference.json').read_text())
    directory=root/'home/.synthetic-projects'
    directory.mkdir(mode=0o755)
    quota_mode=os.environ.get('CLUSTER_TEST_PLAN_QUOTA')=='1'
    configuration={'session':context['session_id'],
        'seed':(definition.root/'seed/app.py').read_text(),'runtime':(library.root/'reference_runtime.py').read_text(),
        'actions':reference['actions'],'step_actions':[step['checks'][0]['input']['action'] for step in manifest['steps']]}
    if quota_mode:
        configuration.update(quota_pause_step=2,quota_schedule=[{'after':0.2,'five_hour':100,'seven_day':9,'five_hour_reset_seconds':8}])
    atomic_json(directory/(context['session_id']+'.json'),configuration,0o644)
    with service.store.database() as connection:
        connection.execute("UPDATE runs SET status='running',started_at=?,capture_permission_mode='bypassPermissions' WHERE id=?",(time.time(),rid))
    token=None
    recovered=False
    try:
        with main._oauth_owner_lock(account['name']):
            _,token=local.start_run(rid,current,task)
        deadline=time.monotonic()+150
        while remote.poll(token)['running']:
            testcase.assertLess(time.monotonic(),deadline,'原同会话计划尚未收口')
            manager.tick()
            if quota_mode:
                _refresh_plan_quota(remote,token)
            progress=manager._one('SELECT completed_steps FROM project_execution_plans WHERE id=?',(context['plan_id'],))
            if os.environ.get('CLUSTER_TEST_PLAN_RECOVERY')=='1' and progress['completed_steps']==1:
                execution=remote._row(token)
                runtime=remote.sessions.runtime
                name=node_container_name(runtime.deployment,execution['record']['scope']['node_key'])
                control=service.docker(execution['node_id']).containers.get(name)
                testcase.assertEqual('node-control',control.labels['vibebench.role'])
                control.kill(signal='SIGKILL')
                control.start()
                deadline=time.monotonic()+30
                while True:
                    try:
                        if service.connection(execution['node_id']).agent_health(name).get('state')=='ready':
                            break
                    except ValueError:
                        pass
                    testcase.assertLess(time.monotonic(),deadline,'原计划节点控制进程尚未恢复')
                    time.sleep(0.2)
                observed=remote.sessions.node_state(execution['operation_id'])
                testcase.assertEqual(('reconcile','NodeRestart'),(observed['phase'],observed['error_type']))
                recovered=True
                break
            time.sleep(0.3)
        if quota_mode:
            testcase.assertEqual(43,remote.poll(token)['exit_code'])
            token,current=_resume_plan_quota(testcase,service,rid,current,local,remote,manager,token)
            deadline=time.monotonic()+130
            while remote.poll(token)['running']:
                testcase.assertLess(time.monotonic(),deadline,'原计划额度恢复后尚未收口')
                manager.tick()
                _refresh_plan_quota(remote,token)
                time.sleep(0.2)
        if not recovered:
            testcase.assertEqual(0,remote.poll(token)['exit_code'])
        with service.store.database() as connection:
            connection.execute("UPDATE runs SET status=?,ended_at=? WHERE id=?",('failed' if recovered else 'success',time.time(),rid))
    finally:
        if token is not None:
            local.cleanup(token,token)
    manager.record_native_end(rid,service.data/'missing-native')
    attempt=remote._row(token)['record']['work']['task']['quota_attempt']
    manager.execution_released(rid,attempt)
    manager.tick()
    updated=manager.run_context(rid)
    if recovered:
        testcase.assertEqual(1,updated['next_step_index'])
        accepted=manager._rows("SELECT validation_status,candidate_digest FROM project_step_attempts WHERE run_id=? AND validation_status='passed'",(rid,))
        testcase.assertEqual(1,len(accepted))
        testcase.assertEqual(updated['checkpoint_digest'],accepted[0]['candidate_digest'])
        testcase.assertEqual('closed',remote._row(token)['phase'])
        testcase.assertEqual([],remote.sessions.ledger.active(account['id']))
        with main._oauth_owner_lock(account['name']):
            with testcase.assertRaisesRegex(ValueError,'已经收口'):
                local.start_run(rid,current,task)
        return
    testcase.assertEqual(2,updated['next_step_index'])
    testcase.assertEqual('completed',updated['plan_status'])
    workspace=root/'projects'/Path(updated['workspace_relative']).name
    testcase.assertEqual('step-01\nstep-02\n',(workspace/'fixture-progress.txt').read_text())
    turns=[json.loads(line) for line in (workspace/'.synthetic-turns.jsonl').read_text().splitlines()]
    testcase.assertEqual(3 if quota_mode else 2,len(turns))
    testcase.assertEqual({context['session_id']},{item['session'] for item in turns})
    usage=main._aggregate_claude_session_usage(rid)
    testcase.assertEqual((14,33,2),(usage['tokens_in'],usage['tokens_out'],usage['requests']))
    attempts=manager._rows('SELECT id,validation_status FROM project_step_attempts WHERE run_id=? ORDER BY phase_seq',(rid,))
    testcase.assertEqual(['passed','passed'],[item['validation_status'] for item in attempts])
    testcase.assertEqual([11,22],[manager.step_usage(item['id'],main._usage_input_tokens)['tokens_out'] for item in attempts])
    testcase.assertEqual([],remote.sessions.ledger.active(account['id']))


def _resume_plan_quota(testcase,service,rid,account,local,remote,manager,token):
    """通过原QuotaGuard等待真实到期，确认旧Scope停止后认领新尝试。

    :param testcase: 原断言。
    :param service: 原中央服务。
    :param rid: 原Run。
    :param account: 原合成账号。
    :param local: 原Runner。
    :param remote: 原节点协调器。
    :param manager: 原计划管理器。
    :param token: 原耗尽Scope。
    :return: 同Run新尝试的实际token及当前完整账号。
    """
    pending=[]
    scheduler=main.Scheduler(local)
    scheduler.submit=lambda run,current,task:pending.append((run,current,task))
    with patch.multiple(main,scheduler=scheduler,PROJECTS_AGENT_ENABLED=False):
        _refresh_plan_quota(remote,token)
        testcase.assertEqual(100,main.quota_guard.snapshot(account)['windows']['five_hour']['utilization'])
        scheduler._mark_quota_wait(rid,account,0)
        manager.tick()
        deadline=time.monotonic()+20
        while main.quota_guard.snapshot(account)['blocked']:
            testcase.assertLess(time.monotonic(),deadline,'原额度窗口尚未真实到期')
            time.sleep(0.1)
        with service.store.database() as connection:
            current=dict(connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone())
        main.quota_guard._resume_account(current)
        testcase.assertEqual([],pending)
        with service.store.database() as connection:
            testcase.assertEqual(0,connection.execute('SELECT quota_attempt FROM runs WHERE id=?',(rid,)).fetchone()[0])
        local.cleanup(token,token)
        testcase.assertEqual('closed',remote._row(token)['phase'])
        manager.record_native_end(rid,service.data/'missing-native')
        manager.execution_released(rid,0)
        main.quota_guard._resume_account(current)
        testcase.assertEqual(1,len(pending))
        run,current,task=pending[0]
        testcase.assertEqual((rid,1),(run,task['quota_attempt']))
        with service.store.database() as connection:
            connection.execute("UPDATE runs SET status='running',started_at=? WHERE id=?",(time.time(),rid))
        with main._oauth_owner_lock(current['name']):
            _,next_token=local.start_run(run,current,task)
        testcase.assertNotEqual(token,next_token)
        testcase.assertEqual(remote._row(token)['record']['work']['project']['plan']['session_id'],
            remote._row(next_token)['record']['work']['project']['plan']['session_id'])
        return next_token,current


def _refresh_plan_quota(remote,token) -> None:
    """在原Scope操作锁内发布额度，保持与正式续约相同的序号边界。

    :param remote: 原节点协调器。
    :param token: 原执行定位。
    :return: None。
    """
    row=remote._row(token)
    with remote.sessions._operation_lock(row['operation_id']):
        remote.sessions.quota_refresh(remote.sessions.ledger.admit(row['operation_id']))
