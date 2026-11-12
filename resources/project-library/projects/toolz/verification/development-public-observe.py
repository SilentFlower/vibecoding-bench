"""独立运行交付的公开回归，要求实际收集并绑定当前候选源码。"""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse


def main():
    """运行冻结指定的公开测试文件，不接触账号或网络。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    report = Path('/tmp/development-public.xml')
    test = 'toolz/tests/test_development_padding.py'
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', test, '-p', 'no:cacheprovider',
        '--junitxml=' + str(report)], cwd=root / 'library',
        env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'), capture_output=True, timeout=25)
    cases = list(parse(report).getroot().iter('testcase')) if report.exists() else []
    failures = sum(bool(case.findall('failure') or case.findall('error') or case.findall('skipped')) for case in cases)
    bound = Path(importlib.import_module('toolz').__file__).resolve().is_relative_to(root / 'library')
    print(json.dumps({'passed': result.returncode == 0 and bound and bool(cases),
        'executed': len(cases), 'failures': failures}))


if __name__ == '__main__':
    main()
