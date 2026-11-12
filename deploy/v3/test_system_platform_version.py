"""语义版本元数据、历史兼容及正式发布递增合同。"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from source_layout import source_path

sys.path.insert(0, str(source_path(Path(__file__).resolve().parents[2], 'orchestrator')))
from platform_version import ensure_forward_version, read_version, signed_changes, version_from_changes


class PlatformVersionTests(unittest.TestCase):
    """版本来源及受信说明保持一致。"""

    def test_metadata_and_signed_projection(self):
        """真实元数据生成可读版本，非法或旧说明保持区别。@return None。"""
        value = read_version(Path(__file__).with_name('platform-release.json'))
        self.assertEqual(version_from_changes(signed_changes(value)), tuple(map(int, value['version'][1:].split('.'))))
        self.assertIsNone(version_from_changes('历史发行'))
        self.assertIsNone(version_from_changes('平台版本：v01.0.0'))
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'version.json'
            for invalid in [dict(value, version='1.0.0'), dict(value, extra=True), dict(value, schema_version=True)]:
                target.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    read_version(target)

    def test_patch_feature_legacy_and_same_source_rerun(self):
        """允许递增及同源重跑，不同源码必须更新版本。@return None。"""
        previous = {'changes': '平台版本：v1.0.0\n旧说明', 'control': {'revision': 'a' * 40}, 'account': {'revision': 'b' * 40}}
        ensure_forward_version(copy.deepcopy(previous), previous)
        for version in ['v1.0.1', 'v1.1.0', 'v2.0.0']:
            current = copy.deepcopy(previous)
            current['changes'] = '平台版本：' + version
            current['control']['revision'] = 'c' * 40
            ensure_forward_version(current, previous)
        for version in ['v1.0.0', 'v0.9.0']:
            current = copy.deepcopy(previous)
            current['changes'] = '平台版本：' + version
            current['account']['revision'] = 'c' * 40
            with self.assertRaisesRegex(ValueError, '递增'):
                ensure_forward_version(current, previous)
        ensure_forward_version(previous, dict(previous, changes='旧说明'))


if __name__ == '__main__':
    unittest.main()
