"""完整运行原冻结回归，并在原覆盖率会话内验证新增能力。"""
import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

source = Path(__file__).with_name('native_regression.py')
assert 'def pytest_runtest_setup' not in source.read_text()
specification = importlib.util.spec_from_file_location('frozen_injector_upstream', source)
original = importlib.util.module_from_spec(specification)
specification.loader.exec_module(original)
copy_original = original.shutil.copyfile
hook = '\n\n_BENCH_EXPANSION_COVERAGE_DONE = False\n@pytest.hookimpl(tryfirst=True)\ndef pytest_runtest_setup(item):\n    """在原覆盖引擎内执行新增功能断言。@param item 原测试节点。@return None。"""\n    global _BENCH_EXPANSION_COVERAGE_DONE\n    if _BENCH_EXPANSION_COVERAGE_DONE:\n        return\n    _BENCH_EXPANSION_COVERAGE_DONE = True\n    control = json.loads(Path(os.environ[\'BENCH_NATIVE_CONTROL\']).read_text())\n    helper = Path(\'/request-data/verification/INJECTOR-O04-DEV-coverage.py\')\n    namespace = runpy.run_path(str(helper))\n    namespace[\'cover_features\'](Path(control[\'project\']), Path(control[\'evidence\']))\n'

def copy_with_protected_probe(source_path, destination, *args, **kwargs):
    """只给可信临时插件增加额外断言，不改原控制文件或测试。@param source_path 来源。
    @param destination 临时目标。@param args 原参数。@param kwargs 原命名参数。@return 原复制结果。
    """
    result = copy_original(source_path, destination, *args, **kwargs)
    path = Path(destination)
    if path.name == '_bench_native_regression_control.py':
        with path.open('a') as output:
            output.write(hook)
    return result

original.shutil.copyfile = copy_with_protected_probe
captured = io.StringIO()
code = 0
try:
    with contextlib.redirect_stdout(captured):
        original.main()
except SystemExit as outcome:
    code = outcome.code or 0
finally:
    original.shutil.copyfile = copy_original
result = json.loads(captured.getvalue())
evidence = Path(sys.argv[sys.argv.index('--evidence-dir') + 1]) / 'expansion-coverage.json'
probe = json.loads(evidence.read_text()) if evidence.is_file() else {'status':'not_executed'}
result['expansion_coverage'] = probe
if result['status'] == 'passed' and probe['status'] != 'passed':
    result['status'] = 'failed'
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(0 if result['status'] == 'passed' and code == 0 else 1)
