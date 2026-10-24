"""合法falsey回调不丢失，非法回调在调用前拒绝。"""
import unittest
import pydash

def test_falsey_callable_gets_each_exception_and_attempt():
    """失败三次时通知包含最终一次。@return None。"""
    seen=[]
    class Callback:
        """自定义假值但可调用。"""
        def __bool__(self):return False
        def __call__(self,error,attempt):seen.append((str(error),attempt))
    @pydash.retry(attempts=3,delay=0,on_exception=Callback())
    def fail():raise ValueError('bad')
    with unittest.TestCase().assertRaises(ValueError):fail()
    assert seen==[('bad',1),('bad',2),('bad',3)]

def test_falsey_invalid_and_callback_exception_are_not_retried():
    """回调本身错误不被被包装函数的重试吞掉。@return None。"""
    for invalid in (False,0,'',[]):
        with unittest.TestCase().assertRaises(TypeError):pydash.retry(on_exception=invalid)
    calls=[]
    def callback(error,attempt):raise LookupError('callback')
    @pydash.retry(attempts=4,delay=0,on_exception=callback)
    def fail():calls.append(1);raise ValueError('operation')
    with unittest.TestCase().assertRaises(LookupError):fail()
    assert calls==[1]

