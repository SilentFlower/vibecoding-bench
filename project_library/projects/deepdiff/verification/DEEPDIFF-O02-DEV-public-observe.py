"""独立执行本任务公开回归，核对实际收集数量及源码归属。"""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse

root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['deepdiff']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

report = Path('/tmp/test_development_deepdiff_o02_dev.xml')
result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-o', 'addopts=', 'tests/test_development_deepdiff_o02_dev.py',
    '-p', 'no:cacheprovider', '--junitxml=' + str(report)], cwd=root / 'library',
    env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'), capture_output=True, timeout=25)
cases = list(parse(report).getroot().iter('testcase')) if report.exists() else []
failures = sum(bool(case.findall('failure') or case.findall('error') or case.findall('skipped')) for case in cases)
bound = Path(importlib.import_module('deepdiff').__file__).resolve().is_relative_to(root / 'library')
print(json.dumps({'passed': result.returncode == 0 and bound and bool(cases),
    'executed': len(cases), 'failures': failures}))
