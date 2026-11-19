"""同一真实 Rust 网关的双账号、双 SSH Node JSON/SSE 位置核对。"""
import json
import os
import shutil
from unittest.mock import patch

from cluster_nodes import NodeCreate
from runtime_files import atomic_json
import test_cluster_ssh as ssh_fixture


def verify_two_node_gateway(testcase, service, runtime, source, account, upstream, upstream_root,
                            configuration, backend, secondary_fixtures) -> None:
    """在原统一网关内按原令牌范围分别完成两个节点的请求。

    :param testcase: 随机隔离部署的验证器。
    :param service: 当前真实节点服务。
    :param runtime: 原中央运行时。
    :param source: 第一个已准备节点。
    :param account: 第一个合成账号。
    :param upstream: 本地合成 HTTPS/代理服务。
    :param upstream_root: 合成 TLS 证据根。
    :param configuration: 原上游代理配置。
    :param backend: 本次明确请求后端。
    :param secondary_fixtures: 随机 SSH 夹具的原清理所有者。
    :return: None；只访问隔离部署与本地合成上游。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST') != '1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('双节点网关验证只用于随机隔离部署')
    fixture = ssh_fixture.ClusterSshTests(methodName='runTest')
    secondary_fixtures.append(fixture)
    fixture.setUp()
    target = service.register(NodeCreate(**{**fixture.config.model_dump(), 'data_root': str(fixture.root / 'remote'),
        'private_key': fixture.identity.read_text()}))
    testcase.prepare_network(service.local_client, runtime.deployment, target)
    target_network = 'flower2api-' + runtime.deployment + '-node-' + target['node_key'][:12]
    service.local_client.networks.get(target_network).connect(upstream, aliases=['cluster-test-proxy'])
    service.prepare_node(target['id'], target['revision'])
    with service.store.database() as connection:
        cursor = connection.execute("INSERT INTO accounts(name,profile_path,cc2api_account_id) VALUES('synthetic_second','profiles/synthetic_second',999)")
        other = dict(connection.execute('SELECT * FROM accounts WHERE id=?', (cursor.lastrowid,)).fetchone())
    profile = service.data / other['profile_path']
    atomic_json(profile / '.claude.json', {'userID': 'b' * 64, 'oauthAccount': {
        'emailAddress': 'synthetic-second@example.invalid', 'accountUuid': 'synthetic-second', 'organizationUuid': 'synthetic-org'}})
    atomic_json(profile / '.credentials.json', json.loads((service.data / account['profile_path'] / '.credentials.json').read_text()))
    assignment=service.assign_initial(other, runtime, target['id'], 1)
    row=runtime._row(other['name'],other['id'])
    target_root=fixture.root/'remote/environments'/row['environment_id']
    atomic_json(target_root/'runtime/node-assignment.json',{'protocol':1,'node_key':target['node_key'],
        'account_id':other['id'],'environment_id':row['environment_id'],'revision':assignment['revision'],'phase':'ready'})
    shutil.copyfile(upstream_root/'ca.der',target_root/'runtime/verification-ca.der')
    observed = set()
    register = service.transports.register
    def remember(binding):
        """记录实际准备完成且交给转发器的原账号/节点。:return: 原登记结果。"""
        observed.add((binding.account_id, binding.node_key))
        return register(binding)
    network = 'flower2api-' + runtime.deployment + '-node-' + source['node_key'][:12]
    with patch.object(service.transports, 'register', side_effect=remember):
        testcase.verify_gateway(service.local_client, service, runtime, account, upstream_root,
            network, configuration, backend, extra_accounts=[other])
    for selected in (account, other):
        row = runtime._row(selected['name'], selected['id'])
        summary = service.remote_summary(row, runtime, '2.1.293')
        testcase.assertTrue(summary['node_observed'], summary)
        testcase.assertIsInstance(summary['content_capture'], dict)
        testcase.assertIsInstance(summary['criu'], dict)
    testcase.assertEqual({(account['id'], source['node_key']), (other['id'], target['node_key'])}, observed)
    testcase.assertNotEqual(source['node_key'], target['node_key'])
