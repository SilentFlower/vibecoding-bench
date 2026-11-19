"""验证发布提速时的缓存隔离、校验覆盖及并行失败收口。"""
import sys
import tempfile
import unittest
from pathlib import Path

from build_cache_key import backend_recipe_digest
from verify_release_tests import run_checks, suite_commands


class ReleaseSpeedTests(unittest.TestCase):
    """用真实子进程及独立 Dockerfile 验证优化后的边界。"""

    def test_control_changes_keep_rust_recipe_but_backend_and_global_args_invalidate_it(self) -> None:
        """控制依赖变化复用 Rust 缓存，编译器或全局参数变化继续失效。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Dockerfile'
            recipe = 'ARG RUST_TAG=1.96\nFROM node AS frontend\nRUN npm ci\nFROM rust:${RUST_TAG} AS backend\nRUN cargo build --locked\nFROM python AS control\nRUN apt-get install ssh\n'
            path.write_text(recipe)
            before = backend_recipe_digest(path)
            path.write_text(recipe.replace('install ssh', 'install ssh sshpass'))
            self.assertEqual(before, backend_recipe_digest(path))
            for old, new in (('cargo build --locked', 'cargo build --release'), ('RUST_TAG=1.96', 'RUST_TAG=1.97')):
                path.write_text(recipe.replace(old, new))
                self.assertNotEqual(before, backend_recipe_digest(path))
            for invalid in ('FROM python AS control\n', recipe + 'FROM rust AS backend\n'):
                path.write_text(invalid)
                with self.assertRaises(ValueError):
                    backend_recipe_digest(path)

    def test_parallel_checks_reach_shared_barrier(self) -> None:
        """三个真实进程需同时进入屏障，串行执行会超时失败。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            script = ('import sys,time; from pathlib import Path; root=Path(sys.argv[1]); '
                '(root/sys.argv[2]).touch(); end=time.monotonic()+5\n'
                'while len(list(root.iterdir()))<3 and time.monotonic()<end: time.sleep(0.01)\n'
                'raise SystemExit(0 if len(list(root.iterdir()))==3 else 1)')
            commands = {str(index): [sys.executable, '-c', script, temporary, str(index)] for index in range(3)}
            self.assertTrue(run_checks(commands))

    def test_failure_waits_for_other_checks_and_spawn_failure_is_nonzero(self) -> None:
        """一组失败或启动失败均拒绝继续，其他组仍完成并被回收。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'completed'
            slow = [sys.executable, '-c', 'import sys,time; from pathlib import Path; time.sleep(0.1); Path(sys.argv[1]).touch()', str(path)]
            for failure in ([sys.executable, '-c', 'raise SystemExit(7)'], ['/synthetic/missing-python']):
                self.assertFalse(run_checks({'failed': failure, 'other': slow}))
                self.assertTrue(path.exists())
                path.unlink()

    def test_original_suites_remain_complete_and_host_uses_root(self) -> None:
        """宿主权限、两路发现模式与额外校验模块全部保留。:return: None。"""
        commands = suite_commands('/synthetic/python')
        self.assertEqual(['sudo', '/synthetic/python'], commands['host'][:2])
        self.assertIn('test_system*.py', commands['host'])
        self.assertIn('test_system_update*.py', commands['orchestrator'])
        self.assertEqual(commands['publication'][3:], ['test_publication', 'test_database_definitions',
            'test_database_migrations', 'test_database_compatibility', 'test_source_layout',
            'test_legacy_packages', 'test_scratchpad_update_compatibility', 'test_agy_supervisor',
            'test_agy_artifact', 'test_agy_images'])


if __name__ == '__main__':
    unittest.main()
