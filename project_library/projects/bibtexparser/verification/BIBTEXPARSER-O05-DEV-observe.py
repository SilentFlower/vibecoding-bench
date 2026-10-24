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
    from bibtexparser.identifiers import NormalizeIdentifiers
    from bibtexparser.model import Entry, Field
    source = bibtexparser.Library([Entry('article', 'private', [Field('doi', 'doi: 10.9999/ABC(1).'), Field('title', '10.9999/KEEP')])])
    output = NormalizeIdentifiers(fields=['doi']).transform(source)
    business = output.entries[0]['doi'] == '10.9999/abc(1).' and output.entries[0]['title'] == '10.9999/KEEP'
    bad = bibtexparser.Library([Entry('book', 'b', [Field('isbn', 'not-an-isbn')])])
    business &= NormalizeIdentifiers().transform(bad).entries[0]['isbn'] == 'not-an-isbn'
    business &= source.entries[0]['doi'] == 'doi: 10.9999/ABC(1).'
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(bibtexparser.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
