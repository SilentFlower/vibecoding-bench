"""原生 sender 的显式预算、加权容量及旧布局回归。"""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from native_sender import NativePreparationBlocked, sender_config, installed_versions, native_resource_layout, stage_asset
from native_criu_policy import restore_policy
from resource_budget import account_limits, memory_bytes, isolated_account_limits, scenario_account_limits, serial_review_limits


class NativeSenderTests(unittest.TestCase):
    """使用合成配置核对有限资源与可回退的后端选择。"""

    def test_293_staging_requires_local_input_and_rejects_corruption(self):
        """缺失输入直接提示本仓库准备，损坏附件在staging阶段拒绝。@return None。"""
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'V3_NATIVE_RUNTIME_ASSET': ''}):
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, '本仓库准备293'):
                stage_asset(root / 'output')
            source = root / 'input'
            source.write_bytes(b'corrupted synthetic launcher')
            with self.assertRaisesRegex(ValueError, '身份不匹配'):
                stage_asset(root / 'output', str(source))
            self.assertFalse((root / 'output').exists())
        self.assertEqual(installed_versions({'vibebench.native-runtime-versions':'2.1.293'}), ('2.1.293',))

    def test_dual_version_budget_and_resource_identity(self):
        """两版低额度配置保留共享六槽及发行切换资源身份。@return None。"""
        self.assertEqual(installed_versions({}), ('2.1.293',))
        versions = installed_versions({'vibebench.native-runtime-versions': '2.1.280,2.1.293'})
        with self.assertRaises(ValueError):
            installed_versions({'vibebench.native-runtime-versions': '2.1.280'})
        account = {'request_backend': 'native293', 'concurrency': 3}
        for budget, expected in [('128m', 128), ('1535m', 1535), ('1536m', 1536)]:
            config = sender_config(account, '4g', budget=budget, versions=versions)
            self.assertEqual(config['memory_mib'], expected)
            self.assertEqual(config['max_workers'], 6)
        self.assertEqual(config['max_workers'], 6)
        self.assertEqual(config['runtimes']['2.1.280']['binary_path'], '/usr/local/bin/ccrb-runtime-280')
        before = native_resource_layout(config)
        config['runtimes']['2.1.280'].update(release={'release': 'synthetic', 'launcher_sha256': 'a'*64}, kernel_generation='new')
        self.assertEqual(native_resource_layout(config), before)

    def test_criu_accounts_for_each_restored_code_image(self):
        """显式恢复开关覆盖每进程独立代码映像预算。@return 无。"""
        account = {'request_backend': 'native293', 'concurrency': 3}
        with patch.dict('os.environ', {'V3_NATIVE_CRIU': '1'}):
            ordinary = sender_config(account, '4g', budget='128m')
            self.assertEqual(restore_policy(ordinary, {}, True)['reason'], 'memory_budget')
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
        for budget in ['', '0', '-1m', 'unlimited', '1.5g', '4g']:
            with self.assertRaises(ValueError):
                sender_config(account, '4g', budget=budget)
        configuration = sender_config(account, '4g', budget='1536m')
        self.assertEqual(configuration['max_workers'], 6)
        self.assertEqual(sender_config(account, '4g', budget='1408m')['memory_mib'], 1408)
        self.assertEqual(sender_config(account, '4g', budget='1407m')['memory_mib'], 1407)
        limits = isolated_account_limits('4g', '1g', '1536m')
        self.assertEqual(sum(value[0] for value in limits.values()), 4 * 1024 ** 3)
        self.assertEqual(limits['sender'], (1536 * 1024 ** 2,) * 2)
        self.assertEqual(limits['cli'][1] - limits['cli'][0], 1024 ** 3)
        review = scenario_account_limits('4g', '1g', '1536m')
        self.assertEqual(sum(value[0] for value in review.values()), 4 * 1024 ** 3)
        self.assertEqual(review['cli'][0], 1792 * 1024 ** 2)
        self.assertEqual(serial_review_limits('4g', '1g', '1536m'), (2304 * 1024 ** 2,) * 2)

    def test_preparation_resource_failures_use_explicit_safe_codes(self):
        """资源预检保留兼容异常并提供固定原因，UI 无需猜测 503。@return None。"""
        account = {'request_backend': 'native293', 'concurrency': 4}
        for memory, budget, reason in [('1536m', '', 'native_sender_budget_missing'),
                ('1536m', '1792m', 'account_memory_insufficient')]:
            with self.subTest(reason=reason), self.assertRaises(NativePreparationBlocked) as error:
                sender_config(account, memory, budget=budget)
            self.assertEqual(reason, error.exception.reason)
        self.assertEqual(8, sender_config(account, '2560m', budget='1792m')['max_workers'])
        self.assertEqual(8, sender_config(account, '4g', budget='1536m')['max_workers'])

    def test_capacity_follows_account_concurrency_without_memory_formula(self):
        """更高账号并发保持原容量，显式额度独立冻结。@return None。"""
        for concurrency in [33, 100]:
            configuration = sender_config({'request_backend':'native293', 'concurrency':concurrency}, '32g', budget='128m')
            self.assertEqual(configuration['max_workers'], concurrency * 2)
            self.assertEqual(configuration['memory_mib'], 128)

    def test_unknown_backend_and_nonpositive_concurrency_fail(self):
        """未知后端与非正数并发明确拒绝。@return None。"""
        for configuration in [{'request_backend':'unknown'}, {'request_backend':'native293', 'concurrency':0},
                {'request_backend':'native293', 'concurrency':-1}]:
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
