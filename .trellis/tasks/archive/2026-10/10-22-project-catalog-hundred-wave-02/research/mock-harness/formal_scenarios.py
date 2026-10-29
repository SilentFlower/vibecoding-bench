"""正式场景内容的隔离模拟试跑，业务回答与语义评分均由明确标注的替身提供。"""
import hashlib
import json
import os
import shutil
import threading
import time
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import uvicorn

import main
from account_runtime import AccountRuntime, atomic_json
from project_iteration import ProjectIterationManager
from project_library import ProjectLibrary, read_document, write_document
from project_verifier import ProjectVerifier


# 本工具只回放独立内容任务，不模拟与本批无关的超时修复。


def selected_tasks(details: list[dict]) -> list[dict]:
    """返回真实实例投影中已选择的任务。@param details 实例列表。@return 任务列表。"""
    return [task for detail in details for scene in detail['scenarios'] for task in scene['tasks'] if task['selected']]


def preserve_execution_diagnostics(manager, runtime, facts: dict, target: Path) -> None:
    """按本次真实来源白名单归档 TTY、driver 状态与用量诊断，避开账号凭据。

    :param manager: 本次正式状态机。
    :param runtime: 本次隔离账号运行器。
    :param facts: 已冻结的本轮数据库事实。
    :param target: 本次证据目录。
    :return: None；缺失的可选诊断记入索引。
    """
    destination = target/'execution-diagnostics'
    destination.mkdir(exist_ok=True)
    index = []

    def copy_file(source: Path, saved: Path) -> None:
        """只归档已有普通文件，不穿过指向其他目录的链接。"""
        if source.is_file() and not source.is_symlink():
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, saved)
            index.append({'source': str(source.relative_to(manager.data)),
                'saved': str(saved.relative_to(target)), 'bytes': source.stat().st_size})

    executions = {item['id']: item for item in facts['project_task_executions']}
    owner_root = runtime._root(runtime._row('synthetic', 1))
    run_names = {'transcript.log', 'status.json', 'session-baseline.json', 'project-plan-request.json',
        'project-work.json', 'project-plan-state.json', 'followups.json'}
    job_names = {'claude-exit-code', 'claude-exited', 'process.json', 'process-result.json',
        'claude-completion-state', 'claude-fatal-error', 'claude-api-fatal-error',
        'project-work-action.json', 'project-plan-action.json', 'claude-followup-init'}
    flow_names = {'stats.jsonl', 'cli-quota.jsonl', 'passive-quota.jsonl', 'process-metrics.jsonl',
        'driver.log', 'worker.log', 'status.json', 'transcript.log'}
    for source in facts['project_execution_sources']:
        execution = executions[source['execution_id']]
        run_id = execution['run_id']
        base = destination/run_id/str(source['id'])
        for field in ('request_relative', 'decision_relative', 'work_relative'):
            if source.get(field):
                path = manager.data/source[field]
                copy_file(path, base/'controls'/path.name)
        root = runtime.reviews.root_for_run(run_id) if execution['role'] == 'review' else owner_root
        for name in run_names:
            copy_file(root/'runtime/runs'/run_id/name, base/'runtime'/name)
        handle = hashlib.sha256(source['source'].encode()).hexdigest()[:20]
        for name in job_names:
            copy_file(root/'runtime/jobs'/handle/name, base/'driver'/name)
        flow_root = root/'flows'
        if flow_root.is_dir():
            for path in flow_root.rglob('*'):
                if path.name in flow_names:
                    copy_file(path, destination/'flows'/str(root.relative_to(manager.data))/path.relative_to(flow_root))
    for job in runtime.environment_jobs(runtime._row('synthetic', 1)['environment_id']):
        if not job.get('tmux_socket') or not job.get('run_id'):
            continue
        try:
            child = runtime.reviews.container(job) if job.get('execution_role') == 'project-review' else runtime._container(job['row'])
            captured = child.exec_run(['tmux', '-S', job['tmux_socket'], 'capture-pane', '-p', '-S', '-2000'])
            path = destination/job['run_id']/'active-tmux.txt'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(captured.output)
            index.append({'run_id': job['run_id'], 'tmux_exit_code': captured.exit_code,
                'saved': str(path.relative_to(target))})
        except Exception as error:
            index.append({'run_id': job['run_id'], 'tmux_capture_error': type(error).__name__})
    write_document(destination/'index.json', {'files': index, 'credentials_included': False})


def preserve_evidence(manager, runtime, details: list[dict], evidence: dict) -> None:
    """冻结本次合成数据库、原生会话和公开成果，不复制合成登录凭据。

    :param manager: 本次正式状态机。
    :param runtime: 本次隔离账号运行器。
    :param details: 当前实例投影。
    :param evidence: 本次验证结果。
    :return: None。
    """
    target = Path('/verify/evidence')
    target.mkdir(exist_ok=True)
    usages, artifacts, attempts = [], [], []
    for detail in details:
        usages.append(manager.scenarios.usage(detail['id']))
        for scene in detail['scenarios']:
            for task in scene['tasks']:
                if not task['selected']:
                    continue
                attempts.append(manager.scenarios.attempts(detail['id'], task['id']))
                artifacts.append({'instance_id': detail['id'], **manager.scenarios.artifacts(detail['id'], task['id'])})
    write_document(target/'details.json', details)
    write_document(target/'usage.json', {'synthetic': True, 'measurement': 'fixture-native-log', 'instances': usages})
    write_document(target/'artifacts.json', artifacts)
    write_document(target/'attempts.json', attempts)
    write_document(target/'batches.json', manager.batches())
    write_document(target/'candidate-starts.json', evidence.get('candidate_starts', []))
    tables = ['project_iteration_batches', 'project_instances', 'project_scenario_instances', 'project_scenario_tasks',
        'project_task_attempts', 'project_task_executions', 'project_execution_sources', 'project_work_segments',
        'project_task_deliveries', 'project_evaluation_jobs', 'runs']
    with main.get_db() as connection:
        import sqlite3
        with sqlite3.connect(target/'private-synthetic.sqlite') as saved:
            connection.backup(saved)
        facts = {table: [dict(item) for item in connection.execute('SELECT * FROM '+table+' ORDER BY id')] for table in tables}
    (target/'private-synthetic.sqlite').chmod(0o600)
    write_document(target/'database-facts.json', facts)
    write_document(target/'result.json', evidence)
    preserve_execution_diagnostics(manager, runtime, facts, target)
    if (manager.data/'project-artifacts').is_dir():
        shutil.copytree(manager.data/'project-artifacts', target/'project-artifacts', dirs_exist_ok=True, symlinks=True)
    for source in facts['project_execution_sources']:
        if not source.get('native_relative'):
            continue
        directory = manager.data/source['native_relative']
        if directory.is_dir():
            shutil.copytree(directory, target/'native-sessions'/str(source['id']), dirs_exist_ok=True, symlinks=True)
    for path in (runtime._root(runtime._row('synthetic', 1))/'home/.synthetic-scenarios').glob('*-state.json'):
        shutil.copy2(path, target/path.name)


def verify_formal_scenarios(runtime, client, account: dict, row: dict) -> None:
    """用正式库和真实运行链执行新增任务及材料变化入口。

    :param runtime: 空数据和内部网络中的合成账号运行器。
    :param client: 当前 Docker 客户端。
    :param account: 唯一合成账号。
    :param row: 预留私有评审资源后的固定环境。
    :return: None；断言失败时保留本次证据并非零退出。
    """
    data = runtime.data
    paths = {'BENCH_DATA': data, 'HOST_BENCH_DATA': runtime.host_data, 'DB_PATH': data/'scenario.sqlite',
        'PROFILES_DIR': data/'profiles', 'WORKSPACES_DIR': data/'workspaces', 'FLOWS_DIR': data/'flows',
        'CA_DIR': data/'ca', 'TOPICS_FILE': data/'missing-topics.md'}
    evidence = {'schema': 1, 'status': 'running', 'synthetic': True, 'semantic_assessment': 'mock',
        'token_usage': 'mock', 'native_verification': 'real', 'real_model_calls': 0,
        'real_oauth_calls': 0, 'capacity': 2, 'maximum_holders': 0, 'private_reviews_checked': 0,
        'candidate_starts': [], 'stages': [], 'timeout_observations': [],
        'source_identity': read_document(Path('/verify/source-validation.json'))}
    evidence['source_overlay'] = evidence['source_identity']['source_overlay']
    details, batches, seen_reviews, private_observations = [], [], set(), []
    with ExitStack() as stack:
        for key, value in {**paths, 'V3_ENABLED': True, 'TIMEOUT_WRAPUP_SEC': 0, 'CLAUDE_CODE_VERSION': '9.9.9',
                'login_manager': None, 'continue_manager': None, 'warmup_scheduler': None,
                'project_iterations': None}.items():
            stack.enter_context(patch.object(main, key, value))
        main.init_db()
        verified = AccountRuntime(client, data, runtime.host_data, main.get_db, runtime.fingerprint, None, main._quota_identity)
        stack.callback(verified.heartbeat_pool.shutdown)
        with main.get_db() as connection:
            connection.execute('INSERT INTO accounts(id,name,profile_path,upstream_proxy_scheme,upstream_socks5_host,upstream_socks5_port) VALUES(?,?,?,?,?,?)',
                (account['id'], account['name'], str(data/'profiles'/account['name']), account['upstream_proxy_scheme'],
                    account['upstream_socks5_host'], account['upstream_socks5_port']))
            connection.execute('INSERT INTO account_environments('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')', tuple(row.values()))
        runner = main.Runner()
        scheduler = main.Scheduler(runner)
        guard = main.QuotaGuard(runner)
        for key, value in (('account_runtime', verified), ('runner', runner), ('scheduler', scheduler), ('quota_guard', guard)):
            stack.enter_context(patch.object(main, key, value))
        library = ProjectLibrary(Path('/repo/project_library'))
        identity = read_document(Path('/pilot/catalog-identity.json'))
        assert library.version == identity['version'] and library.digest == identity['digest']
        stage_definitions = read_document(Path('/pilot/stages.json'))
        overrides = read_document(Path('/pilot/recipe-overrides.json'))
        recipes = read_document(Path('/pilot/recipes.json'))
        formal_tasks = {task['id']: task for project_key, project in library.projects.items()
            for scene in project.manifest['scenarios'] for task in scene['tasks']
            if project_key in identity['project_keys']}
        assert set(formal_tasks) == set(recipes) and len(formal_tasks) == identity['tasks']
        manager = ProjectIterationManager(data, library, main.get_db, main._db_lock, scheduler.submit,
            lambda: {'claude_code_version': '9.9.9', 'claude_effort_level': 'high', 'execution_model': 'offline-fixture'},
            main._quota_identity, main._stop_project_run, ProjectVerifier(client, data, runtime.host_data, verified.image),
            scheduler.is_executing, admission=main._project_admission, execution_control=main._project_execution_control,
            schedule_admission=main._project_schedule_admission, concurrency_limit=2)
        verified.set_project_iterations(manager)
        manager.review_refresh = lambda current: verified.reviews.retry_owner_refresh(current, main._refresh_project_review_owner)
        stack.enter_context(patch.object(main, 'project_iterations', manager))
        stack.callback(manager.stop)
        stack.callback(scheduler.stop_window_waits)
        original_start = verified.start_run

        def start(current_account, task, run_id, worker_env, quota_env):
            """仅给模型替身设置答案配方，候选指令及正式运行链保持原样。"""
            context = manager.scenarios.context(run_id)
            if context['role'] == 'candidate':
                directory = verified._root(row)/'home/.synthetic-scenarios'
                directory.mkdir(exist_ok=True)
                os.chown(directory, 1000, 1000)
                key = context['task_key']
                recipe = overrides.get(context['scenario_key'] + ':' + context['entry_key'],
                    overrides.get(context['entry_key'], {})).get(key, recipes[key])
                recipe = stage_definition.get('recipe_overrides', {}).get(key, recipe)
                atomic_json(directory/(context['session_id']+'.json'), {'task_key': key, 'recipe': recipe,
                    'timeout_once': False}, 0o644)
                record = {'task_id': context['scenario_task_id'], 'task_key': key, 'run_id': run_id,
                    'session_id': context['session_id'], 'workspace_relative': context['workspace_relative'],
                    'candidate_budget': manager.scenarios.budget(context['scenario_task_id']), 'at': time.time()}
                evidence['candidate_starts'].append(record)
                write_document(Path('/verify/candidate-starts-live.json'), evidence['candidate_starts'])
            return original_start(current_account, task, run_id, {**worker_env, 'COMPLETION_IDLE_SEC': '1'}, quota_env)

        stack.enter_context(patch.object(verified, 'start_run', side_effect=start))
        server = uvicorn.Server(uvicorn.Config(main.app, host='0.0.0.0', port=8000, lifespan='off', log_level='warning',
            timeout_graceful_shutdown=2))
        service = threading.Thread(target=server.run, daemon=True)
        service.start()

        def stop_service() -> None:
            """关闭本次合成服务。@return None。"""
            server.should_exit = True
            service.join(timeout=5)

        stack.callback(stop_service)
        write_document(Path('/verify/service-started.json'), {'schema': 1, 'status': 'running'})
        policy = {'concurrency': 2, 'active_projects': 3, 'timeout_sec': 60, 'task_budget_sec': 1800,
            'review_timeout_sec': 180, 'review_budget_sec': 720}
        started = time.monotonic()
        first_facts = None
        try:
            for number, stage_definition in enumerate(stage_definitions, 1):
                keys, count, name = stage_definition['project_keys'], stage_definition['count'], stage_definition['name']
                batch = manager.create_batch(account['id'], name, project_keys=keys, policy={**policy, 'concurrency': min(2, len(keys))},
                    scenario_entries=stage_definition.get('scenario_entries'))
                batches.append(batch['id'])
                manager.transition(batch['id'], 'start')
                stage_started = time.monotonic()
                while time.monotonic()-stage_started < 5400:
                    manager.tick()
                    jobs = verified.environment_jobs(row['environment_id'])
                    evidence['maximum_holders'] = max(evidence['maximum_holders'], len(jobs))
                    assert len(jobs) <= 2
                    for job in jobs:
                        if (job.get('execution_role') != 'project-review' or not job.get('review_container_id')
                                or job.get('review_phase') != 'running' or not job.get('process') or job['source'] in seen_reviews):
                            continue
                        child = verified.reviews.container(job)
                        child.reload()
                        candidate = verified._container(row)
                        candidate.reload()
                        private = verified.reviews.root_for_job(job)
                        private_host = runtime.host_data / private.relative_to(data)
                        package = read_document(private/'input/package.json')
                        assert package['resolved_model'] == 'offline-fixture'
                        assert child.attrs['HostConfig']['ReadonlyRootfs']
                        assert child.attrs['HostConfig']['CapDrop'] == ['ALL']
                        assert child.attrs['HostConfig']['NetworkMode'] == 'container:'+row['network_container_id']
                        assert child.attrs['Config']['User'] == '1000:1000'
                        # Docker挂载的Source在宿主命名空间，先换算私有根再比较，父子方向均不能重叠。
                        private_not_mounted = not any(private_host == Path(mount['Source'])
                            or private_host.is_relative_to(Path(mount['Source']))
                            or Path(mount['Source']).is_relative_to(private_host) for mount in candidate.attrs['Mounts'])
                        assert private_not_mounted
                        hidden_input = candidate.exec_run(['test', '-e', '/input/package.json']).exit_code
                        candidate_pid = candidate.exec_run(['readlink', '/proc/self/ns/pid']).output.decode().strip()
                        review_pid = child.exec_run(['readlink', '/proc/self/ns/pid']).output.decode().strip()
                        assert hidden_input != 0 and candidate_pid != review_pid
                        credentials = read_document(private/'home/.claude/.credentials.json')
                        assert 'refreshToken' not in credentials['claudeAiOauth']
                        packet = (private/'input/package.json').read_bytes()
                        mounts = [{key: mount.get(key) for key in ('Source', 'Destination', 'Mode', 'RW')}
                            for mount in candidate.attrs['Mounts']]
                        observation = {'source': job['source'], 'run_id': job['run_id'],
                            'evaluation_job_id': package['job_id'], 'task_id': package['task_id'],
                            'candidate_container_id': candidate.id, 'review_container_id': child.id,
                            'package_sha256': hashlib.sha256(packet).hexdigest(),
                            'response_digest': package['response_digest'], 'basis_digest': package['basis_digest'],
                            'resolved_model': package['resolved_model'], 'readonly_root': child.attrs['HostConfig']['ReadonlyRootfs'],
                            'user': child.attrs['Config']['User'], 'cap_drop': child.attrs['HostConfig']['CapDrop'],
                            'network_mode': child.attrs['HostConfig']['NetworkMode'],
                            'expected_network_mode': 'container:'+row['network_container_id'],
                            'candidate_mounts': mounts,
                            'private_root': str(private_host), 'private_runtime_root': str(private),
                            'runtime_data_root': str(data), 'host_data_root': str(runtime.host_data),
                            'candidate_mounts_sha256': hashlib.sha256(json.dumps(mounts, sort_keys=True).encode()).hexdigest(),
                            'private_not_mounted': private_not_mounted,
                            'candidate_input_visibility_exit_code': hidden_input,
                            'candidate_pid_namespace': candidate_pid, 'review_pid_namespace': review_pid,
                            'credential_top_keys': sorted(credentials),
                            'oauth_credential_keys': sorted(credentials['claudeAiOauth'])}
                        assert hidden_input != 0 and candidate_pid != review_pid
                        packet_path = Path('/verify/evidence/private-review-packages')/str(package['job_id'])/(
                            hashlib.sha256(job['source'].encode()).hexdigest()+'.json')
                        packet_path.parent.mkdir(parents=True, exist_ok=True)
                        packet_path.write_bytes(packet)
                        observation['package_relative'] = str(packet_path.relative_to(Path('/verify/evidence')))
                        private_observations.append(observation)
                        write_document(Path('/verify/evidence/private-review-observations.json'), private_observations)
                        seen_reviews.add(job['source'])
                        evidence['private_reviews_checked'] += 1
                    current = manager.batch(batch['id'])
                    statuses = Counter(task['status'] for item in current['instances'] for scene in manager.instance(item['id'])['scenarios']
                        for task in scene['tasks'] if task['selected'])
                    write_document(Path('/verify/progress.json'), {'schema': 1, 'stage': number, 'batch_ids': batches,
                        'status': current['status'], 'task_counts': dict(statuses), 'elapsed_sec': time.monotonic()-started})
                    if current['status'] == 'completed':
                        break
                    if current['status'] == 'blocked' or statuses.get('blocked'):
                        raise AssertionError('正式模拟试跑受阻：'+json.dumps(current, ensure_ascii=False))
                    time.sleep(0.2)
                else:
                    raise AssertionError('正式模拟试跑超过本阶段截止时间')
                stage_details = [manager.instance(item['id']) for item in current['instances']]
                tasks = selected_tasks(stage_details)
                assert len(tasks) == count and all(task['status'] == 'passed' for task in tasks), stage_details
                details.extend(stage_details)
                evidence['stages'].append({'stage': number, 'batch_id': batch['id'], 'project_keys': keys, 'selected_tasks': count,
                    'batch_status': current['status'], 'task_counts': dict(Counter(task['status'] for task in tasks)),
                    'elapsed_sec': time.monotonic()-stage_started})
                with main.get_db() as connection:
                    first_ids = ([task['id'] for task in selected_tasks(stage_details)] if number == 1
                        else [task['id'] for task in first_facts])
                    facts = [dict(item) for item in connection.execute('SELECT * FROM project_scenario_tasks WHERE id IN ('+
                        ','.join('?' for _ in first_ids)+') ORDER BY id', first_ids)]
                if number == 1:
                    first_facts = facts
                else:
                    assert first_facts == facts
            tasks = selected_tasks(details)
            assert len(tasks) == sum(stage['count'] for stage in stage_definitions)
            assert {task['task_key'] for task in tasks} == set(formal_tasks)
            modifications = [task for task in tasks if task['kind'] == 'modify']
            assert all(task['accepted_checkpoint_digest'] for task in modifications)
            assert all(not task['accepted_checkpoint_digest'] for task in tasks if task['kind'] != 'modify')
            assert all(task['attempt_count'] == 1 for task in tasks)
            assert evidence['private_reviews_checked'] >= len(formal_tasks)
            assert evidence['maximum_holders'] == 2
            with main.get_db() as connection:
                snapshots = [tuple(item) for item in connection.execute('SELECT DISTINCT claude_code_version,claude_effort_level,execution_model FROM runs')]
                review_executions = connection.execute("SELECT COUNT(*) FROM project_task_executions WHERE role='review'").fetchone()[0]
                actual = [dict(item) for item in connection.execute('SELECT id,task_key,status,attempt_count,accepted_checkpoint_digest FROM project_scenario_tasks WHERE selected=1 ORDER BY id')]
                attempts = [dict(item) for item in connection.execute('SELECT task_id,attempt_no,ended_at,result FROM project_task_attempts ORDER BY task_id,attempt_no')]
                assert snapshots == [('9.9.9', 'high', 'offline-fixture')]
            assert evidence['private_reviews_checked'] == review_executions
            evidence['review_executions'] = review_executions
            expected = sorted(tasks, key=lambda task: task['id'])
            assert actual == [{key: task[key] for key in actual[0]} for task in expected]
            assert all(item['ended_at'] is not None and item['result'] in ('passed',) for item in attempts)
            evidence.update(status='passed', tasks=len(tasks), unique_tasks=len(formal_tasks), task_counts=dict(Counter(task['status'] for task in tasks)),
                code_acceptances=len(modifications), first_batch_not_replayed=True, timeout_resume_verified=None,
                catalog_version=library.version, catalog_digest=library.digest, elapsed_sec=time.monotonic()-started,
                batch_ids=batches, db_cross_checked=True)
            preserve_evidence(manager, verified, details, evidence)
            write_document(Path('/verify/browser-ready.json'), {'status': 'ready', 'batch_ids': batches,
                'expected_selected_task_counts': [stage['count'] for stage in stage_definitions], 'stages': evidence['stages']})
            print('新增内容默认及材料分支模拟完成；等待只读浏览器核验。', flush=True)
            deadline = time.monotonic()+1800
            while not Path('/verify/browser-done.json').exists() and time.monotonic() < deadline:
                time.sleep(0.2)
            assert Path('/verify/browser-done.json').exists(), '浏览器验证未在保留窗口内完成'
            browser = read_document(Path('/verify/browser-done.json'))
            assert browser['status'] == 'passed', browser
            evidence['browser_status'] = browser['status']
            preserve_evidence(manager, verified, details, evidence)
            print('通过：本批内容、跨批次去重、私有评审、原生验收与用量机制；真实模型调用 0。', flush=True)
        except BaseException as error:
            evidence.update(status='failed', error=type(error).__name__+': '+str(error), batch_ids=batches,
                elapsed_sec=time.monotonic()-started)
            details = [manager.instance(item['id']) for batch_id in batches for item in manager.batch(batch_id)['instances']]
            preserve_evidence(manager, verified, details, evidence)
            raise
        finally:
            for batch_id in batches:
                manager.transition(batch_id, 'stop')
            for job in verified.environment_jobs(row['environment_id']):
                try:
                    verified.cleanup(job['token'])
                except Exception:
                    pass
            deadline = time.monotonic()+15
            while scheduler._executing and time.monotonic() < deadline:
                time.sleep(0.1)
