"""执行XML参考交付的三条公开回归，核真实节点及失败类型。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse

import xmltodict


def main() -> None:
    """核三条测试是否真的执行且通过。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    report = Path('/tmp/xmltodict-public-tests.xml')
    names = {'test_order_chunk_iterator_and_map_regression',
        'test_order_utf8_chunk_iterator_regression',
        'test_order_iterator_callback_stops_consumption_regression'}
    command = [sys.executable, '-m', 'pytest', '-q', *[
        'tests/test_xmltodict.py::' + name for name in sorted(names)], '--junitxml=' + str(report)]
    completed = subprocess.run(command, cwd=root / 'library',
        env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'), capture_output=True, timeout=15)
    cases = list(parse(report).getroot().iter('testcase')) if report.is_file() else []
    counts = {'tests': len(cases), 'failed': sum(len(case.findall('failure')) for case in cases),
        'errors': sum(len(case.findall('error')) for case in cases),
        'skipped': sum(len(case.findall('skipped')) for case in cases)}
    failures = [{'test': case.attrib['name'], 'message': child.attrib.get('message', '')[:1000]}
        for case in cases for child in case if child.tag in ('failure', 'error')]
    print(json.dumps({'candidate_import': Path(xmltodict.__file__).resolve() == root / 'library/xmltodict.py',
        'public_tests_passed': completed.returncode == 0 and {case.attrib['name'] for case in cases} == names
            and len(cases) == 3 and all(not list(case) for case in cases),
        'counts': counts, 'failures': failures}, ensure_ascii=False))


if __name__ == '__main__':
    main()
