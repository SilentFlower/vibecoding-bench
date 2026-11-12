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
suite = control.SUITES['feedparser']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import feedparser
_bench_candidate_module = feedparser
import io,json
result=feedparser.parse(io.StringIO(json.dumps({'version':'https://jsonfeed.org/version/1.1','title':'T','authors':[{'name':'first'},{'name':'second','avatar':'a'}],'language':'fr','items':[{'id':'x','content_text':'body'}]})))
business=not result.bozo and result.feed.get('authors') is not None and [person.name for person in result.feed.authors]==['first','second'] and result.entries[0].get('language')=='fr' and result.entries[0].authors is not result.feed.authors

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
