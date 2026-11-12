"""核格式选项隔离的两个公开测试在实际候选上执行。"""
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse

import cli_helpers


def main() -> None:
    """核真实节点、失败明细和源码来源。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    report = Path('/tmp/cli-helpers-public-tests.xml')
    names = {'test_export_call_options_do_not_leak_between_instances',
        'test_registered_export_defaults_and_caller_mapping_stay_unchanged'}
    command = [sys.executable, '-m', 'pytest', '-q', *[
        'tests/tabular_output/test_output_formatter.py::' + name for name in sorted(names)],
        '--junitxml=' + str(report)]
    completed = subprocess.run(command, cwd=root / 'library',
        env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'), capture_output=True, timeout=15)
    cases = list(parse(report).getroot().iter('testcase')) if report.is_file() else []
    counts = {'tests': len(cases), 'failed': sum(len(case.findall('failure')) for case in cases),
        'errors': sum(len(case.findall('error')) for case in cases),
        'skipped': sum(len(case.findall('skipped')) for case in cases)}
    failures = [{'test': case.attrib['name'], 'message': child.attrib.get('message', '')[:1000]}
        for case in cases for child in case if child.tag in ('failure', 'error')]
    print(json.dumps({'candidate_import': Path(cli_helpers.__file__).resolve() == root / 'library/cli_helpers/__init__.py',
        'public_tests_passed': completed.returncode == 0 and {case.attrib['name'] for case in cases} == names
            and len(cases) == 2 and all(not list(case) for case in cases),
        'counts': counts, 'failures': failures}, ensure_ascii=False))


if __name__ == '__main__':
    main()
