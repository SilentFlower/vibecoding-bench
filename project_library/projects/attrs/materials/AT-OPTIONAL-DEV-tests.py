"""公开字符串注解可选转换回归。"""
import typing
import attrs

def test_string_parameter_and_return_annotations_are_supported():
    def convert(value: 'str') -> 'int':
        return int(value)
    wrapped = attrs.converters.optional(convert)
    assert wrapped('17') == 17 and wrapped(None) is None

def test_unknown_forward_references_are_not_resolved_during_wrapping():
    def convert(value):
        return value
    convert.__annotations__ = {'value':'UnknownBusinessType', 'return':'UnknownBusinessType'}
    wrapped = attrs.converters.optional(convert)
    assert wrapped(3) == 3 and wrapped(None) is None

def test_original_annotations_are_not_changed():
    def convert(value: 'str') -> 'int':
        return int(value)
    before = dict(convert.__annotations__)
    attrs.converters.optional(convert)
    assert convert.__annotations__ == before

def test_real_type_annotations_keep_optional_semantics():
    def convert(value: str) -> int:
        return int(value)
    wrapped = attrs.converters.optional(convert)
    assert wrapped.__annotations__['val'] == typing.Optional[str]
    assert wrapped.__annotations__['return'] == typing.Optional[int]

def test_builtin_and_unannotated_converters_still_work():
    assert attrs.converters.optional(int)('4') == 4
    assert attrs.converters.optional(lambda value: value + 1)(2) == 3

def test_optional_converter_can_be_used_in_a_real_model():
    def convert(value: 'str') -> 'int':
        return int(value)
    @attrs.define
    class Order:
        quantity = attrs.field(converter=attrs.converters.optional(convert))
    assert Order('8').quantity == 8 and Order(None).quantity is None
