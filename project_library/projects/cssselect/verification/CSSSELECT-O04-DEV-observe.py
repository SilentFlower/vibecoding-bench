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
    from cssselect.extensions import PluginTranslator
    p=PluginTranslator();p.register_pseudo('z-tag',lambda x:x.add_condition('@z'))
    before=p.extension_fingerprint();other=PluginTranslator();other.register_pseudo('z-tag',lambda x:x.add_condition('@other'),version='3')
    business=p.extension_fingerprint()==before and p.extension_fingerprint()!=other.extension_fingerprint() and '@other' not in p.css_to_xpath(':z-tag')
    try:p.register_pseudo('nth-child',lambda x:x)
    except ValueError:pass
    else:business=False
except ImportError:business=False

print(json.dumps({'candidate_import': Path(cssselect.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
