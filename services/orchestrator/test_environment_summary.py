"""环境汇总的并发上限、排序和请求上下文回归。"""
import threading
import time
import unittest
from contextvars import ContextVar
from unittest.mock import Mock, patch

import main


class EnvironmentSummaryTests(unittest.TestCase):
    """只替换环境核对边界，验证实际路由的汇总语义。"""

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


if __name__ == '__main__':
    unittest.main()
