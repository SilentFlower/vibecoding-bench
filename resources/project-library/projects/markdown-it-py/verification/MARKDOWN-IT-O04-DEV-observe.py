"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
_bench_candidate_root = root
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['markdown-it-py']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import markdown_it
_bench_candidate_module = markdown_it
import tempfile,contextlib,io
from pathlib import Path
from markdown_it.cli.parse import main
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'bad.md';path.write_bytes(b'A\xffB');out=io.StringIO();err=io.StringIO();failed=False
    try:
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):main(['--encoding-errors','strict',str(path)])
    except SystemExit as error:failed=error.code==1
    business=failed and not out.getvalue() and str(path) in err.getvalue()

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
