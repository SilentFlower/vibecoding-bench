"""隔离Docker夹具内使用合成CLI验证真实节点终端，模型出口保持离线。"""
from __future__ import annotations

import json
import hashlib
import os
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import main
from cluster_deployment import node_container_name
from cluster_execution_grants import ExecutionScope
from cluster_execution_store import NodeExecutions
from cluster_projects_terminal import ClusterProjectsTerminal
from cluster_quota import RemoteTerminalQuota
from cluster_terminal import TerminalWork
from cluster_terminal_sessions import TerminalSessions
from project_library import ProjectLibrary, materialize_snapshot, safe_relative, snapshot_tree
from projects_runtime import ProjectsTerminal
from projects_catalog import ProjectsCatalog


_SYNTHETIC_CLAUDE = '''#!/usr/bin/env python3
"""仅在本次随机测试账号内运行的离线合成TTY。"""
import json, os, sys, tty, uuid
from pathlib import Path
if '--version' in sys.argv:
    print('2.1.303')
    raise SystemExit(0)
flag = '--resume' if '--resume' in sys.argv else '--session-id'
session = sys.argv[sys.argv.index(flag) + 1]
directory = Path.home() / '.claude/projects' / os.getcwd().replace('/', '-')
directory.mkdir(parents=True, exist_ok=True)
native = directory / (session + '.jsonl')
with native.open('a') as output:
    output.write(json.dumps({'type':'assistant','sessionId':session,'uuid':uuid.uuid4().hex,
        'message':{'role':'assistant','content':'节点合成终端就绪'}},ensure_ascii=False)+'\\n')
tty.setraw(sys.stdin.fileno())
os.write(1, b'\\x1b[?2004h')
os.write(1, '节点合成终端就绪\\r\\n'.encode())
data = b''
while True:
    value = os.read(0, 1)
    if not value:
        break
    data += value
    pasting = b'\\x1b[200~' in data and b'\\x1b[201~' not in data
    if value == b'\\r' and not pasting:
        text = data.replace(b'\\x1b[200~',b'').replace(b'\\x1b[201~',b'').decode().strip('\\r')
        with native.open('a') as output:
            output.write(json.dumps({'type':'user','sessionId':session,'uuid':uuid.uuid4().hex,
                'message':{'role':'user','content':text}},ensure_ascii=False)+'\\n')
        os.write(1, ('节点已收到：'+text+'\\r\\n').encode())
        data = b''
'''


def verify_node_terminal(testcase, service, runtime, node: dict, account: dict, gateway) -> None:
    """真实SSH、原Pi监督器和Rust租约验证单次输入与期限隔离。

    :param testcase: 原隔离unittest断言。
    :param service: 原随机测试部署的节点服务。
    :param runtime: 原中央账号环境登记器。
    :param node: 原已准备SSH节点。
    :param account: 合成账号。
    :param gateway: 当前实际Rust网关的受信私有客户端。
    :return: None；所有进程和资料由原随机部署夹具精确收口。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST') != '1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('合成终端验证仅用于本次隔离Docker部署')
    assignment = service.store.assignment(account['id'])
    row = runtime._row(account['name'], account['id'])
    root = Path(node['data_root']) / 'environments' / row['environment_id']
    prefix = root / 'cli/2.1.303'
    if prefix.exists() or prefix.is_symlink():
        raise ValueError('合成CLI需要本次全新测试环境')
    program = prefix / 'node_modules/.bin/claude'
    program.parent.mkdir(parents=True, mode=0o755)
    program.write_text(_SYNTHETIC_CLAUDE)
    program.chmod(0o755)
    (prefix / '.ready').touch()
    library = ProjectLibrary(Path(__file__).resolve().parents[2] / 'resources/project-library')
    project = library.projects['python-frontmatter']
    objective = next(task for scenario in project.manifest['scenarios'] for task in scenario['tasks']
        if task.get('development_cycle') in ('feature', 'bug'))
    work = TerminalWork(id=uuid.uuid4().hex, account_id=account['id'], generation=1, session_id=str(uuid.uuid4()),
        project_key='python-frontmatter', objective_id=objective['id'], library_digest=library.digest,
        settings_json=json.dumps({'claude_code_version': '2.1.303', 'claude_effort_level': 'high'}),
        remaining_sec=180, created_at=time.time())
    source = 'projects:' + work.id + ':1'
    scope = ExecutionScope(operation_id=uuid.uuid4().hex, node_key=node['node_key'], account_id=account['id'],
        gateway_account_id=account['cc2api_account_id'], environment_id=row['environment_id'],
        assignment_revision=assignment['revision'], generation=row['generation'], source=source, role='projects')
    connection = service.connection(node['id'])
    container = node_container_name(runtime.deployment, node['node_key'])

    def call(operation, value):
        response = connection.execution_environment(container, value, operation)
        return response['terminal'] if operation.startswith('terminal-') else response['record']

    ledger = NodeExecutions(service.store, runtime.release_id)
    context = ExitStack()
    context.enter_context(patch.multiple(main, get_db=service.store.database, _db_lock=service.store.lock,
        BENCH_DATA=service.data, PROFILES_DIR=service.data / 'profiles', account_runtime=None,
        _quota_identity=lambda _: 'synthetic-quota'))
    guard = main.QuotaGuard(Mock())

    def admit(current, original_source):
        if not guard.admit(current, original_source, warmup=True, workload='warmup'):
            raise ValueError('合成执行尚未取得原中央额度许可')
        return 'synthetic-quota'

    sessions = TerminalSessions(ledger, service, runtime, gateway, admit,
        lambda current, original_source, unstarted: guard.release(current, original_source, unstarted=unstarted))
    quotas = RemoteTerminalQuota(sessions, guard, lambda _: 'synthetic-quota')
    sessions.quota_refresh = quotas.refresh
    installed = library.install(service.data)
    catalog = ProjectsCatalog(Path(__file__).resolve().parents[2] / 'resources/project-research', installed)
    local = ProjectsTerminal(runtime, catalog, None, None)
    terminal = ClusterProjectsTerminal(local, sessions, lambda _: 'synthetic-quota')
    try:
        original_work = {**work.model_dump(exclude={'has_baseline'}), 'baseline_json': None, 'status': 'running',
            'library_root': str(installed.root), 'definition_json': json.dumps(objective)}
        location = terminal.start(account, original_work)
        started = ledger.get(location['remote_execution'])
        scope = ExecutionScope.model_validate(started['record']['scope'])
        testcase.assertEqual('running', started['phase'], started)
        testcase.assertEqual(location, terminal.start(account, original_work))
        baseline_id = uuid.uuid4().hex
        baseline = sessions.snapshot(scope.operation_id, baseline_id)
        workspace_relative = started['record']['node_receipt']['result']['workspace']
        workspace = Path(node['data_root']) / safe_relative(workspace_relative)
        testcase.assertEqual(snapshot_tree(workspace), baseline)
        flows = (root / 'flows' / ('group-' + hashlib.sha256(('projects/' + work.id).encode()).hexdigest()[:20])
            / 'executions' / hashlib.sha256(scope.source.encode()).hexdigest()[:20] / 'cli/cli-quota.jsonl')
        flows.write_text(json.dumps({'source': 'cli:' + scope.source, 'identity': 'synthetic-quota', 'origin': 'cli',
            'ts': time.time(), 'rate_limits': {'five_hour': {'used_percentage': 25, 'resets_at': time.time() + 600}}}) + '\n')
        sessions.renew(scope.operation_id)
        testcase.assertEqual(25, guard.snapshot(account)['windows']['five_hour']['utilization'])
        node_gate = json.loads((Path(node['data_root']) / 'quota' / str(account['id']) / 'state.json').read_text())
        testcase.assertEqual(25, node_gate['windows']['five_hour']['utilization'])
        deadline = time.monotonic() + 15
        while True:
            observed = sessions.read(scope.operation_id, 'observe', cursor=0)
            if '节点合成终端就绪' in observed['screen']:
                break
            testcase.assertLess(time.monotonic(), deadline, '合成终端画面未就绪')
            time.sleep(0.1)
        operation = uuid.uuid4().hex
        payload = {'scope': scope.model_dump(), 'operation_id': operation, 'text': '节点输入第一行\n节点输入第二行',
            'keys': [], 'submit': True}
        receipt = sessions.send(scope.operation_id, operation, payload['text'], [], True)
        testcase.assertEqual('sent', receipt['status'])
        testcase.assertEqual(receipt, sessions.send(scope.operation_id, operation, payload['text'], [], True))
        deadline = time.monotonic() + 10
        while True:
            conversation = sessions.read(scope.operation_id, 'conversation')
            inputs = [item for item in conversation if item['role'] == 'user']
            if inputs:
                break
            testcase.assertLess(time.monotonic(), deadline, '原生会话尚未确认合成输入')
            time.sleep(0.1)
        testcase.assertEqual(1, len(inputs))
        testcase.assertIn('节点输入第一行', inputs[0]['content'])
        testcase.assertIn('节点输入第二行', inputs[0]['content'])
        testcase.assertEqual(baseline, sessions.snapshot(scope.operation_id, baseline_id))
        with testcase.assertRaises(ValueError):
            sessions.snapshot(scope.operation_id, uuid.uuid4().hex)
        (workspace / 'cluster-snapshot-probe.txt').write_text('所属节点上的真实源码对象\n')
        submission_id = uuid.uuid4().hex
        objects = service.data / 'cluster-snapshot-verification/objects'
        candidate = sessions.snapshot(scope.operation_id, submission_id, objects)
        testcase.assertEqual(snapshot_tree(workspace), candidate)
        restored = service.data / 'cluster-snapshot-verification/candidate'
        materialize_snapshot(candidate, objects, restored)
        testcase.assertEqual('所属节点上的真实源码对象\n', (restored / 'cluster-snapshot-probe.txt').read_text())
        inspected = sessions.control(scope.operation_id, 'inspect')
        testcase.assertEqual(scope.source, inspected['source'])
        testcase.assertIn(inspected['state'], ('T', 't', 'Z'))
        testcase.assertTrue(all(process['state'] in ('T', 't', 'Z') for process in inspected['processes']))
        testcase.assertEqual(candidate, sessions.snapshot(scope.operation_id, submission_id, objects))
        current_work = {**original_work, 'runtime_json': json.dumps(location)}
        report = terminal.verify_program(current_work, candidate, service.data / 'projects/submissions' / submission_id,
            current_work, answer='当前候选是原冻结源码基线，独立程序验收应识别原业务缺陷')
        testcase.assertEqual('failed', report['status'], report)
        testcase.assertTrue(list((service.data / 'cluster-verifications').glob('*/*/report.json')))
        capture = terminal.capture(current_work)
        testcase.assertEqual(work.id, capture['work_id'])
        testcase.assertEqual('projects', capture['namespace'])
        sessions.control(scope.operation_id, 'resume')
        testcase.assertEqual('running', ledger.get(scope.operation_id)['phase'])
        sessions.close()
        remaining = max(0, ledger.get(scope.operation_id)['record']['grant']['not_after'] - time.time() + 1)
        time.sleep(remaining)
        observed = sessions.read(scope.operation_id, 'observe', cursor=0)
        testcase.assertTrue(observed['running'])
        with testcase.assertRaises(ValueError):
            call('terminal-send', {**payload, 'operation_id': uuid.uuid4().hex, 'text': '过期后禁止新输入'})
        testcase.assertEqual(receipt, sessions.read(scope.operation_id, 'input', input_id=operation))
        control = service.docker(node['id']).containers.get(container)
        testcase.assertEqual(runtime.deployment, control.labels['vibebench.deployment'])
        testcase.assertEqual('node-control', control.labels['vibebench.role'])
        control.kill(signal='SIGKILL')
        control.start()
        deadline = time.monotonic() + 25
        while True:
            try:
                health = connection.agent_health(container)
                if health.get('state') == 'ready':
                    break
            except ValueError:
                pass
            testcase.assertLess(time.monotonic(), deadline, '原节点控制进程重启未就绪')
            time.sleep(0.1)
        restarted = call('terminal-get', scope.model_dump())
        testcase.assertEqual('reconcile', restarted['phase'])
        testcase.assertEqual('NodeRestart', restarted['error_type'])
    finally:
        try:
            sessions.close()
            original = ledger.by_source(account['id'], source, active_only=False)
            if original is not None:
                stopped = sessions.stop(original['operation_id'])
                testcase.assertEqual('closed', stopped['phase'])
                testcase.assertEqual('closed', stopped['record']['node_receipt']['phase'])
                if account['cc2api_account_id'] is None:
                    testcase.assertTrue(stopped['record']['local_admission_released'])
                    testcase.assertIsNone(stopped['record']['lease'])
                    testcase.assertIsNone(stopped['record']['lease_released'])
                else:
                    testcase.assertTrue(stopped['record']['lease_released']['released'])
                actual = runtime._row(account['name'], account['id'])
                cli = service.docker(node['id']).containers.get(actual['container_id'])
                testcase.assertEqual(1, cli.exec_run(['python3', '-I', '/usr/local/bin/v3-cli-control', 'status']).exit_code)
        finally:
            context.close()
