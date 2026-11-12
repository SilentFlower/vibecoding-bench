"""运行当前目标的真实公开回归，核实际收集数及源码归属。"""
import importlib
import json
import os
import runpy
import unittest
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['pypika']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))

namespace = runpy.run_path(str(root / 'library/tests/test_development_pypika_04_dev.py'))
functions = [value for name,value in sorted(namespace.items()) if name.startswith('test_') and callable(value)]
result = unittest.TestResult()
unittest.TestSuite(unittest.FunctionTestCase(function) for function in functions).run(result)
bound = Path(importlib.import_module('pypika').__file__).resolve().is_relative_to(root / 'library')
print(json.dumps({'passed': result.wasSuccessful() and bool(functions) and bound,
    'executed': result.testsRun, 'failures': len(result.failures)+len(result.errors)+len(result.skipped)}))
