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
suite = control.SUITES['cssselect']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import cssselect
business=False
try:
    from cssselect.compiled import compile_selector
    result=compile_selector('p:is(.a,.b), :where(#q)',prefix='')
    business=len(result.canonical)==2 and result.specificity==((0,1,1),(0,0,0)) and result.xpath==cssselect.GenericTranslator().css_to_xpath('p:is(.a,.b), :where(#q)',prefix='')
    try:compile_selector('p',mode='xml',xhtml=True)
    except ValueError:pass
    else:business=False
except ImportError:business=False

print(json.dumps({'candidate_import': Path(cssselect.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
