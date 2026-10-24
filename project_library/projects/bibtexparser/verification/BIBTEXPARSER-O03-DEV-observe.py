"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['bibtexparser']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import bibtexparser
business = False
try:
    from bibtexparser.pages import NormalizePages
    from bibtexparser.model import Entry, Field
    source = bibtexparser.Library([Entry('article', 'private', [Field('pages', ' 001 - 009 '), Field('year', '2026')])])
    output = NormalizePages().transform(source)
    business = output.entries[0]['pages'] == '001--009' and output.entries[0]['year'] == '2026'
    business &= source.entries[0]['pages'] == ' 001 - 009 '
    untouched = bibtexparser.Library([Entry('article', 'x', [Field('pages', '1-3,unknown')])])
    business &= NormalizePages().transform(untouched).entries[0]['pages'] == '1-3,unknown'
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(bibtexparser.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
