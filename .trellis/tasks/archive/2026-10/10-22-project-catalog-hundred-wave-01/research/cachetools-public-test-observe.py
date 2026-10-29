"""独立执行参考所交付的公开测试，证明其在原版失败、参考通过。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse

import cachetools


def main() -> None:
    """核真实收集的两个公开测试，不将退出码零等同于已执行。

    :return: None。
    """
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    report = Path('/tmp/cachetools-public-tests.xml')
    environment = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    completed = subprocess.run([sys.executable, '-m', 'pytest', '-q',
        'tests/test_cachedmethod.py::KeywordReceiverRegressionTests', '--junitxml=' + str(report)],
        cwd=root / 'library', env=environment, capture_output=True, timeout=15)
    cases = list(parse(report).getroot().iter('testcase')) if report.is_file() else []
    failures = [{'test': case.attrib['name'], 'message': child.attrib.get('message', '')[:1000]}
        for case in cases for child in case if child.tag in ('failure', 'error')]
    counts = {'tests': len(cases), 'failed': sum(len(case.findall('failure')) for case in cases),
        'errors': sum(len(case.findall('error')) for case in cases),
        'skipped': sum(len(case.findall('skipped')) for case in cases)}
    valid = (completed.returncode == 0 and len(cases) == 2
        and all(not list(case) for case in cases)
        and {case.attrib['name'] for case in cases} == {
            'test_keyword_receiver_and_cache_info', 'test_nonstandard_receiver_name'})
    print(json.dumps({'candidate_import': Path(cachetools.__file__).resolve().is_relative_to(root / 'library/src/cachetools'),
        'public_tests_passed': valid, 'counts': counts, 'failures': failures}))


if __name__ == '__main__':
    main()
