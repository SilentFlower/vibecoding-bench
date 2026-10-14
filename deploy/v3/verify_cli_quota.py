#!/usr/bin/env python3
"""隔离运行指定官方 CLI，比较采集前后的请求及状态栏输出。"""
import argparse
import json
import shutil
import tempfile
from pathlib import Path

import docker


def verify(image: str, binary: Path) -> None:
    """在无外部网络、空 HOME 和合成凭据下核实官方本地额度入口。

    :param image: 本地账号镜像
    :param binary: 已安装的官方 CLI 原生二进制；不下载、不读取真实凭据
    :return: None；字段、原输出或请求计数不符时抛出异常
    """
    repository = Path(__file__).resolve().parents[2]
    fixtures = repository / "deploy/v3/fixtures"
    client = docker.from_env()
    results = {}
    with tempfile.TemporaryDirectory(prefix="v3-official-quota-") as temporary:
        for mode in ("baseline", "collected"):
            root = Path(temporary) / mode
            root.mkdir()
            shutil.copy2(fixtures / "official_cli_quota.py", root / "run.py")
            shutil.copy2(fixtures / "quota_statusline.py", root / "wrapper.py")
            container = client.containers.run(image, ["/lab/run.py"], entrypoint="python3", detach=True,
                network_mode="none", environment={"LAB_COLLECTOR": "1" if mode == "collected" else "0"},
                labels={"vibebench.verification": "official-cli-quota"},
                volumes={str(root): {"bind": "/lab", "mode": "rw"},
                    str(binary.resolve()): {"bind": "/official/claude", "mode": "ro"}})
            try:
                result = container.wait(timeout=60)
                assert result["StatusCode"] == 0, "官方 CLI 隔离演练失败"
                results[mode] = json.loads(container.logs().decode().splitlines()[-1])
                assert b"ORIGINAL_STATUSLINE" in (root / "terminal.log").read_bytes(), "原状态栏输出丢失"
                assert not (root / "collector-errors.log").exists(), "本地采集脚本出现错误"
            finally:
                container.remove(force=True)
        baseline, collected = results["baseline"], results["collected"]
        assert baseline["version"] == collected["version"]
        assert baseline["requests"] and baseline["requests"] == collected["requests"], "采集增加了网络请求"
        assert all("usage" not in item["path"] for item in collected["requests"]), "出现主动额度查询"
        events = [json.loads(line) for line in (collected["quota"] or "").splitlines()]
        assert len(events) == 1, "正常响应未产生唯一被动观察"
        event = events[0]
        assert event["source"] == "cli:run:synthetic-official" and event["identity"] == "synthetic-identity"
        assert event["rate_limits"]["five_hour"]["used_percentage"] == 42
        assert event["rate_limits"]["seven_day"]["used_percentage"] == 35
        assert collected["statusline_calls"] >= 2, "未覆盖启动未知和首次正常响应"
        print(f"通过：官方 {collected['version']} 本地采集 5h 42%／7d 35%，原输出保留；"
            f"前后各 {len(collected['requests'])} 次相同模型请求，零 usage，Docker 外网禁用")


def main() -> None:
    """解析本地镜像和官方二进制位置并执行验证，返回 None。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-image", required=True)
    parser.add_argument("--cli-binary", type=Path, required=True)
    arguments = parser.parse_args()
    verify(arguments.account_image, arguments.cli_binary)


if __name__ == "__main__":
    main()
