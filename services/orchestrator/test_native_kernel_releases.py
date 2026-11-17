"""独立发行发现退役后的离线兼容合同。"""
import unittest
from unittest.mock import patch
from native_kernel_releases import discover_releases


class ReleaseDiscoveryTests(unittest.TestCase):
    """历史导入只返回平台管理说明。"""

    def test_discovery_is_retired_without_network(self):
        """刷新参数也保持零网络副作用。@return None。"""
        with patch('urllib.request.urlopen', side_effect=AssertionError('退役入口禁止网络')):
            for refresh in (False, True):
                self.assertEqual(discover_releases(refresh), {
                    'state': 'retired', 'management': 'platform', 'versions': [], 'latest': None})
