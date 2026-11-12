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
from rich.cells import _split_text,split_graphemes,cell_len,set_cell_size,split_text
from rich.console import Console
from rich.panel import Panel
from io import StringIO
business=True
for value in ('👩\u200d❤️\u200d👩中','A\u200dB\ufe0f中文','\ufe0f\u200d','👨\u200d👩\u200d👧\u200d👦'):
    width=split_graphemes(value)[1]
    business &= cell_len(value)==width and _split_text(value,width+1)==(value,'')
    for size in range(width+3):business &= cell_len(set_cell_size(value,size))==size
out=StringIO();Console(file=out,width=10,force_terminal=False).print(Panel('👩\u200d🔧中文'))
business &= bool(out.getvalue()) and split_text('abc',-1)==('','abc')

print(json.dumps({'candidate_import': Path(rich.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
