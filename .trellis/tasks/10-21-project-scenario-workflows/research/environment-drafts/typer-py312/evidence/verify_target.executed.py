"""在本任务专属无网络容器中核对离线环境、原生测试和业务候选。

@param /input 只读 Typer 场景内容草案。
@param /environment 只读离线制品与环境档案。
@param /evidence 本次专属容器的持久输出目录。
@return 写入真实运行证据；任一步失败时非零结束。
"""
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET


_EVIDENCE = Path("/evidence")


def _write(name: str, value: object) -> None:
    temporary = _EVIDENCE / (name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(_EVIDENCE / name)


def _progress(stage: str) -> None:
    _write("progress.json", {"stage": stage, "time": time.time()})
    print(stage, flush=True)


def _command(name: str, arguments: list[str], cwd: Path, environment: dict, timeout: int) -> dict:
    started = time.monotonic()
    with (_EVIDENCE / (name + ".stdout.log")).open("w") as output, (
            _EVIDENCE / (name + ".stderr.log")).open("w") as errors:
        completed = subprocess.run(arguments, cwd=cwd, env=environment, stdout=output,
            stderr=errors, timeout=timeout, check=False)
    result = {"command": arguments, "cwd": str(cwd), "exit_code": completed.returncode,
        "elapsed_sec": round(time.monotonic() - started, 6)}
    _write(name + ".command.json", result)
    return result


def main() -> None:
    """以冻结依赖验证目标镜像，分开记录测试与模型证据。@return None。"""
    _progress("prepare")
    root = Path("/work/project")
    shutil.copytree("/input/seed", root)
    profile = json.loads(Path("/environment/profile/profile.json").read_text())
    environment = dict(os.environ)
    home = Path("/work/home")
    home.mkdir()
    (home / ".config").mkdir()
    Path("/work/temporary").mkdir()
    environment.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
        TMPDIR="/work/temporary", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
        PIP_CONFIG_FILE="/dev/null", PIP_NO_CACHE_DIR="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    result = _command("create-venv", [sys.executable, "-B", "-m", "venv", "/work/venv"],
        root, environment, 120)
    if result["exit_code"]:
        raise RuntimeError("目标镜像无法准备独立venv")
    python = "/work/venv/bin/python"
    environment.update(PATH="/work/venv/bin:" + environment.get("PATH", ""),
        PYTHONPATH=str(root / "library"))
    _progress("install-offline")
    result = _command("install-offline", [python, "-B", "-m", "pip", "install", "--no-index",
        "--no-deps", "--find-links", "/environment/artifacts", *profile["requirements"]],
        root, environment, 180)
    if result["exit_code"]:
        raise RuntimeError("冻结离线制品安装失败")
    # 上游测试会主动替换子进程PYTHONPATH，venv的.pth需始终指向这份候选源码。
    registered = subprocess.run([python, "-B", "-c",
        "import sysconfig;print(sysconfig.get_paths()['purelib'])"], cwd=root, env=environment,
        capture_output=True, text=True, timeout=15, check=True)
    source_registration = Path(registered.stdout.strip()) / "typer_candidate_source.pth"
    source_registration.write_text(str(root / "library") + "\n", encoding="utf-8")
    _write("source-registration.json", {"kind": "venv-pth", "path": str(source_registration),
        "source": str(root / "library"), "upstream_source_modified": False})
    _command("runtime", [python, "-B", "-c",
        "import json,platform,sys,typer;print(json.dumps({'python':sys.version,'platform':platform.platform(),'typer':typer.__version__,'typer_file':typer.__file__}))"],
        root, environment, 30)
    environment.update(TERMINAL_WIDTH="3000", _TYPER_FORCE_DISABLE_TERMINAL="1",
        _TYPER_RUN_INSTALL_COMPLETION_TESTS="1", CONTEXT="typer-scenario-target-runtime")
    command = [python, "-B", "-m", "pytest", "--cov", "--cov-report=term-missing", "-o",
        "console_output_style=progress", "--showlocals", "--numprocesses=2", "-ra"]
    # 保留真实Bash祖先，让上游completion测试按真实shell条件执行，不改skip装饰器。
    shell = ["bash", "-c", '"$@" & child=$!; wait "$child"', "typer-native"]
    _progress("affected-environment-preflight")
    preflight = _command("environment-preflight", [*shell, *command,
        "tests/test_tutorial/test_subcommands/test_tutorial001.py::test_scripts",
        "tests/test_tutorial/test_subcommands/test_tutorial003.py::test_scripts",
        "tests/test_completion/test_completion.py::test_show_completion",
        "tests/test_completion/test_completion.py::test_install_completion",
        "--junitxml=/evidence/environment-preflight.xml"], root / "library", environment, 120)
    if preflight["exit_code"]:
        raise RuntimeError("源码注册与Bash祖先的针对性环境检查没有通过")
    _progress("full-native-regression")
    command = [*shell, *command, "--junitxml=/evidence/native-tests.xml"]
    regression = _command("native-tests", command, root / "library", environment, 600)
    if not (_EVIDENCE / "native-tests.xml").is_file():
        raise RuntimeError(f"pytest在输出JUnit前退出，退出码{regression['exit_code']}；具体环境原因见原始stderr")
    cases = list(ET.parse(_EVIDENCE / "native-tests.xml").getroot().iter("testcase"))
    counts = {"total": len(cases), "passed": 0, "skipped": 0, "xfailed": 0, "failures": 0, "errors": 0}
    for case in cases:
        if case.find("failure") is not None:
            counts["failures"] += 1
        elif case.find("error") is not None:
            counts["errors"] += 1
        elif case.find("skipped") is not None:
            key = "xfailed" if case.find("skipped").get("type") == "pytest.xfail" else "skipped"
            counts[key] += 1
        else:
            counts["passed"] += 1
    regression.update(counts=counts, max_rss_children_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        environment={key:environment[key] for key in ("HOME", "XDG_CONFIG_HOME", "PYTHONPATH", "TERMINAL_WIDTH",
            "_TYPER_FORCE_DISABLE_TERMINAL", "_TYPER_RUN_INSTALL_COMPLETION_TESTS", "CONTEXT")})
    _write("native-regression-result.json", regression)
    if regression["exit_code"]:
        raise RuntimeError("完整适用原生集合没有通过，保留实际日志")
    _progress("business-calibration")
    environment.update(NO_COLOR="1", TERM="dumb", PROJECT_CANDIDATE_ROOT=str(root))
    manifest = json.loads(Path("/input/project.json").read_text())
    for item in manifest["scenarios"][3]["tasks"][0]["setup"]:
        destination = root / item["target"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path("/input") / item["source"], destination)
    records = []
    for mode in ("consult", "single", "group", "types", "export"):
        names = ("baseline", "reference") if mode == "export" else ("baseline",)
        for name in names:
            if name == "reference":
                reference = Path("/input/verification/reference")
                for path in reference.rglob("*"):
                    if path.is_file() and path.suffix in (".py", ".md") and path.name != "consult_answer.md":
                        destination = root / "app" / path.relative_to(reference)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(path, destination)
            arguments = [python, "-B", "/input/verification/native_checks.py", "--candidate-root", str(root),
                "--mode", mode]
            if mode == "consult":
                arguments.extend(["--answer-file", "/input/verification/reference/consult_answer.md"])
            entry = _command(name + "-" + mode, arguments, root, environment, 180)
            output = json.loads((_EVIDENCE / (name + "-" + mode + ".stdout.log")).read_text())
            expected = json.loads(Path("/input/verification/native/" + mode + ".json").read_text())["expected"]
            entry.update(mode=mode, candidate=name, matches_expected=output == expected,
                expected_baseline_failure=mode == "export" and name == "baseline")
            records.append(entry)
    for name, arguments in (("root-help", ["--help"]), ("export-help", ["export", "--help"])):
        _command(name, [python, "-B", "/input/disclosure/TY-D02/shop.py", *arguments],
            root, environment, 30)
    passed = all(entry["exit_code"] == 0 and (not entry["matches_expected"]
        if entry["expected_baseline_failure"] else entry["matches_expected"]) for entry in records)
    _write("business-calibration-result.json", {"passed": passed, "records": records, "model_runs": 0})
    peak = Path("/sys/fs/cgroup/memory.peak")
    _write("container-resources.json", {"uid": os.getuid(), "gid": os.getgid(),
        "cgroup_memory_peak_bytes": int(peak.read_text()) if peak.exists() else None,
        "max_rss_children_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "max_rss_note": "子进程生命周期高水位，不是所有进程RSS之和；容器峰值另读cgroup。"})
    if not passed:
        raise RuntimeError("业务原版/参考候选校准与冻结结果不符")
    _write("target-result.json", {"status": "passed", "native": regression, "business_passed": passed,
        "model_runs": 0, "evidence_scope": "目标镜像离线环境、完整原生集合与控制端参考业务候选，不是模型完成成绩"})
    _progress("completed")


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        _write("target-result.json", {"status": "error", "type": type(error).__name__, "message": str(error),
            "model_runs": 0})
        traceback.print_exc()
        raise
