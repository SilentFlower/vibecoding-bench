"""独立账号真实双SSH迁移、取消与单节点故障隔离。"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from uuid import uuid4

from cluster_deployment import node_container_name
from cluster_migration_runner import MigrationCoordinator, MigrationStart
from cluster_nodes import NodeCreate
from runtime_files import atomic_json
from verify_cluster_terminal import verify_node_terminal
import test_cluster_ssh as ssh_fixture


def verify_independent_migration(testcase, service, runtime, source, account, gateway, upstream, source_root, secondary_fixtures):
    """实际迁移保留Node当前RT和工程，另一个节点离线后目标继续工作。

    :param testcase: 本次随机部署。
    :param service: 原中央节点服务。
    :param runtime: 原中央运行时。
    :param source: 原所属SSH节点。
    :param account: 合成正式独立账号。
    :param gateway: 禁止调用的Gateway边界替身。
    :param upstream: 本地合成代理。
    :param source_root: 原Node环境。
    :param secondary_fixtures: 由外层按随机身份收口的SSH夹具。
    :return: None；所有资料与调用位于本次隔离部署。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('独立迁移验证只用于随机隔离部署')
    fixture=ssh_fixture.ClusterSshTests(methodName='runTest')
    secondary_fixtures.append(fixture)
    fixture.setUp()
    target_data=fixture.root/'remote'
    target=service.register(NodeCreate(**{**fixture.config.model_dump(),'data_root':str(target_data),
        'private_key':fixture.identity.read_text()}))
    testcase.prepare_network(service.local_client,runtime.deployment,target)
    network='flower2api-'+runtime.deployment+'-node-'+target['node_key'][:12]
    service.local_client.networks.get(network).connect(upstream,aliases=['cluster-test-proxy'])
    service.prepare_node(target['id'],target['revision'])
    path=source_root/'home/.claude/.credentials.json'
    credentials=json.loads(path.read_text())
    credentials['claudeAiOauth'].update(accessToken='synthetic-migration-current-at',refreshToken='synthetic-migration-current-rt')
    credentials['unknown_source_field']={'preserved':True}
    atomic_json(path,credentials)
    os.chown(path,1000,1000)
    # 人工停用账号仍可迁移资料；迁移期间两端保持原停用值。
    with service.store.database() as connection:
        connection.execute('UPDATE accounts SET enabled=0 WHERE id=?',(account['id'],))
    account={**account,'enabled':0}
    owner=threading.RLock()
    @contextmanager
    def guard(account_id):
        """持有本次原中央owner，实际Node锁和停止由迁移器完成。:return: 原账号和环境。"""
        with owner:
            connection=service.store.database()
            try:
                current=dict(connection.execute('SELECT * FROM accounts WHERE id=?',(account_id,)).fetchone())
                row=dict(connection.execute('SELECT * FROM account_environments WHERE account_id=?',(account_id,)).fetchone())
            finally:
                connection.close()
            yield current,row
    coordinator=MigrationCoordinator(service,runtime,gateway,lambda current:'synthetic-quota',guard)
    assignment=service.store.assignment(account['id'])
    request=MigrationStart(operation_id=uuid4().hex,node_id=target['id'],revision=assignment['revision'],version='2.1.293')
    coordinator.begin(account['id'],request)
    actual=coordinator.io.command
    lost=[True]
    def command(node_id,operation,payload):
        """真实激活之后仅丢一次回包。:return: 原Node结果。"""
        value=actual(node_id,operation,payload)
        if operation=='activate-import' and lost[0]:
            lost[0]=False
            raise ConnectionError('synthetic independent activation response lost')
        return value
    coordinator.io.command=command
    with testcase.assertRaises(ConnectionError):
        coordinator.run(request.operation_id)
    testcase.assertEqual(target['id'],service.store.assignment(account['id'])['node_id'])
    testcase.assertEqual('completed',coordinator.run(request.operation_id)['phase'])
    row=runtime._row(account['name'],account['id'])
    target_root=target_data/'environments'/row['environment_id']
    with service.store.database() as connection:
        testcase.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=?',(account['id'],)).fetchone()[0])
    with sqlite3.connect(target_data/'node-execution.sqlite') as connection:
        testcase.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=?',(account['id'],)).fetchone()[0])
    restored=json.loads((target_root/'home/.claude/.credentials.json').read_text())
    testcase.assertEqual('synthetic-migration-current-rt',restored['claudeAiOauth']['refreshToken'])
    testcase.assertTrue(restored['unknown_source_field']['preserved'])
    testcase.assertEqual('合成工程资料',(target_root/'projects/migration.txt').read_text())
    testcase.assertEqual('a'*64,json.loads((target_root/'home/.claude.json').read_text())['userID'])
    current=service.store.assignment(account['id'])
    returning=MigrationStart(operation_id=uuid4().hex,node_id=source['id'],revision=current['revision'],version='2.1.293')
    coordinator.begin(account['id'],returning)
    testcase.assertEqual('cancelled',coordinator.cancel(returning.operation_id)['phase'])
    testcase.assertEqual((target['id'],'ready'),(service.store.assignment(account['id'])['node_id'],service.store.assignment(account['id'])['phase']))
    gateway._request.assert_not_called()
    other_name='synthetic_other'
    with service.store.database() as connection:
        cursor=connection.execute('INSERT INTO accounts(name,profile_path,upstream_proxy_scheme,upstream_socks5_host,upstream_socks5_port) '
            'VALUES(?,?,?,?,?)',(other_name,'profiles/'+other_name,'socks5','cluster-test-proxy',1080))
        other=dict(connection.execute('SELECT * FROM accounts WHERE id=?',(cursor.lastrowid,)).fetchone())
    profile=service.data/'profiles'/other_name
    atomic_json(profile/'.claude.json',{'userID':'b'*64,'oauthAccount':{'accountUuid':'synthetic-other','organizationUuid':'synthetic-org'}})
    atomic_json(profile/'.credentials.json',{'claudeAiOauth':{'accessToken':'synthetic-other-at','refreshToken':'synthetic-other-rt',
        'expiresAt':credentials['claudeAiOauth']['expiresAt']}})
    service.assign_initial(other,runtime,source['id'],1)
    service.prepare_remote_cli(other,runtime,gateway,'synthetic-quota')
    testcase.assertNotEqual(service.store.assignment(other['id'])['node_id'],service.store.assignment(account['id'])['node_id'])
    # 以下明确启用本次合成账号，再验证普通执行；迁移本身保留原停用值。
    with service.store.database() as connection:
        connection.execute('UPDATE accounts SET enabled=1 WHERE id=?',(account['id'],))
    account={**account,'enabled':1}
    service.prepare_remote_cli(account,runtime,gateway,'synthetic-quota')
    # 目标继续原工程CLI，原源节点的控制进程停机不会成为全局准入条件。
    control=service.local_client.containers.get(node_container_name(runtime.deployment,source['node_key']))
    control.stop(timeout=5)
    with testcase.assertRaises(ValueError):
        service.prepare_remote_cli(other,runtime,gateway,'synthetic-quota')
    verify_node_terminal(testcase,service,runtime,target,account,gateway)
    gateway._request.assert_not_called()
