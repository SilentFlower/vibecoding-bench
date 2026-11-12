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
suite = control.SUITES['pyparsing']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pyparsing
from dataclasses import dataclass
from pyparsing.dataclass_results import to_dataclass,ResultMappingError
business=True
@dataclass
class Row:
    amount:int
@dataclass
class Batch:
    rows:list[Row]
a={'rows':[{'amount':2},{'amount':5}]};value=to_dataclass(a,Batch)
business &= [row.amount for row in value.rows]==[2,5] and isinstance(a['rows'][0],dict)
try:to_dataclass({'rows':[{'amount':'bad'}]},Batch)
except ResultMappingError as error:business &= error.path=='$.rows[0].amount'
else:business=False

print(json.dumps({'candidate_import': Path(pyparsing.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
