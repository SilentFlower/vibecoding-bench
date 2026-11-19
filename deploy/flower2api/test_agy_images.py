"""检查镜像验收绑定正式清单并显式使用镜像包。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agy_auth import SOURCE_BYTES, SOURCE_SHA256
import verify_agy_images as verifier


class AgyImageTests(unittest.TestCase):
    """覆盖验收顺序和处理产物缺失的发布前拒绝。"""

    def setUp(self) -> None:
        """建立独立的同批引用。@return 无。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.manifest = Path(temporary.name) / 'manifest.json'
        self.value = {'agy_auth': {'available': True, 'source_version': '1.5.9', 'bytes': SOURCE_BYTES, 'sha256': SOURCE_SHA256},
            'images': {role: {'reference': 'synthetic-' + role} for role in ('control', 'account')}}
        self.manifest.write_text(json.dumps(self.value))

    def test_checks_actual_package_before_both_native_exit_modes(self) -> None:
        """两个角色只用镜像自带目录，原生正常与异常退出均执行。@return 无。"""
        with patch.object(verifier.manage, 'inspect_images') as inspect, patch.object(verifier.manage, 'command') as command, \
                patch.object(verifier, 'native_probe', return_value={'passed': True, 'model_submissions': 0}) as probe:
            result = verifier.verify_images(self.manifest)
        inspect.assert_called_once()
        self.assertEqual(2, command.call_count)
        for call in command.call_args_list:
            self.assertIn('none', call.args)
            self.assertNotIn('-v', call.args)
        self.assertIn('PYTHONPATH=/opt/v3/python:/usr/local/bin', command.call_args_list[1].args)
        self.assertEqual(probe.call_args_list[0].kwargs, {'image_package': True})
        self.assertEqual(probe.call_args_list[1].kwargs, {'crash': True, 'image_package': True})
        self.assertTrue(result['passed'])

    def test_missing_asset_stops_before_any_container(self) -> None:
        """能力声明缺失时，实际容器验收也保持零启动。@return 无。"""
        self.value.pop('agy_auth')
        self.manifest.write_text(json.dumps(self.value))
        with patch.object(verifier.manage, 'command') as command, patch.object(verifier, 'native_probe') as probe:
            with self.assertRaisesRegex(ValueError, 'AGY'):
                verifier.verify_images(self.manifest)
            command.assert_not_called()
            probe.assert_not_called()
