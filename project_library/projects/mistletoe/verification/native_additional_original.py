"""实际运行上游CommonMark官方入口并保留每例结果，仅验证固定原版。"""
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import runpy
import sys

import mistletoe


def main() -> None:
    """保留官方加载和比较逻辑，不复制成另一套Markdown验收。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    project = root / 'library'
    os.chdir(project)
    sys.path.insert(0, str(project))
    from test.specification import commonmark
    source = project / 'test/specification/commonmark.json'
    fixtures = json.loads(source.read_text())
    if commonmark.KNOWN or len(fixtures) != 652:
        raise ValueError('固定CommonMark原件或已知排除表变化')
    original = commonmark.run_test
    records = []

    def observed(entry, quiet=False):
        """执行真实原用例并记录独立结果。@param entry 原例。@param quiet 原参数。@return 原结果。"""
        actual = original(entry, quiet)
        records.append({'id': 'commonmark::' + str(entry['example']), 'kind': 'CommonMarkExample',
            'outcome': 'passed' if actual[0] else 'failed', 'section': entry['section']})
        return actual

    commonmark.run_test = observed
    out, err, code = StringIO(), StringIO(), 0
    arguments = sys.argv
    try:
        sys.argv = ['test.specification', '--ignore-known']
        with redirect_stdout(out), redirect_stderr(err):
            try:
                runpy.run_module('test.specification', run_name='__main__')
            except SystemExit as error:
                code = error.code or 0
    finally:
        commonmark.run_test = original
        sys.argv = arguments
    identities = {row['id'] for row in records}
    candidate = Path(mistletoe.__file__).resolve() == project / 'mistletoe/__init__.py'
    valid = candidate and code == 0 and len(records) == len(identities) == len(fixtures) and all(row['outcome'] == 'passed' for row in records)
    report = {'status': 'passed' if valid else 'failed', 'candidate_import': candidate,
        'entry': ['-m', 'test.specification', '--ignore-known'], 'collected': len(records),
        'passed': sum(row['outcome'] == 'passed' for row in records), 'known_excluded': [],
        'source_sha256': sha256(source.read_bytes()).hexdigest(), 'nodes': records,
        'stdout': out.getvalue()[-3000:], 'stderr': err.getvalue()[-3000:], 'returncode': code,
        'scope': '完整固定原版的额外官方集合；不是可修改候选的累计回归或真实模型成绩'}
    print(json.dumps(report))
    raise SystemExit(0 if valid else 1)


if __name__ == '__main__':
    main()
