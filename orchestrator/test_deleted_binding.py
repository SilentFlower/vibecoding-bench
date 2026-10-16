"""验证远端账号删除后的解绑收口，不使用真实账号或 Docker。"""
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

from account_runtime import AccountRuntime
import main


class DeletedBindingTests(unittest.TestCase):
    """通过真实管理客户端、运行时及 SQLite 验证缺失判断与占用保护。"""

    def setUp(self) -> None:
        """准备独立绑定与停止的合成发送实例。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, value in [('DB_PATH', self.root / 'db.sqlite'), ('PROFILES_DIR', self.root / 'profiles'),
                ('TOPICS_FILE', self.root / 'missing.md'), ('login_manager', None),
                ('continue_manager', None), ('warmup_scheduler', None)]:
            guard = patch.object(main, name, value)
            guard.start()
            self.addCleanup(guard.stop)
        main.init_db()
        with closing(main.get_db()) as database, database:
            database.execute("INSERT INTO accounts(name,profile_path,cc2api_account_id,warmup_enabled,"
                "warmup_next_run_at,warmup_last_status) VALUES('synthetic','profiles/synthetic',7,1,123,'scheduled')")
        self.client = Mock()
        guard = patch.dict(os.environ, {'V3_DEPLOYMENT_ID': 'synthetic-unbind',
            'V3_ACCOUNT_IMAGE': 'synthetic-image', 'V3_NETWORK': 'synthetic-network'})
        guard.start()
        self.addCleanup(guard.stop)
        self.gateway = main.Cc2ApiClient('http://synthetic.invalid', 'synthetic-password', 1)
        self.runtime = AccountRuntime(self.client, self.root, self.root, main.get_db,
            lambda timezone: {'profile_version': 2, 'mem': '4g', 'swap': '0'}, self.gateway)
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)
        guard = patch.object(main, 'account_runtime', self.runtime)
        guard.start()
        self.addCleanup(guard.stop)
        self.row = self.runtime._row('synthetic', 1)
        self.runtime._update(self.row, container_id='old-synthetic-instance')
        self.container = Mock(status='exited')
        guard = patch.object(self.runtime, '_container', return_value=self.container)
        guard.start()
        self.addCleanup(guard.stop)
        self.paths = []
        self.remote_status = 404
        self.prepare_missing = False
        self.list_response = {'data': [], 'page': 1, 'page_size': 100, 'total': 0, 'total_pages': 0}
        guard = patch('main.urllib.request.urlopen', side_effect=self._respond)
        guard.start()
        self.addCleanup(guard.stop)

    def _respond(self, request, **kwargs):
        """模拟管理 HTTP 响应，保留生产客户端生成的真实异常链。"""
        self.paths.append((request.method, request.full_url))
        if '/admin/accounts?' in request.full_url:
            if isinstance(self.list_response, Exception):
                raise self.list_response
            value = self.list_response
            if callable(value):
                value = value(request.full_url)
        elif self.remote_status != 200 or (self.prepare_missing and request.method == 'POST'):
            if self.remote_status == 'network':
                raise URLError('synthetic offline')
            code = 404 if self.prepare_missing else self.remote_status
            raise HTTPError(request.full_url, code, 'synthetic', {}, BytesIO(b'{"error":"not found"}'))
        else:
            payload = json.loads(request.data) if request.data else {}
            lease = None if request.method == 'GET' or payload.get('operation') == 'release' else {
                'owner': payload['owner'], 'generation': 'synthetic-generation'}
            value = {'active': 0, 'waiting': 0, 'lease': lease}
        return closing(BytesIO(json.dumps(value).encode()))

    def _binding(self) -> tuple:
        """读取解绑与养号状态，供成功和拒绝场景交叉核对。"""
        with closing(main.get_db()) as database:
            return tuple(database.execute('SELECT cc2api_account_id,warmup_enabled,warmup_next_run_at,'
                'warmup_last_status FROM accounts WHERE id=1').fetchone())

    def test_deleted_remote_account_unbinds_and_repeated_unbind_is_idempotent(self) -> None:
        """明确删除后可解绑，写库前停止原实例，重复调用保持成功。@return None。"""
        self.container.stop.side_effect = lambda **kwargs: self.assertEqual(7, self._binding()[0])
        self.assertEqual({'ok': True}, main.delete_account_cc2api_binding(1))
        self.assertEqual((None, 0, None, 'off'), self._binding())
        self.container.stop.assert_called_once_with(timeout=5)
        self.container.stop.side_effect = None
        self.assertEqual({'ok': True}, main.delete_account_cc2api_binding(1))
        self.assertEqual(1, sum('/admin/accounts?' in path for method, path in self.paths))
        self.assertFalse(any(method == 'POST' for method, path in self.paths))

    def test_unbind_preserves_home_profile_and_device_identity(self) -> None:
        """悬空解绑保留原 HOME、设备及本地凭据内容，不重建账号。@return None。"""
        profile = self.root / 'profiles/synthetic'
        home = self.runtime._root(self.row) / 'home'
        values = {profile / '.credentials.json': {'claudeAiOauth': {'accessToken': 'profile-at', 'refreshToken': 'profile-rt'}},
            home / '.claude/.credentials.json': {'claudeAiOauth': {'accessToken': 'home-at'}},
            profile / '.claude.json': {'userID': 'd' * 64}, home / '.claude.json': {'userID': 'd' * 64}}
        for path, value in values.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value))
        original = self.runtime._row('synthetic', 1)
        main.delete_account_cc2api_binding(1)
        after = self.runtime._row('synthetic', 1)
        self.assertEqual(original['environment_id'], after['environment_id'])
        self.assertEqual(original['fingerprint_json'], after['fingerprint_json'])
        for path, value in values.items():
            self.assertEqual(value, json.loads(path.read_text()))

    def test_delete_local_account_with_deleted_remote_binding(self) -> None:
        """本地删除复用相同收口规则，不依赖已经删除的远端。@return None。"""
        result = main.delete_account(1)
        self.assertTrue(result['ok'])
        with closing(main.get_db()) as database:
            self.assertIsNone(database.execute('SELECT id FROM accounts WHERE id=1').fetchone())

    def test_remote_deletion_between_status_and_prepare_still_unbinds(self) -> None:
        """GET 后删除导致 prepare 404 时仍须确认列表缺失并完成本地收口。@return None。"""
        self.remote_status = 200
        self.prepare_missing = True
        self.assertEqual({'ok': True}, main.delete_account_cc2api_binding(1))
        self.assertIsNone(self._binding()[0])

    def test_other_http_errors_and_network_failure_preserve_binding(self) -> None:
        """不能依据错误文案把鉴权、服务和网络错误当作账号删除。@return None。"""
        for status in (400, 401, 403, 408, 429, 500, 503, 'network'):
            with self.subTest(status=status):
                self.remote_status = status
                with self.assertRaises(main.HTTPException):
                    main.delete_account_cc2api_binding(1)
                self.assertEqual((7, 1, 123, 'scheduled'), self._binding())
                self.container.stop.assert_not_called()
        self.assertFalse(any('/admin/accounts?' in path for method, path in self.paths))

    def test_404_requires_successful_complete_account_list(self) -> None:
        """错误路由、列表损坏或分页不完整都不能成为删除证明。@return None。"""
        cases = [
            {'data': [{'id': 7}], 'page': 1, 'page_size': 100, 'total': 1, 'total_pages': 1},
            {'data': [None], 'page': 1, 'page_size': 100, 'total': 1, 'total_pages': 1},
            {'data': [{}], 'page': 1, 'page_size': 100, 'total': 1, 'total_pages': 1},
            {'data': [], 'total_pages': 0},
            {'data': [], 'page': 1, 'page_size': 100, 'total': 1, 'total_pages': 1},
            {'data': [], 'page': 1, 'page_size': 100, 'total': 0, 'total_pages': -1},
            URLError('synthetic list offline'),
        ]
        for response in cases:
            with self.subTest(response=response):
                self.list_response = response
                with self.assertRaises(main.HTTPException):
                    main.delete_account_cc2api_binding(1)
                self.assertEqual(7, self._binding()[0])
                self.container.stop.assert_not_called()

    def test_deleted_remote_binding_never_bypasses_local_work(self) -> None:
        """本地任务或环境作业仍阻止解绑，不发起远端缺失探测。@return None。"""
        with closing(main.get_db()) as database, database:
            database.execute("INSERT INTO runs(id,task_id,account_id,status) VALUES('synthetic-run',1,1,'queued')")
        with self.assertRaises(main.HTTPException):
            main.delete_account_cc2api_binding(1)
        self.assertFalse(self.paths)
        with closing(main.get_db()) as database, database:
            database.execute('DELETE FROM runs')
        self.runtime.jobs[self.row['environment_id']] = {}
        with self.assertRaises(main.HTTPException):
            main.delete_account_cc2api_binding(1)
        self.assertEqual(7, self._binding()[0])
        self.container.stop.assert_not_called()
        self.assertFalse(self.paths)

    def test_original_account_on_later_page_still_blocks_missing_recovery(self) -> None:
        """必须读取后续页面，不能因第一页找不到原 ID 就允许解绑。@return None。"""
        self.list_response = lambda url: {'data': [{'id': 7}] if '?page=2&' in url else [
            {'id': value} for value in range(1001, 1101)], 'page': 2 if '?page=2&' in url else 1,
            'page_size': 100, 'total': 101, 'total_pages': 2}
        with self.assertRaises(main.HTTPException):
            main.delete_account_cc2api_binding(1)
        self.assertEqual(7, self._binding()[0])
        self.assertTrue(any('?page=2&' in path for method, path in self.paths))
        self.container.stop.assert_not_called()

    def test_deleted_remote_account_does_not_bypass_sender_occupancy(self) -> None:
        """原实例仍有活动发送或状态未知时不停止它也不改绑定。@return None。"""
        self.container.status = 'running'
        for state in (1, ValueError('synthetic invalid status'), URLError('synthetic sender offline')):
            with self.subTest(state=state), patch.object(self.runtime, '_sender_active') as active:
                if isinstance(state, Exception):
                    active.side_effect = state
                else:
                    active.return_value = state
                with self.assertRaises((main.HTTPException, URLError)):
                    main.delete_account_cc2api_binding(1)
                self.assertEqual(7, self._binding()[0])
                self.container.stop.assert_not_called()

    def test_missing_target_or_rebinding_keeps_strict_remote_gate(self) -> None:
        """缺失放行只适用于解绑原账号，新绑定目标仍严格拒绝。@return None。"""
        with self.assertRaises(ValueError):
            with self.runtime.owner_transition({'id': 1, 'name': 'synthetic', 'cc2api_account_id': 7}, 8):
                self.fail('不得进入改绑事务')
        self.assertFalse(any('/admin/accounts?' in path for method, path in self.paths))
        self.container.stop.assert_not_called()

    def test_normal_unbind_keeps_prepare_and_release(self) -> None:
        """远端仍存在时沿用排他门禁，并在本地写入后释放。@return None。"""
        self.remote_status = 200
        self.assertEqual({'ok': True}, main.delete_account_cc2api_binding(1))
        self.assertEqual(['GET', 'POST', 'POST'], [method for method, path in self.paths])
        self.assertIsNone(self._binding()[0])


if __name__ == '__main__':
    unittest.main()
