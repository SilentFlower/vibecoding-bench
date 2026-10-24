"""坏行旁路通知包含精确来源，只有请求前缀才处理。"""
import unittest
from more_itertools import map_except,filter_except

def test_transform_and_filter_errors_are_each_reported_once():
    """成功路径值/身份不变，错误位置为零起始输入索引。@return None。"""
    seen=[]
    rows=['1','bad','3',None]
    result=list(map_except(int,rows,ValueError,TypeError,on_error=lambda index,item,error:seen.append((index,item,type(error)))))
    assert result==[1,3] and seen==[(1,'bad',ValueError),(3,None,TypeError)]
    seen=[]
    assert list(filter_except(int,rows,ValueError,TypeError,on_error=lambda *args:seen.append(args[0])))==['1','3']
    assert seen==[1,3]

def test_lazy_falsey_callback_and_callback_failure_not_swallowed():
    """回调抛错不被同一except再次捕获，外部throw不冒充转换错。@return None。"""
    seen=[]
    class Callback:
        """假值但可调用通知。"""
        def __bool__(self):return False
        def __call__(self,index,item,error):seen.append(index)
    values=map_except(int,['1','bad','2'],ValueError,on_error=Callback())
    assert next(values)==1 and seen==[]
    assert next(values)==2 and seen==[1]
    def fail(*args):raise ValueError('callback')
    with unittest.TestCase().assertRaisesRegex(ValueError,'callback'):list(map_except(int,['bad'],ValueError,on_error=fail))

