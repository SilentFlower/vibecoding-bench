"""验证主机性能采样的计数口径、指标缺失与异常退出收口。"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from threading import Event
from unittest.mock import patch

import verification_resources as resources


class VerificationResourceTests(unittest.TestCase):
    """资源统计独立于原兼容证据，保持主机范围并明确观测有效性。"""

    def test_linux_snapshot_excludes_guest_cpu_and_reads_host_memory(self) -> None:
        """guest已包含在user/nice中，CPU计数只累计前八项。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'stat').write_text('cpu 10 2 3 40 5 6 7 8 9 10\ncpu0 0\ncpu1 0\n')
            (root / 'meminfo').write_text('MemTotal: 1000 kB\nMemAvailable: 600 kB\n')
            (root / 'vmstat').write_text('oom_kill 3\n')
            value = resources._snapshot(root)
        self.assertEqual(value, {'cpu_total': 81, 'cpu_idle': 45, 'cpu_count': 2,
            'memory_total': 1024000, 'memory_available': 614400, 'oom_kill': 3})

    def test_metrics_keep_peak_not_last_value_and_report_oom_delta(self) -> None:
        """中间资源峰值应保留，恢复后的末次采样不能覆盖峰值。:return: None。"""
        snapshots = [dict(cpu_total=100, cpu_idle=50, cpu_count=4, memory_total=1000, memory_available=800, oom_kill=3),
            dict(cpu_total=200, cpu_idle=70, cpu_count=4, memory_total=1000, memory_available=300, oom_kill=4),
            dict(cpu_total=300, cpu_idle=150, cpu_count=4, memory_total=1000, memory_available=700, oom_kill=4)]
        stream = io.StringIO()
        with patch.object(resources, '_snapshot', side_effect=snapshots), redirect_stderr(stream):
            with resources.VerificationResources(4, interval=60) as monitor:
                monitor._sample()
        value = json.loads(stream.getvalue())
        self.assertEqual(value['scope'], 'host')
        self.assertEqual(value['workers'], 4)
        self.assertEqual(value['samples'], 3)
        self.assertEqual(value['cpu_peak_percent'], 80)
        self.assertEqual(value['memory_used_start_bytes'], 200)
        self.assertEqual(value['memory_used_peak_bytes'], 700)
        self.assertEqual(value['memory_used_peak_delta_bytes'], 500)
        self.assertEqual(value['memory_available_min_bytes'], 300)
        self.assertEqual(value['oom_kill_delta'], 1)
        self.assertFalse(monitor.thread.is_alive())

    def test_malformed_cpu_and_memory_are_rejected(self) -> None:
        """缺失CPU汇总或越界内存计数必须标记无效，不能作为零负载结果。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'vmstat').write_text('oom_kill 0\n')
            for cpu, memory in [('', 'MemTotal: 100 kB\nMemAvailable: 50 kB\n'),
                    ('cpu0 1 2 3 4 5 6 7 8\n', 'MemTotal: 100 kB\nMemAvailable: 50 kB\n'),
                    ('cpu 1 2 3 4 5 6 7 8\n', 'MemTotal: 100 kB\nMemAvailable: 101 kB\n')]:
                with self.subTest(cpu=cpu, memory=memory):
                    (root / 'stat').write_text(cpu)
                    (root / 'meminfo').write_text(memory)
                    with self.assertRaises(ValueError):
                        resources._snapshot(root)

    def test_missing_metrics_are_unknown_and_do_not_hide_original_failure(self) -> None:
        """资源读取失败时标记不可用，原演练异常类型与对象保持原值。:return: None。"""
        error = RuntimeError('合成演练失败')
        stream = io.StringIO()
        with patch.object(resources, '_snapshot', side_effect=OSError('private-path-secret')), redirect_stderr(stream):
            with self.assertRaises(RuntimeError) as caught:
                with resources.VerificationResources(4) as monitor:
                    raise error
        self.assertIs(caught.exception, error)
        self.assertIsNone(monitor.thread)
        value = json.loads(stream.getvalue())
        self.assertFalse(value['available'])
        self.assertEqual(value['samples'], 0)
        self.assertIsNone(value['cpu_peak_percent'])
        self.assertIsNone(value['memory_used_peak_bytes'])
        self.assertNotIn('private-path-secret', stream.getvalue())

    def test_background_sampling_thread_is_joined_on_exception(self) -> None:
        """实际采样线程进入第二次读取后，主流程异常仍使线程退出并保持原错误。:return: None。"""
        sampled = Event()
        count = 0
        error = ValueError('合成迁移失败')

        def snapshot(root):
            """使用可观测事件替代固定等待，确认实际线程已经执行采样。"""
            nonlocal count
            count += 1
            if count > 1:
                sampled.set()
            return dict(cpu_total=count * 100, cpu_idle=count * 50, cpu_count=4,
                memory_total=1000, memory_available=800, oom_kill=None)

        with patch.object(resources, '_snapshot', side_effect=snapshot), redirect_stderr(io.StringIO()):
            with self.assertRaises(ValueError) as caught:
                with resources.VerificationResources(4, interval=0.01) as monitor:
                    self.assertTrue(sampled.wait(5))
                    raise error
        self.assertIs(caught.exception, error)
        self.assertGreaterEqual(count, 2)
        self.assertFalse(monitor.thread.is_alive())
        self.assertIsNone(monitor.result['oom_kill_delta'])

    def test_invalid_cpu_counters_mark_partial_metrics_unavailable(self) -> None:
        """累计计数回退时拒绝输出有效CPU利用率，已采样数量仍可追溯。:return: None。"""
        before = dict(cpu_total=100, cpu_idle=50, cpu_count=4, memory_total=1000, memory_available=800, oom_kill=0)
        after = {**before, 'cpu_total': 90}
        with patch.object(resources, '_snapshot', side_effect=[before, after]), redirect_stderr(io.StringIO()):
            with resources.VerificationResources(2, interval=60) as monitor:
                pass
        self.assertFalse(monitor.result['available'])
        self.assertEqual(monitor.result['samples'], 1)
        self.assertIsNone(monitor.result['cpu_peak_percent'])


if __name__ == '__main__':
    unittest.main()
