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
suite = control.SUITES['pypika']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pypika
from pypika import Interval
from pypika.enums import Dialects
business=True
for count in (-1,-999999,-(2**64)):
    interval=Interval(microseconds=count)
    for dialect in (Dialects.POSTGRESQL,Dialects.MYSQL):
        business &= str(count) in interval.get_sql(dialect=dialect)
    business &= interval.microseconds==abs(count) and interval.is_negative
business &= '12' in Interval(microseconds=12).get_sql()

print(json.dumps({'candidate_import': Path(pypika.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
