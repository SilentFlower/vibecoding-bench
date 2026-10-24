"""一次性输入分批实际写库，失败事务边界清楚。"""
import dataset
import pytest

def test_single_pass_chunks_and_late_columns():
    """观察每批写入发生在后续生成之前，后批新列可建。@return None。"""
    db=dataset.connect('sqlite://');t=db['items'];events=[]
    def rows():
        for n in range(5):
            if n==2:events.append(t.count())
            yield {'n':n,**({'later':'yes'} if n==4 else {})}
    assert t.insert_iter(rows(),chunk_size=2)==5 and events==[2] and t.count()==5
    assert t.find_one(n=4)['later']=='yes';db.close()

def test_atomic_generator_error_rolls_back_prior_dml():
    """已存在表的整次DML事务可回滚，非atomic保留先前批次。@return None。"""
    db=dataset.connect('sqlite://');t=db['items'];t.insert({'n':-1})
    def broken():
        yield {'n':1};yield {'n':2};raise RuntimeError('input')
    with pytest.raises(RuntimeError):t.insert_iter(broken(),chunk_size=1,atomic=True)
    assert t.count()==1
    with pytest.raises(RuntimeError):t.insert_iter(broken(),chunk_size=1)
    assert t.count()==3;db.close()

def test_update_iter_scope_bounds_and_empty():
    """更新迭代保留省略字段，边界非法不消费输入。@return None。"""
    db=dataset.connect('sqlite://');t=db['items'];t.insert_many([{'key':'a','x':1,'y':2},{'key':'b','x':3,'y':4}])
    assert t.update_iter(iter([{'key':'a','x':8},{'key':'b','y':9}]),['key'],chunk_size=2)==2
    assert t.find_one(key='a')['y']==2 and t.find_one(key='b')['x']==3
    assert t.insert_iter(iter([]))==0
    with pytest.raises(ValueError):t.insert_iter(iter([]),chunk_size=0)
    db.close()
