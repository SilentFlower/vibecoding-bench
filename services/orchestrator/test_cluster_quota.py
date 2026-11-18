"""真实额度JSONL、私有镜像和原QuotaGuard的远程消费合同验证。"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from cluster_quota import (ApiQuotaRead, ApiQuotaScope, NodeTerminalQuota, RemoteApiQuota,
    RemoteTerminalQuota, TerminalQuotaRead, TerminalQuotaState, quota_scope_path, read_api_quota)
from cluster_store import ClusterStore
import test_cluster_terminal as node_fixture
import test_quota as quota_fixture


class RemoteQuotaTests(unittest.TestCase):
    """节点真实文件传到中央，原消费器校验来源并持久合并窗口。"""

    def setUp(self) -> None:
        """建立两个独立数据根、实际SQLite和固定时钟。:return: None。"""
        clock = patch('cluster_quota.time.time', return_value=1000.0)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        central = quota_fixture.QuotaGuardTests(methodName='runTest')
        central.setUp()
        self.addCleanup(central.doCleanups)
        node = node_fixture.NodeTerminalTests(methodName='runTest')
        node.setUp()
        self.addCleanup(node.doCleanups)
        self.central, self.node, self.scope = central, node, node.scope
        node.terminals.start(node.request)
        self.quota = NodeTerminalQuota(node.terminals)
        identity = main._quota_identity(central.account)
        node.host.gateway.quotas[1] = lambda _: identity
        self.row = {'operation_id': self.scope.operation_id, 'record': {'scope': self.scope.model_dump(),
            'grant': node.grant.model_dump(), 'node_receipt': node.terminals.get(self.scope), 'quota_identity': identity}}
        self.calls = []

        def call(row, operation, payload):
            self.calls.append(operation)
            return (self.quota.publish(TerminalQuotaState.model_validate(payload)) if operation == 'terminal-quota-state'
                else self.quota.read(TerminalQuotaRead.model_validate(payload)))

        sessions = SimpleNamespace(service=SimpleNamespace(data=central.base, store=ClusterStore(main.get_db, main._db_lock)),
            _call=call, _account=lambda scope: central.account, _operation_lock=lambda _: threading.RLock())
        self.remote = RemoteTerminalQuota(sessions, central.guard, main._quota_identity)
        group = 'projects/' + node.work.id
        self.flows = (node.fixture.root / 'environments' / self.scope.environment_id / 'flows'
            / ('group-' + hashlib.sha256(group.encode()).hexdigest()[:20]) / 'executions'
            / hashlib.sha256(self.scope.source.encode()).hexdigest()[:20])
        (self.flows / 'cli').mkdir(parents=True)

    def event(self, *, source=None, identity=None, used=25, observed=1000.0) -> bytes:
        """创建原状态栏实际格式。:param source: 可选错误来源。:param identity: 可选错误身份。:param used: 使用量。:param observed: 观察时间。:return: 原JSONL行。"""
        return (json.dumps({'source': source or 'cli:' + self.scope.source,
            'identity': identity or self.row['record']['quota_identity'], 'ts': observed, 'origin': 'cli',
            'rate_limits': {'five_hour': {'used_percentage': used, 'resets_at': 1500}}}) + '\n').encode()

    def test_real_quota_file_is_mirrored_consumed_and_published_into_original_node_mount(self) -> None:
        """原QuotaGuard消费所属节点的正常额度，节点门禁沿原只读挂载更新。:return: None。"""
        (self.flows / 'cli/cli-quota.jsonl').write_bytes(self.event())
        self.remote.refresh(self.row)
        state = self.central.guard.snapshot(self.central.account)
        self.assertEqual(25, state['windows']['five_hour']['utilization'])
        path = self.node.fixture.root / 'quota/1/state.json'
        self.assertEqual(state['identity'], json.loads(path.read_text())['identity'])
        self.remote.refresh(self.row)
        connection = main.get_db()
        try:
            row = connection.execute("SELECT * FROM quota_observation_cursors WHERE source=?", ('cli:' + self.scope.source,)).fetchone()
            self.assertEqual(len(self.event()), row['byte_offset'])
        finally:
            connection.close()

    def test_half_lines_wrong_source_and_wrong_identity_preserve_original_consumer_rules(self) -> None:
        """半行等待追加，其他来源和身份的样本不改变中央额度。:return: None。"""
        path = self.flows / 'cli/cli-quota.jsonl'
        path.write_bytes(self.event(source='cli:other') + self.event(identity='other-identity') + self.event()[:-1])
        self.remote.refresh(self.row)
        self.assertFalse(self.central.guard.snapshot(self.central.account)['known'])
        with path.open('ab') as target:
            target.write(b'\n')
        self.clock.return_value = 1001.0
        self.remote.refresh(self.row)
        self.assertEqual(25, self.central.guard.snapshot(self.central.account)['windows']['five_hour']['utilization'])

    def test_rotation_and_crash_after_copy_before_metadata_do_not_skip_new_observation(self) -> None:
        """镜像游标保存失败可重读，节点轮转后较新的真实样本继续被消费。:return: None。"""
        path = self.flows / 'cli/cli-quota.jsonl'
        path.write_bytes(self.event())
        self.remote.refresh(self.row)
        with path.open('ab') as target:
            target.write(self.event(used=50, observed=1001.0))
        self.clock.return_value = 1001.0
        with patch('cluster_quota.atomic_json', side_effect=OSError('合成游标发布中断')):
            with self.assertRaises(OSError):
                self.remote.pull(self.row)
        self.remote.refresh(self.row)
        self.assertEqual(50, self.central.guard.snapshot(self.central.account)['windows']['five_hour']['utilization'])
        temporary = path.with_suffix('.rotated')
        temporary.write_bytes(self.event(used=75, observed=1002.0))
        os.replace(temporary, path)
        self.clock.return_value = 1002.0
        self.remote.refresh(self.row)
        self.assertEqual(75, self.central.guard.snapshot(self.central.account)['windows']['five_hour']['utilization'])

    def test_node_link_and_stale_grant_or_sampling_cannot_replace_original_gate(self) -> None:
        """节点文件链接、旧证明及迟到采样均被拒绝，中央保留原额度事实。:return: None。"""
        path = self.flows / 'cli/cli-quota.jsonl'
        path.symlink_to(self.node.fixture.root / 'cluster-node.json')
        with self.assertRaises(OSError):
            self.remote.pull(self.row)
        path.unlink()
        self.remote.refresh(self.row)
        state = json.loads((self.node.fixture.root / 'quota/1/state.json').read_text())
        request = TerminalQuotaState(scope=self.scope, sequence=1, sampled_at=999.0, state=state)
        with self.assertRaisesRegex(ValueError, '迟到'):
            self.quota.publish(request)
        with self.assertRaisesRegex(ValueError, '失效'):
            self.quota.publish(request.model_copy(update={'sequence': 2, 'sampled_at': 1000.0}))

    def test_shared_sources_keep_separate_context_and_late_other_scope_does_not_rewind_account(self) -> None:
        """同账号两个scope独立保存上下文，迟到的另一scope保留自身收据并维持最新账号窗口。:return: None。"""
        self.remote.refresh(self.row)
        first = TerminalQuotaState.model_validate(json.loads(quota_scope_path(self.node.fixture.root, self.scope).read_text()))
        source = 'projects:' + '9' * 32 + ':1'
        lease = self.node.grant.lease.model_copy(update={'owner': source})
        grant = self.node.grant.model_copy(update={'operation_id': '9' * 32, 'source': source, 'lease': lease})
        self.node.grants.create(grant)
        other = grant.scope()
        self.clock.return_value = 1002.0
        state = {**first.state, 'remote_cli': {'source': source, 'sample_required': False}}
        second = TerminalQuotaState(scope=other, sequence=1, sampled_at=1002.0, state=state)
        self.quota.publish(second)
        self.quota.publish(first)
        self.assertEqual(source, json.loads((self.node.fixture.root / 'quota/1/state.json').read_text())['remote_cli']['source'])
        self.assertEqual(self.scope.source, json.loads(quota_scope_path(self.node.fixture.root, self.scope).read_text())['state']['remote_cli']['source'])
        self.assertEqual(source, json.loads(quota_scope_path(self.node.fixture.root, other).read_text())['state']['remote_cli']['source'])

    def test_small_clock_skew_uses_same_five_second_proof_margin_and_large_future_sample_is_rejected(self) -> None:
        """采样容忍证明合同已有的五秒时钟余量，超出余量保持拒绝。:return: None。"""
        self.remote.refresh(self.row)
        first = TerminalQuotaState.model_validate(json.loads(quota_scope_path(self.node.fixture.root, self.scope).read_text()))
        self.quota.publish(first.model_copy(update={'sampled_at': 1004.0}))
        with self.assertRaisesRegex(ValueError, '采样已失效'):
            self.quota.publish(first.model_copy(update={'sampled_at': 1006.0}))

    def test_closed_source_resume_preserves_original_central_cursor_path(self) -> None:
        """同source的新握手沿同一中央证据镜像和事务游标追加。:return: None。"""
        path = self.flows / 'cli/cli-quota.jsonl'
        path.write_bytes(self.event())
        self.remote.refresh(self.row)
        scope = self.scope.model_copy(update={'operation_id': '9' * 32})
        # 模拟已确认关闭后新握手的原节点收据，源码文件继续由原source追加。
        self.node.terminals._record = lambda _: {'work': self.node.work.model_dump()}
        resumed = {**self.row, 'operation_id': scope.operation_id, 'record': {**self.row['record'], 'scope': scope.model_dump()}}
        with path.open('ab') as target:
            target.write(self.event(used=60, observed=1001.0))
        self.remote.pull(resumed)
        self.central.guard.consume(self.central.account)
        self.assertEqual(60, self.central.guard.snapshot(self.central.account)['windows']['five_hour']['utilization'])


class RemoteApiQuotaTests(unittest.TestCase):
    """发送器真实文件经精确环境范围镜像，继续由原QuotaGuard消费。"""

    def setUp(self) -> None:
        """复用双数据根和真实SQLite夹具，API读取独立于终端生命周期。:return: None。"""
        fixture = RemoteQuotaTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.central, self.node = fixture, fixture.central, fixture.node
        self.scope = ApiQuotaScope(**fixture.scope.model_dump(include={
            'node_key', 'account_id', 'environment_id', 'assignment_revision', 'generation'}))
        self.store = ClusterStore(main.get_db, main._db_lock)
        self.account = {**self.central.account, 'cc2api_account_id': 7}
        connection = main.get_db()
        try:
            with connection:
                node_id = connection.execute("INSERT INTO cluster_nodes(node_key,name,kind,config_json,created_at) "
                    "VALUES(?,'合成API节点','ssh','{}',0)", (self.scope.node_key,)).lastrowid
                connection.execute('UPDATE account_node_assignments SET node_id=? WHERE account_id=1', (node_id,))
                connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json,generation) "
                    "VALUES(?,'fixture',1,'{}',?)", (self.scope.environment_id, self.scope.generation))
        finally:
            connection.close()
        self.calls = []

        def execute(container, payload, operation):
            self.calls.append(operation)
            return {'protocol': 1, 'node_key': self.scope.node_key,
                'quota': read_api_quota(self.node.executor, ApiQuotaRead.model_validate(payload))}

        self.connection = SimpleNamespace(execution_environment=execute)
        service = SimpleNamespace(store=self.store, data=self.central.base, connection=lambda _: self.connection)
        self.remote = RemoteApiQuota(service, SimpleNamespace(deployment='synthetic'), main._quota_identity)
        self.central.guard.remote_api = self.remote
        self.path = self.node.fixture.root / 'environments' / self.scope.environment_id / 'flows/api/observations.jsonl'
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, used=0.2, *, identity=None) -> bytes:
        """构造原sender响应事实。:param used: 原比例。:param identity: 可选错误身份。:return: 原JSONL。"""
        identity = identity or main._quota_identity(self.account)
        return (json.dumps({'source': f'api:{self.scope.environment_id}:{identity}', 'identity': identity,
            'ts': 1000.0, 'origin': 'api', 'status': 200,
            'headers': {'anthropic-ratelimit-unified-5h-utilization': str(used),
                'anthropic-ratelimit-unified-5h-reset': '1500'}}) + '\n').encode()

    def test_api_file_is_consumed_without_terminal_execution_and_half_line_waits(self) -> None:
        """固定API文件半行保留，完整样本被原解析器按真实比例消费。:return: None。"""
        self.path.write_bytes(self.event()[:-1])
        self.central.guard.consume(self.account)
        self.assertFalse(self.central.guard.snapshot(self.account)['known'])
        with self.path.open('ab') as target:
            target.write(b'\n')
        self.central.guard.consume(self.account)
        self.assertEqual(20, self.central.guard.snapshot(self.account)['windows']['five_hour']['utilization'])
        self.assertEqual(['api-quota-read'] * 2, self.calls)

    def test_old_assignment_generation_links_and_network_failure_preserve_quota(self) -> None:
        """旧范围、文件链接和断连拒绝新读取，原消费事实保持。:return: None。"""
        self.path.write_bytes(self.event())
        self.central.guard.consume(self.account)
        for changes in ({'assignment_revision': 2}, {'generation': 2}, {'node_key': '9' * 32}):
            with self.assertRaises(ValueError):
                read_api_quota(self.node.executor, ApiQuotaRead(scope=self.scope.model_copy(update=changes)))
        self.path.unlink()
        self.path.symlink_to(self.node.fixture.root / 'cluster-node.json')
        with self.assertRaises(OSError):
            self.central.guard.consume(self.account)
        self.connection.execution_environment = Mock(side_effect=ValueError('合成节点断连'))
        with self.assertRaisesRegex(ValueError, '断连'):
            self.central.guard.admit(self.account, 'run:synthetic:0')
        self.assertEqual(20, self.central.guard.snapshot(self.account)['windows']['five_hour']['utilization'])

    def test_bound_manual_usage_uses_original_gateway_owner(self) -> None:
        """手动查询交由原刷新所有者，实际发送采用账号节点通道。:return: None。"""
        runner = main.Runner.__new__(main.Runner)
        gateway = Mock()
        gateway.refresh_usage.return_value = {'status': 'ok', 'usage': {'five_hour': {'utilization': 20}}}
        service = SimpleNamespace(store=self.store)
        with patch.object(main, 'account_runtime', Mock()), patch.object(main, 'cluster_service', service), \
                patch.object(main, 'cc2api_client', gateway), \
                patch.object(main, '_sync_bound_account_credentials_locked') as synchronize:
            result = runner.query_quota({**self.account, 'upstream_socks5_host': 'synthetic.invalid'})
        self.assertTrue(result['ok'])
        gateway.refresh_usage.assert_called_once_with(7)
        synchronize.assert_called_once_with({**self.account, 'upstream_socks5_host': 'synthetic.invalid'}, 600)

    def test_corrupt_cursor_is_preserved_and_manual_failure_remains_explicit(self) -> None:
        """坏游标拒绝覆盖，网关失败回执保持明确查询失败。:return: None。"""
        self.path.write_bytes(self.event())
        self.remote.pull(self.account)
        metadata = next((self.central.base / 'cluster-quota').glob('*/api.json'))
        value = json.loads(metadata.read_text())
        value['offset'] = True
        metadata.write_text(json.dumps(value))
        original = metadata.read_bytes()
        with self.assertRaises(ValueError):
            self.remote.pull(self.account)
        self.assertEqual(original, metadata.read_bytes())
        gateway = Mock()
        gateway.refresh_usage.return_value = {'status': 'error', 'message': '合成节点待核对'}
        with patch.object(main, 'account_runtime', Mock()), \
                patch.object(main, 'cluster_service', SimpleNamespace(store=self.store)), \
                patch.object(main, 'cc2api_client', gateway), \
                patch.object(main, '_sync_bound_account_credentials_locked'):
            with self.assertRaisesRegex(ValueError, '所属节点额度查询未完成'):
                main.Runner.__new__(main.Runner).query_quota({**self.account, 'upstream_socks5_host': 'synthetic.invalid'})

    def test_remote_credential_snapshot_updates_central_profile_before_node_preparation(self) -> None:
        """中央只解析原网关快照，实际HOME发布留在所属节点。:return: None。"""
        runtime = Mock()
        runtime._row.side_effect = AssertionError('远程凭据不得创建中央本机HOME')
        runtime.sync_credentials.side_effect = AssertionError('实际HOME必须由所属节点发布')
        snapshot = {'account_id': 7}
        with patch.object(main, 'account_runtime', runtime), patch.object(main, 'credential_ownership', None), \
                patch.object(main, 'cluster_service', SimpleNamespace(store=self.store)), \
                patch.object(main, '_resolve_and_sync_cc2api_credentials', return_value=snapshot) as resolve:
            self.assertEqual(snapshot, main._sync_bound_account_credentials_locked(self.account, 600))
        resolve.assert_called_once_with(self.account['name'], 7, 600, False)
