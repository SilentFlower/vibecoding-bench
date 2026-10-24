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
    from bibtexparser.keywords import SplitKeywords, MergeKeywords
    from bibtexparser.model import Entry, Field
    source = bibtexparser.Library([Entry('article', 'private', [Field('keywords', 'one;{two;three};;four')])])
    output = SplitKeywords(delimiter=';').transform(source)
    business = output.entries[0]['keywords'] == ['one', '{two;three}', 'four']
    merged = MergeKeywords(delimiter=';').transform(output)
    business &= merged.entries[0]['keywords'] == 'one;{two;three};four'
    business &= source.entries[0]['keywords'] == 'one;{two;three};;four'
    for raw in ('a,}', '{a'):
        try:
            SplitKeywords().transform(bibtexparser.Library([Entry('article', 'x', [Field('keywords', raw)])]))
        except ValueError:
            pass
        else:
            business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(bibtexparser.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
