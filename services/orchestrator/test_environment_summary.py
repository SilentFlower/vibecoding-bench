"""环境汇总的并发上限、排序和请求上下文回归。"""
import threading
import time
import unittest
from contextvars import ContextVar
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, call, patch

import main


class EnvironmentSummaryTests(unittest.TestCase):
    """只替换环境核对边界，验证实际路由的汇总语义。"""

    def test_local_and_remote_report_effective_request_backend(self):
        """本机与远程使用网关已生效的后端，未知值和缺失快照保持为空。@return 无。"""
        row = {'environment_id': 'a' * 32, 'name': 'synthetic', 'account_id': 1,
            'generation': 1, 'fingerprint_json': '{"tz":"UTC"}'}
        db = Mock()
        db.execute.return_value.fetchone.return_value = {'id': 1, 'cc2api_account_id': 7}
        cluster = Mock()
        cluster.remote_summary.return_value = {}
        runtime = MagicMock()
        runtime.environment_lock.return_value.acquire.return_value = False
        with TemporaryDirectory() as directory, patch('agy_environment.lookup_environment', return_value=None), \
                patch.multiple(main, account_runtime=runtime, cluster_service=cluster), \
                patch.object(main, 'get_db', return_value=db), patch.object(main, 'effective_claude_code_version', return_value='2.1.293'):
            runtime._root.return_value = Path(directory)
            runtime._sender_config.return_value = Path(directory) / 'sender.json'
            for kind in ('local', 'ssh'):
                cluster.store.assignment.return_value = {'kind': kind}
                for backend, expected in (('legacy', 'legacy'), ('native293', 'native293'), ('tui_v2', 'tui_v2'),
                        ('future', None), (None, None)):
                    with self.subTest(kind=kind, backend=backend):
                        snapshots = {7: {'request_backend': backend, 'request_backend_pending': 'tui_v2'}} if backend else {}
                        result = main._v3_environment_summary(dict(row), {}, snapshots, None)
                        self.assertEqual(result['request_backend'], expected)

    def test_bounded_parallel_order_and_context(self):
        """慢环境并行读取后仍保持顺序及调用方上下文。@return None。"""
        rows = [{'environment_id': str(number)} for number in range(4)]
        connection = Mock()
        connection.execute.return_value = rows
        runtime = Mock()
        runtime.native_preparation_snapshots.return_value = ({}, None)
        context = ContextVar('summary_test_context', default='missing')
        token = context.set('synthetic-request')
        barrier = threading.Barrier(3)
        lock = threading.Lock()
        active = 0
        maximum = 0

        def summary(row, ownerships, snapshots, error):
            """模拟顺序不同的慢只读核对。@param row 环境。@param ownerships 归属。@param snapshots 快照。@param error 错误。@return 公开投影。"""
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                if int(row['environment_id']) < 3:
                    barrier.wait(timeout=3)
                time.sleep((3 - int(row['environment_id'])) * .01)
                return dict(row, context=context.get())
            finally:
                with lock:
                    active -= 1

        try:
            with patch.object(main, 'get_db', return_value=connection), \
                    patch.object(main, 'account_runtime', runtime), \
                    patch.object(main, 'credential_ownership', None), \
                    patch.object(main, '_v3_environment_summary', side_effect=summary):
                result = main.v3_environments()
            self.assertEqual([row['environment_id'] for row in result], ['0', '1', '2', '3'])
            self.assertTrue(all(row['context'] == 'synthetic-request' for row in result))
            self.assertEqual(maximum, 3)
            connection.close.assert_called_once()
        finally:
            context.reset(token)

    def test_empty_list_and_failed_summary_keep_error_contract(self):
        """空列表不启动汇总，错误保持原异常。@return None。"""
        connection = Mock()
        runtime = Mock()
        runtime.native_preparation_snapshots.return_value = ({}, None)
        with patch.object(main, 'get_db', return_value=connection), \
                patch.object(main, 'account_runtime', runtime), \
                patch.object(main, 'credential_ownership', None), \
                patch.object(main, '_v3_environment_summary', side_effect=ValueError('合成核对失败')) as summary:
            connection.execute.return_value = []
            self.assertEqual(main.v3_environments(), [])
            summary.assert_not_called()
            connection.execute.return_value = [{'environment_id': 'synthetic'}]
            with self.assertRaisesRegex(ValueError, '合成核对失败'):
                main.v3_environments()

    def test_agy_environment_uses_current_gateway_name_by_account_id(self):
        """环境保留内部名，同时按平台批量读取最新显示名称。@return 无。"""
        rows = [{'environment_id': 'synthetic', 'platform': 'antigravity', 'name': 'agy:14', 'gateway_account_id': 14},
            {'environment_id': 'other', 'platform': 'antigravity', 'name': 'agy:15', 'gateway_account_id': 15}]
        connection = Mock()
        connection.execute.return_value = rows
        runtime = Mock()
        runtime.native_preparation_snapshots.return_value = ({}, None)
        gateway = main.Cc2ApiClient('http://synthetic.invalid', 'synthetic-only', 1)
        pages = [
            {'data': [{'id': 15, 'name': '其他平台', 'platform': 'claude_code'}], 'total_pages': 2},
            {'data': [{'id': 14, 'name': '反重力测试账号', 'platform': 'antigravity'}], 'total_pages': 2},
            ConnectionError('网关不可用'),
        ]
        with patch.multiple(main, account_runtime=runtime, credential_ownership=None, cc2api_client=gateway), \
                patch.object(main, 'get_db', return_value=connection), \
                patch.object(main, '_v3_environment_summary', side_effect=lambda row, *_: row), \
                patch.object(gateway, '_request', side_effect=pages) as request:
            result = main.v3_environments()
            self.assertEqual(result[0]['gateway_account_name'], '反重力测试账号')
            self.assertEqual(result[0]['name'], 'agy:14')
            self.assertEqual(result[0]['gateway_account_id'], 14)
            self.assertIsNone(result[1]['gateway_account_name'])
            self.assertTrue(all(row['gateway_account_name'] is None for row in main.v3_environments()))
            first = call('GET', '/admin/accounts?page=1&page_size=100&platform=antigravity')
            second = call('GET', '/admin/accounts?page=2&page_size=100&platform=antigravity')
            self.assertEqual(request.call_args_list, [first, second, first])


if __name__ == '__main__':
    unittest.main()
