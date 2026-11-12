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
suite = control.SUITES['docutils']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import docutils
_bench_candidate_module = docutils
from docutils.core import publish_doctree
from docutils import nodes
import io
document=publish_doctree('.. segmented-list::\n   :columns: Key | Value\n\n   A | 1\n   B | 2\n',settings_overrides={'warning_stream':io.StringIO(),'halt_level':6,'report_level':5})
tables=list(document.findall(nodes.table))
business=len(tables)==1 and [node.astext() for node in tables[0].findall(nodes.entry)]==['Key','Value','A','1','B','2'] and not list(document.findall(nodes.system_message))

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
