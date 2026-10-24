"Public regression tests for DATASET-O05-DEV; the complete business contract is in materials/DATASET-O05-DEV-contract.md."
import dataset
import pytest

def test_single_pass_chunks_and_late_columns():
    "Verify single pass chunks and late columns."
    db=dataset.connect('sqlite://');t=db['items'];events=[]
    def rows():
        for n in range(5):
            if n==2:events.append(t.count())
            yield {'n':n,**({'later':'yes'} if n==4 else {})}
    assert t.insert_iter(rows(),chunk_size=2)==5 and events==[2] and t.count()==5
    assert t.find_one(n=4)['later']=='yes';db.close()

def test_atomic_generator_error_rolls_back_prior_dml():
    "Verify atomic generator error rolls back prior dml."
    db=dataset.connect('sqlite://');t=db['items'];t.insert({'n':-1})
    def broken():
        yield {'n':1};yield {'n':2};raise RuntimeError('input')
    with pytest.raises(RuntimeError):t.insert_iter(broken(),chunk_size=1,atomic=True)
    assert t.count()==1
    with pytest.raises(RuntimeError):t.insert_iter(broken(),chunk_size=1)
    assert t.count()==3;db.close()

def test_update_iter_scope_bounds_and_empty():
    "Verify update iter scope bounds and empty."
    db=dataset.connect('sqlite://');t=db['items'];t.insert_many([{'key':'a','x':1,'y':2},{'key':'b','x':3,'y':4}])
    assert t.update_iter(iter([{'key':'a','x':8},{'key':'b','y':9}]),['key'],chunk_size=2)==2
    assert t.find_one(key='a')['y']==2 and t.find_one(key='b')['x']==3
    assert t.insert_iter(iter([]))==0
    with pytest.raises(ValueError):t.insert_iter(iter([]),chunk_size=0)
    db.close()
