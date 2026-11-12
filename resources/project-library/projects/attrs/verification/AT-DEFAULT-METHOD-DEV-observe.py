"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import attrs
_candidate_source_root = root
business = False
try:
    @attrs.define
    class Parent:
        value = attrs.field(default=attrs.Factory.from_method('_default'))
        def _default(self):
            return 'parent'
    @attrs.define
    class Middle(Parent):
        def _default(self):
            return 'middle'
    @attrs.frozen
    class Final(Middle):
        def _default(self):
            return 'final'
    @attrs.define
    class Invalid:
        value = attrs.field(default=attrs.Factory.from_method('_default'))
        @classmethod
        def _default(cls):
            raise AssertionError('不能执行classmethod')
    rejected = False
    try:
        Invalid()
    except TypeError:
        rejected = True
    @attrs.define
    class Broken:
        value = attrs.field(default=attrs.Factory.from_method('_default'))
        def _default(self):
            raise LookupError('原始业务异常')
    propagated = False
    try:
        Broken()
    except LookupError:
        propagated = True
    business = Final().value == 'final' and Parent().value == 'parent' and rejected and propagated
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(attrs.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
