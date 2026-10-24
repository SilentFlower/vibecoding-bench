"""公开查询列投影回归。"""
import json
import pytest
from cli_helpers.tabular_output.projection import select_columns
from cli_helpers.tabular_output import TabularOutputFormatter

def test_name_and_index_selection_preserve_order_and_duplicates():
    rows,headers=select_columns([[1,'a',3]],['id','name','n'],['name',0,'name'])
    assert headers==['name','id','name'] and list(rows)==[['a',1,'a']]

def test_projection_is_lazy_and_original_values_are_preserved():
    consumed=[];value=object()
    def data():
        consumed.append(1)
        yield [value,2]
    rows,headers=select_columns(data(),['a','b'],[0])
    assert consumed==[] and next(rows)[0] is value and consumed==[1]

def test_ambiguous_headers_invalid_indices_and_ragged_rows_fail():
    for selection in (['a'],[-1],[True],[2]):
        with pytest.raises((ValueError,TypeError,IndexError)):
            select_columns([],['a','a'],selection)
    rows,headers=select_columns([[1]],['a','b'],[0])
    with pytest.raises(ValueError):
        next(rows)

def test_projected_values_integrate_with_real_json_formatter():
    rows,headers=select_columns([[1,'a']],['id','name'],['name','id'])
    result=list(TabularOutputFormatter('jsonl').format_output(rows,headers))
    assert json.loads(result[0])=={'name':'a','id':1}
