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
from io import StringIO
from rich.console import Console
from rich.text import Text
business=True
def run(text,**options):
    """真实控制台输出。@param text 内容。@param options 参数。@return 文本。"""
    output=StringIO();Console(file=output,width=16,force_terminal=False,color_system=None).print(text,**options);return output.getvalue()
for justify in ('left','center','right'):
    text=Text('中文',style='bold',justify=justify)
    business &= run(text)==run(Text('中文',style='bold'),justify=justify)
    business &= text.justify==justify and text.style=='bold'
out=StringIO();Console(file=out,force_terminal=False).print(Text('one'),Text('two'),sep='|',end='!')
business &= out.getvalue()=='one|two!'

print(json.dumps({'candidate_import': Path(rich.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
