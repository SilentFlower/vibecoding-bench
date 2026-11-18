"""隔离真实SSH、Node三角色及原管理HTTP的环境操作验收。"""
import json
import os
import time
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

import main
from runtime_files import atomic_json
from cluster_deployment import node_container_name


def verify_environment_management(testcase, service, runtime, node, account, gateway, root) -> None:
    """沿原HTTP验证所属Node资源、采集配置、快照和实际空闲维护。

    :param testcase: 本次隔离部署的验证器。
    :param service: 原SSH节点服务。
    :param runtime: 中央环境登记。
    :param node: 当前人工归属节点。
    :param account: 本次合成账号。
    :param gateway: 实际Rust网关。
    :param root: Node实际环境目录。
    :return: None；所有数据与调用只在随机隔离部署内。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST') != '1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('环境管理验收仅用于随机隔离部署')
    environment = runtime._row(account['name'], account['id'])
    prefix = '/api/environments/' + environment['environment_id']
    original_identity = json.loads((root / 'home/.claude.json').read_text())
    marker = root / 'home/.cluster-management-preserved.json'
    atomic_json(marker, {'unknown': {'preserved': True}})
    # 原服务已由本次随机部署持有，HTTP夹具仅复用路由，避免再次进入生产启动生命周期。
    http = TestClient(main.app, headers={'Authorization': 'Bearer ' + os.environ['V3_INTERNAL_TOKEN']})
    testcase.addCleanup(http.close)
    connection = service.connection(node['id'])
    execute = connection.execution_environment
    def observed(container, payload, operation):
        """仅记录合成验收的具体操作名和耗时。:return: 原私有结果。"""
        started = time.monotonic()
        print('合成环境管理开始：' + operation, flush=True)
        try:
            return execute(container, payload, operation)
        except Exception as error:
            print('合成环境管理失败类型：' + type(error).__name__, flush=True)
            raise
        finally:
            print('合成环境管理结束：' + operation + ' ' + str(round(time.monotonic() - started, 3)), flush=True)
    with patch.multiple(main, account_runtime=runtime, cluster_service=service, cc2api_client=gateway,
            credential_ownership=None, cluster_runner=None, login_manager=None,
            get_db=service.store.database, _db_lock=service.store.lock, V3_ENABLED=True,
            _quota_identity=lambda current: 'synthetic-quota'), patch.object(connection, 'execution_environment', side_effect=observed):
        def request(method, path, body=None):
            """原管理HTTP必须成功，失败保留有限响应用于定位。:return: 原JSON。"""
            response = http.request(method, path, json=body) if body is not None else http.request(method, path)
            if response.status_code != 200:
                control = service.local_client.containers.get(node_container_name(runtime.deployment, node['node_key']))
                testcase.fail(response.text[:700] + '；Node受限位置：' + control.logs(tail=12).decode(errors='replace'))
            return response.json()
        with patch.object(runtime, '_root', side_effect=AssertionError('远程管理禁止中央HOME')):
            cpu = request('GET', prefix + '/cpu-resources')
            cpus = {**cpu['cpus'], 'cli': 0.75}
            changed = request('POST', prefix + '/cpu-resources', {'expected_generation': cpu['generation'],
                'expected_revision': cpu['revision'], 'cpus': cpus})
            testcase.assertEqual(cpus, changed['cpus'])
            stale = http.post(prefix + '/cpu-resources', json={'expected_generation': cpu['generation'],
                'expected_revision': cpu['revision'], 'cpus': cpu['cpus']})
            testcase.assertEqual(409, stale.status_code)
            request('POST', prefix + '/physical-features/refresh')
            testcase.assertTrue((root / 'runtime/physical-features.json').is_file())
            attempt = str(uuid4())
            snapshot = {'schema_version': 1, 'stage': 'cc_prepared', 'account_id': account['cc2api_account_id'],
                'attempt_id': attempt, 'captured_at_ms': int(time.time() * 1000), 'headers': [], 'body': 'x' * (300 * 1024)}
            atomic_json(root / 'flows/api/cc-prepared' / (attempt + '.json'), snapshot)
            testcase.assertEqual(snapshot, request('GET', f"/internal/v3/native-captures/{account['cc2api_account_id']}/{attempt}"))
            for suffix in ('content-capture', 'criu'):
                current = request('GET', prefix + '/' + suffix)
                testcase.assertTrue(current['supported'], current)
                target = not current['enabled'] if suffix == 'content-capture' else False
                changed = request('POST', prefix + '/' + suffix, {'expected_generation': current['generation'],
                    'expected_revision': current['revision'], 'enabled': target})
                testcase.assertEqual(target, changed['enabled'])
                testcase.assertTrue(changed['applied'], changed)
            request('POST', prefix + '/maintenance', {'operation': 'stop'})
            containers = service.local_client.containers.list(all=True, filters={'label': [
                'vibebench.deployment=' + runtime.deployment, 'vibebench.environment=' + environment['environment_id']]})
            testcase.assertEqual(3, len(containers))
            for container in containers:
                container.reload()
                testcase.assertEqual((False, 0), (container.attrs['State']['Running'], container.attrs['State']['Pid']))
            testcase.assertEqual(cpus, request('GET', prefix + '/cpu-resources')['cpus'])
            request('POST', prefix + '/maintenance', {'operation': 'rebuild'})
        service.prepare_remote(account, runtime, gateway, 'synthetic-quota')
        with patch.object(runtime, '_root', side_effect=AssertionError('远程管理禁止中央HOME')):
            testcase.assertEqual(cpus, request('GET', prefix + '/cpu-resources')['cpus'])
            request('POST', prefix + '/maintenance', {'operation': 'reconcile'})
        testcase.assertEqual(original_identity, json.loads((root / 'home/.claude.json').read_text()))
        testcase.assertEqual({'unknown': {'preserved': True}}, json.loads(marker.read_text()))
        testcase.assertIsNone(gateway._request('GET', f"/admin/runtime/accounts/{account['cc2api_account_id']}/lease")['lease'])
