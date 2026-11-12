"""独立执行本任务公开回归，核对实际收集数量及源码归属。"""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse

root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

report = Path('/tmp/test_click_exception.xml')
result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-o', 'addopts=', 'tests/test_exceptions/test_click_exception.py',
    '-k', 'test_order_error_notes_display_and_unnoted_control or test_order_usage_notes_keep_exit_and_usage', '-p', 'no:cacheprovider', '--junitxml=' + str(report)], cwd=root / 'library',
    env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'), capture_output=True, timeout=25)
cases = list(parse(report).getroot().iter('testcase')) if report.exists() else []
failures = sum(bool(case.findall('failure') or case.findall('error') or case.findall('skipped')) for case in cases)
bound = Path(importlib.import_module('click').__file__).resolve().is_relative_to(root / 'library')
print(json.dumps({'passed': result.returncode == 0 and bound and bool(cases),
    'executed': len(cases), 'failures': failures}))
