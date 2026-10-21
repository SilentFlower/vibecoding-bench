"""真实Scheduler、Docker和driver下的场景／私有评审机制验证，不调用模型。"""
import hashlib
import io
import json
import os
import threading
import time
import zipfile
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import uvicorn

import main
from account_runtime import AccountRuntime, atomic_json
from project_iteration import ProjectIterationManager
from project_library import ProjectLibrary, read_document, snapshot_tree, write_document
from project_verifier import ProjectVerifier


def create_scenario_fixture(root: Path, python: str) -> ProjectLibrary:
    """生成仅用于隔离机制验证的合法内容及本地纯Python离线wheel。

    :param root: 测试临时内容根。
    :param python: 实际镜像精确Python版本。
    :return: 已校验内容库，不能作为正式真实项目计数。
    """
    environment=root/'environments/fixture-python'
    wheel=environment/'artifacts/bench_fixture-1.0.0-py3-none-any.whl'
    wheel.parent.mkdir(parents=True)
    with zipfile.ZipFile(wheel,'w') as archive:
        files={'bench_fixture.py':'VALUE = 1\n','bench_fixture-1.0.0.dist-info/METADATA':
            'Metadata-Version: 2.1\nName: bench-fixture\nVersion: 1.0.0\n',
            'bench_fixture-1.0.0.dist-info/WHEEL':'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
        files['bench_fixture-1.0.0.dist-info/RECORD']='\n'.join(name+',,' for name in files)+'\nbench_fixture-1.0.0.dist-info/RECORD,,\n'
        for name,content in files.items():
            archive.writestr(name,content)
    resources={'timeout_sec':60,'memory_mb':512,'pids_limit':64}
    write_document(environment/'profile/profile.json',{'schema':1,'id':'fixture-python','adapter':'python-native',
        'python':python,'requirements':['bench-fixture==1.0.0'],'business':resources,'regression':resources,
        'artifacts':[{'path':'artifacts/'+wheel.name,'digest':hashlib.sha256(wheel.read_bytes()).hexdigest()}]})
    for key,count in (('fixture-one',4),('fixture-two',2)):
        project=root/'projects'/key
        seed=project/'seed/library'
        seed.mkdir(parents=True)
        (seed/'example.py').write_text('VALUE = 1\n')
        (seed/'LICENSE').write_text('仅用于本地验证的自有测试夹具。')
        write_document(project/'verification/rubric.json',{'criteria':[{'id':'fact','requirement':'依据冻结真实测试源码回答问题',
            'evidence':['library/example.py:1']}]})
        (project/'verification/native.py').write_text('import json,example\nprint(json.dumps({"value":example.VALUE}))\n')
        write_document(project/'verification/native.json',{'script':'verification/native.py','args':[],
            'python_paths':['library'],'expected':{'value':2},'resource_profile':'business'})
        (project/'disclosure').mkdir()
        (project/'disclosure/context.txt').write_text('冻结调用材料：公开代码和预期行为都正确，请完成诊断。')
        tasks=[]
        for number in range(1,count+1):
            task={'id':f'Q{number}','kind':{1:'understand',2:'diagnose',3:'plan',4:'modify'}[number],
                'goal':'隔离场景机制测试','prompt':f'固定场景任务Q{number}：请处理当前业务问题。',
                'requires':[{'task_id':f'Q{number-1}','artifact':'answer'}] if number>1 else [],
                'materials':[],'allowed_paths':['library/example.py'] if number==4 else ['app'] if number==3 else [],
                'outcomes':['resolved'],'evaluation':{'version':1,'rubric':'verification/rubric.json'}}
            if number==2:
                task['branches']=[{'id':'context','when':'合理请求调用材料','materials':['disclosure/context.txt'],'activate_tasks':[]}]
            if number==4:
                task['evaluation']['native']='verification/native.json'
                task['evaluation']['semantic']=True
            tasks.append(task)
        write_document(project/'project.json',{'schema':2,'project_key':key,'title':key,'description':'本地测试，非正式内容',
            'category':'test','source':{'repository':'https://github.com/example/fixture','commit':'a'*40,'license_files':['seed/library/LICENSE']},
            'seed_digest':snapshot_tree(project/'seed')['digest'],'environment':'fixture-python','scenarios':[{'id':'S1','title':'合成业务',
                'goal':'验证真实执行链','default_entry':'default','entries':[{'id':'default','task_ids':[task['id'] for task in tasks]}],'tasks':tasks}]})
    write_document(root/'catalog.json',{'schema':2,'version':'test-only','projects':['fixture-one','fixture-two']})
    return ProjectLibrary(root)


def verify_project_scenarios(runtime, client, account: dict, row: dict) -> None:
    """验证容量1／2、候选释放、评审隔离、澄清、超时及代码接受。

    :param runtime: 随机内部网络中的合成账号运行器。
    :param client: Docker SDK。
    :param account: 本次合成账号，不读取已有真实账号。
    :param row: 已准备静态评审资源的固定环境。
    :return: None；结果只说明机制，不是模型成绩。
    """
    data=runtime.data
    paths={'BENCH_DATA':data,'HOST_BENCH_DATA':runtime.host_data,'DB_PATH':data/'scenario.sqlite','PROFILES_DIR':data/'profiles',
        'WORKSPACES_DIR':data/'workspaces','FLOWS_DIR':data/'flows','CA_DIR':data/'ca','TOPICS_FILE':data/'missing-topics.md'}
    with ExitStack() as stack:
        for key,value in {**paths,'V3_ENABLED':True,'TIMEOUT_WRAPUP_SEC':0,'CLAUDE_CODE_VERSION':'9.9.9',
                'login_manager':None,'continue_manager':None,'warmup_scheduler':None,'project_iterations':None}.items():
            stack.enter_context(patch.object(main,key,value))
        main.init_db()
        verified=AccountRuntime(client,data,runtime.host_data,main.get_db,runtime.fingerprint,None,main._quota_identity)
        stack.callback(verified.heartbeat_pool.shutdown)
        with main.get_db() as connection:
            connection.execute('INSERT INTO accounts(id,name,profile_path,upstream_proxy_scheme,upstream_socks5_host,upstream_socks5_port) VALUES(?,?,?,?,?,?)',
                (account['id'],account['name'],str(data/'profiles'/account['name']),account['upstream_proxy_scheme'],account['upstream_socks5_host'],account['upstream_socks5_port']))
            connection.execute('INSERT INTO account_environments('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
        runner=main.Runner()
        scheduler=main.Scheduler(runner)
        guard=main.QuotaGuard(runner)
        for key,value in (('account_runtime',verified),('runner',runner),('scheduler',scheduler),('quota_guard',guard)):
            stack.enter_context(patch.object(main,key,value))
        python=runtime._container(row).exec_run(['python3','-c','import platform;print(platform.python_version())']).output.decode().strip()
        library=create_scenario_fixture(data/'scenario-fixture-library',python)
        manager=ProjectIterationManager(data,library,main.get_db,main._db_lock,scheduler.submit,
            lambda:{'claude_code_version':'9.9.9','claude_effort_level':'high','execution_model':''},main._quota_identity,
            main._stop_project_run,ProjectVerifier(client,data,runtime.host_data,verified.image),scheduler.is_executing,
            admission=main._project_admission,execution_control=main._project_execution_control,
            schedule_admission=main._project_schedule_admission,concurrency_limit=main.PER_ACCOUNT_CONCURRENCY)
        verified.set_project_iterations(manager)
        current_library=manager.library
        manager.review_refresh=lambda current:verified.reviews.retry_owner_refresh(current,main._refresh_project_review_owner)
        stack.enter_context(patch.object(main,'project_iterations',manager))
        stack.callback(manager.stop)
        stack.callback(scheduler.stop_window_waits)
        original_start=verified.start_run

        def start(current_account, task, run_id, worker_env, quota_env):
            """只为替身保存合成执行参数，保留真实运行器和受控输入路径。"""
            context=manager.scenarios.context(run_id)
            if context['role']=='candidate':
                directory=verified._root(row)/'home/.synthetic-scenarios'
                directory.mkdir(exist_ok=True)
                os.chown(directory,1000,1000)
                atomic_json(directory/(context['session_id']+'.json'),{'task_key':context['task_key'],
                    'delay_sec':12 if context['project_key']=='fixture-two' and context['task_key']=='Q1' else 0.5},0o644)
            return original_start(current_account,task,run_id,{**worker_env,'COMPLETION_IDLE_SEC':'1'},quota_env)

        stack.enter_context(patch.object(verified,'start_run',side_effect=start))
        evidence={'capacity':main.PER_ACCOUNT_CONCURRENCY,'maximum_holders':0,'review_count':0,'private_checked':False,
            'candidate_review_overlap':False,'real_model_calls':0}
        failures=os.environ.get('VERIFY_SCENARIO_FAILURES')=='1'
        if failures:
            collection_type=type(client.containers)
            original_container_run=collection_type.run

            def lost_create_ack(collection,*args,**kwargs):
                """创建确实成功后丢一次ACK，交原登记和cleanup回收实际容器。"""
                child=original_container_run(collection,*args,**kwargs)
                if (collection.client is client and kwargs.get('labels',{}).get('vibebench.role')=='project-review'
                        and not evidence.get('lost_create_ack')):
                    evidence['lost_create_ack']=True
                    raise RuntimeError('本地测试：评审创建完成后ACK丢失')
                return child

            stack.enter_context(patch.object(collection_type,'run',new=lost_create_ack))
        seen=set()
        browser_mode=os.environ.get('VERIFY_SCENARIO_BROWSER')=='1'
        batch=None
        if browser_mode:
            server=uvicorn.Server(uvicorn.Config(main.app,host='0.0.0.0',port=8000,lifespan='off',log_level='warning',timeout_graceful_shutdown=2))
            service=threading.Thread(target=server.run,daemon=True)
            service.start()

            def stop_service() -> None:
                """关闭本次测试HTTP服务，不能覆盖产品生命周期。@return None。"""
                server.should_exit=True
                service.join(timeout=5)

            stack.callback(stop_service)
            write_document(Path('/verify/scenario-browser-ready.json'),{'schema':1,'status':'ready'})
        else:
            batch=manager.create_batch(account['id'],'合成场景完整链路',policy={'concurrency':main.PER_ACCOUNT_CONCURRENCY,
                'timeout_sec':60,'task_budget_sec':180,'review_timeout_sec':60,'review_budget_sec':240})
            manager.transition(batch['id'],'start')
        started=time.monotonic()
        try:
            while time.monotonic()-started<900:
                manager.tick()
                if batch is None:
                    batches=manager.batches()
                    if not batches:
                        time.sleep(0.2)
                        continue
                    batch=batches[0]
                jobs=verified.environment_jobs(row['environment_id'])
                evidence['maximum_holders']=max(evidence['maximum_holders'],len(jobs))
                assert len(jobs)<=main.PER_ACCOUNT_CONCURRENCY
                reviews=[job for job in jobs if job.get('execution_role')=='project-review' and job.get('review_container_id')
                    and job.get('review_phase')=='running' and job.get('process')]
                candidates=[job for job in jobs if job.get('execution_role')!='project-review']
                for job in reviews:
                    child=verified.reviews.container(job)
                    if job['source'] in seen:
                        continue
                    cli=verified._container(row)
                    cli.reload()
                    child.reload()
                    assert child.attrs['HostConfig']['ReadonlyRootfs']
                    assert child.attrs['HostConfig']['CapDrop']==['ALL']
                    assert child.attrs['HostConfig']['NetworkMode']=='container:'+row['network_container_id']
                    assert child.attrs['Config']['User']=='1000:1000'
                    package=read_document(verified.reviews.root_for_job(job)/'input/package.json')
                    process_model=child.exec_run(['python3','-c',
                        "import pathlib;print(next((item.split('=',1)[1] for item in pathlib.Path('/proc/"+str(job['process']['pid'])+"/environ').read_bytes().decode().split(chr(0)) if item.startswith('CLAUDE_MODEL_OVERRIDE=')),''))"])
                    if process_model.exit_code:
                        continue
                    assert process_model.output.decode().strip()==package['resolved_model']=='offline-fixture'
                    seen.add(job['source'])
                    evidence['review_count']+=1
                    private=verified.reviews.root_for_job(job)
                    assert not any(str(private).startswith(mount['Source']+'/') or str(private)==mount['Source']
                        for mount in cli.attrs['Mounts'])
                    assert cli.exec_run(['test','-e','/input/package.json']).exit_code!=0
                    assert cli.exec_run(['readlink','/proc/self/ns/pid']).output != child.exec_run(['readlink','/proc/self/ns/pid']).output
                    credentials=json.loads((private/'home/.claude/.credentials.json').read_text())
                    assert 'refreshToken' not in credentials['claudeAiOauth']
                    assert 'refreshToken' in json.loads((verified._root(row)/'home/.claude/.credentials.json').read_text())['claudeAiOauth']
                    limits=json.loads((verified._root(row)/'runtime/project-review-layout.json').read_text())['limits']
                    assert child.attrs['HostConfig']['Memory']==limits['review'][0]
                    assert cli.attrs['HostConfig']['Memory']==limits['cli'][0]
                    evidence['private_checked']=True
                    evidence['actual_model_pinned']=True
                    evidence['candidate_review_overlap'] |= bool(candidates)
                current=manager.batch(batch['id'])
                if current['status']=='completed':
                    break
                if current['status']=='blocked' or any(instance['task_counts'].get('blocked') for instance in current['instances']):
                    raise AssertionError('场景链路受阻：'+json.dumps(current,ensure_ascii=False))
                time.sleep(0.2)
            else:
                raise AssertionError('合成场景链路超过总截止时间')
            details=[manager.instance(instance['id']) for instance in current['instances']]
            tasks=[task for detail in details for scene in detail['scenarios'] for task in scene['tasks'] if task['selected']]
            assert len(tasks)==6 and all(task['status']=='passed' for task in tasks),details
            assert sum(bool(task['accepted_checkpoint_digest']) for task in tasks)==1
            assert all(task['attempt_count']==1 for task in tasks if task['task_key']!='Q3')
            resumed=next(task for task in tasks if task['task_key']=='Q3')
            assert resumed['attempt_count']==2
            assert resumed['candidate_budget']['confirmed_sec']>45 and resumed['candidate_budget']['remaining_sec']<135
            assert any(execution['execution_status']=='timeout' for execution in resumed['executions'])
            context=manager.scenarios.task(resumed['id'])
            submission=manager._one("SELECT candidate_relative FROM project_evaluation_jobs WHERE task_id=? AND status='passed' ORDER BY id DESC LIMIT 1",(resumed['id'],))
            assert (data/submission['candidate_relative']/'app/partial.txt').read_text()=='保留真实超时前的半成品'
            following=next(task for task in tasks if task['task_key']=='Q4')
            binding=read_document(data/'project-artifacts/task-inputs'/str(following['id'])/'code-dependency.json')
            # 新任务输入已切回确定基线；超时半成品仍须同时存在于候选和交接备份。
            assert (data/binding['saved_relative']/'app/partial.txt').read_text()=='保留真实超时前的半成品'
            assert not (data/context['workspace_relative']/'app/partial.txt').exists()
            assert evidence['private_checked'] and evidence['review_count']>=5
            if main.PER_ACCOUNT_CONCURRENCY==2:
                assert evidence['maximum_holders']==2 and evidence['candidate_review_overlap']
            with main.get_db() as connection:
                snapshots=[tuple(row) for row in connection.execute('SELECT DISTINCT claude_code_version,claude_effort_level,execution_model FROM runs')]
            assert snapshots==[('9.9.9','high','')]
            if failures:
                assert evidence.get('lost_create_ack')
                with main.get_db() as connection:
                    assert connection.execute('SELECT MAX(infra_recoveries) FROM project_evaluation_jobs').fetchone()[0]>=1
                verify_private_recovery(verified,client,account,row,evidence)
            evidence.update(status='passed',tasks=len(tasks),code_acceptances=1,elapsed_sec=time.monotonic()-started,
                details=details,usage=[manager.scenarios.usage(instance['id']) for instance in current['instances']])
            write_document(Path('/verify')/f'scenario-capacity-{main.PER_ACCOUNT_CONCURRENCY}.json',evidence)
            print('通过：真实场景／私有评审、容量、超时接续与代码接受，模型调用数0。',flush=True)
            if browser_mode:
                deadline=time.monotonic()+120
                while not Path('/verify/scenario-browser-result.json').exists() and time.monotonic()<deadline:
                    fault=Path('/verify/scenario-catalog-fault.json')
                    if fault.exists():
                        request=read_document(fault)
                        assert request['batch_id']==batch['id'] and request['action']=='disable_current_catalog'
                        manager.library=None
                    time.sleep(0.2)
                browser=read_document(Path('/verify/scenario-browser-result.json'))
                assert browser['status']=='passed'
                with main.get_db() as connection:
                    actual=[dict(item) for item in connection.execute('SELECT id,task_key,status,attempt_count,accepted_checkpoint_digest FROM project_scenario_tasks ORDER BY id')]
                    attempts=[dict(item) for item in connection.execute('SELECT task_id,attempt_no,ended_at,result FROM project_task_attempts ORDER BY task_id,attempt_no')]
                expected=sorted((task for detail in browser['details'] for scene in detail['scenarios'] for task in scene['tasks']),key=lambda item:item['id'])
                assert actual==[{key:item[key] for key in actual[0]} for item in expected]
                assert all(item['ended_at'] is not None and item['result'] in ('passed','timeout') for item in attempts)
                write_document(Path('/verify/scenario-browser-db.json'),{'status':'passed','tasks':actual,'attempts':attempts})
        finally:
            manager.library=current_library
            if batch:
                manager.transition(batch['id'],'stop')
            for job in verified.environment_jobs(row['environment_id']):
                try:
                    verified.cleanup(job['token'])
                except Exception:
                    pass
            deadline=time.monotonic()+15
            while scheduler._executing and time.monotonic()<deadline:
                time.sleep(0.1)


def verify_private_recovery(runtime, client, account: dict, row: dict, evidence: dict) -> None:
    """通过真实原租约及创建意图验证重启后running/exited/missing精确收口。

    :param runtime: 本次合成账号运行器。
    :param client: 本次Docker客户端。
    :param account: 唯一合成账号。
    :param row: 已预留评审资源的原环境。
    :param evidence: 本次机制证据，不能当模型结果。
    :return: None；不修改任何业务任务结论。
    """
    public_ids=[row[key] for key in ('container_id','network_container_id','sender_container_id')]
    expected={**runtime._labels(row),'vibebench.role':'project-review',
        'vibebench.release':runtime.release_id,'vibebench.isolation-version':str(row['isolation_version'])}

    def idle(labels: dict):
        """在静态预留内创建只属于本测试的闲置私有PID命名空间。"""
        return client.containers.run(runtime.image,entrypoint=['python3','-c'],command=['import time;time.sleep(120)'],
            labels=labels,detach=True,user='1000:1000',read_only=True,network_mode='container:'+row['network_container_id'],
            cap_drop=['ALL'],security_opt=['no-new-privileges:true'],mem_limit='512m',memswap_limit='512m',pids_limit=128)

    orphan=idle({**expected,'vibebench.review-intent':uuid.uuid4().hex+uuid.uuid4().hex})
    try:
        assert runtime.reviews.admission(account)['blocked']
        orphan.reload()
        assert orphan.status=='running'
        orphan.stop(timeout=2)
        assert runtime.reviews.admission(account)['allowed']
    finally:
        try:
            orphan.remove(force=True)
        except Exception:
            pass
    outcomes=[]
    for state in ('running','exited','missing'):
        source='recovery-fixture:'+uuid.uuid4().hex
        job=runtime.claim(row,account,source,shared_cli=True)
        job.update(execution_role='project-review',review_intent=hashlib.sha256(source.encode()).hexdigest(),
            private_relative='project-review-private/recovery-'+uuid.uuid4().hex,review_phase='creating')
        runtime._save_execution(job)
        child=idle(runtime.reviews.labels(job))
        job.update(review_container_id=child.id,review_phase='created')
        runtime._save_execution(job)
        if state in ('exited','missing'):
            child.stop(timeout=2)
        if state=='missing':
            child.remove()
        # 模拟管理进程消失：只遗忘本进程索引，持久创建意图和真实子容器都保留。
        with runtime.lock:
            runtime._remove_job(job)
        restarted=AccountRuntime(client,runtime.data,runtime.host_data,runtime.database,runtime.fingerprint,None,runtime.quota_identity)
        try:
            restarted.reconcile(row['environment_id'])
            assert not runtime._execution_path(job).exists()
            assert not client.containers.list(all=True,filters={'label':['vibebench.review-intent='+job['review_intent']]})
            outcomes.append(state)
        finally:
            restarted.heartbeat_pool.shutdown()
    for identity in public_ids:
        current=client.containers.get(identity)
        current.reload()
        assert current.status=='running'
    evidence.update(orphan_pool_fenced=True,private_restart_recovered=outcomes,public_roles_preserved=True)
