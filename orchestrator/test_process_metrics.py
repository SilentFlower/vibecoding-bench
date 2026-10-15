"""验证真实进程的识别、cgroup 语义及未知指标边界。"""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from process_metrics import PROCESS_SOURCE, cli_processes, memory_limit, process_executable, sample_process_metrics, validate_process_metrics


class ProcessMetricsTests(unittest.TestCase):
    """通过最小 procfs/cgroup 夹具覆盖采样来源和持久化边界。"""

    def setUp(self) -> None:
        """创建当前用例专用目录。

        :return: None。
        """
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root, self.proc, self.cli, self.cgroup = [self.base / name for name in ('runtime', 'proc', 'cli', 'cgroup')]
        for path in (self.root, self.proc, self.cli, self.cgroup):
            path.mkdir()
        self.environment = 'a' * 32
        (self.root / 'sender.json').write_text(json.dumps({'binding': {'environment_id': self.environment}}))
        (self.cgroup / 'memory.max').write_text('1610612736')

    def _process(self, pid: int, version: str = '2.1.293', rss: int = 64000, uid: int = 1000) -> Path:
        """准备可核对的官方 CLI 路径和进程记录。

        :param pid: 合成 PID。
        :param version: 版本缓存名。
        :param rss: KiB RSS。
        :param uid: 进程用户。
        :return: 官方 CLI 文件路径。
        """
        executable = self.cli / version / 'node_modules/@anthropic-ai/claude-code/bin/claude.exe'
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b'synthetic native executable path')
        executable.chmod(0o755)
        (self.cli / version / '.ready').touch()
        process = self.proc / str(pid)
        process.mkdir()
        (process / 'exe').symlink_to(executable)
        (process / 'stat').write_text(str(pid) + ' (cli (native)) ' + ' '.join(['S'] + ['0'] * 18 + ['77'] + ['0'] * 4))
        (process / 'status').write_text(f'Uid:\t{uid}\t{uid}\t{uid}\t{uid}\nVmRSS:\t{rss} kB\n')
        return executable

    @unittest.skipUnless(os.geteuid() == 0, '真实 UID 隔离检查需要 root')
    def test_real_proc_executable_of_account_user_is_readable_without_ptrace_capability(self) -> None:
        """读取跨 UID 的内核路径后，仍能访问 root 私有文件。

        :return: None。
        """
        child = subprocess.Popen(['/usr/bin/sleep', '5'], user=1000, group=1000)
        try:
            time.sleep(0.05)
            self.assertEqual(Path('/usr/bin/sleep').resolve(), process_executable(Path('/proc') / str(child.pid)))
            private = self.root / 'root-only'
            private.write_text('restored')
            private.chmod(0o600)
            self.assertEqual('restored', private.read_text())
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_memory_limit_distinguishes_unlimited_missing_and_broken(self) -> None:
        """缺文件不能被当成无限制，v1/v2 的无限制值具有明确语义。

        :return: None。
        """
        self.assertEqual(1610612736, memory_limit(self.cgroup))
        (self.cgroup / 'memory.max').write_text('max')
        self.assertEqual(0, memory_limit(self.cgroup))
        (self.cgroup / 'memory.max').write_text('broken')
        with self.assertRaises(ValueError):
            memory_limit(self.cgroup)
        (self.cgroup / 'memory.max').unlink()
        with self.assertRaises(ValueError):
            memory_limit(self.cgroup)
        v1 = self.cgroup / 'memory/memory.limit_in_bytes'
        v1.parent.mkdir()
        v1.write_text(str(1 << 62))
        self.assertEqual(0, memory_limit(self.cgroup))
        v1.write_text('1073741824')
        self.assertEqual(1073741824, memory_limit(self.cgroup))

    @unittest.skipUnless(os.geteuid() == 0, '官方缓存由 root 所有，进程路径夹具需要 root')
    def test_only_trusted_official_cli_user_processes_are_sampled(self) -> None:
        """不把 root、Node 或用户可改写文件的占用当成官方 CLI。

        :return: None。
        """
        self._process(101)
        self._process(102, '2.1.280', uid=0)
        untrusted = self._process(103, '2.1.260')
        untrusted.chmod(0o777)
        self.assertEqual([('2.1.293', 64000 * 1024)], cli_processes(self.proc, self.cli))

    @unittest.skipUnless(os.geteuid() == 0, '官方缓存由 root 所有，进程路径夹具需要 root')
    def test_observations_survive_idle_and_reject_corruption(self) -> None:
        """真实样本保留来源和范围，进程退出后不回填假样本，坏文件保持原样。

        :return: None。
        """
        self._process(101)
        first = sample_process_metrics(self.root, self.proc, self.cli, self.cgroup)
        sample = first['versions']['2.1.293']
        self.assertEqual(1, sample['sample_count'])
        self.assertEqual(64000 * 1024, sample['rss_bytes'])
        (self.proc / '101/status').write_text('Uid:\t1000\t1000\t1000\t1000\nVmRSS:\t72000 kB\n')
        second = sample_process_metrics(self.root, self.proc, self.cli, self.cgroup)
        sample = second['versions']['2.1.293']
        self.assertEqual((2, 64000 * 1024, 72000 * 1024),
            (sample['sample_count'], sample['rss_min_bytes'], sample['rss_max_bytes']))
        (self.proc / '101/exe').unlink()
        idle = sample_process_metrics(self.root, self.proc, self.cli, self.cgroup)
        self.assertEqual(sample, idle['versions']['2.1.293'])
        path = self.root / 'process-metrics.json'
        path.write_text('{')
        with self.assertRaises(ValueError):
            sample_process_metrics(self.root, self.proc, self.cli, self.cgroup)
        self.assertEqual('{', path.read_text())

    def test_unknown_rss_is_explicit_and_cross_environment_is_rejected(self) -> None:
        """缺样本保持空值，跨环境、伪造时间和真假类型均拒绝。

        :return: None。
        """
        value = {'constrained_memory': 1610612736, 'observation': {
            'source': PROCESS_SOURCE, 'environment_id': self.environment, 'cli_version': '2.1.293',
            'observed_at': time.time(), 'sampled_at': None, 'sample_count': 0,
            'rss_bytes': None, 'rss_min_bytes': None, 'rss_max_bytes': None}}
        validate_process_metrics(value, self.environment, '2.1.293')
        for field, bad in (('source', 'unknown'), ('environment_id', 'b' * 32),
                ('observed_at', time.time() + 3600), ('sample_count', True), ('rss_bytes', 123)):
            broken = json.loads(json.dumps(value))
            broken['observation'][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_process_metrics(broken, self.environment, '2.1.293')


if __name__ == '__main__':
    unittest.main()
