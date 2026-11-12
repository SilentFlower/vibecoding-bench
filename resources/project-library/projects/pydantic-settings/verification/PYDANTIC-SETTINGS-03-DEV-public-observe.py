"""运行当前目标的真实公开回归，核实际收集数及源码归属。"""
import importlib
import json
import os
import runpy
import unittest
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))

namespace = runpy.run_path(str(root / 'library/tests/test_development_pydantic_settings_03_dev.py'))
functions = [value for name,value in sorted(namespace.items()) if name.startswith('test_') and callable(value)]
result = unittest.TestResult()
unittest.TestSuite(unittest.FunctionTestCase(function) for function in functions).run(result)
bound = Path(importlib.import_module('pydantic_settings').__file__).resolve().is_relative_to(root / 'library')
print(json.dumps({'passed': result.wasSuccessful() and bool(functions) and bound,
    'executed': result.testsRun, 'failures': len(result.failures)+len(result.errors)+len(result.skipped)}))
