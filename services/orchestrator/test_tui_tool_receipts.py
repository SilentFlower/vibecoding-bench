"""核对账号私有工具回执的所有权、并发认领和断线恢复。"""

import sqlite3
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from multiprocessing import get_context
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest

from tui_tool_receipts import ReceiptConflict, ToolReceiptStore, ToolTurn, UnknownToolCall


def _client_edits_then_exits(directory, turn, output):
    store = ToolReceiptStore(directory)
    if store.claim_delivery(turn, "edit"):
        with output.open("a") as target:
            target.write("once\n")
            target.flush()
            os.fsync(target.fileno())
    # 模拟客户端确实执行后、工具结果交还前进程崩溃，绕过正常退出清理。
    os._exit(0)


class ToolReceiptTests(unittest.TestCase):
    """使用独立连接、账号私有临时目录和独立进程验证工具交接。"""

    def test_schema_adopts_existing_receipt_and_preserves_unknown_version(self):
        """旧候选保留已登记工具，未来版本只报错。@return 无。"""
        self._register("existing")
        path = self.private / "tui-tool-receipts.sqlite"
        with closing(sqlite3.connect(path)) as db:
            db.execute("PRAGMA user_version=0")
        self.assertEqual(ToolReceiptStore(self.private).read(self.turn, "existing").name, "Read")
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            db.execute("PRAGMA user_version=2")
        with self.assertRaisesRegex(ValueError, "版本不受支持"):
            ToolReceiptStore(self.private)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)

    def setUp(self):
        """建立真实 SQLite 数据库及合成的认证身份。@return 无。"""
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private = self.root / "private"
        self.store = ToolReceiptStore(self.private)
        self.turn = ToolTurn("account-a", "principal-a", "session-a", "turn-a")

    def _worker(self, tool_id):
        return {"internal_id": "internal-" + tool_id, "backend": "tui", "generation": "generation-1"}

    def _register(self, tool_id="first", *, turn=None, name="Read", arguments=None):
        return self.store.register(turn or self.turn, tool_id, name=name,
                                   arguments=arguments if arguments is not None else {"path": "temporary"},
                                   **self._worker(tool_id))

    def _result(self, tool_id="first", content="读取结果", **extra):
        return {"type": "tool_result", "tool_use_id": tool_id, "content": content, **extra}

    def _race(self, function, count=6):
        barrier = Barrier(count)

        def attempt(index):
            barrier.wait(timeout=5)
            return function(index)

        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(attempt, range(count)))

    def test_multiple_same_name_out_of_order_denial_and_original_worker(self):
        """同名调用按 ID 接回乱序、多块和拒绝结果，worker 身份逐字段核对。@return 无。"""
        allowed = self._result("one", [{"type": "text", "text": "第一块"}, {"type": "text", "text": "第二块"}])
        denied = self._result("two", "客户端拒绝", is_error=True)
        for key in ("one", "two"):
            self.assertTrue(self._register(key))
            self.assertTrue(self.store.claim_delivery(self.turn, key))
            self.assertIsNone(self.store.take_result(self.turn, key, **self._worker(key)))

        for result in (denied, allowed):
            self.assertTrue(self.store.submit(self.turn, result))
        for result in (allowed, denied):
            key = result["tool_use_id"]
            worker = self._worker(key)
            for field in worker:
                incorrect = dict(worker, **{field: "other"})
                with self.subTest(field=field), self.assertRaises(UnknownToolCall):
                    self.store.take_result(self.turn, key, **incorrect)
            record = self.store.read(self.turn, key)
            self.assertEqual((record.state, record.name, record.internal_id), ("received", "Read", worker["internal_id"]))
            self.assertEqual(record.result, result)
            self.assertEqual(self.store.take_result(self.turn, key, **worker), result)
            self.assertFalse(self.store.submit(self.turn, result))
            with self.assertRaises(ReceiptConflict):
                self.store.close_turn(self.turn)
            for field in worker:
                with self.subTest(field=field), self.assertRaises(UnknownToolCall):
                    self.store.confirm_result(self.turn, key, **dict(worker, **{field: "other"}))
            self.assertTrue(self.store.confirm_result(self.turn, key, **worker))

        self.store.close_turn(self.turn)
        self.assertEqual(self.store.read(self.turn, "two").state, "closed")

    def test_scope_includes_all_authenticated_identifiers_and_registered_id(self):
        """相同内容及调用 ID 在四项归属中逐项隔离。@return 无。"""
        self._register()
        self.store.claim_delivery(self.turn, "first")
        original = self._result(content="原轮数据")
        self.store.submit(self.turn, original)
        for field in ("account_id", "principal_id", "session_id", "turn_id"):
            other = replace(self.turn, **{field: "different"})
            with self.subTest(field=field):
                with self.assertRaises(UnknownToolCall):
                    self.store.read(other, "first")
                with self.assertRaises(UnknownToolCall):
                    self.store.submit(other, original)
                self._register(turn=other)
                self.assertIsNone(self.store.read(other, "first").result)
                result = self._result(content=field)
                self.store.claim_delivery(other, "first")
                self.assertTrue(self.store.submit(other, result))
                self.assertEqual(self.store.read(other, "first").result, result)
                self.assertEqual(self.store.read(self.turn, "first").result, original)
                with self.assertRaises(ValueError):
                    replace(self.turn, **{field: " "})
        with self.assertRaises(UnknownToolCall):
            self.store.submit(self.turn, self._result("unregistered"))
        with self.assertRaises(UnknownToolCall):
            self.store.claim_delivery(self.turn, "unregistered")

    def test_registration_replay_requires_same_binding_and_argument_structure(self):
        """外部 ID、内部 ID、工具名、参数和原 worker 映射均不可篡改。@return 无。"""
        arguments = {"one": True, "two": [2, 3]}
        self.assertTrue(self._register(arguments=arguments))
        self.assertFalse(self._register(arguments={"two": [2, 3], "one": True}))
        self.assertEqual(self.store.read(self.turn, "first").state, "registered")
        worker = self._worker("first")
        binding = {"arguments": arguments, "name": "Read", **worker}
        for change in ({"internal_id": "other"}, {"name": "Edit"}, {"arguments": {"one": 1, "two": [2, 3]}},
                       {"arguments": {"one": True, "two": [3, 2]}}, {"backend": "legacy"}, {"generation": "g2"}):
            with self.subTest(change=change), self.assertRaises(ReceiptConflict):
                self.store.register(self.turn, "first", **(binding | change))
        with self.assertRaises(ReceiptConflict):
            self.store.register(self.turn, "another", **binding)
        with self.assertRaises(UnknownToolCall):
            self.store.read(self.turn, "another")
        with self.assertRaises(ReceiptConflict):
            self.store.close_turn(self.turn)

    def test_streamed_arguments_and_delivery_are_both_required_for_first_result(self):
        """参数流开始前持久登记，发出块结束前封存；先到的结果在任一条件缺失时拒绝。@return 无。"""
        worker = self._worker("first")
        result = self._result()
        self.assertTrue(self.store.register(self.turn, "first", name="Read", arguments=None, **worker))
        self.assertTrue(self.store.claim_delivery(self.turn, "first"))
        with self.assertRaises(ReceiptConflict):
            self.store.submit(self.turn, result)
        self.assertEqual(self.store.read(self.turn, "first").state, "delivery_unknown")
        reopened = ToolReceiptStore(self.private)
        self.assertFalse(reopened.register(self.turn, "first", name="Read", arguments={"path": "私有文件"}, **worker))
        self.assertFalse(reopened.register(self.turn, "first", name="Read", arguments=None, **worker))
        with self.assertRaises(ReceiptConflict):
            reopened.register(self.turn, "first", name="Read", arguments={}, **worker)
        self.assertTrue(reopened.submit(self.turn, result))
        self._register("second", arguments={})
        with self.assertRaises(ReceiptConflict):
            self.store.submit(self.turn, self._result("second"))
        self.assertEqual(self.store.read(self.turn, "second").state, "registered")
        self.assertTrue(self.store.claim_delivery(self.turn, "second"))
        self.assertTrue(self.store.submit(self.turn, self._result("second")))

    def test_result_batch_rolls_back_new_rows_on_conflicts_and_unknown_calls(self):
        """同批重复、与已有结果冲突、未登记及尚未封存均保持接收的原子性。@return 无。"""
        for key in ("read", "edit"):
            self._register(key)
            self.store.claim_delivery(self.turn, key)
        self.store.register(self.turn, "partial", arguments=None, name="Read", **self._worker("partial"))
        self.store.claim_delivery(self.turn, "partial")
        read, edit = self._result("read"), self._result("edit")
        self.store.submit(self.turn, read)
        for last, error in ((self._result("read", "冲突"), ReceiptConflict),
                            (self._result("edit", "同批冲突"), ReceiptConflict),
                            (self._result("absent"), UnknownToolCall),
                            (self._result("partial"), ReceiptConflict),
                            (self._result("read", is_error="非法"), ValueError)):
            with self.subTest(last=last):
                with self.assertRaises(error):
                    self.store.submit_many(self.turn, [read, edit, last])
                self.assertEqual(self.store.read(self.turn, "edit").state, "delivery_unknown")
                self.assertEqual(self.store.read(self.turn, "read").result, read)
        self.assertEqual(self.store.submit_many(self.turn, [edit, edit, read]), [True, False, False])
        self.assertEqual(self.store.submit_many(self.turn, [read, edit]), [False, False])
        with self.assertRaises(ValueError):
            self.store.submit_many(self.turn, [])

    def test_client_crash_after_edit_preserves_uncertainty_and_reconciles_by_original_result(self):
        """真实进程在一次写文件后退出；恢复按原回执收尾，文件只追加一次。@return 无。"""
        self._register("edit", name="Edit")
        output = self.root / "client-file"
        child = get_context("spawn").Process(target=_client_edits_then_exits, args=(self.private, self.turn, output))
        child.start()
        try:
            child.join(timeout=10)
            self.assertEqual(child.exitcode, 0)
        finally:
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)
            child.close()
        restarted = ToolReceiptStore(self.private)
        self.assertEqual(restarted.read(self.turn, "edit").state, "delivery_unknown")
        self.assertFalse(restarted.claim_delivery(self.turn, "edit"))
        self.assertEqual(output.read_text(), "once\n")
        worker = self._worker("edit")
        result = self._result("edit", "已核对写入")
        self.assertTrue(restarted.submit(self.turn, result))
        self.assertEqual(restarted.take_result(self.turn, "edit", **worker), result)
        reopened = ToolReceiptStore(self.private)
        self.assertEqual(reopened.read(self.turn, "edit").state, "result_delivery_unknown")
        self.assertIsNone(reopened.take_result(self.turn, "edit", **worker))
        with self.assertRaises(ReceiptConflict):
            reopened.close_turn(self.turn)
        self.assertTrue(reopened.confirm_result(self.turn, "edit", **worker))
        self.assertFalse(reopened.confirm_result(self.turn, "edit", **worker))
        self.assertEqual(reopened.read(self.turn, "edit").state, "confirmed")
        self.assertEqual(output.read_text(), "once\n")

    def test_racing_writes_in_two_stores_grant_each_delivery_once(self):
        """不同存储实例共用数据库时仅一个调用方取得各阶段首次写入。@return 无。"""
        stores = [self.store, ToolReceiptStore(self.private)]
        self.assertEqual(self._race(lambda i: stores[i % 2].register(
            self.turn, "first", name="Read", arguments={}, **self._worker("first"))).count(True), 1)
        self.assertEqual(self._race(lambda i: stores[i % 2].claim_delivery(self.turn, "first")).count(True), 1)
        result = self._result(content=[{"type": "text", "text": "多块结果"}])
        self.assertEqual(self._race(lambda i: stores[i % 2].submit(self.turn, result)).count(True), 1)
        ordered_differently = dict(reversed(list(result.items())))
        self.assertFalse(self.store.submit(self.turn, ordered_differently))
        deliveries = self._race(lambda i: stores[i % 2].take_result(self.turn, "first", **self._worker("first")))
        self.assertEqual(deliveries.count(result), 1)
        self.assertEqual(deliveries.count(None), len(deliveries) - 1)
        self.assertEqual(self._race(lambda i: stores[i % 2].confirm_result(
            self.turn, "first", **self._worker("first"))).count(True), 1)

    def test_concurrent_conflict_preserves_first_result_and_error_flag(self):
        """两个不同回执竞争时保留唯一赢家，冲突消息不含正文。@return 无。"""
        self._register()
        self.store.claim_delivery(self.turn, "first")
        results = [self._result(content="客户端私有正文", is_error=value) for value in (False, True)]

        def submit(index):
            try:
                return self.store.submit(self.turn, results[index])
            except ReceiptConflict as exc:
                self.assertNotIn("客户端私有正文", str(exc))
                return False

        accepted = self._race(submit, count=2)
        self.assertEqual(accepted.count(True), 1)
        self.assertEqual(self.store.read(self.turn, "first").result, results[accepted.index(True)])
        with self.assertRaises(ValueError):
            self.store.submit(self.turn, self._result(is_error=1))
        with self.assertRaises(ValueError):
            self.store.submit(self.turn, {"type": "tool_use", "tool_use_id": "first"})

    def test_close_scrubs_body_but_retains_replay_fence(self):
        """已确认后清除磁盘结果正文，旧轮的相同及冲突重放仍可判别。@return 无。"""
        self._register()
        self.store.claim_delivery(self.turn, "first")
        worker = self._worker("first")
        result = self._result(content="PRIVATE-BODY-Ut3jiXcQ")
        self.store.submit(self.turn, result)
        with self.assertRaises(ReceiptConflict):
            self.store.confirm_result(self.turn, "first", **worker)
        with self.assertRaises(ReceiptConflict):
            self.store.close_turn(self.turn)
        self.store.take_result(self.turn, "first", **worker)
        self.store.confirm_result(self.turn, "first", **worker)
        self.store.close_turn(self.turn)
        self.store.close_turn(self.turn)
        reopened = ToolReceiptStore(self.private)
        record = reopened.read(self.turn, "first")
        self.assertEqual((record.state, record.result), ("closed", None))
        self.assertFalse(reopened.claim_delivery(self.turn, "first"))
        self.assertIsNone(reopened.take_result(self.turn, "first", **worker))
        self.assertFalse(reopened.submit(self.turn, result))
        with self.assertRaises(ReceiptConflict):
            reopened.submit(self.turn, self._result(content="另一个结果"))
        self.assertFalse(self._register())
        with self.assertRaises(ReceiptConflict):
            self._register("late")
        for entry in self.private.iterdir():
            self.assertNotIn(result["content"].encode(), entry.read_bytes())

    def test_private_files_and_unsafe_existing_paths(self):
        """核对私有目录与 SQLite 文件权限，并拒绝链接及开放的目录。@return 无。"""
        self.assertEqual(self.private.stat().st_mode & 0o777, 0o700)
        path = self.private / "tui-tool-receipts.sqlite"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        public = self.root / "public"
        public.mkdir(mode=0o700)
        public.chmod(0o755)
        with self.assertRaises(ValueError):
            ToolReceiptStore(public)
        private_link = self.root / "private-link"
        private_link.symlink_to(self.private, target_is_directory=True)
        with self.assertRaises(OSError):
            ToolReceiptStore(private_link)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            ToolReceiptStore(self.private)
        path.unlink()
        target = self.root / "target"
        target.write_text("保留")
        path.symlink_to(target)
        with self.assertRaises(ValueError):
            ToolReceiptStore(self.private)
        self.assertEqual(target.read_text(), "保留")


if __name__ == "__main__":
    unittest.main()
