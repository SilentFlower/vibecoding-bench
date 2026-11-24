"""验证 V2 的显式 RAM 预算、并发队列与进程名额生命周期。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from time import monotonic, sleep
import unittest

from tui_capacity import TuiCapacity, TuiCapacityError, TuiCapacitySnapshot


class TuiCapacityTests(unittest.TestCase):
    """在多个真实线程中覆盖名额占用和等待清理。"""

    def _capacity(self, *, concurrency=1, budget=1100, reserve=100, process=250, waiters=2):
        return TuiCapacity(
            concurrency,
            budget_bytes=budget,
            fixed_reserve_bytes=reserve,
            per_process_reserve_bytes=process,
            max_waiters=waiters,
        )

    def _wait_for_queue(self, capacity, size):
        deadline = monotonic() + 2
        while capacity.snapshot().waiting != size and monotonic() < deadline:
            sleep(0.001)
        self.assertEqual(capacity.snapshot().waiting, size)

    def _expect(self, code, fn, *args, **kwargs):
        with self.assertRaises(TuiCapacityError) as raised:
            fn(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)

    def test_limit_uses_both_concurrency_and_whole_memory_slots(self):
        """验证取小值、按字节向下取整和固定保留。@return 无。"""
        for concurrency, budget, limit in ((3, 1500, 3), (9, 1099, 3), (9, 1100, 4), (9, 350, 1)):
            with self.subTest(concurrency=concurrency, budget=budget):
                capacity = self._capacity(concurrency=concurrency, budget=budget)
                slots = [capacity.acquire(timeout=0) for _ in range(limit)]
                self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(limit, limit, 0))
                self._expect("capacity_busy", capacity.acquire, timeout=0)
                for slot in slots:
                    slot.release_after_close()
                self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(limit, 0, 0))

    def test_zero_capacity_rejects_without_queuing(self):
        """显式零并发、预算低于固定保留及不足一个名额均立即拒绝。@return 无。"""
        for values in ({"concurrency": 0}, {"budget": 1}, {"budget": 349}):
            with self.subTest(**values):
                capacity = self._capacity(**values)
                self._expect("capacity_unavailable", capacity.acquire, timeout=1)
                self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(0, 0, 0))

    def test_invalid_input_does_not_implicitly_choose_a_budget_or_deadline(self):
        """非法预算或时间输入不会隐式变为无限额。@return 无。"""
        for values in (
            {"concurrency": True}, {"budget": -1}, {"budget": float("inf")},
            {"reserve": -1}, {"process": 0}, {"process": 1.5}, {"waiters": -1},
        ):
            with self.subTest(**values), self.assertRaises(ValueError):
                self._capacity(**values)
        capacity = self._capacity()
        for timeout in (-1, float("nan"), float("inf"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                capacity.acquire(timeout=timeout)
        self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(1, 0, 0))

    def test_reuse_keeps_the_slot_until_process_close(self):
        """已启动进程续轮复用，旧名额和另一账号名额无法归还新占用。@return 无。"""
        capacity, other = self._capacity(), self._capacity()
        slot = capacity.acquire(timeout=0)
        foreign = other.acquire(timeout=0)
        self.assertIs(capacity.reuse(slot), slot)
        self.assertIs(capacity.reuse(slot), slot)
        self._expect("capacity_slot_inactive", capacity.reuse, foreign)
        self._expect("capacity_busy", capacity.acquire, timeout=0)
        slot.release_after_close()
        next_slot = capacity.acquire(timeout=0)
        slot.release_after_close()
        self._expect("capacity_slot_inactive", capacity.reuse, slot)
        self.assertIs(capacity.reuse(next_slot), next_slot)
        self.assertEqual(capacity.snapshot().in_use, 1)
        next_slot.release_after_close()
        foreign.release_after_close()

    def test_queue_is_bounded_and_fifo_while_continuations_reuse(self):
        """满队列立即拒绝，已有进程续轮和两名排队者按各自归属执行。@return 无。"""
        capacity = self._capacity()
        running = capacity.acquire(timeout=0)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(capacity.acquire, timeout=3)
            self._wait_for_queue(capacity, 1)
            second = pool.submit(capacity.acquire, timeout=3)
            self._wait_for_queue(capacity, 2)
            self._expect("capacity_busy", capacity.acquire, timeout=3)
            self.assertIs(capacity.reuse(running), running)
            self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(1, 1, 2))
            running.release_after_close()
            first_slot = first.result(timeout=2)
            self.assertFalse(second.done())
            first_slot.release_after_close()
            second.result(timeout=2).release_after_close()
        self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(1, 0, 0))

    def test_parallel_launches_wait_at_the_ram_limit(self):
        """计算出的 RAM 上限覆盖实际并发争抢。@return 无。"""
        capacity = self._capacity(concurrency=8, budget=850, waiters=5)
        starting = Barrier(9)
        close_processes = Event()

        def run_process():
            starting.wait(timeout=2)
            slot = capacity.acquire(timeout=3)
            try:
                self.assertTrue(close_processes.wait(timeout=2))
            finally:
                slot.release_after_close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            workers = [pool.submit(run_process) for _ in range(8)]
            try:
                starting.wait(timeout=2)
                self._wait_for_queue(capacity, 5)
                self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(3, 3, 5))
            finally:
                close_processes.set()
            for worker in workers:
                worker.result(timeout=2)
        self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(3, 0, 0))

    def test_zero_queue_rejects_full_account_immediately(self):
        """零队列配置只接纳能立即获得名额的进程。@return 无。"""
        capacity = self._capacity(waiters=0)
        slot = capacity.acquire(timeout=5)
        self._expect("capacity_busy", capacity.acquire, timeout=5)
        self.assertEqual(capacity.snapshot().waiting, 0)
        slot.release_after_close()

    def test_timeout_removes_waiter_and_keeps_next_request_eligible(self):
        """超时队首不会占据队列或吞掉后续可用名额。@return 无。"""
        capacity = self._capacity()
        running = capacity.acquire(timeout=0)
        with ThreadPoolExecutor(max_workers=2) as pool:
            expires = pool.submit(capacity.acquire, timeout=0.25)
            self._wait_for_queue(capacity, 1)
            following = pool.submit(capacity.acquire, timeout=3)
            self._wait_for_queue(capacity, 2)
            self._expect("capacity_timeout", expires.result, timeout=2)
            self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(1, 1, 1))
            running.release_after_close()
            following.result(timeout=2).release_after_close()
        self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(1, 0, 0))

    def test_cancellation_removes_waiter_without_closing_running_process(self):
        """取消预检及排队清理均不改变其他进程占用。@return 无。"""
        capacity = self._capacity(waiters=1)
        cancelled = Event()
        cancelled.set()
        self._expect("capacity_cancelled", capacity.acquire, timeout=0, cancel_event=cancelled)
        cancelled.clear()
        running = capacity.acquire(timeout=0)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(capacity.acquire, timeout=3, cancel_event=cancelled)
            self._wait_for_queue(capacity, 1)
            cancelled.set()
            self._expect("capacity_cancelled", pending.result, timeout=1)
            self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(1, 1, 0))
            next_waiter = pool.submit(capacity.acquire, timeout=3)
            self._wait_for_queue(capacity, 1)
            running.release_after_close()
            next_waiter.result(timeout=2).release_after_close()
        self.assertEqual(capacity.snapshot(), TuiCapacitySnapshot(1, 0, 0))
