"""核候选cattrs的真实结构化、线缆格式和错误路径。"""
from base64 import b85encode
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import attrs
import cattrs
from cattrs import ClassValidationError, Converter, ForbiddenExtraKeysError, transform_error
from cattrs.preconf.json import make_converter


@attrs.define
class Product:
    """合成输入行。"""
    name: str
    quantity: int


@attrs.define
class Exchange:
    """带日期与二进制附件的合成交换包。"""
    items: list[Product]
    created: datetime
    attachment: bytes


@attrs.define
class Aliased:
    """构造别名与存储字段名不同的合成记录。"""
    _quantity: int = attrs.field(alias='quantity')


@attrs.define
class Order:
    """用于聚合嵌套错误的合成订单。"""
    customer_id: int
    items: list[Product]


def main() -> None:
    """执行单条固定业务，不访问数据服务或发布对象。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(cattrs.__file__).resolve() == root / 'library/src/cattrs/__init__.py'}
    task = sys.argv[1]
    if task == 'CA-U01':
        payload = {'name': 'tea', 'quantity': '2', 'extra': 'LOCAL'}
        converted = Converter().structure(payload, Product)
        strict_extra_rejected = False
        try:
            Converter(forbid_extra_keys=True).structure(payload, Product)
        except ClassValidationError as error:
            strict_extra_rejected = any(isinstance(item, ForbiddenExtraKeysError) for item in error.exceptions)
        result['structuring_coerces_values_and_extra_key_rejection_is_a_separate_option'] = (
            converted == Product('tea', 2) and type(converted.quantity) is int
            and strict_extra_rejected and Converter(forbid_extra_keys=True).structure({'name': 'tea', 'quantity': '2'}, Product) == converted)
    elif task == 'CA-U02':
        converter = make_converter()
        value = Exchange([Product('tea', 2)], datetime(2026, 4, 3, 10, 1, 2, tzinfo=timezone.utc), b'hello')
        encoded = converter.dumps(value)
        plain = json.loads(encoded)
        result['json_preconfiguration_roundtrips_nested_types_iso_dates_and_base85_bytes'] = (
            plain['created'] == '2026-04-03T10:01:02+00:00'
            and plain['attachment'] == b85encode(b'hello').decode()
            and plain['items'] == [{'name': 'tea', 'quantity': 2}]
            and converter.loads(encoded, Exchange) == value)
    elif task == 'CA-C01':
        stored, aliased = Converter(), Converter(use_alias=True)
        first = stored.structure({'_quantity': '2'}, Aliased)
        second = aliased.structure({'quantity': '2'}, Aliased)
        result['constructor_aliases_and_wire_dictionary_keys_follow_explicit_converter_policy'] = (
            first == second == Aliased(2) and stored.unstructure(first) == {'_quantity': 2}
            and aliased.unstructure(second) == {'quantity': 2})
    elif task == 'CA-C02':
        strict, permissive = Converter(), Converter()

        def exact_integer(value, target):
            """演示当前精确类型钩子。@param value 输入。@param target 目标类型。@return 已验证整数。"""
            if type(value) is not int:
                raise TypeError('exact integer required')
            return value

        strict.register_structure_hook(int, exact_integer)
        rejected = []
        for value in ('2', True):
            try:
                strict.structure(value, int)
            except TypeError:
                rejected.append(value)
        result['custom_hooks_are_owned_by_converter_instances_and_global_helpers_remain_separate'] = (
            len(rejected) == 2 and strict.structure(2, int) == 2
            and permissive.structure('2', int) == cattrs.structure('2', int) == 2)
    elif task == 'CA-P01':
        converter = Converter(detailed_validation=True)
        messages = []
        try:
            converter.structure({'customer_id': 'bad', 'items': [
                {'name': 'tea', 'quantity': 'bad'}, {'name': 'mug', 'quantity': '3'}]}, Order)
        except ClassValidationError as error:
            messages = transform_error(error)
        good = converter.structure({'customer_id': '1', 'items': [{'name': 'tea', 'quantity': '2'}]}, Order)
        paths = sorted(message.rsplit(' @ ', 1)[-1] for message in messages)
        result['detailed_errors_keep_nested_paths_and_support_validate_before_application_publication'] = (
            paths == ['$.customer_id', '$.items[0].quantity'] and good == Order(1, [Product('tea', 2)]))
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
