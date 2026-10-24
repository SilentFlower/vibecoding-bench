"""实际单条UPDATE累加值，NULL和类型政策明确。"""
import dataset
import pytest
from sqlalchemy import Integer

def test_atomic_deltas_filter_and_zero():
    """正负与零增量保留过滤，未命中返回零。@return None。"""
    db=dataset.connect('sqlite://');t=db['stock'];t.insert({'sku':'a','qty':10})
    assert t.increment('qty',-3,{'sku':'a'})==1 and t.increment('qty',2,{'sku':'a'})==1
    assert t.find_one(sku='a')['qty']==9 and t.increment('qty',0,{'sku':'none'})==0
    db.close()

def test_null_and_type_validation_before_change():
    """NULL可保留或明确按零，文本列不能隐式转数值。@return None。"""
    db=dataset.connect('sqlite://');t=db['items'];t.insert({'name':'x','n':None},types={'n':Integer})
    t.increment('n',2,{},nulls='preserve');assert t.find_one()['n'] is None
    t.increment('n',2,{},nulls='zero');assert t.find_one()['n']==2
    for column,amount,error in [('name',1,TypeError),('n',True,TypeError),('n',float('inf'),ValueError)]:
        with pytest.raises(error):t.increment(column,amount,{})
    assert t.find_one()['name']=='x';db.close()

def test_two_connections_and_rollback(tmp_path):
    """两个连接的数据库表达式累计，无读后写丢失。@return None。"""
    url='sqlite:///'+str(tmp_path/'db.sqlite');a=dataset.connect(url);b=dataset.connect(url)
    a['items'].insert({'key':'a','n':0});a['items'].increment('n',2,{});b['items'].increment('n',3,{})
    assert a['items'].find_one()['n']==5
    with pytest.raises(RuntimeError):
        with a:
            a['items'].increment('n',10,{})
            raise RuntimeError('abort')
    assert b['items'].find_one()['n']==5;a.close();b.close()
