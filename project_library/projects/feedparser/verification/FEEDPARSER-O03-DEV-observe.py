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
import io
business=False
try:
    from feedparser import DateHandlerRegistry
    registry=DateHandlerRegistry([lambda text:(2026,10,24,1,2,3,5,297,0) if text=='unique-date' else None],include_builtin=False)
    text='<rss version="2.0"><channel><title>T</title><item><pubDate>unique-date</pubDate></item></channel></rss>'
    actual=feedparser.parse(io.StringIO(text),date_handlers=registry).entries[0]
    other=feedparser.parse(io.StringIO(text)).entries[0]
    business=actual.published_parsed[:6]==(2026,10,24,1,2,3) and other.published_parsed is None
except ImportError:pass

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
