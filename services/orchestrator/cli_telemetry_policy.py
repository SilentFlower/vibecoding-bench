"""统一官方 Claude Code CLI 的遥测与错误上报策略。"""
import os


def cli_telemetry_mode(value: str | None = None) -> str:
    """校验部署策略。@param value 显式值；None 读取环境。@return off 或 on。"""
    mode = (os.environ.get("V3_CLI_TELEMETRY", "") if value is None else value).strip() or "off"
    if mode not in ("off", "on"):
        raise ValueError("V3_CLI_TELEMETRY 必须为 off 或 on")
    return mode


def cli_telemetry_environment(environment: dict[str, str]) -> dict[str, str]:
    """投影官方 CLI 的受控环境。@param environment 原环境。@return 应用策略后的副本。"""
    result = dict(environment)
    mode = cli_telemetry_mode()
    for key in ("DISABLE_TELEMETRY", "DISABLE_ERROR_REPORTING"):
        if mode == "off":
            result[key] = "1"
        else:
            # 官方按非空值关闭上报，恢复默认许可必须删除关闭键，不能写入 0。
            result.pop(key, None)
    return result
