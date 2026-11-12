"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['sqlparse']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import sqlparse
from sqlparse.sourcemap import SourceMap
business=True
for text in ('select 1;  select 2;  ','--中文\r\nSELECT (a+b),\n t.x FROM t;','select $$a; -- x$$;',''):
    mapping=SourceMap(text);previous=0
    for token,span in mapping.tokens():
        business &= span.start==previous and text[span.start:span.end]==token.value
        previous=span.end
    business &= previous==len(text)
    for statement in mapping.statements:
        pending=[statement]
        while pending:
            token=pending.pop();span=mapping.span(token)
            business &= text[span.start:span.end]==str(token)
            if token.is_group:pending.extend(token.tokens)

print(json.dumps({'candidate_import': Path(sqlparse.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
