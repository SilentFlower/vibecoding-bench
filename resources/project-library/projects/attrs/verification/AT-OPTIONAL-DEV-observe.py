"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import attrs
_candidate_source_root = root
import attr
from typing import get_args, ForwardRef
business = False
try:
    calls = []
    def convert(value: 'str', instance, attribute) -> 'int':
        calls.append((instance, attribute.name))
        return int(value) + instance.offset
    converter = attrs.Converter(convert, takes_self=True, takes_field=True)
    @attrs.define
    class Record:
        offset: int
        amount: int | None = attrs.field(converter=attrs.converters.optional(converter))
    first, second = Record(5, '7'), Record(5, None)
    def unknown(value):
        return value
    unknown.__annotations__ = {'value':'dangerous()', 'return':'UnknownName'}
    wrapped = attr.converters.optional(unknown)
    business = (first.amount == 12 and second.amount is None and len(calls) == 1
        and calls[0][0] is first and calls[0][1] == 'amount' and wrapped(9) == 9
        and any(isinstance(item, ForwardRef) for item in get_args(wrapped.__annotations__['val'])))
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(attrs.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
