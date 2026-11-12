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
suite = control.SUITES['python-markdown']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import markdown
business=True
for character in ('~','`'):
    for opening,closing in ((3,3),(3,4),(5,7)):
        raw=character*opening+'txt\nx < y & z\n'+character*closing
        output=markdown.markdown(raw,extensions=['markdown.extensions.fenced_code'],extension_configs={'markdown.extensions.fenced_code':{'closing_fence':'at_least'}})
        business &= '<pre>' in output and 'x &lt; y &amp; z\n' in output and 'language-txt' in output
text='~~~ {.python #example}\nvalue\n~~~~'
output=markdown.markdown(text,extensions=['markdown.extensions.fenced_code','markdown.extensions.attr_list'],extension_configs={'markdown.extensions.fenced_code':{'closing_fence':'at_least'}})
business &= 'id="example"' in output and 'language-python' in output

print(json.dumps({'candidate_import': Path(markdown.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
