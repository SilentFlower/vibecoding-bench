"""随机隔离部署的真实 Node 停机换批与原 HOME 保留验证。"""
import json
import os
from pathlib import Path
from unittest.mock import patch

from cluster_deployment import node_container_name
from cluster_node_ops import node_action
from runtime_files import atomic_json


def verify_node_upgrade(testcase, service, runtime, node, account, gateway, root: Path) -> None:
    """以已冻结的两个测试批次验证原停止实例重建合同。

    :param testcase: 随机 cluster-test 部署的验证器。
    :param service: 实际中央 SSH 节点服务。
    :param runtime: 本次中央运行时。
    :param node: 原已准备节点。
    :param account: 合成独立账号。
    :param gateway: 禁止使用 Gateway 的原边界。
    :param root: 原 Node 实际账号环境。
    :return: None；所有操作限于本次隔离部署。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST') != '1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('节点换批验证只用于随机隔离部署')
    target_release = os.environ['CLUSTER_TEST_TARGET_RELEASE']
    target_control = os.environ['CLUSTER_TEST_TARGET_CONTROL_IMAGE']
    target_account = os.environ['CLUSTER_TEST_TARGET_ACCOUNT_IMAGE']
    client = service.local_client
    name = node_container_name(runtime.deployment, node['node_key'])
    old_control = client.containers.get(name).id
    original = json.loads((root / 'home/.claude.json').read_text())
    path = root / 'home/.claude/.credentials.json'
    credentials = json.loads(path.read_text())
    credentials['claudeAiOauth']['refreshToken'] = 'synthetic-current-node-upgrade-rt'
    credentials['unknown_upgrade_field'] = {'preserved': True}
    atomic_json(path, credentials)
    os.chown(path, 1000, 1000)
    with service.store.database() as connection:
        generation = connection.execute('SELECT generation FROM account_environments WHERE account_id=?', (account['id'],)).fetchone()[0]
    data = root.parents[1]
    node_action(data, data, 'stop', client=client)
    with patch.dict(os.environ, {'V3_RELEASE': target_release, 'V3_ACCOUNT_RELEASE': target_release,
            'V3_CONTROL_IMAGE': target_control, 'V3_ACCOUNT_IMAGE': target_account}):
        runtime.release_id = target_release
        runtime.account_release_id = target_release
        runtime.image = target_account
        service.prepare_node(node['id'], node['revision'])
        result = service.prepare_remote_cli(account, runtime, gateway, 'synthetic-quota')
    control = client.containers.get(name)
    testcase.assertNotEqual(old_control, control.id)
    testcase.assertEqual(target_release, control.labels['vibebench.release'])
    testcase.assertGreater(result['environment']['generation'], generation)
    testcase.assertEqual(original, json.loads((root / 'home/.claude.json').read_text()))
    current = json.loads(path.read_text())
    testcase.assertEqual('synthetic-current-node-upgrade-rt', current['claudeAiOauth']['refreshToken'])
    testcase.assertEqual({'preserved': True}, current['unknown_upgrade_field'])
    target = client.images.get(target_account).id
    for column in ('container_id', 'network_container_id', 'sender_container_id'):
        testcase.assertEqual(target, client.containers.get(result['environment'][column]).attrs['Image'])
