"Public regression tests for PYDASH-02-DEV; the complete business contract is in materials/PYDASH-02-DEV-contract.md."
import unittest
import pydash

def test_falsey_callable_gets_each_exception_and_attempt():
    "Verify falsey callable gets each exception and attempt."
    seen=[]
    class Callback:
        "Public regression fixture: Callback."
        def __bool__(self):return False
        def __call__(self,error,attempt):seen.append((str(error),attempt))
    @pydash.retry(attempts=3,delay=0,on_exception=Callback())
    def fail():raise ValueError('bad')
    with unittest.TestCase().assertRaises(ValueError):fail()
    assert seen==[('bad',1),('bad',2),('bad',3)]

def test_falsey_invalid_and_callback_exception_are_not_retried():
    "Verify falsey invalid and callback exception are not retried."
    for invalid in (False,0,'',[]):
        with unittest.TestCase().assertRaises(TypeError):pydash.retry(on_exception=invalid)
    calls=[]
    def callback(error,attempt):raise LookupError('callback')
    @pydash.retry(attempts=4,delay=0,on_exception=callback)
    def fail():calls.append(1);raise ValueError('operation')
    with unittest.TestCase().assertRaises(LookupError):fail()
    assert calls==[1]

