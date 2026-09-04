"""定时养号和 cc2api 集成的后端回归测试。"""

import json
import os
import re
import sqlite3
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic import ValidationError

import main


class TopicPromptTests(unittest.TestCase):
    """验证 topic prompt 模式、自然组合、相似度窗口和覆盖优先级。"""

    def setUp(self) -> None:
        """
        准备各测试复用的标准 topic。

        :return: None
        """
        self.topic = {
            "no": 1,
            "title": "标准题目",
            "description": "只使用题库描述",
            "category": "测试",
        }

    def test_canonical_prompt_is_stable(self) -> None:
        """
        规范模式应保持固定结构，适合正式 benchmark 对比。

        :return: None
        """
        expected = (
            "题目：标准题目\n"
            "分类：测试\n"
            "描述：只使用题库描述\n\n"
            "请在当前目录下实现一个可运行的 MVP。\n"
            "完成后请说明启动方式、验证方式和主要取舍。"
        )
        self.assertEqual(expected, main.build_topic_prompt(self.topic, "canonical"))
        self.assertEqual(expected, main.build_topic_prompt(self.topic, "canonical"))

    def test_natural_candidates_are_distinct_and_keep_contract(self) -> None:
        """
        自然候选应结构不同，但都保留 topic 内容和四类交付语义。

        :return: None
        """
        prompts = main._build_natural_topic_prompt_candidates(self.topic)

        self.assertEqual(main._NATURAL_TOPIC_PROMPT_CANDIDATE_COUNT, len(prompts))
        self.assertEqual(len(prompts), len(set(prompts)))
        for prompt in prompts:
            self.assertIn("标准题目", prompt)
            self.assertIn("只使用题库描述", prompt)
            self.assertIn("测试", prompt)
            self.assertTrue(any(
                marker in prompt
                for marker in ("当前工作区", "现有目录", "这个工作区", "当前项目", "手头目录")
            ))
            self.assertTrue(any(
                marker in prompt
                for marker in ("启动命令", "怎么运行", "运行步骤", "使用命令", "跑起来")
            ))
            self.assertTrue(any(
                marker in prompt
                for marker in ("实际验证", "自测", "检查结果", "测试情况", "实际检查")
            ))
            self.assertTrue(any(
                marker in prompt
                for marker in ("取舍", "留到后续", "权衡", "舍弃", "范围是怎样控制")
            ))

    def test_all_seed_categories_map_to_defined_styles(self) -> None:
        """
        题库全部 21 个分类都应命中已定义风格，而不是落入兜底。

        :return: None
        """
        topics_path = Path(__file__).resolve().parents[1] / "topics.md"
        with patch.object(main, "TOPICS_FILE", topics_path):
            categories = {topic["category"] for topic in main.load_seed_topics()}

        self.assertEqual(21, len(categories))
        self.assertNotIn("generic", {
            main._topic_prompt_style(category)
            for category in categories
        })
        self.assertEqual("engineering", main._topic_prompt_style("命令行工具"))
        self.assertEqual("product", main._topic_prompt_style("个人效率 Web 应用"))
        self.assertEqual("data_ai", main._topic_prompt_style("AI 集成应用"))
        self.assertEqual("creative", main._topic_prompt_style("小游戏"))

    def test_topic_content_is_removed_before_fingerprint_comparison(self) -> None:
        """
        不同 topic 套用相同包装时应得到同一个公共措辞指纹。

        :return: None
        """
        left_topic = {
            "title": "标准题目",
            "description": "标准题目需要处理甲数据",
            "category": "命令行工具",
        }
        right_topic = {
            "title": "替代题目",
            "description": "替代题目需要处理乙数据",
            "category": "小游戏",
        }
        left_prompt = "想做标准题目，分类命令行工具。需求：标准题目需要处理甲数据。完成后说明验证。"
        right_prompt = "想做替代题目，分类小游戏。需求：替代题目需要处理乙数据。完成后说明验证。"

        self.assertEqual(
            main._topic_prompt_fingerprint(left_prompt, left_topic),
            main._topic_prompt_fingerprint(right_prompt, right_topic),
        )

    def test_natural_mode_selects_candidate_with_lower_recent_similarity(self) -> None:
        """
        自然模式应避开与近期公共包装完全相同的候选。

        :return: None
        """
        close_prompt = (
            "想做标准题目，分类测试。需求：只使用题库描述。"
            "请在当前工作区完成，最后说明启动、验证和取舍。"
        )
        distant_prompt = (
            "标准题目这件事先按测试场景落地。只使用题库描述。"
            "代码放进现有目录并跑通，收尾列出用法、自测结果和范围权衡。"
        )
        recent = deque([
            main._topic_prompt_fingerprint(close_prompt, self.topic),
        ], maxlen=64)
        with patch.object(
            main,
            "_build_natural_topic_prompt_candidates",
            return_value=[close_prompt, distant_prompt],
        ):
            selected = main.build_topic_prompt(self.topic, "natural", recent)

        self.assertEqual(distant_prompt, selected)

    def test_recent_prompt_history_reads_both_sources_and_caps_window(self) -> None:
        """
        近期窗口应读取普通任务和批次项，并只保留最新 64 条。

        :return: None
        """
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "db.sqlite"
            topics_path = Path(tmp) / "missing-topics.md"
            with (
                patch.object(main, "DB_PATH", db_path),
                patch.object(main, "TOPICS_FILE", topics_path),
            ):
                main.init_db()
                conn = main.get_db()
                try:
                    with conn:
                        conn.execute(
                            "INSERT INTO accounts(name, profile_path) VALUES('main','profiles/main')"
                        )
                        topic_id = int(conn.execute(
                            "INSERT INTO topics(no, title, description, category) "
                            "VALUES(1,'标准题目','只使用题库描述','测试')"
                        ).lastrowid)
                        for index in range(65):
                            conn.execute(
                                "INSERT INTO tasks(topic_no, title, prompt, account_id, topic_id, created_at) "
                                "VALUES(1,'标准题目',?,1,?,?)",
                                (f"普通历史 {index}", topic_id, 1000 + index),
                            )
                        batch_id = int(conn.execute(
                            "INSERT INTO task_batches(account_id, name, created_at) "
                            "VALUES(1,'test batch',2000)"
                        ).lastrowid)
                        conn.execute(
                            "INSERT INTO task_batch_items(batch_id, topic_id, prompt, created_at) "
                            "VALUES(?,?,?,?)",
                            (batch_id, topic_id, "最新批次历史", 2001),
                        )
                    fingerprints = main._load_recent_topic_prompt_fingerprints(conn)
                finally:
                    conn.close()

        self.assertEqual(64, len(fingerprints))
        self.assertEqual(64, fingerprints.maxlen)
        self.assertEqual(
            main._topic_prompt_fingerprint("最新批次历史", self.topic),
            fingerprints[-1],
        )

    def test_batch_loads_history_once_and_extends_it_per_item(self) -> None:
        """
        批量自然模式应只查一次历史，并让后续项比较本批次已选 prompt。

        :return: None
        """
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "db.sqlite"
            topics_path = Path(tmp) / "missing-topics.md"
            scheduler = Mock()
            with (
                patch.object(main, "DB_PATH", db_path),
                patch.object(main, "TOPICS_FILE", topics_path),
                patch.object(main, "scheduler", scheduler),
            ):
                main.init_db()
                conn = main.get_db()
                try:
                    with conn:
                        conn.execute(
                            "INSERT INTO accounts(name, profile_path) VALUES('main','profiles/main')"
                        )
                        topic_ids = [int(conn.execute(
                            "INSERT INTO topics(no, title, description, category) VALUES(?,?,?,?)",
                            (index, f"题目 {index}", f"描述 {index}", "测试"),
                        ).lastrowid) for index in range(1, 4)]
                finally:
                    conn.close()
                history_sizes: list[int] = []

                def resolve_prompt(
                    topic: dict,
                    prompt_override: str | None,
                    mode: main.TopicPromptMode,
                    recent_fingerprints: deque[frozenset[str]] | None,
                ) -> str:
                    """
                    记录每个批次项生成时可见的历史窗口长度。

                    :param topic: 当前 topic
                    :param prompt_override: 自定义 prompt 覆盖
                    :param mode: 默认 prompt 模式
                    :param recent_fingerprints: 当前历史指纹窗口
                    :return: 可持久化的测试 prompt
                    """
                    history_sizes.append(len(recent_fingerprints or ()))
                    return f"批次 prompt {topic['id']}"

                with (
                    patch.object(
                        main,
                        "_load_recent_topic_prompt_fingerprints",
                        return_value=deque(maxlen=64),
                    ) as loader,
                    patch.object(main, "_resolve_topic_prompt", side_effect=resolve_prompt),
                ):
                    result = main.create_task_batch(main.BatchIn(
                        account_id=1,
                        topic_ids=topic_ids,
                    ))
                conn = main.get_db()
                try:
                    item_count = conn.execute(
                        "SELECT COUNT(*) AS n FROM task_batch_items WHERE batch_id=?",
                        (result["id"],),
                    ).fetchone()["n"]
                finally:
                    conn.close()

        loader.assert_called_once()
        self.assertEqual([0, 1, 2], history_sizes)
        self.assertEqual(3, item_count)
        scheduler.submit_batch.assert_called_once_with(result["id"])

    def test_prompt_mode_defaults_and_validation(self) -> None:
        """
        三个请求 DTO 的默认模式应匹配各自运行场景，并拒绝非法值。

        :return: None
        """
        self.assertEqual("natural", main.TaskIn(topic_no=1, account_id=1).prompt_mode)
        self.assertEqual(
            "natural",
            main.BatchIn(account_id=1, topic_ids=[1]).prompt_mode,
        )
        self.assertEqual(
            "canonical",
            main.CaptureRunIn(account_id=1, topic_id=1).prompt_mode,
        )
        with self.assertRaises(ValidationError):
            main.TaskIn(topic_no=1, account_id=1, prompt_mode="invalid")

    def test_prompt_override_bypasses_mode_renderer(self) -> None:
        """
        自定义 prompt 必须原样优先，不能再进入自然模板处理。

        :return: None
        """
        with patch.object(main, "build_topic_prompt") as builder:
            prompt = main._resolve_topic_prompt(
                self.topic,
                "完全自定义的 prompt",
                "natural",
            )
        self.assertEqual("完全自定义的 prompt", prompt)
        builder.assert_not_called()
        self.assertFalse(main._should_load_topic_prompt_history(
            "完全自定义的 prompt",
            "natural",
        ))
        self.assertFalse(main._should_load_topic_prompt_history(None, "canonical"))
        self.assertTrue(main._should_load_topic_prompt_history(None, "natural"))


class ClaudeCodeVersionTests(unittest.TestCase):
    """验证 Claude Code 默认版本、页面覆盖和各类 worker 的版本传递。"""

    def setUp(self) -> None:
        """
        准备独立 SQLite、profile 和 worker 目录。

        :return: None
        """
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.originals = (
            main.DB_PATH,
            main.BENCH_DATA,
            main.HOST_BENCH_DATA,
            main.PROFILES_DIR,
            main.FLOWS_DIR,
            main.WORKSPACES_DIR,
            main.CA_DIR,
            main.TOPICS_FILE,
        )
        main.DB_PATH = self.base / "db.sqlite"
        main.BENCH_DATA = self.base
        main.HOST_BENCH_DATA = self.base
        main.PROFILES_DIR = self.base / "profiles"
        main.FLOWS_DIR = self.base / "flows"
        main.WORKSPACES_DIR = self.base / "workspaces"
        main.CA_DIR = self.base / "ca"
        main.TOPICS_FILE = self.base / "missing-topics.md"
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        (profile_dir / ".credentials.json").write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "test-access",
                    "refreshToken": "test-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        """
        恢复模块全局目录并清理临时数据。

        :return: None
        """
        (
            main.DB_PATH,
            main.BENCH_DATA,
            main.HOST_BENCH_DATA,
            main.PROFILES_DIR,
            main.FLOWS_DIR,
            main.WORKSPACES_DIR,
            main.CA_DIR,
            main.TOPICS_FILE,
        ) = self.originals
        self.tmp.cleanup()

    def _docker_client(self) -> tuple[Mock, list[tuple[str, dict]]]:
        """
        创建记录容器启动参数的 Docker client mock。

        :return: Docker client mock 和 `(image, kwargs)` 调用列表
        """
        client = Mock()
        calls: list[tuple[str, dict]] = []

        def run(image: str, **kwargs) -> Mock:
            """
            记录容器创建参数并返回带稳定 ID 的 mock。

            :param image: 容器镜像名
            :param kwargs: docker SDK 创建参数
            :return: 带 ID 的容器 mock
            """
            container = Mock()
            container.id = f"container-{len(calls) + 1}"
            calls.append((image, kwargs))
            return container

        client.containers.run.side_effect = run
        return client, calls

    def _assert_worker_version(
        self,
        calls: list[tuple[str, dict]],
        label: str,
        expected_version: str = "2.1.260",
    ) -> None:
        """
        断言指定路径创建的 worker 显式携带目标版本。

        :param calls: Docker client mock 记录的容器创建参数
        :param label: 失败时标识当前 worker 路径
        :param expected_version: 期望传入 worker 的 Claude Code 版本
        :return: None
        """
        worker_calls = [kwargs for image, kwargs in calls if image == main.WORKER_IMAGE]
        self.assertEqual(1, len(worker_calls), label)
        self.assertEqual(
            expected_version,
            worker_calls[0]["environment"]["CLAUDE_CODE_VERSION"],
            label,
        )

    def _assert_worker_effort(
        self,
        calls: list[tuple[str, dict]],
        label: str,
        expected_effort: str,
        expected_profile_effort: str | None = None,
    ) -> None:
        """
        断言指定路径创建的 worker 显式携带目标思考预算。

        :param calls: Docker client mock 记录的容器创建参数
        :param label: 失败时标识当前 worker 路径
        :param expected_effort: 期望传入 worker 的 run 思考预算
        :param expected_profile_effort: 期望写回 profile 的兜底预算；None 表示不校验
        :return: None
        """
        worker_calls = [kwargs for image, kwargs in calls if image == main.WORKER_IMAGE]
        self.assertEqual(1, len(worker_calls), label)
        environment = worker_calls[0]["environment"]
        self.assertEqual(
            expected_effort,
            environment["CLAUDE_CODE_EFFORT_LEVEL"],
            label,
        )
        if expected_profile_effort is not None:
            self.assertEqual(
                expected_profile_effort,
                environment["PROFILE_CLAUDE_CODE_EFFORT_LEVEL"],
                label,
            )

    def test_runtime_version_setting_override_and_reset(self) -> None:
        """
        无覆盖、保存覆盖和清空覆盖应按既定优先级返回版本。

        :return: None
        """
        self.assertEqual("2.1.260", main.CLAUDE_CODE_VERSION)
        self.assertEqual({
            "configured_version": None,
            "env_default_version": "2.1.260",
            "effective_version": "2.1.260",
        }, main.get_claude_code_version())

        overridden = main.update_claude_code_version(
            main.ClaudeCodeVersionIn(claude_code_version="2.1.220")
        )
        self.assertEqual("2.1.220", overridden["configured_version"])
        self.assertEqual("2.1.260", overridden["env_default_version"])
        self.assertEqual("2.1.220", overridden["effective_version"])

        reset = main.update_claude_code_version(
            main.ClaudeCodeVersionIn(claude_code_version=None)
        )
        self.assertIsNone(reset["configured_version"])
        self.assertEqual("2.1.260", reset["env_default_version"])
        self.assertEqual("2.1.260", reset["effective_version"])

    def test_run_workers_use_snapshot_and_ephemeral_workers_use_effective_version(self) -> None:
        """
        run/continue worker 应使用身份快照，临时 worker 应使用启动时有效配置。

        :return: None
        """
        account = {
            "name": "main",
            "enabled": 1,
            "deleted_at": None,
            "upstream_socks5_host": "proxy.example.com",
            "upstream_socks5_port": 1080,
        }
        with (
            patch.object(main, "effective_claude_code_version", return_value="2.1.257"),
            patch.object(main, "effective_runtime_effort", return_value="medium"),
            patch.object(main, "_wait_sidecar_ready"),
        ):
            for capture_full_http, label, effort_level in (
                (False, "task", "high"),
                (True, "capture", "low"),
            ):
                with self.subTest(worker=label):
                    client, calls = self._docker_client()
                    runner = object.__new__(main.Runner)
                    runner.client = client
                    runner.start_run(
                        f"{label}-run",
                        account,
                        {
                            "id": 1,
                            "prompt": "test prompt",
                            "timeout_sec": 60,
                            "capture_full_http": capture_full_http,
                            "claude_code_version": "2.1.260",
                            "claude_effort_level": effort_level,
                        },
                    )
                    self._assert_worker_version(calls, label)
                    self._assert_worker_effort(
                        calls,
                        label,
                        effort_level,
                        main.CLAUDE_CODE_EFFORT_LEVEL,
                    )

            client, calls = self._docker_client()
            runner = object.__new__(main.Runner)
            runner.client = client
            runner.start_continue(
                "continue-session",
                {
                    "id": "continue-run",
                    "run_kind": "capture",
                    "flows_dir": str(main.FLOWS_DIR / "main" / "1" / "continue-run"),
                    "claude_code_version": "2.1.260",
                    "claude_effort_level": "xhigh",
                },
                account,
                "claude-session",
            )
            self._assert_worker_version(calls, "continue")
            self._assert_worker_effort(calls, "continue", "xhigh")

            client, calls = self._docker_client()
            runner = object.__new__(main.Runner)
            runner.client = client
            with (
                patch.object(runner, "cleanup"),
                patch.object(runner, "_exec_oauth_refresh_probe", return_value={"skipped": True}),
                patch.object(runner, "_exec_quota_probe", return_value={}),
            ):
                runner.query_quota(account)
            self._assert_worker_version(calls, "quota", "2.1.257")
            self._assert_worker_effort(
                calls,
                "quota",
                main.CLAUDE_CODE_EFFORT_LEVEL,
            )

            client, calls = self._docker_client()
            runner = object.__new__(main.Runner)
            runner.client = client
            with (
                patch.object(runner, "cleanup"),
                patch.object(runner, "_exec_oauth_refresh_probe", return_value={"refreshed": True}),
            ):
                self.assertTrue(runner.refresh_account_oauth_token(account))
            self._assert_worker_version(calls, "oauth-refresh", "2.1.257")
            self._assert_worker_effort(
                calls,
                "oauth-refresh",
                main.CLAUDE_CODE_EFFORT_LEVEL,
            )

            client, calls = self._docker_client()
            login_manager = main.LoginManager(client)
            login_manager.start("login-account", {}, timezone="Asia/Singapore")
            self._assert_worker_version(calls, "login", "2.1.257")

    def test_run_creation_paths_persist_and_submit_runtime_identity_snapshot(self) -> None:
        """
        普通、抓包、批次和养号 run 都应保存并提交创建时的运行身份。

        :return: None
        """
        conn = main.get_db()
        try:
            with conn:
                account_id = int(conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled) "
                    "VALUES('snapshot','profiles/snapshot',7,1)"
                ).lastrowid)
                topic_id = int(conn.execute(
                    "INSERT INTO topics(no, title, description, category) "
                    "VALUES(1,'版本快照','验证版本快照','测试')"
                ).lastrowid)
                task_id = int(conn.execute(
                    "INSERT INTO tasks(topic_no, title, prompt, account_id, topic_id) "
                    "VALUES(1,'普通任务','普通 prompt',?,?)",
                    (account_id, topic_id),
                ).lastrowid)
                batch_id = int(conn.execute(
                    "INSERT INTO task_batches(account_id, name) VALUES(?,'版本批次')",
                    (account_id,),
                ).lastrowid)
                conn.execute(
                    "INSERT INTO task_batch_items(batch_id, topic_id, prompt) "
                    "VALUES(?,?,'批次 prompt')",
                    (batch_id, topic_id),
                )
        finally:
            conn.close()

        api_scheduler = Mock()
        with (
            patch.object(main, "effective_claude_code_version", return_value="2.1.260"),
            patch.object(main, "effective_runtime_effort", return_value="high"),
            patch.object(main, "scheduler", api_scheduler),
        ):
            normal_result = main.run_task(task_id)
            capture_result = main.start_capture_run(main.CaptureRunIn(
                account_id=account_id,
                topic_id=topic_id,
                prompt="抓包 prompt",
                effort_level="low",
            ))

            batch_scheduler = main.Scheduler(Mock())
            batch_scheduler.submit = Mock()
            batch_scheduler._wait_all_runs_finished = Mock()
            batch_scheduler._finish_batch_when_done = Mock()
            batch_scheduler._execute_batch(batch_id)

            conn = main.get_db()
            try:
                account = dict(conn.execute(
                    "SELECT * FROM accounts WHERE id=?",
                    (account_id,),
                ).fetchone())
                topic = dict(conn.execute(
                    "SELECT * FROM topics WHERE id=?",
                    (topic_id,),
                ).fetchone())
            finally:
                conn.close()
            warmup_created = main.WarmupScheduler(Mock())._create_task_and_run(
                account,
                topic,
                "养号 prompt",
            )

        self.assertIsNotNone(warmup_created)
        warmup_run_id, _warmup_task_id, warmup_version, warmup_effort = warmup_created
        self.assertEqual("2.1.260", warmup_version)
        self.assertEqual("high", warmup_effort)
        normal_run_id = normal_result["run_ids"][0]
        capture_run_id = capture_result["run_id"]
        batch_run_id = batch_scheduler.submit.call_args.args[0]
        run_ids = [normal_run_id, capture_run_id, batch_run_id, warmup_run_id]
        conn = main.get_db()
        try:
            rows = conn.execute(
                f"SELECT id, claude_code_version, claude_effort_level "
                f"FROM runs WHERE id IN ({','.join('?' for _ in run_ids)})",
                run_ids,
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(
            {run_id: "2.1.260" for run_id in run_ids},
            {row["id"]: row["claude_code_version"] for row in rows},
        )
        self.assertEqual(
            {
                normal_run_id: "high",
                capture_run_id: "low",
                batch_run_id: "high",
                warmup_run_id: "high",
            },
            {row["id"]: row["claude_effort_level"] for row in rows},
        )
        api_payloads = {
            call.args[0]: call.args[2]
            for call in api_scheduler.submit.call_args_list
        }
        self.assertEqual("2.1.260", api_payloads[normal_run_id]["claude_code_version"])
        self.assertEqual("2.1.260", api_payloads[capture_run_id]["claude_code_version"])
        self.assertEqual("high", api_payloads[normal_run_id]["claude_effort_level"])
        self.assertEqual("low", api_payloads[capture_run_id]["claude_effort_level"])
        self.assertEqual(
            "2.1.260",
            batch_scheduler.submit.call_args.args[2]["claude_code_version"],
        )
        self.assertEqual(
            "high",
            batch_scheduler.submit.call_args.args[2]["claude_effort_level"],
        )
        self.assertEqual("2.1.260", capture_result["claude_code_version"])
        self.assertEqual("low", capture_result["claude_effort_level"])
        self.assertEqual(
            "low",
            main.get_capture(capture_run_id)["claude_effort_level"],
        )

    def test_capture_effort_defaults_to_env_and_rejects_invalid_value(self) -> None:
        """
        抓包留空应忽略页面覆盖并回退 `.env`，非法值不得产生新记录。

        :return: None
        """
        conn = main.get_db()
        try:
            with conn:
                account_id = int(conn.execute(
                    "INSERT INTO accounts(name, profile_path) "
                    "VALUES('capture-effort','profiles/capture-effort')"
                ).lastrowid)
                topic_id = int(conn.execute(
                    "INSERT INTO topics(no, title, description, category) "
                    "VALUES(1,'抓包预算','验证抓包预算','测试')"
                ).lastrowid)
        finally:
            conn.close()
        main.save_runtime_effort_setting("low")
        test_scheduler = Mock()
        with (
            patch.object(main, "scheduler", test_scheduler),
            patch.object(main, "CLAUDE_CODE_EFFORT_LEVEL", "max"),
        ):
            result = main.start_capture_run(main.CaptureRunIn(
                account_id=account_id,
                topic_id=topic_id,
                prompt="默认预算",
            ))
            with self.assertRaises(main.HTTPException) as raised:
                main.start_capture_run(main.CaptureRunIn(
                    account_id=account_id,
                    topic_id=topic_id,
                    prompt="非法预算",
                    effort_level="extreme",
                ))

        self.assertEqual(400, raised.exception.status_code)
        self.assertEqual("max", result["claude_effort_level"])
        self.assertEqual(
            "max",
            test_scheduler.submit.call_args.args[2]["claude_effort_level"],
        )
        conn = main.get_db()
        try:
            run = conn.execute(
                "SELECT claude_effort_level FROM runs WHERE id=?",
                (result["run_id"],),
            ).fetchone()
            task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            run_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual("max", run["claude_effort_level"])
        self.assertEqual(1, task_count)
        self.assertEqual(1, run_count)
        self.assertEqual(1, test_scheduler.submit.call_count)

    def test_historical_run_identity_is_backfilled_only_once(self) -> None:
        """
        历史 NULL 快照首次继续时应补写，之后不再受全局配置变化影响。

        :return: None
        """
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path) VALUES('legacy','profiles/legacy')"
                )
                task_id = int(conn.execute(
                    "INSERT INTO tasks(topic_no, title, prompt, account_id) "
                    "VALUES(1,'历史任务','历史 prompt',1)"
                ).lastrowid)
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status) "
                    "VALUES('legacy-run',?,1,'success')",
                    (task_id,),
                )
        finally:
            conn.close()

        run = {
            "id": "legacy-run",
            "claude_code_version": None,
            "claude_effort_level": None,
        }
        with patch.object(main, "effective_claude_code_version", return_value="2.1.260"):
            self.assertEqual("2.1.260", main._ensure_run_claude_code_version(run))
        run["claude_code_version"] = None
        with patch.object(main, "effective_claude_code_version", return_value="2.1.257"):
            self.assertEqual("2.1.260", main._ensure_run_claude_code_version(run))
        with patch.object(main, "CLAUDE_CODE_EFFORT_LEVEL", "high"):
            self.assertEqual("high", main._ensure_run_claude_effort_level(run))
        run["claude_effort_level"] = None
        with patch.object(main, "CLAUDE_CODE_EFFORT_LEVEL", "low"):
            self.assertEqual("high", main._ensure_run_claude_effort_level(run))

        conn = main.get_db()
        try:
            stored = conn.execute(
                "SELECT claude_code_version, claude_effort_level "
                "FROM runs WHERE id='legacy-run'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual("2.1.260", stored["claude_code_version"])
        self.assertEqual("high", stored["claude_effort_level"])

    def test_continue_endpoint_passes_backfilled_effort_snapshot(self) -> None:
        """
        继续接口应先补写历史预算，再把同一快照交给 continue manager。

        :return: None
        """
        conn = main.get_db()
        try:
            with conn:
                account_id = int(conn.execute(
                    "INSERT INTO accounts(name, profile_path) "
                    "VALUES('continue-effort','profiles/continue-effort')"
                ).lastrowid)
                task_id = int(conn.execute(
                    "INSERT INTO tasks(topic_no, title, prompt, account_id) "
                    "VALUES(1,'继续任务','继续 prompt',?)",
                    (account_id,),
                ).lastrowid)
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status, claude_code_version) "
                    "VALUES('continue-effort-run',?,?,'success','2.1.260')",
                    (task_id, account_id),
                )
        finally:
            conn.close()

        session = Mock()
        session.sid = "continue-sid"
        session.run_id = "continue-effort-run"
        session.session_id = "claude-session"
        manager = Mock()
        manager.start.return_value = session
        with (
            patch.object(main, "continue_manager", manager),
            patch.object(main, "CLAUDE_CODE_EFFORT_LEVEL", "xhigh"),
        ):
            result = main.continue_run_start("continue-effort-run")

        passed_run = manager.start.call_args.args[0]
        self.assertEqual("xhigh", passed_run["claude_effort_level"])
        self.assertEqual("continue-sid", result["session_id"])
        conn = main.get_db()
        try:
            stored = conn.execute(
                "SELECT claude_effort_level FROM runs WHERE id='continue-effort-run'"
            ).fetchone()["claude_effort_level"]
        finally:
            conn.close()
        self.assertEqual("xhigh", stored)

    def test_new_run_after_setting_change_uses_new_snapshot(self) -> None:
        """
        同一任务再次运行时应使用新设置，同时保留前一个 run 的旧快照。

        :return: None
        """
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path) VALUES('rerun','profiles/rerun')"
                )
                task_id = int(conn.execute(
                    "INSERT INTO tasks(topic_no, title, prompt, account_id) "
                    "VALUES(1,'重跑任务','重跑 prompt',1)"
                ).lastrowid)
        finally:
            conn.close()

        test_scheduler = Mock()
        with patch.object(main, "scheduler", test_scheduler):
            with (
                patch.object(main, "effective_claude_code_version", return_value="2.1.260"),
                patch.object(main, "effective_runtime_effort", return_value="high"),
            ):
                first_run_id = main.run_task(task_id)["run_ids"][0]
            with (
                patch.object(main, "effective_claude_code_version", return_value="2.1.257"),
                patch.object(main, "effective_runtime_effort", return_value="low"),
            ):
                second_run_id = main.run_task(task_id)["run_ids"][0]

        conn = main.get_db()
        try:
            rows = conn.execute(
                "SELECT id, claude_code_version, claude_effort_level "
                "FROM runs WHERE id IN (?,?)",
                (first_run_id, second_run_id),
            ).fetchall()
        finally:
            conn.close()
        versions = {row["id"]: row["claude_code_version"] for row in rows}
        self.assertEqual("2.1.260", versions[first_run_id])
        self.assertEqual("2.1.257", versions[second_run_id])
        efforts = {row["id"]: row["claude_effort_level"] for row in rows}
        self.assertEqual("high", efforts[first_run_id])
        self.assertEqual("low", efforts[second_run_id])

    def test_old_database_upgrade_adds_run_identity_snapshot_columns(self) -> None:
        """
        旧 runs 表重复升级后应幂等补齐版本和思考预算快照列。

        :return: None
        """
        old_db_path = self.base / "old-runs.sqlite"
        conn = sqlite3.connect(old_db_path)
        conn.execute(
            "CREATE TABLE runs(id TEXT PRIMARY KEY, task_id INTEGER NOT NULL, "
            "account_id INTEGER NOT NULL, status TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, "
            "updated_at REAL)"
        )
        conn.execute(
            "INSERT INTO runs(id, task_id, account_id, status) "
            "VALUES('preserved-run',7,9,'success')"
        )
        conn.execute(
            "INSERT INTO app_settings(key, value) "
            "VALUES('claude_effort_level','low')"
        )
        conn.commit()
        conn.close()

        with patch.object(main, "DB_PATH", old_db_path):
            main.init_db()
            main.init_db()
        conn = sqlite3.connect(old_db_path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
            preserved_run = conn.execute(
                "SELECT id, task_id, account_id, status, claude_effort_level "
                "FROM runs WHERE id='preserved-run'"
            ).fetchone()
            preserved_setting = conn.execute(
                "SELECT value FROM app_settings WHERE key='claude_effort_level'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIn("claude_code_version", columns)
        self.assertIn("claude_effort_level", columns)
        self.assertEqual(
            ("preserved-run", 7, 9, "success", None),
            preserved_run,
        )
        self.assertEqual(("low",), preserved_setting)

    def test_capture_webui_exposes_independent_effort_selector_and_details(self) -> None:
        """
        抓包表单与详情页必须提交并展示独立思考预算字段。

        :return: None
        """
        webui_dir = Path(__file__).resolve().parents[1] / "webui"
        index_html = (webui_dir / "index.html").read_text(encoding="utf-8")
        app_js = (webui_dir / "app.js").read_text(encoding="utf-8")
        style_css = (webui_dir / "style.css").read_text(encoding="utf-8")
        self.assertEqual(2, index_html.count('<select name="effort_level"></select>'))
        self.assertIn("默认 .env (", app_js)
        self.assertIn("effort_level: (fd.get('effort_level')", app_js)
        self.assertIn('data-stat-key="claude_effort_level"', app_js)
        capture_stats = re.search(
            r"const captureStats = `(?P<body>.*?)`;",
            app_js,
            re.DOTALL,
        )
        self.assertIsNotNone(capture_stats)
        self.assertIn("capture.claude_effort_level", capture_stats.group("body"))
        unavailable_branch = re.search(
            r"if \(capture\.available === false\) \{\s*return `(?P<body>.*?)`;",
            app_js,
            re.DOTALL,
        )
        self.assertIsNotNone(unavailable_branch)
        self.assertIn("${captureStats}", unavailable_branch.group("body"))
        self.assertIn(
            ".capture-panel > .row { flex-wrap: wrap; align-items: stretch; }",
            style_css,
        )

    def test_entrypoint_keeps_strict_version_fallback_and_install(self) -> None:
        """
        entrypoint 的 shell/Node fallback 必须一致，非法或安装不匹配仍失败。

        :return: None
        """
        entrypoint = (
            Path(__file__).resolve().parents[1] / "images" / "worker" / "entrypoint.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'CLAUDE_CODE_VERSION="${CLAUDE_CODE_VERSION:-2.1.260}"',
            entrypoint,
        )
        self.assertIn("process.argv[3] || '2.1.260'", entrypoint)
        ensure_match = re.search(
            r"ensure_claude_code_version\(\) \{(?P<body>.*?)\n\}",
            entrypoint,
            re.DOTALL,
        )
        self.assertIsNotNone(ensure_match)
        ensure_body = ensure_match.group("body")
        self.assertIn('npm install -g "@anthropic-ai/claude-code@$desired"', ensure_body)
        self.assertIn("Invalid CLAUDE_CODE_VERSION", ensure_body)
        self.assertIn("Claude Code version mismatch after install", ensure_body)

    def test_first_run_gates_include_workspace_trust_without_overwriting_profile(self) -> None:
        """
        补齐目录信任时应保留身份字段、其他项目和 `/workspace` 既有状态。

        :return: None
        """
        profile_dir = main.PROFILES_DIR / "main"
        top_config_path = profile_dir / ".claude.json"
        top_config_path.write_text(
            json.dumps({
                "oauthAccount": {"accountUuid": "account-uuid"},
                "projects": {
                    "/workspace": {
                        "allowedTools": ["Bash"],
                        "hasTrustDialogAccepted": False,
                    },
                    "/another-project": {"hasTrustDialogAccepted": False},
                },
            }),
            encoding="utf-8",
        )

        main._persist_default_claude_top_config(profile_dir)

        persisted = json.loads(top_config_path.read_text(encoding="utf-8"))
        self.assertEqual("account-uuid", persisted["oauthAccount"]["accountUuid"])
        self.assertEqual(["Bash"], persisted["projects"]["/workspace"]["allowedTools"])
        self.assertTrue(persisted["projects"]["/workspace"]["hasTrustDialogAccepted"])
        self.assertFalse(
            persisted["projects"]["/another-project"]["hasTrustDialogAccepted"]
        )
        self.assertTrue(persisted["hasCompletedOnboarding"])
        self.assertTrue(persisted["bypassPermissionsModeAccepted"])

    def test_entrypoint_has_workspace_trust_gate_fallback(self) -> None:
        """
        profile 预置未生效时，entrypoint 仍应识别并通过目录信任菜单。

        :return: None
        """
        entrypoint = (
            Path(__file__).resolve().parents[1] / "images" / "worker" / "entrypoint.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('"hasTrustDialogAccepted": true', entrypoint)
        self.assertIn(
            "Quick safety check: Is this a project you created or one you trust?",
            entrypoint,
        )
        self.assertIn('tmux send-keys -t "$SESSION" Down Enter', entrypoint)

    def test_worker_image_generates_all_fingerprint_locales(self) -> None:
        """
        worker 镜像应生成账号指纹池可能选中的全部 locale。

        :return: None
        """
        dockerfile = (
            Path(__file__).resolve().parents[1] / "images" / "worker" / "Dockerfile"
        ).read_text(encoding="utf-8")
        self.assertRegex(dockerfile, r"ca-certificates\s+locales")
        self.assertIn("locale-gen", dockerfile)
        for locale_name in main._LANG_POOL:
            self.assertIn(f"{locale_name} UTF-8", dockerfile)

    def test_continue_without_session_reports_actionable_error(self) -> None:
        """
        首次启动失败且无 JSONL 时，应明确提示重新运行而不是暴露内部文件名。

        :return: None
        """
        manager = main.ContinueManager(Mock())

        with self.assertRaisesRegex(ValueError, "没有可恢复记录.*重新运行任务"):
            manager.start({"id": "missing-session"}, {"id": 1})


class ScheduledWarmupTests(unittest.TestCase):
    """验证养号迁移、匹配、凭据同步和调度状态。"""

    def setUp(self) -> None:
        """为每个测试创建独立 SQLite 和 profile 目录。"""
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.originals = (
            main.DB_PATH,
            main.PROFILES_DIR,
            main.TOPICS_FILE,
        )
        self.runtime_originals = (
            main.cc2api_client,
            main.runner,
            main.login_manager,
            main.continue_manager,
            main.warmup_scheduler,
        )
        main.DB_PATH = self.base / "db.sqlite"
        main.PROFILES_DIR = self.base / "profiles"
        main.TOPICS_FILE = self.base / "missing-topics.md"

    def tearDown(self) -> None:
        """恢复模块全局路径并清理临时目录。"""
        main.DB_PATH, main.PROFILES_DIR, main.TOPICS_FILE = self.originals
        (
            main.cc2api_client,
            main.runner,
            main.login_manager,
            main.continue_manager,
            main.warmup_scheduler,
        ) = self.runtime_originals
        self.tmp.cleanup()

    def _oauth_refresh_node_scripts(self) -> list[tuple[str, str]]:
        """
        读取两个生产刷新入口实际执行的 Node 脚本。

        :return: `(入口名, Node 源码)` 列表
        """
        runner = object.__new__(main.Runner)
        runner.client = Mock()
        runner.client.api.exec_create.return_value = {"Id": "oauth-exec"}
        runner.client.api.exec_start.return_value = b'{"skipped":true}'
        runner.client.api.exec_inspect.return_value = {"ExitCode": 0}
        runner._exec_oauth_refresh_probe("worker-id")
        shell_script = runner.client.api.exec_create.call_args.args[1][2]
        orchestrator_match = re.search(
            r"node - <<'JS'\n(?P<script>.*?)\nJS\n?$",
            shell_script,
            re.DOTALL,
        )
        self.assertIsNotNone(orchestrator_match)

        entrypoint = (
            Path(__file__).resolve().parents[1] / "images" / "worker" / "entrypoint.sh"
        ).read_text(encoding="utf-8")
        worker_match = re.search(
            r"force_refresh_profile_credentials_unlocked\(\) \{.*?"
            r"node - \"\$credentials_path\" \"\$CLAUDE_CODE_VERSION\" \"\$reason\" <<'JS'\n"
            r"(?P<script>.*?)\nJS\n",
            entrypoint,
            re.DOTALL,
        )
        self.assertIsNotNone(worker_match)
        return [
            ("orchestrator", orchestrator_match.group("script")),
            ("worker", worker_match.group("script")),
        ]

    def _run_oauth_refresh_node_script(
        self,
        entrypoint: str,
        script: str,
        credentials: dict,
        response_body: dict,
        response_status: int = 200,
        retry_after: str = "",
    ) -> tuple[subprocess.CompletedProcess[str], dict, dict]:
        """
        用本地伪造 fetch 执行生产 Node 刷新脚本。

        :param entrypoint: `orchestrator` 或 `worker`
        :param script: 待执行的生产 Node 源码
        :param credentials: 初始 `.credentials.json`
        :param response_body: token endpoint JSON 响应
        :param response_status: HTTP 状态码
        :param retry_after: 可选 Retry-After 响应头
        :return: 子进程结果、捕获到的请求体和执行后的凭据
        """
        case_dir = self.base / f"oauth-node-{entrypoint}-{time.time_ns()}"
        home_dir = case_dir / "home"
        credentials_path = home_dir / ".claude" / ".credentials.json"
        credentials_path.parent.mkdir(parents=True)
        credentials_path.write_text(
            json.dumps(credentials, ensure_ascii=False),
            encoding="utf-8",
        )
        capture_path = case_dir / "request.json"
        preload_path = case_dir / "preload.js"
        preload_path.write_text(
            """
const fs = require('fs');
global.fetch = async (_url, options) => {
  fs.writeFileSync(process.env.OAUTH_TEST_CAPTURE_PATH, options.body, 'utf8');
  const status = Number(process.env.OAUTH_TEST_RESPONSE_STATUS || '200');
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name) => name.toLowerCase() === 'retry-after'
        ? (process.env.OAUTH_TEST_RETRY_AFTER || '')
        : null,
    },
    text: async () => process.env.OAUTH_TEST_RESPONSE_BODY,
  };
};
""".strip(),
            encoding="utf-8",
        )
        env = dict(os.environ)
        env.update({
            "HOME": str(home_dir),
            "OAUTH_TEST_CAPTURE_PATH": str(capture_path),
            "OAUTH_TEST_RESPONSE_STATUS": str(response_status),
            "OAUTH_TEST_RETRY_AFTER": retry_after,
            "OAUTH_TEST_RESPONSE_BODY": json.dumps(response_body, ensure_ascii=False),
        })
        command = ["node", "--require", str(preload_path), "-"]
        if entrypoint == "worker":
            command.extend([str(credentials_path), "2.1.257", "test"])
        completed = subprocess.run(
            command,
            input=script,
            text=True,
            capture_output=True,
            env=env,
            timeout=10,
            check=False,
        )
        request_body = (
            json.loads(capture_path.read_text(encoding="utf-8"))
            if capture_path.exists()
            else {}
        )
        updated_credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
        return completed, request_body, updated_credentials

    def _run_queued_warmup_with_second_sync_error(
        self,
        sync_error: Exception,
    ) -> tuple[dict, dict, float, Mock, Mock]:
        """
        创建养号 run，并让 worker 启动前的第二次凭据同步失败。

        :param sync_error: 第二次 cc2api resolve 抛出的异常
        :return: run、账号、失败前时间、runner mock 和 cc2api client mock
        """
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        (profile_dir / ".credentials.json").write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "old-access",
                    "refreshToken": "old-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled, "
                    "warmup_next_run_at) VALUES('main','profiles/main',7,1,?)",
                    (time.time() - 1,),
                )
                conn.execute(
                    "INSERT INTO topics(no, title, description, category) "
                    "VALUES(1,'标准题目','只使用题库描述','测试')"
                )
        finally:
            conn.close()
        client = Mock()
        client.resolve_credentials.side_effect = [
            {
                "account_id": 7,
                "access_token": "prepared-access",
                "refresh_token": "prepared-refresh",
                "expires_at": int(time.time() * 1000) + 3600000,
            },
            sync_error,
        ]
        main.cc2api_client = client
        submitter = Mock()
        warmup = main.WarmupScheduler(submitter)
        result = warmup.trigger_account(1, require_due=True)
        self.assertTrue(result["started"])
        run_id, account, task = submitter.submit.call_args.args

        fake_runner = Mock()
        main.warmup_scheduler = warmup
        before = time.time()
        main.Scheduler(fake_runner)._execute(run_id, account, task)

        conn = main.get_db()
        try:
            run = dict(conn.execute(
                "SELECT status, error FROM runs WHERE id=?",
                (run_id,),
            ).fetchone())
            account_state = dict(conn.execute(
                "SELECT warmup_enabled, warmup_last_status, warmup_last_error, "
                "warmup_next_run_at FROM accounts WHERE id=1"
            ).fetchone())
        finally:
            conn.close()
        return run, account_state, before, fake_runner, client

    def _prepare_syncable_unbound_account(self) -> Mock:
        """
        创建可执行首次 cc2api 同步的未绑定账号和脱敏客户端替身。

        :return: 已配置 list/resolve 响应的 cc2api client mock
        """
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        (profile_dir / ".credentials.json").write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "bench-access",
                    "refreshToken": "bench-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )
        (profile_dir / ".claude.json").write_text(
            json.dumps({
                "oauthAccount": {
                    "emailAddress": "main@example.test",
                    "accountUuid": "uuid-main",
                    "organizationUuid": "org-main",
                }
            }),
            encoding="utf-8",
        )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path) VALUES('main','profiles/main')"
                )
        finally:
            conn.close()
        client = Mock()
        client.list_accounts.return_value = [{
            "id": 7,
            "name": "existing",
            "email": "main@example.test",
            "status": "active",
            "auth_type": "oauth",
            "account_uuid": "uuid-main",
        }]
        client.resolve_credentials.return_value = {
            "account_id": 7,
            "access_token": "cc2-access",
            "refresh_token": "cc2-refresh",
            "expires_at": int(time.time() * 1000) + 3600000,
        }
        main.cc2api_client = client
        main.login_manager = None
        main.continue_manager = None
        return client

    def test_old_database_upgrade_creates_binding_index_after_column(self) -> None:
        """旧 accounts 表应先补绑定列，再创建唯一索引。"""
        conn = sqlite3.connect(main.DB_PATH)
        conn.executescript(
            """
            CREATE TABLE accounts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT UNIQUE NOT NULL,
              profile_path TEXT NOT NULL,
              enabled INTEGER DEFAULT 1,
              created_at REAL
            );
            """
        )
        conn.close()

        main.init_db()
        main.init_db()

        conn = sqlite3.connect(main.DB_PATH)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(accounts)")}
        conn.close()
        self.assertIn("cc2api_account_id", columns)
        self.assertIn("warmup_enabled", columns)
        self.assertIn("oauth_refresh_last_attempt_at", columns)
        self.assertIn("oauth_refresh_last_status", columns)
        self.assertIn("oauth_refresh_last_error", columns)
        self.assertIn("idx_accounts_cc2api_account_id", indexes)

    def test_oauth_refresh_scripts_reuse_existing_scopes_and_write_tokens(self) -> None:
        """两个刷新入口都只能发送已有 scope，并正确写回服务端结果。"""
        original_scopes = [
            "user:profile",
            "user:inference",
            "user:sessions:claude_code",
            "user:mcp_servers",
            "user:file_upload",
        ]
        for entrypoint, script in self._oauth_refresh_node_scripts():
            with self.subTest(entrypoint=entrypoint):
                completed, request_body, updated = self._run_oauth_refresh_node_script(
                    entrypoint,
                    script,
                    {
                        "claudeAiOauth": {
                            "accessToken": "old-access",
                            "refreshToken": "old-refresh",
                            "expiresAt": 1,
                            "scopes": original_scopes,
                        }
                    },
                    {
                        "access_token": "new-access",
                        "refresh_token": "new-refresh",
                        "expires_in": 3600,
                        "scope": "user:inference user:profile user:inference",
                    },
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual(" ".join(original_scopes), request_body["scope"])
                self.assertNotIn("user:design:read", request_body["scope"])
                self.assertNotIn("user:design:write", request_body["scope"])
                oauth = updated["claudeAiOauth"]
                self.assertEqual("new-access", oauth["accessToken"])
                self.assertEqual("new-refresh", oauth["refreshToken"])
                self.assertGreater(oauth["expiresAt"], int(time.time() * 1000))
                self.assertEqual(
                    ["user:inference", "user:profile"],
                    oauth["scopes"],
                )

    def test_oauth_refresh_scripts_normalize_or_omit_scope(self) -> None:
        """空值和重复 scope 应归一化，没有有效 scope 时必须省略字段。"""
        for entrypoint, script in self._oauth_refresh_node_scripts():
            with self.subTest(entrypoint=entrypoint, case="normalize"):
                completed, request_body, updated = self._run_oauth_refresh_node_script(
                    entrypoint,
                    script,
                    {
                        "claudeAiOauth": {
                            "accessToken": "old-access",
                            "refreshToken": "old-refresh",
                            "expiresAt": 1,
                            "scopes": [
                                " user:profile ",
                                "",
                                "user:profile",
                                None,
                                "user:inference",
                            ],
                        }
                    },
                    {"access_token": "new-access", "expires_in": 3600},
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual(
                    "user:profile user:inference",
                    request_body["scope"],
                )
                self.assertEqual(
                    [" user:profile ", "", "user:profile", None, "user:inference"],
                    updated["claudeAiOauth"]["scopes"],
                )

            with self.subTest(entrypoint=entrypoint, case="omit"):
                completed, request_body, updated = self._run_oauth_refresh_node_script(
                    entrypoint,
                    script,
                    {
                        "claudeAiOauth": {
                            "accessToken": "old-access",
                            "refreshToken": "old-refresh",
                            "expiresAt": 1,
                            "scopes": ["", "   ", None],
                        }
                    },
                    {"access_token": "new-access", "expires_in": 3600},
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertNotIn("scope", request_body)
                self.assertEqual(
                    ["", "   ", None],
                    updated["claudeAiOauth"]["scopes"],
                )

            with self.subTest(entrypoint=entrypoint, case="missing"):
                completed, request_body, updated = self._run_oauth_refresh_node_script(
                    entrypoint,
                    script,
                    {
                        "claudeAiOauth": {
                            "accessToken": "old-access",
                            "refreshToken": "old-refresh",
                            "expiresAt": 1,
                        }
                    },
                    {"access_token": "new-access", "expires_in": 3600},
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertNotIn("scope", request_body)
                self.assertNotIn("scopes", updated["claudeAiOauth"])

    def test_oauth_refresh_scripts_redact_token_endpoint_error(self) -> None:
        """token endpoint 失败输出不得包含响应描述中的敏感值。"""
        for entrypoint, script in self._oauth_refresh_node_scripts():
            with self.subTest(entrypoint=entrypoint):
                completed, _request_body, _updated = self._run_oauth_refresh_node_script(
                    entrypoint,
                    script,
                    {
                        "claudeAiOauth": {
                            "accessToken": "old-access",
                            "refreshToken": "old-refresh",
                            "expiresAt": 1,
                            "scopes": ["user:profile"],
                        }
                    },
                    {
                        "error": "invalid_scope",
                        "error_description": "Bearer sensitive-token-value",
                    },
                    response_status=400,
                    retry_after="17",
                )
                self.assertEqual(1, completed.returncode)
                self.assertIn("HTTP 400", completed.stdout)
                self.assertIn("invalid_scope", completed.stdout)
                self.assertIn("retry_after_sec=17", completed.stdout)
                self.assertNotIn("sensitive-token-value", completed.stdout)

    def test_cc2api_matching_prefers_uuid_and_rejects_email_conflict(self) -> None:
        """UUID 存在时不能退回名称或冲突邮箱匹配。"""
        profile = {
            "account_uuid": "uuid-a",
            "email": "masked@example.test",
        }
        matched = main._find_cc2api_account_for_profile(
            profile,
            [
                {"id": 1, "account_uuid": "uuid-a", "email": "other@example.test"},
                {"id": 2, "account_uuid": "uuid-b", "email": "second@example.test"},
            ],
        )
        self.assertEqual(1, matched["id"])

        with self.assertRaisesRegex(ValueError, "account UUID 不同"):
            main._find_cc2api_account_for_profile(
                profile,
                [{"id": 3, "account_uuid": "uuid-b", "email": "masked@example.test"}],
            )

    def test_invalid_grant_is_classified_as_permanent(self) -> None:
        """invalid_grant 即使由下游包装成 5xx 也不能进入定时重试。"""
        self.assertTrue(
            main._cc2api_error_detail_is_permanent(
                "oauth refresh failed: invalid_grant"
            )
        )
        self.assertFalse(
            main._cc2api_error_detail_is_permanent("HTTP 503 upstream unavailable")
        )

    def test_cc2api_credentials_merge_preserves_profile_metadata(self) -> None:
        """镜像 AT/RT 时应保留 claudeAiOauth 的其它字段。"""
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        credentials_path = profile_dir / ".credentials.json"
        credentials_path.write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "old-access",
                    "refreshToken": "old-refresh",
                    "expiresAt": 1,
                    "subscriptionType": "max",
                    "scopes": ["user:inference"],
                }
            }),
            encoding="utf-8",
        )

        main._sync_cc2api_credentials_to_profile(
            "main",
            {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_at": 999999,
            },
        )

        data = json.loads(credentials_path.read_text(encoding="utf-8"))
        oauth = data["claudeAiOauth"]
        self.assertEqual("new-access", oauth["accessToken"])
        self.assertEqual("new-refresh", oauth["refreshToken"])
        self.assertEqual(999999, oauth["expiresAt"])
        self.assertEqual("max", oauth["subscriptionType"])
        self.assertEqual(["user:inference"], oauth["scopes"])
        self.assertEqual(0o600, stat.S_IMODE(credentials_path.stat().st_mode))

    def test_resolve_and_profile_write_are_serialized_and_keep_latest_snapshot(self) -> None:
        """慢返回的旧快照不得在并发同步时覆盖后发的新凭据。"""
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        credentials_path = profile_dir / ".credentials.json"
        credentials_path.write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "initial-access",
                    "refreshToken": "initial-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )
        first_entered = threading.Event()
        second_entered = threading.Event()
        release_first = threading.Event()
        call_lock = threading.Lock()
        call_count = 0

        def resolve_credentials(*_args, **_kwargs):
            """按调用顺序模拟慢旧响应和快新响应。"""
            nonlocal call_count
            with call_lock:
                index = call_count
                call_count += 1
            if index == 0:
                first_entered.set()
                release_first.wait(2)
                return {
                    "account_id": 7,
                    "access_token": "old-access",
                    "refresh_token": "old-refresh",
                    "expires_at": 100,
                }
            second_entered.set()
            return {
                "account_id": 7,
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_at": 200,
            }

        client = Mock()
        client.resolve_credentials.side_effect = resolve_credentials
        main.cc2api_client = client
        errors: list[Exception] = []

        def sync_once() -> None:
            """在线程中执行一次完整 resolve + profile 写入。"""
            try:
                main._resolve_and_sync_cc2api_credentials("main", 7, 600)
            except Exception as exc:
                errors.append(exc)

        first = threading.Thread(target=sync_once)
        second = threading.Thread(target=sync_once)
        first.start()
        self.assertTrue(first_entered.wait(1))
        second.start()
        self.assertFalse(second_entered.wait(0.1))
        release_first.set()
        first.join(2)
        second.join(2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual([], errors)
        self.assertTrue(second_entered.is_set())
        data = json.loads(credentials_path.read_text(encoding="utf-8"))
        self.assertEqual("new-access", data["claudeAiOauth"]["accessToken"])
        self.assertEqual("new-refresh", data["claudeAiOauth"]["refreshToken"])

    def test_bound_account_refresh_scheduler_only_mirrors_cc2api(self) -> None:
        """绑定账号后台刷新不得调用 bench 本地 RT 刷新路径。"""
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        (profile_dir / ".credentials.json").write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "old-access",
                    "refreshToken": "old-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id) "
                    "VALUES('main','profiles/main',7)"
                )
        finally:
            conn.close()
        client = Mock()
        client.resolve_credentials.return_value = {
            "account_id": 7,
            "access_token": "cc2-access",
            "refresh_token": "cc2-refresh",
            "expires_at": int(time.time() * 1000) + 3600000,
        }
        runner = Mock()
        original_client = main.cc2api_client
        main.cc2api_client = client
        try:
            main.OAuthRefreshScheduler(runner)._tick()
        finally:
            main.cc2api_client = original_client

        client.resolve_credentials.assert_called_once()
        runner.refresh_account_oauth_token.assert_not_called()
        data = json.loads((profile_dir / ".credentials.json").read_text(encoding="utf-8"))
        self.assertEqual("cc2-access", data["claudeAiOauth"]["accessToken"])

    def test_oauth_refresh_error_summary_only_keeps_safe_fields(self) -> None:
        """后台错误摘要只保留状态、OAuth 错误码和 retry-after。"""
        cases = [
            (
                "HTTP 400 invalid_scope Bearer access-secret refreshToken=refresh-secret",
                ["HTTP 400", "invalid_scope"],
            ),
            (
                "HTTP 400 invalid_grant Cookie=session-secret",
                ["HTTP 400", "invalid_grant"],
            ),
            (
                "HTTP 429 invalid_request retry_after_sec=60 proxy-pass=secret",
                ["HTTP 429", "invalid_request", "retry_after_sec=60"],
            ),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                summary = main._oauth_refresh_error_summary(RuntimeError(raw))
                for value in expected:
                    self.assertIn(value, summary)
                self.assertNotIn("secret", summary)

    def test_unbound_refresh_failure_is_recorded_and_next_account_continues(self) -> None:
        """一个未绑定账号刷新失败后应落安全状态，并继续刷新后续账号。"""
        main.init_db()
        for name in ("first", "second"):
            profile_dir = main.PROFILES_DIR / name
            profile_dir.mkdir(parents=True)
            (profile_dir / ".credentials.json").write_text(
                json.dumps({
                    "claudeAiOauth": {
                        "accessToken": f"{name}-access",
                        "refreshToken": f"{name}-refresh",
                        "expiresAt": 1,
                        "scopes": ["user:profile"],
                    }
                }),
                encoding="utf-8",
            )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path) "
                    "VALUES('first','profiles/first')"
                )
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, oauth_refresh_last_status, "
                    "oauth_refresh_last_error) "
                    "VALUES('second','profiles/second','failed','old-safe-error')"
                )
        finally:
            conn.close()
        runner = Mock()
        runner.refresh_account_oauth_token.side_effect = [
            RuntimeError(
                "OAuth token 刷新失败: HTTP 400; invalid_scope; "
                "Bearer access-secret; refreshToken=refresh-secret"
            ),
            True,
        ]

        main.OAuthRefreshScheduler(runner)._tick()

        self.assertEqual(2, runner.refresh_account_oauth_token.call_count)
        conn = main.get_db()
        try:
            rows = conn.execute(
                "SELECT name, oauth_refresh_last_attempt_at, oauth_refresh_last_status, "
                "oauth_refresh_last_error FROM accounts ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual("failed", rows[0]["oauth_refresh_last_status"])
        self.assertIsNotNone(rows[0]["oauth_refresh_last_attempt_at"])
        self.assertIn("HTTP 400", rows[0]["oauth_refresh_last_error"])
        self.assertIn("invalid_scope", rows[0]["oauth_refresh_last_error"])
        self.assertNotIn("access-secret", rows[0]["oauth_refresh_last_error"])
        self.assertNotIn("refresh-secret", rows[0]["oauth_refresh_last_error"])
        self.assertEqual("success", rows[1]["oauth_refresh_last_status"])
        self.assertIsNotNone(rows[1]["oauth_refresh_last_attempt_at"])
        self.assertIsNone(rows[1]["oauth_refresh_last_error"])

    def test_unbound_refresh_scheduler_blocks_first_binding(self) -> None:
        """未绑定账号的本地 RT 刷新完成前，首次绑定必须等待 owner lock。"""
        client = self._prepare_syncable_unbound_account()
        refresh_entered = threading.Event()
        release_refresh = threading.Event()
        runner = Mock()

        def refresh_account_oauth_token(_account: dict) -> bool:
            """阻塞本地刷新，暴露首次绑定必须等待的临界区。"""
            refresh_entered.set()
            release_refresh.wait(2)
            return True

        runner.refresh_account_oauth_token.side_effect = refresh_account_oauth_token
        refresh_thread = threading.Thread(target=main.OAuthRefreshScheduler(runner)._tick)
        refresh_thread.start()
        self.assertTrue(refresh_entered.wait(1))

        sync_results: list[dict] = []
        sync_errors: list[Exception] = []

        def sync_account() -> None:
            """并发执行首次绑定并记录结果。"""
            try:
                sync_results.append(main.sync_account_to_cc2api(1))
            except Exception as exc:
                sync_errors.append(exc)

        sync_thread = threading.Thread(target=sync_account)
        sync_thread.start()
        time.sleep(0.1)
        self.assertTrue(sync_thread.is_alive())
        client.list_accounts.assert_not_called()

        release_refresh.set()
        refresh_thread.join(2)
        sync_thread.join(2)
        self.assertFalse(refresh_thread.is_alive())
        self.assertFalse(sync_thread.is_alive())
        self.assertEqual([], sync_errors)
        self.assertEqual(1, len(sync_results))
        client.list_accounts.assert_called_once()

    def test_unbound_quota_query_blocks_first_binding(self) -> None:
        """未绑定 quota worker 结束前，首次绑定不得读取可能轮换前的旧 RT。"""
        client = self._prepare_syncable_unbound_account()
        quota_entered = threading.Event()
        release_quota = threading.Event()
        quota_runner = Mock()

        def query_quota(_account: dict) -> dict:
            """阻塞额度查询，模拟其中可能发生的本地 RT 轮换。"""
            quota_entered.set()
            release_quota.wait(2)
            return {"ok": True}

        quota_runner.query_quota.side_effect = query_quota
        main.runner = quota_runner
        quota_results: list[dict] = []
        quota_errors: list[Exception] = []
        sync_results: list[dict] = []
        sync_errors: list[Exception] = []

        def run_quota() -> None:
            """在线程中执行未绑定账号额度查询。"""
            try:
                quota_results.append(main.query_account_quota(1))
            except Exception as exc:
                quota_errors.append(exc)

        def sync_account() -> None:
            """并发执行首次绑定并记录结果。"""
            try:
                sync_results.append(main.sync_account_to_cc2api(1))
            except Exception as exc:
                sync_errors.append(exc)

        quota_thread = threading.Thread(target=run_quota)
        quota_thread.start()
        self.assertTrue(quota_entered.wait(1))
        sync_thread = threading.Thread(target=sync_account)
        sync_thread.start()
        time.sleep(0.1)
        self.assertTrue(sync_thread.is_alive())
        client.list_accounts.assert_not_called()

        release_quota.set()
        quota_thread.join(2)
        sync_thread.join(2)
        self.assertFalse(quota_thread.is_alive())
        self.assertFalse(sync_thread.is_alive())
        self.assertEqual([], quota_errors)
        self.assertEqual([], sync_errors)
        self.assertEqual([{"ok": True}], quota_results)
        self.assertEqual(1, len(sync_results))
        client.list_accounts.assert_called_once()

    def test_bound_sync_rejects_stale_binding_before_resolve(self) -> None:
        """后台拿到旧绑定快照时不得覆盖新绑定账号的 profile。"""
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        credentials_path = profile_dir / ".credentials.json"
        credentials_path.write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "current-access",
                    "refreshToken": "current-refresh",
                    "expiresAt": 123,
                }
            }),
            encoding="utf-8",
        )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id) "
                    "VALUES('main','profiles/main',8)"
                )
        finally:
            conn.close()
        client = Mock()
        main.cc2api_client = client

        with self.assertRaisesRegex(ValueError, "绑定已变化"):
            main._sync_bound_account_credentials(
                {"id": 1, "name": "main", "cc2api_account_id": 7},
                600,
            )

        client.resolve_credentials.assert_not_called()
        data = json.loads(credentials_path.read_text(encoding="utf-8"))
        self.assertEqual("current-access", data["claudeAiOauth"]["accessToken"])
        self.assertEqual("current-refresh", data["claudeAiOauth"]["refreshToken"])

    def test_temporary_cc2api_failure_schedules_fifteen_minute_retry(self) -> None:
        """临时 cc2api 故障不得创建 run，应保留开关并安排重试。"""
        main.init_db()
        now = time.time()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled, "
                    "warmup_next_run_at) VALUES('main','profiles/main',7,1,?)",
                    (now - 1,),
                )
        finally:
            conn.close()
        client = Mock()
        client.resolve_credentials.side_effect = ConnectionError("network unavailable")
        original_client = main.cc2api_client
        main.cc2api_client = client
        try:
            result = main.WarmupScheduler(Mock()).trigger_account(1, require_due=True)
        finally:
            main.cc2api_client = original_client
        self.assertFalse(result["started"])

        conn = main.get_db()
        try:
            row = conn.execute(
                "SELECT warmup_enabled, warmup_last_status, warmup_next_run_at FROM accounts WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(1, row["warmup_enabled"])
        self.assertEqual("sync_failed", row["warmup_last_status"])
        self.assertGreaterEqual(row["warmup_next_run_at"], now + main.WARMUP_SYNC_RETRY_SEC - 2)

    def test_sync_links_existing_cc2api_account_without_create(self) -> None:
        """匹配到现有 cc2api 账号时只关联并以 cc2api 凭据覆盖 bench。"""
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        (profile_dir / ".credentials.json").write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "bench-old-access",
                    "refreshToken": "bench-old-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )
        (profile_dir / ".claude.json").write_text(
            json.dumps({
                "oauthAccount": {
                    "emailAddress": "main@example.test",
                    "accountUuid": "uuid-main",
                    "organizationUuid": "org-main",
                }
            }),
            encoding="utf-8",
        )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path) VALUES('main','profiles/main')"
                )
        finally:
            conn.close()
        client = Mock()
        client.list_accounts.return_value = [{
            "id": 7,
            "name": "existing",
            "email": "main@example.test",
            "status": "active",
            "auth_type": "oauth",
            "account_uuid": "uuid-main",
        }]
        client.resolve_credentials.return_value = {
            "account_id": 7,
            "access_token": "cc2-current-access",
            "refresh_token": "cc2-current-refresh",
            "expires_at": int(time.time() * 1000) + 3600000,
        }
        original_client = main.cc2api_client
        main.cc2api_client = client
        try:
            result = main.sync_account_to_cc2api(1)
            conn = main.get_db()
            try:
                initial = conn.execute(
                    "SELECT warmup_enabled, warmup_last_status FROM accounts WHERE id=1"
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(0, initial["warmup_enabled"])
            self.assertEqual("off", initial["warmup_last_status"])
            scheduled_at = time.time() + 3600
            conn = main.get_db()
            try:
                with conn:
                    conn.execute(
                        "UPDATE accounts SET warmup_enabled=1, warmup_next_run_at=?, "
                        "warmup_last_status='scheduled' WHERE id=1",
                        (scheduled_at,),
                    )
            finally:
                conn.close()
            repeated = main.sync_account_to_cc2api(1)
        finally:
            main.cc2api_client = original_client

        self.assertFalse(result["created"])
        self.assertFalse(repeated["created"])
        client.create_account.assert_not_called()
        conn = main.get_db()
        try:
            row = conn.execute(
                "SELECT cc2api_account_id, warmup_enabled, warmup_next_run_at, "
                "warmup_last_status FROM accounts WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(7, row["cc2api_account_id"])
        self.assertEqual(1, row["warmup_enabled"])
        self.assertEqual("scheduled", row["warmup_last_status"])
        self.assertAlmostEqual(scheduled_at, row["warmup_next_run_at"], places=3)
        data = json.loads((profile_dir / ".credentials.json").read_text(encoding="utf-8"))
        self.assertEqual("cc2-current-refresh", data["claudeAiOauth"]["refreshToken"])

    def test_sync_creates_cc2api_account_with_fast_mode_disabled(self) -> None:
        """首次同步创建 cc2api 账号时必须显式禁止客户端 Fast Mode。"""
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        (profile_dir / ".credentials.json").write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "bench-access",
                    "refreshToken": "bench-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )
        (profile_dir / ".claude.json").write_text(
            json.dumps({
                "oauthAccount": {
                    "emailAddress": "main@example.test",
                    "accountUuid": "uuid-main",
                    "organizationUuid": "org-main",
                }
            }),
            encoding="utf-8",
        )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path) VALUES('main','profiles/main')"
                )
        finally:
            conn.close()

        client = Mock()
        client.list_accounts.return_value = []
        client.create_account.return_value = {
            "id": 7,
            "name": "main",
            "email": "main@example.test",
            "status": "active",
            "auth_type": "oauth",
            "account_uuid": "uuid-main",
            "allow_fast_mode": False,
        }
        client.resolve_credentials.return_value = {
            "account_id": 7,
            "access_token": "cc2-current-access",
            "refresh_token": "cc2-current-refresh",
            "expires_at": int(time.time() * 1000) + 3600000,
        }
        main.cc2api_client = client
        main.login_manager = None
        main.continue_manager = None

        result = main.sync_account_to_cc2api(1)

        self.assertTrue(result["created"])
        payload = client.create_account.call_args.args[0]
        self.assertIs(payload["allow_fast_mode"], False)
        conn = main.get_db()
        try:
            row = conn.execute(
                "SELECT cc2api_account_id, warmup_enabled, warmup_last_status "
                "FROM accounts WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(7, row["cc2api_account_id"])
        self.assertEqual(0, row["warmup_enabled"])
        self.assertEqual("off", row["warmup_last_status"])
        data = json.loads((profile_dir / ".credentials.json").read_text(encoding="utf-8"))
        self.assertEqual("cc2-current-refresh", data["claudeAiOauth"]["refreshToken"])

    def test_bound_sync_does_not_rematch_or_overwrite_profile_before_rejecting(self) -> None:
        """已绑定账号同步失败时不得先写入另一个 cc2api 账号的凭据。"""
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        credentials_path = profile_dir / ".credentials.json"
        credentials_path.write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "bound-access",
                    "refreshToken": "bound-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )
        (profile_dir / ".claude.json").write_text(
            json.dumps({
                "oauthAccount": {
                    "emailAddress": "other@example.test",
                    "accountUuid": "uuid-other",
                }
            }),
            encoding="utf-8",
        )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id) "
                    "VALUES('main','profiles/main',7)"
                )
        finally:
            conn.close()
        client = Mock()
        client.list_accounts.return_value = [{
            "id": 8,
            "name": "other",
            "email": "other@example.test",
            "account_uuid": "uuid-other",
            "status": "active",
            "auth_type": "oauth",
        }]
        client.resolve_credentials.return_value = {
            "account_id": 8,
            "access_token": "other-access",
            "refresh_token": "other-refresh",
            "expires_at": 9999999999999,
        }
        main.cc2api_client = client
        main.login_manager = None
        main.continue_manager = None

        with self.assertRaises(main.HTTPException) as error:
            main.sync_account_to_cc2api(1)

        self.assertEqual(409, error.exception.status_code)
        client.resolve_credentials.assert_not_called()
        oauth = json.loads(credentials_path.read_text(encoding="utf-8"))["claudeAiOauth"]
        self.assertEqual("bound-access", oauth["accessToken"])
        self.assertEqual("bound-refresh", oauth["refreshToken"])

    def test_sync_rejects_cc2api_id_already_bound_to_another_bench_account(self) -> None:
        """重复绑定应在 resolve 和 profile 写入前拒绝。"""
        client = self._prepare_syncable_unbound_account()
        credentials_path = main.PROFILES_DIR / "main" / ".credentials.json"
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id) "
                    "VALUES('other','profiles/other',7)"
                )
        finally:
            conn.close()

        with self.assertRaises(main.HTTPException) as error:
            main.sync_account_to_cc2api(1)

        self.assertEqual(409, error.exception.status_code)
        client.resolve_credentials.assert_not_called()
        oauth = json.loads(credentials_path.read_text(encoding="utf-8"))["claudeAiOauth"]
        self.assertEqual("bench-access", oauth["accessToken"])
        self.assertEqual("bench-refresh", oauth["refreshToken"])

    def test_active_run_blocks_binding_change_and_unbind(self) -> None:
        """queued/running/stopping run 存在时不得切换或解除凭据所有权。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id) "
                    "VALUES('main','profiles/main',7)"
                )
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status) "
                    "VALUES('queued-run',1,1,'queued')"
                )
        finally:
            conn.close()
        main.login_manager = None
        main.continue_manager = None

        with self.assertRaises(main.HTTPException) as update_error:
            main.update_account_warmup(
                1,
                main.WarmupConfigIn(
                    cc2api_account_id=8,
                    enabled=False,
                    interval_min_hours=3,
                    interval_max_hours=5,
                ),
            )
        self.assertEqual(409, update_error.exception.status_code)

        with self.assertRaises(main.HTTPException) as delete_error:
            main.delete_account_cc2api_binding(1)
        self.assertEqual(409, delete_error.exception.status_code)

    def test_bound_account_delete_waits_for_owner_and_rejects_active_run(self) -> None:
        """绑定账号删除必须等待 owner lock，并在存在活跃 run 时保持原账号。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id) "
                    "VALUES('main','profiles/main',7)"
                )
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status) "
                    "VALUES('queued-run',1,1,'queued')"
                )
        finally:
            conn.close()
        main.login_manager = None
        main.continue_manager = None
        owner_lock = main._oauth_owner_lock("main")
        delete_errors: list[Exception] = []

        def delete_bound_account() -> None:
            """并发删除绑定账号并记录业务拒绝。"""
            try:
                main.delete_account(1)
            except Exception as exc:
                delete_errors.append(exc)

        owner_lock.acquire()
        delete_thread = threading.Thread(target=delete_bound_account)
        try:
            delete_thread.start()
            time.sleep(0.1)
            self.assertTrue(delete_thread.is_alive())
        finally:
            owner_lock.release()
        delete_thread.join(2)
        self.assertFalse(delete_thread.is_alive())
        self.assertEqual(1, len(delete_errors))
        self.assertIsInstance(delete_errors[0], main.HTTPException)
        self.assertEqual(409, delete_errors[0].status_code)

        conn = main.get_db()
        try:
            account = conn.execute(
                "SELECT deleted_at, cc2api_account_id FROM accounts WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNone(account["deleted_at"])
        self.assertEqual(7, account["cc2api_account_id"])

    def test_unbound_account_delete_preserves_physical_and_soft_delete_semantics(self) -> None:
        """未绑定账号加 owner lock 后仍按历史引用选择物理或软删除。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                first = conn.execute(
                    "INSERT INTO accounts(name, profile_path) VALUES('first','profiles/first')"
                )
                first_id = int(first.lastrowid)
        finally:
            conn.close()

        physical = main.delete_account(first_id)
        self.assertFalse(physical["soft_deleted"])
        conn = main.get_db()
        try:
            self.assertIsNone(conn.execute(
                "SELECT id FROM accounts WHERE id=?",
                (first_id,),
            ).fetchone())
            with conn:
                second = conn.execute(
                    "INSERT INTO accounts(name, profile_path) VALUES('second','profiles/second')"
                )
                second_id = int(second.lastrowid)
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status) "
                    "VALUES('historical-run',1,?,'success')",
                    (second_id,),
                )
        finally:
            conn.close()

        soft = main.delete_account(second_id)
        self.assertTrue(soft["soft_deleted"])
        conn = main.get_db()
        try:
            account = conn.execute(
                "SELECT enabled, deleted_at FROM accounts WHERE id=?",
                (second_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(0, account["enabled"])
        self.assertIsNotNone(account["deleted_at"])

    def test_active_run_cannot_be_deleted_or_hidden_from_owner_checks(self) -> None:
        """活跃 run 不可软删除，历史脏数据也不能绕过所有权和养号检查。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled) "
                    "VALUES('main','profiles/main',7,1)"
                )
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status, run_kind) "
                    "VALUES('active-warmup',1,1,'queued','warmup')"
                )
        finally:
            conn.close()

        with self.assertRaises(main.HTTPException) as delete_error:
            main.delete_run("active-warmup")
        self.assertEqual(409, delete_error.exception.status_code)

        conn = main.get_db()
        try:
            with conn:
                row = conn.execute(
                    "SELECT deleted_at FROM runs WHERE id='active-warmup'"
                ).fetchone()
                self.assertIsNone(row["deleted_at"])
                conn.execute(
                    "UPDATE runs SET deleted_at=? WHERE id='active-warmup'",
                    (time.time(),),
                )
        finally:
            conn.close()
        main.login_manager = None
        main.continue_manager = None
        blocker = main._oauth_owner_transition_blocker({"id": 1, "name": "main"})
        self.assertIn("active-warmup", blocker)
        claimed = main.WarmupScheduler(Mock())._claim_account(1, require_due=False)
        self.assertIsNone(claimed)

    def test_continue_and_login_sessions_block_unbind(self) -> None:
        """继续对话或登录会话活跃时不得解绑 cc2api。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id) "
                    "VALUES('main','profiles/main',7)"
                )
        finally:
            conn.close()

        continue_manager = Mock()
        continue_manager.has_active_account.return_value = True
        login_manager = Mock()
        login_manager.has_active_name.return_value = False
        main.continue_manager = continue_manager
        main.login_manager = login_manager
        with self.assertRaises(main.HTTPException) as continue_error:
            main.delete_account_cc2api_binding(1)
        self.assertEqual(409, continue_error.exception.status_code)

        continue_manager.has_active_account.return_value = False
        login_manager.has_active_name.return_value = True
        with self.assertRaises(main.HTTPException) as login_error:
            main.delete_account_cc2api_binding(1)
        self.assertEqual(409, login_error.exception.status_code)

    def test_bound_login_start_is_rejected_before_worker_creation(self) -> None:
        """已绑定账号不能通过任何 login start 路径生成第二条 RT。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id) "
                    "VALUES('main','profiles/main',7)"
                )
        finally:
            conn.close()
        login_manager = Mock()
        main.login_manager = login_manager

        with self.assertRaises(main.HTTPException) as error:
            main.login_start(main.LoginStartIn(name="main"))

        self.assertEqual(409, error.exception.status_code)
        login_manager.start.assert_not_called()

    def test_worker_start_and_unbind_are_serialized_by_owner_lock(self) -> None:
        """worker 创建完成前解绑必须等待，随后因活跃 run 被拒绝。"""
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        (profile_dir / ".credentials.json").write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "old-access",
                    "refreshToken": "old-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id) "
                    "VALUES('main','profiles/main',7)"
                )
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status) "
                    "VALUES('owner-run',1,1,'queued')"
                )
        finally:
            conn.close()
        client = Mock()
        client.resolve_credentials.return_value = {
            "account_id": 7,
            "access_token": "cc2-access",
            "refresh_token": "cc2-refresh",
            "expires_at": int(time.time() * 1000) + 3600000,
        }
        main.cc2api_client = client
        main.login_manager = None
        main.continue_manager = None
        main.warmup_scheduler = None

        start_entered = threading.Event()
        release_start = threading.Event()
        release_wait = threading.Event()
        fake_runner = Mock()

        def start_run(*_args):
            """阻塞 worker 创建，暴露所有权锁的临界区。"""
            start_entered.set()
            release_start.wait(2)
            return "sidecar", "worker"

        def wait_worker(_worker_id):
            """保持 run 活跃，直到解绑线程完成检查。"""
            release_wait.wait(2)
            return 0

        fake_runner.start_run.side_effect = start_run
        fake_runner.wait_worker.side_effect = wait_worker
        fake_runner.read_worker_status.return_value = {}
        scheduler = main.Scheduler(fake_runner)
        account = {"id": 1, "name": "main", "cc2api_account_id": 7}
        task = {"id": 1, "timeout_sec": 1800}
        worker_thread = threading.Thread(
            target=scheduler._execute,
            args=("owner-run", account, task),
        )
        worker_thread.start()
        self.assertTrue(start_entered.wait(1))

        unbind_errors: list[Exception] = []

        def unbind() -> None:
            """并发尝试解绑并记录业务拒绝。"""
            try:
                main.delete_account_cc2api_binding(1)
            except Exception as exc:
                unbind_errors.append(exc)

        unbind_thread = threading.Thread(target=unbind)
        unbind_thread.start()
        time.sleep(0.1)
        self.assertTrue(unbind_thread.is_alive())
        release_start.set()
        unbind_thread.join(2)
        self.assertFalse(unbind_thread.is_alive())
        self.assertEqual(1, len(unbind_errors))
        self.assertIsInstance(unbind_errors[0], main.HTTPException)
        self.assertEqual(409, unbind_errors[0].status_code)
        release_wait.set()
        worker_thread.join(2)
        self.assertFalse(worker_thread.is_alive())

        conn = main.get_db()
        try:
            row = conn.execute(
                "SELECT cc2api_account_id FROM accounts WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(7, row["cc2api_account_id"])

    def test_warmup_creates_real_run_with_topic_only_prompt(self) -> None:
        """养号应创建真实 warmup run，且 prompt 不拼接账号信息。"""
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        (profile_dir / ".credentials.json").write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "old-access",
                    "refreshToken": "old-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled, "
                    "warmup_next_run_at) VALUES('main','profiles/main',7,1,?)",
                    (time.time() - 1,),
                )
                conn.execute(
                    "INSERT INTO topics(no, title, description, category) "
                    "VALUES(1,'标准题目','只使用题库描述','测试')"
                )
        finally:
            conn.close()
        client = Mock()
        client.resolve_credentials.return_value = {
            "account_id": 7,
            "access_token": "cc2-access",
            "refresh_token": "cc2-refresh",
            "expires_at": int(time.time() * 1000) + 3600000,
        }
        run_scheduler = Mock()
        original_client = main.cc2api_client
        main.cc2api_client = client
        try:
            with patch.object(main, "effective_runtime_effort", return_value="high"):
                result = main.WarmupScheduler(run_scheduler).trigger_account(
                    1,
                    require_due=True,
                )
        finally:
            main.cc2api_client = original_client
        self.assertTrue(result["started"])

        conn = main.get_db()
        try:
            run = conn.execute(
                "SELECT * FROM runs WHERE id=?",
                (result["run_id"],),
            ).fetchone()
            task = conn.execute(
                "SELECT * FROM tasks WHERE id=?",
                (result["task_id"],),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual("warmup", run["run_kind"])
        self.assertEqual("queued", run["status"])
        self.assertEqual("2.1.260", run["claude_code_version"])
        self.assertEqual("high", run["claude_effort_level"])
        submitted_task = run_scheduler.submit.call_args.args[2]
        self.assertEqual("2.1.260", submitted_task["claude_code_version"])
        self.assertEqual("high", submitted_task["claude_effort_level"])
        self.assertEqual(task["prompt"], submitted_task["prompt"])
        self.assertIn("标准题目", task["prompt"])
        self.assertIn("只使用题库描述", task["prompt"])
        self.assertNotIn("main", task["prompt"])
        run_scheduler.submit.assert_called_once()

    def test_queued_warmup_syncs_again_before_start_and_reports_running(self) -> None:
        """养号排队后拿到信号量时必须再次同步，并先展示 running。"""
        main.init_db()
        profile_dir = main.PROFILES_DIR / "main"
        profile_dir.mkdir(parents=True)
        credentials_path = profile_dir / ".credentials.json"
        credentials_path.write_text(
            json.dumps({
                "claudeAiOauth": {
                    "accessToken": "initial-access",
                    "refreshToken": "initial-refresh",
                    "expiresAt": 1,
                }
            }),
            encoding="utf-8",
        )
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled, "
                    "warmup_next_run_at) VALUES('main','profiles/main',7,1,?)",
                    (time.time() - 1,),
                )
                conn.execute(
                    "INSERT INTO topics(no, title, description, category) "
                    "VALUES(1,'标准题目','只使用题库描述','测试')"
                )
        finally:
            conn.close()
        client = Mock()
        client.resolve_credentials.side_effect = [
            {
                "account_id": 7,
                "access_token": "prepared-access",
                "refresh_token": "prepared-refresh",
                "expires_at": int(time.time() * 1000) + 3600000,
            },
            {
                "account_id": 7,
                "access_token": "start-access",
                "refresh_token": "start-refresh",
                "expires_at": int(time.time() * 1000) + 7200000,
            },
        ]
        main.cc2api_client = client
        submitter = Mock()
        warmup = main.WarmupScheduler(submitter)
        result = warmup.trigger_account(1, require_due=True)
        self.assertTrue(result["started"])
        submitter.submit.assert_called_once()
        run_id, account, task = submitter.submit.call_args.args
        self.assertNotIn("cc2api_credentials_prepared", task)

        observed_statuses: list[str] = []
        fake_runner = Mock()

        def start_run(*_args):
            """记录真实 worker 创建时账号页已经同步到的养号状态。"""
            conn = main.get_db()
            try:
                row = conn.execute(
                    "SELECT warmup_last_status FROM accounts WHERE id=1"
                ).fetchone()
                observed_statuses.append(str(row["warmup_last_status"]))
            finally:
                conn.close()
            return "sidecar", "worker"

        fake_runner.start_run.side_effect = start_run
        fake_runner.wait_worker.return_value = 0
        fake_runner.read_worker_status.return_value = {}
        main.warmup_scheduler = warmup
        main.Scheduler(fake_runner)._execute(run_id, account, task)

        self.assertEqual(2, client.resolve_credentials.call_count)
        self.assertEqual(["running"], observed_statuses)
        data = json.loads(credentials_path.read_text(encoding="utf-8"))
        self.assertEqual("start-access", data["claudeAiOauth"]["accessToken"])
        self.assertEqual("start-refresh", data["claudeAiOauth"]["refreshToken"])

    def test_queued_warmup_temporary_sync_failure_keeps_short_retry(self) -> None:
        """排队后二次同步临时失败时应保留 15 分钟短重试。"""
        run, account, before, fake_runner, client = self._run_queued_warmup_with_second_sync_error(
            ConnectionError("network unavailable")
        )

        self.assertEqual("failed", run["status"])
        self.assertEqual(1, account["warmup_enabled"])
        self.assertEqual("sync_failed", account["warmup_last_status"])
        self.assertGreaterEqual(
            account["warmup_next_run_at"],
            before + main.WARMUP_SYNC_RETRY_SEC - 2,
        )
        self.assertLessEqual(
            account["warmup_next_run_at"],
            before + main.WARMUP_SYNC_RETRY_SEC + 2,
        )
        fake_runner.start_run.assert_not_called()
        self.assertEqual(2, client.resolve_credentials.call_count)

    def test_queued_warmup_permanent_sync_failure_pauses_immediately(self) -> None:
        """排队后二次同步遇到永久凭据错误时应立即暂停养号。"""
        run, account, _before, fake_runner, client = self._run_queued_warmup_with_second_sync_error(
            ValueError("cc2api 请求失败：OAuth 刷新失败: invalid_grant")
        )

        self.assertEqual("failed", run["status"])
        self.assertEqual(0, account["warmup_enabled"])
        self.assertEqual("paused", account["warmup_last_status"])
        self.assertIsNone(account["warmup_next_run_at"])
        self.assertIn("invalid_grant", account["warmup_last_error"])
        fake_runner.start_run.assert_not_called()
        self.assertEqual(2, client.resolve_credentials.call_count)

    def test_first_invalid_grant_auth_failure_pauses_warmup(self) -> None:
        """首个包含 invalid_grant 的 auth_failed 就应立即暂停养号。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled, "
                    "warmup_last_run_id, warmup_last_status, warmup_auth_failures) "
                    "VALUES('main','profiles/main',7,1,'warmup-run','running',0)"
                )
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status, run_kind, error) "
                    "VALUES('warmup-run',1,1,'auth_failed','warmup',"
                    "'OAuth 认证失败；cc2api 刷新失败：invalid_grant')"
                )
        finally:
            conn.close()

        scheduler = main.WarmupScheduler(object())
        scheduler.handle_run_terminal("warmup-run")

        conn = main.get_db()
        try:
            row = conn.execute(
                "SELECT warmup_enabled, warmup_last_status, warmup_last_error, "
                "warmup_auth_failures, warmup_next_run_at FROM accounts WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(0, row["warmup_enabled"])
        self.assertEqual("paused", row["warmup_last_status"])
        self.assertEqual(1, row["warmup_auth_failures"])
        self.assertIsNone(row["warmup_next_run_at"])
        self.assertIn("invalid_grant", row["warmup_last_error"])

    def test_stopping_warmup_immediately_schedules_next_run(self) -> None:
        """停止养号 run 后应立即写终态并安排下一次随机触发。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled, "
                    "warmup_last_run_id, warmup_last_status) "
                    "VALUES('main','profiles/main',7,1,'warmup-run','running')"
                )
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status, run_kind) "
                    "VALUES('warmup-run',1,1,'running','warmup')"
                )
        finally:
            conn.close()
        main.runner = Mock()
        main.warmup_scheduler = main.WarmupScheduler(Mock())
        before = time.time()

        main.stop_run("warmup-run")

        conn = main.get_db()
        try:
            run = conn.execute(
                "SELECT status FROM runs WHERE id='warmup-run'"
            ).fetchone()
            account = conn.execute(
                "SELECT warmup_last_status, warmup_next_run_at FROM accounts WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual("stopped", run["status"])
        self.assertEqual("stopped", account["warmup_last_status"])
        self.assertGreater(account["warmup_next_run_at"], before)

    def test_disabled_warmup_run_terminal_keeps_off_status(self) -> None:
        """用户主动关闭养号后，活跃 run 收口不能把 off 改成 paused。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled, "
                    "warmup_last_run_id, warmup_last_status) "
                    "VALUES('main','profiles/main',7,0,'warmup-run','off')"
                )
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status, run_kind) "
                    "VALUES('warmup-run',1,1,'success','warmup')"
                )
        finally:
            conn.close()

        main.WarmupScheduler(object()).handle_run_terminal("warmup-run")

        conn = main.get_db()
        try:
            row = conn.execute(
                "SELECT warmup_enabled, warmup_last_status, warmup_next_run_at "
                "FROM accounts WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(0, row["warmup_enabled"])
        self.assertEqual("off", row["warmup_last_status"])
        self.assertIsNone(row["warmup_next_run_at"])

    def test_old_warmup_terminal_does_not_update_new_cc2api_binding(self) -> None:
        """旧绑定的养号终态不得把认证失败写到新 cc2api 绑定上。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled, "
                    "warmup_next_run_at, warmup_last_run_id, warmup_last_status) "
                    "VALUES('main','profiles/main',8,1,?,'warmup-run','scheduled')",
                    (time.time() + 3600,),
                )
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status, run_kind, error) "
                    "VALUES('warmup-run',1,1,'auth_failed','warmup','OAuth invalid_grant')"
                )
        finally:
            conn.close()

        main.WarmupScheduler(Mock()).handle_run_terminal("warmup-run", 7)

        conn = main.get_db()
        try:
            row = conn.execute(
                "SELECT cc2api_account_id, warmup_enabled, warmup_last_status, "
                "warmup_auth_failures FROM accounts WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(8, row["cc2api_account_id"])
        self.assertEqual(1, row["warmup_enabled"])
        self.assertEqual("scheduled", row["warmup_last_status"])
        self.assertEqual(0, row["warmup_auth_failures"])

    def test_topic_selection_excludes_recent_twenty_when_candidate_exists(self) -> None:
        """养号抽题应优先排除账号最近 20 道题。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled) "
                    "VALUES('main','profiles/main',7,1)"
                )
                for no in range(1, 22):
                    conn.execute(
                        "INSERT INTO topics(no, title, description, category) VALUES(?,?,?,?)",
                        (no, f"topic-{no}", "description", "category"),
                    )
                for index in range(1, 21):
                    conn.execute(
                        "INSERT INTO runs(id, task_id, account_id, topic_id, status, run_kind, created_at) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (f"run-{index}", index, 1, index, "success", "warmup", float(index)),
                    )
        finally:
            conn.close()

        scheduler = main.WarmupScheduler(object())
        topic = scheduler._select_topic(1)
        self.assertEqual(21, topic["id"])

    def test_third_auth_failure_pauses_warmup(self) -> None:
        """连续第三次 auth_failed 应关闭养号并保留暂停原因。"""
        main.init_db()
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO accounts(name, profile_path, cc2api_account_id, warmup_enabled, "
                    "warmup_last_run_id, warmup_last_status, warmup_auth_failures) "
                    "VALUES('main','profiles/main',7,1,'warmup-run','running',2)"
                )
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, status, run_kind, error) "
                    "VALUES('warmup-run',1,1,'auth_failed','warmup','OAuth 认证失败')"
                )
        finally:
            conn.close()

        scheduler = main.WarmupScheduler(object())
        scheduler.handle_run_terminal("warmup-run")

        conn = main.get_db()
        try:
            row = conn.execute(
                "SELECT warmup_enabled, warmup_last_status, warmup_last_error, "
                "warmup_auth_failures, warmup_next_run_at FROM accounts WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(0, row["warmup_enabled"])
        self.assertEqual("paused", row["warmup_last_status"])
        self.assertEqual(3, row["warmup_auth_failures"])
        self.assertIsNone(row["warmup_next_run_at"])
        self.assertIn("连续 3 次", row["warmup_last_error"])


if __name__ == "__main__":
    unittest.main()
