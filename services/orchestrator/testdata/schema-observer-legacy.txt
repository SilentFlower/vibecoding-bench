"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import agate
from decimal import Decimal
business = False
try:
    source = agate.Table([(1, 'a'), (3, 'b'), (1, None), (9, 'c')], ['quantity', 'label'], [agate.Number(), agate.Text()])
    schema = agate.Schema({'quantity': {'unique': True, 'min': 2, 'max': 7}, 'label': {'nullable': False, 'choices': ['a', 'b']}})
    expected = [{'row': 0, 'column': 'quantity', 'code': 'min'}, {'row': 2, 'column': 'quantity', 'code': 'unique'},
        {'row': 2, 'column': 'quantity', 'code': 'min'}, {'row': 2, 'column': 'label', 'code': 'null'},
        {'row': 3, 'column': 'quantity', 'code': 'max'}, {'row': 3, 'column': 'label', 'code': 'choice'}]
    actual = schema.validate(source)
    strict = False
    try:
        schema.validate(source, strict=True, max_errors=3)
    except agate.SchemaValidationError as error:
        strict = error.errors == tuple(expected[:3])
    rejected = 0
    for rules in ({'label': {'nullable': 1}}, {'label': {'choices': 'ab'}}, {'quantity': {'min': None}}):
        try:
            agate.Schema(rules)
        except TypeError:
            rejected += 1
    business = actual == expected and strict and rejected == 3 and len(source.rows) == 4
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(agate.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
