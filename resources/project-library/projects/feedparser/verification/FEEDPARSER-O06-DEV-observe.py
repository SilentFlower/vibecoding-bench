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
from feedparser.util import FeedParserDict
business=False
try:
    from feedparser.readers import entry_text
    entry=FeedParserDict(content=[{'type':'text/html','value':'<p>One</p><p>Two &amp; three</p>'}],summary='other')
    actual=entry_text(entry)
    business=actual['text']=='One\nTwo & three' and actual['source']=='content' and actual['value']==entry.content[0]['value'] and entry_text(FeedParserDict(title='only')) is None
except ImportError:pass

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
