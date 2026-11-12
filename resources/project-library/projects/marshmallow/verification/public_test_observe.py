"""在实际候选导入下独立执行四项公开日期回归。"""
from io import StringIO
import json
import os
from pathlib import Path
import unittest

import marshmallow


def main() -> None:
    """核实际公开用例及失败，拒绝候选自报。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    suite = unittest.defaultTestLoader.discover(str(root / 'app'), pattern='test_date.py')
    result = unittest.TextTestRunner(stream=StringIO(), verbosity=2).run(suite)
    print(json.dumps({'candidate_import': Path(marshmallow.__file__).resolve() == root / 'library/src/marshmallow/__init__.py',
        'public_tests_passed': result.wasSuccessful() and result.testsRun == 4 and not result.skipped,
        'counts': {'tests': result.testsRun, 'failed': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped)},
        'failures': [{'test': test.id(), 'message': message[-1000:]} for test, message in [*result.failures, *result.errors]]}))


if __name__ == '__main__':
    main()
