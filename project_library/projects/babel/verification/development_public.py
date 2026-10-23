"""隔离运行候选交付的公开回归测试；不加载原项目测试控制。"""
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest

def main():
    """加载公开交付文件并输出真实测试结论。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    path = root / 'library/tests/test_development_datetime_parts.py'
    result = {'public_file_exists': path.is_file(), 'public_tests_pass': False}
    if path.is_file():
        specification = importlib.util.spec_from_file_location('development_public', path)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        run = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        result['public_tests_pass'] = run.testsRun >= 4 and run.wasSuccessful()
    print(json.dumps(result, sort_keys=True))

if __name__ == '__main__':
    main()
