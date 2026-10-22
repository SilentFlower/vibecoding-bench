"""独立运行血缘渲染的六项公开回归。"""
from io import StringIO
import json
import os
from pathlib import Path
import unittest

import sqlglot


def main() -> None:
    """核实际公开测试及候选绑定。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    suite = unittest.defaultTestLoader.discover(str(root / 'app'), pattern='test_lineage_render.py')
    result = unittest.TextTestRunner(stream=StringIO(), verbosity=2).run(suite)
    failures = [{'test': case.id(), 'message': message[-1000:]}
        for case, message in [*result.failures, *result.errors]]
    print(json.dumps({'candidate_import': Path(sqlglot.__file__).resolve() == root / 'library/sqlglot/__init__.py',
        'public_tests_passed': result.wasSuccessful() and result.testsRun == 6 and not result.skipped,
        'counts': {'tests': result.testsRun, 'failed': len(result.failures), 'errors': len(result.errors),
            'skipped': len(result.skipped)}, 'failures': failures}, ensure_ascii=False))


if __name__ == '__main__':
    main()
