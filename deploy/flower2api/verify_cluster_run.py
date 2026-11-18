"""真实SSH节点运行原worker及离线CLI，核对自动输入、许可撤销和实际收口。"""
from __future__ import annotations

import hashlib
import faulthandler
import json
import os
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import main
from cluster_deployment import node_container_name
from cluster_execution_store import NodeExecutions
from cluster_quota import RemoteTerminalQuota
from cluster_runner import ClusterRunner
from cluster_terminal_sessions import TerminalSessions
from runtime_files import atomic_json
from verify_cluster_continue import verify_node_continue
from verify_cluster_legacy_project import verify_legacy_project
from verify_cluster_scenario import verify_cluster_scenario
from verify_cluster_development import verify_cluster_development


def verify_node_run(testcase, service, runtime, node: dict, account: dict, gateway) -> None:
    """通过正式Runner和worker完成真实多轮，所有模型响应均由离线替身产生。

    :param testcase: 原隔离断言。
    :param service: 原SSH节点服务。
    :param runtime: 原中央实际环境登记。
    :param node: 本次节点。
    :param account: 本次随机部署合成账号。
    :param gateway: 原真实网关；独立账号使用禁止调用的替身。
    :return: None；失败保留本轮精确诊断并由外层夹具收口。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST') != '1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('普通Run验证仅用于本次隔离Docker部署')
    row = runtime._row(account['name'], account['id'])
    root = Path(node['data_root']) / 'environments' / row['environment_id']
    prefix = root / 'cli/2.1.303'
    if prefix.exists() or prefix.is_symlink():
        raise ValueError('合成Run需要本次全新测试环境')
    program = prefix / 'node_modules/.bin/claude'
    program.parent.mkdir(parents=True, mode=0o755)
    source = (Path(__file__).parent / 'fixtures/mock_cli.py').read_text()
    program.write_text(source.replace('9.9.9 (Synthetic lifecycle fixture)', '2.1.303 (Synthetic lifecycle fixture)'))
    program.chmod(0o755)
    (prefix / '.ready').touch()
    configuration = root / 'home/.synthetic-followups.json'
    ledger = NodeExecutions(service.store, runtime.release_id)
    identity=(json.dumps({'account_id':account['id'],'binding':None,'uuid':'synthetic-account','org':'synthetic-org'},sort_keys=True)
        if os.environ.get('CLUSTER_TEST_REVIEW_REFRESH')=='1' else 'synthetic-quota')
    with ExitStack() as context:
        context.enter_context(patch.multiple(main, get_db=service.store.database, _db_lock=service.store.lock,
            BENCH_DATA=service.data, PROFILES_DIR=service.data / 'profiles', account_runtime=runtime,
            project_iterations=None, credential_ownership=None, _quota_identity=lambda _: identity,
            TIMEOUT_WRAPUP_SEC=0, cluster_service=service))
        local = main.Runner()
        context.callback(local.client.close)
        guard = main.QuotaGuard(local)

        sessions = TerminalSessions(ledger, service, runtime, gateway, main._remote_projects_quota_admit,
            main._projects_quota_release, run_quota_admit=main._remote_execution_quota_admit_locked,
            admission=main._remote_cli_admission)
        context.callback(sessions.close)
        quota = RemoteTerminalQuota(sessions, guard, lambda _: identity)
        sessions.quota_refresh, sessions.quota_finalize = quota.refresh, quota.finalize
        remote = ClusterRunner(sessions, lambda _: identity)
        context.enter_context(patch.multiple(main, quota_guard=guard, cluster_runner=remote,
            cluster_terminal_sessions=sessions))
        # 远程路由必须先于该函数的中央目录/额度挂载副作用。
        context.enter_context(patch.object(local, '_quota_mounts', side_effect=AssertionError('远程Run误用中央挂载')))
        if os.environ.get('CLUSTER_TEST_RUN_DEVELOPMENT')=='1':
            verify_cluster_development(testcase,service,runtime,node,account,local,remote)
            return
        if os.environ.get('CLUSTER_TEST_RUN_SCENARIO')=='1':
            verify_cluster_scenario(testcase,service,runtime,node,account,local,remote)
            return
        if os.environ.get('CLUSTER_TEST_RUN_PROJECT') == '1' or os.environ.get('CLUSTER_TEST_RUN_PLAN') == '1':
            verify_legacy_project(testcase,service,runtime,node,account,local,remote,configuration)
            return
        if os.environ.get('CLUSTER_TEST_RUN_PARALLEL') == '1':
            _verify_parallel_runs(testcase, service, local, remote, ledger, account, root, configuration)
            return
        prompts = ['Build a local lead table.\nUse generated sample rows.',
            'Compare two date windows.\nKeep the generated rows.', 'Export the comparison report.']
        scenarios = ((False,) if os.environ.get('CLUSTER_TEST_RUN_CONTINUE') == '1' else
            (True,) if os.environ.get('CLUSTER_TEST_RUN_RECOVERY') == '1' else (False, True))
        for revoked in scenarios:
            run_id = uuid.uuid4().hex[:12]
            session_id = str(uuid.uuid4())
            atomic_json(configuration, {'session': session_id, 'out_of_order': True, 'busy_seconds': 1,
                'reply_usage': {'input_tokens': 2, 'cache_creation_input_tokens': 3, 'cache_read_input_tokens': 5, 'output_tokens': 7},
                'quota_schedule': [{'after': 0.2, 'five_hour': 25, 'seven_day': 9}]}, 0o644)
            connection = service.store.database()
            try:
                with connection:
                    connection.execute("INSERT INTO runs(id,account_id,task_id,status,run_kind,quota_attempt) VALUES(?,?,1,'running','normal',0)",
                        (run_id, account['id']))
            finally:
                connection.close()
            task = {'id': 1, 'prompt': prompts[0], 'timeout_sec': 90, 'quota_attempt': 0,
                'claude_code_version': '2.1.303', 'claude_effort_level': 'high', 'capture_permission_mode': 'bypassPermissions',
                'capture_full_http': False, 'followup_plan_json': json.dumps(prompts[1:]), 'model_override': 'offline-model'}
            token = None
            try:
                with main._oauth_owner_lock(account['name']):
                    _, token = local.start_run(run_id, account, task)
                execution = remote._row(token)
                scope = execution['record']['scope']
                testcase.assertFalse((service.data / 'environments' / row['environment_id']).exists())
                with main._oauth_owner_lock(account['name']):
                    testcase.assertEqual((token, token), local.start_run(run_id, account, task))
                alias = 'project-' + hashlib.sha256(f"{row['environment_id']}:{run_id}".encode()).hexdigest()[:12]
                turns_path = root / 'projects' / alias / '.synthetic-turns.jsonl'
                deadline = time.monotonic() + 125
                first_seen = False
                while True:
                    status = remote.poll(token)
                    if turns_path.exists() and turns_path.stat().st_size and not first_seen:
                        first_seen = True
                        if revoked:
                            service.connection(node['id']).execution_environment(node_container_name(runtime.deployment, node['node_key']),
                                {**scope, 'reason': 'synthetic_input_revoked'}, 'grant-close')
                    if not status['running']:
                        break
                    if time.monotonic() > deadline:
                        transcript = root / 'runtime/runs' / run_id / 'transcript.log'
                        detail = transcript.read_text(errors='replace')[-2000:] if transcript.exists() else ''
                        raise AssertionError('原节点worker未在期限内结束：' + detail)
                    time.sleep(0.5)
                testcase.assertEqual(45 if revoked else 0, status['exit_code'], status)
                turns = [json.loads(line) for line in turns_path.read_text().splitlines()]
                testcase.assertEqual(prompts[:1] if revoked else prompts, [turn['text'] for turn in turns])
                testcase.assertEqual({'paste'}, {turn['transport'] for turn in turns})
                inputs = Path(node['data_root']) / 'node-inputs' / row['environment_id'] / scope['operation_id']
                receipts = [json.loads(path.read_text()) for path in inputs.glob('*.json') if path.name != 'state.json']
                testcase.assertTrue(all(receipt['scope'] == scope for receipt in receipts))
                testcase.assertEqual(2 if revoked else 4, sum(receipt['status'] == 'sent' for receipt in receipts))
                testcase.assertEqual(1 if revoked else 0, sum(receipt['status'] == 'not_sent' for receipt in receipts))
                testcase.assertIsNone(json.loads((inputs / 'state.json').read_text())['pending_input'])
                testcase.assertEqual(session_id, remote.latest_session(run_id))
                phase = main._public_followup_progress({'id': run_id, 'status': 'running',
                    'followup_plan_json': json.dumps(prompts[1:])})
                testcase.assertEqual('complete' if not revoked else 'pending', phase['phase'])
                transcript = remote.artifact(run_id, 'transcript.log', limit=1024 * 1024)
                testcase.assertIn(b'Fixture', transcript)
                workspace = root / 'projects' / alias
                (workspace / 'result.txt').write_text('原节点中文产物')
                (workspace / 'outside-link').symlink_to(configuration)
                files = remote.files(run_id)
                testcase.assertIn('result.txt', [item['path'] for item in files])
                testcase.assertNotIn('outside-link', [item['path'] for item in files])
                testcase.assertEqual('原节点中文产物', remote.file(run_id, 'result.txt')['text'])
                stats = remote.stats(run_id)
                testcase.assertEqual('claude_session', stats['source'])
                testcase.assertEqual((10, 7) if revoked else (30, 21), (stats['tokens_in'], stats['tokens_out']))
                with patch.object(main, '_require_visible_run'):
                    testcase.assertEqual(files, main.list_workspace(run_id))
                    testcase.assertEqual('原节点中文产物', main.preview_run_file(run_id, 'result.txt')['text'])
                    testcase.assertEqual(stats, main.get_stats(run_id))
                quota.pull(execution)
                guard.consume(account)
                testcase.assertEqual(25, guard.snapshot(account)['windows']['five_hour']['utilization'])
                if revoked and os.environ.get('CLUSTER_TEST_RUN_RECOVERY') == '1':
                    name = node_container_name(runtime.deployment, node['node_key'])
                    control = service.docker(node['id']).containers.get(name)
                    testcase.assertEqual('node-control', control.labels['vibebench.role'])
                    testcase.assertEqual(runtime.deployment, control.labels['vibebench.deployment'])
                    control.kill(signal='SIGKILL')
                    control.start()
                    ready_until = time.monotonic() + 25
                    while True:
                        try:
                            if service.connection(node['id']).agent_health(name).get('state') == 'ready':
                                break
                        except ValueError:
                            pass
                        testcase.assertLess(time.monotonic(), ready_until, '原Run节点进程未恢复')
                        time.sleep(0.1)
                    observed = sessions.node_state(execution['operation_id'])
                    testcase.assertEqual(('reconcile', 'NodeRestart'), (observed['phase'], observed['error_type']))
            except Exception as error:
                if os.environ.get('CLUSTER_TEST_RUN_DIAGNOSTICS') == '1':
                    faulthandler.dump_traceback()
                control = service.docker(node['id']).containers.get(node_container_name(runtime.deployment, node['node_key']))
                transcript = root / 'runtime/runs' / run_id / 'transcript.log'
                detail = transcript.read_text(errors='replace')[-3000:] if transcript.exists() else ''
                raise AssertionError('隔离Run失败；节点调用位置：' + control.logs(tail=15).decode(errors='replace')
                    + '；原worker转录：' + detail) from error
            finally:
                if token is not None:
                    local.cleanup(token, token)
                    stopped = remote._row(token)
                    testcase.assertEqual('closed', stopped['phase'])
                    testcase.assertEqual('closed', stopped['record']['node_receipt']['phase'])
                    if account.get('cc2api_account_id') is None:
                        testcase.assertTrue(stopped['record']['local_admission_released'])
                        testcase.assertIsNone(stopped['record']['lease'])
            testcase.assertEqual([], ledger.active(account['id']))
            if os.environ.get('CLUSTER_TEST_RUN_CONTINUE') == '1':
                verify_node_continue(testcase, service, runtime, node, account, gateway, local, sessions, quota,
                    run_id, session_id, root)


def _verify_parallel_runs(testcase, service, local, remote, ledger, account, root, configuration) -> None:
    """用同一账号两个实际shared作业核对独立输入、会话与额度上下文。

    :param testcase: 原断言。
    :param service: 原中央存储。
    :param local: 实际Runner入口。
    :param remote: 原节点路由。
    :param ledger: 原执行账本。
    :param account: 原合成账号。
    :param root: 原节点实际环境根。
    :param configuration: 本次合成CLI私有配置。
    :return: None；异常也沿原Scope实际停止。
    """
    atomic_json(configuration, {'session_by_run': True, 'busy_seconds': 1,
        'quota_schedule': [{'after': 0.2, 'five_hour': 25, 'seven_day': 9}]}, 0o644)
    jobs = []
    try:
        for index in range(2):
            run_id = uuid.uuid4().hex[:12]
            connection = service.store.database()
            try:
                with connection:
                    connection.execute("INSERT INTO runs(id,account_id,task_id,status,run_kind,quota_attempt) VALUES(?,?,1,'running','normal',0)",
                        (run_id, account['id']))
            finally:
                connection.close()
            prompts = [f'Parallel original {index}.', f'Parallel followup {index}.', f'Parallel final {index}.']
            task = {'id': 1, 'prompt': prompts[0], 'timeout_sec': 100, 'quota_attempt': 0,
                'claude_code_version': '2.1.303', 'claude_effort_level': 'high', 'capture_permission_mode': 'bypassPermissions',
                'capture_full_http': False, 'followup_plan_json': json.dumps(prompts[1:]), 'model_override': 'offline-model'}
            with main._oauth_owner_lock(account['name']):
                _, token = local.start_run(run_id, account, task)
            jobs.append((run_id, token, prompts))
        testcase.assertEqual(2, len(ledger.active(account['id'])))
        testcase.assertTrue(all(remote.poll(token)['running'] for _, token, _ in jobs))
        deadline = time.monotonic() + 130
        while any(remote.poll(token)['running'] for _, token, _ in jobs):
            testcase.assertLess(time.monotonic(), deadline, '同账号原并行worker未在期限内收口')
            time.sleep(0.5)
        for run_id, token, prompts in jobs:
            testcase.assertEqual(0, remote.poll(token)['exit_code'])
            testcase.assertEqual(run_id, remote.latest_session(run_id))
            alias = 'project-' + hashlib.sha256(f'{root.name}:{run_id}'.encode()).hexdigest()[:12]
            turns = [json.loads(line) for line in (root / 'projects' / alias / '.synthetic-turns.jsonl').read_text().splitlines()]
            testcase.assertEqual(prompts, [item['text'] for item in turns])
            scope = remote._row(token)['record']['scope']
            quota_file = root.parent.parent / 'node-quota-scopes' / root.name / (scope['operation_id'] + '.json')
            testcase.assertEqual(scope, json.loads(quota_file.read_text())['scope'])
    finally:
        for _, token, _ in jobs:
            local.cleanup(token, token)
            testcase.assertEqual('closed', remote._row(token)['phase'])
    testcase.assertEqual([], ledger.active(account['id']))
