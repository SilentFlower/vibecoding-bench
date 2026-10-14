"""验证真实形状的 CLI 本地采集，避免缓存刷新及旧会话伪造新观察。"""
import json
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cli_quota import collect_statusline, statusline_quota_observation


class CliQuotaTests(unittest.TestCase):
    """使用本地真实文件验证采集和状态栏命令，参数及返回值见各方法。"""

    def setUp(self) -> None:
        """创建专用会话与观察目录，返回 None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = time.time()
        self.session = "synthetic-session"
        self.transcript = self.root / (self.session + ".jsonl")
        self.configuration = {"source": "cli:run:synthetic:0", "identity": "synthetic-identity",
            "cwd": "/home/node/projects/project-synthetic", "session_dir": str(self.root),
            "output": str(self.root / "cli-quota.jsonl"), "started_at": self.now - 1}
        self.payload = {"session_id": self.session, "cwd": self.configuration["cwd"],
            "transcript_path": str(self.transcript), "rate_limits": {
                "five_hour": {"used_percentage": 0, "resets_at": self.now + 3600},
                "seven_day": {"used_percentage": 35, "resets_at": self.now + 86400}}}
        self.response = {"type": "assistant", "sessionId": self.session,
            "timestamp": datetime.fromtimestamp(self.now, timezone.utc).isoformat(),
            "message": {"role": "assistant", "id": "response-1", "model": "synthetic-model", "content": []}}
        self.transcript.write_text(json.dumps(self.response) + "\n")

    def test_zero_value_and_exact_percent_are_preserved(self) -> None:
        """百分比不重复乘百，0% 保留，返回 None。"""
        observation = statusline_quota_observation(self.payload["rate_limits"], self.now)
        self.assertEqual(0, observation["windows"]["five_hour"]["utilization"])
        self.assertEqual(35, observation["windows"]["seven_day"]["utilization"])
        self.assertFalse(observation["windows"]["five_hour"]["exhausted"])

    def test_invalid_and_expired_windows_do_not_become_zero(self) -> None:
        """缺失／非法／过期窗口保持未知，返回 None。"""
        for used in (True, -1, 101, float("nan"), float("inf"), "20"):
            observation = statusline_quota_observation({"five_hour": {
                "used_percentage": used, "resets_at": self.now + 3600}}, self.now)
            self.assertEqual({}, observation["windows"])
        for reset in (None, True, self.now - 1, self.now + 10 * 86400):
            self.assertEqual({}, statusline_quota_observation({"five_hour": {
                "used_percentage": 0, "resets_at": reset}}, self.now)["windows"])

    def test_new_response_is_recorded_once_without_stdin_contents(self) -> None:
        """同一正常响应去重，不记录完整输入、工具内容或外部字段。@return None。"""
        self.payload["unrelated"] = "不得保存的完整内容"
        self.assertTrue(collect_statusline(self.payload, self.configuration, self.now))
        self.assertFalse(collect_statusline(self.payload, self.configuration, self.now + 10))
        output = Path(self.configuration["output"])
        self.assertEqual(1, len(output.read_text().splitlines()))
        event = json.loads(output.read_text())
        self.assertAlmostEqual(self.now, event["ts"], delta=0.000001)
        self.assertEqual(self.configuration["source"], event["source"])
        self.assertNotIn("unrelated", event)
        self.assertNotIn("message", event)

    def test_startup_cache_and_synthetic_response_are_ignored(self) -> None:
        """旧响应和认证错误不能被状态栏缓存解释成新允许观察。@return None。"""
        self.configuration["started_at"] = self.now + 1
        self.assertFalse(collect_statusline(self.payload, self.configuration, self.now + 2))
        self.configuration["started_at"] = self.now - 1
        self.response["isApiErrorMessage"] = True
        self.response["message"]["model"] = "<synthetic>"
        self.transcript.write_text(json.dumps(self.response) + "\n")
        self.assertFalse(collect_statusline(self.payload, self.configuration, self.now))

    def test_other_project_or_session_is_rejected(self) -> None:
        """不能把其他项目或会话样本写入当前执行，返回 None。"""
        self.payload["cwd"] = "/other"
        self.assertFalse(collect_statusline(self.payload, self.configuration, self.now))
        self.payload["cwd"] = self.configuration["cwd"]
        self.response["sessionId"] = "other"
        self.transcript.write_text(json.dumps(self.response) + "\n")
        self.assertFalse(collect_statusline(self.payload, self.configuration, self.now))

    def test_original_statusline_receives_stdin_and_keeps_its_output(self) -> None:
        """执行真实采集命令并保留原状态栏输出，不使用网络。@return None。"""
        self.configuration["previous_command"] = "python3 -c 'import sys,json; print(json.load(sys.stdin)[\"session_id\"])'"
        path = self.root / "config.json"
        path.write_text(json.dumps(self.configuration))
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("cli_quota.py")),
            "--config", str(path)], input=json.dumps(self.payload), text=True, capture_output=True, check=True)
        self.assertEqual(self.session, result.stdout.strip())
        self.assertTrue(Path(self.configuration["output"]).is_file())


if __name__ == "__main__":
    unittest.main()
