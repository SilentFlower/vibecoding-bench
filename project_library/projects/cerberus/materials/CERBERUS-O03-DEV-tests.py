"""字段比较使用受控操作符与真实归一化文档。"""
from cerberus import Validator

def test_normalized_sibling_comparison():
    """转换后比较起止字段。@return None。"""
    schema = {'start': {'coerce': int, 'compare_to': {'field': 'end', 'operator': 'le'}}, 'end': {'coerce': int}}
    validator = Validator(schema)
    assert validator.validate({'start': '2', 'end': '3'})
    assert not validator.validate({'start': '4', 'end': '3'})

def test_root_reference_and_missing():
    """嵌套可显式引用根，缺失政策可选。@return None。"""
    validator = Validator({'limit': {'type': 'integer'}, 'child': {'type': 'dict', 'schema': {'value': {'compare_to': {'field': '^limit', 'operator': 'lt'}}}}})
    assert validator.validate({'limit': 5, 'child': {'value': 4}})
    assert not validator.validate({'limit': 5, 'child': {'value': 6}})
    assert Validator({'x': {'compare_to': {'field': 'missing', 'operator': 'eq', 'missing': 'ignore'}}}).validate({'x': 1})

def test_incomparable_and_invalid_operator():
    """不比较类型和未知操作符不会执行表达式。@return None。"""
    import pytest
    from cerberus import SchemaError
    validator = Validator({'a': {'compare_to': {'field': 'b', 'operator': 'lt'}}, 'b': {}})
    assert not validator.validate({'a': 1, 'b': 'text'})
    with pytest.raises(SchemaError): Validator({'a': {'compare_to': {'field': 'b', 'operator': 'eval'}}})
