"""核对冷导入边界、记录归属和工具声明。"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
import json
from os import close, openpty
from pathlib import Path
from sys import executable
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import TestCase
from uuid import uuid4

from tui_cold_history import IMPORT_BOUNDARY, ColdHistory
from tui_reconnect import digest
from tui_workspace_launch import HistoryReplay, _key, _project_history_dir, _resume_path, launch_workspace_cli


class ColdHistoryTests(TestCase):
    """使用合成输入测试固定 CLI 的历史合同。"""

    def setUp(self):
        """建立带已完成工具组的对话。@return 无。"""
        self.body = {
            "model": "claude-sonnet-4-6", "max_tokens": 128,
            "system": [{"type": "text", "text": "业务指令一"}, {"type": "text", "text": "业务指令二"}],
            "tools": [{"name": "LookupNote", "input_schema": {"type": "object"}}],
            "messages": [
                {"role": "user", "content": "上一轮输入"},
                {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "toolu_old", "name": "LookupNote", "input": {}}]},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_old", "content": "上一轮结果"}]},
                {"role": "assistant", "content": "上一轮答复"},
                {"role": "user", "content": "本轮输入"},
            ],
        }

    def test_bound_history_is_idempotent_and_readable_after_restart(self):
        """核对同一绑定只写入已完成的历史，重启后由启动器读回。@return 无。"""
        plan = ColdHistory.from_request(self.body)
        self.assertEqual(plan.prompt, "本轮输入")
        self.assertEqual(plan.system, "业务指令一\n业务指令二")
        session = str(uuid4())
        work = Path("/native/workspace")
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            self.assertEqual(plan.import_session(config, work, session), session)
            history = _resume_path(stack, config, work, session, required=True)
            initial = history.read_bytes()
            restored = ColdHistory.from_request(deepcopy(self.body))
            self.assertEqual(restored.import_session(config, work, session), session)
            self.assertEqual(history.read_bytes(), initial)
            self.assertEqual(list(history.parent.iterdir()), [history])
            self.assertEqual(history.stat().st_mode & 0o777, 0o600)
            rows = [json.loads(line) for line in initial.splitlines()]
            self.assertEqual([row["type"] for row in rows], ["user", "assistant", "user", "assistant"])
            self.assertEqual([row["parentUuid"] for row in rows], [None, *[row["uuid"] for row in rows[:-1]]])
            self.assertEqual({row["sessionId"] for row in rows}, {session})
            expected = []
            for row in self.body["messages"][:-1]:
                content = row["content"]
                if isinstance(content, str):
                    content = [{"type": "text", "text": content}]
                expected.append({"role": row["role"], "content": content})
            self.assertEqual([row["message"] for row in rows], expected)

    def test_same_binding_reopens_through_real_pty_launcher(self):
        """以独立 PTY 子进程核对重复导入、显式恢复、自动恢复及分叉启动。@return 无。"""
        scope = (3, "测试环境", 8)
        account, environment, principal = scope
        session, native_id = "测试会话", str(uuid4())
        key = _key((scope, session))
        plan = ColdHistory.from_request(self.body)
        with TemporaryDirectory() as directory:
            storage = Path(directory)
            base = storage / "tui-workspaces"
            base.mkdir(mode=0o700)
            work = base / _key((scope, "session", session))
            work.mkdir(mode=0o700)
            binding = base / (key + ".json")
            binding.write_text(json.dumps({"session_key": key, "client_path": None, "native_session_id": native_id}))
            binding.chmod(0o600)
            config = storage / "config"
            config.mkdir(mode=0o700)
            project = _project_history_dir(config, work)
            history = project / (native_id + ".jsonl")
            workspace = {"version": 1, "work_dir": str(work), "binding_file": str(binding), "native_session_id": native_id}
            # 终端子进程只记录真实启动参数，保留历史在 CLI 提交当前问题前的状态。
            probe = (
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "assert os.isatty(0)\n"
                "Path(sys.argv[1]).write_text(json.dumps([os.getcwd(), *sys.argv[2:]]))\n"
            )

            def start(prepare=None, *, resume=None):
                reservation_id = str(uuid4())
                reservation = {"account_id": account, "environment_id": environment, "principal_id": principal,
                               "session_id": session, "reservation_id": reservation_id}
                command = {"action": "send", "reservation_id": reservation_id, "workspace": workspace}
                output = storage / reservation_id
                master, slave = openpty()
                try:
                    child = launch_workspace_cli(
                        reservation, command, program=Path(executable), arguments=["-I", "-c", probe, str(output)],
                        config_dir=config, environment={}, resume=resume, terminal_fd=slave, storage=storage,
                        prepare_history=prepare,
                    )
                    try:
                        self.assertEqual(child.wait(timeout=5), 0)
                    finally:
                        if child.poll() is None:
                            child.kill()
                            child.wait()
                finally:
                    close(slave)
                    close(master)
                cwd, *argv = json.loads(output.read_text())
                self.assertEqual(cwd, str(work))
                return argv

            expected = ["--resume", str(history)]
            self.assertEqual(start(plan.import_session), expected)
            snapshot = history.read_bytes()
            with ThreadPoolExecutor(max_workers=4) as pool:
                retries = [pool.submit(start, plan.import_session) for _ in range(4)]
                self.assertEqual([retry.result() for retry in retries], [expected] * 4)
            self.assertEqual(start(resume=True), expected)
            self.assertEqual(start(), expected)
            self.assertEqual(list(project.iterdir()), [history])

            changed = deepcopy(self.body)
            changed["messages"][0]["content"] = "不同的确认边界"
            fork_plan = ColdHistory.from_request(changed)
            flag, path = start(fork_plan.import_session)
            self.assertEqual(flag, "--resume")
            fork = Path(path)
            self.assertNotEqual(fork, history)
            fork_snapshot = fork.read_bytes()
            for resume in (True, None):
                with self.subTest(branch=fork.stem, resume=resume):
                    restored = ColdHistory.from_request(deepcopy(changed))
                    self.assertEqual(start(restored.import_session, resume=resume), ["--resume", str(fork)])
            self.assertEqual(start(resume=True), expected)
            self.assertEqual(start(), expected)
            self.assertEqual(set(project.iterdir()), {history, fork})
            self.assertEqual(history.read_bytes(), snapshot)
            self.assertEqual(fork.read_bytes(), fork_snapshot)

    def test_reuses_previous_import_format_without_rewriting(self):
        """旧版文件沿原条件读回，新模型请求另建只含历史事实的分支。@return 无。"""
        plan = ColdHistory.from_request(self.body)
        session = str(uuid4())
        work = Path("/native/workspace")
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            plan.import_session(config, work, session)
            history = _resume_path(stack, config, work, session, required=True)
            rows = [json.loads(line) for line in history.read_bytes().splitlines()]
            rows[0].pop(IMPORT_BOUNDARY)
            for row in rows:
                if row["type"] == "assistant":
                    row["message"].update(model=plan.model, id="msg_legacy", usage={"output_tokens": 0})
            history.write_text("".join(json.dumps(row) + "\n" for row in rows))
            old_bytes = history.read_bytes()
            self.assertEqual(plan.import_session(config, work, session), session)
            changed = ColdHistory.from_request({**self.body, "model": "another-model"})
            branch = changed.import_session(config, work, session)
            self.assertNotEqual(branch, session)
            self.assertEqual(changed.import_session(config, work, session), branch)
            self.assertEqual(history.read_bytes(), old_bytes)

    def test_import_scope_changes_fork_without_overwriting_history(self):
        """消息相同且本轮有效设置有变化时，分别复用两个已发布的记录。@return 无。"""
        plan = ColdHistory.from_request(self.body)
        changed = ColdHistory.from_request({**self.body, "max_tokens": 256})
        session = str(uuid4())
        work = Path("/native/workspace")
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            self.assertEqual(plan.import_session(config, work, session), session)
            history = _resume_path(stack, config, work, session, required=True)
            snapshot = history.read_bytes()
            fork = changed.import_session(config, work, session)
            self.assertNotEqual(fork, session)
            self.assertEqual(changed.import_session(config, work, session), fork)
            self.assertEqual(plan.import_session(config, work, session), session)
            self.assertEqual(history.read_bytes(), snapshot)

    def test_concurrent_imports_preserve_winning_history(self):
        """相同并发导入复用原文件，分歧历史保留原文件并使用独立会话。@return 无。"""
        first = ColdHistory.from_request(self.body)
        changed = deepcopy(self.body)
        changed["messages"][0]["content"] = "另一条已确认的上一轮输入"
        second = ColdHistory.from_request(changed)
        work = Path("/native/workspace")
        session = str(uuid4())
        with TemporaryDirectory() as directory, ThreadPoolExecutor(max_workers=8) as pool, ExitStack() as stack:
            config = Path(directory)
            barrier = Barrier(8)

            def prepare(plan):
                barrier.wait(timeout=5)
                return plan.import_session(config, work, session)

            futures = [pool.submit(prepare, first) for _ in range(8)]
            self.assertEqual([future.result() for future in futures], [session] * 8)
            original = _resume_path(stack, config, work, session, required=True)
            original_bytes = original.read_bytes()
            self.assertEqual(list(original.parent.iterdir()), [original])
            barrier = Barrier(8)
            original_retry = pool.submit(prepare, first)
            fork_attempts = [pool.submit(prepare, second) for _ in range(7)]
            fork, = {future.result() for future in fork_attempts}
            self.assertEqual(original_retry.result(), session)
            self.assertNotEqual(fork, session)
            self.assertEqual(original.read_bytes(), original_bytes)
            forked = _resume_path(stack, config, work, fork, required=True)
            fork_bytes = forked.read_bytes()
            self.assertEqual(json.loads(fork_bytes.splitlines()[0])["message"]["content"][0]["text"],
                             "另一条已确认的上一轮输入")
            barrier = Barrier(8)
            futures = [pool.submit(prepare, second) for _ in range(8)]
            self.assertEqual([future.result() for future in futures], [fork] * 8)
            self.assertEqual(set(original.parent.iterdir()), {original, forked})
            self.assertEqual(forked.read_bytes(), fork_bytes)

    def test_advanced_fork_keeps_its_bytes_and_reuses_unadvanced_revision(self):
        """已推进的分叉保持原记录，重复确认边界复用同一未推进修订。@return 无。"""
        base = ColdHistory.from_request(self.body)
        changed = deepcopy(self.body)
        changed["messages"][0]["content"] = "分叉的确认输入"
        fork_plan = ColdHistory.from_request(changed)
        work = Path("/native/workspace")
        session, other = str(uuid4()), str(uuid4())
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            base.import_session(config, work, session)
            base.import_session(config, work, other)
            original = _resume_path(stack, config, work, session, required=True)
            original_bytes = original.read_bytes()
            first = fork_plan.import_session(config, work, session)
            forked = _resume_path(stack, config, work, first, required=True)
            last = json.loads(forked.read_bytes().splitlines()[-1])
            with forked.open("a") as output:
                output.write(json.dumps({**last, "type": "user", "parentUuid": last["uuid"], "uuid": str(uuid4()),
                                         "message": {"role": "user", "content": "当前问题"}}) + "\n")
            advanced_bytes = forked.read_bytes()
            second = fork_plan.import_session(config, work, session)
            self.assertNotIn(second, {session, first})
            restored = ColdHistory.from_request(deepcopy(changed))
            self.assertEqual(restored.import_session(config, work, session), second)
            self.assertNotIn(restored.import_session(config, work, other), {session, first, second, other})
            self.assertEqual(original.read_bytes(), original_bytes)
            self.assertEqual(forked.read_bytes(), advanced_bytes)

    def test_completed_fork_reuses_confirmed_prefix_for_the_same_question(self):
        """同一问题使用原分叉 UUID，退出后清除临时前缀。@return 无。"""
        original = ColdHistory.from_request(self.body)
        changed = deepcopy(self.body)
        changed["messages"][0]["content"] = "分叉的确认输入"
        fork = ColdHistory.from_request(changed)
        work, session = Path("/native/workspace"), str(uuid4())
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            original.import_session(config, work, session)
            fork_id = fork.import_session(config, work, session)
            archive = _resume_path(stack, config, work, fork_id, required=True)
            prefix = archive.read_bytes()
            parent = json.loads(prefix.splitlines()[-1])["uuid"]
            with archive.open("a") as output:
                for message in ({"role": "user", "content": fork.prompt},
                                {"role": "assistant", "content": "原答复", "stop_reason": "end_turn"}):
                    entry = str(uuid4())
                    output.write(json.dumps({"type": message["role"], "uuid": entry, "parentUuid": parent,
                                             "sessionId": fork_id, "cwd": str(work), "message": message}) + "\n")
                    parent = entry
            completed = archive.read_bytes()
            with ExitStack() as replay_resources:
                replay = fork.import_session(config, work, session, replay_resources=replay_resources)
                self.assertIsInstance(replay, HistoryReplay)
                self.assertEqual(replay.native_id, fork_id)
                self.assertEqual(replay.path.read_bytes(), prefix)
                self.assertEqual(len(list(archive.parent.glob("*.jsonl"))), 2)
            self.assertFalse(replay.path.exists())
            self.assertEqual(archive.read_bytes(), completed)

            changed["messages"][-1]["content"] = "另一条当前输入"
            different = ColdHistory.from_request(changed)
            self.assertIsInstance(different.import_session(config, work, session, replay_resources=stack), str)
            self.assertEqual(len(list(archive.parent.glob("*.jsonl"))), 3)
            self.assertEqual(archive.read_bytes(), completed)

    def test_mismatched_disk_owner_is_not_replaced_or_used(self):
        """已有文件的原生会话或目录发生变化时拒绝恢复并保留文件。@return 无。"""
        plan = ColdHistory.from_request(self.body)
        work = Path("/native/workspace")
        session = str(uuid4())
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            plan.import_session(config, work, session)
            path = _resume_path(stack, config, work, session, required=True)
            payload = path.read_text().replace(str(work), "/native/other")
            path.write_text(payload)
            with self.assertRaisesRegex(ValueError, "工作区不匹配"):
                plan.import_session(config, work, session)
            self.assertEqual(path.read_text(), payload)

    def test_plain_first_turn_leaves_creation_to_cli_and_isolates_old_history(self):
        """纯新轮复用登记身份或另开无历史的会话，已有对话保留原字节。@return 无。"""
        previous = ColdHistory.from_request(self.body)
        fresh = ColdHistory.from_request({
            "model": self.body["model"], "max_tokens": 128,
            "messages": [{"role": "user", "content": "新问题"}],
        })
        self.assertEqual((fresh.history, fresh.system, fresh.tools), ([], "", {}))
        work = Path("/native/workspace")
        session = str(uuid4())
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            self.assertEqual(fresh.import_session(config, work, session), session)
            self.assertIsNone(_resume_path(stack, config, work, session, required=False))
            previous.import_session(config, work, session)
            original = _resume_path(stack, config, work, session, required=True)
            payload = original.read_bytes()
            branch = fresh.import_session(config, work, session)
            self.assertNotEqual(branch, session)
            self.assertIsNone(_resume_path(stack, config, work, branch, required=False))
            self.assertEqual(original.read_bytes(), payload)

    def test_unpaired_and_unsupported_inputs_use_existing_contract(self):
        """检查缺配对及扩展字段按原入口合同准入。@return 无。"""
        missing = deepcopy(self.body)
        missing["messages"][2]["content"][0]["tool_use_id"] = "toolu_other"
        self.assertIsNone(ColdHistory.from_request(missing))
        self.assertIsNone(ColdHistory.from_request({**self.body, "tool_choice": {"type": "any"}}))
        cached = deepcopy(self.body)
        cached["system"][0]["cache_control"] = {"type": "ephemeral"}
        self.assertIsNone(ColdHistory.from_request(cached))

    def test_native_historical_cache_markers_keep_block_positions_and_ttl(self):
        """相同文本上的断点依块位置核对，支持原始 TTL 缺省。@return 无。"""
        long = {"type": "ephemeral", "ttl": "1h"}
        short = {"type": "ephemeral"}
        same = {"type": "text", "text": "重复历史段"}
        cached = {**same, "cache_control": long}
        body = {**self.body, "messages": [
            {"role": "user", "content": [cached]},
            {"role": "user", "content": [same]},
            {"role": "assistant", "content": [{"type": "text", "text": "已回复", "cache_control": short}]},
            self.body["messages"][-1],
        ]}
        plan = ColdHistory.from_request(body)
        self.assertTrue(plan.has_history_cache_markers())
        native = {**body, "messages": [{"role": "user", "content": [cached, same]}, *body["messages"][2:]]}
        self.assertTrue(plan.matches_history_cache_markers(native))
        moved = deepcopy(native)
        moved["messages"][0]["content"] = [same, cached]
        self.assertFalse(plan.matches_history_cache_markers(moved))
        rewritten = deepcopy(native)
        rewritten["messages"][1]["content"][0]["cache_control"]["ttl"] = "5m"
        self.assertFalse(plan.matches_history_cache_markers(rewritten))
        self.assertFalse(plan.matches_history_cache_markers({**native, "cache_control": long}))
        self.assertFalse(plan.matches_history_cache_markers({**native, "system": [cached]}))

    def test_history_cache_native_selection_leaves_other_cache_shapes_to_existing_contract(self):
        """仅准入已验证的断点类型、数量、时长顺序及历史位置。@return 无。"""
        marker = {"type": "ephemeral", "ttl": "1h"}
        marked = {"type": "text", "text": "合成标记", "cache_control": marker}
        cases = ([marked] * 5, [{**marked, "cache_control": {"type": "ephemeral"}}, marked],
                 [{**marked, "cache_control": {**marker, "scope": "global"}}])
        for blocks in cases:
            rows = [{"role": "user", "content": blocks}, *self.body["messages"][1:]]
            self.assertIsNone(ColdHistory.from_request({**self.body, "messages": rows}))
        rows = [*self.body["messages"][:-1], {"role": "user", "content": [marked]}]
        self.assertIsNone(ColdHistory.from_request({**self.body, "messages": rows}))

    def test_forced_history_cache_ttl_preserves_original_receipt_boundary(self):
        """有效 TTL 写入原生历史，冻结边界仍核对平台政策和客户端原值。@return 无。"""
        body = deepcopy(self.body)
        body["messages"][0]["content"] = [{"type": "text", "text": "有标记的历史",
                                           "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
        plan = ColdHistory.from_request(body, cache_ttl="5m")
        forced = deepcopy(body)
        forced["messages"][0]["content"][0]["cache_control"]["ttl"] = "5m"
        self.assertTrue(plan.matches_history_cache_markers(forced))
        self.assertFalse(plan.matches_history_cache_markers(body))
        self.assertEqual(plan.history[0]["content"][0]["cache_control"]["ttl"], "1h")
        self.assertNotEqual(plan.receipt_boundary(), ColdHistory.from_request(body).receipt_boundary())
        self.assertNotEqual(plan.receipt_boundary(), ColdHistory.from_request(forced, cache_ttl="5m").receipt_boundary())
        self.assertIsNone(ColdHistory.from_request(self.body, cache_ttl="5m"))
        for ttl in ("off", "5m", "1h"):
            signed = ColdHistory.from_request(body, cache_ttl=ttl)
            boundary = signed.receipt_boundary()
            self.assertEqual(ColdHistory.from_receipt_boundary(body, boundary), signed)
            self.assertIsNone(ColdHistory.from_receipt_boundary(forced, boundary))

        with TemporaryDirectory() as directory, ExitStack() as stack:
            config, work, native_id = Path(directory), Path("/native/workspace"), str(uuid4())
            self.assertEqual(plan.import_session(config, work, native_id), native_id)
            path = _resume_path(stack, config, work, native_id, required=True)
            self.assertEqual(json.loads(path.read_bytes().splitlines()[0])["message"], forced["messages"][0])

    def test_preserves_completed_tool_result_text_blocks(self):
        """导入旧工具结果的文本块顺序及配对，扩展块沿原入口合同。@return 无。"""
        body = deepcopy(self.body)
        result = body["messages"][2]["content"][0]
        result["content"] = [
            {"type": "text", "text": "旧工具结果第一段"},
            {"type": "text", "text": "旧工具结果第二段"},
        ]
        work, session = Path("/native/workspace"), str(uuid4())
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            self.assertEqual(ColdHistory.from_request(body).import_session(config, work, session), session)
            path = _resume_path(stack, config, work, session, required=True)
            row = json.loads(path.read_bytes().splitlines()[2])
            self.assertEqual(row["message"], {"role": "user", "content": [result]})
        result["content"][1]["cache_control"] = {"type": "ephemeral"}
        plan = ColdHistory.from_request(body)
        self.assertTrue(plan.has_history_cache_markers())
        self.assertTrue(plan.matches_history_cache_markers(body))
        moved = deepcopy(body)
        moved["messages"][2]["content"][0]["content"].reverse()
        self.assertFalse(plan.matches_history_cache_markers(moved))
        replayed = deepcopy(body)
        replayed["messages"][2]["content"][0]["tool_use_id"] = "toolu_other"
        self.assertFalse(plan.matches_history_cache_markers(replayed))
        result["content"][1]["cache_control"]["ttl"] = "unsupported"
        self.assertIsNone(ColdHistory.from_request(body))

    def test_split_assistant_and_user_rows_preserve_the_closed_tool_group(self):
        """相邻同角色历史保留原始内容，整组回执须在下一助理轮之前闭合。@return 无。"""
        body = deepcopy(self.body)
        messages = body["messages"]
        other_call = {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_other", "name": "LookupNote", "input": {}}]}
        other_result = {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_other", "content": "第二个历史结果"}]}
        messages.insert(2, other_call)
        messages.insert(4, other_result)
        plan = ColdHistory.from_request(body)
        self.assertEqual(plan.history, messages[:-1])
        work, session = Path("/native/workspace"), str(uuid4())
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            self.assertEqual(plan.import_session(config, work, session), session)
            path = _resume_path(stack, config, work, session, required=True)
            recorded = [json.loads(line)["message"] for line in path.read_bytes().splitlines()]
            self.assertEqual(recorded[1:3], [
                {"role": "assistant", "content": [*messages[1]["content"], *other_call["content"]]},
                {"role": "user", "content": [*messages[3]["content"], *other_result["content"]]},
            ])
            self.assertEqual(plan.history, messages[:-1])
        messages[4], messages[5] = messages[5], messages[4]
        self.assertIsNone(ColdHistory.from_request(body))

    def test_current_text_boundaries_are_part_of_the_tool_receipt(self):
        """冻结本轮文本块的顺序与边界，对照同一字符串的不同切分。@return 无。"""
        body = deepcopy(self.body)
        current = [{"type": "text", "text": part} for part in ("本轮", "输入")]
        body["messages"][-1]["content"] = current
        plan = ColdHistory.from_request(body)
        self.assertEqual(plan.submitted_blocks(), current)
        self.assertEqual(plan.receipt_boundary()["digest"], digest([plan._scope(), plan.history, ("本轮", "输入")]))
        self.assertNotEqual(plan.receipt_boundary(), ColdHistory.from_request(self.body).receipt_boundary())

    def test_replace_distinguishes_omitted_and_empty_system(self):
        """省略保留工作正文，显式空值使用空的原生替换文件。@return 无。"""
        body = deepcopy(self.body)
        self.assertEqual(ColdHistory.from_request(body, "replace").system_argument(),
                         ("--system-prompt-file", "业务指令一\n业务指令二"))
        del body["system"]
        self.assertIsNone(ColdHistory.from_request(body, "replace").system_argument())
        for value in ("", []):
            self.assertEqual(ColdHistory.from_request({**body, "system": value}, "replace").system_argument(),
                             ("--system-prompt-file", ""))

    def test_reminder_is_added_only_to_first_suitable_user_message(self):
        """导入优先附在首条用户消息，纯新轮保留原始问题和提醒顺序。@return 无。"""
        marker = "<system-reminder>\n业务指令一\n业务指令二\n</system-reminder>"
        plan = ColdHistory.from_request(self.body, "user_reminder")
        self.assertEqual(plan.submitted_prompt(), "本轮输入")
        self.assertIsNone(plan.system_argument())
        work = Path("/native/workspace")
        session = str(uuid4())
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            plan.import_session(config, work, session)
            path = _resume_path(stack, config, work, session, required=True)
            rows = [json.loads(line) for line in path.read_bytes().splitlines()]
            self.assertEqual(rows[0]["message"]["content"], [
                {"type": "text", "text": "上一轮输入"}, {"type": "text", "text": marker},
            ])
            self.assertEqual(rows[2]["message"]["content"], self.body["messages"][2]["content"])
            self.assertEqual(path.read_text().count("<system-reminder>"), 1)
        fresh = ColdHistory.from_request({**self.body, "messages": self.body["messages"][-1:]}, "user_reminder")
        self.assertEqual(fresh.submitted_prompt(), f"本轮输入\n\n{marker}")

    def test_mcp_only_advertises_this_sessions_declarations(self):
        """检查 MCP 只提供本次准入的定义，执行由原回执链处理。@return 无。"""
        body = deepcopy(self.body)
        for name in ("Lookup-Note", "Lookup_Note"):
            body["tools"].append({"name": name, "input_schema": {"type": "object"}})
        plan = ColdHistory.from_request(body)
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        self.assertEqual(plan.mcp(request)["result"]["tools"], [
            {"name": name, "description": "", "inputSchema": {"type": "object"}}
            for name in ("LookupNote", "Lookup-Note", "Lookup_Note")
        ])
        self.assertEqual(list(plan.tools), ["mcp__flower__LookupNote", "mcp__flower__Lookup-Note", "mcp__flower__Lookup_Note"])
        self.assertIn("error", plan.mcp({**request, "method": "tools/call"}))

    def test_output_effort_matches_the_frozen_root_scope(self):
        """只有原生交互 CLI 已支持的强度进入原生计划。@return 无。"""
        expected = ColdHistory.from_request({**self.body, "output_config": {"effort": "low"}})
        self.assertEqual(expected.effort, "low")
        self.assertNotEqual(expected.receipt_boundary(), ColdHistory.from_request(self.body).receipt_boundary())
        for output in ({"effort": "unknown"}, {"format": {"type": "json_schema", "schema": {}}}):
            self.assertIsNone(ColdHistory.from_request({**self.body, "output_config": output}))

    def test_explicit_adaptive_updates_is_frozen(self):
        """已验证的自适应思考配置随根轮冻结。@return 无。"""
        thinking = {"type": "adaptive", "display": "updates"}
        for model in ("claude-sonnet-4-6", "claude-opus-5-5"):
            with self.subTest(model=model):
                body = {**self.body, "model": model, "thinking": thinking}
                plan = ColdHistory.from_request(body)
                boundary = plan.receipt_boundary()
                self.assertEqual(plan.thinking, thinking)
                self.assertEqual(ColdHistory.from_receipt_boundary(body, boundary), plan)
                for changed in ({"type": "adaptive"}, {**thinking, "display": "omitted"},
                                {**thinking, "display": "summarized"}, {"type": "disabled"}):
                    self.assertIsNone(ColdHistory.from_receipt_boundary({**body, "thinking": changed}, boundary))
        self.assertIsNone(ColdHistory.from_request({**self.body, "model": "claude-haiku-4-5", "thinking": thinking}))

    def test_explicit_auto_tool_choice_preserves_parallel_permission(self):
        """自动选择进入原生合同并随原工具组冻结。@return 无。"""
        choice = {"type": "auto", "disable_parallel_tool_use": False}
        plan = ColdHistory.from_request({**self.body, "tool_choice": choice})
        native = {"tools": list(plan.tools.values())}
        self.assertTrue(plan.matches_tool_choice(native))
        self.assertTrue(plan.matches_tool_choice({**native, "tool_choice": choice}))
        self.assertFalse(plan.matches_tool_choice({"tools": []}))
        self.assertNotEqual(plan.receipt_boundary(), ColdHistory.from_request(self.body).receipt_boundary())
        for other in ({"type": "none"}, {"type": "tool", "name": "LookupNote"},
                      {**choice, "disable_parallel_tool_use": True}, {**choice, "disable_parallel_tool_use": 0}):
            with self.subTest(other=other):
                self.assertFalse(plan.matches_tool_choice({**native, "tool_choice": other}))
                self.assertIsNone(ColdHistory.from_request({**self.body, "tool_choice": other}))

    def test_only_matching_inline_image_enters_native_input(self):
        """历史和本轮的内嵌图像须匹配声明格式。@return 无。"""
        picture = {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                  "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j4uoAAAAASUVORK5CYII="}}
        raw = deepcopy(self.body)
        raw["messages"][0]["content"] = [{"type": "text", "text": "历史图像"}, picture]
        self.assertEqual(ColdHistory.from_request(raw).history[0]["content"][-1], picture)
        current = {**raw, "messages": raw["messages"][:1]}
        self.assertEqual(ColdHistory.from_request(current).submitted_blocks(), raw["messages"][0]["content"])
        image_only = {**raw, "messages": [{"role": "user", "content": [picture]}]}
        self.assertEqual(ColdHistory.from_request(image_only).submitted_blocks(), [picture])
        for source in ({"type": "url", "url": "https://example.invalid/picture.png"},
                       {**picture["source"], "data": "invalid base64"},
                       {**picture["source"], "media_type": "image/jpeg"},
                       {**picture["source"], "media_type": []},
                       {**picture["source"], "media_type": "image/webp", "data": "UklGRiQAAABXQVZF"}):
            with self.subTest(source=source):
                raw["messages"][0]["content"][-1] = {"type": "image", "source": source}
                self.assertIsNone(ColdHistory.from_request(raw))
                self.assertIsNone(ColdHistory.from_request(current))
