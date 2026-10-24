"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import attrs
_candidate_source_root = root
from attrs.evolution import evolve_as
business = False
try:
    @attrs.define
    class Before:
        quantity: str
    @attrs.frozen
    class After:
        quantity: int = attrs.field(converter=int)
        labels: list = attrs.field(factory=list)
    first, second = evolve_as(Before('6'), After), evolve_as(Before('8'), After)
    first.labels.append('a')
    @attrs.define
    class Unrelated:
        other: int = 3
    rejected = False
    try:
        evolve_as(Before('1'), Unrelated)
    except TypeError:
        rejected = True
    business = first.quantity == 6 and second.quantity == 8 and second.labels == [] and rejected
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(attrs.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
