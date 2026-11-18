"""真实Rust与SSH节点的受限后台出站验证，只访问隔离合成TLS上游。"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from unittest.mock import Mock, patch

import main
from cluster_quota import RemoteApiQuota


def verify_node_background(testcase, http, admin: dict, service, runtime, account: dict, upstream_root) -> None:
    """核对后台出口、原唯一刷新所有者及提交未知阻断。

    :param testcase: 原隔离测试断言。
    :param http: 实际Rust管理客户端。
    :param admin: 本次私有管理证明。
    :param service: 原中央归属。
    :param runtime: 原中央环境登记器。
    :param account: 原合成账号。
    :param upstream_root: 本次隔离上游证据目录。
    :return: None；保留断言证据。
    """
    remote_id = account['cc2api_account_id']
    url = '/admin/accounts/' + str(remote_id)
    current = http.get(url, headers=admin).json()
    legacy_telemetry = current['request_backend'] == 'legacy'
    row = runtime._row(account['name'], account['id'])
    request = {'protocol': 1, 'operation_id': uuid.uuid4().hex, 'direction': 'attach',
        'identity': {'deployment_id': runtime.deployment, 'environment_id': row['environment_id'],
            'bench_account_id': account['id'], 'device_id': current['device_id'], 'email': current['email'],
            'account_uuid': current['account_uuid'], 'organization_uuid': current['organization_uuid']},
        'source_refresh_sha256': hashlib.sha256(b'synthetic-refresh').hexdigest()}
    for action in ('prepare', 'commit', 'finish'):
        response = http.post(url + '/oauth-ownership', headers=admin, json={**request, 'action': action})
        testcase.assertEqual(200, response.status_code, '合成凭据归属交接失败')
    for action in ('usage', 'test'):
        response = http.post(url + '/' + action, headers=admin)
        testcase.assertEqual(200, response.status_code)
        testcase.assertEqual('ok', response.json().get('status'), response.text[:200])
    response = http.post(url + '/oauth-credentials/resolve', headers=admin,
        json={'min_validity_seconds': 60, 'force_refresh': True})
    testcase.assertEqual(200, response.status_code, '节点固定OAuth刷新失败')
    testcase.assertTrue(response.json()['access_token'].startswith('synthetic-refreshed-'))
    response = http.get(url + '/oauth-ownership', headers=admin)
    testcase.assertEqual('ready', response.json()['ownership']['phase'])
    if legacy_telemetry:
        response = http.put(url, headers=admin, json={'auto_telemetry': True})
        testcase.assertEqual(200, response.status_code)
    # Rust自动遥测容器由legacy消息创建；原生后端继续使用自身遥测合同。
    response = http.post('/admin/tokens', headers=admin,
        json={'name': 'background-telemetry', 'allowed_accounts': str(remote_id)})
    testcase.assertEqual(201, response.status_code)
    response = http.post('/v1/messages', headers={'authorization': 'Bearer ' + response.json()['token']},
        json={'model': 'claude-sonnet-4-6', 'max_tokens': 10,
            'messages': [{'role': 'user', 'content': 'cluster-background-telemetry'}]})
    testcase.assertEqual(200, response.status_code)
    deadline = time.monotonic() + 30
    while True:
        records = [json.loads(line) for line in (upstream_root / 'evidence.jsonl').read_text().splitlines()]
        paths = {item['path'] for item in records if item['kind'] == 'telemetry'}
        if not legacy_telemetry or ('/api/event_logging/v2/batch' in paths and any(path.startswith('/api/eval/') for path in paths)):
            break
        testcase.assertLess(time.monotonic(), deadline, '节点遥测等待超时')
        time.sleep(0.2)
    assignment = service.store.assignment(account['id'])
    environment = runtime._row(account['name'], account['id'])
    network = 'flower2api-' + runtime.deployment + '-node-' + assignment['node_key'][:12]
    network_role = service.local_client.containers.get(environment['network_container_id'])
    network_role.reload()
    sender_ip = network_role.attrs['NetworkSettings']['Networks'][network]['IPAddress']
    peers = {item['peer'] for item in records if item['kind'] == 'proxy' and item['port'] == 443}
    testcase.assertEqual({sender_ip}, peers)
    testcase.assertTrue(any(item['kind'] == 'oauth-usage' for item in records))
    testcase.assertTrue(any(item['kind'] == 'oauth-refresh' for item in records))
    testcase.assertTrue(any(item['kind'] == 'oauth-refresh' and item['host'] == 'platform.claude.com' for item in records))
    testcase.assertTrue(all(item['host'] == 'api.anthropic.com'
        for item in records if item['kind'] in ('oauth-usage', 'telemetry')))
    with patch.multiple(main, get_db=service.store.database, _db_lock=service.store.lock,
            BENCH_DATA=service.data, PROFILES_DIR=service.data / 'profiles', account_runtime=None,
            _quota_identity=lambda _: 'synthetic-quota'):
        guard = main.QuotaGuard(Mock())
        guard.remote_api = RemoteApiQuota(service, runtime, lambda _: 'synthetic-quota')
        guard.consume(account)
        testcase.assertEqual(12, guard.snapshot(account)['windows']['five_hour']['utilization'])
    refresh_count = sum(item['kind'] == 'oauth-refresh' for item in records)
    (upstream_root / 'oauth-drop-response').touch()
    for _ in range(2):
        response = http.post(url + '/oauth-credentials/resolve', headers=admin,
            json={'min_validity_seconds': 60, 'force_refresh': True})
        testcase.assertEqual(503, response.status_code)
    response = http.get(url + '/oauth-ownership', headers=admin)
    testcase.assertEqual('reconcile', response.json()['ownership']['phase'])
    records = [json.loads(line) for line in (upstream_root / 'evidence.jsonl').read_text().splitlines()]
    testcase.assertEqual(refresh_count + 1, sum(item['kind'] == 'oauth-refresh' for item in records))
    testcase.assertEqual({}, service.transports.active)
