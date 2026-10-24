"Public regression tests for MORE-ITERTOOLS-01-DEV; the complete business contract is in materials/MORE-ITERTOOLS-01-DEV-contract.md."
import unittest
from more_itertools import map_except,filter_except

def test_transform_and_filter_errors_are_each_reported_once():
    "Verify transform and filter errors are each reported once."
    seen=[]
    rows=['1','bad','3',None]
    result=list(map_except(int,rows,ValueError,TypeError,on_error=lambda index,item,error:seen.append((index,item,type(error)))))
    assert result==[1,3] and seen==[(1,'bad',ValueError),(3,None,TypeError)]
    seen=[]
    assert list(filter_except(int,rows,ValueError,TypeError,on_error=lambda *args:seen.append(args[0])))==['1','3']
    assert seen==[1,3]

def test_lazy_falsey_callback_and_callback_failure_not_swallowed():
    "Verify lazy falsey callback and callback failure not swallowed."
    seen=[]
    class Callback:
        "Public regression fixture: Callback."
        def __bool__(self):return False
        def __call__(self,index,item,error):seen.append(index)
    values=map_except(int,['1','bad','2'],ValueError,on_error=Callback())
    assert next(values)==1 and seen==[]
    assert next(values)==2 and seen==[1]
    def fail(*args):raise ValueError('callback')
    with unittest.TestCase().assertRaisesRegex(ValueError,'callback'):list(map_except(int,['bad'],ValueError,on_error=fail))

