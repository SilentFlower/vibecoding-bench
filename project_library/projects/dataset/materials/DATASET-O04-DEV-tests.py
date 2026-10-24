"""结果上下文提前退出、转换失败和资源异常均清理。"""
import dataset
import pytest

def test_real_streamed_early_exit_leaves_database_usable():
    """退出游标上下文不关闭共享Database。@return None。"""
    db=dataset.connect('sqlite://');table=db['items'];table.insert_many([{'x':1},{'x':2}])
    with table.find(_streamed=True) as result:
        assert next(result)['x']==1;connection=result._conn;proxy=result.result_proxy
    assert connection.closed and proxy.closed and table.count()==2
    result.close();assert list(result)==[];db.close()

def test_conversion_error_releases_actual_result():
    """row_type抛错也释放专用连接。@return None。"""
    db=dataset.connect('sqlite://');table=db['items'];table.insert({'x':1})
    result=table.find(_streamed=True);connection=result._conn;proxy=result.result_proxy
    def fail(items):raise ValueError('conversion')
    result.row_type=fail
    with pytest.raises(ValueError,match='conversion'):next(result)
    assert connection.closed and proxy.closed;db.close()

def test_cleanup_failure_preserves_original_and_is_idempotent():
    """双资源均尝试关闭，原业务异常不能被清理错误遮蔽。@return None。"""
    from dataset.util import ResultIter
    class Proxy:
        calls=0
        def keys(self):return []
        def close(self):self.calls+=1;raise OSError('close cursor')
    class Connection:
        calls=0
        def close(self):self.calls+=1
    proxy,connection=Proxy(),Connection();result=ResultIter(proxy,connection=connection)
    with pytest.raises(RuntimeError,match='business'):
        with result:raise RuntimeError('business')
    result.close();assert proxy.calls==1 and connection.calls==1
