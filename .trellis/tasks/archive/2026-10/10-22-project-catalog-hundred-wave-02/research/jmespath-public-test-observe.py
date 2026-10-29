"""独立执行候选公开unittest，记录实际用例与失败。"""
from io import StringIO
import json
import os
from pathlib import Path
import unittest

import jmespath


def main() -> None:
    """核四个公开回归真实执行，不按候选自报放行。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    suite = unittest.defaultTestLoader.discover(str(root / 'app'), pattern='test_json_equality.py')
    result = unittest.TextTestRunner(stream=StringIO(), verbosity=2).run(suite)
    failures = [{'test': case.id(), 'message': message[-1000:]}
        for case, message in [*result.failures, *result.errors]]
    print(json.dumps({'candidate_import': Path(jmespath.__file__).resolve() == root / 'library/jmespath/__init__.py',
        'public_tests_passed': result.wasSuccessful() and result.testsRun == 4 and not result.skipped,
        'counts': {'tests': result.testsRun, 'failed': len(result.failures), 'errors': len(result.errors),
            'skipped': len(result.skipped)}, 'failures': failures}, ensure_ascii=False))


if __name__ == '__main__':
    main()
