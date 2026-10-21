"""独立观察Cerberus规范化、未知字段和局部更新边界。"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import cerberus
from cerberus import Validator


def normalization() -> dict:
    """核复制、转换和仅规范化接口的责任。@return 实际事实。"""
    schema = {'n': {'type': 'integer', 'coerce': int, 'min': 2, 'required': True}}
    original = {'n': '2'}
    normal = Validator(schema)
    passed = normal.validate(original)
    raw = Validator(schema)
    raw_passed = raw.validate(original, normalize=False)
    only = Validator(schema)
    normalized = only.normalized({'n': '1'})
    only_errors = deepcopy(only.errors)
    checked = only.validated({'n': '1'})
    return {'validate_normalizes_copy_unless_explicitly_disabled': passed and normal.document == {'n': 2}
            and original == {'n': '2'} and not raw_passed,
        'normalized_is_not_a_validation_success_result': normalized == {'n': 1}
            and only_errors == {} and checked is None and 'n' in only.errors}


def null_defaults() -> dict:
    """核缺失、None、零值以及必需字段存在性。@return 实际事实。"""
    schema = {'a': {'type': 'integer', 'default': 5},
        'b': {'type': 'integer', 'nullable': True, 'default': 5}}
    validator = Validator(schema)
    nil = validator.validated({'a': None, 'b': None})
    missing = validator.validated({})
    zero = validator.validated({'a': 0, 'b': 0})
    required = Validator({'n': {'required': True, 'nullable': True, 'type': 'integer'}})
    absent = required.validate({})
    present_null = required.validate({'n': None})
    return {'nullable_controls_null_defaults_and_required_still_means_present':
        nil == {'a': 5, 'b': None} and missing == {'a': 5, 'b': 5}
        and zero == {'a': 0, 'b': 0} and not absent and present_null}


def unknown_fields() -> dict:
    """核拒绝、清除和允许未知字段是不同合同。@return 实际事实。"""
    schema, source = {'name': {'type': 'string'}}, {'name': 'A', 'extra': 1}
    strict = Validator(schema)
    strict_result = strict.validate(source)
    purge = Validator(schema, purge_unknown=True)
    purged = purge.validated(source)
    allowed = Validator(schema, purge_unknown=True, allow_unknown=True).validated(source)
    return {'unknown_policy_distinguishes_reject_purge_and_allow': not strict_result
        and 'extra' in strict.errors and purged == {'name': 'A'} and allowed == source
        and source == {'name': 'A', 'extra': 1}}


def partial_update() -> dict:
    """核局部更新不免除所提供字段的依赖。@return 实际事实。"""
    schema = {'id': {'type': 'string', 'required': True},
        'confirm': {'type': 'boolean', 'dependencies': 'token'}, 'token': {'type': 'string'}}
    validator = Validator(schema)
    full = validator.validate({'token': 'synthetic'})
    partial = validator.validate({'token': 'synthetic'}, update=True)
    missing_dependency = validator.validate({'confirm': True}, update=True)
    errors = deepcopy(validator.errors)
    complete_partial = validator.validate({'confirm': True, 'token': 'synthetic'}, update=True)
    return {'update_skips_required_but_keeps_dependencies_of_present_fields': not full and partial
        and not missing_dependency and 'confirm' in errors and complete_partial}


def result_ownership() -> dict:
    """核同一实例的错误状态会被下一次处理替换。@return 实际事实。"""
    validator = Validator({'n': {'type': 'integer', 'min': 2}})
    first = validator.validate({'n': 0})
    saved = deepcopy(validator.errors)
    second = validator.validate({'n': 3})
    return {'validator_state_is_per_latest_call_and_saved_results_need_ownership':
        not first and 'n' in saved and second and validator.errors == {}
        and validator.document == {'n': 3}}


def main() -> None:
    """核候选源码绑定并输出本任务精确布尔合同。@return None。"""
    entries = {'CB-U01': (normalization, 'validate_normalizes_copy_unless_explicitly_disabled'),
        'CB-C01': (normalization, 'normalized_is_not_a_validation_success_result'),
        'CB-U02': (null_defaults, 'nullable_controls_null_defaults_and_required_still_means_present'),
        'CB-C02': (unknown_fields, 'unknown_policy_distinguishes_reject_purge_and_allow'),
        'CB-U03': (partial_update, 'update_skips_required_but_keeps_dependencies_of_present_fields'),
        'CB-P01': (result_ownership, 'validator_state_is_per_latest_call_and_saved_results_need_ownership')}
    observe, field = entries[sys.argv[1]]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(cerberus.__file__).resolve() == root / 'library/cerberus/__init__.py',
        field: observe()[field]}))


if __name__ == '__main__':
    main()
