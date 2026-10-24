"Public regression tests for DATASET-O04-DEV; the complete business contract is in materials/DATASET-O04-DEV-contract.md."
import dataset
import pytest

def test_real_streamed_early_exit_leaves_database_usable():
    "Verify real streamed early exit leaves database usable."
    db=dataset.connect('sqlite://');table=db['items'];table.insert_many([{'x':1},{'x':2}])
    with table.find(_streamed=True) as result:
        assert next(result)['x']==1;connection=result._conn;proxy=result.result_proxy
    assert connection.closed and proxy.closed and table.count()==2
    result.close();assert list(result)==[];db.close()

def test_conversion_error_releases_actual_result():
    "Verify conversion error releases actual result."
    db=dataset.connect('sqlite://');table=db['items'];table.insert({'x':1})
    result=table.find(_streamed=True);connection=result._conn;proxy=result.result_proxy
    def fail(items):raise ValueError('conversion')
    result.row_type=fail
    with pytest.raises(ValueError,match='conversion'):next(result)
    assert connection.closed and proxy.closed;db.close()

def test_cleanup_failure_preserves_original_and_is_idempotent():
    "Verify cleanup failure preserves original and is idempotent."
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
