"""在独立 Docker 环境验证真实多步 driver、并行调度和超时接续。"""
import json
import os
import sqlite3
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import main
from account_runtime import AccountRuntime, atomic_json
from project_iteration import ProjectIterationManager
from project_test_content import create_project_fixture
from project_verifier import ProjectVerifier


def verify_project_scheduling(runtime, client, account: dict, row: dict, *, catalog_only: bool = False) -> None:
    """运行合成 CLI，但完整使用 Scheduler、tmux、监督器和 Docker 业务验收。

    :param runtime: 当前随机部署的账号运行时。
    :param client: Docker 客户端。
    :param account: 合成账号。
    :param row: 已完成合成登录的环境。
    :param catalog_only: 单独执行默认稳定等待下的百项目规模场景。
    :return: None；任何证据不一致则失败。
    """
    data = runtime.data
    paths = {'BENCH_DATA':data,'HOST_BENCH_DATA':runtime.host_data,'DB_PATH':data/'project-scheduling.sqlite',
        'PROFILES_DIR':data/'profiles','WORKSPACES_DIR':data/'workspaces','FLOWS_DIR':data/'flows','CA_DIR':data/'ca',
        'TOPICS_FILE':data/'missing-topics.md'}
    with ExitStack() as stack:
        for key,value in {**paths,'V3_ENABLED':True,'TIMEOUT_WRAPUP_SEC':0,'CLAUDE_CODE_VERSION':'9.9.9',
                'login_manager':None,'continue_manager':None,'warmup_scheduler':None,'project_iterations':None}.items():
            stack.enter_context(patch.object(main,key,value))
        main.init_db()
        original_database = main.get_db
        transactions = []

        def traced_database():
            """仅保留事务边界帮助定位并行收口锁，不记录 SQL 正文或凭据。"""
            connection = original_database()
            identity = len(transactions)
            def traced(statement):
                operation = statement.split(' ',1)[0].upper()
                if operation in ('BEGIN','COMMIT','ROLLBACK'):
                    transactions.append((time.time(),threading.current_thread().name,identity,operation))
            connection.set_trace_callback(traced)
            return connection

        stack.enter_context(patch.object(main,'get_db',traced_database))
        verified = AccountRuntime(client,data,runtime.host_data,main.get_db,runtime.fingerprint,None,main._quota_identity)
        stack.callback(verified.heartbeat_pool.shutdown)
        with main.get_db() as connection:
            connection.execute('INSERT INTO accounts(id,name,profile_path,upstream_proxy_scheme,upstream_socks5_host,upstream_socks5_port) VALUES(?,?,?,?,?,?)',
                (account['id'],account['name'],str(data/'profiles'/account['name']),account['upstream_proxy_scheme'],account['upstream_socks5_host'],account['upstream_socks5_port']))
            connection.execute('INSERT INTO account_environments('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
        runner = main.Runner()
        scheduler = main.Scheduler(runner)
        guard = main.QuotaGuard(runner)
        for key,value in (('account_runtime',verified),('runner',runner),('scheduler',scheduler),('quota_guard',guard)):
            stack.enter_context(patch.object(main,key,value))
        library = create_project_fixture(data/'project-scheduling-fixtures')
        manager = ProjectIterationManager(data,library,main.get_db,main._db_lock,
            scheduler.submit,lambda:{'claude_code_version':'9.9.9','claude_effort_level':'high','execution_model':''},
            main._quota_identity,main._stop_project_run,ProjectVerifier(client,data,runtime.host_data,verified.image),scheduler.is_executing,
            admission=main._project_admission,execution_control=main._project_execution_control,
            schedule_admission=main._project_schedule_admission,concurrency_limit=main.PER_ACCOUNT_CONCURRENCY)
        verified.set_project_iterations(manager)
        stack.enter_context(patch.object(main,'project_iterations',manager))
        stack.callback(manager.stop)
        stack.callback(scheduler.stop_window_waits)
        original_start = runner.start_run
        observed = {'overlap':False,'frozen_sibling':False,'maximum':0}

        def start_fixture(run_id, current_account, task):
            """为当前 pinned session 提供有限测试程序，不在执行后修改代码。"""
            context = manager.run_context(run_id)
            if context is None:
                return original_start(run_id,current_account,task)
            definition = manager.library.projects[context['project_key']]
            manifest = json.loads(context['manifest_json'])
            reference = json.loads((definition.root/'verification/reference.json').read_text())
            directory = verified._root(row)/'home/.synthetic-projects'
            directory.mkdir(exist_ok=True)
            fixture = {'session':context['session_id'],'seed':(definition.root/'seed/app.py').read_text(),
                'runtime':(library.root/'reference_runtime.py').read_text(),
                'actions':{step['checks'][0]['input']['action']:reference['actions'][step['checks'][0]['input']['action']]
                    for step in manifest['steps']},'step_actions':[step['checks'][0]['input']['action'] for step in manifest['steps']],
                'delay_sec':0.05 if catalog_only else 2}
            if not catalog_only and context['project_key']=='project-004':
                fixture['timeout_step'] = 2
            atomic_json(directory/(context['session_id']+'.json'),fixture,0o644)
            return original_start(run_id,current_account,task)

        original_control = manager.plans.control

        def control_fixture(run_id, epoch, operation):
            """核对真实暂停时兄弟监督器仍在运行，并保留完整内核控制路径。"""
            result = original_control(run_id,epoch,operation)
            if operation=='freeze':
                for job in verified.environment_jobs(row['environment_id']):
                    if job.get('run_id')!=run_id and job.get('shared_cli') and job.get('process'):
                        state = verified.control_execution(job['token'],'inspect')
                        if state.get('exists') and state.get('state') not in ('T','t','Z'):
                            observed['frozen_sibling'] = True
            return result

        manager.plans.control = control_fixture
        stack.enter_context(patch.object(runner,'start_run',side_effect=start_fixture))

        def finish_executions():
            """在全局测试配置恢复前排空本次线程，避免失败日志被假数据库错误淹没。"""
            scheduler.stop_window_waits()
            for job in verified.environment_jobs(row['environment_id']):
                try:
                    main.stop_run(job['run_id'])
                except Exception:
                    verified.cleanup(job['token'])
            deadline = time.monotonic()+12
            while scheduler._executing and time.monotonic()<deadline:
                time.sleep(0.1)

        stack.callback(finish_executions)
        if catalog_only:
            from verify_project_catalog import verify_project_catalog
            verify_project_catalog(manager,verified,client,account,row)
            return

        def await_condition(condition, seconds=180):
            """在有界循环中推进真实控制器并检查失败证据。"""
            deadline = time.monotonic()+seconds
            while time.monotonic()<deadline:
                try:
                    manager.tick()
                except sqlite3.OperationalError as error:
                    print('事务边界诊断：'+json.dumps(transactions[-60:]),flush=True)
                    if 'locked' not in str(error):
                        raise
                    # 正式后台循环也会在短暂 SQLite 占用后继续；总场景截止时间仍保持原值。
                    time.sleep(0.1)
                    continue
                jobs = verified.environment_jobs(row['environment_id'])
                active = [job for job in jobs if job.get('exec') and client.api.exec_inspect(job['exec'])['Running']]
                observed['maximum'] = max(observed['maximum'],len(active))
                if len(active)==2:
                    assert len({job['cwd'] for job in active})==2
                    assert len({job['run_id'] for job in active})==2
                    observed['overlap'] = True
                if condition():
                    return
                with main.get_db() as connection:
                    failures = [dict(item) for item in connection.execute("SELECT id,status,error FROM project_iteration_batches WHERE status='blocked'")]
                    run_failures = [dict(item) for item in connection.execute("SELECT id,status,error FROM runs WHERE status IN ('auth_failed','failed')")]
                if failures or run_failures:
                    raise AssertionError({'batches':failures,'runs':run_failures})
                time.sleep(0.2)
            with main.get_db() as connection:
                evidence = {'runs':[dict(item) for item in connection.execute('SELECT id,status,error FROM runs')],
                    'plans':[dict(item) for item in connection.execute('SELECT id,completed_steps,status,error FROM project_execution_plans')]}
            evidence['jobs'] = []
            for job in verified.environment_jobs(row['environment_id']):
                artifact = verified.run_artifact_path(job['run_id'],'project-plan-state.json')
                state = json.loads(artifact.read_text()) if artifact.exists() else {}
                evidence['jobs'].append({'run_id':job['run_id'],'phase':state.get('phase_seq'),'delivery':state.get('delivery'),
                    'process':verified.control_execution(job['token'],'inspect'),
                    'transcript':verified.run_artifact_path(job['run_id'],'transcript.log').read_text()[-1200:]})
            raise AssertionError({'message':'调度验证等待超时','evidence':evidence})

        if os.environ.get('VERIFY_PROJECT_SCHEDULING_TASKS_ONLY')!='1':
            batch = manager.create_batch(account['id'],'同账号并行两步',['project-001','project-002','project-003'],
                {'concurrency':2,'active_projects':3,'interval_min_sec':30,'interval_max_sec':30,'timeout_sec':90})
            manager.transition(batch['id'],'start')
            await_condition(lambda:len(manager.batch(batch['id'])['scheduling']['active_runs'])==2)
            await_condition(lambda:observed['overlap'])
            manager.transition(batch['id'],'pause')
            await_condition(lambda:manager.batch(batch['id'])['status']=='paused'
                and not manager.batch(batch['id'])['scheduling']['active_runs'])
            after = manager.batch(batch['id'])
            assert sorted(item['next_step_index'] for item in after['instances'])==[0,2,2],after
            assert sum(item['workspace_path'] is not None for item in after['instances'])==2
            for instance in after['instances']:
                if instance['next_step_index']:
                    detail = manager.instance(instance['id'])
                    assert len(detail['plans'])==1 and len(detail['plans'][0]['runs'])==1
                    assert len({item['run_id'] for item in detail['attempts']})==1
                    usages = [manager.step_usage(item['id'],main._usage_input_tokens) for item in detail['attempts']]
                    assert [item['tokens_out'] for item in usages]==[11,22],usages
            assert after['next_launch_at']>time.time()
            saved_deadline = after['next_launch_at']
            manager.recover(runner.cleanup_quota_run)
            manager.tick()
            assert manager.batch(batch['id'])['next_launch_at']==saved_deadline
            manager.transition(batch['id'],'stop')
            manager.tick()
            assert observed['overlap'] and observed['frozen_sibling'] and observed['maximum']==2,observed
            print('通过：真实两 CLI 重叠运行；暂停 A 验收时 B 继续；同一 Run/session 两步；逐步用量 11/22；补位截止跨恢复不变',flush=True)

            fault = manager.create_batch(account['id'],'局部阻塞不停止健康项目',['project-005','project-006','project-007'],
                {'concurrency':2,'active_projects':3,'rotation_steps':2,'steps_per_plan':2,'timeout_sec':180})
            manager.transition(fault['id'],'start')
            await_condition(lambda:len(manager.batch(fault['id'])['scheduling']['active_runs'])==2)
            active = manager.batch(fault['id'])['scheduling']['active_runs']
            active_instances = {item['instance_id'] for item in active}
            # 首步已接受才注入，证明真实driver已经启动，避免把启动前取消当作交接故障。
            await_condition(lambda:all(item['next_step_index']>=1 for item in manager.batch(fault['id'])['instances']
                if item['id'] in active_instances))
            victim = active[0]
            with main.get_db() as connection:
                execution = dict(connection.execute('SELECT * FROM project_plan_executions WHERE run_id=?',(victim['id'],)).fetchone())
            manager.plans._block(execution,'合成局部交接故障，保留原始原因')
            # 后续项目首步通过后再暂停，目录发布本身不能证明它已经越过启动门禁。
            await_condition(lambda:all(item['next_step_index']>=1 for item in manager.batch(fault['id'])['instances']
                if item['id']!=victim['instance_id']))
            manager.transition(fault['id'],'pause')
            await_condition(lambda:manager.batch(fault['id'])['status']=='paused'
                and not manager.batch(fault['id'])['scheduling']['active_runs'])
            failed_instance = manager.instance(victim['instance_id'])
            assert failed_instance['status']=='blocked' and failed_instance['error']=='合成局部交接故障，保留原始原因',failed_instance
            assert all(item['next_step_index']>=2 for item in manager.batch(fault['id'])['instances'] if item['id']!=victim['instance_id'])
            manager.transition(fault['id'],'stop')
            print('通过：实际停止故障CLI后保留局部blocked及原因；兄弟和原队列后续项目继续独立验收',flush=True)

            # 第二批保留一次实际 60 秒工作超时，不能用数据库伪造 timeout 冒充 driver 行为。
            timeout_batch = manager.create_batch(account['id'],'半步超时接续',['project-004'],{'concurrency':1,'timeout_sec':60})
            manager.transition(timeout_batch['id'],'start')
            manager.tick()
            detail = manager.batch(timeout_batch['id'])
            instance_id = detail['instances'][0]['id']
            with main.get_db() as connection:
                plan = dict(connection.execute('SELECT * FROM project_execution_plans WHERE instance_id=?',(instance_id,)).fetchone())
            await_condition(lambda:manager.instance(instance_id)['next_step_index']==1)
            manager.transition(timeout_batch['id'],'pause')
            await_condition(lambda:manager.batch(timeout_batch['id'])['status']=='paused'
                and not manager.batch(timeout_batch['id'])['scheduling']['active_runs'],seconds=95)
            before = manager.instance(instance_id)
            assert before['plans'][0]['completed_steps']==1 and before['plans'][0]['runs'][0]['status']=='timeout',before
            partial = data/manager.run_context(before['plans'][0]['runs'][0]['id'])['workspace_relative']/'partial-artifact.txt'
            assert partial.read_text()=='half of step 2'
            manager.transition(timeout_batch['id'],'start')
            await_condition(lambda:len(manager.instance(instance_id)['plans'][0]['runs'])==2)
            resumed_id = manager.instance(instance_id)['plans'][0]['runs'][-1]['id']
            await_condition(lambda:any(job.get('run_id')==resumed_id and job.get('process_permitted')
                for job in verified.environment_jobs(row['environment_id'])))
            manager.transition(timeout_batch['id'],'pause')
            await_condition(lambda:manager.instance(instance_id)['next_step_index']==2
                and not manager.batch(timeout_batch['id'])['scheduling']['active_runs'])
            resumed = manager.instance(instance_id)
            assert len(resumed['plans'])==1 and len(resumed['plans'][0]['runs'])==2
            assert [run['status'] for run in resumed['plans'][0]['runs']]==['timeout','success']
            assert partial.read_text()=='half of step 2'
            manager.transition(timeout_batch['id'],'stop')
            manager.tick()
            print('通过：真实 driver 60 秒超时保留计划 1/2、半成品及旧 timeout Run；新 Run 恢复原 session 并只通过剩余一步；全部为合成 CLI',flush=True)

        # 沿用同一个 Scheduler 的 Tasks 也必须真正并行，透传长连接覆盖第二次入场和首次清理。
        home = verified._root(row)/'home'
        atomic_json(home/'.synthetic-followups.json',{'session':'task-fixture','session_by_run':True,'busy_seconds':10},0o644)
        stream_marker = home/'.synthetic-live-stream.json'
        stop_marker = home/'.synthetic-stop-stream'
        stop_marker.unlink(missing_ok=True)
        stream_code = """import http.client,json,time
from pathlib import Path
home=Path('/home/node')
connection=http.client.HTTPConnection('api.anthropic.com',8081,timeout=8)
connection.request('POST','/v1/v3-stream',body=b'{}',headers={'Content-Type':'application/json'})
response=connection.getresponse()
assert response.status==200
count=0
while not (home/'.synthetic-stop-stream').exists():
 data=response.read(64)
 if not data: raise RuntimeError('长连接提前结束')
 count+=len(data)
 (home/'.synthetic-live-stream.json').write_text(json.dumps({'bytes':count,'at':time.time()}))
connection.close()
"""
        container = verified._container(row)
        stream_exec = client.api.exec_create(container.id,['python3','-c',stream_code],user='1000:1000')
        client.api.exec_start(stream_exec['Id'],detach=True)
        await_condition(lambda:stream_marker.exists(),seconds=12)
        first_bytes = json.loads(stream_marker.read_text())['bytes']
        relay_before = json.loads((verified._network_runtime(row)/'context-ack.json').read_text())
        task_runs = []
        for number in (1,2):
            run_id = 'parallel-task-'+str(number)
            with main.get_db() as connection:
                task_id = connection.execute('INSERT INTO tasks(topic_no,title,prompt,account_id,timeout_sec) VALUES(1,?,?,?,90)',
                    ('Synthetic parallel task','Complete this local synthetic task.',account['id'])).lastrowid
                connection.execute("INSERT INTO runs(id,task_id,account_id,status,run_kind,claude_code_version,claude_effort_level,execution_model,quota_identity) VALUES(?,?,?,'queued','normal','9.9.9','high','',?)",
                    (run_id,task_id,account['id'],main._quota_identity(account)))
            scheduler.submit(run_id,account,{'id':task_id,'prompt':'Complete this local synthetic task.',
                'timeout_sec':90,'claude_code_version':'9.9.9','claude_effort_level':'high','model_override':''})
            task_runs.append(run_id)
        await_condition(lambda:len([job for job in verified.environment_jobs(row['environment_id']) if job.get('run_id') in task_runs and job.get('process')])==2)
        await_condition(lambda:all((scheduler._get_run_state(run_id) or {}).get('status')=='success' for run_id in task_runs),seconds=75)
        await_condition(lambda:not verified.environment_jobs(row['environment_id']),seconds=15)
        relay_after = json.loads((verified._network_runtime(row)/'context-ack.json').read_text())
        assert relay_before['pid']==relay_after['pid'] and relay_before['started_at']==relay_after['started_at']
        assert client.api.exec_inspect(stream_exec['Id'])['Running']
        assert json.loads(stream_marker.read_text())['bytes']>first_bytes
        stop_marker.write_text('stop')
        await_condition(lambda:not client.api.exec_inspect(stream_exec['Id'])['Running'],seconds=12)
        assert client.api.exec_inspect(stream_exec['Id'])['ExitCode']==0
        assert observed['maximum']==2
        print('通过：Tasks 同账号两个真实 CLI 同时存在；全部执行共用容量 2；已建立透传长连接跨补位及清理继续，relay PID 与启动时刻保持',flush=True)
