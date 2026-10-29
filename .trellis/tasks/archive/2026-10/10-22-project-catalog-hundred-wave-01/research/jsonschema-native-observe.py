"""独立观察固定JSON Schema的注解、格式、类型、组合与离线引用。"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import sys

import jsonschema
from jsonschema import Draft7Validator, Draft202012Validator, FormatChecker
from jsonschema.validators import extend
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable


def configuration() -> dict:
    """核注解不会改输入，批量错误保留真实位置。@return 配置事实。"""
    schema = {'type': 'object', 'properties': {'retries': {'type': 'integer', 'default': 3}},
        'required': ['retries']}
    payload = {}
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    nested = {'type': 'object', 'properties': {'orders': {'type': 'array',
        'items': {'type': 'object', 'properties': {'qty': {'type': 'integer', 'minimum': 1}}, 'required': ['qty']}}}}
    rows = {'orders': [{'qty': 0}, {'qty': 'many'}, {}]}
    all_errors = list(Draft202012Validator(nested).iter_errors(rows))
    return {'default_is_annotation_and_input_stays_unchanged': payload == {} and len(errors) == 1
            and errors[0].validator == 'required' and Draft202012Validator(schema).is_valid({'retries': 3}),
        'error_list_keeps_paths_and_independent_failures': len(all_errors) == 3
            and {(tuple(error.path), error.validator) for error in all_errors}
                == {(('orders', 0, 'qty'), 'minimum'), (('orders', 1, 'qty'), 'type'), (('orders', 2), 'required')}}


def formats() -> dict:
    """核format显式启用、未知格式及局部异常原因。@return 格式事实。"""
    schema = {'type': 'string', 'format': 'email'}
    checker = FormatChecker()
    scoped = FormatChecker()

    @scoped.checks('warehouse-bin', raises=ValueError)
    def warehouse_bin(value):
        """只校验业务字符串，保留可报告原因。@param value 实际值。@return 是否为合法货位。"""
        if not isinstance(value, str):
            return True
        if not value.startswith('BIN-') or not value[4:].isdigit():
            raise ValueError('expected BIN followed by digits')
        return True

    local_schema = {'type': 'string', 'format': 'warehouse-bin'}
    failure = next(Draft202012Validator(local_schema, format_checker=scoped).iter_errors('rack-A'))
    return {'format_needs_explicit_checker_and_unknown_is_ignored': Draft202012Validator(schema).is_valid('broken')
            and not Draft202012Validator(schema, format_checker=checker).is_valid('broken')
            and Draft202012Validator(schema, format_checker=checker).is_valid('a@example.test')
            and Draft202012Validator({'format': 'typo-format'}, format_checker=checker).is_valid('anything'),
        'local_format_does_not_mutate_other_checkers': isinstance(failure.cause, ValueError)
            and Draft202012Validator(local_schema, format_checker=scoped).is_valid('BIN-12')
            and 'warehouse-bin' not in FormatChecker().checkers and 'warehouse-bin' not in checker.checkers}


def numeric_types() -> dict:
    """核JSON整数与Python继承区别、已有局部扩展能力。@return 类型事实。"""
    validator = Draft202012Validator({'type': 'integer'})
    original = Draft202012Validator.TYPE_CHECKER

    def decimal_integer(checker, value):
        """保留原类型判断并显式扩展有限Decimal整数。@param checker 调用检查器。@param value 原值。@return 合法性。"""
        return original.is_type(value, 'integer') or (
            isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value())

    extended = extend(Draft202012Validator, type_checker=original.redefine('integer', decimal_integer))
    local = extended({'type': 'integer'})
    return {'integer_excludes_bool_but_accepts_integral_float': not validator.is_valid(True)
            and validator.is_valid(1) and validator.is_valid(1.0) and not validator.is_valid(1.5),
        'decimal_extension_is_local_and_keeps_integer_rules': not validator.is_valid(Decimal('2'))
            and local.is_valid(Decimal('2')) and not local.is_valid(Decimal('2.5'))
            and not local.is_valid(Decimal('NaN')) and not local.is_valid(True)
            and Draft202012Validator.TYPE_CHECKER is original and not validator.is_valid(Decimal('2'))}


def composed_properties() -> dict:
    """核分支局部additionalProperties与2020-12组合求值。@return 组合事实。"""
    schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'type': 'object',
        'allOf': [{'properties': {'name': {'type': 'string'}}, 'required': ['name']},
            {'properties': {'age': {'type': 'integer'}}, 'required': ['age']}]}
    local_closed = deepcopy(schema)
    for branch in local_closed['allOf']:
        branch['additionalProperties'] = False
    closed = {**schema, 'unevaluatedProperties': False}
    payload = {'name': 'Ada', 'age': 30}
    return {'additional_properties_is_branch_local': not Draft202012Validator(local_closed).is_valid(payload),
        'unevaluated_properties_closes_successfully_evaluated_composition': Draft202012Validator(closed).is_valid(payload)
            and not Draft202012Validator(closed).is_valid({**payload, 'debug': True})
            and Draft7Validator(closed).is_valid({**payload, 'debug': True})}


def offline_references() -> dict:
    """只读注册受控内存资源，未知引用不回退到网络。@return 引用事实。"""
    resource = Resource.from_contents({'$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'urn:catalog:quantity', 'type': 'integer', 'minimum': 1})
    empty = Registry()
    registry = empty.with_resource('urn:catalog:quantity', resource)
    schema = {'$ref': 'urn:catalog:quantity'}
    validator = Draft202012Validator(schema, registry=registry)
    missing = False
    try:
        Draft202012Validator({'$ref': 'urn:catalog:missing'}, registry=registry).validate(1)
    except Unresolvable:
        missing = True
    return {'registry_has_explicit_resources_and_rejects_unknown': validator.is_valid(2)
        and not validator.is_valid(0) and missing and len(empty) == 0 and len(registry) == 1}


def main() -> None:
    """确认实际候选导入并输出当前任务的独立断言。@return None。"""
    task = sys.argv[1]
    entries = {'JV-U01': (configuration, ['default_is_annotation_and_input_stays_unchanged']),
        'JV-C01': (configuration, ['error_list_keeps_paths_and_independent_failures']),
        'JV-C02': (formats, ['format_needs_explicit_checker_and_unknown_is_ignored', 'local_format_does_not_mutate_other_checkers']),
        'JV-U02': (numeric_types, ['integer_excludes_bool_but_accepts_integral_float']),
        'JV-P01': (numeric_types, ['decimal_extension_is_local_and_keeps_integer_rules']),
        'JV-U03': (composed_properties, ['additional_properties_is_branch_local']),
        'JV-C03': (composed_properties, ['unevaluated_properties_closes_successfully_evaluated_composition']),
        'JV-P02': (offline_references, ['registry_has_explicit_resources_and_rejects_unknown'])}
    observe, fields = entries[task]
    facts = observe()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(jsonschema.__file__).resolve() == root / 'library/jsonschema/__init__.py',
        **{field: facts[field] for field in fields}}))


if __name__ == '__main__':
    main()
