"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import attrs
_candidate_source_root = root
from attrs.validation import validate_all, MultiValidationError
business = False
try:
    seen = []
    def first(instance, attribute, value):
        seen.append(attribute.name)
        raise TypeError('first')
    def second(instance, attribute, value):
        seen.append(attribute.name)
        raise ValueError('second')
    @attrs.frozen
    class Record:
        _private: int = attrs.field(alias='value', validator=first)
        other: int = attrs.field(validator=second)
    with attrs.validators.disabled():
        value = Record(1,2)
    issues = validate_all(value)
    invalid_switch = False
    try:
        validate_all(value, raise_errors=1)
    except TypeError:
        invalid_switch = True
    business = (seen == ['_private','other'] and [issue.field_name for issue in issues] == ['_private','other']
        and type(issues[0].error) is TypeError and type(issues[1].error) is ValueError and invalid_switch
        and value._private == 1 and value.other == 2)
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(attrs.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
