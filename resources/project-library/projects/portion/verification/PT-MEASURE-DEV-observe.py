"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
control._bind_source(root / 'library', Path('.'), cleanup, distribution=control.SUITES['portion']['distribution'])

import portion
from datetime import date, timedelta
from decimal import Decimal
business = False
try:
    spans = portion.closedopen(date(2026, 1, 1), date(2026, 1, 4)) | portion.closedopen(date(2026, 2, 1), date(2026, 2, 3))
    seen = []
    def duration(atom):
        """只解释实际原子日期窗口。@param atom 原子区间。@return 时长。"""
        seen.append(atom)
        return atom.upper - atom.lower
    business = spans.measure(duration, start=timedelta()) == timedelta(days=5) and len(seen) == 2
    business &= all(atom.atomic for atom in seen) and len(spans) == 2
    marker = object()
    business &= portion.empty().measure(lambda _: 1 / 0, start=marker) is marker
    def bounded(atom):
        """无界业务区间明确拒绝。@param atom 原子区间。@return 长度。"""
        if atom.lower == -portion.inf or atom.upper == portion.inf:
            raise ValueError('无界区间')
        return atom.upper - atom.lower
    try:
        portion.open(0, portion.inf).measure(bounded)
    except ValueError:
        pass
    else:
        business = False
    business &= portion.singleton(Decimal('8')).measure(bounded, start=Decimal(0)) == Decimal(0)
except (AttributeError, TypeError):
    business = False

print(json.dumps({'candidate_import': Path(portion.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
