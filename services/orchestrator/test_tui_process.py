"""通过真实的本地子进程验证账号执行器的归属、通信、取消和名额回收。"""

from concurrent.futures import ThreadPoolExecutor
from os import close, openpty, read, write
from select import select
from signal import SIGKILL
from socket import socketpair
from subprocess import DEVNULL, Popen
from sys import executable
from threading import Event, current_thread
from time import monotonic, sleep
from tty import setraw
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

from tui_capacity import TuiCapacity, TuiCapacityError
from tui_process import TuiProcessError, TuiProcessExecutor


class TuiProcessTests(TestCase):
    """每项测试使用独立容量、显式环境和可回收的真实子进程。"""

    def setUp(self) -> None:
        """创建本测试的单进程预算及后备清理。@return 无。"""
        self.capacity = TuiCapacity(1, budget_bytes=10, fixed_reserve_bytes=0, per_process_reserve_bytes=10,
                                    max_waiters=2)
        self.children = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)

    def _child(self, script='import time; time.sleep(30)', **io):
        streams = {'stdin': DEVNULL, 'stdout': DEVNULL, 'stderr': DEVNULL, **io}
        child = Popen([executable, '-I', '-c', script], env={}, **streams)
        self.children.append(child)
        return child

    def _until(self, predicate):
        deadline = monotonic() + 3
        while not predicate():
            if monotonic() >= deadline:
                self.fail('等待进程状态超时')
            sleep(0.002)

    def _error(self, code, function, *args, **kwargs):
        with self.assertRaises((TuiCapacityError, TuiProcessError)) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_private_terminal_continuation_and_generation(self):
        """从真实终端续轮，拒绝另一会话和账号的句柄，重开后旧句柄仍只对应原进程。@return 无。"""
        master, slave = openpty()
        self.addCleanup(close, master)
        self.addCleanup(close, slave)
        setraw(slave)

        def spawn(session_id):
            self.assertEqual(session_id, 'session')
            script = 'import os\nassert os.isatty(0)\nwhile data := os.read(0, 256):\n os.write(1, data.upper())'
            return self._child(script, stdin=slave, stdout=slave, stderr=slave)

        executor = TuiProcessExecutor(self.capacity, spawn)
        foreign = TuiProcessExecutor(self.capacity, spawn)
        handle = executor.start('session', timeout=0)
        self.addCleanup(executor.close, handle)
        self.assertEqual(UUID(handle.generation).version, 4)
        with self.assertRaises(AttributeError):
            handle.generation = 'replacement'
        for request in (b'one', b'two'):
            self.assertIs(executor.resume('session', handle), self.children[0])
            self.assertEqual(write(master, request), len(request))
            self.assertTrue(select([master], [], [], 3)[0])
            self.assertEqual(read(master, 256), request.upper())
        self._error('tui_process_inactive', executor.resume, 'other', handle)
        self._error('tui_process_inactive', foreign.resume, 'session', handle)
        self._error('tui_process_inactive', foreign.close, handle)
        self._error('tui_session_in_use', executor.start, 'session', timeout=0)
        self._error('capacity_busy', executor.start, 'other', timeout=0)
        original_code = executor.close(handle)
        replacement = executor.start('session', timeout=0)
        self.addCleanup(executor.close, replacement)
        self.assertNotEqual(handle.generation, replacement.generation)
        self._error('tui_process_inactive', executor.resume, 'session', handle)
        self.assertEqual(executor.close(handle), original_code)
        self.assertIs(executor.resume('session', replacement), self.children[1])
        self.assertEqual(len(self.children), 2)

    def test_launch_failure_and_monitor_failure_return_slot(self):
        """真实 exec 失败或启动线程创建失败都应回收会话和预留名额。@return 无。"""
        with self.assertRaises(FileNotFoundError):
            TuiProcessExecutor(self.capacity, lambda _: Popen(['/不存在的测试程序'], env={})).start('a', timeout=0)
        self.assertEqual(self.capacity.snapshot().in_use, 0)
        executor = TuiProcessExecutor(self.capacity, lambda _: self._child())
        with patch('tui_process.Thread') as monitor:
            monitor.return_value.start.side_effect = RuntimeError('监护线程创建失败')
            with self.assertRaisesRegex(RuntimeError, '监护线程创建失败'):
                executor.start('a', timeout=0)
        self.assertEqual(self.children, [])
        self.assertEqual(self.capacity.snapshot().in_use, 0)
        executor.close(executor.start('a', timeout=0))

    def test_launcher_outlives_first_request_during_tool_handoff(self):
        """首轮请求线程退出后，原启动线程和子进程继续接收工具结果。@return 无。"""
        owners = []
        source, control = socketpair()
        with source, control:
            control.settimeout(3)

            def spawn(_):
                owners.append(current_thread())
                return self._child('import os; os.write(1, os.read(0, 4).upper()); os.read(0, 1)',
                                   stdin=source, stdout=source)

            executor = TuiProcessExecutor(self.capacity, spawn)
            with ThreadPoolExecutor(1) as first_request:
                handle = first_request.submit(executor.start, 'native', timeout=0).result(timeout=3)
            self.assertTrue(owners[0].is_alive())
            self.assertIs(executor.resume('native', handle), self.children[0])
            control.sendall(b'read')
            self.assertEqual(control.recv(4), b'READ')
            control.sendall(b'x')
            owners[0].join(timeout=3)
            self.assertFalse(owners[0].is_alive())
            self.assertEqual(executor.close(handle), 0)
            self.assertEqual(self.capacity.snapshot().in_use, 0)

    def test_cancellation_during_spawn_reaps_before_delivery(self):
        """工厂持有活进程时取消，重复启动拒绝，名额在旧进程收回后才可重用。@return 无。"""
        created, finish_spawn, cancel = Event(), Event(), Event()

        def spawn(_):
            child = self._child()
            created.set()
            self.assertTrue(finish_spawn.wait(3))
            return child

        executor = TuiProcessExecutor(self.capacity, spawn)
        with ThreadPoolExecutor(1) as pool:
            pending = pool.submit(executor.start, 'a', timeout=0, cancel_event=cancel)
            try:
                self.assertTrue(created.wait(3))
                self._error('tui_session_in_use', executor.start, 'a', timeout=0)
                cancel.set()
                self.assertEqual(self.capacity.snapshot().in_use, 1)
                self.assertEqual(len(self.children), 1)
            finally:
                finish_spawn.set()
            self._error('capacity_cancelled', pending.result, timeout=3)
        self.assertIsNotNone(self.children[0].returncode)
        self.assertEqual(self.capacity.snapshot().in_use, 0)
        executor.close(executor.start('a', timeout=0))

    def test_natural_exit_without_consumer_reaps_and_wakes_next(self):
        """没有调用方等待或关闭时，监护线程回收正常和异常退出并唤醒队首。@return 无。"""
        for code in (0, 23):
            with self.subTest(code=code):
                source, control = socketpair()
                with source, control:
                    def spawn(session_id):
                        if session_id == 'first':
                            return self._child(f'import os; os.read(0, 1); raise SystemExit({code})', stdin=source)
                        self.assertEqual(self.children[-1].returncode, code)
                        return self._child()

                    executor = TuiProcessExecutor(self.capacity, spawn)
                    first = executor.start('first', timeout=0)
                    with ThreadPoolExecutor(1) as pool:
                        second = pool.submit(executor.start, 'next', timeout=3)
                        self._until(lambda: self.capacity.snapshot().waiting == 1)
                        self._error('tui_session_in_use', executor.start, 'next', timeout=0)
                        control.sendall(b'x')
                        next_handle = second.result(timeout=3)
                    self._error('tui_process_inactive', executor.resume, 'first', first)
                    self.assertEqual(executor.close(first), code)
                    executor.close(next_handle)
                    self.assertEqual(self.capacity.snapshot().in_use, 0)

    def test_cancel_running_process_and_concurrent_close_preserve_fifo(self):
        """运行中取消、并发关闭、忽略 TERM 的进程和两个排队会话共享同一回收顺序。@return 无。"""
        cancel = Event()
        source, control = socketpair()
        with source, control, ThreadPoolExecutor(4) as pool:
            control.settimeout(3)
            launches = []

            def spawn(session_id):
                launches.append(session_id)
                if session_id == 'first':
                    script = ('import os, signal, time\n'
                              'signal.signal(signal.SIGTERM, lambda *_: os.write(1, b"T"))\n'
                              'os.write(1, b"R")\ntime.sleep(30)')
                    return self._child(script, stdout=source)
                self.assertIsNotNone(self.children[-1].returncode)
                return self._child()

            executor = TuiProcessExecutor(self.capacity, spawn, terminate_grace=0.4)
            first = executor.start('first', timeout=0, cancel_event=cancel)
            self.assertEqual(control.recv(1), b'R')
            second = pool.submit(executor.start, 'second', timeout=3)
            self._until(lambda: self.capacity.snapshot().waiting == 1)
            third = pool.submit(executor.start, 'third', timeout=3)
            self._until(lambda: self.capacity.snapshot().waiting == 2)
            self.assertIs(executor.resume('first', first), self.children[0])
            cancel.set()
            self.assertEqual(control.recv(1), b'T')
            self._error('tui_process_inactive', executor.resume, 'first', first)
            readers = [pool.submit(executor.close, first) for _ in range(2)]
            self.assertEqual(launches, ['first'])
            self.assertEqual(self.capacity.snapshot().in_use, 1)
            for result in readers:
                self.assertEqual(result.result(timeout=3), -SIGKILL)
            executor.close(second.result(timeout=3))
            executor.close(third.result(timeout=3))
            self.assertEqual(launches, ['first', 'second', 'third'])
            self.assertEqual(self.capacity.snapshot().in_use, 0)

    def test_cancelled_waiter_clears_its_session_reservation(self):
        """等候期间取消释放会话名；同一会话随后可重新排队取得进程。@return 无。"""
        executor = TuiProcessExecutor(self.capacity, lambda _: self._child())
        first = executor.start('first', timeout=0)
        with ThreadPoolExecutor(1) as pool:
            cancel = Event()
            pending = pool.submit(executor.start, 'waiting', timeout=3, cancel_event=cancel)
            self._until(lambda: self.capacity.snapshot().waiting == 1)
            cancel.set()
            self._error('capacity_cancelled', pending.result, timeout=3)
            self.assertEqual(len(self.children), 1)
            again = pool.submit(executor.start, 'waiting', timeout=3)
            self._until(lambda: self.capacity.snapshot().waiting == 1)
            executor.close(first)
            executor.close(again.result(timeout=3))

    def test_failed_cancel_signal_keeps_reaper_until_exit(self):
        """取消信号发送失败后持续持有名额，真实进程最终退出时自动释放。@return 无。"""
        cancel, attempted = Event(), Event()
        source, control = socketpair()
        with source, control:
            executor = TuiProcessExecutor(self.capacity, lambda _: self._child('import os; os.read(0, 1)', stdin=source))
            handle = executor.start('a', timeout=0, cancel_event=cancel)
            child = executor.resume('a', handle)

            def fail_signal():
                attempted.set()
                raise PermissionError('信号被拒绝')

            with patch.object(child, 'terminate', side_effect=fail_signal):
                cancel.set()
                self.assertTrue(attempted.wait(3))
                self._error('tui_process_inactive', executor.resume, 'a', handle)
                self.assertEqual(self.capacity.snapshot().in_use, 1)
                with self.assertRaises(PermissionError):
                    executor.close(handle)
                control.sendall(b'x')
                self._until(lambda: self.capacity.snapshot().in_use == 0)
            self.assertEqual(executor.close(handle), 0)
