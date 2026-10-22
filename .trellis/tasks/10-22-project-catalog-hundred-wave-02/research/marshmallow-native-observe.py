"""独立核反序列化、未知字段、失败发布和日期类型边界。"""
import datetime as dt
import json
import os
from pathlib import Path
import sys

import marshmallow
from marshmallow import EXCLUDE, INCLUDE, Schema, ValidationError, fields


def rejects(action) -> bool:
    """只将实际ValidationError当预期拒绝。@param action 调用。@return 是否拒绝。"""
    try:
        action()
    except ValidationError:
        return True
    return False


def positive(value):
    """拒绝非正订单数量。@param value 已转换值。@return None。"""
    if value <= 0:
        raise ValidationError('Positive quantity required.')


class Order(Schema):
    """只使用已核字段与签名的合成订单。"""
    sku = fields.String(required=True, data_key='product')
    qty = fields.Integer(required=True, strict=True, validate=positive)


def main() -> None:
    """按独立任务核候选事实。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(marshmallow.__file__).resolve() == root / 'library/src/marshmallow/__init__.py'}
    task = sys.argv[1]
    if task == 'MM-U01':
        class Credentials(Schema):
            """区分外部键、内部属性和输入／输出字段。"""
            name = fields.String(data_key='displayName', attribute='label')
            secret = fields.String(load_only=True)
            ident = fields.Integer(dump_only=True)
        schema = Credentials()
        loaded = schema.load({'displayName': 'A', 'secret': 'SYNTHETIC'})
        dumped = schema.dump({'label': 'A', 'secret': 'SYNTHETIC', 'ident': 7})
        result['external_internal_and_directional_fields_are_distinct'] = (
            loaded == {'label': 'A', 'secret': 'SYNTHETIC'} and dumped == {'displayName': 'A', 'ident': 7}
            and rejects(lambda: schema.load({'ident': 7})))
    elif task == 'MM-U02':
        data = {'sku': 'A', 'qty': -2}
        result['dump_does_not_run_load_validators'] = (
            Order().dump(data) == {'product': 'A', 'qty': -2}
            and rejects(lambda: Order().load({'product': 'A', 'qty': -2})))
    elif task == 'MM-C01':
        data = {'product': 'A', 'qty': 2, 'extra': 'opaque'}
        result['unknown_policies_are_explicit_and_include_is_not_validation'] = (
            rejects(lambda: Order().load(data))
            and Order(unknown=EXCLUDE).load(data) == {'sku': 'A', 'qty': 2}
            and Order(unknown=INCLUDE).load(data) == {'sku': 'A', 'qty': 2, 'extra': 'opaque'}
            and data['extra'] == 'opaque')
    elif task == 'MM-C02':
        schema = Order()
        result['partial_skips_missing_fields_but_not_present_invalid_values'] = (
            schema.load({}, partial=True) == {}
            and schema.load({'qty': 3}, partial=('sku',)) == {'qty': 3}
            and rejects(lambda: schema.load({'qty': None}, partial=True))
            and rejects(lambda: schema.load({'qty': -1}, partial=True))
            and rejects(lambda: schema.load({'qty': 3}, partial=('qty',))))
    elif task == 'MM-P01':
        data = [{'product': 'A', 'qty': 2}, {'product': 'B', 'qty': -1}]
        try:
            Order(many=True).load(data)
        except ValidationError as error:
            result['failed_many_valid_data_is_partial_not_accepted_batch'] = (
                set(error.messages) == {1} and 'qty' in error.messages[1]
                and error.valid_data == [{'sku': 'A', 'qty': 2}, {'sku': 'B'}] and error.data is data)
        else:
            result['failed_many_valid_data_is_partial_not_accepted_batch'] = False
    elif task == 'MM-M01':
        class DateChild(dt.date):
            """保留原来支持的date子类。"""
        field = fields.Date()
        value = dt.date(2026, 4, 3)
        child = DateChild(2026, 4, 3)
        inputs = [dt.datetime(2026, 4, 3, 23, 59), dt.datetime(2026, 4, 3, tzinfo=dt.timezone.utc)]
        class Shipment(Schema):
            """为字段错误提供正常外部键。"""
            day = fields.Date(data_key='shipDate')
        result['date_rejects_datetime_without_truncation_and_preserves_date_controls'] = (
            all(rejects(lambda value=value: field.deserialize(value)) for value in inputs)
            and rejects(lambda: Shipment().load({'shipDate': inputs[0]}))
            and field.deserialize(value) is value and field.deserialize(child) is child
            and type(field.deserialize('2026-04-03')) is dt.date
            and fields.Date(format='%d/%m/%Y').deserialize('03/04/2026') == value
            and fields.Date(allow_none=True).deserialize(None) is None
            and rejects(lambda: field.deserialize('2026-04-03T00:00:00'))
            and fields.DateTime().deserialize(inputs[0]) is inputs[0])
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
