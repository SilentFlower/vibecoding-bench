"""组装快照只读访问与账号隔离回归。"""
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from native_capture import MAX_CAPTURE_BYTES, read_capture


class NativeCaptureTests(unittest.TestCase):
    """用合成快照验证归属、链接和读取边界。"""

    def test_read_only_capture_and_account_ownership(self):
        """重复读取保持文件内容和修改时间，错账号明确拒绝。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'flows/api/cc-prepared'
            directory.mkdir(parents=True)
            attempt = str(uuid.uuid4())
            path = directory / (attempt + '.json')
            value = {'schema_version': 1, 'stage': 'cc_prepared', 'account_id': 7, 'attempt_id': attempt,
                'headers': [['x-custom', 'first'], ['x-custom', 'second']], 'body': '{}'}
            path.write_text(json.dumps(value))
            modified = path.stat().st_mtime_ns
            self.assertEqual(read_capture(root, 7, attempt), value)
            self.assertEqual(path.stat().st_mtime_ns, modified)
            with self.assertRaises(ValueError):
                read_capture(root, 8, attempt)
            with self.assertRaises(ValueError):
                read_capture(root, 7, '../credentials')
            with self.assertRaises(FileNotFoundError):
                read_capture(root, 7, str(uuid.uuid4()))
            path.unlink()
            path.symlink_to(root / 'secret')
            with self.assertRaises(OSError):
                read_capture(root, 7, attempt)
            path.unlink()
            with path.open('wb') as source:
                source.truncate(MAX_CAPTURE_BYTES + 1)
            with self.assertRaises(ValueError):
                read_capture(root, 7, attempt)
