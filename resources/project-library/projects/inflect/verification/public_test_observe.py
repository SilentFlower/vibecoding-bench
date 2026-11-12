"""以实际候选核四项公开模式回归。"""
from io import StringIO
import json
import os
from pathlib import Path
import unittest

import inflect


def main() -> None:
    """记录实际执行、异常和失败。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    suite = unittest.defaultTestLoader.discover(str(root / 'app'), pattern='test_classical.py')
    result = unittest.TextTestRunner(stream=StringIO(), verbosity=2).run(suite)
    print(json.dumps({'candidate_import': Path(inflect.__file__).resolve() == root / 'library/inflect/__init__.py',
        'public_tests_passed': result.wasSuccessful() and result.testsRun == 4 and not result.skipped,
        'counts': {'tests': result.testsRun, 'failed': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped)},
        'failures': [{'test': test.id(), 'message': message[-1000:]} for test, message in [*result.failures, *result.errors]]}))


if __name__ == '__main__':
    main()
