"""随机隔离部署的真实 Node 停机换批与原 HOME 保留验证。"""
import json
import os
import time
import uuid
from pathlib import Path
from unittest.mock import patch
from system_update_gate import DeploymentGate

from cluster_deployment import node_container_name
from cluster_node_ops import node_action
from cluster_synchronization import NodeSynchronization
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
    automatic = os.environ.get('CLUSTER_TEST_AUTO_UPGRADE') == '1'
    if automatic:
        service.synchronization = NodeSynchronization(service, runtime, gateway, lambda account: 'synthetic-quota', lambda account: '2.1.293')
    else:
        node_action(data, data, 'stop', client=client)
    with patch.dict(os.environ, {'V3_RELEASE': target_release,
            'V3_CONTROL_IMAGE': target_control, 'V3_ACCOUNT_IMAGE': target_account,
            'V3_ACCOUNT_RELEASE': os.environ.get('CLUSTER_TEST_TARGET_ACCOUNT_RELEASE', target_release)}):
        runtime.release_id = target_release
        runtime.account_release_id = os.environ.get('CLUSTER_TEST_TARGET_ACCOUNT_RELEASE', target_release)
        runtime.image = target_account
        service.prepare_node(node['id'], node['revision'])
        wait_node_preparation(testcase, service, node)
        result = service.prepare_remote_cli(account, runtime, gateway, 'synthetic-quota')
    control = client.containers.get(name)
    testcase.assertNotEqual(old_control, control.id)
    testcase.assertEqual(target_release, control.labels['vibebench.release'])
    if automatic and os.environ.get('CLUSTER_TEST_TARGET_ACCOUNT_RELEASE') == os.environ.get('CLUSTER_TEST_RELEASE'):
        testcase.assertEqual(generation, result['environment']['generation'])
    else:
        testcase.assertGreater(result['environment']['generation'], generation)
    testcase.assertEqual(original, json.loads((root / 'home/.claude.json').read_text()))
    current = json.loads(path.read_text())
    testcase.assertEqual('synthetic-current-node-upgrade-rt', current['claudeAiOauth']['refreshToken'])
    testcase.assertEqual({'preserved': True}, current['unknown_upgrade_field'])
    if automatic and os.environ.get('CLUSTER_TEST_AUTO_RESTORE') == '1':
        verify_node_snapshot_restore(testcase, service, runtime, node, account, root)
        return
    target = client.images.get(target_account).id
    for column in ('container_id', 'network_container_id', 'sender_container_id'):
        testcase.assertEqual(target, client.containers.get(result['environment'][column]).attrs['Image'])


def wait_node_preparation(testcase, service, node: dict) -> dict:
    """等待真实后台安装完整落盘。:param testcase: 隔离验证器。:param service: 原服务。:param node: 节点。:return: 收口后的公开节点。"""
    deadline = time.monotonic() + 180
    while True:
        with service.lock:
            running = node['id'] in service.install_workers
        current = next(row for row in service.store.list() if row['id'] == node['id'])
        if not running:
            testcase.assertEqual('prepared', current['preparation']['state'], str(current['preparation']))
            return current
        testcase.assertLess(time.monotonic(), deadline, '隔离节点后台同步超时')
        time.sleep(.1)


def verify_node_snapshot_restore(testcase, service, runtime, node: dict, account: dict, root: Path) -> None:
    """用隔离Node原地切回旧组件，保留当前资料并核对大profile。

    :param testcase: 隔离验证器。
    :param service: 原节点服务。
    :param runtime: 当前运行时。
    :param node: 原随机节点。
    :param account: 合成独立账号。
    :param root: 原实际HOME根。
    :return: None。
    """
    sync = service.synchronization
    connection = service.connection(node['id'])
    journal = connection.private / 'maintenance/current.json'
    job = json.loads(journal.read_text())
    operation, epoch = str(uuid.uuid4()), str(uuid.uuid4())
    job.update(platform_operation=operation, platform_epoch=epoch)
    atomic_json(journal, job)
    gate_root = service.data / 'restore-test-gate'
    gate = DeploymentGate(gate_root, runtime.deployment)
    atomic_json(gate_root / 'admission.json', {'schema_version': 1, 'deployment': runtime.deployment,
        'operation_id': operation, 'epoch': epoch, 'phase': 'blocked', 'target_release': 'cluster-sync-current',
        'revision': str(uuid.uuid4()), 'created_at': time.time()})
    later = root / 'projects/later.txt'
    later.write_text('后来资料原地保留')
    large = service.data / 'profiles' / account['name'] / 'settings.json'
    atomic_json(large, {'large_config': 'x' * (2 * 1024 ** 2)})
    with patch('cluster_synchronization.UPDATE_GATE', gate), patch.object(sync.gateway, '_request', return_value={
            'phase': 'blocked', 'operation_id': operation, 'epoch': epoch, 'active': 0}):
        restored = sync.restore_platform_snapshot(node['id'])
    testcase.assertEqual('prepared', restored['state'])
    testcase.assertEqual(job['old_release'], restored['release'])
    testcase.assertEqual('in_place', job['data_policy'])
    testcase.assertNotIn('backup', job)
    testcase.assertEqual('后来资料原地保留', later.read_text())
    quarantine = root.parents[1].parent / ('.flower-node-previous-' + job['job_id'])
    testcase.assertFalse(quarantine.exists())
    actual = json.loads((root.parents[1] / 'profiles' / account['name'] / 'settings.json').read_text())
    testcase.assertEqual(2 * 1024 ** 2, len(actual['large_config']))
    testcase.assertEqual('platform_restored', json.loads(journal.read_text())['phase'])
