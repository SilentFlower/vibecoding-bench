"""检查真实兼容演练入口的受信来源与镜像身份边界。"""
import unittest
from concurrent.futures import CancelledError
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Lock
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
        for arguments in ([str(verifier.REPO / 'deploy/flower2api/verify_database_compatibility.py'), '--help'],
                ['-m', 'unittest', 'discover', '-s', 'deploy/flower2api', '-p', 'test_system_database.py']):
            result = subprocess.run([sys.executable, *arguments], cwd=verifier.REPO, env=environment,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)


class CompatibilityConcurrencyTests(unittest.TestCase):
    """通过真实线程调度核验并发、结果顺序和失败收口。"""

    def run_verification(self, root: Path, worker, *, workers: int | None = None) -> dict:
        """隔离外部来源和Docker操作，运行真实协调逻辑。

        :param root: 合成工作目录。
        :param worker: 模拟单来源演练，实际执行于工作线程。
        :param workers: 待验证并发数。
        :return: 完整协调结果。
        """
        manifest = root / 'build.json'
        manifest.write_text(json.dumps({'parent_revision': 'synthetic', 'images': {
            role: {'reference': role, 'config_digest': role} for role in ('control', 'account')}}))
        sources = [({'release': str(index)}, b'synthetic') for index in range(8)]
        with ExitStack() as stack:
            for name, value in (('image_identity', 'candidate'), ('migration_registries', {}),
                    ('data_contracts', {}), ('_sources', sources)):
                stack.enter_context(patch.object(verifier, name, return_value=value))
            stack.enter_context(patch.object(verifier, '_verify_source', side_effect=worker))
            options = {} if workers is None else {'workers': workers}
            return verifier.verify(manifest, 'synthetic', root / 'proof.json', history_root=root, **options)

    def test_parallel_completion_preserves_source_order_and_bound(self) -> None:
        """两路同时执行且首项后完成时，最终证据仍按来源顺序排列。@return None。"""
        second = Event()
        lock = Lock()
        active = 0
        maximum = 0

        def worker(release, *arguments):
            """用事件强制首两项重叠并交换完成顺序。"""
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                if release['release'] == '0':
                    self.assertTrue(second.wait(5))
                if release['release'] == '1':
                    second.set()
                return release, 0.01
            finally:
                with lock:
                    active -= 1

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = self.run_verification(root, worker, workers=2)
            self.assertEqual(result['sources'], [{'release': str(index)} for index in range(8)])
            self.assertEqual(json.loads((root / 'proof.json').read_text()), result)
        self.assertEqual(maximum, 2)
        self.assertEqual(active, 0)

    def test_default_remains_serial(self) -> None:
        """默认协调行为依次完成全部八个来源。@return None。"""
        sequence = []

        def worker(release, *arguments):
            """记录串行顺序并返回合成证据。"""
            sequence.append(release['release'])
            return release, 0.01

        with tempfile.TemporaryDirectory() as folder:
            self.run_verification(Path(folder), worker)
        self.assertEqual(sequence, list(map(str, range(8))))

    def test_failure_waits_cleanup_cancels_pending_and_preserves_error(self) -> None:
        """来源失败后排队项停止，运行项收口完成后传播原异常。@return None。"""
        second = Event()
        cleaned = Event()
        started = []
        error = RuntimeError('合成来源失败')

        def worker(release, raw, candidate, registries, contracts, history, stopped):
            """模拟单来源失败通知及另一路 finally 收口。"""
            if stopped.is_set():
                raise CancelledError()
            started.append(release['release'])
            if release['release'] == '0':
                self.assertTrue(second.wait(5))
                stopped.set()
                raise error
            try:
                second.set()
                self.assertTrue(stopped.wait(5))
                return release, 0.01
            finally:
                cleaned.set()

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(RuntimeError) as caught:
                self.run_verification(root, worker, workers=2)
            self.assertIs(caught.exception, error)
            self.assertFalse((root / 'proof.json').exists())
        self.assertTrue(cleaned.is_set())
        self.assertEqual(set(started), {'0', '1'})

    def test_worker_stop_and_failure_keep_original_error_context(self) -> None:
        """停止任务在Docker前退出，实际来源失败附加身份并保留异常类型。@return None。"""
        stopped = Event()
        stopped.set()
        release = {'release': 'synthetic', 'control': {'reference': 'original',
            'config_digest': 'synthetic', 'registry_digest': 'synthetic'}}
        with patch.object(verifier, 'image_identity') as identity, patch.object(verifier, 'command') as command:
            with self.assertRaises(CancelledError):
                verifier._verify_source(release, b'', 'candidate', {}, {}, Path('/synthetic'), stopped)
            identity.assert_not_called()
            command.assert_not_called()
        error = ValueError('合成镜像身份失败')
        stopped.clear()
        with patch.object(verifier, 'image_identity', side_effect=error):
            with self.assertRaises(ValueError) as caught:
                verifier._verify_source(release, b'', 'candidate', {}, {}, Path('/synthetic'), stopped)
        self.assertIs(caught.exception, error)
        self.assertEqual(error.__notes__, ['兼容演练来源：synthetic'])
        self.assertTrue(stopped.is_set())

    def test_invalid_workers_stop_before_external_work(self) -> None:
        """非法并发输入在读取文件和Docker之前拒绝。@return None。"""
        for workers in (True, False, 0, 3, '2'):
            with self.subTest(workers=workers), patch.object(verifier, 'image_identity') as identity:
                with self.assertRaises(ValueError):
                    verifier.verify(Path('/synthetic/missing'), '', Path('/synthetic/proof'), workers=workers)
                identity.assert_not_called()


if __name__ == '__main__':
    unittest.main()
