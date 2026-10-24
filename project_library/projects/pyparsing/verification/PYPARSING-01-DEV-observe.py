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
suite = control.SUITES['pyparsing']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pyparsing
import pyparsing as pp
from pyparsing.grammar_tools import lint_grammar
business=True
f=pp.Forward();g=pp.Group(f)+pp.Group(f)
issues=lint_grammar(g)
business &= len(issues)==1 and issues[0].code=='undefined-forward'
f <<= pp.Literal('x')+pp.Optional(f)
business &= lint_grammar(f)==()

print(json.dumps({'candidate_import': Path(pyparsing.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
