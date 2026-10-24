"""公开按列业务格式化回归。"""
import pytest
from tabulate import tabulate,SEPARATING_LINE
from tabulate.formatters import tabulate_with_formatters

def test_column_callbacks_receive_business_coordinates():
    seen=[];rows=[[1,'a'],SEPARATING_LINE,[2,'b']]
    def convert(value,row,column):
        seen.append((value,row,column))
        return str(value)+' units'
    result=tabulate_with_formatters(rows,formatters=[convert],tablefmt='plain')
    assert seen==[(1,0,0),(2,1,0)] and '1 units' in result and rows[0]==[1,'a']

def test_mapping_keys_and_disabled_numeric_parse_are_preserved():
    result=tabulate_with_formatters([{'code':1}],headers='keys',formatters=[lambda value,row,col:'001'],disable_numparse=True,tablefmt='plain')
    assert 'code' in result and '001' in result

def test_ragged_cells_are_not_synthesized_for_callbacks():
    seen=[]
    tabulate_with_formatters([[1],[2,3]],formatters=[None,lambda value,row,col:not seen.append((value,row,col))])
    assert seen==[(3,1,1)]

def test_invalid_and_failing_callbacks_leave_input_unchanged():
    rows=[[1]]
    with pytest.raises(TypeError):
        tabulate_with_formatters(rows,formatters=[3])
    def fail(*args):
        raise LookupError('synthetic')
    with pytest.raises(LookupError):
        tabulate_with_formatters(rows,formatters=[fail])
    assert rows==[[1]]
