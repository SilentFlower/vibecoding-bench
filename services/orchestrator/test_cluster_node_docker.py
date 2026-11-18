"""显式启用的真实SSH、Docker三角色和本地TLS上游纵向验证。"""
from __future__ import annotations

import base64
import asyncio
import ipaddress
import json
import os
import shutil
import sqlite3
import socket
import subprocess
import threading
import time
import unittest
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from docker import DockerClient
from docker.errors import APIError
from docker.types import IPAMConfig, IPAMPool
from fastapi import FastAPI
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse
from uvicorn import Config, Server
from httpx import Client

from account_runtime import AccountRuntime, RuntimeBusy, derive_v3_fingerprint
from cluster_nodes import NodeCreate
from cluster_deployment import node_container_name
from cluster_execution import ImportActivation, ImportPreparation, ImportRevocation
from cluster_environment import EnvironmentFence
from cluster_migration_files import ArchiveDescriptor, ArchiveExport, ImportStage
from cluster_migrations import NodeMigrations
from cluster_migration_runner import MigrationCoordinator, MigrationStart
from cluster_service import ClusterService
from cluster_store import ClusterStore
from cluster_bound_identity import RemoteBoundIdentity
from cluster_execution_store import NodeExecutions
from cluster_terminal_sessions import TerminalSessions
from cluster_transport import node_transport_router
from cluster_transfer import NodeArchiveTransfer
from database_migrations import apply_migrations
from runtime_files import atomic_json
from verify_forwarding import certificates
from verify_cluster_terminal import verify_node_terminal
from verify_cluster_background import verify_node_background
from verify_cluster_credentials import verify_node_credentials
from verify_cluster_bound_login import verify_bound_node_login, verify_product_bound_login
from verify_cluster_independent_migration import verify_independent_migration
from verify_cluster_node_upgrade import verify_node_upgrade, wait_node_preparation
from verify_cluster_two_node_gateway import verify_two_node_gateway
from verify_cluster_environment_management import verify_environment_management
from verify_cluster_draft_login import verify_node_draft_login, verify_draft_login_coordinator, verify_product_draft_login
from verify_cluster_run import verify_node_run
from main import Cc2ApiClient
from project_library import ProjectLibrary
import test_cluster_ssh as ssh_fixture
import main


@unittest.skipUnless(os.environ.get('CLUSTER_DOCKER_TEST') == '1', '真实Docker纵向验证按需显式启用')
class ClusterNodeDockerTests(unittest.TestCase):
    """所有资料和容器使用随机部署标签，只访问隔离合成上游。"""

    def test_remote_account_preparation_and_sender_json_sse(self) -> None:
        """中央人工分配经真实SSH准备节点，三角色发送JSON和SSE到本地TLS。:return: None。"""
        fixture = ssh_fixture.ClusterSshTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        secondary_fixtures = []
        self.addCleanup(self.cleanup_fixtures, secondary_fixtures)
        root = fixture.root
        central = root / 'central'
        central.mkdir()
        self.database_path = central / 'bench.sqlite'
        connection = self.database()
        try:
            apply_migrations(connection)
            with connection:
                connection.execute("INSERT INTO accounts(id,name,profile_path,cc2api_account_id) VALUES(1,'synthetic','profiles/synthetic',7)")
        finally:
            connection.close()
        client = DockerClient.from_env(timeout=30)
        self.addCleanup(client.close)
        deployment = 'cluster-test-' + uuid.uuid4().hex[:12]
        release = os.environ['CLUSTER_TEST_RELEASE']
        backend = os.environ.get('CLUSTER_TEST_BACKEND', 'legacy')
        self.assertIn(backend, ('legacy', 'native293'))
        environment = {'V3_DEPLOYMENT_ID': deployment, 'V3_RELEASE': release,
            'V3_CONTROL_IMAGE': os.environ['CLUSTER_TEST_CONTROL_IMAGE'],
            'V3_ACCOUNT_IMAGE': os.environ['CLUSTER_TEST_ACCOUNT_IMAGE'],
            'V3_NETWORK': 'unused-central-' + deployment, 'V3_ACCOUNT_MEMORY': '4g', 'V3_ACCOUNT_SWAP': '0',
            'V3_MAX_ACTIVE_ACCOUNTS': '2', 'V3_RUNTIME_URL': 'http://testserver', 'V3_NATIVE_CRIU': '0',
            'V3_NATIVE_SENDER_MEMORY': '1g'}
        variables = patch.dict(os.environ, environment)
        variables.start()
        self.addCleanup(variables.stop)
        self.addCleanup(self.cleanup_docker, client, deployment)
        store = ClusterStore(self.database, threading.Lock())
        service = ClusterService(store, central, client, root / 's')
        self.addCleanup(service.close)
        remote_data = root / 'remote'
        request = NodeCreate(**{**fixture.config.model_dump(), 'data_root': str(remote_data),
            'private_key': fixture.identity.read_text()})
        node = service.register(request)
        self.prepare_network(client, deployment, node)
        service.prepare_node(node['id'], node['revision'])
        prepared = wait_node_preparation(self, service, node)
        self.assertEqual('prepared', prepared['preparation']['state'])
        if os.environ.get('CLUSTER_TEST_TERMINAL_ASSETS') == '1' or os.environ.get('CLUSTER_TEST_TERMINAL_EXECUTION') == '1':
            library = ProjectLibrary(Path(__file__).resolve().parents[2] / 'resources/project-library')
            assets = service.connection(node['id']).execution_environment(node_container_name(deployment, node['node_key']),
                {'node_key': node['node_key'], 'digest': library.digest}, 'terminal-assets')
            self.assertEqual({'digest': library.digest, 'state': 'registered'}, assets['terminal'])
        network = 'flower2api-' + deployment + '-node-' + node['node_key'][:12]
        upstream_root = root / 'upstream'
        upstream_root.mkdir()
        certificates(upstream_root)
        fixtures = Path(__file__).resolve().parents[2] / 'deploy/flower2api/fixtures'
        upstream = client.containers.run(environment['V3_CONTROL_IMAGE'], ['/fixtures/forwarding_network.py'],
            entrypoint='python3', detach=True, network=network,
            networking_config={network: client.api.create_endpoint_config(aliases=['cluster-test-proxy'])},
            labels={'vibebench.product': 'v3', 'vibebench.deployment': deployment, 'vibebench.role': 'verification'},
            volumes={str(fixtures): {'bind': '/fixtures', 'mode': 'ro'},
                str(upstream_root): {'bind': '/fixtures-data', 'mode': 'rw'}})
        upstream.reload()
        deadline = time.monotonic() + 10
        while not (upstream_root / 'ready').exists():
            if time.monotonic() > deadline:
                self.fail('隔离TLS代理启动超时')
            time.sleep(0.05)
        gateway = Mock()
        configuration = {'auth_type': 'oauth', 'status': 'active', 'proxy_url': 'socks5://cluster-test-proxy:1080',
            'request_backend': backend, 'concurrency': 1}
        gateway._request.return_value = configuration
        runtime = AccountRuntime(client, central, central, self.database, derive_v3_fingerprint, gateway,
            lambda account: 'synthetic-quota', placement=service.admit_local, locality=service.owns_local)
        self.addCleanup(runtime.heartbeat_pool.shutdown)
        account = {'id': 1, 'name': 'synthetic', 'profile_path': 'profiles/synthetic', 'cc2api_account_id': 7}
        independent = os.environ.get('CLUSTER_TEST_INDEPENDENT') == '1'
        if independent:
            account.update(cc2api_account_id=None, upstream_proxy_scheme='socks5',
                upstream_socks5_host='cluster-test-proxy', upstream_socks5_port=1080)
            connection = self.database()
            try:
                with connection:
                    connection.execute('UPDATE accounts SET cc2api_account_id=NULL,upstream_proxy_scheme=?,upstream_socks5_host=?,upstream_socks5_port=? WHERE id=1',
                        ('socks5', 'cluster-test-proxy', 1080))
            finally:
                connection.close()
        assignment = service.assign_initial(account, runtime, node['id'], 1)
        row = runtime._row('synthetic', 1)
        node_root = remote_data / 'environments' / row['environment_id']
        atomic_json(node_root / 'runtime/node-assignment.json', {'protocol': 1, 'node_key': node['node_key'],
            'account_id': 1, 'environment_id': row['environment_id'], 'revision': assignment['revision'], 'phase': 'ready'})
        shutil.copyfile(upstream_root / 'ca.der', node_root / 'runtime/verification-ca.der')
        identity = {'userID': 'a' * 64,
            'oauthAccount': {'accountUuid': 'synthetic-account', 'organizationUuid': 'synthetic-org'}}
        atomic_json(central / 'profiles/synthetic/.claude.json', identity)
        # API独立准备会保留空HOME；迁移夹具显式建立已有CLI身份和工程文件，核对实际持久资料。
        atomic_json(node_root / 'home/.claude.json', identity)
        os.chown(node_root / 'home/.claude.json', 1000, 1000)
        (node_root / 'projects').mkdir()
        (node_root / 'projects/migration.txt').write_text('合成工程资料')
        os.chown(node_root / 'projects/migration.txt', 1000, 1000)
        atomic_json(central / 'profiles/synthetic/.credentials.json', {'claudeAiOauth': {
            'accessToken': 'synthetic-access', 'refreshToken': 'synthetic-refresh', 'expiresAt': int(time.time() * 1000) + 3600000}})
        if os.environ.get('CLUSTER_TEST_DRAFT_API')=='1':
            verify_product_draft_login(self,service,runtime,node,remote_data)
            return
        if os.environ.get('CLUSTER_TEST_DRAFT_COORDINATOR')=='1':
            verify_draft_login_coordinator(self,service,runtime,node,remote_data)
            return
        if os.environ.get('CLUSTER_TEST_DRAFT_LOGIN')=='1':
            verify_node_draft_login(self,service,runtime,node,remote_data)
            return
        if independent:
            service.prepare_remote_cli(account, runtime, gateway, 'synthetic-quota')
            unused_gateway = Mock()
            unused_gateway._request.side_effect = AssertionError('独立账号不得调用网关租约')
            if os.environ.get('CLUSTER_TEST_NODE_UPGRADE')=='1':
                verify_node_upgrade(self,service,runtime,node,account,unused_gateway,node_root)
            elif os.environ.get('CLUSTER_TEST_INDEPENDENT_MIGRATION')=='1':
                verify_independent_migration(self,service,runtime,node,account,unused_gateway,upstream,node_root,secondary_fixtures)
            elif os.environ.get('CLUSTER_TEST_CREDENTIAL_REFRESH')=='1':
                verify_node_credentials(self,service,runtime,node,account,unused_gateway,upstream_root,remote_data)
            elif os.environ.get('CLUSTER_TEST_RUN_EXECUTION') == '1':
                verify_node_run(self, service, runtime, node, account, unused_gateway)
            else:
                verify_node_terminal(self, service, runtime, node, account, unused_gateway)
            unused_gateway._request.assert_not_called()
            return
        try:
            binding = service.prepare_remote(account, runtime, gateway, 'synthetic-quota')
        except ValueError:
            control = client.containers.get(node_container_name(runtime.deployment, node['node_key']))
            self.fail('合成节点准备失败；受限调用位置：' + control.logs(tail=12).decode(errors='replace'))
        self.assertEqual(row['environment_id'], binding['environment_id'])
        self.assertTrue(binding['endpoint'].startswith('http://testserver/cluster-transports/v2/'))
        private_profile = json.loads((remote_data / 'profiles/synthetic/.credentials.json').read_text())
        self.assertNotIn('refreshToken', private_profile['claudeAiOauth'])
        self.assertFalse((central / 'environments' / row['environment_id']).exists())
        if os.environ.get('CLUSTER_TEST_TWO_NODE_GATEWAY')=='1':
            verify_two_node_gateway(self,service,runtime,node,account,upstream,upstream_root,configuration,backend,secondary_fixtures)
            return
        if os.environ.get('CLUSTER_TEST_BOUND_IDENTITY')=='1':
            sessions=TerminalSessions(NodeExecutions(service.store,runtime.release_id),service,runtime,gateway,
                Mock(side_effect=AssertionError('设备纯读取不能认领模型额度')),Mock())
            self.addCleanup(sessions.close)
            identity_reader=RemoteBoundIdentity(sessions,lambda current:'2.1.293')
            frozen={item.id:item.attrs['State']['StartedAt'] for item in client.containers.list(filters={
                'label':['vibebench.deployment='+deployment,'vibebench.environment='+row['environment_id']]})}
            observed=identity_reader.read(account,{'account_id':7,'email':'synthetic@example.invalid',
                'account_uuid':'synthetic-account','organization_uuid':'synthetic-org'})
            self.assertEqual({'device_id':'a'*64,'environment_id':row['environment_id']},observed)
            if os.environ.get('CLUSTER_TEST_BOUND_LOGIN_PREPARE')=='1':
                gateway._request.return_value={**configuration,'status':'disabled','account_id':7,
                    'email':'synthetic@example.invalid','account_uuid':'synthetic-account','organization_uuid':'synthetic-org'}
                prepared=service.prepare_remote_login(account,runtime,gateway,'synthetic-quota','a'*12)
                self.assertEqual(row['environment_id'],prepared['environment']['environment_id'])
                self.assertNotIn('binding',prepared)
                self.assertEqual(observed,identity_reader.read(account,gateway._request.return_value))
                self.assertNotIn('refreshToken',json.loads((remote_data/'profiles/synthetic/.credentials.json').read_text())['claudeAiOauth'])
            self.assertEqual(frozen,{item.id:item.attrs['State']['StartedAt'] for item in client.containers.list(filters={
                'label':['vibebench.deployment='+deployment,'vibebench.environment='+row['environment_id']]})})
            self.assertFalse((central/'environments'/row['environment_id']).exists())
            self.assertEqual([],sessions.ledger.pending())
            if os.environ.get('CLUSTER_TEST_BOUND_LOGIN')=='1':
                verify_bound_node_login(self,service,runtime,node,account,gateway,node_root)
            return
        instances = client.containers.list(filters={'label': ['vibebench.deployment=' + deployment,
            'vibebench.environment=' + row['environment_id']]})
        self.assertEqual({'account', 'account-sender', 'account-network'}, {item.labels['vibebench.role'] for item in instances})
        app = FastAPI()
        app.include_router(node_transport_router(lambda: service.transports))
        with TestClient(app) as http:
            for stream in (False, True):
                marker = 'cluster-json' if not stream else 'cluster-sse'
                body = json.dumps({'model': 'claude-sonnet-4-6', 'max_tokens': 10, 'stream': stream,
                    'messages': [{'role': 'user', 'content': marker}]}).encode()
                metadata = {key: binding[key] for key in ('account_id', 'environment_id', 'generation')}
                metadata.update(request_id=str(uuid.uuid4()), deadline_unix_ms=int(time.time() * 1000) + 90000,
                    method='POST', target_url='https://api.anthropic.com/v1/messages',
                    headers=[['Content-Type', 'application/json'], ['Authorization', 'Bearer synthetic-access']],
                    preserve_header_casing=False)
                headers = {'authorization': 'Bearer ' + binding['secret']}
                if backend == 'native293':
                    submission = {'request': metadata, 'input': {'schema_version': 1, 'request_id': metadata['request_id'],
                        'body': json.loads(body), 'headers': []}, 'bearer': 'synthetic-access', 'device_id': 'a' * 64,
                        'account_uuid': 'synthetic-account', 'organization_uuid': 'synthetic-org',
                        'email': 'synthetic@example.invalid', 'concurrency': 1}
                    response = http.post(binding['endpoint'] + '/internal/native/messages', json=submission, headers=headers)
                else:
                    response = http.post(binding['endpoint'] + '/internal/send', content=body,
                        headers={**headers, 'x-v3-request': base64.b64encode(json.dumps(metadata).encode()).decode()})
                if response.status_code != 200:
                    evidence = upstream_root / 'evidence.jsonl'
                    details = evidence.read_text()[-3000:] if evidence.exists() else '尚无代理调用记录'
                    self.fail(f'节点sender返回{response.status_code}: {response.text[:300]}；隔离代理证据：{details}；夹具日志：'
                        + upstream.logs(tail=15).decode(errors='replace'))
                self.assertIn(marker, response.text)
                if stream:
                    self.assertIn('text/event-stream', response.headers['content-type'])
        self.assertEqual({}, service.transports.active)
        use_coordinator = os.environ.get('CLUSTER_TEST_COORDINATOR') == '1'
        if os.environ.get('CLUSTER_GATEWAY_BIN'):
            def after_work(real_gateway):
                if os.environ.get('CLUSTER_TEST_ENVIRONMENT_MANAGEMENT')=='1':
                    verify_environment_management(self,service,runtime,node,account,real_gateway,node_root)
                if os.environ.get('CLUSTER_TEST_BOUND_LOGIN_API')=='1':
                    verify_product_bound_login(self,service,runtime,node,account,real_gateway,node_root)
                if os.environ.get('CLUSTER_TEST_TERMINAL_EXECUTION') == '1':
                    verify_node_terminal(self, service, runtime, node, account, real_gateway)
                if os.environ.get('CLUSTER_TEST_RUN_EXECUTION') == '1':
                    verify_node_run(self, service, runtime, node, account, real_gateway)
                if use_coordinator:
                    self.verify_migration_files(service, runtime, node, account,
                        secondary_fixtures, gateway, upstream, upstream_root, configuration, backend,
                        coordinator_gateway=real_gateway)

            after = after_work if use_coordinator or os.environ.get('CLUSTER_TEST_TERMINAL_EXECUTION') == '1' or os.environ.get('CLUSTER_TEST_RUN_EXECUTION') == '1' or os.environ.get('CLUSTER_TEST_BOUND_LOGIN_API')=='1' or os.environ.get('CLUSTER_TEST_ENVIRONMENT_MANAGEMENT')=='1' else None
            self.verify_gateway(client, service, runtime, account, upstream_root, network, configuration, backend, after=after)
        if os.environ.get('CLUSTER_TEST_MIGRATION_IO') == '1' and not use_coordinator:
            self.verify_migration_files(service, runtime, node, account, secondary_fixtures,
                gateway, upstream, upstream_root, configuration, backend)

    def verify_migration_files(self, service, runtime, source_node: dict, account: dict, secondary_fixtures: list,
                               gateway, upstream, upstream_root, configuration: dict, backend: str,
                               coordinator_gateway=None) -> None:
        """用两个真实SSH节点核对源停止、目标发布、归属切换与重新转发。

        :param service: 同一中央节点服务。
        :param runtime: 同一中央环境登记器。
        :param source_node: 已执行业务的原节点。
        :param account: 原固定账号。
        :param secondary_fixtures: 由外层统一收口的隔离sshd。
        :param gateway: 原合成网关配置来源。
        :param upstream: 双网络共享的隔离上游。
        :param upstream_root: 原TLS夹具数据。
        :param configuration: 原账号代理和后端。
        :param backend: 原请求后端。
        :param coordinator_gateway: 实际Rust网关客户端，提供原生排他租约合同。
        :return: None；成功后源仍隔离，目标承担同一账号业务。
        """
        fixture = ssh_fixture.ClusterSshTests(methodName='runTest')
        secondary_fixtures.append(fixture)
        fixture.setUp()
        target_data = fixture.root / 'remote'
        target = service.register(NodeCreate(**{**fixture.config.model_dump(), 'data_root': str(target_data),
            'private_key': fixture.identity.read_text()}))
        self.prepare_network(service.local_client, runtime.deployment, target)
        target_network = 'flower2api-' + runtime.deployment + '-node-' + target['node_key'][:12]
        service.local_client.networks.get(target_network).connect(upstream, aliases=['cluster-test-proxy'])
        service.prepare_node(target['id'], target['revision'])
        original = service.store.assignment(account['id'])
        row = runtime._row(account['name'], account['id'])
        if coordinator_gateway is not None:
            @contextmanager
            def guard(account_id):
                connection = self.database()
                try:
                    current = dict(connection.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone())
                    environment = dict(connection.execute('SELECT * FROM account_environments WHERE account_id=?', (account_id,)).fetchone())
                finally:
                    connection.close()
                yield current, environment
            coordinator = MigrationCoordinator(service, runtime, coordinator_gateway, lambda current: 'synthetic-quota', guard)
            request = MigrationStart(operation_id=uuid.uuid4().hex, node_id=target['id'], revision=original['revision'], version='2.1.293')
            coordinator.begin(account['id'], request)
            self.assertEqual('completed', coordinator.run(request.operation_id)['phase'])
            actual = service.store.assignment(account['id'])
            self.assertEqual((target['id'], original['revision'] + 1, 'ready'), (actual['node_id'], actual['revision'], actual['phase']))
            target_root = target_data / 'environments' / row['environment_id']
            self.assertEqual('合成工程资料', (target_root / 'projects/migration.txt').read_text())
            self.assertEqual([], coordinator_gateway._request('GET', f"/admin/runtime/accounts/{account['cc2api_account_id']}/lease")['holders'])
            self.verify_gateway(service.local_client, service, runtime, account, upstream_root, target_network, configuration, backend)
            self.verify_cancelled_return(service, runtime, target, source_node, account, gateway)
            self.verify_local_target(service, runtime, account, coordinator_gateway, upstream, upstream_root, configuration, backend)
            return
        operation_id = uuid.uuid4().hex
        ledger = NodeMigrations(service.store)
        ledger.begin(operation_id, account['id'], target['id'], original['revision'])
        ledger.advance(operation_id, 'draining', {'active_requests': 0})
        request = EnvironmentFence(operation_id=operation_id, node_key=source_node['node_key'],
            account_id=account['id'], environment_id=row['environment_id'], assignment_revision=original['revision'],
            generation=row['generation'])
        source = service.connection(source_node['id'])
        source_container = node_container_name(runtime.deployment, source_node['node_key'])
        fence = source.fence_environment(source_container, request.model_dump())
        self.assertEqual('fenced', fence['phase'])
        ledger.advance(operation_id, 'source_fenced', fence)
        export = ArchiveExport(**request.model_dump(), attempt_id=uuid.uuid4().hex, version='2.1.293')
        exported = source.migration_environment(source_container, export.model_dump(), 'export')
        archive = ArchiveDescriptor.model_validate(exported['archive'])
        self.assertEqual('a' * 64, archive.cli_identity.device_id)
        ledger.advance(operation_id, 'exporting', archive.model_dump())
        central_directory = service.data / 'migration-test'
        central_directory.mkdir(mode=0o700)
        bundle = central_directory / 'environment.tar'
        sender = NodeArchiveTransfer(source.docker_socket(), service.docker(source_node['id']).api._version, source_container)
        sender.download(operation_id, archive.attempt_id, bundle, archive.sha256, archive.bytes)
        stage = ImportStage(node_key=target['node_key'], transfer_id=uuid.uuid4().hex,
            target_revision=original['revision'] + 1, archive=archive)
        target_connection = service.connection(target['id'])
        target_container = node_container_name(runtime.deployment, target['node_key'])
        accepted = target_connection.migration_environment(target_container, stage.model_dump(), 'stage-import')
        self.assertFalse(accepted['uploaded'])
        receiver = NodeArchiveTransfer(target_connection.docker_socket(), service.docker(target['id']).api._version, target_container)
        receiver.upload(operation_id, stage.transfer_id, bundle, archive.sha256, archive.bytes)
        ledger.advance(operation_id, 'importing', {'transfer_id': stage.transfer_id})
        result = target_connection.migration_environment(target_container, stage.model_dump(), 'verify-import')
        self.assertEqual(('verified', archive.sha256), (result['phase'], result['sha256']))
        imported = target_data / 'node-migrations' / operation_id / 'imports' / stage.transfer_id / 'environment'
        self.assertEqual('a' * 64, json.loads((imported / 'home/.claude.json').read_text())['userID'])
        self.assertEqual('合成工程资料', (imported / 'projects/migration.txt').read_text())
        self.assertFalse((imported / 'runtime/node-fence.json').exists())
        self.assertFalse((imported / 'runtime/sender').exists())
        assignment = service.store.assignment(account['id'])
        self.assertEqual((source_node['id'], 'maintenance'), (assignment['node_id'], assignment['phase']))
        self.assertFalse((target_data / 'environments' / row['environment_id']).exists())
        preparation = service.build_preparation(account, row, target['node_key'], stage.target_revision,
            runtime, gateway, 'synthetic-quota')
        published = target_connection.migration_environment(target_container,
            ImportPreparation(stage=stage, preparation=preparation).model_dump(), 'prepare-import')
        self.assertEqual('prepared', published['phase'])
        self.assertGreater(published['environment']['generation'], row['generation'])
        self.assertEqual('合成工程资料', (target_data / 'environments' / row['environment_id'] / 'projects/migration.txt').read_text())
        ledger.advance(operation_id, 'verified', {'transfer_id': stage.transfer_id, 'generation': published['environment']['generation']})
        ledger.commit(operation_id, published['environment'])
        activation = ImportActivation(node_key=target['node_key'], operation_id=operation_id,
            transfer_id=stage.transfer_id, account_id=account['id'], environment_id=row['environment_id'],
            revision=stage.target_revision, generation=published['environment']['generation'])
        receipt = target_connection.migration_environment(target_container, activation.model_dump(), 'activate-import')
        self.assertEqual('activated', receipt['phase'])
        ledger.finish(operation_id, {'operation_id': operation_id, 'node_id': target['id'], 'account_id': account['id'],
            'environment_id': row['environment_id'], 'revision': stage.target_revision,
            'generation': published['environment']['generation'], 'phase': 'activated'})
        actual = service.store.assignment(account['id'])
        self.assertEqual((target['id'], stage.target_revision, 'ready'), (actual['node_id'], actual['revision'], actual['phase']))
        source_marker = Path(source_node['data_root']) / 'environments' / row['environment_id'] / 'runtime/node-fence.json'
        self.assertEqual('fenced', json.loads(source_marker.read_text())['phase'])
        if os.environ.get('CLUSTER_GATEWAY_BIN'):
            self.verify_gateway(service.local_client, service, runtime, account, upstream_root,
                target_network, configuration, backend)
        self.verify_cancelled_return(service, runtime, target, source_node, account, gateway)

    def verify_cancelled_return(self, service, runtime, source_node: dict, target_node: dict,
                                account: dict, gateway) -> None:
        """迁回原停止副本，准备后撤销目标并核对源恢复。

        :param service: 原中央节点服务。
        :param runtime: 原中央环境登记器。
        :param source_node: 当前归属节点。
        :param target_node: 留有前次已隔离副本的目标节点。
        :param account: 原合成账号。
        :param gateway: 原冻结上游配置。
        :return: None；取消后保持当前源归属与原分配版本。
        """
        ledger = NodeMigrations(service.store)
        original = service.store.assignment(account['id'])
        row = runtime._row(account['name'], account['id'])
        operation_id = uuid.uuid4().hex
        ledger.begin(operation_id, account['id'], target_node['id'], original['revision'])
        ledger.advance(operation_id, 'draining', {'active_requests': 0})
        fence_request = EnvironmentFence(operation_id=operation_id, node_key=source_node['node_key'],
            account_id=account['id'], environment_id=row['environment_id'], assignment_revision=original['revision'],
            generation=row['generation'])
        source = service.connection(source_node['id'])
        source_container = node_container_name(runtime.deployment, source_node['node_key'])
        fence = source.fence_environment(source_container, fence_request.model_dump())
        ledger.advance(operation_id, 'source_fenced', fence)
        export_request = ArchiveExport(**fence_request.model_dump(), attempt_id=uuid.uuid4().hex, version='2.1.293')
        archive = ArchiveDescriptor.model_validate(source.migration_environment(source_container, export_request.model_dump(), 'export')['archive'])
        ledger.advance(operation_id, 'exporting', archive.model_dump())
        bundle = service.data / 'migration-test' / (operation_id + '.tar')
        bundle.parent.mkdir(mode=0o700, exist_ok=True)
        NodeArchiveTransfer(source.docker_socket(), service.docker(source_node['id']).api._version, source_container).download(
            operation_id, archive.attempt_id, bundle, archive.sha256, archive.bytes)
        stage = ImportStage(node_key=target_node['node_key'], transfer_id=uuid.uuid4().hex,
            target_revision=original['revision'] + 1, archive=archive)
        target = service.connection(target_node['id'])
        target_container = node_container_name(runtime.deployment, target_node['node_key'])
        target.migration_environment(target_container, stage.model_dump(), 'stage-import')
        NodeArchiveTransfer(target.docker_socket(), service.docker(target_node['id']).api._version, target_container).upload(
            operation_id, stage.transfer_id, bundle, archive.sha256, archive.bytes)
        ledger.advance(operation_id, 'importing', {'transfer_id': stage.transfer_id})
        target.migration_environment(target_container, stage.model_dump(), 'verify-import')
        preparation = service.build_preparation(account, row, target_node['node_key'], stage.target_revision,
            runtime, gateway, 'synthetic-quota')
        published = target.migration_environment(target_container,
            ImportPreparation(stage=stage, preparation=preparation).model_dump(), 'prepare-import')
        self.assertGreater(published['environment']['generation'], row['generation'])
        private = Path(target_node['data_root']) / 'node-migrations' / operation_id / 'imports' / stage.transfer_id
        self.assertEqual('合成工程资料', (private / 'previous-environment/projects/migration.txt').read_text())
        revoke = ImportRevocation(node_key=target_node['node_key'], target_revision=stage.target_revision, identity=archive.identity)
        revoked = target.migration_environment(target_container, revoke.model_dump(), 'revoke-import')
        self.assertEqual('revoked', revoked['phase'])
        restored = source.migration_environment(source_container, fence_request.model_dump(), 'restore-source')
        self.assertEqual('restored', restored['phase'])
        ledger.cancel(operation_id, {'operation_id': operation_id, 'node_id': source_node['id'], 'account_id': account['id'],
            'environment_id': row['environment_id'], 'revision': original['revision'], 'generation': row['generation'], 'phase': 'restored'},
            {'operation_id': operation_id, 'node_id': target_node['id'], 'account_id': account['id'],
                'environment_id': row['environment_id'], 'revision': stage.target_revision, 'phase': 'revoked'})
        actual = service.store.assignment(account['id'])
        self.assertEqual((source_node['id'], original['revision'], 'ready'), (actual['node_id'], actual['revision'], actual['phase']))
        with self.assertRaises(ValueError):
            target.migration_environment(target_container,
                ImportPreparation(stage=stage, preparation=preparation).model_dump(), 'prepare-import')

    def cleanup_fixtures(self, fixtures: list) -> None:
        """在原Docker和隧道资源收口后清理附加sshd。:param fixtures: 本次附加节点。:return: None。"""
        for fixture in reversed(fixtures):
            fixture.doCleanups()

    def verify_local_target(self, service, runtime, account: dict, gateway, upstream, upstream_root,
                            configuration: dict, backend: str) -> None:
        """真实SSH源迁回本机目标，核对权威CAS、管理RT和本机实际角色转发。

        :param service: 原中央节点服务。
        :param runtime: 原本机运行时。
        :param account: 原合成账号。
        :param gateway: 提供排他租约的实际网关。
        :param upstream: 原隔离上游。
        :param upstream_root: 原合成证书和证据。
        :param configuration: 原账号配置。
        :param backend: 原请求后端。
        :return: None；本机承接原环境及持久资料。
        """
        client = service.local_client
        local = next(node for node in service.store.list() if node['kind'] == 'local')
        self.prepare_network(client, runtime.deployment, local, network_name=runtime.network)
        client.networks.get(runtime.network).connect(upstream, aliases=['cluster-test-proxy'])
        original = service.store.assignment(account['id'])
        profile = runtime.data / 'profiles' / account['name'] / '.credentials.json'
        credentials = profile.read_bytes()

        @contextmanager
        def guard(account_id):
            connection = self.database()
            try:
                current = dict(connection.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone())
                row = dict(connection.execute('SELECT * FROM account_environments WHERE account_id=?', (account_id,)).fetchone())
            finally:
                connection.close()
            yield current, row

        resolver = socket.getaddrinfo
        def local_dns(host, port, *arguments, **keywords):
            address = host
            if host == 'cluster-test-proxy':
                upstream.reload()
                address = upstream.attrs['NetworkSettings']['Networks'][runtime.network]['IPAddress']
            elif isinstance(host, str) and host.startswith('flower2api-') and len(host) < 128:
                instance = client.containers.get(host)
                instance.reload()
                address = instance.attrs['NetworkSettings']['Networks'][runtime.network]['IPAddress']
            return resolver(address, port, *arguments, **keywords)

        def migrate_here(real_gateway):
            coordinator = MigrationCoordinator(service, runtime, real_gateway, lambda current: 'synthetic-quota', guard)
            request = MigrationStart(operation_id=uuid.uuid4().hex, node_id=local['id'], revision=original['revision'], version='2.1.293')
            coordinator.begin(account['id'], request)
            self.assertEqual('completed', coordinator.run(request.operation_id)['phase'])
            actual = service.store.assignment(account['id'])
            self.assertEqual((local['id'], original['revision'] + 1, 'ready'), (actual['node_id'], actual['revision'], actual['phase']))
            row = runtime._row(account['name'], account['id'])
            self.assertEqual('合成工程资料', (runtime._root(row) / 'projects/migration.txt').read_text())
            self.assertEqual(credentials, profile.read_bytes())
            self.assertEqual(dict.fromkeys(('cli', 'sender', 'network'), 'exited'), runtime.role_status(row))
        # 夹具中央运行于宿主Python；只将原本由中央控制容器Docker DNS提供的名字解析到本次隔离网络。
        with patch('account_isolation.socket.getaddrinfo', side_effect=local_dns):
            # 与实际部署一致，中央gateway先加入网络，随后目标准备将其实际IP纳入原入站策略。
            self.verify_gateway(client, service, runtime, account, upstream_root, runtime.network, configuration, backend, before=migrate_here)
            self.assertEqual(dict.fromkeys(('cli', 'sender', 'network'), 'running'), runtime.role_status(runtime._row(account['name'], account['id'])))

    def prepare_network(self, client, deployment: str, node: dict, *, network_name: str | None = None) -> None:
        """为随机测试节点创建经冲突核对的独立网段。

        :param client: 测试Docker客户端。
        :param deployment: 本次随机部署。
        :param node: 本次测试节点。
        :param network_name: 本机目标使用原中央网络名称。
        :return: None，原网络及宿主路由保持原配置。
        """
        used = [ipaddress.ip_network(item['Subnet']) for network in client.networks.list()
            for item in network.attrs.get('IPAM', {}).get('Config') or [] if item.get('Subnet')]
        routes = json.loads(subprocess.check_output(['ip', '-j', 'route', 'show']))
        used.extend(ipaddress.ip_network(item['dst']) for item in routes if item.get('dst') not in (None, 'default'))
        name = network_name or 'flower2api-' + deployment + '-node-' + node['node_key'][:12]
        labels = {'vibebench.product': 'v3', 'vibebench.deployment': deployment, 'vibebench.cluster-node': node['node_key']}
        for index in range(200, 250):
            subnet = ipaddress.ip_network(f'10.232.{index}.0/24')
            if any(subnet.overlaps(existing) for existing in used if existing.version == 4):
                continue
            try:
                client.networks.create(name, driver='bridge', labels=labels,
                    ipam=IPAMConfig(pool_configs=[IPAMPool(subnet=str(subnet))]))
                return
            except APIError as error:
                if 'overlap' not in str(error).lower():
                    raise
        self.fail('隔离测试缺少可用私有网段')

    def verify_gateway(self, client, service, runtime, account: dict, upstream_root: Path,
                       network: str, configuration: dict, backend: str, after=None, before=None, extra_accounts=None) -> None:
        """经实际Rust网关选号、原请求路径和SSH发送器核对统一入口。

        :param client: 隔离Docker客户端。
        :param service: 中央真实节点服务。
        :param runtime: 环境登记器。
        :param account: 合成账号。
        :param upstream_root: TLS夹具资料。
        :param network: 节点独立网络。
        :param configuration: 该账号上游配置。
        :param backend: 请求后端。
        :param after: 实际请求完成后在同一私有认证上下文内调用的验证步骤。
        :param before: gateway已准备且实际入站IP可见后执行的迁移步骤。
        :param extra_accounts: 同一Gateway内另外指定节点的合成账号。
        :return: None。
        """
        token, password = uuid.uuid4().hex * 2, uuid.uuid4().hex * 2
        listener = socket.socket()
        listener.bind(('0.0.0.0', 0))
        gateway_address = client.networks.get(network).attrs['IPAM']['Config'][0]['Gateway']
        runtime_base = f'http://{gateway_address}:{listener.getsockname()[1]}'
        app = FastAPI()
        app.include_router(node_transport_router(lambda: service.transports))
        context = {}

        @app.middleware('http')
        async def authenticate(request: Request, call_next):
            actual = request.headers.get('x-v3-relay-token') if request.url.path.startswith('/cluster-transports/') else request.headers.get('authorization', '').removeprefix('Bearer ')
            if actual != token:
                return JSONResponse({'detail': '合成内部认证无效'}, status_code=401)
            return await call_next(request)

        @app.get('/internal/v3/transport/{gateway_account_id}')
        def transport(gateway_account_id: int, wake: bool = True):
            selected=next((item for item in [account,*(extra_accounts or [])] if item['cc2api_account_id']==gateway_account_id),None)
            if selected is None or 'gateway' not in context:
                raise HTTPException(409, '合成账号尚未绑定')
            try:
                if service.store.assignment(selected['id'])['kind'] == 'local':
                    if not wake:
                        return runtime.existing_transport(selected)
                    return runtime.transport(selected, '2.1.293')
                if not wake:
                    return None
                return service.prepare_remote(selected, runtime, context['gateway'], 'synthetic-quota')
            except (ValueError, RuntimeError):
                raise HTTPException(503, '合成账号正在迁移维护') from None

        @app.post('/internal/v3/quiesce/{gateway_account_id}')
        def quiesce(gateway_account_id: int, body: dict):
            """原Rust配置事务回调实际产品SSH收口入口。:param gateway_account_id: 原绑定。:param body: 原门禁。:return: 实际结果。"""
            original=main.quiesce_remote
            def observe(*args):
                """为本次无凭据配置操作保留精确失败位置。:return: 原实际结果。"""
                try:
                    return original(*args)
                except Exception as error:
                    context['quiesce_error']=type(error).__name__+':'+str(error)
                    node_key=service.store.assignment(account['id'])['node_key']
                    control=client.containers.get(node_container_name(runtime.deployment,node_key))
                    context['quiesce_error']+='；Node调用位置：'+control.logs(tail=12).decode(errors='replace')
                    raise
            with patch.multiple(main,account_runtime=runtime,cluster_service=service,get_db=service.store.database,
                    cc2api_client=context['gateway'],quiesce_remote=observe):
                return main.v3_quiesce(gateway_account_id,body)

        server = Server(Config(app, log_level='error', lifespan='off', ws='none'))
        thread = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[listener])), daemon=True)
        thread.start()
        self.addCleanup(self.stop_server, server, thread, listener)
        deadline = time.monotonic() + 5
        while not server.started:
            self.assertLess(time.monotonic(), deadline, '中央回环服务启动超时')
            time.sleep(0.01)
        gateway_root = service.data / ('gateway-test-' + uuid.uuid4().hex)
        gateway_root.mkdir()
        binary = str(Path(os.environ['CLUSTER_GATEWAY_BIN']).resolve())
        with patch.dict(os.environ, {'V3_RUNTIME_URL': runtime_base, 'V3_INTERNAL_TOKEN': token}):
            gateway = client.containers.run(os.environ['CLUSTER_TEST_CONTROL_IMAGE'], entrypoint=['/app/claude-code-gateway'],
                detach=True, network=network, ports={'5674/tcp': ('127.0.0.1', 0)},
                labels={'vibebench.product': 'v3', 'vibebench.deployment': runtime.deployment, 'vibebench.role': 'gateway'},
                environment={'SERVER_HOST': '0.0.0.0', 'SERVER_PORT': '5674', 'DATABASE_DRIVER': 'sqlite',
                    'DATABASE_DSN': '/gateway/gateway.sqlite', 'ADMIN_PASSWORD': password, 'LOG_LEVEL': 'error',
                    'V3_DEPLOYMENT_ID': runtime.deployment, 'V3_RELEASE': runtime.release_id,
                    'V3_RUNTIME_URL': runtime_base, 'V3_INTERNAL_TOKEN': token},
                volumes={binary: {'bind': '/app/claude-code-gateway', 'mode': 'ro'},
                    str(gateway_root): {'bind': '/gateway', 'mode': 'rw'},
                    str(upstream_root / 'ca.der'): {'bind': '/run/v3/verification-ca.der', 'mode': 'ro'}})
            gateway.reload()
            port = gateway.attrs['NetworkSettings']['Ports']['5674/tcp'][0]['HostPort']
            base = 'http://127.0.0.1:' + port
            context['gateway'] = Cc2ApiClient(base, password, 30)
            with Client(base_url=base, trust_env=False, timeout=120) as http:
                admin = {'authorization': 'Bearer ' + password, 'x-v3-service-token': token}
                deadline = time.monotonic() + 15
                while True:
                    try:
                        if http.get('/admin/accounts', headers=admin).status_code == 200:
                            break
                    except OSError:
                        pass
                    except Exception:
                        if time.monotonic() > deadline:
                            raise
                    self.assertLess(time.monotonic(), deadline, '实际网关启动超时')
                    time.sleep(0.05)
                tokens={}
                for selected in [account,*(extra_accounts or [])]:
                    identity=json.loads((service.data/selected['profile_path']/'.claude.json').read_text())['oauthAccount']
                    response = http.post('/admin/accounts', headers=admin, json={'name': 'cluster-gateway-test-'+str(selected['id']),
                        'email': identity.get('emailAddress','synthetic@example.invalid'), 'auth_type': 'oauth', 'access_token': 'synthetic-access',
                        'refresh_token': 'synthetic-refresh', 'expires_at': int(time.time() * 1000) + 3600000,
                        'proxy_url': configuration['proxy_url'], 'request_backend': backend, 'concurrency': 1,
                        'account_uuid': identity['accountUuid'], 'organization_uuid': identity.get('organizationUuid')})
                    self.assertEqual(201, response.status_code, response.text[:300])
                    selected['cc2api_account_id'] = response.json()['id']
                    connection = self.database()
                    try:
                        with connection:
                            connection.execute('UPDATE accounts SET cc2api_account_id=? WHERE id=?',
                                (selected['cc2api_account_id'], selected['id']))
                    finally:
                        connection.close()
                    response = http.post('/admin/tokens', headers=admin,
                        json={'name': 'cluster-test-'+str(selected['id']), 'allowed_accounts': str(selected['cc2api_account_id'])})
                    self.assertEqual(201, response.status_code, response.text[:300])
                    tokens[selected['id']] = response.json()['token']
                if before is not None:
                    before(context['gateway'])
                for selected in [account,*(extra_accounts or [])]:
                    for stream in (False, True):
                        marker = ('cluster-gateway-sse' if stream else 'cluster-gateway-json') + ('-'+str(selected['id']) if extra_accounts else '')
                        response = http.post('/v1/messages', headers={'authorization': 'Bearer ' + tokens[selected['id']],
                            'anthropic-version': '2023-06-01'}, json={'model': 'claude-sonnet-4-6', 'max_tokens': 10,
                                'stream': stream, 'messages': [{'role': 'user', 'content': marker}]})
                        if response.status_code != 200:
                            evidence = upstream_root / 'evidence.jsonl'
                            details = evidence.read_text()[-1500:] if evidence.exists() else '合成上游尚无证据'
                            self.fail(f'实际网关返回{response.status_code}: {response.text[:300]}；上游证据：{details}；网关日志：'
                                + gateway.logs(tail=20).decode(errors='replace'))
                        self.assertIn(marker, response.text)
                        if extra_accounts:
                            request_id=response.headers['x-cc2api-request-id']
                            deadline=time.monotonic()+5
                            while True:
                                detail=http.get('/admin/request-diagnostics/'+request_id,headers=admin)
                                if detail.status_code==200 and detail.json()['attempts']:
                                    break
                                self.assertLess(time.monotonic(),deadline,'原发送尝试诊断尚未落盘')
                                time.sleep(.05)
                            attempts=detail.json()['attempts']
                            self.assertEqual(1,len(attempts))
                            assignment=service.store.assignment(selected['id'])
                            row=runtime._row(selected['name'],selected['id'])
                            self.assertEqual({'node_key':assignment['node_key'],'environment_id':row['environment_id'],
                                'generation':row['generation'],'assignment_revision':assignment['revision']},attempts[0]['execution_location'])
                if extra_accounts:
                    def parallel_request(selected, stream):
                        """两个原令牌同时经统一网关发送到各自节点。:return: 实际响应及合成标记。"""
                        marker = 'cluster-parallel-' + str(selected['id'])
                        with Client(base_url=base, trust_env=False, timeout=120) as parallel_http:
                            response = parallel_http.post('/v1/messages', headers={
                                'authorization': 'Bearer ' + tokens[selected['id']], 'anthropic-version': '2023-06-01'},
                                json={'model': 'claude-sonnet-4-6', 'max_tokens': 10, 'stream': stream,
                                    'messages': [{'role': 'user', 'content': marker}]})
                        return response, marker
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [pool.submit(parallel_request, selected, bool(index))
                            for index, selected in enumerate([account, extra_accounts[0]])]
                        for future in futures:
                            response, marker = future.result()
                            self.assertEqual(200, response.status_code, response.text[:300])
                            self.assertIn(marker, response.text)
                self.assertEqual({}, service.transports.active)
                if os.environ.get('CLUSTER_TEST_BACKGROUND') == '1':
                    verify_node_background(self, http, admin, service, runtime, account, upstream_root)
                if after is not None:
                    try:
                        after(context['gateway'])
                    except Exception:
                        if context.get('quiesce_error'):
                            self.fail('实际Gateway配置收口失败：'+context['quiesce_error'])
                        raise

    def stop_server(self, server, thread, listener) -> None:
        """释放本次实际HTTP服务。:param server: ASGI服务。:param thread: 原线程。:param listener: 原套接字。:return: None。"""
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()

    def database(self):
        """打开本次随机部署的中央数据库。:return: 待关闭连接。"""
        if os.environ.get('CLUSTER_TEST_SQLITE_TRACE')=='1':
            from verify_cluster_sqlite import traced_connect
            connection=traced_connect(self.database_path)
        else:
            connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def cleanup_docker(self, client, deployment: str) -> None:
        """只清理本次随机部署标签的测试资源。:param client: Docker。:param deployment: 本次随机身份。:return: None。"""
        for container in client.containers.list(all=True, filters={'label': ['vibebench.deployment=' + deployment]}):
            container.remove(force=True)
        for network in client.networks.list(filters={'label': ['vibebench.deployment=' + deployment]}):
            network.remove()
