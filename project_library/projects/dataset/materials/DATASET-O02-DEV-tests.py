"""投影发生在真实SQL SELECT，保持过滤排序及row_type。"""
import dataset
import pytest

def test_find_findone_order_and_named_projection():
    """只返回指定顺序列，过滤及降序不需出现在投影中。@return None。"""
    db=dataset.connect('sqlite://');t=db['items'];t.insert_many([{'sku':'a','qty':1,'secret':'x'},{'sku':'b','qty':3,'secret':'y'}])
    rows=list(t.find(_columns=['sku','qty'],order_by='-qty',qty={'>':0}))
    assert list(rows[0])==['sku','qty'] and rows[0]['sku']=='b' and 'secret' not in rows[0]
    assert t.find_one(sku='a',_columns='qty')=={'qty':1}
    db.close()

def test_invalid_empty_duplicate_unknown_and_space_name():
    """列名走SQLAlchemy引用，不拼SQL。@return None。"""
    db=dataset.connect('sqlite://');t=db['items'];t.insert({'with space':'ok'})
    assert t.find_one(_columns=['with space'])=={'with space':'ok'}
    for columns in [[],['id','id'],['missing']]:
        with pytest.raises(ValueError):list(t.find(_columns=columns))
    db.close()

def test_streamed_custom_row_type_and_no_match():
    """真实流式和自定义row_type按投影字段转换。@return None。"""
    db=dataset.connect('sqlite://',row_type=lambda items:tuple(items));t=db['items'];t.insert({'x':1,'y':2})
    assert list(t.find(_columns=['y'],_streamed=True))==[(('y',2),)]
    assert t.find_one(x=999,_columns=['y']) is None
    db.close()
