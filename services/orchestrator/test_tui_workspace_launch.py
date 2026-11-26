"""核对账号进程启动前的工作区、原生历史和身份绑定。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from tui_workspace_launch import HistoryReplay, _key, _project_history_dir, launch_workspace_cli, publish_workspace_history


class BoundLaunchTests(TestCase):
    """用相同会话名覆盖跨用户交付与恢复时的错绑。"""

    def setUp(self):
        """建立私有账号卷和两名主体之一的绑定。@return 无。"""
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.base = self.root / "tui-workspaces"
        self.base.mkdir(mode=0o700)
        self.source = (3, "环境", 8)
        self.client = r"\\files\开发组\代码 A"
        self.session = "同名会话"
        self.key = _key((self.source, self.session))
        self.cwd = self.base / _key((self.source, "project", self.client))
        self.cwd.mkdir(mode=0o700)
        self.record = self.base / (self.key + ".json")
        self.native = str(uuid4())
        self.record.write_text(
            json.dumps(
                {
                    "session_key": self.key,
                    "client_path": self.client,
                    "native_session_id": self.native,
                }
            )
        )
        self.record.chmod(0o600)
        self.who = dict(
            zip(("account_id", "environment_id", "principal_id"), self.source),
            session_id=self.session,
            reservation_id=str(uuid4()),
        )
        self.launch = {
            "version": 1,
            "work_dir": str(self.cwd),
            "binding_file": str(self.record),
            "native_session_id": self.native,
        }
        self.config = self.root / "config"
        self.history = (
            _project_history_dir(self.config, self.cwd)
            / (self.native + ".jsonl")
        )
        self.history.parent.mkdir(parents=True)

    def _start(self, *, resume=False, who=None, launch=None, prepare_history=None):
        command = {
            "action": "send",
            "reservation_id": self.who["reservation_id"],
            "workspace": launch or self.launch,
        }
        return launch_workspace_cli(
            who or self.who,
            command,
            program=Path("/fixture/official"),
            arguments=[],
            config_dir=self.config,
            environment={},
            resume=resume,
            terminal_fd=0,
            storage=self.root,
            prepare_history=prepare_history,
        )

    def test_wrong_subject_session_and_workspace_never_reach_spawn(self):
        """逐项交换提交、用户、路径与 UUID 时保留原绑定。@return 无。"""
        with patch("tui_workspace_launch.Popen") as spawn:
            for field, value in (
                ("principal_id", 9),
                ("account_id", 4),
                ("environment_id", "别处"),
                ("session_id", "其他会话"),
                ("reservation_id", str(uuid4())),
            ):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self._start(who={**self.who, field: value})
            for field, value in (
                ("native_session_id", str(uuid4())),
                ("work_dir", str(self.root)),
                ("binding_file", str(self.root)),
            ):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self._start(launch={**self.launch, field: value})
            spawn.assert_not_called()

    def test_resume_checks_stored_main_chain_and_missing_history(self):
        """缺失、空白或属于别处的原生记录不能恢复。@return 无。"""
        with patch("tui_workspace_launch.Popen") as spawn:
            with self.assertRaises(FileNotFoundError):
                self._start(resume=True)
            for records in (
                [],
                [
                    {
                        "type": "assistant",
                        "cwd": str(self.cwd),
                        "sessionId": str(uuid4()),
                    }
                ],
                [{"type": "user", "cwd": "/other", "sessionId": self.native}],
            ):
                self.history.write_text("".join(json.dumps(x) + "\n" for x in records))
                self.history.chmod(0o600)
                with self.assertRaises(ValueError):
                    self._start(resume=True)
            spawn.assert_not_called()
            self.history.write_text(
                json.dumps(
                    {"type": "user", "cwd": str(self.cwd), "sessionId": self.native}
                )
            )
            self._start(resume=True)
            self.assertIn("--resume", spawn.call_args.args[0])
            self.assertNotIn("--session-id", spawn.call_args.args[0])

    def test_run_uses_opened_local_directory_and_preserves_client_path(self):
        """真实启动参数中的目录来自账号卷，远程 UNC 原文只作描述。@return 无。"""

        def capture(argv, *, cwd, **kwargs):
            self.assertTrue(Path(cwd).samefile(self.cwd))
            self.assertNotIn(self.client, argv)
            self.assertEqual(argv[-2:], ["--session-id", self.native])
            self.assertEqual(kwargs["env"]["CLAUDE_CONFIG_DIR"], str(self.config))

        with patch("tui_workspace_launch.Popen", side_effect=capture):
            self._start()
        self.assertEqual(
            json.loads(self.record.read_text())["client_path"], self.client
        )
        self.record.unlink()
        self.record.symlink_to(self.history)
        with self.assertRaises(OSError):
            self._start()

    def test_auto_resume_only_when_the_bound_history_exists(self):
        """普通对话结束后重开时恢复原记录，损坏或跨项目的同名历史须报错。@return 无。"""
        with patch("tui_workspace_launch.Popen") as spawn:
            self._start(resume=None)
            self.assertEqual(spawn.call_args.args[0][-2:], ["--session-id", self.native])
            row = {"type": "assistant", "cwd": str(self.cwd), "sessionId": self.native}
            self.history.write_text(json.dumps(row))
            self.history.chmod(0o600)
            self._start(resume=None)
            self.assertEqual(spawn.call_args.args[0][-2:], ["--resume", str(self.history)])
            self.history.write_text(json.dumps({**row, "cwd": "/other"}))
            with self.assertRaises(ValueError):
                self._start(resume=None)
            self.history.unlink()
            self.history.symlink_to(self.record)
            with self.assertRaises(OSError):
                self._start(resume=None)
            self.assertEqual(spawn.call_count, 2)

    def test_import_returns_bound_session_for_standard_restart(self):
        """首次发布和再次启动均使用经过归属校验的原生记录。@return 无。"""
        # 真实账号进程继承 0077 umask，历史项目目录须为当前服务私有。
        self.history.parent.chmod(0o700)
        self.history.parent.parent.chmod(0o700)

        def prepare(config, work, native_id):
            self.assertEqual(native_id, self.native)
            return publish_workspace_history(config, work, native_id, lambda rows: bool(list(rows)), lambda sid: json.dumps(
                {"type": "user", "cwd": str(work), "sessionId": sid, "message": {"role": "user", "content": "合成历史"}}
            ) + "\n", boundary="fixture-boundary")

        with patch("tui_workspace_launch.Popen") as spawn:
            self._start(prepare_history=prepare, resume=None)
            snapshot = self.history.read_bytes()
            self.assertEqual(spawn.call_args.args[0][-2:], ["--resume", str(self.history)])
            self.who = {**self.who, "reservation_id": str(uuid4())}
            self._start(resume=True)
            self.assertEqual(spawn.call_args.args[0][-2:], ["--resume", str(self.history)])
            self._start(prepare_history=prepare, resume=None)
            self.assertEqual(spawn.call_args.args[0][-2:], ["--resume", str(self.history)])
            self._start(resume=None)
            self.assertEqual(spawn.call_args.args[0][-2:], ["--resume", str(self.history)])
            self.assertEqual(spawn.call_count, 4)
            self.assertEqual(list(self.history.parent.iterdir()), [self.history])
            self.assertEqual(self.history.read_bytes(), snapshot)

    def test_prepared_session_checks_fork_history_before_launch(self):
        """回调选中的分支执行与绑定历史一致的校验。@return 无。"""
        fork_id = str(uuid4())
        fork = self.history.with_name(fork_id + ".jsonl")
        row = {"type": "user", "cwd": str(self.cwd), "sessionId": fork_id}

        def prepare(config, work, native_id):
            self.assertEqual((config, work, native_id), (self.config, self.cwd, self.native))
            return fork_id

        with patch("tui_workspace_launch.Popen") as spawn:
            with self.assertRaises(FileNotFoundError):
                self._start(prepare_history=prepare, resume=None)
            for invalid in ({**row, "cwd": "/other"}, {**row, "sessionId": self.native}):
                fork.write_text(json.dumps(invalid))
                fork.chmod(0o600)
                for resume in (None, False):
                    with self.subTest(row=invalid, resume=resume), self.assertRaisesRegex(ValueError, "工作区不匹配"):
                        self._start(prepare_history=prepare, resume=resume)
            fork.write_text(json.dumps(row))
            fork.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "归属或权限"):
                self._start(prepare_history=prepare, resume=None)
            fork.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "已有历史记录"):
                self._start(prepare_history=prepare, resume=False)
            spawn.assert_not_called()

            self._start(prepare_history=prepare, resume=None)
            self.assertEqual(spawn.call_args.args[0][-2:], ["--resume", str(fork)])
            fork.unlink()
            self._start(prepare_history=prepare, resume=False)
            self.assertEqual(spawn.call_args.args[0][-2:], ["--session-id", fork_id])

    def test_replay_checks_both_the_archive_and_private_prefix(self):
        """临时前缀与账号档案均通过原生会话归属检查。@return 无。"""
        fork_id = str(uuid4())
        archive = self.history.with_name(fork_id + ".jsonl")
        replay_dir = self.config / "history-replay-fixture"
        replay_dir.mkdir(mode=0o700)
        prefix = replay_dir / archive.name
        row = {"type": "user", "cwd": str(self.cwd), "sessionId": fork_id}
        prefix.write_text(json.dumps(row))
        prefix.chmod(0o600)

        def prepare(config, work, native_id):
            return HistoryReplay(fork_id, prefix)

        with patch("tui_workspace_launch.Popen") as spawn:
            with self.assertRaises(FileNotFoundError):
                self._start(prepare_history=prepare, resume=True)
            archive.write_text(json.dumps(row))
            archive.chmod(0o600)
            prefix.write_text(json.dumps({**row, "sessionId": self.native}))
            with self.assertRaisesRegex(ValueError, "工作区不匹配"):
                self._start(prepare_history=prepare, resume=True)
            prefix.write_text(json.dumps(row))
            replay_dir.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "目录的归属或权限"):
                self._start(prepare_history=prepare, resume=True)
            replay_dir.chmod(0o700)
            spawn.assert_not_called()
            self._start(prepare_history=prepare, resume=True)
            self.assertEqual(spawn.call_args.args[0][-2:], ["--resume", str(prefix)])
