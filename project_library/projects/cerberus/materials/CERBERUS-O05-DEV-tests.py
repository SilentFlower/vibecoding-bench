"""结果外壳和本次文档错误快照应独立于后续调用。"""
from dataclasses import FrozenInstanceError
import pytest
from cerberus import Validator

def test_result_survives_next_call():
    """第一次失败结果不会被第二次成功覆盖。@return None。"""
    validator = Validator({'count': {'type': 'integer'}})
    first = validator.validate_result({'count': 'bad'})
    second = validator.validate_result({'count': 4})
    assert not first.valid and first.errors and second.valid and second.errors == {}
    assert first.document == {'count': 'bad'} and first.completed

def test_deep_snapshot_and_frozen_shell():
    """嵌套内容与Validator不共享，外壳字段不可重赋。@return None。"""
    validator = Validator({'rows': {'type': 'list'}})
    result = validator.validate_result({'rows': [{'x': 1}]})
    result.document['rows'][0]['x'] = 9
    assert validator.document['rows'][0]['x'] == 1
    with pytest.raises(FrozenInstanceError): result.valid = False

def test_normalization_and_update_options():
    """真实归一化和update参数保留。@return None。"""
    validator = Validator({'count': {'coerce': int}, 'required': {'required': True}})
    result = validator.validate_result({'count': '3'}, update=True)
    assert result.valid and result.document == {'count': 3}
