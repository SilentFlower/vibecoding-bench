"""验证 worker 首次权限引导不会改变指定模式或吞掉原始题目。"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


class WorkerStartupTests(unittest.TestCase):
    """通过终端替身执行真实 shell 函数，验证首次启动时序。"""

    def setUp(self) -> None:
        """
        准备独立终端状态目录和真实入口脚本。

        :return: None
        """
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.source = (
            Path(__file__).resolve().parents[1] / "images/worker/entrypoint.sh"
        ).read_text(encoding="utf-8")

    def _functions(self, *names: str) -> str:
        """
        提取入口脚本函数，避免执行 CA 安装和真实 Claude 进程。

        :param names: 已存在的 shell 函数名
        :return: 可以直接由 bash 执行的函数定义
        """
        definitions = []
        for name in names:
            match = re.search(
                rf"^{name}\(\) \{{.*?^\}}$", self.source, re.MULTILINE | re.DOTALL
            )
            self.assertIsNotNone(match, name)
            definitions.append(match.group(0))
        return "\n".join(definitions).replace("/tmp/", f"{self.base}/")

    def _submit_after_auto_offer(self, mode: str, stuck: bool = False) -> subprocess.CompletedProcess:
        """
        模拟 Auto 推荐菜单：回车接受 Auto，取消保留模式，菜单期间丢弃粘贴。

        :param mode: 当前任务指定的权限模式
        :param stuck: 是否模拟菜单收到取消后仍未消失
        :return: 实际入口函数的执行结果
        """
        (self.base / "mode").write_text(mode, encoding="utf-8")
        script = r'''
set -euo pipefail
SESSION=test-session
log() { :; }
sleep() { :; }
tmux() {
  case "$1" in
    has-session) return 0 ;;
    capture-pane)
      if [ ! -f "$TEST_STATE/declined" ]; then
        printf '%s\n' 'Make auto mode your default permission mode?' \
          'Yes, set auto mode as my default permission mode' 'No, keep the current mode'
      else
        printf '%s\n' 'Claude Code' '❯ 输入任务'
      fi
      ;;
    load-buffer) cp "${@: -1}" "$TEST_STATE/buffer" ;;
    paste-buffer)
      if [ -f "$TEST_STATE/declined" ]; then
        cp "$TEST_STATE/buffer" "$TEST_STATE/draft"
      fi
      ;;
    send-keys)
      printf '%s\n' "${@: -1}" >> "$TEST_STATE/keys"
      if [ "${@: -1}" = Escape ]; then
        [ "$TEST_STUCK" = 1 ] || touch "$TEST_STATE/declined"
      elif [ "${@: -1}" = Enter ]; then
        if [ ! -f "$TEST_STATE/declined" ]; then
          printf auto > "$TEST_STATE/mode"
          touch "$TEST_STATE/declined"
        else
          cp "$TEST_STATE/draft" "$TEST_STATE/submitted"
        fi
      fi
      ;;
  esac
}
'''
        script += self._functions("handle_claude_startup_gates", "inject_tmux_prompt")
        script += '\nhandle_claude_startup_gates && inject_tmux_prompt prompt "$TEST_PROMPT"\n'
        return subprocess.run(
            ["bash", "-c", script],
            env={
                **os.environ,
                "TEST_STATE": str(self.base),
                "TEST_STUCK": "1" if stuck else "0",
                "TEST_PROMPT": "题目：保持原始内容\n不要替换题目。",
            },
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_auto_offer_preserves_mode_and_submits_original_prompt(self) -> None:
        """
        普通 bypass 和显式 Auto 任务都应保留模式，并真正提交原始题目。

        :return: None
        """
        for mode in ("bypassPermissions", "auto", "plan"):
            with self.subTest(mode=mode):
                for path in self.base.iterdir():
                    path.unlink()
                result = self._submit_after_auto_offer(mode)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(mode, (self.base / "mode").read_text())
                self.assertTrue((self.base / "submitted").exists())
                self.assertEqual(
                    "题目：保持原始内容\n不要替换题目。",
                    (self.base / "submitted").read_text(),
                )

    def test_uncleared_auto_offer_prevents_prompt_submission(self) -> None:
        """
        推荐菜单未消失时应启动失败，不能把题目的回车发给菜单。

        :return: None
        """
        result = self._submit_after_auto_offer("bypassPermissions", stuck=True)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse((self.base / "submitted").exists())
        self.assertEqual("bypassPermissions", (self.base / "mode").read_text())

    def test_top_config_skips_auto_offer_and_preserves_identity(self) -> None:
        """
        worker 补齐推荐标记时应保留账号身份和原有项目状态。

        :return: None
        """
        initial = {
            "oauthAccount": {"accountUuid": "测试账号"},
            "hasSeenAutoDefaultNudge": False,
            "projects": {"/workspace": {"allowedTools": ["Read"]}},
        }
        path = self.base / ".claude.json"
        path.write_text(json.dumps(initial), encoding="utf-8")
        result = subprocess.run(
            ["bash", "-c", self._functions("patch_top_config_gates") + "\npatch_top_config_gates"],
            env={**os.environ, "CLAUDE_HOME": str(self.base)},
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        persisted = json.loads(path.read_text())
        self.assertTrue(persisted["hasSeenAutoDefaultNudge"])
        self.assertEqual(initial["oauthAccount"], persisted["oauthAccount"])
        self.assertEqual(["Read"], persisted["projects"]["/workspace"]["allowedTools"])
