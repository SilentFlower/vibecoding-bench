"""独立核对参考交付的公开回归确实执行。"""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse


def main():
    """运行新公开文件，验证收集、失败与实际源码绑定。@return None。"""
    root = Path(os.environ["PROJECT_CANDIDATE_ROOT"]).resolve()
    report = Path("/tmp/development-public.xml")
    completed = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_development_cycle.py", "--junitxml=" + str(report)],
        cwd=root / "library", env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"), capture_output=True, timeout=30)
    cases = list(parse(report).getroot().iter("testcase")) if report.exists() else []
    failures = sum(bool(case.findall("failure") or case.findall("error") or case.findall("skipped")) for case in cases)
    bound = Path(importlib.import_module("frontmatter").__file__).resolve().is_relative_to(root / "library")
    print(json.dumps({"passed": completed.returncode == 0 and bound and bool(cases), "executed": len(cases), "failures": failures}))


if __name__ == "__main__":
    main()
