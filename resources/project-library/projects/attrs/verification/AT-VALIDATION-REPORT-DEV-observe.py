"""独立核对 attrs 已公布的验证报告合同，反馈仅使用固定业务类别。"""
import json
import os
from pathlib import Path

import attrs
from attr.validation import ValidationIssue as AttrValidationIssue
from attrs.validation import MultiValidationError, ValidationIssue, validate_all


def _invalid_record():
    """构造冻结字段、原异常对象与一次调用计数。:return: 实例、调用列表及原始异常。"""
    seen = []
    errors = (TypeError('first'), ValueError('second'))

    def first(instance, attribute, value):
        """抛出第一字段原异常。:param instance: 实例。:param attribute: 字段。:param value: 值。:return: 不返回。"""
        seen.append(attribute.name)
        raise errors[0]

    def second(instance, attribute, value):
        """抛出第二字段原异常。:param instance: 实例。:param attribute: 字段。:param value: 值。:return: 不返回。"""
        seen.append(attribute.name)
        raise errors[1]

    @attrs.frozen
    class Record:
        """保留真实字段名与初始化别名。:param value: 私有字段值。:param other: 第二字段值。"""
        _private: int = attrs.field(alias='value', validator=first)
        other: int = attrs.field(validator=second)

    with attrs.validators.disabled():
        value = Record(1, 2)
    return value, seen, errors


def _composites():
    """核对组合验证的原始短路和一次迭代语义。:return: 是否符合已公布行为。"""
    seen = []
    first, member_error = ValueError('first'), LookupError('member')
    mapping_error, tail_error = TypeError('mapping'), RuntimeError('tail')

    def record(label, error=None):
        """创建只记录一次的验证器。:param label: 调用标识。:param error: 原异常。:return: 验证器。"""
        def validator(instance, attribute, value):
            """记录实际执行并保留原异常。:param instance: 实例。:param attribute: 字段。:param value: 值。:return: None。"""
            seen.append(label)
            if error is not None:
                raise error
        return validator

    def member(instance, attribute, value):
        """验证一次性迭代器成员。:param instance: 实例。:param attribute: 字段。:param value: 成员。:return: None。"""
        seen.append('member:' + str(value))
        if value < 0:
            raise member_error

    @attrs.define
    class Composite:
        """提供相互独立的组合验证字段。:param chained: 与校验。:param alternative: 或校验。:param optional: 可空值。:param stream: 迭代器。:param mapping: 映射。:param tail: 后续字段。"""
        chained = attrs.field(validator=attrs.validators.and_(record('and-ok'), record('and-first', first), record('never')))
        alternative = attrs.field(validator=attrs.validators.or_(record('or-first', TypeError()), record('or-second', KeyError())))
        optional = attrs.field(validator=attrs.validators.optional(record('optional', ValueError())))
        stream = attrs.field(validator=attrs.validators.deep_iterable(member))
        mapping = attrs.field(validator=attrs.validators.deep_mapping(
            key_validator=attrs.validators.instance_of(str), value_validator=record('mapping', mapping_error)))
        tail = attrs.field(validator=record('tail', tail_error))

    stream = iter([1, -2, -3])
    with attrs.validators.disabled():
        value = Composite(1, 2, None, stream, {'first': 1, 2: 2}, 3)
    issues = validate_all(value)
    return (seen == ['and-ok', 'and-first', 'or-first', 'or-second', 'member:1', 'member:-2', 'mapping', 'tail']
        and [issue.field_name for issue in issues] == ['chained', 'alternative', 'stream', 'mapping', 'tail']
        and issues[0].error is first and isinstance(issues[1].error, ValueError)
        and issues[2].error is member_error and issues[3].error is mapping_error and issues[4].error is tail_error
        and next(stream) == -3)


def _base_exception():
    """确认 BaseException 不被聚合吞掉。:return: 是否传播原对象。"""
    stopped = KeyboardInterrupt()

    def stop(instance, attribute, value):
        """抛出原中断对象。:param instance: 实例。:param attribute: 字段。:param value: 值。:return: 不返回。"""
        raise stopped

    @attrs.define
    class Model:
        """包含中断验证器。:param value: 被验证值。"""
        value = attrs.field(validator=stop)

    with attrs.validators.disabled():
        value = Model(1)
    try:
        validate_all(value)
    except KeyboardInterrupt as error:
        return error is stopped
    return False


def main():
    """执行公开合同对应矩阵并输出有界诊断。:return: None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    checks = dict.fromkeys(('attrs_report_order', 'attrs_report_identity', 'attrs_report_once',
        'attrs_report_values', 'attrs_report_aggregate', 'attrs_report_disabled',
        'attrs_report_composites', 'attrs_report_base_exception'), False)
    try:
        value, seen, errors = _invalid_record()
        issues = validate_all(value)
        fields = attrs.fields(type(value))
        checks['attrs_report_order'] = [issue.field_name for issue in issues] == ['_private', 'other']
        checks['attrs_report_identity'] = (ValidationIssue is AttrValidationIssue and len(issues) == 2
            and all(isinstance(issue, ValidationIssue) for issue in issues)
            and issues[0].attribute is fields._private and issues[1].attribute is fields.other
            and issues[0].error is errors[0] and issues[1].error is errors[1])
        checks['attrs_report_once'] = seen == ['_private', 'other']
        checks['attrs_report_values'] = value._private == 1 and value.other == 2
        # 普通 validate 的兼容性用新实例核对，避免观察器自身的第二次调用污染一次性计数。
        ordinary, calls, original_errors = _invalid_record()
        try:
            attrs.validate(ordinary)
            checks['attrs_report_once'] = False
        except Exception as error:
            checks['attrs_report_once'] = (checks['attrs_report_once']
                and calls == ['_private'] and error is original_errors[0])
    except Exception:
        pass
    try:
        value, seen, errors = _invalid_record()
        try:
            validate_all(value, raise_errors=True)
        except MultiValidationError as error:
            checks['attrs_report_aggregate'] = (isinstance(error.issues, tuple) and len(error.issues) == 2
                and [issue.field_name for issue in error.issues] == ['_private', 'other']
                and error.issues[0].error is errors[0] and error.issues[1].error is errors[1]
                and seen == ['_private', 'other'])
    except Exception:
        pass
    try:
        value, seen, _ = _invalid_record()
        with attrs.validators.disabled():
            checks['attrs_report_disabled'] = (validate_all(value) == ()
                and validate_all(value, raise_errors=True) == () and not seen)
    except Exception:
        pass
    for code, check in (('attrs_report_composites', _composites), ('attrs_report_base_exception', _base_exception)):
        try:
            checks[code] = bool(check())
        except Exception:
            pass
    print(json.dumps({'candidate_import': Path(attrs.__file__).resolve().is_relative_to(root / 'library'),
        'business': all(checks.values()), 'feedback_codes': [code for code, passed in checks.items() if not passed]}))


if __name__ == '__main__':
    main()
