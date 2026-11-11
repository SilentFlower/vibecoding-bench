"""检查真实兼容演练入口的受信来源与镜像身份边界。"""
import unittest
import os
import subprocess
import sys
from urllib.error import HTTPError
from unittest.mock import patch

import verify_database_compatibility as verifier


class CompatibilitySourceTests(unittest.TestCase):
    """用读取边界故障验证通道降级规则。"""

    def test_existing_migration_channel_asset_failure_stops(self) -> None:
        """新通道存在时，资产缺失直接失败。@return None。"""
        error = HTTPError('https://synthetic.invalid/index.json', 404, 'synthetic', {}, None)
        with patch.object(verifier, 'fetch_bytes', return_value=b'{"object":{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}') as fetch:
            with patch.object(verifier, 'fetch_repository_file', side_effect=error):
                with self.assertRaises(HTTPError):
                    verifier._sources('a' * 64, None)
        self.assertEqual(fetch.call_count, 1)

    def test_only_missing_migration_reference_falls_back(self) -> None:
        """首次迁移通道尚未创建时才读取旧通道。@return None。"""
        error = HTTPError('https://synthetic.invalid/ref', 404, 'synthetic', {}, None)
        with patch.object(verifier, 'fetch_bytes', side_effect=[error, b'{"object":{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}']) as fetch:
            with patch.object(verifier, 'fetch_repository_file', side_effect=ValueError('合成停止点')):
                with self.assertRaisesRegex(ValueError, '合成停止点'):
                    verifier._sources('a' * 64, None)
        self.assertEqual(fetch.call_count, 2)
        self.assertTrue(fetch.call_args.args[0].endswith('/updates/v3'))

    def test_standalone_entry_and_discovery_work_without_pythonpath(self) -> None:
        """CI 默认环境可直接加载演练入口及独立快照测试。@return None。"""
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        for arguments in ([str(verifier.REPO / 'deploy/v3/verify_database_compatibility.py'), '--help'],
                ['-m', 'unittest', 'discover', '-s', 'deploy/v3', '-p', 'test_system_database.py']):
            result = subprocess.run([sys.executable, *arguments], cwd=verifier.REPO, env=environment,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
