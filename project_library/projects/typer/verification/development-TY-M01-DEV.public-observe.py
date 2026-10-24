"""真实执行原export交付的两项应用测试。"""
import json,os,sys,unittest
from pathlib import Path
root=Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))

suite=unittest.defaultTestLoader.discover(str(root/'app/tests'),pattern='test_shop.py')
result=unittest.TestResult();suite.run(result)
print(json.dumps({'passed':result.wasSuccessful() and result.testsRun==2,'executed':result.testsRun,'failures':len(result.failures)+len(result.errors)+len(result.skipped)}))
