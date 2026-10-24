"""批量更新真实同步schema，缺字段不变成NULL。"""
import dataset
import pytest
from sqlalchemy import Integer

def test_new_column_override_type_and_partial_row_shapes():
    """原生SQL实际创建并更新新增列，省略字段保持原值。@return None。"""
    db=dataset.connect('sqlite://');t=db['items'];t.insert_many([{'key':'a','keep':'old-a'},{'key':'b','keep':'old-b'}])
    t.update_many([{'key':'a','score':3},{'key':'b','keep':'next'}],['key'],types={'score':Integer})
    assert t.find_one(key='a')['score']==3 and t.find_one(key='a')['keep']=='old-a'
    assert t.find_one(key='b')['keep']=='next' and isinstance(t.table.c.score.type,Integer)
    db.close()

def test_missing_keys_checked_before_any_update_or_schema():
    """后行缺匹配键也不能先写前行或建新列。@return None。"""
    db=dataset.connect('sqlite://');t=db['items'];t.insert({'key':'a','x':1})
    with pytest.raises(KeyError):t.update_many([{'key':'a','new':2},{'new':3}],['key'],chunk_size=1)
    assert 'new' not in t.columns and t.find_one(key='a')['x']==1
    db.close()

def test_ensure_false_empty_and_bind_name_collision():
    """禁用自动schema丢弃未知字段，空输入不建表。@return None。"""
    db=dataset.connect('sqlite://');empty=db['empty'];empty.update_many([],['id']);assert not empty.exists
    t=db['items'];t.insert({'key':'a','_key':1})
    t.update_many([{'key':'a','_key':2,'unknown':9}],['key'],ensure=False)
    assert 'unknown' not in t.columns and t.find_one(key='a')['_key']==2
    db.close()
