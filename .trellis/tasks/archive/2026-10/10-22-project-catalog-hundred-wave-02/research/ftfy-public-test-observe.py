"""从实际候选运行五项公开配置回归。"""
from io import StringIO
import json
import os
from pathlib import Path
import unittest

import ftfy


def main() -> None:
    """保留实际计数和失败，不把存在测试文件当作通过。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    suite = unittest.defaultTestLoader.discover(str(root / 'app'), pattern='test_explain_config.py')
    result = unittest.TextTestRunner(stream=StringIO(), verbosity=2).run(suite)
    print(json.dumps({'candidate_import': Path(ftfy.__file__).resolve() == root / 'library/ftfy/__init__.py',
        'public_tests_passed': result.wasSuccessful() and result.testsRun == 5 and not result.skipped,
        'counts': {'tests': result.testsRun, 'failed': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped)},
        'failures': [{'test': test.id(), 'message': message[-1000:]} for test, message in [*result.failures, *result.errors]]}))


if __name__ == '__main__':
    main()
