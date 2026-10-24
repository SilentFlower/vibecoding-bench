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
suite = control.SUITES['html5lib']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import html5lib
_bench_candidate_module = html5lib
business=False
try:
    from html5lib.links import collect_links
    tree=html5lib.parse('<base href="/assets/"><a href="page">a</a><img src="pic">')
    result=collect_links(tree,document_url='https://e.test/root')
    malformed=collect_links(html5lib.parse('<img srcset="a badx, b 0w, c 2x">'))['links']
    business=result['base_url']=='https://e.test/assets/' and [row['resolved'] for row in result['links']]==['https://e.test/assets/page','https://e.test/assets/pic'] and [row['status'] for row in malformed]==['unparsed_srcset','unparsed_srcset','parsed']
except ImportError:pass

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
