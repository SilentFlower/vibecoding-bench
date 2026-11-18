"""节点公开抓包投影的原脱敏、续聊兼容和读取上限回归。"""
import json
import tempfile
import unittest
from pathlib import Path

from run_capture import run_capture


class RunCaptureTests(unittest.TestCase):
    """原始正文仅验证文件元信息，公开元数据沿原脱敏读取器。"""

    def test_public_snapshot_preserves_original_summary_without_reading_raw_body(self):
        """原始大正文只列元信息，索引敏感header仍被脱敏。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / 'group-original'
            attempt = base / 'executions' / ('a' * 20)
            attempt.mkdir(parents=True)
            index = {'entries': [{'flow_id': 'original', 'capture_state': 'complete',
                'request': {'headers': {'authorization': 'synthetic-secret', 'content-type': 'application/json'}}}]}
            (attempt / 'capture_index.json').write_text(json.dumps(index))
            with (attempt / 'http_capture.jsonl').open('wb') as output:
                output.truncate(100 * 1024 * 1024)
            result = run_capture(base, running=False)
            self.assertEqual(('complete', 1), (result['status'], result['sample_count']))
            self.assertNotIn('synthetic-secret', json.dumps(result))
            self.assertEqual(100 * 1024 * 1024, next(item['size'] for item in result['files'] if item['path'].endswith('http_capture.jsonl')))
            preview = run_capture(base, running=False, relative=f'executions/{"a" * 20}/capture_index.json')
            self.assertEqual('[redacted]', preview['entries'][0]['request']['headers']['authorization'])
            with self.assertRaises(ValueError):
                run_capture(base, running=False, relative=f'executions/{"a" * 20}/http_capture.jsonl')

    def test_continuation_link_only_accepts_same_environment_group_and_metadata_limit_is_explicit(self):
        """续聊入口核对同环境，过大索引在复制前拒绝。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, continuation = root / 'group-original', root / 'group-continued'
            base.mkdir(); continuation.mkdir()
            (continuation / 'capture_index.json').write_text(json.dumps({'entries': [{'flow_id': 'continued'}]}))
            link = base / 'continue-original'
            link.symlink_to(continuation, target_is_directory=True)
            self.assertEqual(1, run_capture(base, running=False)['sample_count'])
            link.unlink(); link.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, '归属'):
                run_capture(base, running=False)
            link.unlink()
            with (base / 'capture_index.json').open('wb') as output:
                output.truncate(8 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(ValueError, '上限'):
                run_capture(base, running=False)
