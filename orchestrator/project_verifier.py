"""在无凭据、无外网的临时容器中验证候选项目行为。"""
from __future__ import annotations

import json
import math
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from docker.types import LogConfig
from requests.exceptions import ReadTimeout

from project_library import canonical_json, digest_json


_EXECUTE = """import os,runpy,shutil,sys
shutil.copytree('/source','/work/project')
os.chdir('/work/project')
sys.path.insert(0,'/work/project')
sys.stdin=open('/request-data/input.jsonl',encoding='utf-8')
sys.argv=['app.py']
runpy.run_path('app.py',run_name='__main__')
"""


def _same_json(actual: object, expected: object) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6)
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(_same_json(actual[key], expected[key]) for key in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(_same_json(a, b) for a, b in zip(actual, expected))
    return actual == expected


class ProjectVerifier:
    """复用同批运行时镜像验证程序，不进入账号网络或 HOME。

    :param client: Docker SDK 客户端。
    :param data: 控制端数据根。
    :param host_data: Docker daemon 视角的数据根。
    :param image: 同批 account 镜像。
    """

    def __init__(self, client, data: Path, host_data: Path, image: str) -> None:
        """保存运行时依赖；参数契约见类说明。@return None。"""
        self.client, self.data, self.host_data, self.image = client, data, host_data, image
        self._slots = threading.Semaphore(2)

    def verify(self, candidate: Path, cases: list[dict], *, timeout: int = 30) -> dict:
        """运行冻结断言并在控制端生成判定。

        :param candidate: 控制端刚封存的只读候选副本。
        :param cases: 已通过项目内容校验的行为用例。
        :param timeout: 单次验证容器的秒数上限。
        :return: passed、failed 或 error 及有界证据。
        """
        suite_digest = digest_json(cases)
        payload = "".join(canonical_json(case["input"]).decode() + "\n" for case in cases)
        if len(payload.encode()) > 2 * 1024 * 1024:
            return {"status": "error", "message": "验收输入超过上限", "suite_digest": suite_digest}
        host_candidate = self.host_data / candidate.relative_to(self.data)
        container = None
        input_root = self.data / "project-verification-inputs"
        input_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        input_directory = Path(tempfile.mkdtemp(prefix="input-", dir=input_root))
        input_directory.chmod(0o755)
        (input_directory / "input.jsonl").write_text(payload, encoding="utf-8")
        (input_directory / "input.jsonl").chmod(0o644)
        host_input = self.host_data / input_directory.relative_to(self.data)
        with self._slots:
            try:
                container = self.client.containers.create(
                    self.image, name="bench-project-verifier-" + uuid.uuid4().hex[:12],
                    entrypoint=["python3", "-I", "-B", "-c"], command=[_EXECUTE],
                    user="1000:1000", working_dir="/work", network_mode="none", read_only=True,
                    cap_drop=["ALL"], security_opt=["no-new-privileges"],
                    mem_limit="256m", memswap_limit="256m", pids_limit=64,
                    tmpfs={"/work": "rw,nosuid,nodev,size=134217728,mode=1777",
                        "/tmp": "rw,nosuid,nodev,size=16777216,mode=1777"},
                    volumes={str(host_candidate): {"bind": "/source", "mode": "ro"},
                        str(host_input): {"bind": "/request-data", "mode": "ro"}},
                    environment={"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
                    log_config=LogConfig(type="json-file", config={"max-size": "2m", "max-file": "1"}),
                    labels={"vibebench.project-verifier": "1"},
                )
                container.start()
                try:
                    completed = container.wait(timeout=max(1, min(timeout, 60)))
                except ReadTimeout:
                    # 程序未在限定时间内退出属于候选行为，允许原项目的有限修复。
                    return {"status": "failed", "message": "程序超过验收时限",
                        "suite_digest": suite_digest}
                output = container.logs(stdout=True, stderr=False, tail=1024)
                errors = container.logs(stdout=False, stderr=True, tail=10)[-4096:]
                if len(output) > 2 * 1024 * 1024:
                    return {"status": "failed", "message": "程序输出超过验收上限", "suite_digest": suite_digest}
                if completed.get("StatusCode") != 0:
                    return {"status": "failed", "message": "被测程序未正常退出",
                        "stderr": errors.decode(errors="replace"), "suite_digest": suite_digest}
                try:
                    actual = [json.loads(line) for line in output.decode().splitlines() if line.strip()]
                    # JSON 的 NaN 等扩展不能绕过严格的预期结果比较。
                    canonical_json(actual)
                except (ValueError, UnicodeError):
                    return {"status": "failed", "message": "程序未输出约定的逐行 JSON", "suite_digest": suite_digest}
                failures = []
                if len(actual) != len(cases):
                    failures.append({"message": "响应数量不符", "expected_count": len(cases), "actual_count": len(actual)})
                for index, (reply, case) in enumerate(zip(actual, cases)):
                    if not _same_json(reply, case["expected"]):
                        failures.append({"case": index, "input": case["input"],
                            "expected": case["expected"], "actual": reply})
                    if len(failures) >= 3:
                        break
                return {"status": "failed" if failures else "passed", "suite_digest": suite_digest,
                    "case_count": len(cases), "failures": failures, "image": self.image}
            except Exception as error:
                # 基础设施故障不进入模型业务修复，也不能被误记为通过。
                return {"status": "error", "message": "独立验收环境失败：" + type(error).__name__,
                    "suite_digest": suite_digest}
            finally:
                if container is not None:
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass
                shutil.rmtree(input_directory, ignore_errors=True)
