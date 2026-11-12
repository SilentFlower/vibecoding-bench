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
suite = control.SUITES['cattrs']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import cattrs
from dataclasses import dataclass
business = False
try:
    from cattrs.strategies.sequence_union import configure_sequence_union
    @dataclass
    class Event:
        """私有记录。"""
        count: int
    target = tuple[Event, ...] | Event
    converter = configure_sequence_union(cattrs.Converter(), target)
    business = converter.structure([{'count': '4'}, {'count': 5}], target) == (Event(4), Event(5))
    for value in (b'bytes', 4, iter([])):
        try:
            converter.structure(value, target)
        except TypeError:
            pass
        else:
            business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(cattrs.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
