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
suite = control.SUITES['webcolors']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import webcolors
import string
business=True
# 独立保留原算法主体，仅在入口用ASCII裁剪后以非空白哨兵校准宽容结果。
for value,expected in [('\u00a0red\u00a0',(0,237,0)),('\x0bred\x0b',(0,237,0)),('\u2003red\u2003',(0,237,0))]:
    business &= webcolors.html5_parse_legacy_color(value)==expected
for char in ' \t\r\n\f':
    business &= webcolors.html5_parse_legacy_color(char+'#aBc'+char)==(170,187,204)
business &= webcolors.html5_parse_legacy_color('chucknorris')==(192,0,0)
business &= webcolors.html5_parse_legacy_color('red')==(255,0,0)

print(json.dumps({'candidate_import': Path(webcolors.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
