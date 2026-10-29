"""只复核固定终端宽度后的业务校准，不重复已通过的完整原生集合。"""
import json
import os
from pathlib import Path
import resource
import runpy
import shutil
import subprocess
import sys
import traceback


_HELPERS = runpy.run_path("/environment/verify_target.py", run_name="typer_native_helpers")
_write = _HELPERS["_write"]
_command = _HELPERS["_command"]
_progress = _HELPERS["_progress"]


def main() -> None:
    """运行各业务正反例并输出独立证据。@return None。"""
    root = Path("/work/project")
    shutil.copytree("/input/seed", root)
    Path("/work/home").mkdir()
    Path("/work/temporary").mkdir()
    environment = dict(os.environ)
    environment.update(HOME="/work/home", TMPDIR="/work/temporary", PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1", PIP_CONFIG_FILE="/dev/null", PIP_NO_CACHE_DIR="1", NO_COLOR="1",
        TERM="dumb", TERMINAL_WIDTH="80", _TYPER_FORCE_DISABLE_TERMINAL="1")
    profile = json.loads(Path("/environment/profile/profile.json").read_text())
    _progress("prepare-business")
    created = _command("create-venv", [sys.executable, "-B", "-m", "venv", "/work/venv"],
        root, environment, 120)
    if created["exit_code"]:
        raise RuntimeError("无法准备业务验证环境")
    python = "/work/venv/bin/python"
    environment.update(PATH="/work/venv/bin:" + environment.get("PATH", ""),
        PYTHONPATH=str(root / "library"), PROJECT_CANDIDATE_ROOT=str(root))
    installed = _command("install-offline", [python, "-B", "-m", "pip", "install", "--no-index",
        "--no-deps", "--find-links", "/environment/artifacts", *profile["requirements"]],
        root, environment, 180)
    if installed["exit_code"]:
        raise RuntimeError("固定离线依赖准备失败")
    purelib = subprocess.run([python, "-B", "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
        capture_output=True, text=True, check=True, env=environment, timeout=15).stdout.strip()
    (Path(purelib) / "typer_candidate_source.pth").write_text(str(root / "library") + "\n", encoding="utf-8")
    _command("runtime", [python, "-B", "-c",
        "import json,sys,typer;print(json.dumps({'python':sys.version,'typer':typer.__version__,'typer_file':typer.__file__}))"],
        root, environment, 30)
    manifest = json.loads(Path("/input/project.json").read_text())
    for item in manifest["scenarios"][3]["tasks"][0]["setup"]:
        destination = root / item["target"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path("/input") / item["source"], destination)
    records = []
    _progress("business-calibration")
    for mode in ("consult", "single", "group", "types", "export"):
        for name in (("baseline", "reference") if mode == "export" else ("baseline",)):
            if name == "reference":
                reference = Path("/input/verification/reference")
                for path in reference.rglob("*"):
                    if path.is_file() and path.suffix in (".py", ".md") and path.name != "consult_answer.md":
                        destination = root / "app" / path.relative_to(reference)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(path, destination)
            arguments = [python, "-B", "/input/verification/native_checks.py", "--mode", mode,
                "--candidate-root", str(root)]
            if mode == "consult":
                arguments.extend(["--answer-file", "/input/verification/reference/consult_answer.md"])
            entry = _command(name + "-" + mode, arguments, root, environment, 180)
            actual = json.loads(Path("/evidence/" + name + "-" + mode + ".stdout.log").read_text())
            expected = json.loads(Path("/input/verification/native/" + mode + ".json").read_text())["expected"]
            entry.update(mode=mode, candidate=name, matches_expected=actual == expected,
                expected_baseline_failure=mode == "export" and name == "baseline")
            records.append(entry)
    answer = Path("/input/verification/reference/consult_answer.md").read_text()
    negatives = {"negative_quantity_allowed": answer.replace("typer.Option(min=0)", "typer.Option()"),
        "no_program": "需要先修改Typer才能支持这个命令。",
        "ambiguous_programs": answer + "\n" + answer.replace("min=0", "min=1")}
    negative_results = []
    expected = json.loads(Path("/input/verification/native/consult.json").read_text())["expected"]
    for name, text in negatives.items():
        answer_path = Path("/work/" + name + ".md")
        answer_path.write_text(text, encoding="utf-8")
        entry = _command("negative-" + name, [python, "-B", "/input/verification/native_checks.py",
            "--mode", "consult", "--candidate-root", str(root), "--answer-file", str(answer_path)],
            root, environment, 180)
        actual = json.loads(Path("/evidence/negative-" + name + ".stdout.log").read_text())
        entry.update(case=name, rejected=actual != expected)
        negative_results.append(entry)
    tests = _command("reference-user-tests", [python, "-B", "-m", "unittest", "discover",
        "-s", str(root / "app/tests"), "-v"], root, environment, 60)
    for name, arguments in (("root-help", ["--help"]), ("export-help", ["export", "--help"])):
        _command(name, [python, "-B", "/input/disclosure/TY-D02/shop.py", *arguments], root, environment, 30)
    passed = all(entry["exit_code"] == 0 and (not entry["matches_expected"]
        if entry["expected_baseline_failure"] else entry["matches_expected"]) for entry in records)
    passed = passed and all(entry["exit_code"] == 0 and entry["rejected"] for entry in negative_results)
    passed = passed and tests["exit_code"] == 0
    _write("business-calibration-result.json", {"passed": passed, "records": records,
        "negative_results": negative_results, "user_reference_tests": tests, "model_runs": 0})
    peak = Path("/sys/fs/cgroup/memory.peak")
    _write("container-resources.json", {"uid": os.getuid(), "gid": os.getgid(),
        "cgroup_memory_peak_bytes": int(peak.read_text()) if peak.exists() else None,
        "max_rss_children_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss})
    if not passed:
        raise RuntimeError("业务正反例或参考应用用户测试没有通过")
    _write("target-result.json", {"status": "passed", "model_runs": 0,
        "evidence_scope": "固定终端宽度后的独立业务校准；不重复原生全套、不代表模型能力"})
    _progress("completed")


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        _write("target-result.json", {"status": "error", "type": type(error).__name__, "message": str(error)})
        traceback.print_exc()
        raise
