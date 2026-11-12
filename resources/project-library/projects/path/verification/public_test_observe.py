"""执行两个真实公开取消回归，核候选导入和逐项失败证据。"""
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse

import path


def main() -> None:
    """核真实用例身份与结果，不用退出码替代节点。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    report = Path('/tmp/path-public-tests.xml')
    names = {'test_in_place_recovers_original_after_keyboard_interrupt', 'test_in_place_recovers_original_after_system_exit'}
    arguments = [sys.executable, '-m', 'pytest', '-q',
        *['tests/test_path.py::' + name for name in sorted(names)], '--junitxml=' + str(report)]
    result = subprocess.run(arguments, cwd=root / 'library',
        env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'), capture_output=True, timeout=15)
    cases = list(parse(report).getroot().iter('testcase')) if report.is_file() else []
    counts = {'tests': len(cases), 'failed': sum(len(case.findall('failure')) for case in cases),
        'errors': sum(len(case.findall('error')) for case in cases), 'skipped': sum(len(case.findall('skipped')) for case in cases)}
    failures = [{'test': case.attrib['name'], 'message': child.attrib.get('message', '')[:1000]}
        for case in cases for child in case if child.tag in ('failure', 'error')]
    print(json.dumps({'candidate_import': Path(path.__file__).resolve() == root / 'library/path/__init__.py',
        'public_tests_passed': result.returncode == 0 and {case.attrib['name'] for case in cases} == names
            and len(cases) == 2 and all(not list(case) for case in cases), 'counts': counts, 'failures': failures}, ensure_ascii=False))


if __name__ == '__main__':
    main()
