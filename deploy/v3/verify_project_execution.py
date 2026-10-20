"""使用合成 CLI、真实执行器和独立 Docker 验收证明项目自动推进闭环。"""
import json
import os
import shutil
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import main
from account_runtime import AccountRuntime, atomic_json
from project_iteration import ProjectIterationManager
from project_library import ProjectLibrary
from project_verifier import ProjectVerifier


def verify_project_execution(runtime, client, account: dict, row: dict) -> None:
    """在隔离账号中执行两个真实 driver 回合，不连接真实模型。

    :param runtime: 已完成合成登录的运行时。
    :param client: 本次 Docker 客户端。
    :param account: 本次合成账号。
    :param row: 已存在的环境行。
    :return: None；状态、目录或验收不满足时失败。
    """
    data = runtime.data
    repository = Path('/source')
    paths = {'BENCH_DATA':data,'HOST_BENCH_DATA':runtime.host_data,'DB_PATH':data/'project-execution.sqlite',
        'PROFILES_DIR':data/'profiles','WORKSPACES_DIR':data/'workspaces','FLOWS_DIR':data/'flows','CA_DIR':data/'ca',
        'TOPICS_FILE':data/'missing-topics.md'}
    with ExitStack() as stack:
        for key,value in {**paths,'V3_ENABLED':True,'TIMEOUT_WRAPUP_SEC':0,'CLAUDE_CODE_VERSION':'9.9.9',
                'login_manager':None,'continue_manager':None,'warmup_scheduler':None,'project_iterations':None}.items():
            stack.enter_context(patch.object(main,key,value))
        main.init_db()
        verified = AccountRuntime(client,data,runtime.host_data,main.get_db,runtime.fingerprint,None,main._quota_identity)
        stack.callback(verified.heartbeat_pool.shutdown)
        with main.get_db() as connection:
            connection.execute('INSERT INTO accounts(id,name,profile_path,upstream_proxy_scheme,upstream_socks5_host,upstream_socks5_port) VALUES(?,?,?,?,?,?)',
                (account['id'],account['name'],str(data/'profiles'/account['name']),account['upstream_proxy_scheme'],account['upstream_socks5_host'],account['upstream_socks5_port']))
            columns = list(row)
            connection.execute('INSERT INTO account_environments('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(row.values()))
        runner = main.Runner()
        scheduler = main.Scheduler(runner)
        guard = main.QuotaGuard(runner)
        for key,value in (('account_runtime',verified),('runner',runner),('scheduler',scheduler),('quota_guard',guard)):
            stack.enter_context(patch.object(main,key,value))
        manager = ProjectIterationManager(data,ProjectLibrary(repository/'project_library'),main.get_db,main._db_lock,
            scheduler.submit,lambda:{'claude_code_version':'9.9.9','claude_effort_level':'high','execution_model':''},
            main._quota_identity,main.stop_run,ProjectVerifier(client,data,runtime.host_data,verified.image),scheduler.is_executing,
            admission=main._project_admission)
        verified.set_project_iterations(manager)
        stack.enter_context(patch.object(main,'project_iterations',manager))
        stack.callback(manager.stop)
        stack.callback(scheduler.stop_window_waits)
        original_start,original_wait = runner.start_run,runner.wait_worker
        run_for_token = {}

        def start_fixture(run_id, current_account, task):
            """提供只消费输入和写入主日志的 CLI 替身。"""
            atomic_json(verified._root(row)/'home/.synthetic-followups.json',{'session':run_id},0o644)
            result = original_start(run_id,current_account,task)
            run_for_token[result[1]] = run_id
            return result

        def finish_fixture(token):
            """仅在测试中模拟本轮代码修改；真实 driver 与清理仍完整运行。"""
            result = original_wait(token)
            if result!=0:
                return result
            context = manager.run_context(run_for_token[token])
            definition = manager.library.projects[context['project_key']]
            workspace = data/context['workspace_relative']
            reference = json.loads((definition.root/'verification/reference.json').read_text())
            manifest = json.loads(context['manifest_json'])
            actions = {step['checks'][0]['input']['action']:reference['actions'][step['checks'][0]['input']['action']]
                for step in manifest['steps'][:context['next_step_index']+1]}
            shutil.copy2(repository/'project_library/reference_runtime.py',workspace/'fixture_behaviors.py')
            source = (definition.root/'seed/app.py').read_text().replace('def handle(request):','def original_handle(request):')
            insertion = '\nfrom fixture_behaviors import evaluate\nACTIONS = '+repr(actions)+'\ndef handle(request):\n    action=request.get("action","overview")\n    if action in ACTIONS:\n        return evaluate(ACTIONS[action],request,FIELDS)\n    return original_handle(request)\n\n'
            (workspace/'app.py').write_text(source.replace("if __name__ == '__main__':",insertion+"if __name__ == '__main__':"))
            progress = workspace/'fixture-progress.txt'
            before = progress.read_text() if progress.exists() else ''
            progress.write_text(before+context['step_id']+'\n')
            return result

        stack.enter_context(patch.object(runner,'start_run',side_effect=start_fixture))
        stack.enter_context(patch.object(runner,'wait_worker',side_effect=finish_fixture))
        batch = manager.create_batch(account['id'],'真实执行器闭环',['project-001','project-002'])
        manager.transition(batch['id'],'start')
        manager.tick()
        launch_deadline = time.monotonic()+60
        while time.monotonic()<launch_deadline:
            with main.get_db() as connection:
                started_run = connection.execute('SELECT worker_container,status,error FROM runs ORDER BY created_at DESC LIMIT 1').fetchone()
            if started_run and started_run['worker_container']:
                break
            if started_run and started_run['status'] in ('failed','auth_failed','stopped'):
                raise AssertionError(dict(started_run))
            time.sleep(0.1)
        else:
            raise AssertionError('合成项目 driver 未实际启动')
        manager.transition(batch['id'],'pause')
        deadline = time.monotonic()+90
        first = None
        while time.monotonic()<deadline:
            manager.tick()
            first = manager.instance(batch['instances'][0]['id'])
            if first['next_step_index']==1 and manager.batch(batch['id'])['status']=='paused':
                break
            if manager.batch(batch['id'])['status']=='blocked':
                raise AssertionError(manager.batch(batch['id']))
            time.sleep(0.25)
        else:
            raise AssertionError({'message':'第一步未完成','batch':manager.batch(batch['id']),'instance':first})
        directory = data/manager.run_context(first['attempts'][0]['run_id'])['workspace_relative']
        first_seed_path = first['workspace_path']
        assert directory.exists() and (directory/'fixture-progress.txt').read_text()=='step-01\n'
        assert manager.batch(batch['id'])['instances'][1]['workspace_path'] is None
        manager.transition(batch['id'],'start')
        manager.tick()
        launch_deadline = time.monotonic()+60
        while time.monotonic()<launch_deadline:
            with main.get_db() as connection:
                started_run = connection.execute('SELECT worker_container,status,error FROM runs ORDER BY created_at DESC LIMIT 1').fetchone()
            if started_run and started_run['worker_container']:
                break
            if started_run and started_run['status'] in ('failed','auth_failed','stopped'):
                raise AssertionError(dict(started_run))
            time.sleep(0.1)
        else:
            raise AssertionError('合成项目 driver 未实际启动')
        manager.transition(batch['id'],'pause')
        deadline = time.monotonic()+90
        while time.monotonic()<deadline:
            manager.tick()
            second = manager.instance(first['id'])
            if second['next_step_index']==2 and manager.batch(batch['id'])['status']=='paused':
                break
            time.sleep(0.25)
        else:
            raise AssertionError({'message':'第二步未完成','instance':manager.instance(first['id'])})
        assert second['workspace_path']==first_seed_path
        assert (directory/'fixture-progress.txt').read_text()=='step-01\nstep-02\n'
        assert all(item['validation_status']=='passed' and item['execution_released_at'] for item in second['attempts'])
        assert verified.run_session_path(second['attempts'][0]['run_id'])==verified.run_session_path(second['attempts'][1]['run_id'])
        assert second['attempts'][0]['run_id']!=second['attempts'][1]['run_id']
        manager.transition(batch['id'],'stop')
        manager.tick()
        assert directory.exists()
        print('通过：真实 Scheduler→固定账号 driver/tmux→原生主会话→严格清理→独立 Docker 验收→两步累积；未启动项目无目录；合成 CLI，不代表真实模型推理',flush=True)
