"""核参考交付的两个tuple公开测试在实际候选上执行。"""
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse

import tabulate


def main() -> None:
    """核真实节点、失败类型和候选绑定。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    report = Path('/tmp/tabulate-public-tests.xml')
    names = {'test_inventory_rowalign_tuple_equivalence', 'test_inventory_headerwidth_tuple_equivalence'}
    command = [sys.executable, '-m', 'pytest', '-q', *['test/test_api.py::' + name for name in sorted(names)],
        '--junitxml=' + str(report)]
    completed = subprocess.run(command, cwd=root / 'library',
        env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'), capture_output=True, timeout=15)
    cases = list(parse(report).getroot().iter('testcase')) if report.is_file() else []
    counts = {'tests': len(cases), 'failed': sum(len(case.findall('failure')) for case in cases),
        'errors': sum(len(case.findall('error')) for case in cases),
        'skipped': sum(len(case.findall('skipped')) for case in cases)}
    failures = [{'test': case.attrib['name'], 'message': child.attrib.get('message', '')[:1000]}
        for case in cases for child in case if child.tag in ('failure', 'error')]
    print(json.dumps({'candidate_import': Path(tabulate.__file__).resolve() == root / 'library/tabulate/__init__.py',
        'public_tests_passed': completed.returncode == 0 and {case.attrib['name'] for case in cases} == names
            and len(cases) == 2 and all(not list(case) for case in cases),
        'counts': counts, 'failures': failures}, ensure_ascii=False))


if __name__ == '__main__':
    main()
