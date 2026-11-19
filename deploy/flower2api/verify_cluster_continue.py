"""真实SSH与Node私有WS续聊验证，使用原Run的离线CLI会话。"""
from __future__ import annotations

import json
import os
import select
import time
from pathlib import Path
from unittest.mock import patch

import main
from cluster_continue_runner import ClusterContinues
from cluster_deployment import node_container_name
from run_artifacts import ordinary_run_alias
from runtime_files import atomic_json


def verify_node_continue(testcase, service, runtime, node, account, gateway, local, sessions, quota, run_id, session_id, root) -> None:
    """沿原HTTP准备、实际WS/PTY输入与原停止回执验证续聊。

    :param testcase: 原隔离断言。
    :param service: 原中央节点服务。
    :param runtime: 原中央运行时登记。
    :param node: 本次合成节点。
    :param account: 原账号。
    :param gateway: 原唯一网关所有者。
    :param local: 原Runner。
    :param sessions: 原中央许可协调器。
    :param quota: 原远程额度镜像。
    :param run_id: 已完成的原Run。
    :param session_id: 原实际Claude会话。
    :param root: 原环境物理根。
    :return: None；停止未知仍保留原Scope账本。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST') != '1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('续聊验证仅用于本次隔离部署')
    connection = service.store.database()
    try:
        with connection:
            connection.execute("UPDATE runs SET status='success',claude_code_version='2.1.303',claude_effort_level='high',"
                "capture_permission_mode='bypassPermissions',execution_model='offline-model' WHERE id=?", (run_id,))
        active_account = dict(connection.execute('SELECT * FROM accounts WHERE id=?', (account['id'],)).fetchone())
    finally:
        connection.close()
    continues = ClusterContinues(sessions, lambda _: 'synthetic-quota')
    manager = main.ContinueManager(local)
    bridge, session = None, None
    quota_mode = os.environ.get('CLUSTER_TEST_CONTINUE_QUOTA') == '1'
    configuration = root / 'home/.synthetic-followups.json'
    if quota_mode:
        value = json.loads(configuration.read_text())
        value['quota_schedule'] = [{'after': 0.2, 'five_hour': 100, 'seven_day': 9, 'five_hour_reset_seconds': 3}]
        atomic_json(configuration, value, 0o644)
    with patch.multiple(main, cluster_continues=continues, continue_manager=manager, cc2api_client=gateway):
        try:
            prepared = main.continue_run_start(run_id)
            session = manager.get(prepared['session_id'])
            testcase.assertEqual(session_id, session.session_id)
            testcase.assertEqual('running', session.status)
            execution = continues._row(session.worker_id)
            scope = execution['record']['scope']
            testcase.assertEqual(f'continue:{session.sid}:0', scope['source'])
            testcase.assertFalse(execution['record']['grant']['lease']['shared_cli'] if scope['gateway_account_id'] is not None else False)
            bridge = continues.open(session.worker_id)
            _wait_banner(testcase, bridge)
            alias = ordinary_run_alias(root.name, run_id)
            # 中央没有远程物理目录；别名只沿既有摘要规则供隔离断言定位。
            turns = root / 'projects' / alias / '.synthetic-turns.jsonl'
            original = len(turns.read_text().splitlines())
            prompt = 'Continue the original local report.\nKeep the same generated rows.'
            data = b'\x1b[200~' + prompt.encode() + b'\x1b[201~\r'
            testcase.assertTrue(manager.send_input(session, session.generation, bridge, data))
            deadline = time.monotonic() + 10
            while len(turns.read_text().splitlines()) == original:
                testcase.assertLess(time.monotonic(), deadline, '原PTY输入未到达原CLI')
                time.sleep(0.1)
            messages = [json.loads(line) for line in turns.read_text().splitlines()]
            testcase.assertEqual(prompt, messages[-1]['text'])
            testcase.assertEqual(session_id, messages[-1]['session'])
            with patch.object(main, '_account_run_window', return_value={'allowed': False}):
                for denied in (b'late text\r', b'late binary\0\r'):
                    testcase.assertFalse(manager.send_input(session, session.generation, bridge, denied))
            testcase.assertEqual(original + 1, len(turns.read_text().splitlines()))
            expected_count = original + 1
            if quota_mode:
                deadline = time.monotonic() + 20
                while True:
                    quota.pull(execution)
                    main.quota_guard.consume(account)
                    if main.quota_guard.snapshot(account)['windows']['five_hour']['utilization'] == 100:
                        break
                    testcase.assertLess(time.monotonic(), deadline, '续聊实际额度样本未到达原QuotaGuard')
                    time.sleep(0.1)
                old_generation = session.generation
                testcase.assertFalse(manager.send_input(session, old_generation, bridge, b'quota denied input\r'))
                testcase.assertEqual(('quota_wait', 1, None), (session.status, session.generation, session.worker_id))
                testcase.assertEqual('closed', sessions.ledger.get(execution['operation_id'])['phase'])
                bridge.close()
                value = json.loads(configuration.read_text())
                value['quota_schedule'] = [{'after': 0.2, 'five_hour': 25, 'seven_day': 9}]
                atomic_json(configuration, value, 0o644)
                session.connected = True
                deadline = time.monotonic() + 10
                while not main.quota_guard.snapshot(account)['retry_ready']:
                    testcase.assertLess(time.monotonic(), deadline, '真实额度窗口尚未到期')
                    time.sleep(0.1)
                manager.quota_tick(active_account)
                testcase.assertEqual('running', session.status)
                testcase.assertEqual(session_id, session.session_id)
                bridge = continues.open(session.worker_id)
                _wait_banner(testcase, bridge)
                testcase.assertFalse(manager.send_input(session, old_generation, bridge, b'old generation input\r'))
                testcase.assertTrue(manager.send_input(session, session.generation, bridge, b'New input after quota recovery.\r'))
                expected_count += 1
                deadline = time.monotonic() + 10
                while len(turns.read_text().splitlines()) < expected_count:
                    testcase.assertLess(time.monotonic(), deadline, '原会话额度恢复后的新输入未到达CLI')
                    time.sleep(0.1)
                testcase.assertEqual(expected_count, len(turns.read_text().splitlines()))
                execution = continues._row(session.worker_id)
                scope = execution['record']['scope']
                testcase.assertEqual(f'continue:{session.sid}:1', scope['source'])
            bridge.resize(50, 140)
            if os.environ.get('CLUSTER_TEST_CONTINUE_RECOVERY') == '1':
                name = node_container_name(runtime.deployment, node['node_key'])
                control = service.docker(node['id']).containers.get(name)
                testcase.assertEqual(runtime.deployment, control.labels['vibebench.deployment'])
                control.kill(signal='SIGKILL'); control.start()
                deadline = time.monotonic() + 25
                while True:
                    try:
                        if service.connection(node['id']).agent_health(name).get('state') == 'ready':
                            break
                    except ValueError:
                        pass
                    testcase.assertLess(time.monotonic(), deadline, '原续聊节点未恢复')
                    time.sleep(0.1)
                testcase.assertEqual('reconcile', sessions.node_state(execution['operation_id'])['phase'])
            else:
                sessions._call(execution, 'grant-close', {**scope, 'reason': 'synthetic_continue_revoked'})
                with testcase.assertRaises(ValueError):
                    manager.send_input(session, session.generation, bridge, b'forbidden after revoke\r')
                receipts = list((Path(node['data_root']) / 'node-continues' / scope['environment_id'] / scope['operation_id']).glob('*.json'))
                not_sent = [json.loads(path.read_text()) for path in receipts if path.name not in ('execution.json', 'pty.json', 'input-state.json')]
                testcase.assertEqual(1, sum(item['status'] == 'not_sent' for item in not_sent))
                testcase.assertEqual(expected_count, len(turns.read_text().splitlines()))
        finally:
            if bridge is not None:
                bridge.close()
            if session is not None:
                manager.cleanup(session.sid)
                testcase.assertIsNone(manager.get(session.sid))
                testcase.assertEqual([], sessions.ledger.active(account['id']))
            continues.close()


def _wait_banner(testcase, bridge) -> None:
    """等待原CLI实际输出，不向尚未启动的PTY预存输入。:param testcase: 原断言。:param bridge: 原PTY。:return: None。"""
    output, deadline = bytearray(), time.monotonic() + 15
    while b'Synthetic task pane' not in output:
        testcase.assertLess(time.monotonic(), deadline, '原续聊PTY未返回真实启动输出')
        if select.select([bridge], [], [], 0.2)[0]:
            data = bridge.recv(4096)
            testcase.assertTrue(data, '原PTY在准备期间关闭')
            output.extend(data)
