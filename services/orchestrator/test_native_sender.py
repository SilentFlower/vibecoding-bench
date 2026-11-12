"""原生 sender 的显式预算、加权容量及旧布局回归。"""
import unittest
from unittest.mock import patch

from native_sender import sender_config
from resource_budget import account_limits, memory_bytes, isolated_account_limits, scenario_account_limits, serial_review_limits


class NativeSenderTests(unittest.TestCase):
    """使用合成配置核对有限资源与可回退的后端选择。"""

    def test_criu_accounts_for_each_restored_code_image(self):
        """显式恢复开关覆盖每进程独立代码映像预算。@return 无。"""
        account = {'request_backend': 'native293', 'concurrency': 3}
        with patch.dict('os.environ', {'V3_NATIVE_CRIU': '1'}):
            with self.assertRaises(ValueError):
                sender_config(account, '4g', budget='1536m')
            self.assertEqual(sender_config(account, '4g', budget='2056m')['max_workers'], 6)
            self.assertEqual(sender_config(account, 'unlimited', budget='')['memory_mib'], 0)
        with patch.dict('os.environ', {'V3_NATIVE_CRIU': '0'}):
            self.assertEqual(sender_config(account, '4g', budget='1408m')['max_workers'], 6)

    def test_default_keeps_legacy_budget(self):
        """省略后端保持原 sender 布局。@return None。"""
        self.assertIsNone(sender_config({}, '4g', budget=''))
        self.assertEqual(isolated_account_limits('4g')['sender'][0], 128 * 1024 ** 2)

    def test_native_requires_budget_and_preserves_account_total(self):
        """默认标准并发三覆盖六个物理进程，总预算保持不变。@return None。"""
        account = {'request_backend': 'native293', 'concurrency': 3}
        for budget in ['', '0', '1407m', '4g']:
            with self.assertRaises(ValueError):
                sender_config(account, '4g', budget=budget)
        configuration = sender_config(account, '4g', budget='1536m')
        self.assertEqual(configuration['max_workers'], 6)
        self.assertEqual(sender_config(account, '4g', budget='1408m')['memory_mib'], 1408)
        limits = isolated_account_limits('4g', '1g', '1536m')
        self.assertEqual(sum(value[0] for value in limits.values()), 4 * 1024 ** 3)
        self.assertEqual(limits['sender'], (1536 * 1024 ** 2,) * 2)
        self.assertEqual(limits['cli'][1] - limits['cli'][0], 1024 ** 3)
        review = scenario_account_limits('4g', '1g', '1536m')
        self.assertEqual(sum(value[0] for value in review.values()), 4 * 1024 ** 3)
        self.assertEqual(review['cli'][0], 1792 * 1024 ** 2)
        self.assertEqual(serial_review_limits('4g', '1g', '1536m'), (2304 * 1024 ** 2,) * 2)

    def test_capacity_follows_account_budget_without_artificial_worker_ceiling(self):
        """更高账号并发由显式预算决定。@return None。"""
        configuration = sender_config({'request_backend':'native293', 'concurrency':33}, '32g', budget='30g')
        self.assertEqual(configuration['max_workers'], 66)

    def test_unknown_backend_and_excessive_concurrency_fail(self):
        """未知后端与超出有限池容量的配置明确拒绝。@return None。"""
        for configuration in [{'request_backend':'unknown'}, {'request_backend':'native293', 'concurrency':100}]:
            with self.assertRaises(ValueError):
                sender_config(configuration, '32g', budget='30g')

    def test_unlimited_preserves_capacity_and_explicit_resource_semantics(self):
        """无限账号跳过 RAM 门槛，保留并发与严格有限解析。@return None。"""
        configuration = sender_config({'request_backend': 'native293', 'concurrency': 2}, 'unlimited', '2048m', budget='')
        self.assertEqual((configuration['memory_mib'], configuration['max_workers']), (0, 4))
        self.assertEqual(account_limits('unlimited', '2048m'), (0, -1))
        self.assertEqual(set(isolated_account_limits('unlimited', '2048m', 'unlimited').values()), {(0, -1)})
        self.assertEqual(scenario_account_limits('unlimited')['review'], (0, -1))
        self.assertEqual(serial_review_limits('unlimited', '2048m'), (0, -1))
        for invalid in ['0', '-1', 'Unlimited', 'unlimited ']:
            with self.assertRaises(ValueError):
                account_limits(invalid)
        with self.assertRaises(ValueError):
            memory_bytes('unlimited')
        with self.assertRaises(ValueError):
            account_limits('unlimited', '-1')
        with self.assertRaises(ValueError):
            sender_config({'request_backend': 'native293', 'concurrency': 0}, 'unlimited')
