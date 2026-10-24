"""异常退出只处理未提交队列，不承诺撤销此前批次。"""
import dataset
from dataset.chunked import ChunkedInsert,ChunkedUpdate
import pytest

def test_discard_only_pending_and_original_error_preserved():
    """已满批次保留，异常时尾部不写且应用异常不变。@return None。"""
    db=dataset.connect('sqlite://');t=db['items']
    with pytest.raises(RuntimeError,match='application'):
        with ChunkedInsert(t,chunksize=2,on_error='discard') as writer:
            writer.insert({'n':1});writer.insert({'n':2});writer.insert({'n':3});raise RuntimeError('application')
    assert [row['n'] for row in t.find(order_by='n')]==[1,2]
    assert writer.queue==[] and writer.fields==set();db.close()

def test_default_flush_and_normal_discard_mode_completion():
    """默认异常仍flush兼容，discard只在异常时生效。@return None。"""
    db=dataset.connect('sqlite://');t=db['items']
    with pytest.raises(RuntimeError):
        with ChunkedInsert(t) as writer:writer.insert({'n':1});raise RuntimeError('app')
    with ChunkedInsert(t,on_error='discard') as writer:writer.insert({'n':2})
    assert t.count()==2;db.close()

def test_update_discard_callback_and_transaction_rollback():
    """丢弃不调用callback，外层事务仍可回滚已刷批次。@return None。"""
    db=dataset.connect('sqlite://');t=db['items'];t.insert({'key':'a','n':1});calls=[]
    with pytest.raises(RuntimeError):
        with ChunkedUpdate(t,['key'],on_error='discard',callback=lambda rows:calls.append(rows)) as writer:
            writer.update({'key':'a','n':9});raise RuntimeError('app')
    assert calls==[] and t.find_one()['n']==1
    with pytest.raises(RuntimeError):
        with db:
            with ChunkedInsert(t,chunksize=1,on_error='discard') as writer:
                writer.insert({'key':'b','n':2});raise RuntimeError('app')
    assert t.count()==1;db.close()
