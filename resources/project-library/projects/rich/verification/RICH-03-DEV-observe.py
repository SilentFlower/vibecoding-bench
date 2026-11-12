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
suite = control.SUITES['rich']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import rich
from rich.text import Text,Span
business=True
for value in ('a','中文','e\u0301','ab😀'):
    text=Text(value,style='bold',spans=[Span(0,len(value),'red')])
    for index in range(len(value)):
        a,b=text[index],text[index-len(value)]
        business &= (a.plain,a.style,a.spans)==(b.plain,b.style,b.spans) and a.spans==[Span(0,1,'red')]
    for index in (-len(value)-1,len(value)):
        try:text[index]
        except IndexError:pass
        else:business=False

print(json.dumps({'candidate_import': Path(rich.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
