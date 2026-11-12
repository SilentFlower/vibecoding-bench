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
    from bibtexparser.crossref import ResolveCrossrefMiddleware
    from bibtexparser.model import Entry, Field
    source = bibtexparser.Library([Entry('book', 'UPPER', [Field('year', '2024'), Field('publisher', 'Press')]), Entry('article', 'leaf', [Field('year', ''), Field('crossref', 'UPPER')])])
    result = ResolveCrossrefMiddleware().transform(source)
    business = result.entries_dict['leaf']['year'] == '' and result.entries_dict['leaf']['publisher'] == 'Press'
    result.entries_dict['leaf']['publisher'] = 'Changed'
    business &= source.entries_dict['UPPER']['publisher'] == 'Press'
    source.entries_dict['leaf']['crossref'] = 'upper'
    try:
        ResolveCrossrefMiddleware().transform(source)
    except ValueError:
        pass
    else:
        business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(bibtexparser.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
