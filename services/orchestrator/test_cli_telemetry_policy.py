"""验证官方 CLI 遥测配置、环境投影及子命令启动边界。"""
import os
import unittest
from unittest.mock import patch

from cli_telemetry_policy import cli_telemetry_environment, cli_telemetry_mode
import main


class CliTelemetryPolicyTests(unittest.TestCase):
    """覆盖默认关闭、恢复许可及非法部署值。"""

    def test_default_and_off_override_existing_flags(self) -> None:
        """空值与 off 均覆盖旧关闭键且保留其它配置。@return None。"""
        for value in (None, "", "off"):
            with self.subTest(value=value), patch.dict(os.environ, {}, clear=True):
                if value is not None:
                    os.environ["V3_CLI_TELEMETRY"] = value
                original = {"DISABLE_TELEMETRY": "0", "DISABLE_ERROR_REPORTING": "false", "OTHER": "keep"}
                actual = cli_telemetry_environment(original)
                self.assertEqual("off", cli_telemetry_mode())
                self.assertEqual({"DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1", "OTHER": "keep"}, actual)
                self.assertEqual("0", original["DISABLE_TELEMETRY"])

    def test_on_removes_disable_keys_from_final_exec_environment(self) -> None:
        """额外参数里的历史关闭键也由最终策略清理。@return None。"""
        with patch.dict(os.environ, {"V3_CLI_TELEMETRY": "on"}):
            actual = main._claude_exec_env(False, {"DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
                "CLAUDE_CODE_VERSION": "2.1.293", "DISABLE_AUTOUPDATER": "1"})
        self.assertNotIn("DISABLE_TELEMETRY", actual)
        self.assertNotIn("DISABLE_ERROR_REPORTING", actual)
        self.assertEqual("1", actual["DISABLE_AUTOUPDATER"])
        self.assertEqual("2.1.293", actual["CLAUDE_CODE_VERSION"])

    def test_invalid_configuration_is_rejected(self) -> None:
        """非法值在策略入口明确拒绝。@return None。"""
        for value in ("0", "false", "OFF", "unknown"):
            with self.subTest(value=value), patch.dict(os.environ, {"V3_CLI_TELEMETRY": value}):
                with self.assertRaisesRegex(ValueError, "V3_CLI_TELEMETRY"):
                    cli_telemetry_environment({})
