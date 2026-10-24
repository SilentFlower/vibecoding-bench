"""公开重复JSON对象列名回归。"""
import json
import pytest
from cli_helpers.tabular_output.json_output_adapter import adapter

def test_default_and_error_modes_are_explicit():
    assert json.loads(next(adapter([[1,2]],['a','a'])))=={'a':2}
    with pytest.raises(ValueError):
        next(adapter([[1,2]],['a','a'],duplicate_headers='error'))

def test_suffix_mode_reserves_existing_real_names():
    value=json.loads(next(adapter([[1,2,3,4]],['a','a','a_2','a'],duplicate_headers='suffix')))
    assert value=={'a':1,'a_3':2,'a_2':3,'a_4':4}

def test_one_shot_headers_are_reused_for_every_row():
    result=list(adapter([[1],[2]],iter(['name']),duplicate_headers='error'))
    assert [json.loads(row) for row in result]==[{'name':1},{'name':2}]

def test_rejection_does_not_consume_data_and_input_headers_are_unchanged():
    headers=['a','a'];consumed=[]
    def rows():
        consumed.append(1)
        yield [1,2]
    with pytest.raises(ValueError):
        next(adapter(rows(),headers,duplicate_headers='error'))
    assert consumed==[] and headers==['a','a']
