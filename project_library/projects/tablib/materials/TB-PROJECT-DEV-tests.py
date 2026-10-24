"""公开表格字段投影回归。"""
import pytest
from tablib import Dataset
from tablib.projection import select_columns

def test_reorder_aliases_title_and_row_tags_are_preserved():
    data=Dataset(headers=['sku','qty'],title='Stock');data.append(['A',2],tags=['active'])
    result=select_columns(data,['qty','sku'],rename={'qty':'count'})
    assert result.headers==['count','sku'] and result[0]==(2,'A') and result.title=='Stock'
    assert result.filter('active').height==1 and data.headers==['sku','qty']

def test_nested_values_and_headers_are_detached():
    data=Dataset([{'values':[1]},2],headers=['payload','n']);result=select_columns(data,['payload'])
    result[0][0]['values'].append(2);assert data[0][0]=={'values':[1]}

def test_duplicate_or_missing_names_and_alias_collisions_fail():
    data=Dataset([1,2],headers=['a','b'])
    for columns in (['a','a'],['missing']):
        with pytest.raises(ValueError): select_columns(data,columns)
    with pytest.raises(ValueError): select_columns(data,['a','b'],rename={'b':'a'})

def test_projection_uses_raw_cells_without_running_export_formatters():
    data=Dataset(['raw'],headers=['v']);data._formatters=[(0,lambda value:'formatted')]
    assert select_columns(data,['v'])[0]==('raw',) and data.dict==[{'v':'formatted'}]
