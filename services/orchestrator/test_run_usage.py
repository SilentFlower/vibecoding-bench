"""普通Run共享统计的阶段、去重、缓存、回退与安全读取回归。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import run_usage as usage


class RunUsageTests(unittest.TestCase):
    """使用实际JSONL文件验证原聚合规则及读取边界。"""

    def test_sidecar_phase_flow_cache_errors_and_native_fallback_preserve_original_counts(self):
        """请求与响应去重，缓存计入输入，原生回退保持sidecar请求数。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'stats.jsonl'
            records = [{'phase': 'request', 'flow_id': 'a'}, {'phase': 'response', 'flow_id': 'a',
                'usage': {'input_tokens': 2, 'cache_creation_input_tokens': 3, 'cache_read_input_tokens': 5, 'output_tokens': 7}},
                {'phase': 'request', 'flow_id': 'b'}, {'error': 'synthetic'}, {'phase': 'ignored', 'usage': {'input_tokens': 999}}]
            path.write_text('\n'.join(json.dumps(item) for item in records))
            native = Mock(side_effect=AssertionError('已有sidecar用量时误读会话'))
            self.assertEqual({'tokens_in': 10, 'tokens_out': 7, 'requests': 2, 'errors': 1,
                'available': True, 'usage_available': True, 'source': 'sidecar'}, usage.run_usage([path], native))
            path.write_text(json.dumps({'phase': 'request', 'flow_id': 'a'}))
            native = Mock(return_value={'tokens_in': 11, 'tokens_out': 12, 'requests': 4, 'usage_available': True})
            value = usage.run_usage([path], native)
            self.assertEqual((11, 12, 1, 'claude_session'), (value['tokens_in'], value['tokens_out'], value['requests'], value['source']))
            self.assertEqual(4, usage.run_usage([], native)['requests'])

    def test_native_original_request_and_usage_dedup_skip_other_roles_and_invalid_lines(self):
        """保留requestId优先与原usage JSON回退，忽略无效行和非assistant。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = {'type': 'assistant', 'requestId': 'original', 'message': {'role': 'assistant',
                'usage': {'input_tokens': 2, 'cache_read_input_tokens': 3, 'output_tokens': 7}}}
            fallback = {key: value for key, value in record.items() if key != 'requestId'}
            (root / 'a.jsonl').write_text('\n'.join(json.dumps(item) for item in [record, record, fallback, fallback,
                {**record, 'type': 'user'}, {'message': {'role': 'user', 'usage': {'input_tokens': 999}}}, []]) + '\ninvalid\n')
            self.assertEqual({'tokens_in': 10, 'tokens_out': 14, 'requests': 2, 'usage_available': True}, usage.native_session_usage(root))

    def test_links_special_files_and_resource_limits_reject_reading(self):
        """链接和FIFO在打开边界拒绝，总字节与单行上限均显式报错。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'stats.jsonl'
            path.write_bytes(b'x' * 100)
            native = Mock()
            with patch.object(usage, 'MAX_USAGE_BYTES', 99), self.assertRaisesRegex(ValueError, '总字节'):
                usage.run_usage([path], native)
            with patch.object(usage, 'MAX_USAGE_LINE_BYTES', 99), self.assertRaisesRegex(ValueError, '单行'):
                usage.run_usage([path], native)
            (root / 'link').symlink_to(path)
            os.mkfifo(root / 'pipe')
            for name in ('link', 'pipe'):
                with self.subTest(name=name), self.assertRaises((ValueError, OSError)):
                    usage.run_usage([root / name], native)
            os.link(path, root / 'hardlink')
            with self.assertRaisesRegex(ValueError, '单链接'):
                usage.run_usage([path], native)
