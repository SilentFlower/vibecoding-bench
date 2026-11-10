"""组装快照只读访问与账号隔离回归。"""
import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from native_capture import CaptureExpired, MAX_CAPTURE_BYTES, RETENTION_MS, cleanup_captures, read_capture
from unittest.mock import patch


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
                'captured_at_ms': int(time.time() * 1000), 'headers': [['x-custom', 'first'], ['x-custom', 'second']], 'body': '{}'}
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

    def test_seven_day_boundary_and_safe_background_cleanup(self):
        """边界保留、过期读取明确、仅删除归属正确的普通快照。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'flows/api/cc-prepared'
            directory.mkdir(parents=True)
            now = int(time.time() * 1000)
            paths = []
            for captured, account in [(now - RETENTION_MS - 1, 7), (now - RETENTION_MS, 7),
                    (now - RETENTION_MS - 1, 8), (now + 600_000, 7)]:
                attempt = str(uuid.uuid4())
                path = directory / (attempt + '.json')
                path.write_text(json.dumps({'schema_version': 1, 'stage': 'cc_prepared', 'account_id': account,
                    'attempt_id': attempt, 'captured_at_ms': captured, 'body': '{}'}))
                paths.append(path)
            with self.assertRaises(CaptureExpired):
                read_capture(root, 7, paths[0].stem, now_ms=now)
            self.assertTrue(paths[0].exists(), '只读过期判断保持磁盘内容')
            self.assertEqual(read_capture(root, 7, paths[1].stem, now_ms=now)['captured_at_ms'], now - RETENTION_MS)
            link = directory / (str(uuid.uuid4()) + '.json')
            link.symlink_to(paths[0])
            broken = directory / (str(uuid.uuid4()) + '.json')
            broken.write_text('{')
            temporary_file = directory / '正在写入.tmp'
            temporary_file.write_text('保留')
            results = list(cleanup_captures(root, 7, now_ms=now))
            self.assertEqual(sum(item['deleted'] for item in results), 1)
            self.assertGreaterEqual(sum(item['failed'] for item in results), 4)
            self.assertFalse(paths[0].exists())
            self.assertTrue(all(path.exists() for path in paths[1:]))
            self.assertTrue(link.is_symlink())
            self.assertTrue(temporary_file.exists())
            directory.rename(directory.with_name('original'))
            directory.symlink_to(directory.with_name('original'), target_is_directory=True)
            with self.assertRaises(OSError):
                list(cleanup_captures(root, 7, now_ms=now))

    def test_replaced_file_and_stopping_keep_new_content(self):
        """读取后原子替换及停止期间保留文件。@return None。"""
        import native_capture
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'flows/api/cc-prepared'
            directory.mkdir(parents=True)
            attempt = str(uuid.uuid4())
            path = directory / (attempt + '.json')
            value = {'schema_version': 1, 'stage': 'cc_prepared', 'account_id': 7, 'attempt_id': attempt,
                'captured_at_ms': int(time.time() * 1000) - RETENTION_MS - 1000}
            path.write_text(json.dumps(value))
            reader = native_capture._read

            def replace(*args):
                """在旧快照读取后发布新文件。@return 原读取结果。"""
                result = reader(*args)
                pending = directory / 'new.tmp'
                pending.write_text(json.dumps({**value, 'captured_at_ms': int(time.time() * 1000)}))
                pending.replace(path)
                return result

            with patch('native_capture._read', side_effect=replace):
                self.assertEqual(sum(item['deleted'] for item in cleanup_captures(root, 7)), 0)
            self.assertTrue(path.exists())
            path.write_text(json.dumps(value))
            self.assertEqual(sum(item['deleted'] for item in cleanup_captures(root, 7, stopping=lambda: True)), 0)
