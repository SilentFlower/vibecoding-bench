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
    from bibtexparser.diff import diff_libraries
    from bibtexparser.model import Entry, Field
    one = bibtexparser.Library([Entry('article', 'x', [Field('tags', ['a']), Field('empty', None)])])
    two = bibtexparser.Library([Entry('book', 'x', [Field('tags', ['b'])])])
    result = diff_libraries(one, two)
    state = result['entries']['changed'][0]
    business = state['before']['type'] == 'article' and state['after']['type'] == 'book' and 'empty' in state['before']['fields'] and 'empty' not in state['after']['fields']
    state['before']['fields']['tags'].append('mutate-report')
    business &= one.entries[0]['tags'] == ['a']
    business &= diff_libraries(bibtexparser.Library(), bibtexparser.Library())['failed'] is None
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(bibtexparser.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
