"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['mistletoe']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import mistletoe
import subprocess
import sys
business=True
for text,expected in [('plain text','<p>plain text</p>\n'),('## two\n','<h2>two</h2>\n'),('', '')]:
    result=subprocess.run([sys.executable,'-m','mistletoe','-'],input=text,text=True,capture_output=True,timeout=3)
    business &= result.returncode==0 and result.stdout==expected and 'interactive' not in result.stdout

print(json.dumps({'candidate_import': Path(mistletoe.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
