"""并发进度锁借用结束后即使失败也恢复原本作用域。"""
import threading
import unittest
from tqdm import tqdm
from tqdm.contrib.concurrent import ensure_lock,thread_map


def test_exception_and_nested_lock_context_restore_exact_identity():
    """异常展开和嵌套上下文逐层恢复。@return None。"""
    class Local(tqdm):
        """独立控制类避免影响全局测试进度。"""
    original=threading.RLock();temporary=threading.RLock();inner=threading.RLock();Local.set_lock(original)
    with unittest.TestCase().assertRaises(ValueError):
        with ensure_lock(Local,lock=temporary):
            assert Local.get_lock() is temporary
            with ensure_lock(Local,lock=inner):assert Local.get_lock() is inner
            assert Local.get_lock() is temporary
            raise ValueError('worker failed')
    assert Local.get_lock() is original


def test_inherited_absent_and_real_worker_failure_cleanup():
    """原无自有锁时清除临时属性，真实thread_map异常仍恢复。@return None。"""
    class Local(tqdm):
        """继承而非持有自己的锁。"""
    parent=tqdm.get_lock();assert Local.get_lock() is parent
    assert '_lock' not in Local.__dict__
    with unittest.TestCase().assertRaises(RuntimeError):
        with ensure_lock(Local,lock=threading.RLock()):raise RuntimeError('body')
    assert '_lock' not in Local.__dict__ and Local.get_lock() is parent
    def broken(value):
        """真实线程池任务失败。@param value 输入。@return 不返回。"""
        raise RuntimeError('worker')
    with unittest.TestCase().assertRaises(RuntimeError):thread_map(broken,[1],max_workers=1,tqdm_class=Local,disable=True)
    assert '_lock' not in Local.__dict__ and Local.get_lock() is parent

