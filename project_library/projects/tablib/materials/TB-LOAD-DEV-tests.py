"""公开真实表格导入端到端回归。"""
from decimal import Decimal
import pytest
from tablib.loading import load_records

def test_aliases_and_reordered_records_follow_explicit_output_columns():
    records=[{'sku':'A','quantity':'2'},{'quantity':'3','sku':'B'}]
    result=load_records(iter(records),['id','qty'],aliases={'id':'sku','qty':'quantity'},converters={'qty':int})
    assert result.dataset.headers==['id','qty'] and list(result.dataset)==[('A',2),('B',3)] and records[0]['quantity']=='2'

def test_falsey_missing_and_extra_policies_are_not_conflated():
    result=load_records([{'n':0,'flag':False,'text':'','extra':1}],['n','flag','text','missing'],missing='none',extra='ignore')
    assert result.dataset[0]==(0,False,'',None)
    with pytest.raises(ValueError): load_records([{'n':1,'extra':2}],['n'])

def test_conversion_collection_and_empty_dataset_keep_schema():
    result=load_records([{'n':'bad'},{'n':'2'}],['n'],converters={'n':int},errors='collect')
    assert result.errors[0].row==0 and list(result.dataset)==[('bad',),(2,)]
    empty=load_records([],['n'],title='Empty');assert empty.dataset.headers==['n'] and empty.dataset.title=='Empty'

def test_input_failure_and_alias_collision_are_explicit():
    records=[{'a':1},7]
    with pytest.raises(TypeError): load_records(records,['a'])
    with pytest.raises(ValueError): load_records([],['a','b'],aliases={'b':'a'})
    assert records==[{'a':1},7]
